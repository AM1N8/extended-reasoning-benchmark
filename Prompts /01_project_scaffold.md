# Prompt 01 — Project Scaffold & Tooling Configuration

## Role & Mission

You are a senior Python engineer setting up a **production-grade research repository** for a large-scale LLM benchmarking project. Your goal is to create the complete project scaffold: directory structure, tooling config files, and developer automation — before a single line of application code is written.

---

## GLOBAL CONTEXT

```
Project: Systematic benchmark of test-time compute (extended reasoning) in LLMs
Models: OpenAI o1, o3-mini, DeepSeek R1, Gemini 2.0 Flash Thinking + 2 baselines
Stack: Python 3.12+, uv, just, ruff, polars, sqlite3, httpx, matplotlib, pydantic-settings
```

---

## Task

Generate **every configuration file** and the **full directory tree** for this project. Do not write any application logic yet — only scaffolding.

---

## Directory Structure to Create

```
llm-reasoning-benchmark/
├── .env.example                  # API key template
├── .gitignore
├── .python-version               # "3.12"
├── justfile                      # All dev tasks
├── pyproject.toml                # uv + ruff + project metadata
├── README.md                     # Placeholder with project title
│
├── data/
│   ├── raw/                      # Downloaded dataset files (git-ignored)
│   └── processed/                # Standardized JSON datasets
│
├── db/
│   └── .gitkeep                  # benchmark.db goes here (git-ignored)
│
├── results/
│   ├── figures/                  # PNG plots
│   └── tables/                   # CSV exports
│
├── src/
│   └── benchmark/
│       ├── __init__.py
│       ├── config.py             # Pydantic settings
│       ├── database.py           # SQLite connection + schema
│       ├── datasets/
│       │   ├── __init__.py
│       │   └── loader.py
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── github_models.py
│       │   └── google_studio.py
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── runner.py
│       │   └── budget.py
│       ├── grading/
│       │   ├── __init__.py
│       │   ├── quantitative.py
│       │   └── qualitative.py
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── metrics.py
│       │   └── visualizations.py
│       └── report/
│           ├── __init__.py
│           └── cost_dashboard.py
│
└── tests/
    ├── conftest.py
    ├── test_clients.py
    ├── test_database.py
    └── test_metrics.py
```

---

## File 1: `pyproject.toml`

Generate a complete `pyproject.toml` using **uv** as the package manager and **ruff** as the linter/formatter. Requirements:

```toml
[project]
name = "llm-reasoning-benchmark"
version = "0.1.0"
requires-python = ">=3.12"

# Dependencies must include:
# - httpx[http2] (async API calls)
# - polars (data processing — NOT pandas)
# - matplotlib
# - seaborn
# - pydantic-settings
# - python-dotenv
# - tqdm
# - rich (for beautiful CLI output)

[tool.ruff]
# line-length = 100
# target-version = "py312"
# Enable: E, F, I, N, UP, B, SIM rules
# Format: double quotes, 4-space indent

[tool.ruff.lint]
# select the most important rule sets for a data science project

[tool.pytest.ini_options]
# testpaths = ["tests"]
# asyncio_mode = "auto"
```

---

## File 2: `justfile`

Generate a complete `justfile` (using `just` task runner syntax) with these recipes:

| Recipe | Description |
|---|---|
| `just install` | Run `uv sync` to install all dependencies |
| `just lint` | Run `ruff check src/ tests/` |
| `just format` | Run `ruff format src/ tests/` |
| `just test` | Run `pytest tests/ -v` |
| `just db-init` | Initialize the SQLite schema |
| `just dry-run` | Run 2 questions per category through the full pipeline |
| `just run` | Execute the full benchmark (all models, all datasets) |
| `just grade-quant` | Run quantitative LLM-as-Judge grading |
| `just grade-qual` | Run qualitative trace analysis |
| `just analyze` | Compute all metrics and export to CSV |
| `just plot` | Generate all visualizations |
| `just report` | Generate the cost dashboard table |
| `just clean` | Remove `db/benchmark.db` and `results/` contents |

The justfile must:
- Use `uv run python -m benchmark.xxx` pattern to run scripts
- Show a help message when running `just` with no args
- Include comments explaining each recipe

---

## File 3: `.env.example`

```env
# GitHub Models API (for OpenAI o1, o3-mini, DeepSeek R1)
GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_MODELS_ENDPOINT=https://models.inference.ai.azure.com

# Google AI Studio (for Gemini 2.0 Flash Thinking)
GOOGLE_AI_STUDIO_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxx

# Benchmark settings
DB_PATH=db/benchmark.db
DATA_DIR=data/processed
RESULTS_DIR=results
DRY_RUN_QUESTIONS=2
LOG_LEVEL=INFO
```

---

## File 4: `src/benchmark/config.py`

Generate a `pydantic-settings` `Settings` class that:
- Loads all values from `.env`
- Has typed fields for every key in `.env.example`
- Has a `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`
- Provides a `get_settings()` function with `@lru_cache` for singleton access

---

## File 5: `.gitignore`

Include ignores for:
- `.env` (never commit secrets)
- `db/*.db`
- `data/raw/`
- `results/figures/*.png`
- `results/tables/*.csv`
- Standard Python ignores (`__pycache__`, `.venv`, `*.egg-info`, `dist/`, `.pytest_cache/`)
- `.DS_Store`, `*.log`

---

## File 6: `README.md` (Placeholder)

Generate a README with:
- Project title and one-paragraph abstract (from the project charter)
- Badges: Python version, license, code style (ruff)
- Quick start section using `just` commands
- Section headers for: Overview, Methodology, Results (TBD), Repository Structure, License

---

## Requirements

- All Python files must have proper module docstrings
- `pyproject.toml` must be valid TOML — test mentally before outputting
- The `justfile` must use correct `just` syntax (not Makefile syntax)
- `config.py` must use `pydantic-settings` v2 API (not v1)
- Ensure `uv` is used everywhere — never reference `pip` or `poetry`
- All paths should be relative to the project root

---

## Output Format

Output each file as a separate fenced code block with the filename as the label. After all files, print the complete directory tree using ASCII art.
