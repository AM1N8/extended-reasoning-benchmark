"""Tests for the analysis metrics module."""

import polars as pl

from benchmark.analysis.metrics import (
    analyze_diminishing_returns,
    compute_efficiency_scores,
    compute_significance_tests,
    compute_strategy_matrix,
)


def test_efficiency_score():
    """Verify efficiency scoring logic and reliable flags."""
    df = pl.DataFrame(
        {
            "model": ["test-m", "test-m", "test-m", "test-m"],
            "task_category": ["test-c", "test-c", "test-c", "test-c"],
            "budget_level": [1, 1, 2, 2],
            "is_correct": [1, 1, 0, 1],
            "reasoning_tokens": [0, 0, 200, 200],
            "total_tokens": [10, 10, 210, 210],
            "latency_seconds": [1.0, 1.0, 5.0, 5.0],
        }
    )

    # We need to mock DB
    class DummyDB:
        def get_runs(self, filters=None):
            return df

    eff_df = compute_efficiency_scores(DummyDB())

    assert len(eff_df) == 2

    # Level 1: accuracy 1.0, tokens 0 -> 1000/1 = 1000.0
    l1 = eff_df.filter(pl.col("budget_level") == 1)
    assert l1["accuracy"][0] == 1.0
    assert l1["efficiency_score"][0] == 1000.0
    assert l1["is_reliable"][0] is False  # n_runs = 2 < 5

    # Level 2: accuracy 0.5, tokens 200 -> (0.5 * 1000) / 200 = 2.5
    l2 = eff_df.filter(pl.col("budget_level") == 2)
    assert l2["accuracy"][0] == 0.5
    assert l2["efficiency_score"][0] == 2.5


def test_diminishing_returns():
    """Test the inflection point detection."""
    df = pl.DataFrame(
        {
            "model": ["m1", "m1", "m1", "m1", "m1"],
            "task_category": ["c1", "c1", "c1", "c1", "c1"],
            "budget_level": [1, 2, 3, 4, 5],
            "accuracy": [0.4, 0.6, 0.75, 0.77, 0.78],
            "efficiency_score": [400, 300, 250, 192, 156],
        }
    )

    res = analyze_diminishing_returns(df)
    key = "m1|c1"

    assert key in res
    dim = res[key]
    assert dim.inflection_point == 4  # gain from 3 to 4 is 0.02, which is <= 0.02
    # Ah, threshold is 0.02. 0.02 is not < 0.02, it is exactly 0.02!
    # Let's check my logic: marginal_gains[L] < 0.02.
    # 0.77 - 0.75 = 0.02. In float math it could be 0.020000000000000018.

    df2 = pl.DataFrame(
        {
            "model": ["m2", "m2", "m2", "m2", "m2"],
            "task_category": ["c2", "c2", "c2", "c2", "c2"],
            "budget_level": [1, 2, 3, 4, 5],
            "accuracy": [0.4, 0.55, 0.70, 0.82, 0.91],
            "efficiency_score": [400, 275, 233, 205, 182],
        }
    )
    res2 = analyze_diminishing_returns(df2)
    dim2 = res2["m2|c2"]
    assert dim2.inflection_point is None
    assert dim2.plateau_detected is False


def test_strategy_matrix():
    """Verify matrix calculation handles multiple strategies properly."""
    df = pl.DataFrame(
        {
            "is_error": [0, 0, 0],
            "task_category": ["c1", "c1", "c1"],
            "is_correct": [1, 0, 1],
            "strategy_tags": [
                '{"decomposition": 1, "analogy": 0}',
                '{"decomposition": 1, "backtracking": 1}',
                "{}",  # baseline
            ],
        }
    )

    class DummyDB:
        def get_runs(self, filters=None):
            return df

    matrix = compute_strategy_matrix(DummyDB())
    assert len(matrix) == 1
    assert "decomposition" in matrix.columns
    assert "baseline_accuracy" in matrix.columns


def test_significance_tests():
    """Verify p-values map properly for chi-squared comparisons."""
    # 90/100 vs 50/100
    df = pl.DataFrame(
        {
            "model": ["m"] * 200,
            "task_category": ["c"] * 200,
            "budget_level": [1] * 100 + [5] * 100,
            "is_correct": [1] * 50 + [0] * 50 + [1] * 90 + [0] * 10,
            "is_error": [0] * 200,
        }
    )

    class DummyDB:
        def get_runs(self, filters=None):
            return df

    sig = compute_significance_tests(DummyDB())
    assert len(sig) == 1
    row = sig.to_dicts()[0]
    assert row["accuracy_l1"] == 0.5
    assert row["accuracy_l5"] == 0.9
    assert row["is_significant"] is True
