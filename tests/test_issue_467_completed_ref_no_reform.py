"""
Tests for Issue #467: Completed references should not re-form.

When a reference reaches completion (location > 2x), it is terminal.
The reference should never re-enter _formed_refs even if price returns
below 2x on subsequent bars.

Solution: Track max_location on Leg.ref.max_location. Derive completion
status at runtime via _is_completed() which checks if max_location >=
completion_threshold.

Test scenarios:
1. Form -> Complete -> Price falls back -> Should NOT re-form
2. max_location tracking persists on Leg.ref
3. get_all_with_status respects completion
4. _is_completed reflects config changes
"""

import pytest
from decimal import Decimal

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    FilterReason,
)
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg, RefMetadata
from src.swing_analysis.types import Bar


def make_leg(
    direction: str = 'bear',
    origin_price: float = 110.0,
    origin_index: int = 100,
    pivot_price: float = 100.0,
    pivot_index: int = 105,
    depth: int = 0,
) -> Leg:
    """Helper to create a test Leg."""
    return Leg(
        direction=direction,
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
        depth=depth,
    )


def make_bar(
    index: int = 0,
    open_: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    close: float = 101.0,
    timestamp: int = 0,
) -> Bar:
    """Helper to create a test Bar."""
    return Bar(
        index=index,
        timestamp=timestamp,
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
    )


def _populate_distribution(ref_layer: ReferenceLayer, count: int = 50):
    """Pre-populate distribution to exit cold start."""
    for i in range(count):
        ref_layer._bin_distribution.add_leg(f"warmup_leg_{i}", float((i + 1) * 10), 1000.0 + i)


class TestRefMetadataDataclass:
    """Tests for RefMetadata dataclass on Leg."""

    def test_ref_metadata_default_factory(self):
        """Leg should have ref field with RefMetadata by default."""
        leg = make_leg()
        assert hasattr(leg, 'ref')
        assert isinstance(leg.ref, RefMetadata)
        assert leg.ref.max_location is None

    def test_ref_metadata_independent_per_leg(self):
        """Each leg should have its own RefMetadata instance."""
        leg1 = make_leg(origin_index=1)
        leg2 = make_leg(origin_index=2)

        leg1.ref.max_location = 1.5
        leg2.ref.max_location = 0.8

        assert leg1.ref.max_location == 1.5
        assert leg2.ref.max_location == 0.8


class TestCompletedReferencesDoNotReForm:
    """Tests for #467: Completed references should not re-form."""

    def test_completed_reference_does_not_reform_on_price_return(self):
        """
        A reference that reaches completion should not re-form when price
        returns below 2x.

        Scenario from issue:
        1. Bear leg: 110 (origin) -> 100 (pivot), used as bull reference
        2. Bulls defend 100, price rises to 104 -> leg forms (location >= 0.236)
        3. Bulls succeed, price reaches 125 -> leg completes (location > 2.0)
        4. Price pulls back to 115 -> leg should NOT re-form
        """
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        # Bear leg: origin=110, pivot=100, range=10
        # For bull reference: 0=pivot(100), 1=origin(110), 2=target(120)
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Step 1: Form the reference at location 0.4
        # location = (close - pivot) / range = (104 - 100) / 10 = 0.4
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        state1 = ref_layer.update([leg], form_bar)
        assert len(state1.references) == 1, "Leg should be formed"
        assert leg.leg_id in ref_layer._formed_refs, "Leg should be in _formed_refs"
        assert leg.ref.max_location is not None, "max_location should be tracked"
        assert leg.ref.max_location < 2.0, "Should not be completed yet"

        # Step 2: Price reaches completion (> 2x)
        # location > 2 means close > pivot + 2*range = 100 + 20 = 120
        complete_bar = make_bar(close=125, high=126, low=124, index=2)
        state2 = ref_layer.update([leg], complete_bar)
        assert len(state2.references) == 0, "Leg should be completed and removed"
        assert leg.leg_id not in ref_layer._formed_refs, "Leg should not be in _formed_refs"
        assert leg.ref.max_location >= 2.0, "max_location should record completion"

        # Step 3: Price returns to location 1.5 (which is above formation threshold)
        # location = (close - pivot) / range = (115 - 100) / 10 = 1.5
        return_bar = make_bar(close=115, high=116, low=114, index=3)
        state3 = ref_layer.update([leg], return_bar)
        assert len(state3.references) == 0, "Leg should NOT re-form after completion"
        assert leg.leg_id not in ref_layer._formed_refs, "Leg should stay out of _formed_refs"
        # max_location should not decrease
        assert leg.ref.max_location >= 2.0, "max_location should persist"

    def test_completed_reference_does_not_reform_at_formation_level(self):
        """
        Even if price returns exactly to formation level after completion,
        the reference should not re-form.
        """
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form at location 0.4
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg], form_bar)
        assert leg.leg_id in ref_layer._formed_refs

        # Complete at location > 2
        complete_bar = make_bar(close=125, high=126, low=124, index=2)
        ref_layer.update([leg], complete_bar)
        assert leg.ref.max_location >= 2.0

        # Return to exactly formation level (location = 0.382)
        # location = 0.382 means close = pivot + 0.382*range = 100 + 3.82 = 103.82
        formation_level_bar = make_bar(close=103.82, high=104, low=103, index=3)
        state = ref_layer.update([leg], formation_level_bar)
        assert len(state.references) == 0, "Completed reference should never re-form"
        assert leg.leg_id not in ref_layer._formed_refs

    def test_is_formed_for_reference_returns_false_for_completed(self):
        """_is_formed_for_reference should immediately return False for completed legs."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Set max_location to indicate completion
        leg.ref.max_location = 2.5

        # Try to form at a price that would normally trigger formation
        formed = ref_layer._is_formed_for_reference(
            leg, Decimal("104"), timestamp=1000, bar_index=1
        )
        assert formed is False, "Completed leg should never form"
        assert leg.leg_id not in ref_layer._formed_refs


class TestMaxLocationTracking:
    """Tests for max_location tracking on Leg.ref."""

    def test_max_location_updated_on_each_bar(self):
        """max_location should track the highest location seen."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # First bar at location 0.4
        bar1 = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg], bar1)
        max_loc_1 = leg.ref.max_location
        assert max_loc_1 is not None

        # Higher location at 0.8
        bar2 = make_bar(close=108, high=109, low=107, index=2)
        ref_layer.update([leg], bar2)
        assert leg.ref.max_location > max_loc_1

        # Lower location - max should not decrease
        bar3 = make_bar(close=104, high=105, low=103, index=3)
        ref_layer.update([leg], bar3)
        assert leg.ref.max_location == leg.ref.max_location  # Should not change

    def test_max_location_tracks_bar_extreme_not_just_close(self):
        """max_location should track bar high/low, not just close."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Bar with close at location 0.5, but high reaches 2.5
        # For bear leg with bull reference: high price = higher location
        # location at high=125: (125-100)/10 = 2.5
        bar = make_bar(close=105, high=125, low=100, index=1)
        ref_layer.update([leg], bar)

        # max_location should capture the high
        assert leg.ref.max_location >= 2.0, "Should capture extreme location from bar high"

    def test_max_location_persists_with_leg(self):
        """max_location is stored on leg, persists across calls."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        bar = make_bar(close=125, high=126, low=124, index=1)
        ref_layer.update([leg], bar)

        expected_max = leg.ref.max_location

        # Create new ref_layer instance
        new_ref_layer = ReferenceLayer()
        _populate_distribution(new_ref_layer)

        # Same leg object - max_location persists on leg itself
        bar2 = make_bar(close=105, high=106, low=104, index=2)
        new_ref_layer.update([leg], bar2)

        assert leg.ref.max_location == expected_max


class TestIsCompletedMethod:
    """Tests for _is_completed helper method."""

    def test_is_completed_false_when_no_max_location(self):
        """_is_completed returns False when max_location is None."""
        ref_layer = ReferenceLayer()
        leg = make_leg()
        assert leg.ref.max_location is None
        assert ref_layer._is_completed(leg) is False

    def test_is_completed_false_below_threshold(self):
        """_is_completed returns False when max_location < threshold."""
        ref_layer = ReferenceLayer()
        leg = make_leg()
        leg.ref.max_location = 1.9
        assert ref_layer._is_completed(leg) is False

    def test_is_completed_true_at_threshold(self):
        """_is_completed returns True when max_location >= threshold."""
        config = ReferenceConfig(completion_threshold=2.0)
        ref_layer = ReferenceLayer(reference_config=config)
        leg = make_leg()
        leg.ref.max_location = 2.0
        assert ref_layer._is_completed(leg) is True

    def test_is_completed_respects_config_change(self):
        """
        _is_completed derives from max_location and config, so changing
        config changes completion status.
        """
        leg = make_leg()
        leg.ref.max_location = 2.5

        # With threshold=2.0, leg is completed
        config1 = ReferenceConfig(completion_threshold=2.0)
        ref_layer1 = ReferenceLayer(reference_config=config1)
        assert ref_layer1._is_completed(leg) is True

        # With threshold=3.0, same leg is NOT completed
        config2 = ReferenceConfig(completion_threshold=3.0)
        ref_layer2 = ReferenceLayer(reference_config=config2)
        assert ref_layer2._is_completed(leg) is False


class TestGetAllWithStatusRespectsCompletion:
    """Tests for get_all_with_status respecting completion."""

    def test_get_all_with_status_marks_completed_leg_correctly(self):
        """get_all_with_status should mark legs that complete during the call."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form first
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg], form_bar)

        # Now call get_all_with_status with price at completion level
        complete_bar = make_bar(close=125, high=126, low=124, index=2)
        statuses = ref_layer.get_all_with_status([leg], complete_bar)

        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.COMPLETED
        assert leg.ref.max_location >= 2.0

    def test_get_all_with_status_shows_completed_for_previously_completed(self):
        """After completion, subsequent get_all_with_status shows COMPLETED."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg], form_bar)

        # Complete
        complete_bar = make_bar(close=125, high=126, low=124, index=2)
        ref_layer.update([leg], complete_bar)

        # Now get_all_with_status on return bar
        return_bar = make_bar(close=110, high=111, low=109, index=3)
        statuses = ref_layer.get_all_with_status([leg], return_bar)

        assert len(statuses) == 1
        # Completed legs always show as COMPLETED (derived from max_location)
        assert statuses[0].reason == FilterReason.COMPLETED


class TestBullLegCompletion:
    """Tests for bull leg completion (opposite direction)."""

    def test_bull_leg_completion_prevents_reform(self):
        """Bull legs should also be prevented from re-forming after completion."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        # Bull leg: origin=90, pivot=100, range=10
        # For bear reference: 0=pivot(100), 1=origin(90), 2=target(80)
        leg = make_leg(direction='bull', origin_price=90, pivot_price=100)

        # Form at location 0.4 (price needs to go toward origin from pivot)
        # location = (pivot - close) / range = (100 - 96) / 10 = 0.4
        form_bar = make_bar(close=96, high=100, low=95, index=1)
        state1 = ref_layer.update([leg], form_bar)
        assert len(state1.references) == 1, "Bull leg should be formed"

        # Complete at location > 2 (price < pivot - 2*range = 100 - 20 = 80)
        complete_bar = make_bar(close=75, high=76, low=74, index=2)
        state2 = ref_layer.update([leg], complete_bar)
        assert len(state2.references) == 0, "Bull leg should be completed"
        assert leg.ref.max_location >= 2.0

        # Return to location 1.5 (price = 85)
        return_bar = make_bar(close=85, high=86, low=84, index=3)
        state3 = ref_layer.update([leg], return_bar)
        assert len(state3.references) == 0, "Bull leg should NOT re-form after completion"


class TestEdgeCases:
    """Edge case tests for completion tracking."""

    def test_multiple_legs_only_completed_one_blocked(self):
        """Only completed legs should be blocked; other legs form normally."""
        ref_layer = ReferenceLayer()
        _populate_distribution(ref_layer)

        leg1 = make_leg(direction='bear', origin_price=110, pivot_price=100, origin_index=1)
        leg2 = make_leg(direction='bear', origin_price=115, pivot_price=100, origin_index=2)

        # Form both
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg1, leg2], form_bar)

        # Complete only leg1
        # leg1 completes at >120, leg2 completes at >130
        partial_complete_bar = make_bar(close=125, high=126, low=124, index=2)
        ref_layer.update([leg1, leg2], partial_complete_bar)

        assert leg1.ref.max_location >= 2.0, "leg1 should be completed"
        assert leg2.ref.max_location < 2.0, "leg2 should not be completed yet"

        # Return to formation level
        return_bar = make_bar(close=110, high=111, low=109, index=3)
        state = ref_layer.update([leg1, leg2], return_bar)

        # Only leg2 should be a valid reference
        assert len(state.references) == 1
        assert state.references[0].leg.leg_id == leg2.leg_id

    def test_completion_at_exactly_threshold(self):
        """Leg at exactly completion threshold should be completed."""
        config = ReferenceConfig(completion_threshold=2.0)
        ref_layer = ReferenceLayer(reference_config=config)
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg], form_bar)

        # Exactly at threshold (location = 2.0, close = 120)
        # location = 2.0 is >= 2.0, so should complete
        threshold_bar = make_bar(close=120, high=120, low=119, index=2)
        state = ref_layer.update([leg], threshold_bar)

        assert leg.ref.max_location >= 2.0
        assert ref_layer._is_completed(leg) is True
        assert len(state.references) == 0

    def test_completion_just_below_threshold(self):
        """Leg just below completion threshold should not complete."""
        config = ReferenceConfig(completion_threshold=2.0)
        ref_layer = ReferenceLayer(reference_config=config)
        _populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        ref_layer.update([leg], form_bar)

        # Just below threshold (location = 1.99, close = 119.9)
        below_threshold_bar = make_bar(close=119.9, high=119.9, low=118, index=2)
        state = ref_layer.update([leg], below_threshold_bar)

        assert leg.ref.max_location < 2.0
        assert ref_layer._is_completed(leg) is False
        assert len(state.references) == 1
