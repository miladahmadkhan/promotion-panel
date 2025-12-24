import streamlit as st
import pandas as pd
import secrets
import string
import io

import db
import auth
import logic


def _gen_password(n: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


def _read_user_import(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _role_choices():
    return ["ADMIN", "HRBP", "APPROVER", "EVALUATOR"]


def admin_page():
    auth.require_roles("ADMIN")
    st.header("Admin Dashboard")

    db.init_db()
    rules = logic.get_rules()
    tabs = st.tabs(["Access Management", "Create Evaluation", "Assign Evaluators", "Monitor & Close"])

    # -------------------- ACCESS MANAGEMENT --------------------
    with tabs[0]:
        st.subheader("Access Management")
        sub_tabs = st.tabs(["Create User", "Import Users (Excel/CSV)", "Users List"])

        with sub_tabs[0]:
            st.markdown("### Create user (single)")
            username = st.text_input("Username (unique)", placeholder="e.g. milad.ahmadkhan")
            full_name = st.text_input("Full name")
            email = st.text_input("Email")
            role = st.selectbox("Role", _role_choices(), index=_role_choices().index("EVALUATOR"))

            if "suggested_pass" not in st.session_state:
                st.session_state["suggested_pass"] = _gen_password()

            col1, col2 = st.columns([2, 1])
            with col1:
                password = st.text_input("Password (auto-suggested, editable)",
                                         value=st.session_state["suggested_pass"])
            with col2:
                if st.button("Regenerate", use_container_width=True):
                    st.session_state["suggested_pass"] = _gen_password()
                    st.rerun()

            if st.button("Create user", type="primary"):
                u = (username or "").strip().lower()
                if not u:
                    st.error("Username is required.")
                elif db.user_by_username(u):
                    st.error("Username already exists.")
                else:
                    uid = db.create_user(
                        username=u,
                        full_name=(full_name or "").strip() or u,
                        email=(email or "").strip() or f"{u}@example.com",
                        role=role,
                        password_hash=auth.hash_password(password.strip() or "changeme"),
                    )
                    db.set_temp_password(uid, password.strip() or "changeme")
                    st.success(f"User created: {u}")
                    st.session_state["suggested_pass"] = _gen_password()
                    st.rerun()

        with sub_tabs[1]:
            st.markdown("### Import users from Excel/CSV")
            st.info(
                "Template columns: **username, full_name, email, role, password**\n\n"
                "- password can be empty → system generates.\n"
                "- role must be ADMIN/HRBP/APPROVER/EVALUATOR."
            )

            template_df = pd.DataFrame([{
                "username": "example.user",
                "full_name": "Example User",
                "email": "example.user@digikala.com",
                "role": "EVALUATOR",
                "password": ""
            }])
            st.download_button(
                "Download import template (Excel)",
                data=_to_excel_bytes(template_df, "template"),
                file_name="user_import_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            up = st.file_uploader("Upload Excel/CSV", type=["xlsx", "csv"])
            if up is not None:
                try:
                    df = _read_user_import(up)
                except Exception as e:
                    st.error(f"Could not read file: {e}")
                    df = None

                if df is not None:
                    required = {"username", "full_name", "email", "role"}
                    missing = [c for c in required if c not in df.columns]
                    if missing:
                        st.error(f"Missing columns: {missing}")
                    else:
                        if "password" not in df.columns:
                            df["password"] = ""

                        created_rows, skipped_rows = [], []

                        for _, row in df.iterrows():
                            u = str(row.get("username", "")).strip().lower()
                            if not u:
                                skipped_rows.append({"username": "", "reason": "empty username"})
                                continue
                            if db.user_by_username(u):
                                skipped_rows.append({"username": u, "reason": "already exists"})
                                continue

                            r = str(row.get("role", "")).strip().upper()
                            if r not in _role_choices():
                                skipped_rows.append({"username": u, "reason": f"invalid role: {r}"})
                                continue

                            pwd = str(row.get("password", "")).strip() or _gen_password()

                            uid = db.create_user(
                                username=u,
                                full_name=str(row.get("full_name", "")).strip() or u,
                                email=str(row.get("email", "")).strip() or f"{u}@example.com",
                                role=r,
                                password_hash=auth.hash_password(pwd),
                            )
                            db.set_temp_password(uid, pwd)

                            created_rows.append({
                                "username": u,
                                "full_name": str(row.get("full_name", "")).strip() or u,
                                "email": str(row.get("email", "")).strip() or f"{u}@example.com",
                                "role": r,
                                "password": pwd,
                            })

                        if created_rows:
                            out_df = pd.DataFrame(created_rows)
                            st.success(f"Imported {len(created_rows)} users.")
                            st.dataframe(out_df, use_container_width=True)
                            st.download_button(
                                "Download created users (Excel)",
                                data=_to_excel_bytes(out_df, "created_users"),
                                file_name="created_users_with_passwords.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                        if skipped_rows:
                            st.warning(f"Skipped {len(skipped_rows)} rows.")
                            st.dataframe(pd.DataFrame(skipped_rows), use_container_width=True)

        with sub_tabs[2]:
            st.markdown("### Users list")
            show_inactive = st.checkbox("Show inactive users", value=True)
            q = st.text_input("Search (username / name / email)", placeholder="type to filter...").strip().lower()

            users = db.list_users(include_inactive=show_inactive)
            rows = []
            for u in users:
                label = f"{u['username']} {u['full_name']} {u['email']} {u['role']}".lower()
                if q and q not in label:
                    continue
                rows.append({
                    "id": int(u["id"]),
                    "username": u["username"],
                    "full_name": u["full_name"],
                    "email": u["email"],
                    "role": u["role"],
                    "is_active": int(u["is_active"]),
                    "temp_password": u["temp_password"] or "",
                    "temp_password_created_at": u["temp_password_created_at"] or "",
                    "created_at": u["created_at"],
                })

            if rows:
                dfu = pd.DataFrame(rows)
                st.dataframe(dfu, use_container_width=True)
                st.download_button(
                    "Download users (Excel)",
                    data=_to_excel_bytes(dfu, "users"),
                    file_name="users_access_list.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.info("No users match your filter.")

    # -------------------- CREATE EVALUATION --------------------
    with tabs[1]:
        st.subheader("Create Evaluation")
        candidate_id = st.text_input("Candidate ID", placeholder="e.g. DK-12345")
        candidate_name = st.text_input("Candidate Name")
        level_path = st.selectbox("Promotion Path (from Sheet2)", rules.level_paths)
        target_level = logic.level_path_to_target_level(level_path)
        st.caption(f"Target level derived: **{target_level}**")

        if st.button("Create Evaluation", type="primary"):
            if not candidate_id.strip() or not candidate_name.strip():
                st.error("Candidate ID and Name are required.")
            else:
                eval_id = db.create_evaluation(
                    candidate_id=candidate_id.strip(),
                    candidate_name=candidate_name.strip(),
                    level_path=level_path,
                    target_level=target_level,
                    created_by=auth.current_user()["id"],
                )
                st.success(f"Evaluation created (ID: {eval_id})")

    # -------------------- ASSIGN EVALUATORS --------------------
    with tabs[2]:
        st.subheader("Assign Evaluators")

        evals = db.list_evaluations()
        if not evals:
            st.info("No evaluations yet.")
            return

        q = st.text_input("Search candidate", placeholder="type to filter candidate list...").strip().lower()

        def _eval_label(e):
            return f"{e['candidate_name']} | {e['level_path']} | #{e['id']}"

        filtered = [e for e in evals if (not q) or q in _eval_label(e).lower() or q in str(e["candidate_id"]).lower()]
        if not filtered:
            st.warning("No evaluations match your search.")
            return

        eval_id = st.selectbox(
            "Select evaluation",
            options=[e["id"] for e in filtered],
            format_func=lambda eid: _eval_label(db.get_evaluation(eid))
        )
        ev = db.get_evaluation(int(eval_id))

        allowed_roles = logic.allowed_evaluator_roles_by_level_path(ev["level_path"])
        st.caption(f"Allowed evaluator roles: {', '.join(allowed_roles)}")

        # ✅ IMPORTANT CHANGE: any active user (except ADMIN) can be an evaluator
        all_users = db.list_users(include_inactive=False)
        eligible = [u for u in all_users if int(u["is_active"]) == 1 and u["role"] != "ADMIN"]

        if not eligible:
            st.warning("No eligible users found. Create/import users in Access Management first.")
            return

        uq = st.text_input("Search user", placeholder="type username/name/email...").strip().lower()
        eligible_filtered = []
        for u in eligible:
            s = f"{u['username']} {u['full_name']} {u['email']} {u['role']}".lower()
            if (not uq) or uq in s:
                eligible_filtered.append(u)

        if not eligible_filtered:
            st.info("No users match your search.")
            return

        user_id = st.selectbox(
            "Select user to assign as evaluator",
            options=[int(u["id"]) for u in eligible_filtered],
            format_func=lambda uid: next(
                (f"{u['full_name']} ({u['username']}) - {u['email']} | role={u['role']}"
                 for u in eligible_filtered if int(u["id"]) == int(uid)),
                str(uid)
            )
        )

        evaluator_role = st.selectbox("Evaluator role for this evaluation", allowed_roles)

        if st.button("Assign evaluator", type="primary"):
            db.create_assignment(int(eval_id), int(user_id), evaluator_role)
            st.success("Assigned.")
            st.rerun()

        st.markdown("### Current assignments")
        assigns = db.list_assignments_for_evaluation(int(eval_id))
        if assigns:
            df = pd.DataFrame([{
                "Name": a["full_name"],
                "Email": a["email"],
                "Username": a["username"],
                "User Role": db.user_by_id(int(a["user_id"]))["role"],
                "Evaluator Role (weight role)": a["evaluator_role"],
            } for a in assigns])
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "Download assignments (Excel)",
                data=_to_excel_bytes(df, "assignments"),
                file_name=f"assignments_eval_{eval_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("No assignments yet.")

    # -------------------- MONITOR & CLOSE --------------------
    with tabs[3]:
        st.subheader("Monitor & Close")
        evals = db.list_evaluations()
        if not evals:
            st.info("No evaluations yet.")
            return

        eval_id = st.selectbox(
            "Select Evaluation",
            options=[e["id"] for e in evals],
            format_func=lambda eid: f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | {db.get_evaluation(eid)['level_path']} | {db.get_evaluation(eid)['status']}"
        )

        ev = db.get_evaluation(int(eval_id))
        assigns = db.list_assignments_for_evaluation(int(eval_id))
        responses = db.list_responses_for_evaluation(int(eval_id))

        st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
        st.write(f"**Promotion Path:** {ev['level_path']}")
        st.write(f"**Status:** {ev['status']}")
        st.write(f"Assigned: **{len(assigns)}** | Submitted: **{len(responses)}**")

        agg = logic.committee_aggregate(int(eval_id))
        if agg["committee_decision"] == "Pending":
            st.info(f"Pending: {agg['responded_count']}/{agg['assigned_count']} submitted.")
        else:
            st.success(f"Committee Decision: **{agg['committee_decision']}**")

        if st.button("Recompute committee decision"):
            agg = logic.committee_aggregate(int(eval_id))
            db.set_decision(int(eval_id), committee_decision=agg["committee_decision"])
            st.success("Recomputed & saved committee decision.")

        st.markdown("### Close phase")
        if ev["target_level"] in ("Principal", "Distinguished"):
            if st.button("Move to Approver (READY_FOR_APPROVER)", type="primary"):
                db.set_evaluation_status(int(eval_id), "READY_FOR_APPROVER")
                st.success("Moved to READY_FOR_APPROVER.")
                st.rerun()
        else:
            if st.button("Close evaluation (CLOSED)", type="primary"):
                db.set_evaluation_status(int(eval_id), "CLOSED")
                st.success("Closed.")
                st.rerun()
