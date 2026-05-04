# Prompt 08 — Visualizations & Plots

## Role & Mission

You are a data visualization engineer creating the **complete set of research-grade plots and figures** for the LLM reasoning benchmark paper. You will generate 6 distinct visualizations using matplotlib and seaborn, all following a consistent professional style.

---

## GLOBAL CONTEXT

```
Project: LLM reasoning benchmark
Input: CSV files from results/tables/ (produced by metrics.py)
Stack: Python 3.12+, matplotlib, seaborn, polars
Output: PNG files in results/figures/ at 300 DPI
Style: Academic paper quality, colorblind-friendly palette
```

---

## Global Style Configuration

Apply this style to ALL plots before generating any figure:

```python
import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns

# Color palette — colorblind-safe (Wong 2011)
PALETTE = {
    "openai/o1":                      "#0072B2",  # blue
    "openai/o3-mini":                 "#56B4E9",  # sky blue
    "deepseek/DeepSeek-R1":           "#009E73",  # green
    "gemini-2.0-flash-thinking-exp":  "#E69F00",  # orange
    "openai/gpt-4o":                  "#CC79A7",  # pink (baseline)
    "anthropic/claude-3-5-sonnet":    "#999999",  # gray (baseline)
}

STYLE_CONFIG = {
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,  # for display
    "savefig.dpi": 300,  # for saving
    "figure.facecolor": "white",
}

plt.rcParams.update(STYLE_CONFIG)
```

---

## Figure 1: Accuracy vs Reasoning Tokens (Scatter + Trend)

**Filename:** `results/figures/fig1_diminishing_returns.png`  
**Size:** 12×8 inches  
**Purpose:** Show the non-linear relationship between reasoning tokens and accuracy — the "sweet spot" hypothesis.

**Plot specification:**
- X-axis: Average reasoning tokens per run (log scale: 0–100,000)
- Y-axis: Accuracy (0.0–1.0)
- One subplot per task category (3×4 grid, 12 subplots)
- Each subplot: scatter points colored by model, with a **LOWESS smoothing trendline** per model
- Mark the "inflection zone" (L3 typically) with a shaded vertical band (e.g., gray band at 2,000–5,000 tokens)
- Title each subplot with task category name
- Shared X/Y axis labels on outer edges only
- Legend: model colors, positioned in figure-level legend outside the grid

```python
def plot_diminishing_returns(
    efficiency_df: pl.DataFrame,
    runs_df: pl.DataFrame,
    output_path: Path,
) -> None:
    """
    Create 3×4 grid of scatter plots showing accuracy vs reasoning tokens.
    One subplot per task category, points colored by model.
    Include LOWESS trendline per model.
    Shade the 'sweet spot' zone with a transparent band.
    """
    from statsmodels.nonparametric.smoothers_lowess import lowess
    
    fig, axes = plt.subplots(3, 4, figsize=(12, 8), sharex=False, sharey=True)
    # ... implementation
    
    # Annotate best efficiency point per subplot
    # Add annotation: "Sweet spot: L3 (~3,000 tokens)"
    
    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
```

---

## Figure 2: Reasoning Efficiency Heatmap (Model × Budget Level)

**Filename:** `results/figures/fig2_efficiency_heatmap.png`  
**Size:** 10×6 inches  
**Purpose:** Show which model+budget combination is most cost-efficient.

**Plot specification:**
- Rows: 6 models
- Columns: 5 budget levels (L1–L5)
- Cell values: Average efficiency score across all task categories
- Color: Sequential colormap (`YlOrRd` — red=high efficiency)
- Annotate each cell with the numeric score (2 decimal places)
- Add a vertical dashed separator between baseline models and reasoning models
- Mark the global maximum cell with a bold border
- X-axis: "Budget Level (L1=baseline → L5=max reasoning)"
- Y-axis: Model names (short display names)

```python
def plot_efficiency_heatmap(
    efficiency_df: pl.DataFrame,
    output_path: Path,
) -> None:
    """
    Heatmap of average efficiency score per (model, budget_level).
    Rows = models, columns = budget levels.
    """
    # Pivot to matrix: model (rows) × budget_level (cols), values=efficiency_score
    pivot = (
        efficiency_df
        .filter(pl.col("is_reliable"))
        .group_by(["model", "budget_level"])
        .agg(pl.col("efficiency_score").mean())
        .pivot(index="model", columns="budget_level", values="efficiency_score")
    )
    # ... seaborn heatmap
```

---

## Figure 3: Accuracy by Budget Level — Line Chart

**Filename:** `results/figures/fig3_accuracy_by_budget.png`  
**Size:** 14×8 inches  
**Purpose:** Show how each model improves (or doesn't) as reasoning budget increases.

**Plot specification:**
- One subplot per task category (3×4 grid)
- X-axis: Budget level (1–5, discrete)
- Y-axis: Accuracy (0.0–1.0)
- Lines: One per model, colored by `PALETTE`
- Line style: reasoning models = solid, baselines = dashed
- Markers: Circle (o) for reasoning models, X for baselines
- Error bars: 95% CI (if sample size allows) using `plt.fill_between()`
- Mark the "inflection point" per model per subplot with a triangle marker (▲)
- Add horizontal dashed line at baseline (L1) accuracy for reference

```python
def plot_accuracy_by_budget(
    efficiency_df: pl.DataFrame,
    dim_returns: dict[str, DimReturnsResult],
    output_path: Path,
) -> None:
    """
    3×4 grid. Each subplot: accuracy lines per model across budget levels.
    Mark inflection points.
    """
```

---

## Figure 4: Strategy Effectiveness Heatmap

**Filename:** `results/figures/fig4_strategy_matrix.png`  
**Size:** 10×7 inches  
**Purpose:** Show which reasoning strategies are most effective for which task types.

**Plot specification:**
- Rows: 12 task categories
- Columns: 5 reasoning strategies (Decomposition, Analogy, Verification, Backtracking, Self-Consistency)
- Cell values: Average accuracy when strategy IS detected (vs baseline row)
- Color: Diverging colormap (`RdYlGn`) centered at the baseline accuracy
- Add a "Baseline" column (accuracy with no strategy detected)
- Annotate cells with accuracy value
- Sort rows by "most strategy-responsive" (largest spread between min and max accuracy)
- Add column totals showing: % of traces where strategy was detected

```python
def plot_strategy_matrix(
    strategy_df: pl.DataFrame,
    output_path: Path,
) -> None:
    """
    Heatmap: task_category (rows) × strategy (cols), values=accuracy_when_present.
    Diverging colormap centered at no-strategy baseline.
    """
```

---

## Figure 5: Cost vs Accuracy Scatter (Pareto Frontier)

**Filename:** `results/figures/fig5_cost_vs_accuracy.png`  
**Size:** 8×6 inches  
**Purpose:** Enterprise decision-making visualization — is extended reasoning worth the cost?

**Plot specification:**
- X-axis: Estimated cost per 1,000 questions (USD, log scale)
- Y-axis: Average accuracy across all categories (0.0–1.0)
- One point per (model, budget_level) combination
- Point size: proportional to average latency
- Point color: model color from PALETTE
- Point label: "{model_short} L{budget}"
- **Pareto frontier**: Draw a step line connecting Pareto-optimal points (maximum accuracy for minimum cost). Shade the "dominated" region in light red.
- Add annotation arrows pointing to: "Best accuracy", "Best cost-efficiency", "Best for simple tasks"

```python
def plot_cost_accuracy_pareto(
    cost_df: pl.DataFrame,  # from cost_dashboard module
    output_path: Path,
) -> None:
    """
    Scatter plot of cost vs accuracy with Pareto frontier.
    """

def _compute_pareto_frontier(costs: list[float], accuracies: list[float]) -> list[int]:
    """Return indices of Pareto-optimal points (min cost, max accuracy)."""
```

---

## Figure 6: Marginal Gain Waterfall Chart

**Filename:** `results/figures/fig6_marginal_gains.png`  
**Size:** 12×5 inches  
**Purpose:** Directly visualize the "diminishing returns" hypothesis — how much accuracy gain does each budget step add?

**Plot specification:**
- X-axis: Budget step transitions (L1→L2, L2→L3, L3→L4, L4→L5)
- Y-axis: Marginal accuracy gain (percentage points)
- One grouped bar per transition, grouped by model
- Color bars by model (PALETTE)
- Add a horizontal dashed line at `y=0` and at `y=MARGINAL_GAIN_THRESHOLD` (2%)
- Shade the region below the threshold in light red (the "diminishing returns zone")
- Include a small inset showing the cumulative gain curve

```python
def plot_marginal_gains(
    dim_returns: dict[str, DimReturnsResult],
    output_path: Path,
    task_categories: list[str] | None = None,  # None = macro average
) -> None:
    """
    Grouped bar chart of marginal accuracy gains per budget step.
    """
```

---

## Main Module: `src/benchmark/analysis/visualizations.py`

```python
def generate_all_figures(
    db: DatabaseManager,
    tables_dir: Path,
    figures_dir: Path,
) -> dict[str, Path]:
    """
    Generate all 6 figures.
    Returns dict of {figure_name: output_path}.
    Creates figures_dir if it doesn't exist.
    Prints progress with rich.
    """
    
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    # Load CSVs (not DB) for speed — assume metrics have been computed
    efficiency_df = pl.read_csv(tables_dir / "efficiency_scores.csv")
    strategy_df = pl.read_csv(tables_dir / "strategy_matrix.csv")
    cost_df = pl.read_csv(tables_dir / "cost_dashboard.csv")
    
    figures = {}
    
    with Progress() as progress:
        task = progress.add_task("Generating figures...", total=6)
        
        figures["diminishing_returns"] = plot_diminishing_returns(...)
        progress.advance(task)
        # ... etc
    
    return figures
```

---

## Testing

Write `tests/test_visualizations.py`:

1. **Smoke test**: Call each plot function with minimal synthetic data (2 models, 2 categories, 5 budget levels). Verify the PNG file is created and is > 10KB.

2. **Pareto test**: `_compute_pareto_frontier([1, 2, 3], [0.5, 0.7, 0.6])` → should return indices `[0, 1]` (point at cost=3 is dominated by cost=2 with higher accuracy).

3. **Style test**: Load a generated PNG with PIL and verify dimensions are within expected range.

---

## Requirements

- All figures must close after saving (`plt.close(fig)`) to prevent memory leaks
- Use `bbox_inches="tight"` on all `savefig()` calls
- Never use `plt.show()` — always save to file
- All figure functions must return the `Path` of the saved file
- Use polars for ALL data wrangling before passing to matplotlib
- Include figure number and a short title in each plot's `fig.suptitle()`
- Ensure figures are readable in black-and-white (use both color AND linestyle/marker to distinguish series)

---

## Output Format

1. `src/benchmark/analysis/visualizations.py` — complete module with all 6 plot functions
2. `tests/test_visualizations.py` — smoke tests
3. A markdown description of each figure suitable for inclusion in the paper's Figure captions section
