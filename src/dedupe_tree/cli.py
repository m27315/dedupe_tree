"""Command-line interface for dedupe-tree."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .deduplicator import DeduplicationResult, Deduplicator, format_size
from .scanner import FileScanner

console = Console()


@click.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--delete", is_flag=True, help="Actually delete duplicate files (default is dry-run with report)")
@click.option("--extensions", help="Comma-separated list of file extensions to include (e.g., '.txt,.py,.md')")
@click.option("--min-size", type=int, default=0, help="Minimum file size in bytes to consider (default: 0)")
@click.option("--log-file", type=click.Path(path_type=Path), help="Write output to a log file")
def main(directory: Path, delete: bool, extensions: str | None, min_size: int, log_file: Path | None) -> None:
    """
    Find and remove duplicate files based on SHA256 checksums.

    By default, runs in dry-run mode with comprehensive reporting.
    Use --delete to actually delete files.

    Strategy: Keeps files with the shallowest nesting depth.
    """
    start_time = time.time()

    # Set up console for potential log file output
    if log_file:
        log_console = Console(file=open(log_file, 'w'), width=120)
        # Use a custom function to write to both console and log
        def dual_print(content, **kwargs) -> None:
            console.print(content, **kwargs)
            log_console.print(content, **kwargs)
        print_func = dual_print
    else:
        print_func = console.print

    # Parse extensions filter
    ext_filter: set[str] | None = None
    if extensions:
        ext_filter = {ext.strip().lower() for ext in extensions.split(",")}
        if not all(ext.startswith(".") for ext in ext_filter):
            print_func("[red]Error: Extensions must start with a dot (e.g., '.txt')[/red]")
            raise click.Abort()

    # Display mode
    mode = "DELETE" if delete else "DRY RUN"
    mode_color = "red" if delete else "yellow"

    print_func(
        Panel(
            f"[bold]{mode} MODE[/bold]\n"
            f"Directory: {directory}\n"
            f"Extensions: {extensions or 'All files'}\n"
            f"Min size: {format_size(min_size)}",
            title=f"[{mode_color}]Dedupe Tree[/{mode_color}]",
            border_style=mode_color,
        )
    )

    # Scan files
    scanner = FileScanner()

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        scan_task = progress.add_task("Scanning files...", total=None)
        scanner.scan_directory(directory, ext_filter)
        progress.update(scan_task, description=f"Found {len(scanner.scanned_files)} files")

    # Filter by minimum size
    if min_size > 0:
        original_count = len(scanner.scanned_files)
        scanner.scanned_files = [f for f in scanner.scanned_files if f.size >= min_size]
        filtered_count = original_count - len(scanner.scanned_files)
        if filtered_count > 0:
            print_func(f"[dim]Filtered out {filtered_count} files smaller than " f"{format_size(min_size)}[/dim]")

    if not scanner.scanned_files:
        print_func("[yellow]No files found to process.[/yellow]")
        return

    # Find duplicates
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        dup_task = progress.add_task("Calculating checksums and finding duplicates...", total=None)
        duplicate_groups = scanner.get_duplicates()
        progress.update(dup_task, description="Analyzing duplicates...")

    if not duplicate_groups:
        print_func("[green]✓ No duplicate files found![/green]")
        return

    # Analyze what to remove
    deduplicator = Deduplicator()
    result = deduplicator.analyze_duplicates(duplicate_groups)

    # Display summary
    print_func("\n[bold]Summary:[/bold]")
    print_func(f"• Total duplicate groups: {len(result.groups)}")
    print_func(f"• Files to remove: {result.total_files_to_remove}")
    print_func(f"• Space to free: [green]{format_size(result.total_space_to_free)}[/green]")

    if result.errors:
        print_func(f"• Errors encountered: [red]{len(result.errors)}[/red]")

    # Show detailed report (always enabled)
    show_detailed_report(result, print_func)

    # Show errors if any
    if result.errors:
        print_func("\n[red]Errors:[/red]")
        for path, error in result.errors:
            print_func(f"  {path}: {error}")

    # Delete files or show dry run summary
    if delete:
        if not click.confirm(f"\nReally delete {result.total_files_to_remove} files?"):
            print_func("[yellow]Aborted.[/yellow]")
            return

        removed_files = deduplicator.execute_removal(result, dry_run=False)
        print_func(f"\n[green]✓ Removed {len(removed_files)} duplicate files[/green]")

        if deduplicator.errors:
            print_func(f"[red]Failed to remove {len(deduplicator.errors)} files[/red]")
            for path, error in deduplicator.errors:
                print_func(f"  {path}: {error}")
    else:
        # Comprehensive dry-run summary
        show_dry_run_summary(result, scanner, print_func)

    # Calculate and display total time
    end_time = time.time()
    total_time = end_time - start_time
    print_func(f"\n[dim]Total time: {total_time:.2f} seconds[/dim]")

    # Close log file if opened
    if log_file:
        log_console.file.close()


def show_detailed_report(result: DeduplicationResult, print_func: Callable[..., Any] = console.print) -> None:
    """Show detailed report of all duplicate groups."""
    print_func("\n[bold]Detailed Report:[/bold]")

    for i, group in enumerate(result.groups, 1):
        table = Table(
            title=(f"Group {i}: {group.checksum[:16]}... " f"({format_size(group.total_size)} total)"), show_header=True, header_style="bold magenta"
        )
        table.add_column("Status", style="bold")
        table.add_column("Depth", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Path")

        # Add keep file
        table.add_row("[green]KEEP[/green]", str(group.keep_file.depth), format_size(group.keep_file.size), str(group.keep_file.path))

        # Add remove files
        for file_info in group.remove_files:
            table.add_row("[red]REMOVE[/red]", str(file_info.depth), format_size(file_info.size), str(file_info.path))

        print_func(table)
        print_func()


def show_dry_run_summary(result: DeduplicationResult, scanner: FileScanner, print_func: Callable[..., Any] = console.print) -> None:
    """Show comprehensive summary for dry-run mode."""
    # Calculate total file statistics
    total_files_scanned = len(scanner.scanned_files)
    total_unique_files = total_files_scanned - result.total_files_to_remove
    unique_files_with_duplicates = len(result.groups)

    # Calculate space statistics
    total_space_scanned = sum(f.size for f in scanner.scanned_files)
    total_space_after_cleanup = total_space_scanned - result.total_space_to_free
    space_savings_percent = (result.total_space_to_free / total_space_scanned * 100) if total_space_scanned > 0 else 0

    print_func("\n" + "="*60)
    print_func(Panel(
        f"[bold green]DRY RUN COMPLETE - COMPREHENSIVE SUMMARY[/bold green]\n\n"
        f"[bold]File Analysis:[/bold]\n"
        f"• Total files scanned: [cyan]{total_files_scanned:,}[/cyan]\n"
        f"• Unique files found: [green]{total_unique_files:,}[/green]\n"
        f"• Files with duplicates: [yellow]{unique_files_with_duplicates:,}[/yellow]\n"
        f"• Total duplicate groups: [red]{len(result.groups):,}[/red]\n"
        f"• Duplicate files to remove: [red]{result.total_files_to_remove:,}[/red]\n\n"
        f"[bold]Space Analysis:[/bold]\n"
        f"• Total space scanned: [cyan]{format_size(total_space_scanned)}[/cyan]\n"
        f"• Space to be freed: [green]{format_size(result.total_space_to_free)}[/green]\n"
        f"• Space after cleanup: [blue]{format_size(total_space_after_cleanup)}[/blue]\n"
        f"• Space savings: [green]{space_savings_percent:.1f}%[/green]\n\n"
        f"[bold]Next Steps:[/bold]\n"
        f"• Review the detailed report above\n"
        f"• Run with [yellow]--delete[/yellow] to perform the actual deletion\n"
        f"• Use [yellow]--extensions[/yellow] or [yellow]--min-size[/yellow] to filter results",
        title="[yellow]Dry Run Summary[/yellow]",
        border_style="yellow"
    ))

    if result.errors:
        print_func(f"\n[red]⚠ {len(result.errors)} errors encountered during analysis[/red]")

    print_func("[yellow]No files were modified. Use --delete to actually delete duplicates.[/yellow]")


if __name__ == "__main__":
    main()
