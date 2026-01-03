"""
Test for Issue #192: Leg bar indices don't match actual price locations

The bug: Leg objects have pivot_index and origin_index values that don't
correspond to the bars where those prices actually occur. The prices are
correct, but the bar indices are stale/wrong.

This test reproduces the exact scenario from the issue using synthetic data.
"""

import pytest
from decimal import Decimal
from typing import List

from src.swing_analysis.dag import (
    HierarchicalDetector,
    Leg,
)
from src.swing_analysis.detection_config import DetectionConfig
from src.swing_analysis.types import Bar


def calibrate(bars, config=None):
    """Process bars through detector and return detector + all events."""
    detector = HierarchicalDetector(config or DetectionConfig.default())
    all_events = []
    for bar in bars:
        events = detector.process_bar(bar)
        all_events.extend(events)
    return detector, all_events


def make_bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    timestamp: int = None,
) -> Bar:
    """Helper to create Bar objects for testing."""
    return Bar(
        index=index,
        timestamp=timestamp or 1700000000 + index * 60,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class TestLegBarIndexConsistency:
    """Test that leg bar indices always match their corresponding prices."""

    def test_pivot_index_matches_pivot_price_location(self):
        """
        Pivot index should always point to a bar where pivot price occurs.

        Scenario from issue #192:
        - Bar 31: L=4426.50 (first occurrence of pivot price)
        - Bar 32: L=4426.50
        - Bar 34: H=4436.75 (major high)
        - Bar 36: H=4435.25
        - Bar 37: L=4432.00
        - Bar 38: H=4434.00
        - Bar 39: L=4426.50

        A bull leg should NOT have pivot_index=37 if pivot_price=4426.50,
        because bar 37's low is 4432.00, not 4426.50.
        """
        # Build synthetic bars matching the issue scenario
        bars = [
            # Bars 0-30: setup bars with declining prices
            make_bar(0, 4450.0, 4455.0, 4445.0, 4450.0),
            make_bar(1, 4450.0, 4452.0, 4440.0, 4445.0),
            make_bar(2, 4445.0, 4448.0, 4435.0, 4440.0),
            make_bar(3, 4440.0, 4445.0, 4430.0, 4435.0),
        ]

        # Add bars from the issue
        # Starting at index 4 to simulate the window offset
        bars.extend([
            # Bars leading up to the scenario
            make_bar(4, 4435.0, 4440.0, 4428.0, 4430.0),
            make_bar(5, 4430.0, 4432.0, 4425.0, 4428.0),

            # Bar 6 (simulating bar 31): L=4426.50 - first occurrence
            make_bar(6, 4428.0, 4429.75, 4426.50, 4427.0),

            # Bar 7 (simulating bar 32): L=4426.50 - same low
            make_bar(7, 4427.0, 4428.75, 4426.50, 4428.0),

            # Bar 8 (gap to simulating bar 34): H=4436.75 major high
            make_bar(8, 4428.0, 4436.75, 4430.75, 4435.0),

            # Bar 9 (simulating bar 36): H=4435.25
            make_bar(9, 4435.0, 4435.25, 4432.50, 4433.0),

            # Bar 10 (simulating bar 37): L=4432.00
            make_bar(10, 4433.0, 4434.75, 4432.00, 4433.5),

            # Bar 11 (simulating bar 38): H=4434.00
            make_bar(11, 4433.5, 4434.00, 4430.75, 4431.0),

            # Bar 12 (simulating bar 39): L=4426.50 - same as bar 6
            make_bar(12, 4431.0, 4432.50, 4426.50, 4427.5),

            # Additional bars to allow swing formation
            make_bar(13, 4427.5, 4430.0, 4427.0, 4429.0),
            make_bar(14, 4429.0, 4432.0, 4428.0, 4431.0),
            make_bar(15, 4431.0, 4435.0, 4430.0, 4434.0),
        ])

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        # Check all active legs for price/index consistency
        for leg in detector.state.active_legs:
            pivot_bar = bars[leg.pivot_index] if leg.pivot_index < len(bars) else None
            origin_bar = bars[leg.origin_index] if leg.origin_index < len(bars) else None

            # After #197 terminology fix:
            # - Bull leg: origin=LOW (starting point), pivot=HIGH (defended extreme)
            # - Bear leg: origin=HIGH (starting point), pivot=LOW (defended extreme)
            if pivot_bar is not None:
                if leg.direction == 'bull':
                    # Bull leg pivot is at HIGH
                    actual_price_at_index = Decimal(str(pivot_bar.high))
                    assert leg.pivot_price == actual_price_at_index, (
                        f"Bull leg {leg.leg_id}: pivot_price={leg.pivot_price} "
                        f"but bar {leg.pivot_index}'s high is {actual_price_at_index}"
                    )
                else:
                    # Bear leg pivot is at LOW
                    actual_price_at_index = Decimal(str(pivot_bar.low))
                    assert leg.pivot_price == actual_price_at_index, (
                        f"Bear leg {leg.leg_id}: pivot_price={leg.pivot_price} "
                        f"but bar {leg.pivot_index}'s low is {actual_price_at_index}"
                    )

            if origin_bar is not None:
                if leg.direction == 'bull':
                    # Bull leg origin is at LOW
                    actual_price_at_index = Decimal(str(origin_bar.low))
                    assert leg.origin_price == actual_price_at_index, (
                        f"Bull leg {leg.leg_id}: origin_price={leg.origin_price} "
                        f"but bar {leg.origin_index}'s low is {actual_price_at_index}"
                    )
                else:
                    # Bear leg origin is at HIGH
                    actual_price_at_index = Decimal(str(origin_bar.high))
                    assert leg.origin_price == actual_price_at_index, (
                        f"Bear leg {leg.leg_id}: origin_price={leg.origin_price} "
                        f"but bar {leg.origin_index}'s high is {actual_price_at_index}"
                    )

    def test_origin_index_matches_origin_price_location(self):
        """
        Origin index should always point to a bar where origin price occurs.

        From issue #192:
        - origin_price: 4434.0, origin_index: 36
        - But bar 36's high is 4435.25, not 4434.0
        - 4434.0 actually appears at bar 38
        """
        # Same setup as above
        bars = [
            make_bar(0, 4440.0, 4445.0, 4430.0, 4435.0),
            make_bar(1, 4435.0, 4440.0, 4428.0, 4430.0),
            make_bar(2, 4430.0, 4432.0, 4425.0, 4428.0),
            make_bar(3, 4428.0, 4429.75, 4426.50, 4427.0),
            make_bar(4, 4427.0, 4428.75, 4426.50, 4428.0),
            make_bar(5, 4428.0, 4436.75, 4430.75, 4435.0),
            make_bar(6, 4435.0, 4435.25, 4432.50, 4433.0),
            make_bar(7, 4433.0, 4434.75, 4432.00, 4433.5),
            make_bar(8, 4433.5, 4434.00, 4430.75, 4431.0),
            make_bar(9, 4431.0, 4432.50, 4426.50, 4427.5),
            make_bar(10, 4427.5, 4430.0, 4427.0, 4429.0),
            make_bar(11, 4429.0, 4432.0, 4428.0, 4431.0),
            make_bar(12, 4431.0, 4435.0, 4430.0, 4434.0),
        ]

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        # Same checks as above
        for leg in detector.state.active_legs:
            origin_bar = bars[leg.origin_index] if leg.origin_index < len(bars) else None

            # After #197 terminology fix:
            # - Bull leg: origin=LOW (starting point), pivot=HIGH (defended extreme)
            # - Bear leg: origin=HIGH (starting point), pivot=LOW (defended extreme)
            if origin_bar is not None:
                if leg.direction == 'bull':
                    actual_price_at_index = Decimal(str(origin_bar.low))
                    assert leg.origin_price == actual_price_at_index, (
                        f"Bull leg {leg.leg_id}: origin_price={leg.origin_price} "
                        f"but bar {leg.origin_index}'s low is {actual_price_at_index}"
                    )
                else:
                    actual_price_at_index = Decimal(str(origin_bar.high))
                    assert leg.origin_price == actual_price_at_index, (
                        f"Bear leg {leg.leg_id}: origin_price={leg.origin_price} "
                        f"but bar {leg.origin_index}'s high is {actual_price_at_index}"
                    )

    def test_extended_origin_updates_both_price_and_index(self):
        """
        Origins are FIXED after #197 - they do NOT extend.
        This test now verifies origin consistency (price matches bar).

        Bull leg: origin=LOW (fixed starting point)
        Bear leg: origin=HIGH (fixed starting point)
        """
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),
            make_bar(1, 100.0, 108.0, 98.0, 105.0),
            make_bar(2, 105.0, 112.0, 102.0, 110.0),
            make_bar(3, 110.0, 115.0, 107.0, 112.0),
            make_bar(4, 112.0, 113.0, 108.0, 110.0),
            make_bar(5, 110.0, 112.0, 109.0, 111.0),
        ]

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        # Check that bull legs have consistent origin price/index
        for leg in detector.state.active_legs:
            if leg.direction == 'bull':
                origin_bar = bars[leg.origin_index]
                # Bull leg origin is at LOW (not HIGH)
                actual_low_at_index = Decimal(str(origin_bar.low))
                assert leg.origin_price == actual_low_at_index, (
                    f"Bull leg origin mismatch: origin_price={leg.origin_price} "
                    f"but bar {leg.origin_index}'s low is {actual_low_at_index}"
                )

    def test_extended_pivot_updates_both_price_and_index(self):
        """
        When a pivot extends to a new extreme, both price AND index must update.
        After #197: Bull leg pivot is at HIGH and extends on new highs.
        """
        # Bars with progressively higher highs for bull leg pivot extension
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),
            make_bar(1, 100.0, 108.0, 98.0, 105.0),   # Type 2-Bull
            make_bar(2, 105.0, 112.0, 102.0, 110.0),  # Type 2-Bull, higher high 112
            make_bar(3, 110.0, 115.0, 107.0, 112.0),  # Type 2-Bull, higher high 115
            make_bar(4, 112.0, 113.0, 108.0, 110.0),  # Type 2-Bear retracement
            make_bar(5, 110.0, 112.0, 109.0, 111.0),
        ]

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        # Check that bull legs have consistent pivot price/index
        # Bull leg pivot is at HIGH (not LOW)
        for leg in detector.state.active_legs:
            if leg.direction == 'bull':
                pivot_bar = bars[leg.pivot_index]
                actual_high_at_index = Decimal(str(pivot_bar.high))
                assert leg.pivot_price == actual_high_at_index, (
                    f"Bull leg pivot mismatch: pivot_price={leg.pivot_price} "
                    f"but bar {leg.pivot_index}'s high is {actual_high_at_index}"
                )


class TestPivotExtension:
    """Test that pivots are extended correctly when price makes new extremes (#192)."""

    def test_bull_leg_pivot_extends_on_new_low(self):
        """
        Bull leg pivots should extend to new lows.

        Scenario:
        1. Bull leg created with pivot at bar 2's low
        2. Bar 3 makes a new low
        3. Pivot should update to bar 3's low and index
        """
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),   # Setup
            make_bar(1, 100.0, 108.0, 98.0, 105.0),   # Type 2-Bull, creates bull leg
            make_bar(2, 105.0, 106.0, 92.0, 95.0),    # Type 2-Bear, new low at 92
            make_bar(3, 95.0, 97.0, 88.0, 90.0),      # Type 2-Bear, even lower at 88
            make_bar(4, 90.0, 95.0, 89.0, 94.0),      # Some retracement
        ]

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        # Find active, non-breached bull legs and check their pivot matches the lowest point
        # Breached legs (max_origin_breach is not None) don't have extending pivots
        for leg in detector.state.active_legs:
            if leg.direction == 'bull' and leg.status == 'active' and leg.max_origin_breach is None:
                pivot_bar = bars[leg.pivot_index]
                actual_low = Decimal(str(pivot_bar.low))
                assert leg.pivot_price == actual_low, (
                    f"Bull leg {leg.leg_id}: pivot_price={leg.pivot_price} "
                    f"should match bar {leg.pivot_index}'s low={actual_low}"
                )

    def test_bear_leg_pivot_extends_on_new_high(self):
        """
        Bear leg pivots should extend to new highs.

        Scenario:
        1. Bear leg created with pivot at bar 2's high
        2. Bar 3 makes a new high
        3. Pivot should update to bar 3's high and index
        """
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),   # Setup
            make_bar(1, 100.0, 102.0, 92.0, 95.0),    # Type 2-Bear, creates bear leg
            make_bar(2, 95.0, 110.0, 94.0, 108.0),    # Type 2-Bull, new high at 110
            make_bar(3, 108.0, 115.0, 106.0, 112.0),  # Type 2-Bull, even higher at 115
            make_bar(4, 112.0, 113.0, 108.0, 110.0),  # Some retracement
        ]

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        # Find active, non-breached bear legs and check their pivot matches the highest point
        # Breached legs (max_origin_breach is not None) don't have extending pivots
        for leg in detector.state.active_legs:
            if leg.direction == 'bear' and leg.status == 'active' and leg.max_origin_breach is None:
                pivot_bar = bars[leg.pivot_index]
                actual_high = Decimal(str(pivot_bar.high))
                assert leg.pivot_price == actual_high, (
                    f"Bear leg {leg.leg_id}: pivot_price={leg.pivot_price} "
                    f"should match bar {leg.pivot_index}'s high={actual_high}"
                )

    def test_pivot_extension_updates_both_price_and_index(self):
        """
        When pivot extends, both price AND index must update together.

        This is the core of issue #192 - prices were updating but indices were stale.

        After #197: Bull leg pivot is at HIGH (defended extreme that extends on new highs).
        """
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),
            make_bar(1, 100.0, 108.0, 98.0, 105.0),   # Type 2-Bull
            make_bar(2, 105.0, 112.0, 102.0, 110.0),  # Type 2-Bull, high at 112
            make_bar(3, 110.0, 115.0, 107.0, 113.0),  # Type 2-Bull, higher at 115
            make_bar(4, 113.0, 118.0, 110.0, 116.0),  # Type 2-Bull, higher at 118
            make_bar(5, 116.0, 117.0, 112.0, 114.0),  # Retracement
        ]

        config = DetectionConfig.default()
        detector, events = calibrate(bars, config)

        for leg in detector.state.active_legs:
            if leg.direction == 'bull':
                pivot_bar = bars[leg.pivot_index]
                # After #197: Bull leg pivot is at HIGH
                actual_high = Decimal(str(pivot_bar.high))
                assert leg.pivot_price == actual_high, (
                    f"MISMATCH: Bull leg pivot_price={leg.pivot_price} "
                    f"but bar {leg.pivot_index}'s high is {actual_high}. "
                    f"The index points to a bar with different price!"
                )


class TestPendingOriginConsistency:
    """Test that pending origins maintain price/index consistency."""

    def test_pending_origin_price_matches_index(self):
        """
        Pending origin's price should always match the bar at its index.
        """
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),
            make_bar(1, 100.0, 108.0, 98.0, 105.0),  # Type 2-Bull
            make_bar(2, 105.0, 106.0, 99.0, 103.0),  # Type 1 (inside)
        ]

        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        for bar in bars:
            detector.process_bar(bar)

            # After each bar, check pending origins are consistent
            for direction in ['bull', 'bear']:
                pending = detector.state.pending_origins.get(direction)
                if pending is not None:
                    # Get the bar at the pending pivot's index
                    pivot_bar = bars[pending.bar_index]

                    if direction == 'bull':
                        # Bull pending pivot should be at LOW
                        expected_price = Decimal(str(pivot_bar.low))
                        assert pending.price == expected_price, (
                            f"After bar {bar.index}: pending bull pivot price={pending.price} "
                            f"but bar {pending.bar_index}'s low is {expected_price}"
                        )
                    else:
                        # Bear pending pivot should be at HIGH
                        expected_price = Decimal(str(pivot_bar.high))
                        assert pending.price == expected_price, (
                            f"After bar {bar.index}: pending bear pivot price={pending.price} "
                            f"but bar {pending.bar_index}'s high is {expected_price}"
                        )
