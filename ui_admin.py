import streamlit as st
import pandas as pd
import secrets
import string
import io
import datetime as dt

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


def _iso(d: dt.date) -> str:
    return dt.datetime(d.year, d.month, d.day).isoformat(timespec="seconds")


def _read_departments_excel(file) -> list:
    df = pd.read_excel(file)
    cols = list(df.columns)

    preferred = None
    for c in cols:
        if str(c).strip().lower() == "dept level 2":
            preferred = c
            break
    if preferred is None:
        for c in cols:
            cl = str(c).strip().lower()
            if "dept" in cl or "department" in cl:
                preferred = c
                break
    if preferred is None and cols:
        preferred = cols[0]
    if preferred is None:
        return []

    return df[preferred].tolist()


def admin_page():
    auth.require_roles("ADMIN")
    st.header("Admin Dashboard")

    db.init_db()
    rules = logic.get_rules()

    tabs = st.tabs([
        "Departments",
        "Department ↔ HRBP Mapping",
        "Access Management",
        "Create Evaluation",
        "Assign Evaluators",
        "Org Reports",
        "Monitor & Close",
    ])

    # -------------------- DEPARTMENTS --------------------
    with tabs[0]:
        st.subheader("Departments")

        st.markdown("### Bulk import from Excel")
        up = st.file_uploader("Upload departments.xlsx", type=["xlsx"])
        if up is not None:
            try:
                names = _read_departments_excel(up)
                preview = [str(x).strip() for x in names if str(x).strip()]
                st.write(f"Found **{len(preview)}** department rows in file.")
                st.dataframe(pd.DataFrame({"department_name": preview}).head(50), use_container_width=True)

                if st.button("Import departments from file", type="primary"):
                    stats = db.bulk_upsert_departments(preview)
                    st.success(
                        f"Imported successfully. Created={stats['created']} | "
                        f"Skipped(existing)={stats['skipped_existing']} | Cleaned={stats['cleaned']}"
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"Could not read/import file: {e}")

        st.divider()
        st.markdown("### Add single department")
        col1, col2 = st.columns([2, 1])
        with col1:
            new_dept = st.text_input("New department name")
        with col2:
            if st.button("Add department"):
                if not new_dept.strip():
                    st.error("Department name is required.")
                else:
                    db.create_department(new_dept.strip())
                    st.success("Added.")
                    st.rerun()

        st.divider()
        st.markdown("### Current departments")
        depts = db.list_departments()
        if not depts:
            st.info("No departments yet.")
        else:
            df = pd.DataFrame([{"id": int(d["id"]), "name": d["name"]} for d in depts])
            st.dataframe(df, use_container_width=True)

    # -------------------- Department ↔ HRBP Mapping (NEW) --------------------
    with tabs[1]:
        st.subheader("Department ↔ HRBP Mapping")
        depts = db.list_departments()
        if not depts:
            st.warning("Import/create departments first.")
        else:
            dept_id = st.selectbox(
                "Select department",
                options=[int(d["id"]) for d in depts],
                format_func=lambda i: next((d["name"] for d in depts if int(d["id"]) == int(i)), str(i))
            )

            # Eligible users: all active non-admin users (admin can't be HRBP)
            eligible = db.list_non_admin_active_users()
            if not eligible:
                st.warning("No eligible users found. Create users in Access Management first.")
            else:
                current_hrbps = db.get_department_hrbps(int(dept_id))
                current_ids = [int(u["id"]) for u in current_hrbps]

                # Show current
                if current_hrbps:
                    st.caption("Current HRBPs for this department:")
                    st.dataframe(pd.DataFrame([{
                        "full_name": u["full_name"],
                        "username": u["username"],
                        "email": u["email"],
                        "role": u["role"],
                    } for u in current_hrbps]), use_container_width=True)
                else:
                    st.info("No HRBP assigned to this department yet.")

                options = [int(u["id"]) for u in eligible]
                def fmt(uid: int) -> str:
                    u = next((x for x in eligible if int(x["id"]) == int(uid)), None)
                    if not u:
                        return str(uid)
                    return f"{u['full_name']} ({u['username']}) | {u['email']} | role={u['role']}"

                selected_ids = st.multiselect(
                    "Select one or more HRBPs for this department",
                    options=options,
                    default=current_ids,
                    format_func=fmt
                )

                st.warning(
                    "Note: Saving will automatically set selected users' role to **HRBP** (access will be upgraded)."
                )

                if st.button("Save Department HRBPs", type="primary"):
                    db.set_department_hrbps(int(dept_id), selected_ids)
                    st.success("Saved. HRBP access updated automatically.")
                    st.rerun()

    # -------------------- ACCESS MANAGEMENT --------------------
    with tabs[2]:
        st.subheader("Access Management")

        sub_tabs = st.tabs(["Create User", "Import Users (Excel/CSV)", "Users List (Edit/Delete)"])

        # Create user
        with sub_tabs[0]:
            username = st.text_input("Username (unique)", placeholder="e.g. milad.ahmadkhan")
            full_name = st.text_input("Full name")
            email = st.text_input("Email")
            role = st.selectbox("Role", _role_choices(), index=_role_choices().index("EVALUATOR"))

            if "suggested_pass" not in st.session_state:
                st.session_state["suggested_pass"] = _gen_password()

            col1, col2 = st.columns([2, 1])
            with col1:
                password = st.text_input("Password (auto-suggested, editable)", value=st.session_state["suggested_pass"])
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

        # Import users
        with sub_tabs[1]:
            st.info("Columns: username, full_name, email, role, password (password can be empty)")
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

            upu = st.file_uploader("Upload users Excel/CSV", type=["xlsx", "csv"], key="users_uploader")
            if upu is not None:
                dfu = _read_user_import(upu)
                required = {"username", "full_name", "email", "role"}
                missing = [c for c in required if c not in dfu.columns]
                if missing:
                    st.error(f"Missing columns: {missing}")
                else:
                    if "password" not in dfu.columns:
                        dfu["password"] = ""

                    created_rows, skipped_rows = [], []
                    for _, row in dfu.iterrows():
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
                            "username": u, "full_name": str(row.get("full_name", "")).strip() or u,
                            "email": str(row.get("email", "")).strip() or f"{u}@example.com",
                            "role": r, "password": pwd
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

        # Users list edit/delete
        with sub_tabs[2]:
            st.markdown("### Users List (Edit/Delete)")

            show_inactive = st.checkbox("Show inactive users", value=True)
            q = st.text_input("Search users", placeholder="username / name / email").strip().lower()

            users = db.list_users(include_inactive=show_inactive)
            filtered = []
            for u in users:
                label = f"{u['username']} {u['full_name']} {u['email']} {u['role']}".lower()
                if q and q not in label:
                    continue
                filtered.append(u)

            if not filtered:
                st.info("No users match your filter.")
            else:
                df_list = pd.DataFrame([{
                    "id": int(u["id"]),
                    "username": u["username"],
                    "full_name": u["full_name"],
                    "email": u["email"],
                    "role": u["role"],
                    "is_active": int(u["is_active"]),
                    "temp_password": u["temp_password"] or "",
                } for u in filtered])
                st.dataframe(df_list, use_container_width=True)

                st.download_button(
                    "Download users (Excel)",
                    data=_to_excel_bytes(df_list, "users"),
                    file_name="users_access_list.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                st.divider()
                st.markdown("### Edit or Delete a user")

                user_id = st.selectbox(
                    "Select user",
                    options=[int(u["id"]) for u in filtered],
                    format_func=lambda uid: next((f"{u['full_name']} ({u['username']}) | {u['role']}" for u in filtered if int(u["id"]) == int(uid)), str(uid))
                )
                u0 = db.user_by_id(int(user_id))
                if not u0:
                    st.error("User not found.")
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        full_name = st.text_input("Full name", value=u0["full_name"])
                        email = st.text_input("Email", value=u0["email"])
                    with col2:
                        role = st.selectbox("Role", _role_choices(), index=_role_choices().index(u0["role"]))
                        is_active = st.checkbox("Active", value=bool(int(u0["is_active"])))

                    if st.button("Save changes", type="primary"):
                        # prevent accidentally demoting ADMIN via UI for the main admin user, but still allow if you insist
                        db.update_user(int(user_id), full_name.strip(), email.strip(), role, int(is_active))
                        st.success("User updated.")
                        st.rerun()

                    st.warning("Delete is permanent and removes assignments/responses/mappings for this user.")
                    if st.button("Delete user"):
                        if u0["role"] == "ADMIN":
                            st.error("Deleting ADMIN user is blocked to avoid locking yourself out.")
                        else:
                            db.delete_user(int(user_id))
                            st.success("User deleted.")
                            st.rerun()

    # -------------------- CREATE EVALUATION --------------------
    with tabs[3]:
        st.subheader("Create Evaluation")
        depts = db.list_departments()
        if not depts:
            st.warning("Please import/create departments first.")
        else:
            candidate_id = st.text_input("Candidate ID", placeholder="e.g. DK-12345")
            candidate_name = st.text_input("Candidate Name")
            department = st.selectbox("Department", options=[d["name"] for d in depts])

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
                        department=department,
                        created_by=auth.current_user()["id"],
                    )
                    st.success(f"Evaluation created (ID: {eval_id})")

    # -------------------- ASSIGN EVALUATORS --------------------
    with tabs[4]:
        st.subheader("Assign Evaluators")
        evals = db.list_evaluations()
        if not evals:
            st.info("No evaluations yet.")
        else:
            q = st.text_input("Search candidate", placeholder="type to filter candidate list...").strip().lower()

            def _eval_label(e):
                dept = e["department"] or "-"
                return f"{e['candidate_name']} | {dept} | {e['level_path']} | #{e['id']}"

            filtered = [e for e in evals if (not q) or q in _eval_label(e).lower() or q in str(e["candidate_id"]).lower()]
            if not filtered:
                st.warning("No evaluations match your search.")
            else:
                eval_id = st.selectbox(
                    "Select evaluation",
                    options=[e["id"] for e in filtered],
                    format_func=lambda eid: _eval_label(db.get_evaluation(eid))
                )
                ev = db.get_evaluation(int(eval_id))
                allowed_roles = logic.allowed_evaluator_roles_by_level_path(ev["level_path"])
                st.caption(f"Allowed evaluator roles: {', '.join(allowed_roles)}")

                users = db.list_users(include_inactive=False)
                eligible = [u for u in users if int(u["is_active"]) == 1 and u["role"] != "ADMIN"]

                uq = st.text_input("Search user", placeholder="username/name/email...").strip().lower()
                eligible_filtered = []
                for u in eligible:
                    s = f"{u['username']} {u['full_name']} {u['email']} {u['role']}".lower()
                    if not uq or uq in s:
                        eligible_filtered.append(u)

                user_id = st.selectbox(
                    "Select user to assign",
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

                assigns = db.list_assignments_for_evaluation(int(eval_id))
                if assigns:
                    df = pd.DataFrame([{
                        "Name": a["full_name"],
                        "Email": a["email"],
                        "Username": a["username"],
                        "Evaluator Role": a["evaluator_role"],
                    } for a in assigns])
                    st.dataframe(df, use_container_width=True)

    # -------------------- ORG REPORTS --------------------
    with tabs[5]:
        st.subheader("Organization Reports (Admin only)")
        today = dt.date.today()
        default_start = today - dt.timedelta(days=183)

        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Start date", value=default_start)
        with c2:
            end_date = st.date_input("End date (exclusive)", value=today + dt.timedelta(days=1))

        rows = db.org_summary_report(_iso(start_date), _iso(end_date))
        if not rows:
            st.info("No data in this range.")
        else:
            df = pd.DataFrame([{"target_level": r["target_level"], "decision": r["decision"], "count": int(r["cnt"])} for r in rows])
            st.dataframe(df, use_container_width=True)

            pivot = df.pivot_table(index="target_level", columns="decision", values="count", aggfunc="sum", fill_value=0).reset_index()
            st.markdown("### Pivot view")
            st.dataframe(pivot, use_container_width=True)

            st.download_button(
                "Download report (Excel)",
                data=_to_excel_bytes(df, "org_report"),
                file_name=f"org_report_{start_date}_to_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    # -------------------- MONITOR & CLOSE --------------------
    with tabs[6]:
        st.subheader("Monitor & Close")
        evals = db.list_evaluations()
        if not evals:
            st.info("No evaluations yet.")
        else:
            eval_id = st.selectbox(
                "Select Evaluation",
                options=[e["id"] for e in evals],
                format_func=lambda eid: (
                    f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | "
                    f"{db.get_evaluation(eid)['department'] or '-'} | "
                    f"{db.get_evaluation(eid)['level_path']} | {db.get_evaluation(eid)['status']}"
                )
            )
            ev = db.get_evaluation(int(eval_id))
            assigns = db.list_assignments_for_evaluation(int(eval_id))
            responses = db.list_responses_for_evaluation(int(eval_id))

            st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
            st.write(f"**Department:** {ev['department'] or '-'}")
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
