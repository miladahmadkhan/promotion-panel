import streamlit as st
import pandas as pd

import auth
import db
import logic


def _hrbp_allowed_evals(user_id: int):
    depts = db.get_hrbp_department_names(user_id)
    return depts, db.list_evaluations_by_departments(depts)


def hrbp_page():
    u = auth.require_roles("HRBP")
    st.header("HRBP Dashboard")

    rules = logic.get_rules()

    # HRBP departments
    depts, allowed_evals = _hrbp_allowed_evals(int(u["id"]))
    st.caption(f"Your departments: {', '.join(depts) if depts else 'None'}")
    if not depts:
        st.warning("No departments assigned to you. Ask Admin to map your departments in Access Management.")
        return

    tab_reports, tab_my_eval = st.tabs(["Reports", "My Evaluations"])

    # -------------------- REPORTS (only my depts) --------------------
    with tab_reports:
        if not allowed_evals:
            st.info("No evaluations for your departments.")
            return

        eval_id = st.selectbox(
            "Select evaluation (only your departments)",
            options=[e["id"] for e in allowed_evals],
            format_func=lambda eid: (
                f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | "
                f"{db.get_evaluation(eid)['department']} | "
                f"{db.get_evaluation(eid)['level_path']} | {db.get_evaluation(eid)['status']}"
            )
        )
        ev = db.get_evaluation(int(eval_id))

        st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
        st.write(f"**Department:** {ev['department'] or '-'}")
        st.write(f"**Promotion Path:** {ev['level_path']}")
        st.write(f"**Target Level:** {ev['target_level']}")
        st.write(f"**Status:** {ev['status']}")

        assigns = db.list_assignments_for_evaluation(int(eval_id))
        responses = db.list_responses_for_evaluation(int(eval_id))

        st.subheader("Completion")
        assigned_map = {int(a["user_id"]): (a["full_name"], a["evaluator_role"], a["email"]) for a in assigns}
        responded_ids = {int(r["user_id"]) for r in responses}

        completion_rows = [
            {"Evaluator": name, "Role": role, "Email": email, "Submitted": "✅" if uid in responded_ids else "❌"}
            for uid, (name, role, email) in assigned_map.items()
        ]
        st.dataframe(pd.DataFrame(completion_rows), use_container_width=True)

        st.subheader("Individual votes (details)")
        if not responses:
            st.info("No submissions yet.")
        else:
            rows = []
            for r in responses:
                dims = [r["dim1"], r["dim2"], r["dim3"], r["dim4"], r["dim5"], r["dim6"], r["dim7"], r["dim8"]]
                row = {"Evaluator": r["full_name"], "Role": r["evaluator_role"], "SubmittedAt": r["submitted_at"]}
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
                [{
                    "Dimension": x["dimension"],
                    "Demonstrated Weight": round(float(x["demo_weight"]), 3),
                    "Aggregated Result": x["result"],
                    "Critical?": "✅" if i in critical_idxs else "",
                } for i, x in enumerate(agg["per_dim"])]
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

    # -------------------- MY EVALUATIONS (only assigned + only my depts) --------------------
    with tab_my_eval:
        st.subheader("My assigned evaluations (within my departments)")

        assigned = db.list_assigned_evaluations_for_user_in_departments(int(u["id"]), depts)
        if not assigned:
            st.info("You have no assigned evaluations in your departments.")
            return

        eval_id = st.selectbox(
            "Select evaluation",
            options=[e["id"] for e in assigned],
            format_func=lambda eid: (
                f"#{eid} | {db.get_evaluation(eid)['candidate_name']} | "
                f"{db.get_evaluation(eid)['department']} | {db.get_evaluation(eid)['level_path']}"
            )
        )
        ev = db.get_evaluation(int(eval_id))
        assign = db.get_assignment(int(eval_id), int(u["id"]))
        if not assign:
            st.error("You are not assigned to this evaluation.")
            return

        existing = db.get_response(int(eval_id), int(u["id"]))
        readonly = existing is not None or ev["status"] == "CLOSED"

        st.write(f"**Candidate:** {ev['candidate_name']} ({ev['candidate_id']})")
        st.write(f"**Department:** {ev['department']}")
        st.write(f"**Promotion Path:** {ev['level_path']}")
        st.write(f"**Your evaluator role:** {assign['evaluator_role']}")

        if existing:
            st.success("✅ Your response has been submitted. Read-only.")
        if ev["status"] == "CLOSED":
            st.warning("Evaluation is closed. Read-only.")

        # defaults
        if existing:
            default_vals = [existing["dim1"], existing["dim2"], existing["dim3"], existing["dim4"],
                            existing["dim5"], existing["dim6"], existing["dim7"], existing["dim8"]]
            default_comment = existing["comment"] or ""
        else:
            default_vals = ["Partially Demonstrated"] * 8
            default_comment = ""

        dims = []
        for i, dim_name in enumerate(rules.dimensions[:8]):
            idx = logic.RATING_OPTIONS.index(default_vals[i]) if default_vals[i] in logic.RATING_OPTIONS else 1
            dims.append(st.radio(dim_name, logic.RATING_OPTIONS, index=idx, key=f"hrbp_dim_{i}", disabled=readonly))

        comment = st.text_area("Optional comment", value=default_comment, disabled=readonly)

        if st.button("Submit", type="primary", disabled=readonly):
            db.upsert_response(int(eval_id), int(u["id"]), dims, comment)
            st.success("✅ Submitted successfully.")
            st.rerun()
