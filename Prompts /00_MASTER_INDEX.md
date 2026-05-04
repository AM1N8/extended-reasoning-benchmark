# 🧠 LLM Extended Reasoning Analysis — AI Prompt Suite

## Project Summary

This prompt suite guides an AI assistant to build a full research pipeline analyzing **test-time compute scaling** across state-of-the-art reasoning LLMs (OpenAI o1/o3, DeepSeek R1, Gemini 2.0 Flash Thinking).

The system benchmarks 6 models × 12 task categories × 5 reasoning budget levels, introduces a custom **Reasoning Efficiency Metric**, and produces actionable enterprise guidance.

---

## Tech Stack Decisions

| Concern | Tool |
|---|---|
| Package management | `uv` (not pip) |
| Task runner | `just` (not make) |
| Linter/formatter | `ruff` |
| Data processing | `polars` (not pandas) |
| Database | `sqlite3` (via Python stdlib) |
| Visualization | `matplotlib` + `seaborn` |
| API calls | `httpx` (async) |
| Config | `pydantic-settings` + `.env` |
| Testing | `pytest` |

---

## Prompt Execution Order

Execute these prompts **in sequence**. Each prompt builds on the previous phase's output.

```
00_MASTER_INDEX.md          ← You are here
01_project_scaffold.md      ← Phase 0: Repo structure, tooling config
02_database_schema.md       ← Phase 1a: SQLite schema + migrations
03_dataset_pipeline.md      ← Phase 1b: Dataset download + formatting
04_api_clients.md           ← Phase 2a: API wrapper functions
05_execution_engine.md      ← Phase 2b: Main benchmark loop
06_grading_pipeline.md      ← Phase 3: LLM-as-Judge (quant + qual)
07_analysis_metrics.md      ← Phase 4a: Efficiency metric calculation
08_visualizations.md        ← Phase 4b: All plots and heatmaps
09_cost_dashboard.md        ← Phase 4c: Cost vs accuracy table
10_final_report.md          ← Phase 5: Synthesis, decision tree, README
```

---

## Global Context Block

**Paste this at the start of every prompt session** to anchor the AI:

```
GLOBAL CONTEXT:
- Project: Systematic benchmark of test-time compute (extended reasoning) in LLMs
- Models: OpenAI o1, o3-mini, DeepSeek R1, Gemini 2.0 Flash Thinking + 2 baselines
- Task categories: 12 (math, coding, logic, planning, etc.)
- Reasoning budgets: 5 levels (L1=baseline → L5=max reasoning)
- Core metric: Reasoning Efficiency = (Accuracy / Reasoning Tokens) × 1000
- Stack: Python, uv, just, ruff, polars, sqlite3, httpx, matplotlib
- APIs: GitHub Models REST API, Google AI Studio API
- Storage: local SQLite
- Style: production-grade, typed, documented, testable
```

---

## Key Hypotheses Being Tested

1. **Non-linear returns**: Reasoning gains plateau after 3–7 deductive steps
2. **Strategy effectiveness**: Backtracking and verification dominate in complex tasks
3. **Cost ROI**: Extended reasoning is not always worth the token cost
4. **Task specificity**: Reasoning models outperform on math/logic but not necessarily on simple retrieval

---

## Deliverables

- ✅ Fully functional Python benchmark pipeline
- ✅ SQLite database with all traces and metrics
- ✅ Scatter plots, heatmaps, cost tables
- ✅ Enterprise decision tree
- ✅ Clean GitHub repository with README
