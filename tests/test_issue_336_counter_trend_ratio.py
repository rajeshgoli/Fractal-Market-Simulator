"""
Tests for issue #336: Counter-trend ratio calculation fix.

The counter_trend_ratio should measure how much counter-trend pressure accumulated
at a leg's origin, calculated as:

    counter_trend_ratio = longest_opposite_leg_range / this_leg_range

Where longest_opposite_leg is the longest opposite-direction leg whose pivot
equals this leg's origin.
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


def make_bear_leg(
    origin_price: float,
    origin_index: int,
    pivot_price: float,
    pivot_index: int,
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
    )


class TestCounterTrendRatioCalculation:
    """Test the counter_trend_ratio calculation."""

    def test_basic_calculation(self):
        """
        Test basic CTR calculation.

        At pivot 100, bull legs exist: 50→100 (range=50), 60→100 (range=40)
        New bear leg: 100→20 (range=80)

        CTR = longest_opposite_range / this_leg_range = 50 / 80 = 0.625
        """
        config = SwingConfig.default().with_min_counter_trend(0.01)  # Low threshold to not prune
        pruner = LegPruner(config)

        state = DetectorState()

        # Bull legs with pivot at 100
        bull1 = make_bull_leg(50.0, 0, 100.0, 10)   # range = 50 (longest)
        bull2 = make_bull_leg(60.0, 5, 100.0, 15)   # range = 40
        bull3 = make_bull_leg(70.0, 8, 100.0, 18)   # range = 30

        # Bear leg with origin at 100
        bear = make_bear_leg(100.0, 20, 20.0, 30)   # range = 80

        state.active_legs = [bull1, bull2, bull3, bear]

        bar = make_bar(35)
        # Run pruning to calculate CTR (with min_ratio=0, nothing gets pruned)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # CTR should be calculated on the bear leg
        # longest_opposite = bull1 (range=50), bear.range = 80
        # ratio = 50 / 80 = 0.625
        assert bear.counter_trend_ratio == pytest.approx(0.625, rel=0.01)

    def test_prunes_low_ctr_legs(self):
        """
        Test that legs with CTR below threshold are pruned.

        Bull leg with pivot at 100 (range=10)
        Bear leg with origin at 100 (range=100)

        CTR = 10 / 100 = 0.10
        With min_counter_trend_ratio=0.15, bear leg should be pruned.
        """
        config = SwingConfig.default().with_min_counter_trend(0.15)  # 15% threshold
        pruner = LegPruner(config)

        state = DetectorState()

        # Small bull leg
        bull = make_bull_leg(90.0, 0, 100.0, 10)   # range = 10

        # Large bear leg with origin at 100
        bear = make_bear_leg(100.0, 15, 0.0, 25)   # range = 100

        state.active_legs = [bull, bear]

        bar = make_bar(30)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # CTR = 10 / 100 = 0.10 < 0.15 threshold → pruned
        assert len(events) == 1
        assert events[0].leg_id == bear.leg_id
        assert events[0].reason == "min_counter_trend"

        # Bear leg should be removed
        remaining = [l for l in state.active_legs if l.direction == 'bear']
        assert len(remaining) == 0

    def test_keeps_high_ctr_legs(self):
        """
        Test that legs with CTR above threshold are kept.

        Bull leg with pivot at 100 (range=50)
        Bear leg with origin at 100 (range=80)

        CTR = 50 / 80 = 0.625 > 0.15 threshold → kept
        """
        config = SwingConfig.default().with_min_counter_trend(0.15)
        pruner = LegPruner(config)

        state = DetectorState()

        # Bull leg with decent range
        bull = make_bull_leg(50.0, 0, 100.0, 10)   # range = 50

        # Bear leg with origin at 100
        bear = make_bear_leg(100.0, 15, 20.0, 25)  # range = 80

        state.active_legs = [bull, bear]

        bar = make_bar(30)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # CTR = 50 / 80 = 0.625 > 0.15 → not pruned
        assert len(events) == 0
        assert bear.counter_trend_ratio == pytest.approx(0.625, rel=0.01)

    def test_no_opposite_legs_defaults_to_pass(self):
        """
        Test that legs with no opposite-direction legs at origin pass by default.

        Bear leg with origin at 100, but no bull legs have pivot at 100.
        CTR defaults to 1.0 (always pass).
        """
        config = SwingConfig.default().with_min_counter_trend(0.15)
        pruner = LegPruner(config)

        state = DetectorState()

        # Bull leg with different pivot
        bull = make_bull_leg(50.0, 0, 90.0, 10)   # pivot at 90, not 100

        # Bear leg with origin at 100 - no matching bull legs
        bear = make_bear_leg(100.0, 15, 20.0, 25)

        state.active_legs = [bull, bear]

        bar = make_bar(30)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # No opposite legs at origin → CTR = 1.0 → passes
        assert len(events) == 0
        assert bear.counter_trend_ratio == 1.0

    def test_uses_longest_opposite_leg(self):
        """
        Test that the longest opposite-direction leg is used.

        Multiple bull legs at pivot 100 with different ranges.
        Bear leg should use the longest one for CTR calculation.
        """
        config = SwingConfig.default().with_min_counter_trend(0.01)  # Low threshold to not prune
        pruner = LegPruner(config)

        state = DetectorState()

        # Multiple bull legs with pivot at 100
        bull1 = make_bull_leg(80.0, 0, 100.0, 10)   # range = 20
        bull2 = make_bull_leg(40.0, 3, 100.0, 12)   # range = 60 (longest!)
        bull3 = make_bull_leg(70.0, 5, 100.0, 14)   # range = 30

        # Bear leg with origin at 100
        bear = make_bear_leg(100.0, 20, 50.0, 30)   # range = 50

        state.active_legs = [bull1, bull2, bull3, bear]

        bar = make_bar(35)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # longest_opposite = bull2 (range=60), bear.range = 50
        # ratio = 60 / 50 = 1.2
        assert bear.counter_trend_ratio == pytest.approx(1.2, rel=0.01)

    def test_only_considers_active_opposite_legs(self):
        """
        Test that only active opposite-direction legs are considered.

        Inactive (stale, invalidated, pruned) legs should be ignored.
        """
        config = SwingConfig.default().with_min_counter_trend(0.01)  # Low threshold to not prune
        pruner = LegPruner(config)

        state = DetectorState()

        # Active bull leg with pivot at 100
        active_bull = make_bull_leg(90.0, 0, 100.0, 10)   # range = 10

        # Inactive bull leg with larger range at same pivot
        inactive_bull = make_bull_leg(40.0, 2, 100.0, 12)   # range = 60
        inactive_bull.status = 'stale'

        # Bear leg with origin at 100
        bear = make_bear_leg(100.0, 20, 50.0, 30)   # range = 50

        state.active_legs = [active_bull, inactive_bull, bear]

        bar = make_bar(35)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # Only active_bull should be considered (range=10)
        # ratio = 10 / 50 = 0.2
        assert bear.counter_trend_ratio == pytest.approx(0.2, rel=0.01)

    def test_bull_and_bear_legs_separate(self):
        """
        Test that bull and bear legs are processed separately.

        Bull legs should find bear opposite legs, and vice versa.
        """
        config = SwingConfig.default().with_min_counter_trend(0.01)  # Low threshold to not prune
        pruner = LegPruner(config)

        state = DetectorState()

        # Bear leg with pivot at 50
        bear = make_bear_leg(100.0, 0, 50.0, 10)   # range = 50

        # Bull leg with origin at 50 (should find bear with pivot at 50)
        bull = make_bull_leg(50.0, 15, 80.0, 25)   # range = 30

        state.active_legs = [bear, bull]

        bar = make_bar(30)
        events = pruner.apply_min_counter_trend_prune(state, 'bull', bar, datetime.now())

        # bull looks for bear legs with pivot == 50 → finds bear (range=50)
        # ratio = 50 / 30 = 1.67
        assert bull.counter_trend_ratio == pytest.approx(1.67, rel=0.01)


class TestCounterTrendRatioSerialization:
    """Test that counter_trend_ratio is properly serialized/deserialized."""

    def test_serialization_round_trip(self):
        """Test that counter_trend_ratio survives serialization."""
        state = DetectorState()

        leg = make_bull_leg(100.0, 0, 110.0, 10)
        leg.counter_trend_ratio = 0.75
        state.active_legs = [leg]

        # Serialize
        data = state.to_dict()

        # Check it's in the serialized data
        assert data['active_legs'][0]['counter_trend_ratio'] == 0.75

        # Deserialize
        restored = DetectorState.from_dict(data)
        assert restored.active_legs[0].counter_trend_ratio == 0.75

    def test_none_value_survives_serialization(self):
        """Test that None counter_trend_ratio survives serialization."""
        state = DetectorState()

        leg = make_bull_leg(100.0, 0, 110.0, 10)
        # counter_trend_ratio is None by default
        state.active_legs = [leg]

        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert restored.active_legs[0].counter_trend_ratio is None


class TestDisabledMinCtrFilter:
    """Test that min_counter_trend_ratio=0 disables the filter."""

    def test_zero_threshold_skips_pruning(self):
        """Setting min_counter_trend_ratio=0 should skip all pruning."""
        # Default config has min_counter_trend_ratio=0, which means disabled
        config = SwingConfig.default()
        pruner = LegPruner(config)

        state = DetectorState()

        # Very small bull leg
        bull = make_bull_leg(99.0, 0, 100.0, 10)   # range = 1

        # Large bear leg - would normally be pruned with low CTR
        bear = make_bear_leg(100.0, 15, 0.0, 25)   # range = 100

        state.active_legs = [bull, bear]

        bar = make_bar(30)
        events = pruner.apply_min_counter_trend_prune(state, 'bear', bar, datetime.now())

        # Filter is disabled, no pruning
        assert len(events) == 0
        # CTR is not calculated when filter is disabled
        assert bear.counter_trend_ratio is None
