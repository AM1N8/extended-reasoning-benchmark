"""SQLite database schema and operations for the LLM Reasoning Benchmark."""

import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class BenchmarkRun:
    """Represents a single execution of a benchmark question by a model."""

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


@dataclass
class DatasetRecord:
    """Represents a dataset registered in the system."""

    dataset_name: str
    task_category: str
    source_url: str
    num_questions: int


@dataclass
class RunSession:
    """Represents a benchmark execution session."""

    session_id: str
    started_at: str
    mode: str
    finished_at: str | None = None
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    notes: str | None = None


class DatabaseManager:
    """Manages SQLite database connections and CRUD operations."""

    def __init__(self, db_path: Path | str) -> None:
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._local = threading.local()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for thread-safe database connections.

        Yields:
            A sqlite3.Connection with row_factory set to sqlite3.Row.
        """
        if not hasattr(self._local, "connection"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.db_path,
                isolation_level=None,  # Autocommit mode
            )
            conn.row_factory = sqlite3.Row

            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON;")

            # Use Write-Ahead Logging for better concurrency
            conn.execute("PRAGMA journal_mode = WAL;")

            self._local.connection = conn

        try:
            yield self._local.connection
        except Exception:
            self._local.connection.rollback()
            raise
        else:
            if self._local.connection.in_transaction:
                self._local.connection.commit()

    def get_schema_version(self) -> int:
        """Read the current schema version from the database.

        Returns:
            The current schema version as an integer.
        """
        with self.get_connection() as conn:
            cursor = conn.execute("PRAGMA user_version;")
            return cursor.fetchone()[0]

    def _set_schema_version(self, version: int) -> None:
        """Set the schema version in the database."""
        with self.get_connection() as conn:
            conn.execute(f"PRAGMA user_version = {version};")

    def initialize(self) -> None:
        """Create tables and indexes if they don't exist, and run migrations."""
        with self.get_connection() as conn:
            # benchmark_runs table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    run_id          TEXT PRIMARY KEY,
                    created_at      TEXT NOT NULL,
                    
                    -- Identification
                    model           TEXT NOT NULL,
                    task_category   TEXT NOT NULL,
                    dataset_name    TEXT NOT NULL,
                    question_id     TEXT NOT NULL,
                    budget_level    INTEGER NOT NULL,
                    
                    -- Input
                    prompt          TEXT NOT NULL,
                    ground_truth    TEXT NOT NULL,
                    
                    -- Raw output
                    raw_trace       TEXT,
                    final_answer    TEXT,
                    
                    -- Token accounting
                    input_tokens    INTEGER,
                    reasoning_tokens INTEGER,
                    output_tokens   INTEGER,
                    total_tokens    INTEGER GENERATED ALWAYS AS (
                                        COALESCE(input_tokens, 0) + 
                                        COALESCE(reasoning_tokens, 0) + 
                                        COALESCE(output_tokens, 0)
                                    ) STORED,
                    
                    -- Performance
                    latency_seconds REAL,
                    
                    -- Grading
                    is_correct      INTEGER,
                    grader_rationale TEXT,
                    
                    -- Qualitative trace tags
                    strategy_tags   TEXT,
                    
                    -- Derived metric
                    efficiency_score REAL,
                    
                    -- Error tracking
                    error_message   TEXT,
                    is_error        INTEGER DEFAULT 0
                );
                """
            )

            # datasets_registry table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS datasets_registry (
                    dataset_name    TEXT PRIMARY KEY,
                    task_category   TEXT NOT NULL,
                    source_url      TEXT,
                    num_questions   INTEGER,
                    downloaded_at   TEXT,
                    processed_at    TEXT,
                    status          TEXT DEFAULT 'pending'
                );
                """
            )

            # run_sessions table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_sessions (
                    session_id      TEXT PRIMARY KEY,
                    started_at      TEXT NOT NULL,
                    finished_at     TEXT,
                    mode            TEXT NOT NULL,
                    total_runs      INTEGER DEFAULT 0,
                    successful_runs INTEGER DEFAULT 0,
                    failed_runs     INTEGER DEFAULT 0,
                    notes           TEXT
                );
                """
            )

            # Indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_runs_model ON benchmark_runs(model);",
                "CREATE INDEX IF NOT EXISTS idx_runs_category ON benchmark_runs(task_category);",
                "CREATE INDEX IF NOT EXISTS idx_runs_budget ON benchmark_runs(budget_level);",
                """CREATE INDEX IF NOT EXISTS idx_runs_model_category_budget 
                   ON benchmark_runs(model, task_category, budget_level);""",
                """CREATE INDEX IF NOT EXISTS idx_runs_ungraded 
                   ON benchmark_runs(is_correct) WHERE is_correct IS NULL;""",
                """CREATE INDEX IF NOT EXISTS idx_runs_with_traces 
                   ON benchmark_runs(model) WHERE raw_trace IS NOT NULL;""",
            ]
            for idx_sql in indexes:
                conn.execute(idx_sql)

        self.migrate()
        logger.info("Database initialized successfully.")

    def migrate(self) -> None:
        """Run any pending migrations."""
        current_version = self.get_schema_version()
        if current_version < SCHEMA_VERSION:
            logger.info("Migrating schema from %s to %s", current_version, SCHEMA_VERSION)
            # Add migration steps here as schema evolves
            self._set_schema_version(SCHEMA_VERSION)

    # ── Write Operations ──────────────────────────────────────────────

    def insert_run(self, run: BenchmarkRun) -> str:
        """Insert a single run into the database.

        Args:
            run: The BenchmarkRun instance to insert.

        Returns:
            The generated UUID4 string for the new run.
        """
        run_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()

        data = asdict(run)
        data["run_id"] = run_id
        data["created_at"] = created_at

        # Extract keys and values ensuring order matches
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = tuple(data.values())

        with self.get_connection() as conn:
            conn.execute(
                f"INSERT INTO benchmark_runs ({columns}) VALUES ({placeholders})",
                values,
            )

        return run_id

    def update_grading(self, run_id: str, is_correct: int, rationale: str) -> None:
        """Update grading fields for a run.

        Args:
            run_id: The ID of the run to update.
            is_correct: 1 if correct, 0 if wrong.
            rationale: Explanation from the LLM judge.
        """
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE benchmark_runs 
                SET is_correct = ?, grader_rationale = ? 
                WHERE run_id = ?
                """,
                (is_correct, rationale, run_id),
            )

    def update_strategy_tags(self, run_id: str, tags: dict[str, int]) -> None:
        """Update the strategy_tags JSON field for a run.

        Args:
            run_id: The ID of the run to update.
            tags: A dictionary of strategy tags (e.g., {"decomposition": 1}).
        """
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE benchmark_runs SET strategy_tags = ? WHERE run_id = ?",
                (json.dumps(tags), run_id),
            )

    def update_efficiency_score(self, run_id: str, score: float) -> None:
        """Update the derived efficiency_score for a run.

        Args:
            run_id: The ID of the run to update.
            score: The calculated efficiency score.
        """
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE benchmark_runs SET efficiency_score = ? WHERE run_id = ?",
                (score, run_id),
            )

    def upsert_dataset(self, dataset: DatasetRecord) -> None:
        """Insert or update a dataset registry entry.

        Args:
            dataset: The DatasetRecord to insert or update.
        """
        data = asdict(dataset)
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)

        # Create EXCLUDED updates for ON CONFLICT DO UPDATE
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in data.keys() if k != "dataset_name")

        sql = f"""
            INSERT INTO datasets_registry ({columns}) 
            VALUES ({placeholders})
            ON CONFLICT(dataset_name) DO UPDATE SET {updates};
        """

        with self.get_connection() as conn:
            conn.execute(sql, tuple(data.values()))

    def create_session(self, session: RunSession) -> None:
        """Create a new run session record."""
        data = asdict(session)
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        with self.get_connection() as conn:
            conn.execute(
                f"INSERT INTO run_sessions ({columns}) VALUES ({placeholders})",
                tuple(data.values()),
            )

    def update_session(
        self,
        session_id: str,
        finished_at: str,
        total_runs: int,
        successful_runs: int,
        failed_runs: int,
    ) -> None:
        """Update a run session record when finished."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE run_sessions 
                SET finished_at = ?, total_runs = ?, successful_runs = ?, failed_runs = ?
                WHERE session_id = ?
                """,
                (finished_at, total_runs, successful_runs, failed_runs, session_id),
            )

    # ── Read Operations ───────────────────────────────────────────────

    def _query_to_df(self, sql: str, params: tuple = ()) -> pl.DataFrame:
        """Execute a query and return results as a Polars DataFrame.

        Args:
            sql: The SQL query to execute.
            params: Parameters to substitute in the query.

        Returns:
            A Polars DataFrame containing the results.
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            if not cursor.description:
                return pl.DataFrame()

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            # SQLite returns Rows, convert to tuples
            row_tuples = [tuple(row) for row in rows]

            if not row_tuples:
                # Return empty DF with correct schema
                return pl.DataFrame(schema=columns)

            return pl.DataFrame(row_tuples, schema=columns, orient="row")

    def get_runs(self, filters: dict[str, Any] | None = None) -> pl.DataFrame:
        """Get runs matching the optional filters.

        Args:
            filters: Dictionary of column to value mappings to filter by.

        Returns:
            A Polars DataFrame with the matching runs.
        """
        sql = "SELECT * FROM benchmark_runs"
        params: list[Any] = []

        if filters:
            conditions = []
            for k, v in filters.items():
                if v is None:
                    conditions.append(f"{k} IS NULL")
                else:
                    conditions.append(f"{k} = ?")
                    params.append(v)
            sql += " WHERE " + " AND ".join(conditions)

        return self._query_to_df(sql, tuple(params))

    def get_ungraded_runs(self) -> pl.DataFrame:
        """Get all runs where is_correct IS NULL and is_error=0.

        Returns:
            A Polars DataFrame with ungraded runs.
        """
        sql = "SELECT * FROM benchmark_runs WHERE is_correct IS NULL AND is_error = 0"
        return self._query_to_df(sql)

    def get_runs_with_traces(self) -> pl.DataFrame:
        """Get all runs where raw_trace IS NOT NULL.

        Returns:
            A Polars DataFrame with runs containing raw traces.
        """
        sql = "SELECT * FROM benchmark_runs WHERE raw_trace IS NOT NULL"
        return self._query_to_df(sql)

    def get_summary_stats(self) -> pl.DataFrame:
        """Calculate summary statistics grouped by model, category, and budget.

        Returns:
            A Polars DataFrame with aggregated statistics.
        """
        sql = """
            SELECT 
                model, 
                task_category, 
                budget_level,
                COUNT(*) as run_count,
                AVG(is_correct) as accuracy,
                AVG(total_tokens) as avg_tokens,
                AVG(latency_seconds) as avg_latency
            FROM benchmark_runs
            WHERE is_error = 0 AND is_correct IS NOT NULL
            GROUP BY model, task_category, budget_level
            ORDER BY model, task_category, budget_level
        """
        return self._query_to_df(sql)


if __name__ == "__main__":
    from benchmark.config import get_settings

    logging.basicConfig(level=logging.INFO)

    settings = get_settings()
    db = DatabaseManager(settings.db_path)
    db.initialize()
    print(f"✅ Database initialized at {settings.db_path}")
