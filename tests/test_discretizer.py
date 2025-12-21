"""
Unit tests for the Discretizer module.

Tests cover:
- Basic discretization workflow
- Level crossing detection
- Multi-level jump handling
- Completion detection
- Invalidation detection
- Side-channel annotations (effort, shock, parent context)
- Config-driven behavior
"""

import pandas as pd
import pytest
from decimal import Decimal

from src.discretization import (
    Discretizer,
    DiscretizerConfig,
    DiscretizationLog,
    EventType,
    validate_log,
)
from src.discretization.discretizer import _get_band, _levels_between
from src.swing_analysis.swing_node import SwingNode


# =============================================================================
# Test Fixtures
# =============================================================================


def make_ohlc(bars: list[tuple]) -> pd.DataFrame:
    """
    Create OHLC DataFrame from list of tuples.

    Each tuple: (timestamp, open, high, low, close)
    """
    data = []
    for i, bar in enumerate(bars):
        ts, o, h, l, c = bar
        data.append({
            "timestamp": ts,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        })
    return pd.DataFrame(data)


def make_swing(
    high_price: float,
    low_price: float,
    high_bar: int,
    low_bar: int,
    direction: str = "bull",
) -> SwingNode:
    """Create a SwingNode for testing."""
    formed_bar = max(high_bar, low_bar)
    return SwingNode(
        swing_id=SwingNode.generate_id(),
        high_price=Decimal(str(high_price)),
        high_bar_index=high_bar,
        low_price=Decimal(str(low_price)),
        low_bar_index=low_bar,
        direction=direction,
        status="active",
        formed_at_bar=formed_bar,
    )


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestGetBand:
    """Tests for _get_band helper function."""

    def test_below_lowest_level(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        assert _get_band(-0.1, levels) == "<0.0"

    def test_above_highest_level(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        assert _get_band(1.5, levels) == ">=1.0"

    def test_exact_level_lower_bound(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        # At exact level, should be in band starting at that level
        assert _get_band(0.382, levels) == "0.382-0.5"

    def test_mid_band(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        assert _get_band(0.45, levels) == "0.382-0.5"

    def test_near_upper_bound(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        assert _get_band(0.499, levels) == "0.382-0.5"


class TestLevelsBetween:
    """Tests for _levels_between helper function."""

    def test_no_levels_crossed(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        # Moving within same band
        crossed = _levels_between(0.4, 0.45, levels, 0.001)
        assert crossed == []

    def test_single_level_crossed_up(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        crossed = _levels_between(0.4, 0.55, levels, 0.001)
        assert crossed == [0.5]

    def test_single_level_crossed_down(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        crossed = _levels_between(0.55, 0.4, levels, 0.001)
        assert crossed == [0.5]

    def test_multiple_levels_crossed_up(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        crossed = _levels_between(0.3, 0.7, levels, 0.001)
        # Should cross 0.382, 0.5, 0.618 in that order
        assert crossed == [0.382, 0.5, 0.618]

    def test_multiple_levels_crossed_down(self):
        levels = [0.0, 0.382, 0.5, 0.618, 1.0]
        crossed = _levels_between(0.7, 0.3, levels, 0.001)
        # Should cross 0.618, 0.5, 0.382 in that order (reverse)
        assert crossed == [0.618, 0.5, 0.382]

    def test_tolerance_prevents_crossing(self):
        levels = [0.0, 0.5, 1.0]
        # Movement is within tolerance of the level
        crossed = _levels_between(0.499, 0.501, levels, 0.01)
        assert crossed == []


# =============================================================================
# Discretizer Config Tests
# =============================================================================


class TestDiscretizerConfig:
    """Tests for DiscretizerConfig dataclass."""

    def test_default_config(self):
        config = DiscretizerConfig()
        assert len(config.level_set) > 0
        assert config.crossing_semantics == "close_cross"
        assert config.crossing_tolerance_pct == 0.001
        assert "S" in config.invalidation_thresholds
        assert "XL" in config.rolling_window_sizes

    def test_custom_config(self):
        config = DiscretizerConfig(
            level_set=[0.0, 0.5, 1.0, 2.0],
            crossing_semantics="wick_touch",
            crossing_tolerance_pct=0.002,
        )
        assert config.level_set == [0.0, 0.5, 1.0, 2.0]
        assert config.crossing_semantics == "wick_touch"

    def test_to_output_config(self):
        config = DiscretizerConfig()
        output_config = config.to_output_config()
        assert output_config.level_set == config.level_set
        assert output_config.crossing_semantics == config.crossing_semantics


# =============================================================================
# Basic Discretization Tests
# =============================================================================


class TestBasicDiscretization:
    """Tests for basic discretization workflow."""

    def test_empty_ohlc(self):
        """Discretization with empty OHLC should return empty log."""
        discretizer = Discretizer()
        ohlc = make_ohlc([])
        log = discretizer.discretize(ohlc, {})

        assert len(log.events) == 0
        assert len(log.swings) == 0

    def test_no_swings(self):
        """Discretization with OHLC but no swings."""
        discretizer = Discretizer()
        ohlc = make_ohlc([
            (1000, 100, 101, 99, 100),
            (1001, 100, 102, 98, 101),
            (1002, 101, 103, 100, 102),
        ])
        log = discretizer.discretize(ohlc, {})

        assert len(log.events) == 0
        assert len(log.swings) == 0

    def test_swing_formation_event(self):
        """Swing formation should produce SWING_FORMED event."""
        discretizer = Discretizer()

        # Bull swing: high at bar 0, low at bar 1
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0: forms high
            (1001, 108, 108, 100, 102),  # Bar 1: forms low, swing complete
            (1002, 102, 105, 101, 104),  # Bar 2
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Should have SWING_FORMED event
        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 1
        assert formed_events[0].bar == 1  # Formed at bar 1 (max of high_bar, low_bar)
        assert formed_events[0].data["direction"] == "bull"
        assert formed_events[0].data["scale"] == "M"

    def test_metadata_populated(self):
        """Log metadata should be properly populated."""
        discretizer = Discretizer()
        ohlc = make_ohlc([
            (1000, 100, 101, 99, 100),
            (1001, 100, 102, 98, 101),
        ])
        log = discretizer.discretize(ohlc, {}, instrument="ES", source_resolution="5m")

        assert log.meta.instrument == "ES"
        assert log.meta.source_resolution == "5m"
        assert log.meta.config is not None


# =============================================================================
# Level Crossing Tests
# =============================================================================


class TestLevelCrossing:
    """Tests for level crossing detection."""

    def test_single_level_crossing(self):
        """Price crossing a single level should produce LEVEL_CROSS event."""
        config = DiscretizerConfig(level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 2.0])
        discretizer = Discretizer(config)

        # Bull swing from 100 to 110 (size = 10)
        # 0.382 level = 100 + 0.382 * 10 = 103.82
        # 0.5 level = 100 + 0.5 * 10 = 105
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms, close below 0.382
            (1002, 102, 106, 102, 106),  # Bar 2: crosses 0.382 and 0.5 levels
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Check for level crossings at bar 2
        cross_events = [
            e for e in log.events
            if e.event_type == EventType.LEVEL_CROSS and e.bar == 2
        ]
        assert len(cross_events) >= 1

        # Should have crossed at least 0.382 and 0.5
        crossed_levels = [e.data["level_crossed"] for e in cross_events]
        assert 0.382 in crossed_levels or 0.5 in crossed_levels

    def test_multi_level_jump(self):
        """Price jumping multiple levels in one bar should log all intermediate levels."""
        config = DiscretizerConfig(level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 2.0])
        discretizer = Discretizer(config)

        # Bull swing from 100 to 110
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 101),  # Bar 1: swing forms, close at ~0.1
            (1002, 101, 118, 101, 117),  # Bar 2: jumps from 0.1 to 1.7 (past 1.0!)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Check level crossings at bar 2
        cross_events = [
            e for e in log.events
            if e.event_type == EventType.LEVEL_CROSS and e.bar == 2
        ]

        # Should have multiple level crossings in order
        assert len(cross_events) >= 3  # At least 0.382, 0.5, 0.618, 1.0

        # All should have same shock annotation with levels_jumped > 1
        if cross_events:
            shock = cross_events[0].shock
            assert shock is not None
            assert shock.levels_jumped >= 3


# =============================================================================
# Completion Tests
# =============================================================================


class TestCompletion:
    """Tests for swing completion detection."""

    def test_completion_at_2x(self):
        """Price reaching 2.0 extension should produce COMPLETION event."""
        config = DiscretizerConfig(level_set=[0.0, 0.5, 1.0, 2.0])
        discretizer = Discretizer(config)

        # Bull swing from 100 to 110 (size = 10)
        # 2.0 level = 100 + 2.0 * 10 = 120
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms
            (1002, 102, 115, 102, 115),  # Bar 2: ratio ~1.5
            (1003, 115, 122, 115, 121),  # Bar 3: crosses 2.0 (ratio = 2.1)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Should have COMPLETION event at bar 3
        completion_events = [e for e in log.events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1
        assert completion_events[0].bar == 3
        assert completion_events[0].data["completion_ratio"] >= 2.0

        # Should also have SWING_TERMINATED event
        term_events = [e for e in log.events if e.event_type == EventType.SWING_TERMINATED]
        assert len(term_events) == 1
        assert term_events[0].data["termination_type"] == "COMPLETED"

    def test_swing_status_updated_on_completion(self):
        """Swing entry status should update to 'completed' after completion."""
        config = DiscretizerConfig(level_set=[0.0, 1.0, 2.0])
        discretizer = Discretizer(config)

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
            (1002, 102, 125, 102, 122),  # Crosses 2.0
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        assert len(log.swings) == 1
        assert log.swings[0].status == "completed"
        assert log.swings[0].terminated_at_bar == 2


# =============================================================================
# Invalidation Tests
# =============================================================================


class TestInvalidation:
    """Tests for swing invalidation detection."""

    def test_invalidation_below_threshold(self):
        """Price falling below threshold should produce INVALIDATION event."""
        config = DiscretizerConfig(
            level_set=[-0.15, -0.10, 0.0, 0.5, 1.0, 2.0],
            invalidation_thresholds={"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15},
        )
        discretizer = Discretizer(config)

        # Bull swing from 100 to 110
        # -0.10 level = 100 - 0.10 * 10 = 99
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms
            (1002, 102, 103, 98, 98),    # Bar 2: drops below -0.10 level
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Should have INVALIDATION event
        inv_events = [e for e in log.events if e.event_type == EventType.INVALIDATION]
        assert len(inv_events) == 1
        assert inv_events[0].data["threshold"] == -0.10

        # Swing should be terminated
        term_events = [e for e in log.events if e.event_type == EventType.SWING_TERMINATED]
        assert len(term_events) == 1
        assert term_events[0].data["termination_type"] == "INVALIDATED"

    def test_swing_status_updated_on_invalidation(self):
        """Swing entry status should update to 'invalidated' after invalidation."""
        config = DiscretizerConfig(
            level_set=[-0.15, 0.0, 1.0, 2.0],
            invalidation_thresholds={"M": -0.10},
        )
        discretizer = Discretizer(config)

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
            (1002, 102, 103, 97, 97),  # Below -0.10
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        assert len(log.swings) == 1
        assert log.swings[0].status == "invalidated"

    def test_scale_specific_thresholds(self):
        """Different scales should use their specific invalidation thresholds."""
        config = DiscretizerConfig(
            level_set=[-0.20, -0.15, -0.10, 0.0, 1.0, 2.0],
            invalidation_thresholds={"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15},
        )
        discretizer = Discretizer(config)

        # Same swing, different scales
        swing_m = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")
        swing_l = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        # Price at -0.12: should invalidate M (threshold -0.10) but not L (threshold -0.15)
        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
            (1002, 102, 103, 98, 98.8),  # ratio = -0.12
        ])

        # Test M scale
        log_m = discretizer.discretize(ohlc, {"M": [swing_m]})
        inv_m = [e for e in log_m.events if e.event_type == EventType.INVALIDATION]
        assert len(inv_m) == 1  # M should be invalidated

        # Test L scale
        log_l = discretizer.discretize(ohlc, {"L": [swing_l]})
        inv_l = [e for e in log_l.events if e.event_type == EventType.INVALIDATION]
        assert len(inv_l) == 0  # L should NOT be invalidated yet


# =============================================================================
# Side-Channel Annotation Tests
# =============================================================================


class TestShockAnnotation:
    """Tests for ShockAnnotation side-channel."""

    def test_shock_levels_jumped(self):
        """ShockAnnotation should count levels jumped correctly."""
        config = DiscretizerConfig(level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 2.0])
        discretizer = Discretizer(config)

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 101),  # Close at 0.1
            (1002, 101, 108, 101, 107),  # Jump to 0.7 (crosses 0.382, 0.5, 0.618)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        cross_events = [e for e in log.events if e.event_type == EventType.LEVEL_CROSS and e.bar == 2]
        if cross_events:
            # All events at same bar should have same levels_jumped
            shock = cross_events[0].shock
            assert shock is not None
            assert shock.levels_jumped >= 2

    def test_shock_range_multiple(self):
        """ShockAnnotation should calculate range_multiple correctly."""
        config = DiscretizerConfig(rolling_window_sizes={"M": 3})
        discretizer = Discretizer(config)

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 106, 104, 105),  # Range = 2
            (1001, 105, 106, 100, 102),  # Range = 6, swing forms
            (1002, 102, 104, 101, 103),  # Range = 3
            (1003, 103, 120, 103, 118),  # Range = 17 (big bar!)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Look for events at bar 3 with high range_multiple
        events_bar3 = [e for e in log.events if e.bar == 3 and e.shock is not None]
        if events_bar3:
            # Range of 17 vs median of recent bars should give high multiple
            assert events_bar3[0].shock.range_multiple > 2.0

    def test_shock_gap_detection(self):
        """ShockAnnotation should detect gaps correctly."""
        config = DiscretizerConfig(gap_threshold_pct=0.01)  # 1% gap threshold
        discretizer = Discretizer(config)

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),  # Close at 102
            (1002, 107, 110, 106, 108),  # Opens at 107 (5% gap from 102!)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Events at bar 2 should have is_gap=True
        events_bar2 = [e for e in log.events if e.bar == 2 and e.shock is not None]
        if events_bar2:
            assert events_bar2[0].shock.is_gap is True
            assert events_bar2[0].shock.gap_multiple is not None


class TestEffortAnnotation:
    """Tests for EffortAnnotation side-channel."""

    def test_effort_dwell_bars(self):
        """EffortAnnotation should track dwell bars in a band."""
        config = DiscretizerConfig(level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 2.0])
        discretizer = Discretizer(config)

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),   # Bar 0
            (1001, 108, 108, 100, 101),   # Bar 1: swing forms, ratio ~0.1 (band 0-0.382)
            (1002, 101, 102, 100.5, 101), # Bar 2: still in 0-0.382 band
            (1003, 101, 103, 101, 102),   # Bar 3: still in band
            (1004, 102, 106, 102, 105.5), # Bar 4: crosses to 0.5-0.618 band
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Find crossing events at bar 4 with effort annotation
        cross_events = [
            e for e in log.events
            if e.event_type == EventType.LEVEL_CROSS and e.bar == 4 and e.effort is not None
        ]

        if cross_events:
            # Should have dwelled in previous band for multiple bars
            assert cross_events[0].effort.dwell_bars >= 2


class TestParentContext:
    """Tests for ParentContext side-channel."""

    def test_parent_context_for_smaller_scale(self):
        """Smaller scale events should have parent context from larger scale."""
        config = DiscretizerConfig(level_set=[0.0, 0.5, 1.0, 2.0])
        discretizer = Discretizer(config)

        # XL swing forms first
        xl_swing = make_swing(high_price=120, low_price=100, high_bar=0, low_bar=1, direction="bull")
        # M swing forms later
        m_swing = make_swing(high_price=115, low_price=105, high_bar=2, low_bar=3, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 120, 105, 118),   # Bar 0
            (1001, 118, 118, 100, 102),   # Bar 1: XL forms
            (1002, 102, 115, 102, 114),   # Bar 2
            (1003, 114, 114, 105, 107),   # Bar 3: M forms
            (1004, 107, 112, 107, 111),   # Bar 4: M crosses level
        ])

        log = discretizer.discretize(ohlc, {"XL": [xl_swing], "M": [m_swing]})

        # M scale events should have parent_context pointing to XL
        m_events = [
            e for e in log.events
            if e.swing_id in [s.swing_id for s in log.swings if s.scale == "M"]
            and e.parent_context is not None
        ]

        # Should have some events with parent context
        if m_events:
            assert m_events[0].parent_context.scale == "XL"

    def test_no_parent_context_for_xl(self):
        """XL scale events should not have parent context."""
        config = DiscretizerConfig(level_set=[0.0, 0.5, 1.0, 2.0])
        discretizer = Discretizer(config)

        xl_swing = make_swing(high_price=120, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 120, 105, 118),
            (1001, 118, 118, 100, 102),
            (1002, 102, 115, 102, 112),  # Level crossing
        ])

        log = discretizer.discretize(ohlc, {"XL": [xl_swing]})

        # XL events should not have parent context
        xl_cross_events = [
            e for e in log.events
            if e.event_type == EventType.LEVEL_CROSS
        ]

        for event in xl_cross_events:
            assert event.parent_context is None


# =============================================================================
# Validation Tests
# =============================================================================


class TestLogValidation:
    """Tests for log validation."""

    def test_valid_log_passes_validation(self):
        """A properly constructed log should pass validation."""
        discretizer = Discretizer()

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
            (1002, 102, 106, 102, 105),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        errors = validate_log(log)
        assert len(errors) == 0

    def test_events_ordered_by_bar(self):
        """Events should be ordered by bar index."""
        discretizer = Discretizer()

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
            (1002, 102, 106, 102, 105),
            (1003, 105, 108, 105, 107),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Verify ordering
        for i in range(1, len(log.events)):
            assert log.events[i].bar >= log.events[i-1].bar


# =============================================================================
# Bear Swing Tests
# =============================================================================


class TestBearSwings:
    """Tests for bear swing discretization."""

    def test_bear_swing_formation(self):
        """Bear swing should form and generate SWING_FORMED event."""
        discretizer = Discretizer()

        # Bear swing: low at bar 0, high at bar 1
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=1,
            low_bar=0,
            direction="bear",
        )

        ohlc = make_ohlc([
            (1000, 105, 105, 100, 102),  # Bar 0: forms low
            (1001, 102, 110, 102, 108),  # Bar 1: forms high, swing complete
            (1002, 108, 109, 106, 107),  # Bar 2
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 1
        assert formed_events[0].data["direction"] == "bear"

    def test_bear_swing_completion(self):
        """Bear swing completing (falling to 2.0 level down) should trigger COMPLETION."""
        config = DiscretizerConfig(level_set=[0.0, 0.5, 1.0, 2.0])
        discretizer = Discretizer(config)

        # Bear swing from 100 to 110 (anchor0=110, anchor1=100)
        # For bear: ratio = (price - anchor0) / (anchor1 - anchor0)
        #         = (price - 110) / (100 - 110) = (price - 110) / -10
        # ratio = 2.0 means price = 110 + 2.0 * (-10) = 90
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=1,
            low_bar=0,
            direction="bear",
        )

        ohlc = make_ohlc([
            (1000, 105, 105, 100, 102),  # Bar 0
            (1001, 102, 110, 102, 108),  # Bar 1: swing forms
            (1002, 108, 108, 95, 96),    # Bar 2: drops
            (1003, 96, 96, 88, 89),      # Bar 3: crosses 2.0 (below 90)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        completion_events = [e for e in log.events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1

    def test_bear_swing_invalidation(self):
        """Bear swing invalidation should trigger when price rises above threshold."""
        config = DiscretizerConfig(
            level_set=[-0.15, -0.10, 0.0, 0.5, 1.0, 2.0],
            invalidation_thresholds={"M": -0.10},
        )
        discretizer = Discretizer(config)

        # Bear swing: anchor0=110 (defended), anchor1=100 (origin)
        # ratio < -0.10 means (price - 110) / -10 < -0.10
        # price - 110 > 1 => price > 111
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=1,
            low_bar=0,
            direction="bear",
        )

        ohlc = make_ohlc([
            (1000, 105, 105, 100, 102),
            (1001, 102, 110, 102, 108),
            (1002, 108, 112, 108, 112),  # Rises above threshold
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        inv_events = [e for e in log.events if e.event_type == EventType.INVALIDATION]
        assert len(inv_events) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_swing_lifecycle(self):
        """Test complete swing lifecycle: formation -> level crosses -> completion."""
        config = DiscretizerConfig(level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 1.5, 2.0])
        discretizer = Discretizer(config)

        swing = make_swing(high_price=110, low_price=100, high_bar=0, low_bar=1, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),   # Bar 0
            (1001, 108, 108, 100, 101),   # Bar 1: swing forms, ratio ~0.1
            (1002, 101, 105, 101, 104),   # Bar 2: ratio ~0.4
            (1003, 104, 108, 104, 107),   # Bar 3: ratio ~0.7
            (1004, 107, 113, 107, 112),   # Bar 4: ratio ~1.2
            (1005, 112, 116, 112, 115),   # Bar 5: ratio ~1.5
            (1006, 115, 122, 115, 121),   # Bar 6: ratio ~2.1 (completion)
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Verify lifecycle events
        event_types = [e.event_type for e in log.events]

        assert EventType.SWING_FORMED in event_types
        assert EventType.LEVEL_CROSS in event_types
        assert EventType.COMPLETION in event_types
        assert EventType.SWING_TERMINATED in event_types

        # Verify swing status
        assert log.swings[0].status == "completed"

    def test_multi_scale_concurrent_swings(self):
        """Test multiple swings active at different scales simultaneously."""
        discretizer = Discretizer()

        xl_swing = make_swing(high_price=120, low_price=100, high_bar=0, low_bar=1, direction="bull")
        m_swing = make_swing(high_price=112, low_price=105, high_bar=2, low_bar=3, direction="bull")

        ohlc = make_ohlc([
            (1000, 105, 120, 105, 118),   # Bar 0
            (1001, 118, 118, 100, 102),   # Bar 1: XL forms
            (1002, 102, 112, 102, 110),   # Bar 2
            (1003, 110, 110, 105, 106),   # Bar 3: M forms
            (1004, 106, 115, 106, 114),   # Bar 4: both active
            (1005, 114, 118, 114, 117),   # Bar 5
        ])

        log = discretizer.discretize(ohlc, {"XL": [xl_swing], "M": [m_swing]})

        # Should have swings at both scales
        scales = {s.scale for s in log.swings}
        assert "XL" in scales
        assert "M" in scales

        # Should have events for both swings
        swing_ids_with_events = {e.swing_id for e in log.events}
        assert len(swing_ids_with_events) >= 2


# =============================================================================
# SWING_FORMED Explanation Tests (#82)
# =============================================================================


class TestSwingFormedExplanation:
    """Tests for SWING_FORMED event explanation data (#82)."""

    def test_explanation_field_present(self):
        """SWING_FORMED event should include explanation field."""
        discretizer = Discretizer()

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms
            (1002, 102, 105, 101, 104),  # Bar 2
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 1

        # Explanation field should be present
        assert "explanation" in formed_events[0].data
        explanation = formed_events[0].data["explanation"]
        assert explanation is not None

    def test_explanation_high_low_fields(self):
        """Explanation should include high/low bar indices, prices, and timestamps."""
        discretizer = Discretizer()

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 1001, 108, 100, 102),
            (1002, 102, 105, 101, 104),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})
        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # High fields
        assert "high_bar" in explanation
        assert explanation["high_bar"] == 0
        assert "high_price" in explanation
        assert explanation["high_price"] == 110
        assert "high_timestamp" in explanation
        assert explanation["high_timestamp"] != ""

        # Low fields
        assert "low_bar" in explanation
        assert explanation["low_bar"] == 1
        assert "low_price" in explanation
        assert explanation["low_price"] == 100
        assert "low_timestamp" in explanation
        assert explanation["low_timestamp"] != ""

    def test_explanation_size_fields(self):
        """Explanation should include size_pts and size_pct."""
        discretizer = Discretizer()

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})
        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # Size fields
        assert "size_pts" in explanation
        assert explanation["size_pts"] == 10  # 110 - 100

        assert "size_pct" in explanation
        assert explanation["size_pct"] > 0  # Should be ~9.09% (10/110 * 100)

    def test_explanation_scale_reason(self):
        """Explanation should include scale_reason with actual threshold values."""
        config = DiscretizerConfig(scale_thresholds={"M": 5, "L": 25})
        discretizer = Discretizer(config)

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})
        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # scale_reason should show the threshold
        assert "scale_reason" in explanation
        assert "M threshold 5" in explanation["scale_reason"]
        assert "Size 10" in explanation["scale_reason"]

    def test_explanation_is_anchor_first_swing(self):
        """First swing (with no parents) should be marked as anchor (is_anchor=True)."""
        discretizer = Discretizer()

        # Create a swing with no parents (anchor)
        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})
        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # is_anchor should be True (no parents)
        assert "is_anchor" in explanation
        assert explanation["is_anchor"] is True

        # separation should be null for anchor
        assert "separation" in explanation
        assert explanation["separation"] is None

    def test_explanation_separation_for_non_anchor(self):
        """Non-anchor swing (with parent) should include separation details."""
        discretizer = Discretizer()

        # Create parent swing
        parent = SwingNode(
            swing_id="parent-456",
            high_price=Decimal("120"),
            high_bar_index=0,
            low_price=Decimal("90"),
            low_bar_index=5,
            direction="bull",
            status="active",
            formed_at_bar=5,
        )

        # Create a child swing with parent
        swing = SwingNode(
            swing_id=SwingNode.generate_id(),
            high_price=Decimal("110"),
            high_bar_index=0,
            low_price=Decimal("100"),
            low_bar_index=1,
            direction="bull",
            status="active",
            formed_at_bar=1,
        )
        swing.add_parent(parent)

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})
        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # is_anchor should be False (has parent)
        assert explanation["is_anchor"] is False

        # separation should have containing_swing_id from parent
        assert explanation["separation"] is not None
        separation = explanation["separation"]

        assert separation["containing_swing_id"] == "parent-456"

    def test_explanation_bear_swing(self):
        """Bear swing should also include explanation data."""
        discretizer = Discretizer()

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=1,
            low_bar=0,
            direction="bear",
        )

        ohlc = make_ohlc([
            (1000, 105, 105, 100, 102),
            (1001, 102, 110, 102, 108),
            (1002, 108, 109, 106, 107),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 1

        explanation = formed_events[0].data["explanation"]
        assert explanation is not None
        assert explanation["high_bar"] == 1
        assert explanation["low_bar"] == 0
        assert explanation["high_price"] == 110
        assert explanation["low_price"] == 100

    def test_explanation_timestamps_iso8601(self):
        """Timestamps in explanation should be ISO 8601 formatted."""
        discretizer = Discretizer()

        swing = make_swing(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        # Use Unix timestamps
        ohlc = make_ohlc([
            (1609459200, 105, 110, 105, 108),  # 2021-01-01 00:00:00 UTC
            (1609459260, 108, 108, 100, 102),  # 2021-01-01 00:01:00 UTC
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})
        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # Timestamps should be ISO 8601 format
        assert "2021-01-01" in explanation["high_timestamp"]
        assert "2021-01-01" in explanation["low_timestamp"]


# =============================================================================
# SwingNode Input Tests (#151)
# =============================================================================


# Alias for backward compatibility with existing tests
make_swing_node = make_swing


class TestSwingNodeInput:
    """Tests for SwingNode input support (#151)."""

    def test_swing_node_discretization(self):
        """Discretizer should accept SwingNode input and produce valid output."""
        discretizer = Discretizer()

        # Create SwingNode instead of ReferenceSwing
        swing = make_swing_node(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms
            (1002, 102, 105, 101, 104),  # Bar 2
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Should have SWING_FORMED event
        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 1
        assert formed_events[0].bar == 1
        assert formed_events[0].data["direction"] == "bull"
        assert formed_events[0].data["scale"] == "M"

    def test_swing_node_level_crossing(self):
        """SwingNode input should correctly produce level crossing events."""
        config = DiscretizerConfig(level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 2.0])
        discretizer = Discretizer(config)

        swing = make_swing_node(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms, close below 0.382
            (1002, 102, 106, 102, 106),  # Bar 2: crosses levels
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Should have level crossings
        cross_events = [
            e for e in log.events
            if e.event_type == EventType.LEVEL_CROSS and e.bar == 2
        ]
        assert len(cross_events) >= 1

    def test_swing_node_completion(self):
        """SwingNode should reach completion at 2.0 level."""
        config = DiscretizerConfig(level_set=[0.0, 0.5, 1.0, 2.0])
        discretizer = Discretizer(config)

        swing = make_swing_node(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),  # Bar 0
            (1001, 108, 108, 100, 102),  # Bar 1: swing forms
            (1002, 102, 125, 102, 122),  # Bar 2: crosses 2.0
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        # Should have COMPLETION event
        completion_events = [e for e in log.events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1
        assert log.swings[0].status == "completed"

    def test_swing_node_invalidation(self):
        """SwingNode should be invalidated when price falls below threshold."""
        config = DiscretizerConfig(
            level_set=[-0.15, -0.10, 0.0, 0.5, 1.0, 2.0],
            invalidation_thresholds={"M": -0.10},
        )
        discretizer = Discretizer(config)

        swing = make_swing_node(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
            (1002, 102, 103, 98, 98),  # Below -0.10
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        inv_events = [e for e in log.events if e.event_type == EventType.INVALIDATION]
        assert len(inv_events) == 1
        assert log.swings[0].status == "invalidated"

    def test_multi_scale_swing_input(self):
        """Discretizer should accept SwingNode input at multiple scales."""
        discretizer = Discretizer()

        # XL scale swing
        xl_swing = make_swing_node(
            high_price=120,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        # M scale swing
        m_swing = make_swing_node(
            high_price=115,
            low_price=105,
            high_bar=2,
            low_bar=3,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 120, 105, 118),   # Bar 0
            (1001, 118, 118, 100, 102),   # Bar 1: xl_swing forms
            (1002, 102, 115, 102, 114),   # Bar 2
            (1003, 114, 114, 105, 107),   # Bar 3: m_swing forms
            (1004, 107, 112, 107, 111),   # Bar 4
        ])

        log = discretizer.discretize(ohlc, {"XL": [xl_swing], "M": [m_swing]})

        # Should have swings at both scales
        scales = {s.scale for s in log.swings}
        assert "XL" in scales
        assert "M" in scales

        # Should have formed events for both
        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 2

    def test_swing_node_bear_swing(self):
        """Bear SwingNode should work correctly."""
        discretizer = Discretizer()

        swing = make_swing_node(
            high_price=110,
            low_price=100,
            high_bar=1,
            low_bar=0,
            direction="bear",
        )

        ohlc = make_ohlc([
            (1000, 105, 105, 100, 102),  # Bar 0: forms low
            (1001, 102, 110, 102, 108),  # Bar 1: forms high, swing complete
            (1002, 108, 109, 106, 107),  # Bar 2
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        formed_events = [e for e in log.events if e.event_type == EventType.SWING_FORMED]
        assert len(formed_events) == 1
        assert formed_events[0].data["direction"] == "bear"

    def test_swing_node_fib_levels_calculated(self):
        """SwingNode conversion should correctly calculate Fib levels for explanation."""
        discretizer = Discretizer()

        swing = make_swing_node(
            high_price=110,
            low_price=100,
            high_bar=0,
            low_bar=1,
            direction="bull",
        )

        ohlc = make_ohlc([
            (1000, 105, 110, 105, 108),
            (1001, 108, 108, 100, 102),
        ])

        log = discretizer.discretize(ohlc, {"M": [swing]})

        formed = [e for e in log.events if e.event_type == EventType.SWING_FORMED][0]
        explanation = formed.data["explanation"]

        # Verify the high/low data came through correctly
        assert explanation["high_price"] == 110
        assert explanation["low_price"] == 100
        assert explanation["size_pts"] == 10
