"""
Comprehensive test suite for BarAggregator module.

Covers all 8 test categories:
1. Basic Aggregation Correctness
2. Alignment to Natural Boundaries
3. Incomplete Bar Detection
4. Index Mapping Accuracy
5. All Standard Timeframes
6. Real Data Integration
7. Performance Benchmark
8. Edge Cases

Author: Generated for Market Simulator Project
"""

import pytest
import time
from datetime import datetime, timezone
from typing import List
import random

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.bar_aggregator import BarAggregator, AggregatedBars
from src.data.ohlc_loader import load_ohlc
from bull_reference_detector import Bar


class TestBarAggregator:
    """Test suite for BarAggregator functionality."""
    
    def create_test_bars(self, count: int, start_timestamp: int = 1640995200) -> List[Bar]:
        """Create test bars with predictable OHLC values for testing."""
        bars = []
        timestamp = start_timestamp  # Jan 1, 2022 00:00:00 UTC
        
        for i in range(count):
            # Create predictable OHLC values for easy verification
            base_price = 100 + i * 0.1
            bars.append(Bar(
                index=i,
                timestamp=timestamp + i * 60,  # 1-minute intervals
                open=base_price,
                high=base_price + 0.5,
                low=base_price - 0.3,
                close=base_price + 0.2
            ))
        
        return bars
    
    def test_5min_aggregation_ohlc(self):
        """Verify OHLC rules are correctly applied for 5-minute bars."""
        # Create 5 one-minute bars with known values
        bars = [
            Bar(0, 1640995200, 100.0, 101.0, 99.0, 100.5),    # 00:00
            Bar(1, 1640995260, 100.5, 102.0, 100.0, 101.0),   # 00:01
            Bar(2, 1640995320, 101.0, 103.0, 100.5, 102.0),   # 00:02
            Bar(3, 1640995380, 102.0, 102.5, 101.0, 101.5),   # 00:03
            Bar(4, 1640995440, 101.5, 104.0, 101.0, 103.0),   # 00:04
        ]
        
        aggregator = BarAggregator(bars)
        agg_bars = aggregator.get_bars(5)
        
        # Should have exactly 1 aggregated 5-minute bar
        assert len(agg_bars) == 1
        
        agg_bar = agg_bars[0]
        
        # Verify OHLC aggregation rules
        assert agg_bar.open == 100.0    # Open of first bar
        assert agg_bar.high == 104.0    # Maximum high (from bar 4)
        assert agg_bar.low == 99.0      # Minimum low (from bar 0)
        assert agg_bar.close == 103.0   # Close of last bar
        assert agg_bar.timestamp == bars[0].timestamp  # Timestamp of first bar
    
    def test_alignment_to_natural_boundaries(self):
        """Verify aggregated bars start at correct times."""
        # Source data starting at 09:03 (not aligned to 5-min boundary)
        start_time = datetime(2022, 1, 1, 9, 3, 0, tzinfo=timezone.utc)
        start_timestamp = int(start_time.timestamp())
        
        bars = []
        for i in range(7):  # 7 minutes of data: 09:03 to 09:09
            bars.append(Bar(
                index=i,
                timestamp=start_timestamp + i * 60,
                open=100 + i,
                high=100 + i + 0.5,
                low=100 + i - 0.3,
                close=100 + i + 0.2
            ))
        
        aggregator = BarAggregator(bars)
        agg_bars = aggregator.get_bars(5)
        
        # Should have 2 bars: partial period (09:03-09:04) and aligned period (09:05-09:09)
        assert len(agg_bars) == 2
        
        # First bar starts at 09:03 (partial period)
        first_dt = datetime.fromtimestamp(agg_bars[0].timestamp, timezone.utc)
        assert first_dt.hour == 9 and first_dt.minute == 3
        
        # Second bar starts at 09:05 (aligned to 5-min boundary)
        second_dt = datetime.fromtimestamp(agg_bars[1].timestamp, timezone.utc)
        assert second_dt.hour == 9 and second_dt.minute == 5
    
    def test_incomplete_bar_handling(self):
        """Verify incomplete bars are correctly identified."""
        # Create 7 minutes of data
        bars = self.create_test_bars(7)
        aggregator = BarAggregator(bars)
        
        # 5-minute aggregation should show 1 complete bar + partial data
        agg_bars = aggregator.get_bars(5)
        assert len(agg_bars) == 2  # Two 5-minute periods, second is partial
        
        # Test get_closed_bar_at_source_time
        # For source bar 6 (last bar), should return the first complete 5-min bar
        closed_bar = aggregator.get_closed_bar_at_source_time(5, 6)
        assert closed_bar is not None
        assert closed_bar.index == 0  # Should be first aggregated bar
        
        # For source bar 4 (end of first complete period), should return that bar
        closed_bar = aggregator.get_closed_bar_at_source_time(5, 4)
        assert closed_bar is not None
        assert closed_bar.index == 0
    
    def test_source_to_aggregated_mapping(self):
        """Verify bidirectional index mapping works correctly."""
        bars = self.create_test_bars(10)
        aggregator = BarAggregator(bars)
        
        # Test 5-minute mapping
        # Source bars 0-4 should map to aggregated bar 0
        for source_idx in range(5):
            agg_bar = aggregator.get_bar_at_source_time(5, source_idx)
            assert agg_bar is not None
            assert agg_bar.index == 0
        
        # Source bars 5-9 should map to aggregated bar 1
        for source_idx in range(5, 10):
            agg_bar = aggregator.get_bar_at_source_time(5, source_idx)
            assert agg_bar is not None
            assert agg_bar.index == 1
    
    def test_all_standard_timeframes(self):
        """Verify all 6 standard timeframes are computed correctly."""
        # Create enough data for all timeframes (4 hours = 240 minutes)
        bars = self.create_test_bars(240)
        aggregator = BarAggregator(bars)
        
        expected_counts = {
            1: 240,    # 240 / 1 = 240
            5: 48,     # 240 / 5 = 48
            15: 16,    # 240 / 15 = 16
            30: 8,     # 240 / 30 = 8
            60: 4,     # 240 / 60 = 4
            240: 1,    # 240 / 240 = 1
        }
        
        for timeframe in BarAggregator.STANDARD_TIMEFRAMES:
            bar_count = aggregator.aggregated_bar_count(timeframe)
            assert bar_count == expected_counts[timeframe], \
                f"Timeframe {timeframe}: expected {expected_counts[timeframe]}, got {bar_count}"
    
    def test_with_real_market_data(self):
        """Integration test with test.csv if available."""
        test_csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'test.csv')
        
        if not os.path.exists(test_csv_path):
            pytest.skip("test.csv not available")
        
        try:
            # Load real data
            df, gaps = load_ohlc(test_csv_path)
            
            # Convert DataFrame to Bar objects
            bars = []
            for i, (timestamp, row) in enumerate(df.iterrows()):
                bars.append(Bar(
                    index=i,
                    timestamp=int(timestamp.timestamp()),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close'])
                ))
            
            if len(bars) < 10:
                pytest.skip("Not enough bars in test.csv")
            
            # Test aggregation
            aggregator = BarAggregator(bars)
            
            # Verify all timeframes work
            for timeframe in BarAggregator.STANDARD_TIMEFRAMES:
                agg_count = aggregator.aggregated_bar_count(timeframe)
                assert agg_count > 0, f"No bars generated for {timeframe}-minute timeframe"
                
                # Verify compression ratio is reasonable
                compression_ratio = len(bars) / agg_count
                assert compression_ratio >= 1.0, f"Compression ratio should be >= 1.0 for {timeframe}-minute"
            
            # Test retrieval methods work
            mid_idx = len(bars) // 2
            for timeframe in BarAggregator.STANDARD_TIMEFRAMES:
                bar = aggregator.get_bar_at_source_time(timeframe, mid_idx)
                assert bar is not None, f"Failed to get {timeframe}-minute bar at source index {mid_idx}"
        
        except Exception as e:
            pytest.fail(f"Real data test failed: {e}")
    
    def test_retrieval_performance(self):
        """Verify retrieval methods meet latency requirements."""
        # Create large dataset (10,000 bars for reasonable test time)
        bars = self.create_test_bars(10000)
        aggregator = BarAggregator(bars)
        
        # Time 1000 random retrievals
        random_indices = [random.randint(0, len(bars) - 1) for _ in range(1000)]
        
        start_time = time.time()
        
        for idx in random_indices:
            # Test both retrieval methods
            for timeframe in [5, 15, 60]:  # Test subset for speed
                bar1 = aggregator.get_bar_at_source_time(timeframe, idx)
                bar2 = aggregator.get_closed_bar_at_source_time(timeframe, idx)
        
        elapsed_time = time.time() - start_time
        avg_time_per_retrieval = (elapsed_time / (1000 * 3 * 2)) * 1000  # Convert to ms
        
        # Assert average < 1ms per retrieval (generous allowance for test environment)
        assert avg_time_per_retrieval < 1.0, \
            f"Average retrieval time {avg_time_per_retrieval:.3f}ms exceeds 1ms limit"
    
    def test_edge_cases(self):
        """Handle edge cases gracefully."""
        
        # Test empty source bars
        with pytest.raises(ValueError, match="Source bars cannot be empty"):
            BarAggregator([])
        
        # Test single bar
        single_bar = [Bar(0, 1640995200, 100.0, 100.5, 99.5, 100.2)]
        aggregator = BarAggregator(single_bar)
        
        # Should work for all timeframes
        for timeframe in BarAggregator.STANDARD_TIMEFRAMES:
            bars = aggregator.get_bars(timeframe)
            assert len(bars) == 1
            assert bars[0].open == 100.0
            assert bars[0].close == 100.2
        
        # Test out-of-bounds indices
        bars = self.create_test_bars(10)
        aggregator = BarAggregator(bars)
        
        # Out of bounds source index
        assert aggregator.get_bar_at_source_time(5, -1) is None
        assert aggregator.get_bar_at_source_time(5, 100) is None
        assert aggregator.get_closed_bar_at_source_time(5, -1) is None
        assert aggregator.get_closed_bar_at_source_time(5, 100) is None
        
        # Invalid timeframe
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            aggregator.get_bars(7)  # 7 minutes not in STANDARD_TIMEFRAMES
        
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            aggregator.get_bar_at_source_time(7, 0)
        
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            aggregator.get_closed_bar_at_source_time(7, 0)
        
        # Test non-chronological source bars
        bad_bars = [
            Bar(0, 1640995200, 100.0, 100.5, 99.5, 100.2),
            Bar(1, 1640995100, 100.2, 100.7, 99.8, 100.4),  # Earlier timestamp
        ]
        
        with pytest.raises(ValueError, match="chronological order"):
            BarAggregator(bad_bars)
    
    def test_ohlc_validation(self):
        """Test that aggregated bars maintain valid OHLC relationships."""
        bars = self.create_test_bars(20)
        aggregator = BarAggregator(bars)
        
        for timeframe in BarAggregator.STANDARD_TIMEFRAMES:
            agg_bars = aggregator.get_bars(timeframe)
            
            for bar in agg_bars:
                # Verify OHLC constraints
                assert bar.low <= bar.open <= bar.high, f"Open {bar.open} not between low {bar.low} and high {bar.high}"
                assert bar.low <= bar.close <= bar.high, f"Close {bar.close} not between low {bar.low} and high {bar.high}"
                assert bar.low <= bar.high, f"Low {bar.low} should be <= high {bar.high}"
    
    def test_natural_boundary_alignment_detailed(self):
        """Detailed test of natural boundary alignment for all timeframes."""
        # Test alignment behavior: first bar reflects actual start, subsequent bars align to boundaries
        
        # Test 5-minute alignment starting at 9:03
        start_time = datetime(2022, 1, 1, 9, 3, 0, tzinfo=timezone.utc)
        bars = []
        for i in range(10):  # 10 minutes of data: 09:03 to 09:12
            bars.append(Bar(
                index=i,
                timestamp=int(start_time.timestamp()) + i * 60,
                open=100 + i * 0.1,
                high=100 + i * 0.1 + 0.5,
                low=100 + i * 0.1 - 0.3,
                close=100 + i * 0.1 + 0.2
            ))
        
        aggregator = BarAggregator(bars)
        agg_bars = aggregator.get_bars(5)
        
        # Should have 3 bars: 09:03-09:04, 09:05-09:09, 09:10-09:12
        assert len(agg_bars) == 3
        
        # First bar: 09:03 (unaligned start)
        first_dt = datetime.fromtimestamp(agg_bars[0].timestamp, timezone.utc)
        assert first_dt.minute == 3
        
        # Second bar: 09:05 (aligned to 5-minute boundary)
        second_dt = datetime.fromtimestamp(agg_bars[1].timestamp, timezone.utc)
        assert second_dt.minute == 5
        
        # Third bar: 09:10 (aligned to 5-minute boundary)
        third_dt = datetime.fromtimestamp(agg_bars[2].timestamp, timezone.utc)
        assert third_dt.minute == 10
        
        # Test 15-minute alignment starting at 9:07
        start_time = datetime(2022, 1, 1, 9, 7, 0, tzinfo=timezone.utc)
        bars = []
        for i in range(20):  # 20 minutes of data
            bars.append(Bar(
                index=i,
                timestamp=int(start_time.timestamp()) + i * 60,
                open=100 + i * 0.1,
                high=100 + i * 0.1 + 0.5,
                low=100 + i * 0.1 - 0.3,
                close=100 + i * 0.1 + 0.2
            ))
        
        aggregator = BarAggregator(bars)
        agg_bars = aggregator.get_bars(15)
        
        # Should have 2 bars: 09:07-09:14 (partial), 09:15-09:26 (aligned)
        assert len(agg_bars) == 2
        first_dt = datetime.fromtimestamp(agg_bars[0].timestamp, timezone.utc)
        assert first_dt.minute == 7  # Unaligned start
        second_dt = datetime.fromtimestamp(agg_bars[1].timestamp, timezone.utc)
        assert second_dt.minute == 15  # Aligned to 15-minute boundary


# Additional integration tests
class TestBarAggregatorIntegration:
    """Integration tests with other system components."""
    
    def test_integration_with_scale_calibrator(self):
        """Test integration with ScaleCalibrator aggregation settings."""
        # Create test bars
        bars = []
        start_timestamp = 1640995200
        for i in range(100):
            bars.append(Bar(
                index=i,
                timestamp=start_timestamp + i * 60,
                open=100 + i * 0.1,
                high=100 + i * 0.1 + 0.5,
                low=100 + i * 0.1 - 0.3,
                close=100 + i * 0.1 + 0.2
            ))
        
        # Test that BarAggregator works with ScaleCalibrator's standard timeframes
        from src.analysis.scale_calibrator import ScaleCalibrator
        
        calibrator = ScaleCalibrator()
        config = calibrator.calibrate(bars)
        aggregator = BarAggregator(bars)
        
        # Verify we can get bars for each scale's aggregation setting
        for scale, timeframe in config.aggregations.items():
            if timeframe in BarAggregator.STANDARD_TIMEFRAMES:
                scale_bars = aggregator.get_bars(timeframe)
                assert len(scale_bars) > 0, f"No bars for scale {scale} timeframe {timeframe}"
    
    def test_debug_aggregation_info(self):
        """Test the debug aggregation info method."""
        bars = []
        start_timestamp = 1640995200
        for i in range(60):  # 1 hour of data
            bars.append(Bar(
                index=i,
                timestamp=start_timestamp + i * 60,
                open=100 + i * 0.1,
                high=100 + i * 0.1 + 0.5,
                low=100 + i * 0.1 - 0.3,
                close=100 + i * 0.1 + 0.2
            ))
        
        aggregator = BarAggregator(bars)
        info = aggregator.get_aggregation_info()
        
        # Verify info structure
        assert 'source_bar_count' in info
        assert info['source_bar_count'] == 60
        assert 'timeframes' in info
        
        # Check each timeframe
        for timeframe in BarAggregator.STANDARD_TIMEFRAMES:
            assert timeframe in info['timeframes']
            tf_info = info['timeframes'][timeframe]
            
            assert 'bar_count' in tf_info
            assert 'compression_ratio' in tf_info
            assert 'first_timestamp' in tf_info
            assert 'last_timestamp' in tf_info
            
            # Verify compression ratios are sensible
            assert tf_info['compression_ratio'] >= 1.0
            assert tf_info['compression_ratio'] <= 60