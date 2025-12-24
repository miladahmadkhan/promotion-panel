import os
import bcrypt
import streamlit as st
import sqlite3
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
    Race-safe bootstrap users.
    - If user exists -> do nothing
    - If created concurrently -> ignore IntegrityError
    """
    admin_user = st.secrets.get("ADMIN_USER", os.environ.get("ADMIN_USER", "admin")).strip()
    admin_pass = st.secrets.get("ADMIN_PASS", os.environ.get("ADMIN_PASS", "admin")).strip()
    admin_email = st.secrets.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@example.com")).strip()
    admin_name = st.secrets.get("ADMIN_NAME", os.environ.get("ADMIN_NAME", "Admin")).strip()

    hrbp_user = st.secrets.get("HRBP_USER", os.environ.get("HRBP_USER", "hrbp")).strip()
    hrbp_pass = st.secrets.get("HRBP_PASS", os.environ.get("HRBP_PASS", "hrbp")).strip()
    hrbp_email = st.secrets.get("HRBP_EMAIL", os.environ.get("HRBP_EMAIL", "hrbp@example.com")).strip()
    hrbp_name = st.secrets.get("HRBP_NAME", os.environ.get("HRBP_NAME", "HRBP")).strip()

    appr_user = st.secrets.get("APPROVER_USER", os.environ.get("APPROVER_USER", "approver")).strip()
    appr_pass = st.secrets.get("APPROVER_PASS", os.environ.get("APPROVER_PASS", "approver")).strip()
    appr_email = st.secrets.get("APPROVER_EMAIL", os.environ.g
