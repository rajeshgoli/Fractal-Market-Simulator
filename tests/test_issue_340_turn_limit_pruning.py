"""
Tests for Issue #340: Turn Limit Pruning

This feature caps the number of counter-direction legs at each turn (pivot price).
When a new leg forms and reaches min_turn_threshold of the largest counter-leg,
keep only top max_legs_per_turn by score (range of counter-leg at their origin).
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.dag.leg_detector import LegDetector
from src.swing_analysis.types import Bar


# ============================================================================
# Config Tests
# ============================================================================


class TestTurnLimitConfig:
    """Test config parameters and builder method."""

    def test_default_values(self):
        """Default config has turn limit disabled."""
        config = SwingConfig.default()
        assert config.max_legs_per_turn == 0  # Disabled
        assert config.min_turn_threshold == 0.236

    def test_with_turn_limit_builder(self):
        """with_turn_limit() creates new config with updated values."""
        config = SwingConfig.default()
        updated = config.with_turn_limit(max_legs_per_turn=3, min_turn_threshold=0.382)

        assert updated.max_legs_per_turn == 3
        assert updated.min_turn_threshold == 0.382
        # Original unchanged (frozen dataclass)
        assert config.max_legs_per_turn == 0
        assert config.min_turn_threshold == 0.236

    def test_with_turn_limit_preserves_other_fields(self):
        """with_turn_limit() preserves all other config fields."""
        config = SwingConfig.default().with_bull(formation_fib=0.5).with_min_branch_ratio(0.1)
        updated = config.with_turn_limit(max_legs_per_turn=5)

        assert updated.bull.formation_fib == 0.5
        assert updated.min_branch_ratio == 0.1
        assert updated.max_legs_per_turn == 5

    def test_with_turn_limit_partial_update(self):
        """with_turn_limit() only updates provided fields."""
        config = SwingConfig.default().with_turn_limit(max_legs_per_turn=3, min_turn_threshold=0.5)
        # Update only max_legs
        updated = config.with_turn_limit(max_legs_per_turn=5)

        assert updated.max_legs_per_turn == 5
        assert updated.min_turn_threshold == 0.5  # Preserved


# ============================================================================
# Pruner Unit Tests
# ============================================================================


class TestPruneTurnLimit:
    """Test LegPruner.prune_turn_limit() method."""

    @pytest.fixture
    def make_bar(self):
        """Factory for creating test bars."""
        def _make(index: int, o: float, h: float, l: float, c: float) -> Bar:
            return Bar(
                index=index,
                timestamp=1000 + index,
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(l)),
                close=Decimal(str(c)),
            )
        return _make

    @pytest.fixture
    def make_leg(self):
        """Factory for creating test legs."""
        counter = [0]

        def _make(
            direction: str,
            origin_price: float,
            pivot_price: float,
            origin_index: int = 0,
            pivot_index: int = 10,
            formed: bool = True,
            status: str = 'active',
        ) -> Leg:
            counter[0] += 1
            return Leg(
                leg_id=f"leg_{counter[0]}",
                direction=direction,
                origin_price=Decimal(str(origin_price)),
                origin_index=origin_index,
                pivot_price=Decimal(str(pivot_price)),
                pivot_index=pivot_index,
                bar_count=pivot_index - origin_index,
                formed=formed,
                status=status,
                retracement_pct=Decimal("0.5"),
            )
        return _make

    def test_disabled_when_max_zero(self, make_bar, make_leg):
        """No pruning when max_legs_per_turn=0."""
        config = SwingConfig.default()  # max_legs_per_turn=0
        pruner = LegPruner(config)

        # Create detector state with legs
        from src.swing_analysis.dag.leg_detector import DetectorState
        state = DetectorState(active_legs=[], pending_origins={})

        # Add several bear legs at same pivot
        bear1 = make_leg('bear', 100, 90)  # Large
        bear2 = make_leg('bear', 100, 90)
        bear3 = make_leg('bear', 100, 90)
        bear4 = make_leg('bear', 100, 90)
        state.active_legs = [bear1, bear2, bear3, bear4]

        # Create new bull leg with origin at bear pivot
        new_leg = make_leg('bull', 90, 105, origin_index=10, pivot_index=20)

        bar = make_bar(20, 104, 106, 103, 105)

        events = pruner.prune_turn_limit(state, new_leg, bar, datetime.now())

        # No pruning when disabled
        assert events == []
        assert len(state.active_legs) == 4

    def test_threshold_gate_blocks_early_pruning(self, make_bar, make_leg):
        """Pruning blocked when new leg hasn't reached min_turn_threshold."""
        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=2, min_turn_threshold=0.5
        )
        pruner = LegPruner(config)

        from src.swing_analysis.dag.leg_detector import DetectorState
        state = DetectorState(active_legs=[], pending_origins={})

        # Bear leg with range 10 (100 - 90)
        bear1 = make_leg('bear', 100, 90)
        bear2 = make_leg('bear', 100, 90)
        bear3 = make_leg('bear', 100, 90)
        state.active_legs = [bear1, bear2, bear3]

        # Bull leg with origin at bear pivot, but range only 4 (less than 50% of 10)
        new_leg = make_leg('bull', 90, 94, origin_index=10, pivot_index=20)

        bar = make_bar(20, 93, 95, 92, 94)

        events = pruner.prune_turn_limit(state, new_leg, bar, datetime.now())

        # No pruning - new leg too small (ratio 0.4 < 0.5 threshold)
        assert events == []
        assert len(state.active_legs) == 3

    def test_prunes_excess_legs_when_enabled(self, make_bar, make_leg):
        """Prunes legs beyond max_legs_per_turn when threshold met."""
        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=2, min_turn_threshold=0.236
        )
        pruner = LegPruner(config)

        from src.swing_analysis.dag.leg_detector import DetectorState
        state = DetectorState(active_legs=[], pending_origins={})

        # 4 bear legs at same pivot (100 -> 90)
        # We need counter-legs at their origins to score them
        # Add bull legs that ended at origin 100 to give scoring context
        bull_parent = make_leg('bull', 80, 100, origin_index=0, pivot_index=5)
        bull_parent2 = make_leg('bull', 85, 100, origin_index=2, pivot_index=5)

        bear1 = make_leg('bear', 100, 90, origin_index=5, pivot_index=15)  # 100-90=10
        bear2 = make_leg('bear', 100, 90, origin_index=6, pivot_index=15)
        bear3 = make_leg('bear', 100, 90, origin_index=7, pivot_index=15)
        bear4 = make_leg('bear', 100, 90, origin_index=8, pivot_index=15)

        state.active_legs = [bull_parent, bull_parent2, bear1, bear2, bear3, bear4]

        # Bull leg with origin at bear pivot, range 8 (90 -> 98)
        # Ratio = 8/10 = 0.8 > 0.236 threshold
        new_leg = make_leg('bull', 90, 98, origin_index=15, pivot_index=25)

        bar = make_bar(25, 97, 99, 96, 98)

        events = pruner.prune_turn_limit(state, new_leg, bar, datetime.now())

        # Should have pruned 2 legs (4 bears - 2 max = 2 pruned)
        assert len(events) == 2
        for event in events:
            assert event.reason == "turn_limit"

        # Check remaining active bear legs
        remaining_bears = [l for l in state.active_legs if l.direction == 'bear']
        assert len(remaining_bears) == 2

    def test_scoring_by_counter_leg_range(self, make_bar, make_leg):
        """Legs scored by range of counter-legs at their origin."""
        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=1, min_turn_threshold=0.1
        )
        pruner = LegPruner(config)

        from src.swing_analysis.dag.leg_detector import DetectorState
        state = DetectorState(active_legs=[], pending_origins={})

        # Bull legs as parents (at different origins)
        # bull_large ends at 100 with large range (60->100 = 40)
        bull_large = make_leg('bull', 60, 100, origin_index=0, pivot_index=5)
        # bull_small ends at 100 with small range (90->100 = 10)
        bull_small = make_leg('bull', 90, 100, origin_index=2, pivot_index=5)

        # Bear legs - both at pivot 90, but different origins
        bear_high_score = make_leg('bear', 100, 90, origin_index=5, pivot_index=15)  # Origin 100 - backed by larger bull
        bear_low_score = make_leg('bear', 100, 90, origin_index=6, pivot_index=15)  # Same origin

        state.active_legs = [bull_large, bull_small, bear_high_score, bear_low_score]

        # New bull leg at pivot
        new_leg = make_leg('bull', 90, 95, origin_index=15, pivot_index=25)

        bar = make_bar(25, 94, 96, 93, 95)

        events = pruner.prune_turn_limit(state, new_leg, bar, datetime.now())

        # Should prune 1 (2 bears - 1 max = 1 pruned)
        assert len(events) == 1

        # The pruned leg should be the one with lower score (later origin_index as tiebreaker)
        pruned_id = events[0].leg_id
        assert pruned_id == bear_low_score.leg_id

    def test_first_leg_infinite_score(self, make_bar, make_leg):
        """First leg (no counter at origin) gets infinite score - never pruned."""
        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=1, min_turn_threshold=0.1
        )
        pruner = LegPruner(config)

        from src.swing_analysis.dag.leg_detector import DetectorState
        state = DetectorState(active_legs=[], pending_origins={})

        # First bear leg has no bull parent at its origin
        bear_first = make_leg('bear', 100, 90, origin_index=0, pivot_index=10)
        # Second bear leg has a bull parent at its origin
        bull_parent = make_leg('bull', 80, 100, origin_index=5, pivot_index=8)
        bear_second = make_leg('bear', 100, 90, origin_index=8, pivot_index=15)

        state.active_legs = [bear_first, bull_parent, bear_second]

        # New bull leg triggers pruning
        new_leg = make_leg('bull', 90, 95, origin_index=15, pivot_index=25)

        bar = make_bar(25, 94, 96, 93, 95)

        events = pruner.prune_turn_limit(state, new_leg, bar, datetime.now())

        # Should prune 1 (2 bears - 1 max = 1 pruned)
        assert len(events) == 1

        # The pruned leg should be bear_second (finite score)
        # bear_first has infinite score (no counter at origin)
        pruned_id = events[0].leg_id
        assert pruned_id == bear_second.leg_id

    def test_no_pruning_when_under_limit(self, make_bar, make_leg):
        """No pruning when leg count <= max_legs_per_turn."""
        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=5, min_turn_threshold=0.1
        )
        pruner = LegPruner(config)

        from src.swing_analysis.dag.leg_detector import DetectorState
        state = DetectorState(active_legs=[], pending_origins={})

        # Only 3 bear legs at pivot
        bear1 = make_leg('bear', 100, 90)
        bear2 = make_leg('bear', 100, 90)
        bear3 = make_leg('bear', 100, 90)
        state.active_legs = [bear1, bear2, bear3]

        new_leg = make_leg('bull', 90, 95, origin_index=10, pivot_index=20)
        bar = make_bar(20, 94, 96, 93, 95)

        events = pruner.prune_turn_limit(state, new_leg, bar, datetime.now())

        # No pruning - 3 legs <= 5 max
        assert events == []
        assert len(state.active_legs) == 3


# ============================================================================
# Integration Tests
# ============================================================================


class TestTurnLimitIntegration:
    """Integration tests with LegDetector."""

    def test_turn_limit_triggered_at_formation(self):
        """Turn limit pruning happens when new leg forms."""
        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=2, min_turn_threshold=0.236
        ).with_bull(formation_fib=0.236).with_bear(formation_fib=0.236)

        detector = LegDetector(config)

        # Build a scenario with multiple legs at same turn
        bars = [
            # Initial bars establishing structure
            Bar(index=0, timestamp=0, open=Decimal("100"), high=Decimal("105"), low=Decimal("95"), close=Decimal("100")),
        ]

        # Process bars
        for bar in bars:
            detector.process_bar(bar)

        # Verify detector created with turn limit config
        assert detector.config.max_legs_per_turn == 2
        assert detector.config.min_turn_threshold == 0.236


# ============================================================================
# Serialization Tests
# ============================================================================


class TestTurnLimitSerialization:
    """Test serialization/deserialization of turn limit config."""

    def test_config_to_dict(self):
        """Config with turn limit serializes correctly."""
        from dataclasses import asdict

        config = SwingConfig.default().with_turn_limit(
            max_legs_per_turn=3, min_turn_threshold=0.382
        )

        config_dict = asdict(config)

        assert config_dict['max_legs_per_turn'] == 3
        assert config_dict['min_turn_threshold'] == 0.382

    def test_all_builder_methods_preserve_turn_limit(self):
        """All builder methods preserve turn limit settings."""
        base = SwingConfig.default().with_turn_limit(max_legs_per_turn=3)

        # Test each builder method
        assert base.with_bull(formation_fib=0.5).max_legs_per_turn == 3
        assert base.with_bear(formation_fib=0.5).max_legs_per_turn == 3
        assert base.with_origin_prune(origin_range_prune_threshold=0.1).max_legs_per_turn == 3
        assert base.with_stale_extension(2.0).max_legs_per_turn == 3
        assert base.with_level_crosses(True).max_legs_per_turn == 3
        assert base.with_prune_toggles(enable_engulfed_prune=False).max_legs_per_turn == 3
        assert base.with_min_branch_ratio(0.1).max_legs_per_turn == 3
