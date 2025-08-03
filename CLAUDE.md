# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**dedupe-tree** is a Python CLI tool that finds duplicate files and directory trees, replacing duplicates with symbolic links based on SHA256 checksums. It analyzes both individual files and entire directory structures, prioritizing keeping files/directories with the shallowest nesting depth (fewest directory levels) and replacing more deeply nested duplicates with symbolic links to the kept versions.

## Development Commands

```bash
# Install dependencies and create virtual environment
uv sync --dev

# Run the application
uv run dedupe-tree /path/to/directory

# Development commands
uv run pytest                    # Run tests
uv run black .                   # Format code
uv run ruff check .              # Lint code
uv run mypy src/                 # Type check

# Install in development mode
uv pip install -e .
```

## Project Architecture

### Core Components

- **`src/dedupe_tree/scanner.py`** - File scanning and SHA256 checksum calculation
  - `FileInfo`: Represents a file with path, size, depth, and lazy checksum calculation
  - `FileScanner`: Recursively scans directories and groups files by checksum

- **`src/dedupe_tree/directory_scanner.py`** - Directory tree scanning and checksum calculation
  - `DirectoryInfo`: Represents a directory with path, checksum, size, file count, and depth
  - `DirectoryScanner`: Recursively scans directory trees and creates hierarchical checksums

- **`src/dedupe_tree/deduplicator.py`** - Duplicate analysis and symbolic link creation logic
  - `Deduplicator`: Analyzes duplicate groups and determines which files/directories to keep/link
  - Strategy: Keep shallowest files/directories (by path depth), replace deeper nested duplicates with symbolic links

- **`src/dedupe_tree/cli.py`** - Command-line interface using Click and Rich
  - Beautiful terminal output with progress bars and tables
  - Dry-run mode by default for safety
  - Detailed reporting options

### Key Features

- **SHA256-based detection** - Reliable duplicate identification for both files and directory trees
- **Hierarchical directory fingerprinting** - Creates checksums for entire directory structures
- **Symbolic link replacement** - Keeps files/directories closest to root directory, replaces duplicates with symbolic links
- **Safety first** - Dry-run mode by default, requires `--delete` to create symbolic links
- **Rich reporting** - Detailed analysis of duplicates and planned actions
- **Error handling** - Graceful handling of permission errors and inaccessible files
- **Comprehensive filtering** - File extension, minimum size, and minimum files per directory filters
- **Performance caching** - SQLite-based caching for faster repeated scans

## Python Environment

- **Python 3.12+** required
- **uv** for dependency management (replaces pip/poetry)
- **Type hints** throughout codebase with MyPy checking
- **Modern tooling**: Black, Ruff, Pytest

## Usage Examples

```bash
# Dry run (safe, shows what would be linked) - analyzes both files and directories
uv run dedupe-tree /home/user/documents

# Replace duplicates with symbolic links (with confirmation prompt)
uv run dedupe-tree /home/user/documents --delete

# Filter by file types
uv run dedupe-tree /home/user/documents --extensions=".jpg,.png,.gif"

# Ignore small files
uv run dedupe-tree /home/user/documents --min-size=1024

# Only consider directories with at least 5 files
uv run dedupe-tree /home/user/documents --min-files=5

# Log output to file
uv run dedupe-tree /home/user/documents --log-file=dedupe.log
```

## Testing Strategy

- Unit tests for core functionality in `tests/`
- Temporary file/directory testing for file operations
- Mock objects for testing without filesystem dependencies