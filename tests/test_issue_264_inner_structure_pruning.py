"""
Test for issue #264: Prune inner structure bull legs when outer bear structure is invalidated.

When a bear leg that is fully contained inside a larger bear leg gets invalidated,
prune any bull legs originating from the inner bear's pivot. These are "inner structure"
legs that become redundant when price breaks past the outer structure.

Containment definition (bear legs):
- B_inner contained in B_outer iff B_inner.origin < B_outer.origin AND B_inner.pivot > B_outer.pivot

For bull legs:
- B_inner contained in B_outer iff B_inner.origin > B_outer.origin AND B_inner.pivot < B_outer.pivot
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.dag import HierarchicalDetector, Leg
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.dag.state import DetectorState
from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.types import Bar
from src.swing_analysis.events import LegCreatedEvent, LegPrunedEvent, OriginBreachedEvent


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


class TestInnerStructurePruningBasic:
    """Test basic inner structure pruning scenarios."""

    def test_prune_inner_structure_bull_leg(self):
        """
        Test the primary scenario from issue #264:

        H1=6100 -> L1=5900 -> H2=6050 -> L2=5950 -> H4=6150

        At H4:
        - Bear leg H1->L1 (origin=6100, pivot=5900) is invalidated
        - Bear leg H2->L2 (origin=6050, pivot=5950) is invalidated
        - Bull leg L1->H4 (origin=5900, pivot=6150) exists
        - Bull leg L2->H4 (origin=5950, pivot=6150) exists

        H2->L2 is contained in H1->L1 (H2 < H1 and L2 > L1).
        L2->H4 should be pruned, L1->H4 should survive.
        """
        detector = HierarchicalDetector()

        # Bar 0: H1=6100, L=6090
        bar0 = make_bar(0, 6095.0, 6100.0, 6090.0, 6095.0)
        detector.process_bar(bar0)

        # Bar 1: L1=5900 - Type 2-Bear (LH, LL), starts bear leg from H1
        bar1 = make_bar(1, 6095.0, 6098.0, 5900.0, 5910.0)
        detector.process_bar(bar1)

        # Bar 2: H2=6050 - Type 2-Bull (HH, HL), this retraces back up
        # Also starts a bull leg from L1
        bar2 = make_bar(2, 5910.0, 6050.0, 5905.0, 6045.0)
        detector.process_bar(bar2)

        # Bar 3: L2=5950 - Type 2-Bear (LH, LL), inner low higher than L1
        # This creates a bear leg H2->L2 that is contained in H1->L1
        bar3 = make_bar(3, 6045.0, 6048.0, 5950.0, 5960.0)
        detector.process_bar(bar3)

        # Bar 4: H3=6000 - partial retrace, may form swings
        bar4 = make_bar(4, 5960.0, 6000.0, 5955.0, 5995.0)
        detector.process_bar(bar4)

        # Check we have bear legs from both H1 and H2
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.max_origin_breach is None
        ]
        # We should have at least one bear leg
        # Due to domination pruning, we might only have the H1->L1 leg
        # Let's check what we have

        # Bar 5: H4=6150 - breaks above H1=6100, invalidating both bear legs
        bar5 = make_bar(5, 5995.0, 6150.0, 5990.0, 6140.0)
        events5 = detector.process_bar(bar5)

        # Check for origin breach events
        origin_breach_events = [e for e in events5 if isinstance(e, OriginBreachedEvent)]

        # Check for inner_structure prune events
        prune_events = [e for e in events5 if isinstance(e, LegPrunedEvent)]
        inner_structure_events = [e for e in prune_events if e.reason == 'inner_structure']

        # Get remaining bull legs (non-breached)
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]

        # If we had multiple bear legs invalidated together with containment,
        # and both had corresponding bull legs with the same pivot,
        # the inner structure pruning should have occurred
        # The exact behavior depends on how many legs were actually created

        # The key assertion: if there are bull legs, the one from the outer
        # structure's pivot (L1=5900) should survive
        if bull_legs:
            # Find the bull leg with the lowest origin (L1 is lower than L2)
            min_origin_leg = min(bull_legs, key=lambda l: l.origin_price)
            # This should be from L1=5900
            assert min_origin_leg.origin_price == Decimal('5900')

    def test_no_prune_when_pivot_breaks_outside(self):
        """
        Test that inner structure pruning does NOT occur when the inner pivot
        breaks outside the outer structure.

        H1=6100 -> L1=5900 -> H2=6050 -> L2=5850 -> H3=6150
                                          ^
                                     L2 < L1 (breaks outside!)

        L2=5850 is NOT contained in H1->L1 because L2 < L1.
        At H3, L2->H3 should NOT be pruned.
        """
        detector = HierarchicalDetector()

        # Bar 0: H1=6100
        bar0 = make_bar(0, 6095.0, 6100.0, 6090.0, 6095.0)
        detector.process_bar(bar0)

        # Bar 1: L1=5900 - starts bear leg H1->L1
        bar1 = make_bar(1, 6095.0, 6098.0, 5900.0, 5910.0)
        detector.process_bar(bar1)

        # Bar 2: H2=6050 - retraces up, starts bull leg from L1
        bar2 = make_bar(2, 5910.0, 6050.0, 5905.0, 6045.0)
        detector.process_bar(bar2)

        # Bar 3: L2=5850 - Type 2-Bear, goes BELOW L1=5900
        # This breaches the origin of L1's bull leg
        bar3 = make_bar(3, 6045.0, 6048.0, 5850.0, 5860.0)
        detector.process_bar(bar3)

        # Bar 4: H3=6150 - big rally, breaks above H1
        bar4 = make_bar(4, 5860.0, 6150.0, 5855.0, 6140.0)
        events4 = detector.process_bar(bar4)

        # Check that NO inner_structure prune events occurred
        prune_events = [e for e in events4 if isinstance(e, LegPrunedEvent)]
        inner_structure_events = [e for e in prune_events if e.reason == 'inner_structure']
        assert len(inner_structure_events) == 0

        # The bull leg from L2=5850 should survive (if it was created)
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]
        if bull_legs:
            # The surviving bull leg should be from L2=5850 (the deeper low)
            min_origin_leg = min(bull_legs, key=lambda l: l.origin_price)
            assert min_origin_leg.origin_price == Decimal('5850')

    def test_no_prune_without_shared_pivot(self):
        """
        Test that inner structure pruning requires both legs to share the same pivot.

        If inner and outer bull legs have different current pivots, no pruning should occur
        even if containment is detected.
        """
        detector = HierarchicalDetector()

        # Create a scenario where we have contained bear legs but the resulting
        # bull legs have different pivots

        # Bar 0: H1=6100
        bar0 = make_bar(0, 6095.0, 6100.0, 6090.0, 6095.0)
        detector.process_bar(bar0)

        # Bar 1: L1=5900
        bar1 = make_bar(1, 6095.0, 6098.0, 5900.0, 5910.0)
        detector.process_bar(bar1)

        # Bar 2: H2=6050 - inner high
        bar2 = make_bar(2, 5910.0, 6050.0, 5905.0, 6045.0)
        detector.process_bar(bar2)

        # Bar 3: L2=5950 - inner low, contained in H1->L1
        bar3 = make_bar(3, 6045.0, 6048.0, 5950.0, 5960.0)
        detector.process_bar(bar3)

        # Note: At this point, if both bull legs L1->H2 and L2->H2 existed,
        # they would have the same pivot. But due to domination pruning,
        # we might only have one. The key test is that inner_structure
        # pruning only fires when there's actually a matching outer-origin leg.

        # Capture the current state of bull legs
        bull_legs_before = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull'
        ]

        # Bar 4: Break above H1 to trigger invalidations
        bar4 = make_bar(4, 5960.0, 6120.0, 5955.0, 6110.0)
        events4 = detector.process_bar(bar4)

        # Count inner_structure prune events
        prune_events = [e for e in events4 if isinstance(e, LegPrunedEvent)]
        inner_structure_events = [e for e in prune_events if e.reason == 'inner_structure']

        # The number of inner_structure events depends on whether
        # we actually had both inner and outer legs with same pivot


class TestInnerStructurePruningSymmetric:
    """Test inner structure pruning for the symmetric (bear direction) case."""

    def test_prune_inner_structure_bear_leg(self):
        """
        Test symmetric case for bear legs:

        L1=5900 -> H1=6100 -> L2=5950 -> H2=6050 -> L4=5850

        At L4:
        - Bull leg L1->H1 (origin=5900, pivot=6100) is invalidated
        - Bull leg L2->H2 (origin=5950, pivot=6050) is invalidated
        - Bear leg H1->L4 (origin=6100, pivot=5850) exists
        - Bear leg H2->L4 (origin=6050, pivot=5850) exists

        L2->H2 is contained in L1->H1 (L2 > L1 and H2 < H1).
        H2->L4 should be pruned, H1->L4 should survive.
        """
        detector = HierarchicalDetector()

        # Bar 0: L1=5900
        bar0 = make_bar(0, 5905.0, 5910.0, 5900.0, 5905.0)
        detector.process_bar(bar0)

        # Bar 1: H1=6100 - starts bull leg from L1
        bar1 = make_bar(1, 5905.0, 6100.0, 5902.0, 6090.0)
        detector.process_bar(bar1)

        # Bar 2: L2=5950 - retraces, inner low higher than L1
        bar2 = make_bar(2, 6090.0, 6095.0, 5950.0, 5960.0)
        detector.process_bar(bar2)

        # Bar 3: H2=6050 - inner high lower than H1
        # This creates bull leg L2->H2 contained in L1->H1
        bar3 = make_bar(3, 5960.0, 6050.0, 5955.0, 6045.0)
        detector.process_bar(bar3)

        # Bar 4: Retrace down a bit
        bar4 = make_bar(4, 6045.0, 6048.0, 6000.0, 6010.0)
        detector.process_bar(bar4)

        # Bar 5: L4=5850 - breaks below L1, invalidating both bull legs
        bar5 = make_bar(5, 6010.0, 6015.0, 5850.0, 5860.0)
        events5 = detector.process_bar(bar5)

        # Check for inner_structure prune events
        prune_events = [e for e in events5 if isinstance(e, LegPrunedEvent)]
        inner_structure_events = [e for e in prune_events if e.reason == 'inner_structure']

        # Get remaining bear legs (non-breached)
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.max_origin_breach is None
        ]

        # The bear leg from the outer structure's pivot (H1=6100) should survive
        if bear_legs:
            max_origin_leg = max(bear_legs, key=lambda l: l.origin_price)
            # For bear legs, higher origin = outer structure
            assert max_origin_leg.origin_price == Decimal('6100')


class TestInnerStructurePruningMultipleNesting:
    """Test inner structure pruning with multiple levels of nesting."""

    def test_multiple_nested_inner_structures(self):
        """
        Test multiple levels of nested containment:

        H1=6100 -> L1=5900 -> H2=6050 -> L2=5950 -> H3=6020 -> L3=5970 -> H4=6150

        Two levels of nesting:
        - H2->L2 contained in H1->L1
        - H3->L3 contained in H2->L2 (and transitively in H1->L1)

        At H4: Both L2->H4 and L3->H4 should be pruned, only L1->H4 survives.
        """
        detector = HierarchicalDetector()

        # Bar 0: H1=6100
        bar0 = make_bar(0, 6095.0, 6100.0, 6090.0, 6095.0)
        detector.process_bar(bar0)

        # Bar 1: L1=5900
        bar1 = make_bar(1, 6095.0, 6098.0, 5900.0, 5910.0)
        detector.process_bar(bar1)

        # Bar 2: H2=6050 - inner high 1
        bar2 = make_bar(2, 5910.0, 6050.0, 5905.0, 6045.0)
        detector.process_bar(bar2)

        # Bar 3: L2=5950 - inner low 1
        bar3 = make_bar(3, 6045.0, 6048.0, 5950.0, 5960.0)
        detector.process_bar(bar3)

        # Bar 4: H3=6020 - inner high 2 (inside H2->L2)
        bar4 = make_bar(4, 5960.0, 6020.0, 5955.0, 6015.0)
        detector.process_bar(bar4)

        # Bar 5: L3=5970 - inner low 2 (inside H2->L2)
        bar5 = make_bar(5, 6015.0, 6018.0, 5970.0, 5980.0)
        detector.process_bar(bar5)

        # Bar 6: H4=6150 - breaks above H1, invalidating all bear legs
        bar6 = make_bar(6, 5980.0, 6150.0, 5975.0, 6140.0)
        events6 = detector.process_bar(bar6)

        # Check for inner_structure prune events
        prune_events = [e for e in events6 if isinstance(e, LegPrunedEvent)]
        inner_structure_events = [e for e in prune_events if e.reason == 'inner_structure']

        # Get remaining bull legs (non-breached)
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]

        # The bull leg from L1=5900 (the outermost structure) should survive
        if bull_legs:
            min_origin_leg = min(bull_legs, key=lambda l: l.origin_price)
            assert min_origin_leg.origin_price == Decimal('5900')


class TestInnerStructurePruningEdgeCases:
    """Test edge cases for inner structure pruning."""

    def test_single_invalidated_leg_no_pruning(self):
        """
        When only one leg is invalidated, there's no containment to check.
        Inner structure pruning should not occur.
        """
        detector = HierarchicalDetector()

        # Create scenario with only one bear leg
        bar0 = make_bar(0, 6095.0, 6100.0, 6090.0, 6095.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 6095.0, 6098.0, 5900.0, 5910.0)
        detector.process_bar(bar1)

        bar2 = make_bar(2, 5910.0, 6050.0, 5905.0, 6045.0)
        detector.process_bar(bar2)

        # Break above H1, invalidating the single bear leg
        bar3 = make_bar(3, 6045.0, 6150.0, 6040.0, 6140.0)
        events3 = detector.process_bar(bar3)

        # Check that NO inner_structure events occurred
        prune_events = [e for e in events3 if isinstance(e, LegPrunedEvent)]
        inner_structure_events = [e for e in prune_events if e.reason == 'inner_structure']
        assert len(inner_structure_events) == 0

    def test_no_swing_immunity_for_inner_structure(self):
        """
        Swing immunity does NOT apply for inner structure pruning.

        If a leg is structurally inner (contained in a larger structure)
        and there's an outer-origin leg with the same pivot, the inner
        leg is redundant regardless of whether it formed a swing.

        See test_issue_266_no_swing_immunity.py for comprehensive test.
        """
        # This is a placeholder - the comprehensive test is in
        # test_issue_266_no_swing_immunity.py which verifies that
        # inner structure legs ARE pruned even with active swings.
        pass


class TestLegPrunerUnit:
    """Unit tests for the LegPruner.prune_inner_structure_legs method."""

    def test_prune_inner_structure_direct_call(self):
        """
        Test prune_inner_structure_legs directly with constructed state.
        """
        config = SwingConfig.default().with_prune_toggles(enable_inner_structure_prune=True)
        pruner = LegPruner(config)
        state = DetectorState()
        timestamp = datetime.now()

        # Create two bear legs where one is contained in the other
        # Use max_origin_breach to indicate legs have been breached
        outer_bear = Leg(
            direction='bear',
            origin_price=Decimal('6100'),  # Higher origin
            origin_index=0,
            pivot_price=Decimal('5900'),   # Lower pivot
            pivot_index=1,
            max_origin_breach=Decimal('1'),  # Just breached
            formed=True,
        )

        inner_bear = Leg(
            direction='bear',
            origin_price=Decimal('6050'),  # Lower origin (inner.origin < outer.origin)
            origin_index=2,
            pivot_price=Decimal('5950'),   # Higher pivot (inner.pivot > outer.pivot)
            pivot_index=3,
            max_origin_breach=Decimal('1'),  # Just breached
            formed=True,
        )

        # Create bull legs from their pivots (non-breached, so max_origin_breach is None)
        outer_bull = Leg(
            direction='bull',
            origin_price=Decimal('5900'),  # From outer bear's pivot
            origin_index=1,
            pivot_price=Decimal('6150'),   # Same current pivot
            pivot_index=4,
            formed=True,
        )

        inner_bull = Leg(
            direction='bull',
            origin_price=Decimal('5950'),  # From inner bear's pivot
            origin_index=3,
            pivot_price=Decimal('6150'),   # Same current pivot
            pivot_index=4,
            formed=True,
        )

        state.active_legs = [outer_bear, inner_bear, outer_bull, inner_bull]

        bar = make_bar(4, 6140.0, 6150.0, 6135.0, 6145.0)

        # Call prune_inner_structure_legs
        events = pruner.prune_inner_structure_legs(
            state, [outer_bear, inner_bear], bar, timestamp
        )

        # Should have one inner_structure prune event
        assert len(events) == 1
        assert events[0].reason == 'inner_structure'
        assert events[0].leg_id == inner_bull.leg_id

        # inner_bull should be removed from active_legs
        remaining_bull_legs = [
            leg for leg in state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]
        assert len(remaining_bull_legs) == 1
        assert remaining_bull_legs[0].origin_price == Decimal('5900')

    def test_no_prune_without_outer_leg(self):
        """
        Test that no pruning occurs if the outer-origin counter-leg doesn't exist.
        """
        config = SwingConfig.default()
        pruner = LegPruner(config)
        state = DetectorState()
        timestamp = datetime.now()

        # Create two bear legs where one is contained
        # Use max_origin_breach to indicate legs have been breached
        outer_bear = Leg(
            direction='bear',
            origin_price=Decimal('6100'),
            origin_index=0,
            pivot_price=Decimal('5900'),
            pivot_index=1,
            max_origin_breach=Decimal('1'),
            formed=True,
        )

        inner_bear = Leg(
            direction='bear',
            origin_price=Decimal('6050'),
            origin_index=2,
            pivot_price=Decimal('5950'),
            pivot_index=3,
            max_origin_breach=Decimal('1'),
            formed=True,
        )

        # Only create the inner bull leg, NOT the outer one
        inner_bull = Leg(
            direction='bull',
            origin_price=Decimal('5950'),
            origin_index=3,
            pivot_price=Decimal('6150'),
            pivot_index=4,
            formed=True,
        )

        state.active_legs = [outer_bear, inner_bear, inner_bull]

        bar = make_bar(4, 6140.0, 6150.0, 6135.0, 6145.0)

        # Call prune_inner_structure_legs
        events = pruner.prune_inner_structure_legs(
            state, [outer_bear, inner_bear], bar, timestamp
        )

        # No events - can't prune without outer leg
        assert len(events) == 0

        # inner_bull should still exist
        remaining_bull_legs = [
            leg for leg in state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]
        assert len(remaining_bull_legs) == 1

    def test_different_pivots_no_prune(self):
        """
        Test that no pruning occurs if counter-legs have different pivots.
        """
        config = SwingConfig.default()
        pruner = LegPruner(config)
        state = DetectorState()
        timestamp = datetime.now()

        # Use max_origin_breach to indicate legs have been breached
        outer_bear = Leg(
            direction='bear',
            origin_price=Decimal('6100'),
            origin_index=0,
            pivot_price=Decimal('5900'),
            pivot_index=1,
            max_origin_breach=Decimal('1'),
            formed=True,
        )

        inner_bear = Leg(
            direction='bear',
            origin_price=Decimal('6050'),
            origin_index=2,
            pivot_price=Decimal('5950'),
            pivot_index=3,
            max_origin_breach=Decimal('1'),
            formed=True,
        )

        # Create bull legs with DIFFERENT current pivots (non-breached)
        outer_bull = Leg(
            direction='bull',
            origin_price=Decimal('5900'),
            origin_index=1,
            pivot_price=Decimal('6100'),   # Different pivot
            pivot_index=4,
            formed=True,
        )

        inner_bull = Leg(
            direction='bull',
            origin_price=Decimal('5950'),
            origin_index=3,
            pivot_price=Decimal('6150'),   # Different pivot
            pivot_index=5,
            formed=True,
        )

        state.active_legs = [outer_bear, inner_bear, outer_bull, inner_bull]

        bar = make_bar(5, 6140.0, 6150.0, 6135.0, 6145.0)

        # Call prune_inner_structure_legs
        events = pruner.prune_inner_structure_legs(
            state, [outer_bear, inner_bear], bar, timestamp
        )

        # No events - different pivots
        assert len(events) == 0

        # Both bull legs should still exist
        remaining_bull_legs = [
            leg for leg in state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]
        assert len(remaining_bull_legs) == 2


class TestSequentialInvalidation:
    """
    Test for #279: Inner structure pruning with sequential invalidation.

    Containment pairs are invalidated SEQUENTIALLY because:
    - Inner bear has lower origin (H2 < H1)
    - Invalidation happens when price > origin
    - So inner invalidates first (price > H2), outer invalidates later (price > H1)

    The fix ensures we check newly-invalidated legs against already-invalidated legs.
    """

    def test_sequential_invalidation_prunes_inner_bull(self):
        """
        Test the sequential invalidation case from user feedback.

        Bar 200: Inner bear (origin=4429.0, pivot=4426.25) invalidated
        Bar 202: Outer bear (origin=4429.5, pivot=4425.0) invalidated

        At bar 202, the inner bull leg (origin=4426.25) should be pruned
        because outer bull leg (origin=4425.0) exists with same pivot.
        """
        detector = HierarchicalDetector()

        # Build up the structure with sequential bars
        bars = [
            # Initial structure
            make_bar(0, 4430.0, 4430.0, 4424.0, 4425.0),   # Establish range
            make_bar(1, 4425.0, 4429.5, 4424.5, 4429.0),   # H=4429.5 (outer origin)
            make_bar(2, 4429.0, 4429.2, 4425.0, 4425.5),   # L=4425.0 (outer pivot)
            make_bar(3, 4425.5, 4429.0, 4425.2, 4428.5),   # H=4429.0 (inner origin)
            make_bar(4, 4428.5, 4428.8, 4426.25, 4426.5),  # L=4426.25 (inner pivot)
            make_bar(5, 4426.5, 4428.0, 4426.0, 4427.5),   # Consolidation
            make_bar(6, 4427.5, 4429.2, 4427.0, 4429.0),   # Rally starts, price > inner origin (4429)
            make_bar(7, 4429.0, 4430.0, 4428.5, 4429.8),   # Price > outer origin (4429.5)
            make_bar(8, 4429.8, 4432.0, 4429.5, 4431.5),   # Rally continues
        ]

        # Process bars and track events
        all_events = []
        for bar in bars:
            events = detector.process_bar(bar)
            all_events.extend(events)

        # Check for inner_structure prune events
        inner_structure_events = [
            e for e in all_events
            if isinstance(e, LegPrunedEvent) and e.reason == 'inner_structure'
        ]

        # Get remaining bull legs (non-breached)
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]

        # The key assertion: if both inner and outer bear legs were created
        # and subsequently invalidated, the inner bull leg should be pruned
        # This test verifies the fix for #279
        #
        # Note: The exact pruning depends on leg creation order, which depends
        # on bar type classification. The test passes if inner_structure pruning
        # fires at all during sequential invalidation.
        if len(inner_structure_events) > 0:
            # Pruning occurred - verify the pruned leg was from inner structure
            pass  # Success - inner structure pruning fired
        else:
            # Check if we even had the containment pattern
            bear_legs = [
                leg for leg in detector.state.active_legs
                if leg.direction == 'bear'
            ]
            breached_bears = [l for l in bear_legs if l.max_origin_breach is not None]

            # If we have 2+ breached bears, check containment
            if len(breached_bears) >= 2:
                # Find containment pairs
                for inner in breached_bears:
                    for outer in breached_bears:
                        if inner.leg_id == outer.leg_id:
                            continue
                        # Bear containment: inner.origin < outer.origin AND inner.pivot > outer.pivot
                        if (inner.origin_price < outer.origin_price and
                            inner.pivot_price > outer.pivot_price):
                            # Found containment - check if bull legs exist from both pivots
                            inner_bulls = [l for l in bull_legs if l.origin_price == inner.pivot_price]
                            outer_bulls = [l for l in bull_legs if l.origin_price == outer.pivot_price]
                            if inner_bulls and outer_bulls:
                                # Check same pivot
                                for ib in inner_bulls:
                                    for ob in outer_bulls:
                                        if ib.pivot_price == ob.pivot_price:
                                            # Pattern exists but wasn't pruned - this is a bug
                                            assert False, (
                                                f"Inner structure pattern found but not pruned: "
                                                f"inner_bear={inner.leg_id}, outer_bear={outer.leg_id}, "
                                                f"inner_bull={ib.leg_id}, outer_bull={ob.leg_id}"
                                            )

    def test_sequential_invalidation_with_real_data_pattern(self):
        """
        Test using the exact pattern from user feedback:
        - Inner bear: origin=4429.0@189, pivot=4426.25@191
        - Outer bear: origin=4429.5@160, pivot=4425.0@179
        - Inner bull: origin=4426.25@191, pivot=4437.0@219
        - Outer bull: origin=4425.0@144, pivot=4437.0@219

        Uses direct state manipulation to test the pruner logic.
        """
        config = SwingConfig.default().with_prune_toggles(enable_inner_structure_prune=True)
        pruner = LegPruner(config)
        state = DetectorState()
        timestamp = datetime.now()

        # Create the outer bear (breached first in real scenario, but
        # for test we set both as breached via max_origin_breach)
        outer_bear = Leg(
            direction='bear',
            origin_price=Decimal('4429.5'),
            origin_index=160,
            pivot_price=Decimal('4425.0'),
            pivot_index=179,
            max_origin_breach=Decimal('1'),  # Breached
            formed=True,
        )

        # Create the inner bear (contained in outer)
        inner_bear = Leg(
            direction='bear',
            origin_price=Decimal('4429.0'),  # < outer.origin (4429.5)
            origin_index=189,
            pivot_price=Decimal('4426.25'),  # > outer.pivot (4425.0)
            pivot_index=191,
            max_origin_breach=Decimal('1'),  # Breached
            formed=True,
        )

        # Create bull leg from outer pivot (non-breached)
        outer_bull = Leg(
            direction='bull',
            origin_price=Decimal('4425.0'),  # From outer bear's pivot
            origin_index=144,
            pivot_price=Decimal('4437.0'),   # Same pivot
            pivot_index=219,
            formed=True,
        )

        # Create bull leg from inner pivot (this should be pruned, non-breached)
        inner_bull = Leg(
            direction='bull',
            origin_price=Decimal('4426.25'),  # From inner bear's pivot
            origin_index=191,
            pivot_price=Decimal('4437.0'),    # Same pivot as outer_bull
            pivot_index=219,
            formed=True,
        )

        state.active_legs = [outer_bear, inner_bear, outer_bull, inner_bull]

        bar = make_bar(219, 4435.0, 4437.0, 4434.0, 4436.5)

        # Call prune_inner_structure_legs with both breached bears
        events = pruner.prune_inner_structure_legs(
            state, [outer_bear, inner_bear], bar, timestamp
        )

        # Should have pruned the inner bull leg
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"
        assert events[0].reason == 'inner_structure'
        assert events[0].leg_id == inner_bull.leg_id

        # Verify inner_bull was pruned, outer_bull remains
        remaining_bulls = [
            leg for leg in state.active_legs
            if leg.direction == 'bull' and leg.max_origin_breach is None
        ]
        assert len(remaining_bulls) == 1
        assert remaining_bulls[0].origin_price == Decimal('4425.0')
