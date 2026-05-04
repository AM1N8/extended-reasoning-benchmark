"""Tests for dataset loading and processing pipeline."""

import json
from pathlib import Path

from benchmark.datasets.loader import (
    PROMPT_TEMPLATES,
    Question,
    StandardDataset,
    load_gsm8k,
    validate_dataset,
)


def test_validate_dataset_missing_ground_truth() -> None:
    """Test that validation catches missing ground_truth."""
    ds = StandardDataset(
        dataset_name="test_ds",
        task_category="Testing",
        source="test",
        questions=[
            Question(
                question_id="q1",
                prompt="Prompt",
                ground_truth="",  # Missing ground truth
                answer_type="numeric",
                difficulty="medium",
            )
        ],
    )
    errors = validate_dataset(ds)
    assert len(errors) == 1
    assert "missing ground_truth" in errors[0]


def test_standard_dataset_to_json(tmp_path: Path) -> None:
    """Test serialization of StandardDataset produces correct schema."""
    ds = StandardDataset(
        dataset_name="gsm8k",
        task_category="Math",
        source="openai/gsm8k",
        questions=[
            Question(
                question_id="q1",
                prompt="Prompt 1",
                ground_truth="10",
                answer_type="numeric",
                difficulty="easy",
                metadata={"test": "abc"},
            )
        ],
    )

    file_path = tmp_path / "test.json"
    ds.save(file_path)

    # Verify file contents
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["dataset_name"] == "gsm8k"
    assert data["num_questions"] == 1
    assert data["questions"][0]["question_id"] == "q1"
    assert data["questions"][0]["metadata"]["test"] == "abc"


def test_prompt_template_rendering() -> None:
    """Test that prompt templates render correctly with special characters."""
    template = PROMPT_TEMPLATES["humaneval"]
    question_text = 'def solve(a: int) -> int:\n    """Docstring with {curly} braces."""'

    # .format() requires escaping {{curly}} if we do straight format,
    # but the way we use it only replaces {question}. Let's ensure it handles correctly.
    # Python's .format() will error if there are unescaped braces in the replacement text
    # IF we used the text as a template, but we are injecting it AS the parameter.
    rendered = template.format(question=question_text)

    assert "def solve" in rendered
    assert "Docstring with {curly}" in rendered
    assert "Your implementation:" in rendered


def test_load_gsm8k_answer_type(tmp_path: Path) -> None:
    """Mock test verifying GSM8K sets answer_type to numeric."""
    # Since HTTP can fail in tests, this will likely hit the synthetic fallback.
    # Either way, it should return answer_type="numeric".
    output_path = tmp_path / "gsm8k.json"
    ds = load_gsm8k(output_path, n=2)

    assert ds.dataset_name == "gsm8k"
    assert len(ds.questions) >= 2
    for q in ds.questions:
        assert q.answer_type == "numeric"
