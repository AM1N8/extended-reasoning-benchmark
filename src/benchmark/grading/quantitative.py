"""Quantitative grading strategies (rule-based and LLM-assisted)."""

import asyncio
import json
import logging
import re
import subprocess
import tempfile

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from benchmark.clients.__init__ import RateLimitedDispatcher
from benchmark.clients.base import BudgetLevel, QueryRequest
from benchmark.database import DatabaseManager

logger = logging.getLogger(__name__)

LLM_JUDGE_SYSTEM_PROMPT = """You are a precise answer-grading assistant. 
Your job is to determine if a model's answer is CORRECT or INCORRECT compared to the ground truth.

Rules:
- Be lenient about formatting differences (e.g., '1/2' and '0.5' are the same)
- Be strict about mathematical values (e.g., '3' and '3.1' are NOT the same)
- For free-text answers, check if the meaning is equivalent
- Ignore preamble/explanation — only grade the FINAL answer

Respond ONLY with a JSON object:
{"correct": true, "rationale": "one sentence explanation"}
"""

LLM_JUDGE_USER_TEMPLATE = """Ground truth: {ground_truth}

Model's answer: {final_answer}

Is the model's answer correct?"""


def _parse_numeric(text: str) -> float | None:
    """Extremely basic numeric parser. For fractions, percentages, etc."""
    text = text.replace(",", "").strip()
    if text.endswith("%"):
        try:
            return float(text[:-1]) / 100.0
        except ValueError:
            pass
    # simple fraction?
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 2:
            try:
                return float(parts[0]) / float(parts[1])
            except ValueError:
                pass
    try:
        return float(text)
    except ValueError:
        return None


def grade_numeric(final_answer: str, ground_truth: str) -> tuple[int | None, str]:
    """Grade numeric answers strictly. Returns None if it needs LLM fallback."""
    if not final_answer:
        return 0, "Empty final answer"

    ans_str = str(final_answer).strip()
    gt_str = str(ground_truth).strip()

    if ans_str == gt_str:
        return 1, "Exact string match"

    # Try parsing both to floats
    ans_val = _parse_numeric(ans_str)
    gt_val = _parse_numeric(gt_str)

    if ans_val is not None and gt_val is not None:
        if abs(ans_val - gt_val) < 1e-5:
            return 1, "Numeric equivalence"
        else:
            return 0, "Numeric values do not match"

    # If the answer contains no digits at all, it's structurally wrong
    if not any(c.isdigit() for c in ans_str):
        return 0, "No digits found in answer"

    # Fallback to LLM if there's complex LaTeX
    return None, "Needs LLM judge"


def grade_multiple_choice(final_answer: str, ground_truth: str) -> tuple[int | None, str]:
    """Grade multiple choice by extracting A/B/C/D."""
    if not final_answer:
        return 0, "Empty final answer"

    ans_str = str(final_answer).strip()
    gt_str = str(ground_truth).strip().upper()

    # Fast exact match
    if ans_str.upper() == gt_str:
        return 1, "Exact match"

    # Look for standalone option, or "Answer: X", or "(X)"
    # Regex looks for letters A-E in isolation or specific prefixes
    match = re.search(r"(?i)(?:answer is|answer:)\s*\(?([A-E])\)?", ans_str)
    if match:
        extracted = match.group(1).upper()
        if extracted == gt_str:
            return 1, "Regex extracted exact match"
        else:
            return 0, f"Regex extracted {extracted}, expected {gt_str}"

    # Look for just "(A)"
    match = re.search(r"\(([A-E])\)", ans_str)
    if match:
        extracted = match.group(1).upper()
        if extracted == gt_str:
            return 1, "Regex extracted exact match"
        else:
            return 0, f"Regex extracted {extracted}, expected {gt_str}"

    # Look for isolated A-E as fallback
    match = re.search(r"\b([A-E])\b", ans_str)
    if match:
        extracted = match.group(1).upper()
        if extracted == gt_str:
            return 1, "Regex extracted exact match"
        else:
            return 0, f"Regex extracted {extracted}, expected {gt_str}"

    return None, "Needs LLM judge"


def grade_code(final_answer: str, ground_truth: str, timeout_seconds: int = 10) -> tuple[int, str]:
    """Execute python code in a subprocess to grade."""
    if not final_answer or "def " not in final_answer:
        return 0, "No parseable function found"

    # Isolate python code block if exists
    code = final_answer
    if "```python" in final_answer:
        code = final_answer.split("```python")[1].split("```")[0]
    elif "```" in final_answer:
        code = final_answer.split("```")[1].split("```")[0]

    full_script = f"{code}\n\n{ground_truth}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(full_script)
        script_path = f.name

    try:
        result = subprocess.run(
            ["python", script_path], capture_output=True, timeout=timeout_seconds, text=True
        )
        if result.returncode == 0:
            return 1, "Test suite passed"
        else:
            return 0, f"Test suite failed: {result.stderr.strip()[:100]}"
    except subprocess.TimeoutExpired:
        return 0, f"Execution timed out after {timeout_seconds}s"
    except Exception as e:
        return 0, f"Execution error: {e}"


async def _grade_with_llm(
    final_answer: str, ground_truth: str, dispatcher: RateLimitedDispatcher
) -> tuple[int | None, str]:
    """Call the LLM Judge (Gemini) to determine correctness."""
    prompt = LLM_JUDGE_USER_TEMPLATE.format(ground_truth=ground_truth, final_answer=final_answer)
    request = QueryRequest(
        prompt=prompt,
        model="gemini-2.0-flash-thinking-exp-01-21",  # Default cheap model
        budget_level=BudgetLevel.BASELINE,
        temperature=0.0,
    )

    for attempt in range(2):
        response = await dispatcher.query(request, max_retries=2)
        if not response or not response.final_answer:
            continue

        try:
            # Look for JSON block
            content = response.final_answer
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "{" in content:
                content = content[content.find("{") : content.rfind("}") + 1]

            data = json.loads(content)
            is_correct = 1 if data.get("correct") else 0
            rationale = data.get("rationale", "LLM Judge decision")
            return is_correct, rationale
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"Failed to parse LLM judge JSON (attempt {attempt + 1})")
            continue

    return None, "LLM judge parsing failed"


async def grade_quantitative(
    db: DatabaseManager,
    dispatcher: RateLimitedDispatcher,
    batch_size: int = 50,
) -> None:
    """Fetch all ungraded runs and process them."""
    df = db.get_ungraded_runs()
    if df.is_empty():
        print("No ungraded runs found.")
        return

    runs = df.to_dicts()
    total = len(runs)

    correct = 0
    graded = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("✓ {task.fields[correct]}/{task.completed} ({task.fields[acc]:.1f}%)"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Grading...", total=total, correct=0, acc=0.0)

        # We can run these sequentially to avoid hammering the LLM if many fallbacks happen
        # Or batch them if LLM calls are needed. Let's do a simple bounded loop.
        semaphore = asyncio.Semaphore(5)

        async def process_row(row):
            nonlocal correct, graded
            run_id = row["run_id"]
            ans_type = "numeric"  # default
            # Deduce type if not in DB directly (we can get from dataset_registry conceptually,
            # or pass it along. Our DB schema doesn't have answer_type, but let's infer or default
            # to LLM judge if unsure, though we can guess from task_category).
            cat = row["task_category"].lower()
            if "math" in cat or "arithmetic" in cat:
                ans_type = "numeric"
            elif "code" in cat:
                ans_type = "code"
            elif "multiple choice" in cat or "qa" in cat or "common sense" in cat:
                ans_type = "multiple_choice"
            else:
                ans_type = "free_text"

            is_correct = None
            rationale = ""

            # 1. Rule-based
            if ans_type == "numeric":
                is_correct, rationale = grade_numeric(row["final_answer"], row["ground_truth"])
            elif ans_type == "multiple_choice":
                is_correct, rationale = grade_multiple_choice(
                    row["final_answer"], row["ground_truth"]
                )
            elif ans_type == "code":
                is_correct, rationale = grade_code(row["final_answer"], row["ground_truth"])

            # 2. LLM fallback
            if is_correct is None:
                async with semaphore:
                    is_correct, rationale = await _grade_with_llm(
                        row["final_answer"] or "", row["ground_truth"] or "", dispatcher
                    )

            # 3. Update DB
            if is_correct is not None:
                db.update_grading(run_id, is_correct, rationale)
                correct += is_correct
                graded += 1

            acc = (correct / graded * 100) if graded > 0 else 0.0
            progress.update(task, advance=1, correct=correct, acc=acc)

        tasks = [process_row(r) for r in runs]
        await asyncio.gather(*tasks)
