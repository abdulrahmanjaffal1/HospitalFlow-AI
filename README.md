# HospitalFlow AI — README

## Overview
HospitalFlow AI is an agentic AI hospital operations coordinator built for the
**IBM SkillsBuild AI Experiential Learning Lab**.

It helps hospital capacity managers identify potential bed-capacity problems,
investigate operational constraints, and review AI-generated recommendations
before approving any response.

> ⚠️ **DISCLAIMER: All hospital data is entirely fictional.**
> This is an educational operational decision-support prototype, NOT a clinical
> decision-making system. Do not use with real patient data.

---

## Project Structure

```
HospitalFlow.AI/
├── app.py                         # Streamlit entry point
├── requirements.txt
├── data/
│   └── hospital_data.py           # Synthetic dataset + scenario modifiers
├── agents/
│   ├── capacity_agent.py          # Bed capacity analysis (deterministic rules)
│   ├── patient_flow_agent.py      # Arrival/discharge flow analysis
│   ├── staffing_agent.py          # Staffing constraint analysis
│   └── coordinator_agent.py       # Combines findings → recommendations
└── ui/
    ├── dashboard.py               # Metrics dashboard panel
    └── approval.py                # Human approval interface
```

---

## Quick Start

### 1. Prerequisites
- Python 3.10 or later
- pip

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the application
```bash
streamlit run app.py
```

The app will open at **http://localhost:8501** in your browser.

---

## Using the Application

### Scenarios
Select a scenario from the sidebar and click **Run Analysis**:

| Scenario | Description |
|---|---|
| **Baseline** | Normal weekday operations — no active incidents |
| **Patient Arrival Surge** | Regional incident + seasonal flu peak — high arrivals |
| **Staffing Shortage** | Seven nurses called in sick — reduced ward staffing |
| **Unexpected Discharge Delay** | Pharmacy/social-care backlog — discharges blocked |

### Tabs
- **📊 Dashboard** — KPI tiles, ward-level occupancy table, operational flags
- **🔍 Agent Analysis** — Coordinator summary and per-agent detail panels
- **✅ Recommendations & Approval** — Review and approve/modify/reject each recommendation

### Re-analysis
Click **Re-run Current Scenario** (Approval tab) or change the scenario in the
sidebar and click **Run Analysis** to refresh all calculations.

---

## Architecture

### Agents (current implementation)
All agent logic is **deterministic rule-based Python calculation**.
No LLM or external AI service is called in this MVP.

| Agent | Responsibility |
|---|---|
| **Capacity Agent** | Calculates occupancy, staffed-available beds, projected shortfalls |
| **Patient Flow Agent** | Analyses arrivals, discharges, transfers — detects surge/delay |
| **Staffing Agent** | Checks nurse-to-patient ratios, flags breaches, estimates locked beds |
| **Coordinator Agent** | Combines findings, applies priority rules, produces recommendations |

### Planned Integrations (not yet implemented)
| Component | Integration |
|---|---|
| LLM reasoning | **watsonx.ai** — replace template summaries with contextual natural-language analysis |
| Agent orchestration | **watsonx Orchestrate** — automated multi-agent pipeline and workflow triggers |
| External systems | Bed management system, HR scheduling, transfer coordination APIs |

---

## Development Notes

- The codebase is intentionally modular so each agent can be replaced independently.
- `HospitalSnapshot` and `Ward` dataclasses in `data/hospital_data.py` are the
  shared data contract between all agents.
- Scenario modifiers in `apply_scenario()` produce deep copies of the baseline —
  the original is never mutated.
- All Streamlit state is managed through `st.session_state` to support re-analysis
  without full page reloads.
