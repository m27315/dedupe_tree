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

## Legal Disclaimer

**USE AT YOUR OWN RISK.** This software is provided "as is" without warranty of any kind. The authors and contributors are not responsible for any data loss, corruption, or damage that may result from downloading, installing, or using this tool. 

This tool modifies files and directories on your system by creating symbolic links and potentially removing duplicate files. While it includes safety features like dry-run mode by default, users are strongly advised to:

- Backup important data before using this tool
- Test the tool on non-critical data first
- Carefully review the dry-run output before executing actual operations
- Understand that file operations cannot always be undone

By using this software, you acknowledge and accept full responsibility for any consequences that may arise from its use.