"""
Capacity Agent — HospitalFlow AI

Responsibility: calculate current and projected bed capacity, identify shortages,
and flag critical occupancy thresholds.

IMPLEMENTATION NOTE:
All logic here is deterministic rule-based calculation in Python.
No AI reasoning is applied at this stage.
Planned integration: watsonx.ai can replace or augment the analysis() method
to provide natural-language reasoning over the same structured inputs.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
from data.hospital_data import HospitalSnapshot, Ward


# ---------------------------------------------------------------------------
# Thresholds (configurable constants)
# ---------------------------------------------------------------------------

CRITICAL_OCCUPANCY   = 0.95   # ≥95 % → critical
HIGH_OCCUPANCY       = 0.85   # ≥85 % → high pressure
SAFE_STAFFED_BUFFER  = 5      # minimum staffed-available beds across hospital


# ---------------------------------------------------------------------------
# Output structures
# ---------------------------------------------------------------------------

@dataclass
class WardCapacityStatus:
    ward_name: str
    total_beds: int
    occupied_beds: int
    staffed_available: int
    occupancy_rate: float
    pressure_level: str           # "critical" | "high" | "moderate" | "normal"
    flags: List[str] = field(default_factory=list)


@dataclass
class CapacityReport:
    hospital_total_beds: int
    hospital_occupied_beds: int
    hospital_staffed_available: int
    overall_occupancy_rate: float
    overall_pressure_level: str
    ward_statuses: List[WardCapacityStatus]
    shortage_predicted: bool
    shortfall_beds: int           # positive = predicted beds needed beyond capacity
    flags: List[str] = field(default_factory=list)
    agent_note: str = ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CapacityAgent:
    """
    Analyses current bed capacity and predicts near-term shortages.

    Inputs : HospitalSnapshot
    Outputs: CapacityReport
    """

    name = "Capacity Agent"

    def run(self, snapshot: HospitalSnapshot) -> CapacityReport:
        ward_statuses = [self._assess_ward(w) for w in snapshot.wards]
        flags: List[str] = []

        # Projected demand over next 4 hours
        net_new_patients = (
            snapshot.expected_arrivals_next_4h
            + snapshot.pending_transfers_in
            - snapshot.expected_discharges_next_4h
            - snapshot.pending_transfers_out
        )
        projected_occupied = snapshot.occupied_beds + net_new_patients
        projected_available_staffed = snapshot.staffed_available_beds - net_new_patients
        shortfall = max(0, net_new_patients - snapshot.staffed_available_beds)

        # Overall pressure
        occ = snapshot.occupancy_rate
        if occ >= CRITICAL_OCCUPANCY:
            overall_pressure = "critical"
            flags.append(f"⚠️  Hospital-wide occupancy {occ:.0%} — CRITICAL threshold exceeded.")
        elif occ >= HIGH_OCCUPANCY:
            overall_pressure = "high"
            flags.append(f"⚠️  Hospital-wide occupancy {occ:.0%} — HIGH pressure.")
        else:
            overall_pressure = "moderate" if occ >= 0.70 else "normal"

        if snapshot.staffed_available_beds < SAFE_STAFFED_BUFFER:
            flags.append(
                f"⚠️  Only {snapshot.staffed_available_beds} staffed available beds — "
                f"below safe buffer of {SAFE_STAFFED_BUFFER}."
            )

        if shortfall > 0:
            flags.append(
                f"⚠️  Projected shortfall: {shortfall} additional beds needed in next 4 hours."
            )

        if snapshot.ambulance_divert_active:
            flags.append("ℹ️  Ambulance divert currently ACTIVE — incoming load partially redirected.")

        # Collect ward-level flags
        critical_wards = [s.ward_name for s in ward_statuses if s.pressure_level == "critical"]
        if critical_wards:
            flags.append(f"⚠️  Wards at CRITICAL occupancy: {', '.join(critical_wards)}.")

        agent_note = (
            "Analysis produced by deterministic rule-based calculations. "
            "Planned: replace with watsonx.ai for natural-language capacity reasoning."
        )

        return CapacityReport(
            hospital_total_beds=snapshot.total_beds,
            hospital_occupied_beds=snapshot.occupied_beds,
            hospital_staffed_available=snapshot.staffed_available_beds,
            overall_occupancy_rate=occ,
            overall_pressure_level=overall_pressure,
            ward_statuses=ward_statuses,
            shortage_predicted=shortfall > 0,
            shortfall_beds=shortfall,
            flags=flags,
            agent_note=agent_note,
        )

    # ------------------------------------------------------------------

    def _assess_ward(self, ward: Ward) -> WardCapacityStatus:
        staffed_total = int(ward.total_beds * ward.staffed_ratio)
        staffed_avail = max(0, staffed_total - ward.occupied_beds)
        occ = ward.occupied_beds / ward.total_beds if ward.total_beds else 0.0
        flags: List[str] = []

        if occ >= CRITICAL_OCCUPANCY:
            level = "critical"
            flags.append(f"{ward.name} occupancy {occ:.0%} — CRITICAL.")
        elif occ >= HIGH_OCCUPANCY:
            level = "high"
            flags.append(f"{ward.name} occupancy {occ:.0%} — HIGH.")
        elif occ >= 0.70:
            level = "moderate"
        else:
            level = "normal"

        if staffed_avail == 0 and ward.occupied_beds < ward.total_beds:
            flags.append(f"{ward.name}: physical beds available but none are staffed.")

        return WardCapacityStatus(
            ward_name=ward.name,
            total_beds=ward.total_beds,
            occupied_beds=ward.occupied_beds,
            staffed_available=staffed_avail,
            occupancy_rate=occ,
            pressure_level=level,
            flags=flags,
        )
