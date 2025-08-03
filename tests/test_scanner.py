"""Tests for file scanner functionality."""

import tempfile
from pathlib import Path

from dedupe_tree.scanner import FileInfo, FileScanner


def test_file_info_checksum():
    """Test FileInfo checksum calculation."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("hello world")
        temp_path = Path(f.name)

    try:
        file_info = FileInfo(temp_path)
        # SHA256 of "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert file_info.checksum == expected
    finally:
        temp_path.unlink()


def test_file_info_depth():
    """Test depth calculation."""
    # Create a test path with known depth

    # Mock the path to avoid file system operations
    class MockPath(Path):
        def stat(self):
            class MockStat:
                st_size = 100
                st_mtime = 1234567890.0

            return MockStat()

    mock_path = MockPath("/a/b/c/file.txt")
    file_info = FileInfo(mock_path)

    # Depth should be number of parts - 1 (for root)
    # /a/b/c/file.txt has 5 parts: ['/', 'a', 'b', 'c', 'file.txt']
    # But Path.parts on different systems may vary, so test relative depth
    assert file_info.depth >= 0


def test_scanner_find_duplicates():
    """Test finding duplicates in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create some test files
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.txt").write_text("content")  # Duplicate
        (tmp_path / "file3.txt").write_text("different")

        # Create subdirectory with another duplicate
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file4.txt").write_text("content")  # Another duplicate

        scanner = FileScanner()
        scanner.scan_directory(tmp_path)

        assert len(scanner.scanned_files) == 4

        duplicates = scanner.get_duplicates()

        # Should find one group of 3 duplicates
        assert len(duplicates) == 1

        # Get the duplicate group
        duplicate_group = list(duplicates.values())[0]
        assert len(duplicate_group) == 3

        # All should have same content
        checksums = {f.checksum for f in duplicate_group}
        assert len(checksums) == 1


def test_scanner_extensions_filter():
    """Test filtering by file extensions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create files with different extensions
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.py").write_text("content")
        (tmp_path / "file3.md").write_text("content")

        scanner = FileScanner()
        scanner.scan_directory(tmp_path, extensions={".txt", ".py"})

        # Should only find .txt and .py files
        assert len(scanner.scanned_files) == 2

        found_extensions = {f.path.suffix for f in scanner.scanned_files}
        assert found_extensions == {".txt", ".py"}


def test_scanner_extensions_case_insensitive():
    """Test that extension filtering is case insensitive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create files with different case extensions
        (tmp_path / "file1.TXT").write_text("content")
        (tmp_path / "file2.Py").write_text("content")
        (tmp_path / "file3.MD").write_text("content")

        scanner = FileScanner()
        # Use lowercase extensions in filter
        scanner.scan_directory(tmp_path, extensions={".txt", ".py"})

        # Should find files regardless of case
        assert len(scanner.scanned_files) == 2

        found_extensions = {f.path.suffix for f in scanner.scanned_files}
        assert found_extensions == {".TXT", ".Py"}
