"""
Tests for issue #281: Implement leg hierarchy (parent-child relationships).

Tests cover:
- Parent assignment for bull and bear legs
- Root leg (no eligible parent)
- Price tie tiebreaker (latest origin_index wins)
- Breach filtering (origin-breached legs cannot be parents)
- Reparenting when parent is pruned
- Sibling scenario (same price level legs)
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.dag import LegDetector, DetectorState, Leg
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.types import Bar


def make_bar(index: int, o: float, h: float, l: float, c: float, ts: int = 0) -> Bar:
    """Create a test bar."""
    return Bar(
        index=index,
        timestamp=ts or (1000000 + index * 60),
        open=o,
        high=h,
        low=l,
        close=c,
    )


class TestFindParentForLeg:
    """Test _find_parent_for_leg() method."""

    def test_root_leg_bull_no_eligible_parent(self):
        """New leg with lowest origin in direction → parent_leg_id = None."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create first bull leg - should be root (no parent)
        bars = [
            make_bar(0, 100, 105, 95, 100),
            make_bar(1, 100, 110, 98, 108),  # HH, HL = Type 2-Bull
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check the bull leg has no parent
        bull_legs = [l for l in detector.state.active_legs if l.direction == 'bull']
        assert len(bull_legs) == 1
        assert bull_legs[0].parent_leg_id is None  # Root leg

    def test_root_leg_bear_no_eligible_parent(self):
        """New leg with highest origin in direction → parent_leg_id = None."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create first bear leg - should be root (no parent)
        bars = [
            make_bar(0, 100, 105, 95, 100),
            make_bar(1, 100, 102, 90, 92),  # LH, LL = Type 2-Bear
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check the bear leg has no parent
        bear_legs = [l for l in detector.state.active_legs if l.direction == 'bear']
        assert len(bear_legs) == 1
        assert bear_legs[0].parent_leg_id is None  # Root leg

    def test_bull_leg_finds_parent_with_lower_origin(self):
        """Bull leg with higher origin should have parent with lower origin."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Manually create a parent bull leg
        parent_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
        )
        detector.state.active_legs.append(parent_leg)

        # Test _find_parent_for_leg directly
        # For a bull leg at origin=95, parent should be the leg at origin=90
        parent_id = detector._find_parent_for_leg('bull', Decimal("95"), 5)

        assert parent_id == parent_leg.leg_id

    def test_bear_leg_finds_parent_with_higher_origin(self):
        """Bear leg with lower origin should have parent with higher origin."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Manually create a parent bear leg
        parent_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
        )
        detector.state.active_legs.append(parent_leg)

        # Test _find_parent_for_leg directly
        # For a bear leg at origin=105, parent should be the leg at origin=110
        parent_id = detector._find_parent_for_leg('bear', Decimal("105"), 5)

        assert parent_id == parent_leg.leg_id

    def test_price_tie_selects_latest_origin_index(self):
        """When multiple legs have same origin price, select latest origin_index."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create two legs at same origin price but different times
        leg1 = Leg(
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
        )
        leg2 = Leg(
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=2,  # Later time
            pivot_price=Decimal("100"),
            pivot_index=3,
        )
        detector.state.active_legs.append(leg1)
        detector.state.active_legs.append(leg2)

        # Find parent for a new leg with origin at 95
        parent_id = detector._find_parent_for_leg('bull', Decimal("95"), 5)

        # Should select leg2 (later origin_index)
        assert parent_id == leg2.leg_id

    def test_breach_filtering_excludes_origin_breached_legs(self):
        """Legs with origin_breached=True cannot be parents."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create a breached leg (should be excluded)
        breached_leg = Leg(
            direction='bull',
            origin_price=Decimal("85"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            max_origin_breach=Decimal("5"),  # Origin was breached
        )
        # Create a non-breached leg
        non_breached_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
        )
        detector.state.active_legs.append(breached_leg)
        detector.state.active_legs.append(non_breached_leg)

        # Find parent for a new leg with origin at 95
        parent_id = detector._find_parent_for_leg('bull', Decimal("95"), 5)

        # Should select non_breached_leg (breached one is excluded)
        assert parent_id == non_breached_leg.leg_id

    def test_breach_filtering_returns_none_if_all_breached(self):
        """If all potential parents are breached, return None."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create only breached legs
        breached_leg = Leg(
            direction='bull',
            origin_price=Decimal("85"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            max_origin_breach=Decimal("5"),
        )
        detector.state.active_legs.append(breached_leg)

        # Find parent - should return None
        parent_id = detector._find_parent_for_leg('bull', Decimal("95"), 5)
        assert parent_id is None


class TestReparentChildren:
    """Test _reparent_children() method."""

    def test_reparent_to_grandparent(self):
        """When L5 is pruned, L6.parent should become L4."""
        config = SwingConfig.default()
        pruner = LegPruner(config)
        state = DetectorState()

        # Create chain: L4 (root) -> L5 -> L6
        L4 = Leg(
            leg_id="L4",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            parent_leg_id=None,  # Root
        )
        L5 = Leg(
            leg_id="L5",
            direction='bull',
            origin_price=Decimal("95"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            parent_leg_id="L4",
        )
        L6 = Leg(
            leg_id="L6",
            direction='bull',
            origin_price=Decimal("98"),
            origin_index=4,
            pivot_price=Decimal("110"),
            pivot_index=5,
            parent_leg_id="L5",
        )
        state.active_legs = [L4, L5, L6]

        # Reparent when L5 is pruned
        pruner.reparent_children(state, L5)

        # L6 should now point to L4
        assert L6.parent_leg_id == "L4"
        # L4 should remain root
        assert L4.parent_leg_id is None
        # L5 parent unchanged (it's being pruned anyway)
        assert L5.parent_leg_id == "L4"

    def test_reparent_to_none_when_root_pruned(self):
        """When root L4 is pruned, L5.parent becomes None."""
        config = SwingConfig.default()
        pruner = LegPruner(config)
        state = DetectorState()

        # Create chain: L4 (root) -> L5
        L4 = Leg(
            leg_id="L4",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            parent_leg_id=None,  # Root
        )
        L5 = Leg(
            leg_id="L5",
            direction='bull',
            origin_price=Decimal("95"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            parent_leg_id="L4",
        )
        state.active_legs = [L4, L5]

        # Reparent when L4 is pruned
        pruner.reparent_children(state, L4)

        # L5 should now be root (parent = None)
        assert L5.parent_leg_id is None

    def test_cascade_prune_reparents_correctly(self):
        """When L4 and L5 both pruned, L6 ends up as root."""
        config = SwingConfig.default()
        pruner = LegPruner(config)
        state = DetectorState()

        # Create chain: L4 (root) -> L5 -> L6
        L4 = Leg(
            leg_id="L4",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            parent_leg_id=None,
        )
        L5 = Leg(
            leg_id="L5",
            direction='bull',
            origin_price=Decimal("95"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            parent_leg_id="L4",
        )
        L6 = Leg(
            leg_id="L6",
            direction='bull',
            origin_price=Decimal("98"),
            origin_index=4,
            pivot_price=Decimal("110"),
            pivot_index=5,
            parent_leg_id="L5",
        )
        state.active_legs = [L4, L5, L6]

        # Prune L4 first
        pruner.reparent_children(state, L4)
        # L5 should point to None
        assert L5.parent_leg_id is None

        # Then prune L5
        pruner.reparent_children(state, L5)
        # L6 should point to None (L5's former parent)
        assert L6.parent_leg_id is None


class TestSiblingScenario:
    """Test sibling legs at same price level."""

    def test_siblings_share_same_parent(self):
        """Two legs at same origin price (different times) share the same parent."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create grandparent leg
        grandparent = Leg(
            leg_id="grandparent",
            direction='bull',
            origin_price=Decimal("85"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
        )
        detector.state.active_legs.append(grandparent)

        # Create sibling 1
        sibling1 = Leg(
            leg_id="sibling1",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
        )
        # Manually set parent
        sibling1.parent_leg_id = detector._find_parent_for_leg('bull', Decimal("90"), 2)
        detector.state.active_legs.append(sibling1)

        # Create sibling 2 at same price but later time
        sibling2 = Leg(
            leg_id="sibling2",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=4,  # Later time
            pivot_price=Decimal("108"),
            pivot_index=5,
        )
        sibling2.parent_leg_id = detector._find_parent_for_leg('bull', Decimal("90"), 4)

        # Both siblings should have grandparent as parent
        assert sibling1.parent_leg_id == "grandparent"
        assert sibling2.parent_leg_id == "grandparent"

    def test_legs_at_same_price_are_not_parents_of_each_other(self):
        """Legs at same origin price level are NOT parents of each other."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create first leg at price 90
        leg1 = Leg(
            leg_id="leg1",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
        )
        detector.state.active_legs.append(leg1)

        # Try to find parent for leg at same price but later time
        parent_id = detector._find_parent_for_leg('bull', Decimal("90"), 2)

        # Should NOT find leg1 as parent (same price, not lower)
        assert parent_id is None


class TestIntegration:
    """Integration tests for hierarchy in full detector flow."""

    def test_hierarchy_through_multiple_bars(self):
        """Test hierarchy builds correctly through multiple bars."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create ascending bull structure: L1 (90) -> L2 (95) -> L3 (98)
        bars = [
            make_bar(0, 100, 105, 90, 100),   # Initialize with low at 90
            make_bar(1, 100, 110, 92, 108),   # Type 2-Bull, creates leg from 90
            make_bar(2, 108, 112, 95, 110),   # New low at 95
            make_bar(3, 110, 118, 96, 116),   # Type 2-Bull, creates leg from 95
            make_bar(4, 116, 120, 98, 118),   # New low at 98
            make_bar(5, 118, 125, 99, 123),   # Type 2-Bull, creates leg from 98
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Get bull legs ordered by origin
        bull_legs = sorted(
            [l for l in detector.state.active_legs if l.direction == 'bull'],
            key=lambda l: l.origin_price
        )

        # Verify hierarchy if multiple legs exist
        # Note: Due to domination pruning, not all legs may survive
        # At minimum, verify the structure is consistent
        for leg in bull_legs:
            if leg.parent_leg_id is not None:
                # Parent should have lower origin price
                parent = next(
                    (l for l in bull_legs if l.leg_id == leg.parent_leg_id), None
                )
                if parent:
                    assert parent.origin_price < leg.origin_price

    def test_bear_hierarchy_through_multiple_bars(self):
        """Test bear hierarchy builds correctly through multiple bars."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create descending bear structure
        bars = [
            make_bar(0, 100, 110, 95, 100),   # Initialize with high at 110
            make_bar(1, 100, 108, 88, 90),    # Type 2-Bear, creates leg from 110
            make_bar(2, 90, 105, 85, 100),    # New high at 105
            make_bar(3, 100, 103, 80, 82),    # Type 2-Bear, creates leg from 105
            make_bar(4, 82, 100, 78, 95),     # New high at 100
            make_bar(5, 95, 98, 72, 75),      # Type 2-Bear, creates leg from 100
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Get bear legs ordered by origin (descending)
        bear_legs = sorted(
            [l for l in detector.state.active_legs if l.direction == 'bear'],
            key=lambda l: l.origin_price,
            reverse=True
        )

        # Verify hierarchy if multiple legs exist
        for leg in bear_legs:
            if leg.parent_leg_id is not None:
                # Parent should have higher origin price
                parent = next(
                    (l for l in bear_legs if l.leg_id == leg.parent_leg_id), None
                )
                if parent:
                    assert parent.origin_price > leg.origin_price


class TestEdgeCases:
    """Test edge cases from issue specification."""

    def test_out_of_order_creation(self):
        """L2's parent reflects state at creation time, L3's parent unchanged."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create L1 first
        L1 = Leg(
            leg_id="L1",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
        )
        detector.state.active_legs.append(L1)

        # Create L3 with higher origin - parent is L1
        L3 = Leg(
            leg_id="L3",
            direction='bull',
            origin_price=Decimal("98"),
            origin_index=4,
            pivot_price=Decimal("108"),
            pivot_index=5,
        )
        L3.parent_leg_id = detector._find_parent_for_leg('bull', Decimal("98"), 4)
        detector.state.active_legs.append(L3)

        assert L3.parent_leg_id == "L1"

        # Now create L2 with origin between L1 and L3
        L2 = Leg(
            leg_id="L2",
            direction='bull',
            origin_price=Decimal("95"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
        )
        L2.parent_leg_id = detector._find_parent_for_leg('bull', Decimal("95"), 2)
        detector.state.active_legs.append(L2)

        # L2's parent should be L1 (based on state at creation)
        assert L2.parent_leg_id == "L1"
        # L3's parent unchanged
        assert L3.parent_leg_id == "L1"

    def test_only_active_legs_are_eligible_parents(self):
        """Invalidated legs cannot be parents."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create invalidated leg
        invalidated_leg = Leg(
            leg_id="invalidated",
            direction='bull',
            origin_price=Decimal("90"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            status='invalidated',
        )
        detector.state.active_legs.append(invalidated_leg)

        # Try to find parent
        parent_id = detector._find_parent_for_leg('bull', Decimal("95"), 5)

        # Should NOT find invalidated leg
        assert parent_id is None

    def test_only_earlier_legs_are_eligible_parents(self):
        """Only legs with earlier origin_index can be parents."""
        config = SwingConfig.default()
        detector = LegDetector(config)

        # Create leg with later origin_index
        later_leg = Leg(
            leg_id="later",
            direction='bull',
            origin_price=Decimal("85"),
            origin_index=10,  # Later than what we'll search for
            pivot_price=Decimal("100"),
            pivot_index=11,
        )
        detector.state.active_legs.append(later_leg)

        # Try to find parent for leg at index 5
        parent_id = detector._find_parent_for_leg('bull', Decimal("90"), 5)

        # Should NOT find later_leg (origin_index > search origin_index)
        assert parent_id is None
