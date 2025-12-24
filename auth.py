import os
import sqlite3
from typing import Optional, Dict, Any

import bcrypt
import streamlit as st

import db


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def ensure_bootstrap_users() -> None:
    """
    Creates bootstrap users (ADMIN/HRBP/APPROVER) safely.
    - idempotent
    - safe against Streamlit reruns / concurrent startup
    """
    def _get(key: str, default: str) -> str:
        # secrets may not exist in local runs
        try:
            v = st.secrets.get(key, os.environ.get(key, default))
        except Exception:
            v = os.environ.get(key, default)
        return str(v).strip()

    admin_user = _get("ADMIN_USER", "admin")
    admin_pass = _get("ADMIN_PASS", "admin")
    admin_email = _get("ADMIN_EMAIL", "admin@example.com")
    admin_name = _get("ADMIN_NAME", "Admin")

    hrbp_user = _get("HRBP_USER", "hrbp")
    hrbp_pass = _get("HRBP_PASS", "hrbp")
    hrbp_email = _get("HRBP_EMAIL", "hrbp@example.com")
    hrbp_name = _get("HRBP_NAME", "HRBP")

    appr_user = _get("APPROVER_USER", "approver")
    appr_pass = _get("APPROVER_PASS", "approver")
    appr_email = _get("APPROVER_EMAIL", "approver@example.com")
    appr_name = _get("APPROVER_NAME", "Final Approver")

    def ensure_one(username: str, full_name: str, email: str, role: str, password: str) -> None:
        username = (username or "").strip()
        if not username:
            return

        existing = db.user_by_username(username)
        if existing:
            return

        try:
            db.create_user(
                username=username,
                full_name=(full_name or "").strip() or username,
                email=(email or "").strip() or f"{username}@example.com",
                role=role,
                password_hash=hash_password(password or "changeme"),
            )
        except sqlite3.IntegrityError:
            # created concurrently in another rerun/worker
            return

    ensure_one(admin_user, admin_name, admin_email, "ADMIN", admin_pass)
    ensure_one(hrbp_user, hrbp_name, hrbp_email, "HRBP", hrbp_pass)
    ensure_one(appr_user, appr_name, appr_email, "APPROVER", appr_pass)


def current_user() -> Optional[Dict[str, Any]]:
    return st.session_state.get("user")


def logout() -> None:
    if "user" in st.session_state:
        del st.session_state["user"]
    st.rerun()


def login_screen() -> None:
    st.subheader("Login")

    qp = st.query_params
    default_username = qp.get("username", "")

    username = st.text_input("Username", value=str(default_username))
    password = st.text_input("Password", type="password")

    if st.button("Login", type="primary"):
        u = db.user_by_username(username.strip())
        if (not u) or (int(u["is_active"]) != 1):
            st.error("Invalid username/password")
            return

        if not verify_password(password, u["password_hash"]):
            st.error("Invalid username/password")
            return

        st.session_state["user"] = {
            "id": int(u["id"]),
            "username": u["username"],
            "full_name": u["full_name"],
            "email": u["email"],
            "role": u["role"],
        }
        st.success("Logged in")
        st.rerun()


def require_roles(*roles: str) -> Dict[str, Any]:
    u = current_user()
    if not u:
        st.warning("Please log in.")
        login_screen()
        st.stop()

    if u["role"] not in roles:
        st.error("You do not have access to this section.")
        st.stop()

    return u
