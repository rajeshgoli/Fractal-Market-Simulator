"""
Annotation Storage Layer

JSON-backed persistence for annotation sessions and swing annotations.
Handles file I/O, session management, and data export.

## Single-User Assumption

This storage layer is designed for single-user operation. Concurrent users would
cause race conditions on ground_truth.json writes and potential data loss.

If multi-user becomes a requirement, the storage layer would need:
- File locking on ground_truth.json appends, or
- SQLite/database backend, or
- Per-user ground truth files with merge strategy
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .csv_utils import escape_csv_field
from .models import (
    AnnotationSession, SwingAnnotation, ReviewSession, SwingFeedback,
    REVIEW_SCHEMA_VERSION, PlaybackSession, PlaybackObservation
)

# Ground truth directory structure
GROUND_TRUTH_DIR = Path("ground_truth")
GROUND_TRUTH_FILE = GROUND_TRUTH_DIR / "ground_truth.json"
GROUND_TRUTH_SESSIONS_DIR = GROUND_TRUTH_DIR / "sessions"
PLAYBACK_FEEDBACK_FILE = GROUND_TRUTH_DIR / "playback_feedback.json"

# Schema version for ground_truth.json
GROUND_TRUTH_SCHEMA_VERSION = 1

# Schema version for playback_feedback.json
# v2: Added 'offset' field to session metadata
PLAYBACK_FEEDBACK_SCHEMA_VERSION = 2

# Maximum age for stale sessions (3 hours in seconds)
STALE_SESSION_MAX_AGE_HOURS = 3


def get_local_time(dt: datetime) -> datetime:
    """
    Convert datetime to local timezone.

    Uses system's local timezone (e.g., PST/PDT on the user's machine).

    Args:
        dt: datetime (naive assumed UTC, or timezone-aware)

    Returns:
        Datetime in local timezone (naive, for filename use)
    """
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        timestamp = dt.replace(tzinfo=timezone.utc).timestamp()
    else:
        timestamp = dt.timestamp()

    # Convert to local time using system timezone
    local_struct = time.localtime(timestamp)
    return datetime(*local_struct[:6])


def generate_timestamp_base(created_at: datetime, use_local: bool = True) -> str:
    """
    Generate timestamp base string from session creation time.

    Format: yyyy-mmm-dd-HHmm (e.g., 2025-dec-15-0830)

    Args:
        created_at: Session creation timestamp
        use_local: If True, convert to local timezone

    Returns:
        Timestamp string without prefix or extension
    """
    if use_local:
        local_dt = get_local_time(created_at)
    else:
        local_dt = created_at

    month_abbr = local_dt.strftime('%b').lower()
    return f"{local_dt.year}-{month_abbr}-{local_dt.day:02d}-{local_dt.hour:02d}{local_dt.minute:02d}"


def generate_inprogress_filename(created_at: datetime) -> str:
    """
    Generate in-progress filename for new sessions.

    Format: inprogress-yyyy-mmm-dd-HHmm.json

    Args:
        created_at: Session creation timestamp

    Returns:
        Filename string (without path)

    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2025, 12, 15, 8, 30)
        >>> generate_inprogress_filename(dt)
        'inprogress-2025-dec-15-0830.json'
    """
    timestamp_base = generate_timestamp_base(created_at)
    return f"inprogress-{timestamp_base}.json"


def generate_final_filename(
    created_at: datetime,
    label: Optional[str] = None,
    collision_number: int = 0
) -> str:
    """
    Generate final filename for kept sessions with schema versioning.

    Format: yyyy-mmm-dd-HHmm-ver<schema>.json (default)
    Format: yyyy-mmm-dd-HHmm-ver<schema>-try<N>.json (collision)
    Format: yyyy-mmm-dd-HHmm-ver<schema>-label.json (with label)
    Format: yyyy-mmm-dd-HHmm-ver<schema>-label-try<N>.json (label + collision)

    Version reflects the schema version (REVIEW_SCHEMA_VERSION from models.py).
    Collision handling uses -try<N> suffix for the rare case of duplicate timestamps.

    Args:
        created_at: Session creation timestamp (UTC, converted to local)
        label: Optional user-provided label
        collision_number: Collision avoidance number (0 = no collision)

    Returns:
        Filename string (without path)

    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2025, 12, 15, 16, 30)  # 16:30 UTC = 08:30 PST
        >>> generate_final_filename(dt)
        '2025-dec-15-0830-ver2.json'
        >>> generate_final_filename(dt, "trending_market")
        '2025-dec-15-0830-ver2-trending_market.json'
        >>> generate_final_filename(dt, collision_number=2)
        '2025-dec-15-0830-ver2-try2.json'
    """
    timestamp_base = generate_timestamp_base(created_at)
    version = REVIEW_SCHEMA_VERSION

    if label:
        sanitized_label = sanitize_label(label)
        if collision_number > 0:
            return f"{timestamp_base}-ver{version}-{sanitized_label}-try{collision_number}.json"
        return f"{timestamp_base}-ver{version}-{sanitized_label}.json"
    else:
        if collision_number > 0:
            return f"{timestamp_base}-ver{version}-try{collision_number}.json"
        return f"{timestamp_base}-ver{version}.json"


def sanitize_label(label: str) -> str:
    """
    Sanitize user-provided label for safe filesystem use.

    - Replaces spaces with underscores
    - Removes special characters except underscore and hyphen
    - Converts to lowercase
    - Truncates to 50 characters

    Args:
        label: Raw user input

    Returns:
        Sanitized label safe for filenames
    """
    # Replace spaces with underscores
    sanitized = label.replace(' ', '_')
    # Remove special characters except underscore and hyphen
    sanitized = re.sub(r'[^\w\-]', '', sanitized)
    # Convert to lowercase
    sanitized = sanitized.lower()
    # Truncate to 50 characters
    sanitized = sanitized[:50]
    return sanitized


class AnnotationStorage:
    """
    JSON-backed annotation persistence.

    Stores in-progress sessions as separate JSON files in ground_truth/sessions/.
    On finalize "keep", session+review data is appended to ground_truth/ground_truth.json
    and the working files are deleted.

    ## Single-User Assumption

    This storage layer is designed for single-user operation. Concurrent users
    would cause race conditions on ground_truth.json writes. See module docstring
    for multi-user alternatives.

    ## Lifecycle

    1. Session start → Create ground_truth/sessions/inprogress-{timestamp}.json
    2. During session → Update working file as normal
    3. Finalize "keep" → Append to ground_truth.json, delete working files
    4. Finalize "discard" → Delete working files
    """

    DEFAULT_STORAGE_DIR = str(GROUND_TRUTH_SESSIONS_DIR)

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        ground_truth_dir: Optional[str] = None
    ):
        """
        Initialize storage with a directory for session files.

        Args:
            storage_dir: Directory path for storing session files.
                        Defaults to 'ground_truth/sessions' in current directory.
            ground_truth_dir: Directory path for ground_truth.json.
                             Defaults to 'ground_truth' in current directory.
        """
        self._storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # Track session_id -> current filename mapping for active sessions
        self._session_paths: dict = {}
        # Ground truth directory (configurable for testing)
        self._ground_truth_dir = Path(ground_truth_dir) if ground_truth_dir else GROUND_TRUTH_DIR
        self._ground_truth_file = self._ground_truth_dir / "ground_truth.json"
        self._ground_truth_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        # Check if we have a tracked path for this session
        if session_id in self._session_paths:
            return self._storage_dir / self._session_paths[session_id]
        # Fall back to UUID-based path (for legacy/compatibility)
        return self._storage_dir / f"{session_id}.json"

    def create_session(
        self,
        data_file: str,
        resolution: str,
        window_size: int,
        window_offset: int = 0
    ) -> AnnotationSession:
        """
        Create a new annotation session.

        Session is saved with 'inprogress-' prefix filename. Call finalize_session()
        when done to either keep (rename to clean timestamp) or discard (delete).

        Args:
            data_file: Path or identifier for the source data
            resolution: Source data resolution (e.g., "1m", "5m")
            window_size: Number of bars per annotation window
            window_offset: Offset into the source data (for random window selection)

        Returns:
            Newly created AnnotationSession
        """
        session = AnnotationSession.create(
            data_file=data_file,
            resolution=resolution,
            window_size=window_size,
            window_offset=window_offset
        )

        # Generate inprogress filename and track it
        inprogress_filename = generate_inprogress_filename(session.created_at)

        # Handle collision (rare, but possible if creating multiple sessions same minute)
        counter = 1
        base_filename = inprogress_filename
        while (self._storage_dir / inprogress_filename).exists():
            base = base_filename.rsplit('.json', 1)[0]
            inprogress_filename = f"{base}_{counter}.json"
            counter += 1

        # Track this session's filename
        self._session_paths[session.session_id] = inprogress_filename

        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[AnnotationSession]:
        """
        Retrieve a session by ID.

        Args:
            session_id: UUID of the session

        Returns:
            AnnotationSession if found, None otherwise
        """
        path = self._session_path(session_id)
        if path.exists():
            with open(path, 'r') as f:
                data = json.load(f)
                return AnnotationSession.from_dict(data)

        # File not found at expected path - search all JSON files
        # This handles restarts where _session_paths mapping is lost
        for json_path in self._storage_dir.glob("*.json"):
            if json_path.name.endswith("_review.json"):
                continue  # Skip review files
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    if data.get('session_id') == session_id:
                        # Found it - update tracking for future lookups
                        self._session_paths[session_id] = json_path.name
                        return AnnotationSession.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                continue

        return None

    def list_sessions(self) -> List[AnnotationSession]:
        """
        List all available sessions.

        Returns:
            List of all AnnotationSession objects in storage
        """
        sessions = []
        for path in self._storage_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    sessions.append(AnnotationSession.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                # Skip malformed files
                continue
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)

    def save_annotation(
        self,
        session_id: str,
        annotation: SwingAnnotation
    ) -> None:
        """
        Save a new annotation to a session.

        Args:
            session_id: UUID of the session
            annotation: SwingAnnotation to add

        Raises:
            ValueError: If session not found
        """
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        session.add_annotation(annotation)
        self._save_session(session)

    def get_annotations(
        self,
        session_id: str,
        scale: Optional[str] = None
    ) -> List[SwingAnnotation]:
        """
        Get annotations from a session, optionally filtered by scale.

        Args:
            session_id: UUID of the session
            scale: Optional scale filter ("S", "M", "L", "XL")

        Returns:
            List of matching SwingAnnotation objects

        Raises:
            ValueError: If session not found
        """
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if scale is None:
            return session.annotations.copy()
        return session.get_annotations_by_scale(scale)

    def delete_annotation(
        self,
        session_id: str,
        annotation_id: str
    ) -> bool:
        """
        Delete an annotation from a session.

        Args:
            session_id: UUID of the session
            annotation_id: UUID of the annotation to delete

        Returns:
            True if annotation was found and deleted, False otherwise

        Raises:
            ValueError: If session not found
        """
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if session.remove_annotation(annotation_id):
            self._save_session(session)
            return True
        return False

    def update_session(self, session: AnnotationSession) -> None:
        """
        Update an existing session (e.g., to mark scales complete).

        Args:
            session: AnnotationSession with updated state
        """
        self._save_session(session)

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its annotations.

        Args:
            session_id: UUID of the session

        Returns:
            True if session was found and deleted, False otherwise
        """
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def _find_collision_number(self, timestamp_base: str, label: Optional[str] = None) -> int:
        """
        Find the collision number needed for a filename with given timestamp and label.

        Checks both the working directory AND ground_truth.json for existing filenames.
        Returns 0 if no collision, or the next try number if collision exists.

        Args:
            timestamp_base: The timestamp portion (e.g., '2025-dec-15-0830')
            label: Optional label to match

        Returns:
            0 if no collision, otherwise next available try number
        """
        version = REVIEW_SCHEMA_VERSION

        # Build the base filename (without -try<N>)
        if label:
            sanitized_label = sanitize_label(label)
            base_filename = f"{timestamp_base}-ver{version}-{sanitized_label}.json"
        else:
            base_filename = f"{timestamp_base}-ver{version}.json"

        # Collect existing filenames from both sources
        existing_filenames: set = set()

        # Source 1: Working directory files
        for path in self._storage_dir.glob("*.json"):
            existing_filenames.add(path.name)

        # Source 2: ground_truth.json entries
        if self._ground_truth_file.exists():
            try:
                with open(self._ground_truth_file, 'r') as f:
                    ground_truth = json.load(f)
                    for session_entry in ground_truth.get("sessions", []):
                        orig_filename = session_entry.get("original_filename")
                        if orig_filename:
                            existing_filenames.add(orig_filename)
            except (json.JSONDecodeError, OSError):
                pass  # If we can't read ground truth, proceed with working dir only

        # Check if base filename exists in either source
        if base_filename not in existing_filenames:
            # No collision - use base filename
            return 0

        # Base filename exists - find next available try number
        # Pattern: {timestamp_base}-ver{version}[-label]-try{N}.json
        if label:
            sanitized_label = sanitize_label(label)
            pattern = re.compile(
                rf'^{re.escape(timestamp_base)}-ver{version}-{re.escape(sanitized_label)}-try(\d+)\.json$'
            )
        else:
            pattern = re.compile(
                rf'^{re.escape(timestamp_base)}-ver{version}-try(\d+)\.json$'
            )

        max_try = 1  # Start at 2 since base filename (try 1 implicitly) exists
        for filename in existing_filenames:
            match = pattern.match(filename)
            if match:
                try_num = int(match.group(1))
                max_try = max(max_try, try_num)

        return max_try + 1

    def finalize_session(
        self,
        session_id: str,
        status: str = "keep",
        label: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Finalize a session: keep (append to ground_truth.json) or discard (delete).

        - keep: Appends session+review to ground_truth.json, deletes working files
        - discard: Deletes the session file entirely

        Args:
            session_id: UUID of the session
            status: "keep" (append to ground_truth) or "discard" (delete file)
            label: Optional user-provided label (used in original_filename for reference)

        Returns:
            Tuple of (original_filename, path_id) for "keep", or (None, None) for "discard"
            Note: Working files are deleted; data is now in ground_truth.json

        Raises:
            ValueError: If session not found or invalid status
        """
        if status not in ("keep", "discard"):
            raise ValueError(f"Invalid status: {status}. Must be 'keep' or 'discard'.")

        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        old_path = self._session_path(session_id)

        if status == "discard":
            # Delete the file
            if old_path.exists():
                old_path.unlink()
            # Clean up tracking
            self._session_paths.pop(session_id, None)
            return None, None

        # status == "keep": append to ground_truth.json, then delete working files

        # Generate the original_filename for reference (same format as before)
        timestamp_base = generate_timestamp_base(session.created_at)
        collision_number = self._find_collision_number(timestamp_base, label)
        original_filename = generate_final_filename(session.created_at, label, collision_number)
        path_id = original_filename.rsplit('.json', 1)[0]

        # Read review data if it exists
        review_data = None
        review_path = self._storage_dir / f"{session_id}_review.json"
        if review_path.exists():
            try:
                with open(review_path, 'r') as f:
                    review_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass  # If we can't read review, proceed without it

        # Append to ground_truth.json
        self._append_to_ground_truth(session, path_id, review_data)

        # Delete the session working file
        if old_path.exists():
            old_path.unlink()

        # Clean up tracking
        self._session_paths.pop(session_id, None)

        return original_filename, path_id

    def export_session(
        self,
        session_id: str,
        format: str = "json"
    ) -> str:
        """
        Export a session to a string representation.

        Args:
            session_id: UUID of the session
            format: Export format ("json" or "csv")

        Returns:
            String representation of the session data

        Raises:
            ValueError: If session not found or unsupported format
        """
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if format == "json":
            return json.dumps(session.to_dict(), indent=2)
        elif format == "csv":
            return self._export_csv(session)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_csv(self, session: AnnotationSession) -> str:
        """Export session annotations to CSV format."""
        lines = [
            "annotation_id,scale,direction,start_bar_index,end_bar_index,"
            "start_source_index,end_source_index,start_price,end_price,"
            "created_at,window_id"
        ]

        for ann in session.annotations:
            line = (
                f"{ann.annotation_id},{ann.scale},{ann.direction},"
                f"{ann.start_bar_index},{ann.end_bar_index},"
                f"{ann.start_source_index},{ann.end_source_index},"
                f"{ann.start_price},{ann.end_price},"
                f"{ann.created_at.isoformat()},{ann.window_id}"
            )
            lines.append(line)

        return "\n".join(lines)

    def _save_session(self, session: AnnotationSession) -> None:
        """Persist a session to disk."""
        path = self._session_path(session.session_id)
        with open(path, 'w') as f:
            json.dump(session.to_dict(), f, indent=2)

    def _append_to_ground_truth(
        self,
        session: AnnotationSession,
        original_filename: str,
        review_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Append a finalized session to the ground truth file.

        Creates the ground_truth.json file if it doesn't exist.
        Appends the session and optional review data as a new entry.

        Args:
            session: The finalized AnnotationSession
            original_filename: The session's filename (without .json extension)
            review_data: Optional review session dict to include
        """
        # Read existing ground truth or create new structure
        if self._ground_truth_file.exists():
            with open(self._ground_truth_file, 'r') as f:
                ground_truth = json.load(f)
        else:
            ground_truth = {
                "metadata": {
                    "schema_version": GROUND_TRUTH_SCHEMA_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                },
                "sessions": []
            }

        # Create the session entry
        entry = {
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "original_filename": original_filename,
            "session": session.to_dict()
        }

        # Include review data if available
        if review_data is not None:
            entry["review"] = review_data

        # Append and update metadata
        ground_truth["sessions"].append(entry)
        ground_truth["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Write back
        with open(self._ground_truth_file, 'w') as f:
            json.dump(ground_truth, f, indent=2)

    def cleanup_stale_sessions(self, max_age_hours: int = STALE_SESSION_MAX_AGE_HOURS) -> int:
        """
        Delete in-progress sessions older than max_age_hours.

        Stale sessions are working files that were never finalized,
        likely from crashed or abandoned annotation sessions.

        Args:
            max_age_hours: Maximum age in hours before a session is considered stale

        Returns:
            Number of stale sessions deleted
        """
        deleted_count = 0
        max_age_seconds = max_age_hours * 3600
        now = time.time()

        for path in self._storage_dir.glob("inprogress-*.json"):
            try:
                # Check file modification time
                mtime = path.stat().st_mtime
                age_seconds = now - mtime

                if age_seconds > max_age_seconds:
                    # Also delete associated review file if exists
                    # First, read the session to get its ID
                    try:
                        with open(path, 'r') as f:
                            data = json.load(f)
                            session_id = data.get('session_id')
                            if session_id:
                                review_path = self._storage_dir / f"{session_id}_review.json"
                                if review_path.exists():
                                    review_path.unlink()
                    except (json.JSONDecodeError, KeyError):
                        pass  # Can't read session ID, just delete the file

                    path.unlink()
                    deleted_count += 1
            except OSError:
                continue  # Skip files we can't access

        return deleted_count


class ReviewStorage:
    """
    JSON-backed review feedback persistence.

    Stores review sessions separately from annotation sessions using
    a {session_id}_review.json naming convention.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize storage with a directory for review files.

        Uses the same directory as AnnotationStorage by default.

        Args:
            storage_dir: Directory path for storing review files.
                        Defaults to 'annotation_sessions' in current directory.
        """
        self._storage_dir = Path(storage_dir or AnnotationStorage.DEFAULT_STORAGE_DIR)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _review_path(self, session_id: str) -> Path:
        """Get the file path for a review session."""
        return self._storage_dir / f"{session_id}_review.json"

    def create_review(self, session_id: str) -> ReviewSession:
        """
        Create a new review session for an annotation session.

        Args:
            session_id: UUID of the annotation session to review

        Returns:
            Newly created ReviewSession
        """
        review = ReviewSession.create(session_id)
        self.save_review(review)
        return review

    def get_review(self, session_id: str) -> Optional[ReviewSession]:
        """
        Get review session by annotation session ID.

        Args:
            session_id: UUID of the annotation session

        Returns:
            ReviewSession if found, None otherwise
        """
        path = self._review_path(session_id)
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
            return ReviewSession.from_dict(data)

    def save_review(self, review: ReviewSession) -> None:
        """
        Persist review session to disk.

        Args:
            review: ReviewSession to save
        """
        path = self._review_path(review.session_id)
        with open(path, 'w') as f:
            json.dump(review.to_dict(), f, indent=2)

    def delete_review(self, session_id: str) -> bool:
        """
        Delete a review session.

        Args:
            session_id: UUID of the annotation session

        Returns:
            True if review was found and deleted, False otherwise
        """
        path = self._review_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def finalize_review(
        self,
        session_id: str,
        status: str = "keep",
        new_path_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Finalize review file: delete working file.

        Note: On "keep", the review data is already appended to ground_truth.json
        by AnnotationStorage.finalize_session(). This method just cleans up the
        working file.

        Args:
            session_id: Original UUID of the annotation session
            status: "keep" or "discard" (both delete the working file)
            new_path_id: Path ID for reference in returned filename (optional)

        Returns:
            Reference filename for "keep" (e.g., "2025-dec-15-1225-ver4_review.json"),
            None for "discard" or if no review existed
        """
        old_path = self._review_path(session_id)
        if not old_path.exists():
            return None

        # Delete the working file (data already in ground_truth.json for "keep")
        old_path.unlink()

        if status == "discard":
            return None

        # Return reference filename for API compatibility
        if new_path_id is not None:
            return f"{new_path_id}_review.json"
        return None

    def export_review(self, session_id: str, format: str = "json") -> str:
        """
        Export review as JSON or CSV string.

        Args:
            session_id: UUID of the annotation session
            format: Export format ("json" or "csv")

        Returns:
            String representation of the review data

        Raises:
            ValueError: If review not found or unsupported format
        """
        review = self.get_review(session_id)
        if review is None:
            raise ValueError(f"Review not found for session: {session_id}")

        if format == "json":
            return json.dumps(review.to_dict(), indent=2)
        elif format == "csv":
            return self._export_csv(review)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_csv(self, review: ReviewSession) -> str:
        """Export review feedback to CSV format."""
        lines = [
            "feedback_id,swing_type,verdict,category,comment,created_at"
        ]

        all_feedback = review.match_feedback + review.fp_feedback + review.fn_feedback

        for fb in all_feedback:
            comment = escape_csv_field(fb.comment or "")
            line = (
                f"{fb.feedback_id},{fb.swing_type},{fb.verdict},"
                f"{fb.category or ''},{comment},{fb.created_at.isoformat()}"
            )
            lines.append(line)

        return "\n".join(lines)


class PlaybackFeedbackStorage:
    """
    JSON-backed storage for playback feedback observations.

    Stores observations in a separate file from ground truth annotations,
    following the schema defined in architect_notes.md.

    File structure:
    {
        "schema_version": 1,
        "playback_sessions": [
            {
                "session_id": "uuid",
                "data_file": "es-5m.csv",
                "started_at": "2025-12-17T14:30:00Z",
                "observations": [...]
            }
        ]
    }

    ## Single-User Assumption

    Like AnnotationStorage, this is designed for single-user operation.
    """

    def __init__(self, feedback_file: Optional[str] = None):
        """
        Initialize storage with path to feedback file.

        Args:
            feedback_file: Path to playback_feedback.json.
                          Defaults to 'ground_truth/playback_feedback.json'.
        """
        self._feedback_file = Path(feedback_file) if feedback_file else PLAYBACK_FEEDBACK_FILE
        self._feedback_file.parent.mkdir(parents=True, exist_ok=True)
        # Cache for current session (to avoid re-reading file on every add)
        self._current_session: Optional[PlaybackSession] = None

    def _load_feedback_data(self) -> Dict[str, Any]:
        """Load the playback feedback file or create new structure."""
        if self._feedback_file.exists():
            with open(self._feedback_file, 'r') as f:
                return json.load(f)
        return {
            "schema_version": PLAYBACK_FEEDBACK_SCHEMA_VERSION,
            "playback_sessions": []
        }

    def _save_feedback_data(self, data: Dict[str, Any]) -> None:
        """Save the playback feedback file."""
        with open(self._feedback_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_or_create_session(self, data_file: str, offset: int = 0) -> PlaybackSession:
        """
        Get the current session for a data file, or create a new one.

        Sessions are identified by data_file. A new session is created
        if no session exists for the current data file in this instance.

        Args:
            data_file: The data file being reviewed
            offset: Offset into source data for this window

        Returns:
            PlaybackSession (existing or newly created)
        """
        # Check cached session
        if self._current_session and self._current_session.data_file == data_file:
            return self._current_session

        # Create new session for this data file
        session = PlaybackSession.create(data_file, offset=offset)
        self._current_session = session

        # Persist immediately
        data = self._load_feedback_data()
        data["playback_sessions"].append(session.to_dict())
        self._save_feedback_data(data)

        return session

    def add_observation(
        self,
        data_file: str,
        playback_bar: int,
        event_context: Dict[str, Any],
        text: str,
        offset: int = 0
    ) -> PlaybackObservation:
        """
        Add an observation to the current session.

        Creates a session if none exists for the data file.

        Args:
            data_file: Source data file being reviewed
            playback_bar: Current playback bar index
            event_context: Full event context (type, scale, swing details)
            text: Free-form observation text
            offset: Offset into source data for this window

        Returns:
            The created PlaybackObservation
        """
        # Get or create session
        session = self.get_or_create_session(data_file, offset=offset)

        # Create observation
        observation = PlaybackObservation.create(
            playback_bar=playback_bar,
            event_context=event_context,
            text=text
        )
        session.add_observation(observation)

        # Persist
        data = self._load_feedback_data()

        # Find and update the session in the file
        for i, s in enumerate(data["playback_sessions"]):
            if s["session_id"] == session.session_id:
                data["playback_sessions"][i] = session.to_dict()
                break

        self._save_feedback_data(data)
        return observation

    def get_sessions(self, data_file: Optional[str] = None) -> List[PlaybackSession]:
        """
        Get all playback sessions, optionally filtered by data file.

        Args:
            data_file: Optional filter by data file

        Returns:
            List of PlaybackSession objects
        """
        data = self._load_feedback_data()
        sessions = [
            PlaybackSession.from_dict(s)
            for s in data["playback_sessions"]
        ]

        if data_file:
            sessions = [s for s in sessions if s.data_file == data_file]

        return sorted(sessions, key=lambda s: s.started_at, reverse=True)

    def get_observations(
        self,
        data_file: Optional[str] = None,
        scale: Optional[str] = None,
        event_type: Optional[str] = None,
        date_filter: Optional[str] = None  # Format: "YYYY-MM-DD"
    ) -> List[PlaybackObservation]:
        """
        Query observations with optional filters.

        Args:
            data_file: Filter by source data file
            scale: Filter by swing scale (S, M, L, XL)
            event_type: Filter by event type (SWING_FORMED, etc.)
            date_filter: Filter by date (YYYY-MM-DD)

        Returns:
            List of matching PlaybackObservation objects
        """
        sessions = self.get_sessions(data_file)
        observations: List[PlaybackObservation] = []

        for session in sessions:
            for obs in session.observations:
                # Apply filters
                if scale and obs.event_context.get("scale") != scale:
                    continue
                if event_type and obs.event_context.get("event_type") != event_type:
                    continue
                if date_filter:
                    obs_date = obs.created_at.strftime("%Y-%m-%d")
                    if obs_date != date_filter:
                        continue
                observations.append(obs)

        return observations
