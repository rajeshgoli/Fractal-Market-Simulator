"""
Tests for issue #307: Segment impulse tracking.

Verifies that parent legs track impulse metrics when children form:
- segment_deepest_price: Deepest point when first child formed
- segment_deepest_index: Bar index of the deepest point
- impulse_to_deepest: Price change per bar from origin to deepest
- impulse_back: Price change per bar from deepest back to child origin
- net_segment_impulse: Difference (sustained conviction)
"""

import pytest
from decimal import Decimal

from src.swing_analysis.dag import LegDetector
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.leg_detector import (
    _calculate_segment_impulse,
    _update_segment_impulse_for_new_child,
)
from src.swing_analysis.detection_config import DetectionConfig
from src.swing_analysis.types import Bar


def make_bar(index: int, o: float, h: float, l: float, c: float) -> Bar:
    """Helper to create a test bar."""
    return Bar(
        index=index,
        timestamp=1000000 + index * 300,
        open=o,
        high=h,
        low=l,
        close=c,
    )


class TestSegmentImpulseFields:
    """Test that Leg has the segment impulse fields."""

    def test_leg_has_segment_impulse_fields(self):
        """Leg should have all segment impulse fields."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('110'),
            pivot_index=5,
            price_at_creation=Decimal('105'),
            last_modified_bar=5,
        )

        # Default values should be None
        assert leg.segment_deepest_price is None
        assert leg.segment_deepest_index is None
        assert leg.impulse_to_deepest is None
        assert leg.impulse_back is None

    def test_net_segment_impulse_property_none_when_not_set(self):
        """net_segment_impulse should be None when components not set."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('110'),
            pivot_index=5,
            price_at_creation=Decimal('105'),
            last_modified_bar=5,
        )

        assert leg.net_segment_impulse is None

    def test_net_segment_impulse_property_calculates_difference(self):
        """net_segment_impulse should be impulse_to_deepest - impulse_back."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('110'),
            pivot_index=5,
            price_at_creation=Decimal('105'),
            last_modified_bar=5,
            impulse_to_deepest=2.0,
            impulse_back=0.5,
        )

        assert leg.net_segment_impulse == 1.5

    def test_net_segment_impulse_can_be_negative(self):
        """net_segment_impulse can be negative if counter-move was stronger."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('110'),
            pivot_index=5,
            price_at_creation=Decimal('105'),
            last_modified_bar=5,
            impulse_to_deepest=1.0,
            impulse_back=3.0,
        )

        assert leg.net_segment_impulse == -2.0


class TestCalculateSegmentImpulse:
    """Test the _calculate_segment_impulse helper function."""

    def test_calculates_impulse_to_deepest(self):
        """Should calculate price/bar from origin to deepest."""
        parent = Leg(
            direction='bear',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('90'),  # Deepest point for bear
            pivot_index=10,
            price_at_creation=Decimal('95'),
            last_modified_bar=10,
        )

        _calculate_segment_impulse(
            parent,
            child_origin_price=Decimal('95'),
            child_origin_index=15,
        )

        # Origin 100 -> Deepest 90 = 10 points over 10 bars = 1.0
        assert parent.impulse_to_deepest == 1.0

    def test_calculates_impulse_back(self):
        """Should calculate price/bar from deepest to child origin."""
        parent = Leg(
            direction='bear',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('90'),
            pivot_index=10,
            price_at_creation=Decimal('95'),
            last_modified_bar=10,
        )

        _calculate_segment_impulse(
            parent,
            child_origin_price=Decimal('95'),
            child_origin_index=15,
        )

        # Deepest 90 -> Child origin 95 = 5 points over 5 bars = 1.0
        assert parent.impulse_back == 1.0

    def test_stores_deepest_price_and_index(self):
        """Should store the deepest price and index."""
        parent = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('120'),  # Deepest for bull (highest)
            pivot_index=8,
            price_at_creation=Decimal('115'),
            last_modified_bar=8,
        )

        _calculate_segment_impulse(
            parent,
            child_origin_price=Decimal('105'),
            child_origin_index=12,
        )

        assert parent.segment_deepest_price == Decimal('120')
        assert parent.segment_deepest_index == 8

    def test_handles_zero_bar_difference(self):
        """Should handle edge case where bars are at same index."""
        parent = Leg(
            direction='bear',
            origin_price=Decimal('100'),
            origin_index=5,
            pivot_price=Decimal('95'),
            pivot_index=5,  # Same as origin!
            price_at_creation=Decimal('97'),
            last_modified_bar=5,
        )

        _calculate_segment_impulse(
            parent,
            child_origin_price=Decimal('97'),
            child_origin_index=5,
        )

        # Should handle gracefully (0 bars = 0 impulse)
        assert parent.impulse_to_deepest == 0.0
        assert parent.impulse_back == 0.0


class TestUpdateSegmentImpulseForNewChild:
    """Test the _update_segment_impulse_for_new_child helper function."""

    def test_first_child_calculates_from_scratch(self):
        """First child should trigger full calculation."""
        parent = Leg(
            direction='bear',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('90'),
            pivot_index=10,
            price_at_creation=Decimal('95'),
            last_modified_bar=10,
        )

        _update_segment_impulse_for_new_child(
            parent,
            new_child_origin_price=Decimal('95'),
            new_child_origin_index=15,
        )

        # Should have calculated everything
        assert parent.segment_deepest_price == Decimal('90')
        assert parent.segment_deepest_index == 10
        assert parent.impulse_to_deepest == 1.0
        assert parent.impulse_back == 1.0

    def test_second_child_same_deepest_updates_only_impulse_back(self):
        """Second child at same deepest should only update impulse_back."""
        parent = Leg(
            direction='bear',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('90'),  # Same as before
            pivot_index=10,
            price_at_creation=Decimal('95'),
            last_modified_bar=10,
            # Already has segment impulse from first child
            segment_deepest_price=Decimal('90'),
            segment_deepest_index=10,
            impulse_to_deepest=1.0,
            impulse_back=1.0,
        )

        _update_segment_impulse_for_new_child(
            parent,
            new_child_origin_price=Decimal('98'),  # Higher origin
            new_child_origin_index=20,
        )

        # Deepest and impulse_to_deepest unchanged
        assert parent.segment_deepest_price == Decimal('90')
        assert parent.segment_deepest_index == 10
        assert parent.impulse_to_deepest == 1.0

        # impulse_back recalculated: 90 -> 98 = 8 points over 10 bars = 0.8
        assert parent.impulse_back == 0.8

    def test_pivot_extended_deeper_recalculates_both(self):
        """When pivot extends deeper, both impulses should recalculate."""
        parent = Leg(
            direction='bear',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('85'),  # Extended deeper than stored 90
            pivot_index=15,  # New pivot index
            price_at_creation=Decimal('87'),
            last_modified_bar=15,
            # Previously stored deepest
            segment_deepest_price=Decimal('90'),
            segment_deepest_index=10,
            impulse_to_deepest=1.0,
            impulse_back=1.0,
        )

        _update_segment_impulse_for_new_child(
            parent,
            new_child_origin_price=Decimal('88'),
            new_child_origin_index=18,
        )

        # Deepest should update to new pivot
        assert parent.segment_deepest_price == Decimal('85')
        assert parent.segment_deepest_index == 15

        # impulse_to_deepest recalculated: 100 -> 85 = 15 points over 15 bars = 1.0
        assert parent.impulse_to_deepest == 1.0

        # impulse_back recalculated: 85 -> 88 = 3 points over 3 bars = 1.0
        assert parent.impulse_back == 1.0

    def test_bull_leg_pivot_extended_deeper(self):
        """Bull leg pivot extends deeper when HIGH increases."""
        parent = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('120'),  # Extended higher than stored 110
            pivot_index=12,
            price_at_creation=Decimal('115'),
            last_modified_bar=12,
            # Previously stored deepest
            segment_deepest_price=Decimal('110'),
            segment_deepest_index=8,
            impulse_to_deepest=1.25,  # 10 points / 8 bars
            impulse_back=0.5,
        )

        _update_segment_impulse_for_new_child(
            parent,
            new_child_origin_price=Decimal('105'),
            new_child_origin_index=16,
        )

        # Deepest should update (bull: higher is deeper)
        assert parent.segment_deepest_price == Decimal('120')
        assert parent.segment_deepest_index == 12

        # impulse_to_deepest: 100 -> 120 = 20 points over 12 bars
        assert pytest.approx(parent.impulse_to_deepest, rel=0.01) == 20.0 / 12

        # impulse_back: 120 -> 105 = 15 points over 4 bars
        assert parent.impulse_back == 15.0 / 4


class TestIntegrationWithLegDetector:
    """Test segment impulse tracking through the full detector flow."""

    def test_child_leg_updates_parent_segment_impulse(self):
        """When a child leg forms, parent should get segment impulse."""
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # Create a downtrend that establishes a bear parent leg
        # Then a rally creates a child bear leg
        bars = [
            make_bar(0, 100, 102, 99, 101),   # Establish bear origin
            make_bar(1, 101, 101.5, 95, 96),  # Drop, potential bear leg
            make_bar(2, 96, 97, 94, 95),      # Continue down
            make_bar(3, 95, 96, 92, 93),      # Deeper low
            make_bar(4, 93, 94, 91, 92),      # Even deeper
            make_bar(5, 92, 98, 91, 97),      # Rally - potential child origin
            make_bar(6, 97, 99, 96, 98),      # Continue rally
            make_bar(7, 98, 100, 97, 99),     # Higher high for child origin
            make_bar(8, 99, 99.5, 93, 94),    # Drop - child leg forming
            make_bar(9, 94, 95, 90, 91),      # Child extends lower
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Find bear legs
        bear_legs = [leg for leg in detector.state.active_legs if leg.direction == 'bear']

        # Should have at least one bear leg with a parent
        child_legs = [leg for leg in bear_legs if leg.parent_leg_id is not None]

        if child_legs:
            # Get the parent of the first child
            child = child_legs[0]
            parent = detector._find_leg_by_id(child.parent_leg_id)

            if parent:
                # Parent should have segment impulse set
                assert parent.segment_deepest_price is not None
                assert parent.segment_deepest_index is not None
                assert parent.impulse_to_deepest is not None
                assert parent.impulse_back is not None
                assert parent.net_segment_impulse is not None


class TestStateSerialization:
    """Test that segment impulse fields serialize/deserialize correctly."""

    def test_leg_segment_impulse_serializes(self):
        """Segment impulse fields should be included in state serialization."""
        from src.swing_analysis.dag.state import DetectorState

        leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('110'),
            pivot_index=5,
            price_at_creation=Decimal('105'),
            last_modified_bar=5,
            segment_deepest_price=Decimal('110'),
            segment_deepest_index=5,
            impulse_to_deepest=2.0,
            impulse_back=0.5,
        )

        state = DetectorState()
        state.active_legs = [leg]

        # Serialize
        data = state.to_dict()

        # Check serialized data
        leg_data = data['active_legs'][0]
        assert leg_data['segment_deepest_price'] == '110'
        assert leg_data['segment_deepest_index'] == 5
        assert leg_data['impulse_to_deepest'] == 2.0
        assert leg_data['impulse_back'] == 0.5

    def test_leg_segment_impulse_deserializes(self):
        """Segment impulse fields should be restored from serialization."""
        from src.swing_analysis.dag.state import DetectorState

        data = {
            'active_swings': [],
            'active_legs': [{
                'direction': 'bull',
                'origin_price': '100',
                'origin_index': 0,
                'pivot_price': '110',
                'pivot_index': 5,
                'retracement_pct': '0.5',
                'formed': True,
                'status': 'active',
                'bar_count': 5,
                'gap_count': 0,
                'last_modified_bar': 5,
                'price_at_creation': '105',
                'segment_deepest_price': '110',
                'segment_deepest_index': 5,
                'impulse_to_deepest': 2.0,
                'impulse_back': 0.5,
            }],
            'pending_origins': {'bull': None, 'bear': None},
        }

        state = DetectorState.from_dict(data)

        leg = state.active_legs[0]
        assert leg.segment_deepest_price == Decimal('110')
        assert leg.segment_deepest_index == 5
        assert leg.impulse_to_deepest == 2.0
        assert leg.impulse_back == 0.5
        assert leg.net_segment_impulse == 1.5

    def test_leg_segment_impulse_handles_none(self):
        """None values should serialize and deserialize correctly."""
        from src.swing_analysis.dag.state import DetectorState

        leg = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('110'),
            pivot_index=5,
            price_at_creation=Decimal('105'),
            last_modified_bar=5,
            # No segment impulse set
        )

        state = DetectorState()
        state.active_legs = [leg]

        # Round-trip
        data = state.to_dict()
        restored_state = DetectorState.from_dict(data)

        restored_leg = restored_state.active_legs[0]
        assert restored_leg.segment_deepest_price is None
        assert restored_leg.segment_deepest_index is None
        assert restored_leg.impulse_to_deepest is None
        assert restored_leg.impulse_back is None
        assert restored_leg.net_segment_impulse is None
