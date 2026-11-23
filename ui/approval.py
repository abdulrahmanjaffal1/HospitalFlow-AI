"""
Human Approval Interface — HospitalFlow AI

Renders each recommendation with Approve / Modify / Reject controls
and collects the operations manager's decisions.
"""

from __future__ import annotations
import streamlit as st
from typing import List
from agents.coordinator_agent import Recommendation


PRIORITY_COLOURS = {
    range(8, 11): "#b91c1c",   # critical — red
    range(6, 8):  "#dc4f26",   # high — orange
    range(4, 6):  "#d97706",   # elevated — amber
    range(1, 4):  "#2d8a4e",   # normal — green
}

CATEGORY_ICONS = {
    "capacity": "🏥",
    "staffing": "👩‍⚕️",
    "flow":     "🔄",
    "protocol": "📋",
}


def _priority_colour(p: int) -> str:
    for r, c in PRIORITY_COLOURS.items():
        if p in r:
            return c
    return "#6b7280"


def render_approval_panel(recommendations: List[Recommendation]) -> List[Recommendation]:
    """
    Renders the approval interface.
    Returns the updated list of Recommendation objects with manager decisions applied.
    """
    st.subheader("📋 Recommendations — Operations Manager Review")
    st.markdown(
        "Review each recommendation below. **Approve**, **modify**, or **reject** each one. "
        "Your decisions are recorded for audit. No action is taken automatically."
    )

    updated: List[Recommendation] = []

    for rec in recommendations:
        colour = _priority_colour(rec.priority)
        icon = CATEGORY_ICONS.get(rec.category, "📌")

        # Card header
        st.markdown(
            f"""
            <div style="border-left:4px solid {colour};padding:4px 12px;
                        background:#f8f9fa;border-radius:4px;margin-top:16px;">
                <strong style="font-size:1.05rem;">{icon} [{rec.id}] {rec.title}</strong>
                &nbsp;<span style="color:{colour};font-size:0.85rem;">
                    Priority {rec.priority}/10 · {rec.category.capitalize()}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_desc, col_action = st.columns([3, 2])

        with col_desc:
            st.markdown(f"**Situation:** {rec.description}")
            st.markdown(f"**Rationale:** {rec.rationale}")
            with st.expander("Suggested action"):
                st.info(rec.suggested_action)

        with col_action:
            if not rec.requires_approval:
                st.success("✅ Auto-approved (no manager action required)")
                rec.status = "approved"
            else:
                # Decision widget — use unique key per recommendation
                decision_key = f"decision_{rec.id}"
                note_key = f"note_{rec.id}"

                decision = st.radio(
                    "Decision",
                    options=["pending", "approved", "modified", "rejected"],
                    index=["pending", "approved", "modified", "rejected"].index(
                        st.session_state.get(decision_key, rec.status)
                    ),
                    key=decision_key,
                    horizontal=True,
                )
                rec.status = decision

                manager_note = st.text_area(
                    "Manager note (optional)",
                    value=st.session_state.get(note_key, rec.manager_note),
                    key=note_key,
                    height=68,
                    placeholder="Add context, modification, or reason for rejection…",
                )
                rec.manager_note = manager_note

        updated.append(rec)
        st.divider()

    return updated


def render_decision_summary(recommendations: List[Recommendation]) -> None:
    """Shows a compact summary of all decisions made."""
    approved   = [r for r in recommendations if r.status == "approved"]
    modified   = [r for r in recommendations if r.status == "modified"]
    rejected   = [r for r in recommendations if r.status == "rejected"]
    pending    = [r for r in recommendations if r.status == "pending"]

    st.subheader("Decision Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("✅ Approved",  len(approved))
    c2.metric("✏️ Modified",  len(modified))
    c3.metric("❌ Rejected",  len(rejected))
    c4.metric("⏳ Pending",   len(pending))

    if pending:
        st.warning(f"{len(pending)} recommendation(s) still awaiting a decision.")
    elif not recommendations:
        pass
    else:
        st.success("All recommendations have been reviewed.")

    # Detailed table
    if any([approved, modified, rejected]):
        rows = []
        for r in recommendations:
            rows.append({
                "ID": r.id,
                "Title": r.title,
                "Priority": r.priority,
                "Status": r.status.capitalize(),
                "Note": r.manager_note or "—",
            })
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
