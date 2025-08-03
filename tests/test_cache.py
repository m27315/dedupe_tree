"""Tests for cache functionality."""

import tempfile
import time
from pathlib import Path

from dedupe_tree.cache import ChecksumCache
from dedupe_tree.scanner import FileInfo


def test_cache_basic_operations():
    """Test basic cache operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.db"
        cache = ChecksumCache(cache_path)

        # Test storing and retrieving
        file_path = Path("/test/file.txt")
        file_size = 1024
        mod_time = time.time()
        checksum = "abc123"

        cache.store_checksum(file_path, file_size, mod_time, checksum)
        retrieved = cache.get_checksum(file_path, file_size, mod_time)

        assert retrieved == checksum

        # Test cache miss for different file
        miss = cache.get_checksum(Path("/other/file.txt"), file_size, mod_time)
        assert miss is None

        # Test cache miss for different size
        miss = cache.get_checksum(file_path, 2048, mod_time)
        assert miss is None

        # Test cache miss for different modification time
        miss = cache.get_checksum(file_path, file_size, mod_time + 1)
        assert miss is None

        cache.close()


def test_cache_with_file_info():
    """Test cache integration with FileInfo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cache_path = tmp_path / "test_cache.db"
        test_file = tmp_path / "test.txt"

        # Create a test file
        test_file.write_text("hello world")

        # Create cache and FileInfo
        cache = ChecksumCache(cache_path)
        file_info = FileInfo(test_file, cache)

        # First access should calculate and cache
        checksum1 = file_info.checksum
        assert len(checksum1) == 64  # SHA256 length

        # Create another FileInfo for same file
        file_info2 = FileInfo(test_file, cache)
        checksum2 = file_info2.checksum

        # Should get same checksum from cache
        assert checksum1 == checksum2

        # Verify it's actually in cache
        cached = cache.get_checksum(test_file, file_info.size, file_info.modification_time)
        assert cached == checksum1

        cache.close()


def test_cache_invalidation():
    """Test cache invalidation when file changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cache_path = tmp_path / "test_cache.db"
        test_file = tmp_path / "test.txt"

        # Create initial file
        test_file.write_text("original content")

        cache = ChecksumCache(cache_path)
        file_info1 = FileInfo(test_file, cache)
        checksum1 = file_info1.checksum

        # Modify file (this will change modification time)
        time.sleep(0.1)  # Ensure different modification time
        test_file.write_text("modified content")

        # Create new FileInfo for modified file
        file_info2 = FileInfo(test_file, cache)
        checksum2 = file_info2.checksum

        # Should be different checksums
        assert checksum1 != checksum2

        cache.close()


def test_cache_stats():
    """Test cache statistics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.db"
        cache = ChecksumCache(cache_path)

        # Initially empty
        stats = cache.get_cache_stats()
        assert stats["total_entries"] == 0
        assert stats["unique_checksums"] == 0

        # Add some entries
        cache.store_checksum(Path("/file1.txt"), 100, time.time(), "checksum1")
        cache.store_checksum(Path("/file2.txt"), 200, time.time(), "checksum2")
        cache.store_checksum(Path("/file3.txt"), 300, time.time(), "checksum1")  # Duplicate checksum

        stats = cache.get_cache_stats()
        assert stats["total_entries"] == 3
        assert stats["unique_checksums"] == 2

        cache.close()


def test_cache_cleanup():
    """Test cache cleanup of old entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.db"
        cache = ChecksumCache(cache_path)

        # Add old and new entries
        old_time = time.time() - (35 * 24 * 60 * 60)  # 35 days ago
        new_time = time.time()

        cache.store_checksum(Path("/old_file.txt"), 100, old_time, "old_checksum")
        cache.store_checksum(Path("/new_file.txt"), 200, new_time, "new_checksum")

        # Cleanup entries older than 30 days
        removed = cache.cleanup_stale_entries(30)
        assert removed == 1

        # Only new entry should remain
        stats = cache.get_cache_stats()
        assert stats["total_entries"] == 1

        cache.close()


def test_cache_context_manager():
    """Test cache as context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.db"

        with ChecksumCache(cache_path) as cache:
            cache.store_checksum(Path("/test.txt"), 100, time.time(), "checksum")
            assert cache.get_cache_stats()["total_entries"] == 1

        # Cache should be closed now, but data should persist
        with ChecksumCache(cache_path) as cache2:
            assert cache2.get_cache_stats()["total_entries"] == 1
