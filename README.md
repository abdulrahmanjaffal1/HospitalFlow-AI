# HospitalFlow AI

**Agentic AI hospital operations coordinator** — IBM SkillsBuild AI Experiential Learning Lab

HospitalFlow AI helps hospital capacity managers spot bed-capacity problems early,
understand *why* they are happening, and review recommended responses before anything
is done. Specialised agents analyse capacity, patient flow and staffing. A Coordinator
Agent combines their findings and uses an **IBM watsonx.ai** foundation model to
explain the situation in plain language. A manager approves, modifies or rejects every
recommendation.

> ⚠️ **All hospital data is fictional.** This is an educational operational
> decision-support prototype, not a clinical decision-making system.

---

## What is implemented vs. planned

| Capability | Status | How |
|---|---|---|
| Hospital dashboard (beds, occupancy, staffing, arrivals/discharges) | ✅ Implemented | Streamlit |
| 4 scenarios: Baseline, Arrival Surge, Staffing Shortage, Discharge Delay | ✅ Implemented | Synthetic data, `data/hospital_data.py` |
| Capacity, Patient Flow, Staffing agents | ✅ Implemented | Deterministic Python rules |
| Coordinator Agent: status + prioritised recommendations | ✅ Implemented | Deterministic Python rules |
| **Contextual situation briefing and per-recommendation explanations** | ✅ Implemented | **IBM watsonx.ai** (`ibm/granite-4-h-small`) via `ibm-watsonx-ai` SDK |
| Guardrails on AI output | ✅ Implemented | Deterministic checks, `agents/ai_guardrails.py` |
| Human approval (approve / modify / reject + notes) | ✅ Implemented | Streamlit; no action is executed by the system |
| Automatic fallback when watsonx.ai is unavailable | ✅ Implemented | Rule-based summary shown instead |
| Agent orchestration | 🔜 Planned | watsonx Orchestrate (see [Future work](#future-work-watsonx-orchestrate)) |
| Integration with real hospital systems (bed mgmt, HR rostering, transfers) | 🔜 Planned | — |
| Persistent audit log of manager decisions | 🔜 Planned | Decisions are held in the browser session only |

**What the AI does and does not do.** The watsonx.ai model *explains*. It does not
decide. Which recommendations exist, their priority, the hospital status, and whether
approval is needed are all set by the deterministic rule engine. The model receives
those results as structured facts and writes the narrative. The capacity, flow, and
staffing agents are rule-based by design, so their numbers are reproducible and auditable.

---

## Architecture

```
 Synthetic hospital snapshot (scenario)
        │
        ├──► Capacity Agent ──────┐
        ├──► Patient Flow Agent ──┤   deterministic Python
        └──► Staffing Agent ──────┤
                                  ▼
                   Coordinator Agent — rule engine
                   status · recommendations · priorities · approval flags
                                  │  structured facts (JSON)
                                  ▼
                   watsonx.ai foundation model (Granite 4)
                   situation briefing · key risks · per-recommendation context
                                  │
                                  ▼
                   Deterministic guardrails
                   action-claim check · number grounding · ID check · sanitise
                                  │
                                  ▼
                   Streamlit UI ──► Manager: Approve / Modify / Reject
```

### Safety design
- **Rules decide, AI explains.** The model cannot add, remove, re-order, re-prioritise
  or approve recommendations. Tests assert that every decision field is identical with
  AI on and off (`tests/test_ai_layer.py`).
- **Action-claim check.** AI text that says or implies something has already been done
  (for example "I have activated the surge protocol") is withheld. A warning is shown in its place.
- **Number grounding.** Any figure in AI text that is not in the source data is flagged
  so the manager can verify it.
- **Unknown IDs dropped.** Explanations for recommendation IDs the rule engine did not
  produce are discarded.
- **Sanitised output.** HTML is stripped and length is capped.
- **Graceful fallback.** If credentials are missing or the call fails, the app shows the
  rule-based summary and keeps working.
- **Human in the loop.** Every incident recommendation stays `pending` until a manager
  decides. Decisions reset when a new analysis is run.

---

## Quick start

Requires **Python 3.11–3.13**.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open **http://localhost:8501**. Without watsonx.ai credentials the app runs in rule-based
mode, and the sidebar shows *"watsonx.ai: Not configured"*.

---

## Connecting watsonx.ai

### 1. Associate the watsonx.ai Runtime with the project (one-time, in the browser)
1. Open **watsonx.ai Studio** (https://dataplatform.cloud.ibm.com/wx/home), go to
   **Projects** and open **HospitalFlow AI**.
2. Go to the **Manage** tab, then **Services & integrations**.
3. If no watsonx.ai Runtime is listed, click **Associate service**, tick your
   **watsonx.ai Runtime** instance, and click **Associate**.
4. Still under **Manage**, open **General** and copy the **Project ID**.

### 2. Create an API key
IBM Cloud console → **Manage → Access (IAM) → API keys → Create**. Copy it now, because it is
only shown once.

### 3. Configure the app
```bash
cp .env.example .env
# edit .env: set WATSONX_APIKEY and WATSONX_PROJECT_ID
# set WATSONX_URL to your Runtime's region if it is not Dallas (us-south)
```
`.env` is git-ignored. Never commit keys.

### 4. Verify, then run
```bash
python scripts/check_watsonx.py arrival_surge   # live check: prints the AI briefing
streamlit run app.py
```
The sidebar should show **watsonx.ai: Configured · `ibm/granite-4-h-small`**. Run a
scenario, then open the **🔍 Agent Analysis** tab for the briefing and the
**✅ Recommendations & Approval** tab for per-recommendation AI context.

| Variable | Required | Default |
|---|---|---|
| `WATSONX_APIKEY` | yes | — |
| `WATSONX_PROJECT_ID` | yes | — |
| `WATSONX_URL` | no | `https://us-south.ml.cloud.ibm.com` |
| `WATSONX_MODEL_ID` | no | `ibm/granite-4-h-small` |
| `WATSONX_ENABLED` | no | `true` (set `false` for an offline demo) |

**Model notes.** The Granite 3.x instruct models were withdrawn from watsonx.ai on
22 Feb 2026. `ibm/granite-4-h-small` is served in Dallas (us-south) and Frankfurt (eu-de).
In other regions, set `WATSONX_MODEL_ID=meta-llama/llama-3-3-70b-instruct`.
The Lite plan allows about 300,000 tokens/month. One analysis uses up to about 3,000
(roughly 100 analyses a month), and the model is only called when you click **Run Analysis**.

---

## Testing

```bash
python -m pytest -q
```

43 tests, all offline (watsonx.ai is replaced by a fake model):
- **`tests/test_scenarios.py`**: expected status and recommendations for all four
  scenarios, priority ordering, approval requirements, and baseline immutability.
- **`tests/test_ai_layer.py`**: AI never changes decision fields. Also covers rogue
  output (fake IDs, priority overrides), action-claim withholding, number grounding,
  HTML stripping, error fallback, non-JSON output, and the on/off toggle.
- **`tests/test_app_smoke.py`**: renders the real Streamlit app for each scenario,
  checks that decisions reset between analyses, and renders the AI panels.

The live watsonx.ai call is checked separately with `scripts/check_watsonx.py`.

---

## Future work: watsonx Orchestrate

**Not implemented.** Agent coordination today is a direct Python call sequence in
`app.py`. The planned design:

1. Expose each agent as an Orchestrate **tool** (a Python tool built with the watsonx
   Orchestrate ADK, or an OpenAPI endpoint wrapping the existing `run()` methods).
2. Define a **HospitalFlow Coordinator agent** in Orchestrate that calls the capacity,
   flow and staffing tools, then the explanation step, in place of `app.py`'s fixed sequence.
3. After a manager approves a recommendation, trigger a **workflow** such as a bank/agency
   staff request, a bed-manager notification, or a discharge-round task. The human
   approval step remains the gate. Nothing runs before approval.
4. Add persistent audit logging of decisions and resulting actions.

---

## Project structure

```
├── app.py                        # Streamlit entry point
├── requirements.txt
├── .env.example                  # watsonx.ai configuration template
├── data/hospital_data.py         # Synthetic dataset + scenario modifiers
├── agents/
│   ├── capacity_agent.py         # Bed capacity analysis (rules)
│   ├── patient_flow_agent.py     # Arrival/discharge flow analysis (rules)
│   ├── staffing_agent.py         # Nurse-ratio analysis (rules)
│   ├── coordinator_agent.py      # Rules → recommendations; calls watsonx.ai to explain
│   ├── watsonx_explainer.py      # IBM watsonx.ai client + prompt
│   └── ai_guardrails.py          # Deterministic checks on AI output
├── ui/
│   ├── dashboard.py              # KPI tiles, ward table, flags
│   ├── ai_panel.py               # watsonx.ai situation briefing
│   └── approval.py               # Human approval interface
├── scripts/check_watsonx.py      # Live watsonx.ai connection check
└── tests/                        # pytest suite (offline)
```

Built with IBM Bob IDE, Python, Streamlit, and IBM watsonx.ai.
