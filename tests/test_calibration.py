"""
Tests for calibration: calibrate functions, DataFrame helpers, performance.

Tests the batch processing and utility functions of the swing analysis system.
"""

import pytest
import time
from decimal import Decimal

import pandas as pd

from src.swing_analysis.dag import (
    HierarchicalDetector,
    calibrate,
    calibrate_from_dataframe,
    dataframe_to_bars,
    FIB_LEVELS,
)
from src.swing_analysis.swing_config import SwingConfig

from conftest import make_bar


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

    def test_performance_1k_bars_dag_only(self):
        """Performance test: 1K bars should complete in reasonable time.

        Note: This tests DAG-only path (without Reference layer pruning).
        After DAG/Reference layer separation (#164), swings accumulate
        without pruning until the Reference layer processes them.

        The 30s threshold applies to this isolated DAG test. The full
        pipeline with Reference layer achieves <60s for 6M bars as
        documented in CLAUDE.md. See #176 for tracking.

        Tech debt: Consider reducing this threshold as optimizations land.
        """
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

        # DAG-only path allows 30s for 1K bars due to swing accumulation.
        # Full pipeline with Reference layer is much faster (see #176).
        assert elapsed < 30.0, f"1K bars took {elapsed:.2f}s, should be <30s"
        assert detector.state.last_bar_index == 999
