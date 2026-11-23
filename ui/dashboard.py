"""
Dashboard panel — HospitalFlow AI

Renders the hospital operations metrics tiles and ward-level breakdown.
"""

from __future__ import annotations
import streamlit as st
from data.hospital_data import HospitalSnapshot
from agents.coordinator_agent import CoordinatorReport


STATUS_COLOURS = {
    "normal":   "#2d8a4e",   # green
    "elevated": "#d97706",   # amber
    "high":     "#dc4f26",   # orange-red
    "critical": "#b91c1c",   # red
}

PRESSURE_EMOJI = {
    "normal":   "🟢",
    "moderate": "🟡",
    "high":     "🟠",
    "critical": "🔴",
}


def render_status_banner(report: CoordinatorReport) -> None:
    colour = STATUS_COLOURS.get(report.overall_status, "#6b7280")
    st.markdown(
        f"""
        <div style="background:{colour};padding:14px 20px;border-radius:8px;margin-bottom:16px;">
            <span style="color:white;font-size:1.25rem;font-weight:700;">
                🏥 Riverside General Hospital (Fictional) — Status:
                {report.overall_status.upper()}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_top_metrics(snapshot: HospitalSnapshot, report: CoordinatorReport) -> None:
    """Six KPI tiles across the top."""
    cap = report.capacity_report
    flow = report.flow_report

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Beds", cap.hospital_total_beds)
    col2.metric(
        "Occupied Beds",
        cap.hospital_occupied_beds,
        delta=f"{cap.overall_occupancy_rate:.0%} occupancy",
        delta_color="inverse",
    )
    col3.metric(
        "Staffed Available",
        cap.hospital_staffed_available,
        delta=("⚠️ LOW" if cap.hospital_staffed_available < 10 else None),
        delta_color="inverse",
    )
    col4.metric(
        "Expected Arrivals (4h)",
        flow.expected_arrivals,
        delta=(f"+{flow.expected_arrivals - 18} vs baseline" if flow.expected_arrivals != 18 else None),
        delta_color="inverse",
    )
    col5.metric(
        "Expected Discharges (4h)",
        flow.expected_discharges,
        delta=(f"{flow.expected_discharges - 14:+d} vs baseline" if flow.expected_discharges != 14 else None),
        delta_color="normal",
    )
    col6.metric(
        "Net Demand Change",
        f"{flow.net_demand_change:+d}",
        delta=("⚠️ Pressure" if flow.net_demand_change > 5 else None),
        delta_color="inverse",
    )


def render_ward_table(report: CoordinatorReport) -> None:
    """Ward-level capacity breakdown."""
    st.subheader("Ward Capacity Overview")

    rows = []
    for ws in report.capacity_report.ward_statuses:
        # find matching staffing status
        staffing_ws = next(
            (s for s in report.staffing_report.ward_statuses if s.ward_name == ws.ward_name),
            None,
        )
        ratio_ok = "✅" if (staffing_ws and not staffing_ws.ratio_breached) else "⚠️"
        rows.append({
            "Ward": ws.ward_name,
            "Total Beds": ws.total_beds,
            "Occupied": ws.occupied_beds,
            "Staffed Available": ws.staffed_available,
            "Occupancy": f"{ws.occupancy_rate:.0%}",
            "Pressure": f"{PRESSURE_EMOJI.get(ws.pressure_level, '')} {ws.pressure_level.capitalize()}",
            "Nurse Ratio": ratio_ok,
        })

    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_flags_panel(report: CoordinatorReport) -> None:
    """Consolidated flags from all agents."""
    flags = report.all_flags
    if not flags:
        st.success("No operational flags raised.")
        return

    with st.expander(f"🚨 Operational Flags ({len(flags)})", expanded=True):
        for flag in flags:
            if flag.startswith("⚠️"):
                st.warning(flag)
            elif flag.startswith("✅"):
                st.success(flag)
            else:
                st.info(flag)


def render_agent_detail(report: CoordinatorReport) -> None:
    """Expandable detail panels for each sub-agent's findings."""
    with st.expander("🔍 Capacity Agent Detail", expanded=False):
        cap = report.capacity_report
        st.markdown(f"**Overall Pressure:** {cap.overall_pressure_level.capitalize()}")
        st.markdown(f"**Shortage Predicted:** {'Yes ⚠️' if cap.shortage_predicted else 'No ✅'}")
        if cap.shortage_predicted:
            st.markdown(f"**Projected Shortfall:** {cap.shortfall_beds} bed(s)")
        st.caption(f"ℹ️ {cap.agent_note}")

    with st.expander("🔍 Patient Flow Agent Detail", expanded=False):
        fl = report.flow_report
        st.markdown(f"**Arrival Surge:** {'Yes ⚠️' if fl.arrival_surge_detected else 'No ✅'}")
        st.markdown(f"**Discharge Delay:** {'Yes ⚠️' if fl.discharge_delay_detected else 'No ✅'}")
        st.markdown(f"**Transfers In / Out:** {fl.pending_transfers_in} / {fl.pending_transfers_out}")
        st.caption(f"ℹ️ {fl.agent_note}")

    with st.expander("🔍 Staffing Agent Detail", expanded=False):
        sf = report.staffing_report
        st.markdown(f"**Total Nurses on Shift:** {sf.total_nurses}")
        breached = sf.wards_ratio_breached
        if breached:
            st.warning(f"Ratio breached in: {', '.join(breached)}")
        else:
            st.success("All nurse-to-patient ratios within limits.")
        st.markdown(f"**Effective Bed Reduction from Staffing:** {sf.effective_bed_reduction}")
        st.caption(f"ℹ️ {sf.agent_note}")
