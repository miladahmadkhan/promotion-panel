import os
import bcrypt
import streamlit as st
from typing import Optional, Dict, Any
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


def ensure_bootstrap_users():
    """
    Creates Admin/HRBP/Approver from st.secrets or env vars if they don't exist.
    This is useful for first run on Streamlit Cloud.
    """
    # Admin
    admin_user = st.secrets.get("ADMIN_USER", os.environ.get("ADMIN_USER", "admin"))
    admin_pass = st.secrets.get("ADMIN_PASS", os.environ.get("ADMIN_PASS", "admin"))
    admin_email = st.secrets.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@example.com"))
    admin_name = st.secrets.get("ADMIN_NAME", os.environ.get("ADMIN_NAME", "Admin"))

    # HRBP
    hrbp_user = st.secrets.get("HRBP_USER", os.environ.get("HRBP_USER", "hrbp"))
    hrbp_pass = st.secrets.get("HRBP_PASS", os.environ.get("HRBP_PASS", "hrbp"))
    hrbp_email = st.secrets.get("HRBP_EMAIL", os.environ.get("HRBP_EMAIL", "hrbp@example.com"))
    hrbp_name = st.secrets.get("HRBP_NAME", os.environ.get("HRBP_NAME", "HRBP"))

    # Approver
    appr_user = st.secrets.get("APPROVER_USER", os.environ.get("APPROVER_USER", "approver"))
    appr_pass = st.secrets.get("APPROVER_PASS", os.environ.get("APPROVER_PASS", "approver"))
    appr_email = st.secrets.get("APPROVER_EMAIL", os.environ.get("APPROVER_EMAIL", "approver@example.com"))
    appr_name = st.secrets.get("APPROVER_NAME", os.environ.get("APPROVER_NAME", "Final Approver"))

    def ensure_one(username: str, full_name: str, email: str, role: str, password: str):
        u = db.user_by_username(username)
        if u:
            return
        db.create_user(
            username=username,
            full_name=full_name,
            email=email,
            role=role,
            password_hash=hash_password(password),
        )

    ensure_one(admin_user, admin_name, admin_email, "ADMIN", admin_pass)
    ensure_one(hrbp_user, hrbp_name, hrbp_email, "HRBP", hrbp_pass)
    ensure_one(appr_user, appr_name, appr_email, "APPROVER", appr_pass)


def current_user() -> Optional[Dict[str, Any]]:
    return st.session_state.get("user")


def logout():
    if "user" in st.session_state:
        del st.session_state["user"]
    st.rerun()


def login_screen():
    st.subheader("Login")
    qp = st.query_params
    default_username = qp.get("username", "")

    username = st.text_input("Username", value=default_username)
    password = st.text_input("Password", type="password")

    if st.button("Login", type="primary"):
        u = db.user_by_username(username.strip())
        if not u or int(u["is_active"]) != 1:
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
