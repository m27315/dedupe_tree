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
from .directory_scanner import DirectoryScanner
from .scanner import FileScanner

console = Console()


@click.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--delete", is_flag=True, help="Actually delete duplicate files/directories (default is dry-run with report)")
@click.option("--extensions", help="Comma-separated list of file extensions to include (e.g., '.txt,.py,.md')")
@click.option("--min-size", type=int, default=0, help="Minimum file size in bytes to consider (default: 0)")
@click.option("--min-files", type=int, default=2, help="Minimum files in directory to consider for directory deduplication (default: 2)")
@click.option("--log-file", type=click.Path(path_type=Path), help="Write output to a log file")
def main(directory: Path, delete: bool, extensions: str | None, min_size: int, min_files: int, log_file: Path | None) -> None:
    """
    Find and remove duplicate files and directory trees based on SHA256 checksums.

    By default, runs in dry-run mode with comprehensive reporting.
    Use --delete to actually delete files/directories.

    Strategy: Keeps files/directories with the shallowest nesting depth.
    """
    start_time = time.time()

    # Set up console for potential log file output
    if log_file:
        log_console = Console(file=open(log_file, "w"), width=120)

        # Use a custom function to write to both console and log
        def dual_print(content: object, **kwargs: object) -> None:
            console.print(content, **kwargs)  # type: ignore[arg-type]
            log_console.print(content, **kwargs)  # type: ignore[arg-type]

        print_func = dual_print
    else:
        print_func = console.print  # type: ignore[assignment]

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

    info_text = (
        f"[bold]{mode} MODE - Files & Directory Trees[/bold]\n"
        f"Directory: {directory}\n"
        f"Extensions: {extensions or 'All files'}\n"
        f"Min file size: {format_size(min_size)}\n"
        f"Min files per directory: {min_files}"
    )

    print_func(
        Panel(
            info_text,
            title=f"[{mode_color}]Dedupe Tree[/{mode_color}]",
            border_style=mode_color,
        )
    )

    # Scan both files and directories
    scanner = FileScanner()
    dir_scanner = DirectoryScanner()

    # Scan files
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        scan_task = progress.add_task("Scanning files...", total=None)
        scanner.scan_directory(directory, ext_filter)
        progress.update(scan_task, description=f"Found {len(scanner.scanned_files)} files")

    # Filter files by minimum size
    if min_size > 0:
        original_count = len(scanner.scanned_files)
        scanner.scanned_files = [f for f in scanner.scanned_files if f.size >= min_size]
        filtered_count = original_count - len(scanner.scanned_files)
        if filtered_count > 0:
            print_func(f"[dim]Filtered out {filtered_count} files smaller than {format_size(min_size)}[/dim]")

    # Scan directory trees
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        scan_task = progress.add_task("Scanning directory trees...", total=None)
        dir_scanner.scan_directory_tree(directory, min_files)
        progress.update(scan_task, description=f"Found {len(dir_scanner.scanned_directories)} directories")

    # Find duplicates
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        dup_task = progress.add_task("Finding duplicates...", total=None)
        duplicate_groups = scanner.get_duplicates()
        duplicate_directories = dir_scanner.get_duplicate_directories()
        progress.update(dup_task, description="Analyzing duplicates...")

    # Check if we found any files or directories to process
    if not scanner.scanned_files and not dir_scanner.scanned_directories:
        print_func("[yellow]No files or directories found to process.[/yellow]")
        return

    # Check if we found any duplicates
    if not duplicate_groups and not duplicate_directories:
        print_func("[green]✓ No duplicate files or directories found![/green]")
        return

    # Analyze what to remove
    deduplicator = Deduplicator()
    result = deduplicator.analyze_duplicates(duplicate_groups, duplicate_directories)

    # Display summary
    print_func("\n[bold]Summary:[/bold]")
    if result.groups:
        print_func(f"• Total duplicate file groups: {len(result.groups)}")
        print_func(f"• Files to remove: {result.total_files_to_remove}")
    if result.directory_groups:
        print_func(f"• Total duplicate directory groups: {len(result.directory_groups)}")
        print_func(f"• Directories to remove: {result.total_directories_to_remove}")
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

    # Delete files/directories or show dry run summary
    if delete:
        total_items = result.total_files_to_remove + result.total_directories_to_remove
        if total_items == 0:
            print_func("[yellow]Nothing to delete.[/yellow]")
            return

        items_desc = []
        if result.total_files_to_remove > 0:
            items_desc.append(f"{result.total_files_to_remove} files")
        if result.total_directories_to_remove > 0:
            items_desc.append(f"{result.total_directories_to_remove} directories")

        item_description = " and ".join(items_desc)

        if not click.confirm(f"\nReally delete {item_description}?"):
            print_func("[yellow]Aborted.[/yellow]")
            return

        removed_files, removed_directories = deduplicator.execute_removal(result, dry_run=False)

        success_messages = []
        if removed_files:
            success_messages.append(f"{len(removed_files)} duplicate files")
        if removed_directories:
            success_messages.append(f"{len(removed_directories)} duplicate directories")

        if success_messages:
            print_func(f"\n[green]✓ Removed {' and '.join(success_messages)}[/green]")

        if deduplicator.errors:
            print_func(f"[red]Failed to remove {len(deduplicator.errors)} items[/red]")
            for path, error in deduplicator.errors:
                print_func(f"  {path}: {error}")
    else:
        # Comprehensive dry-run summary - show both scanner results
        show_dry_run_summary(result, scanner, dir_scanner, print_func)

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

    # Show file duplicates
    for i, group in enumerate(result.groups, 1):
        table = Table(
            title=(f"File Group {i}: {group.checksum[:16]}... " f"({format_size(group.total_size)} total)"),
            show_header=True,
            header_style="bold magenta",
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

    # Show directory duplicates
    for i, dir_group in enumerate(result.directory_groups, 1):
        table = Table(
            title=(
                f"Directory Group {i}: {dir_group.checksum[:16]}... " f"({format_size(dir_group.total_size)} total, {dir_group.total_files} files)"
            ),
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Status", style="bold")
        table.add_column("Depth", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Files", justify="right")
        table.add_column("Path")

        # Add keep directory
        table.add_row(
            "[green]KEEP[/green]",
            str(dir_group.keep_directory.depth),
            format_size(dir_group.keep_directory.size),
            str(dir_group.keep_directory.file_count),
            str(dir_group.keep_directory.path),
        )

        # Add remove directories
        for dir_info in dir_group.remove_directories:
            table.add_row("[red]REMOVE[/red]", str(dir_info.depth), format_size(dir_info.size), str(dir_info.file_count), str(dir_info.path))

        print_func(table)
        print_func()


def show_dry_run_summary(result: DeduplicationResult, file_scanner: Any, dir_scanner: Any, print_func: Callable[..., Any] = console.print) -> None:
    """Show comprehensive summary for dry-run mode."""

    # File statistics
    total_files_scanned = len(file_scanner.scanned_files)
    total_unique_files = total_files_scanned - result.total_files_to_remove
    unique_files_with_duplicates = len(result.groups)

    # Directory statistics
    total_dirs_scanned = len(dir_scanner.scanned_directories)
    total_unique_dirs = total_dirs_scanned - result.total_directories_to_remove
    unique_dirs_with_duplicates = len(result.directory_groups)

    # Calculate combined space statistics
    total_file_space = sum(f.size for f in file_scanner.scanned_files)
    total_dir_space = sum(d.size for d in dir_scanner.scanned_directories)
    total_space_scanned = total_file_space + total_dir_space
    total_space_after_cleanup = total_space_scanned - result.total_space_to_free
    space_savings_percent = (result.total_space_to_free / total_space_scanned * 100) if total_space_scanned > 0 else 0

    # Build analysis text
    analysis_parts = []

    if total_files_scanned > 0:
        analysis_parts.append(
            f"[bold]File Analysis:[/bold]\n"
            f"• Total files scanned: [cyan]{total_files_scanned:,}[/cyan]\n"
            f"• Unique files found: [green]{total_unique_files:,}[/green]\n"
            f"• Files with duplicates: [yellow]{unique_files_with_duplicates:,}[/yellow]\n"
            f"• Duplicate file groups: [red]{len(result.groups):,}[/red]\n"
            f"• Duplicate files to remove: [red]{result.total_files_to_remove:,}[/red]"
        )

    if total_dirs_scanned > 0:
        analysis_parts.append(
            f"[bold]Directory Analysis:[/bold]\n"
            f"• Total directories scanned: [cyan]{total_dirs_scanned:,}[/cyan]\n"
            f"• Unique directories found: [green]{total_unique_dirs:,}[/green]\n"
            f"• Directories with duplicates: [yellow]{unique_dirs_with_duplicates:,}[/yellow]\n"
            f"• Duplicate directory groups: [red]{len(result.directory_groups):,}[/red]\n"
            f"• Duplicate directories to remove: [red]{result.total_directories_to_remove:,}[/red]"
        )

    analysis_text = "\n\n".join(analysis_parts) + "\n\n"

    next_steps_text = (
        "[bold]Next Steps:[/bold]\n"
        "• Review the detailed report above\n"
        "• Run with [yellow]--delete[/yellow] to perform the actual deletion\n"
        "• Use [yellow]--extensions[/yellow], [yellow]--min-size[/yellow], or [yellow]--min-files[/yellow] to filter results"
    )

    print_func("\n" + "=" * 60)
    print_func(
        Panel(
            f"[bold green]DRY RUN COMPLETE - COMPREHENSIVE SUMMARY[/bold green]\n\n"
            f"{analysis_text}"
            f"[bold]Space Analysis:[/bold]\n"
            f"• Total space scanned: [cyan]{format_size(total_space_scanned)}[/cyan]\n"
            f"• Space to be freed: [green]{format_size(result.total_space_to_free)}[/green]\n"
            f"• Space after cleanup: [blue]{format_size(total_space_after_cleanup)}[/blue]\n"
            f"• Space savings: [green]{space_savings_percent:.1f}%[/green]\n\n"
            f"{next_steps_text}",
            title="[yellow]Dry Run Summary[/yellow]",
            border_style="yellow",
        )
    )

    if result.errors:
        print_func(f"\n[red]⚠ {len(result.errors)} errors encountered during analysis[/red]")

    print_func("[yellow]No files or directories were modified. Use --delete to actually delete duplicates.[/yellow]")


if __name__ == "__main__":
    main()
