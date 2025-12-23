import streamlit as st
import uuid

# ---------- CONFIG ----------
DIMENSIONS = [
    "Impact & Scope",
    "Problem Solving",
    "Collaboration & Influence",
    "Customer & Market",
    "Values & Culture",
    "Craft Depth",
    "Innovation & Systems",
    "Knowledge Sharing"
]

LEVEL_RULES = {
    "Senior Specialist": {
        "weights": {
            "Line Manager": 0.10,
            "Second Line Manager": 0.35,
            "OPD": 0.15,
            "HRBP": 0.20,
            "External Stakeholder": 0.20
        },
        "min_demo": 4,
        "critical": [0, 4]
    },
    "Lead Expert": {
        "weights": {
            "Line Manager": 0.10,
            "Second Line Manager": 0.30,
            "OPD": 0.10,
            "HRBP": 0.20,
            "External Stakeholder 1": 0.15,
            "External Stakeholder 2": 0.15
        },
        "min_demo": 6,
        "critical": [0, 5]
    },
    "Advanced Expert": {
        "weights": {
            "Line Manager": 0.10,
            "Department Deputy": 0.30,
            "OPD": 0.10,
            "HRBP": 0.20,
            "External Stakeholder 1": 0.15,
            "External Stakeholder 2": 0.15
        },
        "min_demo": 7,
        "critical": [0, 5]
    },
    "Principal": {
        "weights": {
            "Line Manager": 0.10,
            "Department Deputy": 0.30,
            "HR Deputy": 0.15,
            "HRBP Director": 0.15,
            "External Stakeholder 1": 0.15,
            "External Stakeholder 2": 0.15
        },
        "min_demo": 0,
        "critical": []
    },
    "Distinguished": {
        "weights": {
            "Department Deputy": 0.10,
            "CEO Deputy": 0.30,
            "HR Deputy": 0.15,
            "HRBP Director": 0.15,
            "External Stakeholder 1": 0.15,
            "External Stakeholder 2": 0.15
        },
        "min_demo": 0,
        "critical": []
    }
}

# ---------- STATE ----------
if "evaluations" not in st.session_state:
    st.session_state.evaluations = {}

# ---------- FUNCTIONS ----------
def calculate_dimension_result(votes, weights):
    demo_weight = sum(
        weights[p] for p, v in votes.items() if v == "Demonstrated"
    )
    if demo_weight >= 0.7:
        return "Demonstrated", demo_weight
    elif demo_weight >= 0.4:
        return "Partially Demonstrated", demo_weight
    else:
        return "Not Demonstrated", demo_weight


def final_decision(results, rules):
    demo_count = sum(1 for r, _ in results if r == "Demonstrated")
    for idx in rules["critical"]:
        if results[idx][0] != "Demonstrated":
            return "Reject"
    if demo_count >= rules["min_demo"]:
        return "Confirmed"
    return "Reject"

# ---------- UI ----------
st.title("🎯 Promotion Panel Evaluation Tool")

role = st.sidebar.selectbox(
    "Role",
    ["Admin", "Panelist", "HRBP", "Final Approver"]
)

# ---------- ADMIN ----------
if role == "Admin":
    st.header("Create Evaluation")
    candidate = st.text_input("Candidate Name")
    level = st.selectbox("Target Level", LEVEL_RULES.keys())

    if st.button("Create Evaluation"):
        eval_id = str(uuid.uuid4())[:8]
        st.session_state.evaluations[eval_id] = {
            "candidate": candidate,
            "level": level,
            "votes": {},
            "final_override": None
        }
        st.success(f"Evaluation Created: {eval_id}")

    st.subheader("Existing Evaluations")
    for eid, ev in st.session_state.evaluations.items():
        st.write(f"**{eid}** | {ev['candidate']} | {ev['level']}")

# ---------- PANELIST ----------
if role == "Panelist":
    st.header("Panelist Form")
    eval_id = st.text_input("Evaluation ID")
    panelist = st.text_input("Your Role")

    if eval_id in st.session_state.evaluations:
        rules = LEVEL_RULES[st.session_state.evaluations[eval_id]["level"]]
        if panelist not in rules["weights"]:
            st.error("Invalid role for this level")
        else:
            votes = {}
            for d in DIMENSIONS:
                votes[d] = st.radio(
                    d,
                    ["Demonstrated", "Partially Demonstrated", "Not Demonstrated"],
                    key=d
                )
            if st.button("Submit"):
                st.session_state.evaluations[eval_id]["votes"][panelist] = votes
                st.success("Submitted")

# ---------- HRBP ----------
if role == "HRBP":
    st.header("Final Results")
    for eid, ev in st.session_state.evaluations.items():
        if ev.get("final_decision"):
            st.write(
                f"**{ev['candidate']} ({ev['level']}) → {ev['final_decision']}**"
            )

# ---------- FINAL APPROVER ----------
if role == "Final Approver":
    st.header("Final Decision")
    eval_id = st.text_input("Evaluation ID")

    if eval_id in st.session_state.evaluations:
        decision = st.selectbox(
            "Final Decision",
            ["Confirmed", "Reject"]
        )
        if st.button("Confirm Decision"):
            st.session_state.evaluations[eval_id]["final_decision"] = decision
            st.success("Final Decision Saved")
