"""
Tests for Playback Feedback Storage functionality.

Tests the PlaybackObservation, PlaybackSession models and
PlaybackFeedbackStorage persistence layer.
"""

import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.ground_truth_annotator.models import (
    PlaybackObservation, PlaybackSession
)
from src.ground_truth_annotator.storage import (
    PlaybackFeedbackStorage, PLAYBACK_FEEDBACK_SCHEMA_VERSION
)


class TestPlaybackObservation:
    """Tests for PlaybackObservation dataclass."""

    def test_create_observation(self):
        """Test factory method creates observation with auto-generated fields."""
        event_context = {
            "event_type": "SWING_FORMED",
            "scale": "M",
            "swing": {
                "high_bar_index": 100,
                "low_bar_index": 150,
                "high_price": "4500.00",
                "low_price": "4400.00",
                "direction": "bull"
            },
            "detection_bar_index": 160
        }

        observation = PlaybackObservation.create(
            playback_bar=1234,
            event_context=event_context,
            text="Swing detected but price already hit 2x target"
        )

        assert observation.observation_id  # UUID generated
        assert observation.created_at is not None
        assert observation.playback_bar == 1234
        assert observation.event_context == event_context
        assert observation.text == "Swing detected but price already hit 2x target"

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        observation = PlaybackObservation.create(
            playback_bar=500,
            event_context={"event_type": "LEVEL_CROSS", "scale": "L"},
            text="Test observation"
        )

        data = observation.to_dict()
        restored = PlaybackObservation.from_dict(data)

        assert restored.observation_id == observation.observation_id
        assert restored.playback_bar == observation.playback_bar
        assert restored.event_context == observation.event_context
        assert restored.text == observation.text


class TestPlaybackSession:
    """Tests for PlaybackSession dataclass."""

    def test_create_session(self):
        """Test factory method creates session with auto-generated fields."""
        session = PlaybackSession.create(data_file="es-5m.csv")

        assert session.session_id  # UUID generated
        assert session.data_file == "es-5m.csv"
        assert session.started_at is not None
        assert session.observations == []

    def test_add_observation(self):
        """Test adding observations to session."""
        session = PlaybackSession.create(data_file="test.csv")
        observation = PlaybackObservation.create(
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="Test"
        )

        session.add_observation(observation)

        assert len(session.observations) == 1
        assert session.observations[0] == observation

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip with observations."""
        session = PlaybackSession.create(data_file="test.csv")
        session.add_observation(PlaybackObservation.create(
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="First observation"
        ))
        session.add_observation(PlaybackObservation.create(
            playback_bar=200,
            event_context={"event_type": "LEVEL_CROSS", "scale": "M"},
            text="Second observation"
        ))

        data = session.to_dict()
        restored = PlaybackSession.from_dict(data)

        assert restored.session_id == session.session_id
        assert restored.data_file == session.data_file
        assert len(restored.observations) == 2
        assert restored.observations[0].text == "First observation"
        assert restored.observations[1].text == "Second observation"


class TestPlaybackFeedbackStorage:
    """Tests for PlaybackFeedbackStorage persistence layer."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create a storage instance with a temporary file."""
        feedback_file = tmp_path / "playback_feedback.json"
        return PlaybackFeedbackStorage(feedback_file=str(feedback_file))

    def test_create_session_on_first_observation(self, temp_storage):
        """Test that first observation creates a session."""
        observation = temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="First observation"
        )

        assert observation.observation_id
        sessions = temp_storage.get_sessions()
        assert len(sessions) == 1
        assert sessions[0].data_file == "test.csv"

    def test_add_multiple_observations_same_session(self, temp_storage):
        """Test adding multiple observations to the same session."""
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="First"
        )
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=200,
            event_context={"event_type": "LEVEL_CROSS", "scale": "M"},
            text="Second"
        )

        sessions = temp_storage.get_sessions()
        assert len(sessions) == 1
        assert len(sessions[0].observations) == 2

    def test_file_persistence(self, tmp_path):
        """Test that data persists to file."""
        feedback_file = tmp_path / "playback_feedback.json"

        # First storage instance - add observation
        storage1 = PlaybackFeedbackStorage(feedback_file=str(feedback_file))
        storage1.add_observation(
            data_file="test.csv",
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="Persisted observation"
        )

        # Second storage instance - should see the data
        storage2 = PlaybackFeedbackStorage(feedback_file=str(feedback_file))
        sessions = storage2.get_sessions()

        assert len(sessions) == 1
        # Note: second instance creates a new session, so observations are in first session
        # We need to read the raw file to verify persistence
        with open(feedback_file, 'r') as f:
            data = json.load(f)
        assert len(data["playback_sessions"]) == 1
        assert len(data["playback_sessions"][0]["observations"]) == 1

    def test_get_observations_filter_by_scale(self, temp_storage):
        """Test filtering observations by scale."""
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="Small scale"
        )
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=200,
            event_context={"event_type": "SWING_FORMED", "scale": "M"},
            text="Medium scale"
        )

        s_observations = temp_storage.get_observations(scale="S")
        m_observations = temp_storage.get_observations(scale="M")

        assert len(s_observations) == 1
        assert s_observations[0].text == "Small scale"
        assert len(m_observations) == 1
        assert m_observations[0].text == "Medium scale"

    def test_get_observations_filter_by_event_type(self, temp_storage):
        """Test filtering observations by event type."""
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="Swing formed"
        )
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=200,
            event_context={"event_type": "LEVEL_CROSS", "scale": "M"},
            text="Level cross"
        )

        swing_observations = temp_storage.get_observations(event_type="SWING_FORMED")
        level_observations = temp_storage.get_observations(event_type="LEVEL_CROSS")

        assert len(swing_observations) == 1
        assert swing_observations[0].text == "Swing formed"
        assert len(level_observations) == 1
        assert level_observations[0].text == "Level cross"

    def test_schema_version_in_file(self, temp_storage, tmp_path):
        """Test that schema version is written to file."""
        temp_storage.add_observation(
            data_file="test.csv",
            playback_bar=100,
            event_context={"event_type": "SWING_FORMED", "scale": "S"},
            text="Test"
        )

        with open(tmp_path / "playback_feedback.json", 'r') as f:
            data = json.load(f)

        assert data["schema_version"] == PLAYBACK_FEEDBACK_SCHEMA_VERSION
