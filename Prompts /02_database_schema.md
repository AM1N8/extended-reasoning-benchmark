# Prompt 02 — Database Schema & SQLite Infrastructure

## Role & Mission

You are a data engineer designing the **SQLite persistence layer** for a large-scale LLM benchmark. You will write the complete `src/benchmark/database.py` module: schema definition, connection management, all CRUD operations, and migration logic.

---

## GLOBAL CONTEXT

```
Project: Systematic benchmark of test-time compute (extended reasoning) in LLMs
Models: OpenAI o1, o3-mini, DeepSeek R1, Gemini 2.0 Flash Thinking + 2 baselines (GPT-4o, Claude 3.5 Sonnet)
Task categories: 12 (see full list below)
Reasoning budgets: 5 levels (L1–L5)
Stack: Python 3.12+, sqlite3 (stdlib), polars for queries
DB location: configured via Settings.db_path
```

---

## Schema Design

### Table: `benchmark_runs`

This is the **core fact table** — one row per (model × question × budget_level) execution.

```sql
CREATE TABLE benchmark_runs (
    run_id          TEXT PRIMARY KEY,          -- UUID4
    created_at      TEXT NOT NULL,             -- ISO-8601 UTC timestamp
    
    -- Identification
    model           TEXT NOT NULL,             -- e.g. "openai/o1", "deepseek/r1"
    task_category   TEXT NOT NULL,             -- e.g. "MATH", "HumanEval"
    dataset_name    TEXT NOT NULL,             -- e.g. "gsm8k", "math_500"
    question_id     TEXT NOT NULL,             -- Original dataset question ID
    budget_level    INTEGER NOT NULL,          -- 1 to 5
    
    -- Input
    prompt          TEXT NOT NULL,             -- Full prompt sent to model
    ground_truth    TEXT NOT NULL,             -- Expected answer
    
    -- Raw output
    raw_trace       TEXT,                      -- Full <think>...</think> content (if exposed)
    final_answer    TEXT,                      -- Extracted final answer
    
    -- Token accounting
    input_tokens    INTEGER,
    reasoning_tokens INTEGER,                  -- Tokens in the thinking trace
    output_tokens   INTEGER,
    total_tokens    INTEGER GENERATED ALWAYS AS (
                        COALESCE(input_tokens,0) + 
                        COALESCE(reasoning_tokens,0) + 
                        COALESCE(output_tokens,0)
                    ) STORED,
    
    -- Performance
    latency_seconds REAL,
    
    -- Grading (populated by grading pipeline)
    is_correct      INTEGER,                   -- 1=correct, 0=wrong, NULL=ungraded
    grader_rationale TEXT,                     -- LLM judge explanation
    
    -- Qualitative trace tags (JSON, populated by qual grading pipeline)
    strategy_tags   TEXT,                      -- JSON: {"decomposition":1,"backtracking":0,...}
    
    -- Derived metric (populated by analysis pipeline)
    efficiency_score REAL,                     -- (is_correct / reasoning_tokens) * 1000
    
    -- Error tracking
    error_message   TEXT,                      -- NULL if successful
    is_error        INTEGER DEFAULT 0          -- 1 if API call failed
);
```

### Table: `datasets_registry`

Track which datasets have been downloaded and processed.

```sql
CREATE TABLE datasets_registry (
    dataset_name    TEXT PRIMARY KEY,
    task_category   TEXT NOT NULL,
    source_url      TEXT,
    num_questions   INTEGER,
    downloaded_at   TEXT,
    processed_at    TEXT,
    status          TEXT DEFAULT 'pending'    -- pending | downloaded | processed | error
);
```

### Table: `run_sessions`

Track each benchmark execution session (for dry-run vs full-run distinction).

```sql
CREATE TABLE run_sessions (
    session_id      TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    mode            TEXT NOT NULL,            -- 'dry_run' | 'full'
    total_runs      INTEGER DEFAULT 0,
    successful_runs INTEGER DEFAULT 0,
    failed_runs     INTEGER DEFAULT 0,
    notes           TEXT
);
```

---

## Indexes Required

```sql
-- Frequent query patterns:
CREATE INDEX idx_runs_model ON benchmark_runs(model);
CREATE INDEX idx_runs_category ON benchmark_runs(task_category);
CREATE INDEX idx_runs_budget ON benchmark_runs(budget_level);
CREATE INDEX idx_runs_model_category_budget ON benchmark_runs(model, task_category, budget_level);
CREATE INDEX idx_runs_ungraded ON benchmark_runs(is_correct) WHERE is_correct IS NULL;
CREATE INDEX idx_runs_with_traces ON benchmark_runs(model) WHERE raw_trace IS NOT NULL;
```

---

## Module to Generate: `src/benchmark/database.py`

### Requirements

Generate a complete, production-ready module with:

**1. `DatabaseManager` class**
- `__init__(self, db_path: Path)` — takes path from `Settings`
- `initialize()` — creates all tables and indexes if they don't exist (idempotent)
- Uses a context manager pattern for connections: `with self.get_connection() as conn:`
- Thread-safe via `threading.local()` for connection storage
- Enables WAL mode (`PRAGMA journal_mode=WAL`) for concurrent reads
- Enables foreign keys (`PRAGMA foreign_keys=ON`)

**2. Write operations**
```python
def insert_run(self, run: BenchmarkRun) -> str:
    """Insert a single run, return run_id."""

def update_grading(self, run_id: str, is_correct: int, rationale: str) -> None:
    """Update is_correct and grader_rationale for a run."""

def update_strategy_tags(self, run_id: str, tags: dict[str, int]) -> None:
    """Update strategy_tags JSON field."""

def update_efficiency_score(self, run_id: str, score: float) -> None:
    """Update the derived efficiency_score."""

def upsert_dataset(self, dataset: DatasetRecord) -> None:
    """Insert or update a dataset registry entry."""
```

**3. Read operations (return `polars.DataFrame`)**
```python
def get_runs(self, filters: dict | None = None) -> pl.DataFrame:
    """Flexible query: filter by model, category, budget, is_correct."""

def get_ungraded_runs(self) -> pl.DataFrame:
    """All runs where is_correct IS NULL and is_error=0."""

def get_runs_with_traces(self) -> pl.DataFrame:
    """All runs where raw_trace IS NOT NULL."""

def get_summary_stats(self) -> pl.DataFrame:
    """GROUP BY model, task_category, budget_level aggregates."""
```

**4. Dataclasses / typed models**

Define Python dataclasses (not SQLAlchemy models) for:

```python
@dataclass
class BenchmarkRun:
    model: str
    task_category: str
    dataset_name: str
    question_id: str
    budget_level: int
    prompt: str
    ground_truth: str
    raw_trace: str | None = None
    final_answer: str | None = None
    input_tokens: int | None = None
    reasoning_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float | None = None
    error_message: str | None = None
    is_error: int = 0
    # run_id and created_at are auto-generated

@dataclass  
class DatasetRecord:
    dataset_name: str
    task_category: str
    source_url: str
    num_questions: int
```

**5. Migration system**

```python
SCHEMA_VERSION = 1

def get_schema_version(self) -> int:
    """Read current schema version from user_version PRAGMA."""

def migrate(self) -> None:
    """Run any pending migrations. Called automatically in initialize()."""
```

---

## Polars Query Pattern

When reading from SQLite into Polars, use this pattern:

```python
import polars as pl
import sqlite3

def _query_to_df(self, sql: str, params: tuple = ()) -> pl.DataFrame:
    with self.get_connection() as conn:
        cursor = conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    return pl.DataFrame(rows, schema=columns, orient="row")
```

---

## CLI Entry Point

Add a `__main__` block so `uv run python -m benchmark.database` initializes the DB:

```python
if __name__ == "__main__":
    from benchmark.config import get_settings
    settings = get_settings()
    db = DatabaseManager(settings.db_path)
    db.initialize()
    print(f"✅ Database initialized at {settings.db_path}")
```

---

## Requirements

- All functions must have **type hints** and **docstrings**
- Use `uuid.uuid4()` for `run_id` generation
- Use `datetime.utcnow().isoformat()` for timestamps
- **Never use pandas** — all DataFrame returns must be `polars.DataFrame`
- Use `ruff`-compatible style: double quotes, 100 char line limit
- Include `logging` at module level with `logger = logging.getLogger(__name__)`
- Write 3 unit tests in `tests/test_database.py` covering: insert + read, update grading, get_summary_stats
- The module must be importable with no side effects

---

## Output Format

1. Full `src/benchmark/database.py` in a fenced code block
2. Full `tests/test_database.py` in a fenced code block
3. A brief explanation of any non-obvious design decisions (e.g. WAL mode rationale, thread safety approach)
