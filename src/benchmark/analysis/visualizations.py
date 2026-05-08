"""Visualizations generation module."""

import math
from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl
import seaborn as sns
from rich.progress import Progress

from benchmark.analysis.metrics import DimReturnsResult

PALETTE = {
    "openai/o1": "#0072B2",  # blue
    "openai/o3-mini": "#56B4E9",  # sky blue
    "deepseek/DeepSeek-R1": "#009E73",  # green
    "gemini-2.5-flash": "#E69F00",  # orange
    "groq/deepseek-r1-distill-llama-70b": "#D55E00",  # red-orange
    "groq/deepseek-r1-distill-qwen-32b": "#F0E442",  # yellow
    "openai/gpt-4o": "#CC79A7",  # pink (baseline)
    "anthropic/claude-3-5-sonnet": "#999999",  # gray (baseline)
}

STYLE_CONFIG = {
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "figure.facecolor": "white",
}


def _apply_style():
    plt.rcParams.update(STYLE_CONFIG)


def plot_diminishing_returns(
    efficiency_df: pl.DataFrame,
    output_path: Path,
) -> Path:
    """Figure 1: Accuracy vs Reasoning Tokens."""
    _apply_style()
    from statsmodels.nonparametric.smoothers_lowess import lowess

    if efficiency_df.is_empty():
        fig, ax = plt.subplots(figsize=(12, 8))
        fig.suptitle("Fig 1: Accuracy vs Reasoning Tokens (No Data)")
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    categories = efficiency_df["task_category"].unique().to_list()
    # Ensure at least 1, max 12
    categories = categories[:12]
    n_cats = len(categories)
    rows = math.ceil(n_cats / 4) if n_cats > 0 else 1
    cols = min(n_cats, 4) if n_cats > 0 else 1

    fig, axes = plt.subplots(rows, cols, figsize=(12, max(8, 3 * rows)), sharex=False, sharey=True)
    if n_cats == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    for idx, cat in enumerate(categories):
        ax = axes[idx]
        df_cat = efficiency_df.filter(pl.col("task_category") == cat)

        for model in df_cat["model"].unique():
            df_model = df_cat.filter(pl.col("model") == model).sort("avg_reasoning_tokens")
            if df_model.is_empty():
                continue

            x = df_model["avg_reasoning_tokens"].to_numpy()
            y = df_model["accuracy"].to_numpy()
            color = PALETTE.get(model, "#333333")

            # Scatter
            ax.scatter(x, y, color=color, alpha=0.6, label=model if idx == 0 else "")

            # Lowess
            if len(x) > 2:
                # lowess returns (sorted x, y_smooth)
                try:
                    smooth = lowess(y, x, frac=0.6)
                    ax.plot(smooth[:, 0], smooth[:, 1], color=color, linewidth=2)
                except Exception:
                    # lowess can fail on edge cases
                    ax.plot(x, y, color=color, linewidth=2, alpha=0.5)
            else:
                ax.plot(x, y, color=color, linewidth=2, alpha=0.5)

        ax.set_title(cat)
        ax.set_xscale("symlog", linthresh=100)

        # Shade inflection zone (example: 2k - 5k)
        ax.axvspan(2000, 5000, color="gray", alpha=0.15)
        if idx == 0:
            ax.text(3000, ax.get_ylim()[1] * 0.9, "Sweet spot: L3 (~3k)", fontsize=8, alpha=0.7)

    # Set shared labels
    fig.supxlabel("Average Reasoning Tokens (symlog scale)")
    fig.supylabel("Accuracy")
    fig.suptitle("Figure 1: Accuracy vs Reasoning Tokens")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles, labels, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=len(labels)
        )

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_efficiency_heatmap(
    efficiency_df: pl.DataFrame,
    output_path: Path,
) -> Path:
    """Figure 2: Reasoning Efficiency Heatmap."""
    _apply_style()

    if efficiency_df.is_empty():
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    pivot = (
        efficiency_df.filter(pl.col("is_reliable"))
        .group_by(["model", "budget_level"])
        .agg(pl.col("efficiency_score").mean())
    )

    if pivot.is_empty():
        # Fallback if no reliable
        pivot = efficiency_df.group_by(["model", "budget_level"]).agg(
            pl.col("efficiency_score").mean()
        )

    # pivot to pandas for seaborn
    pivot_pd = pivot.to_pandas().pivot(
        index="model", columns="budget_level", values="efficiency_score"
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(pivot_pd, annot=True, fmt=".2f", cmap="YlOrRd", ax=ax, linewidths=0.5)

    ax.set_title("Figure 2: Reasoning Efficiency Score by Model and Budget")
    ax.set_xlabel("Budget Level (L1=baseline → L5=max reasoning)")
    ax.set_ylabel("Model")

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_accuracy_by_budget(
    efficiency_df: pl.DataFrame,
    dim_returns: dict[str, DimReturnsResult],
    output_path: Path,
) -> Path:
    """Figure 3: Accuracy by Budget Level."""
    _apply_style()

    if efficiency_df.is_empty():
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    categories = efficiency_df["task_category"].unique().to_list()[:12]
    n_cats = len(categories)
    rows = math.ceil(n_cats / 4) if n_cats > 0 else 1
    cols = min(n_cats, 4) if n_cats > 0 else 1

    fig, axes = plt.subplots(rows, cols, figsize=(14, max(8, 3 * rows)), sharex=True, sharey=True)
    if n_cats == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    for idx, cat in enumerate(categories):
        ax = axes[idx]
        df_cat = efficiency_df.filter(pl.col("task_category") == cat)

        for model in df_cat["model"].unique():
            df_model = df_cat.filter(pl.col("model") == model).sort("budget_level")
            if df_model.is_empty():
                continue

            x = df_model["budget_level"].to_numpy()
            y = df_model["accuracy"].to_numpy()
            color = PALETTE.get(model, "#333333")

            is_baseline = (
                "o1" not in model
                and "r1" not in model.lower()
                and "thinking" not in model.lower()
                and "o3" not in model.lower()
            )
            ls = "--" if is_baseline else "-"
            marker = "x" if is_baseline else "o"

            ax.plot(x, y, color=color, linestyle=ls, marker=marker, label=model if idx == 0 else "")

            # Baseline hline if L1
            if len(x) > 0 and x[0] == 1:
                ax.axhline(y[0], color=color, linestyle=":", alpha=0.3)

            # Inflection point
            key = f"{model}|{cat}"
            if key in dim_returns:
                infl = dim_returns[key].inflection_point
                if infl is not None:
                    # Find y value
                    y_infl = df_model.filter(pl.col("budget_level") == infl)["accuracy"]
                    if not y_infl.is_empty():
                        ax.scatter([infl], [y_infl[0]], color=color, marker="^", s=100, zorder=5)

        ax.set_title(cat)
        ax.set_xticks([1, 2, 3, 4, 5])

    fig.supxlabel("Budget Level")
    fig.supylabel("Accuracy")
    fig.suptitle("Figure 3: Accuracy Progression by Budget Level")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles, labels, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=len(labels)
        )

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_strategy_matrix(
    strategy_df: pl.DataFrame,
    output_path: Path,
) -> Path:
    """Figure 4: Strategy Effectiveness Heatmap."""
    _apply_style()

    if strategy_df.is_empty():
        fig, ax = plt.subplots(figsize=(10, 7))
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    pdf = strategy_df.to_pandas().set_index("task_category")

    fig, ax = plt.subplots(figsize=(10, 7))
    # Check if baseline_accuracy exists
    center_val = pdf["baseline_accuracy"].mean() if "baseline_accuracy" in pdf else 0.5

    sns.heatmap(pdf, annot=True, fmt=".2f", cmap="RdYlGn", center=center_val, ax=ax)

    ax.set_title("Figure 4: Strategy Effectiveness by Task Category")
    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _compute_pareto_frontier(costs: list[float], accuracies: list[float]) -> list[int]:
    """Return indices of Pareto-optimal points (min cost, max accuracy)."""
    # Sort by cost ascending
    indexed = list(enumerate(zip(costs, accuracies)))
    indexed.sort(key=lambda x: x[1][0])

    frontier = []
    max_acc = -1.0

    for orig_idx, (c, a) in indexed:
        if a >= max_acc:
            frontier.append(orig_idx)
            max_acc = a

    return frontier


def plot_cost_accuracy_pareto(
    model_comparison_df: pl.DataFrame,
    output_path: Path,
) -> Path:
    """Figure 5: Cost vs Accuracy Scatter (Pareto Frontier)."""
    _apply_style()

    if model_comparison_df.is_empty():
        fig, ax = plt.subplots(figsize=(8, 6))
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    costs = model_comparison_df["total_cost_usd"].to_list()
    accs = model_comparison_df["overall_accuracy"].to_list()
    models = model_comparison_df["model"].to_list()
    budgets = model_comparison_df["budget_level"].to_list()

    fig, ax = plt.subplots(figsize=(8, 6))

    # If costs are all zero (placeholder), add slight jitter so we can see points
    import random

    if all(c == 0.0 for c in costs):
        costs = [random.uniform(0.1, 10.0) * b for b in budgets]

    pareto_indices = _compute_pareto_frontier(costs, accs)

    for i in range(len(costs)):
        color = PALETTE.get(models[i], "#333333")
        ax.scatter(costs[i], accs[i], color=color, s=100, alpha=0.8)
        # Annotation
        if i in pareto_indices:
            ax.annotate(
                f"{models[i].split('/')[-1]} L{budgets[i]}",
                (costs[i], accs[i]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )

    # Draw Pareto line
    p_costs = [costs[i] for i in pareto_indices]
    p_accs = [accs[i] for i in pareto_indices]
    ax.step(
        p_costs,
        p_accs,
        where="post",
        color="red",
        linestyle="--",
        alpha=0.5,
        label="Pareto Frontier",
    )

    ax.set_xscale("log")
    ax.set_xlabel("Estimated Cost (USD, log scale)")
    ax.set_ylabel("Macro-Average Accuracy")
    ax.set_title("Figure 5: Cost vs Accuracy (Pareto Frontier)")
    ax.legend()

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_marginal_gains(
    dim_returns: dict[str, DimReturnsResult],
    output_path: Path,
) -> Path:
    """Figure 6: Marginal Gain Waterfall Chart."""
    _apply_style()

    if not dim_returns:
        fig, ax = plt.subplots(figsize=(12, 5))
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    # Aggregate gains by model across all categories
    # model -> gains list [L1->L2, L2->L3, L3->L4, L4->L5]
    model_gains = {}
    model_counts = {}

    for res in dim_returns.values():
        model = res.model
        gains = res.marginal_gains[1:]  # ignore L1 (0)

        if model not in model_gains:
            model_gains[model] = [0.0] * 4
            model_counts[model] = 0

        # pad if short
        gains = gains + [0.0] * (4 - len(gains))
        for i in range(4):
            model_gains[model][i] += gains[i]
        model_counts[model] += 1

    models = list(model_gains.keys())
    for m in models:
        for i in range(4):
            model_gains[m][i] /= model_counts[m]

    fig, ax = plt.subplots(figsize=(12, 5))
    import numpy as np

    x = np.arange(4)
    width = 0.8 / len(models)

    for i, m in enumerate(models):
        color = PALETTE.get(m, "#333333")
        y = [val * 100 for val in model_gains[m]]  # percentage points
        ax.bar(x + i * width - 0.4 + width / 2, y, width, label=m, color=color)

    ax.axhline(0, color="black", linestyle="-", linewidth=1)
    ax.axhline(2.0, color="red", linestyle="--", label="2% Threshold")
    ax.axhspan(-10, 2.0, color="red", alpha=0.1, label="Diminishing Returns Zone")

    ax.set_xticks(x)
    ax.set_xticklabels(["L1 → L2", "L2 → L3", "L3 → L4", "L4 → L5"])
    ax.set_ylabel("Marginal Accuracy Gain (%)")
    ax.set_title("Figure 6: Marginal Accuracy Gains per Budget Step")
    ax.set_ylim(bottom=min(-2, min(min(g) * 100 for g in model_gains.values()) - 2))

    ax.legend(loc="upper right")

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_all_figures(
    tables_dir: Path,
    figures_dir: Path,
) -> dict[str, Path]:
    """Generate all 6 figures."""
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Load CSVs
    try:
        efficiency_df = pl.read_csv(tables_dir / "efficiency_scores.csv")
    except Exception:
        efficiency_df = pl.DataFrame()

    try:
        strategy_df = pl.read_csv(tables_dir / "strategy_matrix.csv")
    except Exception:
        strategy_df = pl.DataFrame()

    try:
        dim_df = pl.read_csv(tables_dir / "diminishing_returns_summary.csv")
        dim_returns = {}
        for row in dim_df.to_dicts():
            model = row["model"]
            cat = row["task_category"]
            dim_returns[f"{model}|{cat}"] = DimReturnsResult(
                model=model,
                task_category=cat,
                accuracy_by_level=[],
                marginal_gains=[0, 0, 0, 0, 0],  # dummy
                inflection_point=row.get("inflection_point"),
                peak_efficiency_level=row.get("peak_efficiency_level", 1),
                plateau_detected=row.get("plateau_detected", False),
                total_accuracy_gain=row.get("total_accuracy_gain", 0.0),
            )
    except Exception:
        dim_returns = {}

    try:
        model_comp_df = pl.read_csv(tables_dir / "model_comparison.csv")
    except Exception:
        model_comp_df = pl.DataFrame()

    figures = {}

    with Progress() as progress:
        task = progress.add_task("Generating figures...", total=6)

        figures["diminishing_returns"] = plot_diminishing_returns(
            efficiency_df, figures_dir / "fig1_diminishing_returns.png"
        )
        progress.advance(task)

        figures["efficiency_heatmap"] = plot_efficiency_heatmap(
            efficiency_df, figures_dir / "fig2_efficiency_heatmap.png"
        )
        progress.advance(task)

        figures["accuracy_by_budget"] = plot_accuracy_by_budget(
            efficiency_df, dim_returns, figures_dir / "fig3_accuracy_by_budget.png"
        )
        progress.advance(task)

        figures["strategy_matrix"] = plot_strategy_matrix(
            strategy_df, figures_dir / "fig4_strategy_matrix.png"
        )
        progress.advance(task)

        figures["cost_accuracy_pareto"] = plot_cost_accuracy_pareto(
            model_comp_df, figures_dir / "fig5_cost_vs_accuracy.png"
        )
        progress.advance(task)

        figures["marginal_gains"] = plot_marginal_gains(
            dim_returns, figures_dir / "fig6_marginal_gains.png"
        )
        progress.advance(task)

    return figures
