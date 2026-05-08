"""Qualitative grading of reasoning traces (strategy detection)."""

import asyncio
import json
import logging

import polars as pl
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from benchmark.clients.__init__ import RateLimitedDispatcher
from benchmark.clients.base import BudgetLevel, QueryRequest
from benchmark.config import get_settings
from benchmark.database import DatabaseManager

logger = logging.getLogger(__name__)

REASONING_STRATEGIES = {
    "decomposition": "Breaking problem into sub-problems or steps",
    "analogy": "Using a simpler analogous problem to guide reasoning",
    "verification": "Checking the answer by re-solving or substituting back",
    "backtracking": "Abandoning a wrong approach and restarting with new strategy",
    "self_consistency": "Generating multiple solution attempts and voting on the answer",
}

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
  "reasoning_depth": 1,
  "confidence": 0.9
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


async def _analyze_trace(row: dict, dispatcher: RateLimitedDispatcher) -> dict | None:
    """Call the LLM Judge to classify the trace."""
    trace = row.get("raw_trace", "")
    if not trace:
        return None

    # Truncate to 8,000 chars to avoid massive context
    if len(trace) > 8000:
        trace = trace[:8000] + "...[TRUNCATED]"

    prompt = QUAL_JUDGE_USER_TEMPLATE.format(
        task_category=row.get("task_category", "Unknown"),
        model=row.get("model", "Unknown"),
        budget_level=row.get("budget_level", 1),
        raw_trace=trace,
    )
    prompt = f"{QUAL_JUDGE_SYSTEM_PROMPT}\n\n{prompt}"

    request = QueryRequest(
        prompt=prompt,
        model=get_settings().grader_model,
        budget_level=BudgetLevel.BASELINE,
        temperature=0.0,
        max_tokens=256,
    )

    for attempt in range(2):
        response = await dispatcher.query(request, max_retries=2)
        if not response or not response.final_answer:
            continue

        try:
            content = response.final_answer
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "{" in content:
                content = content[content.find("{") : content.rfind("}") + 1]

            data = json.loads(content)
            # Validate presence of keys
            for key in REASONING_STRATEGIES:
                if key not in data:
                    data[key] = 0
            return data
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Failed to parse qual judge JSON (attempt {attempt + 1}). Content: {content}")
            continue

    return None


async def grade_qualitative(
    db: DatabaseManager,
    dispatcher: RateLimitedDispatcher,
    models_with_traces: list[str] | None = None,
) -> None:
    """Fetch runs with traces and no strategy tags, and analyze them."""
    # Find records where raw_trace is not null and strategy_tags is null
    df = db.get_runs_with_traces()
    if df.is_empty():
        print("No un-analyzed traces found.")
        return

    # Filter for missing strategy_tags
    if "strategy_tags" in df.columns:
        df = df.filter(pl.col("strategy_tags").is_null())

    if models_with_traces:
        df = df.filter(pl.col("model").is_in(models_with_traces))

    if df.is_empty():
        print("No un-analyzed traces found after filtering.")
        return

    runs = df.to_dicts()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("[magenta]Analyzing traces...", total=len(runs))

        semaphore = asyncio.Semaphore(5)

        async def process_row(row):
            async with semaphore:
                tags = await _analyze_trace(row, dispatcher)
                if tags is not None:
                    db.update_strategy_tags(row["run_id"], tags)
                progress.advance(task)

        tasks = [process_row(r) for r in runs]
        await asyncio.gather(*tasks)


def print_grading_summary(db: DatabaseManager) -> None:
    """Print a rich table summarizing the grading results."""
    stats = db.get_summary_stats()

    console = Console()
    if stats.is_empty():
        console.print("[yellow]No grading data available.[/yellow]")
        return

    table = Table(title="Grading Summary", show_header=True, header_style="bold magenta")
    table.add_column("Model", style="cyan")
    table.add_column("Task Category")
    table.add_column("Budget", justify="center")
    table.add_column("Runs", justify="right")
    table.add_column("Accuracy", justify="right", style="green")

    for row in stats.to_dicts():
        table.add_row(
            row["model"],
            row["task_category"],
            str(row["budget_level"]),
            str(row["run_count"]),
            f"{row['accuracy'] * 100:.1f}%" if row["accuracy"] is not None else "N/A",
        )

    console.print(table)
