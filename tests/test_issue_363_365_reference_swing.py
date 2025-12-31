"""
Tests for ReferenceSwing dataclass (#363) and scale classification (#365).

Issue #363: ReferenceSwing dataclass that wraps a DAG Leg with reference-layer
specific annotations (scale, depth, location, salience_score).

Issue #365: Scale classification using percentile-based buckets:
- XL: Top 10% (≥ P90)
- L:  60-90% (P60-P90)
- M:  30-60% (P30-P60)
- S:  Bottom 30% (< P30)
"""

import pytest
from decimal import Decimal

from src.swing_analysis.reference_layer import ReferenceSwing, ReferenceLayer
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg


class TestReferenceSwingDataclass:
    """Tests for ReferenceSwing dataclass (#363)."""

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
            scale='L',
            depth=0,
            location=0.382,
            salience_score=0.75,
        )

        assert ref.leg is leg
        assert ref.scale == 'L'
        assert ref.depth == 0
        assert ref.location == 0.382
        assert ref.salience_score == 0.75

    def test_create_with_all_scales(self):
        """ReferenceSwing should accept all valid scale values."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=5,
        )

        for scale in ['S', 'M', 'L', 'XL']:
            ref = ReferenceSwing(
                leg=leg,
                scale=scale,
                depth=1,
                location=0.5,
                salience_score=0.5,
            )
            assert ref.scale == scale

    def test_location_not_auto_capped(self):
        """ReferenceSwing stores location as-is; capping is caller's responsibility."""
        # The spec says location is capped at 2.0 in output, but the dataclass
        # itself doesn't enforce this - it's done during creation
        leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=100,
            pivot_price=Decimal("100"),
            pivot_index=105,
        )

        ref = ReferenceSwing(
            leg=leg,
            scale='XL',
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
            scale='XL',
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
            scale='M',
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
            scale='L',
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
            scale='S',
            depth=3,
            location=1.5,
            salience_score=0.1,
        )
        assert ref_low.salience_score == 0.1

        # High salience
        ref_high = ReferenceSwing(
            leg=leg,
            scale='XL',
            depth=0,
            location=0.3,
            salience_score=0.95,
        )
        assert ref_high.salience_score == 0.95


class TestScaleClassificationPercentiles:
    """Tests for _classify_scale method (#365)."""

    def _create_layer_with_distribution(self, ranges: list) -> ReferenceLayer:
        """Create a ReferenceLayer with a pre-populated range distribution."""
        layer = ReferenceLayer(reference_config=ReferenceConfig.default())
        # Populate the sorted distribution
        for r in ranges:
            layer._add_to_range_distribution(Decimal(str(r)))
        return layer

    def test_xl_classification_top_10_percent(self):
        """XL should be top 10% (≥ P90)."""
        # 100 values: 1-100
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # Range 91 is at P90 (90 values below it)
        assert layer._classify_scale(Decimal("91")) == 'XL'
        # Range 95 is clearly in top 10%
        assert layer._classify_scale(Decimal("95")) == 'XL'
        # Range 100 is the largest
        assert layer._classify_scale(Decimal("100")) == 'XL'

    def test_l_classification_60_to_90_percent(self):
        """L should be 60-90% (P60-P90)."""
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # Range 61 is at P60 (60 values below it)
        assert layer._classify_scale(Decimal("61")) == 'L'
        # Range 70 is in the L range
        assert layer._classify_scale(Decimal("70")) == 'L'
        # Range 89 is just below XL threshold
        assert layer._classify_scale(Decimal("89")) == 'L'

    def test_m_classification_30_to_60_percent(self):
        """M should be 30-60% (P30-P60)."""
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # Range 31 is at P30 (30 values below it)
        assert layer._classify_scale(Decimal("31")) == 'M'
        # Range 45 is in the M range
        assert layer._classify_scale(Decimal("45")) == 'M'
        # Range 59 is just below L threshold
        assert layer._classify_scale(Decimal("59")) == 'M'

    def test_s_classification_bottom_30_percent(self):
        """S should be bottom 30% (< P30)."""
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # Range 1 is the smallest
        assert layer._classify_scale(Decimal("1")) == 'S'
        # Range 15 is in the S range
        assert layer._classify_scale(Decimal("15")) == 'S'
        # Range 29 is just below M threshold
        assert layer._classify_scale(Decimal("29")) == 'S'

    def test_boundary_at_90_percentile(self):
        """Value exactly at 90th percentile should be XL."""
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # 90 values below 91, so percentile = 90%
        assert layer._classify_scale(Decimal("91")) == 'XL'
        # 89 values below 90, so percentile = 89%
        assert layer._classify_scale(Decimal("90")) == 'L'

    def test_boundary_at_60_percentile(self):
        """Value exactly at 60th percentile should be L."""
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # 60 values below 61
        assert layer._classify_scale(Decimal("61")) == 'L'
        # 59 values below 60
        assert layer._classify_scale(Decimal("60")) == 'M'

    def test_boundary_at_30_percentile(self):
        """Value exactly at 30th percentile should be M."""
        layer = self._create_layer_with_distribution(list(range(1, 101)))

        # 30 values below 31
        assert layer._classify_scale(Decimal("31")) == 'M'
        # 29 values below 30
        assert layer._classify_scale(Decimal("30")) == 'S'

    def test_empty_distribution_returns_middle(self):
        """Empty distribution should return 50th percentile (M)."""
        layer = ReferenceLayer(reference_config=ReferenceConfig.default())
        # No distribution populated

        # With no data, percentile defaults to 50 (middle)
        # 50 < 60 (L threshold), so should be M
        assert layer._classify_scale(Decimal("100")) == 'M'

    def test_single_value_distribution(self):
        """Single value distribution edge case."""
        layer = self._create_layer_with_distribution([50])

        # Value smaller than the only entry: P0
        assert layer._classify_scale(Decimal("25")) == 'S'
        # Value equal to the only entry: P0 (bisect_left returns 0)
        assert layer._classify_scale(Decimal("50")) == 'S'
        # Value larger than the only entry: P100
        assert layer._classify_scale(Decimal("75")) == 'XL'

    def test_duplicate_values_in_distribution(self):
        """Distribution with duplicate values."""
        # 50 values of 10, 50 values of 100
        layer = self._create_layer_with_distribution([10] * 50 + [100] * 50)

        # 10 is at P0 (no values strictly less)
        assert layer._classify_scale(Decimal("10")) == 'S'
        # 50 has 50 values below it (all the 10s) = P50
        assert layer._classify_scale(Decimal("50")) == 'M'
        # 100 has 50 values below it = P50
        assert layer._classify_scale(Decimal("100")) == 'M'
        # 200 has all 100 values below it = P100
        assert layer._classify_scale(Decimal("200")) == 'XL'


class TestComputePercentile:
    """Tests for _compute_percentile method."""

    def test_percentile_empty_distribution(self):
        """Empty distribution returns 50% (middle)."""
        layer = ReferenceLayer()
        assert layer._compute_percentile(Decimal("100")) == 50.0

    def test_percentile_basic(self):
        """Basic percentile calculation."""
        layer = ReferenceLayer()
        for r in [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")]:
            layer._add_to_range_distribution(r)

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
        for r in [Decimal("10"), Decimal("30"), Decimal("50")]:
            layer._add_to_range_distribution(r)

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
        for r in [Decimal("50"), Decimal("10"), Decimal("90"), Decimal("30"), Decimal("70")]:
            layer._add_to_range_distribution(r)

        # Should be sorted
        expected = [Decimal("10"), Decimal("30"), Decimal("50"), Decimal("70"), Decimal("90")]
        assert layer._range_distribution == expected

    def test_handles_duplicates(self):
        """Distribution should handle duplicate values."""
        layer = ReferenceLayer()

        for _ in range(3):
            layer._add_to_range_distribution(Decimal("50"))

        assert len(layer._range_distribution) == 3
        assert all(r == Decimal("50") for r in layer._range_distribution)


class TestScaleClassificationWithCustomConfig:
    """Tests for scale classification with custom config thresholds."""

    def test_custom_xl_threshold(self):
        """Custom XL threshold should be respected."""
        config = ReferenceConfig.default().with_scale_thresholds(xl_threshold=0.95)
        layer = ReferenceLayer(reference_config=config)

        # Populate with 100 values
        for i in range(1, 101):
            layer._add_to_range_distribution(Decimal(str(i)))

        # With 95% threshold, only top 5% should be XL
        # P95 = 95 values below = range 96
        assert layer._classify_scale(Decimal("95")) == 'L'
        assert layer._classify_scale(Decimal("96")) == 'XL'

    def test_custom_all_thresholds(self):
        """All custom thresholds should work together."""
        config = ReferenceConfig(
            xl_threshold=0.80,  # Top 20%
            l_threshold=0.50,   # Top 50%
            m_threshold=0.20,   # Top 80%
        )
        layer = ReferenceLayer(reference_config=config)

        for i in range(1, 101):
            layer._add_to_range_distribution(Decimal(str(i)))

        # S: Bottom 20% (1-20)
        assert layer._classify_scale(Decimal("10")) == 'S'
        assert layer._classify_scale(Decimal("19")) == 'S'

        # M: 20-50% (21-50)
        assert layer._classify_scale(Decimal("21")) == 'M'
        assert layer._classify_scale(Decimal("49")) == 'M'

        # L: 50-80% (51-80)
        assert layer._classify_scale(Decimal("51")) == 'L'
        assert layer._classify_scale(Decimal("79")) == 'L'

        # XL: Top 20% (81-100)
        assert layer._classify_scale(Decimal("81")) == 'XL'
        assert layer._classify_scale(Decimal("100")) == 'XL'
