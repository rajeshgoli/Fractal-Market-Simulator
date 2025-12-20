"""
Test for issue #195: TYPE_2_BEAR creates bull leg with inverted temporal order.

TYPE_2_BEAR processing was creating bull legs where origin_index < pivot_index
(past HIGH → current LOW), but bull legs should have pivot_index < origin_index
(past LOW → current HIGH) to maintain consistent temporal semantics with TYPE_2_BULL.

The fix is to not create bull legs in TYPE_2_BEAR since price is trending down.
Bull legs should only be created when price is trending up (TYPE_2_BULL).
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.hierarchical_detector import HierarchicalDetector, Leg
from src.swing_analysis.types import Bar
from src.swing_analysis.events import LegCreatedEvent


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


class TestBullLegTemporalOrder:
    """Test that bull legs always have correct temporal order."""

    def test_bull_legs_have_pivot_before_origin_temporally(self):
        """
        Bull legs should have pivot_index < origin_index.

        This ensures temporal order: past LOW (pivot) → current HIGH (origin)
        which matches the structure created by TYPE_2_BULL.
        """
        detector = HierarchicalDetector()

        # Create a sequence that establishes legs
        # Bar 0: Initial bar - establishes pending pivots
        bar0 = make_bar(0, 100.0, 105.0, 98.0, 102.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH, HL) - should create bull leg
        bar1 = make_bar(1, 102.0, 108.0, 100.0, 106.0)
        events1 = detector.process_bar(bar1)

        # Check all bull legs have correct temporal order
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]

        for leg in bull_legs:
            assert leg.pivot_index < leg.origin_index, (
                f"Bull leg has inverted temporal order: "
                f"pivot_index={leg.pivot_index}, origin_index={leg.origin_index}. "
                f"Expected pivot_index < origin_index."
            )

    def test_type2_bear_does_not_create_inverted_bull_leg(self):
        """
        TYPE_2_BEAR should not create bull legs with inverted temporal order.

        Reproduction of issue #195:
        - Bar 0: H=4416.25 L=4414.25
        - Bar 1: H=4416.00 L=4414.25 (TYPE_1 - equal low)
        - Bar 2: H=4415.75 L=4414.25 (TYPE_1 - equal low)
        - Bar 3: H=4415.25 L=4413.75 (TYPE_2_BEAR - LH, LL)

        The bug was that at bar 3, a bull leg was created with:
        - origin: 4416.25 @ bar 0 (HIGH) - PAST
        - pivot: 4413.75 @ bar 3 (LOW) - CURRENT
        This has origin_index < pivot_index (inverted temporal order).
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 4415.0, 4416.25, 4414.25, 4415.5)
        detector.process_bar(bar0)

        # Bar 1: TYPE_1 - equal low (not HH, not LL, but equal low)
        bar1 = make_bar(1, 4415.5, 4416.0, 4414.25, 4415.0)
        detector.process_bar(bar1)

        # Bar 2: TYPE_1 - equal low again
        bar2 = make_bar(2, 4415.0, 4415.75, 4414.25, 4415.0)
        detector.process_bar(bar2)

        # Bar 3: TYPE_2_BEAR (LH, LL - lower high, lower low)
        bar3 = make_bar(3, 4415.0, 4415.25, 4413.75, 4414.0)
        events3 = detector.process_bar(bar3)

        # Check that no bull leg has inverted temporal order
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]

        for leg in bull_legs:
            assert leg.pivot_index < leg.origin_index, (
                f"Bull leg has inverted temporal order after TYPE_2_BEAR: "
                f"origin_price={leg.origin_price} @ index {leg.origin_index}, "
                f"pivot_price={leg.pivot_price} @ index {leg.pivot_index}. "
                f"Expected pivot_index < origin_index."
            )

    def test_type2_bear_creates_bear_leg_correctly(self):
        """
        TYPE_2_BEAR should create bear legs with correct structure.

        Bear legs have:
        - pivot (defended) at HIGH
        - origin at LOW

        Temporal order: past HIGH (pivot) → current LOW (origin)
        So pivot_index < origin_index.
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar - establishes high
        bar0 = make_bar(0, 100.0, 105.0, 98.0, 102.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bear (LH, LL) - should create bear leg
        bar1 = make_bar(1, 102.0, 103.0, 95.0, 96.0)
        events1 = detector.process_bar(bar1)

        # Check bear legs have correct temporal order
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]

        for leg in bear_legs:
            assert leg.pivot_index < leg.origin_index, (
                f"Bear leg has inverted temporal order: "
                f"pivot_index={leg.pivot_index}, origin_index={leg.origin_index}. "
                f"Expected pivot_index < origin_index."
            )


class TestType2BearBullLegRemoval:
    """Test that TYPE_2_BEAR no longer creates bull legs."""

    def test_type2_bear_does_not_emit_bull_leg_created_event(self):
        """
        After the fix, TYPE_2_BEAR should not emit LegCreatedEvent for bull direction.

        TYPE_2_BEAR indicates price is trending down (LH, LL), so creating bull legs
        doesn't make sense - we shouldn't be setting up bull swings when the trend is down.
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 100.0, 105.0, 98.0, 102.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bear (LH, LL)
        bar1 = make_bar(1, 102.0, 103.0, 95.0, 96.0)
        events1 = detector.process_bar(bar1)

        # Should not have bull LegCreatedEvent from TYPE_2_BEAR
        bull_leg_events = [
            e for e in events1
            if isinstance(e, LegCreatedEvent) and e.direction == 'bull'
        ]

        # With the fix, no bull legs should be created in TYPE_2_BEAR
        assert len(bull_leg_events) == 0, (
            f"TYPE_2_BEAR should not create bull legs, but found {len(bull_leg_events)} "
            f"bull LegCreatedEvents"
        )

    def test_extended_downtrend_no_inverted_bull_legs(self):
        """
        During an extended downtrend, no bull legs with inverted temporal order.

        Simulates multiple TYPE_2_BEAR bars in succession.
        """
        detector = HierarchicalDetector()

        # Start with a high
        bar0 = make_bar(0, 100.0, 110.0, 98.0, 105.0)
        detector.process_bar(bar0)

        # Series of TYPE_2_BEAR bars (downtrend)
        prices = [
            (105.0, 108.0, 95.0, 96.0),   # Bar 1
            (96.0, 100.0, 90.0, 92.0),    # Bar 2
            (92.0, 95.0, 85.0, 86.0),     # Bar 3
            (86.0, 90.0, 80.0, 82.0),     # Bar 4
        ]

        for i, (o, h, l, c) in enumerate(prices, 1):
            bar = make_bar(i, o, h, l, c)
            detector.process_bar(bar)

        # Check no bull legs with inverted temporal order exist
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]

        for leg in bull_legs:
            assert leg.pivot_index < leg.origin_index, (
                f"Found bull leg with inverted temporal order during downtrend: "
                f"origin_index={leg.origin_index}, pivot_index={leg.pivot_index}"
            )
