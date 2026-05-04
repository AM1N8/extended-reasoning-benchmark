"""Shared test fixtures for the benchmark test suite."""

import pytest

from benchmark.config import Settings


@pytest.fixture()
def settings() -> Settings:
    """Return a test Settings instance with safe defaults."""
    return Settings(
        github_pat="test-pat-xxxx",
        google_ai_studio_key="test-key-xxxx",
        db_path="db/test_benchmark.db",
        data_dir="data/processed",
        results_dir="results",
        log_level="DEBUG",
    )
