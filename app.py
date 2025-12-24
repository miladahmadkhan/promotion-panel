import streamlit as st
import db
import auth
from ui_admin import admin_page
from ui_evaluator import evaluator_page
from ui_hrbp import hrbp_page
from ui_approver import approver_page

st.set_page_config(page_title="Promotion Panel Tool", layout="wide")

# init db + bootstrap users
db.init_db()
auth.ensure_bootstrap_users()

st.sidebar.title("Promotion Panel Tool")

u = auth.current_user()
if not u:
    auth.login_screen()
    st.stop()

st.sidebar.write(f"**User:** {u['full_name']}")
st.sidebar.write(f"**Role:** {u['role']}")

if st.sidebar.button("Logout"):
    auth.logout()

# Route by role
role = u["role"]
if role == "ADMIN":
    admin_page()
elif role == "EVALUATOR":
    evaluator_page()
elif role == "HRBP":
    hrbp_page()
elif role == "APPROVER":
    approver_page()
else:
    st.error("Unknown role.")


