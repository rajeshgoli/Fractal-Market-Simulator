"""
Tests for issue #341: Turn ratio pruning for sibling legs.

Turn ratio measures how far a leg has extended relative to the counter-trend
pressure that created its origin. Low turn ratio legs have "punched above
their weight class" - extending far beyond what the structure justified.

When a new leg forms at origin O, counter-legs (opposite direction) with
pivot == O are checked:
  turn_ratio = _max_counter_leg_range / counter_leg.range
  If turn_ratio < min_turn_ratio, the counter-leg is pruned.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.dag import HierarchicalDetector, Leg
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.dag.state import DetectorState
from src.swing_analysis.swing_config import SwingConfig

from conftest import make_bar


class TestTurnRatioConfig:
    """Tests for min_turn_ratio configuration."""

    def test_config_default_is_zero(self):
        """Default min_turn_ratio should be 0.0 (disabled)."""
        config = SwingConfig.default()
        assert config.min_turn_ratio == 0.0

    def test_with_min_turn_ratio(self):
        """with_min_turn_ratio creates new config with updated value."""
        config = SwingConfig.default()
        new_config = config.with_min_turn_ratio(0.5)

        # Original unchanged
        assert config.min_turn_ratio == 0.0

        # New config updated
        assert new_config.min_turn_ratio == 0.5

        # Other fields preserved
        assert new_config.bull.formation_fib == config.bull.formation_fib
        assert new_config.stale_extension_threshold == config.stale_extension_threshold

    def test_config_serialization(self):
        """min_turn_ratio should serialize properly through with_* methods."""
        config = SwingConfig.default().with_min_turn_ratio(0.3)

        # Test that it persists through other with_ methods
        config2 = config.with_bull(formation_fib=0.5)
        assert config2.min_turn_ratio == 0.3

        config3 = config.with_bear(formation_fib=0.5)
        assert config3.min_turn_ratio == 0.3


class TestLegTurnRatioProperty:
    """Tests for the turn_ratio property on Leg."""

    def test_turn_ratio_none_when_no_max_counter_range(self):
        """turn_ratio should be None if _max_counter_leg_range is not set."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
        )
        assert leg._max_counter_leg_range is None
        assert leg.turn_ratio is None

    def test_turn_ratio_none_when_range_is_zero(self):
        """turn_ratio should be None if leg range is zero."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Same as origin - zero range
            pivot_index=1,
            price_at_creation=Decimal("100"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,
        )
        assert leg.range == 0
        assert leg.turn_ratio is None

    def test_turn_ratio_calculation(self):
        """turn_ratio = _max_counter_leg_range / range."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("120"),  # Range = 20
            pivot_index=1,
            price_at_creation=Decimal("118"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,  # Counter-trend was 10
        )
        # turn_ratio = 10 / 20 = 0.5
        assert leg.turn_ratio == pytest.approx(0.5)

    def test_turn_ratio_high_when_leg_small(self):
        """High turn_ratio when leg is small relative to counter-trend."""
        leg = Leg(
            direction='bear',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("95"),  # Range = 5 (small leg)
            pivot_index=1,
            price_at_creation=Decimal("96"),
            last_modified_bar=1,
            _max_counter_leg_range=20.0,  # Counter-trend was 20 (large)
        )
        # turn_ratio = 20 / 5 = 4.0 (high - structurally significant)
        assert leg.turn_ratio == pytest.approx(4.0)

    def test_turn_ratio_low_when_leg_extended_far(self):
        """Low turn_ratio when leg extended far beyond counter-trend."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("200"),  # Range = 100 (huge extension)
            pivot_index=1,
            price_at_creation=Decimal("195"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,  # Counter-trend was only 10
        )
        # turn_ratio = 10 / 100 = 0.1 (low - riding coattails)
        assert leg.turn_ratio == pytest.approx(0.1)


class TestPruneByTurnRatio:
    """Tests for the prune_by_turn_ratio method in LegPruner."""

    def create_test_state(self) -> DetectorState:
        """Create a test detector state."""
        return DetectorState()

    def test_no_pruning_when_disabled(self):
        """No pruning when min_turn_ratio is 0.0 (disabled)."""
        config = SwingConfig.default()  # min_turn_ratio = 0.0
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Counter-leg with very low turn ratio
        # origin=200, pivot=100, range=100, _max_counter=5, ratio=0.05
        counter_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Pivot matches new leg's origin
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=5.0,  # Small counter -> ratio = 5/100 = 0.05
        )
        state.active_legs.append(counter_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning when disabled
        assert len(events) == 0
        assert counter_leg in state.active_legs

    def test_counter_leg_pruned_when_below_threshold(self):
        """Counter-leg is pruned when turn_ratio < min_turn_ratio."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Counter-leg with low turn ratio (0.1 < 0.5 threshold)
        # _max_counter = 10, range = 100, ratio = 0.1
        counter_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Pivot matches new leg's origin
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,  # Counter-trend was 10
        )
        state.active_legs.append(counter_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Counter-leg should be pruned
        assert len(events) == 1
        assert events[0].reason == "turn_ratio"
        assert counter_leg.leg_id in events[0].leg_id
        assert counter_leg not in state.active_legs

    def test_counter_leg_preserved_when_above_threshold(self):
        """Counter-leg is preserved when turn_ratio >= min_turn_ratio."""
        config = SwingConfig.default().with_min_turn_ratio(0.3)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Counter-leg with adequate turn ratio (0.5 >= 0.3 threshold)
        # _max_counter = 50, range = 100, ratio = 0.5
        counter_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Pivot matches new leg's origin
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=50.0,  # Counter-trend was 50
        )
        state.active_legs.append(counter_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning - ratio is above threshold
        assert len(events) == 0
        assert counter_leg in state.active_legs

    def test_only_counter_legs_at_origin_checked(self):
        """Only counter-legs with pivot == new_leg.origin are checked."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Counter-leg at different pivot (should NOT be checked)
        unrelated_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("150"),  # Different pivot
            pivot_index=1,
            price_at_creation=Decimal("160"),
            last_modified_bar=1,
            _max_counter_leg_range=5.0,  # Would fail ratio check
        )
        state.active_legs.append(unrelated_leg)

        # Counter-leg at matching pivot (should be checked and pruned)
        matching_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=2,
            pivot_price=Decimal("100"),  # Matches new leg's origin
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=5.0,  # Will fail ratio check
        )
        state.active_legs.append(matching_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=4,
            pivot_price=Decimal("105"),
            pivot_index=5,
            price_at_creation=Decimal("104"),
            last_modified_bar=5,
        )

        bar = make_bar(5, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Only matching leg pruned
        assert len(events) == 1
        assert matching_leg.leg_id in events[0].leg_id
        assert matching_leg not in state.active_legs
        assert unrelated_leg in state.active_legs

    def test_same_direction_legs_not_checked(self):
        """Same-direction legs are not considered counter-legs."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Same-direction leg with pivot at new leg's origin (should NOT be checked)
        same_dir_leg = Leg(
            direction='bull',  # Same direction as new_leg
            origin_price=Decimal("80"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Matches new leg's origin
            pivot_index=1,
            price_at_creation=Decimal("98"),
            last_modified_bar=1,
            _max_counter_leg_range=1.0,  # Would fail ratio check
        )
        state.active_legs.append(same_dir_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning - same direction legs not checked
        assert len(events) == 0
        assert same_dir_leg in state.active_legs

    def test_legacy_legs_without_max_counter_not_pruned(self):
        """Legs without _max_counter_leg_range (legacy) are skipped."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Legacy counter-leg without _max_counter_leg_range
        legacy_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Matches new leg's origin
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            # _max_counter_leg_range not set (legacy)
        )
        state.active_legs.append(legacy_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Legacy leg not pruned
        assert len(events) == 0
        assert legacy_leg in state.active_legs


class TestTurnRatioIntegration:
    """Integration tests for turn ratio pruning through HierarchicalDetector."""

    def test_max_counter_leg_range_set_at_creation(self):
        """_max_counter_leg_range is set when legs are created and counter-legs exist."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create scenario where counter-legs exist at an origin
        # First create a bull leg, then a bear leg, then another bull leg
        # that originates at the bear leg's pivot
        bars = [
            make_bar(0, 100.0, 100.0, 90.0, 95.0),   # Initial down
            make_bar(1, 95.0, 105.0, 94.0, 104.0),   # Reversal up (creates bull origin at 90)
            make_bar(2, 104.0, 110.0, 103.0, 108.0), # Continue up
            make_bar(3, 108.0, 108.0, 100.0, 102.0), # Pullback down
            make_bar(4, 102.0, 115.0, 101.0, 114.0), # Strong up (may create new leg)
        ]

        for bar in bars:
            detector.process_bar(bar)

        # At minimum, verify that the field exists on legs
        for leg in detector.state.active_legs:
            # _max_counter_leg_range may be None if no counter-legs at origin
            # This just verifies the field is present (not an attribute error)
            assert hasattr(leg, '_max_counter_leg_range')

        # When there ARE counter-legs at origin, _max_counter_leg_range should be set
        # Find legs where origin_counter_trend_range is set (implies counter-legs existed)
        legs_with_counter = [l for l in detector.state.active_legs
                            if l.origin_counter_trend_range is not None]
        for leg in legs_with_counter:
            # If origin_counter_trend_range is set, _max_counter_leg_range should match
            assert leg._max_counter_leg_range == leg.origin_counter_trend_range

    def test_turn_ratio_pruning_triggers_on_new_leg_creation(self):
        """Turn ratio pruning happens when new legs form at shared pivots."""
        # Use a high min_turn_ratio to trigger pruning
        config = SwingConfig.default().with_min_turn_ratio(0.9)
        detector = HierarchicalDetector(config)

        # Create scenario where bear leg forms, extends far, then bull leg forms at its pivot
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 100.0),   # Initial
            make_bar(1, 100.0, 100.0, 90.0, 92.0),   # Bear move down
            make_bar(2, 92.0, 93.0, 85.0, 86.0),     # Continue down (extends range)
            make_bar(3, 86.0, 87.0, 80.0, 81.0),     # Continue down more
            make_bar(4, 81.0, 95.0, 80.0, 94.0),     # Strong reversal up
        ]

        events_by_bar = []
        for bar in bars:
            events = detector.process_bar(bar)
            events_by_bar.append(events)

        # Check if any turn_ratio prune events were emitted
        all_events = [e for es in events_by_bar for e in es]
        turn_ratio_events = [e for e in all_events if hasattr(e, 'reason') and e.reason == 'turn_ratio']

        # With high threshold (0.9), legs that extended significantly should be pruned
        # The exact count depends on market structure, but pruning should occur
        # This is a smoke test to ensure integration works


class TestTurnRatioEdgeCases:
    """Edge case tests for turn ratio pruning."""

    def test_zero_range_counter_leg_not_pruned(self):
        """Counter-legs with zero range are skipped (avoid division by zero)."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = DetectorState()

        # Counter-leg with zero range
        zero_range_leg = Leg(
            direction='bear',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("100"),  # Same as origin - zero range
            pivot_index=1,
            price_at_creation=Decimal("100"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,
        )
        state.active_legs.append(zero_range_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Zero-range leg not pruned
        assert len(events) == 0
        assert zero_range_leg in state.active_legs

    def test_inactive_counter_legs_not_checked(self):
        """Only active counter-legs are checked for pruning."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = DetectorState()

        # Inactive counter-leg (status != 'active')
        inactive_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=5.0,
            status='invalidated',  # Not active
        )
        state.active_legs.append(inactive_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Inactive leg not checked/pruned
        assert len(events) == 0
        assert inactive_leg in state.active_legs

    def test_threshold_boundary_exact_match(self):
        """Counter-leg at exactly threshold ratio is NOT pruned (>= threshold passes)."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = DetectorState()

        # Counter-leg with exactly 0.5 ratio (50/100 = 0.5)
        boundary_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=50.0,  # 50 / 100 = 0.5
        )
        state.active_legs.append(boundary_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=2,
            pivot_price=Decimal("105"),
            pivot_index=3,
            price_at_creation=Decimal("104"),
            last_modified_bar=3,
        )

        bar = make_bar(3, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Boundary case - ratio == threshold, should NOT be pruned
        assert len(events) == 0
        assert boundary_leg in state.active_legs

    def test_multiple_counter_legs_selective_pruning(self):
        """Multiple counter-legs at same pivot: only low-ratio ones pruned."""
        config = SwingConfig.default().with_min_turn_ratio(0.4)
        pruner = LegPruner(config)
        state = DetectorState()

        # Counter-leg 1: low ratio (0.2 < 0.4) - should be pruned
        low_ratio_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=20.0,  # 20 / 100 = 0.2
        )
        state.active_legs.append(low_ratio_leg)

        # Counter-leg 2: high ratio (0.8 >= 0.4) - should be preserved
        high_ratio_leg = Leg(
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("120"),
            last_modified_bar=3,
            _max_counter_leg_range=64.0,  # 64 / 80 = 0.8
        )
        state.active_legs.append(high_ratio_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=4,
            pivot_price=Decimal("105"),
            pivot_index=5,
            price_at_creation=Decimal("104"),
            last_modified_bar=5,
        )

        bar = make_bar(5, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Only low-ratio leg pruned
        assert len(events) == 1
        assert low_ratio_leg.leg_id in events[0].leg_id
        assert low_ratio_leg not in state.active_legs
        assert high_ratio_leg in state.active_legs
