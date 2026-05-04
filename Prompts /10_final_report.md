# Prompt 10 — Final Synthesis, README & Repository Polish

## Role & Mission

You are a technical writer and developer advocate writing the **final README, methodology documentation, and repository polish** for a published research benchmark. This prompt assumes all code and analysis is complete — you are synthesizing findings and making the repository presentable for GitHub publication.

---

## GLOBAL CONTEXT

```
Project: Systematic analysis of test-time compute scaling in LLMs
Hypothesis confirmed: Non-linear diminishing returns at budget L3–L4
Key finding: Reasoning Efficiency metric reveals "value per token" clearly
Stack published: Python 3.12, uv, just, ruff, polars, sqlite3, httpx
Audience: ML engineers, applied researchers, cost-sensitive production teams
```

---

## Task 1: Complete `README.md`

Write a **production-quality README** for GitHub. Requirements:

### Header Section
- Project title with emoji: `🧠 LLM Extended Reasoning Benchmark`
- One-paragraph abstract (adapt from the project charter abstract)
- Badges:
  ```markdown
  ![Python](https://img.shields.io/badge/python-3.12+-blue)
  ![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
  ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
  ```

### Sections Required

**1. 🔬 Research Questions**
List the 3 core hypotheses being tested (non-linear returns, strategy effectiveness, cost ROI).

**2. 📊 Key Findings** *(fill with realistic placeholder results)*
Write as if the benchmark ran successfully:
- "Extended reasoning provides substantial gains for tasks requiring 3–7 deductive steps, with accuracy improvements of 15–28% over baselines"
- "Beyond budget level L3, marginal gains drop below 2% for 8 of 12 task categories"
- "DeepSeek R1 achieves the highest reasoning efficiency score (X.X pts per 1,000 tokens) across mathematical tasks"
- Include a small markdown table: top 5 (model, budget, category, efficiency_score)

**3. 🏗️ Architecture**

```
┌─────────────────────────────────────────────────────────┐
│                    Benchmark Pipeline                   │
│                                                         │
│  Dataset Layer        API Layer          Analysis       │
│  ┌───────────┐   →   ┌──────────────┐  →  ┌─────────┐ │
│  │ 12 datasets│       │ GitHub Models│     │Metrics  │ │
│  │ 50-100 q  │       │ Google Studio│     │Plots    │ │
│  │ 5 formats │       │ Rate Limiter │     │Reports  │ │
│  └───────────┘       └──────────────┘     └─────────┘ │
│         ↓                   ↓                   ↓      │
│  ┌─────────────────────────────────────────────────┐   │
│  │              SQLite Database                    │   │
│  │  benchmark_runs (18,000–36,000 rows)           │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**4. ⚡ Quick Start**

```bash
# 1. Clone and install
git clone https://github.com/USERNAME/llm-reasoning-benchmark
cd llm-reasoning-benchmark
uv sync

# 2. Configure API keys
cp .env.example .env
# Edit .env with your GitHub PAT and Google AI Studio key

# 3. Download datasets
just download-datasets

# 4. Dry run (validates pipeline, ~5 minutes)
just dry-run

# 5. Full benchmark (run overnight)
just run

# 6. Grade + analyze + visualize
just grade-quant
just grade-qual
just analyze
just plot

# 7. Generate enterprise report
just report
```

**5. 📁 Repository Structure**

ASCII directory tree with a one-line description of each file/module.

**6. 🧪 Running Tests**

```bash
just test                # All tests
just test tests/test_clients.py  # Specific module
```

**7. 📈 Reproducing Results**

Step-by-step instructions for a researcher to reproduce the exact benchmark:
- API access requirements (GitHub Student Pack, Google AI Studio free tier)
- Estimated time: ~18 hours on free tier rate limits
- Estimated tokens consumed: ~50M reasoning tokens total
- Storage: ~2GB for the SQLite database

**8. 🔧 Extending the Benchmark**

How to:
- Add a new model (implement `BaseLLMClient`, register in dispatcher)
- Add a new dataset (implement loader, add to `DATASET_REGISTRY`)
- Add a new reasoning strategy tag (update `REASONING_STRATEGIES` dict and judge prompt)

**9. 📝 Citation**

BibTeX placeholder.

**10. 📄 License**

MIT.

---

## Task 2: `METHODOLOGY.md`

Write a detailed methodology document (1,500–2,000 words) covering:

**Section 1: Experimental Design**
- The matrix: 6 models × 12 datasets × 5 budget levels
- Why these models were chosen (coverage of different reasoning approaches)
- Why these 12 task categories (cognitive diversity)

**Section 2: Budget Level Definitions**
- Precise definition of each L1–L5 level per model family
- The L5 system injection prompt verbatim

**Section 3: The Reasoning Efficiency Metric**
- Mathematical definition with LaTeX: `$E = \frac{A \times 1000}{T_r}$`
- Interpretation guide
- Limitations (doesn't account for latency, only tokens)

**Section 4: Grading Methodology**
- Priority order: rule-based → LLM judge
- LLM judge model choice (why Gemini Flash: fast + cheap + reliable JSON)
- Grading accuracy estimate (human validation on 100-sample subset)

**Section 5: Qualitative Trace Analysis**
- The 5 strategy definitions with examples from actual traces
- Limitations of automated strategy detection

**Section 6: Cost Simulation**
- Pricing sources and date
- GitHub Models vs production pricing distinction
- What "cost per correct answer" captures

---

## Task 3: Code Quality Pass

For the entire codebase, produce a **ruff compliance checklist** and any needed fixes:

```bash
# Commands the developer should run:
just format   # auto-fix formatting
just lint     # check remaining issues
```

Generate a `ruff.toml` or update `pyproject.toml` `[tool.ruff]` section with:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # Pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "ANN",  # flake8-annotations (type hints)
    "PTH",  # flake8-use-pathlib (enforce pathlib over os.path)
    "RUF",  # Ruff-specific rules
]
ignore = [
    "ANN101",  # Missing type annotation for self
    "ANN102",  # Missing type annotation for cls
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["ANN"]  # Don't require annotations in tests

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

---

## Task 4: `justfile` — Final Complete Version

Produce the **final, complete justfile** with all recipes, including the ones added during development:

```just
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
test:
    uv run pytest tests/ -v

# Run tests with coverage
test-cov:
    uv run pytest tests/ --cov=src/benchmark --cov-report=term-missing

# ─── Database ─────────────────────────────────────────────────────────────────

# Initialize/migrate SQLite database
db-init:
    uv run python -m benchmark.database

# Show DB stats
db-stats:
    uv run python -c "
from benchmark.config import get_settings
from benchmark.database import DatabaseManager
db = DatabaseManager(get_settings().db_path)
df = db.get_summary_stats()
print(df)
"

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
```

---

## Task 5: `CONTRIBUTING.md`

Write a brief contributing guide:
- How to add a new model
- How to add a new dataset  
- Test requirements for PRs
- Ruff style requirements

---

## Output Format

1. Complete `README.md`
2. Complete `METHODOLOGY.md`
3. Final `pyproject.toml` `[tool.ruff]` section
4. Final complete `justfile`
5. `CONTRIBUTING.md`
6. A `CHECKLIST.md` the developer can use to verify everything is ready for GitHub publication:
   - [ ] `.env` is NOT committed (check `.gitignore`)
   - [ ] All tests pass (`just test`)
   - [ ] No ruff errors (`just lint`)
   - [ ] README has real results (not placeholders)
   - [ ] All figure PNGs are in `results/figures/`
   - [ ] `enterprise_guide.md` is complete
   - [ ] Database is NOT committed (check `.gitignore`)
   - [ ] `uv.lock` IS committed (reproducibility)
