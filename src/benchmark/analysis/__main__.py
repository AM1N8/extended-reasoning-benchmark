"""CLI entry point to generate the rich analysis summary."""

import argparse
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from benchmark.analysis.metrics import (
    analyze_diminishing_returns,
    compute_efficiency_scores,
    compute_significance_tests,
    export_all_metrics,
)
from benchmark.config import get_settings
from benchmark.database import DatabaseManager


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark Analysis & Metrics")
    parser.add_argument(
        "--output-dir", type=str, default="results", help="Output directory for CSVs"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    settings = get_settings()
    db = DatabaseManager(settings.db_path)

    out_dir = Path(args.output_dir)
    print(f"Exporting metrics to {out_dir}...")
    export_all_metrics(db, out_dir)

    # Generate numbers for summary report
    df_runs = db.get_runs()
    total_runs = len(df_runs)
    if total_runs == 0:
        print("No runs in database.")
        return

    df_graded = df_runs.filter(df_runs["is_correct"].is_not_null())
    total_graded = len(df_graded)
    graded_pct = (total_graded / total_runs * 100) if total_runs > 0 else 0

    df_traces = db.get_runs_with_traces()
    models_with_traces = df_traces["model"].n_unique() if not df_traces.is_empty() else 0

    eff_df = compute_efficiency_scores(db)

    top_efficiency_lines = []
    if not eff_df.is_empty():
        # Let's get top efficiency for L3
        l3_df = eff_df.filter(eff_df["budget_level"] == 3)
        if not l3_df.is_empty():
            l3_sorted = l3_df.sort("efficiency_score", descending=True).head(2).to_dicts()
            for idx, row in enumerate(l3_sorted):
                top_efficiency_lines.append(
                    f"{idx + 1}. {row['model']} | {row['task_category']} | {row['efficiency_score']:.2f} pts/1k"
                )

    dim_returns = analyze_diminishing_returns(eff_df)
    plateaus = sum(1 for r in dim_returns.values() if r.plateau_detected)
    improves = len(dim_returns) - plateaus

    sig_df = compute_significance_tests(db)
    sig_count = sig_df["is_significant"].sum() if not sig_df.is_empty() else 0
    sig_status = (
        f"✓ CONFIRMED ({sig_count}/{len(sig_df)} tests significant)"
        if sig_count > 0
        else "✗ NOT SIGNIFICANT"
    )

    # Rich Summary Report
    console = Console()
    summary = Text()

    summary.append(f"  Total runs analyzed:     {total_runs}\n")
    summary.append(f"  Graded runs:             {total_graded} ({graded_pct:.1f}%)\n")
    summary.append(f"  Models with traces:      {models_with_traces}\n")

    summary.append("\n  TOP EFFICIENCY (L3 reasoning):\n", style="bold cyan")
    for line in top_efficiency_lines:
        summary.append(f"  {line}\n")

    summary.append("\n  DIMINISHING RETURNS DETECTED:\n", style="bold yellow")
    if dim_returns:
        summary.append(f"  - {plateaus}/{len(dim_returns)} pairs show plateau\n")
        summary.append(f"  - {improves}/{len(dim_returns)} pairs improve through L5\n")

    summary.append("\n  HYPOTHESIS: Non-linear returns\n", style="bold magenta")
    summary.append(f"  Status: {sig_status}\n")

    console.print(
        Panel(summary, title="BENCHMARK ANALYSIS SUMMARY", border_style="blue", expand=False)
    )


if __name__ == "__main__":
    main()
