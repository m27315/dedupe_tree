"""Tests for directory scanner functionality."""

import tempfile
from pathlib import Path

from dedupe_tree.directory_scanner import DirectoryInfo, DirectoryScanner


def test_directory_info_basic():
    """Test DirectoryInfo creation and properties."""
    path = Path("/test/dir")
    checksum = "abc123"
    size = 1024
    file_count = 5
    depth = 2

    dir_info = DirectoryInfo(path, checksum, size, file_count, depth)

    assert dir_info.path == path
    assert dir_info.checksum == checksum
    assert dir_info.size == size
    assert dir_info.file_count == file_count
    assert dir_info.depth == depth


def test_directory_scanner_identical_directories():
    """Test scanning and detecting identical directory trees."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create two identical directory trees
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        # Create identical structure and content
        for base_dir in [dir1, dir2]:
            base_dir.mkdir()
            (base_dir / "file1.txt").write_text("content1")
            (base_dir / "file2.txt").write_text("content2")

            subdir = base_dir / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("nested content")

        scanner = DirectoryScanner()
        scanner.scan_directory_tree(tmp_path, min_files=2)

        # Should find directories
        assert len(scanner.scanned_directories) >= 2

        # Check for duplicates
        duplicates = scanner.get_duplicate_directories()

        # Should find duplicate directories
        assert len(duplicates) >= 1

        # Find the group containing our main directories
        main_dir_group = None
        for _checksum, dirs in duplicates.items():
            dir_paths = {d.path for d in dirs}
            if dir1 in dir_paths and dir2 in dir_paths:
                main_dir_group = dirs
                break

        assert main_dir_group is not None
        assert len(main_dir_group) == 2

        # Both directories should have same checksum
        checksums = {d.checksum for d in main_dir_group}
        assert len(checksums) == 1


def test_directory_scanner_different_directories():
    """Test that different directory trees get different checksums."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create two different directory trees
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        # Different content
        dir1.mkdir()
        (dir1 / "file1.txt").write_text("content1")
        (dir1 / "file2.txt").write_text("content2")

        dir2.mkdir()
        (dir2 / "file1.txt").write_text("different content")
        (dir2 / "file2.txt").write_text("content2")

        scanner = DirectoryScanner()
        scanner.scan_directory_tree(tmp_path, min_files=2)

        # Should find both directories
        assert len(scanner.scanned_directories) >= 2

        # Check for duplicates
        duplicates = scanner.get_duplicate_directories()

        # Should NOT find any duplicates between dir1 and dir2
        for _checksum, dirs in duplicates.items():
            dir_paths = {d.path for d in dirs}
            assert not (dir1 in dir_paths and dir2 in dir_paths)


def test_directory_scanner_nested_structure():
    """Test scanning directories with complex nested structures."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create complex nested structure
        base = tmp_path / "complex"
        base.mkdir()

        # Create multiple levels
        (base / "level1" / "level2" / "level3").mkdir(parents=True)
        (base / "level1" / "file.txt").write_text("content")
        (base / "level1" / "level2" / "file2.txt").write_text("content2")
        (base / "level1" / "level2" / "level3" / "deep.txt").write_text("deep content")

        scanner = DirectoryScanner()
        scanner.scan_directory_tree(tmp_path, min_files=1)

        # Should find all directories with at least 1 file
        found_paths = {d.path for d in scanner.scanned_directories}

        # Should include various levels
        assert any("level1" in str(path) for path in found_paths)
        assert any("level2" in str(path) for path in found_paths)
        assert any("level3" in str(path) for path in found_paths)


def test_directory_scanner_min_files_filter():
    """Test minimum files filtering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create directories with different file counts
        dir_with_1_file = tmp_path / "one_file"
        dir_with_3_files = tmp_path / "three_files"

        dir_with_1_file.mkdir()
        (dir_with_1_file / "single.txt").write_text("content")

        dir_with_3_files.mkdir()
        (dir_with_3_files / "file1.txt").write_text("content1")
        (dir_with_3_files / "file2.txt").write_text("content2")
        (dir_with_3_files / "file3.txt").write_text("content3")

        scanner = DirectoryScanner()
        scanner.scan_directory_tree(tmp_path, min_files=2)

        # Should only find directory with 3 files
        found_paths = {d.path for d in scanner.scanned_directories}

        assert dir_with_3_files in found_paths
        assert dir_with_1_file not in found_paths


def test_directory_fingerprint_consistency():
    """Test that directory fingerprints are consistent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create directory
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "a.txt").write_text("content a")
        (test_dir / "b.txt").write_text("content b")

        scanner = DirectoryScanner()
        scanner.scan_directory_tree(tmp_path, min_files=1)

        # Get fingerprint multiple times
        fingerprint1 = scanner.get_directory_fingerprint(test_dir)
        fingerprint2 = scanner.get_directory_fingerprint(test_dir)

        assert fingerprint1 == fingerprint2
        assert fingerprint1 is not None

        # Should contain file information
        assert "a.txt" in fingerprint1
        assert "b.txt" in fingerprint1


def test_directory_scanner_error_handling():
    """Test error handling for inaccessible directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create a normal directory
        normal_dir = tmp_path / "normal"
        normal_dir.mkdir()
        (normal_dir / "file.txt").write_text("content")

        scanner = DirectoryScanner()
        scanner.scan_directory_tree(tmp_path, min_files=1)

        # Should handle the scan without crashing
        assert len(scanner.scanned_directories) >= 1
        # Scanner should track some errors if any occurred
        # (errors list exists even if empty)
        assert hasattr(scanner, "errors")
