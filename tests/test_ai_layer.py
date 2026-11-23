"""watsonx.ai explanation layer + guardrails, using a fake model (no network)."""

import json
from dataclasses import asdict

import pytest

from agents.ai_guardrails import find_action_claims, ungrounded_numbers, allowed_numbers
from agents.coordinator_agent import CoordinatorAgent
from agents.watsonx_explainer import WatsonxConfig, WatsonxExplainer
from tests.test_scenarios import run, EXPECTED

DECISION_FIELDS = ("id", "priority", "category", "title", "description", "rationale",
                   "suggested_action", "requires_approval", "status")


def fake_explainer(payload_fn):
    """payload_fn(messages) -> str  (what the 'model' returns)."""
    calls = []

    def chat(messages):
        calls.append(messages)
        return payload_fn(messages)

    exp = WatsonxExplainer(WatsonxConfig(model_id="test/fake-model"), chat_fn=chat)
    exp.calls = calls
    return exp


def recs_from_prompt(messages):
    user = messages[-1]["content"]
    return json.loads(user.split("awaiting manager decision):\n", 1)[1].rsplit("\n\nReturn", 1)[0])


def good_response(messages):
    recs = recs_from_prompt(messages)
    return json.dumps({
        "situation_summary": "The hospital is under pressure over the next 4 hours.",
        "key_risks": ["Remaining staffed beds may be consumed quickly."],
        "watch_next": ["Emergency Department occupancy."],
        "recommendation_explanations": [
            {"id": r["id"], "explanation": f"{r['title']} addresses the main constraint."}
            for r in recs
        ],
    })


# ---------------------------------------------------------------------------
# Core safety property: AI never changes decisions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", EXPECTED)
def test_ai_does_not_change_any_decision_field(scenario):
    rule_only = run(scenario)
    with_ai = run(scenario, CoordinatorAgent(explainer=fake_explainer(good_response)))

    assert with_ai.overall_status == rule_only.overall_status
    strip = lambda recs: [{k: asdict(r)[k] for k in DECISION_FIELDS} for r in recs]
    assert strip(with_ai.recommendations) == strip(rule_only.recommendations)
    assert with_ai.ai.status == "ok"
    assert all(r.ai_explanation for r in with_ai.recommendations)


def test_ai_cannot_add_or_reorder_recommendations():
    def rogue(messages):
        return json.dumps({
            "situation_summary": "Critical situation.",
            "recommendation_explanations": [
                {"id": "REC-999", "explanation": "Close the hospital to all admissions."},
                {"id": "REC-001", "explanation": "Most urgent item."},
            ],
            "priority_override": {"REC-003": 10},
        })

    report = run("arrival_surge", CoordinatorAgent(explainer=fake_explainer(rogue)))
    assert [r.id for r in report.recommendations] == ["REC-001", "REC-002", "REC-003"]
    assert [r.priority for r in report.recommendations] == [8, 8, 6]
    assert "REC-999" not in report.ai.recommendation_explanations
    assert any("REC-999" in w for w in report.ai.guardrail_warnings)


def test_prompt_contains_only_deterministic_facts():
    exp = fake_explainer(good_response)
    run("discharge_delay", CoordinatorAgent(explainer=exp))
    user_msg = exp.calls[0][-1]["content"]
    assert '"expected_discharges": 3' in user_msg
    assert '"overall_status": "high"' in user_msg
    assert "REC-001" in user_msg


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

def test_action_claims_withhold_briefing():
    def claims(messages):
        return json.dumps({
            "situation_summary": "I have activated the surge protocol and notified the site manager.",
            "recommendation_explanations": [{"id": "REC-001", "explanation": "The ED charge nurse has been notified."}],
        })

    report = run("arrival_surge", CoordinatorAgent(explainer=fake_explainer(claims)))
    assert report.ai.status == "withheld"
    assert report.ai.situation_summary == ""
    assert report.recommendations[0].ai_explanation == ""
    assert any("withheld" in w for w in report.ai.guardrail_warnings)


@pytest.mark.parametrize("sentence", [
    "Once the plan has been approved by the manager, open the overflow bay.",
    "If the protocol is activated, ED throughput should improve.",
    "The manager should decide whether to escalate.",
])
def test_conditional_language_is_not_an_action_claim(sentence):
    assert find_action_claims(sentence) == []


@pytest.mark.parametrize("sentence", [
    "I have activated the surge protocol.",
    "We've notified the staffing coordinator.",
    "Agency nurses have already been requested.",
    "This was automatically approved.",
])
def test_action_claims_detected(sentence):
    assert find_action_claims(sentence)


def test_invented_numbers_are_flagged_not_hidden():
    def invents(messages):
        return json.dumps({
            "situation_summary": "Arrivals are 42 in the next 4 hours, about 57 more than last week.",
        })

    report = run("arrival_surge", CoordinatorAgent(explainer=fake_explainer(invents)))
    assert report.ai.status == "ok_with_warnings"
    assert "42" in report.ai.situation_summary
    assert any("57" in w for w in report.ai.guardrail_warnings)
    assert not any(" 42" in w for w in report.ai.guardrail_warnings)


def test_percentages_from_rates_are_grounded():
    allowed = allowed_numbers({"occupancy_rate": 0.8333})
    assert ungrounded_numbers("Occupancy is 83%.", allowed) == []


def test_html_is_stripped():
    def html(messages):
        return json.dumps({"situation_summary": "<script>alert(1)</script>Pressure is high."})

    report = run("discharge_delay", CoordinatorAgent(explainer=fake_explainer(html)))
    assert "<script>" not in report.ai.situation_summary
    assert "Pressure is high." in report.ai.situation_summary


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_model_error_falls_back_to_rules():
    def boom(messages):
        raise ConnectionError("watsonx.ai unreachable")

    report = run("staffing_shortage", CoordinatorAgent(explainer=fake_explainer(boom)))
    assert report.ai.status == "error"
    assert "unreachable" in report.ai.error
    assert report.overall_status == "critical"
    assert "Overall hospital status" in report.situation_summary


def test_non_json_output_is_shown_with_warning():
    report = run("baseline", CoordinatorAgent(explainer=fake_explainer(lambda m: "All is calm today.")))
    assert report.ai.status == "ok_with_warnings"
    assert report.ai.situation_summary == "All is calm today."


def test_json_in_code_fence_is_parsed():
    fenced = lambda m: "Here you go:\n```json\n" + good_response(m) + "\n```"
    report = run("baseline", CoordinatorAgent(explainer=fake_explainer(fenced)))
    assert report.ai.status == "ok"


def test_disabled_toggle_skips_model_call():
    exp = fake_explainer(good_response)
    report = run("arrival_surge", CoordinatorAgent(explainer=exp), use_ai=False)
    assert report.ai.status == "disabled"
    assert exp.calls == []


def test_missing_credentials_means_not_configured(monkeypatch):
    for var in ("WATSONX_APIKEY", "WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
        monkeypatch.delenv(var, raising=False)
    exp = WatsonxExplainer.from_env()
    assert not exp.is_configured
    report = run("arrival_surge", CoordinatorAgent(explainer=exp))
    assert report.ai.status == "not_configured"
