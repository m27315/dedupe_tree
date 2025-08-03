"""Tests for CLI functionality."""

import tempfile
from pathlib import Path

from click.testing import CliRunner

from dedupe_tree.cli import main
from dedupe_tree.deduplicator import DeduplicationResult, DuplicateGroup
from dedupe_tree.scanner import FileInfo


def test_log_file_functionality():
    """Test that log file functionality works correctly with detailed reports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with duplicate content
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        log_file = tmp_path / "output.log"

        content = "duplicate content"
        file1.write_text(content)
        file2.write_text(content)

        runner = CliRunner()
        result = runner.invoke(main, [
            str(tmp_path),
            "--log-file", str(log_file)
        ])

        # Should complete successfully
        assert result.exit_code == 0

        # Log file should be created
        assert log_file.exists()

        # Log file should contain the output
        log_content = log_file.read_text()
        assert "DRY RUN MODE" in log_content
        assert "Detailed Report:" in log_content
        assert "File Group 1:" in log_content
        assert str(file1) in log_content or str(file2) in log_content


def test_show_detailed_report_with_log_file():
    """Test that show_detailed_report works correctly with log file output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        log_file = tmp_path / "test.log"

        # Create mock data
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content")
        file2.write_text("content")

        files = [FileInfo(f) for f in [file1, file2]]
        group = DuplicateGroup(
            checksum="abc123",
            keep_file=files[0],
            remove_files=[files[1]],
            total_size=sum(f.size for f in files)
        )

        result = DeduplicationResult(
            groups=[group],
            directory_groups=[],
            total_files_to_remove=1,
            total_directories_to_remove=0,
            total_space_to_free=files[1].size,
            errors=[]
        )

        # Test the function directly to ensure it doesn't crash with log file
        from rich.console import Console

        from dedupe_tree.cli import show_detailed_report

        with open(log_file, 'w') as f:
            log_console = Console(file=f, width=120)

            def dual_print(content, **kwargs):
                log_console.print(content, **kwargs)

            # This should not raise an error
            show_detailed_report(result, dual_print)

        # Verify log file was written
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "Detailed Report:" in log_content
        assert "File Group 1:" in log_content


def test_cli_help():
    """Test that CLI help works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "Find duplicate files or directory trees" in result.output
    assert "symbolic links" in result.output
    assert "--directories" in result.output
    assert "--delete" in result.output
    assert "--extensions" in result.output
    assert "--min-size" in result.output
    assert "--min-files" in result.output
    assert "--log-file" in result.output


def test_cli_with_extensions_filter():
    """Test CLI with extensions filter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files
        txt_file1 = tmp_path / "file1.txt"
        txt_file2 = tmp_path / "file2.txt"
        py_file = tmp_path / "script.py"

        content = "duplicate content"
        txt_file1.write_text(content)
        txt_file2.write_text(content)
        py_file.write_text(content)

        runner = CliRunner()
        result = runner.invoke(main, [
            str(tmp_path),
            "--extensions", ".txt"
        ])

        assert result.exit_code == 0
        # Should find duplicates among .txt files only
        assert "File Group 1:" in result.output
        assert str(txt_file1) in result.output or str(txt_file2) in result.output
        # Python file should not be mentioned in duplicates
        assert str(py_file) not in result.output


def test_cli_with_min_size_filter():
    """Test CLI with minimum size filter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create small and large duplicate files
        small_file1 = tmp_path / "small1.txt"
        small_file2 = tmp_path / "small2.txt"
        large_file1 = tmp_path / "large1.txt"
        large_file2 = tmp_path / "large2.txt"

        small_content = "x"  # 1 byte
        large_content = "x" * 2000  # 2000 bytes

        small_file1.write_text(small_content)
        small_file2.write_text(small_content)
        large_file1.write_text(large_content)
        large_file2.write_text(large_content)

        runner = CliRunner()
        result = runner.invoke(main, [
            str(tmp_path),
            "--min-size", "1000"  # Only large files should be considered
        ])

        assert result.exit_code == 0
        assert "Filtered out" in result.output  # Should mention filtering small files

        if "File Group 1:" in result.output:
            # If duplicates found, they should be large files only
            assert str(large_file1) in result.output or str(large_file2) in result.output
            assert str(small_file1) not in result.output
            assert str(small_file2) not in result.output


def test_cli_error_handling():
    """Test CLI error handling for invalid paths."""
    runner = CliRunner()
    result = runner.invoke(main, ["/nonexistent/path"])

    # Should fail with non-zero exit code
    assert result.exit_code != 0


def test_cli_symbolic_link_creation():
    """Test that CLI creates symbolic links when --delete is used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with duplicate content
        file1 = tmp_path / "original.txt"
        file2 = tmp_path / "copy.txt"

        content = "duplicate content for symbolic link test"
        file1.write_text(content)
        file2.write_text(content)

        # Verify both files exist initially
        assert file1.exists() and not file1.is_symlink()
        assert file2.exists() and not file2.is_symlink()

        runner = CliRunner()
        # Use --delete flag and automatically confirm with 'y'
        result = runner.invoke(main, [
            str(tmp_path),
            "--delete"
        ], input='y\n')

        # Should complete successfully
        assert result.exit_code == 0
        assert "Replaced" in result.output
        assert "symbolic links" in result.output

        # Both files should still exist
        assert file1.exists()
        assert file2.exists()

        # One should be original, one should be a symbolic link
        # The shallowest (alphabetically first in this case) should be kept
        if file1.name < file2.name:  # file1 should be kept
            assert not file1.is_symlink()
            assert file2.is_symlink()
            assert file2.resolve() == file1
        else:  # file2 should be kept
            assert not file2.is_symlink()
            assert file1.is_symlink()
            assert file1.resolve() == file2

        # Both should still be readable with same content
        assert file1.read_text() == content
        assert file2.read_text() == content


def test_cli_file_mode_default():
    """Test that CLI processes files by default (without --directories flag)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with duplicate content
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        content = "duplicate content"
        file1.write_text(content)
        file2.write_text(content)

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        # Should complete successfully
        assert result.exit_code == 0
        assert "Files Only" in result.output
        assert "File Group 1:" in result.output
        assert "File Analysis:" in result.output
        assert "Directory Analysis:" not in result.output


def test_cli_directory_mode():
    """Test that CLI processes directories when --directories flag is used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create duplicate directories
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        dir1.mkdir()
        dir2.mkdir()

        # Add files to make them detectable as directories with content
        (dir1 / "file1.txt").write_text("content1")
        (dir1 / "file2.txt").write_text("content2")
        (dir2 / "file1.txt").write_text("content1")
        (dir2 / "file2.txt").write_text("content2")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path), "--directories"])

        # Should complete successfully
        assert result.exit_code == 0
        assert "Directory Trees Only" in result.output
        assert "Directory Group 1:" in result.output
        assert "Directory Analysis:" in result.output
        assert "File Analysis:" not in result.output


def test_cli_directory_symbolic_link_creation():
    """Test that CLI creates symbolic links for directories when --directories and --delete are used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create duplicate directories
        dir1 = tmp_path / "original_dir"
        dir2 = tmp_path / "copy_dir"

        dir1.mkdir()
        dir2.mkdir()

        # Add identical files to both directories
        content1 = "content of file 1"
        content2 = "content of file 2"
        (dir1 / "file1.txt").write_text(content1)
        (dir1 / "file2.txt").write_text(content2)
        (dir2 / "file1.txt").write_text(content1)
        (dir2 / "file2.txt").write_text(content2)

        # Verify both directories exist initially
        assert dir1.exists() and dir1.is_dir()
        assert dir2.exists() and dir2.is_dir()

        runner = CliRunner()
        # Use --directories and --delete flags and automatically confirm with 'y'
        result = runner.invoke(main, [
            str(tmp_path),
            "--directories",
            "--delete"
        ], input='y\n')

        # Should complete successfully
        assert result.exit_code == 0
        assert "Replaced" in result.output
        assert "directories" in result.output
        assert "symbolic links" in result.output

        # Both directories should still exist
        assert dir1.exists()
        assert dir2.exists()

        # One should be original, one should be a symbolic link
        # Based on the algorithm, copy_dir is kept and original_dir is removed
        assert not dir2.is_symlink()  # copy_dir is kept
        assert dir1.is_symlink()     # original_dir becomes link
        assert dir1.resolve() == dir2

        # Both should still be accessible with same content
        assert (dir1 / "file1.txt").read_text() == content1
        assert (dir2 / "file1.txt").read_text() == content1
        assert (dir1 / "file2.txt").read_text() == content2
        assert (dir2 / "file2.txt").read_text() == content2


def test_cli_with_min_dir_size_filter():
    """Test CLI with minimum directory size filter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create small and large directories with duplicate content
        small_dir1 = tmp_path / "small1"
        small_dir2 = tmp_path / "small2"
        large_dir1 = tmp_path / "large1"
        large_dir2 = tmp_path / "large2"

        small_dir1.mkdir()
        small_dir2.mkdir()
        large_dir1.mkdir()
        large_dir2.mkdir()

        # Create small files (small directories)
        small_content = "x"  # 1 byte per file
        (small_dir1 / "file1.txt").write_text(small_content)
        (small_dir1 / "file2.txt").write_text(small_content)
        (small_dir2 / "file1.txt").write_text(small_content)
        (small_dir2 / "file2.txt").write_text(small_content)

        # Create large files (large directories)
        large_content = "x" * 1000  # 1000 bytes per file
        (large_dir1 / "file1.txt").write_text(large_content)
        (large_dir1 / "file2.txt").write_text(large_content)
        (large_dir2 / "file1.txt").write_text(large_content)
        (large_dir2 / "file2.txt").write_text(large_content)

        runner = CliRunner()
        result = runner.invoke(main, [
            str(tmp_path),
            "--directories",
            "--min-dir-size", "1500"  # Only large directories should be considered
        ])

        assert result.exit_code == 0
        assert "Filtered out" in result.output  # Should mention filtering small directories

        if "Directory Group 1:" in result.output:
            # If duplicates found, they should be large directories only
            assert str(large_dir1) in result.output or str(large_dir2) in result.output
            assert str(small_dir1) not in result.output
            assert str(small_dir2) not in result.output


def test_cli_help_includes_min_dir_size():
    """Test that CLI help includes --min-dir-size option."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--min-dir-size" in result.output
    assert "Minimum directory size in bytes" in result.output
