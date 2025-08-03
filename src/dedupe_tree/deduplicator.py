"""Duplicate file removal engine with dry-run and report modes."""

import os
import shutil
from pathlib import Path
from typing import NamedTuple

from .directory_scanner import DirectoryInfo
from .scanner import FileInfo


class DuplicateGroup(NamedTuple):
    """A group of duplicate files with the file to keep and files to remove."""

    checksum: str
    keep_file: FileInfo
    remove_files: list[FileInfo]
    total_size: int


class DuplicateDirectoryGroup(NamedTuple):
    """A group of duplicate directories with the directory to keep and directories to remove."""

    checksum: str
    keep_directory: DirectoryInfo
    remove_directories: list[DirectoryInfo]
    total_size: int
    total_files: int


class DeduplicationResult(NamedTuple):
    """Result of deduplication operation."""

    groups: list[DuplicateGroup]
    directory_groups: list[DuplicateDirectoryGroup]
    total_files_to_remove: int
    total_directories_to_remove: int
    total_space_to_free: int
    errors: list[tuple[Path, Exception]]


class Deduplicator:
    """Handles duplicate file removal logic."""

    def __init__(self) -> None:
        self.errors: list[tuple[Path, Exception]] = []

    def _get_path_preference_score(self, item: FileInfo | DirectoryInfo) -> tuple[int, int, str]:
        """
        Calculate path preference score for duplicate file/directory selection.

        Priority (lower scores are better):
        1. Paths WITHOUT 'New Folder' or 'Recycle' (score 0)
        2. Paths WITH 'New Folder' or 'Recycle' (score 1)
        3. Then by depth (shallower is better)
        4. Then alphabetically by path

        Returns:
            Tuple of (undesirable_path_score, depth, path_str) for sorting
        """
        path_str = str(item.path).lower()

        # Check if path contains undesirable patterns
        undesirable_patterns = ["new folder", "recycle"]
        has_undesirable = any(pattern in path_str for pattern in undesirable_patterns)

        # Score: 0 for good paths, 1 for paths with undesirable patterns
        undesirable_score = 1 if has_undesirable else 0

        return (undesirable_score, item.depth, str(item.path))

    def analyze_duplicates(
        self, duplicate_groups: dict[str, list[FileInfo]], duplicate_directories: dict[str, list[DirectoryInfo]] | None = None
    ) -> DeduplicationResult:
        """
        Analyze duplicate groups and determine which files/directories to keep/remove.

        Strategy:
        1. Prefer paths WITHOUT 'New Folder' or 'Recycle' in the name
        2. Then prefer items with the shallowest nesting depth (fewest path parts)
        3. If equal, keep the first one alphabetically

        Args:
            duplicate_groups: Dictionary mapping checksums to lists of duplicate files
            duplicate_directories: Dictionary mapping checksums to lists of duplicate directories

        Returns:
            DeduplicationResult with analysis of what would be removed
        """
        # Analyze file duplicates
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

        # Analyze directory duplicates
        directory_groups: list[DuplicateDirectoryGroup] = []
        total_directories_to_remove = 0

        if duplicate_directories:
            for checksum, directories in duplicate_directories.items():
                if len(directories) < 2:
                    continue  # Skip non-duplicates

                # Sort by same criteria as files
                sorted_directories = sorted(directories, key=self._get_path_preference_score)

                keep_directory = sorted_directories[0]
                remove_directories = sorted_directories[1:]

                # Calculate total metrics
                group_size = sum(d.size for d in directories)
                group_files = sum(d.file_count for d in directories)
                space_to_free_dirs = sum(d.size for d in remove_directories)

                dir_group = DuplicateDirectoryGroup(
                    checksum=checksum,
                    keep_directory=keep_directory,
                    remove_directories=remove_directories,
                    total_size=group_size,
                    total_files=group_files,
                )

                directory_groups.append(dir_group)
                total_directories_to_remove += len(remove_directories)
                total_space_to_free += space_to_free_dirs

        # Sort groups by space to be freed (descending order - largest savings first)
        groups.sort(key=lambda g: sum(f.size for f in g.remove_files), reverse=True)
        directory_groups.sort(key=lambda g: sum(d.size for d in g.remove_directories), reverse=True)

        return DeduplicationResult(
            groups=groups,
            directory_groups=directory_groups,
            total_files_to_remove=total_files_to_remove,
            total_directories_to_remove=total_directories_to_remove,
            total_space_to_free=total_space_to_free,
            errors=self.errors.copy(),
        )

    def execute_removal(self, result: DeduplicationResult, dry_run: bool = True) -> tuple[list[Path], list[Path]]:
        """
        Replace duplicate files and directories with symbolic links.

        Args:
            result: DeduplicationResult from analyze_duplicates
            dry_run: If True, don't actually create symbolic links

        Returns:
            Tuple of (linked_files, linked_directories)
        """
        linked_files: list[Path] = []
        linked_directories: list[Path] = []

        # Replace duplicate files with symbolic links
        for group in result.groups:
            for file_info in group.remove_files:
                try:
                    if not dry_run:
                        # Remove the duplicate file
                        os.remove(file_info.path)
                        # Create symbolic link to the kept file
                        os.symlink(group.keep_file.path, file_info.path)
                    linked_files.append(file_info.path)

                except (OSError, PermissionError) as e:
                    self.errors.append((file_info.path, e))

        # Replace duplicate directories with symbolic links
        for dir_group in result.directory_groups:
            for dir_info in dir_group.remove_directories:
                try:
                    if not dry_run:
                        # Remove the duplicate directory
                        shutil.rmtree(dir_info.path)
                        # Create symbolic link to the kept directory
                        os.symlink(dir_group.keep_directory.path, dir_info.path)
                    linked_directories.append(dir_info.path)

                except (OSError, PermissionError) as e:
                    self.errors.append((dir_info.path, e))

        return linked_files, linked_directories

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
