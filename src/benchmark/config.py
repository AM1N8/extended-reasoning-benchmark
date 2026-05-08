"""Pydantic-settings configuration — loads all env vars from .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All values can be overridden via a `.env` file at the project root
    or via actual environment variables (which take precedence).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── GitHub Models API (OpenAI o1, o3-mini, DeepSeek R1) ──────────
    github_pat: str = ""
    github_models_endpoint: str = "https://models.inference.ai.azure.com"

    # ── Google AI Studio (Gemini 2.5 Flash) ──────────────────────────
    google_ai_studio_key: str = ""

    # ── Groq API ─────────────────────────────────────────────────────
    groq_api_key: str = ""

    # ── Benchmark Settings ───────────────────────────────────────────
    db_path: Path = Path("db/benchmark.db")
    data_dir: Path = Path("data/processed")
    results_dir: Path = Path("results")
    dry_run_questions: int = 2
    log_level: str = "INFO"
    grader_model: str = "groq/llama-3.3-70b-versatile"  # Default grader, can be overriden via .env

    # ── Derived paths ────────────────────────────────────────────────
    @property
    def figures_dir(self) -> Path:
        """Path to the figures output directory."""
        return self.results_dir / "figures"

    @property
    def tables_dir(self) -> Path:
        """Path to the tables output directory."""
        return self.results_dir / "tables"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
