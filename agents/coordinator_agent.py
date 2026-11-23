"""
Coordinator Agent — HospitalFlow AI

Responsibility: combine the findings from the Capacity, Patient Flow, and
Staffing agents, determine the overall operational status, and produce
structured recommendations for human review and approval.

IMPLEMENTATION NOTE — two layers, deliberately separated:

  1. Deterministic rule engine (always runs)
     Decides WHICH recommendations exist, their priority (1–10), the overall
     hospital status, and whether manager approval is required.

  2. watsonx.ai explanation layer (optional — runs when credentials exist)
     An IBM watsonx.ai foundation model writes a contextual situation briefing
     and a short explanation for each recommendation, using only the
     structured facts produced by layer 1. Its output passes through
     deterministic guardrails (agents/ai_guardrails.py) before display.
     The model CANNOT add, remove, re-prioritise, approve, or execute
     recommendations. If watsonx.ai is unavailable the app falls back to the
     rule-based summary.

Planned (not implemented):
  - watsonx Orchestrate: coordinate agent invocations and route approved
                       actions to external systems (HR scheduling, transfer
                       coordination, bed management).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING
from agents.capacity_agent import CapacityReport
from agents.patient_flow_agent import FlowReport
from agents.staffing_agent import StaffingReport
from agents.ai_guardrails import AIExplanation, apply_guardrails

if TYPE_CHECKING:
    from agents.watsonx_explainer import WatsonxExplainer


# ---------------------------------------------------------------------------
# Output structures
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    id: str
    priority: int                     # 1 (low) → 10 (critical)
    category: str                     # "capacity" | "staffing" | "flow" | "protocol"
    title: str
    description: str
    rationale: str
    suggested_action: str
    requires_approval: bool = True
    status: str = "pending"           # "pending" | "approved" | "modified" | "rejected"
    manager_note: str = ""
    ai_explanation: str = ""          # watsonx.ai context — display only, never drives logic


@dataclass
class CoordinatorReport:
    overall_status: str               # "normal" | "elevated" | "high" | "critical"
    situation_summary: str
    recommendations: List[Recommendation]
    all_flags: List[str]
    capacity_report: CapacityReport
    flow_report: FlowReport
    staffing_report: StaffingReport
    agent_note: str = ""
    ai: AIExplanation = field(default_factory=lambda: AIExplanation(status="not_configured"))


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CoordinatorAgent:
    """
    Orchestrates the sub-agent findings and produces prioritised recommendations.

    Inputs : CapacityReport, FlowReport, StaffingReport, HospitalSnapshot
    Outputs: CoordinatorReport
    """

    name = "Coordinator Agent"

    def __init__(self, explainer: Optional["WatsonxExplainer"] = None) -> None:
        self.explainer = explainer

    def run(
        self,
        capacity: CapacityReport,
        flow: FlowReport,
        staffing: StaffingReport,
        snapshot_notes: str = "",
        use_ai: bool = True,
    ) -> CoordinatorReport:

        recommendations: List[Recommendation] = []
        all_flags = capacity.flags + flow.flags + staffing.flags
        rec_id = 0

        def next_id() -> str:
            nonlocal rec_id
            rec_id += 1
            return f"REC-{rec_id:03d}"

        # ------------------------------------------------------------------
        # Rule set — each rule produces 0 or 1 recommendations
        # Rules are evaluated in priority order (highest first)
        # ------------------------------------------------------------------

        # R1: Predicted bed shortfall
        if capacity.shortage_predicted:
            recommendations.append(Recommendation(
                id=next_id(),
                priority=9,
                category="capacity",
                title="Activate Surge Capacity Protocol",
                description=(
                    f"A projected shortfall of {capacity.shortfall_beds} bed(s) is expected "
                    f"within the next 4 hours based on current arrivals and discharges."
                ),
                rationale=(
                    f"Net demand of +{flow.net_demand_change} patients exceeds the "
                    f"{capacity.hospital_staffed_available} staffed available beds."
                ),
                suggested_action=(
                    "Activate surge capacity plan: open overflow bay, escalate to site manager, "
                    "review elective admission schedule."
                ),
            ))

        # R2: Arrival surge
        if flow.arrival_surge_detected:
            recommendations.append(Recommendation(
                id=next_id(),
                priority=8,
                category="flow",
                title="Manage Patient Arrival Surge",
                description=(
                    f"Arrival rate ({flow.expected_arrivals} in next 4h) is significantly "
                    f"above the normal baseline."
                ),
                rationale="High arrival volumes will rapidly consume remaining bed capacity.",
                suggested_action=(
                    "Notify ED charge nurse. Consider activating ambulance divert if ED occupancy "
                    "exceeds 90 %. Expedite senior clinical review to accelerate ED throughput."
                ),
            ))

        # R3: Discharge delay
        if flow.discharge_delay_detected:
            recommendations.append(Recommendation(
                id=next_id(),
                priority=7,
                category="flow",
                title="Resolve Discharge Bottleneck",
                description=(
                    f"Only {flow.expected_discharges} discharges expected (normal ~14). "
                    "Blocked discharges are reducing available bed stock."
                ),
                rationale=(
                    "Discharge delays compound with incoming demand. Each delayed discharge "
                    "directly displaces an arriving patient."
                ),
                suggested_action=(
                    "Convene urgent discharge round. Alert pharmacy and social-care team. "
                    "Identify top 5 discharge-ready patients and remove blockers."
                ),
            ))

        # R4: Nurse ratio breaches
        if staffing.wards_ratio_breached:
            ward_list = ", ".join(staffing.wards_ratio_breached)
            recommendations.append(Recommendation(
                id=next_id(),
                priority=8,
                category="staffing",
                title="Address Nurse-to-Patient Ratio Breach",
                description=(
                    f"Nurse-to-patient ratios are breached in: {ward_list}. "
                    f"Approximately {staffing.effective_bed_reduction} bed(s) are effectively "
                    "unavailable due to insufficient staffing."
                ),
                rationale=(
                    "Operating below minimum ratios increases patient safety risk and "
                    "means physically available beds cannot be used safely."
                ),
                suggested_action=(
                    "Contact staffing coordinator for bank/agency staff. Consider redeploying "
                    "nurses from lower-acuity wards. Escalate to nurse manager if unresolved "
                    "within 30 minutes."
                ),
            ))

        # R5: Critical ward occupancy (not already covered by shortfall)
        critical_wards = [
            s for s in capacity.ward_statuses if s.pressure_level == "critical"
        ]
        if critical_wards and not capacity.shortage_predicted:
            ward_names = ", ".join(w.ward_name for w in critical_wards)
            recommendations.append(Recommendation(
                id=next_id(),
                priority=6,
                category="capacity",
                title="Monitor Critical Ward Occupancy",
                description=f"Ward(s) at critical occupancy (≥95%): {ward_names}.",
                rationale="Critical occupancy leaves no buffer for unexpected admissions.",
                suggested_action=(
                    "Increase frequency of capacity checks to every 30 minutes. "
                    "Pre-alert receiving wards for potential patient moves."
                ),
            ))

        # R6: High overall occupancy with no other critical issue
        if (
            capacity.overall_pressure_level == "high"
            and not capacity.shortage_predicted
            and not staffing.wards_ratio_breached
        ):
            recommendations.append(Recommendation(
                id=next_id(),
                priority=4,
                category="capacity",
                title="Heightened Capacity Monitoring",
                description=(
                    f"Hospital-wide occupancy is {capacity.overall_occupancy_rate:.0%} — "
                    "elevated but not yet critical."
                ),
                rationale="Early awareness prevents escalation to crisis level.",
                suggested_action=(
                    "Notify bed manager. Schedule capacity review in 2 hours. "
                    "Ensure elective admission list is reviewed."
                ),
                requires_approval=False,
            ))

        # R7: Normal operations
        if not recommendations:
            recommendations.append(Recommendation(
                id=next_id(),
                priority=1,
                category="protocol",
                title="Continue Standard Operations",
                description="All capacity, flow, and staffing indicators are within normal range.",
                rationale="No threshold breaches or predicted shortfalls detected.",
                suggested_action="Maintain routine monitoring cycle. No immediate action required.",
                requires_approval=False,
                status="approved",
            ))

        # Sort by priority descending
        recommendations.sort(key=lambda r: r.priority, reverse=True)

        # ------------------------------------------------------------------
        # Overall status
        # ------------------------------------------------------------------
        max_priority = recommendations[0].priority if recommendations else 1
        if max_priority >= 8:
            overall_status = "critical"
        elif max_priority >= 6:
            overall_status = "high"
        elif max_priority >= 4:
            overall_status = "elevated"
        else:
            overall_status = "normal"

        # ------------------------------------------------------------------
        # Situation summary (deterministic — always produced)
        # ------------------------------------------------------------------
        situation_summary = self._build_summary(
            overall_status, capacity, flow, staffing, snapshot_notes
        )

        # ------------------------------------------------------------------
        # watsonx.ai explanation layer (optional, display-only)
        # ------------------------------------------------------------------
        ai = self._explain(
            overall_status, capacity, flow, staffing, snapshot_notes,
            all_flags, recommendations, use_ai,
        )
        for rec in recommendations:
            rec.ai_explanation = ai.recommendation_explanations.get(rec.id, "")

        if ai.has_content:
            agent_note = (
                "Recommendations, priorities and status are set by deterministic rules. "
                f"Contextual explanations generated by watsonx.ai ({ai.model_id}) and "
                "checked by deterministic guardrails. All actions require manager approval."
            )
        else:
            agent_note = (
                "Recommendations, priorities and status are set by deterministic rules. "
                "watsonx.ai explanations are not active for this run "
                f"({ai.status.replace('_', ' ')}); showing rule-based summary only."
            )

        return CoordinatorReport(
            overall_status=overall_status,
            situation_summary=situation_summary,
            recommendations=recommendations,
            all_flags=all_flags,
            capacity_report=capacity,
            flow_report=flow,
            staffing_report=staffing,
            agent_note=agent_note,
            ai=ai,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _explain(
        self,
        status: str,
        capacity: CapacityReport,
        flow: FlowReport,
        staffing: StaffingReport,
        notes: str,
        flags: List[str],
        recommendations: List[Recommendation],
        use_ai: bool,
    ) -> AIExplanation:
        if not use_ai:
            return AIExplanation(status="disabled")
        if self.explainer is None or not self.explainer.is_configured:
            return AIExplanation(status="not_configured")

        facts = self.build_facts(status, capacity, flow, staffing, notes, flags)
        recs = [
            {
                "id": r.id,
                "priority": r.priority,
                "category": r.category,
                "title": r.title,
                "description": r.description,
                "rationale": r.rationale,
                "suggested_action": r.suggested_action,
                "requires_manager_approval": r.requires_approval,
            }
            for r in recommendations
        ]
        try:
            ai = self.explainer.explain(facts, recs)
        except Exception as exc:  # never let the AI layer break the dashboard
            return AIExplanation(status="error", error=f"{type(exc).__name__}: {exc}")
        return apply_guardrails(ai, facts, recs)

    @staticmethod
    def build_facts(
        status: str,
        capacity: CapacityReport,
        flow: FlowReport,
        staffing: StaffingReport,
        notes: str,
        flags: List[str],
    ) -> dict:
        """Structured, deterministic facts handed to the language model."""
        staff_by_ward = {s.ward_name: s for s in staffing.ward_statuses}
        wards = []
        for w in capacity.ward_statuses:
            s = staff_by_ward.get(w.ward_name)
            wards.append({
                "ward": w.ward_name,
                "total_beds": w.total_beds,
                "occupied_beds": w.occupied_beds,
                "occupancy_percent": round(w.occupancy_rate * 100),
                "staffed_available_beds": w.staffed_available,
                "pressure_level": w.pressure_level,
                "nurses_available": s.nurses_available if s else None,
                "nurses_required": s.nurses_required if s else None,
                "nurse_ratio_breached": s.ratio_breached if s else None,
            })
        return {
            "overall_status": status,
            "forecast_window_hours": 4,
            "hospital": {
                "total_beds": capacity.hospital_total_beds,
                "occupied_beds": capacity.hospital_occupied_beds,
                "occupancy_percent": round(capacity.overall_occupancy_rate * 100),
                "staffed_available_beds": capacity.hospital_staffed_available,
                "projected_shortfall_beds": capacity.shortfall_beds,
            },
            "patient_flow": {
                "expected_arrivals": flow.expected_arrivals,
                "expected_discharges": flow.expected_discharges,
                "pending_transfers_in": flow.pending_transfers_in,
                "pending_transfers_out": flow.pending_transfers_out,
                "net_demand_change": flow.net_demand_change,
                "normal_arrivals_baseline": 18,
                "normal_discharges_baseline": 14,
                "arrival_surge_detected": flow.arrival_surge_detected,
                "discharge_delay_detected": flow.discharge_delay_detected,
            },
            "staffing": {
                "total_nurses_on_shift": staffing.total_nurses,
                "wards_with_ratio_breach": staffing.wards_ratio_breached,
                "beds_effectively_locked_by_staffing": staffing.effective_bed_reduction,
            },
            "wards": wards,
            "operational_note": notes,
            "rule_engine_flags": [f.replace("⚠️", "").replace("ℹ️", "").replace("✅", "").strip() for f in flags],
        }

    def _build_summary(
        self,
        status: str,
        capacity: CapacityReport,
        flow: FlowReport,
        staffing: StaffingReport,
        notes: str,
    ) -> str:
        lines = [
            f"Overall hospital status: **{status.upper()}**",
            "",
            f"- **Occupancy**: {capacity.overall_occupancy_rate:.0%} "
            f"({capacity.hospital_occupied_beds}/{capacity.hospital_total_beds} beds occupied)",
            f"- **Staffed available beds**: {capacity.hospital_staffed_available}",
            f"- **Expected arrivals (next 4h)**: {flow.expected_arrivals}",
            f"- **Expected discharges (next 4h)**: {flow.expected_discharges}",
            f"- **Net demand change**: {flow.net_demand_change:+d} beds",
            f"- **Nurse ratio breaches**: "
            + (", ".join(staffing.wards_ratio_breached) if staffing.wards_ratio_breached else "None"),
        ]
        if notes:
            lines += ["", f"**Operational note**: {notes}"]

        lines += [
            "",
            "*Figures above are computed by deterministic rule-based logic.*",
        ]
        return "\n".join(lines)
