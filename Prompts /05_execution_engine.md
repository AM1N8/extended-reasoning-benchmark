# Prompt 05 — Benchmark Execution Engine

## Role & Mission

You are a systems engineer building the **main benchmark orchestration loop** — the core engine that ties together datasets, API clients, and database storage to run the full experiment. This is the heart of the pipeline.

---

## GLOBAL CONTEXT

```
Project: LLM reasoning benchmark
Execution matrix:
  - 6 models × 12 datasets × 5 budget levels = 360 unique configurations
  - 50–100 questions per dataset
  - Total runs: ~18,000–36,000 API calls (run overnight on free tiers)
  
Stack: Python 3.12+, asyncio, httpx, polars, rich, sqlite3
Dispatcher: RateLimitedDispatcher from clients module
Database: DatabaseManager from database module
Inputs: ProcessedDataset JSON files from data/processed/
```

---

## Execution Matrix Definition

```python
# src/benchmark/engine/runner.py

ALL_MODELS = [
    "openai/o1",
    "openai/o3-mini",
    "deepseek/DeepSeek-R1",
    "gemini-2.0-flash-thinking-exp-01-21",
    "openai/gpt-4o",           # Baseline 1
    "anthropic/claude-3-5-sonnet",  # Baseline 2
]

ALL_DATASETS = [
    "math_500", "gsm8k", "humaneval", "mbpp",
    "logic_grid", "cause_effect", "alfworld_plans",
    "arc_challenge", "hellaswag", "drop",
    "bbh_word_sorting", "bbh_analogies",
]

ALL_BUDGET_LEVELS = [1, 2, 3, 4, 5]
```

---

## Module: `src/benchmark/engine/runner.py`

### `BenchmarkRunner` Class

```python
class BenchmarkRunner:
    def __init__(
        self,
        dispatcher: RateLimitedDispatcher,
        db: DatabaseManager,
        data_dir: Path,
        dry_run: bool = False,
        dry_run_questions: int = 2,
        models: list[str] | None = None,       # None = all models
        datasets: list[str] | None = None,     # None = all datasets
        budget_levels: list[int] | None = None, # None = all 5 levels
    ):
```

### Core Execution Flow

**`runner.run()` method must:**

1. **Build the work queue** — a list of `RunJob` namedtuples:
   ```python
   RunJob = namedtuple("RunJob", ["model", "dataset_name", "question", "budget_level"])
   ```

2. **Skip already-completed runs** — before queuing, check the DB for existing `run_id`s with the same `(model, dataset_name, question_id, budget_level)` and skip them. This makes the runner **resumable**.

3. **Display a rich summary table** before starting:
   ```
   ┌─────────────────────────────────────────┐
   │  Benchmark Session                      │
   │  Models:        6                       │
   │  Datasets:      12                      │
   │  Budget levels: 5                       │
   │  Questions:     100 per dataset         │
   │  Total runs:    36,000                  │
   │  Already done:  1,240                   │
   │  Remaining:     34,760                  │
   └─────────────────────────────────────────┘
   ```

4. **Process jobs with concurrency control**:
   - Use `asyncio.Semaphore(max_concurrent=3)` to allow mild parallelism
   - But keep per-provider rate limiting from the dispatcher
   - Process jobs in order: dataset → model → budget (group by dataset to keep context local)

5. **Show a live progress bar** (using `rich.progress`):
   ```
   Running benchmark... ████████████░░░░░░░  62% │ 21,752/34,760 │ ETA: 8h 32m
   Current: gsm8k | deepseek/R1 | L3 | Q045
   Last result: ✓ correct | 1,847 reasoning tokens | 3.2s
   ```

6. **Write results immediately** to DB after each run — never batch writes (protect against crashes).

7. **Checkpoint every 100 runs** — print a summary line to stdout.

### `RunJob` Processing Logic

```python
async def _process_job(self, job: RunJob, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        start_time = time.monotonic()
        
        # 1. Apply budget to get final prompt
        final_prompt, system_prompt, extra_params = apply_budget(
            job.question.prompt, job.model, BudgetLevel(job.budget_level)
        )
        
        # 2. Build request
        request = QueryRequest(
            prompt=final_prompt,
            model=job.model,
            budget_level=BudgetLevel(job.budget_level),
        )
        
        # 3. Dispatch (handles rate limiting + retries)
        response = await self.dispatcher.query(request)
        
        # 4. Build DB record
        if response is None:
            run = BenchmarkRun(
                model=job.model,
                task_category=job.question.task_category,
                dataset_name=job.dataset_name,
                question_id=job.question.question_id,
                budget_level=job.budget_level,
                prompt=final_prompt,
                ground_truth=job.question.ground_truth,
                is_error=1,
                error_message="All retries exhausted",
            )
        else:
            run = BenchmarkRun(
                model=job.model,
                # ... all fields from response
            )
        
        # 5. Insert immediately
        self.db.insert_run(run)
```

---

## Module: `src/benchmark/engine/__main__.py`

The CLI entry point for `uv run python -m benchmark.engine`:

```
Usage:
  python -m benchmark.engine [OPTIONS]

Options:
  --dry-run             Run only 2 questions per dataset (for validation)
  --models TEXT         Comma-separated model list (default: all)
  --datasets TEXT       Comma-separated dataset list (default: all)  
  --budgets TEXT        Comma-separated budget levels, e.g. "1,3,5" (default: all)
  --resume              Skip already-completed runs (default: True)
  --no-resume           Re-run all, overwriting existing results
```

Implement this with `argparse` (not click, to avoid extra dependency).

**Startup sequence:**
1. Load settings
2. Initialize DB (call `db.initialize()`)
3. Validate that all dataset JSON files exist — fail fast with a clear error if not
4. Print the summary table
5. Ask for confirmation if total remaining runs > 1000 (not in dry-run mode)
6. Run `asyncio.run(runner.run())`
7. Print final stats: total runs, success rate, total time elapsed

---

## Resumability Logic

```python
def _get_completed_run_keys(self) -> set[str]:
    """
    Return set of '{model}|{dataset}|{question_id}|{budget}' strings
    for runs already in the database (including errors — don't retry those 
    unless --no-resume is passed).
    """
    df = self.db.get_runs()
    if df.is_empty():
        return set()
    return set(
        df.select(
            (pl.col("model") + "|" + pl.col("dataset_name") + "|" + 
             pl.col("question_id") + "|" + pl.col("budget_level").cast(pl.Utf8))
            .alias("key")
        )["key"].to_list()
    )
```

---

## Progress Tracking with Rich

```python
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, 
    TextColumn, TimeRemainingColumn, MofNCompleteColumn
)
from rich.live import Live
from rich.table import Table
from rich.console import Console

# Use Rich Live display combining progress bar + stats panel
```

---

## Session Logging

At the start of each run, create a `RunSession` record:
```python
session = RunSession(
    session_id=str(uuid4()),
    started_at=datetime.utcnow().isoformat(),
    mode="dry_run" if dry_run else "full",
)
self.db.create_session(session)
```

Update it with `finished_at`, `total_runs`, `successful_runs`, `failed_runs` when done.

---

## Error Recovery

- If a job fails (response is None), mark `is_error=1` in DB and **continue** — never halt the pipeline
- If the DB connection fails, retry 3 times with 1s delay before raising
- If a dataset file is missing, skip that dataset and warn (don't crash)
- Catch `KeyboardInterrupt` gracefully: finish the current batch, flush DB writes, print stats, exit cleanly

---

## Testing

Write `tests/test_runner.py`:

1. **Integration test (mocked)**: Create a `BenchmarkRunner` with mocked `dispatcher` and an in-memory SQLite DB. Run a dry-run with 2 questions for 1 model, 1 dataset, 1 budget. Verify 2 rows are inserted in the DB.

2. **Resumability test**: Pre-populate DB with 1 completed run. Verify the runner skips it and only runs the remaining questions.

3. **Error handling test**: Mock dispatcher to return `None`. Verify the run is inserted with `is_error=1` and the loop continues.

4. **Work queue test**: Verify that `_build_work_queue()` produces exactly `n_questions × n_models × n_budgets` jobs in dry-run mode (with 2 questions).

---

## Requirements

- The engine must be **fully resumable** — killing and restarting must not duplicate runs
- Never use `pandas` — use `polars` for all DataFrame operations
- Use `asyncio.Semaphore` for concurrency — not `ThreadPoolExecutor`
- All logging via `logging` module (not `print`) except for the rich progress display
- Checkpoint stats should be logged to a file `results/run_{session_id}.log`
- Ruff-compliant style

---

## Output Format

1. `src/benchmark/engine/runner.py` — complete module
2. `src/benchmark/engine/__main__.py` — CLI entry point
3. `tests/test_runner.py` — test suite
4. A brief explanation of the concurrency model and why `Semaphore(3)` is chosen
