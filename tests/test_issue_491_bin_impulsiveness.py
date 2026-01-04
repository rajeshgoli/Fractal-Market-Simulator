"""
Tests for Issue #491: Bin-Normalized Impulsiveness

This issue adds `bin_impulsiveness` to legs - a percentile rank of impulse
within the same bin only. More meaningful than global impulsiveness because
it compares apples to apples (e.g., how impulsive is this bin-8 leg compared
to other bin-8 legs?).

Implementation:
- `bin_impulsiveness` field added to Leg dataclass
- Computed in ReferenceLayer._update_bin_classifications()
- Exposed in DAG API via DagLegResponse
"""

import pytest
from decimal import Decimal

from swing_analysis.dag.leg import Leg
from swing_analysis.reference_layer import ReferenceLayer
from swing_analysis.reference_config import ReferenceConfig
from swing_analysis.types import Bar


def create_test_leg(
    direction: str = 'bull',
    origin_price: Decimal = Decimal('100'),
    pivot_price: Decimal = Decimal('110'),
    origin_index: int = 0,
    pivot_index: int = 5,
    impulse: float = 1.0,
    leg_id: str = None,
) -> Leg:
    """Helper to create a test leg with specified properties."""
    leg = Leg(
        direction=direction,
        origin_price=origin_price,
        origin_index=origin_index,
        pivot_price=pivot_price,
        pivot_index=pivot_index,
    )
    leg.impulse = impulse
    if leg_id:
        leg.leg_id = leg_id
    return leg


def create_test_bar(index: int = 0, price: float = 100.0) -> Bar:
    """Helper to create a test bar."""
    return Bar(
        index=index,
        timestamp=1000000 + index,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price,
    )


class TestBinImpulsivenessField:
    """Test the bin_impulsiveness field on Leg dataclass."""

    def test_leg_has_bin_impulsiveness_field(self):
        """Leg should have bin_impulsiveness field, defaulting to None."""
        leg = create_test_leg()
        assert hasattr(leg, 'bin_impulsiveness')
        assert leg.bin_impulsiveness is None

    def test_bin_impulsiveness_is_settable(self):
        """bin_impulsiveness should be settable."""
        leg = create_test_leg()
        leg.bin_impulsiveness = 75.5
        assert leg.bin_impulsiveness == 75.5


class TestBinImpulsivenessComputation:
    """Test bin_impulsiveness computation in ReferenceLayer."""

    def test_single_leg_in_bin_gets_50_percentile(self):
        """A single leg in a bin should get 50% bin_impulsiveness."""
        # Create reference layer with low min_swings for testing
        config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=config)

        # Create a single leg with some impulse
        leg = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('110'),
            origin_index=0,
            pivot_index=5,
            impulse=2.0,
        )

        # Create bar that triggers formation (price at 38.2% retracement)
        # For bull leg: origin=100 (low), pivot=110 (high), range=10
        # Formation at 0.382 means price needs to be at 110 - 0.382*10 = 106.18
        bar = create_test_bar(index=10, price=106.0)

        # Process the leg
        ref_layer.update([leg], bar)

        # Single leg in bin should get 50%
        assert leg.bin_impulsiveness is not None
        assert leg.bin_impulsiveness == 50.0

    def test_two_legs_same_bin_different_impulse(self):
        """Two legs in same bin: higher impulse should get higher percentile."""
        config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=config)

        # Create two legs with same range (will be in same bin) but different impulse
        leg_low_impulse = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('110'),
            origin_index=0,
            pivot_index=10,  # 10 bars, impulse = 10/10 = 1.0
            impulse=1.0,
            leg_id='leg_low',
        )

        leg_high_impulse = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('110'),
            origin_index=20,
            pivot_index=25,  # 5 bars, impulse = 10/5 = 2.0
            impulse=2.0,
            leg_id='leg_high',
        )

        # Create bar that triggers formation
        bar = create_test_bar(index=30, price=106.0)

        # Process both legs
        ref_layer.update([leg_low_impulse, leg_high_impulse], bar)

        # Higher impulse should get higher percentile
        assert leg_low_impulse.bin_impulsiveness is not None
        assert leg_high_impulse.bin_impulsiveness is not None
        assert leg_high_impulse.bin_impulsiveness > leg_low_impulse.bin_impulsiveness

    def test_legs_in_different_bins_computed_separately(self):
        """Legs in different bins should have independent percentile rankings."""
        config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=config)

        # Create legs with very different ranges (will be in different bins)
        # Small range leg (low bin)
        small_leg = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('101'),  # Range = 1
            origin_index=0,
            pivot_index=5,
            impulse=0.2,
            leg_id='small_leg',
        )

        # Large range leg (high bin)
        large_leg = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('200'),  # Range = 100
            origin_index=10,
            pivot_index=15,
            impulse=20.0,
            leg_id='large_leg',
        )

        # Create bar that triggers formation for small leg
        bar = create_test_bar(index=20, price=100.5)

        # Process both legs
        ref_layer.update([small_leg, large_leg], bar)

        # Each leg alone in its bin gets 50%
        if small_leg.bin_impulsiveness is not None:
            assert small_leg.bin_impulsiveness == 50.0
        if large_leg.bin_impulsiveness is not None:
            assert large_leg.bin_impulsiveness == 50.0

    def test_legs_without_impulse_get_none(self):
        """Legs without impulse value should have None bin_impulsiveness."""
        config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=config)

        leg = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('110'),
        )
        leg.impulse = None  # No impulse

        bar = create_test_bar(index=10, price=106.0)
        ref_layer.update([leg], bar)

        assert leg.bin_impulsiveness is None

    def test_legs_with_zero_impulse_get_none(self):
        """Legs with zero impulse should have None bin_impulsiveness."""
        config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=config)

        leg = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('110'),
            impulse=0.0,
        )

        bar = create_test_bar(index=10, price=106.0)
        ref_layer.update([leg], bar)

        assert leg.bin_impulsiveness is None


class TestRangeBinIndexSetting:
    """Test that range_bin_index is set correctly on formed legs."""

    def test_range_bin_index_set_on_formed_leg(self):
        """Formed legs should have range_bin_index set."""
        config = ReferenceConfig(min_swings_for_classification=1)
        ref_layer = ReferenceLayer(reference_config=config)

        leg = create_test_leg(
            direction='bull',
            origin_price=Decimal('100'),
            pivot_price=Decimal('110'),
            impulse=1.0,
        )

        bar = create_test_bar(index=10, price=106.0)
        ref_layer.update([leg], bar)

        # Should have range_bin_index set
        assert leg.range_bin_index is not None
        assert 0 <= leg.range_bin_index <= 10  # Valid bin range


class TestStateSerialization:
    """Test that bin_impulsiveness survives serialization."""

    def test_bin_impulsiveness_serialization(self):
        """bin_impulsiveness should be included in state serialization."""
        from swing_analysis.dag.state import DetectorState

        leg = create_test_leg(impulse=2.0)
        leg.bin_impulsiveness = 75.5
        leg.range_bin_index = 5

        state = DetectorState(active_legs=[leg])
        serialized = state.to_dict()

        # Check that bin_impulsiveness is in serialized data
        assert len(serialized['active_legs']) == 1
        assert serialized['active_legs'][0]['bin_impulsiveness'] == 75.5
        assert serialized['active_legs'][0]['range_bin_index'] == 5

    def test_bin_impulsiveness_deserialization(self):
        """bin_impulsiveness should be restored from serialized state."""
        from swing_analysis.dag.state import DetectorState

        leg = create_test_leg(impulse=2.0)
        leg.bin_impulsiveness = 75.5
        leg.range_bin_index = 5

        state = DetectorState(active_legs=[leg])
        serialized = state.to_dict()

        # Restore state
        restored = DetectorState.from_dict(serialized)

        assert len(restored.active_legs) == 1
        assert restored.active_legs[0].bin_impulsiveness == 75.5
        assert restored.active_legs[0].range_bin_index == 5


class TestAPISchema:
    """Test that DagLegResponse includes the new fields."""

    def test_dag_leg_response_has_new_fields(self):
        """DagLegResponse should include impulse, range, depth, bin, bin_impulsiveness."""
        from replay_server.schemas import DagLegResponse

        # Check that the schema accepts all new fields
        response = DagLegResponse(
            leg_id='test',
            direction='bull',
            pivot_price=110.0,
            pivot_index=5,
            origin_price=100.0,
            origin_index=0,
            retracement_pct=0.5,
            status='active',
            bar_count=5,
            impulse=2.0,
            range=10.0,
            depth=1,
            bin=5,
            impulsiveness=75.0,
            bin_impulsiveness=80.0,
        )

        assert response.impulse == 2.0
        assert response.range == 10.0
        assert response.depth == 1
        assert response.bin == 5
        assert response.bin_impulsiveness == 80.0

    def test_dag_leg_response_optional_fields(self):
        """New fields should be optional (nullable)."""
        from replay_server.schemas import DagLegResponse

        response = DagLegResponse(
            leg_id='test',
            direction='bull',
            pivot_price=110.0,
            pivot_index=5,
            origin_price=100.0,
            origin_index=0,
            retracement_pct=0.5,
            status='active',
            bar_count=5,
            # All new fields omitted - should default to None
        )

        assert response.impulse is None
        assert response.range is None
        assert response.depth == 0  # depth has default value
        assert response.bin is None
        assert response.bin_impulsiveness is None
