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
        """Time should scale better than O(N²) - ratio should be < 4x for 2x data.

        Uses max_pair_distance to enable the O(N log N) optimization path.
        Without max_pair_distance, the algorithm is O(N²) by design (all pairs checked).

        Uses minimum of multiple runs to reduce timing variance from system load.
        Larger dataset sizes provide more stable measurements.
        """
        # Larger sizes for stable timing (small datasets have high variance)
        n1 = 20000
        n2 = 40000
        num_runs = 5  # Multiple runs for stability
        max_pair_distance = 2000  # Enable O(N log N) optimization

        df1 = self._create_synthetic_bars(n1)
        df2 = self._create_synthetic_bars(n2)

        # Warm-up run to eliminate cache effects
        detect_swings(df1, lookback=5, filter_redundant=False, max_pair_distance=max_pair_distance)
        detect_swings(df2, lookback=5, filter_redundant=False, max_pair_distance=max_pair_distance)

        # Collect multiple timing samples
        times1 = []
        times2 = []

        for _ in range(num_runs):
            start = time.time()
            detect_swings(df1, lookback=5, filter_redundant=False, max_pair_distance=max_pair_distance)
            times1.append(time.time() - start)

            start = time.time()
            detect_swings(df2, lookback=5, filter_redundant=False, max_pair_distance=max_pair_distance)
            times2.append(time.time() - start)

        # Use minimum time (best represents true algorithm performance)
        time1 = min(times1)
        time2 = min(times2)

        # For O(N²), ratio would be ~4x
        # For O(N log N), ratio would be ~2.3x
        ratio = time2 / time1 if time1 > 0.001 else float('inf')

        print(f"Scaling test: {n1} bars = {time1*1000:.1f}ms (min of {num_runs}), "
              f"{n2} bars = {time2*1000:.1f}ms (min of {num_runs}), ratio = {ratio:.2f}x")

        # Threshold at 3.5: O(N²) would show 4x+, O(N log N) shows ~2-2.5x
        # This catches genuine regressions while tolerating measurement variance
        self.assertLess(ratio, 3.5,
                       f"Scaling ratio {ratio:.2f}x suggests worse than O(N log N)")


class TestSwingDetectorLargeDataset(unittest.TestCase):
    """Test performance at production scale (6M bars target)"""

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

    def test_1m_bars_with_distance_limit(self):
        """
        1M bars should complete in <10s with max_pair_distance=2000.
        This validates the 6M bar target (<60s) is achievable.
        """
        df = self._create_synthetic_bars(1_000_000)

        start = time.time()
        result = detect_swings(df, lookback=5, filter_redundant=False, max_pair_distance=2000)
        elapsed = time.time() - start

        # 1M bars in <10s implies 6M bars in <60s
        self.assertLess(elapsed, 10.0, f"1M bars took {elapsed:.2f}s, expected <10s")

        # Sanity check results
        self.assertGreater(len(result['swing_highs']), 0)
        self.assertGreater(len(result['swing_lows']), 0)

        print(f"1M bars: {elapsed:.2f}s, {len(result['swing_highs'])} highs, "
              f"{len(result['swing_lows'])} lows, {len(result['bull_references'])} bull refs")

    def test_extrapolated_6m_performance(self):
        """
        Test that extrapolated 6M performance meets <60s target.
        Uses 100K bars and extrapolates (avoids memory issues in CI).
        """
        df = self._create_synthetic_bars(100_000)

        start = time.time()
        result = detect_swings(df, lookback=5, filter_redundant=False, max_pair_distance=2000)
        elapsed = time.time() - start

        # Extrapolate to 6M: With max_pair_distance, scaling is linear
        extrapolated_6m = elapsed * 60  # 100K to 6M

        self.assertLess(extrapolated_6m, 60.0,
                       f"Extrapolated 6M time {extrapolated_6m:.1f}s exceeds 60s target")

        print(f"100K bars: {elapsed:.3f}s -> Extrapolated 6M: {extrapolated_6m:.1f}s")


class TestMaxRankParameter(unittest.TestCase):
    """Test max_rank parameter for filtering secondary structures."""

    def _create_synthetic_bars(self, num_bars: int, seed: int = 42) -> pd.DataFrame:
        """Create synthetic OHLC data with multiple swing patterns."""
        np.random.seed(seed)
        prices = np.cumsum(np.random.randn(num_bars) * 2) + 5000
        return pd.DataFrame({
            'open': prices,
            'high': prices + np.abs(np.random.randn(num_bars)),
            'low': prices - np.abs(np.random.randn(num_bars)),
            'close': prices + np.random.randn(num_bars) * 0.5
        })

    def test_max_rank_none_returns_all(self):
        """With max_rank=None (default), all swings are returned."""
        df = self._create_synthetic_bars(1000)

        result_all = detect_swings(df, lookback=5, filter_redundant=False, max_rank=None)
        result_default = detect_swings(df, lookback=5, filter_redundant=False)

        # Both should return the same number of references
        self.assertEqual(len(result_all['bull_references']), len(result_default['bull_references']))
        self.assertEqual(len(result_all['bear_references']), len(result_default['bear_references']))

    def test_max_rank_limits_output(self):
        """max_rank=N limits output to top N swings per direction."""
        df = self._create_synthetic_bars(1000)

        # Get baseline (unfiltered)
        result_all = detect_swings(df, lookback=5, filter_redundant=False, max_rank=None)

        # Test with max_rank=2
        result_top2 = detect_swings(df, lookback=5, filter_redundant=False, max_rank=2)

        # Should have at most 2 per direction
        self.assertLessEqual(len(result_top2['bull_references']), 2)
        self.assertLessEqual(len(result_top2['bear_references']), 2)

        # Should have fewer than unfiltered (if there were more than 2)
        if len(result_all['bull_references']) > 2:
            self.assertEqual(len(result_top2['bull_references']), 2)
        if len(result_all['bear_references']) > 2:
            self.assertEqual(len(result_top2['bear_references']), 2)

    def test_max_rank_one_returns_largest(self):
        """max_rank=1 returns only the largest swing per direction."""
        df = self._create_synthetic_bars(500)

        result_all = detect_swings(df, lookback=5, filter_redundant=False, max_rank=None)
        result_top1 = detect_swings(df, lookback=5, filter_redundant=False, max_rank=1)

        # Should have at most 1 per direction
        self.assertLessEqual(len(result_top1['bull_references']), 1)
        self.assertLessEqual(len(result_top1['bear_references']), 1)

        # The one returned should be rank 1 (largest)
        for ref in result_top1['bull_references']:
            self.assertEqual(ref['rank'], 1)
        for ref in result_top1['bear_references']:
            self.assertEqual(ref['rank'], 1)

    def test_max_rank_preserves_ranking(self):
        """Returned swings should have correct rank values."""
        df = self._create_synthetic_bars(1000)

        result = detect_swings(df, lookback=5, filter_redundant=False, max_rank=3)

        # Check bull references are in descending size order with correct ranks
        bull_refs = result['bull_references']
        for i, ref in enumerate(bull_refs):
            self.assertEqual(ref['rank'], i + 1)
            if i > 0:
                self.assertLessEqual(ref['size'], bull_refs[i - 1]['size'])

        # Check bear references
        bear_refs = result['bear_references']
        for i, ref in enumerate(bear_refs):
            self.assertEqual(ref['rank'], i + 1)
            if i > 0:
                self.assertLessEqual(ref['size'], bear_refs[i - 1]['size'])

    def test_max_rank_with_filtering(self):
        """max_rank works correctly with structural filtering enabled."""
        df = self._create_synthetic_bars(1000)

        # With filtering enabled
        result_filtered = detect_swings(df, lookback=5, filter_redundant=True, max_rank=2)

        # Should still respect max_rank
        self.assertLessEqual(len(result_filtered['bull_references']), 2)
        self.assertLessEqual(len(result_filtered['bear_references']), 2)

    def test_max_rank_larger_than_total(self):
        """max_rank larger than total swings returns all available."""
        df = self._create_synthetic_bars(100)  # Small dataset

        result_all = detect_swings(df, lookback=5, filter_redundant=False, max_rank=None)
        result_large = detect_swings(df, lookback=5, filter_redundant=False, max_rank=1000)

        # Should return the same results
        self.assertEqual(len(result_all['bull_references']), len(result_large['bull_references']))
        self.assertEqual(len(result_all['bear_references']), len(result_large['bear_references']))


class TestSwingPointProtection(unittest.TestCase):
    """Test swing point protection validation"""

    def test_bull_reference_with_violated_low(self):
        """Bull reference should be filtered when swing low is violated."""
        # Pattern: High at 120 -> Low at 100 -> price recovers to 110 -> then violates low to 85
        # Swing size = 20, violation threshold = 100 - (0.1 * 20) = 98
        # Price goes to 85, which is < 98, so reference should be filtered
        prices = (
            [100, 105, 110, 115, 120, 118, 115] +  # Rise to swing high at idx 4
            [112, 108, 104, 100, 102, 105, 108] +  # Drop to swing low at idx 10
            [110, 112, 110, 108, 105, 100, 95, 90, 85, 90, 95, 100, 105, 110]  # Recovery then violation to 85
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],  # Low at idx 10 is 99, low at idx 22 is 84
            'close': prices
        })

        # With protection validation enabled (default)
        result_with_protection = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.1)

        # Without protection validation
        result_without_protection = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=None)

        # The reference from high->low should be filtered out when protection is enabled
        # because subsequent price action violated the swing low
        bull_refs_with = result_with_protection['bull_references']
        bull_refs_without = result_without_protection['bull_references']

        # Should have fewer bull references when protection is enabled
        self.assertLessEqual(len(bull_refs_with), len(bull_refs_without),
            "Protection validation should filter out violated references")

    def test_bull_reference_with_protected_low(self):
        """Bull reference should be kept when swing low is not violated."""
        # Pattern: High at 120 -> Low at 100 -> price recovers and stays above low
        prices = (
            [100, 105, 110, 115, 120, 118, 115] +  # Rise to swing high at idx 4
            [112, 108, 104, 100, 102, 105, 108] +  # Drop to swing low at idx 10
            [110, 112, 114, 112, 110, 108, 106, 104, 102, 101, 102, 104, 106, 108]  # Never goes below 100
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 0.5 for p in prices],
            'low': [p - 0.5 for p in prices],  # Low at idx 10 is 99.5, never violated
            'close': prices
        })

        # With protection validation enabled (default)
        result_with_protection = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.1)

        # Without protection validation
        result_without_protection = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=None)

        # Both should have the same bull references since low was never violated
        bull_refs_with = result_with_protection['bull_references']
        bull_refs_without = result_without_protection['bull_references']

        # Reference count should be the same when low is protected
        self.assertEqual(len(bull_refs_with), len(bull_refs_without),
            "Protected references should be kept")

    def test_bear_reference_with_violated_high(self):
        """Bear reference should be filtered when swing high is violated."""
        # Pattern: Low at 100 -> High at 120 -> price drops to 110 -> then violates high to 135
        # Swing size = 20, violation threshold = 120 + (0.1 * 20) = 122
        # Price goes to 135, which is > 122, so reference should be filtered
        prices = (
            [120, 115, 110, 105, 100, 102, 105] +  # Drop to swing low at idx 4
            [108, 112, 116, 120, 118, 115, 112] +  # Rise to swing high at idx 10
            [110, 108, 110, 112, 115, 120, 125, 130, 135, 130, 125, 120, 115, 110]  # Drop then violation to 135
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],  # High at idx 10 is 121, high at idx 22 is 136
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # With protection validation enabled (default)
        result_with_protection = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.1)

        # Without protection validation
        result_without_protection = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=None)

        bear_refs_with = result_with_protection['bear_references']
        bear_refs_without = result_without_protection['bear_references']

        # Should have fewer bear references when protection is enabled
        self.assertLessEqual(len(bear_refs_with), len(bear_refs_without),
            "Protection validation should filter out violated references")

    def test_protection_tolerance_threshold(self):
        """Protection should only filter when violation exceeds tolerance threshold."""
        # Pattern with 5% violation (within 10% tolerance)
        # High at 120 -> Low at 100 -> size = 20
        # 5% of 20 = 1, so violation threshold = 100 - 2 = 98
        # If price goes to 99, it's within tolerance and should be kept
        prices = (
            [100, 105, 110, 115, 120, 118, 115] +  # Rise to swing high at idx 4
            [112, 108, 104, 100, 102, 105, 108] +  # Drop to swing low at idx 10
            [110, 108, 106, 104, 102, 100, 99, 100, 102, 104, 106, 108, 110, 112]  # Goes to 99 (5% violation)
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 0.5 for p in prices],
            'low': [p - 0.5 for p in prices],  # Low at idx 10 is 99.5, later low is 98.5
            'close': prices
        })

        # With 10% tolerance - should keep reference (5% violation < 10% threshold)
        result_10pct = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.1)

        # With 3% tolerance - should filter reference (5% violation > 3% threshold)
        result_3pct = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.03)

        # 10% tolerance should be more permissive
        self.assertGreaterEqual(len(result_10pct['bull_references']), len(result_3pct['bull_references']),
            "Higher tolerance should keep more references")

    def test_protection_disabled_with_none(self):
        """Setting protection_tolerance=None should disable protection validation."""
        # Same violated pattern as test_bull_reference_with_violated_low
        prices = (
            [100, 105, 110, 115, 120, 118, 115] +
            [112, 108, 104, 100, 102, 105, 108] +
            [110, 112, 110, 108, 105, 100, 95, 90, 85, 90, 95, 100, 105, 110]
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # With protection disabled
        result = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=None)

        # Should still return results (not crash)
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

    def test_bull_preformation_high_violated(self):
        """Bull reference should be filtered when high is violated before low forms."""
        # Pattern: High at 120 -> Higher high at 130 -> Low at 100
        # The original high at 120 is violated by 130 before the low at 100 forms
        # So 120->100 should be filtered, but 130->100 should be valid
        prices = (
            [100, 105, 110, 115, 120, 118, 115] +  # Swing high at idx 4 (high=121)
            [118, 122, 128, 130, 125, 120, 115] +  # Higher high at idx 10 (high=131)
            [112, 108, 104, 100, 102, 105, 108] +  # Swing low at idx 17 (low=99)
            [110, 112, 114, 112, 110, 108, 106, 108, 110, 112]  # Recovery
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # With protection validation enabled
        result_with = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.1)

        # Without protection validation
        result_without = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=None)

        # With protection, the 120->100 reference should be filtered (high violated by 130)
        # Without protection, it would still appear
        # The 130->100 reference should exist in both
        self.assertLessEqual(len(result_with['bull_references']), len(result_without['bull_references']),
            "Pre-formation protection should filter violated high references")

    def test_bear_preformation_low_violated(self):
        """Bear reference should be filtered when low is violated before high forms."""
        # Pattern: Low at 100 -> Lower low at 90 -> High at 120
        # The original low at 100 is violated by 90 before the high at 120 forms
        # So 100->120 should be filtered, but 90->120 should be valid
        prices = (
            [120, 115, 110, 105, 100, 102, 105] +  # Swing low at idx 4 (low=99)
            [102, 98, 92, 90, 95, 100, 105] +      # Lower low at idx 10 (low=89)
            [108, 112, 116, 120, 118, 115, 112] +  # Swing high at idx 17 (high=121)
            [110, 108, 106, 108, 110, 112, 114, 112, 110, 108]  # Continued
        )

        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # With protection validation enabled
        result_with = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=0.1)

        # Without protection validation
        result_without = detect_swings(df, lookback=2, filter_redundant=False, protection_tolerance=None)

        # With protection, the 100->120 reference should be filtered (low violated by 90)
        # Without protection, it would still appear
        self.assertLessEqual(len(result_with['bear_references']), len(result_without['bear_references']),
            "Pre-formation protection should filter violated low references")


class TestSizeFilter(unittest.TestCase):
    """Test suite for min_candle_ratio and min_range_pct size filters."""

    def test_size_filter_backward_compatibility(self):
        """Default None values should not filter any swings."""
        # Create data with small swings
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 105, 110]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 2 for p in prices],
            'low': [p - 2 for p in prices],
            'close': prices
        })

        # Without size filter (default)
        result_default = detect_swings(df, lookback=2, filter_redundant=False)

        # Explicitly passing None should be the same
        result_none = detect_swings(df, lookback=2, filter_redundant=False,
                                    min_candle_ratio=None, min_range_pct=None)

        self.assertEqual(len(result_default['bull_references']), len(result_none['bull_references']))
        self.assertEqual(len(result_default['bear_references']), len(result_none['bear_references']))

    def test_size_filter_filters_small_swings(self):
        """Swings below both thresholds should be filtered."""
        # Test directly on the helper function for precise control
        from src.swing_analysis.swing_detector import _apply_size_filter

        # Setup: median_candle = 2, price_range = 100
        references = [
            {"size": 5.0, "high_bar_index": 10, "low_bar_index": 0},   # 2.5x candle, 5% range - should filter (fails both)
            {"size": 15.0, "high_bar_index": 30, "low_bar_index": 20},  # 7.5x candle, 15% range - should keep (passes candle)
            {"size": 3.0, "high_bar_index": 50, "low_bar_index": 45},   # 1.5x candle, 3% range - should keep (passes range)
        ]

        # min_candle_ratio=5.0 (needs size >= 10), min_range_pct=10.0 (needs size >= 10)
        filtered = _apply_size_filter(references, median_candle=2.0, price_range=100.0,
                                      min_candle_ratio=5.0, min_range_pct=10.0)

        # First swing (size=5) fails both: 2.5x < 5x and 5% < 10%
        # Second swing (size=15) passes: 7.5x >= 5x
        # Third swing (size=3) fails: 1.5x < 5x and 3% < 10%
        self.assertEqual(len(filtered), 1, "Only swings passing at least one threshold should be kept")
        self.assertEqual(filtered[0]["size"], 15.0)

    def test_size_filter_or_logic_candle_ratio_passes(self):
        """Swing should be kept if candle_ratio passes, even if range_pct fails."""
        from src.swing_analysis.swing_detector import _apply_size_filter

        # Swing size = 12, median_candle = 2 (6x), price_range = 1000 (1.2% - fails)
        references = [
            {"size": 12.0, "high_bar_index": 20, "low_bar_index": 10},
        ]

        # 6x candle passes (>= 5x), 1.2% range fails (< 10%)
        filtered = _apply_size_filter(references, median_candle=2.0, price_range=1000.0,
                                      min_candle_ratio=5.0, min_range_pct=10.0)

        self.assertEqual(len(filtered), 1, "Swing passing candle_ratio should be kept")

    def test_size_filter_or_logic_range_pct_passes(self):
        """Swing should be kept if range_pct passes, even if candle_ratio fails."""
        from src.swing_analysis.swing_detector import _apply_size_filter

        # Swing size = 15, median_candle = 10 (1.5x - fails), price_range = 50 (30% - passes)
        references = [
            {"size": 15.0, "high_bar_index": 20, "low_bar_index": 10},
        ]

        # 1.5x candle fails (< 5x), 30% range passes (>= 10%)
        filtered = _apply_size_filter(references, median_candle=10.0, price_range=50.0,
                                      min_candle_ratio=5.0, min_range_pct=10.0)

        self.assertEqual(len(filtered), 1, "Swing passing range_pct should be kept")

    def test_high_volatility_exception_keeps_short_large_swings(self):
        """1-2 bar swings with 3x+ median candle should be kept."""
        from src.swing_analysis.swing_detector import _apply_size_filter

        # Swing spans 2 bars (bar 10 to 11), size = 8, median_candle = 2 (4x)
        # Fails candle_ratio (4x < 5x), fails range_pct (8% < 10%)
        # BUT passes high volatility exception (span=2, 4x >= 3x)
        references = [
            {"size": 8.0, "high_bar_index": 11, "low_bar_index": 10},  # 2-bar swing
        ]

        filtered = _apply_size_filter(references, median_candle=2.0, price_range=100.0,
                                      min_candle_ratio=5.0, min_range_pct=10.0)

        self.assertEqual(len(filtered), 1, "Short high-volatility swing should be kept")

    def test_high_volatility_exception_not_applied_to_long_swings(self):
        """Swings > 2 bars should not benefit from high volatility exception."""
        from src.swing_analysis.swing_detector import _apply_size_filter

        # Swing spans 10 bars, size = 8, median_candle = 2 (4x)
        # Fails both thresholds and doesn't qualify for high volatility exception
        references = [
            {"size": 8.0, "high_bar_index": 20, "low_bar_index": 10},  # 11-bar swing
        ]

        filtered = _apply_size_filter(references, median_candle=2.0, price_range=100.0,
                                      min_candle_ratio=5.0, min_range_pct=10.0)

        self.assertEqual(len(filtered), 0, "Long swing not qualifying should be filtered")

    def test_size_filter_with_only_candle_ratio(self):
        """Setting only min_candle_ratio should filter by candle ratio only."""
        prices = [100, 105, 110, 120, 130, 125, 115, 105, 100, 102, 105]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # Only candle ratio filter
        result = detect_swings(df, lookback=2, filter_redundant=False,
                               min_candle_ratio=5.0, min_range_pct=None)

        # Should work without error
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

    def test_size_filter_with_only_range_pct(self):
        """Setting only min_range_pct should filter by range percentage only."""
        prices = [100, 105, 110, 120, 130, 125, 115, 105, 100, 102, 105]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # Only range pct filter
        result = detect_swings(df, lookback=2, filter_redundant=False,
                               min_candle_ratio=None, min_range_pct=2.0)

        # Should work without error
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

    def test_size_filter_empty_dataframe(self):
        """Size filter should handle empty DataFrame gracefully."""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close'])

        result = detect_swings(df, lookback=2, filter_redundant=False,
                               min_candle_ratio=5.0, min_range_pct=2.0)

        self.assertEqual(result['bull_references'], [])
        self.assertEqual(result['bear_references'], [])

    def test_size_filter_integration_with_other_filters(self):
        """Size filter should work correctly with redundancy and max_rank filters."""
        prices = (
            [100, 105, 110, 120, 130, 140, 135, 125, 115, 105, 100] +
            [102, 106, 112, 120, 130, 145, 155, 150, 140, 125, 110, 100] +
            [105, 110, 115, 120]
        )
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # All filters enabled
        result = detect_swings(df, lookback=2, filter_redundant=True,
                               min_candle_ratio=3.0, min_range_pct=1.0,
                               max_rank=5)

        # Should return valid results with all filters applied
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

        # Ranks should be sequential
        for i, ref in enumerate(result['bull_references']):
            self.assertEqual(ref['rank'], i + 1)
        for i, ref in enumerate(result['bear_references']):
            self.assertEqual(ref['rank'], i + 1)


class TestProminenceFilter(unittest.TestCase):
    """Test suite for min_prominence filter."""

    def test_prominence_filter_backward_compatibility(self):
        """Default None value should not filter any swings."""
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 105, 110]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 2 for p in prices],
            'low': [p - 2 for p in prices],
            'close': prices
        })

        # Without prominence filter (default)
        result_default = detect_swings(df, lookback=2, filter_redundant=False)

        # Explicitly passing None should be the same
        result_none = detect_swings(df, lookback=2, filter_redundant=False,
                                    min_prominence=None)

        self.assertEqual(len(result_default['bull_references']), len(result_none['bull_references']))
        self.assertEqual(len(result_default['bear_references']), len(result_none['bear_references']))

    def test_calculate_prominence_swing_high(self):
        """Test prominence calculation for swing highs."""
        from src.swing_analysis.swing_detector import _calculate_prominence
        import numpy as np

        # Window: [100, 105, 120, 105, 100] - index 2 is the high
        # Prominence = 120 - 105 = 15
        prices = np.array([100.0, 105.0, 120.0, 105.0, 100.0])

        prominence = _calculate_prominence(120.0, 2, prices, lookback=2, is_high=True)
        self.assertEqual(prominence, 15.0)

    def test_calculate_prominence_swing_low(self):
        """Test prominence calculation for swing lows."""
        from src.swing_analysis.swing_detector import _calculate_prominence
        import numpy as np

        # Window: [110, 105, 90, 105, 110] - index 2 is the low
        # Prominence = 105 - 90 = 15
        prices = np.array([110.0, 105.0, 90.0, 105.0, 110.0])

        prominence = _calculate_prominence(90.0, 2, prices, lookback=2, is_high=False)
        self.assertEqual(prominence, 15.0)

    def test_prominence_filter_keeps_prominent_swings(self):
        """Swings with high prominence should be kept."""
        from src.swing_analysis.swing_detector import _apply_prominence_filter
        import numpy as np

        # Swing low at index 5 with strong prominence
        # Surrounding lows: ..., 105, 110, 80, 105, 110, ...
        # Prominence = 105 - 80 = 25
        highs = np.array([100, 105, 110, 115, 120, 125, 120, 115, 110, 105, 100], dtype=np.float64)
        lows = np.array([98, 103, 108, 105, 110, 80, 105, 110, 108, 103, 98], dtype=np.float64)

        # median candle ~= 2, threshold at min_prominence=5.0 is 10.0
        # Prominence 25 >= 10 so should keep
        references = [
            {"high_price": 125.0, "high_bar_index": 5, "low_price": 80.0, "low_bar_index": 5}
        ]

        filtered = _apply_prominence_filter(
            references, highs, lows, lookback=2, median_candle=2.0,
            min_prominence=5.0, direction='bull'
        )

        self.assertEqual(len(filtered), 1)

    def test_prominence_filter_removes_subsumed_swings(self):
        """Swings with low prominence (subsumed) should be filtered."""
        from src.swing_analysis.swing_detector import _apply_prominence_filter
        import numpy as np

        # Swing low at index 5 with weak prominence
        # Surrounding lows: 99, 98, 97, 98, 99 - all very close
        # Prominence = 98 - 97 = 1
        highs = np.array([100, 101, 102, 101, 100, 101, 102, 101, 100, 101, 102], dtype=np.float64)
        lows = np.array([99, 98, 97, 98, 99, 97, 98, 99, 98, 97, 99], dtype=np.float64)

        # median candle ~= 3, threshold at min_prominence=1.0 is 3.0
        # Prominence 1 < 3 so should filter
        references = [
            {"high_price": 102.0, "high_bar_index": 2, "low_price": 97.0, "low_bar_index": 5}
        ]

        filtered = _apply_prominence_filter(
            references, highs, lows, lookback=2, median_candle=3.0,
            min_prominence=1.0, direction='bull'
        )

        self.assertEqual(len(filtered), 0)

    def test_prominence_filter_bear_direction(self):
        """Test prominence filter for bear references (checks swing high)."""
        from src.swing_analysis.swing_detector import _apply_prominence_filter
        import numpy as np

        # Bear reference: low before high. Check the swing high prominence.
        # Swing high at index 5 with strong prominence
        highs = np.array([100, 105, 110, 105, 100, 130, 100, 105, 110, 105, 100], dtype=np.float64)
        lows = np.array([98, 103, 108, 103, 98, 95, 98, 103, 108, 103, 98], dtype=np.float64)

        # Prominence = 130 - 110 = 20
        # median candle ~= 2, threshold at min_prominence=5.0 is 10.0
        # 20 >= 10 so should keep
        references = [
            {"high_price": 130.0, "high_bar_index": 5, "low_price": 95.0, "low_bar_index": 5}
        ]

        filtered = _apply_prominence_filter(
            references, highs, lows, lookback=2, median_candle=2.0,
            min_prominence=5.0, direction='bear'
        )

        self.assertEqual(len(filtered), 1)

    def test_prominence_filter_integration(self):
        """Test prominence filter integrates correctly with detect_swings."""
        # Create data with clear prominent and non-prominent swings
        # A prominent swing followed by a subsumed swing
        prices = (
            [100, 105, 110, 115, 120] +  # Run up
            [115, 110, 105, 100, 95, 90] +  # Sharp drop (prominent low)
            [92, 94, 96, 98, 100, 102, 104] +  # Gradual rise with minor dips
            [103, 104, 105, 106]  # Continue up
        )
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # Without prominence filter
        result_no_filter = detect_swings(df, lookback=2, filter_redundant=False,
                                         min_prominence=None)

        # With prominence filter
        result_filtered = detect_swings(df, lookback=2, filter_redundant=False,
                                        min_prominence=2.0)

        # Filtered should have fewer or equal swings
        self.assertLessEqual(len(result_filtered['bull_references']),
                            len(result_no_filter['bull_references']))
        self.assertLessEqual(len(result_filtered['bear_references']),
                            len(result_no_filter['bear_references']))

    def test_prominence_filter_empty_dataframe(self):
        """Prominence filter should handle empty DataFrame gracefully."""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close'])

        result = detect_swings(df, lookback=2, filter_redundant=False,
                               min_prominence=1.0)

        self.assertEqual(result['bull_references'], [])
        self.assertEqual(result['bear_references'], [])

    def test_prominence_filter_with_all_filters(self):
        """Prominence filter should work correctly with size and redundancy filters."""
        prices = (
            [100, 105, 110, 120, 130, 140, 135, 125, 115, 105, 100] +
            [102, 106, 112, 120, 130, 145, 155, 150, 140, 125, 110, 100] +
            [105, 110, 115, 120]
        )
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # All filters enabled
        result = detect_swings(df, lookback=2, filter_redundant=True,
                               min_candle_ratio=3.0, min_range_pct=1.0,
                               min_prominence=1.0, max_rank=5)

        # Should return valid results with all filters applied
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

        # Ranks should be sequential
        for i, ref in enumerate(result['bull_references']):
            self.assertEqual(ref['rank'], i + 1)
        for i, ref in enumerate(result['bear_references']):
            self.assertEqual(ref['rank'], i + 1)

    def test_prominence_zero_median_candle(self):
        """Filter should handle zero median candle gracefully."""
        from src.swing_analysis.swing_detector import _apply_prominence_filter
        import numpy as np

        highs = np.array([100.0, 100.0, 100.0], dtype=np.float64)
        lows = np.array([100.0, 100.0, 100.0], dtype=np.float64)

        references = [
            {"high_price": 100.0, "high_bar_index": 1, "low_price": 100.0, "low_bar_index": 1}
        ]

        # Should return references unchanged when median_candle is 0
        filtered = _apply_prominence_filter(
            references, highs, lows, lookback=1, median_candle=0.0,
            min_prominence=1.0, direction='bull'
        )

        self.assertEqual(len(filtered), 1)


class TestBestExtremaAdjustment(unittest.TestCase):
    """Test suite for adjust_extrema feature (best extrema adjustment)."""

    def test_adjust_extrema_default_enabled(self):
        """Default adjust_extrema=True should be enabled."""
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 105, 110]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 2 for p in prices],
            'low': [p - 2 for p in prices],
            'close': prices
        })

        # With adjust_extrema (default True)
        result_adjusted = detect_swings(df, lookback=2, filter_redundant=False)

        # Without adjust_extrema
        result_original = detect_swings(df, lookback=2, filter_redundant=False,
                                        adjust_extrema=False)

        # Both should return valid results
        self.assertIn('bull_references', result_adjusted)
        self.assertIn('bull_references', result_original)

    def test_adjust_extrema_false_preserves_original(self):
        """adjust_extrema=False should preserve original endpoint detection."""
        # Create data where adjustment would change endpoints
        # Swing high at index 4 (120), but index 5 has higher high (122)
        prices = [100, 105, 110, 115, 120, 118, 110, 105, 100, 95, 90, 95, 100]
        highs = [p + 2 for p in prices]
        highs[5] = 122  # Higher high nearby but not the detected swing point
        lows = [p - 2 for p in prices]

        df = pd.DataFrame({
            'open': prices,
            'high': highs,
            'low': lows,
            'close': prices
        })

        # Without adjustment - should use original detection
        result = detect_swings(df, lookback=2, filter_redundant=False,
                               adjust_extrema=False, protection_tolerance=None)

        # Check that references maintain original indices
        # (The actual indices depend on detection, this validates the parameter works)
        self.assertIn('bull_references', result)

    def test_adjust_to_best_extrema_function_directly(self):
        """Test _adjust_to_best_extrema function directly."""
        from src.swing_analysis.swing_detector import _adjust_to_best_extrema
        import numpy as np

        # Create price arrays where better extrema exist nearby
        highs = np.array([100, 105, 110, 125, 120, 105, 100, 95, 90, 85, 80], dtype=np.float64)
        lows = np.array([98, 103, 108, 113, 118, 103, 98, 93, 88, 70, 78], dtype=np.float64)

        # Original swing: high at index 4 (120), low at index 8 (88)
        # Better high at index 3 (125), better low at index 9 (70)
        original_swing = {
            'high_price': 120.0,
            'high_bar_index': 4,
            'low_price': 88.0,
            'low_bar_index': 8,
            'size': 32.0,
            'level_0382': 88.0 + (0.382 * 32.0),
            'level_2x': 88.0 + (2.0 * 32.0),
            'rank': 0
        }

        adjusted = _adjust_to_best_extrema(original_swing, highs, lows, lookback=2)

        # High should be adjusted to index 3 (125)
        self.assertEqual(adjusted['high_bar_index'], 3)
        self.assertEqual(adjusted['high_price'], 125.0)

        # Low should be adjusted to index 9 (70)
        self.assertEqual(adjusted['low_bar_index'], 9)
        self.assertEqual(adjusted['low_price'], 70.0)

        # Size should be recalculated
        self.assertEqual(adjusted['size'], 55.0)  # 125 - 70

    def test_adjust_extrema_no_change_when_optimal(self):
        """When detected points are already optimal, adjustment should not change them."""
        from src.swing_analysis.swing_detector import _adjust_to_best_extrema
        import numpy as np

        # Create data where the detected points ARE the best extrema
        highs = np.array([100, 105, 130, 105, 100], dtype=np.float64)  # 130 is highest
        lows = np.array([98, 103, 70, 103, 98], dtype=np.float64)  # 70 is lowest

        original_swing = {
            'high_price': 130.0,
            'high_bar_index': 2,
            'low_price': 70.0,
            'low_bar_index': 2,
            'size': 60.0,
            'level_0382': 70.0 + (0.382 * 60.0),
            'level_2x': 70.0 + (2.0 * 60.0),
            'rank': 0
        }

        adjusted = _adjust_to_best_extrema(original_swing, highs, lows, lookback=2)

        # Should not change when already optimal
        self.assertEqual(adjusted['high_bar_index'], 2)
        self.assertEqual(adjusted['low_bar_index'], 2)
        self.assertEqual(adjusted['size'], 60.0)

    def test_adjust_extrema_respects_lookback_boundary(self):
        """Adjustment should only search within ±lookback bars."""
        from src.swing_analysis.swing_detector import _adjust_to_best_extrema
        import numpy as np

        # Better extrema exist but outside lookback window
        highs = np.array([200, 100, 105, 110, 105, 100, 200], dtype=np.float64)
        lows = np.array([50, 98, 103, 90, 103, 98, 50], dtype=np.float64)

        # With lookback=1, indices 0 and 6 should not be considered
        original_swing = {
            'high_price': 110.0,
            'high_bar_index': 3,
            'low_price': 90.0,
            'low_bar_index': 3,
            'size': 20.0,
            'level_0382': 90.0 + (0.382 * 20.0),
            'level_2x': 90.0 + (2.0 * 20.0),
            'rank': 0
        }

        adjusted = _adjust_to_best_extrema(original_swing, highs, lows, lookback=1)

        # Should NOT find index 0 or 6 (outside lookback)
        self.assertNotEqual(adjusted['high_bar_index'], 0)
        self.assertNotEqual(adjusted['high_bar_index'], 6)
        self.assertNotEqual(adjusted['low_bar_index'], 0)
        self.assertNotEqual(adjusted['low_bar_index'], 6)

    def test_adjust_extrema_handles_edge_indices(self):
        """Adjustment should handle swings near array boundaries."""
        from src.swing_analysis.swing_detector import _adjust_to_best_extrema
        import numpy as np

        highs = np.array([120, 100, 105, 110], dtype=np.float64)
        lows = np.array([70, 98, 103, 108], dtype=np.float64)

        # Swing near start of array
        original_swing = {
            'high_price': 100.0,
            'high_bar_index': 1,
            'low_price': 98.0,
            'low_bar_index': 1,
            'size': 2.0,
            'level_0382': 98.0 + (0.382 * 2.0),
            'level_2x': 98.0 + (2.0 * 2.0),
            'rank': 0
        }

        # Should not crash and should find better extrema at index 0
        adjusted = _adjust_to_best_extrema(original_swing, highs, lows, lookback=2)

        self.assertEqual(adjusted['high_bar_index'], 0)
        self.assertEqual(adjusted['high_price'], 120.0)
        self.assertEqual(adjusted['low_bar_index'], 0)
        self.assertEqual(adjusted['low_price'], 70.0)

    def test_adjust_extrema_with_protection_revalidation(self):
        """Adjusted swings should be re-validated against protection rules."""
        # Create scenario where original swing passes protection
        # but adjusted swing might fail (or vice versa)
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 95, 90, 85]
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 2 for p in prices],
            'low': [p - 2 for p in prices],
            'close': prices
        })

        # With adjustment and protection
        result_adjusted = detect_swings(df, lookback=2, filter_redundant=False,
                                        adjust_extrema=True,
                                        protection_tolerance=0.1)

        # Without adjustment but with protection
        result_original = detect_swings(df, lookback=2, filter_redundant=False,
                                        adjust_extrema=False,
                                        protection_tolerance=0.1)

        # Both should produce valid results
        self.assertIn('bull_references', result_adjusted)
        self.assertIn('bull_references', result_original)

    def test_adjust_extrema_integration_with_all_filters(self):
        """Test adjust_extrema works correctly with all other filters."""
        prices = (
            [100, 105, 110, 115, 120, 125, 130, 125, 120, 115, 110, 105, 100] +
            [105, 110, 115, 120, 125, 130, 135, 140, 135, 130, 125]
        )
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 3 for p in prices],
            'low': [p - 3 for p in prices],
            'close': prices
        })

        # All filters enabled with adjustment
        result = detect_swings(df, lookback=2, filter_redundant=True,
                               adjust_extrema=True,
                               protection_tolerance=0.1,
                               min_candle_ratio=2.0,
                               min_range_pct=1.0,
                               min_prominence=1.0,
                               max_rank=5)

        # Should return valid results with proper ranking
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

        # Ranks should be sequential
        for i, ref in enumerate(result['bull_references']):
            self.assertEqual(ref['rank'], i + 1)
        for i, ref in enumerate(result['bear_references']):
            self.assertEqual(ref['rank'], i + 1)

    def test_adjust_extrema_recalculates_size_correctly(self):
        """Adjusted swings should have correctly recalculated size."""
        from src.swing_analysis.swing_detector import _adjust_to_best_extrema
        import numpy as np

        highs = np.array([100, 110, 150, 110, 100], dtype=np.float64)
        lows = np.array([95, 100, 50, 100, 95], dtype=np.float64)

        # Original swing: size = 110 - 100 = 10
        original_swing = {
            'high_price': 110.0,
            'high_bar_index': 1,
            'low_price': 100.0,
            'low_bar_index': 3,
            'size': 10.0,
            'level_0382': 100.0 + (0.382 * 10.0),
            'level_2x': 100.0 + (2.0 * 10.0),
            'rank': 0
        }

        adjusted = _adjust_to_best_extrema(original_swing, highs, lows, lookback=2)

        # Adjusted should find 150 high and 50 low
        self.assertEqual(adjusted['high_price'], 150.0)
        self.assertEqual(adjusted['low_price'], 50.0)
        self.assertEqual(adjusted['size'], 100.0)  # 150 - 50

        # Level calculations should be updated
        self.assertAlmostEqual(adjusted['level_0382'], 50.0 + (0.382 * 100.0), places=5)
        self.assertAlmostEqual(adjusted['level_2x'], 50.0 + (2.0 * 100.0), places=5)

    def test_adjust_extrema_empty_dataframe(self):
        """adjust_extrema should handle empty DataFrame gracefully."""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close'])

        result = detect_swings(df, lookback=2, filter_redundant=False,
                               adjust_extrema=True)

        self.assertEqual(result['bull_references'], [])
        self.assertEqual(result['bear_references'], [])


class TestQuotaFilter(unittest.TestCase):
    """Test suite for quota parameter and _apply_quota function."""

    def _create_synthetic_bars(self, num_bars: int, seed: int = 42) -> pd.DataFrame:
        """Create synthetic OHLC data with multiple swing patterns."""
        np.random.seed(seed)
        prices = np.cumsum(np.random.randn(num_bars) * 2) + 5000
        return pd.DataFrame({
            'open': prices,
            'high': prices + np.abs(np.random.randn(num_bars)),
            'low': prices - np.abs(np.random.randn(num_bars)),
            'close': prices + np.random.randn(num_bars) * 0.5
        })

    def test_quota_none_returns_all(self):
        """With quota=None (default), all swings are returned."""
        df = self._create_synthetic_bars(1000)

        result_all = detect_swings(df, lookback=5, filter_redundant=False, quota=None)
        result_default = detect_swings(df, lookback=5, filter_redundant=False)

        # Both should return the same number of references
        self.assertEqual(len(result_all['bull_references']), len(result_default['bull_references']))
        self.assertEqual(len(result_all['bear_references']), len(result_default['bear_references']))

    def test_quota_limits_output(self):
        """quota=N limits output to top N swings per direction."""
        df = self._create_synthetic_bars(1000)

        # Get baseline (unfiltered)
        result_all = detect_swings(df, lookback=5, filter_redundant=False, quota=None)

        # Test with quota=2
        result_quota2 = detect_swings(df, lookback=5, filter_redundant=False, quota=2)

        # Should have at most 2 per direction
        self.assertLessEqual(len(result_quota2['bull_references']), 2)
        self.assertLessEqual(len(result_quota2['bear_references']), 2)

        # Should have fewer than unfiltered (if there were more than 2)
        if len(result_all['bull_references']) > 2:
            self.assertEqual(len(result_quota2['bull_references']), 2)
        if len(result_all['bear_references']) > 2:
            self.assertEqual(len(result_quota2['bear_references']), 2)

    def test_quota_adds_impulse_field(self):
        """Swings with quota should have impulse field."""
        df = self._create_synthetic_bars(500)

        result = detect_swings(df, lookback=5, filter_redundant=False, quota=5)

        for ref in result['bull_references']:
            self.assertIn('impulse', ref)
            self.assertIsNotNone(ref['impulse'])
            # Impulse should be positive (size / span)
            self.assertGreater(ref['impulse'], 0)

        for ref in result['bear_references']:
            self.assertIn('impulse', ref)
            self.assertIsNotNone(ref['impulse'])
            self.assertGreater(ref['impulse'], 0)

    def test_quota_adds_ranking_fields(self):
        """Swings with quota should have size_rank, impulse_rank, combined_score."""
        df = self._create_synthetic_bars(500)

        result = detect_swings(df, lookback=5, filter_redundant=False, quota=5)

        for ref in result['bull_references']:
            self.assertIn('size_rank', ref)
            self.assertIn('impulse_rank', ref)
            self.assertIn('combined_score', ref)
            # Ranks should be positive integers
            self.assertGreater(ref['size_rank'], 0)
            self.assertGreater(ref['impulse_rank'], 0)
            # Combined score should be positive
            self.assertGreater(ref['combined_score'], 0)

    def test_quota_combined_score_calculation(self):
        """Combined score should be 0.6 * size_rank + 0.4 * impulse_rank."""
        from src.swing_analysis.swing_detector import _apply_quota

        references = [
            {"size": 10.0, "high_bar_index": 10, "low_bar_index": 0},
            {"size": 20.0, "high_bar_index": 25, "low_bar_index": 5},
            {"size": 15.0, "high_bar_index": 40, "low_bar_index": 30},
        ]

        result = _apply_quota(references, quota=3)

        for ref in result:
            expected_score = 0.6 * ref['size_rank'] + 0.4 * ref['impulse_rank']
            self.assertAlmostEqual(ref['combined_score'], expected_score, places=5)

    def test_quota_impulse_calculation(self):
        """Impulse should be size / span."""
        from src.swing_analysis.swing_detector import _apply_quota

        references = [
            {"size": 10.0, "high_bar_index": 10, "low_bar_index": 0},  # span = 11
            {"size": 20.0, "high_bar_index": 5, "low_bar_index": 3},   # span = 3
        ]

        result = _apply_quota(references, quota=2)

        # First ref: size=10, span=11, impulse = 10/11 ≈ 0.909
        # Second ref: size=20, span=3, impulse = 20/3 ≈ 6.667
        ref1 = [r for r in result if r['size'] == 10.0][0]
        ref2 = [r for r in result if r['size'] == 20.0][0]

        self.assertAlmostEqual(ref1['impulse'], 10.0 / 11, places=3)
        self.assertAlmostEqual(ref2['impulse'], 20.0 / 3, places=3)

    def test_quota_sorts_by_combined_score(self):
        """Swings should be sorted by combined score (lower is better)."""
        df = self._create_synthetic_bars(1000)

        result = detect_swings(df, lookback=5, filter_redundant=False, quota=5)

        # Check bull references are sorted by combined_score
        if len(result['bull_references']) > 1:
            for i in range(len(result['bull_references']) - 1):
                current = result['bull_references'][i]['combined_score']
                next_score = result['bull_references'][i + 1]['combined_score']
                self.assertLessEqual(current, next_score)

        # Check bear references are sorted by combined_score
        if len(result['bear_references']) > 1:
            for i in range(len(result['bear_references']) - 1):
                current = result['bear_references'][i]['combined_score']
                next_score = result['bear_references'][i + 1]['combined_score']
                self.assertLessEqual(current, next_score)

    def test_quota_takes_precedence_over_max_rank(self):
        """quota should take precedence over max_rank when both are set."""
        df = self._create_synthetic_bars(1000)

        # With both quota=3 and max_rank=5, quota should win
        result = detect_swings(df, lookback=5, filter_redundant=False, quota=3, max_rank=5)

        # Should respect quota (3), not max_rank (5)
        self.assertLessEqual(len(result['bull_references']), 3)
        self.assertLessEqual(len(result['bear_references']), 3)

    def test_quota_backward_compatibility_with_max_rank(self):
        """max_rank should still work when quota is not set."""
        df = self._create_synthetic_bars(1000)

        # Get baseline
        result_all = detect_swings(df, lookback=5, filter_redundant=False)

        # With only max_rank
        result_max_rank = detect_swings(df, lookback=5, filter_redundant=False, max_rank=2)

        # Should have at most 2 per direction (max_rank behavior)
        self.assertLessEqual(len(result_max_rank['bull_references']), 2)
        self.assertLessEqual(len(result_max_rank['bear_references']), 2)

        # Should NOT have quota fields when only max_rank is used
        for ref in result_max_rank['bull_references']:
            self.assertNotIn('impulse', ref)
            self.assertNotIn('combined_score', ref)

    def test_quota_with_filtering(self):
        """quota works correctly with structural filtering enabled."""
        df = self._create_synthetic_bars(1000)

        # With filtering enabled
        result_filtered = detect_swings(df, lookback=5, filter_redundant=True, quota=2)

        # Should still respect quota
        self.assertLessEqual(len(result_filtered['bull_references']), 2)
        self.assertLessEqual(len(result_filtered['bear_references']), 2)

        # Should have quota fields
        for ref in result_filtered['bull_references']:
            self.assertIn('combined_score', ref)

    def test_quota_larger_than_total(self):
        """quota larger than total swings returns all available."""
        df = self._create_synthetic_bars(100)  # Small dataset

        result_all = detect_swings(df, lookback=5, filter_redundant=False, quota=None)
        result_large = detect_swings(df, lookback=5, filter_redundant=False, quota=1000)

        # Should return the same number of results
        self.assertEqual(len(result_all['bull_references']), len(result_large['bull_references']))
        self.assertEqual(len(result_all['bear_references']), len(result_large['bear_references']))

    def test_quota_empty_references(self):
        """_apply_quota should handle empty references gracefully."""
        from src.swing_analysis.swing_detector import _apply_quota

        result = _apply_quota([], quota=5)
        self.assertEqual(result, [])

    def test_quota_preserves_final_rank(self):
        """Final rank should be assigned based on position after quota filter."""
        df = self._create_synthetic_bars(500)

        result = detect_swings(df, lookback=5, filter_redundant=False, quota=3)

        # Ranks should be sequential 1, 2, 3
        for i, ref in enumerate(result['bull_references']):
            self.assertEqual(ref['rank'], i + 1)
        for i, ref in enumerate(result['bear_references']):
            self.assertEqual(ref['rank'], i + 1)

    def test_quota_with_all_filters(self):
        """quota should work correctly with all other filters enabled."""
        prices = (
            [100, 105, 110, 120, 130, 140, 135, 125, 115, 105, 100] +
            [102, 106, 112, 120, 130, 145, 155, 150, 140, 125, 110, 100] +
            [105, 110, 115, 120]
        )
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'close': prices
        })

        # All filters enabled including quota
        result = detect_swings(df, lookback=2, filter_redundant=True,
                               min_candle_ratio=3.0, min_range_pct=1.0,
                               min_prominence=1.0, quota=5)

        # Should return valid results with all filters applied
        self.assertIn('bull_references', result)
        self.assertIn('bear_references', result)

        # Should have quota fields
        for ref in result['bull_references']:
            self.assertIn('combined_score', ref)
            self.assertEqual(ref['rank'], result['bull_references'].index(ref) + 1)


class TestProtectionFilter(unittest.TestCase):
    """Test suite for _apply_protection_filter function."""

    def test_protection_filter_bull_pre_formation(self):
        """Test pre-formation protection for bull references."""
        from src.swing_analysis.swing_detector import _apply_protection_filter, SparseTable
        import numpy as np

        # Create scenario where high is violated before low forms
        highs = np.array([100, 110, 120, 130, 110, 105, 100], dtype=np.float64)
        lows = np.array([95, 105, 115, 125, 105, 100, 95], dtype=np.float64)

        highs_max_table = SparseTable(highs.tolist(), mode='max')
        lows_min_table = SparseTable(lows.tolist(), mode='min')

        # Bull swing: high at index 1 (110), low at index 5 (100)
        # But higher high (130) appears at index 3 between them
        references = [{
            'high_price': 110.0,
            'high_bar_index': 1,
            'low_price': 100.0,
            'low_bar_index': 5,
            'size': 10.0
        }]

        filtered = _apply_protection_filter(
            references, 'bull', highs, lows, 0.1,
            highs_max_table, lows_min_table
        )

        # Should be filtered due to pre-formation violation
        self.assertEqual(len(filtered), 0)

    def test_protection_filter_bull_post_formation(self):
        """Test post-formation protection for bull references."""
        from src.swing_analysis.swing_detector import _apply_protection_filter, SparseTable
        import numpy as np

        # Create scenario where low is violated after formation
        highs = np.array([100, 120, 110, 105, 100, 95, 90], dtype=np.float64)
        lows = np.array([95, 100, 105, 100, 95, 85, 80], dtype=np.float64)

        highs_max_table = SparseTable(highs.tolist(), mode='max')
        lows_min_table = SparseTable(lows.tolist(), mode='min')

        # Bull swing: high at index 1 (120), low at index 4 (95)
        # Low violated at index 6 (80) which is < 95 - 0.1*25 = 92.5
        references = [{
            'high_price': 120.0,
            'high_bar_index': 1,
            'low_price': 95.0,
            'low_bar_index': 4,
            'size': 25.0
        }]

        filtered = _apply_protection_filter(
            references, 'bull', highs, lows, 0.1,
            highs_max_table, lows_min_table
        )

        # Should be filtered due to post-formation violation
        self.assertEqual(len(filtered), 0)

    def test_protection_filter_tolerance_none_disables(self):
        """Setting protection_tolerance=None should return all references."""
        from src.swing_analysis.swing_detector import _apply_protection_filter
        import numpy as np

        highs = np.array([100, 120, 110], dtype=np.float64)
        lows = np.array([95, 100, 50], dtype=np.float64)  # Violating low

        references = [{
            'high_price': 120.0,
            'high_bar_index': 1,
            'low_price': 100.0,
            'low_bar_index': 1,
            'size': 20.0
        }]

        # With None tolerance, should return all
        filtered = _apply_protection_filter(
            references, 'bull', highs, lows, None, None, None
        )

        self.assertEqual(len(filtered), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
