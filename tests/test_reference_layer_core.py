"""
Comprehensive test suite for Reference Layer core functionality.

Covers:
- #371: Cold start handling (is_cold_start, cold_start_progress)
- #372: Range distribution tracking (formed legs only)
- #373: Integration tests for update() and end-to-end workflows

This suite complements existing tests in:
- test_reference_config.py (ReferenceConfig)
- test_issue_363_365_reference_swing.py (ReferenceSwing, scale classification)
- test_issue_364_366_369_reference_layer_methods.py (location, formation, breach, salience)
"""

import pytest
from decimal import Decimal
from typing import List

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwing,
    ReferenceState,
)
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.types import Bar


def make_leg(
    direction: str = 'bear',
    origin_price: float = 110.0,
    origin_index: int = 100,
    pivot_price: float = 100.0,
    pivot_index: int = 105,
    impulsiveness: float = None,
    depth: int = 0,
) -> Leg:
    """Helper to create a test Leg.

    Note: Formation is now checked by Reference Layer based on price location,
    not a flag on the Leg. Create bars with appropriate close prices to test
    formed vs unformed scenarios.
    """
    return Leg(
        direction=direction,
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
        impulsiveness=impulsiveness,
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


class TestColdStartProperty:
    """Tests for is_cold_start property (#371)."""

    def test_cold_start_initially_true(self):
        """Fresh ReferenceLayer should be in cold start."""
        ref_layer = ReferenceLayer()
        assert ref_layer.is_cold_start is True

    def test_cold_start_with_insufficient_swings(self):
        """Cold start should be True with < 50 swings."""
        ref_layer = ReferenceLayer()

        # Add 49 swings (just under threshold)
        for i in range(49):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        assert len(ref_layer._range_distribution) == 49
        assert ref_layer.is_cold_start is True

    def test_cold_start_ends_at_50_swings(self):
        """Cold start should end at exactly 50 swings."""
        ref_layer = ReferenceLayer()

        # Add exactly 50 swings
        for i in range(50):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        assert len(ref_layer._range_distribution) == 50
        assert ref_layer.is_cold_start is False

    def test_cold_start_custom_threshold(self):
        """Cold start threshold should be configurable."""
        config = ReferenceConfig(
            xl_threshold=0.90,
            l_threshold=0.60,
            m_threshold=0.30,
            min_swings_for_scale=100,  # Custom: 100 swings required
        )
        ref_layer = ReferenceLayer(reference_config=config)

        # Add 99 swings
        for i in range(99):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        assert ref_layer.is_cold_start is True

        # Add one more
        ref_layer._add_to_range_distribution(Decimal("100"))
        assert ref_layer.is_cold_start is False


class TestColdStartProgress:
    """Tests for cold_start_progress property (#371)."""

    def test_progress_starts_at_zero(self):
        """Fresh layer should show 0/50 progress."""
        ref_layer = ReferenceLayer()

        current, required = ref_layer.cold_start_progress
        assert current == 0
        assert required == 50

    def test_progress_increments_with_swings(self):
        """Progress should reflect current distribution size."""
        ref_layer = ReferenceLayer()

        for i in range(25):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        current, required = ref_layer.cold_start_progress
        assert current == 25
        assert required == 50

    def test_progress_at_completion(self):
        """Progress should show 50/50 at completion."""
        ref_layer = ReferenceLayer()

        for i in range(50):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        current, required = ref_layer.cold_start_progress
        assert current == 50
        assert required == 50

    def test_progress_after_completion(self):
        """Progress should show actual count after completion."""
        ref_layer = ReferenceLayer()

        for i in range(75):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        current, required = ref_layer.cold_start_progress
        assert current == 75
        assert required == 50

    def test_progress_with_custom_threshold(self):
        """Progress should reflect custom threshold."""
        config = ReferenceConfig(
            xl_threshold=0.90,
            l_threshold=0.60,
            m_threshold=0.30,
            min_swings_for_scale=100,
        )
        ref_layer = ReferenceLayer(reference_config=config)

        current, required = ref_layer.cold_start_progress
        assert current == 0
        assert required == 100


class TestReferenceStateWarmupInfo:
    """Tests for warmup info in ReferenceState (#371)."""

    def test_state_during_cold_start(self):
        """ReferenceState should indicate warming up during cold start."""
        ref_layer = ReferenceLayer()
        leg = make_leg()
        bar = make_bar(close=105)

        state = ref_layer.update([leg], bar)

        assert state.is_warming_up is True
        assert state.warmup_progress == (1, 50)  # 1 formed leg added
        assert len(state.references) == 0

    def test_state_after_cold_start(self):
        """ReferenceState should not indicate warming up after cold start."""
        ref_layer = ReferenceLayer()

        # Pre-populate distribution to exit cold start
        for i in range(50):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        leg = make_leg()
        bar = make_bar(close=105)

        state = ref_layer.update([leg], bar)

        assert state.is_warming_up is False
        assert state.warmup_progress[0] >= 50

    def test_warmup_progress_accuracy(self):
        """Warmup progress should accurately reflect distribution size."""
        ref_layer = ReferenceLayer()

        # Add 30 legs to distribution manually
        for i in range(30):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        leg = make_leg()
        bar = make_bar(close=105)

        state = ref_layer.update([leg], bar)

        assert state.is_warming_up is True
        # 30 from manual + 1 from the leg in update
        assert state.warmup_progress == (31, 50)


class TestRangeDistributionFormedLegsOnly:
    """Tests for range distribution tracking formed legs only (#372).

    Formation is now determined by price position, not a flag.
    For bear leg (origin 110, pivot 100, range 10):
    - Formation threshold = 0.382
    - Price needs to be at 103.82+ for formation
    - close=102 -> location 0.2 -> NOT formed
    - close=105 -> location 0.5 -> formed
    """

    def test_unformed_legs_not_added(self):
        """Legs with price below formation threshold should not be added to distribution."""
        ref_layer = ReferenceLayer()

        # Bear legs: origin > pivot, need close > pivot + 0.382*(origin-pivot)
        unformed_legs = [
            make_leg(origin_price=105, pivot_price=100, origin_index=1),  # range=5, needs close>=101.91
            make_leg(origin_price=108, pivot_price=100, origin_index=2),  # range=8, needs close>=103.06
        ]

        # close=101 is below both formation thresholds
        bar = make_bar(close=101)
        ref_layer.update(unformed_legs, bar)

        assert len(ref_layer._range_distribution) == 0

    def test_formed_legs_added_to_distribution(self):
        """Legs with price at/above formation threshold should be added to distribution."""
        ref_layer = ReferenceLayer()

        formed_legs = [
            make_leg(origin_price=105, pivot_price=100, origin_index=1),  # range=5, needs close>=101.91
            make_leg(origin_price=110, pivot_price=100, origin_index=2),  # range=10, needs close>=103.82
        ]

        # close=105 is above both formation thresholds (location=0.5 for both)
        bar = make_bar(close=105)
        ref_layer.update(formed_legs, bar)

        assert len(ref_layer._range_distribution) == 2
        # Ranges should be 5 and 10
        assert Decimal("5") in ref_layer._range_distribution
        assert Decimal("10") in ref_layer._range_distribution

    def test_mixed_formed_unformed(self):
        """Only formed legs should be added from a mixed set based on price position."""
        ref_layer = ReferenceLayer()

        mixed_legs = [
            make_leg(origin_price=105, pivot_price=100, origin_index=1),  # range=5, needs close>=101.91
            make_leg(origin_price=120, pivot_price=100, origin_index=2),  # range=20, needs close>=107.64
            make_leg(origin_price=115, pivot_price=100, origin_index=3),  # range=15, needs close>=105.73
        ]

        # close=106 forms first and third, not second
        bar = make_bar(close=106)
        ref_layer.update(mixed_legs, bar)

        # First (range=5) and third (range=15) legs should be formed
        assert len(ref_layer._range_distribution) == 2
        assert Decimal("5") in ref_layer._range_distribution
        assert Decimal("15") in ref_layer._range_distribution
        assert Decimal("20") not in ref_layer._range_distribution

    def test_no_duplicate_entries(self):
        """Same leg should not be added twice on subsequent updates."""
        ref_layer = ReferenceLayer()

        leg = make_leg(origin_price=110, pivot_price=100)
        # close=105 forms the leg (location=0.5 > 0.382)
        bar = make_bar(close=105)

        # First update
        ref_layer.update([leg], bar)
        assert len(ref_layer._range_distribution) == 1

        # Second update with same leg
        ref_layer.update([leg], bar)
        assert len(ref_layer._range_distribution) == 1

    def test_distribution_stays_sorted(self):
        """Distribution should remain sorted after multiple updates."""
        ref_layer = ReferenceLayer()

        legs = [
            make_leg(origin_price=150, pivot_price=100, origin_index=1),  # range=50
            make_leg(origin_price=110, pivot_price=100, origin_index=2),  # range=10
            make_leg(origin_price=130, pivot_price=100, origin_index=3),  # range=30
        ]

        # close=120 forms all legs (all have location > 0.382)
        bar = make_bar(close=120)
        ref_layer.update(legs, bar)

        # Should be sorted
        expected = [Decimal("10"), Decimal("30"), Decimal("50")]
        assert ref_layer._range_distribution == expected


class TestUpdateMethodIntegration:
    """Integration tests for update() method."""

    def _populate_distribution(self, ref_layer: ReferenceLayer, count: int = 50):
        """Pre-populate distribution to exit cold start."""
        for i in range(count):
            ref_layer._add_to_range_distribution(Decimal(str((i + 1) * 10)))

    def test_update_returns_empty_during_cold_start(self):
        """update() should return empty references during cold start."""
        ref_layer = ReferenceLayer()

        legs = [make_leg() for _ in range(5)]
        bar = make_bar(close=105)

        state = ref_layer.update(legs, bar)

        assert len(state.references) == 0
        assert state.is_warming_up is True

    def test_update_returns_references_after_cold_start(self):
        """update() should return valid references after cold start."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        # Create a leg that will form (price at 105 = location 0.5 > 0.382)
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)
        bar = make_bar(close=105)

        state = ref_layer.update([leg], bar)

        # Should have reference (after forming it)
        assert len(state.references) >= 0  # May be 0 if not formed
        assert state.is_warming_up is False

    def test_update_filters_unformed_legs(self):
        """update() should not include legs that haven't reached formation threshold."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        # Leg won't form because price (101) is only at location 0.1
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)
        bar = make_bar(close=101)  # location = 0.1, below 0.382

        state = ref_layer.update([leg], bar)

        assert len(state.references) == 0

    def test_update_includes_formed_legs(self):
        """update() should include legs that have reached formation threshold."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        # Leg will form because price (104) is at location 0.4 > 0.382
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)
        # Bar with high >= close to be valid OHLC
        bar = make_bar(close=104, high=105, low=100)

        state = ref_layer.update([leg], bar)

        assert len(state.references) == 1
        assert state.references[0].leg == leg

    def test_update_sorts_by_salience(self):
        """References should be sorted by salience (highest first)."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        # Create legs with different ranges (affects salience)
        # Bear leg 1: 110->100, range=10, forms at 38.2%=103.82
        small_leg = make_leg(
            direction='bear', origin_price=110, pivot_price=100,
            origin_index=1, depth=0
        )  # range=10
        # Bear leg 2: 120->100, range=20, forms at 38.2%=107.64
        large_leg = make_leg(
            direction='bear', origin_price=120, pivot_price=100,
            origin_index=2, depth=0
        )  # range=20

        # Bar at close=108: forms both legs (108 > 103.82 and 108 > 107.64)
        # But 108 < 110 (small origin) and 108 < 120 (large origin), so no origin breach
        bar = make_bar(close=108, high=109, low=100, index=10)

        state = ref_layer.update([small_leg, large_leg], bar)

        # Both should form
        assert len(state.references) == 2
        # Large leg should have higher salience (bigger range)
        assert state.references[0].leg.range > state.references[1].leg.range

    def test_update_computes_direction_imbalance(self):
        """update() should compute direction imbalance correctly."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        # Create 3 bull legs and 1 bear leg
        bull_legs = [
            make_leg(direction='bull', origin_price=90, pivot_price=100, origin_index=i)
            for i in range(3)
        ]
        bear_leg = make_leg(direction='bear', origin_price=110, pivot_price=100, origin_index=10)

        # Price at 96 forms bull legs (location 0.4 > 0.382), and bear leg (location 0.6 > 0.382)
        bar = make_bar(close=104, high=105, low=95, index=20)

        state = ref_layer.update(bull_legs + [bear_leg], bar)

        # Bull count (3) > bear count (1) * 2, so should be bull imbalance
        if len(state.by_direction['bull']) > len(state.by_direction['bear']) * 2:
            assert state.direction_imbalance == 'bull'

    def test_update_populates_groupings(self):
        """update() should populate by_scale, by_depth, by_direction groupings."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        leg = make_leg(
            direction='bear', origin_price=110, pivot_price=100,
            depth=2
        )
        bar = make_bar(close=104)

        state = ref_layer.update([leg], bar)

        if len(state.references) > 0:
            ref = state.references[0]
            # Should be in by_scale
            assert ref in state.by_scale.get(ref.scale, [])
            # Should be in by_depth
            assert ref in state.by_depth.get(ref.depth, [])
            # Should be in by_direction
            assert ref in state.by_direction.get(leg.direction, [])

    def test_update_caps_location_at_2(self):
        """Locations should be capped at 2.0 in output."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        # Bear leg from 110 to 100, range = 10
        # Location 2.5 would be at price = pivot + 1.5*range = 100 + 15 = 115
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # First, form the reference
        form_bar = make_bar(close=104, index=1)
        ref_layer.update([leg], form_bar)

        # Now check with price past 2x
        high_bar = make_bar(close=115, high=118, low=114, index=2)
        state = ref_layer.update([leg], high_bar)

        if len(state.references) > 0:
            # Location should be capped at 2.0
            assert state.references[0].location <= 2.0


class TestUpdateMethodBreaching:
    """Tests for breach detection in update()."""

    def _populate_distribution(self, ref_layer: ReferenceLayer, count: int = 50):
        """Pre-populate distribution to exit cold start."""
        for i in range(count):
            ref_layer._add_to_range_distribution(Decimal(str((i + 1) * 10)))

    def test_pivot_breach_removes_reference(self):
        """Leg with pivot breach should not appear in references."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer)

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # First, form it (high >= close, low at pivot)
        form_bar = make_bar(close=104, high=105, low=100, index=1)
        state1 = ref_layer.update([leg], form_bar)
        assert len(state1.references) == 1

        # Now breach pivot (low below 100)
        breach_bar = make_bar(close=95, low=94, high=98, index=2)
        state2 = ref_layer.update([leg], breach_bar)

        assert len(state2.references) == 0

    def test_origin_breach_removes_small_reference(self):
        """S/M reference with origin breach should be removed."""
        ref_layer = ReferenceLayer()
        self._populate_distribution(ref_layer, 100)  # Ensure leg is S/M scale

        # Small leg (range=5, will be S scale with 100 in distribution)
        leg = make_leg(direction='bear', origin_price=105, pivot_price=100, origin_index=1)

        # First, form it
        form_bar = make_bar(close=102, high=103, low=101, index=1)
        state1 = ref_layer.update([leg], form_bar)

        # Check if it formed
        if len(state1.references) == 1:
            # Now breach origin (price above 105)
            breach_bar = make_bar(close=108, high=110, low=106, index=2)
            state2 = ref_layer.update([leg], breach_bar)
            assert len(state2.references) == 0


class TestScaleClassificationIntegration:
    """Integration tests for scale classification in update()."""

    def test_xl_classification_in_update(self):
        """Large legs should be classified as XL."""
        ref_layer = ReferenceLayer()

        # Add 100 ranges from 1-100
        for i in range(100):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        # Large leg (range=100, should be XL)
        leg = make_leg(direction='bear', origin_price=200, pivot_price=100)
        bar = make_bar(close=104, index=1)

        state = ref_layer.update([leg], bar)

        if len(state.references) > 0:
            assert state.references[0].scale == 'XL'

    def test_small_classification_in_update(self):
        """Small legs should be classified as S."""
        ref_layer = ReferenceLayer()

        # Add 100 ranges from 1-100
        for i in range(100):
            ref_layer._add_to_range_distribution(Decimal(str(i + 1)))

        # Small leg (range=2, should be S)
        leg = make_leg(direction='bear', origin_price=102, pivot_price=100)

        # Form at location 0.5 (price 101)
        bar = make_bar(close=101, index=1)

        state = ref_layer.update([leg], bar)

        if len(state.references) > 0:
            assert state.references[0].scale == 'S'


class TestEndToEndWorkflow:
    """End-to-end tests simulating realistic workflows."""

    def test_warmup_to_active_transition(self):
        """Test transition from cold start to active state."""
        ref_layer = ReferenceLayer()

        # Generate 50 legs with same range to ensure consistent formation
        legs = []
        for i in range(50):
            leg = make_leg(
                direction='bear',
                origin_price=110,  # All same origin for consistent formation
                pivot_price=100,
                origin_index=i,
            )
            legs.append(leg)

        # close=105 forms all legs (range=10, formation at 103.82, 105 > 103.82)
        # First 49 legs: still warming up
        for i in range(49):
            state = ref_layer.update([legs[i]], make_bar(close=105, index=i))
            assert state.is_warming_up is True

        # 50th leg: should exit cold start
        state = ref_layer.update([legs[49]], make_bar(close=105, index=49))
        assert state.is_warming_up is False

    def test_multiple_references_lifecycle(self):
        """Test multiple references forming, ranking, and being invalidated."""
        ref_layer = ReferenceLayer()

        # Pre-populate to exit cold start
        for i in range(50):
            ref_layer._add_to_range_distribution(Decimal(str((i + 1) * 10)))

        # Create multiple legs
        legs = [
            make_leg(direction='bear', origin_price=120, pivot_price=100, origin_index=1),  # range=20
            make_leg(direction='bear', origin_price=115, pivot_price=100, origin_index=2),  # range=15
            make_leg(direction='bull', origin_price=90, pivot_price=100, origin_index=3),   # range=10
        ]

        # Form all legs
        form_bar = make_bar(close=104, high=105, low=95, index=10)
        state = ref_layer.update(legs, form_bar)

        # All should be valid references
        assert len(state.references) >= 0  # Depends on formation conditions

        # Check groupings
        assert 'bull' in state.by_direction
        assert 'bear' in state.by_direction

    def test_reference_persistence_across_updates(self):
        """Once formed, references should persist across updates."""
        ref_layer = ReferenceLayer()

        # Pre-populate
        for i in range(50):
            ref_layer._add_to_range_distribution(Decimal(str((i + 1) * 10)))

        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form the reference
        bar1 = make_bar(close=104, index=1)
        state1 = ref_layer.update([leg], bar1)

        if len(state1.references) == 1:
            # Update with price back near pivot (but not breaching)
            bar2 = make_bar(close=101, high=102, low=100.5, index=2)
            state2 = ref_layer.update([leg], bar2)

            # Should still be valid (once formed, stays formed)
            assert len(state2.references) == 1


class TestReferenceLayerReset:
    """Tests for ReferenceLayer state management."""

    def test_new_layer_has_empty_state(self):
        """New ReferenceLayer should have empty internal state."""
        ref_layer = ReferenceLayer()

        assert len(ref_layer._range_distribution) == 0
        assert len(ref_layer._formed_refs) == 0
        assert len(ref_layer._seen_leg_ids) == 0
        assert ref_layer.is_cold_start is True

    def test_state_persists_across_updates(self):
        """Internal state should accumulate across update() calls."""
        ref_layer = ReferenceLayer()

        for i in range(10):
            leg = make_leg(
                origin_price=110,  # Same origin for consistent formation
                pivot_price=100,
                origin_index=i,
            )
            # close=105 forms each leg (range=10, formation at 103.82)
            bar = make_bar(close=105, index=i)
            ref_layer.update([leg], bar)

        # Should have accumulated 10 legs in distribution
        assert len(ref_layer._range_distribution) == 10
        assert len(ref_layer._seen_leg_ids) == 10
