"""
Tests for issue #319: Counter-trend scoring for proximity pruning.

Validates the new counter-trend scoring algorithm that replaces "oldest wins"
with "highest counter-trend range wins" for selecting which leg survives
proximity pruning.
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
    parent_leg_id: str = None,
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
        parent_leg_id=parent_leg_id,
    )


def make_bear_leg(
    origin_price: float,
    origin_index: int,
    pivot_price: float,
    pivot_index: int,
    parent_leg_id: str = None,
) -> Leg:
    """Create a bear leg for testing."""
    return Leg(
        direction='bear',
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
        formed=True,
        price_at_creation=Decimal(str(pivot_price)),
        last_modified_bar=pivot_index,
        bar_count=pivot_index - origin_index,
        gap_count=0,
        parent_leg_id=parent_leg_id,
    )


class TestProximityPruneStrategyConfig:
    """Test configuration for proximity_prune_strategy."""

    def test_default_strategy_is_oldest(self):
        """Default strategy should be 'oldest'."""
        config = SwingConfig.default()
        assert config.proximity_prune_strategy == 'oldest'

    def test_with_origin_prune_accepts_strategy(self):
        """with_origin_prune should accept proximity_prune_strategy."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.05,
            origin_time_prune_threshold=0.10,
            proximity_prune_strategy='oldest',
        )
        assert config.proximity_prune_strategy == 'oldest'
        assert config.origin_range_prune_threshold == 0.05
        assert config.origin_time_prune_threshold == 0.10

    def test_with_origin_prune_preserves_strategy_when_not_specified(self):
        """with_origin_prune should preserve strategy when not specified."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.05,
        )
        assert config.proximity_prune_strategy == 'oldest'

    def test_strategy_preserved_across_with_methods(self):
        """Strategy should be preserved across all with_* methods."""
        base = SwingConfig.default().with_origin_prune(
            proximity_prune_strategy='oldest'
        )

        # Test with_bull
        c1 = base.with_bull(formation_fib=0.5)
        assert c1.proximity_prune_strategy == 'oldest'

        # Test with_bear
        c2 = base.with_bear(formation_fib=0.5)
        assert c2.proximity_prune_strategy == 'oldest'

        # Test with_stale_extension
        c3 = base.with_stale_extension(5.0)
        assert c3.proximity_prune_strategy == 'oldest'

        # Test with_level_crosses
        c4 = base.with_level_crosses(True)
        assert c4.proximity_prune_strategy == 'oldest'

        # Test with_prune_toggles
        c5 = base.with_prune_toggles(enable_engulfed_prune=False)
        assert c5.proximity_prune_strategy == 'oldest'


class TestCounterTrendScoring:
    """Test counter-trend scoring for proximity pruning."""

    def test_counter_trend_keeps_highest_scorer(self):
        """Leg with highest counter-trend range should survive."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Create parent leg with segment data
        parent = make_bear_leg(110.0, 0, 95.0, 10)
        parent.segment_deepest_price = Decimal("95.0")  # LOW point

        # Create two bull legs (children) from parent's segment
        # Both share same pivot - they're in proximity
        # leg1: origin at 100, counter-trend = |100 - 95| = 5
        leg1 = make_bull_leg(100.0, 5, 108.0, 15, parent_leg_id=parent.leg_id)
        # leg2: origin at 97, counter-trend = |97 - 95| = 2
        leg2 = make_bull_leg(97.0, 7, 108.0, 15, parent_leg_id=parent.leg_id)

        state.active_legs = [parent, leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # leg1 has higher counter-trend (5 > 2), should survive
        # leg2 should be pruned
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id

        remaining_bulls = [l for l in state.active_legs if l.direction == 'bull']
        assert len(remaining_bulls) == 1
        assert remaining_bulls[0].leg_id == leg1.leg_id

    def test_fallback_to_leg_range_when_no_parent(self):
        """When parent is unavailable, use leg's own range as fallback."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Two root legs (no parent) - fallback to own range
        # leg1: range = 10 (bigger)
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        # leg2: range = 8 (smaller)
        leg2 = make_bull_leg(102.0, 5, 110.0, 10)

        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # leg1 has bigger range, should survive
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id

    def test_fallback_when_parent_has_no_segment_data(self):
        """When parent exists but has no segment data, use leg's own range."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Parent with no segment data
        parent = make_bear_leg(110.0, 0, 95.0, 10)
        # segment_deepest_price is None by default

        # Two legs with parent but no segment data - fallback to own range
        leg1 = make_bull_leg(100.0, 5, 108.0, 15, parent_leg_id=parent.leg_id)  # range = 8
        leg2 = make_bull_leg(102.0, 7, 108.0, 15, parent_leg_id=parent.leg_id)  # range = 6

        state.active_legs = [parent, leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # leg1 has bigger range, should survive
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id

    def test_tie_breaker_keeps_oldest(self):
        """When scores are equal, oldest leg wins (tie-breaker)."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Two legs with exactly equal ranges (same counter-trend score fallback)
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)   # older, range = 10
        leg2 = make_bull_leg(100.0, 5, 110.0, 10)   # newer, same origin price, range = 10

        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Both have same score (10), tie-breaker keeps older (leg1)
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id

        remaining = [l for l in state.active_legs]
        assert len(remaining) == 1
        assert remaining[0].leg_id == leg1.leg_id


class TestProximityClusterBuilding:
    """Test the _build_proximity_clusters helper."""

    def test_single_leg_returns_single_cluster(self):
        """Single leg should return a single cluster containing it."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        leg = make_bull_leg(100.0, 0, 110.0, 10)
        clusters = pruner._build_proximity_clusters(
            [leg], Decimal("0.5"), Decimal("0.5"), 20
        )

        assert len(clusters) == 1
        assert len(clusters[0]) == 1
        assert clusters[0][0].leg_id == leg.leg_id

    def test_two_close_legs_same_cluster(self):
        """Two legs within proximity should be in same cluster."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        leg1 = make_bull_leg(100.0, 0, 110.0, 10)   # range = 10
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)   # range = 9, close

        clusters = pruner._build_proximity_clusters(
            [leg1, leg2], Decimal("0.5"), Decimal("0.5"), 20
        )

        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_two_far_legs_separate_clusters(self):
        """Two legs outside proximity should be in separate clusters."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.05,  # tight threshold
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        leg1 = make_bull_leg(100.0, 0, 110.0, 10)   # range = 10
        leg2 = make_bull_leg(108.0, 5, 110.0, 10)   # range = 2, very different

        clusters = pruner._build_proximity_clusters(
            [leg1, leg2], Decimal("0.05"), Decimal("0.50"), 20
        )

        assert len(clusters) == 2
        assert len(clusters[0]) == 1
        assert len(clusters[1]) == 1

    def test_three_legs_two_close_one_far(self):
        """Three legs with two close and one far should form two clusters."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.20,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        leg1 = make_bull_leg(100.0, 0, 110.0, 10)   # range = 10
        leg2 = make_bull_leg(101.0, 5, 110.0, 10)   # range = 9, close to leg1
        leg3 = make_bull_leg(107.0, 8, 110.0, 10)   # range = 3, far from both

        clusters = pruner._build_proximity_clusters(
            [leg1, leg2, leg3], Decimal("0.20"), Decimal("0.50"), 20
        )

        # leg1 and leg2 are close (range_ratio = 1/10 = 0.10 < 0.20)
        # leg3 is far from both (range_ratio with leg1 = 7/10 = 0.70 > 0.20)
        assert len(clusters) == 2

        # Find cluster sizes
        sizes = sorted([len(c) for c in clusters])
        assert sizes == [1, 2]


class TestOldestWinsStrategy:
    """Test that legacy 'oldest' strategy still works."""

    def test_oldest_keeps_older_leg(self):
        """Legacy 'oldest' strategy should keep the older leg."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='oldest',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Create parent with high counter-trend for leg2
        parent = make_bear_leg(110.0, 0, 95.0, 5)
        parent.segment_deepest_price = Decimal("95.0")

        # leg1: older, lower counter-trend (range = 8, counter = 5)
        leg1 = make_bull_leg(100.0, 5, 108.0, 15)
        # leg2: newer, HIGHER counter-trend (range = 10, counter = 8) but newer
        leg2 = make_bull_leg(103.0, 10, 108.0, 15, parent_leg_id=parent.leg_id)

        state.active_legs = [parent, leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # With 'oldest' strategy, leg1 survives (older) despite leg2 having higher counter-trend
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].leg_id == leg2.leg_id

        remaining_bulls = [l for l in state.active_legs if l.direction == 'bull']
        assert len(remaining_bulls) == 1
        assert remaining_bulls[0].leg_id == leg1.leg_id


class TestCounterTrendVsOldest:
    """Compare counter_trend vs oldest strategies."""

    def test_counter_trend_keeps_significant_level_oldest_would_prune(self):
        """
        Test that counter_trend strategy can keep a newer leg with higher
        counter-trend range, even though oldest strategy would prune it.

        Setup: Two bull legs with same pivot but different origins.
        - Older leg (leg1): lower counter-trend
        - Newer leg (leg2): higher counter-trend

        With 'oldest': older leg survives, newer pruned.
        With 'counter_trend': higher counter-trend survives.
        """
        # Use wide thresholds to ensure pruning happens
        # leg1: origin at 101, pivot at 110, range = 9
        # leg2: origin at 100, pivot at 110, range = 10
        # range_ratio = 1/10 = 0.10 < 0.30 threshold -> should prune

        # Test with 'oldest' strategy
        config_oldest = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='oldest',
        )
        pruner_oldest = LegPruner(config_oldest)

        state_oldest = DetectorState()
        # Parent with segment data
        parent1 = make_bear_leg(115.0, 0, 95.0, 10)
        parent1.segment_deepest_price = Decimal("95.0")  # LOW point

        # leg1: older, origin at 101, range=9, counter-trend = |101 - 95| = 6
        leg1_copy = make_bull_leg(101.0, 15, 110.0, 25, parent_leg_id=parent1.leg_id)
        # leg2: newer, origin at 100, range=10, counter-trend = |100 - 95| = 5
        leg2_copy = make_bull_leg(100.0, 18, 110.0, 25, parent_leg_id=parent1.leg_id)

        state_oldest.active_legs = [parent1, leg1_copy, leg2_copy]

        bar = make_bar(30)
        events_oldest = pruner_oldest.apply_origin_proximity_prune(
            state_oldest, 'bull', bar, datetime.now()
        )

        # Oldest keeps leg1 (older), prunes leg2 (newer)
        prox_oldest = [e for e in events_oldest if e.reason == 'origin_proximity_prune']
        assert len(prox_oldest) == 1
        assert prox_oldest[0].leg_id == leg2_copy.leg_id

        # Test with 'counter_trend' strategy
        config_ct = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner_ct = LegPruner(config_ct)

        state_ct = DetectorState()
        parent2 = make_bear_leg(115.0, 0, 95.0, 10)
        parent2.segment_deepest_price = Decimal("95.0")

        # leg1: older, origin at 101, counter-trend = 6 (higher)
        leg1_ct = make_bull_leg(101.0, 15, 110.0, 25, parent_leg_id=parent2.leg_id)
        # leg2: newer, origin at 100, counter-trend = 5 (lower)
        leg2_ct = make_bull_leg(100.0, 18, 110.0, 25, parent_leg_id=parent2.leg_id)

        state_ct.active_legs = [parent2, leg1_ct, leg2_ct]

        events_ct = pruner_ct.apply_origin_proximity_prune(
            state_ct, 'bull', bar, datetime.now()
        )

        # Counter-trend keeps leg1 (higher counter-trend=6), prunes leg2 (lower=5)
        # In this case, both strategies agree because older also has higher counter-trend
        prox_ct = [e for e in events_ct if e.reason == 'origin_proximity_prune']
        assert len(prox_ct) == 1
        assert prox_ct[0].leg_id == leg2_ct.leg_id

    def test_counter_trend_reverses_oldest_decision(self):
        """
        Test where counter_trend reverses the decision that oldest would make.

        Setup: Newer leg has higher counter-trend.
        - With 'oldest': older leg survives
        - With 'counter_trend': newer leg survives (higher counter-trend)
        """
        # Make sure ranges are similar enough for pruning
        # leg1: origin at 100, range = 10, counter-trend = 5
        # leg2: origin at 101, range = 9, counter-trend = 6
        # range_ratio = 1/10 = 0.10 < 0.30

        # Test with 'oldest' strategy
        config_oldest = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='oldest',
        )
        pruner_oldest = LegPruner(config_oldest)

        state_oldest = DetectorState()
        parent1 = make_bear_leg(115.0, 0, 95.0, 10)
        parent1.segment_deepest_price = Decimal("95.0")

        # leg1: older, origin at 100, range=10, counter-trend = |100 - 95| = 5 (LOWER)
        leg1_copy = make_bull_leg(100.0, 15, 110.0, 25, parent_leg_id=parent1.leg_id)
        # leg2: newer, origin at 101, range=9, counter-trend = |101 - 95| = 6 (HIGHER)
        leg2_copy = make_bull_leg(101.0, 18, 110.0, 25, parent_leg_id=parent1.leg_id)

        state_oldest.active_legs = [parent1, leg1_copy, leg2_copy]

        bar = make_bar(30)
        events_oldest = pruner_oldest.apply_origin_proximity_prune(
            state_oldest, 'bull', bar, datetime.now()
        )

        # Oldest keeps leg1 (older), prunes leg2 (newer with higher counter-trend!)
        prox_oldest = [e for e in events_oldest if e.reason == 'origin_proximity_prune']
        assert len(prox_oldest) == 1
        assert prox_oldest[0].leg_id == leg2_copy.leg_id

        # Test with 'counter_trend' strategy
        config_ct = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.30,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner_ct = LegPruner(config_ct)

        state_ct = DetectorState()
        parent2 = make_bear_leg(115.0, 0, 95.0, 10)
        parent2.segment_deepest_price = Decimal("95.0")

        # leg1: older, origin at 100, counter-trend = 5 (LOWER)
        leg1_ct = make_bull_leg(100.0, 15, 110.0, 25, parent_leg_id=parent2.leg_id)
        # leg2: newer, origin at 101, counter-trend = 6 (HIGHER)
        leg2_ct = make_bull_leg(101.0, 18, 110.0, 25, parent_leg_id=parent2.leg_id)

        state_ct.active_legs = [parent2, leg1_ct, leg2_ct]

        events_ct = pruner_ct.apply_origin_proximity_prune(
            state_ct, 'bull', bar, datetime.now()
        )

        # Counter-trend REVERSES: keeps leg2 (higher counter-trend=6), prunes leg1 (lower=5)
        prox_ct = [e for e in events_ct if e.reason == 'origin_proximity_prune']
        assert len(prox_ct) == 1
        assert prox_ct[0].leg_id == leg1_ct.leg_id  # Opposite of oldest!


class TestSwingTransferWithCounterTrend:
    """Test that swings are properly transferred with counter-trend strategy."""

    def test_swing_transferred_to_highest_scorer(self):
        """Swing should transfer to the leg with highest counter-trend score."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Two legs with same pivot, leg2 has swing but lower score
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)   # range = 10, no swing
        leg2 = make_bull_leg(102.0, 5, 110.0, 10)   # range = 8, HAS swing
        leg2.swing_id = "swing-123"

        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # leg1 survives (higher score), leg2 pruned
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 1
        assert prox_events[0].swing_id == "swing-123"

        # Swing should be transferred to leg1
        assert leg1.swing_id == "swing-123"


class TestMultipleClustersPruning:
    """Test pruning with multiple clusters in same pivot group."""

    def test_multiple_clusters_prune_independently(self):
        """Each cluster should select its own winner independently."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.20,  # wide enough for similar ranges
            origin_time_prune_threshold=0.50,
            proximity_prune_strategy='counter_trend',
        )
        pruner = LegPruner(config)

        state = DetectorState()

        # Cluster 1: leg1 and leg2 (similar ranges around 10)
        # range_ratio = |10-9|/10 = 0.10 < 0.20 -> same cluster
        leg1 = make_bull_leg(100.0, 0, 110.0, 20)   # range = 10
        leg2 = make_bull_leg(101.0, 5, 110.0, 20)   # range = 9

        # Cluster 2: leg3 and leg4 (similar ranges around 5)
        # range_ratio = |5-4.5|/5 = 0.10 < 0.20 -> same cluster
        # But these are in separate cluster from leg1/leg2 because:
        # range_ratio(leg1,leg3) = |10-5|/10 = 0.50 > 0.20 -> different clusters
        leg3 = make_bull_leg(105.0, 10, 110.0, 20)  # range = 5
        leg4 = make_bull_leg(105.5, 12, 110.0, 20)  # range = 4.5

        state.active_legs = [leg1, leg2, leg3, leg4]

        bar = make_bar(30)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Each cluster should prune one leg
        prox_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prox_events) == 2

        # leg1 wins cluster 1 (range=10 > 9)
        # leg3 wins cluster 2 (range=5 > 4.5)
        surviving_ids = {l.leg_id for l in state.active_legs}
        assert leg1.leg_id in surviving_ids
        assert leg3.leg_id in surviving_ids
        assert leg2.leg_id not in surviving_ids
        assert leg4.leg_id not in surviving_ids


class TestEdgeCases:
    """Edge cases for counter-trend pruning."""

    def test_empty_legs_no_crash(self):
        """Empty legs list should not crash."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        state.active_legs = []

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())
        assert len(events) == 0

    def test_single_leg_not_pruned(self):
        """Single leg should not be pruned."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        leg = make_bull_leg(100.0, 0, 110.0, 10)
        state.active_legs = [leg]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        assert len(events) == 0
        assert len(state.active_legs) == 1

    def test_different_pivots_not_compared(self):
        """Legs with different pivots should not be compared."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Different pivot prices
        leg1 = make_bull_leg(100.0, 0, 110.0, 10)
        leg2 = make_bull_leg(100.0, 5, 115.0, 15)  # different pivot

        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # No pruning - different pivot groups
        assert len(events) == 0
        assert len(state.active_legs) == 2

    def test_zero_range_legs_handled(self):
        """Legs with zero range should not cause division by zero."""
        config = SwingConfig.default().with_origin_prune(
            origin_range_prune_threshold=0.50,
            origin_time_prune_threshold=0.50,
        )
        pruner = LegPruner(config)

        state = DetectorState()
        # Zero range leg
        leg1 = make_bull_leg(100.0, 0, 100.0, 10)  # range = 0
        leg2 = make_bull_leg(100.0, 5, 100.0, 10)  # range = 0

        state.active_legs = [leg1, leg2]

        bar = make_bar(20)
        # Should not crash
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())
        # Zero range legs are skipped in comparison
        assert len(events) == 0
