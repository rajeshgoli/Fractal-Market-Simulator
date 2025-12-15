"""
Annotation Storage Layer

JSON-backed persistence for annotation sessions and swing annotations.
Handles file I/O, session management, and data export.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .models import AnnotationSession, SwingAnnotation, ReviewSession, SwingFeedback


def generate_timestamp_base(created_at: datetime) -> str:
    """
    Generate timestamp base string from session creation time.

    Format: yyyy-mmm-dd-HHmm (e.g., 2025-dec-15-0830)

    Args:
        created_at: Session creation timestamp

    Returns:
        Timestamp string without prefix or extension
    """
    month_abbr = created_at.strftime('%b').lower()
    return f"{created_at.year}-{month_abbr}-{created_at.day:02d}-{created_at.hour:02d}{created_at.minute:02d}"


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


def generate_final_filename(created_at: datetime, label: Optional[str] = None) -> str:
    """
    Generate final filename for kept sessions.

    Format: yyyy-mmm-dd-HHmm.json (default)
    Format: yyyy-mmm-dd-HHmm-label.json (with label)

    Args:
        created_at: Session creation timestamp
        label: Optional user-provided label

    Returns:
        Filename string (without path)

    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2025, 12, 15, 8, 30)
        >>> generate_final_filename(dt)
        '2025-dec-15-0830.json'
        >>> generate_final_filename(dt, "trending_market")
        '2025-dec-15-0830-trending_market.json'
    """
    timestamp_base = generate_timestamp_base(created_at)

    if label:
        sanitized_label = sanitize_label(label)
        return f"{timestamp_base}-{sanitized_label}.json"
    else:
        return f"{timestamp_base}.json"


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

    Stores each session as a separate JSON file for simplicity and
    easy inspection. Supports CRUD operations on annotations and
    session metadata management.

    New sessions are created with 'inprogress-' prefix and renamed
    to final timestamp-based name when finalized.
    """

    DEFAULT_STORAGE_DIR = "annotation_sessions"

    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize storage with a directory for session files.

        Args:
            storage_dir: Directory path for storing session files.
                        Defaults to 'annotation_sessions' in current directory.
        """
        self._storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # Track session_id -> current filename mapping for active sessions
        self._session_paths: dict = {}

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

    def finalize_session(
        self,
        session_id: str,
        status: str = "keep",
        label: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Finalize a session: keep (rename to clean timestamp) or discard (delete).

        - keep: Renames from 'inprogress-...' to clean 'yyyy-mmm-dd-HHmm[-label].json'
        - discard: Deletes the session file entirely

        Args:
            session_id: UUID of the session
            status: "keep" (rename to final name) or "discard" (delete file)
            label: Optional user-provided label (only used for "keep")

        Returns:
            Tuple of (new_filename, new_path_id) for "keep", or (None, None) for "discard"
            Note: The session object still contains original session_id

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

        # status == "keep": rename to clean timestamp filename
        new_filename = generate_final_filename(session.created_at, label)
        new_path = self._storage_dir / new_filename

        # Handle filename collision (add counter suffix if needed)
        counter = 1
        base_filename = new_filename
        while new_path.exists():
            base = base_filename.rsplit('.json', 1)[0]
            new_filename = f"{base}_{counter}.json"
            new_path = self._storage_dir / new_filename
            counter += 1

        # Rename file
        if old_path.exists():
            old_path.rename(new_path)

        # Update tracking
        self._session_paths[session_id] = new_filename

        # Derive the path_id (filename without .json)
        new_path_id = new_filename.rsplit('.json', 1)[0]

        return new_filename, new_path_id

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
        Finalize review file: keep (rename) or discard (delete).

        Args:
            session_id: Original UUID of the annotation session
            status: "keep" (rename to match session) or "discard" (delete)
            new_path_id: New path ID from finalized session (required for "keep")

        Returns:
            New review filename for "keep", None for "discard" or if no review existed
        """
        old_path = self._review_path(session_id)
        if not old_path.exists():
            return None

        if status == "discard":
            # Delete the review file
            old_path.unlink()
            return None

        # status == "keep": rename to match session filename
        if new_path_id is None:
            raise ValueError("new_path_id required for 'keep' status")

        new_filename = f"{new_path_id}_review.json"
        new_path = self._storage_dir / new_filename

        old_path.rename(new_path)
        return new_filename

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
            # Escape commas in comment
            comment = (fb.comment or "").replace(",", ";").replace("\n", " ")
            line = (
                f"{fb.feedback_id},{fb.swing_type},{fb.verdict},"
                f"{fb.category or ''},{comment},{fb.created_at.isoformat()}"
            )
            lines.append(line)

        return "\n".join(lines)
