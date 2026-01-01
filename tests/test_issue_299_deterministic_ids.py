"""
Tests for deterministic leg and swing IDs (#299).

Verifies that:
1. Leg IDs are deterministic based on (direction, origin_price, origin_index)
2. Swing IDs are deterministic (derived from leg)
3. After reset (fresh detector), same bars produce same IDs
"""

from decimal import Decimal
import pytest

from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.leg_detector import LegDetector
from src.swing_analysis.types import Bar


class TestLegDeterministicId:
    """Test deterministic leg ID generation."""

    def test_leg_id_format(self):
        """Leg ID has format leg_{direction}_{origin_price}_{origin_index}."""
        leg = Leg(
            direction="bull",
            origin_price=Decimal("4425.50"),
            origin_index=1234,
            pivot_price=Decimal("4430.00"),
            pivot_index=1240,
        )
        assert leg.leg_id == "leg_bull_4425.50_1234"

    def test_bear_leg_id_format(self):
        """Bear leg ID also deterministic."""
        leg = Leg(
            direction="bear",
            origin_price=Decimal("4450.00"),
            origin_index=5000,
            pivot_price=Decimal("4440.00"),
            pivot_index=5010,
        )
        assert leg.leg_id == "leg_bear_4450.00_5000"

    def test_same_properties_same_id(self):
        """Two legs with same properties have same ID."""
        leg1 = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
        )
        leg2 = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("120.00"),  # Different pivot
            pivot_index=20,  # Different pivot index
        )
        # Same origin properties = same ID
        assert leg1.leg_id == leg2.leg_id

    def test_different_direction_different_id(self):
        """Different direction = different ID."""
        leg1 = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
        )
        leg2 = Leg(
            direction="bear",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("90.00"),
            pivot_index=15,
        )
        assert leg1.leg_id != leg2.leg_id

    def test_different_origin_price_different_id(self):
        """Different origin price = different ID."""
        leg1 = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
        )
        leg2 = Leg(
            direction="bull",
            origin_price=Decimal("100.25"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
        )
        assert leg1.leg_id != leg2.leg_id

    def test_different_origin_index_different_id(self):
        """Different origin index = different ID."""
        leg1 = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
        )
        leg2 = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=11,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
        )
        assert leg1.leg_id != leg2.leg_id


class TestDetectorIdDeterminism:
    """Test that detector produces deterministic IDs across resets."""

    def _create_bars(self):
        """Create test bars that form a swing."""
        # Bar 0: Initial bar
        # Bar 1: Lower low (establishes bull origin)
        # Bar 2+: Higher prices with retracement
        base_ts = 1704103800  # 2024-01-01 09:30:00 UTC
        bars = [
            Bar(index=0, timestamp=base_ts,
                open=100.0, high=102.0, low=99.0, close=101.0),
            Bar(index=1, timestamp=base_ts + 60,
                open=101.0, high=103.0, low=98.0, close=102.0),
            Bar(index=2, timestamp=base_ts + 120,
                open=102.0, high=108.0, low=101.0, close=107.0),
            Bar(index=3, timestamp=base_ts + 180,
                open=107.0, high=112.0, low=106.0, close=111.0),
            Bar(index=4, timestamp=base_ts + 240,
                open=111.0, high=115.0, low=109.0, close=114.0),
            Bar(index=5, timestamp=base_ts + 300,
                open=114.0, high=116.0, low=108.0, close=109.0),  # Retracement
        ]
        return bars

    def test_same_bars_same_leg_ids(self):
        """Processing same bars twice produces same leg IDs."""
        bars = self._create_bars()

        # First run
        detector1 = LegDetector()
        for bar in bars:
            detector1.process_bar(bar)
        leg_ids_1 = [leg.leg_id for leg in detector1.state.active_legs]

        # Second run (fresh detector, simulating BE reset)
        detector2 = LegDetector()
        for bar in bars:
            detector2.process_bar(bar)
        leg_ids_2 = [leg.leg_id for leg in detector2.state.active_legs]

        # IDs should be identical
        assert leg_ids_1 == leg_ids_2

    def test_followed_leg_survives_reset(self):
        """
        Simulate the FE scenario: store a leg_id, reset detector, verify ID exists.
        """
        bars = self._create_bars()

        # Run 1: Process bars, "follow" a leg
        detector1 = LegDetector()
        for bar in bars:
            detector1.process_bar(bar)

        if detector1.state.active_legs:
            followed_leg_id = detector1.state.active_legs[0].leg_id

            # Run 2: Fresh detector (simulates step-back reset)
            detector2 = LegDetector()
            for bar in bars:
                detector2.process_bar(bar)

            # Verify the followed leg ID still exists
            current_leg_ids = [leg.leg_id for leg in detector2.state.active_legs]
            assert followed_leg_id in current_leg_ids, \
                f"Followed leg {followed_leg_id} not found after reset"


class TestLegIdExplicit:
    """Test explicit leg_id handling."""

    def test_explicit_leg_id_preserved(self):
        """If leg_id is explicitly provided, use it."""
        leg = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
            leg_id="custom_legacy_id_abc",
        )
        # Explicit ID should be preserved
        assert leg.leg_id == "custom_legacy_id_abc"

    def test_empty_leg_id_computed(self):
        """If leg_id is empty string, compute it."""
        leg = Leg(
            direction="bull",
            origin_price=Decimal("100.00"),
            origin_index=10,
            pivot_price=Decimal("110.00"),
            pivot_index=15,
            leg_id="",
        )
        # Should be computed
        assert leg.leg_id == "leg_bull_100.00_10"
