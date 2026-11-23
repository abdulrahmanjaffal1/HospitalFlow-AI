"""
Live connection check for watsonx.ai — run after filling in .env:

    .venv/bin/python scripts/check_watsonx.py [scenario]

1. Shows the configuration being used (API key masked).
2. Confirms the model ID is currently served in the chosen region.
3. Runs the Coordinator Agent once with watsonx.ai and prints the briefing,
   per-recommendation explanations and any guardrail warnings.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.coordinator_agent import CoordinatorAgent
from agents.watsonx_explainer import WatsonxExplainer
from tests.test_scenarios import run


def main() -> int:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "arrival_surge"
    exp = WatsonxExplainer.from_env()
    cfg = exp.config
    masked = (cfg.api_key[:4] + "…" + cfg.api_key[-4:]) if len(cfg.api_key) > 8 else "(missing)"
    print(f"URL        : {cfg.url}\nProject ID : {cfg.project_id or '(missing)'}\n"
          f"API key    : {masked}\nModel      : {cfg.model_id}\n")

    if not exp.is_configured:
        print("✗ Not configured. Set WATSONX_APIKEY and WATSONX_PROJECT_ID in .env.")
        return 1

    specs_url = (f"{cfg.url}/ml/v1/foundation_model_specs?version=2025-01-01"
                 "&filters=function_text_chat,!lifecycle_withdrawn:and&limit=200")
    try:
        with urllib.request.urlopen(specs_url, timeout=15) as resp:
            ids = [m["model_id"] for m in json.load(resp).get("resources", [])]
        if cfg.model_id in ids:
            print(f"✓ {cfg.model_id} is available for chat in this region.")
        else:
            print(f"✗ {cfg.model_id} is NOT served for chat here. Available: {', '.join(ids)}")
            return 1
    except Exception as exc:  # pre-check only; the real call below is authoritative
        print(f"! Could not list models ({exc}); continuing.")

    report = run(scenario, CoordinatorAgent(explainer=exp))
    ai = report.ai
    print(f"\nScenario: {scenario} · rule-based status: {report.overall_status.upper()}")
    print(f"watsonx.ai status: {ai.status} · {ai.latency_s:.1f}s")
    if ai.error:
        print(f"✗ Error: {ai.error}")
        return 1
    print(f"\n--- Situation briefing ---\n{ai.situation_summary}")
    for label, items in (("Key risks", ai.key_risks), ("Watch next", ai.watch_next)):
        if items:
            print(f"\n{label}:\n" + "\n".join(f"  - {i}" for i in items))
    print("\n--- Recommendations (priority set by rules) ---")
    for rec in report.recommendations:
        print(f"[{rec.id}] P{rec.priority} {rec.title}\n    AI: {rec.ai_explanation or '(none)'}")
    for w in ai.guardrail_warnings:
        print(f"🛡️  {w}")
    return 0 if ai.has_content else 1


if __name__ == "__main__":
    sys.exit(main())
