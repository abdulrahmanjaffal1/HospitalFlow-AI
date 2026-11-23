"""Deterministic behaviour of all four scenarios (no AI involved)."""

import pytest

from data.hospital_data import apply_scenario
from agents.capacity_agent import CapacityAgent
from agents.patient_flow_agent import PatientFlowAgent
from agents.staffing_agent import StaffingAgent
from agents.coordinator_agent import CoordinatorAgent


def run(scenario, coordinator=None, use_ai=True):
    snap = apply_scenario(scenario)
    cap = CapacityAgent().run(snap)
    flow = PatientFlowAgent().run(snap)
    staff = StaffingAgent().run(snap)
    return (coordinator or CoordinatorAgent()).run(cap, flow, staff, snap.notes, use_ai=use_ai)


EXPECTED = {
    "baseline": ("normal", ["Continue Standard Operations"]),
    "arrival_surge": (
        "critical",
        ["Manage Patient Arrival Surge", "Address Nurse-to-Patient Ratio Breach",
         "Monitor Critical Ward Occupancy"],
    ),
    "staffing_shortage": ("critical", ["Address Nurse-to-Patient Ratio Breach"]),
    "discharge_delay": ("high", ["Resolve Discharge Bottleneck", "Monitor Critical Ward Occupancy"]),
}


@pytest.mark.parametrize("scenario", EXPECTED)
def test_status_and_recommendations(scenario):
    report = run(scenario)
    status, titles = EXPECTED[scenario]
    assert report.overall_status == status
    assert [r.title for r in report.recommendations] == titles


@pytest.mark.parametrize("scenario", EXPECTED)
def test_recommendations_sorted_and_unique(scenario):
    recs = run(scenario).recommendations
    assert [r.priority for r in recs] == sorted((r.priority for r in recs), reverse=True)
    assert len({r.id for r in recs}) == len(recs)


@pytest.mark.parametrize("scenario", ["arrival_surge", "staffing_shortage", "discharge_delay"])
def test_incident_recommendations_wait_for_manager(scenario):
    for rec in run(scenario).recommendations:
        assert rec.requires_approval is True
        assert rec.status == "pending"


def test_baseline_has_no_flags_requiring_action():
    report = run("baseline")
    assert not report.capacity_report.shortage_predicted
    assert not report.flow_report.arrival_surge_detected
    assert not report.flow_report.discharge_delay_detected
    assert report.staffing_report.wards_ratio_breached == []


def test_scenarios_do_not_mutate_baseline():
    from data.hospital_data import BASELINE
    before = BASELINE.occupied_beds
    for s in EXPECTED:
        apply_scenario(s)
    assert BASELINE.occupied_beds == before


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError):
        apply_scenario("meteor_strike")


def test_without_explainer_uses_rule_based_mode():
    report = run("arrival_surge")
    assert report.ai.status == "not_configured"
    assert "Overall hospital status" in report.situation_summary
    assert all(r.ai_explanation == "" for r in report.recommendations)
