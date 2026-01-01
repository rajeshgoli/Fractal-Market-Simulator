"""
Tests for #395: Pending origin preservation during pivot extension.

Verifies that better pending origins are not overwritten by worse ones:
- Bear pending: higher prices are better (larger potential range)
- Bull pending: lower prices are better (larger potential range)
"""

from decimal import Decimal
import pytest

from src.swing_analysis.dag.leg_detector import LegDetector
from src.swing_analysis.types import Bar


def make_bar(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    """Create a bar with the given OHLC values."""
    return Bar(
        index=index,
        timestamp=index * 1800,  # 30-minute bars
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class TestBearPendingOriginPreservation:
    """Test that higher bear pending origins are preserved."""

    def test_higher_bear_pending_not_replaced_by_lower(self):
        """
        When multiple bull legs extend on different bars, the highest
        pending bear origin should be preserved, not overwritten by lower ones.
        """
        detector = LegDetector()

        # Bar 0: Establish initial state with a low
        detector.process_bar(make_bar(0, 100, 102, 98, 101))

        # Bar 1: Rally to create bull pending
        detector.process_bar(make_bar(1, 101, 105, 100, 104))

        # Bar 2: Pullback to confirm bull leg from 98
        detector.process_bar(make_bar(2, 104, 104, 99, 100))

        # Bar 3: New high at 110 - this should set bear pending to 110
        detector.process_bar(make_bar(3, 100, 110, 99, 108))

        bear_pending = detector.state.pending_origins.get('bear')
        assert bear_pending is not None
        assert float(bear_pending.price) == 110.0

        # Bar 4: A different (smaller) bull leg extends to 106
        # This should NOT replace the bear pending of 110
        detector.process_bar(make_bar(4, 108, 106, 105, 106))

        bear_pending_after = detector.state.pending_origins.get('bear')
        assert bear_pending_after is not None
        # The bear pending should still be 110, not 106
        assert float(bear_pending_after.price) == 110.0, \
            f"Bear pending was incorrectly replaced: {bear_pending_after.price} (expected 110.0)"

    def test_higher_bear_pending_replaces_lower(self):
        """
        When a bull leg extends to a NEW high that's higher than existing
        bear pending, it SHOULD replace the pending origin.
        """
        detector = LegDetector()

        # Bar 0: Establish initial state
        detector.process_bar(make_bar(0, 100, 102, 98, 101))

        # Bar 1: Rally
        detector.process_bar(make_bar(1, 101, 105, 100, 104))

        # Bar 2: Pullback to confirm bull leg
        detector.process_bar(make_bar(2, 104, 104, 99, 100))

        # Bar 3: High at 110 - sets bear pending
        detector.process_bar(make_bar(3, 100, 110, 99, 108))

        bear_pending = detector.state.pending_origins.get('bear')
        assert float(bear_pending.price) == 110.0

        # Bar 4: New higher high at 115 - SHOULD replace bear pending
        detector.process_bar(make_bar(4, 108, 115, 107, 114))

        bear_pending_after = detector.state.pending_origins.get('bear')
        assert bear_pending_after is not None
        assert float(bear_pending_after.price) == 115.0, \
            f"Bear pending should be updated to higher price: {bear_pending_after.price}"


class TestBullPendingOriginPreservation:
    """Test that lower bull pending origins are preserved."""

    def test_lower_bull_pending_not_replaced_by_higher(self):
        """
        When multiple bear legs extend on different bars, the lowest
        pending bull origin should be preserved, not overwritten by higher ones.
        """
        detector = LegDetector()

        # Bar 0: Establish initial state with a high
        detector.process_bar(make_bar(0, 100, 105, 98, 102))

        # Bar 1: Drop to create bear pending
        detector.process_bar(make_bar(1, 102, 103, 95, 96))

        # Bar 2: Bounce to confirm bear leg from 105
        detector.process_bar(make_bar(2, 96, 104, 95, 103))

        # Bar 3: New low at 90 - this should set bull pending to 90
        detector.process_bar(make_bar(3, 103, 104, 90, 92))

        bull_pending = detector.state.pending_origins.get('bull')
        assert bull_pending is not None
        assert float(bull_pending.price) == 90.0

        # Bar 4: A different (smaller) bear leg extends to 94
        # This should NOT replace the bull pending of 90
        detector.process_bar(make_bar(4, 92, 95, 94, 94))

        bull_pending_after = detector.state.pending_origins.get('bull')
        assert bull_pending_after is not None
        # The bull pending should still be 90, not 94
        assert float(bull_pending_after.price) == 90.0, \
            f"Bull pending was incorrectly replaced: {bull_pending_after.price} (expected 90.0)"

    def test_lower_bull_pending_replaces_higher(self):
        """
        When a bear leg extends to a NEW low that's lower than existing
        bull pending, it SHOULD replace the pending origin.
        """
        detector = LegDetector()

        # Bar 0: Establish initial state
        detector.process_bar(make_bar(0, 100, 105, 98, 102))

        # Bar 1: Drop
        detector.process_bar(make_bar(1, 102, 103, 95, 96))

        # Bar 2: Bounce to confirm bear leg
        detector.process_bar(make_bar(2, 96, 104, 95, 103))

        # Bar 3: Low at 90 - sets bull pending
        detector.process_bar(make_bar(3, 103, 104, 90, 92))

        bull_pending = detector.state.pending_origins.get('bull')
        assert float(bull_pending.price) == 90.0

        # Bar 4: New lower low at 85 - SHOULD replace bull pending
        detector.process_bar(make_bar(4, 92, 93, 85, 86))

        bull_pending_after = detector.state.pending_origins.get('bull')
        assert bull_pending_after is not None
        assert float(bull_pending_after.price) == 85.0, \
            f"Bull pending should be updated to lower price: {bull_pending_after.price}"


class TestPendingOriginPreservationIntegration:
    """Integration tests simulating the real-world scenario from feedback."""

    def test_bear_leg_forms_at_best_bull_pivot(self):
        """
        Simulate the scenario from observation 000021cd:
        Multiple bull legs with different pivots should result in a bear leg
        forming at the HIGHEST bull pivot, not an intermediate one.
        """
        detector = LegDetector()

        # Simulate price action similar to the real case:
        # Bull move from ~4459 to ~4517.75, with intermediate legs

        # Bar 0: Start low
        detector.process_bar(make_bar(0, 4460, 4462, 4458, 4461))

        # Bar 1-2: Rally up
        detector.process_bar(make_bar(1, 4461, 4480, 4460, 4478))
        detector.process_bar(make_bar(2, 4478, 4500, 4475, 4498))

        # Bar 3: Pullback to confirm some bull legs
        detector.process_bar(make_bar(3, 4498, 4500, 4485, 4490))

        # Bar 4: Rally to highest high at 4517.75
        detector.process_bar(make_bar(4, 4490, 4517.75, 4488, 4515))

        bear_pending = detector.state.pending_origins.get('bear')
        assert bear_pending is not None
        highest_pending = float(bear_pending.price)

        # Bar 5: Smaller rally (different leg) to 4510 - should NOT replace
        detector.process_bar(make_bar(5, 4515, 4510, 4508, 4509))

        bear_pending_after = detector.state.pending_origins.get('bear')
        assert bear_pending_after is not None
        assert float(bear_pending_after.price) == highest_pending, \
            f"Bear pending should remain at {highest_pending}, not {bear_pending_after.price}"

        # Bar 6-7: Drop to form bear leg from the highest pending
        detector.process_bar(make_bar(6, 4509, 4510, 4480, 4485))
        detector.process_bar(make_bar(7, 4485, 4490, 4460, 4465))

        # Check that a bear leg exists from the highest pending origin
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and float(leg.origin_price) >= 4515
        ]

        assert len(bear_legs) > 0, \
            "A bear leg should have formed from the highest bull pivot (~4517.75)"
