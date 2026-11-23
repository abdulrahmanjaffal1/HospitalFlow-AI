"""End-to-end Streamlit smoke tests: render the real app for every scenario."""

import pytest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

SCENARIOS = ["baseline", "arrival_surge", "staffing_shortage", "discharge_delay"]


@pytest.fixture(autouse=True)
def no_watsonx(monkeypatch):
    # Smoke tests must not call the real watsonx.ai service.
    monkeypatch.setenv("WATSONX_ENABLED", "false")


def _run_scenario(scenario):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.sidebar.radio[0].set_value(scenario).run()
    run_btn = next(b for b in at.sidebar.button if "Run Analysis" in b.label)
    run_btn.click().run()
    assert not at.exception
    return at


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_app_renders_each_scenario(scenario):
    at = _run_scenario(scenario)
    assert at.session_state["scenario"] == scenario
    assert at.session_state["coord_report"].ai.status == "not_configured"
    titles = [m.value for m in at.markdown]
    assert any("watsonx.ai Situation Briefing" in t for t in titles)


def test_decisions_reset_when_scenario_changes():
    at = _run_scenario("arrival_surge")
    at.radio(key="decision_REC-001").set_value("approved").run()
    assert at.session_state["decision_REC-001"] == "approved"

    at.sidebar.radio[0].set_value("discharge_delay").run()
    next(b for b in at.sidebar.button if "Run Analysis" in b.label).click().run()
    assert not at.exception
    assert at.radio(key="decision_REC-001").value == "pending"


def test_ai_briefing_and_recommendation_context_render():
    """Render the AI panels with a fake watsonx.ai model (no network)."""
    def page():
        from agents.coordinator_agent import CoordinatorAgent
        from agents.watsonx_explainer import WatsonxConfig, WatsonxExplainer
        from tests.test_ai_layer import good_response
        from tests.test_scenarios import run
        from ui.ai_panel import render_ai_briefing
        from ui.approval import render_approval_panel

        exp = WatsonxExplainer(WatsonxConfig(model_id="test/fake-model"), chat_fn=good_response)
        report = run("arrival_surge", CoordinatorAgent(explainer=exp))
        render_ai_briefing(report.ai)
        render_approval_panel(report.recommendations)

    at = AppTest.from_function(page, default_timeout=30).run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    captions = "\n".join(c.value for c in at.caption)
    assert "under pressure over the next 4 hours" in text
    assert text.count("AI context (watsonx.ai)") == 3
    assert "test/fake-model" in captions
    assert [r.value for r in at.radio] == ["pending", "pending", "pending"]
