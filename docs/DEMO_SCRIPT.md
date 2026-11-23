# HospitalFlow AI: demo recording script (about 4 minutes)

**Before recording**
- `.env` filled in. `python scripts/check_watsonx.py` prints a briefing.
- `streamlit run app.py`. The sidebar shows **watsonx.ai: Configured · ibm/granite-4-h-small**.
- Browser zoom at 90%, one tab open, notifications off.
- Backup: if the network fails mid-demo, the app falls back to rule-based summaries and
  says so on screen. Say that out loud; it is a feature.

| # | Time | On screen | Say |
|---|---|---|---|
| 1 | 0:00 | Dashboard, **Baseline** | "Riverside General is a fictional 199-bed hospital. Three agents analyse capacity, patient flow and staffing. Baseline is normal: 75% occupancy, 50 staffed beds free." |
| 2 | 0:30 | Agent Analysis tab | "The Coordinator Agent sends the agents' structured findings to IBM watsonx.ai, Granite 4, which writes this briefing. Rules set the status; the model explains it." |
| 3 | 0:50 | Sidebar: **Patient Arrival Surge**, Run | "Regional incident plus flu peak: 42 arrivals expected in 4 hours, 2.3× normal. Status goes CRITICAL." |
| 4 | 1:10 | Agent Analysis tab | Read one or two lines of the AI briefing and key risks. Point at the caption: "AI-generated, does not change priorities or execute actions." |
| 5 | 1:40 | Recommendations tab | "Three recommendations, prioritised by deterministic rules. Each has AI context explaining why it matters now. Nothing happens until a manager decides." Approve REC-001, modify REC-002 with a note, reject REC-003. Show Decision Summary. |
| 6 | 2:30 | **Staffing Shortage**, Run | "Seven nurses off sick. Three wards breach nurse ratios; about 34 beds are effectively locked. Note the decisions reset for the new analysis." |
| 7 | 2:55 | **Discharge Delay**, Run | "Only 3 discharges instead of 14. The AI explains the knock-on effect on incoming patients." |
| 8 | 3:20 | Sidebar toggle off, Run | "Turn AI off and the rules still produce identical recommendations. That is our safety design: AI explains, rules decide, humans approve." |
| 9 | 3:40 | README table or closing slide | "Implemented: rule-based agents, watsonx.ai explanations, guardrails, human approval. Planned: watsonx Orchestrate to coordinate agents and trigger approved workflows." |

Do **not** claim watsonx Orchestrate is working. It is future work.
