"""
Data models for Replay View.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class PlaybackObservation:
    """
    A single observation made during playback.

    Captures free-form text observations with context about the
    current playback state (bar index, active swings, etc.).
    """
    observation_id: str
    text: str
    playback_bar: int           # Bar index when observation was made
    created_at: datetime
    snapshot: Dict[str, Any]    # Rich context snapshot

    @classmethod
    def create(
        cls,
        text: str,
        playback_bar: int,
        snapshot: Dict[str, Any]
    ) -> 'PlaybackObservation':
        """Factory method to create a new observation."""
        return cls(
            observation_id=str(uuid.uuid4()),
            text=text,
            playback_bar=playback_bar,
            created_at=datetime.now(timezone.utc),
            snapshot=snapshot
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            'observation_id': self.observation_id,
            'text': self.text,
            'playback_bar': self.playback_bar,
            'created_at': self.created_at.isoformat(),
            'snapshot': self.snapshot
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlaybackObservation':
        """Deserialize from dictionary."""
        return cls(
            observation_id=data['observation_id'],
            text=data['text'],
            playback_bar=data['playback_bar'],
            created_at=datetime.fromisoformat(data['created_at']),
            snapshot=data.get('snapshot', {})
        )


@dataclass
class PlaybackSession:
    """
    A playback session containing observations made during Replay View.
    """
    session_id: str
    data_file: str
    started_at: datetime
    offset: int
    observations: List[PlaybackObservation] = field(default_factory=list)

    @classmethod
    def create(cls, data_file: str, offset: int = 0) -> 'PlaybackSession':
        """Factory method to create a new playback session."""
        return cls(
            session_id=str(uuid.uuid4()),
            data_file=data_file,
            started_at=datetime.now(timezone.utc),
            offset=offset,
            observations=[]
        )

    def add_observation(self, observation: PlaybackObservation) -> None:
        """Add an observation to the session."""
        self.observations.append(observation)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            'session_id': self.session_id,
            'data_file': self.data_file,
            'offset': self.offset,
            'started_at': self.started_at.isoformat(),
            'observations': [o.to_dict() for o in self.observations]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlaybackSession':
        """Deserialize from dictionary."""
        return cls(
            session_id=data['session_id'],
            data_file=data['data_file'],
            started_at=datetime.fromisoformat(data['started_at']),
            offset=data.get('offset', 0),
            observations=[PlaybackObservation.from_dict(o) for o in data.get('observations', [])]
        )
