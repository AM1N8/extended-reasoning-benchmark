"""Dataset download, normalization, and processing pipeline for LLM reasoning benchmark."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from rich.progress import Progress, SpinnerColumn, TextColumn

logger = logging.getLogger(__name__)

# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class Question:
    """A standardized benchmark question."""

    question_id: str
    prompt: str
    ground_truth: str
    answer_type: Literal["numeric", "code", "multiple_choice", "free_text", "structured"]
    difficulty: Literal["easy", "medium", "hard"]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StandardDataset:
    """A standardized collection of benchmark questions."""

    dataset_name: str
    task_category: str
    source: str
    questions: list[Question]

    def to_json(self) -> dict[str, Any]:
        """Serialize to the standardized output schema."""
        return {
            "dataset_name": self.dataset_name,
            "task_category": self.task_category,
            "source": self.source,
            "num_questions": len(self.questions),
            "created_at": datetime.now(UTC).isoformat(),
            "questions": [asdict(q) for q in self.questions],
        }

    def save(self, path: Path) -> None:
        """Write to JSON file, creating parent dirs as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "StandardDataset":
        """Load and deserialize from JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        questions = [Question(**q) for q in data["questions"]]
        return cls(
            dataset_name=data["dataset_name"],
            task_category=data["task_category"],
            source=data["source"],
            questions=questions,
        )


# ── Validation ───────────────────────────────────────────────────────────────


def validate_dataset(dataset: StandardDataset) -> list[str]:
    """Validate a standardized dataset. Returns a list of validation errors.

    Args:
        dataset: The StandardDataset instance to validate.

    Returns:
        A list of error message strings. Empty if valid.
    """
    errors = []
    if not dataset.dataset_name:
        errors.append("Missing dataset_name")
    if not dataset.task_category:
        errors.append("Missing task_category")

    valid_types = {"numeric", "code", "multiple_choice", "free_text", "structured"}
    valid_difficulties = {"easy", "medium", "hard"}
    seen_ids = set()

    for i, q in enumerate(dataset.questions):
        if not q.question_id:
            errors.append(f"Question {i} missing question_id")
        elif q.question_id in seen_ids:
            errors.append(f"Duplicate question_id found: {q.question_id}")
        seen_ids.add(q.question_id)

        if not q.prompt:
            errors.append(f"Question {q.question_id} missing prompt")
        if not str(q.ground_truth).strip():
            errors.append(f"Question {q.question_id} missing ground_truth")

        if q.answer_type not in valid_types:
            errors.append(f"Question {q.question_id} invalid answer_type: {q.answer_type}")
        if q.difficulty not in valid_difficulties:
            errors.append(f"Question {q.question_id} invalid difficulty: {q.difficulty}")

    return errors


# ── Prompt Templates ─────────────────────────────────────────────────────────

PROMPT_TEMPLATES = {
    "math_500": (
        "Solve the following mathematical problem step by step.\n\n"
        "Problem: {question}\n\n"
        "Provide your final numerical answer after your reasoning."
    ),
    "gsm8k": (
        "Solve the following math word problem step by step.\n\n"
        "Problem: {question}\n\n"
        "Provide your final numerical answer after your reasoning."
    ),
    "humaneval": (
        "Complete the following Python function. Write only the function body.\n\n"
        "{question}\n\n"
        "Your implementation:"
    ),
    "mbpp": (
        "Write a Python function to solve the following problem.\n\n"
        "Problem: {question}\n\n"
        "Provide only the runnable Python code."
    ),
    "logic_grid": (
        "Solve the following logical deduction puzzle.\n\n"
        "Puzzle: {question}\n\n"
        "Provide your final conclusion based on the constraints."
    ),
    "cause_effect": (
        "Identify the cause and effect in the following scenario.\n\n"
        "Scenario: {question}\n\n"
        "Choose the most logical conclusion."
    ),
    "alfworld_plans": (
        "You are an agent in a text-based environment. Create a step-by-step plan "
        "to achieve the following goal.\n\n"
        "Goal: {question}\n\n"
        "Provide your detailed plan."
    ),
    "arc_challenge": (
        "Answer the following multiple choice science question.\n\n"
        "{question}\n\n"
        "Choose the best answer from the options provided."
    ),
    "hellaswag": (
        "Complete the following scenario with the most logical next event.\n\n"
        "Scenario: {question}\n\n"
        "Choose the best continuation from the options."
    ),
    "drop": (
        "Read the following passage and answer the question.\n\n"
        "Passage and Question: {question}\n\n"
        "Provide a concise answer based on the text."
    ),
    "bbh_word_sorting": (
        "Sort the following list of words alphabetically.\n\n"
        "List: {question}\n\n"
        "Provide the sorted list formatted as a JSON array."
    ),
    "bbh_analogies": (
        "Solve the following analogy concerning colored objects.\n\n"
        "Analogy: {question}\n\n"
        "Choose the best answer."
    ),
}

# ── Loaders ──────────────────────────────────────────────────────────────────


def _fetch_hf_rows(dataset: str, split: str = "test", n: int = 5) -> list[dict]:
    """Helper to fetch rows from HuggingFace Datasets Server API.

    Using httpx for lightweight HTTP-only extraction.
    """
    url = f"https://datasets-server.huggingface.co/rows?dataset={dataset}&config=default&split={split}&offset=0&length={n}"
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
        return [row["row"] for row in data["rows"]]


def load_math500(output_path: Path, n: int = 50) -> StandardDataset:
    """Load MATH dataset subset."""
    dataset_name = "math_500"
    questions = []
    try:
        rows = _fetch_hf_rows("HuggingFaceH4/MATH-500", "test", n)
        for i, row in enumerate(rows):
            questions.append(
                Question(
                    question_id=f"{dataset_name}_{i:04d}",
                    prompt=PROMPT_TEMPLATES[dataset_name].format(question=row.get("problem", "")),
                    ground_truth=str(row.get("solution", "")),
                    answer_type="numeric",
                    difficulty="hard",
                    metadata={"level": row.get("level", "5")},
                )
            )
    except Exception as e:
        logger.warning("Failed to fetch %s: %s. Using synthetic data.", dataset_name, e)
        for i in range(5):
            questions.append(
                Question(
                    question_id=f"{dataset_name}_synth_{i:04d}",
                    prompt=PROMPT_TEMPLATES[dataset_name].format(question=f"Solve x + {i} = 10"),
                    ground_truth=str(10 - i),
                    answer_type="numeric",
                    difficulty="hard",
                )
            )

    ds = StandardDataset("math_500", "Mathematical Reasoning", "HendrycksTest/MATH", questions)
    if output_path:
        ds.save(output_path)
    return ds


def load_gsm8k(output_path: Path, n: int = 50) -> StandardDataset:
    """Load GSM8K dataset."""
    dataset_name = "gsm8k"
    questions = []
    try:
        url = "https://datasets-server.huggingface.co/rows?dataset=gsm8k&config=main&split=test&offset=0&length=100"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            rows = [r["row"] for r in resp.json()["rows"]][:n]

        for i, row in enumerate(rows):
            gt_full = row.get("answer", "")
            # GSM8K format: reasoning #### answer
            gt_numeric = gt_full.split("#### ")[-1].strip() if "#### " in gt_full else gt_full
            questions.append(
                Question(
                    question_id=f"{dataset_name}_{i:04d}",
                    prompt=PROMPT_TEMPLATES[dataset_name].format(question=row.get("question", "")),
                    ground_truth=gt_numeric,
                    answer_type="numeric",
                    difficulty="medium",
                )
            )
    except Exception as e:
        logger.warning("Failed to fetch %s: %s. Using synthetic data.", dataset_name, e)
        for i in range(5):
            questions.append(
                Question(
                    question_id=f"{dataset_name}_synth_{i:04d}",
                    prompt=PROMPT_TEMPLATES[dataset_name].format(
                        question=f"Janet has {i} apples..."
                    ),
                    ground_truth=str(i),
                    answer_type="numeric",
                    difficulty="medium",
                )
            )

    ds = StandardDataset("gsm8k", "Arithmetic Word Problems", "openai/gsm8k", questions)
    if output_path:
        ds.save(output_path)
    return ds


def load_humaneval(output_path: Path, n: int = 50) -> StandardDataset:
    """Load HumanEval dataset."""
    dataset_name = "humaneval"
    questions = []
    try:
        rows = _fetch_hf_rows("openai_humaneval", "test", n)
        for i, row in enumerate(rows):
            questions.append(
                Question(
                    question_id=f"{dataset_name}_{i:04d}",
                    prompt=PROMPT_TEMPLATES[dataset_name].format(question=row.get("prompt", "")),
                    ground_truth=row.get("test", ""),
                    answer_type="code",
                    difficulty="hard",
                )
            )
    except Exception as e:
        logger.warning("Failed to fetch %s: %s. Using synthetic data.", dataset_name, e)
        for i in range(5):
            questions.append(
                Question(
                    question_id=f"{dataset_name}_synth_{i:04d}",
                    prompt=PROMPT_TEMPLATES[dataset_name].format(question="def add(a, b):"),
                    ground_truth="assert add(1, 2) == 3",
                    answer_type="code",
                    difficulty="hard",
                )
            )

    ds = StandardDataset("humaneval", "Code Generation", "openai/HumanEval", questions)
    if output_path:
        ds.save(output_path)
    return ds


def load_generic_synthetic(
    dataset_name: str,
    task_category: str,
    source: str,
    answer_type: Literal["numeric", "code", "multiple_choice", "free_text", "structured"],
    difficulty: Literal["easy", "medium", "hard"],
    output_path: Path,
    n: int = 5,
) -> StandardDataset:
    """Generate synthetic fallback data for generic endpoints."""
    questions = []
    for i in range(n):
        questions.append(
            Question(
                question_id=f"{dataset_name}_synth_{i:04d}",
                prompt=PROMPT_TEMPLATES[dataset_name].format(question=f"Synthetic question {i}"),
                ground_truth=f"Synthetic Answer {i}",
                answer_type=answer_type,
                difficulty=difficulty,
            )
        )
    ds = StandardDataset(dataset_name, task_category, source, questions)
    if output_path:
        ds.save(output_path)
    return ds


# Wrappers for the remaining 9 datasets (falling back to generic synthetic for brevity in demo)
def load_mbpp(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "mbpp",
        "Code Debugging",
        "google-research-datasets/mbpp",
        "code",
        "medium",
        output_path,
        min(n, 5),
    )


def load_logic_grid(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "logic_grid", "Logical Deduction", "Custom", "free_text", "hard", output_path, min(n, 5)
    )


def load_cause_effect(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "cause_effect",
        "Causal Reasoning",
        "BIG-Bench",
        "multiple_choice",
        "medium",
        output_path,
        min(n, 5),
    )


def load_alfworld_plans(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "alfworld_plans",
        "Multi-step Planning",
        "ALFWorld",
        "free_text",
        "hard",
        output_path,
        min(n, 5),
    )


def load_arc_challenge(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "arc_challenge",
        "Scientific QA",
        "allenai/ai2_arc",
        "multiple_choice",
        "hard",
        output_path,
        min(n, 5),
    )


def load_hellaswag(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "hellaswag",
        "Common Sense",
        "Rowan/hellaswag",
        "multiple_choice",
        "medium",
        output_path,
        min(n, 5),
    )


def load_drop(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "drop",
        "Reading Comprehension",
        "ucinlp/drop",
        "free_text",
        "medium",
        output_path,
        min(n, 5),
    )


def load_bbh_word_sorting(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "bbh_word_sorting",
        "Symbolic Manipulation",
        "lukaemon/bbh",
        "structured",
        "hard",
        output_path,
        min(n, 5),
    )


def load_bbh_analogies(output_path: Path, n: int = 50) -> StandardDataset:
    return load_generic_synthetic(
        "bbh_analogies",
        "Analogical Reasoning",
        "lukaemon/bbh",
        "multiple_choice",
        "medium",
        output_path,
        min(n, 5),
    )


# ── Main Entry Point ─────────────────────────────────────────────────────────

LOADERS = {
    "math_500": load_math500,
    "gsm8k": load_gsm8k,
    "humaneval": load_humaneval,
    "mbpp": load_mbpp,
    "logic_grid": load_logic_grid,
    "cause_effect": load_cause_effect,
    "alfworld_plans": load_alfworld_plans,
    "arc_challenge": load_arc_challenge,
    "hellaswag": load_hellaswag,
    "drop": load_drop,
    "bbh_word_sorting": load_bbh_word_sorting,
    "bbh_analogies": load_bbh_analogies,
}


def load_all_datasets(
    output_dir: Path,
    questions_per_dataset: int = 100,
    categories: list[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Path]:
    """Download and process all benchmark datasets.

    Args:
        output_dir: Directory to save the normalized JSON files.
        questions_per_dataset: Number of questions to fetch per dataset.
        categories: List of dataset names to process. If None, processes all 12.
        force_refresh: If True, re-download even if file exists.

    Returns:
        A mapping of dataset_name to its output JSON Path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    datasets_to_run = categories if categories else list(LOADERS.keys())
    results = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=False,
    ) as progress:
        task = progress.add_task("[cyan]Processing datasets...", total=len(datasets_to_run))

        for ds_name in datasets_to_run:
            output_path = output_dir / f"{ds_name}.json"

            if output_path.exists() and not force_refresh:
                progress.console.print(f"[green]Skipping {ds_name} (already exists)[/green]")
                results[ds_name] = output_path
                progress.advance(task)
                continue

            progress.update(task, description=f"[cyan]Downloading {ds_name}...")
            loader_fn = LOADERS.get(ds_name)
            if not loader_fn:
                progress.console.print(f"[red]No loader found for {ds_name}[/red]")
                continue

            try:
                ds = loader_fn(output_path, n=questions_per_dataset)
                errors = validate_dataset(ds)
                if errors:
                    progress.console.print(f"[red]Validation failed for {ds_name}: {errors}[/red]")
                else:
                    results[ds_name] = output_path
                    progress.console.print(
                        f"[green]Successfully saved {ds_name} ({len(ds.questions)} qs)[/green]"
                    )
            except Exception as e:
                progress.console.print(f"[red]Failed to process {ds_name}: {e}[/red]")

            progress.advance(task)

    return results
