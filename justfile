# LLM Reasoning Benchmark — Task Runner
# Run `just` to see all available commands

default:
    @just --list

# ─── Setup ───────────────────────────────────────────────────────────────────

# Install all dependencies
install:
    uv sync

# ─── Code Quality ─────────────────────────────────────────────────────────────

# Lint code
lint:
    uv run ruff check src/ tests/

# Format code
format:
    uv run ruff format src/ tests/

# Fix lint issues automatically
fix:
    uv run ruff check --fix src/ tests/

# ─── Testing ──────────────────────────────────────────────────────────────────

# Run all tests
test *args:
    uv run pytest {{args}}

# Run tests with coverage
test-cov:
    uv run pytest tests/ --cov=src/benchmark --cov-report=term-missing

# ─── Database ─────────────────────────────────────────────────────────────────

# Initialize/migrate SQLite database
db-init:
    uv run python -m benchmark.database

# Show DB stats
db-stats:
    uv run python -c "from benchmark.config import get_settings; from benchmark.database import DatabaseManager; db = DatabaseManager(get_settings().db_path); df = db.get_summary_stats(); print(df)"

# ─── Data ─────────────────────────────────────────────────────────────────────

# Download and process all 12 datasets
download-datasets:
    uv run python -m benchmark.datasets

# Download a specific dataset
download-dataset dataset:
    uv run python -m benchmark.datasets --dataset {{dataset}}

# ─── Benchmark ────────────────────────────────────────────────────────────────

# Dry run: 2 questions per dataset (validate pipeline)
dry-run:
    uv run python -m benchmark.engine --dry-run

# Full benchmark run (resume by default)
run:
    uv run python -m benchmark.engine

# Run specific models/datasets/budgets
run-custom models datasets budgets:
    uv run python -m benchmark.engine \
        --models {{models}} \
        --datasets {{datasets}} \
        --budgets {{budgets}}

# ─── Grading ──────────────────────────────────────────────────────────────────

# Quantitative (correctness) grading
grade-quant:
    uv run python -m benchmark.grading --mode quant

# Qualitative (strategy) trace analysis
grade-qual:
    uv run python -m benchmark.grading --mode qual

# Both grading passes
grade-all:
    uv run python -m benchmark.grading --mode both

# ─── Analysis ─────────────────────────────────────────────────────────────────

# Compute all metrics, export CSVs
analyze:
    uv run python -m benchmark.analysis

# Generate all 6 visualizations
plot:
    uv run python -m benchmark.analysis --plot-only

# Generate cost dashboard + enterprise report
report:
    uv run python -m benchmark.report

# ─── Cleanup ──────────────────────────────────────────────────────────────────

# Remove DB and results (keep raw data)
clean:
    rm -f db/benchmark.db
    rm -f results/figures/*.png
    rm -f results/tables/*.csv
    rm -f results/*.md
    @echo "✓ Cleaned DB and results"

# Remove everything including downloaded data
clean-all: clean
    rm -rf data/raw/
    rm -rf data/processed/
    @echo "✓ Also removed downloaded data"
