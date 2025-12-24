import streamlit as st
import pandas as pd

import auth
import db
import logic
from ui_evaluator import evaluator_page


def hrbp_page():
    auth.require_roles("HRBP")
    st.header("HRBP Dashboard")

    rules = logic.get_rules()

    tab_reports, tab_my_eval = st.tabs(["Reports", "My Evaluations"])

    # -------------------- REPORTS (همان گزارش‌ها) --------------------
    with tab_reports:
        evals = db.list_evaluations()
        if not evals:
            st.info("No evaluations.")
            return

        eval_id = st.selectbox(
            "Select evaluation",
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

        st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
        st.write(f"**Promotion Path:** {ev['level_path']}")
        st.write(f"**Target Level:** {ev['target_level']}")
        st.write(f"**Status:** {ev['status']}")

        assigns = db.list_assignments_for_evaluation(int(eval_id))
        responses = db.list_responses_for_evaluation(int(eval_id))

        st.subheader("Completion")
        assigned_map = {int(a["user_id"]): (a["full_name"], a["evaluator_role"], a["email"]) for a in assigns}
        responded_ids = {int(r["user_id"]) for r in responses}

        completion_rows = [
            {
                "Evaluator": name,
                "Role": role,
                "Email": email,
                "Submitted": "✅" if uid in responded_ids else "❌",
            }
            for uid, (name, role, email) in assigned_map.items()
        ]

        if completion_rows:
            st.dataframe(pd.DataFrame(completion_rows), use_container_width=True)
        else:
            st.info("No evaluators assigned yet.")
            return

        st.subheader("Individual votes (details)")
        if not responses:
            st.info("No submissions yet.")
        else:
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

        st.subheader("Committee aggregation (Evidence Threshold)")
        agg = logic.committee_aggregate(int(eval_id))

        if agg["committee_decision"] == "Pending":
            st.warning(f"Pending submissions: {agg['responded_count']}/{agg['assigned_count']}")
        else:
            st.success(f"Committee Decision: **{agg['committee_decision']}**")

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

        st.subheader("Decision")
        dec = db.get_decision(int(eval_id))

        if ev["target_level"] in ("Principal", "Distinguished"):
            appr = logic.approver_final_decision(int(eval_id))
            st.write(f"Committee (Recommendation): **{dec['committee_decision'] if dec else 'Pending'}**")
            st.write(f"Approver Final Decision: **{appr['final_decision']}**")
        else:
            st.write(f"Auto Final Decision: **{dec['committee_decision'] if dec else 'Pending'}**")

    # -------------------- MY EVALUATIONS (HRBP هم می‌تواند ارزیابی کند) --------------------
    with tab_my_eval:
        evaluator_page()
