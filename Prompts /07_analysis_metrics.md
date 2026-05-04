# Prompt 07 — Analysis & Metrics Computation

## Role & Mission

You are a data scientist computing the **core research metrics** from the completed benchmark database. You will write the full analysis module that calculates the Reasoning Efficiency Metric, identifies diminishing returns inflection points, and exports structured results for visualization.

---

## GLOBAL CONTEXT

```
Project: LLM reasoning benchmark analysis
Input: benchmark_runs table (fully graded — is_correct populated)
Stack: Python 3.12+, polars (NOT pandas), scipy, numpy
Core metric: Reasoning Efficiency = (Accuracy / Reasoning Tokens) × 1000
Output: CSV files in results/tables/ + rich console summary
```

---

## The Core Reasoning Efficiency Metric

```
Efficiency Score = (Accuracy × 1000) / Reasoning Tokens

Where:
  Accuracy = average is_correct for a (model, dataset, budget) group (0.0 to 1.0)
  Reasoning Tokens = average reasoning_tokens for that group
  
Special cases:
  - If reasoning_tokens == 0 (baseline models): Efficiency = Accuracy × 1000 / 1
    (treat as 1 token to avoid division by zero, flag separately)
  - If group has < 5 samples: mark efficiency as unreliable (flag column)
```

**Interpretation:**
- High efficiency: model achieves high accuracy with few reasoning tokens (cost-effective)
- Low efficiency: model uses many tokens but accuracy doesn't improve proportionally
- The metric reveals the "value per token" of extended reasoning

---

## Module: `src/benchmark/analysis/metrics.py`

### Function 1: Core Efficiency Metric

```python
def compute_efficiency_scores(db: DatabaseManager) -> pl.DataFrame:
    """
    Compute Reasoning Efficiency Score for every (model, task_category, budget_level) group.
    
    Returns DataFrame with columns:
    - model, task_category, budget_level
    - n_runs, n_correct
    - accuracy (0.0–1.0)
    - avg_reasoning_tokens
    - avg_total_tokens
    - avg_latency_seconds
    - efficiency_score
    - is_reliable (bool: n_runs >= 5 and avg_reasoning_tokens > 0)
    
    Also updates efficiency_score column in DB for each individual run.
    """
```

Implementation note — use Polars groupby:
```python
df = db.get_runs(filters={"is_error": 0}).filter(pl.col("is_correct").is_not_null())

result = (
    df.group_by(["model", "task_category", "budget_level"])
    .agg([
        pl.len().alias("n_runs"),
        pl.col("is_correct").sum().alias("n_correct"),
        pl.col("is_correct").mean().alias("accuracy"),
        pl.col("reasoning_tokens").mean().alias("avg_reasoning_tokens"),
        pl.col("total_tokens").mean().alias("avg_total_tokens"),
        pl.col("latency_seconds").mean().alias("avg_latency_seconds"),
    ])
    .with_columns([
        (pl.col("accuracy") * 1000 / pl.col("avg_reasoning_tokens").clip(lower_bound=1))
            .alias("efficiency_score"),
        (pl.col("n_runs") >= 5).alias("is_reliable"),
    ])
    .sort(["model", "task_category", "budget_level"])
)
```

---

### Function 2: Diminishing Returns Analysis

```python
def analyze_diminishing_returns(
    efficiency_df: pl.DataFrame,
) -> dict[str, DimReturnsResult]:
    """
    For each (model, task_category) pair, analyze how accuracy changes
    across budget levels 1–5.
    
    Returns dict keyed by "{model}|{task_category}" with:
    - accuracy_by_level: list[float]  (index 0=L1, 4=L5)
    - marginal_gains: list[float]     (accuracy[i] - accuracy[i-1])
    - inflection_point: int | None    (budget level where marginal gain < threshold)
    - peak_efficiency_level: int      (budget level with highest efficiency_score)
    - plateau_detected: bool          (True if gain < 2% for 2+ consecutive levels)
    """

@dataclass
class DimReturnsResult:
    model: str
    task_category: str
    accuracy_by_level: list[float]
    marginal_gains: list[float]
    inflection_point: int | None
    peak_efficiency_level: int
    plateau_detected: bool
    total_accuracy_gain: float       # L5 accuracy - L1 accuracy
```

**Inflection point detection algorithm:**
```python
# The inflection point is the first budget level L where:
# marginal_gain[L] < MARGINAL_GAIN_THRESHOLD (default: 0.02, i.e. 2%)
# AND all subsequent gains are also below the threshold

MARGINAL_GAIN_THRESHOLD = 0.02  # 2 percentage points
```

---

### Function 3: Strategy Effectiveness Matrix

```python
def compute_strategy_matrix(db: DatabaseManager) -> pl.DataFrame:
    """
    For runs with strategy_tags populated, compute:
    Success rate when each strategy is present vs absent,
    per task_category.
    
    Returns a DataFrame suitable for heatmap rendering:
    - rows: task_category (12 values)
    - columns: strategy name (5 values)
    - values: accuracy when strategy IS detected (float, 0.0–1.0)
    
    Also compute: baseline accuracy (no strategies detected) per category.
    """
```

Implementation:
```python
# Parse strategy_tags JSON column
df_with_tags = (
    runs_df
    .filter(pl.col("strategy_tags").is_not_null())
    .with_columns([
        pl.col("strategy_tags").str.json_decode().alias("tags_parsed")
    ])
    .unnest("tags_parsed")  # Expands JSON keys to columns
)

# For each strategy, compute accuracy when present
for strategy in REASONING_STRATEGIES:
    mask = pl.col(strategy) == 1
    # group_by task_category, filter to strategy=1, compute mean(is_correct)
```

---

### Function 4: Model Comparison Summary

```python
def compute_model_comparison(efficiency_df: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate across all task categories for each (model, budget_level).
    
    Returns DataFrame with:
    - model, budget_level
    - overall_accuracy (macro-average across categories)
    - best_category (highest accuracy category name)
    - worst_category (lowest accuracy category name)
    - avg_efficiency_score
    - avg_reasoning_tokens
    - total_cost_usd (from cost_dashboard module)
    """
```

---

### Function 5: Statistical Significance Tests

```python
def compute_significance_tests(db: DatabaseManager) -> pl.DataFrame:
    """
    For each (model, task_category), test if the accuracy difference
    between L1 (baseline) and L5 (max reasoning) is statistically significant.
    
    Uses: scipy.stats.chi2_contingency (for proportions)
    
    Returns DataFrame with:
    - model, task_category
    - accuracy_l1, accuracy_l5
    - delta_accuracy
    - p_value
    - is_significant (p < 0.05)
    - effect_size (Cohen's h for proportions)
    """
    from scipy import stats
    
    # For each group: create 2x2 contingency table
    # [[correct_l1, incorrect_l1], [correct_l5, incorrect_l5]]
    # Run chi2_contingency
    # Compute Cohen's h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))
```

---

### Function 6: Export All Results

```python
def export_all_metrics(
    db: DatabaseManager,
    output_dir: Path,
) -> dict[str, Path]:
    """
    Compute all metrics and export to CSV files in output_dir/tables/.
    
    Returns dict of {metric_name: file_path}.
    
    Files produced:
    - efficiency_scores.csv
    - diminishing_returns_summary.csv
    - strategy_matrix.csv
    - model_comparison.csv
    - significance_tests.csv
    """
```

---

## CLI Entry Point

`src/benchmark/analysis/__main__.py`:

After computing all metrics, print a **rich summary report** to the console:

```
╔══════════════════════════════════════════════╗
║        BENCHMARK ANALYSIS SUMMARY           ║
╠══════════════════════════════════════════════╣
║  Total runs analyzed:     35,842            ║
║  Graded runs:             34,109 (95.2%)    ║
║  Models with traces:      2 (R1, Gemini)    ║
╠══════════════════════════════════════════════╣
║  TOP EFFICIENCY (L3 reasoning):             ║
║  1. DeepSeek R1  | MATH    | 8.42 pts/1k   ║
║  2. Gemini Think | Logic   | 7.81 pts/1k   ║
╠══════════════════════════════════════════════╣
║  DIMINISHING RETURNS DETECTED:              ║
║  - 8/12 categories show plateau at L3–L4   ║
║  - 3/12 categories improve through L5      ║
╠══════════════════════════════════════════════╣
║  HYPOTHESIS: Non-linear returns            ║
║  Status: ✓ CONFIRMED (p < 0.01)            ║
╚══════════════════════════════════════════════╝
```

---

## Testing

Write `tests/test_metrics.py`:

1. **`TestEfficiencyScore`** — with synthetic data:
   - Group with accuracy=0.8, reasoning_tokens=200 → efficiency=4.0
   - Group with accuracy=0.8, reasoning_tokens=0 (baseline) → efficiency=800.0, `is_reliable=True` but flag separately
   - Group with n_runs=3 → `is_reliable=False`

2. **`TestDiminishingReturns`** — with synthetic accuracy series:
   - `[0.4, 0.6, 0.75, 0.77, 0.78]` → inflection at L3, plateau_detected=True
   - `[0.4, 0.55, 0.70, 0.82, 0.91]` → no plateau, no inflection

3. **`TestStrategyMatrix`** — verify matrix shape is (12 categories × 5 strategies)

4. **`TestSignificanceTest`** — with known p-values:
   - 90/100 correct at L5, 50/100 at L1 → should be significant
   - 51/100 vs 49/100 → should NOT be significant

---

## Requirements

- Use **polars exclusively** for all DataFrame operations — no pandas, no numpy for data wrangling
- Use **numpy/scipy only** for statistical computations (not data wrangling)
- All computations must handle `null` values gracefully (Polars null-safe operations)
- Cache expensive computations to avoid re-running on re-import
- All functions return `pl.DataFrame` or typed dataclasses — no raw dicts
- Ruff-compliant style

---

## Output Format

1. `src/benchmark/analysis/metrics.py` — complete module
2. `src/benchmark/analysis/__main__.py` — CLI entry point  
3. `tests/test_metrics.py` — test suite
