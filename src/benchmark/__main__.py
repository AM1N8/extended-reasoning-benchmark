"""CLI entry point for the benchmark pipeline."""

from rich.console import Console

console = Console()


def main() -> None:
    """Run the benchmark pipeline."""
    console.print("[bold green]LLM Reasoning Benchmark[/bold green] — v0.1.0")
    console.print("Use [cyan]just --list[/cyan] to see available commands.")


if __name__ == "__main__":
    main()
