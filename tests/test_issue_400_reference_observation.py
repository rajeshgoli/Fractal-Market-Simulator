"""
Tests for Issue #400 - Reference Observation Mode

Tests the new get_all_with_status() method and FilterReason classification
for the Reference Observation UI.

Updated for #436: scale -> bin migration.
- FilteredLeg uses bin (0-10) instead of scale (S/M/L/XL)
- Check bin < 8 for small references (like S/M)
- Check bin >= 8 for significant references (like L/XL)
"""

import pytest
from decimal import Decimal
from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    FilterReason,
    FilteredLeg,
)
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.types import Bar


def make_bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    timestamp: int = 0,
) -> Bar:
    """Create a test bar."""
    return Bar(
        index=index,
        timestamp=timestamp or index * 60000,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def make_leg(
    direction: str,
    origin_price: float,
    origin_index: int,
    pivot_price: float,
    pivot_index: int,
) -> Leg:
    """Create a test leg."""
    return Leg(
        direction=direction,
        origin_price=Decimal(str(origin_price)),
        origin_index=origin_index,
        pivot_price=Decimal(str(pivot_price)),
        pivot_index=pivot_index,
    )


class TestFilterReasonEnum:
    """Test FilterReason enum values."""

    def test_filter_reasons_exist(self):
        """All expected filter reasons should exist."""
        assert FilterReason.VALID.value == "valid"
        assert FilterReason.COLD_START.value == "cold_start"
        assert FilterReason.NOT_FORMED.value == "not_formed"
        assert FilterReason.PIVOT_BREACHED.value == "pivot_breached"
        assert FilterReason.COMPLETED.value == "completed"
        assert FilterReason.ORIGIN_BREACHED.value == "origin_breached"


class TestFilteredLegDataclass:
    """Test FilteredLeg dataclass."""

    def test_filtered_leg_creation(self):
        """FilteredLeg should store all required fields."""
        leg = make_leg('bear', 110, 100, 100, 105)
        filtered = FilteredLeg(
            leg=leg,
            reason=FilterReason.NOT_FORMED,
            bin=8,  # Using bin instead of scale
            location=0.28,
            threshold=0.382,
        )
        assert filtered.leg == leg
        assert filtered.reason == FilterReason.NOT_FORMED
        assert filtered.bin == 8
        assert filtered.location == 0.28
        assert filtered.threshold == 0.382

    def test_filtered_leg_optional_threshold(self):
        """Threshold should be optional."""
        leg = make_leg('bear', 110, 100, 100, 105)
        filtered = FilteredLeg(
            leg=leg,
            reason=FilterReason.VALID,
            bin=9,  # Significant bin (like L)
            location=0.5,
        )
        assert filtered.threshold is None


def _populate_distribution(ref_layer: ReferenceLayer, count: int = 55):
    """
    Helper to populate the bin distribution to exit cold start.

    Creates dummy legs and directly adds them to the distribution to ensure
    we have enough formed legs for bin classification.
    """
    for i in range(count):
        # Add ranges directly to the bin distribution
        ref_layer._bin_distribution.add_leg(f"dummy_{i}", float(10 + i), 1000.0 + i)
        # Also track as seen
        ref_layer._seen_leg_ids.add(f"dummy_{i}")


class TestGetAllWithStatus:
    """Test ReferenceLayer.get_all_with_status() method."""

    def test_cold_start_classification(self):
        """All legs should get COLD_START when below min_swings_for_classification."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Create a leg
        leg = make_leg('bear', 110, 100, 100, 105)
        bar = make_bar(110, 105, 106, 104, 105)

        # Should be cold start (no formed legs yet in distribution)
        statuses = ref_layer.get_all_with_status([leg], bar)
        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.COLD_START

    def test_not_formed_classification(self):
        """Legs below formation threshold should get NOT_FORMED."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution to exit cold start
        _populate_distribution(ref_layer)

        # Create a leg where price hasn't reached 38.2%
        # Bear leg: origin=110, pivot=100, range=10
        # 38.2% retracement from pivot toward origin = 100 + 0.382*10 = 103.82
        leg = make_leg('bear', 110, 100, 100, 105)

        # Price at 102 (only 20% retracement, location = 0.2)
        bar = make_bar(110, 102, 103, 101, 102)

        statuses = ref_layer.get_all_with_status([leg], bar)
        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.NOT_FORMED
        assert statuses[0].threshold == config.formation_fib_threshold

    def test_pivot_breached_classification(self):
        """Legs with price past pivot should get PIVOT_BREACHED."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution
        _populate_distribution(ref_layer)

        # Bear leg: origin=110, pivot=100
        leg = make_leg('bear', 110, 100, 100, 105)

        # Form the leg by reaching 38.2%
        ref_layer._formed_refs[leg.leg_id] = leg.pivot_price

        # Now price drops below pivot (100) - bar low at 98
        # For bear leg/bull reference, pivot breach means bar.low < pivot
        breach_bar = make_bar(110, 99, 100, 98, 99)

        statuses = ref_layer.get_all_with_status([leg], breach_bar)
        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.PIVOT_BREACHED

    def test_completed_classification(self):
        """Legs past 2x extension should get COMPLETED."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution
        _populate_distribution(ref_layer)

        # Bear leg: origin=110, pivot=100, range=10
        # For bull reference: location > 2 means price > 120 (origin + range)
        # Need bar.low > 120 for extreme_location > 2
        leg = make_leg('bear', 110, 100, 100, 105)

        # Form the leg
        ref_layer._formed_refs[leg.leg_id] = leg.pivot_price

        # Price goes past 2x extension (bar low at 125 > 120)
        completion_bar = make_bar(110, 125, 130, 125, 127)

        statuses = ref_layer.get_all_with_status([leg], completion_bar)
        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.COMPLETED
        assert statuses[0].threshold == 2.0

    def test_origin_breached_small_bin(self):
        """Small bin refs (< 8) past origin should get ORIGIN_BREACHED."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate with small ranges (2-10) so our leg ends up with small bin
        for i in range(55):
            ref_layer._bin_distribution.add_leg(f"dummy_{i}", float(2 + i % 8), 1000.0 + i)
            ref_layer._seen_leg_ids.add(f"dummy_{i}")

        # Small bear leg: origin=102, pivot=100 (range=2)
        leg = make_leg('bear', 102, 100, 100, 105)

        # Form the leg
        ref_layer._formed_refs[leg.leg_id] = leg.pivot_price

        # For bear leg (bull reference), extreme_location uses bar.low
        # Origin breach needs extreme_location > 1.0
        # location = (bar.low - pivot) / (origin - pivot) = (bar.low - 100) / 2
        # To get location > 1.0: bar.low > 102
        # Bar with low > origin (103 > 102)
        breach_bar = make_bar(110, 104, 105, 103, 104)

        statuses = ref_layer.get_all_with_status([leg], breach_bar)
        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.ORIGIN_BREACHED
        # Should have small bin (< 8)
        assert statuses[0].bin < 8

    def test_valid_classification(self):
        """Legs passing all filters should get VALID."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution
        _populate_distribution(ref_layer)

        # Bear leg: origin=110, pivot=100
        leg = make_leg('bear', 110, 100, 100, 105)

        # Form the leg
        ref_layer._formed_refs[leg.leg_id] = leg.pivot_price

        # Price in valid zone (between pivot and origin)
        # Close at 105, high at 106 (below origin 110), low at 104 (above pivot 100)
        valid_bar = make_bar(110, 105, 106, 104, 105)

        statuses = ref_layer.get_all_with_status([leg], valid_bar)
        assert len(statuses) == 1
        assert statuses[0].reason == FilterReason.VALID
        assert statuses[0].threshold is None

    def test_multiple_legs_different_reasons(self):
        """Multiple legs should be classified independently."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution
        _populate_distribution(ref_layer)

        # Leg 1: formed and valid
        leg1 = make_leg('bear', 110, 50, 100, 55)
        ref_layer._formed_refs[leg1.leg_id] = leg1.pivot_price

        # Leg 2: not formed (hasn't reached 38.2%)
        leg2 = make_leg('bear', 120, 60, 110, 65)

        # Bar where leg1 is valid (close=105 in range), leg2 not formed
        bar = make_bar(110, 105, 106, 104, 105)

        statuses = ref_layer.get_all_with_status([leg1, leg2], bar)
        assert len(statuses) == 2

        # Find each leg's status
        leg1_status = next(s for s in statuses if s.leg == leg1)
        leg2_status = next(s for s in statuses if s.leg == leg2)

        assert leg1_status.reason == FilterReason.VALID
        assert leg2_status.reason == FilterReason.NOT_FORMED


class TestFilterStatsComputation:
    """Test filter statistics computation."""

    def test_stats_with_mixed_reasons(self):
        """Stats should correctly count each filter reason."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate to exit cold start
        _populate_distribution(ref_layer)

        # Create legs with different outcomes
        legs = []

        # Valid leg (formed)
        leg1 = make_leg('bear', 110, 50, 100, 55)
        ref_layer._formed_refs[leg1.leg_id] = leg1.pivot_price
        legs.append(leg1)

        # Not formed leg
        leg2 = make_leg('bear', 120, 60, 115, 65)
        legs.append(leg2)

        bar = make_bar(110, 105, 106, 104, 105)
        statuses = ref_layer.get_all_with_status(legs, bar)

        # Count each reason
        reason_counts = {}
        for s in statuses:
            reason = s.reason.value
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        assert reason_counts.get('valid', 0) == 1
        assert reason_counts.get('not_formed', 0) == 1


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_legs_list(self):
        """Empty legs list should return empty results."""
        ref_layer = ReferenceLayer()
        bar = make_bar(0, 100, 101, 99, 100)

        statuses = ref_layer.get_all_with_status([], bar)
        assert statuses == []

    def test_location_capped_at_2(self):
        """Location should be capped at 2.0 in output."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution
        _populate_distribution(ref_layer)

        # Bear leg with price way past completion
        leg = make_leg('bear', 110, 100, 100, 105)
        ref_layer._formed_refs[leg.leg_id] = leg.pivot_price

        # Price at 80 (way past 2x completion of 90)
        bar = make_bar(110, 80, 81, 79, 80)

        statuses = ref_layer.get_all_with_status([leg], bar)
        assert len(statuses) == 1
        # Location should be capped at 2.0
        assert statuses[0].location <= 2.0

    def test_bull_leg_classification(self):
        """Bull legs should be classified correctly."""
        config = ReferenceConfig.default()
        ref_layer = ReferenceLayer(reference_config=config)

        # Populate distribution
        _populate_distribution(ref_layer)

        # Bull leg: origin=90 (low), pivot=100 (high)
        # Bear reference: defended pivot is HIGH
        leg = make_leg('bull', 90, 100, 100, 105)

        # Form it
        ref_layer._formed_refs[leg.leg_id] = leg.pivot_price

        # Valid bar
        bar = make_bar(110, 95, 96, 94, 95)

        statuses = ref_layer.get_all_with_status([leg], bar)
        assert len(statuses) == 1
        assert statuses[0].leg.direction == 'bull'
