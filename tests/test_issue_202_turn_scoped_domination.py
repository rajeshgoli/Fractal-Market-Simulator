"""
Test for issue #202: Dominated leg check applied across turns instead of within turn.

The dominated leg optimization (#194) and pending origin tracking (#200) should only
apply within a single turn, not across turns. After a directional reversal, new legs
should be created even if a leg from the previous turn has a "better" origin.

This allows nested subtrees to form after directional reversals.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.dag import HierarchicalDetector, Leg
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


class TestTurnScopedDomination:
    """Test that domination checks are scoped to the current turn."""

    def test_bull_leg_created_after_bear_turn_despite_better_previous_origin(self):
        """
        After a bear turn, a new bull leg should be created even if a bull leg
        from the previous turn has a better (lower) origin.

        Scenario:
        - Bars 0-2: Bull turn, creates bull leg with origin=90
        - Bars 3-4: Bear turn (price retraces)
        - Bars 5+: New bull turn from local low at 93

        Expected: New bull leg from 93 is created, even though 90 < 93.
        The old leg from 90 is from a previous turn and shouldn't dominate.
        """
        detector = HierarchicalDetector()

        # === Bull turn: Bars 0-2 ===
        # Bar 0: Initial bar
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 98.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH=105>100, HL=92>90) - creates bull leg from 90
        bar1 = make_bar(1, 98.0, 105.0, 92.0, 103.0)
        detector.process_bar(bar1)

        # Bar 2: Type 2-Bull continues (HH=110>105, HL=95>92) - extends pivot
        bar2 = make_bar(2, 103.0, 110.0, 95.0, 108.0)
        detector.process_bar(bar2)

        # Verify bull leg exists with origin at 90
        bull_legs_after_bull_turn = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs_after_bull_turn) >= 1
        assert any(leg.origin_price == Decimal('90') for leg in bull_legs_after_bull_turn)

        # === Bear turn: Bars 3-4 ===
        # Bar 3: Type 2-Bear (LH=109<110, LL=93<95) - starts bear turn
        bar3 = make_bar(3, 108.0, 109.0, 93.0, 95.0)
        detector.process_bar(bar3)

        # Verify prev_bar_type is now 'bear'
        assert detector.state.prev_bar_type == 'bear'

        # Bar 4: Type 2-Bear continues (LH=108<109, LL=91<93) - price bottoms at 91
        bar4 = make_bar(4, 95.0, 108.0, 91.0, 93.0)
        detector.process_bar(bar4)

        # === New bull turn: Bar 5 ===
        # Bar 5: Type 2-Bull (HH=112>108, HL=93>91) - starts NEW bull turn
        # This should create a new bull leg from 91 (the local low)
        bar5 = make_bar(5, 93.0, 112.0, 93.0, 110.0)
        events5 = detector.process_bar(bar5)

        # Verify prev_bar_type switched to 'bull'
        assert detector.state.prev_bar_type == 'bull'

        # Verify last_turn_bar['bull'] was set to the pending origin's bar index (bar 4)
        # not the bar where the turn was detected (bar 5). This ensures the first
        # leg created in the new turn is included in domination checks.
        assert detector.state.last_turn_bar['bull'] == 4

        # Key assertion: A new bull leg should be created from the new turn's low
        # even though the old bull leg has origin=90 which is "better" than 91
        bull_legs_after_new_turn = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]

        # Should have bull legs from BOTH turns:
        # 1. Old leg from origin=90 (previous turn)
        # 2. New leg from origin=91 (new turn, created at bar 5)
        origins = [leg.origin_price for leg in bull_legs_after_new_turn]
        assert Decimal('90') in origins, "Old bull leg from previous turn should still exist"
        assert Decimal('91') in origins, "New bull leg from new turn should be created"

        # Verify LegCreatedEvent was emitted for the new bull leg
        bull_created_events = [
            e for e in events5
            if isinstance(e, LegCreatedEvent) and e.direction == 'bull'
        ]
        assert len(bull_created_events) >= 1, "Should emit LegCreatedEvent for new bull leg"
        assert any(e.origin_price == Decimal('91') for e in bull_created_events)

    def test_bear_leg_created_after_bull_turn_despite_better_previous_origin(self):
        """
        After a bull turn, a new bear leg should be created even if a bear leg
        from the previous turn has a better (higher) origin.

        Scenario:
        - Bars 0-2: Bear turn, creates bear leg with origin=110
        - Bars 3-4: Bull turn (price retraces)
        - Bars 5+: New bear turn from local high at 109

        Expected: New bear leg from 109 is created, even though 110 > 109.
        """
        detector = HierarchicalDetector()

        # === Bear turn: Bars 0-2 ===
        # Bar 0: Initial bar
        bar0 = make_bar(0, 105.0, 110.0, 100.0, 102.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bear (LH=108<110, LL=95<100) - creates bear leg from 110
        bar1 = make_bar(1, 102.0, 108.0, 95.0, 96.0)
        detector.process_bar(bar1)

        # Bar 2: Type 2-Bear continues (LH=105<108, LL=90<95)
        bar2 = make_bar(2, 96.0, 105.0, 90.0, 92.0)
        detector.process_bar(bar2)

        # Verify bear leg exists with origin at 110
        bear_legs_after_bear_turn = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        assert len(bear_legs_after_bear_turn) >= 1
        assert any(leg.origin_price == Decimal('110') for leg in bear_legs_after_bear_turn)

        # === Bull turn: Bars 3-4 ===
        # Bar 3: Type 2-Bull (HH=107>105, HL=93>90) - starts bull turn
        bar3 = make_bar(3, 92.0, 107.0, 93.0, 105.0)
        detector.process_bar(bar3)

        # Verify prev_bar_type is now 'bull'
        assert detector.state.prev_bar_type == 'bull'

        # Bar 4: Type 2-Bull continues (HH=109>107, HL=100>93) - price tops at 109
        bar4 = make_bar(4, 105.0, 109.0, 100.0, 107.0)
        detector.process_bar(bar4)

        # === New bear turn: Bar 5 ===
        # Bar 5: Type 2-Bear (LH=107<109, LL=95<100) - starts NEW bear turn
        bar5 = make_bar(5, 107.0, 107.0, 95.0, 96.0)
        events5 = detector.process_bar(bar5)

        # Verify prev_bar_type switched to 'bear'
        assert detector.state.prev_bar_type == 'bear'

        # Verify last_turn_bar['bear'] was set to the pending origin's bar index (bar 4)
        # not the bar where the turn was detected (bar 5).
        assert detector.state.last_turn_bar['bear'] == 4

        # Key assertion: A new bear leg should be created from the new turn's high
        # even though the old bear leg has origin=110 which is "better" than 109
        bear_legs_after_new_turn = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]

        # Should have bear legs from BOTH turns
        origins = [leg.origin_price for leg in bear_legs_after_new_turn]
        assert Decimal('110') in origins, "Old bear leg from previous turn should still exist"
        assert Decimal('109') in origins, "New bear leg from new turn should be created"

    def test_same_turn_domination_still_applies(self):
        """
        Within the same turn, dominated legs should still be skipped.

        This verifies that the turn-scoping doesn't break the original #194 optimization.
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar - establishes pending bull origin at 90
        bar0 = make_bar(0, 95.0, 100.0, 90.0, 98.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull - creates bull leg with origin=90
        bar1 = make_bar(1, 98.0, 105.0, 92.0, 103.0)
        detector.process_bar(bar1)

        # Bar 2: Type 2-Bull - would create leg with origin=92, but dominated by 90
        bar2 = make_bar(2, 103.0, 110.0, 95.0, 108.0)
        events2 = detector.process_bar(bar2)

        # Still same turn, no turn transition
        assert detector.state.last_turn_bar['bull'] == -1  # Never set

        # Should only have 1 bull leg (origin=90)
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs) == 1
        assert bull_legs[0].origin_price == Decimal('90')

        # No LegCreatedEvent for dominated leg
        bull_created_events = [
            e for e in events2
            if isinstance(e, LegCreatedEvent) and e.direction == 'bull'
        ]
        assert len(bull_created_events) == 0

    def test_turn_tracking_state_serialization(self):
        """Verify turn tracking state is properly serialized and restored."""
        detector = HierarchicalDetector()

        # Process some bars to establish turn state
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 102.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 102.0, 110.0, 100.0, 108.0)  # Type 2-Bull (HH=110>105, HL=100>95)
        detector.process_bar(bar1)

        bar2 = make_bar(2, 108.0, 108.0, 93.0, 95.0)  # Type 2-Bear (LH=108<110, LL=93<100) - turn change
        detector.process_bar(bar2)

        # Verify state
        assert detector.state.prev_bar_type == 'bear'
        # last_turn_bar is set to the pending origin's bar index (bar 1, where the high was)
        assert detector.state.last_turn_bar['bear'] == 1

        # Serialize
        state_dict = detector.state.to_dict()

        # Restore
        from src.swing_analysis.dag import DetectorState
        restored_state = DetectorState.from_dict(state_dict)

        # Verify restored state
        assert restored_state.prev_bar_type == 'bear'
        assert restored_state.last_turn_bar['bear'] == 1
        assert restored_state.last_turn_bar['bull'] == -1
