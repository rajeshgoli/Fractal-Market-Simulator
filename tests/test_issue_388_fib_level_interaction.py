"""
Tests for Issue #388: Reference Layer Phase 2 - Fib Level Interaction.

Tests the new get_active_levels() method and level crossing tracking functionality.

Updated for #436: scale -> bin migration.
- ReferenceSwing uses bin (0-10) instead of scale (S/M/L/XL)
- ReferenceState uses by_bin and significant instead of by_scale
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwing,
    LevelInfo,
    ReferenceState,
)
from src.swing_analysis.dag import Leg
from src.swing_analysis.dag.leg import RefMetadata
from src.swing_analysis.types import Bar


class TestGetActiveLevels:
    """Tests for get_active_levels() method."""

    def _create_mock_leg(
        self,
        leg_id: str,
        direction: str,
        pivot_price: float,
        origin_price: float,
        pivot_index: int = 0,
        origin_index: int = 5,
        formed: bool = True,
    ) -> Leg:
        """Create a mock leg for testing."""
        leg = Mock(spec=Leg)
        leg.leg_id = leg_id
        leg.direction = direction
        leg.pivot_price = Decimal(str(pivot_price))
        leg.origin_price = Decimal(str(origin_price))
        leg.pivot_index = pivot_index
        leg.origin_index = origin_index
        leg.formed = formed
        leg.status = "active"
        leg.bar_count = 10
        leg.parent_leg_id = None
        leg.impulsiveness = 0.5
        leg.spikiness = 0.3
        leg.retracement_pct = Decimal("0.382")
        leg.ref = RefMetadata()  # #467: Add RefMetadata for max_location tracking
        return leg

    def _create_reference_swing(
        self,
        leg: Leg,
        bin: int = 8,  # Default to significant bin
        depth: int = 0,
        location: float = 0.5,
    ) -> ReferenceSwing:
        """Create a ReferenceSwing for testing."""
        return ReferenceSwing(
            leg=leg,
            bin=bin,
            depth=depth,
            location=location,
            salience_score=0.5,
        )

    def test_get_active_levels_returns_all_fib_ratios(self):
        """Test that get_active_levels returns all 9 fib ratios."""
        layer = ReferenceLayer()

        # Create a mock reference
        leg = self._create_mock_leg("leg1", "bull", 100.0, 110.0)
        ref = self._create_reference_swing(leg)

        # Create a state with the reference
        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],  # bin >= 8
            by_depth={0: [ref]},
            by_direction={'bull': [ref]},
            direction_imbalance=None,
            is_warming_up=False,
            warmup_progress=(50, 50),
        )

        levels = layer.get_active_levels(state)

        # Check all 9 fib ratios are present
        expected_ratios = [0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2]
        for ratio in expected_ratios:
            assert ratio in levels, f"Missing fib ratio {ratio}"
            assert len(levels[ratio]) == 1, f"Expected 1 level for ratio {ratio}"

    def test_get_active_levels_computes_correct_prices_bull(self):
        """Test that fib level prices are computed correctly for bull leg."""
        layer = ReferenceLayer()

        # Bull leg: pivot=100, origin=110 (bear reference)
        # Range = 10, so 0.382 level = 100 + 0.382 * 10 = 103.82
        leg = self._create_mock_leg("leg1", "bull", 100.0, 110.0)
        ref = self._create_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [ref]},
            direction_imbalance=None,
            is_warming_up=False,
            warmup_progress=(50, 50),
        )

        levels = layer.get_active_levels(state)

        # Check specific levels
        assert abs(levels[0][0].price - 100.0) < 0.01  # Pivot
        assert abs(levels[0.382][0].price - 103.82) < 0.01
        assert abs(levels[0.5][0].price - 105.0) < 0.01
        assert abs(levels[1][0].price - 110.0) < 0.01  # Origin
        assert abs(levels[2][0].price - 120.0) < 0.01  # 2x extension

    def test_get_active_levels_computes_correct_prices_bear(self):
        """Test that fib level prices are computed correctly for bear leg."""
        layer = ReferenceLayer()

        # Bear leg: pivot=110, origin=100 (bull reference)
        # Range = -10, so 0.382 level = 110 + 0.382 * (-10) = 106.18
        leg = self._create_mock_leg("leg1", "bear", 110.0, 100.0)
        ref = self._create_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bear': [ref]},
            direction_imbalance=None,
            is_warming_up=False,
            warmup_progress=(50, 50),
        )

        levels = layer.get_active_levels(state)

        # Check specific levels
        assert abs(levels[0][0].price - 110.0) < 0.01  # Pivot
        assert abs(levels[0.382][0].price - 106.18) < 0.01
        assert abs(levels[1][0].price - 100.0) < 0.01  # Origin
        assert abs(levels[2][0].price - 90.0) < 0.01  # 2x extension

    def test_get_active_levels_multiple_references(self):
        """Test that levels from multiple references are returned."""
        layer = ReferenceLayer()

        # Create two references
        leg1 = self._create_mock_leg("leg1", "bull", 100.0, 110.0)
        leg2 = self._create_mock_leg("leg2", "bear", 120.0, 110.0)
        ref1 = self._create_reference_swing(leg1)
        ref2 = self._create_reference_swing(leg2)

        state = ReferenceState(active_filtered=[],
            references=[ref1, ref2],
            by_bin={8: [ref1, ref2]},
            significant=[ref1, ref2],
            by_depth={0: [ref1, ref2]},
            by_direction={'bull': [ref1], 'bear': [ref2]},
            direction_imbalance=None,
            is_warming_up=False,
            warmup_progress=(50, 50),
        )

        levels = layer.get_active_levels(state)

        # Each ratio should have 2 levels (one from each reference)
        for ratio in [0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2]:
            assert len(levels[ratio]) == 2, f"Expected 2 levels for ratio {ratio}"

    def test_get_active_levels_empty_state(self):
        """Test that empty state returns empty levels."""
        layer = ReferenceLayer()

        state = ReferenceState(active_filtered=[],
            references=[],
            by_bin={},
            significant=[],
            by_depth={},
            by_direction={},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=(0, 50),
        )

        levels = layer.get_active_levels(state)

        assert levels == {}

    def test_level_info_contains_reference(self):
        """Test that LevelInfo contains back-reference to source."""
        layer = ReferenceLayer()

        leg = self._create_mock_leg("leg1", "bull", 100.0, 110.0)
        ref = self._create_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [ref]},
            direction_imbalance=None,
            is_warming_up=False,
            warmup_progress=(50, 50),
        )

        levels = layer.get_active_levels(state)

        # Each LevelInfo should reference back to the source
        for ratio, level_list in levels.items():
            for level_info in level_list:
                assert level_info.reference is ref
                assert level_info.ratio == ratio


class TestLevelCrossingTracking:
    """Tests for level crossing tracking functionality."""

    def test_add_tracking_adds_leg_id(self):
        """Test that add_crossing_tracking adds leg ID to set."""
        layer = ReferenceLayer()

        layer.add_crossing_tracking("leg1")

        assert layer.is_tracked_for_crossing("leg1")
        assert "leg1" in layer.get_tracked_leg_ids()

    def test_remove_tracking_removes_leg_id(self):
        """Test that remove_crossing_tracking removes leg ID."""
        layer = ReferenceLayer()

        layer.add_crossing_tracking("leg1")
        layer.remove_crossing_tracking("leg1")

        assert not layer.is_tracked_for_crossing("leg1")
        assert "leg1" not in layer.get_tracked_leg_ids()

    def test_remove_nonexistent_is_safe(self):
        """Test that removing non-existent leg ID doesn't raise."""
        layer = ReferenceLayer()

        # Should not raise
        layer.remove_crossing_tracking("nonexistent")

    def test_multiple_tracked_legs(self):
        """Test tracking multiple legs simultaneously."""
        layer = ReferenceLayer()

        layer.add_crossing_tracking("leg1")
        layer.add_crossing_tracking("leg2")
        layer.add_crossing_tracking("leg3")

        tracked = layer.get_tracked_leg_ids()

        assert len(tracked) == 3
        assert "leg1" in tracked
        assert "leg2" in tracked
        assert "leg3" in tracked

    def test_get_tracked_returns_copy(self):
        """Test that get_tracked_leg_ids returns a copy."""
        layer = ReferenceLayer()

        layer.add_crossing_tracking("leg1")
        tracked = layer.get_tracked_leg_ids()

        # Modifying the returned set shouldn't affect internal state
        tracked.add("leg2")

        assert not layer.is_tracked_for_crossing("leg2")

    def test_tracking_persists_across_updates(self):
        """Test that tracking state persists across update() calls."""
        layer = ReferenceLayer()

        layer.add_crossing_tracking("leg1")

        # Create a mock leg and bar for update
        leg = Mock(spec=Leg)
        leg.leg_id = "leg2"
        leg.direction = "bull"
        leg.pivot_price = Decimal("100")
        leg.origin_price = Decimal("110")
        leg.pivot_index = 0
        leg.origin_index = 5
        leg.formed = True
        leg.status = "active"
        leg.bar_count = 10
        leg.parent_leg_id = None
        leg.impulsiveness = 0.5
        leg.spikiness = 0.3
        leg.retracement_pct = Decimal("0.382")
        leg.ref = RefMetadata()  # #467: Add RefMetadata for max_location tracking

        bar = Mock(spec=Bar)
        bar.high = 105.0
        bar.low = 95.0
        bar.close = 102.0
        bar.index = 10
        bar.timestamp = 1000.0  # Added for bin distribution tracking (#434)

        # Update shouldn't affect tracking state
        layer.update([leg], bar)

        assert layer.is_tracked_for_crossing("leg1")


class TestLevelInfoDataclass:
    """Tests for LevelInfo dataclass."""

    def test_level_info_creation(self):
        """Test basic LevelInfo creation."""
        leg = Mock(spec=Leg)
        leg.leg_id = "leg1"
        leg.direction = "bull"
        leg.pivot_price = Decimal("100")
        leg.origin_price = Decimal("110")

        ref = ReferenceSwing(
            leg=leg,
            bin=8,  # Significant bin
            depth=0,
            location=0.5,
            salience_score=0.5,
        )

        level = LevelInfo(
            price=103.82,
            ratio=0.382,
            reference=ref,
        )

        assert level.price == 103.82
        assert level.ratio == 0.382
        assert level.reference is ref

    def test_level_info_all_fib_ratios(self):
        """Test LevelInfo works with all fib ratios."""
        leg = Mock(spec=Leg)
        leg.leg_id = "leg1"
        leg.direction = "bull"

        ref = ReferenceSwing(
            leg=leg,
            bin=8,
            depth=0,
            location=0.5,
            salience_score=0.5,
        )

        ratios = [0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2]

        for ratio in ratios:
            level = LevelInfo(price=100 + ratio * 10, ratio=ratio, reference=ref)
            assert level.ratio == ratio
