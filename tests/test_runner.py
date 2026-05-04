"""Integration and unit tests for the BenchmarkRunner."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from benchmark.clients.base import ModelResponse
from benchmark.database import BenchmarkRun, DatabaseManager
from benchmark.datasets.loader import Question, StandardDataset
from benchmark.engine.runner import BenchmarkRunner


@pytest.fixture
def mock_db(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)
    db.initialize()
    return db


@pytest.fixture
def mock_dataset(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    ds = StandardDataset(
        dataset_name="math_500",
        task_category="Math",
        source="Test",
        questions=[
            Question("q1", "What is 2+2?", "4", "numeric", "easy"),
            Question("q2", "What is 3+3?", "6", "numeric", "easy"),
            Question("q3", "What is 4+4?", "8", "numeric", "easy"),
        ],
    )
    ds.save(data_dir / "math_500.json")
    return data_dir


@pytest.fixture
def mock_dispatcher():
    dispatcher = MagicMock()
    dispatcher.query = AsyncMock(
        return_value=ModelResponse(
            model="test-model",
            prompt="Test Prompt",
            raw_trace=None,
            final_answer="Answer",
            input_tokens=10,
            reasoning_tokens=0,
            output_tokens=5,
            latency_seconds=1.0,
            raw_api_response={},
        )
    )
    return dispatcher


@pytest.mark.asyncio
async def test_runner_dry_run_execution(mock_db, mock_dataset, mock_dispatcher):
    """Test full dry run execution inserts exactly N expected rows."""
    runner = BenchmarkRunner(
        dispatcher=mock_dispatcher,
        db=mock_db,
        data_dir=mock_dataset,
        dry_run=True,
        dry_run_questions=2,
        models=["test-model"],
        datasets=["math_500"],
        budget_levels=[1],
    )

    await runner.run()

    # Dry run is 2 questions, 1 model, 1 budget = 2 jobs
    df = mock_db.get_runs()
    assert len(df) == 2
    assert df["question_id"].to_list() == ["q1", "q2"]
    assert df["model"].to_list() == ["test-model", "test-model"]


@pytest.mark.asyncio
async def test_runner_resumability(mock_db, mock_dataset, mock_dispatcher):
    """Test that existing DB records are skipped during queue building."""
    # Pre-populate DB with q1 completion
    run = BenchmarkRun(
        model="test-model",
        task_category="Math",
        dataset_name="math_500",
        question_id="q1",
        budget_level=1,
        prompt="Test",
        ground_truth="4",
        is_error=0,
    )
    mock_db.insert_run(run)

    runner = BenchmarkRunner(
        dispatcher=mock_dispatcher,
        db=mock_db,
        data_dir=mock_dataset,
        dry_run=True,
        dry_run_questions=2,  # Would do q1 and q2
        models=["test-model"],
        datasets=["math_500"],
        budget_levels=[1],
        resume=True,
    )

    queue = runner._build_work_queue()
    # Since q1 is already done, only q2 should be queued
    assert len(queue) == 1
    assert queue[0].question.question_id == "q2"


@pytest.mark.asyncio
async def test_runner_error_handling(mock_db, mock_dataset, mock_dispatcher):
    """Test that a failed dispatcher query inserts an error row and continues."""
    # Force dispatcher to return None (failure)
    mock_dispatcher.query = AsyncMock(return_value=None)

    runner = BenchmarkRunner(
        dispatcher=mock_dispatcher,
        db=mock_db,
        data_dir=mock_dataset,
        dry_run=True,
        dry_run_questions=1,
        models=["test-model"],
        datasets=["math_500"],
        budget_levels=[1],
    )

    await runner.run()

    df = mock_db.get_runs()
    assert len(df) == 1
    assert df["is_error"][0] == 1
    assert df["error_message"][0] == "All retries exhausted"
