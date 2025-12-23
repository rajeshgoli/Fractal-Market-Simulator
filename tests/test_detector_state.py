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
from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.swing_node import SwingNode

from conftest import make_bar


class TestDetectorStateSerialization:
    """Test DetectorState serialization and deserialization."""

    def test_empty_state_roundtrip(self):
        """Empty state serializes and deserializes correctly."""
        state = DetectorState()
        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert restored.last_bar_index == -1
        assert len(restored.active_swings) == 0

    def test_state_with_swings_roundtrip(self):
        """State with active swings serializes and preserves hierarchy."""
        parent = SwingNode(
            swing_id="parent01",
            high_bar_index=0,
            high_price=Decimal("110"),
            low_bar_index=10,
            low_price=Decimal("100"),
            direction="bull",
            status="active",
            formed_at_bar=10,
        )
        child = SwingNode(
            swing_id="child001",
            high_bar_index=20,
            high_price=Decimal("108"),
            low_bar_index=30,
            low_price=Decimal("102"),
            direction="bull",
            status="active",
            formed_at_bar=30,
        )
        child.add_parent(parent)

        state = DetectorState(
            active_swings=[parent, child],
            all_swing_ranges=[parent.range, child.range],
        )
        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert len(restored.active_swings) == 2

        # Find child in restored state
        restored_child = next(
            s for s in restored.active_swings if s.swing_id == "child001"
        )
        assert len(restored_child.parents) == 1
        assert restored_child.parents[0].swing_id == "parent01"


class TestHierarchicalDetectorInitialization:
    """Test detector initialization."""

    def test_default_config(self):
        """Detector initializes with default config."""
        detector = HierarchicalDetector()
        assert detector.config is not None
        assert detector.config.origin_range_prune_threshold == 0.0
        assert detector.config.origin_time_prune_threshold == 0.0

    def test_custom_config(self):
        """Detector accepts custom config (#294)."""
        config = SwingConfig.default().with_origin_prune(
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
        assert len(detector.get_active_swings()) == 0


class TestSingleBarProcessing:
    """Test process_bar() with single bars."""

    def test_first_bar_updates_state(self):
        """First bar updates last_bar_index."""
        detector = HierarchicalDetector()
        bar = make_bar(0, 100.0, 105.0, 95.0, 102.0)

        events = detector.process_bar(bar)

        assert detector.state.last_bar_index == 0

    def test_single_bar_no_swing(self):
        """Single bar cannot form a swing (needs origin before pivot)."""
        detector = HierarchicalDetector()
        bar = make_bar(0, 100.0, 105.0, 95.0, 102.0)

        events = detector.process_bar(bar)

        from src.swing_analysis.events import SwingFormedEvent
        assert len([e for e in events if isinstance(e, SwingFormedEvent)]) == 0
        assert len(detector.get_active_swings()) == 0


class TestNoLookahead:
    """Test that algorithm has no lookahead."""

    def test_bar_index_only_accesses_past(self):
        """Verify that process_bar only uses data from current and past bars."""
        config = SwingConfig.default()
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
        config = SwingConfig.default()

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
