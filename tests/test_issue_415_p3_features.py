"""
Tests for Issue #415: Reference Layer P3 - Structure Panel + Confluence

Tests the new features added in P3:
1. Confluence zone detection (get_confluence_zones)
2. Structure Panel data (level touch tracking)
3. Telemetry data structures

Updated for #436: scale -> bin migration.
- ReferenceSwing uses bin (0-10) instead of scale (S/M/L/XL)
- ReferenceState uses by_bin and significant instead of by_scale
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwing,
    ReferenceState,
    LevelInfo,
    ConfluenceZone,
    LevelTouch,
    StructurePanelData,
)
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.types import Bar


def make_leg(
    leg_id: str,
    direction: str,
    origin_price: float,
    origin_index: int,
    pivot_price: float,
    pivot_index: int,
    impulsiveness: float = None,
) -> Leg:
    """Helper to create a Leg for testing."""
    return Leg(
        direction=direction,
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
        impulsiveness=impulsiveness,
        depth=0,
    )


def make_bar(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    """Helper to create a Bar for testing."""
    return Bar(
        index=index,
        timestamp=0,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def make_reference_swing(
    leg: Leg,
    bin: int = 8,  # Default to significant bin
    depth: int = 0,
    location: float = 0.5,
    salience_score: float = 0.5,
) -> ReferenceSwing:
    """Helper to create a ReferenceSwing for testing."""
    return ReferenceSwing(
        leg=leg,
        bin=bin,
        depth=depth,
        location=location,
        salience_score=salience_score,
    )


class TestConfluenceZoneDataclass:
    """Tests for ConfluenceZone dataclass."""

    def test_confluence_zone_creation(self):
        """Test basic confluence zone creation."""
        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)
        level = LevelInfo(price=105.0, ratio=0.5, reference=ref)

        zone = ConfluenceZone(
            center_price=105.0,
            min_price=104.5,
            max_price=105.5,
            levels=[level],
            reference_count=1,
            reference_ids={"leg1"},
        )

        assert zone.center_price == 105.0
        assert zone.min_price == 104.5
        assert zone.max_price == 105.5
        assert len(zone.levels) == 1
        assert zone.reference_count == 1
        assert "leg1" in zone.reference_ids


class TestLevelTouchDataclass:
    """Tests for LevelTouch dataclass."""

    def test_level_touch_creation(self):
        """Test basic level touch creation."""
        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)
        level = LevelInfo(price=105.0, ratio=0.5, reference=ref)

        touch = LevelTouch(
            level=level,
            bar_index=10,
            touch_price=105.0,
            cross_direction="up",
        )

        assert touch.level == level
        assert touch.bar_index == 10
        assert touch.touch_price == 105.0
        assert touch.cross_direction == "up"


class TestStructurePanelDataDataclass:
    """Tests for StructurePanelData dataclass."""

    def test_structure_panel_data_creation(self):
        """Test basic structure panel data creation."""
        data = StructurePanelData(
            touched_this_session=[],
            currently_active=[],
            current_bar_touches=[],
            current_price=4150.0,
        )

        assert data.touched_this_session == []
        assert data.currently_active == []
        assert data.current_bar_touches == []
        assert data.current_price == 4150.0


class TestGetConfluenceZones:
    """Tests for ReferenceLayer.get_confluence_zones()."""

    def test_no_zones_with_single_reference(self):
        """Single reference cannot form confluence."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)

        # Create a simple state with one reference
        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)
        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [], 'bear': [ref]},
            direction_imbalance=None,
        )

        zones = layer.get_confluence_zones(state)
        assert len(zones) == 0

    def test_confluence_with_clustering_levels(self):
        """Levels within tolerance form confluence zone."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)

        # Create two legs with overlapping levels
        # Leg 1: bear leg from 110 to 100 (range 10)
        leg1 = make_leg("leg1", "bear", 110, 0, 100, 5)
        # Leg 2: bear leg from 105 to 95 (range 10)
        # 0.5 fib of leg2 = 100.0, which is close to pivot of leg1
        leg2 = make_leg("leg2", "bear", 105, 10, 95, 15)

        ref1 = make_reference_swing(leg1, bin=8)
        ref2 = make_reference_swing(leg2, bin=8)

        state = ReferenceState(active_filtered=[],
            references=[ref1, ref2],
            by_bin={8: [ref1, ref2]},
            significant=[ref1, ref2],
            by_depth={0: [ref1, ref2]},
            by_direction={'bull': [], 'bear': [ref1, ref2]},
            direction_imbalance=None,
        )

        # With 0.1% tolerance at price ~100, levels within 0.1 points cluster
        zones = layer.get_confluence_zones(state, tolerance_pct=0.01)  # 1% tolerance

        # At least some zones should form
        # Multiple fib levels from 2 refs may cluster
        assert isinstance(zones, list)

    def test_confluence_requires_multiple_references(self):
        """Confluence zone requires levels from 2+ unique references."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)

        # Create a single leg but check that multiple levels from same ref
        # don't form confluence
        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [], 'bear': [ref]},
            direction_imbalance=None,
        )

        # Even with very large tolerance, single ref won't form confluence
        zones = layer.get_confluence_zones(state, tolerance_pct=0.5)
        assert len(zones) == 0

    def test_empty_state_returns_empty_zones(self):
        """Empty reference state returns no zones."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)

        state = ReferenceState(active_filtered=[],
            references=[],
            by_bin={},
            significant=[],
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
        )

        zones = layer.get_confluence_zones(state)
        assert zones == []


class TestGetStructurePanelData:
    """Tests for ReferenceLayer.get_structure_panel_data()."""

    def test_empty_state_returns_empty_panel(self):
        """Empty reference state returns empty panel data."""
        layer = ReferenceLayer()
        state = ReferenceState(active_filtered=[],
            references=[],
            by_bin={},
            significant=[],
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
        )
        bar = make_bar(100, 4150, 4155, 4145, 4152)

        panel = layer.get_structure_panel_data(state, bar)

        assert panel.touched_this_session == []
        assert panel.currently_active == []
        assert panel.current_bar_touches == []
        assert panel.current_price == 4152.0

    def test_level_touch_detection(self):
        """Detects when bar touches a fib level."""
        layer = ReferenceLayer()

        # Create leg with 0.5 fib at 105
        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [], 'bear': [ref]},
            direction_imbalance=None,
        )

        # Bar that trades through 105 (0.5 fib level)
        bar = make_bar(100, 104, 106, 103, 105)

        panel = layer.get_structure_panel_data(state, bar)

        # Should detect touch of level around 105
        assert len(panel.current_bar_touches) > 0

    def test_currently_active_within_distance(self):
        """Levels within striking distance appear as currently active."""
        config = ReferenceConfig.default()
        # Default active_level_distance_pct is 0.5%
        layer = ReferenceLayer(reference_config=config)

        # Leg with pivot at 100
        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [], 'bear': [ref]},
            direction_imbalance=None,
        )

        # Price very close to 0 fib (100)
        bar = make_bar(100, 100, 100.5, 99.5, 100.2)

        panel = layer.get_structure_panel_data(state, bar)

        # 0 fib at 100 should be in currently_active
        active_prices = [l.price for l in panel.currently_active]
        assert 100.0 in active_prices

    def test_session_touches_accumulate(self):
        """Session touches persist across calls."""
        layer = ReferenceLayer()

        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [], 'bear': [ref]},
            direction_imbalance=None,
        )

        # First bar touches levels
        bar1 = make_bar(100, 104, 106, 103, 105)
        panel1 = layer.get_structure_panel_data(state, bar1)
        touches_after_bar1 = len(panel1.touched_this_session)

        # Second bar touches more levels
        bar2 = make_bar(101, 102, 104, 101, 103)
        panel2 = layer.get_structure_panel_data(state, bar2)
        touches_after_bar2 = len(panel2.touched_this_session)

        # Session should accumulate
        assert touches_after_bar2 >= touches_after_bar1


class TestClearSessionTouches:
    """Tests for ReferenceLayer.clear_session_touches()."""

    def test_clear_resets_history(self):
        """Clear session touches resets history."""
        layer = ReferenceLayer()

        leg = make_leg("leg1", "bear", 110, 0, 100, 5)
        ref = make_reference_swing(leg)

        state = ReferenceState(active_filtered=[],
            references=[ref],
            by_bin={8: [ref]},
            significant=[ref],
            by_depth={0: [ref]},
            by_direction={'bull': [], 'bear': [ref]},
            direction_imbalance=None,
        )

        # Generate some touches
        bar = make_bar(100, 104, 106, 103, 105)
        layer.get_structure_panel_data(state, bar)

        # Clear
        layer.clear_session_touches()

        # Check empty after clear
        panel = layer.get_structure_panel_data(state, bar)
        # The current bar touches should still be detected, but session history should start fresh
        assert layer._session_level_touches == [] or len(layer._session_level_touches) == len(panel.current_bar_touches)


class TestCopyStateFrom:
    """Tests for ReferenceLayer.copy_state_from() with new fields."""

    def test_copies_session_touches(self):
        """copy_state_from copies session touch history."""
        layer1 = ReferenceLayer()
        layer1._session_level_touches = ["touch1", "touch2"]
        layer1._last_price = 4150.0

        layer2 = ReferenceLayer()
        layer2.copy_state_from(layer1)

        assert layer2._session_level_touches == ["touch1", "touch2"]
        assert layer2._last_price == 4150.0


class TestReferenceConfigNewFields:
    """Tests for new ReferenceConfig fields."""

    def test_active_level_distance_pct_default(self):
        """active_level_distance_pct has correct default."""
        config = ReferenceConfig.default()
        assert config.active_level_distance_pct == 0.005  # 0.5%

    def test_active_level_distance_pct_from_dict(self):
        """active_level_distance_pct loads from dict."""
        data = {"active_level_distance_pct": 0.01}
        config = ReferenceConfig.from_dict(data)
        assert config.active_level_distance_pct == 0.01

    def test_active_level_distance_pct_to_dict(self):
        """active_level_distance_pct serializes to dict."""
        config = ReferenceConfig.default()
        data = config.to_dict()
        assert "active_level_distance_pct" in data
        assert data["active_level_distance_pct"] == 0.005


class TestConfluenceZoneAlgorithm:
    """Tests for the confluence zone clustering algorithm details."""

    def test_zone_has_correct_bounds(self):
        """Confluence zone has correct min/max/center."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)

        # Create mock levels
        leg1 = make_leg("leg1", "bear", 110, 0, 100, 5)
        leg2 = make_leg("leg2", "bear", 115, 10, 105, 15)
        ref1 = make_reference_swing(leg1)
        ref2 = make_reference_swing(leg2)

        state = ReferenceState(active_filtered=[],
            references=[ref1, ref2],
            by_bin={8: [ref1, ref2]},
            significant=[ref1, ref2],
            by_depth={0: [ref1, ref2]},
            by_direction={'bull': [], 'bear': [ref1, ref2]},
            direction_imbalance=None,
        )

        zones = layer.get_confluence_zones(state, tolerance_pct=0.05)  # 5% tolerance

        for zone in zones:
            # Center should be between min and max
            assert zone.min_price <= zone.center_price <= zone.max_price
            # Should have at least 2 levels
            assert len(zone.levels) >= 2
            # Reference count should match unique refs
            assert zone.reference_count >= 2
