"""
Tests for swing detection events.

Tests event creation, type discrimination, explanation generation,
and serialization for all event types.
"""

import json
from datetime import datetime
from decimal import Decimal

import pytest

from src.swing_analysis.events import (
    SwingEvent,
    SwingFormedEvent,
    SwingInvalidatedEvent,
    SwingCompletedEvent,
    LevelCrossEvent,
    LegCreatedEvent,
    LegPrunedEvent,
    LegInvalidatedEvent,
)


class TestEventTypeDiscrimination:
    """Test that event types are correctly set and can be discriminated."""

    def test_swing_formed_event_type(self):
        """SwingFormedEvent has correct event_type."""
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test123",
        )
        assert event.event_type == "SWING_FORMED"

    def test_swing_invalidated_event_type(self):
        """SwingInvalidatedEvent has correct event_type."""
        event = SwingInvalidatedEvent(
            bar_index=200,
            timestamp=datetime.now(),
            swing_id="test123",
        )
        assert event.event_type == "SWING_INVALIDATED"

    def test_swing_completed_event_type(self):
        """SwingCompletedEvent has correct event_type."""
        event = SwingCompletedEvent(
            bar_index=300,
            timestamp=datetime.now(),
            swing_id="test123",
        )
        assert event.event_type == "SWING_COMPLETED"

    def test_level_cross_event_type(self):
        """LevelCrossEvent has correct event_type."""
        event = LevelCrossEvent(
            bar_index=150,
            timestamp=datetime.now(),
            swing_id="test123",
        )
        assert event.event_type == "LEVEL_CROSS"

    def test_event_type_cannot_be_overridden(self):
        """Event type is set automatically, not via init."""
        # event_type is not in init, so we can't pass it
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test123",
        )
        # Confirm it's always SWING_FORMED
        assert event.event_type == "SWING_FORMED"

    def test_filter_events_by_type(self):
        """Can filter a list of events by type."""
        now = datetime.now()
        events = [
            SwingFormedEvent(bar_index=100, timestamp=now, swing_id="s1"),
            SwingInvalidatedEvent(bar_index=200, timestamp=now, swing_id="s2"),
            LevelCrossEvent(bar_index=150, timestamp=now, swing_id="s1"),
            SwingCompletedEvent(bar_index=300, timestamp=now, swing_id="s1"),
            SwingFormedEvent(bar_index=400, timestamp=now, swing_id="s3"),
        ]

        formed = [e for e in events if e.event_type == "SWING_FORMED"]
        assert len(formed) == 2

        level_crosses = [e for e in events if e.event_type == "LEVEL_CROSS"]
        assert len(level_crosses) == 1


class TestSwingFormedEvent:
    """Test SwingFormedEvent creation and explanation."""

    def test_bull_swing_creation(self):
        """Create a bull swing formed event."""
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="bull001",
            high_bar_index=80,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bull",
            parent_ids=["parent01", "parent02"],
        )

        assert event.swing_id == "bull001"
        assert event.direction == "bull"
        assert event.high_price == Decimal("5100.00")
        assert event.low_price == Decimal("5000.00")
        assert len(event.parent_ids) == 2

    def test_bear_swing_creation(self):
        """Create a bear swing formed event."""
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="bear001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=80,
            low_price=Decimal("5000.00"),
            direction="bear",
            parent_ids=[],
        )

        assert event.direction == "bear"
        assert event.parent_ids == []

    def test_bull_explanation(self):
        """Bull swing explanation describes upward active zone."""
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test",
            high_price=Decimal("5100.00"),
            low_price=Decimal("5000.00"),
            direction="bull",
        )

        explanation = event.get_explanation()
        assert "0.382" in explanation
        assert "Active range" in explanation
        # Bull: 0.382 = 5000 + 100 * 0.382 = 5038.20
        assert "5038.20" in explanation

    def test_bear_explanation(self):
        """Bear swing explanation describes downward active zone."""
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test",
            high_price=Decimal("5100.00"),
            low_price=Decimal("5000.00"),
            direction="bear",
        )

        explanation = event.get_explanation()
        assert "0.382" in explanation
        assert "below" in explanation
        # Bear: 0.382 = 5100 - 100 * 0.382 = 5061.80
        assert "5061.80" in explanation


class TestSwingInvalidatedEvent:
    """Test SwingInvalidatedEvent creation and explanation."""

    def test_invalidation_creation(self):
        """Create an invalidation event."""
        event = SwingInvalidatedEvent(
            bar_index=200,
            timestamp=datetime(2025, 1, 15, 11, 0, 0),
            swing_id="test123",
            violation_price=Decimal("4990.00"),
            excess_amount=Decimal("10.00"),
        )

        assert event.violation_price == Decimal("4990.00")
        assert event.excess_amount == Decimal("10.00")

    def test_invalidation_explanation(self):
        """Invalidation explanation describes pivot break."""
        event = SwingInvalidatedEvent(
            bar_index=200,
            timestamp=datetime.now(),
            swing_id="test123",
            violation_price=Decimal("4990.00"),
            excess_amount=Decimal("10.00"),
        )

        explanation = event.get_explanation()
        assert "4990.00" in explanation
        assert "10.00" in explanation
        assert "invalidated" in explanation

    def test_negative_excess_uses_absolute_value(self):
        """Negative excess amount is displayed as absolute value."""
        event = SwingInvalidatedEvent(
            bar_index=200,
            timestamp=datetime.now(),
            swing_id="test123",
            violation_price=Decimal("5110.00"),
            excess_amount=Decimal("-10.00"),
        )

        explanation = event.get_explanation()
        # Should show 10.00, not -10.00
        assert "10.00" in explanation


class TestSwingCompletedEvent:
    """Test SwingCompletedEvent creation."""

    def test_completion_creation(self):
        """Create a completion event."""
        event = SwingCompletedEvent(
            bar_index=300,
            timestamp=datetime(2025, 1, 15, 12, 0, 0),
            swing_id="test123",
            completion_price=Decimal("5200.00"),
        )

        assert event.completion_price == Decimal("5200.00")
        assert event.event_type == "SWING_COMPLETED"


class TestLevelCrossEvent:
    """Test LevelCrossEvent creation and explanation."""

    def test_level_cross_creation(self):
        """Create a level cross event."""
        event = LevelCrossEvent(
            bar_index=150,
            timestamp=datetime(2025, 1, 15, 10, 45, 0),
            swing_id="test123",
            level=0.618,
            previous_level=0.5,
            price=Decimal("5061.80"),
        )

        assert event.level == 0.618
        assert event.previous_level == 0.5
        assert event.price == Decimal("5061.80")

    def test_upward_cross_explanation(self):
        """Upward level cross explanation."""
        event = LevelCrossEvent(
            bar_index=150,
            timestamp=datetime.now(),
            swing_id="test123",
            level=0.618,
            previous_level=0.5,
            price=Decimal("5061.80"),
        )

        explanation = event.get_explanation()
        assert "up" in explanation
        assert "0.618" in explanation
        assert "0.500" in explanation
        assert "below" in explanation and "above" in explanation

    def test_downward_cross_explanation(self):
        """Downward level cross explanation."""
        event = LevelCrossEvent(
            bar_index=150,
            timestamp=datetime.now(),
            swing_id="test123",
            level=0.382,
            previous_level=0.5,
            price=Decimal("5038.20"),
        )

        explanation = event.get_explanation()
        assert "down" in explanation
        assert "0.382" in explanation


class TestEventSerialization:
    """Test that events can be serialized to/from JSON-compatible dicts."""

    def test_swing_formed_serialization(self):
        """SwingFormedEvent can be serialized to dict."""
        ts = datetime(2025, 1, 15, 10, 30, 0)
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test123",
            high_bar_index=80,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bull",
            parent_ids=["p1"],
        )

        # Convert to dict (dataclass fields)
        data = {
            "event_type": event.event_type,
            "bar_index": event.bar_index,
            "timestamp": event.timestamp.isoformat(),
            "swing_id": event.swing_id,
            "high_bar_index": event.high_bar_index,
            "high_price": str(event.high_price),
            "low_bar_index": event.low_bar_index,
            "low_price": str(event.low_price),
            "direction": event.direction,
            "parent_ids": event.parent_ids,
        }

        # Verify JSON serializable
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "SWING_FORMED"
        assert parsed["swing_id"] == "test123"
        assert parsed["high_price"] == "5100.00"

    def test_all_event_types_json_serializable(self):
        """All event types can be converted to JSON."""
        ts = datetime(2025, 1, 15, 10, 30, 0)

        events = [
            SwingFormedEvent(
                bar_index=100,
                timestamp=ts,
                swing_id="s1",
                direction="bull",
            ),
            SwingInvalidatedEvent(
                bar_index=200,
                timestamp=ts,
                swing_id="s2",
                violation_price=Decimal("5000"),
                excess_amount=Decimal("10"),
            ),
            SwingCompletedEvent(
                bar_index=300,
                timestamp=ts,
                swing_id="s3",
                completion_price=Decimal("5200"),
            ),
            LevelCrossEvent(
                bar_index=150,
                timestamp=ts,
                swing_id="s4",
                level=0.618,
                previous_level=0.5,
                price=Decimal("5062"),
            ),
        ]

        for event in events:
            # Basic serialization approach
            data = {
                "event_type": event.event_type,
                "bar_index": event.bar_index,
                "timestamp": event.timestamp.isoformat(),
                "swing_id": event.swing_id,
            }
            json_str = json.dumps(data)
            parsed = json.loads(json_str)
            assert parsed["event_type"] == event.event_type


class TestEventEquality:
    """Test event comparison and equality."""

    def test_same_event_data_equal(self):
        """Events with same data are equal."""
        ts = datetime(2025, 1, 15, 10, 30, 0)

        event1 = SwingFormedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test123",
            direction="bull",
        )
        event2 = SwingFormedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test123",
            direction="bull",
        )

        assert event1 == event2

    def test_different_swing_id_not_equal(self):
        """Events with different swing_id are not equal."""
        ts = datetime(2025, 1, 15, 10, 30, 0)

        event1 = SwingFormedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test123",
        )
        event2 = SwingFormedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test456",
        )

        assert event1 != event2

    def test_different_event_types_not_equal(self):
        """Different event types are not equal."""
        ts = datetime(2025, 1, 15, 10, 30, 0)

        formed = SwingFormedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test123",
        )
        completed = SwingCompletedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="test123",
        )

        assert formed != completed


class TestEventDefaults:
    """Test that events have sensible defaults."""

    def test_swing_formed_defaults(self):
        """SwingFormedEvent has correct defaults."""
        event = SwingFormedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test",
        )

        assert event.high_bar_index == 0
        assert event.high_price == Decimal("0")
        assert event.low_bar_index == 0
        assert event.low_price == Decimal("0")
        assert event.direction == ""
        assert event.parent_ids == []

    def test_swing_invalidated_defaults(self):
        """SwingInvalidatedEvent has correct defaults."""
        event = SwingInvalidatedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test",
        )

        assert event.violation_price == Decimal("0")
        assert event.excess_amount == Decimal("0")

    def test_level_cross_defaults(self):
        """LevelCrossEvent has correct defaults."""
        event = LevelCrossEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="test",
        )

        assert event.level == 0.0
        assert event.previous_level == 0.0
        assert event.price == Decimal("0")


class TestLegCreatedEvent:
    """Test LegCreatedEvent creation and fields."""

    def test_leg_created_event_type(self):
        """LegCreatedEvent has correct event_type."""
        event = LegCreatedEvent(
            bar_index=50,
            timestamp=datetime.now(),
            swing_id="",
            leg_id="leg_abc123",
            direction="bull",
            pivot_price=Decimal("5000.00"),
            pivot_index=40,
            origin_price=Decimal("5100.00"),
            origin_index=50,
        )
        assert event.event_type == "LEG_CREATED"

    def test_bull_leg_creation(self):
        """Create a bull leg created event."""
        event = LegCreatedEvent(
            bar_index=50,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="",
            leg_id="leg_bull001",
            direction="bull",
            pivot_price=Decimal("5000.00"),
            pivot_index=40,
            origin_price=Decimal("5100.00"),
            origin_index=50,
        )

        assert event.leg_id == "leg_bull001"
        assert event.direction == "bull"
        assert event.pivot_price == Decimal("5000.00")
        assert event.origin_price == Decimal("5100.00")
        assert event.pivot_index == 40
        assert event.origin_index == 50

    def test_bear_leg_creation(self):
        """Create a bear leg created event."""
        event = LegCreatedEvent(
            bar_index=60,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="",
            leg_id="leg_bear001",
            direction="bear",
            pivot_price=Decimal("5200.00"),
            pivot_index=50,
            origin_price=Decimal("5000.00"),
            origin_index=60,
        )

        assert event.leg_id == "leg_bear001"
        assert event.direction == "bear"
        assert event.pivot_price == Decimal("5200.00")
        assert event.origin_price == Decimal("5000.00")

    def test_leg_created_defaults(self):
        """LegCreatedEvent has correct defaults."""
        event = LegCreatedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="",
        )

        assert event.leg_id == ""
        assert event.direction == ""
        assert event.pivot_price == Decimal("0")
        assert event.pivot_index == 0
        assert event.origin_price == Decimal("0")
        assert event.origin_index == 0


class TestLegPrunedEvent:
    """Test LegPrunedEvent creation and fields."""

    def test_leg_pruned_event_type(self):
        """LegPrunedEvent has correct event_type."""
        event = LegPrunedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="",
            leg_id="leg_abc123",
            reason="staleness",
        )
        assert event.event_type == "LEG_PRUNED"

    def test_staleness_pruning(self):
        """Create a leg pruned event due to staleness."""
        event = LegPrunedEvent(
            bar_index=100,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="",
            leg_id="leg_stale001",
            reason="staleness",
        )

        assert event.leg_id == "leg_stale001"
        assert event.reason == "staleness"

    def test_dominance_pruning(self):
        """Create a leg pruned event due to dominance."""
        event = LegPrunedEvent(
            bar_index=100,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="",
            leg_id="leg_dom001",
            reason="dominance",
        )

        assert event.leg_id == "leg_dom001"
        assert event.reason == "dominance"

    def test_leg_pruned_defaults(self):
        """LegPrunedEvent has correct defaults."""
        event = LegPrunedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="",
        )

        assert event.leg_id == ""
        assert event.reason == ""


class TestLegInvalidatedEvent:
    """Test LegInvalidatedEvent creation and fields."""

    def test_leg_invalidated_event_type(self):
        """LegInvalidatedEvent has correct event_type."""
        event = LegInvalidatedEvent(
            bar_index=75,
            timestamp=datetime.now(),
            swing_id="",
            leg_id="leg_abc123",
            invalidation_price=Decimal("4961.80"),
        )
        assert event.event_type == "LEG_INVALIDATED"

    def test_bull_leg_invalidation(self):
        """Create a bull leg invalidated event."""
        event = LegInvalidatedEvent(
            bar_index=75,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="",
            leg_id="leg_bull001",
            invalidation_price=Decimal("4961.80"),
        )

        assert event.leg_id == "leg_bull001"
        assert event.invalidation_price == Decimal("4961.80")

    def test_leg_with_formed_swing(self):
        """LegInvalidatedEvent can reference a formed swing."""
        event = LegInvalidatedEvent(
            bar_index=75,
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            swing_id="swing_abc123",  # Leg had formed into a swing
            leg_id="leg_bull001",
            invalidation_price=Decimal("4961.80"),
        )

        assert event.swing_id == "swing_abc123"
        assert event.leg_id == "leg_bull001"

    def test_leg_invalidated_defaults(self):
        """LegInvalidatedEvent has correct defaults."""
        event = LegInvalidatedEvent(
            bar_index=100,
            timestamp=datetime.now(),
            swing_id="",
        )

        assert event.leg_id == ""
        assert event.invalidation_price == Decimal("0")


class TestLegEventTypeDiscrimination:
    """Test that leg event types can be filtered and discriminated."""

    def test_filter_leg_events_by_type(self):
        """Can filter a list of events by leg event type."""
        now = datetime.now()
        events = [
            LegCreatedEvent(bar_index=50, timestamp=now, swing_id="", leg_id="l1", direction="bull"),
            LegCreatedEvent(bar_index=60, timestamp=now, swing_id="", leg_id="l2", direction="bear"),
            LegPrunedEvent(bar_index=100, timestamp=now, swing_id="", leg_id="l1", reason="staleness"),
            LegInvalidatedEvent(bar_index=75, timestamp=now, swing_id="", leg_id="l3"),
            SwingFormedEvent(bar_index=80, timestamp=now, swing_id="s1"),  # Regular swing event
        ]

        leg_created = [e for e in events if e.event_type == "LEG_CREATED"]
        assert len(leg_created) == 2

        leg_pruned = [e for e in events if e.event_type == "LEG_PRUNED"]
        assert len(leg_pruned) == 1

        leg_invalidated = [e for e in events if e.event_type == "LEG_INVALIDATED"]
        assert len(leg_invalidated) == 1

    def test_all_leg_event_types_distinct(self):
        """Each leg event type has a distinct event_type string."""
        now = datetime.now()

        created = LegCreatedEvent(bar_index=50, timestamp=now, swing_id="")
        pruned = LegPrunedEvent(bar_index=100, timestamp=now, swing_id="")
        invalidated = LegInvalidatedEvent(bar_index=75, timestamp=now, swing_id="")

        event_types = {created.event_type, pruned.event_type, invalidated.event_type}
        assert len(event_types) == 3
        assert event_types == {"LEG_CREATED", "LEG_PRUNED", "LEG_INVALIDATED"}


class TestLegEventSerialization:
    """Test that leg events can be serialized to JSON-compatible dicts."""

    def test_leg_created_serialization(self):
        """LegCreatedEvent can be serialized to dict."""
        ts = datetime(2025, 1, 15, 10, 30, 0)
        event = LegCreatedEvent(
            bar_index=50,
            timestamp=ts,
            swing_id="",
            leg_id="leg_001",
            direction="bull",
            pivot_price=Decimal("5000.00"),
            pivot_index=40,
            origin_price=Decimal("5100.00"),
            origin_index=50,
        )

        data = {
            "event_type": event.event_type,
            "bar_index": event.bar_index,
            "timestamp": event.timestamp.isoformat(),
            "swing_id": event.swing_id,
            "leg_id": event.leg_id,
            "direction": event.direction,
            "pivot_price": str(event.pivot_price),
            "pivot_index": event.pivot_index,
            "origin_price": str(event.origin_price),
            "origin_index": event.origin_index,
        }

        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "LEG_CREATED"
        assert parsed["leg_id"] == "leg_001"
        assert parsed["direction"] == "bull"
        assert parsed["pivot_price"] == "5000.00"

    def test_leg_pruned_serialization(self):
        """LegPrunedEvent can be serialized to dict."""
        ts = datetime(2025, 1, 15, 10, 30, 0)
        event = LegPrunedEvent(
            bar_index=100,
            timestamp=ts,
            swing_id="",
            leg_id="leg_002",
            reason="staleness",
        )

        data = {
            "event_type": event.event_type,
            "bar_index": event.bar_index,
            "timestamp": event.timestamp.isoformat(),
            "swing_id": event.swing_id,
            "leg_id": event.leg_id,
            "reason": event.reason,
        }

        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "LEG_PRUNED"
        assert parsed["leg_id"] == "leg_002"
        assert parsed["reason"] == "staleness"

    def test_leg_invalidated_serialization(self):
        """LegInvalidatedEvent can be serialized to dict."""
        ts = datetime(2025, 1, 15, 10, 30, 0)
        event = LegInvalidatedEvent(
            bar_index=75,
            timestamp=ts,
            swing_id="swing_001",
            leg_id="leg_003",
            invalidation_price=Decimal("4961.80"),
        )

        data = {
            "event_type": event.event_type,
            "bar_index": event.bar_index,
            "timestamp": event.timestamp.isoformat(),
            "swing_id": event.swing_id,
            "leg_id": event.leg_id,
            "invalidation_price": str(event.invalidation_price),
        }

        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "LEG_INVALIDATED"
        assert parsed["leg_id"] == "leg_003"
        assert parsed["invalidation_price"] == "4961.80"

    def test_all_leg_events_json_serializable(self):
        """All leg event types can be converted to JSON."""
        ts = datetime(2025, 1, 15, 10, 30, 0)

        events = [
            LegCreatedEvent(bar_index=50, timestamp=ts, swing_id="", leg_id="l1", direction="bull"),
            LegPrunedEvent(bar_index=100, timestamp=ts, swing_id="", leg_id="l2", reason="staleness"),
            LegInvalidatedEvent(bar_index=75, timestamp=ts, swing_id="", leg_id="l3"),
        ]

        for event in events:
            data = {
                "event_type": event.event_type,
                "bar_index": event.bar_index,
                "timestamp": event.timestamp.isoformat(),
                "swing_id": event.swing_id,
            }
            json_str = json.dumps(data)
            parsed = json.loads(json_str)
            assert parsed["event_type"] == event.event_type
