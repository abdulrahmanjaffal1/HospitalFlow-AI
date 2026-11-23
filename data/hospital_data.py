"""
Synthetic hospital dataset for HospitalFlow AI.

All data is fictional and created solely for educational demonstration purposes.
This prototype does NOT use real patient data, clinical records, or actual hospital operations.
"""

from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class Ward:
    name: str
    total_beds: int
    occupied_beds: int
    staffed_ratio: float          # fraction of total beds that are staffed right now
    nurse_to_patient_ratio: float # required nurses per patient
    nurses_available: int
    description: str


@dataclass
class HospitalSnapshot:
    """Represents a point-in-time operational snapshot of the fictional hospital."""
    hospital_name: str
    snapshot_label: str           # e.g. "Baseline", "Surge"
    wards: List[Ward]
    expected_arrivals_next_4h: int
    expected_discharges_next_4h: int
    pending_transfers_in: int
    pending_transfers_out: int
    ambulance_divert_active: bool
    notes: str = ""

    # --- derived convenience properties ---

    @property
    def total_beds(self) -> int:
        return sum(w.total_beds for w in self.wards)

    @property
    def occupied_beds(self) -> int:
        return sum(w.occupied_beds for w in self.wards)

    @property
    def available_beds(self) -> int:
        return self.total_beds - self.occupied_beds

    @property
    def staffed_available_beds(self) -> int:
        """Beds that are both unoccupied AND staffed."""
        total = 0
        for w in self.wards:
            ward_staffed = int(w.total_beds * w.staffed_ratio)
            ward_available_staffed = max(0, ward_staffed - w.occupied_beds)
            total += ward_available_staffed
        return total

    @property
    def occupancy_rate(self) -> float:
        return self.occupied_beds / self.total_beds if self.total_beds else 0.0

    @property
    def ward_dict(self) -> Dict[str, Ward]:
        return {w.name: w for w in self.wards}


# ---------------------------------------------------------------------------
# Baseline fictional hospital — "Riverside General Hospital"
# ---------------------------------------------------------------------------

def _baseline_wards() -> List[Ward]:
    return [
        Ward(
            name="Emergency Department",
            total_beds=30,
            occupied_beds=22,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 3,
            nurses_available=8,
            description="24/7 acute assessment and treatment",
        ),
        Ward(
            name="Medical Ward A",
            total_beds=40,
            occupied_beds=34,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 6,
            nurses_available=7,
            description="General internal medicine",
        ),
        Ward(
            name="Medical Ward B",
            total_beds=40,
            occupied_beds=29,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 6,
            nurses_available=7,
            description="General internal medicine overflow",
        ),
        Ward(
            name="Surgical Ward",
            total_beds=35,
            occupied_beds=28,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 5,
            nurses_available=7,
            description="Post-operative and elective surgical patients",
        ),
        Ward(
            name="ICU",
            total_beds=16,
            occupied_beds=12,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 1,
            nurses_available=14,
            description="Intensive care — 1:1 nurse-to-patient",
        ),
        Ward(
            name="Paediatric Ward",
            total_beds=20,
            occupied_beds=11,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 4,
            nurses_available=5,
            description="Children aged 0–16",
        ),
        Ward(
            name="Maternity",
            total_beds=18,
            occupied_beds=13,
            staffed_ratio=1.0,
            nurse_to_patient_ratio=1 / 3,
            nurses_available=5,
            description="Antenatal, delivery, and postnatal",
        ),
    ]


BASELINE: HospitalSnapshot = HospitalSnapshot(
    hospital_name="Riverside General Hospital (Fictional)",
    snapshot_label="Baseline — Normal Operations",
    wards=_baseline_wards(),
    expected_arrivals_next_4h=18,
    expected_discharges_next_4h=14,
    pending_transfers_in=3,
    pending_transfers_out=2,
    ambulance_divert_active=False,
    notes="Typical weekday morning. No active incidents.",
)


# ---------------------------------------------------------------------------
# Scenario modifiers
# ---------------------------------------------------------------------------

def apply_scenario(scenario: str) -> HospitalSnapshot:
    """
    Returns a new HospitalSnapshot with the named scenario applied.

    Scenarios are FICTIONAL and for educational demonstration only.
    'baseline'           — normal operations
    'arrival_surge'      — mass-casualty / seasonal surge
    'staffing_shortage'  — multiple call-outs reduce ward staffing
    'discharge_delay'    — delayed discharges block available beds
    """
    import copy
    snap = copy.deepcopy(BASELINE)

    if scenario == "baseline":
        pass  # no changes

    elif scenario == "arrival_surge":
        snap.snapshot_label = "Scenario: Patient Arrival Surge"
        snap.expected_arrivals_next_4h = 42        # 2.3× normal
        snap.pending_transfers_in = 8
        snap.ambulance_divert_active = False        # divert not yet activated
        # ED and medical wards under pressure
        snap.ward_dict["Emergency Department"].occupied_beds = 27
        snap.ward_dict["Medical Ward A"].occupied_beds = 38
        snap.ward_dict["Medical Ward B"].occupied_beds = 36
        snap.notes = (
            "Regional road incident + seasonal flu peak. "
            "ED near capacity. Medical wards filling rapidly."
        )

    elif scenario == "staffing_shortage":
        snap.snapshot_label = "Scenario: Staffing Shortage"
        snap.expected_arrivals_next_4h = 20        # slightly elevated
        # Nurse call-outs reduce staffed ratios
        snap.ward_dict["Medical Ward A"].nurses_available = 4   # was 7
        snap.ward_dict["Medical Ward A"].staffed_ratio = 0.60
        snap.ward_dict["Medical Ward B"].nurses_available = 3   # was 7
        snap.ward_dict["Medical Ward B"].staffed_ratio = 0.55
        snap.ward_dict["Surgical Ward"].nurses_available = 4    # was 7
        snap.ward_dict["Surgical Ward"].staffed_ratio = 0.70
        snap.notes = (
            "Seven nurses called in sick overnight (gastroenteritis outbreak among staff). "
            "Agency cover not yet confirmed."
        )

    elif scenario == "discharge_delay":
        snap.snapshot_label = "Scenario: Unexpected Discharge Delay"
        snap.expected_discharges_next_4h = 3       # was 14
        snap.expected_arrivals_next_4h = 20
        # Beds remain occupied because discharges are stuck
        snap.ward_dict["Medical Ward A"].occupied_beds = 39
        snap.ward_dict["Medical Ward B"].occupied_beds = 37
        snap.ward_dict["Surgical Ward"].occupied_beds = 33
        snap.notes = (
            "Pharmacy backlog and social-care assessment delays preventing 11 patients "
            "from being discharged as planned."
        )

    else:
        raise ValueError(f"Unknown scenario: {scenario!r}")

    return snap
