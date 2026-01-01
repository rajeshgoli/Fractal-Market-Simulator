"""
Tests for detector state management: initialization, serialization, restoration.

Tests the core state management of the HierarchicalDetector/LegDetector.
"""

import pytest
from decimal import Decimal

from src.swing_analysis.dag import (
    HierarchicalDetector,
    DetectorState,
    calibrate,
)
from src.swing_analysis.detection_config import DetectionConfig

from conftest import make_bar


class TestDetectorStateSerialization:
    """Test DetectorState serialization and deserialization."""

    def test_empty_state_roundtrip(self):
        """Empty state serializes and deserializes correctly."""
        state = DetectorState()
        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert restored.last_bar_index == -1
        assert len(restored.active_legs) == 0

    def test_state_with_legs_roundtrip(self):
        """State with active legs serializes and deserializes correctly."""
        from src.swing_analysis.dag import Leg

        leg1 = Leg(
            direction="bull",
            pivot_price=Decimal("100"),
            pivot_index=0,
            origin_price=Decimal("110"),
            origin_index=10,
        )
        leg2 = Leg(
            direction="bear",
            pivot_price=Decimal("108"),
            pivot_index=20,
            origin_price=Decimal("102"),
            origin_index=30,
        )

        state = DetectorState(
            active_legs=[leg1, leg2],
            all_swing_ranges=[abs(leg1.origin_price - leg1.pivot_price)],
        )
        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert len(restored.active_legs) == 2
        assert restored.active_legs[0].direction == "bull"
        assert restored.active_legs[1].direction == "bear"


class TestHierarchicalDetectorInitialization:
    """Test detector initialization."""

    def test_default_config(self):
        """Detector initializes with default config."""
        detector = HierarchicalDetector()
        assert detector.config is not None
        assert detector.config == DetectionConfig.default()

    def test_custom_config(self):
        """Detector accepts custom config (#294)."""
        config = DetectionConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.10,
            origin_time_prune_threshold=0.20,
        )
        detector = HierarchicalDetector(config)
        assert detector.config.origin_range_prune_threshold == 0.10
        assert detector.config.origin_time_prune_threshold == 0.20

    def test_initial_state(self):
        """Detector starts with empty state."""
        detector = HierarchicalDetector()
        assert detector.state.last_bar_index == -1
        assert len(detector.state.active_legs) == 0


class TestSingleBarProcessing:
    """Test process_bar() with single bars."""

    def test_first_bar_updates_state(self):
        """First bar updates last_bar_index."""
        detector = HierarchicalDetector()
        bar = make_bar(0, 100.0, 105.0, 95.0, 102.0)

        events = detector.process_bar(bar)

        assert detector.state.last_bar_index == 0

    def test_single_bar_no_leg(self):
        """Single bar cannot form a leg (needs origin confirmation)."""
        detector = HierarchicalDetector()
        bar = make_bar(0, 100.0, 105.0, 95.0, 102.0)

        events = detector.process_bar(bar)

        from src.swing_analysis.events import LegCreatedEvent
        assert len([e for e in events if isinstance(e, LegCreatedEvent)]) == 0
        # First bar can set up pending origins but not form legs
        assert len(detector.state.active_legs) == 0


class TestNoLookahead:
    """Test that algorithm has no lookahead."""

    def test_bar_index_only_accesses_past(self):
        """Verify that process_bar only uses data from current and past bars."""
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        # Process bars sequentially
        bars = [make_bar(i, 100.0 + i, 105.0 + i, 95.0 + i, 102.0 + i) for i in range(20)]

        for i, bar in enumerate(bars):
            detector.process_bar(bar)

            # After processing, last_bar_index should be current
            assert detector.state.last_bar_index == bar.index

            # Verify any active legs only reference bars <= current
            for leg in detector.state.active_legs:
                assert leg.origin_index <= bar.index
                assert leg.pivot_index <= bar.index


class TestStateRestore:
    """Test state serialization and restoration."""

    def test_detector_from_state(self):
        """Detector can be restored from state and continue processing."""
        bars = [make_bar(i, 100.0 + i % 10, 105.0 + i % 10, 95.0 + i % 10, 102.0 + i % 10) for i in range(50)]
        config = DetectionConfig.default()

        # Process first half
        detector1 = HierarchicalDetector(config)
        for bar in bars[:25]:
            detector1.process_bar(bar)

        # Save state
        state = detector1.get_state()
        state_dict = state.to_dict()

        # Restore and continue
        restored_state = DetectorState.from_dict(state_dict)
        detector2 = HierarchicalDetector.from_state(restored_state, config)

        # Process second half
        for bar in bars[25:]:
            detector2.process_bar(bar)

        # Compare to processing all at once
        detector3 = HierarchicalDetector(config)
        for bar in bars:
            detector3.process_bar(bar)

        assert detector2.state.last_bar_index == detector3.state.last_bar_index
