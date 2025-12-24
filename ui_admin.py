import streamlit as st
import db
import auth
import logic
import pandas as pd
import secrets
import string


def _gen_temp_password(n: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def admin_page():
    user = auth.require_roles("ADMIN")
    st.header("Admin Dashboard")

    rules = logic.get_rules()

    tabs = st.tabs(["Create Evaluation", "Assign Evaluators", "Monitor & Close"])
    with tabs[0]:
        st.subheader("Create Evaluation")
        candidate_id = st.text_input("Candidate ID", placeholder="e.g. DK-12345")
        candidate_name = st.text_input("Candidate Name")

        level_path = st.selectbox("Promotion Path (from Sheet2)", rules.level_paths)
        target_level = logic.level_path_to_target_level(level_path)
        st.caption(f"Target level derived: **{target_level}**")

        if st.button("Create", type="primary"):
            if not candidate_id.strip() or not candidate_name.strip():
                st.error("Candidate ID and Name are required.")
            else:
                eval_id = db.create_evaluation(
                    candidate_id=candidate_id.strip(),
                    candidate_name=candidate_name.strip(),
                    level_path=level_path,
                    target_level=target_level,
                    created_by=user["id"],
                )
                st.success(f"Evaluation created (ID: {eval_id})")

    with tabs[1]:
        st.subheader("Assign Evaluators")
        evals = db.list_evaluations()
        if not evals:
            st.info("No evaluations yet.")
        else:
            eval_id = st.selectbox(
                "Select Evaluation",
                options=[e["id"] for e in evals],
                format_func=lambda eid: f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | {db.get_evaluation(eid)['level_path']}"
            )
            ev = db.get_evaluation(int(eval_id))

            allowed_roles = logic.allowed_evaluator_roles_by_level_path(ev["level_path"])
            st.caption(f"Allowed roles (per target level): {', '.join(allowed_roles)}")

            st.markdown("### Add / Assign evaluator")
            full_name = st.text_input("Evaluator full name")
            email = st.text_input("Evaluator email")
            evaluator_role = st.selectbox("Evaluator role", allowed_roles)

            if st.button("Create user & Assign"):
                if not full_name.strip() or not email.strip():
                    st.error("Name and email are required.")
                else:
                    username = email.strip().split("@")[0].lower()
                    existing = db.user_by_username(username)
                    temp_password = None

                    if not existing:
                        temp_password = _gen_temp_password()
                        uid = db.create_user(
                            username=username,
                            full_name=full_name.strip(),
                            email=email.strip(),
                            role="EVALUATOR",
                            password_hash=auth.hash_password(temp_password),
                        )
                    else:
                        uid = int(existing["id"])

                    db.create_assignment(int(eval_id), uid, evaluator_role)
                    st.success(f"Assigned {full_name} as {evaluator_role} (username: {username})")
                    if temp_password:
                        st.warning(f"Temporary password for {username}: **{temp_password}** (save it now)")

            st.markdown("### Current assignments")
            assigns = db.list_assignments_for_evaluation(int(eval_id))
            if assigns:
                df = pd.DataFrame([{
                    "Name": a["full_name"],
                    "Email": a["email"],
                    "Username": a["username"],
                    "Role": a["evaluator_role"],
                } for a in assigns])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No assignments yet.")

    with tabs[2]:
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
