"""
Tests for /api/bars endpoint timeframe aggregation (Issue #186).

Verifies that different scale parameters produce correctly aggregated bars
based on timeframe (not fixed bar count targets).
"""

import pytest
from datetime import datetime, timezone
from src.swing_analysis.types import Bar
from src.swing_analysis.bar_aggregator import BarAggregator


class TestScaleToTimeframeMapping:
    """Tests for scale-to-timeframe mapping in bar aggregation."""

    def _create_1m_bars(self, count: int, start_timestamp: int = 1609459200) -> list[Bar]:
        """Create count bars at 1-minute intervals starting from start_timestamp."""
        bars = []
        for i in range(count):
            bars.append(Bar(
                index=i,
                timestamp=start_timestamp + i * 60,
                open=100.0 + i * 0.1,
                high=101.0 + i * 0.1,
                low=99.0 + i * 0.1,
                close=100.5 + i * 0.1,
            ))
        return bars

    def _create_5m_bars(self, count: int, start_timestamp: int = 1609459200) -> list[Bar]:
        """Create count bars at 5-minute intervals."""
        bars = []
        for i in range(count):
            bars.append(Bar(
                index=i,
                timestamp=start_timestamp + i * 300,  # 5 minutes = 300 seconds
                open=100.0 + i * 0.1,
                high=101.0 + i * 0.1,
                low=99.0 + i * 0.1,
                close=100.5 + i * 0.1,
            ))
        return bars

    def test_1m_source_aggregates_to_different_timeframes(self):
        """With 1m source data, different scales produce different bar counts."""
        # Create 720 1-minute bars (12 hours of data)
        bars = self._create_1m_bars(720)
        aggregator = BarAggregator(bars, source_resolution_minutes=1)

        # Get bars at different timeframes
        bars_5m = aggregator.get_bars(5)    # S scale = 5 minutes
        bars_15m = aggregator.get_bars(15)  # M scale = 15 minutes
        bars_60m = aggregator.get_bars(60)  # L scale = 1 hour
        bars_240m = aggregator.get_bars(240)  # XL scale = 4 hours

        # Verify different timeframes produce different bar counts
        assert len(bars_5m) > len(bars_15m), "5m should have more bars than 15m"
        assert len(bars_15m) > len(bars_60m), "15m should have more bars than 1H"
        assert len(bars_60m) > len(bars_240m), "1H should have more bars than 4H"

        # Verify approximate ratios (allowing for boundary effects)
        # 720 bars @ 1m = 144 @ 5m ≈ 48 @ 15m ≈ 12 @ 1H ≈ 3 @ 4H
        assert 130 <= len(bars_5m) <= 150, f"Expected ~144 5m bars, got {len(bars_5m)}"
        assert 40 <= len(bars_15m) <= 55, f"Expected ~48 15m bars, got {len(bars_15m)}"
        assert 10 <= len(bars_60m) <= 14, f"Expected ~12 1H bars, got {len(bars_60m)}"
        assert 2 <= len(bars_240m) <= 4, f"Expected ~3 4H bars, got {len(bars_240m)}"

    def test_5m_source_aggregates_correctly(self):
        """With 5m source data, aggregation respects source resolution."""
        # Create 144 5-minute bars (12 hours of data)
        bars = self._create_5m_bars(144)
        aggregator = BarAggregator(bars, source_resolution_minutes=5)

        # 5m source at 5m timeframe = source bars (no aggregation)
        bars_5m = aggregator.get_bars(5)
        assert len(bars_5m) == 144, "5m source at 5m should return all source bars"

        # 5m source at 15m timeframe
        bars_15m = aggregator.get_bars(15)
        assert 40 <= len(bars_15m) <= 55, f"Expected ~48 15m bars, got {len(bars_15m)}"

        # 5m source at 1H timeframe
        bars_60m = aggregator.get_bars(60)
        assert 10 <= len(bars_60m) <= 14, f"Expected ~12 1H bars, got {len(bars_60m)}"

    def test_aggregated_bars_have_correct_ohlc(self):
        """Aggregated bars correctly combine OHLC values."""
        # Create 60 1-minute bars (1 hour)
        bars = self._create_1m_bars(60)
        aggregator = BarAggregator(bars, source_resolution_minutes=1)

        # Aggregate to 1H - should be 1 bar
        bars_1h = aggregator.get_bars(60)
        assert len(bars_1h) == 1, f"Expected 1 1H bar, got {len(bars_1h)}"

        # The 1H bar should have:
        # - Open from first bar
        # - High from max of all bars
        # - Low from min of all bars
        # - Close from last bar
        bar_1h = bars_1h[0]
        assert bar_1h.open == bars[0].open, "1H open should match first bar open"
        assert bar_1h.close == bars[-1].close, "1H close should match last bar close"
        assert bar_1h.high == max(b.high for b in bars), "1H high should be max of all highs"
        assert bar_1h.low == min(b.low for b in bars), "1H low should be min of all lows"

    def test_source_mapping_preserved(self):
        """Source-to-aggregated mapping is preserved for chart sync."""
        # Create 60 1-minute bars
        bars = self._create_1m_bars(60)
        aggregator = BarAggregator(bars, source_resolution_minutes=1)

        # Get 15m bars (should be 4 bars)
        bars_15m = aggregator.get_bars(15)

        # Check mapping via get_bar_at_source_time
        # Source bar 0 should map to agg bar 0
        # Source bar 14 should map to agg bar 0 (same 15m period)
        # Source bar 15 should map to agg bar 1 (next 15m period)
        bar_for_source_0 = aggregator.get_bar_at_source_time(15, 0)
        bar_for_source_14 = aggregator.get_bar_at_source_time(15, 14)
        bar_for_source_15 = aggregator.get_bar_at_source_time(15, 15)

        assert bar_for_source_0 is not None
        assert bar_for_source_14 is not None
        assert bar_for_source_15 is not None

        # Source bars 0-14 should be in the same aggregated bar
        assert bar_for_source_0.index == bar_for_source_14.index
        # Source bar 15 should be in the next aggregated bar
        assert bar_for_source_15.index == bar_for_source_0.index + 1


class TestChartTimeframeDifferentiation:
    """Tests verifying Chart 1 and Chart 2 can show different timeframes."""

    def _create_test_bars(self, count: int = 480) -> list[Bar]:
        """Create test bars (8 hours @ 1m = 480 bars)."""
        # Start at midnight UTC
        start = int(datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        bars = []
        for i in range(count):
            bars.append(Bar(
                index=i,
                timestamp=start + i * 60,
                open=100.0 + i * 0.01,
                high=100.5 + i * 0.01,
                low=99.5 + i * 0.01,
                close=100.2 + i * 0.01,
            ))
        return bars

    def test_chart1_and_chart2_different_bar_counts(self):
        """Chart 1 at 1H and Chart 2 at 5m produce different bar counts."""
        bars = self._create_test_bars(480)  # 8 hours @ 1m
        aggregator = BarAggregator(bars, source_resolution_minutes=1)

        # Chart 1: L scale (1H) → ~8 bars
        chart1_bars = aggregator.get_bars(60)

        # Chart 2: S scale (5m) → ~96 bars
        chart2_bars = aggregator.get_bars(5)

        # They should have very different counts
        assert len(chart2_bars) > len(chart1_bars) * 5, \
            f"5m ({len(chart2_bars)}) should have 10x+ more bars than 1H ({len(chart1_bars)})"

    def test_each_timeframe_independent(self):
        """Each timeframe aggregation is independent."""
        bars = self._create_test_bars(240)  # 4 hours @ 1m
        aggregator = BarAggregator(bars, source_resolution_minutes=1)

        # Get all timeframes
        tf_5m = aggregator.get_bars(5)
        tf_15m = aggregator.get_bars(15)
        tf_60m = aggregator.get_bars(60)
        tf_240m = aggregator.get_bars(240)

        # Each should be unique
        counts = [len(tf_5m), len(tf_15m), len(tf_60m), len(tf_240m)]
        assert len(set(counts)) == 4, f"All timeframes should have unique counts: {counts}"

        # Ordering should be 5m > 15m > 60m > 240m
        assert len(tf_5m) > len(tf_15m) > len(tf_60m) > len(tf_240m)
