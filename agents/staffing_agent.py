"""
Staffing Agent — HospitalFlow AI

Responsibility: identify staffing constraints that reduce the number of beds
that can safely be opened or maintained, and flag wards where nurse-to-patient
ratios are breached or at risk.

IMPLEMENTATION NOTE:
All logic is deterministic Python calculation based on configured ratios.
Planned integration: watsonx.ai to reason about staffing reallocation options
and trade-offs; watsonx Orchestrate to trigger agency-staff request workflows.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
from data.hospital_data import HospitalSnapshot, Ward


# ---------------------------------------------------------------------------
# Output structures
# ---------------------------------------------------------------------------

@dataclass
class WardStaffingStatus:
    ward_name: str
    nurses_available: int
    nurses_required: int          # for current patient load
    nurses_deficit: int           # positive = shortage
    max_patients_supportable: int # most patients current nurses can safely cover
    ratio_breached: bool
    flags: List[str] = field(default_factory=list)


@dataclass
class StaffingReport:
    total_nurses: int
    ward_statuses: List[WardStaffingStatus]
    wards_ratio_breached: List[str]
    effective_bed_reduction: int   # beds effectively lost due to staffing
    flags: List[str] = field(default_factory=list)
    agent_note: str = ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class StaffingAgent:
    """
    Evaluates nurse-to-patient ratios across all wards to determine
    whether staffing levels are sufficient to support current and
    projected patient volumes.

    Inputs : HospitalSnapshot
    Outputs: StaffingReport
    """

    name = "Staffing Agent"

    def run(self, snapshot: HospitalSnapshot) -> StaffingReport:
        ward_statuses: List[WardStaffingStatus] = []
        total_nurses = sum(w.nurses_available for w in snapshot.wards)
        flags: List[str] = []
        effective_bed_reduction = 0

        for ward in snapshot.wards:
            status = self._assess_ward(ward)
            ward_statuses.append(status)
            if status.ratio_breached:
                flags.append(
                    f"⚠️  {ward.name}: nurse-to-patient ratio breached. "
                    f"Need {status.nurses_required}, have {status.nurses_available}."
                )
            if status.nurses_deficit > 0:
                # beds effectively unusable due to staffing
                beds_locked = status.nurses_deficit * int(1 / ward.nurse_to_patient_ratio) \
                    if ward.nurse_to_patient_ratio > 0 else 0
                effective_bed_reduction += beds_locked

        breached_wards = [s.ward_name for s in ward_statuses if s.ratio_breached]

        if effective_bed_reduction > 0:
            flags.append(
                f"⚠️  Staffing shortfall effectively locks ~{effective_bed_reduction} beds "
                f"across the hospital."
            )

        if not flags:
            flags.append("✅  All wards meet minimum nurse-to-patient ratio requirements.")

        agent_note = (
            "Analysis produced by deterministic ratio calculations. "
            "Planned: watsonx.ai to suggest staffing reallocation strategies "
            "and reason about cross-ward deployment options."
        )

        return StaffingReport(
            total_nurses=total_nurses,
            ward_statuses=ward_statuses,
            wards_ratio_breached=breached_wards,
            effective_bed_reduction=effective_bed_reduction,
            flags=flags,
            agent_note=agent_note,
        )

    # ------------------------------------------------------------------

    def _assess_ward(self, ward: Ward) -> WardStaffingStatus:
        required = ward.occupied_beds * ward.nurse_to_patient_ratio
        required_int = int(required) + (1 if required % 1 > 0 else 0)   # ceiling
        deficit = max(0, required_int - ward.nurses_available)
        breached = deficit > 0

        # maximum patients supportable with current staff
        max_patients = int(ward.nurses_available / ward.nurse_to_patient_ratio) \
            if ward.nurse_to_patient_ratio > 0 else ward.total_beds

        flags: List[str] = []
        if breached:
            flags.append(
                f"Ratio breached — {ward.nurses_available} nurses for "
                f"{ward.occupied_beds} patients (need {required_int})."
            )
        elif ward.nurses_available - required_int <= 1:
            flags.append(
                f"Ratio marginal — only {ward.nurses_available - required_int} spare nurse(s)."
            )

        return WardStaffingStatus(
            ward_name=ward.name,
            nurses_available=ward.nurses_available,
            nurses_required=required_int,
            nurses_deficit=deficit,
            max_patients_supportable=max_patients,
            ratio_breached=breached,
            flags=flags,
        )
