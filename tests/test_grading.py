"""Unit tests for the rule-based grading components and qualitative parser."""

from unittest.mock import AsyncMock

import pytest

from benchmark.clients.base import ModelResponse
from benchmark.grading.qualitative import _analyze_trace
from benchmark.grading.quantitative import grade_code, grade_multiple_choice, grade_numeric


def test_numeric_grader():
    """Test rule-based numerical extraction and comparisons."""
    # Exact matches
    assert grade_numeric("18", "18")[0] == 1
    assert grade_numeric("18.0", "18")[0] == 1

    # Fractions to decimals
    assert grade_numeric("1/2", "0.5")[0] == 1

    # Percentages
    assert grade_numeric("50%", "0.5")[0] == 1

    # Needs LLM judge (LaTeX or complex strings)
    assert grade_numeric("3.14", "pi")[0] is None

    # Clear failures
    assert grade_numeric("wrong", "18")[0] == 0


def test_multiple_choice_grader():
    """Test regex parsing for multiple choice answers."""
    # Exact standalone
    assert grade_multiple_choice("C", "C")[0] == 1

    # Embedded A/B/C/D
    assert grade_multiple_choice("The answer is (B)", "B")[0] == 1
    assert grade_multiple_choice("Answer: C. Because...", "C")[0] == 1
    assert grade_multiple_choice("(A)", "A")[0] == 1

    # Incorrect choices
    assert grade_multiple_choice("I think A is correct", "B")[0] == 0

    # Unclear answers fallback to LLM
    assert grade_multiple_choice("I think it is the third option", "C")[0] is None


def test_code_grader():
    """Test subprocess sandbox execution grading."""
    code = "def add(a, b):\n    return a + b"
    tests = "assert add(1, 2) == 3\nassert add(-1, 1) == 0"

    is_correct, rationale = grade_code(code, tests)
    assert is_correct == 1
    assert "passed" in rationale

    code_bad = "def add(a, b):\n    return a - b"
    is_correct, rationale = grade_code(code_bad, tests)
    assert is_correct == 0
    assert "failed" in rationale


@pytest.mark.asyncio
async def test_qualitative_parser():
    """Verify JSON parsing from LLM judge response handles edge cases."""
    dispatcher = AsyncMock()

    # Valid JSON
    dispatcher.query.return_value = ModelResponse(
        model="gemini",
        prompt="",
        raw_trace=None,
        final_answer='```json\n{"backtracking": 1, "decomposition": 0}\n```',
        input_tokens=0,
        reasoning_tokens=0,
        output_tokens=0,
        latency_seconds=0.1,
        raw_api_response={},
    )
    result = await _analyze_trace({"raw_trace": "Wait, let me retry."}, dispatcher)
    assert result["backtracking"] == 1

    # Malformed JSON triggers retry and returns None if still fails
    dispatcher.query.return_value = ModelResponse(
        model="gemini",
        prompt="",
        raw_trace=None,
        final_answer="```json\n{bad format}\n```",
        input_tokens=0,
        reasoning_tokens=0,
        output_tokens=0,
        latency_seconds=0.1,
        raw_api_response={},
    )
    result = await _analyze_trace({"raw_trace": "Test"}, dispatcher)
    assert result is None
