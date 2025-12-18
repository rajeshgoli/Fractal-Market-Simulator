"""
Tests for the incremental swing detector.

Tests cover:
1. Swing point detection (is_swing_high, is_swing_low)
2. Swing state initialization from calibration
3. Incremental bar advance with event detection
4. Invalidation detection
5. Level cross detection
6. Completion detection
"""

import pytest
from dataclasses import dataclass
from typing import List

from src.swing_analysis.incremental_detector import (
    IncrementalSwingState,
    SwingPoint,
    ActiveSwing,
    IncrementalEvent,
    is_swing_high,
    is_swing_low,
    advance_bar_incremental,
    initialize_from_calibration,
    _format_trigger_explanation,
)


@dataclass
class MockBar:
    """Mock bar for testing."""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class TestSwingPointDetection:
    """Tests for swing point detection functions."""

    def test_is_swing_high_basic(self):
        """Test basic swing high detection."""
        highs = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100]
        #                          ^ swing high at index 5
        assert is_swing_high(5, highs, lookback=2)
        assert not is_swing_high(3, highs, lookback=2)
        assert not is_swing_high(7, highs, lookback=2)

    def test_is_swing_low_basic(self):
        """Test basic swing low detection."""
        lows = [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100]
        #                         ^ swing low at index 5
        assert is_swing_low(5, lows, lookback=2)
        assert not is_swing_low(3, lows, lookback=2)
        assert not is_swing_low(7, lows, lookback=2)

    def test_swing_high_tie_breaking(self):
        """Earlier bar wins for equal values."""
        highs = [100, 101, 105, 103, 105, 102, 101]
        #              ^ first 105 wins
        assert is_swing_high(2, highs, lookback=2)
        assert not is_swing_high(4, highs, lookback=2)

    def test_swing_low_tie_breaking(self):
        """Earlier bar wins for equal values."""
        lows = [100, 99, 95, 97, 95, 98, 99]
        #             ^ first 95 wins
        assert is_swing_low(2, lows, lookback=2)
        assert not is_swing_low(4, lows, lookback=2)

    def test_swing_point_boundary_conditions(self):
        """Swing points near edges should not be detected."""
        highs = [105, 100, 101, 102, 103, 104, 105]
        lows = [95, 100, 99, 98, 97, 96, 95]

        # First index within lookback - should not detect
        assert not is_swing_high(0, highs, lookback=2)
        assert not is_swing_low(0, lows, lookback=2)

        # Last index within lookback - should not detect
        assert not is_swing_high(6, highs, lookback=2)
        assert not is_swing_low(6, lows, lookback=2)


class TestIncrementalSwingState:
    """Tests for IncrementalSwingState class."""

    def test_assign_scale(self):
        """Test scale assignment based on size thresholds."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=500.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        )

        assert state.assign_scale(150.0) == "XL"
        assert state.assign_scale(100.0) == "XL"
        assert state.assign_scale(50.0) == "L"
        assert state.assign_scale(40.0) == "L"
        assert state.assign_scale(20.0) == "M"
        assert state.assign_scale(15.0) == "M"
        assert state.assign_scale(10.0) == "S"
        assert state.assign_scale(0.0) == "S"


class TestActiveSwing:
    """Tests for ActiveSwing class."""

    def test_bull_swing_fib_level(self):
        """Test fib level calculation for bull swing."""
        swing = ActiveSwing(
            swing_id="test-bull",
            direction="bull",
            scale="M",
            high_price=110.0,
            high_bar_index=10,
            low_price=100.0,
            low_bar_index=20,
            size=10.0,
            rank=1,
            formation_bar=20,
        )

        # At low price: 0.0
        assert swing.get_fib_level(100.0) == pytest.approx(0.0)
        # At 50% retracement
        assert swing.get_fib_level(105.0) == pytest.approx(0.5)
        # At high price: 1.0
        assert swing.get_fib_level(110.0) == pytest.approx(1.0)
        # At 2.0 extension
        assert swing.get_fib_level(120.0) == pytest.approx(2.0)

    def test_bear_swing_fib_level(self):
        """Test fib level calculation for bear swing."""
        swing = ActiveSwing(
            swing_id="test-bear",
            direction="bear",
            scale="M",
            high_price=110.0,
            high_bar_index=20,
            low_price=100.0,
            low_bar_index=10,
            size=10.0,
            rank=1,
            formation_bar=20,
        )

        # At high price: 0.0
        assert swing.get_fib_level(110.0) == pytest.approx(0.0)
        # At 50% retracement
        assert swing.get_fib_level(105.0) == pytest.approx(0.5)
        # At low price: 1.0
        assert swing.get_fib_level(100.0) == pytest.approx(1.0)
        # At 2.0 extension
        assert swing.get_fib_level(90.0) == pytest.approx(2.0)

    def test_bull_swing_pivot_violation(self):
        """Test pivot violation for bull swing (low is defended)."""
        swing = ActiveSwing(
            swing_id="test-bull",
            direction="bull",
            scale="M",
            high_price=110.0,
            high_bar_index=10,
            low_price=100.0,
            low_bar_index=20,
            size=10.0,
            rank=1,
            formation_bar=20,
        )

        # 10% tolerance = 1 point below 100 = 99
        assert not swing.is_pivot_violated(bar_low=99.5, bar_high=105.0, tolerance=0.1)
        assert swing.is_pivot_violated(bar_low=98.5, bar_high=105.0, tolerance=0.1)

    def test_bear_swing_pivot_violation(self):
        """Test pivot violation for bear swing (high is defended)."""
        swing = ActiveSwing(
            swing_id="test-bear",
            direction="bear",
            scale="M",
            high_price=110.0,
            high_bar_index=20,
            low_price=100.0,
            low_bar_index=10,
            size=10.0,
            rank=1,
            formation_bar=20,
        )

        # 10% tolerance = 1 point above 110 = 111
        assert not swing.is_pivot_violated(bar_low=95.0, bar_high=110.5, tolerance=0.1)
        assert swing.is_pivot_violated(bar_low=95.0, bar_high=111.5, tolerance=0.1)


class TestAdvanceBarIncremental:
    """Tests for advance_bar_incremental function."""

    def _create_test_state(self) -> IncrementalSwingState:
        """Create a test state with some bars."""
        return IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[100, 102, 105, 103, 101, 99, 97, 95, 93, 91],
            lows=[98, 100, 103, 101, 99, 97, 95, 93, 91, 89],
            closes=[99, 101, 104, 102, 100, 98, 96, 94, 92, 90],
            lookback=2,
            protection_tolerance=0.1,
        )

    def test_append_bar_data(self):
        """Test that new bar data is appended correctly."""
        state = self._create_test_state()
        initial_len = len(state.highs)

        advance_bar_incremental(
            bar_high=110.0,
            bar_low=108.0,
            bar_close=109.0,
            state=state
        )

        assert len(state.highs) == initial_len + 1
        assert state.highs[-1] == 110.0
        assert state.lows[-1] == 108.0
        assert state.closes[-1] == 109.0

    def test_swing_point_detection_deferred(self):
        """Swing point detection is deferred by lookback bars."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[],
            lows=[],
            closes=[],
            lookback=2,
            protection_tolerance=0.1,
        )

        # Build a pattern: rising then falling
        # Swing high should be at index 4 (highest point)
        test_bars = [
            (100, 98, 99),   # 0
            (102, 100, 101), # 1
            (104, 102, 103), # 2
            (106, 104, 105), # 3
            (108, 106, 107), # 4 <- swing high candidate
            (106, 104, 105), # 5
            (104, 102, 103), # 6
            (102, 100, 101), # 7 <- swing high at 4 confirmed
        ]

        for h, l, c in test_bars:
            advance_bar_incremental(h, l, c, state)

        # Swing high at index 4 should be detected after bar 6 is added
        # (need lookback bars after)
        assert len(state.swing_highs) > 0
        swing_high = list(state.swing_highs)[0]
        assert swing_high.bar_index == 4
        assert swing_high.price == 108.0

    def test_invalidation_event(self):
        """Test that invalidation events are generated."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[100.0],
            lows=[90.0],
            closes=[95.0],
            lookback=5,
            protection_tolerance=0.1,
        )

        # Add an active bull swing
        swing = ActiveSwing(
            swing_id="test-bull",
            direction="bull",
            scale="M",
            high_price=110.0,
            high_bar_index=0,
            low_price=100.0,
            low_bar_index=0,
            size=10.0,
            rank=1,
            formation_bar=0,
        )
        state.active_swings["test-bull"] = swing
        state.fib_levels["test-bull"] = 0.5

        # Advance with a bar that violates the pivot (low < 100 - 0.1*10 = 99)
        events = advance_bar_incremental(
            bar_high=105.0,
            bar_low=98.0,  # Below threshold
            bar_close=100.0,
            state=state
        )

        # Should have invalidation event
        invalidation_events = [e for e in events if e.event_type == "SWING_INVALIDATED"]
        assert len(invalidation_events) == 1
        assert invalidation_events[0].swing_id == "test-bull"

        # Swing should be removed from active swings
        assert "test-bull" not in state.active_swings

    def test_level_cross_event(self):
        """Test that level cross events are generated."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[100.0],
            lows=[90.0],
            closes=[95.0],
            lookback=5,
            protection_tolerance=0.1,
        )

        # Add an active bull swing at 0.382 level
        swing = ActiveSwing(
            swing_id="test-bull",
            direction="bull",
            scale="M",
            high_price=110.0,
            high_bar_index=0,
            low_price=100.0,
            low_bar_index=0,
            size=10.0,
            rank=1,
            formation_bar=0,
        )
        state.active_swings["test-bull"] = swing
        state.fib_levels["test-bull"] = 0.4  # Just above 0.382

        # Advance with a bar that crosses 0.5 level (price = 105)
        events = advance_bar_incremental(
            bar_high=106.0,
            bar_low=104.0,
            bar_close=105.5,  # 0.55 level
            state=state
        )

        # Should have level cross event for 0.5
        level_cross_events = [e for e in events if e.event_type == "LEVEL_CROSS"]
        assert len(level_cross_events) == 1
        assert level_cross_events[0].level == 0.5
        assert level_cross_events[0].swing_id == "test-bull"

    def test_completion_event(self):
        """Test that completion events are generated at 2.0."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[100.0],
            lows=[90.0],
            closes=[95.0],
            lookback=5,
            protection_tolerance=0.1,
        )

        # Add an active bull swing at 1.9 level
        swing = ActiveSwing(
            swing_id="test-bull",
            direction="bull",
            scale="M",
            high_price=110.0,
            high_bar_index=0,
            low_price=100.0,
            low_bar_index=0,
            size=10.0,
            rank=1,
            formation_bar=0,
        )
        state.active_swings["test-bull"] = swing
        state.fib_levels["test-bull"] = 1.9  # Near 2.0

        # Advance with a bar that crosses 2.0 level (price = 120)
        events = advance_bar_incremental(
            bar_high=121.0,
            bar_low=119.0,
            bar_close=120.5,  # 2.05 level
            state=state
        )

        # Should have completion event
        completion_events = [e for e in events if e.event_type == "SWING_COMPLETED"]
        assert len(completion_events) == 1
        assert completion_events[0].level == 2.0
        assert completion_events[0].swing_id == "test-bull"


class TestInitializeFromCalibration:
    """Tests for initialize_from_calibration function."""

    def test_basic_initialization(self):
        """Test basic initialization from calibration."""
        # Create mock bars
        bars = [
            MockBar(i, 1000 + i, 100 + i * 0.1, 102 + i * 0.1, 99 + i * 0.1, 101 + i * 0.1)
            for i in range(100)
        ]

        calibration_swings = {
            "XL": [],
            "L": [],
            "M": [
                {
                    "id": "cal-bull-1",
                    "direction": "bull",
                    "high_price": 110.0,
                    "high_bar_index": 10,
                    "low_price": 100.0,
                    "low_bar_index": 20,
                    "size": 10.0,
                    "rank": 1,
                    "is_active": True,
                }
            ],
            "S": [],
        }

        state = initialize_from_calibration(
            calibration_swings=calibration_swings,
            source_bars=bars,
            calibration_bar_count=100,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            current_price=105.0,
            lookback=5,
            protection_tolerance=0.1,
        )

        # Check state initialization
        assert len(state.highs) == 100
        assert len(state.lows) == 100
        assert len(state.closes) == 100
        assert state.lookback == 5
        assert state.protection_tolerance == 0.1

        # Check active swing was imported
        assert "cal-bull-1" in state.active_swings
        swing = state.active_swings["cal-bull-1"]
        assert swing.direction == "bull"
        assert swing.scale == "M"
        assert swing.high_price == 110.0
        assert swing.low_price == 100.0

    def test_swing_points_detected(self):
        """Test that swing points are detected from calibration data."""
        # Create bars with clear swing points
        highs = [100, 102, 105, 103, 101, 99, 97, 95, 97, 99, 102, 105, 103, 101, 99]
        lows = [98, 100, 103, 101, 99, 97, 95, 93, 95, 97, 100, 103, 101, 99, 97]
        closes = [99, 101, 104, 102, 100, 98, 96, 94, 96, 98, 101, 104, 102, 100, 98]

        bars = [
            MockBar(i, 1000 + i, closes[i], highs[i], lows[i], closes[i])
            for i in range(len(highs))
        ]

        state = initialize_from_calibration(
            calibration_swings={"XL": [], "L": [], "M": [], "S": []},
            source_bars=bars,
            calibration_bar_count=len(bars),
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            current_price=98.0,
            lookback=2,
            protection_tolerance=0.1,
        )

        # Should have detected swing points
        # Swing high at index 2 (105) and index 11 (105)
        # Swing low at index 7 (93)
        assert len(state.swing_highs) > 0 or len(state.swing_lows) > 0


class TestIntegration:
    """Integration tests for incremental detection."""

    def test_full_workflow(self):
        """Test complete workflow: init, advance, detect events."""
        # Create initial bars with a clear pattern
        initial_highs = [100, 102, 105, 108, 110, 108, 105, 102, 100, 98]
        initial_lows = [98, 100, 103, 106, 108, 106, 103, 100, 98, 96]
        initial_closes = [99, 101, 104, 107, 109, 107, 104, 101, 99, 97]

        bars = [
            MockBar(i, 1000 + i, initial_closes[i], initial_highs[i], initial_lows[i], initial_closes[i])
            for i in range(len(initial_highs))
        ]

        # Initialize state
        state = initialize_from_calibration(
            calibration_swings={"XL": [], "L": [], "M": [], "S": []},
            source_bars=bars,
            calibration_bar_count=len(bars),
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 10.0, "S": 0.0},
            current_price=97.0,
            lookback=2,
            protection_tolerance=0.1,
        )

        # Advance with new bars
        all_events = []

        # Continue the downtrend then reverse
        new_bars = [
            (96, 94, 95),   # Continue down
            (94, 92, 93),   # Swing low candidate
            (96, 94, 95),   # Start reversing
            (98, 96, 97),   # Confirm swing low
            (100, 98, 99),  # Continue up
        ]

        for high, low, close in new_bars:
            events = advance_bar_incremental(high, low, close, state)
            all_events.extend(events)

        # State should be updated
        assert len(state.highs) == len(initial_highs) + len(new_bars)
        assert len(state.lows) == len(initial_highs) + len(new_bars)


class TestSwingPoint:
    """Tests for SwingPoint dataclass."""

    def test_sorting(self):
        """Test that swing points sort by bar_index."""
        from sortedcontainers import SortedList

        points = SortedList()
        points.add(SwingPoint('high', 10, 105.0))
        points.add(SwingPoint('high', 5, 100.0))
        points.add(SwingPoint('high', 15, 110.0))

        indices = [p.bar_index for p in points]
        assert indices == [5, 10, 15]


class TestTriggerExplanation:
    """Tests for trigger explanation generation."""

    def _create_bull_swing(self) -> ActiveSwing:
        """Create a test bull swing."""
        return ActiveSwing(
            swing_id="test-bull",
            direction="bull",
            scale="M",
            high_price=110.0,
            high_bar_index=10,
            low_price=100.0,
            low_bar_index=20,
            size=10.0,
            rank=1,
            formation_bar=20,
        )

    def _create_bear_swing(self) -> ActiveSwing:
        """Create a test bear swing."""
        return ActiveSwing(
            swing_id="test-bear",
            direction="bear",
            scale="M",
            high_price=110.0,
            high_bar_index=20,
            low_price=100.0,
            low_bar_index=10,
            size=10.0,
            rank=1,
            formation_bar=20,
        )

    def test_swing_formed_bull_explanation(self):
        """Test trigger explanation for bull SWING_FORMED."""
        swing = self._create_bull_swing()
        current_price = 105.0

        explanation = _format_trigger_explanation(
            "SWING_FORMED", swing, current_price
        )

        # Bull swing: fib_0382 = 100 + 10 * 0.382 = 103.82
        # fib_2 = 100 + 10 * 2.0 = 120
        assert "105.00" in explanation
        assert "103.82" in explanation
        assert "120.00" in explanation
        assert "above 0.382" in explanation
        assert "Active range" in explanation

    def test_swing_formed_bear_explanation(self):
        """Test trigger explanation for bear SWING_FORMED."""
        swing = self._create_bear_swing()
        current_price = 105.0

        explanation = _format_trigger_explanation(
            "SWING_FORMED", swing, current_price
        )

        # Bear swing: fib_0382 = 110 - 10 * 0.382 = 106.18
        # fib_2 = 110 - 10 * 2.0 = 90
        assert "105.00" in explanation
        assert "106.18" in explanation
        assert "90.00" in explanation
        assert "below 0.382" in explanation
        assert "Active range" in explanation

    def test_swing_invalidated_bull_explanation(self):
        """Test trigger explanation for bull SWING_INVALIDATED."""
        swing = self._create_bull_swing()
        current_price = 98.0
        excess = 2.0  # Price went 2 pts below pivot

        explanation = _format_trigger_explanation(
            "SWING_INVALIDATED", swing, current_price, excess_amount=excess
        )

        assert "98.00" in explanation
        assert "low" in explanation
        assert "100.00" in explanation
        assert "2.00" in explanation
        assert "invalidated" in explanation

    def test_swing_invalidated_bear_explanation(self):
        """Test trigger explanation for bear SWING_INVALIDATED."""
        swing = self._create_bear_swing()
        current_price = 112.0
        excess = 2.0  # Price went 2 pts above pivot

        explanation = _format_trigger_explanation(
            "SWING_INVALIDATED", swing, current_price, excess_amount=excess
        )

        assert "112.00" in explanation
        assert "high" in explanation
        assert "110.00" in explanation
        assert "2.00" in explanation
        assert "invalidated" in explanation

    def test_swing_completed_bull_explanation(self):
        """Test trigger explanation for bull SWING_COMPLETED."""
        swing = self._create_bull_swing()
        current_price = 120.5

        explanation = _format_trigger_explanation(
            "SWING_COMPLETED", swing, current_price, level=2.0, previous_level=1.9
        )

        # fib_2 = 100 + 10 * 2.0 = 120
        assert "120.50" in explanation
        assert "2x target" in explanation
        assert "120.00" in explanation
        assert "Full extension achieved" in explanation

    def test_swing_completed_bear_explanation(self):
        """Test trigger explanation for bear SWING_COMPLETED."""
        swing = self._create_bear_swing()
        current_price = 89.5

        explanation = _format_trigger_explanation(
            "SWING_COMPLETED", swing, current_price, level=2.0, previous_level=1.9
        )

        # fib_2 = 110 - 10 * 2.0 = 90
        assert "89.50" in explanation
        assert "2x target" in explanation
        assert "90.00" in explanation
        assert "Full extension achieved" in explanation

    def test_level_cross_bull_explanation(self):
        """Test trigger explanation for bull LEVEL_CROSS."""
        swing = self._create_bull_swing()
        current_price = 106.5

        explanation = _format_trigger_explanation(
            "LEVEL_CROSS", swing, current_price, level=0.618, previous_level=0.5
        )

        # level_price = 100 + 10 * 0.618 = 106.18
        assert "Crossed 0.618" in explanation
        assert "106.18" in explanation
        assert "below" in explanation
        assert "above" in explanation

    def test_level_cross_bear_explanation(self):
        """Test trigger explanation for bear LEVEL_CROSS."""
        swing = self._create_bear_swing()
        current_price = 103.5

        explanation = _format_trigger_explanation(
            "LEVEL_CROSS", swing, current_price, level=0.618, previous_level=0.5
        )

        # level_price = 110 - 10 * 0.618 = 103.82
        assert "Crossed 0.618" in explanation
        assert "103.82" in explanation

    def test_events_include_trigger_explanation(self):
        """Test that events generated by advance_bar_incremental include trigger_explanation."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[100.0],
            lows=[90.0],
            closes=[95.0],
            lookback=5,
            protection_tolerance=0.1,
        )

        # Add an active bull swing
        swing = self._create_bull_swing()
        state.active_swings["test-bull"] = swing
        state.fib_levels["test-bull"] = 0.4

        # Advance with a bar that crosses 0.5 level
        events = advance_bar_incremental(
            bar_high=106.0,
            bar_low=104.0,
            bar_close=105.5,
            state=state
        )

        # Find level cross event
        level_cross_events = [e for e in events if e.event_type == "LEVEL_CROSS"]
        assert len(level_cross_events) == 1

        # Check trigger_explanation is populated
        event = level_cross_events[0]
        assert event.trigger_explanation is not None
        assert len(event.trigger_explanation) > 0
        assert "Crossed 0.5" in event.trigger_explanation

    def test_invalidation_event_includes_explanation(self):
        """Test that invalidation events include trigger_explanation."""
        state = IncrementalSwingState(
            median_candle=5.0,
            price_range=100.0,
            scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
            highs=[100.0],
            lows=[90.0],
            closes=[95.0],
            lookback=5,
            protection_tolerance=0.1,
        )

        # Add an active bull swing
        swing = self._create_bull_swing()
        state.active_swings["test-bull"] = swing
        state.fib_levels["test-bull"] = 0.5

        # Advance with a bar that violates the pivot
        events = advance_bar_incremental(
            bar_high=105.0,
            bar_low=98.0,  # Below threshold
            bar_close=100.0,
            state=state
        )

        invalidation_events = [e for e in events if e.event_type == "SWING_INVALIDATED"]
        assert len(invalidation_events) == 1

        event = invalidation_events[0]
        assert event.trigger_explanation is not None
        assert "invalidated" in event.trigger_explanation
        assert "low" in event.trigger_explanation
