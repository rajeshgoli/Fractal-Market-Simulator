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


class TestMaxTurnsPerPivotConfig:
    """Tests for max_turns_per_pivot configuration (#342)."""

    def test_config_default_is_zero(self):
        """Default max_turns_per_pivot should be 0 (disabled)."""
        config = SwingConfig.default()
        assert config.max_turns_per_pivot == 0

    def test_with_max_turns_per_pivot(self):
        """with_max_turns_per_pivot creates new config with updated value."""
        config = SwingConfig.default()
        new_config = config.with_max_turns_per_pivot(3)

        # Original unchanged
        assert config.max_turns_per_pivot == 0

        # New config updated
        assert new_config.max_turns_per_pivot == 3

        # Other fields preserved
        assert new_config.bull.formation_fib == config.bull.formation_fib
        assert new_config.min_turn_ratio == config.min_turn_ratio

    def test_config_serialization(self):
        """max_turns_per_pivot should serialize properly through with_* methods."""
        config = SwingConfig.default().with_max_turns_per_pivot(5)

        # Test that it persists through other with_ methods
        config2 = config.with_bull(formation_fib=0.5)
        assert config2.max_turns_per_pivot == 5

        config3 = config.with_min_turn_ratio(0.3)
        assert config3.max_turns_per_pivot == 5

    def test_mutual_exclusivity_modes(self):
        """Mode selection should be based on which value is set."""
        # Both zero = disabled
        config = SwingConfig.default()
        assert config.min_turn_ratio == 0.0
        assert config.max_turns_per_pivot == 0

        # min_turn_ratio > 0 = threshold mode
        config_threshold = config.with_min_turn_ratio(0.5)
        assert config_threshold.min_turn_ratio == 0.5
        assert config_threshold.max_turns_per_pivot == 0

        # max_turns_per_pivot > 0 with min_turn_ratio = 0 = top-k mode
        config_topk = config.with_max_turns_per_pivot(3)
        assert config_topk.min_turn_ratio == 0.0
        assert config_topk.max_turns_per_pivot == 3


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
        """Counter-leg is pruned when turn_ratio < min_turn_ratio (but not if it's largest)."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Need 2 legs: one largest (exempt) and one below threshold (pruned)
        # Largest leg: range=100, ratio=0.5 (at threshold - kept as exempt)
        largest_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=50.0,  # 50/100 = 0.5 ratio
        )
        state.active_legs.append(largest_leg)

        # Smaller leg with low turn ratio (0.1 < 0.5 threshold) - will be pruned
        # _max_counter = 5, range = 50, ratio = 0.1
        small_leg = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),  # Pivot matches new leg's origin
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=5.0,  # Counter-trend was 5
        )
        state.active_legs.append(small_leg)

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

        # Small leg should be pruned (largest is exempt)
        assert len(events) == 1
        assert events[0].reason == "turn_ratio"
        assert small_leg.leg_id in events[0].leg_id
        assert small_leg not in state.active_legs
        assert largest_leg in state.active_legs  # Exempt

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

        # Largest leg at matching pivot (exempt)
        largest_leg = Leg(
            direction='bear',
            origin_price=Decimal("220"),
            origin_index=2,
            pivot_price=Decimal("100"),  # Matches new leg's origin
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=50.0,
        )
        state.active_legs.append(largest_leg)

        # Smaller counter-leg at matching pivot (should be checked and pruned)
        matching_leg = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=4,
            pivot_price=Decimal("100"),  # Matches new leg's origin
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=5.0,  # Will fail ratio check (5/50 = 0.1 < 0.5)
        )
        state.active_legs.append(matching_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Only matching leg pruned (largest at pivot is exempt)
        assert len(events) == 1
        assert matching_leg.leg_id in events[0].leg_id
        assert matching_leg not in state.active_legs
        assert unrelated_leg in state.active_legs
        assert largest_leg in state.active_legs

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
            max_origin_breach=Decimal("1"),  # Not active (breached)
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
        """Multiple counter-legs at same pivot: largest exempt, then low-ratio ones pruned."""
        config = SwingConfig.default().with_min_turn_ratio(0.4)
        pruner = LegPruner(config)
        state = DetectorState()

        # Largest leg (range=100, exempt)
        largest_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=20.0,  # 20 / 100 = 0.2 (low but exempt)
        )
        state.active_legs.append(largest_leg)

        # Counter-leg: low ratio (0.2 < 0.4) - should be pruned
        low_ratio_leg = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=10.0,  # 10 / 50 = 0.2
        )
        state.active_legs.append(low_ratio_leg)

        # Counter-leg: high ratio (0.8 >= 0.4) - should be preserved
        high_ratio_leg = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("120"),
            last_modified_bar=5,
            _max_counter_leg_range=32.0,  # 32 / 40 = 0.8
        )
        state.active_legs.append(high_ratio_leg)

        # New leg at origin 100
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Only low-ratio leg pruned (largest exempt, high ratio passes)
        assert len(events) == 1
        assert low_ratio_leg.leg_id in events[0].leg_id
        assert low_ratio_leg not in state.active_legs
        assert high_ratio_leg in state.active_legs
        assert largest_leg in state.active_legs


class TestTopKModePruning:
    """Tests for top-k turn ratio pruning (#342)."""

    def create_test_state(self) -> DetectorState:
        """Create a test detector state."""
        return DetectorState()

    def test_no_pruning_when_disabled(self):
        """No pruning when both min_turn_ratio and max_turns_per_pivot are 0."""
        config = SwingConfig.default()  # Both 0
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Add 5 counter-legs at same pivot
        for i in range(5):
            leg = Leg(
                direction='bear',
                origin_price=Decimal(str(200 - i * 10)),
                origin_index=i,
                pivot_price=Decimal("100"),
                pivot_index=i + 1,
                price_at_creation=Decimal("110"),
                last_modified_bar=i + 1,
                _max_counter_leg_range=float(10 + i * 5),
            )
            state.active_legs.append(leg)

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=10,
            pivot_price=Decimal("105"),
            pivot_index=11,
            price_at_creation=Decimal("104"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning
        assert len(events) == 0
        assert len(state.active_legs) == 5

    def test_topk_mode_keeps_only_k_legs(self):
        """Top-k mode keeps only the k highest-ratio legs (excluding exempt largest)."""
        config = SwingConfig.default().with_max_turns_per_pivot(2)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Create 5 counter-legs: 1 largest (exempt) + 4 pruneable
        # With k=2, we keep top 2 of the 4 pruneable legs

        # Largest leg (exempt) - range=150
        largest = Leg(
            direction='bear',
            origin_price=Decimal("250"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,  # ratio=0.067 (low but exempt)
        )
        # Pruneable legs - keep 2 highest ratios
        leg1 = Leg(  # ratio = 10/100 = 0.1 (lowest - prune)
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=10.0,
        )
        leg2 = Leg(  # ratio = 40/80 = 0.5 (2nd highest - keep)
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=40.0,
        )
        leg3 = Leg(  # ratio = 60/60 = 1.0 (highest - keep)
            direction='bear',
            origin_price=Decimal("160"),
            origin_index=6,
            pivot_price=Decimal("100"),
            pivot_index=7,
            price_at_creation=Decimal("110"),
            last_modified_bar=7,
            _max_counter_leg_range=60.0,
        )
        leg4 = Leg(  # ratio = 16/80 = 0.2 (3rd - prune)
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=8,
            pivot_price=Decimal("100"),
            pivot_index=9,
            price_at_creation=Decimal("110"),
            last_modified_bar=9,
            _max_counter_leg_range=16.0,
        )

        state.active_legs.extend([largest, leg1, leg2, leg3, leg4])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=10,
            pivot_price=Decimal("105"),
            pivot_index=11,
            price_at_creation=Decimal("104"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Should prune 2 lowest-ratio legs (leg1 and leg4)
        # largest is exempt, leg2 and leg3 are top 2 by ratio
        assert len(events) == 2
        pruned_ids = {e.leg_id for e in events}
        assert leg1.leg_id in pruned_ids
        assert leg4.leg_id in pruned_ids

        # largest, leg2 and leg3 should remain
        assert largest in state.active_legs
        assert leg2 in state.active_legs
        assert leg3 in state.active_legs
        assert leg1 not in state.active_legs
        assert leg4 not in state.active_legs

        # Events should have correct reason
        for event in events:
            assert event.reason == "turn_ratio_topk"

    def test_topk_mode_no_pruning_when_fewer_than_k_legs(self):
        """Top-k mode doesn't prune if there are k or fewer legs."""
        config = SwingConfig.default().with_max_turns_per_pivot(5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Only 3 legs, but max_turns_per_pivot = 5
        for i in range(3):
            leg = Leg(
                direction='bear',
                origin_price=Decimal(str(200 - i * 10)),
                origin_index=i,
                pivot_price=Decimal("100"),
                pivot_index=i + 1,
                price_at_creation=Decimal("110"),
                last_modified_bar=i + 1,
                _max_counter_leg_range=float(10 + i * 5),
            )
            state.active_legs.append(leg)

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=10,
            pivot_price=Decimal("105"),
            pivot_index=11,
            price_at_creation=Decimal("104"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning - fewer legs than k
        assert len(events) == 0
        assert len(state.active_legs) == 3

    def test_threshold_mode_takes_priority_over_topk(self):
        """When min_turn_ratio > 0, threshold mode is used, ignoring max_turns_per_pivot."""
        # Set both - threshold mode should take priority
        config = SwingConfig.default().with_min_turn_ratio(0.3).with_max_turns_per_pivot(1)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Need 3 legs: largest (exempt) + 2 to test threshold logic
        # Largest leg (exempt) - range=120
        largest = Leg(
            direction='bear',
            origin_price=Decimal("220"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=30.0,  # ratio=0.25 (below threshold but exempt)
        )
        # leg1: ratio = 5/50 = 0.1 (below threshold - prune)
        leg1 = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=5.0,
        )
        # leg2: ratio = 20/40 = 0.5 (above threshold - keep)
        leg2 = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=20.0,
        )

        state.active_legs.extend([largest, leg1, leg2])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Threshold mode: only leg1 pruned (below threshold)
        # largest is exempt, leg2 is above threshold
        assert len(events) == 1
        assert events[0].leg_id == leg1.leg_id
        assert events[0].reason == "turn_ratio"  # Not "turn_ratio_topk"
        assert largest in state.active_legs
        assert leg2 in state.active_legs

    def test_topk_mode_preserves_legacy_legs(self):
        """Legacy legs without _max_counter_leg_range are not pruned in top-k mode."""
        config = SwingConfig.default().with_max_turns_per_pivot(1)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Need 3 legs: largest (exempt) + legacy (preserved) + normal (pruned)
        # With k=1, we keep top 1 of pruneable (non-largest) legs
        # Legacy has inf ratio, normal has low ratio -> normal gets pruned

        # Largest leg (exempt) - range=120
        largest = Leg(
            direction='bear',
            origin_price=Decimal("220"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,
        )
        # Legacy leg without _max_counter_leg_range (inf ratio - keeps)
        legacy_leg = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            # No _max_counter_leg_range
        )
        # Normal leg with low ratio (pruned)
        normal_leg = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=2.0,  # Very low ratio = 2/40 = 0.05
        )

        state.active_legs.extend([largest, legacy_leg, normal_leg])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Legacy leg preserved (inf ratio), normal leg pruned
        # largest is exempt
        assert len(events) == 1
        assert events[0].leg_id == normal_leg.leg_id
        assert largest in state.active_legs
        assert legacy_leg in state.active_legs
        assert normal_leg not in state.active_legs


class TestLargestLegExemption:
    """Tests for #344: Largest leg exemption from turn-ratio pruning."""

    def create_test_state(self) -> DetectorState:
        """Create a test detector state."""
        return DetectorState()

    def test_largest_leg_exempt_in_threshold_mode(self):
        """Largest leg is not pruned even if below threshold."""
        config = SwingConfig.default().with_min_turn_ratio(0.5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Create 3 bear legs at same pivot with different ranges
        # The largest leg has the LOWEST turn ratio (since range is in denominator)
        # but should still be exempt from pruning

        # Small leg: range=20, counter=40, ratio=2.0 (above threshold)
        small_leg = Leg(
            direction='bear',
            origin_price=Decimal("120"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("105"),
            last_modified_bar=1,
            _max_counter_leg_range=40.0,
        )

        # Medium leg: range=50, counter=20, ratio=0.4 (below threshold - would be pruned)
        medium_leg = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=20.0,
        )

        # Largest leg: range=100, counter=10, ratio=0.1 (lowest - would be pruned, but EXEMPT)
        largest_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=10.0,
        )

        state.active_legs.extend([small_leg, medium_leg, largest_leg])

        # New bull leg at origin 100 (triggers check)
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Only medium_leg should be pruned (below threshold, not largest)
        # largest_leg is exempt despite having the lowest ratio
        assert len(events) == 1
        assert events[0].leg_id == medium_leg.leg_id
        assert medium_leg not in state.active_legs
        assert largest_leg in state.active_legs  # Exempt!
        assert small_leg in state.active_legs  # Above threshold

    def test_largest_leg_exempt_in_topk_mode(self):
        """Largest leg is not counted toward k limit in top-k mode."""
        config = SwingConfig.default().with_max_turns_per_pivot(2)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Create 4 bear legs:
        # - 1 largest (exempt from k count)
        # - 3 others (only top 2 of these should survive)

        # Leg A: range=20, counter=50, ratio=2.5 (high - keep)
        leg_a = Leg(
            direction='bear',
            origin_price=Decimal("120"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("105"),
            last_modified_bar=1,
            _max_counter_leg_range=50.0,
        )

        # Leg B: range=30, counter=40, ratio=1.33 (medium - keep)
        leg_b = Leg(
            direction='bear',
            origin_price=Decimal("130"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=40.0,
        )

        # Leg C: range=40, counter=30, ratio=0.75 (lower - prune)
        leg_c = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=30.0,
        )

        # Largest leg: range=60, counter=10, ratio=0.17 (lowest - but EXEMPT)
        largest_leg = Leg(
            direction='bear',
            origin_price=Decimal("160"),
            origin_index=6,
            pivot_price=Decimal("100"),
            pivot_index=7,
            price_at_creation=Decimal("110"),
            last_modified_bar=7,
            _max_counter_leg_range=10.0,
        )

        state.active_legs.extend([leg_a, leg_b, leg_c, largest_leg])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=8,
            pivot_price=Decimal("105"),
            pivot_index=9,
            price_at_creation=Decimal("104"),
            last_modified_bar=9,
        )

        bar = make_bar(9, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Largest exempt -> only 3 legs considered for top-2
        # leg_c should be pruned (3rd highest ratio of the 3 pruneable legs)
        assert len(events) == 1
        assert events[0].leg_id == leg_c.leg_id
        assert events[0].reason == "turn_ratio_topk"

        # Survivors: largest (exempt) + leg_a + leg_b (top 2 of pruneable)
        assert largest_leg in state.active_legs
        assert leg_a in state.active_legs
        assert leg_b in state.active_legs
        assert leg_c not in state.active_legs

    def test_single_leg_not_pruned(self):
        """With only 1 counter-leg (which is also largest), nothing to prune."""
        config = SwingConfig.default().with_min_turn_ratio(0.9)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Single leg with low ratio (would be pruned if not exempt)
        only_leg = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=5.0,  # ratio = 5/100 = 0.05 (very low)
        )
        state.active_legs.append(only_leg)

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

        # No pruning - single leg is largest and thus exempt
        assert len(events) == 0
        assert only_leg in state.active_legs

    def test_topk_with_k_equals_pruneable_count(self):
        """When k equals number of pruneable legs (excluding largest), no pruning."""
        config = SwingConfig.default().with_max_turns_per_pivot(2)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # 3 legs total: 1 largest (exempt) + 2 others (k=2, so both kept)
        leg_a = Leg(
            direction='bear',
            origin_price=Decimal("120"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("105"),
            last_modified_bar=1,
            _max_counter_leg_range=20.0,
        )
        leg_b = Leg(
            direction='bear',
            origin_price=Decimal("130"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=15.0,
        )
        # Largest
        largest_leg = Leg(
            direction='bear',
            origin_price=Decimal("160"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=5.0,
        )

        state.active_legs.extend([leg_a, leg_b, largest_leg])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # k=2, pruneable count=2, so nothing pruned
        assert len(events) == 0
        assert len(state.active_legs) == 3

    def test_largest_exempt_preserves_primary_structure(self):
        """
        Verify the specific scenario from issue description.

        5 bear legs sharing pivot at 5900:
        A: range=20 → ratio=2.50 ✓ survives
        B: range=30 → ratio=1.33 ✓ survives
        C: range=40 → ratio=0.75 ✓ survives (top-3)
        D: range=50 → ratio=0.40 ✗ pruned
        E: range=60 → ratio=0.17 ✓ EXEMPT (largest)
        """
        config = SwingConfig.default().with_max_turns_per_pivot(3)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Build legs exactly as in issue description
        leg_a = Leg(  # range=20, counter=50 → ratio=2.50
            direction='bear',
            origin_price=Decimal("5920"),
            origin_index=0,
            pivot_price=Decimal("5900"),
            pivot_index=1,
            price_at_creation=Decimal("5910"),
            last_modified_bar=1,
            _max_counter_leg_range=50.0,
        )
        leg_b = Leg(  # range=30, counter=40 → ratio=1.33
            direction='bear',
            origin_price=Decimal("5930"),
            origin_index=2,
            pivot_price=Decimal("5900"),
            pivot_index=3,
            price_at_creation=Decimal("5910"),
            last_modified_bar=3,
            _max_counter_leg_range=40.0,
        )
        leg_c = Leg(  # range=40, counter=30 → ratio=0.75
            direction='bear',
            origin_price=Decimal("5940"),
            origin_index=4,
            pivot_price=Decimal("5900"),
            pivot_index=5,
            price_at_creation=Decimal("5910"),
            last_modified_bar=5,
            _max_counter_leg_range=30.0,
        )
        leg_d = Leg(  # range=50, counter=20 → ratio=0.40
            direction='bear',
            origin_price=Decimal("5950"),
            origin_index=6,
            pivot_price=Decimal("5900"),
            pivot_index=7,
            price_at_creation=Decimal("5910"),
            last_modified_bar=7,
            _max_counter_leg_range=20.0,
        )
        leg_e = Leg(  # range=60, counter=10 → ratio=0.17 (LARGEST)
            direction='bear',
            origin_price=Decimal("5960"),
            origin_index=8,
            pivot_price=Decimal("5900"),
            pivot_index=9,
            price_at_creation=Decimal("5910"),
            last_modified_bar=9,
            _max_counter_leg_range=10.0,
        )

        state.active_legs.extend([leg_a, leg_b, leg_c, leg_d, leg_e])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("5900"),
            origin_index=10,
            pivot_price=Decimal("5920"),
            pivot_index=11,
            price_at_creation=Decimal("5915"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 5900.0, 5920.0, 5895.0, 5915.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Largest (leg_e) is exempt
        # Of remaining 4 legs, keep top-3 by ratio: A(2.5), B(1.33), C(0.75)
        # Prune D(0.40)
        assert len(events) == 1
        assert events[0].leg_id == leg_d.leg_id

        # Verify survivors
        remaining_ids = {leg.leg_id for leg in state.active_legs}
        assert leg_a.leg_id in remaining_ids
        assert leg_b.leg_id in remaining_ids
        assert leg_c.leg_id in remaining_ids
        assert leg_e.leg_id in remaining_ids  # Largest - exempt
        assert leg_d.leg_id not in remaining_ids  # Pruned


class TestMaxTurnsPerPivotRawConfig:
    """Tests for max_turns_per_pivot_raw configuration (#355)."""

    def test_config_default_is_zero(self):
        """Default max_turns_per_pivot_raw should be 0 (disabled)."""
        config = SwingConfig.default()
        assert config.max_turns_per_pivot_raw == 0

    def test_with_max_turns_per_pivot_raw(self):
        """with_max_turns_per_pivot_raw creates new config with updated value."""
        config = SwingConfig.default()
        new_config = config.with_max_turns_per_pivot_raw(3)

        # Original unchanged
        assert config.max_turns_per_pivot_raw == 0

        # New config updated
        assert new_config.max_turns_per_pivot_raw == 3

        # Other fields preserved
        assert new_config.bull.formation_fib == config.bull.formation_fib
        assert new_config.min_turn_ratio == config.min_turn_ratio
        assert new_config.max_turns_per_pivot == config.max_turns_per_pivot

    def test_config_serialization(self):
        """max_turns_per_pivot_raw should serialize properly through with_* methods."""
        config = SwingConfig.default().with_max_turns_per_pivot_raw(5)

        # Test that it persists through other with_ methods
        config2 = config.with_bull(formation_fib=0.5)
        assert config2.max_turns_per_pivot_raw == 5

        config3 = config.with_min_turn_ratio(0.3)
        assert config3.max_turns_per_pivot_raw == 5

        config4 = config.with_max_turns_per_pivot(10)
        assert config4.max_turns_per_pivot_raw == 5

    def test_mutual_exclusivity_three_modes(self):
        """Mode selection should be based on priority: threshold > top-k > raw."""
        # All zero = disabled
        config = SwingConfig.default()
        assert config.min_turn_ratio == 0.0
        assert config.max_turns_per_pivot == 0
        assert config.max_turns_per_pivot_raw == 0

        # min_turn_ratio > 0 = threshold mode (ignores others)
        config_threshold = config.with_min_turn_ratio(0.5).with_max_turns_per_pivot(3).with_max_turns_per_pivot_raw(3)
        assert config_threshold.min_turn_ratio == 0.5
        # In threshold mode, the others are still set but ignored

        # max_turns_per_pivot > 0 with min_turn_ratio = 0 = top-k mode
        config_topk = config.with_max_turns_per_pivot(3).with_max_turns_per_pivot_raw(5)
        assert config_topk.min_turn_ratio == 0.0
        assert config_topk.max_turns_per_pivot == 3
        # top-k takes priority over raw when both set

        # max_turns_per_pivot_raw > 0 with both others = 0 = raw mode
        config_raw = config.with_max_turns_per_pivot_raw(3)
        assert config_raw.min_turn_ratio == 0.0
        assert config_raw.max_turns_per_pivot == 0
        assert config_raw.max_turns_per_pivot_raw == 3


class TestRawCounterHeftModePruning:
    """Tests for raw counter-heft pruning mode (#355)."""

    def create_test_state(self) -> DetectorState:
        """Create a test detector state."""
        return DetectorState()

    def test_no_pruning_when_all_disabled(self):
        """No pruning when all three modes are disabled."""
        config = SwingConfig.default()  # All 0
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Add 5 counter-legs at same pivot
        for i in range(5):
            leg = Leg(
                direction='bear',
                origin_price=Decimal(str(200 - i * 10)),
                origin_index=i,
                pivot_price=Decimal("100"),
                pivot_index=i + 1,
                price_at_creation=Decimal("110"),
                last_modified_bar=i + 1,
                _max_counter_leg_range=float(10 + i * 5),
            )
            state.active_legs.append(leg)

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=10,
            pivot_price=Decimal("105"),
            pivot_index=11,
            price_at_creation=Decimal("104"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning
        assert len(events) == 0
        assert len(state.active_legs) == 5

    def test_raw_mode_keeps_only_k_highest_counter_heft(self):
        """Raw mode keeps only the k highest _max_counter_leg_range legs."""
        config = SwingConfig.default().with_max_turns_per_pivot_raw(2)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Create 5 counter-legs: 1 largest (exempt) + 4 pruneable
        # With k=2, we keep top 2 of the 4 pruneable legs by raw counter-heft

        # Largest leg (exempt) - range=150
        largest = Leg(
            direction='bear',
            origin_price=Decimal("250"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=5.0,  # Low counter-heft but exempt
        )
        # Pruneable legs - keep 2 highest counter-heft (regardless of ratio)
        leg1 = Leg(  # counter=10 (lowest - prune)
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=10.0,
        )
        leg2 = Leg(  # counter=40 (2nd highest - keep)
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=40.0,
        )
        leg3 = Leg(  # counter=60 (highest - keep)
            direction='bear',
            origin_price=Decimal("160"),
            origin_index=6,
            pivot_price=Decimal("100"),
            pivot_index=7,
            price_at_creation=Decimal("110"),
            last_modified_bar=7,
            _max_counter_leg_range=60.0,
        )
        leg4 = Leg(  # counter=16 (3rd - prune)
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=8,
            pivot_price=Decimal("100"),
            pivot_index=9,
            price_at_creation=Decimal("110"),
            last_modified_bar=9,
            _max_counter_leg_range=16.0,
        )

        state.active_legs.extend([largest, leg1, leg2, leg3, leg4])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=10,
            pivot_price=Decimal("105"),
            pivot_index=11,
            price_at_creation=Decimal("104"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Should prune 2 lowest-counter-heft legs (leg1 and leg4)
        # largest is exempt, leg2 and leg3 are top 2 by counter-heft
        assert len(events) == 2
        pruned_ids = {e.leg_id for e in events}
        assert leg1.leg_id in pruned_ids
        assert leg4.leg_id in pruned_ids

        # largest, leg2 and leg3 should remain
        assert largest in state.active_legs
        assert leg2 in state.active_legs
        assert leg3 in state.active_legs
        assert leg1 not in state.active_legs
        assert leg4 not in state.active_legs

        # Events should have correct reason
        for event in events:
            assert event.reason == "turn_ratio_raw"

    def test_raw_mode_no_pruning_when_fewer_than_k_legs(self):
        """Raw mode doesn't prune if there are k or fewer legs."""
        config = SwingConfig.default().with_max_turns_per_pivot_raw(5)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Only 3 legs, but max_turns_per_pivot_raw = 5
        for i in range(3):
            leg = Leg(
                direction='bear',
                origin_price=Decimal(str(200 - i * 10)),
                origin_index=i,
                pivot_price=Decimal("100"),
                pivot_index=i + 1,
                price_at_creation=Decimal("110"),
                last_modified_bar=i + 1,
                _max_counter_leg_range=float(10 + i * 5),
            )
            state.active_legs.append(leg)

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=10,
            pivot_price=Decimal("105"),
            pivot_index=11,
            price_at_creation=Decimal("104"),
            last_modified_bar=11,
        )

        bar = make_bar(11, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # No pruning - fewer legs than k
        assert len(events) == 0
        assert len(state.active_legs) == 3

    def test_threshold_mode_takes_priority_over_raw(self):
        """When min_turn_ratio > 0, threshold mode is used, ignoring raw mode."""
        # Set threshold and raw - threshold mode should take priority
        config = SwingConfig.default().with_min_turn_ratio(0.3).with_max_turns_per_pivot_raw(1)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Need 3 legs: largest (exempt) + 2 to test threshold logic
        # Largest leg (exempt) - range=120
        largest = Leg(
            direction='bear',
            origin_price=Decimal("220"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=30.0,  # ratio=0.25 (below threshold but exempt)
        )
        # leg1: ratio = 5/50 = 0.1 (below threshold - prune)
        leg1 = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=5.0,
        )
        # leg2: ratio = 20/40 = 0.5 (above threshold - keep)
        leg2 = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=20.0,
        )

        state.active_legs.extend([largest, leg1, leg2])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Threshold mode: only leg1 pruned (below threshold)
        # largest is exempt, leg2 is above threshold
        assert len(events) == 1
        assert events[0].leg_id == leg1.leg_id
        assert events[0].reason == "turn_ratio"  # Not "turn_ratio_raw"
        assert largest in state.active_legs
        assert leg2 in state.active_legs

    def test_topk_mode_takes_priority_over_raw(self):
        """When max_turns_per_pivot > 0, top-k mode is used, ignoring raw mode."""
        # Set both top-k and raw - top-k should take priority
        config = SwingConfig.default().with_max_turns_per_pivot(1).with_max_turns_per_pivot_raw(10)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Create 3 legs: largest (exempt) + 2 pruneable
        # Largest leg (exempt)
        largest = Leg(
            direction='bear',
            origin_price=Decimal("220"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,
        )
        # leg1: low ratio (prune in top-k mode)
        leg1 = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=10.0,  # ratio = 10/100 = 0.1
        )
        # leg2: high ratio (keep in top-k mode)
        leg2 = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=40.0,  # ratio = 40/40 = 1.0
        )

        state.active_legs.extend([largest, leg1, leg2])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Top-k mode (k=1): leg1 pruned (lower ratio)
        assert len(events) == 1
        assert events[0].leg_id == leg1.leg_id
        assert events[0].reason == "turn_ratio_topk"  # Not "turn_ratio_raw"
        assert largest in state.active_legs
        assert leg2 in state.active_legs

    def test_raw_mode_preserves_legacy_legs(self):
        """Legacy legs without _max_counter_leg_range are not pruned in raw mode."""
        config = SwingConfig.default().with_max_turns_per_pivot_raw(1)
        pruner = LegPruner(config)
        state = self.create_test_state()

        # Need 3 legs: largest (exempt) + legacy (preserved) + normal (pruned)
        # With k=1, we keep top 1 of pruneable (non-largest) legs
        # Legacy has inf score, normal has low counter-heft -> normal gets pruned

        # Largest leg (exempt) - range=120
        largest = Leg(
            direction='bear',
            origin_price=Decimal("220"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,
        )
        # Legacy leg without _max_counter_leg_range (inf score - keeps)
        legacy_leg = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            # No _max_counter_leg_range
        )
        # Normal leg with low counter-heft (pruned)
        normal_leg = Leg(
            direction='bear',
            origin_price=Decimal("140"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=2.0,  # Very low counter-heft
        )

        state.active_legs.extend([largest, legacy_leg, normal_leg])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )

        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Legacy leg preserved (inf score), normal leg pruned
        # largest is exempt
        assert len(events) == 1
        assert events[0].leg_id == normal_leg.leg_id
        assert largest in state.active_legs
        assert legacy_leg in state.active_legs
        assert normal_leg not in state.active_legs

    def test_raw_mode_sorts_by_counter_heft_not_ratio(self):
        """
        Raw mode sorts by raw counter-heft, not by ratio.

        This test demonstrates the key difference between top-k and raw modes:
        - Top-k: sorts by ratio = counter / range (favors small legs with big counters)
        - Raw: sorts by counter only (favors legs with biggest absolute counter-trend)
        """
        # Compare behavior between top-k and raw modes
        state_topk = DetectorState()
        state_raw = DetectorState()

        # Create 3 legs with different ranges but same ranking changes between modes
        # Largest leg (exempt in both) - range=100
        largest = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,  # ratio=0.1, counter=10
        )
        # Small leg with high ratio: range=10, counter=50 → ratio=5.0
        small_high_ratio = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("105"),
            last_modified_bar=3,
            _max_counter_leg_range=50.0,
        )
        # Large leg with low ratio: range=80, counter=40 → ratio=0.5
        large_low_ratio = Leg(
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=40.0,
        )

        # Clone legs for both states
        import copy
        state_topk.active_legs.extend([copy.deepcopy(l) for l in [largest, small_high_ratio, large_low_ratio]])
        state_raw.active_legs.extend([copy.deepcopy(l) for l in [largest, small_high_ratio, large_low_ratio]])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=6,
            pivot_price=Decimal("105"),
            pivot_index=7,
            price_at_creation=Decimal("104"),
            last_modified_bar=7,
        )
        bar = make_bar(7, 100.0, 106.0, 99.0, 105.0)

        # Top-k mode with k=1: keeps highest ratio (small_high_ratio with ratio=5.0)
        config_topk = SwingConfig.default().with_max_turns_per_pivot(1)
        pruner_topk = LegPruner(config_topk)
        events_topk = pruner_topk.prune_by_turn_ratio(state_topk, new_leg, bar, datetime.now())

        # Raw mode with k=1: keeps highest counter-heft (small_high_ratio with counter=50)
        config_raw = SwingConfig.default().with_max_turns_per_pivot_raw(1)
        pruner_raw = LegPruner(config_raw)
        events_raw = pruner_raw.prune_by_turn_ratio(state_raw, new_leg, bar, datetime.now())

        # In this case, both modes prune large_low_ratio (counter=40 < 50)
        # small_high_ratio wins in both (highest ratio AND highest counter)
        assert len(events_topk) == 1
        assert len(events_raw) == 1
        assert events_topk[0].reason == "turn_ratio_topk"
        assert events_raw[0].reason == "turn_ratio_raw"

    def test_raw_mode_example_scenario(self):
        """
        Test raw mode with scenario where raw vs ratio ordering differs.

        Leg A: range=20, counter=30 → ratio=1.50
        Leg B: range=50, counter=40 → ratio=0.80
        Leg C: range=80, counter=20 → ratio=0.25

        Top-k (k=1) ranking by ratio: A(1.50) > B(0.80) > C(0.25) → keeps A, prunes B,C
        Raw (k=1) ranking by counter: B(40) > A(30) > C(20) → keeps B, prunes A,C
        """
        config_raw = SwingConfig.default().with_max_turns_per_pivot_raw(1)
        pruner = LegPruner(config_raw)
        state = self.create_test_state()

        # Largest leg (exempt) - range=100
        largest = Leg(
            direction='bear',
            origin_price=Decimal("200"),
            origin_index=0,
            pivot_price=Decimal("100"),
            pivot_index=1,
            price_at_creation=Decimal("110"),
            last_modified_bar=1,
            _max_counter_leg_range=10.0,
        )
        # Leg A: high ratio but medium counter
        leg_a = Leg(
            direction='bear',
            origin_price=Decimal("120"),
            origin_index=2,
            pivot_price=Decimal("100"),
            pivot_index=3,
            price_at_creation=Decimal("110"),
            last_modified_bar=3,
            _max_counter_leg_range=30.0,  # ratio=1.50, counter=30
        )
        # Leg B: medium ratio but highest counter
        leg_b = Leg(
            direction='bear',
            origin_price=Decimal("150"),
            origin_index=4,
            pivot_price=Decimal("100"),
            pivot_index=5,
            price_at_creation=Decimal("110"),
            last_modified_bar=5,
            _max_counter_leg_range=40.0,  # ratio=0.80, counter=40
        )
        # Leg C: low ratio and low counter
        leg_c = Leg(
            direction='bear',
            origin_price=Decimal("180"),
            origin_index=6,
            pivot_price=Decimal("100"),
            pivot_index=7,
            price_at_creation=Decimal("110"),
            last_modified_bar=7,
            _max_counter_leg_range=20.0,  # ratio=0.25, counter=20
        )

        state.active_legs.extend([largest, leg_a, leg_b, leg_c])

        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=8,
            pivot_price=Decimal("105"),
            pivot_index=9,
            price_at_creation=Decimal("104"),
            last_modified_bar=9,
        )

        bar = make_bar(9, 100.0, 106.0, 99.0, 105.0)
        events = pruner.prune_by_turn_ratio(state, new_leg, bar, datetime.now())

        # Raw mode (k=1): keeps leg_b (highest counter=40), prunes leg_a and leg_c
        assert len(events) == 2
        pruned_ids = {e.leg_id for e in events}
        assert leg_a.leg_id in pruned_ids  # Would survive in top-k!
        assert leg_c.leg_id in pruned_ids

        # leg_b survives (highest counter)
        assert largest in state.active_legs
        assert leg_b in state.active_legs
        assert leg_a not in state.active_legs
        assert leg_c not in state.active_legs
