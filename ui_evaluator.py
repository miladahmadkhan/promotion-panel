import streamlit as st
import auth
import db
import logic


def evaluator_page():
    # فقط لاگین بودن لازم است
    user = auth.current_user()
    if not user:
        st.warning("Please log in.")
        auth.login_screen()
        st.stop()

    st.header("My Assigned Evaluations")
    st.caption(f"Logged in as: {user['full_name']} ({user['username']}) — Role: {user['role']}")

    rules = logic.get_rules()

    evals = db.list_assigned_evaluations_for_user(user["id"])
    if not evals:
        st.info("No assigned evaluations.")
        return

    eval_id = st.selectbox(
        "Select assigned evaluation",
        options=[e["id"] for e in evals],
        format_func=lambda eid: (
            f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | "
            f"{db.get_evaluation(eid)['level_path']} | {db.get_evaluation(eid)['status']}"
        )
    )
    ev = db.get_evaluation(int(eval_id))
    if not ev:
        st.error("Evaluation not found.")
        return

    assign = db.get_assignment(int(eval_id), user["id"])
    if not assign:
        st.error("You are not assigned to this evaluation.")
        return

    st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
    st.write(f"**Promotion Path:** {ev['level_path']}")
    st.write(f"**Target Level:** {ev['target_level']}")
    st.write(
        f"**Your Evaluator Role (weight):** {assign['evaluator_role']} "
        f"({logic.get_weight(ev['level_path'], assign['evaluator_role']):.0%})"
    )

    existing = db.get_response(int(eval_id), user["id"])
    already_submitted = existing is not None

    if already_submitted:
        st.success("✅ Your response has been submitted.")
        st.caption("This form is now read-only. If you need changes, ask Admin/HRBP to reopen/reset.")

    if ev["status"] == "CLOSED":
        st.warning("This evaluation is closed. Read-only.")
        already_submitted = True

    st.markdown("### Provide your ratings")

    if existing:
        default_vals = [
            existing["dim1"], existing["dim2"], existing["dim3"], existing["dim4"],
            existing["dim5"], existing["dim6"], existing["dim7"], existing["dim8"]
        ]
        existing_comment = existing["comment"] or ""
    else:
        default_vals = ["Partially Demonstrated"] * 8
        existing_comment = ""

    dims = []
    for i, dim_name in enumerate(rules.dimensions[:8]):
        idx = logic.RATING_OPTIONS.index(default_vals[i]) if default_vals[i] in logic.RATING_OPTIONS else 1
        v = st.radio(dim_name, logic.RATING_OPTIONS, index=idx, key=f"dim_{i}", disabled=already_submitted)
        dims.append(v)

    comment = st.text_area("Optional comment", value=existing_comment, disabled=already_submitted)

    submit_clicked = st.button("Submit", type="primary", disabled=already_submitted)

    if submit_clicked:
        db.upsert_response(int(eval_id), user["id"], dims, comment)
        st.success("✅ Submitted successfully. Thank you!")
        st.rerun()
