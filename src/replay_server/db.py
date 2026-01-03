"""
SQLite database layer for multi-tenant observations.

Provides persistent storage for user observations in multi-tenant mode.
Uses WAL mode for better read concurrency with single-writer setup.
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default database path (Fly.io volume mount)
DEFAULT_DB_PATH = Path("/data/fractal.db")

# Module-level database path (can be overridden for local dev)
_db_path: Optional[Path] = None


def get_db_path() -> Path:
    """
    Get the database path.

    In production (Fly.io), uses /data/fractal.db on the mounted volume.
    In local development, falls back to a local path if /data doesn't exist.

    Returns:
        Path to the SQLite database file.
    """
    global _db_path

    if _db_path is not None:
        return _db_path

    # Check if we're in production (volume mounted at /data)
    if DEFAULT_DB_PATH.parent.exists() and DEFAULT_DB_PATH.parent.is_dir():
        _db_path = DEFAULT_DB_PATH
        logger.info(f"Using production database path: {_db_path}")
        return _db_path

    # Local development: use project root
    project_root = Path(__file__).parent.parent.parent
    local_db_dir = project_root / "local_data"
    local_db_dir.mkdir(exist_ok=True)
    _db_path = local_db_dir / "fractal.db"
    logger.info(f"Using local development database path: {_db_path}")
    return _db_path


def set_db_path(path: Path) -> None:
    """
    Override the database path (for testing).

    Args:
        path: Custom path for the SQLite database.
    """
    global _db_path
    _db_path = path
    logger.info(f"Database path set to: {_db_path}")


def get_db() -> sqlite3.Connection:
    """
    Get a database connection.

    Creates a new connection with WAL mode enabled for better
    read concurrency.

    Returns:
        SQLite connection object.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row  # Enable dict-like row access
    return conn


def init_db() -> None:
    """
    Initialize the database schema.

    Creates tables if they don't exist. Safe to call multiple times.
    """
    db_path = get_db_path()
    logger.info(f"Initializing database at {db_path}")

    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY,
                user_id TEXT REFERENCES users(id),
                bar_index INTEGER,
                event_context TEXT,
                text TEXT,
                screenshot BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_observations_user_id
                ON observations(user_id);

            CREATE INDEX IF NOT EXISTS idx_observations_created_at
                ON observations(created_at);
        """)
        conn.commit()
        logger.info("Database schema initialized successfully")
    finally:
        conn.close()
