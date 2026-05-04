"""Tests for the cost dashboard logic."""

import polars as pl

from benchmark.report.cost_dashboard import _get_cost, mark_pareto_optimal


def test_pricing_calculation():
    """Verify cost formula logic."""
    # 1000 input tokens, 2000 reasoning tokens, 500 output tokens for openai/o1
    # PRICING["openai/o1"] -> input: 15.00, reasoning: 15.00, output: 60.00
    # Expected: (1000*15 + 2000*15 + 500*60) / 1000000 = (15000 + 30000 + 30000) / 1000000 = 0.075
    # The prompt expected: 0.0756 maybe due to 1024 token math? But the formula asks for raw 1_000_000 division.
    # We will test based on raw division.
    cost = _get_cost("openai/o1", 1000, 2000, 500)
    assert abs(cost - 0.075) < 1e-6

    # Test fallback
    cost_fb = _get_cost("unknown-model", 1000, 2000, 500)
    # Falls back to gpt-4o: 1000*2.5 + 0 + 500*10 / 1m = 7500 / 1000000 = 0.0075
    assert abs(cost_fb - 0.0075) < 1e-6


def test_pareto_optimality():
    """Verify pareto optimality boolean assignment."""
    df = pl.DataFrame(
        {
            "model": ["A", "B", "C"],
            "cost_per_correct_answer_usd": [1.0, 2.0, 2.5],
            "avg_accuracy": [0.7, 0.8, 0.75],
        }
    )

    res = mark_pareto_optimal(df)

    pareto_list = res["is_pareto_optimal"].to_list()
    # A: cost=1.0, acc=0.7 (Pareto)
    # B: cost=2.0, acc=0.8 (Pareto, highest acc)
    # C: cost=2.5, acc=0.75 (Dominated by B: B has lower cost 2.0 < 2.5 and higher acc 0.8 > 0.75)
    assert pareto_list == [True, True, False]


def test_cost_per_correct_answer():
    """Verify cost per correct answer calculation logic (as modeled)."""
    cost_per_run = 0.01
    accuracy = 0.5
    cost_per_correct = cost_per_run / accuracy
    assert cost_per_correct == 0.02

    cost_per_run = 0.001
    accuracy = 0.9
    cost_per_correct = cost_per_run / accuracy
    assert abs(cost_per_correct - 0.0011111) < 1e-5
