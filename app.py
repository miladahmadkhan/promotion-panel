import streamlit as st

import db
import auth

from ui_admin import admin_page
from ui_hrbp import hrbp_page
from ui_approver import approver_page
from ui_evaluator import evaluator_page


def main():
    st.set_page_config(
        page_title="Promotion Panel",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Ensure DB tables exist
    db.init_db()

    # Create bootstrap users safely (ADMIN/HRBP/APPROVER) based on secrets/env
    auth.ensure_bootstrap_users()

    # If not logged in -> show login screen
    u = auth.current_user()
    if not u:
        auth.login_screen()
        st.stop()

    role = u["role"]

    # Sidebar
    with st.sidebar:
        st.markdown("## Promotion Panel")
        st.write(f"**User:** {u['full_name']}")
        st.write(f"**Username:** {u['username']}")
        st.write(f"**Role:** {role}")
        st.divider()

        if st.button("Logout"):
            auth.logout()

    # Route UI by role
    if role == "ADMIN":
        admin_page()
    elif role == "HRBP":
        # HRBP sees HRBP dashboard (includes reports + my evaluations)
        hrbp_page()
    elif role == "APPROVER":
        approver_page()
    else:
        # Default: EVALUATOR and any future roles
        evaluator_page()


if __name__ == "__main__":
    main()
