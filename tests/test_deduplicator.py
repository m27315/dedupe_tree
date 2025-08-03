"""Tests for deduplication logic."""

import tempfile
from pathlib import Path

from dedupe_tree.deduplicator import Deduplicator, format_size
from dedupe_tree.scanner import FileInfo


def test_format_size():
    """Test human-readable size formatting."""
    assert format_size(0) == "0.0 B"
    assert format_size(512) == "512.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1536) == "1.5 KB"
    assert format_size(1024 * 1024) == "1.0 MB"


def test_analyze_duplicates():
    """Test duplicate analysis logic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with known structure
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "deep" / "nested" / "file2.txt"
        file3 = tmp_path / "shallow" / "file3.txt"

        # Create directories
        file2.parent.mkdir(parents=True)
        file3.parent.mkdir(parents=True)

        # Write same content to all files
        content = "duplicate content"
        file1.write_text(content)
        file2.write_text(content)
        file3.write_text(content)

        # Create FileInfo objects
        files = [FileInfo(f) for f in [file1, file2, file3]]

        # Group by checksum (they should all be the same)
        checksum = files[0].checksum
        duplicate_groups = {checksum: files}

        deduplicator = Deduplicator()
        result = deduplicator.analyze_duplicates(duplicate_groups)

        assert len(result.groups) == 1
        group = result.groups[0]

        # Should keep the shallowest file (file1)
        assert group.keep_file.path == file1

        # Should remove the deeper files
        remove_paths = {f.path for f in group.remove_files}
        assert remove_paths == {file2, file3}

        assert result.total_files_to_remove == 2


def test_path_preference_avoids_undesirable_folders():
    """Test that path preference avoids 'New Folder' and 'Recycle' paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with same content but different paths
        good_file = tmp_path / "documents" / "file.txt"
        new_folder_file = tmp_path / "New Folder" / "file.txt"
        recycle_file = tmp_path / "deep" / "Recycle Bin" / "file.txt"

        # Create directories
        good_file.parent.mkdir(parents=True)
        new_folder_file.parent.mkdir(parents=True)
        recycle_file.parent.mkdir(parents=True)

        # Write same content to all files
        content = "duplicate content"
        good_file.write_text(content)
        new_folder_file.write_text(content)
        recycle_file.write_text(content)

        # Create FileInfo objects
        files = [FileInfo(f) for f in [good_file, new_folder_file, recycle_file]]

        # Group by checksum (they should all be the same)
        checksum = files[0].checksum
        duplicate_groups = {checksum: files}

        deduplicator = Deduplicator()
        result = deduplicator.analyze_duplicates(duplicate_groups)

        assert len(result.groups) == 1
        group = result.groups[0]

        # Should keep the good file (not in New Folder or Recycle)
        assert group.keep_file.path == good_file

        # Should remove the files in undesirable paths
        remove_paths = {f.path for f in group.remove_files}
        assert remove_paths == {new_folder_file, recycle_file}


def test_path_preference_depth_tiebreaker():
    """Test that depth is used as tiebreaker when path preference is equal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with same content, both good paths but different depths
        shallow_file = tmp_path / "file.txt"
        deep_file = tmp_path / "deep" / "nested" / "path" / "file.txt"

        # Create directories
        deep_file.parent.mkdir(parents=True)

        # Write same content to both files
        content = "duplicate content"
        shallow_file.write_text(content)
        deep_file.write_text(content)

        # Create FileInfo objects
        files = [FileInfo(f) for f in [deep_file, shallow_file]]  # Intentionally out of order

        # Group by checksum
        checksum = files[0].checksum
        duplicate_groups = {checksum: files}

        deduplicator = Deduplicator()
        result = deduplicator.analyze_duplicates(duplicate_groups)

        assert len(result.groups) == 1
        group = result.groups[0]

        # Should keep the shallow file (fewer path parts)
        assert group.keep_file.path == shallow_file
        assert group.remove_files[0].path == deep_file


def test_groups_sorted_by_space_saved():
    """Test that duplicate groups are sorted by space saved (largest first)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create small duplicate group
        small1 = tmp_path / "small1.txt"
        small2 = tmp_path / "small2.txt"
        small_content = "small"
        small1.write_text(small_content)
        small2.write_text(small_content)

        # Create large duplicate group
        large1 = tmp_path / "large1.txt"
        large2 = tmp_path / "large2.txt"
        large_content = "large content " * 1000  # Much larger
        large1.write_text(large_content)
        large2.write_text(large_content)

        # Create FileInfo objects
        small_files = [FileInfo(f) for f in [small1, small2]]
        large_files = [FileInfo(f) for f in [large1, large2]]

        # Group by checksum
        small_checksum = small_files[0].checksum
        large_checksum = large_files[0].checksum
        duplicate_groups = {small_checksum: small_files, large_checksum: large_files}

        deduplicator = Deduplicator()
        result = deduplicator.analyze_duplicates(duplicate_groups)

        assert len(result.groups) == 2

        # Groups should be sorted by space saved (largest first)
        first_group = result.groups[0]
        second_group = result.groups[1]

        first_space_saved = sum(f.size for f in first_group.remove_files)
        second_space_saved = sum(f.size for f in second_group.remove_files)

        assert first_space_saved >= second_space_saved

        # The large group should come first
        assert first_group.keep_file.path in {large1, large2}


def test_directory_deduplication():
    """Test directory deduplication functionality."""
    from dedupe_tree.directory_scanner import DirectoryInfo

    # Create mock directory info objects
    dir1 = DirectoryInfo(path=Path("/test/documents"), checksum="abc123", size=1000, file_count=5, depth=2)

    dir2 = DirectoryInfo(
        path=Path("/test/New Folder/documents"), checksum="abc123", size=1000, file_count=5, depth=3  # Should be removed due to "New Folder"
    )

    dir3 = DirectoryInfo(path=Path("/test/backup/documents"), checksum="abc123", size=1000, file_count=5, depth=3)

    # Group by checksum
    duplicate_directories = {"abc123": [dir1, dir2, dir3]}

    deduplicator = Deduplicator()
    result = deduplicator.analyze_duplicates({}, duplicate_directories)

    assert len(result.directory_groups) == 1
    dir_group = result.directory_groups[0]

    # Should keep the best directory (not in "New Folder", shallowest depth)
    assert dir_group.keep_directory.path == Path("/test/documents")

    # Should remove the other two
    remove_paths = {d.path for d in dir_group.remove_directories}
    assert remove_paths == {Path("/test/New Folder/documents"), Path("/test/backup/documents")}

    assert result.total_directories_to_remove == 2


def test_mixed_file_and_directory_deduplication():
    """Test deduplication with both files and directories."""
    from dedupe_tree.directory_scanner import DirectoryInfo

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "copy" / "file1.txt"
        file2.parent.mkdir()

        content = "duplicate content"
        file1.write_text(content)
        file2.write_text(content)

        files = [FileInfo(f) for f in [file1, file2]]
        file_checksum = files[0].checksum
        duplicate_files = {file_checksum: files}

        # Create mock directories
        dir1 = DirectoryInfo(path=Path("/test/dir1"), checksum="dir123", size=2000, file_count=10, depth=2)

        dir2 = DirectoryInfo(path=Path("/test/dir2"), checksum="dir123", size=2000, file_count=10, depth=2)

        duplicate_directories = {"dir123": [dir1, dir2]}

        deduplicator = Deduplicator()
        result = deduplicator.analyze_duplicates(duplicate_files, duplicate_directories)

        # Should have both file and directory duplicates
        assert len(result.groups) == 1
        assert len(result.directory_groups) == 1

        assert result.total_files_to_remove == 1
        assert result.total_directories_to_remove == 1
