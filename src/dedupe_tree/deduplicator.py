"""Duplicate file removal engine with dry-run and report modes."""

import os
from pathlib import Path
from typing import NamedTuple

from .scanner import FileInfo


class DuplicateGroup(NamedTuple):
    """A group of duplicate files with the file to keep and files to remove."""

    checksum: str
    keep_file: FileInfo
    remove_files: list[FileInfo]
    total_size: int


class DeduplicationResult(NamedTuple):
    """Result of deduplication operation."""

    groups: list[DuplicateGroup]
    total_files_to_remove: int
    total_space_to_free: int
    errors: list[tuple[Path, Exception]]


class Deduplicator:
    """Handles duplicate file removal logic."""

    def __init__(self) -> None:
        self.errors: list[tuple[Path, Exception]] = []

    def _get_path_preference_score(self, file_info: FileInfo) -> tuple[int, int, str]:
        """
        Calculate path preference score for duplicate file selection.

        Priority (lower scores are better):
        1. Paths WITHOUT 'New Folder' or 'Recycle' (score 0)
        2. Paths WITH 'New Folder' or 'Recycle' (score 1)
        3. Then by depth (shallower is better)
        4. Then alphabetically by path

        Returns:
            Tuple of (undesirable_path_score, depth, path_str) for sorting
        """
        path_str = str(file_info.path).lower()

        # Check if path contains undesirable patterns
        undesirable_patterns = ['new folder', 'recycle']
        has_undesirable = any(pattern in path_str for pattern in undesirable_patterns)

        # Score: 0 for good paths, 1 for paths with undesirable patterns
        undesirable_score = 1 if has_undesirable else 0

        return (undesirable_score, file_info.depth, str(file_info.path))

    def analyze_duplicates(self, duplicate_groups: dict[str, list[FileInfo]]) -> DeduplicationResult:
        """
        Analyze duplicate groups and determine which files to keep/remove.

        Strategy:
        1. Prefer paths WITHOUT 'New Folder' or 'Recycle' in the name
        2. Then prefer files with the shallowest nesting depth (fewest path parts)
        3. If equal, keep the first one alphabetically

        Args:
            duplicate_groups: Dictionary mapping checksums to lists of duplicate files

        Returns:
            DeduplicationResult with analysis of what would be removed
        """
        groups: list[DuplicateGroup] = []
        total_files_to_remove = 0
        total_space_to_free = 0

        for checksum, files in duplicate_groups.items():
            if len(files) < 2:
                continue  # Skip non-duplicates

            # Sort by path preference score (avoiding undesirable paths first),
            # then by depth (ascending), then by path (alphabetically)
            sorted_files = sorted(files, key=self._get_path_preference_score)

            keep_file = sorted_files[0]  # Best file according to our criteria
            remove_files = sorted_files[1:]  # All others

            # Calculate total size of files in this group
            group_size = sum(f.size for f in files)
            space_to_free = sum(f.size for f in remove_files)

            group = DuplicateGroup(checksum=checksum, keep_file=keep_file, remove_files=remove_files, total_size=group_size)

            groups.append(group)
            total_files_to_remove += len(remove_files)
            total_space_to_free += space_to_free

        # Sort groups by space to be freed (descending order - largest savings first)
        groups.sort(key=lambda g: sum(f.size for f in g.remove_files), reverse=True)

        return DeduplicationResult(
            groups=groups, total_files_to_remove=total_files_to_remove, total_space_to_free=total_space_to_free, errors=self.errors.copy()
        )

    def execute_removal(self, result: DeduplicationResult, dry_run: bool = True) -> list[Path]:
        """
        Execute the actual file removal.

        Args:
            result: DeduplicationResult from analyze_duplicates
            dry_run: If True, don't actually delete files

        Returns:
            List of files that were removed (or would be removed in dry-run)
        """
        removed_files: list[Path] = []

        for group in result.groups:
            for file_info in group.remove_files:
                try:
                    if not dry_run:
                        os.remove(file_info.path)
                    removed_files.append(file_info.path)

                except (OSError, PermissionError) as e:
                    self.errors.append((file_info.path, e))

        return removed_files

    def clear_errors(self) -> None:
        """Clear accumulated errors."""
        self.errors.clear()


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    size_float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} PB"
