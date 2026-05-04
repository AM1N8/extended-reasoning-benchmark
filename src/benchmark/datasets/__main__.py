"""CLI entry point for downloading and validating datasets."""

import logging

from rich.console import Console
from rich.table import Table

from benchmark.config import get_settings
from benchmark.datasets.loader import StandardDataset, load_all_datasets

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
console = Console()


def main() -> None:
    """Run the dataset ingestion pipeline."""
    settings = get_settings()
    console.print("[bold cyan]LLM Reasoning Benchmark — Dataset Pipeline[/bold cyan]")
    console.print(f"Output directory: {settings.data_dir}\n")

    # Run the loaders
    results = load_all_datasets(
        output_dir=settings.data_dir,
        questions_per_dataset=5,  # 5 for quick dev iteration, usually 50-100
        force_refresh=True,  # Force download for demonstration
    )

    console.print("\n[bold green]Dataset Summary[/bold green]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Dataset Name", style="cyan")
    table.add_column("Task Category")
    table.add_column("Source")
    table.add_column("Questions", justify="right")
    table.add_column("Output File", style="dim")

    for ds_name, path in results.items():
        try:
            ds = StandardDataset.load(path)
            table.add_row(
                ds.dataset_name,
                ds.task_category,
                ds.source,
                str(len(ds.questions)),
                path.name,
            )
        except Exception as e:
            logger.error("Failed to load %s for summary: %s", path, e)

    console.print(table)


if __name__ == "__main__":
    main()
