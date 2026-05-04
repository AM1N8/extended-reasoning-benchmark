# Prompt 03 — Dataset Download & Processing Pipeline

## Role & Mission

You are a data engineer building the **dataset ingestion layer** for an LLM benchmark. You will create the full pipeline to download, normalize, and store 12 task categories of evaluation questions into a standardized JSON format.

---

## GLOBAL CONTEXT

```
Project: Systematic benchmark of test-time compute (extended reasoning) in LLMs
Stack: Python 3.12+, uv, polars, httpx
Output format: Standardized local JSON files in data/processed/{category}/{dataset_name}.json
Questions per dataset: 50–100 (configurable)
```

---

## The 12 Task Categories

| # | Category | Dataset | Source | Difficulty |
|---|---|---|---|---|
| 1 | Mathematical Reasoning | `math_500` | HendrycksTest/MATH (500 subset) | Hard |
| 2 | Arithmetic Word Problems | `gsm8k` | openai/gsm8k | Medium |
| 3 | Code Generation | `humaneval` | openai/HumanEval | Hard |
| 4 | Code Debugging | `mbpp` | google-research-datasets/mbpp | Medium |
| 5 | Logical Deduction | `logic_grid` | Custom / BIG-Bench logical-deduction | Hard |
| 6 | Causal Reasoning | `cause_effect` | BIG-Bench cause-and-effect | Medium |
| 7 | Multi-step Planning | `alfworld_plans` | Custom subset from ALFWorld | Hard |
| 8 | Scientific QA | `arc_challenge` | allenai/ai2_arc (challenge split) | Hard |
| 9 | Common Sense | `hellaswag` | Rowan/hellaswag | Medium |
| 10 | Reading Comprehension | `drop` | ucinlp/drop | Medium |
| 11 | Symbolic Manipulation | `bbh_word_sorting` | lukaemon/bbh (word_sorting) | Hard |
| 12 | Analogical Reasoning | `bbh_analogies` | lukaemon/bbh (reasoning_about_colored_objects) | Medium |

---

## Standardized Output Schema

Every dataset must be normalized to this JSON format:

```json
{
  "dataset_name": "gsm8k",
  "task_category": "Arithmetic Word Problems",
  "source": "openai/gsm8k",
  "num_questions": 100,
  "created_at": "2025-01-01T00:00:00Z",
  "questions": [
    {
      "question_id": "gsm8k_0001",
      "prompt": "Janet's ducks lay 16 eggs per day...",
      "ground_truth": "18",
      "answer_type": "numeric",
      "difficulty": "medium",
      "metadata": {
        "original_id": "...",
        "source_split": "test"
      }
    }
  ]
}
```

### `answer_type` values:
- `"numeric"` — exact number (GSM8K, MATH)
- `"code"` — runnable Python function (HumanEval, MBPP)
- `"multiple_choice"` — A/B/C/D (ARC, HellaSwag)
- `"free_text"` — natural language answer (DROP, planning)
- `"structured"` — JSON object (BBH tasks)

---

## Module to Generate: `src/benchmark/datasets/loader.py`

### Architecture

```
DatasetLoader (abstract base)
├── HuggingFaceLoader       ← Downloads from HF Hub via datasets lib or HTTP
├── BBHLoader               ← Handles BIG-Bench Hard format
└── CustomLoader            ← For hand-crafted logic grid / planning tasks
```

### Core Functions

**1. Main entry point**

```python
def load_all_datasets(
    output_dir: Path,
    questions_per_dataset: int = 100,
    categories: list[str] | None = None,  # None = all 12
    force_refresh: bool = False,
) -> dict[str, Path]:
    """
    Download and process all 12 datasets.
    Returns mapping of dataset_name -> output JSON path.
    Shows a rich progress bar per dataset.
    Skips already-processed datasets unless force_refresh=True.
    """
```

**2. Per-dataset loaders**

For each of the 12 datasets, write a dedicated function:

```python
def load_gsm8k(output_path: Path, n: int = 100) -> StandardDataset:
    """
    Load GSM8K from HuggingFace datasets library.
    Selects the last n items from the test split.
    Normalizes answers: strip '#### ' prefix, keep numeric string.
    """

def load_math500(output_path: Path, n: int = 100) -> StandardDataset:
    """
    Load MATH dataset, sample n questions stratified by difficulty level.
    Ground truth: the boxed answer string (e.g. '\\frac{1}{2}').
    """

def load_humaneval(output_path: Path, n: int = 50) -> StandardDataset:
    """
    Load HumanEval. Ground truth is the canonical test suite as a string.
    Prompt = function signature + docstring only (no solution).
    """
# ... and so on for all 12
```

**3. Validation**

```python
def validate_dataset(dataset: StandardDataset) -> list[str]:
    """
    Validate a standardized dataset. Returns list of validation errors.
    Checks:
    - All required fields present
    - question_ids are unique
    - ground_truth is non-empty for all questions
    - answer_type is a known value
    """
```

---

## Dataclass Definitions

```python
@dataclass
class Question:
    question_id: str
    prompt: str
    ground_truth: str
    answer_type: Literal["numeric", "code", "multiple_choice", "free_text", "structured"]
    difficulty: Literal["easy", "medium", "hard"]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class StandardDataset:
    dataset_name: str
    task_category: str
    source: str
    questions: list[Question]
    
    def to_json(self) -> dict:
        """Serialize to the standardized output schema."""
    
    def save(self, path: Path) -> None:
        """Write to JSON file, creating parent dirs as needed."""
    
    @classmethod
    def load(cls, path: Path) -> "StandardDataset":
        """Load and deserialize from JSON file."""
```

---

## Prompt Engineering for Each Category

For each dataset, define the **prompt template** that wraps the raw question text before sending to models. The template must:
- Be category-specific (code prompts differ from math prompts)
- NOT leak the answer format (no "Answer: " prefix that biases the model)
- Include a clear task description

Examples:

```python
PROMPT_TEMPLATES = {
    "gsm8k": """Solve the following math word problem step by step.

Problem: {question}

Provide your final numerical answer after your reasoning.""",

    "humaneval": """Complete the following Python function. Write only the function body.

{question}

Your implementation:""",

    "arc_challenge": """Answer the following multiple choice science question.

{question}

Choose the best answer from the options provided.""",
    
    # ... all 12 templates
}
```

---

## CLI Entry Point

```python
# src/benchmark/datasets/__main__.py
# Run with: uv run python -m benchmark.datasets
# Shows rich progress, validates all datasets, prints summary table
```

---

## Error Handling

- Wrap each dataset download in try/except with clear error messages
- If a HuggingFace dataset is unavailable, generate **synthetic fallback questions** (5 per category) so the pipeline can be tested without internet access
- Log all download failures with `logger.warning()`
- Never crash the entire pipeline for one failed dataset

---

## Testing

Write `tests/test_datasets.py` with:
1. Test that `validate_dataset()` catches missing ground_truth
2. Test that `StandardDataset.to_json()` produces valid schema
3. Test prompt template rendering with special characters
4. Mock test that `load_gsm8k()` returns correct `answer_type = "numeric"`

---

## Requirements

- Use `httpx` for any direct HTTP downloads (not `requests`)
- Use `polars` if any tabular processing of downloaded data is needed
- All file I/O uses `pathlib.Path` (never `os.path`)
- Use `rich.progress` for download progress bars
- Ruff-compatible style throughout
- Every function has type hints and docstring with Args/Returns sections

---

## Output Format

1. `src/benchmark/datasets/loader.py` — complete module
2. `src/benchmark/datasets/__main__.py` — CLI entry point
3. `tests/test_datasets.py` — unit tests
4. A markdown table showing: dataset name, source URL, # questions, answer_type, difficulty distribution
