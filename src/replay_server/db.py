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


# ============================================================================
# Observation Functions
# ============================================================================

# Maximum observations to keep per user (LRU cleanup)
MAX_OBSERVATIONS_PER_USER = 20


def add_observation(
    user_id: Optional[str],
    bar_index: int,
    event_context: str,
    text: str,
    screenshot: Optional[bytes] = None
) -> int:
    """
    Add an observation to the database with LRU cleanup.

    In local mode (user_id=None), uses 'local' as the user_id for consistency.
    After inserting, deletes older observations to keep only the latest 20 per user.

    Args:
        user_id: The user's ID (or None for local mode).
        bar_index: The bar index when observation was made.
        event_context: JSON string of event context/snapshot.
        text: The observation text.
        screenshot: Optional PNG screenshot bytes.

    Returns:
        The ID of the inserted observation.
    """
    # Use 'local' for local mode (no authentication)
    effective_user_id = user_id or "local"

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO observations (user_id, bar_index, event_context, text, screenshot)
            VALUES (?, ?, ?, ?, ?)
            """,
            (effective_user_id, bar_index, event_context, text, screenshot)
        )
        observation_id = cursor.lastrowid

        # LRU cleanup - keep only latest MAX_OBSERVATIONS_PER_USER (by id, not timestamp)
        conn.execute(
            """
            DELETE FROM observations
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM observations
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (effective_user_id, effective_user_id, MAX_OBSERVATIONS_PER_USER)
        )

        conn.commit()
        logger.info(f"Added observation {observation_id} for user {effective_user_id}")
        return observation_id
    finally:
        conn.close()


def get_user_observations(user_id: Optional[str], limit: int = 20) -> list[dict]:
    """
    Get observations for a user, ordered by most recent first.

    In local mode (user_id=None), returns observations for 'local' user.

    Args:
        user_id: The user's ID (or None for local mode).
        limit: Maximum number of observations to return.

    Returns:
        List of observation dicts with id, bar_index, event_context, text,
        has_screenshot, and created_at.
    """
    effective_user_id = user_id or "local"

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            SELECT id, bar_index, event_context, text,
                   CASE WHEN screenshot IS NOT NULL THEN 1 ELSE 0 END as has_screenshot,
                   created_at
            FROM observations
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (effective_user_id, limit)
        )

        observations = []
        for row in cursor.fetchall():
            observations.append({
                "id": row["id"],
                "bar_index": row["bar_index"],
                "event_context": row["event_context"],
                "text": row["text"],
                "has_screenshot": bool(row["has_screenshot"]),
                "created_at": row["created_at"],
            })

        return observations
    finally:
        conn.close()


def get_observation_screenshot(observation_id: int, user_id: Optional[str]) -> Optional[bytes]:
    """
    Get the screenshot for an observation.

    Args:
        observation_id: The observation ID.
        user_id: The user's ID (for access control, or None for local mode).

    Returns:
        Screenshot bytes or None if not found/no access.
    """
    effective_user_id = user_id or "local"

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            SELECT screenshot FROM observations
            WHERE id = ? AND user_id = ?
            """,
            (observation_id, effective_user_id)
        )
        row = cursor.fetchone()
        return row["screenshot"] if row else None
    finally:
        conn.close()
