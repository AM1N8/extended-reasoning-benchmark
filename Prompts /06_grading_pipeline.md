# Prompt 06 — LLM-as-Judge Grading Pipeline

## Role & Mission

You are an ML engineer building a **dual-mode automated grading system** for LLM benchmark outputs. You will implement two grading pipelines: (1) a quantitative judge that determines if each answer is correct, and (2) a qualitative judge that analyzes reasoning traces to detect problem-solving strategies.

---

## GLOBAL CONTEXT

```
Project: LLM reasoning benchmark
Input: benchmark_runs table — rows with final_answer, ground_truth, raw_trace
Grading model: Gemini 1.5 Flash (via Google AI Studio — fast + free)
  Fallback: Llama-3 via GitHub Models (if Gemini quota exceeded)
Stack: Python 3.12+, httpx, polars, sqlite3
Output: Updates is_correct, grader_rationale, strategy_tags columns in DB
```

---

## Grading Strategy by Answer Type

Different `answer_type` values require different grading approaches:

| Answer Type | Primary Grading Method | Fallback |
|---|---|---|
| `numeric` | Regex + numeric comparison (exact or ±0.01%) | LLM judge |
| `multiple_choice` | Exact string match on A/B/C/D | LLM judge |
| `code` | Execute test suite in subprocess sandbox | LLM judge |
| `free_text` | LLM judge only | — |
| `structured` | JSON parse + field comparison | LLM judge |

**Always try rule-based methods first** — cheaper and faster. Only call the LLM judge when rule-based fails or is inapplicable.

---

## Module 1: `src/benchmark/grading/quantitative.py`

### Architecture

```
QuantitativeGrader
├── RuleBasedGrader          (no API call)
│   ├── NumericGrader
│   ├── MultipleChoiceGrader
│   └── CodeExecutionGrader
└── LLMJudgeGrader           (API call to fast/cheap model)
```

### Rule-Based Graders

**`NumericGrader`** — for GSM8K, MATH, etc.:
```python
def grade_numeric(final_answer: str, ground_truth: str) -> tuple[int, str]:
    """
    Extract the last number in final_answer.
    Compare to ground_truth numerically.
    Handle fractions (e.g., '1/2' == 0.5), LaTeX (e.g., '\\frac{1}{2}'), 
    percentages, and scientific notation.
    Return (1 or 0, rationale_string).
    """
```

**`MultipleChoiceGrader`** — for ARC, HellaSwag:
```python
def grade_multiple_choice(final_answer: str, ground_truth: str) -> tuple[int, str]:
    """
    Extract A/B/C/D from final_answer using regex.
    Try patterns: 'The answer is (A)', 'Answer: B', standalone 'C', etc.
    Return (1 or 0, rationale_string).
    """
```

**`CodeExecutionGrader`** — for HumanEval, MBPP:
```python
def grade_code(
    final_answer: str,   # Model's generated code
    ground_truth: str,   # Test suite as string
    timeout_seconds: int = 10,
) -> tuple[int, str]:
    """
    Execute the test suite against the generated code in a subprocess.
    Uses subprocess.run() with a timeout.
    SAFETY: Never exec() directly — always use subprocess with restricted env.
    Return (1=pass, 0=fail, rationale with error message if failed).
    
    Security note: Run in a restricted environment:
    - subprocess.run(['python', '-c', code], capture_output=True, timeout=timeout)
    - No network access assumed (can't block in subprocess easily)
    """
```

### LLM Judge

```python
LLM_JUDGE_SYSTEM_PROMPT = """You are a precise answer-grading assistant. 
Your job is to determine if a model's answer is CORRECT or INCORRECT compared to the ground truth.

Rules:
- Be lenient about formatting differences (e.g., '1/2' and '0.5' are the same)
- Be strict about mathematical values (e.g., '3' and '3.1' are NOT the same)
- For free-text answers, check if the meaning is equivalent
- Ignore preamble/explanation — only grade the FINAL answer

Respond ONLY with a JSON object:
{"correct": true/false, "rationale": "one sentence explanation"}
"""

LLM_JUDGE_USER_TEMPLATE = """Ground truth: {ground_truth}

Model's answer: {final_answer}

Is the model's answer correct?"""
```

**`LLMJudgeGrader.grade()` logic:**
1. Call the judge model via the API dispatcher
2. Parse the JSON response
3. If JSON parsing fails, retry once
4. If still fails, log warning and return `is_correct=None` (leave ungraded)

### Main Entry Point: `grade_quantitative()`

```python
async def grade_quantitative(
    db: DatabaseManager,
    dispatcher: RateLimitedDispatcher,
    batch_size: int = 50,
) -> None:
    """
    Fetch all ungraded runs (is_correct IS NULL, is_error=0).
    For each run:
      1. Try rule-based grading based on answer_type
      2. If inconclusive, call LLM judge
      3. Update DB with is_correct + grader_rationale
    Show rich progress bar.
    """
```

---

## Module 2: `src/benchmark/grading/qualitative.py`

### The 5 Reasoning Strategies

```python
REASONING_STRATEGIES = {
    "decomposition": "Breaking problem into sub-problems or steps",
    "analogy": "Using a simpler analogous problem to guide reasoning",
    "verification": "Checking the answer by re-solving or substituting back",
    "backtracking": "Abandoning a wrong approach and restarting with new strategy",
    "self_consistency": "Generating multiple solution attempts and voting on the answer",
}
```

### Qualitative Analysis Prompt

```python
QUAL_JUDGE_SYSTEM_PROMPT = """You are an expert at analyzing reasoning traces from AI models.
Your task is to identify which problem-solving strategies are present in a thinking trace.

The 5 strategies to detect:
1. DECOMPOSITION: The model explicitly breaks the problem into smaller sub-problems or numbered steps
2. ANALOGY: The model references a simpler or similar problem to guide its approach  
3. VERIFICATION: The model checks its answer by plugging back in, re-solving, or explicitly stating "let me verify"
4. BACKTRACKING: The model abandons an approach mid-way with phrases like "wait", "actually", "let me try a different approach", "that's wrong"
5. SELF_CONSISTENCY: The model tries 2+ distinct solution approaches and compares/votes on the results

Respond ONLY with a JSON object (no markdown, no explanation):
{
  "decomposition": 0 or 1,
  "analogy": 0 or 1,
  "verification": 0 or 1,
  "backtracking": 0 or 1,
  "self_consistency": 0 or 1,
  "dominant_strategy": "name of most prominent strategy or null",
  "reasoning_depth": 1-5,
  "confidence": 0.0-1.0
}
"""

QUAL_JUDGE_USER_TEMPLATE = """Task category: {task_category}
Model: {model}
Budget level: {budget_level}

Reasoning trace:
---
{raw_trace}
---

Identify which reasoning strategies are present."""
```

**Important**: Truncate `raw_trace` to 8,000 characters if longer (to stay within judge context window).

### Batch Processing Logic

```python
async def grade_qualitative(
    db: DatabaseManager,
    dispatcher: RateLimitedDispatcher,
    models_with_traces: list[str] | None = None,  # None = all
) -> None:
    """
    Fetch runs where raw_trace IS NOT NULL and strategy_tags IS NULL.
    Group by model to process similar traces together.
    For each run: call LLM judge, parse strategy_tags JSON, update DB.
    
    Only process models that expose traces:
    - deepseek/DeepSeek-R1  (exposes <think> blocks)
    - gemini-2.0-flash-thinking-exp  (exposes thought parts)
    """
```

---

## Grading Statistics Reporter

After grading, generate a summary:

```python
def print_grading_summary(db: DatabaseManager) -> None:
    """
    Print a rich table showing:
    - Total runs graded / ungraded
    - Accuracy per model (rows) × budget level (columns)
    - % runs with each strategy tag detected
    - Average reasoning depth score
    """
```

---

## CLI Entry Points

**`src/benchmark/grading/__main__.py`:**

```
Usage: python -m benchmark.grading [--mode {quant,qual,both}] [--model MODEL]

Modes:
  quant   Run quantitative (correctness) grading
  qual    Run qualitative (strategy) trace analysis
  both    Run both in sequence (default)
```

---

## Testing

Write `tests/test_grading.py`:

1. **`TestNumericGrader`** — test cases:
   - `"18"` vs `"18"` → correct
   - `"18.0"` vs `"18"` → correct
   - `"\\frac{1}{2}"` vs `"0.5"` → correct
   - `"3.14"` vs `"pi"` → test that LLM judge is called (mock it)
   - `"wrong"` vs `"18"` → incorrect

2. **`TestMultipleChoiceGrader`** — test cases:
   - `"The answer is (B)"` vs `"B"` → correct
   - `"Answer: C. Because..."` vs `"C"` → correct
   - `"I think A is correct"` vs `"B"` → incorrect

3. **`TestCodeGrader`** — test with a simple HumanEval-style function:
   ```python
   code = "def add(a, b): return a + b"
   tests = "assert add(1, 2) == 3\nassert add(-1, 1) == 0"
   # Should return is_correct=1
   ```

4. **`TestQualitativeParser`** — verify JSON parsing from LLM judge response handles:
   - Valid JSON response → correct dict
   - JSON with extra whitespace → correct dict
   - Malformed JSON → returns None (triggers retry)

5. **`TestStrategyDetection`** — provide a sample trace containing obvious backtracking (`"wait, that's wrong, let me try again"`) and verify `backtracking=1` is detected.

---

## Requirements

- **Never execute user-provided code in the main process** — always use `subprocess.run()`
- Set `timeout=10` on all code execution
- **Never call the LLM judge for numeric/MC** if rule-based grading is confident (reduces costs by ~40%)
- Use `polars` for all DataFrame operations when fetching from DB
- Log grading decisions at DEBUG level
- Progress: use `rich.progress` with a custom column showing `✓ {n_correct}/{n_total} ({accuracy:.1f}%)`

---

## Output Format

1. `src/benchmark/grading/quantitative.py`
2. `src/benchmark/grading/qualitative.py`
3. `src/benchmark/grading/__main__.py`
4. `tests/test_grading.py`
5. A brief note on the cost savings from rule-based grading first
