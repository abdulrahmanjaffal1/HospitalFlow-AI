"""
HospitalFlow AI — Main Streamlit Application
IBM SkillsBuild AI Experiential Learning Lab

An agentic AI hospital operations coordinator that helps hospital capacity
managers identify potential bed-capacity problems, investigate operational
constraints, and recommend possible responses for human approval.

DISCLAIMER: All hospital data is entirely fictional. This is an educational
operational decision-support prototype, NOT a clinical decision-making system.

Architecture:
  data/hospital_data.py      — Synthetic dataset + scenario modifiers
  agents/capacity_agent.py   — Bed capacity analysis (deterministic)
  agents/patient_flow_agent.py — Arrival/discharge flow analysis (deterministic)
  agents/staffing_agent.py   — Staffing constraint analysis (deterministic)
  agents/coordinator_agent.py — Combines findings, produces recommendations
  ui/dashboard.py            — Metrics dashboard panel
  ui/approval.py             — Human approval interface

Planned integrations (NOT yet implemented):
  - watsonx.ai       : LLM-based reasoning and narrative generation
  - watsonx Orchestrate: Automated multi-agent pipeline and workflow triggers
"""

import streamlit as st

# Page config must be the first Streamlit call
st.set_page_config(
    page_title="HospitalFlow AI",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

from data.hospital_data import apply_scenario
from agents.capacity_agent import CapacityAgent
from agents.patient_flow_agent import PatientFlowAgent
from agents.staffing_agent import StaffingAgent
from agents.coordinator_agent import CoordinatorAgent
from ui.dashboard import (
    render_status_banner,
    render_top_metrics,
    render_ward_table,
    render_flags_panel,
    render_agent_detail,
)
from ui.approval import render_approval_panel, render_decision_summary


# ---------------------------------------------------------------------------
# Agents (stateless — instantiated once)
# ---------------------------------------------------------------------------
_capacity_agent  = CapacityAgent()
_flow_agent      = PatientFlowAgent()
_staffing_agent  = StaffingAgent()
_coordinator     = CoordinatorAgent()


# ---------------------------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------------------------

def _run_analysis(scenario: str) -> None:
    """Run all agents for the given scenario and store results in session_state."""
    snapshot = apply_scenario(scenario)
    cap_report  = _capacity_agent.run(snapshot)
    flow_report = _flow_agent.run(snapshot)
    staff_report = _staffing_agent.run(snapshot)
    coord_report = _coordinator.run(cap_report, flow_report, staff_report, snapshot.notes)

    st.session_state["snapshot"]     = snapshot
    st.session_state["coord_report"] = coord_report
    st.session_state["scenario"]     = scenario
    # Reset any prior approval decisions when scenario changes
    st.session_state["decisions_made"] = False


def _ensure_analysis() -> None:
    if "coord_report" not in st.session_state:
        _run_analysis("baseline")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> None:
    st.sidebar.image(
        "https://upload.wikimedia.org/wikipedia/commons/5/51/IBM_logo.svg",
        width=80,
    )
    st.sidebar.title("HospitalFlow AI")
    st.sidebar.caption("IBM SkillsBuild · AI Experiential Learning Lab")
    st.sidebar.divider()

    st.sidebar.subheader("🎛️ Scenario Selection")
    scenario_options = {
        "baseline":           "Baseline — Normal Operations",
        "arrival_surge":      "🚨 Patient Arrival Surge",
        "staffing_shortage":  "👩‍⚕️ Staffing Shortage",
        "discharge_delay":    "🔄 Unexpected Discharge Delay",
    }

    current = st.session_state.get("scenario", "baseline")
    selected = st.sidebar.radio(
        "Select a scenario to simulate:",
        options=list(scenario_options.keys()),
        format_func=lambda k: scenario_options[k],
        index=list(scenario_options.keys()).index(current),
    )

    if st.sidebar.button("▶️  Run Analysis", use_container_width=True, type="primary"):
        _run_analysis(selected)
        st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("ℹ️ About")
    st.sidebar.markdown(
        """
        **HospitalFlow AI** helps capacity managers:
        - Identify bed-capacity problems
        - Investigate operational constraints
        - Review AI-generated recommendations

        **Current implementation:**
        Deterministic rule-based Python calculations.

        **Planned integrations:**
        - 🤖 watsonx.ai (LLM reasoning)
        - 🔗 watsonx Orchestrate (agent pipeline)

        ---
        ⚠️ *Educational prototype only.*
        *All data is entirely fictional.*
        *Not for clinical use.*
        """
    )


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

def main() -> None:
    _ensure_analysis()
    render_sidebar()

    snapshot     = st.session_state["snapshot"]
    coord_report = st.session_state["coord_report"]

    # ---- Header ----
    st.title("🏥 HospitalFlow AI — Operations Coordinator")
    st.caption(
        f"**{snapshot.hospital_name}**  ·  Scenario: *{snapshot.snapshot_label}*  "
        "·  ⚠️ Fictional data — educational prototype only"
    )

    if snapshot.notes:
        st.info(f"📋 **Operational note:** {snapshot.notes}")

    # ---- Status banner ----
    render_status_banner(coord_report)

    # ---- Tabs ----
    tab_dashboard, tab_analysis, tab_approval = st.tabs([
        "📊 Dashboard",
        "🔍 Agent Analysis",
        "✅ Recommendations & Approval",
    ])

    with tab_dashboard:
        render_top_metrics(snapshot, coord_report)
        st.divider()
        render_ward_table(coord_report)
        st.divider()
        render_flags_panel(coord_report)

    with tab_analysis:
        st.markdown("### Coordinator Situation Summary")
        st.markdown(coord_report.situation_summary)
        st.caption(f"ℹ️ {coord_report.agent_note}")
        st.divider()
        render_agent_detail(coord_report)

    with tab_approval:
        updated_recs = render_approval_panel(coord_report.recommendations)
        # Persist decisions back into the report
        coord_report.recommendations = updated_recs
        st.divider()
        render_decision_summary(coord_report.recommendations)

        st.divider()
        st.subheader("🔁 Re-analysis")
        st.markdown(
            "If you have modified scenario conditions or want to refresh the analysis, "
            "use the scenario selector in the sidebar and click **Run Analysis** again. "
            "All agent calculations will re-run and the dashboard will update."
        )
        col_re1, col_re2 = st.columns([1, 3])
        with col_re1:
            if st.button("🔄 Re-run Current Scenario", use_container_width=True):
                _run_analysis(st.session_state.get("scenario", "baseline"))
                st.rerun()


if __name__ == "__main__":
    main()
