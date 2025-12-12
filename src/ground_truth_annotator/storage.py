"""
Annotation Storage Layer

JSON-backed persistence for annotation sessions and swing annotations.
Handles file I/O, session management, and data export.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import AnnotationSession, SwingAnnotation, ReviewSession, SwingFeedback


class AnnotationStorage:
    """
    JSON-backed annotation persistence.

    Stores each session as a separate JSON file for simplicity and
    easy inspection. Supports CRUD operations on annotations and
    session metadata management.
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

    def _session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self._storage_dir / f"{session_id}.json"

    def create_session(
        self,
        data_file: str,
        resolution: str,
        window_size: int
    ) -> AnnotationSession:
        """
        Create a new annotation session.

        Args:
            data_file: Path or identifier for the source data
            resolution: Source data resolution (e.g., "1m", "5m")
            window_size: Number of bars per annotation window

        Returns:
            Newly created AnnotationSession
        """
        session = AnnotationSession.create(
            data_file=data_file,
            resolution=resolution,
            window_size=window_size
        )
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
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
            return AnnotationSession.from_dict(data)

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
