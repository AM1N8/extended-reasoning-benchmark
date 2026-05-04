"""Core benchmark execution engine."""

import asyncio
import logging
import time
from collections import namedtuple
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import polars as pl
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from benchmark.clients.__init__ import RateLimitedDispatcher
from benchmark.clients.base import BudgetLevel, QueryRequest
from benchmark.database import BenchmarkRun, DatabaseManager, RunSession
from benchmark.datasets.loader import StandardDataset
from benchmark.engine.budget import apply_budget

logger = logging.getLogger(__name__)

ALL_MODELS = [
    "openai/o1",
    "openai/o3-mini",
    "deepseek/DeepSeek-R1",
    "gemini-2.0-flash-thinking-exp-01-21",
    "openai/gpt-4o",  # Baseline 1
    "anthropic/claude-3-5-sonnet",  # Baseline 2
]

ALL_DATASETS = [
    "math_500",
    "gsm8k",
    "humaneval",
    "mbpp",
    "logic_grid",
    "cause_effect",
    "alfworld_plans",
    "arc_challenge",
    "hellaswag",
    "drop",
    "bbh_word_sorting",
    "bbh_analogies",
]

ALL_BUDGET_LEVELS = [1, 2, 3, 4, 5]

RunJob = namedtuple(
    "RunJob", ["model", "dataset_name", "task_category", "question", "budget_level"]
)


class BenchmarkRunner:
    """Orchestrates the execution of the benchmark matrix."""

    def __init__(
        self,
        dispatcher: RateLimitedDispatcher,
        db: DatabaseManager,
        data_dir: Path,
        dry_run: bool = False,
        dry_run_questions: int = 2,
        models: list[str] | None = None,
        datasets: list[str] | None = None,
        budget_levels: list[int] | None = None,
        resume: bool = True,
    ):
        self.dispatcher = dispatcher
        self.db = db
        self.data_dir = data_dir
        self.dry_run = dry_run
        self.dry_run_questions = dry_run_questions
        self.models = models or ALL_MODELS
        self.datasets = datasets or ALL_DATASETS
        self.budget_levels = budget_levels or ALL_BUDGET_LEVELS
        self.resume = resume

        self.console = Console()
        self.session_id = str(uuid4())

        # Setup session log file
        log_dir = Path("results")
        log_dir.mkdir(exist_ok=True)
        self.log_file = log_dir / f"run_{self.session_id}.log"
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)

    def _get_completed_run_keys(self) -> set[str]:
        """Get set of completed runs (model|dataset|question_id|budget)."""
        df = self.db.get_runs()
        if df.is_empty() or "run_id" not in df.columns:
            return set()
        return set(
            df.select(
                (
                    pl.col("model")
                    + "|"
                    + pl.col("dataset_name")
                    + "|"
                    + pl.col("question_id")
                    + "|"
                    + pl.col("budget_level").cast(pl.Utf8)
                ).alias("key")
            )["key"].to_list()
        )

    def _build_work_queue(self) -> list[RunJob]:
        """Build the queue of jobs to run."""
        completed_keys = self._get_completed_run_keys() if self.resume else set()
        queue = []

        for ds_name in self.datasets:
            ds_path = self.data_dir / f"{ds_name}.json"
            if not ds_path.exists():
                logger.warning(f"Dataset missing: {ds_path}. Skipping.")
                continue

            try:
                ds = StandardDataset.load(ds_path)
            except Exception as e:
                logger.error(f"Failed to load {ds_path}: {e}")
                continue

            questions = ds.questions[: self.dry_run_questions] if self.dry_run else ds.questions

            # Group by dataset -> model -> budget to keep context switching minimal
            for model in self.models:
                for budget in self.budget_levels:
                    for q in questions:
                        key = f"{model}|{ds_name}|{q.question_id}|{budget}"
                        if key not in completed_keys:
                            queue.append(RunJob(model, ds_name, ds.task_category, q, budget))

        return queue

    async def _process_job(
        self, job: RunJob, semaphore: asyncio.Semaphore, progress: Progress, task_id: int
    ) -> bool:
        """Process a single job."""
        async with semaphore:
            start_time = time.monotonic()

            try:
                final_prompt, system_prompt, extra_params = apply_budget(
                    job.question.prompt, job.model, BudgetLevel(job.budget_level)
                )

                request = QueryRequest(
                    prompt=final_prompt,
                    model=job.model,
                    budget_level=BudgetLevel(job.budget_level),
                )

                response = await self.dispatcher.query(request)

                is_error = 0
                error_message = ""
                latency = time.monotonic() - start_time

                if response is None:
                    is_error = 1
                    error_message = "All retries exhausted"

                    # Create empty/default record for failure
                    run = BenchmarkRun(
                        model=job.model,
                        task_category=job.task_category,
                        dataset_name=job.dataset_name,
                        question_id=job.question.question_id,
                        budget_level=job.budget_level,
                        prompt=final_prompt,
                        ground_truth=job.question.ground_truth,
                        raw_trace="",
                        final_answer="",
                        input_tokens=0,
                        reasoning_tokens=0,
                        output_tokens=0,
                        latency_seconds=latency,
                        is_error=is_error,
                        error_message=error_message,
                    )
                else:
                    run = BenchmarkRun(
                        model=response.model,
                        task_category=job.task_category,
                        dataset_name=job.dataset_name,
                        question_id=job.question.question_id,
                        budget_level=job.budget_level,
                        prompt=final_prompt,
                        ground_truth=job.question.ground_truth,
                        raw_trace=response.raw_trace or "",
                        final_answer=response.final_answer,
                        input_tokens=response.input_tokens,
                        reasoning_tokens=response.reasoning_tokens,
                        output_tokens=response.output_tokens,
                        latency_seconds=response.latency_seconds,
                        is_error=0,
                        error_message="",
                    )

                # Retry DB inserts on failure
                for db_attempt in range(3):
                    try:
                        self.db.insert_run(run)
                        break
                    except Exception as e:
                        if db_attempt == 2:
                            logger.error(f"Failed to insert DB record for {job}: {e}")
                            raise
                        await asyncio.sleep(1)

                progress.advance(task_id)
                return not is_error

            except Exception as e:
                logger.exception(f"Unhandled exception in job {job}: {e}")
                progress.advance(task_id)
                return False

    async def run(self) -> None:
        """Main execution flow."""
        self.db.initialize()

        session = RunSession(
            session_id=self.session_id,
            started_at=datetime.now(UTC).isoformat(),
            mode="dry_run" if self.dry_run else "full",
        )
        self.db.create_session(session)

        queue = self._build_work_queue()
        total_queued = len(queue)

        if total_queued == 0:
            self.console.print("[bold green]No jobs to run (all completed).[/bold green]")
            return

        completed_keys = self._get_completed_run_keys() if self.resume else set()
        already_done = len(completed_keys)

        self.console.print("┌─────────────────────────────────────────┐")
        self.console.print("│  [bold cyan]Benchmark Session[/bold cyan]                      │")
        self.console.print(f"│  Models:        {len(self.models):<23} │")
        self.console.print(f"│  Datasets:      {len(self.datasets):<23} │")
        self.console.print(f"│  Budget levels: {len(self.budget_levels):<23} │")
        self.console.print(f"│  Mode:          {'Dry Run' if self.dry_run else 'Full':<23} │")
        self.console.print(f"│  Already done:  {already_done:<23} │")
        self.console.print(f"│  Remaining:     {total_queued:<23} │")
        self.console.print("└─────────────────────────────────────────┘")

        if total_queued > 1000 and not self.dry_run:
            self.console.print(
                "[bold red]WARNING: Running >1000 jobs requires significant API credits.[/bold red]"
            )
            # Usually handled in CLI, but runner prints it too for visibility

        # Semaphore limits concurrency at the runner layer,
        # but the actual rate limit dispatching enforces exact API gaps
        semaphore = asyncio.Semaphore(3)

        successful_runs = 0
        failed_runs = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            transient=False,
            console=self.console,
        ) as progress:
            task = progress.add_task("[cyan]Running benchmark...", total=total_queued)

            tasks = []
            for i, job in enumerate(queue):
                t = asyncio.create_task(self._process_job(job, semaphore, progress, task))
                tasks.append(t)

                # We could batch-wait to avoid massive task lists in huge runs,
                # but asyncio handles 36,000 pending tasks relatively well.
                # However, chunking is safer for memory.
                if len(tasks) >= 1000:
                    results = await asyncio.gather(*tasks)
                    successful_runs += sum(results)
                    failed_runs += len(results) - sum(results)
                    tasks = []
                    logger.info(
                        f"Checkpoint: {successful_runs + failed_runs} / {total_queued} completed."
                    )

            if tasks:
                results = await asyncio.gather(*tasks)
                successful_runs += sum(results)
                failed_runs += len(results) - sum(results)

        # Update session
        self.db.update_session(
            session_id=self.session_id,
            finished_at=datetime.now(UTC).isoformat(),
            total_runs=total_queued,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
        )

        self.console.print("\n[bold green]Benchmark Complete[/bold green]")
        self.console.print(
            f"Total: {total_queued} | Success: {successful_runs} | Failed: {failed_runs}"
        )
