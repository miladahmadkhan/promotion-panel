import streamlit as st
import auth
import db
import logic
import pandas as pd


def approver_page():
    user = auth.require_roles("APPROVER")
    st.header("Final Approver Dashboard")
    st.caption("For Principal / Distinguished: review all evaluator votes and submit final per-dimension decision.")

    rules = logic.get_rules()

    evals = db.list_evaluations(status="READY_FOR_APPROVER")
    if not evals:
        st.info("No evaluations waiting for approval.")
        return

    eval_id = st.selectbox(
        "Select evaluation awaiting approval",
        options=[e["id"] for e in evals],
        format_func=lambda eid: f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | {db.get_evaluation(eid)['level_path']}"
    )
    ev = db.get_evaluation(int(eval_id))
    if not ev:
        st.error("Evaluation not found.")
        return

    st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
    st.write(f"**Promotion Path:** {ev['level_path']}")
    st.write(f"**Target Level:** {ev['target_level']}")
    st.write(f"**Status:** {ev['status']}")

    responses = db.list_responses_for_evaluation(int(eval_id))
    if not responses:
        st.warning("No evaluator submissions yet.")
        return

    st.subheader("Evaluator votes (details)")
    rows = []
    for r in responses:
        dims = [r["dim1"], r["dim2"], r["dim3"], r["dim4"], r["dim5"], r["dim6"], r["dim7"], r["dim8"]]
        row = {
            "Evaluator": r["full_name"],
            "Role": r["evaluator_role"],
            "SubmittedAt": r["submitted_at"],
        }
        for i, dim_name in enumerate(rules.dimensions[:8]):
            row[dim_name] = dims[i]
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.subheader("Committee aggregation (decision support)")
    agg = logic.committee_aggregate(int(eval_id))
    if agg["committee_decision"] == "Pending":
        st.warning(f"Pending submissions: {agg['responded_count']}/{agg['assigned_count']}")
        return

    if agg["per_dim"]:
        critical_idxs = set(rules.critical_by_path.get(ev["level_path"], []))
        agg_df = pd.DataFrame(
            [
                {
                    "Dimension": x["dimension"],
                    "Demonstrated Weight": round(float(x["demo_weight"]), 3),
                    "Aggregated Result": x["result"],
                    "Critical?": "✅" if i in critical_idxs else "",
                }
                for i, x in enumerate(agg["per_dim"])
            ]
        )
        st.dataframe(agg_df, use_container_width=True)

    st.subheader("Submit your final per-dimension decision")
    existing = db.get_approver_response(int(eval_id))
    if existing:
        defaults = [existing["dim1"], existing["dim2"], existing["dim3"], existing["dim4"],
                    existing["dim5"], existing["dim6"], existing["dim7"], existing["dim8"]]
        existing_comment = existing["comment"] or ""
    else:
        defaults = ["Partially Demonstrated"] * 8
        existing_comment = ""

    final_dims = []
    for i, dim_name in enumerate(rules.dimensions[:8]):
        idx = logic.RATING_OPTIONS.index(defaults[i]) if defaults[i] in logic.RATING_OPTIONS else 1
        final_dims.append(st.radio(dim_name, logic.RATING_OPTIONS, index=idx, key=f"appr_dim_{i}"))

    comment = st.text_area("Optional approver comment", value=existing_comment)

    if st.button("Submit final decision", type="primary"):
        if len(final_dims) != 8:
            st.error("Expected 8 dimensions from Sheet2 (A12:A19).")
            return

        db.upsert_approver_response(int(eval_id), user["id"], final_dims, comment)

        appr = logic.approver_final_decision(int(eval_id))
        db.set_decision(int(eval_id), final_decision=appr["final_decision"], decided_by=user["id"])
        db.set_evaluation_status(int(eval_id), "CLOSED")

        st.success(f"Final decision saved: {appr['final_decision']} (evaluation closed)")
        st.rerun()
