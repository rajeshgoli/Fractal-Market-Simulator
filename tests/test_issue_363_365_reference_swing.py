"""
Tests for ReferenceSwing dataclass (#363) and bin classification (#436).

Issue #363: ReferenceSwing dataclass that wraps a DAG Leg with reference-layer
specific annotations (bin, depth, location, salience_score).

Issue #436: Bin classification using median-normalized bins:
- Bins 0-7: < 5× median (small)
- Bin 8: 5-10× median (significant)
- Bin 9: 10-25× median (large)
- Bin 10: 25×+ median (exceptional)
"""

import pytest
from decimal import Decimal

from src.swing_analysis.reference_layer import ReferenceSwing, ReferenceLayer
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg


class TestReferenceSwingDataclass:
    """Tests for ReferenceSwing dataclass (#363, updated for #436)."""

    def test_create_with_valid_values(self):
        """ReferenceSwing should accept all valid field values."""
        leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=100,
            pivot_price=Decimal("100"),
            pivot_index=105,
        )

        ref = ReferenceSwing(
            leg=leg,
            bin=9,  # Large bin (10-25× median)
            depth=0,
            location=0.382,
            salience_score=0.75,
        )

        assert ref.leg is leg
        assert ref.bin == 9
        assert ref.depth == 0
        assert ref.location == 0.382
        assert ref.salience_score == 0.75

    def test_create_with_all_bins(self):
        """ReferenceSwing should accept all valid bin values (0-10)."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=5,
        )

        for bin_idx in range(11):  # 0-10
            ref = ReferenceSwing(
                leg=leg,
                bin=bin_idx,
                depth=1,
                location=0.5,
                salience_score=0.5,
            )
            assert ref.bin == bin_idx

    def test_location_not_auto_capped(self):
        """ReferenceSwing stores location as-is; capping is caller's responsibility."""
        leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=100,
            pivot_price=Decimal("100"),
            pivot_index=105,
        )

        ref = ReferenceSwing(
            leg=leg,
            bin=10,  # Exceptional bin
            depth=0,
            location=2.5,  # Caller passed uncapped value
            salience_score=0.9,
        )

        # Dataclass stores what it's given
        assert ref.location == 2.5

    def test_location_capped_value(self):
        """Caller should cap location at 2.0 per spec."""
        leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=100,
            pivot_price=Decimal("100"),
            pivot_index=105,
        )

        # Proper usage: cap at 2.0 when creating
        raw_location = 2.5
        ref = ReferenceSwing(
            leg=leg,
            bin=10,
            depth=0,
            location=min(raw_location, 2.0),  # Cap as spec requires
            salience_score=0.9,
        )

        assert ref.location == 2.0

    def test_depth_from_leg(self):
        """Depth should match the leg's depth field."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("115"),
            pivot_index=10,
            depth=2,
        )

        ref = ReferenceSwing(
            leg=leg,
            bin=8,  # Significant bin
            depth=leg.depth,  # Copy from leg
            location=0.5,
            salience_score=0.6,
        )

        assert ref.depth == 2

    def test_leg_reference_not_copy(self):
        """ReferenceSwing should hold reference to leg, not a copy."""
        leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=100,
            pivot_price=Decimal("100"),
            pivot_index=105,
        )

        ref = ReferenceSwing(
            leg=leg,
            bin=9,
            depth=0,
            location=0.5,
            salience_score=0.7,
        )

        # Modify the original leg
        leg.update_pivot(Decimal("95"), 110)

        # Reference should see the change (same object)
        assert ref.leg.pivot_price == Decimal("95")

    def test_salience_score_range(self):
        """Salience score can be any float (typically 0-1)."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=5,
        )

        # Low salience
        ref_low = ReferenceSwing(
            leg=leg,
            bin=3,  # Small bin
            depth=3,
            location=1.5,
            salience_score=0.1,
        )
        assert ref_low.salience_score == 0.1

        # High salience
        ref_high = ReferenceSwing(
            leg=leg,
            bin=10,  # Exceptional bin
            depth=0,
            location=0.3,
            salience_score=0.95,
        )
        assert ref_high.salience_score == 0.95


class TestBinClassification:
    """Tests for _get_bin_index method (#436).

    Bin classification uses median-normalized bins from RollingBinDistribution.
    """

    def _create_layer_with_ranges(self, ranges: list) -> ReferenceLayer:
        """Create a ReferenceLayer with a pre-populated range distribution."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)
        # Populate the distribution with leg IDs
        for i, r in enumerate(ranges):
            layer._add_to_range_distribution(Decimal(str(r)), leg_id=f"leg_{i}")
        return layer

    def test_bin_index_with_median_normalization(self):
        """Bin classification should be based on median multiple."""
        # Create a distribution where median is around 10
        layer = self._create_layer_with_ranges([5, 8, 10, 12, 15])

        # Verify the bin distribution has data
        assert layer._bin_distribution.total_count > 0

    def test_small_leg_gets_low_bin(self):
        """A leg with range < median should get a low bin (0-3)."""
        # Create a distribution
        ranges = [10, 20, 30, 40, 50]  # Median is 30
        layer = self._create_layer_with_ranges(ranges)

        # A very small range should get a low bin
        bin_idx = layer._get_bin_index(Decimal("5"))  # 5/30 ≈ 0.17× median
        assert bin_idx < 4  # Should be in bins 0-3

    def test_large_leg_gets_high_bin(self):
        """A leg with range >> median should get a high bin (8+)."""
        # Create a distribution where median is around 10
        ranges = [5, 8, 10, 12, 15]
        layer = self._create_layer_with_ranges(ranges)

        # A range 5× median should get bin 8+
        median = layer._bin_distribution.median
        large_range = median * 6  # 6× median
        bin_idx = layer._get_bin_index(Decimal(str(large_range)))
        assert bin_idx >= 8


class TestComputePercentile:
    """Tests for _compute_percentile method."""

    def test_percentile_empty_distribution(self):
        """Empty distribution returns 50% (middle)."""
        layer = ReferenceLayer()
        assert layer._compute_percentile(Decimal("100")) == 50.0

    def test_percentile_basic(self):
        """Basic percentile calculation."""
        layer = ReferenceLayer()
        for i, r in enumerate([Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")]):
            layer._add_to_range_distribution(r, leg_id=f"leg_{i}")

        # 0 values below 10
        assert layer._compute_percentile(Decimal("10")) == 0.0
        # 1 value below 20
        assert layer._compute_percentile(Decimal("20")) == 25.0
        # 2 values below 30
        assert layer._compute_percentile(Decimal("30")) == 50.0
        # 3 values below 40
        assert layer._compute_percentile(Decimal("40")) == 75.0
        # 4 values below 100
        assert layer._compute_percentile(Decimal("100")) == 100.0

    def test_percentile_value_not_in_distribution(self):
        """Percentile for value between existing entries."""
        layer = ReferenceLayer()
        for i, r in enumerate([Decimal("10"), Decimal("30"), Decimal("50")]):
            layer._add_to_range_distribution(r, leg_id=f"leg_{i}")

        # 20 is between 10 and 30: 1 value below it
        assert layer._compute_percentile(Decimal("20")) == pytest.approx(33.33, rel=0.01)
        # 40 is between 30 and 50: 2 values below it
        assert layer._compute_percentile(Decimal("40")) == pytest.approx(66.67, rel=0.01)


class TestAddToRangeDistribution:
    """Tests for _add_to_range_distribution method."""

    def test_maintains_sorted_order(self):
        """Distribution should remain sorted after insertions."""
        layer = ReferenceLayer()

        # Add in random order
        for i, r in enumerate([Decimal("50"), Decimal("10"), Decimal("90"), Decimal("30"), Decimal("70")]):
            layer._add_to_range_distribution(r, leg_id=f"leg_{i}")

        # Should be sorted
        expected = [Decimal("10"), Decimal("30"), Decimal("50"), Decimal("70"), Decimal("90")]
        assert layer._range_distribution == expected

    def test_handles_duplicates(self):
        """Distribution should handle duplicate values."""
        layer = ReferenceLayer()

        for i in range(3):
            layer._add_to_range_distribution(Decimal("50"), leg_id=f"leg_{i}")

        assert len(layer._range_distribution) == 3
        assert all(r == Decimal("50") for r in layer._range_distribution)


class TestSignificantBinThreshold:
    """Tests for significant_bin_threshold configuration (#436)."""

    def test_default_threshold_is_8(self):
        """Default significant bin threshold should be 8."""
        config = ReferenceConfig.default()
        assert config.significant_bin_threshold == 8

    def test_custom_threshold(self):
        """Custom significant bin threshold should be respected."""
        config = ReferenceConfig.from_dict({"significant_bin_threshold": 9})
        assert config.significant_bin_threshold == 9
