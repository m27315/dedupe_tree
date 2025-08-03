"""Directory tree scanning and checksum calculation for duplicate directory detection."""

import hashlib
import subprocess
from pathlib import Path
from typing import NamedTuple

from .cache import ChecksumCache


class DirectoryInfo(NamedTuple):
    """Information about a directory including its contents checksum and metadata."""

    path: Path
    checksum: str
    size: int  # Total size of all files in directory tree
    file_count: int  # Total number of files in directory tree
    depth: int  # Directory nesting depth


class DirectoryScanner:
    """Scans directory trees and calculates checksums for duplicate detection."""

    def __init__(self, cache: ChecksumCache | None = None) -> None:
        self.cache = cache or ChecksumCache()
        self.scanned_directories: list[DirectoryInfo] = []
        self.errors: list[tuple[Path, Exception]] = []
        self._directory_checksums: dict[Path, str] = {}
        self._directory_metadata: dict[Path, tuple[int, int]] = {}  # (size, file_count)

    def scan_directory_tree(self, root_path: Path, min_files: int = 2) -> None:
        """
        Scan directory tree and calculate checksums for all subdirectories.

        Args:
            root_path: Root directory to scan
            min_files: Minimum number of files a directory must contain to be considered
        """
        if not root_path.exists():
            raise FileNotFoundError(f"Directory not found: {root_path}")

        if not root_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root_path}")

        # First pass: Calculate checksums bottom-up
        self._calculate_directory_checksums(root_path)

        # Second pass: Create DirectoryInfo objects for directories with enough files
        for dir_path, checksum in self._directory_checksums.items():
            size, file_count = self._directory_metadata[dir_path]
            if file_count >= min_files:
                depth = len(dir_path.relative_to(root_path).parts)
                dir_info = DirectoryInfo(path=dir_path, checksum=checksum, size=size, file_count=file_count, depth=depth)
                self.scanned_directories.append(dir_info)

    def _calculate_directory_checksums(self, directory: Path) -> str:
        """
        Recursively calculate directory checksums bottom-up.

        Returns:
            SHA256 checksum of the directory's contents
        """
        if directory in self._directory_checksums:
            return self._directory_checksums[directory]

        try:
            entries = []
            total_size = 0
            total_files = 0

            # Get all entries and sort them alphabetically for consistency
            try:
                all_entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
            except (OSError, PermissionError) as e:
                self.errors.append((directory, e))
                # Return a placeholder checksum for inaccessible directories
                placeholder_checksum = hashlib.sha256(f"ERROR:{directory}".encode()).hexdigest()
                self._directory_checksums[directory] = placeholder_checksum
                self._directory_metadata[directory] = (0, 0)
                return placeholder_checksum

            for entry in all_entries:
                try:
                    if entry.is_file():
                        # Calculate file checksum
                        file_checksum = self._get_file_checksum(entry)
                        file_size = entry.stat().st_size
                        entries.append(f"F:{entry.name}:{file_size}:{file_checksum}")
                        total_size += file_size
                        total_files += 1

                    elif entry.is_dir():
                        # Recursively calculate subdirectory checksum
                        subdir_checksum = self._calculate_directory_checksums(entry)
                        entries.append(f"D:{entry.name}:{subdir_checksum}")

                        # Add subdirectory's metadata to totals
                        if entry in self._directory_metadata:
                            subdir_size, subdir_files = self._directory_metadata[entry]
                            total_size += subdir_size
                            total_files += subdir_files

                except (OSError, PermissionError) as e:
                    self.errors.append((entry, e))
                    # Include error entries in checksum to maintain consistency
                    entries.append(f"ERROR:{entry.name}")

            # Create directory fingerprint and calculate checksum
            directory_fingerprint = "\n".join(entries)
            directory_checksum = hashlib.sha256(directory_fingerprint.encode()).hexdigest()

            # Cache the results
            self._directory_checksums[directory] = directory_checksum
            self._directory_metadata[directory] = (total_size, total_files)

            return directory_checksum

        except Exception as e:
            self.errors.append((directory, e))
            # Return error checksum
            error_checksum = hashlib.sha256(f"ERROR:{directory}".encode()).hexdigest()
            self._directory_checksums[directory] = error_checksum
            self._directory_metadata[directory] = (0, 0)
            return error_checksum

    def _get_file_checksum(self, file_path: Path) -> str:
        """Get file checksum, using cache if available."""
        try:
            stat = file_path.stat()
            file_size = stat.st_size
            modification_time = stat.st_mtime

            # Try cache first
            if self.cache:
                cached_checksum = self.cache.get_checksum(file_path, file_size, modification_time)
                if cached_checksum:
                    return cached_checksum

            # Calculate checksum using sha256sum
            result = subprocess.run(["sha256sum", str(file_path)], capture_output=True, text=True, check=True)
            checksum = result.stdout.split()[0]

            # Store in cache
            if self.cache:
                self.cache.store_checksum(file_path, file_size, modification_time, checksum)

            return checksum

        except (subprocess.CalledProcessError, FileNotFoundError, IndexError, OSError):
            # Return a consistent error checksum
            return hashlib.sha256(f"ERROR:{file_path}".encode()).hexdigest()

    def get_duplicate_directories(self) -> dict[str, list[DirectoryInfo]]:
        """
        Group directories by checksum to identify duplicates.

        Returns:
            Dictionary mapping checksums to lists of directories with that checksum
        """
        checksum_groups: dict[str, list[DirectoryInfo]] = {}

        for dir_info in self.scanned_directories:
            if dir_info.checksum not in checksum_groups:
                checksum_groups[dir_info.checksum] = []
            checksum_groups[dir_info.checksum].append(dir_info)

        # Return only groups with duplicates (more than 1 directory)
        return {k: v for k, v in checksum_groups.items() if len(v) > 1}

    def clear(self) -> None:
        """Clear all scanned data."""
        self.scanned_directories.clear()
        self.errors.clear()
        self._directory_checksums.clear()
        self._directory_metadata.clear()

    def get_directory_fingerprint(self, directory: Path) -> str | None:
        """Get the detailed fingerprint string for a directory (for debugging)."""
        if directory not in self._directory_checksums:
            return None

        try:
            entries = []
            all_entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())

            for entry in all_entries:
                if entry.is_file():
                    file_checksum = self._get_file_checksum(entry)
                    file_size = entry.stat().st_size
                    entries.append(f"F:{entry.name}:{file_size}:{file_checksum}")
                elif entry.is_dir() and entry in self._directory_checksums:
                    subdir_checksum = self._directory_checksums[entry]
                    entries.append(f"D:{entry.name}:{subdir_checksum}")

            return "\n".join(entries)

        except Exception:
            return None
