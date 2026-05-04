"""Core research metrics calculation and data analysis."""

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from scipy import stats

from benchmark.database import DatabaseManager


@dataclass
class DimReturnsResult:
    model: str
    task_category: str
    accuracy_by_level: list[float]
    marginal_gains: list[float]
    inflection_point: int | None
    peak_efficiency_level: int
    plateau_detected: bool
    total_accuracy_gain: float


def compute_efficiency_scores(db: DatabaseManager) -> pl.DataFrame:
    """Compute Reasoning Efficiency Score for every (model, task_category, budget_level) group."""
    df = db.get_runs(filters={"is_error": 0})
    if df.is_empty():
        return pl.DataFrame()

    df = df.filter(pl.col("is_correct").is_not_null())
    if df.is_empty():
        return pl.DataFrame()

    result = (
        df.group_by(["model", "task_category", "budget_level"])
        .agg(
            [
                pl.len().alias("n_runs"),
                pl.col("is_correct").sum().alias("n_correct"),
                pl.col("is_correct").mean().alias("accuracy"),
                pl.col("reasoning_tokens").mean().alias("avg_reasoning_tokens"),
                pl.col("total_tokens").mean().alias("avg_total_tokens"),
                pl.col("latency_seconds").mean().alias("avg_latency_seconds"),
            ]
        )
        .with_columns(
            [
                (
                    pl.col("accuracy") * 1000 / pl.col("avg_reasoning_tokens").clip(lower_bound=1.0)
                ).alias("efficiency_score"),
                (pl.col("n_runs") >= 5).alias("is_reliable"),
            ]
        )
        .sort(["model", "task_category", "budget_level"])
    )
    return result


def analyze_diminishing_returns(efficiency_df: pl.DataFrame) -> dict[str, DimReturnsResult]:
    """Analyze how accuracy changes across budget levels."""
    if efficiency_df.is_empty():
        return {}

    MARGINAL_GAIN_THRESHOLD = 0.02
    results = {}

    grouped = efficiency_df.partition_by(["model", "task_category"], as_dict=True)
    for (model, task_category), group in grouped.items():
        # Ensure it's sorted by budget_level
        group = group.sort("budget_level")

        # We need levels 1 to 5, missing levels might break indexing, so we extract carefully
        levels = group["budget_level"].to_list()
        accuracies = group["accuracy"].to_list()
        efficiencies = group["efficiency_score"].to_list()

        accuracy_by_level = []
        marginal_gains = []

        # Build 1-indexed accuracy array if possible, or just sequential based on available data
        for i in range(len(accuracies)):
            accuracy_by_level.append(accuracies[i])
            if i == 0:
                marginal_gains.append(0.0)
            else:
                marginal_gains.append(accuracies[i] - accuracies[i - 1])

        inflection_point = None
        plateau_detected = False

        for i in range(1, len(marginal_gains)):
            if marginal_gains[i] <= MARGINAL_GAIN_THRESHOLD + 1e-7:
                # Check if all subsequent are also below threshold
                if all(g <= MARGINAL_GAIN_THRESHOLD + 1e-7 for g in marginal_gains[i:]):
                    inflection_point = levels[i]
                    if len(marginal_gains) > i + 1:
                        plateau_detected = True
                    break

        if not efficiencies:
            peak_efficiency_level = 1
        else:
            peak_idx = efficiencies.index(max(efficiencies))
            peak_efficiency_level = levels[peak_idx]

        total_gain = accuracy_by_level[-1] - accuracy_by_level[0] if accuracy_by_level else 0.0

        key = f"{model}|{task_category}"
        results[key] = DimReturnsResult(
            model=model,
            task_category=task_category,
            accuracy_by_level=accuracy_by_level,
            marginal_gains=marginal_gains,
            inflection_point=inflection_point,
            peak_efficiency_level=peak_efficiency_level,
            plateau_detected=plateau_detected,
            total_accuracy_gain=total_gain,
        )

    return results


def compute_strategy_matrix(db: DatabaseManager) -> pl.DataFrame:
    """Compute Success rate when each strategy is present vs absent."""
    df = db.get_runs(filters={"is_error": 0}).filter(pl.col("strategy_tags").is_not_null())
    if df.is_empty():
        return pl.DataFrame()

    strategies = ["decomposition", "analogy", "verification", "backtracking", "self_consistency"]

    # Parse the JSON column
    def parse_tags(json_str):
        try:
            return json.loads(json_str)
        except (TypeError, json.JSONDecodeError):
            return {}

    # Add columns for each strategy manually because unnest needs struct type
    parsed_dicts = [parse_tags(s) for s in df["strategy_tags"].to_list()]

    new_cols = []
    for s in strategies:
        new_cols.append(pl.Series(s, [d.get(s, 0) for d in parsed_dicts]))

    df_with_tags = df.with_columns(new_cols)

    agg_exprs = []
    for s in strategies:
        # Mean is_correct where strategy == 1
        # In polars:
        agg_exprs.append(
            (pl.when(pl.col(s) == 1).then(pl.col("is_correct")).otherwise(None).mean()).alias(s)
        )

    # Baseline accuracy (no strategy tags present at all, or all 0)
    agg_exprs.append(
        (
            pl.when(pl.sum_horizontal([pl.col(s) for s in strategies]) == 0)
            .then(pl.col("is_correct"))
            .otherwise(None)
            .mean()
        ).alias("baseline_accuracy")
    )

    matrix = df_with_tags.group_by("task_category").agg(agg_exprs)

    return matrix


def compute_model_comparison(efficiency_df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate across all task categories for each (model, budget_level)."""
    if efficiency_df.is_empty():
        return pl.DataFrame()

    # First get the best and worst categories
    grouped = efficiency_df.partition_by(["model", "budget_level"], as_dict=True)

    results = []
    for (model, budget_level), group in grouped.items():
        if group.is_empty():
            continue

        group = group.sort("accuracy")
        worst_cat = group["task_category"][0]
        best_cat = group["task_category"][-1]

        overall_acc = group["accuracy"].mean()
        avg_eff = group["efficiency_score"].mean()
        avg_rt = group["avg_reasoning_tokens"].mean()

        results.append(
            {
                "model": model,
                "budget_level": budget_level,
                "overall_accuracy": overall_acc,
                "best_category": best_cat,
                "worst_category": worst_cat,
                "avg_efficiency_score": avg_eff,
                "avg_reasoning_tokens": avg_rt,
                "total_cost_usd": 0.0,  # Placeholder for cost dashboard
            }
        )

    if not results:
        return pl.DataFrame()

    return pl.DataFrame(results).sort(["model", "budget_level"])


def compute_significance_tests(db: DatabaseManager) -> pl.DataFrame:
    """Test if L1 to L5 accuracy difference is statistically significant."""
    df = db.get_runs(filters={"is_error": 0}).filter(pl.col("is_correct").is_not_null())
    if df.is_empty():
        return pl.DataFrame()

    grouped = df.partition_by(["model", "task_category"], as_dict=True)

    results = []
    for (model, task_category), group in grouped.items():
        l1_runs = group.filter(pl.col("budget_level") == 1)
        l5_runs = group.filter(pl.col("budget_level") == 5)

        if l1_runs.is_empty() or l5_runs.is_empty():
            continue

        c1 = l1_runs["is_correct"].sum()
        n1 = len(l1_runs)
        c5 = l5_runs["is_correct"].sum()
        n5 = len(l5_runs)

        acc1 = c1 / n1 if n1 > 0 else 0
        acc5 = c5 / n5 if n5 > 0 else 0

        # Chi2 requires expected freq >= 5 usually, but we run it anyway
        table = [[c1, n1 - c1], [c5, n5 - c5]]
        try:
            res = stats.chi2_contingency(table)
            p_val = res.pvalue
        except ValueError:
            p_val = 1.0

        # Cohen's h
        import numpy as np

        h = 2 * np.arcsin(np.sqrt(acc1)) - 2 * np.arcsin(np.sqrt(acc5))

        results.append(
            {
                "model": model,
                "task_category": task_category,
                "accuracy_l1": float(acc1),
                "accuracy_l5": float(acc5),
                "delta_accuracy": float(acc5 - acc1),
                "p_value": float(p_val),
                "is_significant": bool(p_val < 0.05),
                "effect_size": float(abs(h)),
            }
        )

    if not results:
        return pl.DataFrame()

    return pl.DataFrame(results)


def export_all_metrics(db: DatabaseManager, output_dir: Path) -> dict[str, Path]:
    """Compute all metrics and export to CSV files."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    eff_df = compute_efficiency_scores(db)
    eff_path = tables_dir / "efficiency_scores.csv"
    if not eff_df.is_empty():
        eff_df.write_csv(eff_path)

    dim_returns = analyze_diminishing_returns(eff_df)
    dim_path = tables_dir / "diminishing_returns_summary.csv"
    if dim_returns:
        dim_list = [
            {
                "model": r.model,
                "task_category": r.task_category,
                "inflection_point": r.inflection_point,
                "peak_efficiency_level": r.peak_efficiency_level,
                "plateau_detected": r.plateau_detected,
                "total_accuracy_gain": r.total_accuracy_gain,
            }
            for r in dim_returns.values()
        ]
        pl.DataFrame(dim_list).write_csv(dim_path)

    strat_df = compute_strategy_matrix(db)
    strat_path = tables_dir / "strategy_matrix.csv"
    if not strat_df.is_empty():
        strat_df.write_csv(strat_path)

    model_comp_df = compute_model_comparison(eff_df)
    comp_path = tables_dir / "model_comparison.csv"
    if not model_comp_df.is_empty():
        model_comp_df.write_csv(comp_path)

    sig_df = compute_significance_tests(db)
    sig_path = tables_dir / "significance_tests.csv"
    if not sig_df.is_empty():
        sig_df.write_csv(sig_path)

    return {
        "efficiency_scores": eff_path,
        "diminishing_returns_summary": dim_path,
        "strategy_matrix": strat_path,
        "model_comparison": comp_path,
        "significance_tests": sig_path,
    }
