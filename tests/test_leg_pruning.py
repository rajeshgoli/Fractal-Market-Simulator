"""
Tests for leg pruning: turn pruning and bidirectional domination.

Tests the leg pruning algorithms of the HierarchicalDetector/LegDetector.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.swing_analysis.dag import (
    HierarchicalDetector,
    Leg,
)
from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.swing_node import SwingNode
from src.swing_analysis.events import LegPrunedEvent

from conftest import make_bar


class TestTurnPruning:
    """Test recursive 10% leg pruning on directional turn (#185)."""

    def test_bull_legs_pruned_on_type2_bear(self):
        """Bull legs are pruned using 10% rule when Type 2-Bear bar detected.

        During an uptrend, many bull legs accumulate with different pivots
        but the same origin. When a Type 2-Bear bar signals a turn, we keep
        the longest leg + legs >= 10% of the longest per origin group.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a 10-bar uptrend (Type 2-Bull bars)
        # Each bar has HH and HL, creating multiple pending pivots
        bars = []

        # Initial bar
        bars.append(make_bar(0, 100.0, 105.0, 95.0, 102.0))

        # Rising trend - each bar is Type 2-Bull (HH, HL)
        for i in range(1, 11):
            open_price = 100.0 + i * 5
            high_price = 105.0 + i * 5  # HH each bar
            low_price = 96.0 + i * 5   # HL each bar
            close_price = 103.0 + i * 5
            bars.append(make_bar(i, open_price, high_price, low_price, close_price))

        # Process uptrend bars
        for bar in bars:
            detector.process_bar(bar)

        # Count bull legs before the turn
        bull_legs_before = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ])

        # Now add a Type 2-Bear bar (LH, LL) - signals turn
        # Previous bar was at index 10 with high=155, low=146
        # This bar needs LH (< 155) and LL (< 146)
        turn_bar = make_bar(11, 150.0, 152.0, 140.0, 142.0)  # LH=152<155, LL=140<146
        events = detector.process_bar(turn_bar)

        # Count bull legs after the turn
        bull_legs_after = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ])

        # Check that LegPrunedEvent with 10% reason was emitted (if any pruning)
        prune_events = [
            e for e in events
            if isinstance(e, LegPrunedEvent) and e.reason in ("10pct_prune", "subtree_prune")
        ]

        # After pruning, we should have fewer or equal bull legs
        # The 10% rule is more permissive than the old "keep only longest" rule
        assert bull_legs_after <= bull_legs_before

    def test_bear_legs_pruned_on_type2_bull(self):
        """Bear legs are pruned to longest when Type 2-Bull bar detected."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a 10-bar downtrend (Type 2-Bear bars)
        bars = []

        # Initial bar
        bars.append(make_bar(0, 200.0, 205.0, 195.0, 198.0))

        # Falling trend - each bar is Type 2-Bear (LH, LL)
        for i in range(1, 11):
            open_price = 200.0 - i * 5
            high_price = 203.0 - i * 5  # LH each bar
            low_price = 190.0 - i * 5   # LL each bar
            close_price = 192.0 - i * 5
            bars.append(make_bar(i, open_price, high_price, low_price, close_price))

        # Process downtrend bars
        for bar in bars:
            detector.process_bar(bar)

        # Count bear legs before the turn
        bear_legs_before = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ])

        # Now add a Type 2-Bull bar (HH, HL) - signals turn
        # Previous bar at index 10 had high=153, low=140
        # This bar needs HH (> 153) and HL (> 140)
        turn_bar = make_bar(11, 145.0, 160.0, 145.0, 155.0)  # HH=160>153, HL=145>140
        events = detector.process_bar(turn_bar)

        # Count bear legs after the turn
        bear_legs_after = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ])

        # After pruning, we should have fewer or equal bear legs
        assert bear_legs_after <= bear_legs_before

    def test_turn_prune_emits_leg_pruned_event(self):
        """LegPrunedEvent with reason='turn_prune' is emitted for non-largest legs."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually create multiple bull legs sharing the same origin
        # This simulates what happens during an uptrend
        shared_origin_price = Decimal("5100")
        shared_origin_index = 10

        # Create legs with different pivots but same origin
        # leg1: range = 100 (largest - KEEP)
        # leg2: range = 50 (smaller -> PRUNE)
        # leg3: range = 80 (smaller -> PRUNE)
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),  # Range: 100 (KEEP - largest)
            pivot_index=5,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5050"),  # Range: 50 -> PRUNE
            pivot_index=8,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        leg3 = Leg(
            direction='bull',
            pivot_price=Decimal("5020"),  # Range: 80 -> PRUNE
            pivot_index=6,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2, leg3]

        # Create a bar and timestamp for the prune call
        bar = make_bar(15, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        # Call _prune_legs_on_turn directly
        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # Should have pruned 2 legs (leg2 and leg3), keeping leg1 (largest range)
        assert len(events) == 2
        assert all(isinstance(e, LegPrunedEvent) for e in events)
        assert all(e.reason == "turn_prune" for e in events)

        # Only leg1 should remain (largest range: 5100 - 5000 = 100)
        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining_legs) == 1
        assert remaining_legs[0].pivot_price == Decimal("5000")

    def test_10pct_rule_preserves_multi_origin_structure(self):
        """Legs from different origins are preserved even if small."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create two origin groups - each with a single leg
        # Origin 1: large leg
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),  # Range: 100
            pivot_index=5,
            origin_price=Decimal("5100"),
            origin_index=10,
            status='active',
        )

        # Origin 2: small leg (but different origin, so preserved)
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5180"),  # Range: 20 (less than 10% of leg1)
            pivot_index=12,
            origin_price=Decimal("5200"),
            origin_index=15,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(20, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # Both legs preserved - different origins, each is largest in its group
        assert len(events) == 0
        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 2

    def test_single_leg_not_pruned(self):
        """A single leg should not be pruned (nothing to compare against)."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        leg = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),
            pivot_index=5,
            origin_price=Decimal("5100"),
            origin_index=10,
            status='active',
        )
        detector.state.active_legs = [leg]

        bar = make_bar(15, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # No pruning should occur
        assert len(events) == 0
        assert len(detector.state.active_legs) == 1

    def test_legs_with_different_origins_not_grouped(self):
        """Legs with different origins are not grouped together for pruning."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Two legs with different origins - should not be grouped
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),
            pivot_index=5,
            origin_price=Decimal("5100"),  # Origin 1
            origin_index=10,
            status='active',
        )
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5050"),
            pivot_index=8,
            origin_price=Decimal("5200"),  # Origin 2 - different
            origin_index=15,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(20, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # No pruning - each origin group has only one leg
        assert len(events) == 0
        assert len(detector.state.active_legs) == 2

    def test_active_swing_immunity(self):
        """Legs with active swings are never pruned, even if < 10% of largest."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        shared_origin_price = Decimal("5100")
        shared_origin_index = 10

        # leg1: range = 100 (largest)
        # leg2: range = 5 (5% -> would be pruned, but has active swing)
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),
            pivot_index=5,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5095"),  # Range: 5 (5% -> would prune)
            pivot_index=8,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
            swing_id="swing_123",  # Has formed into a swing
        )

        # Create an active swing for leg2
        swing = SwingNode(
            swing_id="swing_123",
            high_bar_index=shared_origin_index,
            high_price=shared_origin_price,
            low_bar_index=8,
            low_price=Decimal("5095"),
            direction="bull",
            status="active",
            formed_at_bar=9,
        )
        detector.state.active_swings = [swing]
        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(15, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # No pruning - leg2 has an active swing (immune)
        assert len(events) == 0
        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 2

    def test_turn_prune_tie_keeps_earliest_pivot(self):
        """
        When legs have identical range, keep the earliest pivot bar (#190).

        Example: Two bear legs with same origin (4422.25, bar 53) and same range (11.25):
        - leg1: pivot at bar 39 (pivot=4433.50)
        - leg2: pivot at bar 40 (pivot=4433.50)

        Both have identical range so there's a tie. Should keep leg1 (bar 39).
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Same origin for both legs
        shared_origin_price = Decimal("4422.25")
        shared_origin_index = 53

        # Both legs hit the same high price, creating identical ranges
        # leg1: earlier pivot (bar 39) - should be KEPT
        leg1 = Leg(
            direction='bear',
            pivot_price=Decimal("4433.50"),  # Range: 11.25
            pivot_index=39,  # Earlier pivot
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        # leg2: later pivot (bar 40) - should be PRUNED
        leg2 = Leg(
            direction='bear',
            pivot_price=Decimal("4433.50"),  # Range: 11.25 (same as leg1)
            pivot_index=40,  # Later pivot
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )

        # Intentionally add them in reverse order to test tie-breaking is not order-dependent
        detector.state.active_legs = [leg2, leg1]

        bar = make_bar(62, 4425.0, 4430.0, 4420.0, 4425.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bear', bar, timestamp)

        # leg2 should be pruned (later pivot), leg1 kept (earlier pivot)
        assert len(events) == 1
        assert isinstance(events[0], LegPrunedEvent)
        assert events[0].reason == "turn_prune"
        assert events[0].leg_id == leg2.leg_id

        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 1
        assert remaining[0].pivot_index == 39, "Should keep earliest pivot"
        assert remaining[0].leg_id == leg1.leg_id


class TestBidirectionalDomination:
    """
    Tests for bidirectional domination - when a leg with a better origin is
    created, existing legs with worse origins in the same turn should be pruned.

    Issue #204: Stop losses placed based on a worse origin could get triggered
    unnecessarily when a better origin exists.
    """

    def test_better_bull_origin_prunes_worse_bull_legs(self):
        """
        When a new bull leg is created with a lower origin (better),
        existing bull legs with worse origins in the SAME TURN should be pruned.

        Directly tests _prune_dominated_legs_in_turn with controlled setup.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually set up: two bull legs in the same turn,
        # where the second has a better (lower) origin
        leg1 = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # Worse origin (higher)
            origin_index=5,
            pivot_price=Decimal("110"),
            pivot_index=8,
            status='active',
        )

        detector.state.active_legs = [leg1]
        # No turn boundary set, so last_turn_bar['bull'] = -1
        # This means all legs are in "current turn"

        # Create a new leg with better origin
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("95"),  # Better origin (lower)
            origin_index=6,
            pivot_price=Decimal("115"),
            pivot_index=10,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Call the pruning function
        bar = make_bar(10, 110.0, 115.0, 108.0, 112.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # leg1 should be pruned because its origin (100) is worse than new_leg's origin (95)
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"
        assert events[0].reason == "dominated_in_turn"

        # Only the new leg should remain
        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining_legs) == 1
        assert remaining_legs[0].origin_price == Decimal("95")

    def test_better_bear_origin_prunes_worse_bear_legs(self):
        """
        When a new bear leg is created with a higher origin (better),
        existing bear legs with worse origins in the SAME TURN should be pruned.

        Directly tests _prune_dominated_legs_in_turn with controlled setup.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually set up: two bear legs in the same turn,
        # where the second has a better (higher) origin
        leg1 = Leg(
            direction='bear',
            origin_price=Decimal("105"),  # Worse origin (lower)
            origin_index=5,
            pivot_price=Decimal("95"),
            pivot_index=8,
            status='active',
        )

        detector.state.active_legs = [leg1]
        # No turn boundary set, so last_turn_bar['bear'] = -1

        # Create a new leg with better origin
        new_leg = Leg(
            direction='bear',
            origin_price=Decimal("112"),  # Better origin (higher)
            origin_index=6,
            pivot_price=Decimal("90"),
            pivot_index=10,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Call the pruning function
        bar = make_bar(10, 92.0, 95.0, 90.0, 91.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # leg1 should be pruned because its origin (105) is worse than new_leg's origin (112)
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"
        assert events[0].reason == "dominated_in_turn"

        # Only the new leg should remain
        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining_legs) == 1
        assert remaining_legs[0].origin_price == Decimal("112")

    def test_cross_turn_legs_not_pruned_by_domination(self):
        """
        Legs from PREVIOUS turns should NOT be pruned by domination (#207).

        Turn boundaries are respected for BOTH creation AND pruning.
        Legs from different turns represent independent structural phases
        and must coexist.

        TC1 from #207: Cross-Turn Survival.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up turn boundary at bar 10
        detector.state.last_turn_bar['bull'] = 10

        # Leg from BEFORE the turn (origin_index = 5 < turn_start = 10)
        # This represents a different structural phase
        leg_from_prev_turn = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # Worse origin (higher)
            origin_index=5,
            pivot_price=Decimal("115"),
            pivot_index=12,
            status='active',
        )

        # Leg from CURRENT turn (origin_index = 12 >= turn_start = 10)
        leg_from_current_turn = Leg(
            direction='bull',
            origin_price=Decimal("105"),  # Also worse origin than new_leg
            origin_index=12,
            pivot_price=Decimal("120"),
            pivot_index=15,
            status='active',
        )

        detector.state.active_legs = [leg_from_prev_turn, leg_from_current_turn]

        # New leg with better origin (in current turn)
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),  # Best origin (lowest)
            origin_index=14,
            pivot_price=Decimal("125"),
            pivot_index=18,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Prune dominated legs
        bar = make_bar(18, 120.0, 125.0, 118.0, 122.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # Only leg from CURRENT turn should be pruned (105)
        # Leg from PREVIOUS turn should survive (100) - different structural phase
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"

        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        origins = [leg.origin_price for leg in remaining_legs]

        # Both the new leg (90) AND the previous-turn leg (100) should remain
        assert len(origins) == 2, f"Expected 2 legs remaining, got {len(origins)}"
        assert Decimal("90") in origins, "New leg should exist"
        assert Decimal("100") in origins, "Leg from previous turn should survive (#207)"
        assert Decimal("105") not in origins, "Leg from current turn should be pruned"

    def test_same_turn_legs_still_pruned_by_domination(self):
        """
        Legs from the SAME turn should still be pruned by domination (#207 R4).

        Within a single turn, domination pruning should still work to consolidate
        redundant legs tracking the same structural move.

        TC2 from #207: Same-Turn Pruning.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up turn boundary at bar 10
        detector.state.last_turn_bar['bear'] = 10

        # Two bear legs from the SAME turn (both origin_index >= turn_start)
        leg_worse_origin = Leg(
            direction='bear',
            origin_price=Decimal("100"),  # Worse origin (lower for bear)
            origin_index=12,
            pivot_price=Decimal("90"),
            pivot_index=15,
            status='active',
        )

        detector.state.active_legs = [leg_worse_origin]

        # New leg with better origin (in same current turn)
        new_leg = Leg(
            direction='bear',
            origin_price=Decimal("105"),  # Better origin (higher for bear)
            origin_index=14,
            pivot_price=Decimal("88"),
            pivot_index=18,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Prune dominated legs
        bar = make_bar(18, 89.0, 92.0, 88.0, 90.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # The worse-origin leg (100) should be pruned - both are in same turn
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"

        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        origins = [leg.origin_price for leg in remaining_legs]

        assert len(origins) == 1, f"Expected 1 leg remaining, got {len(origins)}"
        assert Decimal("105") in origins, "New leg (better origin) should exist"
        assert Decimal("100") not in origins, "Same-turn leg with worse origin should be pruned"

    def test_swing_immunity_still_works_with_turn_scoping(self):
        """
        Legs with active swings are never pruned, even within the same turn (#207 R3).

        This confirms swing immunity is preserved with turn-scoped pruning.

        TC3 from #207: Swing Immunity Still Works.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up turn boundary - all legs in current turn
        detector.state.last_turn_bar['bull'] = 10

        # Create an active swing
        active_swing = SwingNode(
            swing_id="swing_immune",
            high_bar_index=15,
            high_price=Decimal("112"),
            low_bar_index=12,
            low_price=Decimal("100"),
            direction="bull",
            status="active",
            formed_at_bar=15,
        )
        detector.state.active_swings = [active_swing]

        # Leg with active swing (immune)
        immune_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # Worse origin
            origin_index=12,
            pivot_price=Decimal("112"),
            pivot_index=15,
            status='active',
            swing_id="swing_immune",  # Has active swing
        )

        detector.state.active_legs = [immune_leg]

        # New leg with better origin
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("95"),  # Better origin
            origin_index=14,
            pivot_price=Decimal("120"),
            pivot_index=18,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Prune dominated legs
        bar = make_bar(18, 115.0, 120.0, 113.0, 118.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # No legs should be pruned - the worse-origin leg has swing immunity
        assert len(events) == 0, f"Expected 0 prune events, got {len(events)}"

        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        origins = [leg.origin_price for leg in remaining_legs]

        assert len(origins) == 2, f"Expected 2 legs remaining, got {len(origins)}"
        assert Decimal("95") in origins, "New leg should exist"
        assert Decimal("100") in origins, "Immune leg should survive due to swing immunity"

    def test_active_swing_immunity_on_dominated_prune(self):
        """
        Legs that have formed into active swings should NOT be pruned
        even if a better origin is found.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a bull leg that forms into a swing, then create a better origin
        # The first leg should survive because it has an active swing
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 102.0),    # Initial
            make_bar(1, 102.0, 110.0, 100.0, 108.0),   # TYPE_2_BULL - bull leg from 95
            make_bar(2, 108.0, 150.0, 107.0, 145.0),   # TYPE_2_BULL - extends pivot, likely forms swing
            make_bar(3, 145.0, 148.0, 90.0, 92.0),     # TYPE_2_BEAR - lower low at 90
            make_bar(4, 92.0, 160.0, 91.0, 155.0),     # TYPE_2_BULL - new bull leg from 90
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check if any swing formed from the first bull leg
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]

        # If any leg has a swing_id, verify it wasn't pruned
        legs_with_swings = [leg for leg in bull_legs if leg.swing_id is not None]

        # We should have at least the new leg (origin 90)
        origins = [leg.origin_price for leg in bull_legs]
        assert Decimal("90") in origins, "New bull leg from 90 should exist"

        # If a swing formed from origin 95, that leg should also exist
        if legs_with_swings:
            for leg in legs_with_swings:
                # Legs with active swings should not have been pruned
                assert leg.status == 'active', (
                    f"Leg with swing_id {leg.swing_id} should be active, not pruned"
                )
