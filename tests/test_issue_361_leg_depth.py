"""
Tests for issue #361: Add depth field to Leg.

Tests cover:
- Root leg has depth 0
- Child of root has depth 1
- Grandchild has depth 2
- Depth persists through state serialization
"""

import pytest
from decimal import Decimal

from src.swing_analysis.dag import LegDetector, DetectorState, Leg
from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.types import Bar


def make_bar(index: int, o: float, h: float, l: float, c: float, ts: int = 0) -> Bar:
    """Create a test bar."""
    return Bar(
        index=index,
        timestamp=ts or (1000000 + index * 60),
        open=o,
        high=h,
        low=l,
        close=c,
    )


class TestLegDepthField:
    """Tests for Leg.depth field."""

    def test_leg_default_depth_is_zero(self):
        """Leg created without explicit depth should default to 0."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=1,
        )
        assert leg.depth == 0

    def test_leg_with_explicit_depth(self):
        """Leg created with explicit depth should preserve it."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=1,
            depth=3,
        )
        assert leg.depth == 3


class TestComputeDepthForLeg:
    """Tests for LegDetector._compute_depth_for_leg() method."""

    def test_root_leg_depth_is_zero(self):
        """Leg with no parent should have depth 0."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        depth = detector._compute_depth_for_leg(None)
        assert depth == 0

    def test_child_of_root_has_depth_one(self):
        """Leg whose parent has depth 0 should have depth 1."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create a root leg (depth 0)
        root_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            depth=0,
        )
        detector.state.active_legs.append(root_leg)

        # Compute depth for child
        depth = detector._compute_depth_for_leg(root_leg.leg_id)
        assert depth == 1

    def test_grandchild_has_depth_two(self):
        """Leg whose parent has depth 1 should have depth 2."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create parent with depth 1
        parent_leg = Leg(
            direction='bull',
            origin_price=Decimal("95"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            depth=1,
        )
        detector.state.active_legs.append(parent_leg)

        # Compute depth for grandchild
        depth = detector._compute_depth_for_leg(parent_leg.leg_id)
        assert depth == 2

    def test_depth_with_missing_parent_returns_zero(self):
        """If parent leg_id not found, depth should be 0."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Try to compute depth for nonexistent parent
        depth = detector._compute_depth_for_leg("nonexistent_leg_id")
        assert depth == 0


class TestDepthIntegration:
    """Integration tests for depth in full detector flow."""

    def test_root_leg_created_with_depth_zero(self):
        """First leg created should have depth 0."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        bars = [
            make_bar(0, 100, 105, 95, 100),
            make_bar(1, 100, 110, 98, 108),  # Type 2-Bull, creates leg
        ]

        for bar in bars:
            detector.process_bar(bar)

        bull_legs = [l for l in detector.state.active_legs if l.direction == 'bull']
        assert len(bull_legs) >= 1

        # First bull leg should be root with depth 0
        root_leg = min(bull_legs, key=lambda l: l.origin_index)
        assert root_leg.depth == 0
        assert root_leg.parent_leg_id is None

    def test_child_leg_has_depth_one(self):
        """Child leg should have depth = parent.depth + 1."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Manually set up parent-child scenario
        parent_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            depth=0,
        )
        detector.state.active_legs.append(parent_leg)

        # Compute depth for a child that would have this parent
        parent_id = detector._find_parent_for_leg('bull', Decimal("95"), 5)
        assert parent_id == parent_leg.leg_id

        depth = detector._compute_depth_for_leg(parent_id)
        assert depth == 1


class TestDepthSerialization:
    """Tests for depth field serialization."""

    def test_depth_included_in_to_dict(self):
        """Depth should be included in serialized state."""
        state = DetectorState()
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=1,
            depth=3,
        )
        state.active_legs.append(leg)

        serialized = state.to_dict()

        # Check depth is in serialized leg data
        assert len(serialized["active_legs"]) == 1
        assert serialized["active_legs"][0]["depth"] == 3

    def test_depth_restored_from_dict(self):
        """Depth should be correctly restored from serialized state."""
        state = DetectorState()
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=1,
            depth=5,
        )
        state.active_legs.append(leg)

        # Round-trip serialization
        serialized = state.to_dict()
        restored = DetectorState.from_dict(serialized)

        assert len(restored.active_legs) == 1
        assert restored.active_legs[0].depth == 5

    def test_depth_defaults_to_zero_if_missing(self):
        """Depth should default to 0 if missing in serialized data."""
        # Create serialized state without depth field (legacy data)
        legacy_data = {
            "active_legs": [
                {
                    "direction": "bull",
                    "origin_price": "100",
                    "origin_index": 0,
                    "pivot_price": "110",
                    "pivot_index": 1,
                    # depth intentionally omitted
                }
            ],
            "active_swings": [],
        }

        restored = DetectorState.from_dict(legacy_data)

        assert len(restored.active_legs) == 1
        assert restored.active_legs[0].depth == 0


class TestDepthHierarchyChain:
    """Tests for depth in multi-level hierarchy."""

    def test_depth_chain_three_levels(self):
        """Test depth correctly increments through 3-level hierarchy."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create L1 (root, depth 0)
        L1 = Leg(
            leg_id="L1",
            direction='bull',
            origin_price=Decimal("80"),
            origin_index=0,
            pivot_price=Decimal("90"),
            pivot_index=1,
            depth=0,
        )
        detector.state.active_legs.append(L1)

        # Create L2 (child of L1, depth 1)
        parent_id_L2 = detector._find_parent_for_leg('bull', Decimal("85"), 2)
        assert parent_id_L2 == "L1"
        depth_L2 = detector._compute_depth_for_leg(parent_id_L2)
        assert depth_L2 == 1

        L2 = Leg(
            leg_id="L2",
            direction='bull',
            origin_price=Decimal("85"),
            origin_index=2,
            pivot_price=Decimal("95"),
            pivot_index=3,
            parent_leg_id=parent_id_L2,
            depth=depth_L2,
        )
        detector.state.active_legs.append(L2)

        # Create L3 (child of L2, depth 2)
        parent_id_L3 = detector._find_parent_for_leg('bull', Decimal("88"), 4)
        assert parent_id_L3 == "L2"
        depth_L3 = detector._compute_depth_for_leg(parent_id_L3)
        assert depth_L3 == 2

        L3 = Leg(
            leg_id="L3",
            direction='bull',
            origin_price=Decimal("88"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            parent_leg_id=parent_id_L3,
            depth=depth_L3,
        )
        detector.state.active_legs.append(L3)

        # Verify chain: L1 (depth 0) -> L2 (depth 1) -> L3 (depth 2)
        assert L1.depth == 0
        assert L2.depth == 1
        assert L3.depth == 2
