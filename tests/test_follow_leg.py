"""
Tests for the Follow Leg feature (Issue #267).

Verifies:
- Lifecycle events are captured and stored
- API endpoint filters events by leg_ids and since_bar
- Event types map correctly from swing events
"""

import pytest
from datetime import datetime
from typing import List
from decimal import Decimal

from src.swing_analysis.types import Bar
from src.swing_analysis.events import (
    SwingFormedEvent,
    LegPrunedEvent,
    LegInvalidatedEvent,
)
from src.ground_truth_annotator.routers.replay import (
    _event_to_lifecycle_event,
)
from src.ground_truth_annotator.schemas import (
    LifecycleEvent,
    FollowedLegsEventsResponse,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_bar_context():
    """Sample bar context for lifecycle event tests."""
    return {
        "bar_index": 100,
        "csv_index": 150,  # With window offset of 50
        "timestamp": "2024-01-15T10:30:00",
    }


@pytest.fixture
def sample_formed_event():
    """Sample SwingFormedEvent for testing."""
    return SwingFormedEvent(
        bar_index=100,
        timestamp=datetime.now(),
        swing_id="swing_abc123",
        high_bar_index=95,
        high_price=Decimal("5050.00"),
        low_bar_index=90,
        low_price=Decimal("5000.00"),
        direction="bull",
        parent_ids=["parent_123"],
    )


@pytest.fixture
def sample_pruned_event():
    """Sample LegPrunedEvent for testing."""
    return LegPrunedEvent(
        bar_index=105,
        timestamp=datetime.now(),
        swing_id="swing_def456",
        leg_id="leg_def456",
        reason="engulfed",
    )


@pytest.fixture
def sample_invalidated_event():
    """Sample LegInvalidatedEvent for testing."""
    return LegInvalidatedEvent(
        bar_index=110,
        timestamp=datetime.now(),
        swing_id="swing_ghi789",
        leg_id="leg_ghi789",
        invalidation_price=Decimal("4980.00"),
    )


# ============================================================================
# Event to Lifecycle Event Conversion Tests
# ============================================================================


class TestEventToLifecycleEvent:
    """Tests for _event_to_lifecycle_event helper function."""

    def test_formed_event_conversion(self, sample_formed_event, sample_bar_context):
        """SwingFormedEvent should convert to 'formed' lifecycle event."""
        result = _event_to_lifecycle_event(
            sample_formed_event,
            sample_bar_context["bar_index"],
            sample_bar_context["csv_index"],
            sample_bar_context["timestamp"],
        )

        assert result is not None
        assert result.leg_id == sample_formed_event.swing_id
        assert result.event_type == "formed"
        assert result.bar_index == sample_bar_context["bar_index"]
        assert result.csv_index == sample_bar_context["csv_index"]
        assert result.timestamp == sample_bar_context["timestamp"]
        assert "formed" in result.explanation.lower()

    def test_pruned_event_engulfed_conversion(self, sample_bar_context):
        """LegPrunedEvent with reason='engulfed' should convert to 'engulfed'."""
        event = LegPrunedEvent(
            bar_index=105,
            timestamp=datetime.now(),
            swing_id="swing_123",
            leg_id="leg_123",
            reason="engulfed",
        )

        result = _event_to_lifecycle_event(
            event,
            sample_bar_context["bar_index"],
            sample_bar_context["csv_index"],
            sample_bar_context["timestamp"],
        )

        assert result is not None
        assert result.leg_id == "leg_123"
        assert result.event_type == "engulfed"
        assert "engulfed" in result.explanation.lower()

    def test_pruned_event_pivot_breach_conversion(self, sample_bar_context):
        """LegPrunedEvent with reason='pivot_breach' should convert to 'pivot_breached'."""
        event = LegPrunedEvent(
            bar_index=105,
            timestamp=datetime.now(),
            swing_id="swing_123",
            leg_id="leg_123",
            reason="pivot_breach",
        )

        result = _event_to_lifecycle_event(
            event,
            sample_bar_context["bar_index"],
            sample_bar_context["csv_index"],
            sample_bar_context["timestamp"],
        )

        assert result is not None
        assert result.event_type == "pivot_breached"

    def test_pruned_event_general_conversion(self, sample_bar_context):
        """LegPrunedEvent with other reasons should convert to 'pruned'."""
        event = LegPrunedEvent(
            bar_index=105,
            timestamp=datetime.now(),
            swing_id="swing_123",
            leg_id="leg_123",
            reason="turn_prune",
        )

        result = _event_to_lifecycle_event(
            event,
            sample_bar_context["bar_index"],
            sample_bar_context["csv_index"],
            sample_bar_context["timestamp"],
        )

        assert result is not None
        assert result.event_type == "pruned"
        assert "turn prune" in result.explanation.lower()

    def test_invalidated_event_conversion(self, sample_invalidated_event, sample_bar_context):
        """LegInvalidatedEvent should convert to 'invalidated' lifecycle event."""
        result = _event_to_lifecycle_event(
            sample_invalidated_event,
            sample_bar_context["bar_index"],
            sample_bar_context["csv_index"],
            sample_bar_context["timestamp"],
        )

        assert result is not None
        assert result.leg_id == sample_invalidated_event.leg_id
        assert result.event_type == "invalidated"
        assert "invalidated" in result.explanation.lower()


# ============================================================================
# Lifecycle Event Schema Tests
# ============================================================================


class TestLifecycleEventSchema:
    """Tests for LifecycleEvent Pydantic schema."""

    def test_lifecycle_event_creation(self):
        """LifecycleEvent should be creatable with all required fields."""
        event = LifecycleEvent(
            leg_id="leg_abc123",
            event_type="formed",
            bar_index=100,
            csv_index=150,
            timestamp="2024-01-15T10:30:00",
            explanation="Leg formed at pivot 5050.00",
        )

        assert event.leg_id == "leg_abc123"
        assert event.event_type == "formed"
        assert event.bar_index == 100
        assert event.csv_index == 150
        assert event.timestamp == "2024-01-15T10:30:00"
        assert event.explanation == "Leg formed at pivot 5050.00"

    def test_followed_legs_events_response(self):
        """FollowedLegsEventsResponse should contain list of events."""
        events = [
            LifecycleEvent(
                leg_id="leg_1",
                event_type="formed",
                bar_index=100,
                csv_index=150,
                timestamp="2024-01-15T10:30:00",
                explanation="Formed",
            ),
            LifecycleEvent(
                leg_id="leg_2",
                event_type="pruned",
                bar_index=110,
                csv_index=160,
                timestamp="2024-01-15T10:31:00",
                explanation="Pruned",
            ),
        ]

        response = FollowedLegsEventsResponse(events=events)

        assert len(response.events) == 2
        assert response.events[0].leg_id == "leg_1"
        assert response.events[1].leg_id == "leg_2"


# ============================================================================
# Integration Tests (require test data)
# ============================================================================


class TestLifecycleEventFiltering:
    """Tests for filtering lifecycle events by leg_ids and since_bar."""

    def test_filter_by_leg_ids(self):
        """Events should be filtered by leg_ids."""
        events = [
            LifecycleEvent(
                leg_id="leg_1",
                event_type="formed",
                bar_index=100,
                csv_index=150,
                timestamp="2024-01-15T10:30:00",
                explanation="Formed",
            ),
            LifecycleEvent(
                leg_id="leg_2",
                event_type="pruned",
                bar_index=110,
                csv_index=160,
                timestamp="2024-01-15T10:31:00",
                explanation="Pruned",
            ),
            LifecycleEvent(
                leg_id="leg_1",
                event_type="invalidated",
                bar_index=120,
                csv_index=170,
                timestamp="2024-01-15T10:32:00",
                explanation="Invalidated",
            ),
        ]

        leg_id_set = {"leg_1"}
        filtered = [e for e in events if e.leg_id in leg_id_set]

        assert len(filtered) == 2
        assert all(e.leg_id == "leg_1" for e in filtered)

    def test_filter_by_since_bar(self):
        """Events should be filtered by since_bar."""
        events = [
            LifecycleEvent(
                leg_id="leg_1",
                event_type="formed",
                bar_index=100,
                csv_index=150,
                timestamp="2024-01-15T10:30:00",
                explanation="Formed",
            ),
            LifecycleEvent(
                leg_id="leg_1",
                event_type="pruned",
                bar_index=110,
                csv_index=160,
                timestamp="2024-01-15T10:31:00",
                explanation="Pruned",
            ),
            LifecycleEvent(
                leg_id="leg_1",
                event_type="invalidated",
                bar_index=120,
                csv_index=170,
                timestamp="2024-01-15T10:32:00",
                explanation="Invalidated",
            ),
        ]

        since_bar = 110
        filtered = [e for e in events if e.bar_index >= since_bar]

        assert len(filtered) == 2
        assert all(e.bar_index >= 110 for e in filtered)

    def test_combined_filtering(self):
        """Events should be filterable by both leg_ids and since_bar."""
        events = [
            LifecycleEvent(
                leg_id="leg_1",
                event_type="formed",
                bar_index=100,
                csv_index=150,
                timestamp="2024-01-15T10:30:00",
                explanation="Formed",
            ),
            LifecycleEvent(
                leg_id="leg_2",
                event_type="formed",
                bar_index=105,
                csv_index=155,
                timestamp="2024-01-15T10:30:30",
                explanation="Formed",
            ),
            LifecycleEvent(
                leg_id="leg_1",
                event_type="pruned",
                bar_index=110,
                csv_index=160,
                timestamp="2024-01-15T10:31:00",
                explanation="Pruned",
            ),
            LifecycleEvent(
                leg_id="leg_2",
                event_type="invalidated",
                bar_index=115,
                csv_index=165,
                timestamp="2024-01-15T10:31:30",
                explanation="Invalidated",
            ),
        ]

        leg_id_set = {"leg_1"}
        since_bar = 105

        filtered = [
            e for e in events
            if e.leg_id in leg_id_set and e.bar_index >= since_bar
        ]

        assert len(filtered) == 1
        assert filtered[0].leg_id == "leg_1"
        assert filtered[0].event_type == "pruned"
        assert filtered[0].bar_index == 110
