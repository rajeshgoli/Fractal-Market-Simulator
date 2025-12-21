"""
Test for issue #194: Skip creating dominated legs that would be pruned at turn.

When a leg with a better pivot already exists, creating a new leg with a worse
pivot is wasteful - it will be pruned at turn anyway. This optimization skips
creating such dominated legs at creation time.

A leg is dominated if:
- Bull: any existing bull leg has pivot_price <= new_pivot_price (lower low is better)
- Bear: any existing bear leg has pivot_price >= new_pivot_price (higher high is better)
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


class TestWouldLegBeDominated:
    """Test the _would_leg_be_dominated helper method."""

    def test_bull_leg_not_dominated_when_no_existing_legs(self):
        """Bull leg is not dominated when no existing legs."""
        detector = HierarchicalDetector()

        # No existing legs
        assert not detector._would_leg_be_dominated('bull', Decimal('100'))

    def test_bull_leg_dominated_by_lower_origin(self):
        """Bull leg is dominated when existing leg has lower (better) origin."""
        detector = HierarchicalDetector()

        # Create existing bull leg with origin at 95 (LOW - where upward move started)
        # After #197: Bull leg has origin=LOW, pivot=HIGH
        existing_leg = Leg(
            direction='bull',
            origin_price=Decimal('95'),   # LOW - starting point
            origin_index=0,
            pivot_price=Decimal('110'),   # HIGH - defended extreme
            pivot_index=1,
            price_at_creation=Decimal('105'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(existing_leg)

        # New leg with origin at 100 would be dominated (95 <= 100)
        assert detector._would_leg_be_dominated('bull', Decimal('100'))

        # New leg with origin at 90 would NOT be dominated (95 > 90)
        assert not detector._would_leg_be_dominated('bull', Decimal('90'))

    def test_bull_leg_dominated_by_equal_origin(self):
        """Bull leg is dominated when existing leg has equal origin."""
        detector = HierarchicalDetector()

        # After #197: Bull leg has origin=LOW, pivot=HIGH
        existing_leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),   # LOW - starting point
            origin_index=0,
            pivot_price=Decimal('120'),    # HIGH - defended extreme
            pivot_index=1,
            price_at_creation=Decimal('110'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(existing_leg)

        # Equal origin means dominated
        assert detector._would_leg_be_dominated('bull', Decimal('100'))

    def test_bear_leg_dominated_by_higher_origin(self):
        """Bear leg is dominated when existing leg has higher (better) origin."""
        detector = HierarchicalDetector()

        # Create existing bear leg with origin at 105 (HIGH - where downward move started)
        # After #197: Bear leg has origin=HIGH, pivot=LOW
        existing_leg = Leg(
            direction='bear',
            origin_price=Decimal('105'),   # HIGH - starting point
            origin_index=0,
            pivot_price=Decimal('90'),     # LOW - defended extreme
            pivot_index=1,
            price_at_creation=Decimal('95'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(existing_leg)

        # New leg with origin at 100 would be dominated (105 >= 100)
        assert detector._would_leg_be_dominated('bear', Decimal('100'))

        # New leg with origin at 110 would NOT be dominated (105 < 110)
        assert not detector._would_leg_be_dominated('bear', Decimal('110'))

    def test_inactive_legs_not_considered(self):
        """Only active legs can dominate."""
        detector = HierarchicalDetector()

        # Create stale bull leg with better origin
        # After #197: Bull leg has origin=LOW, pivot=HIGH
        stale_leg = Leg(
            direction='bull',
            origin_price=Decimal('90'),    # LOW - better (lower) origin
            origin_index=0,
            pivot_price=Decimal('110'),    # HIGH
            pivot_index=1,
            price_at_creation=Decimal('105'),
            last_modified_bar=1,
        )
        stale_leg.status = 'stale'
        detector.state.active_legs.append(stale_leg)

        # New leg is NOT dominated because stale leg doesn't count
        assert not detector._would_leg_be_dominated('bull', Decimal('100'))

    def test_different_direction_not_considered(self):
        """Bear legs don't dominate bull legs and vice versa."""
        detector = HierarchicalDetector()

        # Create bear leg
        # After #197: Bear leg has origin=HIGH, pivot=LOW
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal('110'),   # HIGH - where downward move started
            origin_index=0,
            pivot_price=Decimal('90'),     # LOW - defended extreme
            pivot_index=1,
            price_at_creation=Decimal('95'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bear_leg)

        # Bull leg is NOT dominated by bear leg
        assert not detector._would_leg_be_dominated('bull', Decimal('100'))


class TestDominatedLegSkipping:
    """Integration tests for skipping dominated leg creation."""

    def test_dominated_bull_leg_not_created_type2_bull(self):
        """
        In Type 2-Bull processing, don't create bull leg if dominated.

        After #197: Bull leg has origin=LOW, pivot=HIGH. Domination is based on
        origin comparison - leg with lower origin is better (larger range).

        Scenario:
        - Bar 0: Establishes pending_origins['bull'] at low=90
        - Bar 1: Type 2-Bull, creates bull leg with origin=90 (LOW), pivot=102 (HIGH)
        - Bar 2: Continue uptrend, pending bull origin would be 92 (higher than 90)
        - Any new bull leg with origin=92 would be dominated by leg with origin=90
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar - establishes pending_origins['bull'] at 90
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH=102 > 100, HL=92 > 90) - creates bull leg
        # Bull leg: origin=90 (LOW from pending pivot), pivot=102 (HIGH)
        bar1 = make_bar(1, 97.0, 102.0, 92.0, 101.0)
        events1 = detector.process_bar(bar1)

        bull_legs_after_bar1 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs_after_bar1) == 1
        # After #197: origin is at LOW, pivot is at HIGH
        assert bull_legs_after_bar1[0].origin_price == Decimal('90')
        assert bull_legs_after_bar1[0].pivot_price == Decimal('102')

        # Bar 2: Another Type 2-Bull (HH=105 > 102, HL=94 > 92)
        # Would create leg with origin=92, but that's dominated by origin=90
        bar2 = make_bar(2, 101.0, 105.0, 94.0, 104.0)
        events2 = detector.process_bar(bar2)

        # Should still have only 1 bull leg (with origin=90)
        # Pivot should have extended to 105 (new HIGH)
        bull_legs_after_bar2 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs_after_bar2) == 1
        assert bull_legs_after_bar2[0].origin_price == Decimal('90')
        assert bull_legs_after_bar2[0].pivot_price == Decimal('105')  # Extended

        # Verify no new LegCreatedEvent for dominated bull leg
        bull_created_events = [
            e for e in events2
            if isinstance(e, LegCreatedEvent) and e.direction == 'bull'
        ]
        assert len(bull_created_events) == 0

    def test_dominated_bear_leg_not_created_type2_bear(self):
        """
        In Type 2-Bear processing, don't create bear leg if dominated.

        After #197: Bear leg has origin=HIGH, pivot=LOW. Domination is based on
        origin comparison - leg with higher origin is better (larger range).

        Scenario:
        - Bar 0: Establishes pending_origins['bear'] at high=100
        - Bar 1: Type 2-Bull updates pending_origins['bear'] to 102
        - Bar 2: Type 2-Bear creates bear leg with origin=102 (HIGH), pivot=85 (LOW)
        - Any new bear leg with origin < 102 would be dominated
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH, HL) - updates pending_origins['bear'] to 102
        bar1 = make_bar(1, 97.0, 102.0, 92.0, 101.0)
        events1 = detector.process_bar(bar1)

        bear_legs_after_bar1 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        # May or may not have bear leg depending on pending pivots
        initial_bear_count = len(bear_legs_after_bar1)

        # Bar 2: Type 2-Bear (LH, LL) - creates bear leg
        # origin should be from the best HIGH seen (102), pivot at current LOW (85)
        bar2 = make_bar(2, 101.0, 101.0, 85.0, 86.0)
        events2 = detector.process_bar(bar2)

        bear_legs_after_bar2 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]

        # Verify bear legs have origin at best HIGH seen
        # After #197: origin is at HIGH, pivot is at LOW
        for leg in bear_legs_after_bar2:
            if initial_bear_count > 0:
                best_existing = max(
                    bear_legs_after_bar1,
                    key=lambda l: l.origin_price
                )
                # No bear leg should have a worse origin than the best existing one
                assert leg.origin_price >= best_existing.origin_price

    def test_non_dominated_bull_leg_still_created(self):
        """
        Legs with better origins should still be created.

        After #197: Bull leg has origin=LOW, pivot=HIGH. Domination is based on
        origin comparison - leg with lower origin is better (larger range).

        Scenario:
        - Bar 0: Establishes pending_origins['bull'] at low=100
        - Bar 1: Dip to make new low at 95 (pending_origins['bull'] updates to 95)
        - Bar 2: Type 2-Bull creates bull leg with origin=95 (best LOW), pivot=115 (HIGH)
        - Verify the better origin (95) was used
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar - establishes pending_origins['bull'] at 100
        bar0 = make_bar(0, 102.0, 110.0, 100.0, 108.0)
        detector.process_bar(bar0)

        # Bar 1: Price dips to make lower low at 95
        # This updates pending_origins['bull'] to 95
        bar1 = make_bar(1, 108.0, 109.0, 95.0, 100.0)
        detector.process_bar(bar1)

        # Bar 2: Type 2-Bull (HH=115 > 109, HL=98 > 95) - creates bull leg
        # origin=95 (LOW from pending pivot), pivot=115 (HIGH)
        bar2 = make_bar(2, 100.0, 115.0, 98.0, 112.0)
        events2 = detector.process_bar(bar2)

        # Check that a bull leg with the best origin was created
        # After #197: origin is at LOW, pivot is at HIGH
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        # Should have at least one bull leg with origin=95 (the best low seen)
        origins = [leg.origin_price for leg in bull_legs]
        assert Decimal('95') in origins or any(o <= Decimal('95') for o in origins)
