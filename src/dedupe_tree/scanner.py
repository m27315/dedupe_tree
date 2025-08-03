"""File scanning and checksum calculation."""

import subprocess
from pathlib import Path

from .cache import ChecksumCache


class FileInfo:
    """Information about a file including its checksum and depth."""

    def __init__(self, path: Path, cache: ChecksumCache | None = None) -> None:
        self.path = path
        stat = path.stat()
        self.size = stat.st_size
        self.modification_time = stat.st_mtime
        self.depth = len(path.parts) - 1  # Subtract 1 for root
        self._checksum: str | None = None
        self._cache = cache

    @property
    def checksum(self) -> str:
        """Calculate SHA256 checksum lazily, using cache if available."""
        if self._checksum is None:
            # Try to get from cache first
            if self._cache:
                cached_checksum = self._cache.get_checksum(self.path, self.size, self.modification_time)
                if cached_checksum:
                    self._checksum = cached_checksum
                    return self._checksum

            # Calculate and cache the checksum
            self._checksum = self._calculate_checksum()

            # Store in cache if available and calculation was successful
            if self._cache and self._checksum:
                self._cache.store_checksum(self.path, self.size, self.modification_time, self._checksum)

        return self._checksum

    def _calculate_checksum(self) -> str:
        """Calculate SHA256 checksum of the file using sha256sum."""
        try:
            result = subprocess.run(["sha256sum", str(self.path)], capture_output=True, text=True, check=True)
            # sha256sum output format: "checksum  filename"
            checksum = result.stdout.split()[0]
            return checksum
        except (subprocess.CalledProcessError, FileNotFoundError, IndexError) as e:
            # Fall back to a descriptive error that will be caught by the caller
            raise OSError(f"Failed to calculate checksum for {self.path}: {e}") from e

    def __repr__(self) -> str:
        return f"FileInfo(path={self.path}, size={self.size}, depth={self.depth})"


class FileScanner:
    """Scans directories and builds file information with checksums."""

    def __init__(self, cache: ChecksumCache | None = None) -> None:
        self.scanned_files: list[FileInfo] = []
        self.errors: list[tuple[Path, Exception]] = []
        self._cache = cache or ChecksumCache()

    def scan_directory(self, root_path: Path, extensions: set[str] | None = None) -> None:
        """
        Recursively scan directory for files.

        Args:
            root_path: Directory to scan
            extensions: Optional set of file extensions to include
                (e.g., {'.txt', '.py'})
        """
        if not root_path.exists():
            raise FileNotFoundError(f"Directory not found: {root_path}")

        if not root_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root_path}")

        for path in root_path.rglob("*"):
            if path.is_file():
                try:
                    # Skip if extensions filter is specified and file doesn't match
                    if extensions and path.suffix.lower() not in extensions:
                        continue

                    file_info = FileInfo(path, self._cache)
                    self.scanned_files.append(file_info)

                except (OSError, PermissionError) as e:
                    self.errors.append((path, e))

    def get_duplicates(self) -> dict[str, list[FileInfo]]:
        """
        Group files by checksum to identify duplicates.

        Returns:
            Dictionary mapping checksums to lists of files with that checksum
        """
        checksum_groups: dict[str, list[FileInfo]] = {}

        for file_info in self.scanned_files:
            try:
                checksum = file_info.checksum
                if checksum not in checksum_groups:
                    checksum_groups[checksum] = []
                checksum_groups[checksum].append(file_info)
            except (OSError, PermissionError) as e:
                self.errors.append((file_info.path, e))

        # Return only groups with duplicates (more than 1 file)
        return {k: v for k, v in checksum_groups.items() if len(v) > 1}

    def clear(self) -> None:
        """Clear scanned files and errors."""
        self.scanned_files.clear()
        self.errors.clear()

    def cleanup_cache(self, max_age_days: int = 30) -> int:
        """Clean up stale cache entries."""
        return self._cache.cleanup_stale_entries(max_age_days)

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return self._cache.get_cache_stats()

    def close(self) -> None:
        """Close cache database connection."""
        if self._cache:
            self._cache.close()

    def __enter__(self) -> "FileScanner":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()
