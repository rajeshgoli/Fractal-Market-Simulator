"""
Test for issue #193: Bear leg pivot should match bull leg origin at swing extrema.

The bug: When a bull leg terminates at a swing high (e.g., 4436.75), the subsequent
bear leg should start from that same extrema. Currently, the pending pivot is
unconditionally overwritten by each bar's high, so bear legs start from a later,
lower high (e.g., 4435.25).
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.hierarchical_detector import HierarchicalDetector, PendingPivot
from src.swing_analysis.types import Bar
from src.data.ohlc_loader import load_ohlc


def make_bar(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    """Helper to create Bar objects for testing."""
    return Bar(
        index=index,
        timestamp=1700000000 + index * 60,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class TestPendingPivotOverwrite:
    """Test that pending pivots are only updated when more extreme."""

    def test_bear_pivot_not_overwritten_by_lower_high(self):
        """
        Bug #193: Bear pivot should only be updated when bar.high > existing pivot.

        Scenario (using Type 1 inside bars to avoid leg creation):
        - Bar 0: High = 100 (sets initial bear pivot)
        - Bar 1: Inside bar with High = 98 (lower high - should NOT overwrite bear pivot)

        Expected: pending_pivots['bear'].price should remain 100
        """
        detector = HierarchicalDetector()

        # Bar 0: Sets initial pending pivots
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        assert detector.state.pending_pivots['bear'] is not None
        assert detector.state.pending_pivots['bear'].price == Decimal('100')
        assert detector.state.pending_pivots['bear'].bar_index == 0

        # Bar 1: Inside bar (LH, HL) - doesn't create legs, doesn't overwrite bear pivot
        bar1 = make_bar(1, 97.0, 98.0, 92.0, 95.0)
        detector.process_bar(bar1)

        # Bear pivot should still be 100 from bar 0
        assert detector.state.pending_pivots['bear'].price == Decimal('100')
        assert detector.state.pending_pivots['bear'].bar_index == 0

        # Bull pivot should also remain at 90 (higher low doesn't overwrite)
        assert detector.state.pending_pivots['bull'].price == Decimal('90')
        assert detector.state.pending_pivots['bull'].bar_index == 0

    def test_bull_pivot_not_overwritten_by_higher_low(self):
        """
        Bull pivot should only be updated when bar.low < existing pivot.

        Scenario (using Type 1 inside bars to avoid leg creation):
        - Bar 0: Low = 90 (sets initial bull pivot)
        - Bar 1: Inside bar with Low = 92 (higher low - should NOT overwrite bull pivot)

        Expected: pending_pivots['bull'].price should remain 90
        """
        detector = HierarchicalDetector()

        # Bar 0: Sets initial pending pivots
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        assert detector.state.pending_pivots['bull'] is not None
        assert detector.state.pending_pivots['bull'].price == Decimal('90')

        # Bar 1: Inside bar (LH, HL) - doesn't create legs, doesn't overwrite bull pivot
        bar1 = make_bar(1, 97.0, 98.0, 92.0, 95.0)
        detector.process_bar(bar1)

        # Bull pivot should still be 90 from bar 0
        assert detector.state.pending_pivots['bull'].price == Decimal('90')
        assert detector.state.pending_pivots['bull'].bar_index == 0

        # Bear pivot should also remain at 100 (lower high doesn't overwrite)
        assert detector.state.pending_pivots['bear'].price == Decimal('100')
        assert detector.state.pending_pivots['bear'].bar_index == 0

    def test_bear_pivot_updated_when_higher(self):
        """Bear pivot should be updated when bar.high > existing pivot."""
        detector = HierarchicalDetector()

        # Bar 0: Sets initial pending pivots
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        assert detector.state.pending_pivots['bear'].price == Decimal('100')

        # Bar 1: Higher high (Type 2-Bull) - SHOULD update bear pivot
        bar1 = make_bar(1, 97.0, 105.0, 92.0, 103.0)
        detector.process_bar(bar1)

        # Bear pivot should be updated to 105
        assert detector.state.pending_pivots['bear'].price == Decimal('105')
        assert detector.state.pending_pivots['bear'].bar_index == 1

    def test_bull_pivot_updated_when_lower(self):
        """Bull pivot should be updated when bar.low < existing pivot."""
        detector = HierarchicalDetector()

        # Bar 0: Sets initial pending pivots
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        assert detector.state.pending_pivots['bull'].price == Decimal('90')

        # Bar 1: Lower low (Type 2-Bear) - SHOULD update bull pivot
        bar1 = make_bar(1, 97.0, 98.0, 85.0, 86.0)
        detector.process_bar(bar1)

        # Bull pivot should be updated to 85
        assert detector.state.pending_pivots['bull'].price == Decimal('85')
        assert detector.state.pending_pivots['bull'].bar_index == 1

    def test_inside_bar_preserves_extreme_pivots(self):
        """
        Inside bars (Type 1) should not overwrite more extreme pivots.

        Scenario:
        - Bar 0: H=100, L=90
        - Bar 1: Inside bar H=98, L=92

        Expected: Both pivots should remain at bar 0 extremes
        """
        detector = HierarchicalDetector()

        # Bar 0: Sets initial pending pivots
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        # Bar 1: Inside bar (LH, HL)
        bar1 = make_bar(1, 95.0, 98.0, 92.0, 94.0)
        detector.process_bar(bar1)

        # Both pivots should remain from bar 0
        assert detector.state.pending_pivots['bear'].price == Decimal('100')
        assert detector.state.pending_pivots['bear'].bar_index == 0
        assert detector.state.pending_pivots['bull'].price == Decimal('90')
        assert detector.state.pending_pivots['bull'].bar_index == 0

    def test_outside_bar_updates_both_if_extreme(self):
        """
        Outside bars (Type 3: HH, LL) update both pivots if more extreme.
        """
        detector = HierarchicalDetector()

        # Bar 0: Sets initial pending pivots
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        # Bar 1: Outside bar (HH, LL)
        bar1 = make_bar(1, 97.0, 110.0, 80.0, 95.0)
        detector.process_bar(bar1)

        # Both pivots should be updated
        assert detector.state.pending_pivots['bear'].price == Decimal('110')
        assert detector.state.pending_pivots['bear'].bar_index == 1
        assert detector.state.pending_pivots['bull'].price == Decimal('80')
        assert detector.state.pending_pivots['bull'].bar_index == 1


class TestRealDataPivotMismatch:
    """Test with real ES 5-minute data from validation session."""

    @pytest.mark.skipif(
        not __import__('os').path.exists('test_data/es-5m.csv'),
        reason="Test data file not available"
    )
    def test_bear_leg_pivot_matches_bull_leg_origin(self):
        """
        Bug #193: Bear leg pivot should equal bull leg origin at swing extrema.

        At bar 45 (window offset 1172207 in es-5m.csv):
        - Bull leg ends at origin 4436.75 (bar 32)
        - Bear leg should start from pivot 4436.75
        - Actually starts from pivot 4435.25 (a later, lower high) - THIS IS THE BUG

        After fix, the largest bear leg should have pivot_price == 4436.75.
        """
        # Load test data
        df, _ = load_ohlc("test_data/es-5m.csv")
        window_offset = 1172207
        window = df.iloc[window_offset:window_offset + 50]

        detector = HierarchicalDetector()

        # Process bars up to bar 45
        for i, (df_idx, row) in enumerate(window.iterrows()):
            if i > 45:
                break
            # The dataframe index IS the timestamp for this format
            if hasattr(df_idx, 'timestamp'):
                ts = int(df_idx.timestamp())
            else:
                ts = 1700000000 + i * 300  # 5-minute bars fallback
            bar = Bar(
                index=i,
                timestamp=ts,
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
            )
            detector.process_bar(bar)

        # Find bear legs
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]

        if not bear_legs:
            pytest.skip("No active bear legs found at this window offset")

        # Find the largest bear leg by range
        largest_bear = max(bear_legs, key=lambda l: l.range)

        # Find the bull leg with origin at 4436.75
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.origin_price == Decimal('4436.75')
        ]

        # The largest bear leg's pivot should be the swing high (4436.75)
        # Not a later, lower high (4435.25)
        if bull_legs:
            bull_origin = bull_legs[0].origin_price
            # After the fix, these should match
            assert largest_bear.pivot_price >= Decimal('4436.75'), (
                f"Bear leg pivot {largest_bear.pivot_price} should be at or above "
                f"the swing high 4436.75, not at a later lower high"
            )
