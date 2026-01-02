"""
Tests for Issue #451: Per-bar reference state for buffered playback.

When querying reference state for a historical bar, only include legs that
were formed at or before that bar, not legs formed later.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from decimal import Decimal

from swing_analysis.dag.leg import Leg
from swing_analysis.reference_layer import ReferenceLayer
from swing_analysis.reference_config import ReferenceConfig
from swing_analysis.types import Bar


def make_bar(index: int, high: float, low: float, close: float) -> Bar:
    """Create a test bar."""
    return Bar(
        index=index,
        timestamp=1000000 + index * 60,
        open=close,
        high=high,
        low=low,
        close=close,
    )


def make_bull_leg(origin_price: float, pivot_price: float, origin_index: int = 0, pivot_index: int = 10) -> Leg:
    """Create a test bull leg."""
    return Leg(
        direction='bull',
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
    )


class TestMaxBarIndexFiltering:
    """Test that max_bar_index filters references by formation bar."""

    def test_leg_formed_at_bar_10_not_visible_at_bar_5(self):
        """Leg formed at bar 10 should not appear when querying bar 5."""
        ref_config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=ref_config)

        # Create leg with origin at 100, pivot at 110
        leg = make_bull_leg(origin_price=100, pivot_price=110)

        # Form the leg at bar 10 (close at 107, ~30% retracement)
        bar10 = make_bar(index=10, high=108, low=106, close=107)
        ref_layer.update([leg], bar10)

        # Verify leg is formed at bar 10
        assert leg.leg_id in ref_layer._formed_refs
        pivot, formation_bar = ref_layer._formed_refs[leg.leg_id]
        assert formation_bar == 10

        # Query at bar 5 - leg should NOT be visible
        bar5 = make_bar(index=5, high=108, low=106, close=107)
        state = ref_layer.update([leg], bar5, max_bar_index=5)
        assert len(state.references) == 0

        # Query at bar 10 - leg should be visible
        state = ref_layer.update([leg], bar10, max_bar_index=10)
        assert len(state.references) == 1
        assert state.references[0].leg.leg_id == leg.leg_id

        # Query at bar 15 - leg should be visible
        bar15 = make_bar(index=15, high=108, low=106, close=107)
        state = ref_layer.update([leg], bar15, max_bar_index=15)
        assert len(state.references) == 1

    def test_multiple_legs_formed_at_different_bars(self):
        """Only legs formed at or before max_bar_index should appear."""
        ref_config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=ref_config)

        # Create two legs with same price range so they share the same bar context
        leg1 = make_bull_leg(origin_price=100, pivot_price=110, origin_index=0, pivot_index=5)
        leg2 = make_bull_leg(origin_price=90, pivot_price=110, origin_index=8, pivot_index=15)

        # Form leg1 at bar 10 (close at 107, ~30% retracement from 110 to 100)
        bar10 = make_bar(index=10, high=108, low=106, close=107)
        ref_layer.update([leg1], bar10)

        # Form leg2 at bar 20 (close at 105, ~25% retracement from 110 to 90)
        bar20 = make_bar(index=20, high=106, low=104, close=105)
        ref_layer.update([leg1, leg2], bar20)

        # Query at bar 15 - only leg1 should be visible (leg2 formed at bar 20)
        bar15 = make_bar(index=15, high=108, low=106, close=107)
        state = ref_layer.update([leg1, leg2], bar15, max_bar_index=15)
        assert len(state.references) == 1
        assert state.references[0].leg.leg_id == leg1.leg_id

        # Query at bar 25 - both legs should be visible
        bar25 = make_bar(index=25, high=108, low=106, close=107)
        state = ref_layer.update([leg1, leg2], bar25, max_bar_index=25)
        assert len(state.references) == 2

    def test_no_max_bar_index_returns_all_formed(self):
        """Without max_bar_index, all formed legs should be returned."""
        ref_config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=ref_config)

        # Create and form leg at bar 10
        leg = make_bull_leg(origin_price=100, pivot_price=110)
        bar10 = make_bar(index=10, high=108, low=106, close=107)
        ref_layer.update([leg], bar10)

        # Query without max_bar_index at bar 5 - leg should still appear
        # (this is the old behavior, maintained for backward compatibility)
        bar5 = make_bar(index=5, high=108, low=106, close=107)
        state = ref_layer.update([leg], bar5)  # No max_bar_index
        assert len(state.references) == 1


class TestGetFormedLegIdsAtBar:
    """Test the get_formed_leg_ids_at_bar helper method."""

    def test_returns_empty_for_unformed_leg(self):
        """No legs formed yet should return empty set."""
        ref_layer = ReferenceLayer()
        assert ref_layer.get_formed_leg_ids_at_bar(10) == set()

    def test_returns_leg_at_formation_bar(self):
        """Leg should be included at its formation bar."""
        ref_config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=ref_config)

        leg = make_bull_leg(origin_price=100, pivot_price=110)
        bar = make_bar(index=10, high=108, low=106, close=107)
        ref_layer.update([leg], bar)

        # At bar 10, leg should be included
        formed = ref_layer.get_formed_leg_ids_at_bar(10)
        assert leg.leg_id in formed

        # At bar 5, leg should NOT be included
        formed = ref_layer.get_formed_leg_ids_at_bar(5)
        assert leg.leg_id not in formed

        # At bar 15, leg should be included
        formed = ref_layer.get_formed_leg_ids_at_bar(15)
        assert leg.leg_id in formed


class TestIsFormedAtBar:
    """Test the is_formed_at_bar helper method."""

    def test_returns_false_for_unknown_leg(self):
        """Unknown leg ID should return False."""
        ref_layer = ReferenceLayer()
        assert ref_layer.is_formed_at_bar("unknown_leg", 10) is False

    def test_returns_true_at_and_after_formation_bar(self):
        """Should return True at and after formation bar."""
        ref_config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=ref_config)

        leg = make_bull_leg(origin_price=100, pivot_price=110)
        bar = make_bar(index=10, high=108, low=106, close=107)
        ref_layer.update([leg], bar)

        # Before formation: False
        assert ref_layer.is_formed_at_bar(leg.leg_id, 5) is False

        # At formation: True
        assert ref_layer.is_formed_at_bar(leg.leg_id, 10) is True

        # After formation: True
        assert ref_layer.is_formed_at_bar(leg.leg_id, 15) is True
