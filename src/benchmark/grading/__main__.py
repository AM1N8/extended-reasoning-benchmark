"""CLI entry point for the dual-mode grading pipeline."""

import argparse
import asyncio
import logging

from benchmark.clients.__init__ import RateLimitedDispatcher
from benchmark.config import get_settings
from benchmark.database import DatabaseManager
from benchmark.grading.qualitative import grade_qualitative, print_grading_summary
from benchmark.grading.quantitative import grade_quantitative

logging.basicConfig(level=logging.WARNING)


def parse_args():
    parser = argparse.ArgumentParser(description="LLM Grading Pipeline")
    parser.add_argument(
        "--mode", choices=["quant", "qual", "both"], default="both", help="Grading mode to run"
    )
    parser.add_argument("--model", type=str, help="Specific model to run qualitative analysis on")
    return parser.parse_args()


async def main_async():
    args = parse_args()
    settings = get_settings()

    db = DatabaseManager(settings.db_path)
    dispatcher = RateLimitedDispatcher(settings)

    if args.mode in ("quant", "both"):
        print("\n--- Running Quantitative Grading ---")
        await grade_quantitative(db, dispatcher)

    if args.mode in ("qual", "both"):
        print("\n--- Running Qualitative Trace Analysis ---")
        models = [args.model] if args.model else None
        await grade_qualitative(db, dispatcher, models_with_traces=models)

    print("\n--- Final Summary ---")
    print_grading_summary(db)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[!] Grading interrupted by user.")


if __name__ == "__main__":
    main()
