"""
Vote persistence for swing validation.

Stores validation results in JSON format for later analysis.
Supports export to CSV/JSON for reporting.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    Scale,
    SessionStats,
    ValidationResult,
    Vote,
    VoteRequest,
    VoteType,
)

logger = logging.getLogger(__name__)


class VoteStorage:
    """
    Persists validation votes and results to JSON files.

    Each validation session creates a timestamped JSON file containing
    all votes and metadata for analysis.
    """

    def __init__(self, storage_dir: str = "validation_results"):
        """
        Initialize storage with directory path.

        Args:
            storage_dir: Directory for storing validation results
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Current session data
        self.session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.session_file = self.storage_dir / f"session_{self.session_id}.json"
        self.results: List[ValidationResult] = []
        self.stats = SessionStats()

        # Initialize session file
        self._save_session()

        logger.info(f"Initialized vote storage: {self.session_file}")

    def record_vote(self, request: VoteRequest, sample_scale: Scale,
                    interval_start: int, interval_end: int) -> ValidationResult:
        """
        Record a validation vote.

        Args:
            request: Vote request from user
            sample_scale: Scale of the sample
            interval_start: Start timestamp of interval
            interval_end: End timestamp of interval

        Returns:
            Persisted ValidationResult
        """
        result = ValidationResult(
            sample_id=request.sample_id,
            scale=sample_scale,
            interval_start=interval_start,
            interval_end=interval_end,
            swing_votes=request.swing_votes,
            found_right_swings=request.found_right_swings,
            overall_comment=request.overall_comment,
        )

        self.results.append(result)
        self._update_stats(result)
        self._save_session()

        logger.info(f"Recorded vote for sample {request.sample_id}")
        return result

    def _update_stats(self, result: ValidationResult) -> None:
        """Update session statistics after a vote."""
        self.stats.samples_validated += 1

        # Count votes by type
        for vote in result.swing_votes:
            if vote.vote == VoteType.UP:
                self.stats.swings_approved += 1
            elif vote.vote == VoteType.DOWN:
                self.stats.swings_rejected += 1
            else:
                self.stats.swings_skipped += 1

        # Update by-scale stats
        scale_key = result.scale.value
        if scale_key not in self.stats.by_scale:
            self.stats.by_scale[scale_key] = {
                "samples": 0,
                "approved": 0,
                "rejected": 0,
                "skipped": 0,
            }

        self.stats.by_scale[scale_key]["samples"] += 1
        for vote in result.swing_votes:
            if vote.vote == VoteType.UP:
                self.stats.by_scale[scale_key]["approved"] += 1
            elif vote.vote == VoteType.DOWN:
                self.stats.by_scale[scale_key]["rejected"] += 1
            else:
                self.stats.by_scale[scale_key]["skipped"] += 1

    def _save_session(self) -> None:
        """Save current session to JSON file."""
        session_data = {
            "session_id": self.session_id,
            "created_at": datetime.utcnow().isoformat(),
            "stats": self.stats.model_dump(),
            "results": [r.model_dump() for r in self.results],
        }

        # Convert datetime objects to ISO strings
        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(self.session_file, 'w') as f:
            json.dump(session_data, f, indent=2, default=serialize_datetime)

    def get_stats(self) -> SessionStats:
        """Get current session statistics."""
        return self.stats

    def get_results(self) -> List[ValidationResult]:
        """Get all validation results for current session."""
        return self.results

    def export_csv(self, filepath: str) -> str:
        """
        Export validation results to CSV.

        Args:
            filepath: Output file path

        Returns:
            Path to exported file
        """
        import csv

        output_path = Path(filepath)

        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                "sample_id", "scale", "interval_start", "interval_end",
                "swing_id", "vote", "comment", "found_right_swings",
                "overall_comment", "validated_at"
            ])

            # Data rows
            for result in self.results:
                for vote in result.swing_votes:
                    writer.writerow([
                        result.sample_id,
                        result.scale.value,
                        result.interval_start,
                        result.interval_end,
                        vote.swing_id,
                        vote.vote.value,
                        vote.comment or "",
                        result.found_right_swings,
                        result.overall_comment or "",
                        result.validated_at.isoformat(),
                    ])

        logger.info(f"Exported {len(self.results)} results to {output_path}")
        return str(output_path)

    def export_json(self, filepath: str) -> str:
        """
        Export validation results to JSON.

        Args:
            filepath: Output file path

        Returns:
            Path to exported file
        """
        output_path = Path(filepath)

        export_data = {
            "session_id": self.session_id,
            "exported_at": datetime.utcnow().isoformat(),
            "stats": self.stats.model_dump(),
            "results": [r.model_dump() for r in self.results],
        }

        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=serialize_datetime)

        logger.info(f"Exported {len(self.results)} results to {output_path}")
        return str(output_path)

    @classmethod
    def load_session(cls, filepath: str) -> "VoteStorage":
        """
        Load a previous session from file.

        Args:
            filepath: Path to session JSON file

        Returns:
            VoteStorage instance with loaded data
        """
        with open(filepath, 'r') as f:
            data = json.load(f)

        storage = cls.__new__(cls)
        storage.storage_dir = Path(filepath).parent
        storage.session_id = data["session_id"]
        storage.session_file = Path(filepath)

        # Parse results
        storage.results = []
        for r in data.get("results", []):
            # Parse votes
            votes = []
            for v in r.get("swing_votes", []):
                votes.append(Vote(
                    swing_id=v["swing_id"],
                    vote=VoteType(v["vote"]),
                    comment=v.get("comment"),
                    voted_at=datetime.fromisoformat(v["voted_at"]) if v.get("voted_at") else datetime.utcnow()
                ))

            storage.results.append(ValidationResult(
                sample_id=r["sample_id"],
                scale=Scale(r["scale"]),
                interval_start=r["interval_start"],
                interval_end=r["interval_end"],
                swing_votes=votes,
                found_right_swings=r.get("found_right_swings"),
                overall_comment=r.get("overall_comment"),
                validated_at=datetime.fromisoformat(r["validated_at"]) if r.get("validated_at") else datetime.utcnow()
            ))

        # Parse stats
        stats_data = data.get("stats", {})
        storage.stats = SessionStats(**stats_data)

        return storage

    @classmethod
    def list_sessions(cls, storage_dir: str = "validation_results") -> List[dict]:
        """
        List available validation sessions.

        Args:
            storage_dir: Directory containing session files

        Returns:
            List of session metadata
        """
        sessions = []
        storage_path = Path(storage_dir)

        if not storage_path.exists():
            return sessions

        for file_path in storage_path.glob("session_*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                sessions.append({
                    "session_id": data.get("session_id"),
                    "file": str(file_path),
                    "created_at": data.get("created_at"),
                    "samples_validated": data.get("stats", {}).get("samples_validated", 0),
                })
            except Exception as e:
                logger.warning(f"Failed to read session {file_path}: {e}")

        # Sort by creation time (newest first)
        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions
