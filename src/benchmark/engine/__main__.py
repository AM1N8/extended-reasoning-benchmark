"""CLI entry point for the benchmark execution engine."""

import argparse
import asyncio
import logging
from pathlib import Path

from benchmark.clients.__init__ import RateLimitedDispatcher
from benchmark.config import get_settings
from benchmark.database import DatabaseManager
from benchmark.engine.runner import BenchmarkRunner

logging.basicConfig(level=logging.WARNING)


def parse_args():
    parser = argparse.ArgumentParser(description="LLM Benchmark Engine")
    parser.add_argument("--dry-run", action="store_true", help="Run only 2 questions per dataset")
    parser.add_argument("--models", type=str, help="Comma-separated model list (default: all)")
    parser.add_argument("--datasets", type=str, help="Comma-separated dataset list (default: all)")
    parser.add_argument(
        "--budgets", type=str, help="Comma-separated budget levels, e.g. '1,3,5' (default: all)"
    )

    # Resume is True by default, --no-resume sets it to False
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Re-run all, overwriting existing results",
    )
    parser.set_defaults(resume=True)

    return parser.parse_args()


async def main_async():
    args = parse_args()
    settings = get_settings()

    db = DatabaseManager(settings.db_path)
    dispatcher = RateLimitedDispatcher(settings)

    # Parse comma-separated inputs
    models = args.models.split(",") if args.models else None
    datasets = args.datasets.split(",") if args.datasets else None
    budgets = [int(x) for x in args.budgets.split(",")] if args.budgets else None

    data_dir = Path("data/processed")

    # Fail fast if datasets missing
    if datasets:
        for ds in datasets:
            if not (data_dir / f"{ds}.json").exists():
                print(
                    f"Error: Dataset file {ds}.json not found in {data_dir}. Run dataset pipeline first."
                )
                return

    runner = BenchmarkRunner(
        dispatcher=dispatcher,
        db=db,
        data_dir=data_dir,
        dry_run=args.dry_run,
        dry_run_questions=2,
        models=models,
        datasets=datasets,
        budget_levels=budgets,
        resume=args.resume,
    )

    # The runner displays the table and prints the warning inside run()
    # It takes care of progress and DB

    try:
        await runner.run()
    except KeyboardInterrupt:
        print("\n[!] Execution interrupted by user. Exiting cleanly.")
        # Async tasks will be cancelled, DB uses immediate inserts so no data loss
    except Exception as e:
        print(f"\n[!] Fatal error: {e}")


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[!] Execution interrupted by user. Exiting cleanly.")


if __name__ == "__main__":
    main()
