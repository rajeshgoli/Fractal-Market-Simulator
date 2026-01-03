"""Tests for SQLite observation storage (Issue #478)."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.replay_server import db


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_fractal.db"
        db.set_db_path(db_path)
        db.init_db()
        yield db_path
        # Reset db path after test
        db._db_path = None


class TestAddObservation:
    """Tests for add_observation function."""

    def test_add_observation_returns_id(self, temp_db):
        """Adding an observation returns the observation ID."""
        obs_id = db.add_observation(
            user_id="test_user",
            bar_index=100,
            event_context='{"mode": "dag"}',
            text="Test observation",
        )
        assert obs_id is not None
        assert obs_id > 0

    def test_add_observation_local_mode(self, temp_db):
        """Adding observation with None user_id uses 'local'."""
        obs_id = db.add_observation(
            user_id=None,
            bar_index=100,
            event_context='{"mode": "dag"}',
            text="Local observation",
        )
        assert obs_id > 0

        # Verify it's stored under 'local'
        observations = db.get_user_observations(user_id=None)
        assert len(observations) == 1
        assert observations[0]["text"] == "Local observation"

    def test_add_observation_with_screenshot(self, temp_db):
        """Adding observation with screenshot stores blob."""
        screenshot_bytes = b"PNG_FAKE_DATA_HERE"
        obs_id = db.add_observation(
            user_id="test_user",
            bar_index=100,
            event_context='{}',
            text="With screenshot",
            screenshot=screenshot_bytes,
        )

        # Verify screenshot can be retrieved
        retrieved = db.get_observation_screenshot(obs_id, "test_user")
        assert retrieved == screenshot_bytes


class TestLRUCleanup:
    """Tests for LRU cleanup keeping latest 20."""

    def test_lru_keeps_latest_20(self, temp_db):
        """Adding more than 20 observations keeps only latest 20."""
        user_id = "lru_test_user"

        # Add 25 observations
        for i in range(25):
            db.add_observation(
                user_id=user_id,
                bar_index=i,
                event_context='{}',
                text=f"Observation {i}",
            )

        # Should only have 20
        observations = db.get_user_observations(user_id=user_id)
        assert len(observations) == 20

        # Should have the latest ones (5-24)
        bar_indices = [obs["bar_index"] for obs in observations]
        assert 0 not in bar_indices  # Old ones removed
        assert 24 in bar_indices  # Latest kept

    def test_lru_per_user_isolation(self, temp_db):
        """Each user has their own 20-observation limit."""
        user1 = "user1"
        user2 = "user2"

        # Add 25 for user1
        for i in range(25):
            db.add_observation(user_id=user1, bar_index=i, event_context='{}', text=f"U1 {i}")

        # Add 5 for user2
        for i in range(5):
            db.add_observation(user_id=user2, bar_index=i, event_context='{}', text=f"U2 {i}")

        # User1 should have 20, user2 should have 5
        assert len(db.get_user_observations(user_id=user1)) == 20
        assert len(db.get_user_observations(user_id=user2)) == 5


class TestGetUserObservations:
    """Tests for get_user_observations function."""

    def test_returns_most_recent_first(self, temp_db):
        """Observations are returned in most-recent-first order."""
        user_id = "order_test"

        db.add_observation(user_id=user_id, bar_index=1, event_context='{}', text="First")
        db.add_observation(user_id=user_id, bar_index=2, event_context='{}', text="Second")
        db.add_observation(user_id=user_id, bar_index=3, event_context='{}', text="Third")

        observations = db.get_user_observations(user_id=user_id)
        assert observations[0]["text"] == "Third"
        assert observations[1]["text"] == "Second"
        assert observations[2]["text"] == "First"

    def test_respects_limit(self, temp_db):
        """Limit parameter restricts result count."""
        user_id = "limit_test"

        for i in range(10):
            db.add_observation(user_id=user_id, bar_index=i, event_context='{}', text=f"Obs {i}")

        observations = db.get_user_observations(user_id=user_id, limit=5)
        assert len(observations) == 5

    def test_has_screenshot_field(self, temp_db):
        """Results include has_screenshot boolean."""
        user_id = "screenshot_flag_test"

        db.add_observation(user_id=user_id, bar_index=1, event_context='{}', text="No screenshot")
        db.add_observation(
            user_id=user_id, bar_index=2, event_context='{}', text="With screenshot",
            screenshot=b"fake_png"
        )

        observations = db.get_user_observations(user_id=user_id)
        with_screenshot = next(o for o in observations if o["text"] == "With screenshot")
        without_screenshot = next(o for o in observations if o["text"] == "No screenshot")

        assert with_screenshot["has_screenshot"] is True
        assert without_screenshot["has_screenshot"] is False

    def test_user_isolation(self, temp_db):
        """Users can only see their own observations."""
        db.add_observation(user_id="alice", bar_index=1, event_context='{}', text="Alice's note")
        db.add_observation(user_id="bob", bar_index=2, event_context='{}', text="Bob's note")

        alice_obs = db.get_user_observations(user_id="alice")
        bob_obs = db.get_user_observations(user_id="bob")

        assert len(alice_obs) == 1
        assert alice_obs[0]["text"] == "Alice's note"
        assert len(bob_obs) == 1
        assert bob_obs[0]["text"] == "Bob's note"


class TestGetObservationScreenshot:
    """Tests for get_observation_screenshot function."""

    def test_returns_screenshot_bytes(self, temp_db):
        """Returns screenshot bytes for valid observation."""
        screenshot_data = b"PNG_BINARY_DATA"
        obs_id = db.add_observation(
            user_id="screenshot_user",
            bar_index=1,
            event_context='{}',
            text="Test",
            screenshot=screenshot_data,
        )

        result = db.get_observation_screenshot(obs_id, "screenshot_user")
        assert result == screenshot_data

    def test_returns_none_for_no_screenshot(self, temp_db):
        """Returns None when observation has no screenshot."""
        obs_id = db.add_observation(
            user_id="no_screenshot_user",
            bar_index=1,
            event_context='{}',
            text="No screenshot",
        )

        result = db.get_observation_screenshot(obs_id, "no_screenshot_user")
        assert result is None

    def test_returns_none_for_wrong_user(self, temp_db):
        """Returns None when user doesn't own the observation."""
        obs_id = db.add_observation(
            user_id="owner",
            bar_index=1,
            event_context='{}',
            text="Private",
            screenshot=b"data",
        )

        result = db.get_observation_screenshot(obs_id, "intruder")
        assert result is None

    def test_returns_none_for_nonexistent_id(self, temp_db):
        """Returns None for non-existent observation ID."""
        result = db.get_observation_screenshot(99999, "any_user")
        assert result is None
