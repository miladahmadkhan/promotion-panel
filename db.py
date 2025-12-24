import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple
import os
import datetime as dt

DB_PATH = os.environ.get("PP_DB_PATH", "app.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL, -- ADMIN | EVALUATOR | HRBP | APPROVER
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            candidate_name TEXT NOT NULL,
            target_level TEXT NOT NULL, -- Senior Specialist | Lead Expert | Advanced Expert | Principal | Distinguished
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN', -- OPEN | READY_FOR_APPROVER | CLOSED
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            evaluator_role TEXT NOT NULL, -- e.g. Line Manager, OPD...
            created_at TEXT NOT NULL,
            UNIQUE(evaluation_id, user_id),
            FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)

        # One response per evaluator per evaluation
        c.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            dim1 TEXT NOT NULL,
            dim2 TEXT NOT NULL,
            dim3 TEXT NOT NULL,
            dim4 TEXT NOT NULL,
            dim5 TEXT NOT NULL,
            dim6 TEXT NOT NULL,
            dim7 TEXT NOT NULL,
            dim8 TEXT NOT NULL,
            comment TEXT,
            UNIQUE(evaluation_id, user_id),
            FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)

        # One approver response per evaluation (only for Principal/Distinguished)
        c.execute("""
        CREATE TABLE IF NOT EXISTS approver_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL UNIQUE,
            approver_user_id INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            dim1 TEXT NOT NULL,
            dim2 TEXT NOT NULL,
            dim3 TEXT NOT NULL,
            dim4 TEXT NOT NULL,
            dim5 TEXT NOT NULL,
            dim6 TEXT NOT NULL,
            dim7 TEXT NOT NULL,
            dim8 TEXT NOT NULL,
            comment TEXT,
            FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
            FOREIGN KEY(approver_user_id) REFERENCES users(id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL UNIQUE,
            committee_decision TEXT, -- Confirmed | Reject | Pending | RecommendationOnly
            final_decision TEXT,     -- Confirmed | Reject | Pending
            decided_by INTEGER,
            decided_at TEXT,
            FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
            FOREIGN KEY(decided_by) REFERENCES users(id)
        )
        """)


def now_iso() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds")


# ---------- USERS ----------
def user_by_username(username: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()


def user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


def create_user(username: str, full_name: str, email: str, role: str, password_hash: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, full_name, email, role, password_hash, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
            (username, full_name, email, role, password_hash, 1, now_iso())
        )
        return int(cur.lastrowid)


def list_users_by_role(role: str) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE role = ? AND is_active = 1 ORDER BY full_name", (role,))
        return cur.fetchall()


# ---------- EVALUATIONS ----------
def create_evaluation(candidate_id: str, candidate_name: str, target_level: str, created_by: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO evaluations (candidate_id, candidate_name, target_level, created_by, created_at, status) VALUES (?,?,?,?,?,?)",
            (candidate_id, candidate_name, target_level, created_by, now_iso(), "OPEN")
        )
        eval_id = int(cur.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO decisions (evaluation_id, committee_decision, final_decision) VALUES (?,?,?)",
            (eval_id, "Pending", "Pending")
        )
        return eval_id


def list_evaluations(status: Optional[str] = None) -> List[sqlite3.Row]:
    q = "SELECT * FROM evaluations"
    params: Tuple[Any, ...] = ()
    if status:
        q += " WHERE status = ?"
        params = (status,)
    q += " ORDER BY created_at DESC"
    with get_conn() as conn:
        cur = conn.execute(q, params)
        return cur.fetchall()


def get_evaluation(eval_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM evaluations WHERE id = ?", (eval_id,))
        return cur.fetchone()


def set_evaluation_status(eval_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE evaluations SET status = ? WHERE id = ?", (status, eval_id))


# ---------- ASSIGNMENTS ----------
def create_assignment(eval_id: int, user_id: int, evaluator_role: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO assignments (evaluation_id, user_id, evaluator_role, created_at) VALUES (?,?,?,?)",
            (eval_id, user_id, evaluator_role, now_iso())
        )


def list_assignments_for_evaluation(eval_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT a.*, u.username, u.full_name, u.email
            FROM assignments a
            JOIN users u ON u.id = a.user_id
            WHERE a.evaluation_id = ?
            ORDER BY a.created_at ASC
        """, (eval_id,))
        return cur.fetchall()


def list_assigned_evaluations_for_user(user_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT e.*
            FROM assignments a
            JOIN evaluations e ON e.id = a.evaluation_id
            WHERE a.user_id = ?
            ORDER BY e.created_at DESC
        """, (user_id,))
        return cur.fetchall()


def get_assignment(eval_id: int, user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT a.*, u.full_name, u.email
            FROM assignments a
            JOIN users u ON u.id = a.user_id
            WHERE a.evaluation_id = ? AND a.user_id = ?
        """, (eval_id, user_id))
        return cur.fetchone()


# ---------- RESPONSES ----------
def upsert_response(eval_id: int, user_id: int, dims: List[str], comment: Optional[str]):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO responses (evaluation_id, user_id, submitted_at, dim1, dim2, dim3, dim4, dim5, dim6, dim7, dim8, comment)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(evaluation_id, user_id)
        DO UPDATE SET
            submitted_at=excluded.submitted_at,
            dim1=excluded.dim1,
            dim2=excluded.dim2,
            dim3=excluded.dim3,
            dim4=excluded.dim4,
            dim5=excluded.dim5,
            dim6=excluded.dim6,
            dim7=excluded.dim7,
            dim8=excluded.dim8,
            comment=excluded.comment
        """, (eval_id, user_id, now_iso(), *dims, comment))


def get_response(eval_id: int, user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM responses WHERE evaluation_id = ? AND user_id = ?", (eval_id, user_id))
        return cur.fetchone()


def list_responses_for_evaluation(eval_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT r.*, u.full_name, u.email, a.evaluator_role
            FROM responses r
            JOIN users u ON u.id = r.user_id
            JOIN assignments a ON a.evaluation_id = r.evaluation_id AND a.user_id = r.user_id
            WHERE r.evaluation_id = ?
            ORDER BY r.submitted_at ASC
        """, (eval_id,))
        return cur.fetchall()


# ---------- APPROVER RESPONSE ----------
def upsert_approver_response(eval_id: int, approver_user_id: int, dims: List[str], comment: Optional[str]):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO approver_responses (evaluation_id, approver_user_id, submitted_at, dim1, dim2, dim3, dim4, dim5, dim6, dim7, dim8, comment)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(evaluation_id)
        DO UPDATE SET
            approver_user_id=excluded.approver_user_id,
            submitted_at=excluded.submitted_at,
            dim1=excluded.dim1,
            dim2=excluded.dim2,
            dim3=excluded.dim3,
            dim4=excluded.dim4,
            dim5=excluded.dim5,
            dim6=excluded.dim6,
            dim7=excluded.dim7,
            dim8=excluded.dim8,
            comment=excluded.comment
        """, (eval_id, approver_user_id, now_iso(), *dims, comment))


def get_approver_response(eval_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM approver_responses WHERE evaluation_id = ?", (eval_id,))
        return cur.fetchone()


# ---------- DECISIONS ----------
def get_decision(eval_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM decisions WHERE evaluation_id = ?", (eval_id,))
        return cur.fetchone()


def set_decision(eval_id: int, committee_decision: Optional[str] = None, final_decision: Optional[str] = None,
                 decided_by: Optional[int] = None):
    with get_conn() as conn:
        d = get_decision(eval_id)
        if not d:
            conn.execute("INSERT INTO decisions (evaluation_id, committee_decision, final_decision) VALUES (?,?,?)",
                         (eval_id, committee_decision or "Pending", final_decision or "Pending"))
            return
        if committee_decision is not None:
            conn.execute("UPDATE decisions SET committee_decision=? WHERE evaluation_id=?", (committee_decision, eval_id))
        if final_decision is not None:
            conn.execute(
                "UPDATE decisions SET final_decision=?, decided_by=?, decided_at=? WHERE evaluation_id=?",
                (final_decision, decided_by, now_iso(), eval_id)
            )
