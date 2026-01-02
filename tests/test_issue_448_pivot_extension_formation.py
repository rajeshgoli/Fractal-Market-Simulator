"""
Tests for Issue #448: Pivot extension should nullify formation.

When a leg's pivot extends beyond the price at which it was formed,
the formation should be nullified and the leg must re-form at the
new pivot level.
"""

import sys
from pathlib import Path

# Add src to path for imports
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


def make_bear_leg(origin_price: float, pivot_price: float, origin_index: int = 0, pivot_index: int = 10) -> Leg:
    """Create a test bear leg."""
    return Leg(
        direction='bear',
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
    )


class TestPivotExtensionNullifiesFormation:
    """Test that pivot extension nullifies formation (Issue #448)."""

    def test_bull_leg_formed_then_pivot_extends(self):
        """Bull leg: formation should be nullified when pivot extends higher."""
        ref_layer = ReferenceLayer()

        # Bull leg: origin at 100, pivot at 110 (range = 10)
        # Formation at 0.236 requires price to drop to: 110 - (10 * 0.236) = 107.64
        leg = make_bull_leg(origin_price=100, pivot_price=110)

        # Bar with close at 107 triggers formation (location ~0.3 >= 0.236)
        bar = make_bar(index=15, high=108, low=106, close=107)

        # First call - should form
        formed = ref_layer._is_formed_for_reference(leg, Decimal("107"), 0.0)
        assert formed is True
        assert leg.leg_id in ref_layer._formed_refs
        assert ref_layer._formed_refs[leg.leg_id][0] == Decimal("110")  # Stored formation pivot

        # Now pivot extends to 120
        leg.update_pivot(Decimal("120"), 20)

        # Check formation again - should be nullified because pivot extended
        bar2 = make_bar(index=25, high=118, low=116, close=117)
        formed2 = ref_layer._is_formed_for_reference(leg, Decimal("117"), 0.0)

        # 117 is at location = (120 - 117) / (120 - 100) = 3/20 = 0.15 < 0.236
        # So leg should NOT be formed
        assert formed2 is False
        assert leg.leg_id not in ref_layer._formed_refs

    def test_bear_leg_formed_then_pivot_extends(self):
        """Bear leg: formation should be nullified when pivot extends lower."""
        ref_layer = ReferenceLayer()

        # Bear leg: origin at 110, pivot at 100 (range = 10)
        # Formation at 0.236 requires price to rise to: 100 + (10 * 0.236) = 102.36
        leg = make_bear_leg(origin_price=110, pivot_price=100)

        # Bar with close at 103 triggers formation (location ~0.3 >= 0.236)
        bar = make_bar(index=15, high=104, low=102, close=103)

        # First call - should form
        formed = ref_layer._is_formed_for_reference(leg, Decimal("103"), 0.0)
        assert formed is True
        assert leg.leg_id in ref_layer._formed_refs
        assert ref_layer._formed_refs[leg.leg_id][0] == Decimal("100")  # Stored formation pivot

        # Now pivot extends to 90 (lower for bear)
        leg.update_pivot(Decimal("90"), 20)

        # Check formation again - should be nullified because pivot extended
        bar2 = make_bar(index=25, high=94, low=92, close=93)
        formed2 = ref_layer._is_formed_for_reference(leg, Decimal("93"), 0.0)

        # 93 is at location = (93 - 90) / (110 - 90) = 3/20 = 0.15 < 0.236
        # So leg should NOT be formed
        assert formed2 is False
        assert leg.leg_id not in ref_layer._formed_refs

    def test_bull_leg_reforms_after_pivot_extension(self):
        """Bull leg can re-form at new pivot level after extension."""
        ref_layer = ReferenceLayer()

        # Bull leg: origin at 100, pivot at 110
        leg = make_bull_leg(origin_price=100, pivot_price=110)

        # Form at pivot 110
        formed = ref_layer._is_formed_for_reference(leg, Decimal("107"), 0.0)
        assert formed is True

        # Pivot extends to 120 - formation nullified
        leg.update_pivot(Decimal("120"), 20)
        formed = ref_layer._is_formed_for_reference(leg, Decimal("117"), 0.0)
        assert formed is False  # 117 is only 0.15 location, not formed

        # Now price drops to formation level for new pivot
        # New range = 20, formation at 0.236 = 120 - 4.72 = 115.28
        formed = ref_layer._is_formed_for_reference(leg, Decimal("115"), 0.0)
        assert formed is True  # 115 is at location = 5/20 = 0.25 >= 0.236
        assert ref_layer._formed_refs[leg.leg_id][0] == Decimal("120")  # New formation pivot

    def test_unchanged_pivot_stays_formed(self):
        """Leg stays formed if pivot hasn't extended."""
        ref_layer = ReferenceLayer()

        # Bull leg: origin at 100, pivot at 110
        leg = make_bull_leg(origin_price=100, pivot_price=110)

        # Form at pivot 110
        formed = ref_layer._is_formed_for_reference(leg, Decimal("107"), 0.0)
        assert formed is True

        # Check again with same pivot - should stay formed
        formed = ref_layer._is_formed_for_reference(leg, Decimal("109"), 0.0)
        assert formed is True

        # Even at location 0 (at pivot), stays formed
        formed = ref_layer._is_formed_for_reference(leg, Decimal("110"), 0.0)
        assert formed is True

    def test_issue_448_scenario(self):
        """
        Reproduce the exact scenario from the user's feedback.

        Bull leg formed early when pivot was ~3695, but by bar 499 the pivot
        had extended to 3952. The leg should NOT appear as formed.
        """
        ref_layer = ReferenceLayer()

        # Bull leg: origin at 3656.5, initially pivot at 3695 (similar to bar 4)
        leg = make_bull_leg(origin_price=3656.5, pivot_price=3695, origin_index=0, pivot_index=4)

        # Form at early pivot (location = (3695 - 3682.75) / 38.5 = 0.32)
        formed = ref_layer._is_formed_for_reference(leg, Decimal("3682.75"), 0.0)
        assert formed is True

        # Pivot extends significantly to 3952 (like in the actual scenario)
        leg.update_pivot(Decimal("3952"), 494)

        # Check at bar 499 with close around 3947
        # Location = (3952 - 3947) / (3952 - 3656.5) = 5 / 295.5 = 0.017
        formed = ref_layer._is_formed_for_reference(leg, Decimal("3947"), 0.0)

        # Should NOT be formed - location 0.017 is way below 0.236 threshold
        assert formed is False
        assert leg.leg_id not in ref_layer._formed_refs


class TestFormationWithGetAllWithStatus:
    """Test formation behavior through get_all_with_status() method."""

    def test_pivot_extension_changes_status_to_not_formed(self):
        """A formed leg should show NOT_FORMED status after pivot extends."""
        from swing_analysis.reference_layer import FilterReason

        ref_layer = ReferenceLayer()

        # Create a bull leg and form it
        leg = make_bull_leg(origin_price=100, pivot_price=110, origin_index=0, pivot_index=10)

        # Form the leg with a bar in formation zone (close at 107, location ~0.3)
        bar1 = make_bar(index=15, high=109, low=106, close=107)
        formed = ref_layer._is_formed_for_reference(leg, Decimal("107"), bar1.timestamp)
        assert formed is True

        # Check status - should be VALID (assuming we're past cold start for this check)
        # Actually get_all_with_status checks cold start, so let's just verify formed
        assert leg.leg_id in ref_layer._formed_refs
        assert ref_layer._formed_refs[leg.leg_id][0] == Decimal("110")

        # Extend pivot to 130
        leg.update_pivot(Decimal("130"), 20)

        # Now check formation again - should be nullified
        bar2 = make_bar(index=25, high=128, low=126, close=127)
        formed2 = ref_layer._is_formed_for_reference(leg, Decimal("127"), bar2.timestamp)

        # 127 at new pivot 130 (range 30): location = 3/30 = 0.1 < 0.236
        assert formed2 is False
        assert leg.leg_id not in ref_layer._formed_refs

    def test_get_all_with_status_shows_not_formed_after_extension(self):
        """get_all_with_status should show NOT_FORMED for extended pivot legs."""
        from swing_analysis.reference_layer import FilterReason

        # Use config with low min_swings to avoid cold_start
        ref_config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=ref_config)

        # Create leg and form it
        leg = make_bull_leg(origin_price=100, pivot_price=110, origin_index=0, pivot_index=10)
        ref_layer._is_formed_for_reference(leg, Decimal("107"), 0.0)
        assert leg.leg_id in ref_layer._formed_refs

        # Extend pivot
        leg.update_pivot(Decimal("130"), 20)

        # Check status through get_all_with_status
        bar = make_bar(index=25, high=128, low=126, close=127)
        statuses = ref_layer.get_all_with_status([leg], bar)

        assert len(statuses) == 1
        status = statuses[0]
        assert status.reason == FilterReason.NOT_FORMED
        assert status.threshold == ref_layer.reference_config.formation_fib_threshold
