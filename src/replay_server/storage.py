"""
Storage layer for Replay View feedback.

JSON-backed persistence for playback sessions and observations.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .models import PlaybackSession, PlaybackObservation

logger = logging.getLogger(__name__)

# Ground truth directory structure
GROUND_TRUTH_DIR = Path("ground_truth")
PLAYBACK_FEEDBACK_FILE = GROUND_TRUTH_DIR / "playback_feedback.json"

# Schema version for playback_feedback.json
PLAYBACK_FEEDBACK_SCHEMA_VERSION = 2


class PlaybackFeedbackStorage:
    """
    Storage for playback feedback/observations.

    Manages a JSON file containing playback sessions with their observations.
    Sessions are keyed by data file to group related feedback.
    """

    def __init__(self, storage_path: Path = None):
        """
        Initialize storage.

        Args:
            storage_path: Optional custom path for the feedback file.
                         Defaults to ground_truth/playback_feedback.json
        """
        self.storage_path = storage_path or PLAYBACK_FEEDBACK_FILE
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure storage file and directory exist."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.storage_path.exists():
            self._write_data({
                "schema_version": PLAYBACK_FEEDBACK_SCHEMA_VERSION,
                "sessions": {}
            })

    def _read_data(self) -> Dict[str, Any]:
        """Read and parse the storage file."""
        with open(self.storage_path, 'r') as f:
            return json.load(f)

    def _write_data(self, data: Dict[str, Any]) -> None:
        """Write data to storage file."""
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_or_create_session(self, data_file: str, offset: int = 0) -> PlaybackSession:
        """
        Get existing session for data file or create new one.

        Args:
            data_file: The data file being reviewed
            offset: Offset into source data for this window

        Returns:
            The playback session (existing or newly created)
        """
        data = self._read_data()
        sessions = data.get("sessions", {})

        # Check for existing session with this data file
        if data_file in sessions:
            return PlaybackSession.from_dict(sessions[data_file])

        # Create new session
        session = PlaybackSession.create(data_file, offset=offset)
        sessions[data_file] = session.to_dict()
        data["sessions"] = sessions
        self._write_data(data)

        logger.info(f"Created new playback session for {data_file}")
        return session

    def add_observation(
        self,
        data_file: str,
        text: str,
        playback_bar: int,
        snapshot: Dict[str, Any],
        offset: int = 0
    ) -> PlaybackObservation:
        """
        Add an observation to the session for the given data file.

        Args:
            data_file: The data file being reviewed
            text: The observation text
            playback_bar: Current playback bar index
            snapshot: Rich context snapshot
            offset: Offset into source data (for session creation if needed)

        Returns:
            The created observation
        """
        session = self.get_or_create_session(data_file, offset=offset)

        observation = PlaybackObservation.create(
            text=text,
            playback_bar=playback_bar,
            snapshot=snapshot
        )
        session.add_observation(observation)

        # Save back to storage
        data = self._read_data()
        data["sessions"][data_file] = session.to_dict()
        self._write_data(data)

        logger.info(f"Added observation {observation.observation_id} at bar {playback_bar}")
        return observation

    def get_session(self, data_file: str) -> Optional[PlaybackSession]:
        """
        Get session for a data file if it exists.

        Args:
            data_file: The data file to look up

        Returns:
            The playback session or None if not found
        """
        data = self._read_data()
        sessions = data.get("sessions", {})

        if data_file in sessions:
            return PlaybackSession.from_dict(sessions[data_file])

        return None

    def get_all_sessions(self) -> Dict[str, PlaybackSession]:
        """
        Get all playback sessions.

        Returns:
            Dict mapping data file paths to their sessions
        """
        data = self._read_data()
        sessions = data.get("sessions", {})
        return {k: PlaybackSession.from_dict(v) for k, v in sessions.items()}
