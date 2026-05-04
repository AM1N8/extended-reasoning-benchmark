"""CLI entry point for generating the cost dashboard and enterprise guide."""

import argparse
from pathlib import Path

from benchmark.analysis.metrics import analyze_diminishing_returns, compute_efficiency_scores
from benchmark.config import get_settings
from benchmark.database import DatabaseManager
from benchmark.report.cost_dashboard import (
    DECISION_TREE,
    build_cost_dashboard,
    generate_enterprise_report,
    recommend_model_per_category,
)


def parse_args():
    parser = argparse.ArgumentParser(description="LLM Enterprise Cost & Report Generator")
    parser.add_argument("--output-dir", type=str, default="results", help="Output directory")
    return parser.parse_args()


def main():
    args = parse_args()
    settings = get_settings()
    db = DatabaseManager(settings.db_path)

    out_dir = Path(args.output_dir)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    print("Computing cost dashboard...")
    cost_df = build_cost_dashboard(db)

    if not cost_df.is_empty():
        cost_path = tables_dir / "cost_dashboard.csv"
        cost_df.write_csv(cost_path)
        print(f"✓ Saved cost dashboard to {cost_path}")

    print("Computing recommendations...")
    eff_df = compute_efficiency_scores(db)
    recs_df = recommend_model_per_category(cost_df, eff_df)

    dim_returns = analyze_diminishing_returns(eff_df)

    print("Generating Enterprise Guide...")
    guide_path = generate_enterprise_report(cost_df, recs_df, dim_returns, out_dir)
    print(f"✓ Saved Enterprise Guide to {guide_path}")

    dt_path = out_dir / "decision_tree.md"
    with open(dt_path, "w", encoding="utf-8") as f:
        f.write(DECISION_TREE)
    print(f"✓ Saved Standalone Decision Tree to {dt_path}")


if __name__ == "__main__":
    main()
