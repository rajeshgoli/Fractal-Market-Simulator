"""
Tests for issue #294: Origin-proximity pruning.

Validates the new origin-proximity pruning algorithm that replaces pivot-based
proximity pruning with origin-based (time, range) space comparison.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.state import DetectorState
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.types import Bar


def make_bar(index: int, high: float = 100.0, low: float = 90.0) -> Bar:
    """Create a test bar."""
    return Bar(
        index=index,
        timestamp=datetime(2024, 1, 1, index // 60, index % 60),
        open=Decimal(str((high + low) / 2)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str((high + low) / 2)),
    )


def make_bull_leg(
    origin_price: float,
    origin_index: int,
    pivot_price: float,
    pivot_index: int,
) -> Leg:
    """Create a bull leg for testing."""
    return Leg(
        direction='bull',
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
        formed=True,
        price_at_creation=Decimal(str(pivot_price)),
        last_modified_bar=pivot_index,
        bar_count=pivot_index - origin_index,
        gap_count=0,
    )


class TestOriginProximityPruningConfig:
    """Test configuration for origin-proximity pruning."""

    def test_default_thresholds_disabled(self):
        """Default thresholds should be 0 (disabled)."""
        config = SwingConfig.default()
        assert config.origin_range_prune_threshold == 0.0
        assert config.origin_time_prune_threshold == 0.0

    def test_with_origin_prune_updates_both(self):
        """with_origin_prune should update both thresholds."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.05,
            origin_time_prune_threshold=0.10,
        )
        assert config.origin_range_prune_threshold == 0.05
        assert config.origin_time_prune_threshold == 0.10

    def test_with_origin_prune_partial_update(self):
        """with_origin_prune should update only provided threshold."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.05,
        )
        assert config.origin_range_prune_threshold == 0.05
        assert config.origin_time_prune_threshold == 0.0  # unchanged

        config = config.with_origin_prune(
            origin_time_prune_threshold=0.10,
        )
        assert config.origin_range_prune_threshold == 0.05  # preserved
        assert config.origin_time_prune_threshold == 0.10


class TestOriginProximityPruningDisabled:
    """Test that pruning is disabled when thresholds are 0."""

    def test_no_pruning_when_both_thresholds_zero(self):
        """No pruning should occur when both thresholds are 0."""
        config = SwingConfig.default()  # Both thresholds are 0
        pruner = LegPruner(config)

        state = DetectorState()
        # Create two similar legs
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)
        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Only turn pruning should occur, not proximity pruning
        # (legs have different origins, so turn pruning won't consolidate them)
        assert len(state.active_legs) == 2

    def test_no_pruning_when_range_threshold_zero(self):
        """No proximity pruning when range threshold is 0."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.0,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)
        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # No proximity pruning should occur
        assert len(state.active_legs) == 2

    def test_no_pruning_when_time_threshold_zero(self):
        """No proximity pruning when time threshold is 0."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.0,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)
        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # No proximity pruning should occur
        assert len(state.active_legs) == 2


class TestOriginProximityPruningLogic:
    """Test the origin-proximity pruning algorithm logic."""

    def test_prunes_newer_leg_when_both_conditions_met(self):
        """Prune newer leg when both time and range ratios are below thresholds."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.20,  # 20% range difference
            origin_time_prune_threshold=0.50,   # 50% time difference
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Older leg: origin at bar 0, range = 10
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        # Newer leg: origin at bar 5, range = 9 (10% smaller)
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)
        state.active_legs = [leg1, leg2]

        # Current bar = 20
        # bars_since_older = 20 - 0 = 20
        # bars_since_newer = 20 - 5 = 15
        # time_ratio = (20 - 15) / 20 = 0.25 < 0.50 ✓
        # range_ratio = |10 - 9| / 10 = 0.10 < 0.20 ✓
        # Both conditions met -> prune newer leg

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Check that proximity prune event was emitted
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id

    def test_no_prune_when_time_ratio_exceeds_threshold(self):
        """Keep both legs when time ratio exceeds threshold."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.20,
            origin_time_prune_threshold=0.10,  # Very tight threshold
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Older leg: origin at bar 0, range = 10
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        # Newer leg: origin at bar 10 (far apart in time)
        leg2 = make_bull_leg(101.0, 10, 110.0, 15)
        state.active_legs = [leg1, leg2]

        # Current bar = 20
        # time_ratio = (20 - 10) / 20 = 0.50 > 0.10 threshold
        # Range similar but time threshold not met -> keep both

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 0
        assert len(state.active_legs) == 2

    def test_no_prune_when_range_ratio_exceeds_threshold(self):
        """Keep both legs when range ratio exceeds threshold."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.05,  # Very tight threshold
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Older leg: origin at bar 0, range = 10
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        # Newer leg: range = 8 (20% smaller, exceeds 5% threshold)
        leg2 = make_bull_leg(102.0, 5, 110.0, 10)
        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 0
        assert len(state.active_legs) == 2


class TestOriginProximityPivotGrouping:
    """Test that proximity pruning only compares legs within the same pivot group (#298)."""

    def test_no_comparison_across_different_pivots(self):
        """Legs with different pivots should NOT be compared (#298).

        Scenario from issue: newer leg has larger range but different pivot.
        This is valid market structure (found better pivot), not a bug.
        """
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Older leg at bar 0: origin=1218.75, pivot at bar 18, range=1.50
        leg1 = make_bull_leg(1218.75, 0, 1220.25, 18)  # range = 1.50
        # Newer leg at bar 39: origin=1218.5, pivot at bar 60, range=1.75
        # This leg found a better origin AND later pivot → larger range. This is VALID.
        leg2 = make_bull_leg(1218.5, 39, 1220.25, 60)  # range = 1.75

        state.active_legs = [leg1, leg2]

        bar = make_bar(100)
        # Should NOT raise ValueError - different pivots are independent
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # No pruning should occur - legs have different pivots
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 0
        assert len(state.active_legs) == 2

    def test_prunes_within_same_pivot_group(self):
        """Legs sharing the same pivot should be compared and pruned if close."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,  # 30% range difference
            origin_time_prune_threshold=0.50,   # 50% time difference
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Both legs share the same pivot (110.0, bar 20)
        leg1 = make_bull_leg(100.0, 0, 110.0, 20)   # range = 10
        leg2 = make_bull_leg(101.0, 5, 110.0, 20)   # range = 9 (same pivot!)

        state.active_legs = [leg1, leg2]

        # Current bar = 30
        # bars_since_older = 30 - 0 = 30
        # bars_since_newer = 30 - 5 = 25
        # time_ratio = (30 - 25) / 30 ≈ 0.167 < 0.50 ✓
        # range_ratio = |10 - 9| / 10 = 0.10 < 0.30 ✓
        # Both conditions met, SAME pivot -> prune newer leg

        bar = make_bar(30)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id
        assert len(state.active_legs) == 1

    def test_multiple_pivot_groups_prune_independently(self):
        """Each pivot group should be pruned independently."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Pivot group 1: (110.0, 20)
        leg1a = make_bull_leg(100.0, 0, 110.0, 20)   # range = 10
        leg1b = make_bull_leg(101.0, 5, 110.0, 20)   # range = 9, should be pruned

        # Pivot group 2: (115.0, 25)
        leg2a = make_bull_leg(105.0, 10, 115.0, 25)  # range = 10
        leg2b = make_bull_leg(106.0, 12, 115.0, 25)  # range = 9, should be pruned

        state.active_legs = [leg1a, leg1b, leg2a, leg2b]

        bar = make_bar(30)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        # One from each pivot group should be pruned
        assert len(prox_events) == 2
        pruned_ids = {e.leg_id for e in prox_events}
        assert leg1b.leg_id in pruned_ids
        assert leg2b.leg_id in pruned_ids
        assert len(state.active_legs) == 2

    def test_different_pivot_index_same_price_are_separate_groups(self):
        """Legs with same pivot price but different pivot index are in separate groups."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Same pivot price (110.0) but different pivot index
        leg1 = make_bull_leg(100.0, 0, 110.0, 20)   # pivot at bar 20
        leg2 = make_bull_leg(101.0, 5, 110.0, 25)   # pivot at bar 25 (different!)

        state.active_legs = [leg1, leg2]

        bar = make_bar(30)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # No pruning - different pivot groups
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 0
        assert len(state.active_legs) == 2


class TestOriginProximitySwingTransfer:
    """Test that swings are transferred when legs with active swings are pruned."""

    def test_swing_transferred_to_older_leg(self):
        """When a leg with a swing is pruned, its swing should transfer to the older leg."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)
        leg2.swing_id = "swing-123"  # Has an active swing

        # Add mock swing to active_swings
        from src.swing_analysis.swing_node import SwingNode
        swing = SwingNode(
            swing_id="swing-123",
            direction='bull',
            high_bar_index=10,
            high_price=Decimal('110.0'),
            low_bar_index=5,
            low_price=Decimal('101.0'),
            status='active',
            formed_at_bar=10,
        )
        state.active_swings.append(swing)
        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # leg2 should be pruned (no immunity) and swing transferred to leg1
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].swing_id == "swing-123"
        assert len(state.active_legs) == 1
        # Swing should have been transferred to the surviving older leg
        assert leg1.swing_id == "swing-123"


class TestOriginProximityMultipleLegs:
    """Test origin-proximity pruning with multiple legs."""

    def test_prunes_multiple_newer_legs(self):
        """Should prune multiple newer legs within same pivot group when conditions are met."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # All legs share the SAME pivot (115.0, bar 10)
        # Oldest leg: largest range (range = 15)
        leg1 = make_bull_leg(100.0, 0, 115.0, 10)  # range = 15
        # Middle leg: similar range, similar time (range = 14)
        leg2 = make_bull_leg(101.0, 2, 115.0, 10)  # range = 14
        # Newest leg: similar range, similar time (range = 13)
        leg3 = make_bull_leg(102.0, 4, 115.0, 10)  # range = 13

        state.active_legs = [leg1, leg2, leg3]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        # Both leg2 and leg3 should be pruned (newer than leg1, same pivot, similar range/time)
        assert len(prox_events) == 2
        assert len(state.active_legs) == 1
        assert state.active_legs[0].leg_id == leg1.leg_id

    def test_keeps_legs_with_different_time_separation(self):
        """Should keep legs that are far apart in time."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.10,  # Tight time threshold
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Legs with similar ranges but far apart in time
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)   # range = 10
        leg2 = make_bull_leg(100.5, 50, 110.0, 60)  # range = 9.5, far in time
        leg3 = make_bull_leg(101.0, 90, 110.0, 95)  # range = 9, even further

        state.active_legs = [leg1, leg2, leg3]

        bar = make_bar(100)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # time_ratio for leg2 vs leg1: (100 - 50) / 100 = 0.50 > 0.10 (keep)
        # time_ratio for leg3 vs leg1: (100 - 10) / 100 = 0.90 > 0.10 (keep)
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 0
        assert len(state.active_legs) == 3
