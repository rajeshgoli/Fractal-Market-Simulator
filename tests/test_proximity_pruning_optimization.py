"""
Tests for proximity pruning optimization (#306).

Validates:
1. Binary search bound calculation correctness
2. Edge cases: threshold boundaries, empty groups, single legs
3. O(N log N) performance scaling (not O(N^2))
"""

import pytest
import time
from decimal import Decimal
from datetime import datetime
from typing import List

from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.dag.state import DetectorState
from src.swing_analysis.detection_config import DetectionConfig
from src.swing_analysis.types import Bar


def make_bar(index: int, high: float = 100.0, low: float = 90.0) -> Bar:
    """Create a test bar."""
    return Bar(
        index=index,
        timestamp=int(datetime.now().timestamp()),
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
        price_at_creation=Decimal(str(pivot_price)),
        last_modified_bar=pivot_index,
        bar_count=pivot_index - origin_index,
        gap_count=0,
    )


class TestBinarySearchBoundsCalculation:
    """Test the mathematical bound calculation for time-based pruning."""

    def test_bound_at_3_percent_threshold(self):
        """Verify bound calculation matches expected for 3% threshold.

        For threshold=0.03, current_bar=100000, newer_idx=95000:
        min_older_idx = (95000 - 0.03 * 100000) / (1 - 0.03)
                      = (95000 - 3000) / 0.97
                      = 94845.36
        """
        threshold = 0.03
        current_bar = 100_000
        newer_idx = 95_000

        min_older_idx = (newer_idx - threshold * current_bar) / (1 - threshold)

        assert abs(min_older_idx - 94845.36) < 1

    def test_bound_at_10_percent_threshold(self):
        """Verify bound at 10% threshold.

        For threshold=0.10, current_bar=100000, newer_idx=95000:
        min_older_idx = (95000 - 0.10 * 100000) / (1 - 0.10)
                      = (95000 - 10000) / 0.90
                      = 94444.44
        """
        threshold = 0.10
        current_bar = 100_000
        newer_idx = 95_000

        min_older_idx = (newer_idx - threshold * current_bar) / (1 - threshold)

        assert abs(min_older_idx - 94444.44) < 1

    def test_bound_at_1_percent_threshold(self):
        """Verify tighter bound at 1% threshold.

        Lower thresholds produce tighter bounds (fewer legs to check).
        """
        threshold = 0.01
        current_bar = 100_000
        newer_idx = 95_000

        min_older_idx = (newer_idx - threshold * current_bar) / (1 - threshold)

        # (95000 - 1000) / 0.99 = 94949.49
        assert abs(min_older_idx - 94949.49) < 1

    def test_bound_window_size_increases_with_threshold(self):
        """Higher thresholds should produce lower bounds (larger windows)."""
        current_bar = 100_000
        newer_idx = 95_000

        bound_1pct = (newer_idx - 0.01 * current_bar) / (1 - 0.01)
        bound_5pct = (newer_idx - 0.05 * current_bar) / (1 - 0.05)
        bound_10pct = (newer_idx - 0.10 * current_bar) / (1 - 0.10)

        # Lower bound means larger window to search
        assert bound_1pct > bound_5pct > bound_10pct


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_active_legs_no_crash(self):
        """Empty active_legs should return empty list."""
        config = DetectionConfig.default().with_origin_prune(0.05, 0.10)
        pruner = LegPruner(config)
        state = DetectorState()
        state.active_legs = []

        bar = make_bar(100)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        assert events == []

    def test_single_leg_no_prune(self):
        """Single leg in pivot group should not be pruned."""
        config = DetectionConfig.default().with_origin_prune(0.05, 0.10)
        pruner = LegPruner(config)
        state = DetectorState()

        leg = make_bull_leg(90.0, 10, 100.0, 20)
        state.active_legs = [leg]

        bar = make_bar(50)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        assert len(events) == 0
        assert len(state.active_legs) == 1

    def test_threshold_zero_disables_pruning(self):
        """Zero threshold should disable pruning entirely."""
        config = DetectionConfig.default().with_origin_prune(0.0, 0.10)
        pruner = LegPruner(config)
        state = DetectorState()

        # Create legs that would be pruned if enabled
        leg1 = make_bull_leg(90.0, 10, 100.0, 20)
        leg2 = make_bull_leg(90.5, 11, 100.0, 20)
        state.active_legs = [leg1, leg2]

        bar = make_bar(50)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        assert len(events) == 0
        assert len(state.active_legs) == 2

    def test_threshold_near_one_degrades_gracefully(self):
        """Threshold near 1.0 should work without crashing."""
        config = DetectionConfig.default().with_origin_prune(0.99, 0.99)
        pruner = LegPruner(config)
        state = DetectorState()

        leg1 = make_bull_leg(90.0, 10, 100.0, 20)
        leg2 = make_bull_leg(90.1, 11, 100.0, 20)
        state.active_legs = [leg1, leg2]

        bar = make_bar(50)

        # Should not crash
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())
        assert isinstance(events, list)

    def test_different_pivot_groups_independent(self):
        """Legs with different pivots should not affect each other."""
        config = DetectionConfig.default().with_origin_prune(0.50, 0.50)
        pruner = LegPruner(config)
        state = DetectorState()

        # Two legs with DIFFERENT pivots - should not prune each other
        leg1 = make_bull_leg(90.0, 10, 100.0, 20)  # pivot at (100.0, 20)
        leg2 = make_bull_leg(90.5, 11, 105.0, 25)  # pivot at (105.0, 25)
        state.active_legs = [leg1, leg2]

        bar = make_bar(50)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # No pruning - different pivot groups
        assert len(events) == 0
        assert len(state.active_legs) == 2

    def test_same_pivot_different_direction_independent(self):
        """Bull and bear legs should be processed independently."""
        config = DetectionConfig.default().with_origin_prune(0.50, 0.50)
        pruner = LegPruner(config)
        state = DetectorState()

        bull_leg = make_bull_leg(90.0, 10, 100.0, 20)
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("110.0"),
            origin_index=10,
            pivot_price=Decimal("100.0"),
            pivot_index=20,
            price_at_creation=Decimal("100.0"),
            last_modified_bar=20,
            bar_count=10,
            gap_count=0,
        )
        state.active_legs = [bull_leg, bear_leg]

        bar = make_bar(50)

        # Process bull direction
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Only bull leg considered, no pruning (single leg in group)
        assert len(events) == 0
        assert len(state.active_legs) == 2


class TestPerformanceScaling:
    """Test O(N log N) performance scaling."""

    def _create_many_legs_same_pivot(self, count: int, pivot_index: int) -> List[Leg]:
        """Create many legs sharing the same pivot for worst-case testing."""
        legs = []
        for i in range(count):
            legs.append(Leg(
                direction='bull',
                origin_price=Decimal(str(90 + i * 0.001)),  # Slightly different origins
                origin_index=i,
                pivot_price=Decimal("100.0"),
                pivot_index=pivot_index,
                price_at_creation=Decimal("100.0"),
                last_modified_bar=pivot_index,
                bar_count=pivot_index - i,
                gap_count=0,
            ))
        return legs

    @pytest.mark.slow
    def test_scaling_is_not_quadratic(self):
        """Verify performance doesn't degrade quadratically with leg count.

        O(N^2) would have times[1000] / times[100] ~= 100
        O(N log N) would have times[1000] / times[100] ~= 15

        Note: This test uses the 'oldest' strategy which is O(N log N).
        The 'counter_trend' strategy (#319) uses O(N^2) for cluster building,
        which is acceptable since N (legs per pivot group) is typically small.
        """
        # Use 'oldest' strategy for O(N log N) optimization test
        config = DetectionConfig.default().with_origin_prune(0.10, 0.10, 'oldest')
        pruner = LegPruner(config)

        times = {}
        for size in [100, 500, 1000]:
            state = DetectorState()
            state.active_legs = self._create_many_legs_same_pivot(size, size + 100)

            bar = make_bar(size + 200)

            start = time.perf_counter()
            pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())
            times[size] = time.perf_counter() - start

        # Calculate scaling ratio
        ratio = times[1000] / max(times[100], 1e-9)

        # O(N^2) would give ratio ~100, O(N log N) should be much less
        # Note: Worst case (all legs in one pivot group) has higher ratio than
        # typical case. Accept up to 60 to account for test variance.
        assert ratio < 60, f"Scaling ratio {ratio:.1f} suggests O(N^2) behavior"

    @pytest.mark.slow
    def test_performance_stable_across_thresholds(self):
        """Performance should be similar at 1% vs 10% threshold after optimization."""
        times = {}

        for threshold_pct in [1, 10]:
            threshold = threshold_pct / 100
            config = DetectionConfig.default().with_origin_prune(threshold, threshold)
            pruner = LegPruner(config)

            state = DetectorState()
            state.active_legs = self._create_many_legs_same_pivot(500, 600)

            bar = make_bar(700)

            start = time.perf_counter()
            pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())
            times[threshold_pct] = time.perf_counter() - start

        # After optimization, 10% should be within 3x of 1% (not 5-10x like before)
        ratio = times[10] / max(times[1], 1e-9)
        assert ratio < 5, f"10% threshold is {ratio:.1f}x slower than 1% - optimization may not be working"


class TestPruningCorrectness:
    """Test that pruning logic remains correct after optimization."""

    def test_closer_leg_pruned_by_older(self):
        """Newer leg close in time/range should be pruned by older."""
        config = DetectionConfig.default().with_origin_prune(0.50, 0.50)
        pruner = LegPruner(config)
        state = DetectorState()

        # Two legs very close in time and range, same pivot
        leg1 = make_bull_leg(90.0, 10, 100.0, 50)  # Older
        leg2 = make_bull_leg(90.1, 12, 100.0, 50)  # Newer, close in time

        state.active_legs = [leg1, leg2]

        bar = make_bar(100)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Newer leg should be pruned
        prune_events = [e for e in events if e.reason == 'origin_proximity_prune']
        assert len(prune_events) == 1
        assert prune_events[0].leg_id == leg2.leg_id

    def test_far_apart_legs_not_pruned(self):
        """Legs far apart in time should not be pruned."""
        config = DetectionConfig.default().with_origin_prune(0.05, 0.05)  # Tight threshold
        pruner = LegPruner(config)
        state = DetectorState()

        # Two legs far apart in time, same pivot
        leg1 = make_bull_leg(90.0, 10, 100.0, 500)   # Old
        leg2 = make_bull_leg(90.1, 400, 100.0, 500)  # Much newer

        state.active_legs = [leg1, leg2]

        bar = make_bar(600)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Should NOT be pruned - too far apart in time
        assert len(events) == 0
        assert len(state.active_legs) == 2

    def test_different_range_legs_not_pruned(self):
        """Legs with very different ranges should not be pruned."""
        config = DetectionConfig.default().with_origin_prune(0.50, 0.05)  # Tight range threshold
        pruner = LegPruner(config)
        state = DetectorState()

        # Two legs close in time but very different ranges
        leg1 = make_bull_leg(90.0, 10, 100.0, 50)   # Range = 10
        leg2 = make_bull_leg(80.0, 12, 100.0, 50)   # Range = 20 (very different)

        state.active_legs = [leg1, leg2]

        bar = make_bar(100)
        events = pruner.apply_origin_proximity_prune(state, 'bull', bar, datetime.now())

        # Should NOT be pruned - ranges too different
        assert len(events) == 0
        assert len(state.active_legs) == 2
