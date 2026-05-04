"""Tests for the visualizations module."""

import tempfile
from pathlib import Path

import polars as pl
from PIL import Image

from benchmark.analysis.metrics import DimReturnsResult
from benchmark.analysis.visualizations import (
    _compute_pareto_frontier,
    plot_accuracy_by_budget,
    plot_cost_accuracy_pareto,
    plot_diminishing_returns,
    plot_efficiency_heatmap,
    plot_marginal_gains,
    plot_strategy_matrix,
)


def _validate_image(path: Path):
    assert path.exists()
    assert path.stat().st_size > 5000  # valid PNG > 5KB
    # Open with PIL
    img = Image.open(path)
    assert img.format == "PNG"


def test_pareto_frontier():
    """Test Pareto indices calculation."""
    costs = [1, 2, 3, 2.5]
    accs = [0.5, 0.7, 0.6, 0.8]
    # Expected:
    # cost 1 -> 0.5 (yes)
    # cost 2 -> 0.7 (yes)
    # cost 2.5 -> 0.8 (yes)
    # cost 3 -> 0.6 (no, dominated by 2.5 which is cheaper and better)
    indices = _compute_pareto_frontier(costs, accs)
    # The _compute_pareto_frontier sorts by cost internally but returns original indices
    # Sort order by cost: (0, c=1, a=0.5), (1, c=2, a=0.7), (3, c=2.5, a=0.8), (2, c=3, a=0.6)
    # Max acc tracks:
    # 1: a=0.5 -> max=0.5, add 0
    # 2: a=0.7 -> max=0.7, add 1
    # 2.5: a=0.8 -> max=0.8, add 3
    # 3: a=0.6 < max (0.8) -> skip
    assert sorted(indices) == [0, 1, 3]


def test_smoke_plots():
    """Smoke test to ensure plots generate without exceptions."""
    eff_df = pl.DataFrame(
        {
            "model": ["m1", "m1", "m2", "m2"],
            "task_category": ["c1", "c1", "c1", "c1"],
            "budget_level": [1, 2, 1, 2],
            "accuracy": [0.5, 0.6, 0.4, 0.5],
            "avg_reasoning_tokens": [100, 200, 150, 250],
            "efficiency_score": [50.0, 30.0, 26.6, 20.0],
            "is_reliable": [True, True, True, True],
        }
    )

    strat_df = pl.DataFrame(
        {
            "task_category": ["c1", "c2"],
            "decomposition": [0.8, 0.9],
            "analogy": [0.7, 0.6],
            "baseline_accuracy": [0.5, 0.4],
        }
    )

    comp_df = pl.DataFrame(
        {
            "model": ["m1", "m2"],
            "budget_level": [1, 1],
            "overall_accuracy": [0.5, 0.4],
            "total_cost_usd": [0.01, 0.05],
        }
    )

    dim_returns = {
        "m1|c1": DimReturnsResult("m1", "c1", [0.5, 0.6], [0, 0.1, 0, 0, 0], None, 1, False, 0.1)
    }

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        p1 = plot_diminishing_returns(eff_df, tdp / "fig1.png")
        _validate_image(p1)

        p2 = plot_efficiency_heatmap(eff_df, tdp / "fig2.png")
        _validate_image(p2)

        p3 = plot_accuracy_by_budget(eff_df, dim_returns, tdp / "fig3.png")
        _validate_image(p3)

        p4 = plot_strategy_matrix(strat_df, tdp / "fig4.png")
        _validate_image(p4)

        p5 = plot_cost_accuracy_pareto(comp_df, tdp / "fig5.png")
        _validate_image(p5)

        p6 = plot_marginal_gains(dim_returns, tdp / "fig6.png")
        _validate_image(p6)
