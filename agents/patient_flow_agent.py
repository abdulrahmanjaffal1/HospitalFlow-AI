"""
Patient Flow Agent — HospitalFlow AI

Responsibility: analyse the balance between patient arrivals, discharges,
and transfers to predict net demand changes over the next operational window.

IMPLEMENTATION NOTE:
All logic is deterministic Python calculation.
Planned integration: watsonx.ai to generate contextual narrative explanations
of flow patterns; watsonx Orchestrate to trigger automated escalation workflows.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
from data.hospital_data import HospitalSnapshot


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

SURGE_MULTIPLIER     = 1.5    # arrivals > 1.5× expected baseline = surge
BASELINE_ARRIVALS    = 18     # normal 4-hour arrival rate for this hospital
LOW_DISCHARGE_RATE   = 0.5    # discharges < 50 % of expected = delay flag


# ---------------------------------------------------------------------------
# Output structures
# ---------------------------------------------------------------------------

@dataclass
class FlowReport:
    expected_arrivals: int
    expected_discharges: int
    pending_transfers_in: int
    pending_transfers_out: int
    net_demand_change: int          # positive = net increase in occupied beds
    arrival_surge_detected: bool
    discharge_delay_detected: bool
    flags: List[str] = field(default_factory=list)
    agent_note: str = ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class PatientFlowAgent:
    """
    Analyses patient arrivals, discharges, and transfers to characterise
    net demand pressure over the next 4-hour window.

    Inputs : HospitalSnapshot
    Outputs: FlowReport
    """

    name = "Patient Flow Agent"

    def run(self, snapshot: HospitalSnapshot) -> FlowReport:
        arrivals  = snapshot.expected_arrivals_next_4h
        discharges = snapshot.expected_discharges_next_4h
        t_in  = snapshot.pending_transfers_in
        t_out = snapshot.pending_transfers_out

        net_demand = (arrivals + t_in) - (discharges + t_out)
        flags: List[str] = []

        # Surge detection
        surge = arrivals > BASELINE_ARRIVALS * SURGE_MULTIPLIER
        if surge:
            ratio = arrivals / BASELINE_ARRIVALS
            flags.append(
                f"⚠️  Arrival surge detected: {arrivals} expected arrivals "
                f"({ratio:.1f}× baseline of {BASELINE_ARRIVALS})."
            )

        # Discharge delay detection
        expected_baseline_discharges = 14   # normal 4-hour discharge rate
        delay = discharges < expected_baseline_discharges * LOW_DISCHARGE_RATE
        if delay:
            blocked = expected_baseline_discharges - discharges
            flags.append(
                f"⚠️  Discharge delay: only {discharges} discharges expected "
                f"(normal: ~{expected_baseline_discharges}). "
                f"Approximately {blocked} patients may be blocked."
            )

        # Transfer pressure
        if t_in > t_out + 3:
            flags.append(
                f"ℹ️  Incoming transfers ({t_in}) significantly exceed "
                f"outgoing ({t_out}) — net inflow of {t_in - t_out}."
            )

        # Net demand summary
        if net_demand > 0:
            flags.append(
                f"ℹ️  Net demand increase: +{net_demand} occupied beds projected over next 4 hours."
            )
        elif net_demand < 0:
            flags.append(
                f"ℹ️  Net demand decrease: {net_demand} occupied beds projected over next 4 hours."
            )
        else:
            flags.append("ℹ️  Net patient demand is neutral over next 4 hours.")

        agent_note = (
            "Analysis produced by deterministic rule-based flow calculations. "
            "Planned: watsonx.ai to provide narrative flow pattern analysis "
            "and trend reasoning from historical data."
        )

        return FlowReport(
            expected_arrivals=arrivals,
            expected_discharges=discharges,
            pending_transfers_in=t_in,
            pending_transfers_out=t_out,
            net_demand_change=net_demand,
            arrival_surge_detected=surge,
            discharge_delay_detected=delay,
            flags=flags,
            agent_note=agent_note,
        )
