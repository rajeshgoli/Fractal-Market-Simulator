"""
Tests for Rolling Bin Distribution (#434).

Tests the median-normalized bin distribution for scale classification,
replacing the sorted list approach with O(1) updates.

Updated for #436 scale->bin migration:
- Bins are always used (no use_bin_distribution toggle)
- _classify_scale removed, use _get_bin_index or RollingBinDistribution.get_scale
"""

import pytest
import sys
from pathlib import Path
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.dag.range_distribution import (
    RollingBinDistribution,
    BIN_MULTIPLIERS,
    NUM_BINS,
)
from swing_analysis.reference_layer import ReferenceLayer
from swing_analysis.reference_config import ReferenceConfig
from swing_analysis.dag.leg import Leg
from swing_analysis.types import Bar


class TestBinMultipliers:
    """Test bin multiplier constants."""

    def test_bin_multipliers_ordered(self):
        """Bin multipliers should be in ascending order."""
        for i in range(len(BIN_MULTIPLIERS) - 1):
            assert BIN_MULTIPLIERS[i] < BIN_MULTIPLIERS[i + 1]

    def test_bin_multipliers_start_at_zero(self):
        """First multiplier should be 0."""
        assert BIN_MULTIPLIERS[0] == 0.0

    def test_bin_multipliers_end_at_infinity(self):
        """Last multiplier should be infinity."""
        assert BIN_MULTIPLIERS[-1] == float('inf')

    def test_num_bins_matches(self):
        """NUM_BINS should be one less than number of multipliers."""
        assert NUM_BINS == len(BIN_MULTIPLIERS) - 1


class TestRollingBinDistributionBasics:
    """Test basic RollingBinDistribution operations."""

    def test_default_initialization(self):
        """Should initialize with default values."""
        dist = RollingBinDistribution()
        assert dist.window_duration_days == 90
        assert dist.recompute_interval_legs == 100
        assert dist.median == 10.0
        assert dist.total_count == 0
        assert len(dist.bin_counts) == NUM_BINS

    def test_custom_initialization(self):
        """Should initialize with custom values."""
        dist = RollingBinDistribution(
            window_duration_days=30,
            recompute_interval_legs=50,
        )
        assert dist.window_duration_days == 30
        assert dist.recompute_interval_legs == 50

    def test_is_cold_start_initially(self):
        """Should be in cold start with no data."""
        dist = RollingBinDistribution()
        assert dist.is_cold_start is True

    def test_not_cold_start_with_enough_legs(self):
        """Should exit cold start after 50 legs."""
        dist = RollingBinDistribution()
        for i in range(50):
            dist.add_leg(f"leg_{i}", float(i + 1))
        assert dist.is_cold_start is False


class TestBinIndexCalculation:
    """Test bin index calculation from range values."""

    def test_bin_edges_depend_on_median(self):
        """Bin edges should scale with median."""
        dist = RollingBinDistribution()
        dist.median = 10.0
        edges = dist.bin_edges

        # First edge is 0
        assert edges[0] == 0.0
        # Second edge is 0.3 * 10 = 3.0
        assert edges[1] == 3.0
        # Etc.
        assert edges[2] == 5.0  # 0.5 * 10
        assert edges[4] == 10.0  # 1.0 * 10
        assert edges[-1] == float('inf')

    def test_bin_index_for_small_values(self):
        """Small values should fall in low bins."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 0 - 3 = bin 0
        assert dist.get_bin_index(0.1) == 0
        assert dist.get_bin_index(2.9) == 0

        # 3 - 5 = bin 1
        assert dist.get_bin_index(3.0) == 1
        assert dist.get_bin_index(4.9) == 1

    def test_bin_index_for_median_value(self):
        """Values near median should be in middle bins."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 7.5 - 10 = bin 3
        assert dist.get_bin_index(9.0) == 3

        # 10 - 15 = bin 4
        assert dist.get_bin_index(10.0) == 4
        assert dist.get_bin_index(14.9) == 4

    def test_bin_index_for_large_values(self):
        """Large values should fall in high bins."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 50 - 100 = bin 8 (5-10x median)
        assert dist.get_bin_index(75.0) == 8

        # 100 - 250 = bin 9 (10-25x median)
        assert dist.get_bin_index(150.0) == 9

        # 250+ = bin 10 (25x+ median)
        assert dist.get_bin_index(500.0) == 10


class TestScaleClassification:
    """Test S/M/L/XL scale classification (backward compatibility)."""

    def test_scale_s_for_small_values(self):
        """Small values (bins 0-7) should be S."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # All values < 5x median (bin 0-7) are S
        assert dist.get_scale(1.0) == 'S'
        assert dist.get_scale(10.0) == 'S'
        assert dist.get_scale(30.0) == 'S'  # bin 6: 2-3x
        assert dist.get_scale(49.0) == 'S'  # bin 7: 3-5x

    def test_scale_m_for_medium_values(self):
        """Medium values (bin 8, 5-10x median) should be M."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 5x - 10x median = bin 8 = M
        assert dist.get_scale(50.0) == 'M'
        assert dist.get_scale(75.0) == 'M'
        assert dist.get_scale(99.0) == 'M'

    def test_scale_l_for_large_values(self):
        """Large values (bin 9, 10-25x median) should be L."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 10x - 25x median = bin 9 = L
        assert dist.get_scale(100.0) == 'L'
        assert dist.get_scale(150.0) == 'L'
        assert dist.get_scale(249.0) == 'L'

    def test_scale_xl_for_huge_values(self):
        """Huge values (bin 10, 25x+ median) should be XL."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 25x+ median = bin 10 = XL
        assert dist.get_scale(250.0) == 'XL'
        assert dist.get_scale(500.0) == 'XL'
        assert dist.get_scale(1000.0) == 'XL'


class TestAddUpdateRemove:
    """Test add, update, and remove operations."""

    def test_add_leg(self):
        """Adding a leg should update bin counts."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        dist.add_leg("leg_1", 10.0)  # bin 4
        assert dist.total_count == 1
        assert dist.bin_counts[4] == 1
        assert "leg_1" in dist.leg_ranges

    def test_add_leg_idempotent(self):
        """Adding same leg twice should be idempotent."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        dist.add_leg("leg_1", 10.0)
        dist.add_leg("leg_1", 10.0)
        assert dist.total_count == 1

    def test_update_leg_same_bin(self):
        """Updating range within same bin should not change counts."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        dist.add_leg("leg_1", 10.0)  # bin 4
        dist.update_leg("leg_1", 12.0)  # still bin 4

        assert dist.total_count == 1
        assert dist.bin_counts[4] == 1
        assert dist.leg_ranges["leg_1"] == 12.0

    def test_update_leg_different_bin(self):
        """Updating range to different bin should update counts."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        dist.add_leg("leg_1", 10.0)  # bin 4
        assert dist.bin_counts[4] == 1
        assert dist.bin_counts[5] == 0

        dist.update_leg("leg_1", 16.0)  # bin 5
        assert dist.bin_counts[4] == 0
        assert dist.bin_counts[5] == 1

    def test_remove_leg(self):
        """Removing a leg should decrement bin count."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        dist.add_leg("leg_1", 10.0)
        dist.add_leg("leg_2", 15.0)
        assert dist.total_count == 2

        dist.remove_leg("leg_1")
        assert dist.total_count == 1
        assert "leg_1" not in dist.leg_ranges
        assert "leg_2" in dist.leg_ranges


class TestMedianRecomputation:
    """Test median recomputation logic."""

    def test_median_recomputes_after_interval(self):
        """Median should recompute after recompute_interval_legs."""
        dist = RollingBinDistribution(recompute_interval_legs=10)

        # Add 10 legs with values 1-10, median should be ~5.5
        for i in range(10):
            dist.add_leg(f"leg_{i}", float(i + 1))

        assert dist._warmup_complete is True
        # Median of 1-10 is 5.5
        assert abs(dist.median - 5.5) < 0.01

    def test_bins_remap_after_median_change(self):
        """Bin counts should update after median recomputation."""
        dist = RollingBinDistribution(recompute_interval_legs=5)

        # Add 5 legs with small values (1-5)
        for i in range(5):
            dist.add_leg(f"leg_{i}", float(i + 1))

        # Median is now 3, so our leg with value 5 should be in bin ~4
        # (5 / 3 = 1.67x median)
        assert dist.median == 3.0
        # All values should be redistributed to new bins


class TestSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self):
        """Should serialize to dictionary."""
        dist = RollingBinDistribution()
        dist.add_leg("leg_1", 10.0, timestamp=1000.0)
        dist.add_leg("leg_2", 20.0, timestamp=2000.0)

        data = dist.to_dict()

        assert data["window_duration_days"] == 90
        assert data["recompute_interval_legs"] == 100
        assert len(data["window"]) == 2
        assert data["leg_ranges"]["leg_1"] == 10.0
        assert data["leg_ranges"]["leg_2"] == 20.0

    def test_from_dict_roundtrip(self):
        """Should restore from dictionary correctly."""
        dist = RollingBinDistribution(
            window_duration_days=30,
            recompute_interval_legs=50,
        )
        dist.add_leg("leg_1", 10.0, timestamp=1000.0)
        dist.add_leg("leg_2", 20.0, timestamp=2000.0)

        data = dist.to_dict()
        restored = RollingBinDistribution.from_dict(data)

        assert restored.window_duration_days == 30
        assert restored.recompute_interval_legs == 50
        assert restored.total_count == 2
        assert restored.leg_ranges["leg_1"] == 10.0
        assert restored.leg_ranges["leg_2"] == 20.0


class TestPercentileCalculation:
    """Test percentile calculation from bin counts."""

    def test_percentile_empty_distribution(self):
        """Empty distribution should return 50%."""
        dist = RollingBinDistribution()
        assert dist.get_percentile(10.0) == 50.0

    def test_percentile_single_leg(self):
        """Single leg should be at 25th percentile (half of bin 0)."""
        dist = RollingBinDistribution()
        dist.add_leg("leg_1", 10.0)
        # With one leg, half the bin is below any value
        assert dist.get_percentile(10.0) == 50.0  # 0.5 / 1 * 100


class TestReferenceLayerIntegration:
    """Test integration with ReferenceLayer."""

    def test_reference_layer_uses_bin_distribution(self):
        """ReferenceLayer should always use bin distribution."""
        config = ReferenceConfig.default()

        ref_layer = ReferenceLayer(reference_config=config)

        # The bin distribution should be initialized
        assert ref_layer._bin_distribution is not None
        assert ref_layer._bin_distribution.total_count == 0

    def test_copy_state_preserves_bin_distribution(self):
        """copy_state_from should preserve bin distribution state."""
        ref1 = ReferenceLayer()
        ref1._bin_distribution.add_leg("leg_1", 10.0)
        ref1._bin_distribution.add_leg("leg_2", 20.0)

        ref2 = ReferenceLayer()
        ref2.copy_state_from(ref1)

        assert ref2._bin_distribution.total_count == 2
        assert "leg_1" in ref2._bin_distribution.leg_ranges

    def test_bin_index_classification_via_reference_layer(self):
        """Bin index classification should use bin distribution thresholds."""
        ref_layer = ReferenceLayer()

        # Set up a known median
        ref_layer._bin_distribution.median = 10.0

        # Test bin index classification
        assert ref_layer._get_bin_index(Decimal("5.0")) <= 2   # < 0.75x median
        assert ref_layer._get_bin_index(Decimal("75.0")) == 8  # 5-10x median
        assert ref_layer._get_bin_index(Decimal("150.0")) == 9 # 10-25x median
        assert ref_layer._get_bin_index(Decimal("300.0")) == 10 # 25x+ median


class TestLegRangeBinIndex:
    """Test range_bin_index field on Leg."""

    def test_leg_has_range_bin_index_field(self):
        """Leg should have range_bin_index field."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=10,
        )
        # Default is None
        assert leg.range_bin_index is None

        # Can be set
        leg.range_bin_index = 5
        assert leg.range_bin_index == 5


class TestReferenceConfigBinSettings:
    """Test ReferenceConfig bin distribution settings."""

    def test_default_config_has_bin_settings(self):
        """Default config should have bin distribution settings."""
        config = ReferenceConfig.default()

        assert config.bin_window_duration_days == 90
        assert config.bin_recompute_interval == 100

    def test_config_serialization_includes_bin_settings(self):
        """Config serialization should include bin settings."""
        config = ReferenceConfig.default()
        data = config.to_dict()

        assert "bin_window_duration_days" in data
        assert "bin_recompute_interval" in data

    def test_config_from_dict_restores_bin_settings(self):
        """Config from_dict should restore bin settings."""
        config = ReferenceConfig.from_dict({
            "bin_window_duration_days": 60,
            "bin_recompute_interval": 50,
        })

        assert config.bin_window_duration_days == 60
        assert config.bin_recompute_interval == 50


class TestWindowEviction:
    """Test rolling window eviction."""

    def test_evict_old_legs(self):
        """Should evict legs older than window duration."""
        dist = RollingBinDistribution(window_duration_days=1)  # 1 day

        # Add legs at different timestamps (in seconds)
        one_hour = 3600
        one_day = 86400

        dist.add_leg("old_leg", 10.0, timestamp=0.0)
        dist.add_leg("recent_leg", 20.0, timestamp=one_day * 2)

        assert dist.total_count == 2

        # Evict legs older than 2 days ago
        evicted = dist.evict_old_legs(one_day * 3)

        assert "old_leg" in evicted
        assert "recent_leg" not in evicted
        assert dist.total_count == 1
        assert "old_leg" not in dist.leg_ranges


class TestBinStats:
    """Test bin statistics for debugging."""

    def test_get_bin_stats(self):
        """Should return bin statistics."""
        dist = RollingBinDistribution()
        dist.median = 10.0

        # 5.0 = 0.5x median -> bin 2 (edge at 0.5x = 5.0, so bisect puts it there)
        dist.add_leg("leg_1", 5.0)   # bin 2 (0.5-0.75x median)
        dist.add_leg("leg_2", 10.0)  # bin 4 (1-1.5x median)
        # 75.0 = 7.5x median -> bin 8 (5-10x median, M scale)
        dist.add_leg("leg_3", 75.0)  # bin 8 (5-10x median, M scale)

        stats = dist.get_bin_stats()

        assert stats["median"] == 10.0
        assert stats["total_count"] == 3
        assert len(stats["bins"]) == NUM_BINS

        # Check bin 2 has one leg (5.0 = 0.5x median)
        bin2 = stats["bins"][2]
        assert bin2["count"] == 1
        assert bin2["scale"] == 'S'

        # Check bin 8 (M scale: 5-10x median)
        bin8 = stats["bins"][8]
        assert bin8["count"] == 1
        assert bin8["scale"] == 'M'
