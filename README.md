# Dedupe Tree

Find and remove duplicate files based on SHA256 checksums, prioritizing removal of deeply nested files.

## Installation

```bash
uv sync --dev
```

## Usage

```bash
# Dry run (default) - shows what would be deleted
uv run dedupe-tree /path/to/directory

# Actually delete duplicates
uv run dedupe-tree /path/to/directory --execute

# Report mode with detailed output
uv run dedupe-tree /path/to/directory --report
```

## Development

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Format code
uv run black .

# Lint code
uv run ruff check .

# Type check
uv run mypy src/
```