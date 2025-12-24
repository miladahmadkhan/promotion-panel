import sqlite3
from contextlib import contextmanager
from typing import Any, List, Optional, Tuple
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


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


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
        CREATE TABLE IF NOT EXISTS user_temp_passwords (
            user_id INTEGER PRIMARY KEY,
            temp_password TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS hrbp_departments (
            hrbp_user_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (hrbp_user_id, department_id),
            FOREIGN KEY(hrbp_user_id) REFERENCES users(id),
            FOREIGN KEY(department_id) REFERENCES departments(id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            candidate_name TEXT NOT NULL,
            level_path TEXT NOT NULL,
            target_level TEXT NOT NULL,
            department TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """)

        if not _table_has_column(conn, "evaluations", "department"):
            conn.execute("ALTER TABLE evaluations ADD COLUMN department TEXT")

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
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users(include_inactive: bool = True) -> List[sqlite3.Row]:
    q = """
    SELECT u.*,
           t.temp_password AS temp_password,
           t.created_at AS temp_password_created_at
    FROM users u
    LEFT JOIN user_temp_passwords t ON t.user_id = u.id
    """
    if not include_inactive:
        q += " WHERE u.is_active = 1"
    q += " ORDER BY u.created_at DESC"
    with get_conn() as conn:
        return conn.execute(q).fetchall()


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
            UPDATE users SET full_name=?, email=?, role=?, is_active=?
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


def delete_user(user_id: int):
    """
    Hard delete user and related data.
    NOTE: This removes historical votes/assignments for that user.
    """
    with get_conn() as conn:
        conn.execute("DELETE FROM user_temp_passwords WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM hrbp_departments WHERE hrbp_user_id=?", (user_id,))
        conn.execute("DELETE FROM responses WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM assignments WHERE user_id=?", (user_id,))
        # approver_responses references approver_user_id (rare)
        conn.execute("DELETE FROM approver_responses WHERE approver_user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))


# ---------------- DEPARTMENTS ----------------
def create_department(name: str) -> Optional[int]:
    name = (name or "").strip()
    if not name:
        return None
    with get_conn() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO departments (name, created_at) VALUES (?,?)", (name, now_iso()))
        if cur.rowcount == 0:
            return None
        return int(cur.lastrowid)


def bulk_upsert_departments(names: List[str]) -> dict:
    cleaned = []
    seen = set()
    for n in names:
        n = (str(n) if n is not None else "").strip()
        if not n:
            continue
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(n)

    created = 0
    with get_conn() as conn:
        for n in cleaned:
            cur = conn.execute("INSERT OR IGNORE INTO departments (name, created_at) VALUES (?,?)", (n, now_iso()))
            if cur.rowcount == 1:
                created += 1

    return {"input": len(names), "cleaned": len(cleaned), "created": created, "skipped_existing": len(cleaned) - created}


def list_departments() -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM departments ORDER BY name ASC").fetchall()


def delete_department(dept_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM hrbp_departments WHERE department_id=?", (dept_id,))
        conn.execute("DELETE FROM departments WHERE id=?", (dept_id,))


# ---------------- HRBP <-> Department mapping (both directions) ----------------
def get_hrbp_department_names(hrbp_user_id: int) -> List[str]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT d.name
            FROM hrbp_departments hd
            JOIN departments d ON d.id = hd.department_id
            WHERE hd.hrbp_user_id = ?
            ORDER BY d.name ASC
        """, (hrbp_user_id,)).fetchall()
        return [r["name"] for r in rows]


def get_department_hrbps(dept_id: int) -> List[sqlite3.Row]:
    """
    Returns HRBP users linked to a department.
    """
    with get_conn() as conn:
        return conn.execute("""
            SELECT u.*
            FROM hrbp_departments hd
            JOIN users u ON u.id = hd.hrbp_user_id
            WHERE hd.department_id = ?
            ORDER BY u.full_name ASC
        """, (dept_id,)).fetchall()


def set_department_hrbps(dept_id: int, hrbp_user_ids: List[int]):
    """
    Sets HRBPs for a department. Also auto-upgrades their role to HRBP (requirement).
    """
    hrbp_user_ids = sorted({int(x) for x in hrbp_user_ids})
    with get_conn() as conn:
        conn.execute("DELETE FROM hrbp_departments WHERE department_id=?", (int(dept_id),))
        for uid in hrbp_user_ids:
            conn.execute(
                "INSERT OR IGNORE INTO hrbp_departments (hrbp_user_id, department_id, created_at) VALUES (?,?,?)",
                (uid, int(dept_id), now_iso())
            )
            # Auto-set access: user becomes HRBP
            conn.execute("UPDATE users SET role='HRBP', is_active=1 WHERE id=?", (uid,))


def list_hrbp_users(include_inactive: bool = False) -> List[sqlite3.Row]:
    q = "SELECT * FROM users WHERE role='HRBP'"
    if not include_inactive:
        q += " AND is_active=1"
    q += " ORDER BY full_name ASC"
    with get_conn() as conn:
        return conn.execute(q).fetchall()


def list_non_admin_active_users() -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE is_active=1 AND role<>'ADMIN' ORDER BY full_name ASC").fetchall()


# ---------------- EVALUATIONS ----------------
def create_evaluation(candidate_id: str, candidate_name: str, level_path: str, target_level: str,
                      department: str, created_by: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO evaluations (candidate_id, candidate_name, level_path, target_level, department, created_by, created_at, status)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (candidate_id, candidate_name, level_path, target_level, (department or "").strip(), created_by, now_iso(), "OPEN")
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


def list_evaluations_by_departments(departments: List[str]) -> List[sqlite3.Row]:
    departments = [d.strip() for d in departments if d and d.strip()]
    if not departments:
        return []
    placeholders = ",".join(["?"] * len(departments))
    q = f"SELECT * FROM evaluations WHERE department IN ({placeholders}) ORDER BY created_at DESC"
    with get_conn() as conn:
        return conn.execute(q, tuple(departments)).fetchall()


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


def list_assigned_evaluations_for_user_in_departments(user_id: int, departments: List[str]):
    departments = [d.strip() for d in departments if d and d.strip()]
    if not departments:
        return []
    placeholders = ",".join(["?"] * len(departments))
    q = f"""
        SELECT e.*
        FROM assignments a
        JOIN evaluations e ON e.id = a.evaluation_id
        WHERE a.user_id = ? AND e.department IN ({placeholders})
        ORDER BY e.created_at DESC
    """
    params = (user_id, *departments)
    with get_conn() as conn:
        return conn.execute(q, params).fetchall()


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


# ---------------- ADMIN ORG REPORTS ----------------
def org_summary_report(start_iso: str, end_iso: str) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("""
            SELECT
                e.target_level AS target_level,
                COALESCE(NULLIF(d.final_decision,''), NULLIF(d.committee_decision,''), 'Pending') AS decision,
                COUNT(*) AS cnt
            FROM evaluations e
            LEFT JOIN decisions d ON d.evaluation_id = e.id
            WHERE e.created_at >= ? AND e.created_at < ?
            GROUP BY e.target_level, decision
            ORDER BY e.target_level, decision
        """, (start_iso, end_iso)).fetchall()
