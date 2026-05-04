# Prompt 09 — Cost Dashboard & Enterprise Decision Framework

## Role & Mission

You are a solutions architect building the **cost analysis and enterprise decision framework** — the final analytical layer that turns benchmark data into actionable business guidance. You will compute simulated API costs, build a decision tree, and produce the enterprise deployment guide.

---

## GLOBAL CONTEXT

```
Project: LLM reasoning benchmark
Input: efficiency_scores.csv, model_comparison.csv from analysis module
Stack: Python 3.12+, polars
Output: cost_dashboard.csv, decision_tree.md, enterprise_guide.md
```

---

## API Pricing Reference

Use these **simulated prices** (as of the project's analysis date). Include the prices as constants so they can easily be updated.

```python
# src/benchmark/report/cost_dashboard.py

# Prices in USD per 1 million tokens
PRICING: dict[str, dict[str, float]] = {
    "openai/o1": {
        "input": 15.00,
        "reasoning": 15.00,   # reasoning tokens billed as output
        "output": 60.00,
    },
    "openai/o3-mini": {
        "input": 1.10,
        "reasoning": 1.10,
        "output": 4.40,
    },
    "deepseek/DeepSeek-R1": {
        "input": 0.55,
        "reasoning": 2.19,   # DeepSeek pricing for thinking tokens
        "output": 2.19,
    },
    "gemini-2.0-flash-thinking-exp-01-21": {
        "input": 0.35,
        "reasoning": 3.50,   # Gemini thinking tokens
        "output": 1.05,
    },
    "openai/gpt-4o": {
        "input": 2.50,
        "reasoning": 0.0,    # No reasoning tokens
        "output": 10.00,
    },
    "anthropic/claude-3-5-sonnet": {
        "input": 3.00,
        "reasoning": 0.0,
        "output": 15.00,
    },
}

NOTE_GITHUB_MODELS = """
These costs reflect retail API pricing. In this benchmark, GitHub Models 
and Google AI Studio free tiers were used (zero cost during data collection).
The costs shown represent what production deployment would cost.
"""
```

---

## Module: `src/benchmark/report/cost_dashboard.py`

### Function 1: Compute Per-Run Costs

```python
def compute_run_costs(db: DatabaseManager) -> pl.DataFrame:
    """
    For every row in benchmark_runs, compute the estimated USD cost.
    
    Formula:
    cost_usd = (
        input_tokens * pricing[model]["input"] / 1_000_000 +
        reasoning_tokens * pricing[model]["reasoning"] / 1_000_000 +
        output_tokens * pricing[model]["output"] / 1_000_000
    )
    
    Returns all benchmark_runs columns + cost_usd column.
    """
```

### Function 2: Cost Summary Table

```python
def build_cost_dashboard(db: DatabaseManager) -> pl.DataFrame:
    """
    Build the main cost vs performance table.
    
    Returns DataFrame with columns:
    - model
    - budget_level  
    - avg_accuracy (across all task categories)
    - avg_cost_per_run_usd
    - cost_per_1000_questions_usd
    - cost_per_correct_answer_usd  (avg_cost / accuracy — the key metric!)
    - avg_reasoning_tokens
    - avg_latency_seconds
    - efficiency_score
    - is_pareto_optimal (bool)
    
    Sort by cost_per_correct_answer_usd ascending (best value first).
    """
```

**Key derived metric:**
```
Cost Per Correct Answer = avg_cost_per_run / accuracy
```
This is the most important enterprise metric — it captures both cost AND accuracy in one number. Lower = better value.

### Function 3: Pareto Optimality

```python
def mark_pareto_optimal(df: pl.DataFrame) -> pl.DataFrame:
    """
    Mark each (model, budget_level) point as Pareto-optimal.
    A point is Pareto-optimal if no other point has BOTH:
    - lower cost_per_correct_answer_usd AND
    - higher avg_accuracy
    
    Add boolean column 'is_pareto_optimal'.
    """
```

### Function 4: Task-Category Cost Recommendations

```python
def recommend_model_per_category(
    cost_dashboard: pl.DataFrame,
    efficiency_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    For each task category, recommend the best model+budget combination.
    
    Criteria: Pareto-optimal point with best cost_per_correct_answer.
    
    Returns DataFrame:
    - task_category
    - recommended_model
    - recommended_budget_level
    - expected_accuracy
    - cost_per_1000_questions_usd
    - rationale (string explanation)
    """
```

---

## Decision Tree Generator

Generate a **text-based and markdown-formatted decision tree** for production deployment:

```python
DECISION_TREE = """
# Enterprise Model Selection Decision Tree

## Step 1: Task Complexity Assessment

Q: How many sequential deductive steps does this task require?

├── < 3 steps (simple lookup, classification, summarization)
│   └── → USE: GPT-4o or Claude 3.5 Sonnet (baseline)
│         Reason: Reasoning models provide no meaningful accuracy gain
│         Est. cost: $2–3 per 1,000 queries
│
├── 3–7 steps (math word problems, basic code, causal reasoning)  
│   └── → USE: DeepSeek R1 (Budget L3) or Gemini Flash Thinking (L3)
│         Reason: Sweet spot — substantial accuracy gain, moderate cost
│         Est. cost: $0.50–1.50 per 1,000 queries
│
└── > 7 steps (complex math, multi-step planning, hard coding)
    │
    ├── Latency-sensitive? (< 5s response time required)
    │   └── → USE: o3-mini (Budget L4)
    │         Reason: Best accuracy-per-latency trade-off
    │
    └── Latency-tolerant? (batch processing, offline)
        └── → USE: o1 (Budget L5) or DeepSeek R1 (Budget L5)
              Reason: Maximum accuracy, cost justified by task value

## Step 2: Budget Calibration

For the chosen model, use the minimum budget level that achieves 
your target accuracy threshold:

Target Accuracy   →  Recommended Budget Level
≥ 50%             →  L1 (baseline, cheapest)  
≥ 65%             →  L2 (light reasoning)
≥ 75%             →  L3 (medium — sweet spot for most tasks)
≥ 85%             →  L4 (high reasoning)
≥ 90%             →  L5 (maximum — use only when justified)

## Step 3: Cost Guardrails

Set a cost_per_correct_answer_usd threshold BEFORE production deployment.
If your threshold is exceeded at L3, do NOT escalate to L4/L5 — 
reconsider task formulation or dataset quality instead.
"""
```

---

## Output: Enterprise Report Generator

```python
def generate_enterprise_report(
    cost_dashboard: pl.DataFrame,
    recommendations: pl.DataFrame,
    dim_returns: dict,
    output_dir: Path,
) -> Path:
    """
    Generate a complete markdown enterprise guide saved to:
    results/enterprise_guide.md
    
    Sections:
    1. Executive Summary (3 bullet points)
    2. Key Findings (top 5 insights with evidence)
    3. Cost Dashboard Table (markdown formatted)
    4. Model Decision Tree (the text above)
    5. Per-Category Recommendations Table
    6. Implementation Checklist for DevOps teams
    7. Cost Optimization Tips
    """
```

**Implementation Checklist to include:**
```markdown
## Implementation Checklist

### Before Deployment
- [ ] Benchmark your specific task distribution (don't rely solely on generic benchmarks)
- [ ] Measure your ground-truth accuracy requirement
- [ ] Set a cost_per_correct_answer budget cap
- [ ] Enable model-level fallback: if reasoning model times out → fall back to baseline

### API Configuration
- [ ] Set `reasoning_effort: "medium"` as the DEFAULT for o1/o3 (not "high")
- [ ] Cap `thinkingBudget` at 2048 tokens for Gemini unless task requires more
- [ ] Implement request caching for identical prompts (save 40–60% on repeated queries)
- [ ] Set `max_completion_tokens` guardrails to control cost spikes

### Monitoring in Production
- [ ] Log `reasoning_tokens` per request to your metrics system
- [ ] Alert if avg_reasoning_tokens > 2× expected baseline
- [ ] Track cost_per_correct_answer weekly — watch for model version regressions
- [ ] A/B test budget levels on 5% of traffic before full rollout
```

---

## CLI Entry Point

`src/benchmark/report/__main__.py`:

```
Usage: uv run python -m benchmark.report [--output-dir results/]

Generates:
  results/tables/cost_dashboard.csv
  results/enterprise_guide.md
  results/decision_tree.md
```

---

## Testing

Write `tests/test_cost_dashboard.py`:

1. **`TestPricingCalculation`** — verify cost formula:
   - Run with 1000 input tokens, 2000 reasoning tokens, 500 output tokens for `openai/o1`
   - Expected: (1000×15 + 2000×15 + 500×60) / 1,000,000 = $0.0756

2. **`TestParetoOptimality`** — with 3 synthetic points:
   - A: cost=1.0, accuracy=0.7 (Pareto-optimal)
   - B: cost=2.0, accuracy=0.8 (Pareto-optimal)
   - C: cost=2.5, accuracy=0.75 (dominated by B — NOT Pareto-optimal)

3. **`TestCostPerCorrectAnswer`** — verify:
   - cost_per_run=0.01, accuracy=0.5 → cost_per_correct=0.02
   - cost_per_run=0.001, accuracy=0.9 → cost_per_correct=0.00111

---

## Requirements

- All pricing constants must be easily updatable (at the top of the file, well-commented)
- Include `PRICING_DATE = "2025-01-01"` constant — note that prices change frequently
- The enterprise guide must be self-contained markdown (no references to internal variables)
- Use polars exclusively for data wrangling
- Decision tree must be correct `just` syntax — actually test the logic against benchmark results

---

## Output Format

1. `src/benchmark/report/cost_dashboard.py`
2. `src/benchmark/report/__main__.py`
3. `tests/test_cost_dashboard.py`
4. The full decision tree in markdown (as it would appear in the final enterprise guide)
