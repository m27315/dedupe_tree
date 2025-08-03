# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**dedupe-tree** is a Python CLI tool that finds and removes duplicate files based on SHA256 checksums. It prioritizes keeping files with the shallowest nesting depth (fewest directory levels) and removing more deeply nested duplicates.

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

- **`src/dedupe_tree/deduplicator.py`** - Duplicate analysis and removal logic
  - `Deduplicator`: Analyzes duplicate groups and determines which files to keep/remove
  - Strategy: Keep shallowest file (by path depth), remove deeper nested duplicates

- **`src/dedupe_tree/cli.py`** - Command-line interface using Click and Rich
  - Beautiful terminal output with progress bars and tables
  - Dry-run mode by default for safety
  - Detailed reporting options

### Key Features

- **SHA256-based detection** - Reliable duplicate identification
- **Depth-based removal** - Keeps files closest to root directory
- **Safety first** - Dry-run mode by default, requires `--execute` for actual deletion
- **Rich reporting** - Detailed analysis of duplicates and planned actions
- **Error handling** - Graceful handling of permission errors and inaccessible files
- **Filtering options** - File extension and minimum size filters

## Python Environment

- **Python 3.12+** required
- **uv** for dependency management (replaces pip/poetry)
- **Type hints** throughout codebase with MyPy checking
- **Modern tooling**: Black, Ruff, Pytest

## Usage Examples

```bash
# Dry run (safe, shows what would be deleted)
uv run dedupe-tree /home/user/documents

# Execute with confirmation prompt
uv run dedupe-tree /home/user/documents --execute

# Detailed report of all duplicate groups
uv run dedupe-tree /home/user/documents --report

# Filter by file types
uv run dedupe-tree /home/user/documents --extensions=".jpg,.png,.gif"

# Ignore small files
uv run dedupe-tree /home/user/documents --min-size=1024
```

## Testing Strategy

- Unit tests for core functionality in `tests/`
- Temporary file/directory testing for file operations
- Mock objects for testing without filesystem dependencies