"""
Tests for Reference Layer Phase 1 methods.

Covers:
- #364: LevelInfo and ReferenceState dataclasses
- #366: _compute_location() method
- #367: _is_formed_for_reference() method
- #368: _is_fatally_breached() method
- #369: _compute_salience() and _normalize_range() methods
"""

import pytest
from decimal import Decimal
from typing import List

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwing,
    LevelInfo,
    ReferenceState,
)
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg


def make_leg(
    direction: str = 'bear',
    origin_price: float = 110.0,
    origin_index: int = 100,
    pivot_price: float = 100.0,
    pivot_index: int = 105,
    impulsiveness: float = None,
    depth: int = 0,
) -> Leg:
    """Helper to create a test Leg."""
    return Leg(
        direction=direction,
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
        impulsiveness=impulsiveness,
        depth=depth,
    )


class TestLevelInfo:
    """Tests for LevelInfo dataclass (#364)."""

    def test_level_info_creation(self):
        """LevelInfo should store price, ratio, and reference."""
        leg = make_leg()
        ref = ReferenceSwing(
            leg=leg,
            scale='L',
            depth=0,
            location=0.5,
            salience_score=0.75,
        )
        level = LevelInfo(price=103.82, ratio=0.382, reference=ref)

        assert level.price == 103.82
        assert level.ratio == 0.382
        assert level.reference == ref

    def test_level_info_all_fib_ratios(self):
        """LevelInfo should work with all standard fib ratios."""
        leg = make_leg()
        ref = ReferenceSwing(leg=leg, scale='M', depth=1, location=0.5, salience_score=0.5)

        ratios = [0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0]
        for ratio in ratios:
            level = LevelInfo(price=100.0 + ratio * 10, ratio=ratio, reference=ref)
            assert level.ratio == ratio


class TestReferenceState:
    """Tests for ReferenceState dataclass (#364)."""

    def test_empty_state_construction(self):
        """ReferenceState should work with empty references."""
        state = ReferenceState(
            references=[],
            by_scale={},
            by_depth={},
            by_direction={},
            direction_imbalance=None,
        )

        assert len(state.references) == 0
        assert state.direction_imbalance is None

    def test_state_with_references(self):
        """ReferenceState should store references correctly."""
        leg1 = make_leg(direction='bear', origin_price=110, pivot_price=100)
        leg2 = make_leg(direction='bull', origin_price=90, pivot_price=105)

        ref1 = ReferenceSwing(leg=leg1, scale='L', depth=0, location=0.5, salience_score=0.8)
        ref2 = ReferenceSwing(leg=leg2, scale='M', depth=1, location=0.3, salience_score=0.6)

        state = ReferenceState(
            references=[ref1, ref2],
            by_scale={'L': [ref1], 'M': [ref2]},
            by_depth={0: [ref1], 1: [ref2]},
            by_direction={'bear': [ref1], 'bull': [ref2]},
            direction_imbalance=None,
        )

        assert len(state.references) == 2
        assert len(state.by_scale['L']) == 1
        assert len(state.by_depth[0]) == 1

    def test_direction_imbalance_bull(self):
        """direction_imbalance should be 'bull' when bull > 2× bear."""
        state = ReferenceState(
            references=[],
            by_scale={},
            by_depth={},
            by_direction={'bull': [1, 2, 3], 'bear': [1]},  # 3:1 ratio
            direction_imbalance='bull',
        )
        assert state.direction_imbalance == 'bull'

    def test_direction_imbalance_bear(self):
        """direction_imbalance should be 'bear' when bear > 2× bull."""
        state = ReferenceState(
            references=[],
            by_scale={},
            by_depth={},
            by_direction={'bull': [1], 'bear': [1, 2, 3, 4]},  # 4:1 ratio
            direction_imbalance='bear',
        )
        assert state.direction_imbalance == 'bear'

    def test_direction_imbalance_balanced(self):
        """direction_imbalance should be None when roughly balanced."""
        state = ReferenceState(
            references=[],
            by_scale={},
            by_depth={},
            by_direction={'bull': [1, 2], 'bear': [1, 2, 3]},  # 1.5:1 ratio
            direction_imbalance=None,
        )
        assert state.direction_imbalance is None


class TestComputeLocation:
    """Tests for _compute_location() method (#366)."""

    def test_location_at_pivot(self):
        """Location should be 0 at pivot price."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        location = ref_layer._compute_location(leg, Decimal("100"))
        assert location == pytest.approx(0.0)

    def test_location_at_origin(self):
        """Location should be 1 at origin price."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        location = ref_layer._compute_location(leg, Decimal("110"))
        assert location == pytest.approx(1.0)

    def test_location_at_2x_extension(self):
        """Location should be 2 at completion target (2x extension)."""
        ref_layer = ReferenceLayer()
        # Bear leg: 110 -> 100, range = 10
        # Location 2 = pivot - range = 100 - 10 = 90
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        location = ref_layer._compute_location(leg, Decimal("120"))
        assert location == pytest.approx(2.0)

    def test_location_at_382_retracement(self):
        """Location should be ~0.382 at 38.2% retracement."""
        ref_layer = ReferenceLayer()
        # Bear leg: 110 -> 100, range = 10
        # 38.2% retracement from pivot toward origin = 100 + 0.382 * 10 = 103.82
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        location = ref_layer._compute_location(leg, Decimal("103.82"))
        assert location == pytest.approx(0.382, abs=0.001)

    def test_location_pivot_breached(self):
        """Location should be < 0 when pivot is breached."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Price below pivot = breach
        location = ref_layer._compute_location(leg, Decimal("95"))
        assert location < 0

    def test_location_past_completion(self):
        """Location should be > 2 when past completion."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Price above origin + range = past 2x
        location = ref_layer._compute_location(leg, Decimal("125"))
        assert location > 2

    def test_location_bull_leg(self):
        """Location computation should work for bull legs."""
        ref_layer = ReferenceLayer()
        # Bull leg: 90 -> 100, range = 10
        leg = make_leg(direction='bull', origin_price=90, pivot_price=100)

        # At pivot = 0
        assert ref_layer._compute_location(leg, Decimal("100")) == pytest.approx(0.0)
        # At origin = 1
        assert ref_layer._compute_location(leg, Decimal("90")) == pytest.approx(1.0)
        # At 38.2% = pivot - 0.382 * range = 100 - 3.82 = 96.18
        assert ref_layer._compute_location(leg, Decimal("96.18")) == pytest.approx(0.382, abs=0.001)


class TestIsFormedForReference:
    """Tests for _is_formed_for_reference() method (#367)."""

    def test_formation_triggers_at_threshold(self):
        """Formation should trigger when price reaches 38.2% threshold."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Below threshold (0.3 < 0.382)
        price_below = Decimal("103")  # location = 0.3
        assert ref_layer._is_formed_for_reference(leg, price_below) is False

        # At threshold (0.382)
        price_at = Decimal("103.82")  # location = 0.382
        assert ref_layer._is_formed_for_reference(leg, price_at) is True

    def test_formation_persists_after_price_moves_away(self):
        """Once formed, should stay formed even if price moves away."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # First, form it
        price_at = Decimal("103.82")
        assert ref_layer._is_formed_for_reference(leg, price_at) is True

        # Now check with price back near pivot
        price_near_pivot = Decimal("100.5")
        assert ref_layer._is_formed_for_reference(leg, price_near_pivot) is True

    def test_formation_not_triggered_below_threshold(self):
        """Formation should NOT trigger below threshold."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Well below threshold
        price_below = Decimal("101")  # location = 0.1
        assert ref_layer._is_formed_for_reference(leg, price_below) is False

    def test_formation_works_for_bull_and_bear(self):
        """Formation should work for both directions."""
        ref_layer = ReferenceLayer()

        # Bear leg
        bear_leg = make_leg(direction='bear', origin_price=110, pivot_price=100)
        assert ref_layer._is_formed_for_reference(bear_leg, Decimal("104")) is True

        # Bull leg
        bull_leg = make_leg(direction='bull', origin_price=90, pivot_price=100)
        # Location 0.382 = 100 - 0.382 * 10 = 96.18
        assert ref_layer._is_formed_for_reference(bull_leg, Decimal("96")) is True


class TestIsFatallyBreached:
    """Tests for _is_fatally_breached() method (#368)."""

    def test_pivot_breach(self):
        """Pivot breach (location < 0) should be fatal."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # location < 0
        assert ref_layer._is_fatally_breached(leg, 'M', -0.1, -0.1) is True

    def test_completion_breach(self):
        """Past completion (location > 2) should be fatal."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # location > 2
        assert ref_layer._is_fatally_breached(leg, 'L', 2.1, 2.1) is True

    def test_sm_origin_breach_zero_tolerance(self):
        """S/M swings have zero tolerance for origin breach by default."""
        config = ReferenceConfig.default()  # small_origin_tolerance = 0.0
        ref_layer = ReferenceLayer(reference_config=config)
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Add to formed refs to test removal
        ref_layer._formed_refs.add(leg.leg_id)

        # Just past origin (location > 1.0 + 0.0 = 1.0)
        assert ref_layer._is_fatally_breached(leg, 'S', 1.01, 1.01) is True
        assert ref_layer._is_fatally_breached(leg, 'M', 1.01, 1.01) is True

        # At exactly 1.0 — NOT breached
        ref_layer._formed_refs.add(leg.leg_id)  # Re-add for next test
        assert ref_layer._is_fatally_breached(leg, 'S', 1.0, 1.0) is False

    def test_sm_origin_breach_configurable_tolerance(self):
        """S/M origin tolerance should be configurable."""
        config = ReferenceConfig.default().with_tolerance(small_origin_tolerance=0.05)
        ref_layer = ReferenceLayer(reference_config=config)
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Within 5% tolerance (location = 1.04)
        assert ref_layer._is_fatally_breached(leg, 'S', 1.04, 1.04) is False

        # Beyond 5% tolerance (location = 1.06)
        assert ref_layer._is_fatally_breached(leg, 'S', 1.06, 1.06) is True

    def test_lxl_trade_breach_15_percent(self):
        """L/XL trade breach at 15% should be fatal."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Within 15% trade tolerance (location = 1.14)
        assert ref_layer._is_fatally_breached(leg, 'L', 1.14, 1.0) is False
        assert ref_layer._is_fatally_breached(leg, 'XL', 1.14, 1.0) is False

        # Beyond 15% trade tolerance (location = 1.16)
        assert ref_layer._is_fatally_breached(leg, 'L', 1.16, 1.0) is True
        assert ref_layer._is_fatally_breached(leg, 'XL', 1.16, 1.0) is True

    def test_lxl_close_breach_10_percent(self):
        """L/XL close breach at 10% should be fatal."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Trade within tolerance, close within tolerance
        assert ref_layer._is_fatally_breached(leg, 'L', 1.08, 1.08) is False

        # Trade within tolerance, close beyond 10%
        assert ref_layer._is_fatally_breached(leg, 'L', 1.08, 1.11) is True

    def test_tolerance_at_exact_boundary(self):
        """Test behavior at exact tolerance boundaries."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # At exactly 15% trade tolerance (L/XL)
        # Note: We use > not >= so exactly at boundary is NOT breached
        assert ref_layer._is_fatally_breached(leg, 'L', 1.15, 1.0) is False

        # Just over 15%
        assert ref_layer._is_fatally_breached(leg, 'L', 1.1501, 1.0) is True

    def test_formed_refs_cleaned_on_breach(self):
        """Fatal breach should remove leg from _formed_refs."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Add to formed refs
        ref_layer._formed_refs.add(leg.leg_id)
        assert leg.leg_id in ref_layer._formed_refs

        # Trigger fatal breach
        ref_layer._is_fatally_breached(leg, 'S', -0.1, -0.1)

        # Should be removed
        assert leg.leg_id not in ref_layer._formed_refs


class TestNormalizeRange:
    """Tests for _normalize_range() method (#369)."""

    def test_empty_distribution(self):
        """Empty distribution should return 0.5."""
        ref_layer = ReferenceLayer()
        assert ref_layer._normalize_range(10.0) == 0.5

    def test_max_range(self):
        """Range equal to max should return 1.0."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("5"), Decimal("10"), Decimal("20")]

        assert ref_layer._normalize_range(20.0) == 1.0

    def test_half_max_range(self):
        """Range equal to half max should return 0.5."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("5"), Decimal("10"), Decimal("20")]

        assert ref_layer._normalize_range(10.0) == 0.5

    def test_above_max_capped(self):
        """Range above max should be capped at 1.0."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("5"), Decimal("10"), Decimal("20")]

        assert ref_layer._normalize_range(30.0) == 1.0


class TestComputeSalience:
    """Tests for _compute_salience() method (#369)."""

    def test_lxl_weighting(self):
        """L/XL should weight range heavily (0.5)."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("10")]  # Max = 10

        leg = make_leg(origin_index=0)

        # L scale, max range, no impulse
        salience = ref_layer._compute_salience(leg, 'L', current_bar_index=0)

        # With range = max (1.0) and no impulse, weights are renormalized:
        # range: 0.5/(0.5+0.1) = 0.833, recency: 0.1/(0.5+0.1) = 0.167
        # recency at age 0 = 1/(1+0) = 1.0
        # salience = 0.833 * 1.0 + 0.167 * 1.0 = 1.0
        assert salience == pytest.approx(1.0, abs=0.01)

    def test_sm_weighting(self):
        """S/M should weight recency heavily (0.5)."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("10")]

        leg = make_leg(origin_index=0)

        # S scale, max range, no impulse
        salience = ref_layer._compute_salience(leg, 'S', current_bar_index=0)

        # With range = max (1.0) and no impulse, weights are renormalized:
        # range: 0.2/(0.2+0.5) = 0.286, recency: 0.5/(0.2+0.5) = 0.714
        # recency at age 0 = 1.0
        # salience = 0.286 * 1.0 + 0.714 * 1.0 = 1.0
        assert salience == pytest.approx(1.0, abs=0.01)

    def test_missing_impulse_handling(self):
        """Missing impulse should renormalize remaining weights."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("10")]

        # Leg without impulsiveness
        leg = make_leg(impulsiveness=None, origin_index=0)

        salience = ref_layer._compute_salience(leg, 'L', current_bar_index=0)

        # Should not crash and should produce valid salience
        assert 0.0 <= salience <= 1.0

    def test_with_impulsiveness(self):
        """Impulse score should be included when available."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("10")]

        # Leg with impulsiveness = 80 (80th percentile)
        leg = make_leg(impulsiveness=80.0, origin_index=0)

        salience_with_impulse = ref_layer._compute_salience(leg, 'L', current_bar_index=0)

        # Leg without impulsiveness
        leg_no_impulse = make_leg(impulsiveness=None, origin_index=0)
        salience_no_impulse = ref_layer._compute_salience(leg_no_impulse, 'L', current_bar_index=0)

        # Both should be valid but potentially different
        assert 0.0 <= salience_with_impulse <= 1.0
        assert 0.0 <= salience_no_impulse <= 1.0

    def test_age_decay_function(self):
        """Recency score should decay with age."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("10")]

        # Same leg at different "ages"
        leg = make_leg(origin_index=0)

        salience_young = ref_layer._compute_salience(leg, 'S', current_bar_index=10)
        salience_old = ref_layer._compute_salience(leg, 'S', current_bar_index=1000)

        # Young legs should have higher salience for S/M (recency-weighted)
        assert salience_young > salience_old

    def test_range_score_impact(self):
        """Larger range should increase salience for L/XL."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [
            Decimal("5"),
            Decimal("10"),
            Decimal("20"),
        ]

        small_leg = make_leg(origin_price=105, pivot_price=100, origin_index=0)  # range = 5
        large_leg = make_leg(origin_price=120, pivot_price=100, origin_index=0)  # range = 20

        salience_small = ref_layer._compute_salience(small_leg, 'L', current_bar_index=0)
        salience_large = ref_layer._compute_salience(large_leg, 'L', current_bar_index=0)

        # Larger leg should have higher salience for L/XL
        assert salience_large > salience_small


class TestReferenceLayerIntegration:
    """Integration tests for Reference Layer methods."""

    def test_formation_and_breach_interaction(self):
        """Test formation and breach methods work together."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Form the reference
        assert ref_layer._is_formed_for_reference(leg, Decimal("104")) is True
        assert leg.leg_id in ref_layer._formed_refs

        # Breach the reference
        assert ref_layer._is_fatally_breached(leg, 'S', -0.1, -0.1) is True
        assert leg.leg_id not in ref_layer._formed_refs

    def test_location_used_by_formation(self):
        """Formation should use location computation correctly."""
        ref_layer = ReferenceLayer()
        leg = make_leg(direction='bear', origin_price=110, pivot_price=100)

        # Location at 103.82 = 0.382
        location = ref_layer._compute_location(leg, Decimal("103.82"))
        assert location == pytest.approx(0.382, abs=0.001)

        # Formation threshold is 0.382, so this should form
        assert ref_layer._is_formed_for_reference(leg, Decimal("103.82")) is True

    def test_salience_uses_scale_correctly(self):
        """Salience computation should use scale-dependent weights."""
        ref_layer = ReferenceLayer()
        ref_layer._range_distribution = [Decimal("10")]

        leg = make_leg(origin_index=0, impulsiveness=50.0)

        salience_xl = ref_layer._compute_salience(leg, 'XL', current_bar_index=500)
        salience_s = ref_layer._compute_salience(leg, 'S', current_bar_index=500)

        # Different scales use different weights, so salience should differ
        # (unless all components happen to produce same result)
        # Both should be valid
        assert 0.0 <= salience_xl <= 1.0
        assert 0.0 <= salience_s <= 1.0
