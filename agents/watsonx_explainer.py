"""
watsonx.ai Explainer — HospitalFlow AI

Thin client around an IBM watsonx.ai foundation model (default: IBM Granite)
used by the Coordinator Agent to turn deterministic findings into a contextual,
plain-language briefing for the hospital operations manager.

Scope (deliberately narrow):
  - INPUT : structured facts + the rule engine's recommendations
  - OUTPUT: explanation text only (situation summary, risks, per-recommendation
            context). The model never decides what to do. Every output is
            checked by agents/ai_guardrails.py before it is displayed.

Configuration (environment variables or a local .env file):
  WATSONX_APIKEY      IBM Cloud API key                       (required)
  WATSONX_PROJECT_ID  watsonx.ai Studio project ID            (required)
  WATSONX_URL         Runtime region endpoint                 (default: Dallas)
  WATSONX_MODEL_ID    Foundation model ID                     (default below)
  WATSONX_ENABLED     "false" to force rule-based mode        (default: true)
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from agents.ai_guardrails import AIExplanation

DEFAULT_URL = "https://us-south.ml.cloud.ibm.com"
# Granite 3.x instruct models were withdrawn from watsonx.ai on 2026-02-22.
# granite-4-h-small is IBM's replacement and is served in us-south and eu-de.
# Alternative available in every region: meta-llama/llama-3-3-70b-instruct
DEFAULT_MODEL_ID = "ibm/granite-4-h-small"

ChatFn = Callable[[List[Dict[str, str]]], str]


SYSTEM_PROMPT = """You are the explanation module of HospitalFlow AI, a decision-support \
prototype that helps a hospital operations manager understand bed-capacity pressure. \
All data is fictional.

Your ONLY job is to explain the situation and the recommendations that a deterministic \
rule engine has already produced. Follow these rules strictly:
1. Use only the facts and numbers in the JSON you are given. Never invent, estimate, or \
compute new figures. If a number is not in the input, do not state it.
2. Do not add, remove, merge, or re-prioritise recommendations. Explain each one by its id.
3. Nothing has been done yet. Every recommendation is waiting for the manager's decision. \
Never say or imply that an action has been taken, activated, approved, or notified.
4. This is operational (beds, flow, staffing), not clinical. Give no advice about the \
diagnosis or treatment of any patient.
5. Be concise, calm, and specific. Plain text only: no markdown headings, no HTML.

Respond with a single JSON object and nothing else, using exactly this shape:
{
  "situation_summary": "3-5 sentences explaining what is happening and why it matters now",
  "key_risks": ["short risk", "..."],
  "watch_next": ["short item to monitor in the next 4 hours", "..."],
  "recommendation_explanations": [
    {"id": "REC-001", "explanation": "2-3 sentences: why this matters now and what the trade-off is"}
  ]
}"""


@dataclass
class WatsonxConfig:
    api_key: str = ""
    project_id: str = ""
    url: str = DEFAULT_URL
    model_id: str = DEFAULT_MODEL_ID
    enabled: bool = True
    max_tokens: int = 900
    timeout_s: int = 60

    @classmethod
    def from_env(cls) -> "WatsonxConfig":
        return cls(
            api_key=(os.getenv("WATSONX_APIKEY") or os.getenv("WATSONX_API_KEY") or "").strip(),
            project_id=(os.getenv("WATSONX_PROJECT_ID") or "").strip(),
            url=(os.getenv("WATSONX_URL") or DEFAULT_URL).strip().rstrip("/"),
            model_id=(os.getenv("WATSONX_MODEL_ID") or DEFAULT_MODEL_ID).strip(),
            enabled=(os.getenv("WATSONX_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")),
        )


class WatsonxExplainer:
    """Generates explanation text via watsonx.ai. Safe to construct without credentials."""

    def __init__(self, config: WatsonxConfig, chat_fn: Optional[ChatFn] = None) -> None:
        self.config = config
        self._chat_fn = chat_fn  # injectable for tests; built lazily otherwise

    @classmethod
    def from_env(cls) -> "WatsonxExplainer":
        return cls(WatsonxConfig.from_env())

    @property
    def is_configured(self) -> bool:
        if self._chat_fn is not None:
            return self.config.enabled
        return bool(self.config.enabled and self.config.api_key and self.config.project_id)

    # ------------------------------------------------------------------

    def explain(self, facts: dict, recommendations: List[dict]) -> AIExplanation:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Hospital facts (computed by deterministic agents):\n"
                    + json.dumps(facts, indent=1)
                    + "\n\nRecommendations from the rule engine (awaiting manager decision):\n"
                    + json.dumps(recommendations, indent=1)
                    + "\n\nReturn the JSON object now."
                ),
            },
        ]
        start = time.perf_counter()
        raw = self._chat(messages)
        latency = time.perf_counter() - start
        return self.parse_response(raw, self.config.model_id, latency)

    # ------------------------------------------------------------------

    @staticmethod
    def parse_response(raw: str, model_id: str, latency_s: float = 0.0) -> AIExplanation:
        data = _extract_json(raw)
        if data is None:
            # Model ignored the format: keep its prose as the summary, no per-rec text.
            return AIExplanation(
                status="ok_with_warnings",
                model_id=model_id,
                situation_summary=(raw or "").strip(),
                guardrail_warnings=["Model did not return structured JSON; showing its text as-is."],
                latency_s=latency_s,
            )

        explanations: Dict[str, str] = {}
        for item in data.get("recommendation_explanations") or []:
            if isinstance(item, dict) and item.get("id") and item.get("explanation"):
                explanations[str(item["id"])] = str(item["explanation"])

        return AIExplanation(
            status="ok",
            model_id=model_id,
            situation_summary=str(data.get("situation_summary") or ""),
            key_risks=[str(x) for x in (data.get("key_risks") or []) if x],
            watch_next=[str(x) for x in (data.get("watch_next") or []) if x],
            recommendation_explanations=explanations,
            latency_s=latency_s,
        )

    def _chat(self, messages: List[Dict[str, str]]) -> str:
        if self._chat_fn is None:
            self._chat_fn = self._build_watsonx_chat_fn()
        return self._chat_fn(messages)

    def _build_watsonx_chat_fn(self) -> ChatFn:
        # Imported lazily so the app runs (rule-based) without the SDK installed.
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        model = ModelInference(
            model_id=self.config.model_id,
            credentials=Credentials(url=self.config.url, api_key=self.config.api_key),
            project_id=self.config.project_id,
        )
        params = {
            "max_tokens": self.config.max_tokens,
            "temperature": 0,
            "time_limit": self.config.timeout_s * 1000,
        }

        def chat(messages: List[Dict[str, str]]) -> str:
            response = model.chat(messages=messages, params=params)
            return response["choices"][0]["message"]["content"]

        return chat


def _extract_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1]):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None
