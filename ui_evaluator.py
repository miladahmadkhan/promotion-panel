import streamlit as st
import auth
import db
import logic


def evaluator_page():
    user = auth.require_roles("EVALUATOR")
    st.header("Evaluator Dashboard")
    st.caption(f"Logged in as: {user['full_name']} ({user['username']})")

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

    if ev["status"] == "CLOSED":
        st.warning("This evaluation is closed. Read-only.")

    assign = db.get_assignment(int(eval_id), user["id"])
    if not assign:
        st.error("You are not assigned to this evaluation.")
        return

    st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
    st.write(f"**Promotion Path:** {ev['level_path']}")
    st.write(f"**Target Level:** {ev['target_level']}")
    st.write(
        f"**Your Role:** {assign['evaluator_role']} "
        f"(weight = {logic.get_weight(ev['level_path'], assign['evaluator_role']):.0%})"
    )

    existing = db.get_response(int(eval_id), user["id"])

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
        v = st.radio(dim_name, logic.RATING_OPTIONS, index=idx, key=f"dim_{i}")
        dims.append(v)

    comment = st.text_area("Optional comment", value=existing_comment)

    if ev["status"] == "CLOSED":
        st.info("Read-only view.")
        return

    if st.button("Submit", type="primary"):
        if len(dims) != 8:
            st.error("Expected 8 dimensions from Sheet2 (A12:A19).")
            return
        db.upsert_response(int(eval_id), user["id"], dims, comment)
        st.success("Submitted.")
        st.rerun()
