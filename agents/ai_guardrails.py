"""
AI Guardrails — HospitalFlow AI

Deterministic Python checks applied to every piece of text returned by the
watsonx.ai foundation model BEFORE it is shown to a hospital manager.

Design principle: the language model may only *explain*. It cannot create,
remove, re-prioritise, approve, or execute recommendations. Those remain the
job of the rule-based agents and the human approval step.

Checks performed:
  1. Action-claim check  — withholds any AI text that states or implies an
                           action has already been taken (e.g. "I have
                           activated the surge protocol"). Nothing in this
                           system executes actions; text claiming otherwise
                           would mislead the manager.
  2. Grounding check     — flags any number in the AI text that does not
                           appear in the structured data the model was given
                           (a common sign of hallucinated figures).
  3. ID check            — drops explanations for recommendation IDs the
                           rule engine did not produce.
  4. Sanitisation        — strips HTML tags, escapes Markdown maths markers,
                           and truncates overly long output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

MAX_SUMMARY_CHARS = 1500
MAX_EXPLANATION_CHARS = 700
MAX_LIST_ITEMS = 5
MAX_LIST_ITEM_CHARS = 300

# ---------------------------------------------------------------------------
# Output structure shared by the explainer, guardrails, coordinator and UI
# ---------------------------------------------------------------------------


@dataclass
class AIExplanation:
    # "ok"             — model responded and output passed all checks
    # "ok_with_warnings" — shown, but some figures could not be verified
    # "withheld"       — model responded but output failed a safety check
    # "not_configured" — no watsonx.ai credentials found
    # "disabled"       — manager turned AI explanations off
    # "error"          — call to watsonx.ai failed
    status: str
    model_id: str = ""
    situation_summary: str = ""
    key_risks: List[str] = field(default_factory=list)
    watch_next: List[str] = field(default_factory=list)
    recommendation_explanations: Dict[str, str] = field(default_factory=dict)
    guardrail_warnings: List[str] = field(default_factory=list)
    error: str = ""
    latency_s: float = 0.0

    @property
    def has_content(self) -> bool:
        return self.status in ("ok", "ok_with_warnings") and bool(
            self.situation_summary or self.recommendation_explanations
        )


# ---------------------------------------------------------------------------
# 1. Action-claim detection
# ---------------------------------------------------------------------------

_ACTION_VERBS = (
    r"activated|approved|authori[sz]ed|notified|contacted|escalated|executed|"
    r"implemented|initiated|ordered|scheduled|diverted|discharged|transferred|"
    r"redeployed|opened|closed|cancelled|canceled|booked|requested|deployed"
)

_ACTION_CLAIM_PATTERNS = [
    # "I have activated…", "We notified…", "I've escalated…"
    re.compile(rf"\b(?:i|we)(?:'ve|\s+have|\s+had)?\s+(?:already\s+)?(?:{_ACTION_VERBS})\b", re.I),
    # "…has been activated", "…have already been notified"
    re.compile(rf"\b(?:has|have)\s+(?:already\s+)?been\s+(?:{_ACTION_VERBS})\b", re.I),
    # "…was automatically approved", "auto-approved", "automatically executed"
    re.compile(r"\bauto(?:matically|-)\s*(?:approved|executed|activated|implemented)\b", re.I),
]

# Words that make a sentence hypothetical ("once it has been approved…").
_CONDITIONAL = re.compile(r"\b(?:once|after|if|when|until|unless|before|whether)\b", re.I)


def find_action_claims(text: str) -> List[str]:
    """Return sentences that claim an action has already been carried out."""
    hits: List[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        for pattern in _ACTION_CLAIM_PATTERNS:
            m = pattern.search(sentence)
            if m and not _CONDITIONAL.search(sentence[: m.start()]):
                hits.append(sentence.strip())
                break
    return hits


# ---------------------------------------------------------------------------
# 2. Numeric grounding
# ---------------------------------------------------------------------------

_REC_ID = re.compile(r"\bREC-\d+\b", re.I)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _numbers_in(text: str) -> List[float]:
    text = _REC_ID.sub(" ", text or "")
    return [float(n) for n in _NUMBER.findall(text)]


def allowed_numbers(*sources: object) -> set:
    """Every number appearing in the given objects (serialised as JSON)."""
    allowed: set = {0.0, 1.0}
    for src in sources:
        blob = src if isinstance(src, str) else json.dumps(src, default=str)
        for n in _numbers_in(blob):
            allowed.add(n)
            allowed.add(round(n, 1))
            # Rates like 0.8333 are commonly written as "83%"
            if 0 < n <= 1.5:
                allowed.add(float(round(n * 100)))
    return allowed


def ungrounded_numbers(text: str, allowed: Iterable[float]) -> List[str]:
    allowed = list(allowed)
    bad: List[str] = []
    for n in _numbers_in(text):
        if not any(abs(n - a) < 0.051 for a in allowed):
            label = f"{n:g}"
            if label not in bad:
                bad.append(label)
    return bad


# ---------------------------------------------------------------------------
# 4. Sanitisation
# ---------------------------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]{0,200}>")


def sanitise(text: str, limit: int) -> str:
    text = _HTML_TAG.sub("", str(text or "")).strip()
    text = text.replace("$", r"\$")  # avoid Streamlit LaTeX rendering
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_guardrails(
    ai: AIExplanation,
    facts: dict,
    recommendations: List[dict],
) -> AIExplanation:
    """Validate model output against the deterministic facts it was given."""
    if ai.status not in ("ok", "ok_with_warnings"):
        return ai

    valid_ids = {r["id"] for r in recommendations}
    allowed = allowed_numbers(facts, recommendations)
    warnings: List[str] = list(ai.guardrail_warnings)

    # --- sanitise -----------------------------------------------------------
    ai.situation_summary = sanitise(ai.situation_summary, MAX_SUMMARY_CHARS)
    ai.key_risks = [sanitise(x, MAX_LIST_ITEM_CHARS) for x in ai.key_risks[:MAX_LIST_ITEMS] if x]
    ai.watch_next = [sanitise(x, MAX_LIST_ITEM_CHARS) for x in ai.watch_next[:MAX_LIST_ITEMS] if x]

    # --- ID check -------------------------------------------------------------
    cleaned: Dict[str, str] = {}
    for rec_id, text in ai.recommendation_explanations.items():
        rec_id = str(rec_id).strip().upper()
        if rec_id not in valid_ids:
            warnings.append(f"Dropped explanation for unknown recommendation ID {rec_id!r}.")
            continue
        cleaned[rec_id] = sanitise(text, MAX_EXPLANATION_CHARS)
    ai.recommendation_explanations = cleaned

    # --- action-claim check (withhold) ---------------------------------------
    briefing_text = "\n".join([ai.situation_summary, *ai.key_risks, *ai.watch_next])
    if find_action_claims(briefing_text):
        ai.situation_summary, ai.key_risks, ai.watch_next = "", [], []
        warnings.append(
            "Situation briefing withheld: the AI text implied an action had already "
            "been taken. No action is ever executed without manager approval."
        )
    for rec_id in list(ai.recommendation_explanations):
        if find_action_claims(ai.recommendation_explanations[rec_id]):
            del ai.recommendation_explanations[rec_id]
            warnings.append(
                f"AI explanation for {rec_id} withheld: it implied the action had "
                "already been carried out."
            )

    # --- grounding check (warn) ----------------------------------------------
    all_text = "\n".join(
        [ai.situation_summary, *ai.key_risks, *ai.watch_next, *ai.recommendation_explanations.values()]
    )
    bad = ungrounded_numbers(all_text, allowed)
    if bad:
        warnings.append(
            "The AI text mentions figure(s) not found in the source data: "
            + ", ".join(bad)
            + ". Verify against the rule-based figures before acting."
        )

    ai.guardrail_warnings = warnings
    if not ai.situation_summary and not ai.recommendation_explanations:
        ai.status = "withheld"
    elif warnings:
        ai.status = "ok_with_warnings"
    return ai
