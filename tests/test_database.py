"""Tests for the SQLite database schema and operations."""

import json

import polars as pl
import pytest

from benchmark.database import BenchmarkRun, DatabaseManager


@pytest.fixture()
def db_manager(tmp_path) -> DatabaseManager:
    """Provide a DatabaseManager instance with a temporary SQLite database."""
    db_path = tmp_path / "test_benchmark.db"
    manager = DatabaseManager(db_path)
    manager.initialize()
    return manager


@pytest.fixture()
def sample_run() -> BenchmarkRun:
    """Provide a sample BenchmarkRun instance for testing."""
    return BenchmarkRun(
        model="openai/o1",
        task_category="MATH",
        dataset_name="gsm8k",
        question_id="q123",
        budget_level=3,
        prompt="What is 2+2?",
        ground_truth="4",
        raw_trace="<think>Adding 2 and 2.</think>",
        final_answer="4",
        input_tokens=10,
        reasoning_tokens=5,
        output_tokens=1,
        latency_seconds=1.5,
    )


def test_insert_and_read_run(db_manager: DatabaseManager, sample_run: BenchmarkRun) -> None:
    """Test inserting a run and reading it back as a Polars DataFrame."""
    run_id = db_manager.insert_run(sample_run)
    assert run_id is not None
    assert isinstance(run_id, str)
    assert len(run_id) > 10  # Roughly UUID length

    # Read back using filters
    df = db_manager.get_runs({"run_id": run_id})
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 1

    # Verify data matches
    row = df.row(0, named=True)
    assert row["model"] == "openai/o1"
    assert row["task_category"] == "MATH"
    assert row["budget_level"] == 3
    assert row["total_tokens"] == 16  # 10 + 5 + 1


def test_update_grading(db_manager: DatabaseManager, sample_run: BenchmarkRun) -> None:
    """Test updating the grading fields of an existing run."""
    run_id = db_manager.insert_run(sample_run)

    # Initial state: is_correct should be NULL
    ungraded = db_manager.get_ungraded_runs()
    assert len(ungraded) == 1
    assert ungraded.row(0, named=True)["run_id"] == run_id

    # Apply grading
    db_manager.update_grading(run_id, is_correct=1, rationale="Correctly added 2+2.")

    # Verify update
    ungraded_after = db_manager.get_ungraded_runs()
    assert len(ungraded_after) == 0

    df = db_manager.get_runs({"run_id": run_id})
    row = df.row(0, named=True)
    assert row["is_correct"] == 1
    assert row["grader_rationale"] == "Correctly added 2+2."


def test_get_summary_stats(db_manager: DatabaseManager, sample_run: BenchmarkRun) -> None:
    """Test aggregation of summary stats over multiple graded runs."""
    # Insert 3 runs: 2 correct, 1 incorrect
    run_id_1 = db_manager.insert_run(sample_run)
    db_manager.update_grading(run_id_1, is_correct=1, rationale="Good")

    # Run 2: Correct, different latency/tokens
    run2 = BenchmarkRun(
        model="openai/o1",
        task_category="MATH",
        dataset_name="gsm8k",
        question_id="q124",
        budget_level=3,
        prompt="What is 3+3?",
        ground_truth="6",
        input_tokens=10,
        reasoning_tokens=10,
        output_tokens=2,
        latency_seconds=2.0,
    )
    run_id_2 = db_manager.insert_run(run2)
    db_manager.update_grading(run_id_2, is_correct=1, rationale="Good")

    # Run 3: Incorrect
    run3 = BenchmarkRun(
        model="openai/o1",
        task_category="MATH",
        dataset_name="gsm8k",
        question_id="q125",
        budget_level=3,
        prompt="What is 4+4?",
        ground_truth="8",
        input_tokens=10,
        reasoning_tokens=5,
        output_tokens=1,
        latency_seconds=1.0,
    )
    run_id_3 = db_manager.insert_run(run3)
    db_manager.update_grading(run_id_3, is_correct=0, rationale="Bad")

    # Run 4: Different model/category (should group separately)
    run4 = BenchmarkRun(
        model="deepseek/r1",
        task_category="CODING",
        dataset_name="humaneval",
        question_id="q1",
        budget_level=1,
        prompt="def add():",
        ground_truth="pass",
        input_tokens=5,
        reasoning_tokens=0,
        output_tokens=5,
        latency_seconds=0.5,
    )
    run_id_4 = db_manager.insert_run(run4)
    db_manager.update_grading(run_id_4, is_correct=1, rationale="Good")

    stats = db_manager.get_summary_stats()
    assert isinstance(stats, pl.DataFrame)
    assert len(stats) == 2  # 2 distinct groups

    # Check openai/o1 group
    o1_stats = stats.filter(
        (pl.col("model") == "openai/o1") & (pl.col("task_category") == "MATH")
    ).row(0, named=True)

    assert o1_stats["run_count"] == 3
    assert o1_stats["accuracy"] == pytest.approx(0.666, rel=1e-2)  # 2 out of 3 correct
    # Avg tokens: (16 + 22 + 16) / 3 = 18
    assert o1_stats["avg_tokens"] == 18.0
    # Avg latency: (1.5 + 2.0 + 1.0) / 3 = 1.5
    assert o1_stats["avg_latency"] == 1.5


def test_update_strategy_tags_and_efficiency(
    db_manager: DatabaseManager, sample_run: BenchmarkRun
) -> None:
    """Test updating JSON strategy tags and efficiency score."""
    run_id = db_manager.insert_run(sample_run)

    tags = {"decomposition": 1, "backtracking": 0}
    db_manager.update_strategy_tags(run_id, tags)
    db_manager.update_efficiency_score(run_id, 200.0)

    df = db_manager.get_runs({"run_id": run_id})
    row = df.row(0, named=True)

    assert row["efficiency_score"] == 200.0
    assert json.loads(row["strategy_tags"]) == tags
