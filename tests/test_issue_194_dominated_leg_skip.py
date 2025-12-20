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

    def test_bull_leg_dominated_by_lower_pivot(self):
        """Bull leg is dominated when existing leg has lower (better) pivot."""
        detector = HierarchicalDetector()

        # Create existing bull leg with pivot at 95
        existing_leg = Leg(
            direction='bull',
            pivot_price=Decimal('95'),
            pivot_index=0,
            origin_price=Decimal('110'),
            origin_index=1,
            price_at_creation=Decimal('105'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(existing_leg)

        # New leg with pivot at 100 would be dominated (95 <= 100)
        assert detector._would_leg_be_dominated('bull', Decimal('100'))

        # New leg with pivot at 90 would NOT be dominated (95 > 90)
        assert not detector._would_leg_be_dominated('bull', Decimal('90'))

    def test_bull_leg_dominated_by_equal_pivot(self):
        """Bull leg is dominated when existing leg has equal pivot."""
        detector = HierarchicalDetector()

        existing_leg = Leg(
            direction='bull',
            pivot_price=Decimal('100'),
            pivot_index=0,
            origin_price=Decimal('110'),
            origin_index=1,
            price_at_creation=Decimal('105'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(existing_leg)

        # Equal pivot means dominated
        assert detector._would_leg_be_dominated('bull', Decimal('100'))

    def test_bear_leg_dominated_by_higher_pivot(self):
        """Bear leg is dominated when existing leg has higher (better) pivot."""
        detector = HierarchicalDetector()

        # Create existing bear leg with pivot at 105
        existing_leg = Leg(
            direction='bear',
            pivot_price=Decimal('105'),
            pivot_index=0,
            origin_price=Decimal('90'),
            origin_index=1,
            price_at_creation=Decimal('95'),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(existing_leg)

        # New leg with pivot at 100 would be dominated (105 >= 100)
        assert detector._would_leg_be_dominated('bear', Decimal('100'))

        # New leg with pivot at 110 would NOT be dominated (105 < 110)
        assert not detector._would_leg_be_dominated('bear', Decimal('110'))

    def test_inactive_legs_not_considered(self):
        """Only active legs can dominate."""
        detector = HierarchicalDetector()

        # Create stale bull leg with better pivot
        stale_leg = Leg(
            direction='bull',
            pivot_price=Decimal('90'),
            pivot_index=0,
            origin_price=Decimal('110'),
            origin_index=1,
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
        bear_leg = Leg(
            direction='bear',
            pivot_price=Decimal('110'),
            pivot_index=0,
            origin_price=Decimal('90'),
            origin_index=1,
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

        Scenario:
        - Bar 0: Establishes pending bull pivot at low=90
        - Bar 1: Type 2-Bear, creates bull leg with pivot=88 (new low)
        - Bar 2: Type 2-Bull, should NOT create new bull leg with pivot=90
                 because existing leg has pivot=88 which is better
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bear (LH, LL) - creates bull leg with lower pivot
        bar1 = make_bar(1, 97.0, 98.0, 88.0, 89.0)
        events1 = detector.process_bar(bar1)

        bull_legs_after_bar1 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs_after_bar1) == 1
        assert bull_legs_after_bar1[0].pivot_price == Decimal('88')

        # Bar 2: Type 2-Bull (HH, HL) - should NOT create new bull leg
        # because existing leg with pivot=88 dominates potential leg with pivot=90
        bar2 = make_bar(2, 89.0, 102.0, 90.0, 101.0)
        events2 = detector.process_bar(bar2)

        # Should still have only 1 bull leg
        bull_legs_after_bar2 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs_after_bar2) == 1
        assert bull_legs_after_bar2[0].pivot_price == Decimal('88')

        # Verify no LegCreatedEvent for dominated bull leg
        bull_created_events = [
            e for e in events2
            if isinstance(e, LegCreatedEvent) and e.direction == 'bull'
        ]
        assert len(bull_created_events) == 0

    def test_dominated_bear_leg_not_created_type2_bear(self):
        """
        In Type 2-Bear processing, don't create bear leg if dominated.

        Scenario:
        - Bar 0: Establishes pending bear pivot at high=100
        - Bar 1: Type 2-Bull creates bear leg with pivot=102 (new high)
        - Bar 2: Type 2-Bear, should NOT create new bear leg with pivot=100
                 because existing leg has pivot=102 which is better
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 97.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH, HL) - creates bear leg with higher pivot
        bar1 = make_bar(1, 97.0, 102.0, 92.0, 101.0)
        events1 = detector.process_bar(bar1)

        bear_legs_after_bar1 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        # May or may not have bear leg depending on pending pivots
        initial_bear_count = len(bear_legs_after_bar1)

        # Bar 2: Type 2-Bear (LH, LL) - should NOT create new bear leg
        # if existing leg with pivot=102 dominates potential leg with pivot=100
        bar2 = make_bar(2, 101.0, 101.0, 85.0, 86.0)
        events2 = detector.process_bar(bar2)

        bear_legs_after_bar2 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]

        # If a bear leg with pivot 102 existed, no new one with pivot 100 should be created
        for leg in bear_legs_after_bar2:
            # No bear leg should have a worse pivot than the best existing one
            if initial_bear_count > 0:
                best_existing = max(
                    bear_legs_after_bar1,
                    key=lambda l: l.pivot_price
                )
                assert leg.pivot_price >= best_existing.pivot_price

    def test_non_dominated_bull_leg_still_created(self):
        """
        Legs with better pivots should still be created.

        Scenario:
        - Bar 0: Creates bull leg with pivot=100
        - Bar 1: Type 2-Bear makes new low at 95 - should create new leg
                 because 95 < 100 (better pivot)
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 95.0, 110.0, 100.0, 105.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bear with lower low - should create leg
        bar1 = make_bar(1, 105.0, 108.0, 95.0, 96.0)
        events1 = detector.process_bar(bar1)

        # Check that a bull leg with the lower pivot was created
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        # Should have at least one bull leg with the lower pivot
        pivots = [leg.pivot_price for leg in bull_legs]
        assert Decimal('95') in pivots or any(p <= Decimal('95') for p in pivots)
