"""
Tests for Issue #416 — Reference Layer P4: Opt-in Level Crossing

Tests the level crossing detection feature for tracked legs.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from src.swing_analysis.events import LevelCrossEvent
from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    STANDARD_FIB_LEVELS,
    MAX_TRACKED_LEGS,
)
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.types import Bar


def make_bar(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    """Create a bar for testing."""
    return Bar(
        index=index,
        timestamp=datetime.now(),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
    )


def make_bull_leg(
    leg_id: str,
    origin_price: float,
    pivot_price: float,
    origin_index: int = 0,
    pivot_index: int = 10,
) -> Leg:
    """Create a bull leg (origin at low, pivot at high)."""
    return Leg(
        leg_id=leg_id,
        direction="bull",
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
    )


def make_bear_leg(
    leg_id: str,
    origin_price: float,
    pivot_price: float,
    origin_index: int = 0,
    pivot_index: int = 10,
) -> Leg:
    """Create a bear leg (origin at high, pivot at low)."""
    return Leg(
        leg_id=leg_id,
        direction="bear",
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
    )


class TestLevelCrossEventDataclass:
    """Tests for LevelCrossEvent dataclass."""

    def test_level_cross_event_creation(self):
        """Test basic LevelCrossEvent creation."""
        event = LevelCrossEvent(
            bar_index=100,
            timestamp=datetime.now(),
            leg_id="leg_test_123",
            direction="bull",
            level_crossed=0.618,
            cross_direction="up",
        )

        assert event.event_type == "LEVEL_CROSS"
        assert event.leg_id == "leg_test_123"
        assert event.direction == "bull"
        assert event.level_crossed == 0.618
        assert event.cross_direction == "up"

    def test_level_cross_event_fields(self):
        """Test all fields are correctly stored."""
        ts = datetime(2024, 1, 15, 12, 0, 0)
        event = LevelCrossEvent(
            bar_index=50,
            timestamp=ts,
            leg_id="leg_bear_5000",
            direction="bear",
            level_crossed=0.382,
            cross_direction="down",
        )

        assert event.bar_index == 50
        assert event.timestamp == ts
        assert event.leg_id == "leg_bear_5000"
        assert event.direction == "bear"
        assert event.level_crossed == 0.382
        assert event.cross_direction == "down"


class TestTrackingLimit:
    """Tests for max tracked legs limit."""

    def test_max_tracked_legs_constant(self):
        """Test MAX_TRACKED_LEGS constant is 10."""
        assert MAX_TRACKED_LEGS == 10

    def test_add_tracking_respects_limit(self):
        """Test that tracking fails after max limit is reached."""
        ref_layer = ReferenceLayer()

        # Add max number of legs
        for i in range(MAX_TRACKED_LEGS):
            success, error = ref_layer.add_crossing_tracking(f"leg_{i}")
            assert success is True
            assert error is None

        # Try to add one more - should fail
        success, error = ref_layer.add_crossing_tracking("leg_excess")
        assert success is False
        assert error is not None
        assert "Maximum" in error
        assert str(MAX_TRACKED_LEGS) in error

    def test_tracking_same_leg_twice_allowed(self):
        """Test that tracking same leg twice is idempotent."""
        ref_layer = ReferenceLayer()

        # Add leg first time
        success1, _ = ref_layer.add_crossing_tracking("leg_1")
        assert success1 is True

        # Add same leg again - should succeed (idempotent)
        success2, _ = ref_layer.add_crossing_tracking("leg_1")
        assert success2 is True

        # Should only have one leg tracked
        assert len(ref_layer.get_tracked_leg_ids()) == 1

    def test_remove_allows_new_tracking(self):
        """Test that removing a leg allows new one to be added."""
        ref_layer = ReferenceLayer()

        # Fill up to max
        for i in range(MAX_TRACKED_LEGS):
            ref_layer.add_crossing_tracking(f"leg_{i}")

        # Remove one
        ref_layer.remove_crossing_tracking("leg_0")

        # Now we can add a new one
        success, error = ref_layer.add_crossing_tracking("leg_new")
        assert success is True
        assert error is None


class TestQuantizeFibLevel:
    """Tests for fib level quantization."""

    def test_quantize_exact_levels(self):
        """Test quantizing exact fib levels."""
        ref_layer = ReferenceLayer()

        for level in STANDARD_FIB_LEVELS:
            assert ref_layer._quantize_to_fib_level(level) == level

    def test_quantize_between_levels(self):
        """Test quantizing values between fib levels."""
        ref_layer = ReferenceLayer()

        # Between 0 and 0.382
        assert ref_layer._quantize_to_fib_level(0.1) == 0.0  # Closer to 0
        assert ref_layer._quantize_to_fib_level(0.3) == 0.382  # Closer to 0.382

        # Between 0.382 and 0.5
        assert ref_layer._quantize_to_fib_level(0.41) == 0.382  # Closer to 0.382
        assert ref_layer._quantize_to_fib_level(0.47) == 0.5  # Closer to 0.5

        # Between 0.5 and 0.618
        assert ref_layer._quantize_to_fib_level(0.55) == 0.5
        assert ref_layer._quantize_to_fib_level(0.6) == 0.618

    def test_quantize_below_zero(self):
        """Test quantizing values below zero."""
        ref_layer = ReferenceLayer()
        assert ref_layer._quantize_to_fib_level(-0.5) == 0.0
        assert ref_layer._quantize_to_fib_level(-1.0) == 0.0

    def test_quantize_above_two(self):
        """Test quantizing values above 2.0."""
        ref_layer = ReferenceLayer()
        assert ref_layer._quantize_to_fib_level(2.5) == 2.0
        assert ref_layer._quantize_to_fib_level(3.0) == 2.0


class TestDetectFibLevelsBetween:
    """Tests for detecting fib levels crossed between two locations."""

    def test_no_crossing_same_location(self):
        """Test no crossing when location doesn't change."""
        ref_layer = ReferenceLayer()
        crossings = ref_layer._detect_fib_levels_between(0.5, 0.5)
        assert crossings == []

    def test_crossing_up_single_level(self):
        """Test detecting single level crossed going up."""
        ref_layer = ReferenceLayer()
        crossings = ref_layer._detect_fib_levels_between(0.4, 0.6)

        # Should cross 0.5
        assert len(crossings) == 1
        assert crossings[0][0] == 0.5
        assert crossings[0][1] == "up"

    def test_crossing_down_single_level(self):
        """Test detecting single level crossed going down."""
        ref_layer = ReferenceLayer()
        crossings = ref_layer._detect_fib_levels_between(0.6, 0.4)

        # Should cross 0.5
        assert len(crossings) == 1
        assert crossings[0][0] == 0.5
        assert crossings[0][1] == "down"

    def test_crossing_multiple_levels_up(self):
        """Test detecting multiple levels crossed going up."""
        ref_layer = ReferenceLayer()
        crossings = ref_layer._detect_fib_levels_between(0.3, 0.7)

        # Should cross 0.382, 0.5, 0.618
        levels_crossed = [c[0] for c in crossings]
        assert 0.382 in levels_crossed
        assert 0.5 in levels_crossed
        assert 0.618 in levels_crossed
        for level, direction in crossings:
            assert direction == "up"

    def test_crossing_multiple_levels_down(self):
        """Test detecting multiple levels crossed going down."""
        ref_layer = ReferenceLayer()
        crossings = ref_layer._detect_fib_levels_between(0.7, 0.3)

        # Should cross 0.382, 0.5, 0.618
        levels_crossed = [c[0] for c in crossings]
        assert 0.382 in levels_crossed
        assert 0.5 in levels_crossed
        assert 0.618 in levels_crossed
        for level, direction in crossings:
            assert direction == "down"

    def test_crossing_at_boundary(self):
        """Test crossing when landing exactly on a level."""
        ref_layer = ReferenceLayer()

        # Move from below to exactly on level
        crossings = ref_layer._detect_fib_levels_between(0.4, 0.5)
        assert len(crossings) == 1
        assert crossings[0][0] == 0.5
        assert crossings[0][1] == "up"

    def test_no_crossing_within_same_zone(self):
        """Test no crossing when staying between levels."""
        ref_layer = ReferenceLayer()
        crossings = ref_layer._detect_fib_levels_between(0.41, 0.49)
        assert crossings == []


class TestDetectLevelCrossings:
    """Tests for the main level crossing detection method."""

    def test_no_crossings_when_no_tracked_legs(self):
        """Test no crossings emitted when no legs are tracked."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)
        bar = make_bar(100, 5050, 5060, 5040, 5055)

        events = ref_layer.detect_level_crossings([leg], bar)
        assert events == []

    def test_crossing_detected_on_second_bar(self):
        """Test that crossing is detected after first bar establishes baseline.

        For bull leg: location 0 = pivot (high), location 1 = origin (low).
        As price rises toward pivot, location decreases.
        """
        ref_layer = ReferenceLayer()
        # Bull leg: origin=5000, pivot=5100 (range=100)
        # Location: 0 = 5100 (pivot), 1 = 5000 (origin)
        leg = make_bull_leg("leg_bull", 5000, 5100)
        ref_layer.add_crossing_tracking("leg_bull")

        # First bar at location 0.3 (price 5070: (5100-5070)/100 = 0.3)
        bar1 = make_bar(100, 5070, 5070, 5070, 5070)
        events1 = ref_layer.detect_level_crossings([leg], bar1)
        assert events1 == []  # First bar establishes baseline

        # Second bar at location 0.7 (price 5030: (5100-5030)/100 = 0.7)
        # Crosses 0.382, 0.5, 0.618 going UP (toward origin)
        bar2 = make_bar(101, 5040, 5045, 5030, 5030)
        events2 = ref_layer.detect_level_crossings([leg], bar2)
        assert len(events2) == 3  # Crosses 0.382, 0.5, 0.618
        levels = [e.level_crossed for e in events2]
        assert 0.382 in levels
        assert 0.5 in levels
        assert 0.618 in levels
        for e in events2:
            assert e.cross_direction == "up"
            assert e.leg_id == "leg_bull"

    def test_crossing_event_fields(self):
        """Test all event fields are populated correctly.

        For bear leg: location 0 = pivot (low), location 1 = origin (high).
        As price falls toward pivot, location decreases.
        """
        ref_layer = ReferenceLayer()
        # Bear leg: origin=5100, pivot=5000 (range=100)
        # Location: 0 = 5000 (pivot), 1 = 5100 (origin)
        leg = make_bear_leg("leg_bear", 5100, 5000)
        ref_layer.add_crossing_tracking("leg_bear")

        # First bar at location 0.7 (price 5070: (5070-5000)/100 = 0.7)
        bar1 = make_bar(50, 5070, 5070, 5070, 5070)
        ref_layer.detect_level_crossings([leg], bar1)

        # Second bar at location 0.3 (price 5030: (5030-5000)/100 = 0.3)
        # Crosses 0.382, 0.5, 0.618 going DOWN (toward pivot)
        bar2 = make_bar(51, 5040, 5045, 5030, 5030)
        events = ref_layer.detect_level_crossings([leg], bar2)

        assert len(events) == 3  # Crosses 0.618, 0.5, 0.382 going down
        levels = [e.level_crossed for e in events]
        assert 0.382 in levels
        assert 0.5 in levels
        assert 0.618 in levels

        # Check first event details
        event = events[0]
        assert event.event_type == "LEVEL_CROSS"
        assert event.bar_index == 51
        assert event.leg_id == "leg_bear"
        assert event.direction == "bear"
        assert event.cross_direction == "down"

    def test_multiple_crossings_single_bar(self):
        """Test detecting multiple crossings in a single bar."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)
        ref_layer.add_crossing_tracking("leg_1")

        # First bar at 0.3 location
        bar1 = make_bar(100, 5030, 5030, 5030, 5030)
        ref_layer.detect_level_crossings([leg], bar1)

        # Second bar at 0.7 location - crosses 0.382, 0.5, 0.618
        bar2 = make_bar(101, 5040, 5070, 5035, 5070)
        events = ref_layer.detect_level_crossings([leg], bar2)

        levels = [e.level_crossed for e in events]
        assert 0.382 in levels
        assert 0.5 in levels
        assert 0.618 in levels

    def test_leg_removed_during_tracking(self):
        """Test that leg is untracked when it disappears from active legs."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)
        ref_layer.add_crossing_tracking("leg_1")

        # First bar with leg present
        bar1 = make_bar(100, 5050, 5050, 5050, 5050)
        ref_layer.detect_level_crossings([leg], bar1)
        assert "leg_1" in ref_layer.get_tracked_leg_ids()

        # Second bar with leg gone
        bar2 = make_bar(101, 5060, 5060, 5060, 5060)
        ref_layer.detect_level_crossings([], bar2)
        assert "leg_1" not in ref_layer.get_tracked_leg_ids()


class TestPendingCrossEvents:
    """Tests for pending cross events accumulation."""

    def test_pending_events_accumulate(self):
        """Test that events accumulate until retrieved."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)
        ref_layer.add_crossing_tracking("leg_1")

        # Generate first event
        bar1 = make_bar(100, 5050, 5050, 5050, 5050)
        ref_layer.detect_level_crossings([leg], bar1)
        bar2 = make_bar(101, 5070, 5070, 5070, 5070)
        ref_layer.detect_level_crossings([leg], bar2)

        # Generate second event
        bar3 = make_bar(102, 5040, 5040, 5040, 5040)
        ref_layer.detect_level_crossings([leg], bar3)

        # Should have accumulated events
        pending = ref_layer.get_pending_cross_events()
        assert len(pending) >= 1  # At least the 0.618 crossing from bar2

    def test_pending_events_cleared_on_get(self):
        """Test that events are cleared after retrieval by default."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)
        ref_layer.add_crossing_tracking("leg_1")

        bar1 = make_bar(100, 5050, 5050, 5050, 5050)
        ref_layer.detect_level_crossings([leg], bar1)
        bar2 = make_bar(101, 5070, 5070, 5070, 5070)
        ref_layer.detect_level_crossings([leg], bar2)

        # First get returns events
        pending1 = ref_layer.get_pending_cross_events()
        assert len(pending1) >= 1

        # Second get returns empty
        pending2 = ref_layer.get_pending_cross_events()
        assert pending2 == []

    def test_pending_events_preserve_on_request(self):
        """Test that events can be preserved by setting clear=False."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)
        ref_layer.add_crossing_tracking("leg_1")

        bar1 = make_bar(100, 5050, 5050, 5050, 5050)
        ref_layer.detect_level_crossings([leg], bar1)
        bar2 = make_bar(101, 5070, 5070, 5070, 5070)
        ref_layer.detect_level_crossings([leg], bar2)

        # Get without clearing
        pending1 = ref_layer.get_pending_cross_events(clear=False)
        pending2 = ref_layer.get_pending_cross_events(clear=False)

        assert pending1 == pending2


class TestClearCrossingState:
    """Tests for clearing crossing state."""

    def test_clear_crossing_state_clears_all(self):
        """Test that clear_crossing_state clears all tracking state."""
        ref_layer = ReferenceLayer()
        leg = make_bull_leg("leg_1", 5000, 5100)

        # Set up tracking
        ref_layer.add_crossing_tracking("leg_1")
        bar1 = make_bar(100, 5050, 5050, 5050, 5050)
        ref_layer.detect_level_crossings([leg], bar1)
        bar2 = make_bar(101, 5070, 5070, 5070, 5070)
        ref_layer.detect_level_crossings([leg], bar2)

        # Clear
        ref_layer.clear_crossing_state()

        assert len(ref_layer.get_tracked_leg_ids()) == 0
        assert ref_layer.get_pending_cross_events() == []
        assert ref_layer._last_level == {}


class TestCopyStateFrom:
    """Tests for copy_state_from with crossing state."""

    def test_copy_state_from_copies_crossing_state(self):
        """Test that copy_state_from copies all crossing tracking state."""
        ref_layer1 = ReferenceLayer()
        ref_layer1.add_crossing_tracking("leg_1")
        ref_layer1.add_crossing_tracking("leg_2")
        ref_layer1._last_level["leg_1"] = 0.5
        ref_layer1._last_level["leg_2"] = 0.618

        # Create event
        event = LevelCrossEvent(
            bar_index=100,
            timestamp=datetime.now(),
            leg_id="leg_1",
            direction="bull",
            level_crossed=0.5,
            cross_direction="up",
        )
        ref_layer1._pending_cross_events.append(event)

        # Copy to new layer
        ref_layer2 = ReferenceLayer()
        ref_layer2.copy_state_from(ref_layer1)

        assert ref_layer2.get_tracked_leg_ids() == ref_layer1.get_tracked_leg_ids()
        assert ref_layer2._last_level == ref_layer1._last_level
        assert len(ref_layer2._pending_cross_events) == 1


class TestStandardFibLevels:
    """Tests for STANDARD_FIB_LEVELS constant."""

    def test_standard_fib_levels_ordered(self):
        """Test that STANDARD_FIB_LEVELS are in ascending order."""
        for i in range(1, len(STANDARD_FIB_LEVELS)):
            assert STANDARD_FIB_LEVELS[i] > STANDARD_FIB_LEVELS[i-1]

    def test_standard_fib_levels_contains_key_levels(self):
        """Test that STANDARD_FIB_LEVELS contains expected key levels."""
        assert 0.0 in STANDARD_FIB_LEVELS
        assert 0.382 in STANDARD_FIB_LEVELS
        assert 0.5 in STANDARD_FIB_LEVELS
        assert 0.618 in STANDARD_FIB_LEVELS
        assert 1.0 in STANDARD_FIB_LEVELS
        assert 2.0 in STANDARD_FIB_LEVELS
