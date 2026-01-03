"""
Tests for issue #476: SQLite database setup for multi-tenant mode.

Tests the db.py module for SQLite initialization and schema creation.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.replay_server.db import get_db, init_db, set_db_path, get_db_path


class TestSqliteSetup:
    """Tests for SQLite database setup."""

    def setup_method(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = Path(self.temp_dir) / "test_fractal.db"
        set_db_path(self.temp_db)

    def teardown_method(self):
        """Clean up temporary database and directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_db_returns_connection(self):
        """get_db() should return a valid SQLite connection."""
        conn = get_db()
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_get_db_enables_wal_mode(self):
        """get_db() should enable WAL mode for better concurrency."""
        conn = get_db()
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"
        conn.close()

    def test_get_db_enables_row_factory(self):
        """get_db() should enable sqlite3.Row for dict-like access."""
        conn = get_db()
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_init_db_creates_tables(self):
        """init_db() should create users and observations tables."""
        init_db()

        conn = get_db()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "users" in tables
        assert "observations" in tables

    def test_init_db_creates_indexes(self):
        """init_db() should create indexes for performance."""
        init_db()

        conn = get_db()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_observations_user_id" in indexes
        assert "idx_observations_created_at" in indexes

    def test_init_db_idempotent(self):
        """init_db() should be safe to call multiple times."""
        init_db()
        init_db()  # Should not raise

        conn = get_db()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "users" in tables
        assert "observations" in tables

    def test_users_table_schema(self):
        """Users table should have correct columns."""
        init_db()

        conn = get_db()
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "id" in columns
        assert "email" in columns
        assert "created_at" in columns

    def test_observations_table_schema(self):
        """Observations table should have correct columns."""
        init_db()

        conn = get_db()
        cursor = conn.execute("PRAGMA table_info(observations)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "id" in columns
        assert "user_id" in columns
        assert "bar_index" in columns
        assert "event_context" in columns
        assert "text" in columns
        assert "screenshot" in columns
        assert "created_at" in columns

    def test_can_insert_user(self):
        """Should be able to insert a user record."""
        init_db()

        conn = get_db()
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?)",
            ("user123", "test@example.com")
        )
        conn.commit()

        cursor = conn.execute("SELECT * FROM users WHERE id = ?", ("user123",))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row["id"] == "user123"
        assert row["email"] == "test@example.com"

    def test_can_insert_observation(self):
        """Should be able to insert an observation record."""
        init_db()

        conn = get_db()
        # Insert user first (foreign key)
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?)",
            ("user123", "test@example.com")
        )
        # Insert observation
        conn.execute(
            """INSERT INTO observations
               (user_id, bar_index, event_context, text, screenshot)
               VALUES (?, ?, ?, ?, ?)""",
            ("user123", 42, '{"legs": []}', "Test observation", b"\x89PNG...")
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT * FROM observations WHERE user_id = ?", ("user123",)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row["user_id"] == "user123"
        assert row["bar_index"] == 42
        assert row["text"] == "Test observation"

    def test_set_db_path_overrides_path(self):
        """set_db_path() should override the default database path."""
        custom_path = Path(self.temp_dir) / "custom.db"
        set_db_path(custom_path)

        assert get_db_path() == custom_path

        # Verify database is created at custom path
        init_db()
        assert custom_path.exists()
