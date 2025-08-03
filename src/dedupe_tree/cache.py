"""File checksum cache database."""

import sqlite3
from pathlib import Path


class ChecksumCache:
    """SQLite-based cache for file checksums and metadata."""

    def __init__(self, cache_path: Path | None = None) -> None:
        """
        Initialize cache database.

        Args:
            cache_path: Path to SQLite database file. If None, uses default location.
        """
        if cache_path is None:
            # Use XDG cache directory or fallback to home
            cache_dir = Path.home() / ".cache" / "dedupe-tree"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "checksums.db"

        self.cache_path = cache_path
        self._connection: sqlite3.Connection | None = None
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the database schema."""
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_cache (
                file_path TEXT PRIMARY KEY,
                file_size INTEGER NOT NULL,
                modification_time REAL NOT NULL,
                checksum TEXT NOT NULL
            )
        """
        )

        # Create index for faster lookups
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_modification_time
            ON file_cache(modification_time)
        """
        )
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection, creating if needed."""
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.cache_path))
            # Enable WAL mode for better performance
            self._connection.execute("PRAGMA journal_mode=WAL")
        return self._connection

    def get_checksum(self, file_path: Path, file_size: int, modification_time: float) -> str | None:
        """
        Get cached checksum for a file if it's still valid.

        Args:
            file_path: Path to the file
            file_size: Current file size
            modification_time: Current file modification time

        Returns:
            Cached checksum if valid, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT checksum FROM file_cache
            WHERE file_path = ? AND file_size = ? AND modification_time = ?
            """,
            (str(file_path), file_size, modification_time),
        )

        row = cursor.fetchone()
        return row[0] if row else None

    def store_checksum(self, file_path: Path, file_size: int, modification_time: float, checksum: str) -> None:
        """
        Store checksum in cache.

        Args:
            file_path: Path to the file
            file_size: File size in bytes
            modification_time: File modification time
            checksum: SHA256 checksum
        """
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO file_cache
            (file_path, file_size, modification_time, checksum)
            VALUES (?, ?, ?, ?)
            """,
            (str(file_path), file_size, modification_time, checksum),
        )
        conn.commit()

    def cleanup_stale_entries(self, max_age_days: int = 30) -> int:
        """
        Remove cache entries older than max_age_days.

        Args:
            max_age_days: Maximum age in days for cache entries

        Returns:
            Number of entries removed
        """
        import time

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM file_cache WHERE modification_time < ?", (cutoff_time,))
        conn.commit()
        return cursor.rowcount

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        conn = self._get_connection()

        cursor = conn.execute("SELECT COUNT(*) FROM file_cache")
        total_entries = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(DISTINCT checksum) FROM file_cache")
        unique_checksums = cursor.fetchone()[0]

        return {"total_entries": total_entries, "unique_checksums": unique_checksums}

    def clear_cache(self) -> None:
        """Clear all cache entries."""
        conn = self._get_connection()
        conn.execute("DELETE FROM file_cache")
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "ChecksumCache":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()
