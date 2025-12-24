import sqlite3
from contextlib import contextmanager
from typing import Any, List, Optional, Tuple, Dict
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


def now_iso() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds")


def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        # USERS
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

        # TEMP PASSWORD REGISTRY (Admin-only usage for distribution/export)
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_temp_passwords (
            user_id INTEGER PRIMARY KEY,
            temp_password TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)

        # EVALUATIONS
        c.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            candidate_name TEXT NOT NULL,
            level_path TEXT NOT NULL,   -- e.g. Senior Specialist → Lead Expert
            target_level TEXT NOT NULL, -- derived from level_path
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN', -- OPEN | READY_FOR_APPROVER | CLOSED
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """)

        # ASSIGNMENTS
        c.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            evaluator_role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(evaluation_id, user_id),
            FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)

        # RESPONSES (8 dimensions)
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

        # APPROVER RESPONSE
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

        # DECISIONS
        c.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL UNIQUE,
            committee_decision TEXT,
            final_decision TEXT,
            decided_by INTEGER,
            decided_at TEXT,
            FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
            FOREIGN KEY(decided_by) REFERENCES users(id)
        )
        """)


# ---------------- USERS ----------------
def user_by_username(username: str):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()


def user_by_id(user_id: int):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


def list_users(include_inactive: bool = True) -> List[sqlite3.Row]:
    q = """
    SELECT u.*,
           t.temp_password AS temp_password,
           t.created_at AS temp_password_created_at
    FROM users u
    LEFT JOIN user_temp_passwords t ON t.user_id = u.id
    """
    params: Tuple[Any, ...] = ()
    if not include_inactive:
        q += " WHERE u.is_active = 1"
    q += " ORDER BY u.created_at DESC"
    with get_conn() as conn:
        return conn.execute(q, params).fetchall()


def create_user(username: str, full_name: str, email: str, role: str, password_hash: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, full_name, email, role, password_hash, is_active, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (username, full_name, email, role, password_hash, 1, now_iso())
        )
        return int(cur.lastrowid)


def update_user(user_id: int, full_name: str, email: str, role: str, is_active: int):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET full_name=?, email=?, role=?, is_active=?
            WHERE id=?
            """,
            (full_name, email, role, int(is_active), user_id)
        )


def update_user_password_hash(user_id: int, password_hash: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))


def set_temp_password(user_id: int, temp_password: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO user_temp_passwords (user_id, temp_password, created_at)
            VALUES (?,?,?)
            ON CONFLICT(user_id)
            DO UPDATE SET temp_password=excluded.temp_password, created_at=excluded.created_at
        """, (user_id, temp_password, now_iso()))


def get_temp_password(user_id: int) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute("SELECT temp_password FROM user_temp_passwords WHERE user_id=?", (user_id,)).fetchone()
        return row["temp_password"] if row else None


# ---------------- EVALUATIONS ----------------
def create_evaluation(candidate_id: str, candidate_name: str, level_path: str, target_level: str, created_by: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO evaluations (candidate_id, candidate_name, level_path, target_level, created_by, created_at, status)
            VALUES (?,?,?,?,?,?,?)
            """,
            (candidate_id, candidate_name, level_path, target_level, created_by, now_iso(), "OPEN")
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
        return conn.execute(q, params).fetchall()


def get_evaluation(eval_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM evaluations WHERE id = ?", (eval_id,)).fetchone()


def set_evaluation_status(eval_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE evaluations SET status = ? WHERE id = ?", (status, eval_id))


# ---------------- ASSIGNMENTS ----------------
def create_assignment(eval_id: int, user_id: int, evaluator_role: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO assignments (evaluation_id, user_id, evaluator_role, created_at)
            VALUES (?,?,?,?)
            """,
            (eval_id, user_id, evaluator_role, now_iso())
        )


def list_assignments_for_evaluation(eval_id: int):
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.*, u.username, u.full_name, u.email
            FROM assignments a
            JOIN users u ON u.id = a.user_id
            WHERE a.evaluation_id = ?
            ORDER BY a.created_at ASC
        """, (eval_id,)).fetchall()


def list_assigned_evaluations_for_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("""
            SELECT e.*
            FROM assignments a
            JOIN evaluations e ON e.id = a.evaluation_id
            WHERE a.user_id = ?
            ORDER BY e.created_at DESC
        """, (user_id,)).fetchall()


def get_assignment(eval_id: int, user_id: int):
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.*, u.full_name, u.email
            FROM assignments a
            JOIN users u ON u.id = a.user_id
            WHERE a.evaluation_id = ? AND a.user_id = ?
        """, (eval_id, user_id)).fetchone()


# ---------------- RESPONSES ----------------
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


def get_response(eval_id: int, user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM responses WHERE evaluation_id = ? AND user_id = ?", (eval_id, user_id)).fetchone()


def list_responses_for_evaluation(eval_id: int):
    with get_conn() as conn:
        return conn.execute("""
            SELECT r.*, u.full_name, u.email, a.evaluator_role
            FROM responses r
            JOIN users u ON u.id = r.user_id
            JOIN assignments a ON a.evaluation_id = r.evaluation_id AND a.user_id = r.user_id
            WHERE r.evaluation_id = ?
            ORDER BY r.submitted_at ASC
        """, (eval_id,)).fetchall()


# ---------------- APPROVER RESPONSE ----------------
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


def get_approver_response(eval_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM approver_responses WHERE evaluation_id = ?", (eval_id,)).fetchone()


# ---------------- DECISIONS ----------------
def get_decision(eval_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM decisions WHERE evaluation_id = ?", (eval_id,)).fetchone()


def set_decision(eval_id: int,
                 committee_decision: Optional[str] = None,
                 final_decision: Optional[str] = None,
                 decided_by: Optional[int] = None):
    with get_conn() as conn:
        if committee_decision is not None:
            conn.execute("UPDATE decisions SET committee_decision=? WHERE evaluation_id=?", (committee_decision, eval_id))
        if final_decision is not None:
            conn.execute(
                "UPDATE decisions SET final_decision=?, decided_by=?, decided_at=? WHERE evaluation_id=?",
                (final_decision, decided_by, now_iso(), eval_id)
            )
