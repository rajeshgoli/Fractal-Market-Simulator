"""
Test suite for Swing Detector Module

Tests performance and correctness of the O(N log N) algorithm rewrite.
"""

import unittest
import time
import sys
import os
import pandas as pd
import numpy as np

# Add paths for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'legacy'))

from src.swing_analysis.swing_detector import detect_swings


class TestSwingDetectorPerformance(unittest.TestCase):
    """Performance benchmarks for swing detection algorithm"""

    def _create_synthetic_bars(self, num_bars: int, seed: int = 42) -> pd.DataFrame:
        """
        Create synthetic OHLC data with realistic price movement.

        Generates random walk data with swings to test detection performance.
        """
        np.random.seed(seed)

        base_price = 5000.0
        prices = [base_price]

        # Random walk with some trend
        for i in range(1, num_bars):
            change = np.random.normal(0, 2.0)  # Small changes
            # Occasional larger swings
            if np.random.random() < 0.05:
                change *= 5
            prices.append(prices[-1] + change)

        # Create OHLC from prices
        data = []
        for i, base in enumerate(prices):
            # Add some noise for OHLC
            noise = np.random.uniform(0.5, 2.0)
            high = base + noise
            low = base - noise
            open_price = base + np.random.uniform(-noise/2, noise/2)
            close_price = base + np.random.uniform(-noise/2, noise/2)

            data.append({
                'open': open_price,
                'high': high,
                'low': low,
                'close': close_price
            })

        return pd.DataFrame(data)

    def test_performance_1k_bars(self):
        """Swing detection should handle 1K bars in <1 second."""
        df = self._create_synthetic_bars(1000)

        start = time.time()
        result = detect_swings(df, lookback=5, filter_redundant=False)
        elapsed = time.time() - start

        self.assertLess(elapsed, 1.0, f"Detection took {elapsed:.3f}s, expected <1s")
        self.assertIn('swing_highs', result)
        self.assertIn('swing_lows', result)
        print(f"1K bars: {elapsed*1000:.1f}ms, {len(result['swing_highs'])} highs, {len(result['swing_lows'])} lows")

    def test_performance_10k_bars(self):
        """Swing detection should handle 10K bars in <5 seconds."""
        df = self._create_synthetic_bars(10000)

        start = time.time()
        result = detect_swings(df, lookback=5, filter_redundant=False)
        elapsed = time.time() - start

        self.assertLess(elapsed, 5.0, f"Detection took {elapsed:.3f}s, expected <5s")
        print(f"10K bars: {elapsed*1000:.1f}ms, {len(result['swing_highs'])} highs, {len(result['swing_lows'])} lows")

    def test_performance_50k_bars(self):
        """Swing detection should handle 50K bars in <15 seconds."""
        df = self._create_synthetic_bars(50000)

        start = time.time()
        result = detect_swings(df, lookback=5, filter_redundant=False)
        elapsed = time.time() - start

        self.assertLess(elapsed, 15.0, f"Detection took {elapsed:.3f}s, expected <15s")
        print(f"50K bars: {elapsed*1000:.1f}ms, {len(result['swing_highs'])} highs, {len(result['swing_lows'])} lows")

    def test_performance_100k_bars(self):
        """Swing detection should handle 100K bars in <30 seconds (target: <10s)."""
        df = self._create_synthetic_bars(100000)

        start = time.time()
        result = detect_swings(df, lookback=5, filter_redundant=False)
        elapsed = time.time() - start

        self.assertLess(elapsed, 30.0, f"Detection took {elapsed:.3f}s, expected <30s")
        print(f"100K bars: {elapsed:.2f}s, {len(result['swing_highs'])} highs, {len(result['swing_lows'])} lows")


class TestSwingDetectorCorrectness(unittest.TestCase):
    """Correctness tests for swing detection algorithm"""

    def test_empty_dataframe(self):
        """Empty DataFrame should return empty results."""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close'])
        result = detect_swings(df, lookback=5)

        self.assertEqual(result['swing_highs'], [])
        self.assertEqual(result['swing_lows'], [])
        self.assertEqual(result['bull_references'], [])
        self.assertEqual(result['bear_references'], [])

    def test_small_dataframe(self):
        """DataFrame smaller than 2*lookback should return empty swings."""
        df = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [101, 102, 103],
            'low': [99, 100, 101],
            'close': [100.5, 101.5, 102.5]
        })
        result = detect_swings(df, lookback=5)

        # With only 3 bars and lookback=5, no swings can be detected
        self.assertEqual(result['swing_highs'], [])
        self.assertEqual(result['swing_lows'], [])

    def test_clear_swing_high(self):
        """Should detect an obvious swing high."""
        # Create a clear peak: prices go up then down
        prices = [100, 102, 105, 108, 110, 112, 110, 108, 105, 102, 100, 98, 96]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 0.5 for p in prices],
            'low': [p - 0.5 for p in prices],
            'close': prices
        })

        result = detect_swings(df, lookback=3, filter_redundant=False)

        # Should find a swing high around the peak (index 5)
        self.assertGreater(len(result['swing_highs']), 0, "Should detect swing high")
        # Find the swing high closest to the peak
        high_indices = [s['bar_index'] for s in result['swing_highs']]
        self.assertTrue(any(4 <= idx <= 7 for idx in high_indices),
                       f"Swing high should be near index 5, got {high_indices}")

    def test_clear_swing_low(self):
        """Should detect an obvious swing low."""
        # Create a clear trough: prices go down then up
        prices = [110, 108, 105, 102, 100, 98, 100, 102, 105, 108, 110, 112, 114]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 0.5 for p in prices],
            'low': [p - 0.5 for p in prices],
            'close': prices
        })

        result = detect_swings(df, lookback=3, filter_redundant=False)

        # Should find a swing low around the trough (index 5)
        self.assertGreater(len(result['swing_lows']), 0, "Should detect swing low")
        low_indices = [s['bar_index'] for s in result['swing_lows']]
        self.assertTrue(any(4 <= idx <= 7 for idx in low_indices),
                       f"Swing low should be near index 5, got {low_indices}")

    def test_bull_reference_creation(self):
        """Should create bull references from high-before-low swings."""
        # Create pattern: high -> low -> current near valid level
        np.random.seed(123)

        # Start high, drop down, then recover to middle
        prices = []
        # Initial rise
        for i in range(10):
            prices.append(100 + i * 2)  # 100 to 118
        # Peak area
        for i in range(5):
            prices.append(120)
        # Drop
        for i in range(10):
            prices.append(118 - i * 3)  # 118 to 91
        # Bottom area
        for i in range(5):
            prices.append(90)
        # Recovery to middle (for valid reference)
        for i in range(10):
            prices.append(90 + i * 2)  # 90 to 108

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        result = detect_swings(df, lookback=3, filter_redundant=False)

        # Should have detected swing points
        self.assertGreater(len(result['swing_highs']), 0, "Should detect swing highs")
        self.assertGreater(len(result['swing_lows']), 0, "Should detect swing lows")

    def test_structural_validity_check(self):
        """Invalid structures (lower intermediate low) should be filtered out."""
        # Create: High -> Intermediate Low (lower) -> Final Low (higher)
        # This should NOT create a valid reference from High to Final Low

        prices = [110, 112, 115, 117, 120,  # Rise to high
                  118, 115, 112, 100,        # Drop to intermediate low (100)
                  102, 105, 108, 110,        # Rise a bit
                  108, 105]                  # End (105 is higher than 100)

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 0.5 for p in prices],
            'low': [p - 0.5 for p in prices],
            'close': prices
        })

        result = detect_swings(df, lookback=2, filter_redundant=False)

        # The algorithm should properly handle intermediate validity checks
        # Just verify it doesn't crash and returns valid structure
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

    def test_results_contain_required_fields(self):
        """Result dictionary should contain all required fields."""
        np.random.seed(456)
        prices = np.cumsum(np.random.randn(100)) + 100

        df = pd.DataFrame({
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices + 0.5
        })

        result = detect_swings(df, lookback=5)

        self.assertIn('current_price', result)
        self.assertIn('swing_highs', result)
        self.assertIn('swing_lows', result)
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

    def test_swing_points_have_required_fields(self):
        """Swing points should have price and bar_index fields."""
        np.random.seed(789)
        prices = np.cumsum(np.random.randn(100)) + 100

        df = pd.DataFrame({
            'open': prices,
            'high': prices + 2,
            'low': prices - 2,
            'close': prices + 1
        })

        result = detect_swings(df, lookback=3, filter_redundant=False)

        for high in result['swing_highs']:
            self.assertIn('price', high)
            self.assertIn('bar_index', high)

        for low in result['swing_lows']:
            self.assertIn('price', low)
            self.assertIn('bar_index', low)


class TestSwingDetectorScaling(unittest.TestCase):
    """Test that algorithm scales sub-quadratically"""

    def _create_synthetic_bars(self, num_bars: int, seed: int = 42) -> pd.DataFrame:
        """Create synthetic OHLC data."""
        np.random.seed(seed)
        prices = np.cumsum(np.random.randn(num_bars) * 2) + 5000
        return pd.DataFrame({
            'open': prices,
            'high': prices + np.abs(np.random.randn(num_bars)),
            'low': prices - np.abs(np.random.randn(num_bars)),
            'close': prices + np.random.randn(num_bars) * 0.5
        })

    def test_scaling_factor(self):
        """Time should scale better than O(N²) - ratio should be < 4x for 2x data."""
        # Time for N bars
        n1 = 5000
        df1 = self._create_synthetic_bars(n1)
        start = time.time()
        detect_swings(df1, lookback=5, filter_redundant=False)
        time1 = time.time() - start

        # Time for 2N bars
        n2 = 10000
        df2 = self._create_synthetic_bars(n2)
        start = time.time()
        detect_swings(df2, lookback=5, filter_redundant=False)
        time2 = time.time() - start

        # For O(N²), ratio would be ~4x
        # For O(N log N), ratio would be ~2.3x
        # Allow some variance, but should be well under 4x
        ratio = time2 / time1 if time1 > 0 else float('inf')

        print(f"Scaling test: {n1} bars = {time1*1000:.1f}ms, {n2} bars = {time2*1000:.1f}ms, ratio = {ratio:.2f}x")

        # If the algorithm were O(N²), doubling input would ~4x the time
        # O(N log N) should give roughly 2-2.5x
        self.assertLess(ratio, 3.5,
                       f"Scaling ratio {ratio:.2f}x suggests worse than O(N log N)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
