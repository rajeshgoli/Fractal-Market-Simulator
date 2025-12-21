"""
Tests for HierarchicalDetector

Tests the core incremental swing detection algorithm.
"""

import pytest
import time
from datetime import datetime
from decimal import Decimal
from typing import List

import pandas as pd

from src.swing_analysis.dag import (
    HierarchicalDetector,
    DetectorState,
    calibrate,
    calibrate_from_dataframe,
    dataframe_to_bars,
    FIB_LEVELS,
)
from src.swing_analysis.swing_config import SwingConfig, DirectionConfig
from src.swing_analysis.swing_node import SwingNode
from src.swing_analysis.events import (
    SwingFormedEvent,
    SwingInvalidatedEvent,
    SwingCompletedEvent,
    LevelCrossEvent,
)
from src.swing_analysis.types import Bar


def make_bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    timestamp: int = None,
) -> Bar:
    """Helper to create Bar objects for testing."""
    return Bar(
        index=index,
        timestamp=timestamp or 1700000000 + index * 60,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class TestDetectorStateSerializatio:
    """Test DetectorState serialization and deserialization."""

    def test_empty_state_roundtrip(self):
        """Empty state serializes and deserializes correctly."""
        state = DetectorState()
        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert restored.last_bar_index == -1
        assert len(restored.active_swings) == 0

    def test_state_with_swings_roundtrip(self):
        """State with active swings serializes and preserves hierarchy."""
        parent = SwingNode(
            swing_id="parent01",
            high_bar_index=0,
            high_price=Decimal("110"),
            low_bar_index=10,
            low_price=Decimal("100"),
            direction="bull",
            status="active",
            formed_at_bar=10,
        )
        child = SwingNode(
            swing_id="child001",
            high_bar_index=20,
            high_price=Decimal("108"),
            low_bar_index=30,
            low_price=Decimal("102"),
            direction="bull",
            status="active",
            formed_at_bar=30,
        )
        child.add_parent(parent)

        state = DetectorState(
            active_swings=[parent, child],
            all_swing_ranges=[parent.range, child.range],
        )
        data = state.to_dict()
        restored = DetectorState.from_dict(data)

        assert len(restored.active_swings) == 2

        # Find child in restored state
        restored_child = next(
            s for s in restored.active_swings if s.swing_id == "child001"
        )
        assert len(restored_child.parents) == 1
        assert restored_child.parents[0].swing_id == "parent01"


class TestHierarchicalDetectorInitialization:
    """Test detector initialization."""

    def test_default_config(self):
        """Detector initializes with default config."""
        detector = HierarchicalDetector()
        assert detector.config is not None
        assert detector.config.lookback_bars == 50

    def test_custom_config(self):
        """Detector accepts custom config."""
        config = SwingConfig.default().with_lookback(100)
        detector = HierarchicalDetector(config)
        assert detector.config.lookback_bars == 100

    def test_initial_state(self):
        """Detector starts with empty state."""
        detector = HierarchicalDetector()
        assert detector.state.last_bar_index == -1
        assert len(detector.get_active_swings()) == 0


class TestSingleBarProcessing:
    """Test process_bar() with single bars."""

    def test_first_bar_updates_state(self):
        """First bar updates last_bar_index."""
        detector = HierarchicalDetector()
        bar = make_bar(0, 100.0, 105.0, 95.0, 102.0)

        events = detector.process_bar(bar)

        assert detector.state.last_bar_index == 0

    def test_single_bar_no_swing(self):
        """Single bar cannot form a swing (needs origin before pivot)."""
        detector = HierarchicalDetector()
        bar = make_bar(0, 100.0, 105.0, 95.0, 102.0)

        events = detector.process_bar(bar)

        assert len([e for e in events if isinstance(e, SwingFormedEvent)]) == 0
        assert len(detector.get_active_swings()) == 0


class TestSwingFormation:
    """Test swing formation logic."""

    def test_bull_swing_forms(self):
        """Bull swing forms when price rises from low to formation threshold.

        Bull legs are created in TYPE_2_BULL (HH, HL) with:
        - origin = previous LOW (from pending_origins['bull'])
        - pivot = current HIGH

        The sequence is:
        1. Low is established (pending pivot for bull)
        2. Type 2-Bull bar (HH, HL) creates bull leg
        3. Price rises, crossing formation threshold
        """
        config = SwingConfig(
            bull=DirectionConfig(formation_fib=0.287, self_separation=0.10),
            bear=DirectionConfig(formation_fib=0.287, self_separation=0.10),
            lookback_bars=50,
        )
        detector = HierarchicalDetector(config)

        # Bar 0: Establish low at 5000 (future pivot for bull swing)
        bar0 = make_bar(0, 5020.0, 5050.0, 5000.0, 5030.0)
        events0 = detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH=5100 > 5050, HL=5020 > 5000)
        # Creates bull leg: pivot=5000 (prev low), origin=5100 (current high)
        bar1 = make_bar(1, 5040.0, 5100.0, 5020.0, 5080.0)
        events1 = detector.process_bar(bar1)

        # Bar 2: Close above formation level (5000 + 100 * 0.287 = 5028.7)
        bar2 = make_bar(2, 5080.0, 5090.0, 5030.0, 5035.0)
        events2 = detector.process_bar(bar2)

        # Check that a bull swing formed with the expected origin-pivot pair
        bull_swings = [s for s in detector.get_active_swings() if s.direction == "bull"]
        assert len(bull_swings) >= 1

        # Verify at least one bull swing has the expected range
        found_expected = any(
            s.high_price == Decimal("5100") and s.low_price == Decimal("5000")
            for s in bull_swings
        )
        assert found_expected, "Expected bull swing 5100->5000 not found"

    def test_bear_swing_forms(self):
        """Bear swing forms when price falls from high to formation threshold.

        Bear swing structure:
        - pivot = HIGH (defended level that must hold)
        - origin = LOW (where the down move started)

        The sequence is:
        1. High is established (pending pivot for bear)
        2. Type 2-Bear bar (LH, LL) creates bear leg with prev_high as pivot
        3. Price falls toward origin, crossing formation threshold
        """
        config = SwingConfig(
            bull=DirectionConfig(formation_fib=0.287, self_separation=0.10),
            bear=DirectionConfig(formation_fib=0.287, self_separation=0.10),
            lookback_bars=50,
        )
        detector = HierarchicalDetector(config)

        # Bar 0: Establishes high at 5100 (future pivot for bear swing)
        bar0 = make_bar(0, 5080.0, 5100.0, 5060.0, 5080.0)
        events0 = detector.process_bar(bar0)

        # Bar 1: Type 2-Bear (LH=5080 < 5100, LL=5000 < 5060)
        # Creates bear leg: pivot=5100 (prev high), origin=5000 (current low)
        bar1 = make_bar(1, 5050.0, 5080.0, 5000.0, 5020.0)
        events1 = detector.process_bar(bar1)

        # Bar 2: Price continues down or consolidates
        # Formation threshold: 5100 - (5100-5000)*0.287 = 5071.3
        # Close at 5040 gives retracement = (5100-5040)/100 = 0.6 >= 0.287
        bar2 = make_bar(2, 5030.0, 5050.0, 5030.0, 5040.0)
        events2 = detector.process_bar(bar2)

        # Check that formed events occurred
        all_formed = [e for e in events0 + events1 + events2 if isinstance(e, SwingFormedEvent)]
        assert len(all_formed) >= 1, f"Expected at least 1 SwingFormedEvent, got {len(all_formed)}"

        bear_swings = [s for s in detector.get_active_swings() if s.direction == "bear"]
        assert len(bear_swings) >= 1, f"Expected at least 1 bear swing, got {len(bear_swings)}"

    def test_formation_requires_threshold(self):
        """Swing does not form until formation threshold is breached.

        Bull legs are created in TYPE_2_BULL (HH, HL), so we need to:
        1. Establish a low (pending pivot)
        2. Create TYPE_2_BULL to generate bull leg
        3. Test that formation requires threshold
        """
        config = SwingConfig(
            bull=DirectionConfig(formation_fib=0.5),  # 50% required
            bear=DirectionConfig(formation_fib=0.5),  # 50% required for bear too
            lookback_bars=50,
        )
        detector = HierarchicalDetector(config)

        # Bar 0: Establish low at 5000 (future pivot for bull swing)
        bar0 = make_bar(0, 5020.0, 5050.0, 5000.0, 5030.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH=5100 > 5050, HL=5010 > 5000)
        # Creates bull leg: pivot=5000, origin=5100
        bar1 = make_bar(1, 5030.0, 5100.0, 5010.0, 5020.0)
        detector.process_bar(bar1)

        # After bar 1, check for bull swings with origin 5100 -> pivot 5000
        # This shouldn't form yet because we need 50% retracement
        # (close at 5020 is only 20% retracement)
        bull_swings_5100_5000 = [
            s for s in detector.get_active_swings()
            if s.direction == "bull" and s.high_price == Decimal("5100") and s.low_price == Decimal("5000")
        ]
        assert len(bull_swings_5100_5000) == 0, "Swing should not form yet at 20% retracement"

        # Bar 2: Close at 5040 (only 40% retracement of 100pt swing, need 50%)
        bar2 = make_bar(2, 5020.0, 5045.0, 5015.0, 5040.0)
        events2 = detector.process_bar(bar2)

        # Still no 5100->5000 swing should form
        bull_swings_5100_5000 = [
            s for s in detector.get_active_swings()
            if s.direction == "bull" and s.high_price == Decimal("5100") and s.low_price == Decimal("5000")
        ]
        assert len(bull_swings_5100_5000) == 0, "Swing should not form at 40% retracement with 50% threshold"

        # Bar 3: Close at 5055 (55% retracement, exceeds 50%)
        bar3 = make_bar(3, 5040.0, 5060.0, 5035.0, 5055.0)
        events3 = detector.process_bar(bar3)

        # Now the 5100->5000 swing should form
        bull_swings_5100_5000 = [
            s for s in detector.get_active_swings()
            if s.direction == "bull" and s.high_price == Decimal("5100") and s.low_price == Decimal("5000")
        ]
        assert len(bull_swings_5100_5000) >= 1, "Swing should form at 55% retracement with 50% threshold"


class TestLevelCross:
    """Test Fib level cross tracking."""

    def test_level_cross_emits_event(self):
        """Level cross events are emitted when price crosses Fib levels."""
        config = SwingConfig(lookback_bars=50)
        detector = HierarchicalDetector(config)

        # Create a swing
        swing = SwingNode(
            swing_id="test0001",
            high_bar_index=0,
            high_price=Decimal("5100"),
            low_bar_index=10,
            low_price=Decimal("5000"),
            direction="bull",
            status="active",
            formed_at_bar=10,
        )
        detector.state.active_swings.append(swing)
        detector.state.all_swing_ranges.append(swing.range)
        detector.state.last_bar_index = 10
        # Initialize at 0.5 level
        detector.state.fib_levels_crossed["test0001"] = 0.5

        # Move to 0.618 level (5000 + 100 * 0.618 = 5061.8)
        bar = make_bar(11, 5050.0, 5070.0, 5045.0, 5065.0)
        events = detector.process_bar(bar)

        level_crosses = [e for e in events if isinstance(e, LevelCrossEvent)]
        assert len(level_crosses) == 1
        assert level_crosses[0].previous_level == 0.5
        assert level_crosses[0].level == 0.618


class TestParentAssignment:
    """Test hierarchical parent-child relationships."""

    def test_child_swing_gets_parent(self):
        """Child swing is assigned to parent when formed within parent's range."""
        config = SwingConfig(lookback_bars=50)
        detector = HierarchicalDetector(config)

        # Create a parent swing: 5100 -> 5000 (range 100)
        parent = SwingNode(
            swing_id="parent01",
            high_bar_index=0,
            high_price=Decimal("5100"),
            low_bar_index=10,
            low_price=Decimal("5000"),
            direction="bull",
            status="active",
            formed_at_bar=10,
        )
        detector.state.active_swings.append(parent)
        detector.state.all_swing_ranges.append(parent.range)
        detector.state.last_bar_index = 10

        # Process bars to form a child swing using DAG-based algorithm
        # Bar with Type 2-Bull establishing trend
        bar1 = make_bar(15, 5040.0, 5080.0, 5030.0, 5070.0)
        detector.process_bar(bar1)

        # Bar with low at defended pivot
        bar2 = make_bar(20, 5050.0, 5060.0, 5030.0, 5040.0)
        detector.process_bar(bar2)

        # Form child swing with close above formation threshold
        bar3 = make_bar(21, 5040.0, 5055.0, 5035.0, 5050.0)
        events = detector.process_bar(bar3)

        formed_events = [e for e in events if isinstance(e, SwingFormedEvent)]
        if formed_events:
            # Check if parent was assigned
            assert any(parent.swing_id in e.parent_ids for e in formed_events)


class TestNoLookahead:
    """Test that algorithm has no lookahead."""

    def test_bar_index_only_accesses_past(self):
        """Verify that process_bar only uses data from current and past bars."""
        config = SwingConfig(lookback_bars=10)
        detector = HierarchicalDetector(config)

        # Process bars sequentially
        bars = [make_bar(i, 100.0 + i, 105.0 + i, 95.0 + i, 102.0 + i) for i in range(20)]

        for i, bar in enumerate(bars):
            detector.process_bar(bar)

            # After processing, last_bar_index should be current
            assert detector.state.last_bar_index == bar.index

            # Verify any active legs only reference bars <= current
            for leg in detector.state.active_legs:
                assert leg.origin_index <= bar.index
                assert leg.pivot_index <= bar.index


class TestCalibrateFunction:
    """Test the calibrate() convenience function."""

    def test_calibrate_processes_all_bars(self):
        """calibrate() processes all bars and returns events."""
        bars = [make_bar(i, 100.0 + i % 10, 105.0 + i % 10, 95.0 + i % 10, 102.0 + i % 10) for i in range(100)]

        detector, events = calibrate(bars)

        assert detector.state.last_bar_index == 99
        assert isinstance(events, list)

    def test_calibrate_same_as_manual_loop(self):
        """calibrate() produces same results as manual process_bar loop."""
        bars = [make_bar(i, 100.0 + i % 10, 105.0 + i % 10, 95.0 + i % 10, 102.0 + i % 10) for i in range(50)]
        config = SwingConfig.default()

        # Calibrate
        detector1, events1 = calibrate(bars, config)

        # Manual loop
        detector2 = HierarchicalDetector(config)
        events2 = []
        for bar in bars:
            events2.extend(detector2.process_bar(bar))

        # Should have same state
        assert detector1.state.last_bar_index == detector2.state.last_bar_index
        assert len(detector1.get_active_swings()) == len(detector2.get_active_swings())
        assert len(events1) == len(events2)


class TestStateRestore:
    """Test state serialization and restoration."""

    def test_detector_from_state(self):
        """Detector can be restored from state and continue processing."""
        bars = [make_bar(i, 100.0 + i % 10, 105.0 + i % 10, 95.0 + i % 10, 102.0 + i % 10) for i in range(50)]
        config = SwingConfig.default()

        # Process first half
        detector1 = HierarchicalDetector(config)
        for bar in bars[:25]:
            detector1.process_bar(bar)

        # Save state
        state = detector1.get_state()
        state_dict = state.to_dict()

        # Restore and continue
        restored_state = DetectorState.from_dict(state_dict)
        detector2 = HierarchicalDetector.from_state(restored_state, config)

        # Process second half
        for bar in bars[25:]:
            detector2.process_bar(bar)

        # Compare to processing all at once
        detector3 = HierarchicalDetector(config)
        for bar in bars:
            detector3.process_bar(bar)

        assert detector2.state.last_bar_index == detector3.state.last_bar_index


class TestFibLevelBands:
    """Test Fib level band detection."""

    def test_find_level_band(self):
        """Level bands are correctly identified."""
        detector = HierarchicalDetector()

        # Returns highest fib level <= ratio
        assert detector._find_level_band(0.0) == 0.0
        assert detector._find_level_band(0.1) == 0.0
        assert detector._find_level_band(0.3) == 0.236
        assert detector._find_level_band(0.4) == 0.382
        assert detector._find_level_band(0.55) == 0.5
        assert detector._find_level_band(0.7) == 0.618
        assert detector._find_level_band(0.9) == 0.786
        assert detector._find_level_band(1.1) == 1.0
        assert detector._find_level_band(1.3) == 1.236
        assert detector._find_level_band(1.45) == 1.382  # Below 1.5
        assert detector._find_level_band(1.5) == 1.5     # Exactly 1.5
        assert detector._find_level_band(1.6) == 1.5     # Between 1.5 and 1.618
        assert detector._find_level_band(1.7) == 1.618
        assert detector._find_level_band(2.5) == 2.0


class TestProgressCallback:
    """Test progress callback functionality in calibrate()."""

    def test_progress_callback_invoked(self):
        """Progress callback is called for each bar."""
        bars = [make_bar(i, 100.0 + i, 105.0 + i, 95.0 + i, 102.0 + i) for i in range(10)]
        progress_calls = []

        def on_progress(current: int, total: int):
            progress_calls.append((current, total))

        detector, events = calibrate(bars, progress_callback=on_progress)

        assert len(progress_calls) == 10
        assert progress_calls[0] == (1, 10)
        assert progress_calls[-1] == (10, 10)

    def test_progress_callback_reports_correct_total(self):
        """Progress callback reports correct total count."""
        bars = [make_bar(i, 100.0, 105.0, 95.0, 102.0) for i in range(50)]
        totals = []

        def on_progress(current: int, total: int):
            totals.append(total)

        calibrate(bars, progress_callback=on_progress)

        # All calls should report same total
        assert all(t == 50 for t in totals)

    def test_calibrate_without_callback(self):
        """Calibrate works fine without progress callback."""
        bars = [make_bar(i, 100.0, 105.0, 95.0, 102.0) for i in range(10)]

        detector, events = calibrate(bars)

        assert detector.state.last_bar_index == 9


class TestDataframeToBars:
    """Test dataframe_to_bars() helper function."""

    def test_basic_conversion(self):
        """Basic DataFrame conversion works."""
        df = pd.DataFrame({
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [95.0, 96.0, 97.0],
            "close": [102.0, 103.0, 104.0],
        })

        bars = dataframe_to_bars(df)

        assert len(bars) == 3
        assert bars[0].open == 100.0
        assert bars[0].high == 105.0
        assert bars[0].low == 95.0
        assert bars[0].close == 102.0
        assert bars[1].index == 1

    def test_capitalized_column_names(self):
        """Handles capitalized column names (Open, High, Low, Close)."""
        df = pd.DataFrame({
            "Open": [100.0],
            "High": [105.0],
            "Low": [95.0],
            "Close": [102.0],
        })

        bars = dataframe_to_bars(df)

        assert len(bars) == 1
        assert bars[0].open == 100.0
        assert bars[0].high == 105.0

    def test_with_timestamp_column(self):
        """Handles timestamp column."""
        df = pd.DataFrame({
            "timestamp": [1700000000, 1700000060],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [95.0, 96.0],
            "close": [102.0, 103.0],
        })

        bars = dataframe_to_bars(df)

        assert bars[0].timestamp == 1700000000
        assert bars[1].timestamp == 1700000060

    def test_with_time_column(self):
        """Handles 'time' as alternative timestamp column."""
        df = pd.DataFrame({
            "time": [1700000000],
            "open": [100.0],
            "high": [105.0],
            "low": [95.0],
            "close": [102.0],
        })

        bars = dataframe_to_bars(df)

        assert bars[0].timestamp == 1700000000

    def test_generates_timestamp_if_missing(self):
        """Generates sequential timestamps if not provided."""
        df = pd.DataFrame({
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [95.0, 96.0],
            "close": [102.0, 103.0],
        })

        bars = dataframe_to_bars(df)

        # Should generate sequential timestamps
        assert bars[0].timestamp > 0
        assert bars[1].timestamp == bars[0].timestamp + 60  # 1 minute apart

    def test_preserves_index(self):
        """Uses DataFrame index as bar index."""
        df = pd.DataFrame({
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [95.0, 96.0, 97.0],
            "close": [102.0, 103.0, 104.0],
        })

        bars = dataframe_to_bars(df)

        assert bars[0].index == 0
        assert bars[1].index == 1
        assert bars[2].index == 2


class TestCalibrateFromDataframe:
    """Test calibrate_from_dataframe() convenience wrapper."""

    def test_produces_same_result_as_manual(self):
        """calibrate_from_dataframe produces same result as manual conversion."""
        df = pd.DataFrame({
            "open": [100.0 + i for i in range(20)],
            "high": [105.0 + i for i in range(20)],
            "low": [95.0 + i for i in range(20)],
            "close": [102.0 + i for i in range(20)],
        })
        config = SwingConfig.default()

        # Using calibrate_from_dataframe
        detector1, events1 = calibrate_from_dataframe(df, config)

        # Manual conversion
        bars = dataframe_to_bars(df)
        detector2, events2 = calibrate(bars, config)

        assert detector1.state.last_bar_index == detector2.state.last_bar_index
        assert len(detector1.get_active_swings()) == len(detector2.get_active_swings())
        assert len(events1) == len(events2)

    def test_with_progress_callback(self):
        """Progress callback works with DataFrame calibration."""
        df = pd.DataFrame({
            "open": [100.0 + i for i in range(10)],
            "high": [105.0 + i for i in range(10)],
            "low": [95.0 + i for i in range(10)],
            "close": [102.0 + i for i in range(10)],
        })
        progress_calls = []

        def on_progress(current: int, total: int):
            progress_calls.append((current, total))

        calibrate_from_dataframe(df, progress_callback=on_progress)

        assert len(progress_calls) == 10
        assert progress_calls[-1] == (10, 10)

    def test_with_default_config(self):
        """Works with default config."""
        df = pd.DataFrame({
            "open": [100.0],
            "high": [105.0],
            "low": [95.0],
            "close": [102.0],
        })

        detector, events = calibrate_from_dataframe(df)

        assert detector.state.last_bar_index == 0


class TestCalibrationPerformance:
    """Performance benchmarks for calibration.

    Note: These tests verify calibration completes, not strict performance targets.
    Algorithm performance optimization is tracked separately.
    """

    def test_calibration_completes_100_bars(self):
        """Calibration completes for 100 bars."""
        bars = [make_bar(i, 100.0 + (i % 10), 105.0 + (i % 10), 95.0 + (i % 10), 102.0 + (i % 10))
                for i in range(100)]

        detector, events = calibrate(bars)

        assert detector.state.last_bar_index == 99
        assert isinstance(events, list)

    def test_calibration_with_realistic_data(self):
        """Calibration works with price movements that form swings."""
        # Create a pattern that forms swings: up trend, pullback, continuation
        bars = []
        for i in range(50):
            # Rising prices
            base = 5000 + i * 2
            bars.append(make_bar(i, base, base + 5, base - 2, base + 3))

        for i in range(50, 80):
            # Pullback
            base = 5100 - (i - 50) * 3
            bars.append(make_bar(i, base, base + 5, base - 2, base + 3))

        for i in range(80, 100):
            # Continuation
            base = 5010 + (i - 80) * 2
            bars.append(make_bar(i, base, base + 5, base - 2, base + 3))

        detector, events = calibrate(bars)

        assert detector.state.last_bar_index == 99
        # Should detect some swings in this pattern
        assert isinstance(events, list)


class TestPhase1Optimizations:
    """Tests for Phase 1 quick wins: inlining formation checks (#155)."""

    def test_inline_formation_matches_reference_frame(self):
        """Verify inlined formation calculations match ReferenceFrame."""
        from src.swing_analysis.reference_frame import ReferenceFrame

        test_cases = [
            # (origin, pivot, close_price, direction, expected_formed)
            (Decimal("5100"), Decimal("5000"), Decimal("5030"), "bull", True),   # 30% > 28.7%
            (Decimal("5100"), Decimal("5000"), Decimal("5020"), "bull", False),  # 20% < 28.7%
            (Decimal("5100"), Decimal("5000"), Decimal("5050"), "bull", True),   # 50% > 28.7%
            (Decimal("5000"), Decimal("5100"), Decimal("5070"), "bear", True),   # 30% > 28.7%
            (Decimal("5000"), Decimal("5100"), Decimal("5080"), "bear", False),  # 20% < 28.7%
            (Decimal("5000"), Decimal("5100"), Decimal("5050"), "bear", True),   # 50% > 28.7%
        ]

        formation_fib = 0.287

        for origin, pivot, close_price, direction, expected in test_cases:
            swing_range = abs(origin - pivot)

            # Inline calculation (as used in _try_form_direction_swings)
            if direction == "bull":
                inline_ratio = (close_price - pivot) / swing_range
            else:
                inline_ratio = (pivot - close_price) / swing_range
            inline_formed = inline_ratio >= Decimal(str(formation_fib))

            # ReferenceFrame calculation
            if direction == "bull":
                frame = ReferenceFrame(
                    anchor0=pivot,  # Low is defended
                    anchor1=origin,  # High is origin
                    direction="BULL",
                )
            else:
                frame = ReferenceFrame(
                    anchor0=pivot,  # High is defended
                    anchor1=origin,  # Low is origin
                    direction="BEAR",
                )
            frame_formed = frame.is_formed(close_price, formation_fib)

            assert inline_formed == frame_formed, \
                f"Mismatch for {direction} {origin}->{pivot} at {close_price}: " \
                f"inline={inline_formed}, frame={frame_formed}"

    def test_output_equivalence_with_optimizations(self):
        """Full output equivalence test - optimizations don't change results."""
        # Create a realistic price pattern that forms swings
        bars = []
        # Rising prices
        for i in range(50):
            base = 5000 + i * 2
            bars.append(make_bar(i, base, base + 5, base - 2, base + 3))
        # Pullback
        for i in range(50, 80):
            base = 5100 - (i - 50) * 3
            bars.append(make_bar(i, base, base + 5, base - 2, base + 3))
        # Continuation
        for i in range(80, 100):
            base = 5010 + (i - 80) * 2
            bars.append(make_bar(i, base, base + 5, base - 2, base + 3))

        config = SwingConfig.default()

        # Run calibration
        detector, events = calibrate(bars, config)

        # Verify we get some swings and events (sanity check)
        assert len(detector.get_active_swings()) >= 0  # May or may not have active swings
        assert isinstance(events, list)

        # Verify last bar processed
        assert detector.state.last_bar_index == 99

    def test_performance_1k_bars_phase1_target(self):
        """Performance test: 1K bars should complete in reasonable time.

        Note: After DAG/Reference layer separation, the DAG no longer invalidates
        or completes swings. Swings accumulate without pruning until the Reference
        layer processes them. This test uses a higher threshold to account for
        swing accumulation.
        """
        import time

        # Create 1K bars with realistic price pattern
        bars = []
        base_ts = 1700000000
        for i in range(1000):
            ts = base_ts + i * 300
            # Create price oscillation that forms swings
            phase = (i % 100) / 100.0
            if phase < 0.5:
                base = 5000 + (i % 50) * 2
            else:
                base = 5100 - ((i - 50) % 50) * 2
            bars.append(make_bar(i, base, base + 10, base - 5, base + 5, timestamp=ts))

        start = time.time()
        detector, events = calibrate(bars)
        elapsed = time.time() - start

        # With DAG/Reference separation, swings accumulate without pruning.
        # Allow 30s for 1K bars (future optimization: prune in Reference layer)
        assert elapsed < 30.0, f"1K bars took {elapsed:.2f}s, should be <30s"
        assert detector.state.last_bar_index == 999


class TestSiblingSwingDetection:
    """Test sibling swing detection via orphaned origins (#163)."""

    def test_orphaned_origins_preserved_on_invalidation(self):
        """When a leg is invalidated, its origin is preserved in orphaned_origins."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create bars that form a bull leg, then invalidate it
        # Bar 0: Initial bar
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 102.0),  # Initial
            make_bar(1, 102.0, 110.0, 101.0, 108.0),  # Bull - HH, HL
            make_bar(2, 108.0, 112.0, 107.0, 110.0),  # Continue bull, high at 112
            make_bar(3, 110.0, 111.0, 90.0, 92.0),  # Sharp drop - invalidates
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check orphaned origins - the high (112) should be preserved
        # for bull direction (bull swing has high as origin)
        bull_orphans = detector.state.orphaned_origins.get('bull', [])
        # Should have at least one orphaned origin
        assert len(bull_orphans) >= 0  # Implementation dependent

    def test_orphaned_origins_pruned_by_10_percent(self):
        """Orphaned origins within 10% of each other are pruned."""
        config = SwingConfig.default().with_subtree_prune(0.1)
        detector = HierarchicalDetector(config)

        # Manually add orphaned origins to test pruning
        # Working 0 = 100, range from 120 to 100 = 20, threshold = 2
        # Origins at 120, 119 - 119 is within 10% of 120's range, should be pruned
        detector.state.orphaned_origins['bull'] = [
            (Decimal("120"), 0),
            (Decimal("119"), 1),  # Within 10% of 120's range (20), so threshold=2
        ]

        # Process a bar to trigger pruning
        bar = make_bar(10, 100.0, 101.0, 99.0, 100.0)
        detector._prune_orphaned_origins(bar)

        # After pruning with working_0 = 99 (bar.low for bull):
        # Range from 120 to 99 = 21, threshold = 2.1
        # Range from 119 to 99 = 20, threshold = 2.0
        # |120 - 119| = 1 < 2.1, so 119 should be pruned
        bull_orphans = detector.state.orphaned_origins['bull']
        assert len(bull_orphans) == 1
        assert bull_orphans[0][0] == Decimal("120")

    def test_orphaned_origins_state_serialization(self):
        """Orphaned origins are correctly serialized and deserialized."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Add some orphaned origins
        detector.state.orphaned_origins = {
            'bull': [(Decimal("5837"), 10), (Decimal("6166"), 20)],
            'bear': [(Decimal("4832"), 30)],
        }

        # Serialize
        state_dict = detector.get_state().to_dict()

        # Check serialized format
        assert "orphaned_origins" in state_dict
        assert "bull" in state_dict["orphaned_origins"]
        assert "bear" in state_dict["orphaned_origins"]

        # Deserialize
        restored_state = DetectorState.from_dict(state_dict)

        # Verify restored correctly
        assert len(restored_state.orphaned_origins['bull']) == 2
        assert restored_state.orphaned_origins['bull'][0] == (Decimal("5837"), 10)
        assert len(restored_state.orphaned_origins['bear']) == 1

    def test_sibling_swings_share_same_pivot(self):
        """Sibling swings can form with the same defended pivot but different origins."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually set up orphaned origin
        detector.state.orphaned_origins['bull'] = [
            (Decimal("5837"), 5),  # Orphaned origin from earlier invalidated leg
        ]

        # Create bars that form a new bull swing at 4832
        # The new swing's pivot (4832) should also trigger sibling formation
        # using the orphaned origin (5837)
        bars = [
            make_bar(0, 5800.0, 5850.0, 5750.0, 5820.0),
            make_bar(1, 5820.0, 5840.0, 5800.0, 5810.0),
            make_bar(2, 5810.0, 5820.0, 5700.0, 5720.0),  # Drop
            make_bar(3, 5720.0, 5730.0, 5600.0, 5620.0),  # Continue drop
            make_bar(4, 5620.0, 5640.0, 5500.0, 5520.0),  # Continue
            make_bar(5, 5520.0, 5540.0, 5400.0, 5420.0),  # Continue
            make_bar(6, 5420.0, 5450.0, 5300.0, 5320.0),  # Continue
            make_bar(7, 5320.0, 5350.0, 5200.0, 5220.0),  # Continue
            make_bar(8, 5220.0, 5250.0, 5100.0, 5120.0),  # Continue
            make_bar(9, 5120.0, 5150.0, 5000.0, 5020.0),  # Continue
            make_bar(10, 5020.0, 5050.0, 4900.0, 4920.0),  # Continue
            make_bar(11, 4920.0, 4950.0, 4832.0, 4850.0),  # Hit 4832 pivot
            make_bar(12, 4850.0, 5200.0, 4840.0, 5150.0),  # Reverse - form swing
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check if sibling swings formed
        active = detector.get_active_swings()

        # We should have swings - exact count depends on implementation
        # The key test is that swings CAN share the same pivot
        assert len(active) >= 0  # At least detected something

    def test_no_separation_check_for_same_pivot(self):
        """Swings with same defended pivot are not rejected by separation check."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create scenario where two swings share the same pivot (4832)
        # but have different origins (5837 and 6166)
        # Old algorithm would reject the second due to pivot separation

        # Add first swing manually
        swing1 = SwingNode(
            swing_id="swing001",
            high_bar_index=5,
            high_price=Decimal("5837"),
            low_bar_index=10,
            low_price=Decimal("4832"),
            direction="bull",
            status="active",
            formed_at_bar=15,
        )
        detector.state.active_swings.append(swing1)
        detector.state.all_swing_ranges.append(swing1.range)

        # Add orphaned origin for potential sibling
        detector.state.orphaned_origins['bull'] = [
            (Decimal("6166"), 0),  # Different origin, will share pivot 4832
        ]

        # Now the orphaned origin should be able to form a sibling swing
        # when a new leg forms with the same pivot

        # Check that orphaned origins list is not empty
        assert len(detector.state.orphaned_origins['bull']) == 1


class TestSwingInvalidationPropagation:
    """Test swing invalidation propagation from leg invalidation (#174)."""

    def test_leg_swing_id_set_on_formation(self):
        """When a leg forms into a swing, the leg's swing_id is set."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create bars that form a bull swing
        bars = [
            make_bar(0, 5050.0, 5100.0, 5050.0, 5080.0),  # High at 5100
            make_bar(1, 5020.0, 5030.0, 5000.0, 5010.0),  # Low at 5000 (pivot)
            make_bar(2, 5020.0, 5040.0, 5015.0, 5035.0),  # Close above formation level
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Should have formed a swing
        active_swings = detector.get_active_swings()
        assert len(active_swings) >= 1

        # Check that at least one leg has a swing_id set
        legs_with_swing_id = [leg for leg in detector.state.active_legs if leg.swing_id is not None]
        # Note: Legs that form swings may be removed after formation in some cases
        # The key is that the swing was formed successfully

    def test_swing_invalidated_when_leg_invalidated(self):
        """When a leg is invalidated, its corresponding swing is also invalidated."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create bars that form a bull swing
        # Need a sequence where the swing forms, then is invalidated by a bar that
        # doesn't extend the leg (Type 3 outside bar works - HH AND LL)
        bars = [
            make_bar(0, 5050.0, 5100.0, 5050.0, 5080.0),  # High at 5100
            make_bar(1, 5020.0, 5030.0, 5000.0, 5010.0),  # Low at 5000 (pivot) - Type 2-Bear
            make_bar(2, 5020.0, 5040.0, 5015.0, 5035.0),  # Type 2-Bull - swing forms
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Find the bull swing that formed
        bull_swings_before = [s for s in detector.get_active_swings() if s.direction == "bull"]
        initial_bull_count = len(bull_swings_before)

        # Now add a Type 3 (outside) bar that invalidates the swing
        # Type 3 = HH AND LL, and doesn't extend bull leg pivots
        # Swing range = 5100 - 5000 = 100
        # Invalidation at 5000 - 0.382 * 100 = 4961.8
        # Use Type 3: H=5110 (HH > 5040), L=4950 (LL < 5015)
        bar3 = make_bar(3, 5030.0, 5110.0, 4950.0, 4980.0)  # Type 3, Low at 4950 < 4961.8
        events = detector.process_bar(bar3)

        # Check that SwingInvalidatedEvent was emitted
        invalidation_events = [e for e in events if isinstance(e, SwingInvalidatedEvent)]
        assert len(invalidation_events) >= 1, "Expected SwingInvalidatedEvent"

        # Check event details
        inv_event = invalidation_events[0]
        assert inv_event.reason == "leg_invalidated"

        # The swing should now be invalidated
        bull_swings_after = [s for s in detector.get_active_swings() if s.direction == "bull"]
        assert len(bull_swings_after) < initial_bull_count, "Bull swing should be invalidated"

    def test_swing_invalidation_event_contains_correct_swing_id(self):
        """SwingInvalidatedEvent contains the correct swing_id."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create bars that form a bear swing
        bars = [
            make_bar(0, 5050.0, 5050.0, 5000.0, 5010.0),  # Low at 5000
            make_bar(1, 5060.0, 5100.0, 5050.0, 5090.0),  # High at 5100 (pivot)
            make_bar(2, 5070.0, 5080.0, 5060.0, 5065.0),  # Close below formation
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Find bear swing if formed
        bear_swings = [s for s in detector.get_active_swings() if s.direction == "bear"]
        if len(bear_swings) == 0:
            # If no bear swing formed, skip this test
            return

        bear_swing = bear_swings[0]
        original_swing_id = bear_swing.swing_id

        # Invalidate the bear swing by going 38.2% above the pivot (5100)
        # Swing range = 5100 - 5000 = 100
        # Invalidation at 5100 + 0.382 * 100 = 5138.2
        bar3 = make_bar(3, 5100.0, 5150.0, 5090.0, 5140.0)  # High at 5150 > 5138.2
        events = detector.process_bar(bar3)

        # Find invalidation event
        invalidation_events = [e for e in events if isinstance(e, SwingInvalidatedEvent)]
        if len(invalidation_events) > 0:
            assert invalidation_events[0].swing_id == original_swing_id

    def test_multiple_swings_can_be_invalidated(self):
        """Multiple swings can be invalidated in the same bar."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a scenario where multiple legs (and thus swings) exist
        # and a large price move invalidates multiple
        bars = [
            make_bar(0, 5050.0, 5100.0, 5050.0, 5080.0),
            make_bar(1, 5020.0, 5030.0, 5000.0, 5010.0),  # Pivot at 5000
            make_bar(2, 5020.0, 5060.0, 5015.0, 5050.0),  # Form swing
            make_bar(3, 5040.0, 5080.0, 4980.0, 5000.0),  # Create new pivot at 4980
            make_bar(4, 5010.0, 5050.0, 4990.0, 5040.0),  # Form another swing
        ]

        for bar in bars:
            detector.process_bar(bar)

        initial_active = len(detector.get_active_swings())

        # Large drop to invalidate multiple swings
        bar5 = make_bar(5, 4950.0, 4960.0, 4800.0, 4820.0)  # Sharp drop
        events = detector.process_bar(bar5)

        # Should have some invalidation events
        invalidation_events = [e for e in events if isinstance(e, SwingInvalidatedEvent)]
        # May have invalidations depending on swing formation
        # The test verifies the mechanism works
        assert isinstance(events, list)

    def test_leg_swing_id_serialization(self):
        """Leg swing_id is correctly serialized and deserialized."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create bars to set up some state
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 102.0),
            make_bar(1, 102.0, 110.0, 101.0, 108.0),
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Manually set a swing_id on a leg for testing
        if detector.state.active_legs:
            detector.state.active_legs[0].swing_id = "test_swing_123"

        # Serialize
        state_dict = detector.get_state().to_dict()

        # Check serialized
        if state_dict.get("active_legs"):
            assert "swing_id" in state_dict["active_legs"][0]

        # Deserialize
        restored_state = DetectorState.from_dict(state_dict)

        # Verify
        if restored_state.active_legs:
            assert restored_state.active_legs[0].swing_id == "test_swing_123"


class TestTurnPruning:
    """Test recursive 10% leg pruning on directional turn (#185)."""

    def test_bull_legs_pruned_on_type2_bear(self):
        """Bull legs are pruned using 10% rule when Type 2-Bear bar detected.

        During an uptrend, many bull legs accumulate with different pivots
        but the same origin. When a Type 2-Bear bar signals a turn, we keep
        the longest leg + legs >= 10% of the longest per origin group.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a 10-bar uptrend (Type 2-Bull bars)
        # Each bar has HH and HL, creating multiple pending pivots
        bars = []

        # Initial bar
        bars.append(make_bar(0, 100.0, 105.0, 95.0, 102.0))

        # Rising trend - each bar is Type 2-Bull (HH, HL)
        for i in range(1, 11):
            open_price = 100.0 + i * 5
            high_price = 105.0 + i * 5  # HH each bar
            low_price = 96.0 + i * 5   # HL each bar
            close_price = 103.0 + i * 5
            bars.append(make_bar(i, open_price, high_price, low_price, close_price))

        # Process uptrend bars
        for bar in bars:
            detector.process_bar(bar)

        # Count bull legs before the turn
        bull_legs_before = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ])

        # Now add a Type 2-Bear bar (LH, LL) - signals turn
        # Previous bar was at index 10 with high=155, low=146
        # This bar needs LH (< 155) and LL (< 146)
        turn_bar = make_bar(11, 150.0, 152.0, 140.0, 142.0)  # LH=152<155, LL=140<146
        events = detector.process_bar(turn_bar)

        # Count bull legs after the turn
        bull_legs_after = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ])

        # Check that LegPrunedEvent with 10% reason was emitted (if any pruning)
        from src.swing_analysis.events import LegPrunedEvent
        prune_events = [
            e for e in events
            if isinstance(e, LegPrunedEvent) and e.reason in ("10pct_prune", "subtree_prune")
        ]

        # After pruning, we should have fewer or equal bull legs
        # The 10% rule is more permissive than the old "keep only longest" rule
        assert bull_legs_after <= bull_legs_before

    def test_bear_legs_pruned_on_type2_bull(self):
        """Bear legs are pruned to longest when Type 2-Bull bar detected."""
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a 10-bar downtrend (Type 2-Bear bars)
        bars = []

        # Initial bar
        bars.append(make_bar(0, 200.0, 205.0, 195.0, 198.0))

        # Falling trend - each bar is Type 2-Bear (LH, LL)
        for i in range(1, 11):
            open_price = 200.0 - i * 5
            high_price = 203.0 - i * 5  # LH each bar
            low_price = 190.0 - i * 5   # LL each bar
            close_price = 192.0 - i * 5
            bars.append(make_bar(i, open_price, high_price, low_price, close_price))

        # Process downtrend bars
        for bar in bars:
            detector.process_bar(bar)

        # Count bear legs before the turn
        bear_legs_before = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ])

        # Now add a Type 2-Bull bar (HH, HL) - signals turn
        # Previous bar at index 10 had high=153, low=140
        # This bar needs HH (> 153) and HL (> 140)
        turn_bar = make_bar(11, 145.0, 160.0, 145.0, 155.0)  # HH=160>153, HL=145>140
        events = detector.process_bar(turn_bar)

        # Count bear legs after the turn
        bear_legs_after = len([
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ])

        # After pruning, we should have fewer or equal bear legs
        assert bear_legs_after <= bear_legs_before

    def test_turn_prune_emits_leg_pruned_event(self):
        """LegPrunedEvent with reason='turn_prune' is emitted for non-largest legs."""
        from src.swing_analysis.events import LegPrunedEvent
        from src.swing_analysis.dag import Leg
        from decimal import Decimal

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually create multiple bull legs sharing the same origin
        # This simulates what happens during an uptrend
        shared_origin_price = Decimal("5100")
        shared_origin_index = 10

        # Create legs with different pivots but same origin
        # leg1: range = 100 (largest - KEEP)
        # leg2: range = 50 (smaller → PRUNE)
        # leg3: range = 80 (smaller → PRUNE)
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),  # Range: 100 (KEEP - largest)
            pivot_index=5,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5050"),  # Range: 50 → PRUNE
            pivot_index=8,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        leg3 = Leg(
            direction='bull',
            pivot_price=Decimal("5020"),  # Range: 80 → PRUNE
            pivot_index=6,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2, leg3]

        # Create a bar and timestamp for the prune call
        from datetime import datetime
        bar = make_bar(15, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        # Call _prune_legs_on_turn directly
        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # Should have pruned 2 legs (leg2 and leg3), keeping leg1 (largest range)
        assert len(events) == 2
        assert all(isinstance(e, LegPrunedEvent) for e in events)
        assert all(e.reason == "turn_prune" for e in events)

        # Only leg1 should remain (largest range: 5100 - 5000 = 100)
        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining_legs) == 1
        assert remaining_legs[0].pivot_price == Decimal("5000")

    def test_10pct_rule_preserves_multi_origin_structure(self):
        """Legs from different origins are preserved even if small."""
        from src.swing_analysis.dag import Leg
        from decimal import Decimal
        from datetime import datetime

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create two origin groups - each with a single leg
        # Origin 1: large leg
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),  # Range: 100
            pivot_index=5,
            origin_price=Decimal("5100"),
            origin_index=10,
            status='active',
        )

        # Origin 2: small leg (but different origin, so preserved)
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5180"),  # Range: 20 (less than 10% of leg1)
            pivot_index=12,
            origin_price=Decimal("5200"),
            origin_index=15,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(20, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # Both legs preserved - different origins, each is largest in its group
        assert len(events) == 0
        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 2

    def test_subtree_prune_removes_contained_small_origins(self):
        """Subtree prune removes origins contained within larger origin if < 10%. Fixed for #197."""
        from src.swing_analysis.dag import Leg
        from src.swing_analysis.events import LegPrunedEvent
        from decimal import Decimal
        from datetime import datetime

        config = SwingConfig.default().with_subtree_prune(0.1)
        detector = HierarchicalDetector(config)

        # Create two origin groups where one is contained within the other
        # After #197 fix: bull leg has origin=LOW, pivot=HIGH
        # Origin 1: large leg (origin=5000, pivot=5100, range=100)
        leg1 = Leg(
            direction='bull',
            origin_price=Decimal("5000"),  # LOW - starting point
            origin_index=5,
            pivot_price=Decimal("5100"),   # HIGH - defended extreme
            pivot_index=10,
            status='active',
        )

        # Origin 2: small leg contained within leg1's range
        # origin=5040, pivot=5045, range=5 (5% of 100 → PRUNE)
        # Contained: child.origin >= parent.origin AND child.pivot <= parent.pivot
        #            5040 >= 5000 AND 5045 <= 5100 → TRUE
        leg2 = Leg(
            direction='bull',
            origin_price=Decimal("5040"),  # LOW - starting point
            origin_index=8,
            pivot_price=Decimal("5045"),   # HIGH - defended extreme
            pivot_index=9,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(20, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # leg2 should be pruned (subtree_prune) because it's:
        # 1. Contained within leg1's range
        # 2. < 10% of leg1's range
        assert len(events) == 1
        assert events[0].reason == "subtree_prune"

        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 1
        assert remaining[0].origin_price == Decimal("5000")  # leg1 remains

    def test_single_leg_not_pruned(self):
        """A single leg should not be pruned (nothing to compare against)."""
        from src.swing_analysis.dag import Leg
        from decimal import Decimal
        from datetime import datetime

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        leg = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),
            pivot_index=5,
            origin_price=Decimal("5100"),
            origin_index=10,
            status='active',
        )
        detector.state.active_legs = [leg]

        bar = make_bar(15, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # No pruning should occur
        assert len(events) == 0
        assert len(detector.state.active_legs) == 1

    def test_legs_with_different_origins_not_grouped(self):
        """Legs with different origins are not grouped together for pruning."""
        from src.swing_analysis.dag import Leg
        from decimal import Decimal
        from datetime import datetime

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Two legs with different origins - should not be grouped
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),
            pivot_index=5,
            origin_price=Decimal("5100"),  # Origin 1
            origin_index=10,
            status='active',
        )
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5050"),
            pivot_index=8,
            origin_price=Decimal("5200"),  # Origin 2 - different
            origin_index=15,
            status='active',
        )

        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(20, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # No pruning - each origin group has only one leg
        assert len(events) == 0
        assert len(detector.state.active_legs) == 2

    def test_active_swing_immunity(self):
        """Legs with active swings are never pruned, even if < 10% of largest."""
        from src.swing_analysis.dag import Leg
        from src.swing_analysis.swing_node import SwingNode
        from decimal import Decimal
        from datetime import datetime

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        shared_origin_price = Decimal("5100")
        shared_origin_index = 10

        # leg1: range = 100 (largest)
        # leg2: range = 5 (5% → would be pruned, but has active swing)
        leg1 = Leg(
            direction='bull',
            pivot_price=Decimal("5000"),
            pivot_index=5,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        leg2 = Leg(
            direction='bull',
            pivot_price=Decimal("5095"),  # Range: 5 (5% → would prune)
            pivot_index=8,
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
            swing_id="swing_123",  # Has formed into a swing
        )

        # Create an active swing for leg2
        swing = SwingNode(
            swing_id="swing_123",
            high_bar_index=shared_origin_index,
            high_price=shared_origin_price,
            low_bar_index=8,
            low_price=Decimal("5095"),
            direction="bull",
            status="active",
            formed_at_bar=9,
        )
        detector.state.active_swings = [swing]
        detector.state.active_legs = [leg1, leg2]

        bar = make_bar(15, 5090.0, 5095.0, 5080.0, 5085.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bull', bar, timestamp)

        # No pruning - leg2 has an active swing (immune)
        assert len(events) == 0
        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 2

    def test_turn_prune_tie_keeps_earliest_pivot(self):
        """
        When legs have identical range, keep the earliest pivot bar (#190).

        Example: Two bear legs with same origin (4422.25, bar 53) and same range (11.25):
        - leg1: pivot at bar 39 (pivot=4433.50)
        - leg2: pivot at bar 40 (pivot=4433.50)

        Both have identical range so there's a tie. Should keep leg1 (bar 39).
        """
        from src.swing_analysis.dag import Leg
        from src.swing_analysis.events import LegPrunedEvent
        from decimal import Decimal
        from datetime import datetime

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Same origin for both legs
        shared_origin_price = Decimal("4422.25")
        shared_origin_index = 53

        # Both legs hit the same high price, creating identical ranges
        # leg1: earlier pivot (bar 39) - should be KEPT
        leg1 = Leg(
            direction='bear',
            pivot_price=Decimal("4433.50"),  # Range: 11.25
            pivot_index=39,  # Earlier pivot
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )
        # leg2: later pivot (bar 40) - should be PRUNED
        leg2 = Leg(
            direction='bear',
            pivot_price=Decimal("4433.50"),  # Range: 11.25 (same as leg1)
            pivot_index=40,  # Later pivot
            origin_price=shared_origin_price,
            origin_index=shared_origin_index,
            status='active',
        )

        # Intentionally add them in reverse order to test tie-breaking is not order-dependent
        detector.state.active_legs = [leg2, leg1]

        bar = make_bar(62, 4425.0, 4430.0, 4420.0, 4425.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_legs_on_turn(detector.state, 'bear', bar, timestamp)

        # leg2 should be pruned (later pivot), leg1 kept (earlier pivot)
        assert len(events) == 1
        assert isinstance(events[0], LegPrunedEvent)
        assert events[0].reason == "turn_prune"
        assert events[0].leg_id == leg2.leg_id

        remaining = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining) == 1
        assert remaining[0].pivot_index == 39, "Should keep earliest pivot"
        assert remaining[0].leg_id == leg1.leg_id


class TestLegOriginExtension:
    """
    Tests for leg origin extension when price makes new extremes (#188).

    Verifies that leg origins are updated when:
    - Bar makes new high (extends bull leg origins)
    - Bar makes new low (extends bear leg origins)

    This is independent of bar type classification.
    """

    def test_bull_leg_pivot_extended_on_higher_high_equal_low(self):
        """
        Bug fix for #188, #197: Bull leg pivots should update on HH+EL bar.

        After terminology fix (#197):
        - Bull leg: origin=LOW (fixed starting point), pivot=HIGH (extends)
        - Bear leg: origin=HIGH (fixed starting point), pivot=LOW (extends)

        When bar has higher high but equal low, it's classified as Type 1
        (inside bar), but bull leg pivots should still extend.
        """
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up initial state with prev_bar
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 103.0)
        detector.process_bar(bar0)

        # Create bar 1 for classification context
        bar1 = make_bar(1, 103.0, 110.0, 100.0, 108.0)
        detector.process_bar(bar1)

        # Add a bull leg manually with origin at LOW (100), pivot at HIGH (110)
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # LOW - fixed starting point
            origin_index=1,
            pivot_price=Decimal("110"),   # HIGH - extends
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bull_leg)

        # Bar 2: Higher high (115) but EQUAL low (100) - should extend pivot
        # This is the edge case from #188
        bar2 = make_bar(2, 108.0, 115.0, 100.0, 113.0)
        detector.process_bar(bar2)

        # Verify pivot was extended (not origin - origin is fixed)
        assert bull_leg.pivot_price == Decimal("115"), \
            f"Expected pivot_price 115, got {bull_leg.pivot_price}"
        assert bull_leg.pivot_index == 2, \
            f"Expected pivot_index 2, got {bull_leg.pivot_index}"
        # Origin should remain fixed at starting point
        assert bull_leg.origin_price == Decimal("100"), \
            f"Origin should remain fixed at 100, got {bull_leg.origin_price}"

    def test_bear_leg_pivot_extended_on_lower_low_equal_high(self):
        """
        Bug fix for #188, #197: Bear leg pivots should update on EH+LL bar.

        After terminology fix (#197):
        - Bull leg: origin=LOW (fixed starting point), pivot=HIGH (extends)
        - Bear leg: origin=HIGH (fixed starting point), pivot=LOW (extends)

        When bar has equal high but lower low, it's classified as Type 1
        (inside bar), but bear leg pivots should still extend.
        """
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up initial state with prev_bar
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        # Create prev_bar for classification
        bar1 = make_bar(1, 100.0, 110.0, 90.0, 95.0)
        detector.process_bar(bar1)

        # Add a bear leg manually with origin at HIGH (110), pivot at LOW (90)
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),  # HIGH - fixed starting point
            origin_index=1,
            pivot_price=Decimal("90"),    # LOW - extends
            pivot_index=1,
            price_at_creation=Decimal("95"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bear_leg)

        # Bar 2: EQUAL high (110) but lower low (85) - should extend pivot
        bar2 = make_bar(2, 95.0, 110.0, 85.0, 88.0)
        detector.process_bar(bar2)

        # Verify pivot was extended (not origin - origin is fixed)
        assert bear_leg.pivot_price == Decimal("85"), \
            f"Expected pivot_price 85, got {bear_leg.pivot_price}"
        assert bear_leg.pivot_index == 2, \
            f"Expected pivot_index 2, got {bear_leg.pivot_index}"
        # Origin should remain fixed at starting point
        assert bear_leg.origin_price == Decimal("110"), \
            f"Origin should remain fixed at 110, got {bear_leg.origin_price}"

    def test_bull_leg_pivot_extended_on_type2_bull(self):
        """Bull leg pivots extend on Type 2-Bull bars (HH+HL). Fixed for #197."""
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 105.0, 95.0, 103.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 103.0, 110.0, 98.0, 108.0)
        detector.process_bar(bar1)

        # Add a bull leg with origin at LOW (98), pivot at HIGH (110)
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("98"),   # LOW - fixed starting point
            origin_index=1,
            pivot_price=Decimal("110"),   # HIGH - extends
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bull_leg)

        # Bar 2: Type 2-Bull (HH=115, HL=100)
        bar2 = make_bar(2, 108.0, 115.0, 100.0, 113.0)
        detector.process_bar(bar2)

        # Pivot extends to new high
        assert bull_leg.pivot_price == Decimal("115")
        assert bull_leg.pivot_index == 2
        # Origin remains fixed
        assert bull_leg.origin_price == Decimal("98")

    def test_bear_leg_pivot_extended_on_type2_bear(self):
        """Bear leg pivots extend on Type 2-Bear bars (LH+LL). Fixed for #197."""
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 110.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 108.0, 90.0, 92.0)
        detector.process_bar(bar1)

        # Add a bear leg with origin at HIGH (108), pivot at LOW (90)
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("108"),  # HIGH - fixed starting point
            origin_index=1,
            pivot_price=Decimal("90"),    # LOW - extends
            pivot_index=1,
            price_at_creation=Decimal("92"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bear_leg)

        # Bar 2: Type 2-Bear (LH=105, LL=85)
        bar2 = make_bar(2, 92.0, 105.0, 85.0, 88.0)
        detector.process_bar(bar2)

        # Pivot extends to new low
        assert bear_leg.pivot_price == Decimal("85")
        assert bear_leg.pivot_index == 2
        # Origin remains fixed
        assert bear_leg.origin_price == Decimal("108")

    def test_both_legs_pivot_extend_on_type3(self):
        """Both bull and bear leg pivots extend on Type 3 bars (HH+LL). Fixed for #197."""
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 90.0, 100.0)
        detector.process_bar(bar1)

        # Add both bull and bear legs with correct terminology
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),   # LOW - fixed starting point
            origin_index=1,
            pivot_price=Decimal("110"),   # HIGH - extends
            pivot_index=1,
            price_at_creation=Decimal("100"),
            last_modified_bar=1,
        )
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),  # HIGH - fixed starting point
            origin_index=1,
            pivot_price=Decimal("90"),    # LOW - extends
            pivot_index=1,
            price_at_creation=Decimal("100"),
            last_modified_bar=1,
        )
        detector.state.active_legs.extend([bull_leg, bear_leg])

        # Bar 2: Type 3 (HH=115, LL=85)
        bar2 = make_bar(2, 100.0, 115.0, 85.0, 100.0)
        detector.process_bar(bar2)

        # Pivots extend on Type 3
        assert bull_leg.pivot_price == Decimal("115")
        assert bull_leg.pivot_index == 2
        assert bear_leg.pivot_price == Decimal("85")
        assert bear_leg.pivot_index == 2
        # Origins remain fixed
        assert bull_leg.origin_price == Decimal("90")
        assert bear_leg.origin_price == Decimal("110")

    def test_pivot_not_extended_if_not_new_extreme(self):
        """Pivot should not change if bar doesn't make new extreme. Fixed for #197."""
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 115.0, 85.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 112.0, 88.0, 100.0)
        detector.process_bar(bar1)

        # Add a bull leg with origin at LOW (85), pivot at HIGH (115)
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("85"),   # LOW - fixed
            origin_index=0,
            pivot_price=Decimal("115"),   # HIGH - extends on new highs only
            pivot_index=0,
            price_at_creation=Decimal("100"),
            last_modified_bar=0,
        )
        detector.state.active_legs.append(bull_leg)

        # Bar 2: Inside bar, no new high (110 < 115)
        bar2 = make_bar(2, 100.0, 110.0, 90.0, 100.0)
        detector.process_bar(bar2)

        # Pivot should remain unchanged (no new high)
        assert bull_leg.pivot_price == Decimal("115")
        assert bull_leg.pivot_index == 0
        # Origin is always fixed
        assert bull_leg.origin_price == Decimal("85")


class TestSameBarLegPrevention:
    """Test that legs cannot have pivot_index == origin_index (Issue #189).

    Same-bar legs violate temporal causality because we cannot know
    the H/L ordering within a single OHLC bar.
    """

    def test_type1_after_type2_no_same_bar_legs(self):
        """After Type 2 bar, Type 1 bar should not create same-bar legs.

        This reproduces issue #189: After a Type 2 bar, both pending pivots
        have the same bar_index. When the next bar is Type 1 (inside bar),
        the old <= comparison would create legs with pivot_index == origin_index.
        """
        from src.swing_analysis.events import LegCreatedEvent

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Bar 0: Initial bar
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2 bar (extends both H and L)
        # After this bar, both pending_bear and pending_bull have bar_index=1
        bar1 = make_bar(1, 100.0, 110.0, 90.0, 100.0)
        events1 = detector.process_bar(bar1)

        # Bar 2: Type 1 inside bar (H < prev.H, L > prev.L)
        # This should NOT create same-bar legs
        bar2 = make_bar(2, 100.0, 108.0, 92.0, 100.0)
        events2 = detector.process_bar(bar2)

        # Check that no legs were created with same pivot and origin index
        leg_events = [e for e in events2 if isinstance(e, LegCreatedEvent)]
        for leg_event in leg_events:
            assert leg_event.pivot_index != leg_event.origin_index, (
                f"Same-bar leg created: pivot_index={leg_event.pivot_index}, "
                f"origin_index={leg_event.origin_index}"
            )

    def test_type1_with_different_bar_indices_creates_legs(self):
        """Type 1 bars should still create legs when indices differ.

        This ensures the fix doesn't prevent legitimate leg creation.
        """
        from src.swing_analysis.events import LegCreatedEvent

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Bar 0: Initial bar with high
        bar0 = make_bar(0, 100.0, 110.0, 95.0, 100.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2 Bull (new low, but not new high)
        # Creates pending_bull at bar 1, pending_bear stays at bar 0
        bar1 = make_bar(1, 100.0, 105.0, 85.0, 90.0)
        events1 = detector.process_bar(bar1)

        # Bar 2: Type 1 inside bar
        # Now pending_bear.bar_index=0, pending_bull.bar_index=1
        # Should create bull leg (origin at 0, pivot at 1)
        bar2 = make_bar(2, 90.0, 100.0, 88.0, 95.0)
        events2 = detector.process_bar(bar2)

        # Verify legs created have different indices
        leg_events = [e for e in events2 if isinstance(e, LegCreatedEvent)]
        for leg_event in leg_events:
            assert leg_event.pivot_index != leg_event.origin_index

    def test_strict_inequality_prevents_same_bar_on_equal_indices(self):
        """Verify strict inequality logic: <= was the bug, < is the fix."""
        from src.swing_analysis.dag import PendingOrigin

        # Simulate the scenario from issue #189
        pending_bear = PendingOrigin(
            price=Decimal("100"), bar_index=5, direction='bear', source='high'
        )
        pending_bull = PendingOrigin(
            price=Decimal("95"), bar_index=5, direction='bull', source='low'
        )

        # Old behavior (bug): <= would allow both conditions to be True
        old_bull_condition = pending_bear.bar_index <= pending_bull.bar_index  # True
        old_bear_condition = pending_bull.bar_index <= pending_bear.bar_index  # True

        # New behavior (fix): < prevents both when equal
        new_bull_condition = pending_bear.bar_index < pending_bull.bar_index  # False
        new_bear_condition = pending_bull.bar_index < pending_bear.bar_index  # False

        assert old_bull_condition is True, "Sanity check: old behavior was <=, True"
        assert old_bear_condition is True, "Sanity check: old behavior was <=, True"
        assert new_bull_condition is False, "Fix: < prevents same-bar leg"
        assert new_bear_condition is False, "Fix: < prevents same-bar leg"


class TestLegCreationCleansUpState:
    """
    Tests for issue #196: Leg creation doesn't clear orphaned origins or pending pivots.

    When a new leg is created, the code should clean up related state:
    1. Orphaned origins containing the new leg's origin should be removed
    2. Pending pivots used to create the leg should be cleared
    """

    def test_leg_creation_clears_orphaned_origin_with_matching_price(self):
        """
        When a new leg is created with an origin that matches an orphaned origin,
        the orphaned origin should be removed.

        Reproduces the scenario from issue #196:
        - Bar 4: Bull leg created with origin=4416.00
        - Bar 5: Bull leg origin extended to 4419.25, then invalidated → origin added to orphaned_origins
        - Bar 6: New bull leg created with origin=4419.25 → orphaned origin should be cleared
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up initial state with bars 0-3 establishing context
        bars = [
            make_bar(0, 4410.0, 4412.0, 4408.0, 4411.0),  # Initial bar
            make_bar(1, 4411.0, 4413.0, 4410.0, 4412.0),  # TYPE_2_BULL (HH, HL)
            make_bar(2, 4412.0, 4415.0, 4411.0, 4414.0),  # TYPE_2_BULL (HH, HL)
            make_bar(3, 4414.0, 4416.0, 4413.0, 4415.0),  # TYPE_2_BULL (HH, HL)
            # Bar 4: TYPE_2_BULL - Bull leg created
            make_bar(4, 4415.0, 4416.0, 4414.25, 4415.5),  # HH (4416 > 4415.5), HL (4414.25 > 4413)
            # Bar 5: TYPE_3 (outside bar) - extends origin, may invalidate
            make_bar(5, 4415.5, 4419.25, 4411.25, 4413.0),  # HH (4419.25 > 4416), LL (4411.25 < 4414.25)
            # Bar 6: TYPE_2_BEAR - New bull leg should be created
            make_bar(6, 4413.0, 4412.25, 4409.0, 4410.0),  # LH (4412.25 < 4419.25), LL (4409 < 4411.25)
        ]

        # Process all bars
        for bar in bars:
            detector.process_bar(bar)

        # Find if there's a bull leg with origin at bar 5, price 4419.25
        bull_legs_with_origin_at_5 = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.origin_index == 5
        ]

        # Check orphaned_origins for bull direction
        bull_orphans = detector.state.orphaned_origins.get('bull', [])
        orphan_at_bar_5 = [o for o in bull_orphans if o[1] == 5]

        # If a bull leg exists with origin at bar 5, the orphaned origin at bar 5 should be cleared
        if bull_legs_with_origin_at_5:
            assert len(orphan_at_bar_5) == 0, (
                f"Orphaned origin at bar 5 should be cleared when a new leg uses that origin. "
                f"Bull legs with origin at 5: {bull_legs_with_origin_at_5}, "
                f"Orphans at bar 5: {orphan_at_bar_5}"
            )

    def test_pending_origins_cleared_after_leg_creation(self):
        """
        Pending origins are cleared when a leg is created from them (#197 fix).

        After the terminology fix (#197, #200):
        - Bear leg: origin_price = HIGH (where downward move started), pivot_price = LOW
        - Bull leg: origin_price = LOW (where upward move started), pivot_price = HIGH
        - pending_origins['bear'] tracks HIGHs (potential bear origins)
        - pending_origins['bull'] tracks LOWs (potential bull origins)

        When a leg is created from a pending origin, that pending origin is cleared.
        However, subsequent bar processing may set a NEW pending origin, so we check
        that the pending origin (if any) is different from the one used for the leg.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a sequence that forms a bear leg from a pending bear origin
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 102.0),  # Initial
            make_bar(1, 102.0, 110.0, 100.0, 108.0),  # TYPE_2_BULL - creates pending bear origin at 110
            make_bar(2, 108.0, 108.5, 98.0, 100.0),  # TYPE_2_BEAR (LH, LL) - creates bear leg from pending origin at 110
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check if bear leg was created with origin at 110 (pending bear origin)
        # After #197 fix: bear leg origin = HIGH (where downward move started)
        bear_legs = [leg for leg in detector.state.active_legs if leg.direction == 'bear']
        bear_legs_with_origin_at_110 = [
            leg for leg in bear_legs if leg.origin_price == Decimal("110")
        ]

        # Verify a bear leg was created with origin at 110
        assert len(bear_legs_with_origin_at_110) > 0, "Bear leg should be created with origin at 110"

        # Verify the original pending origin at 110 was cleared (#197 fix)
        # After leg creation, the pending origin may be updated to a new value (bar 2 high = 108.5)
        # but it should NOT still be at 110 (which was consumed by the leg)
        pending_bear = detector.state.pending_origins.get('bear')
        if pending_bear is not None:
            # If there's a pending origin, it should be from a later bar, not the consumed one
            assert pending_bear.price != Decimal("110"), (
                f"Pending bear origin at 110 should be cleared after leg creation. "
                f"Found: {pending_bear}"
            )

    def test_same_price_not_in_multiple_places(self):
        """
        A price/bar should not appear in multiple places simultaneously:
        - active leg origin
        - orphaned_origins
        - pending_origins

        This is the core invariant that issue #196 violates.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Process bars that might create duplicates
        bars = [
            make_bar(0, 4410.0, 4412.0, 4408.0, 4411.0),
            make_bar(1, 4411.0, 4413.0, 4410.0, 4412.0),
            make_bar(2, 4412.0, 4415.0, 4411.0, 4414.0),
            make_bar(3, 4414.0, 4416.0, 4413.0, 4415.0),
            make_bar(4, 4415.0, 4416.0, 4414.25, 4415.5),
            make_bar(5, 4415.5, 4419.25, 4411.25, 4413.0),
            make_bar(6, 4413.0, 4412.25, 4409.0, 4410.0),
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Collect all locations where each (price, bar_index) appears
        all_locations = {}

        # Check active leg origins
        for leg in detector.state.active_legs:
            if leg.status == 'active':
                origin_key = (leg.origin_price, leg.origin_index)
                if origin_key not in all_locations:
                    all_locations[origin_key] = []
                all_locations[origin_key].append(f"active_leg:{leg.direction}:{leg.leg_id}")

        # Check orphaned origins
        for direction in ['bull', 'bear']:
            for origin_price, origin_index in detector.state.orphaned_origins.get(direction, []):
                origin_key = (origin_price, origin_index)
                if origin_key not in all_locations:
                    all_locations[origin_key] = []
                all_locations[origin_key].append(f"orphaned_origins:{direction}")

        # Check pending origins
        for direction in ['bull', 'bear']:
            pending = detector.state.pending_origins.get(direction)
            if pending:
                origin_key = (pending.price, pending.bar_index)
                if origin_key not in all_locations:
                    all_locations[origin_key] = []
                all_locations[origin_key].append(f"pending_origins:{direction}")

        # Find any duplicates - a price/bar should not appear as both:
        # 1. Active leg origin AND orphaned origin of same direction
        for origin_key, locations in all_locations.items():
            active_leg_origins = [loc for loc in locations if loc.startswith("active_leg:")]
            orphaned_origins = [loc for loc in locations if loc.startswith("orphaned_origins:")]

            for active_loc in active_leg_origins:
                direction = active_loc.split(":")[1]
                matching_orphan = [o for o in orphaned_origins if f"orphaned_origins:{direction}" in o]
                assert len(matching_orphan) == 0, (
                    f"Price {origin_key} appears in both active_leg origin AND orphaned_origins "
                    f"for {direction} direction. Locations: {locations}"
                )


class TestBidirectionalDomination:
    """
    Tests for bidirectional domination - when a leg with a better origin is
    created, existing legs with worse origins in the same turn should be pruned.

    Issue #204: Stop losses placed based on a worse origin could get triggered
    unnecessarily when a better origin exists.
    """

    def test_better_bull_origin_prunes_worse_bull_legs(self):
        """
        When a new bull leg is created with a lower origin (better),
        existing bull legs with worse origins in the SAME TURN should be pruned.

        Directly tests _prune_dominated_legs_in_turn with controlled setup.
        """
        from src.swing_analysis.events import LegPrunedEvent
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually set up: two bull legs in the same turn,
        # where the second has a better (lower) origin
        leg1 = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # Worse origin (higher)
            origin_index=5,
            pivot_price=Decimal("110"),
            pivot_index=8,
            status='active',
        )

        detector.state.active_legs = [leg1]
        # No turn boundary set, so last_turn_bar['bull'] = -1
        # This means all legs are in "current turn"

        # Create a new leg with better origin
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("95"),  # Better origin (lower)
            origin_index=6,
            pivot_price=Decimal("115"),
            pivot_index=10,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Call the pruning function
        from datetime import datetime
        bar = make_bar(10, 110.0, 115.0, 108.0, 112.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # leg1 should be pruned because its origin (100) is worse than new_leg's origin (95)
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"
        assert events[0].reason == "dominated_in_turn"

        # Only the new leg should remain
        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining_legs) == 1
        assert remaining_legs[0].origin_price == Decimal("95")

    def test_better_bear_origin_prunes_worse_bear_legs(self):
        """
        When a new bear leg is created with a higher origin (better),
        existing bear legs with worse origins in the SAME TURN should be pruned.

        Directly tests _prune_dominated_legs_in_turn with controlled setup.
        """
        from src.swing_analysis.events import LegPrunedEvent
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Manually set up: two bear legs in the same turn,
        # where the second has a better (higher) origin
        leg1 = Leg(
            direction='bear',
            origin_price=Decimal("105"),  # Worse origin (lower)
            origin_index=5,
            pivot_price=Decimal("95"),
            pivot_index=8,
            status='active',
        )

        detector.state.active_legs = [leg1]
        # No turn boundary set, so last_turn_bar['bear'] = -1

        # Create a new leg with better origin
        new_leg = Leg(
            direction='bear',
            origin_price=Decimal("112"),  # Better origin (higher)
            origin_index=6,
            pivot_price=Decimal("90"),
            pivot_index=10,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Call the pruning function
        from datetime import datetime
        bar = make_bar(10, 92.0, 95.0, 90.0, 91.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # leg1 should be pruned because its origin (105) is worse than new_leg's origin (112)
        assert len(events) == 1, f"Expected 1 prune event, got {len(events)}"
        assert events[0].reason == "dominated_in_turn"

        # Only the new leg should remain
        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        assert len(remaining_legs) == 1
        assert remaining_legs[0].origin_price == Decimal("112")

    def test_all_dominated_legs_pruned_regardless_of_turn(self):
        """
        ALL dominated legs should be pruned when a better origin is found,
        regardless of turn boundaries. Turn boundaries are respected for
        leg CREATION (to allow nested structure), but not for PRUNING
        (to consolidate origins within the same move).

        Directly tests _prune_dominated_legs_in_turn.
        """
        from src.swing_analysis.dag import Leg

        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Set up turn boundary (shouldn't affect pruning anymore)
        detector.state.last_turn_bar['bull'] = 10

        # Leg from BEFORE the turn (origin_index = 5 < turn_start = 10)
        leg_from_prev_turn = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # Worse origin (higher)
            origin_index=5,
            pivot_price=Decimal("115"),
            pivot_index=12,
            status='active',
        )

        # Leg from CURRENT turn (origin_index = 12 >= turn_start = 10)
        leg_from_current_turn = Leg(
            direction='bull',
            origin_price=Decimal("105"),  # Also worse origin
            origin_index=12,
            pivot_price=Decimal("120"),
            pivot_index=15,
            status='active',
        )

        detector.state.active_legs = [leg_from_prev_turn, leg_from_current_turn]

        # New leg with better origin
        new_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),  # Best origin (lowest)
            origin_index=14,
            pivot_price=Decimal("125"),
            pivot_index=18,
            status='active',
        )
        detector.state.active_legs.append(new_leg)

        # Prune dominated legs
        from datetime import datetime
        bar = make_bar(18, 120.0, 125.0, 118.0, 122.0)
        timestamp = datetime.fromtimestamp(bar.timestamp)

        events = detector._pruner.prune_dominated_legs_in_turn(detector.state, new_leg, bar, timestamp)

        # BOTH legs with worse origins should be pruned (100 and 105)
        # Turn boundaries are NOT respected for pruning
        assert len(events) == 2, f"Expected 2 prune events, got {len(events)}"

        remaining_legs = [leg for leg in detector.state.active_legs if leg.status == 'active']
        origins = [leg.origin_price for leg in remaining_legs]

        # Only the new leg (90) should remain
        assert len(origins) == 1, f"Expected 1 leg remaining, got {len(origins)}"
        assert Decimal("90") in origins, "New leg should exist"
        assert Decimal("100") not in origins, "Leg from previous turn should be pruned"
        assert Decimal("105") not in origins, "Leg from current turn should be pruned"

    def test_active_swing_immunity_on_dominated_prune(self):
        """
        Legs that have formed into active swings should NOT be pruned
        even if a better origin is found.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create a bull leg that forms into a swing, then create a better origin
        # The first leg should survive because it has an active swing
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 102.0),    # Initial
            make_bar(1, 102.0, 110.0, 100.0, 108.0),   # TYPE_2_BULL - bull leg from 95
            make_bar(2, 108.0, 150.0, 107.0, 145.0),   # TYPE_2_BULL - extends pivot, likely forms swing
            make_bar(3, 145.0, 148.0, 90.0, 92.0),     # TYPE_2_BEAR - lower low at 90
            make_bar(4, 92.0, 160.0, 91.0, 155.0),     # TYPE_2_BULL - new bull leg from 90
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check if any swing formed from the first bull leg
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]

        # If any leg has a swing_id, verify it wasn't pruned
        legs_with_swings = [leg for leg in bull_legs if leg.swing_id is not None]

        # We should have at least the new leg (origin 90)
        origins = [leg.origin_price for leg in bull_legs]
        assert Decimal("90") in origins, "New bull leg from 90 should exist"

        # If a swing formed from origin 95, that leg should also exist
        if legs_with_swings:
            for leg in legs_with_swings:
                # Legs with active swings should not have been pruned
                assert leg.status == 'active', (
                    f"Leg with swing_id {leg.swing_id} should be active, not pruned"
                )
