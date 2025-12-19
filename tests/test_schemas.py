"""
Tests for Pydantic schemas in ground_truth_annotator.

Tests V2 hierarchical swing schemas added in rewrite Phase 3.
"""

import pytest
from pydantic import ValidationError

from src.ground_truth_annotator.schemas import (
    HierarchicalSwingResponse,
    SwingEventResponse,
    CalibrationSwingResponseV2,
    CalibrationResponseV2,
)


class TestHierarchicalSwingResponse:
    """Tests for HierarchicalSwingResponse schema."""

    def test_valid_swing_creates_successfully(self):
        """Valid data should create a swing response."""
        swing = HierarchicalSwingResponse(
            swing_id="abc123",
            high_bar_index=100,
            high_price=6166.0,
            low_bar_index=200,
            low_price=4832.0,
            direction="bull",
            status="active",
            formed_at_bar=210,
            parent_ids=[],
            child_ids=["def456", "ghi789"],
            depth=0,
            fib_0=4832.0,
            fib_0382=5341.98,
            fib_0618=5657.02,
            fib_1=6166.0,
            fib_2=7500.0,
        )
        assert swing.swing_id == "abc123"
        assert swing.direction == "bull"
        assert swing.depth == 0

    def test_serialization_round_trip(self):
        """Serialization and deserialization should preserve data."""
        original = HierarchicalSwingResponse(
            swing_id="xyz789",
            high_bar_index=50,
            high_price=5000.0,
            low_bar_index=100,
            low_price=4500.0,
            direction="bear",
            status="forming",
            formed_at_bar=105,
            parent_ids=["parent1"],
            child_ids=[],
            depth=1,
            fib_0=5000.0,
            fib_0382=4809.0,
            fib_0618=4691.0,
            fib_1=4500.0,
            fib_2=4000.0,
        )

        # Serialize to dict, then back to model
        data = original.model_dump()
        restored = HierarchicalSwingResponse.model_validate(data)

        assert restored.swing_id == original.swing_id
        assert restored.direction == original.direction
        assert restored.parent_ids == original.parent_ids
        assert restored.fib_0618 == original.fib_0618

    def test_json_round_trip(self):
        """JSON serialization should work correctly."""
        original = HierarchicalSwingResponse(
            swing_id="test123",
            high_bar_index=10,
            high_price=100.0,
            low_bar_index=20,
            low_price=90.0,
            direction="bull",
            status="completed",
            formed_at_bar=25,
            parent_ids=[],
            child_ids=[],
            depth=0,
            fib_0=90.0,
            fib_0382=93.82,
            fib_0618=96.18,
            fib_1=100.0,
            fib_2=110.0,
        )

        json_str = original.model_dump_json()
        restored = HierarchicalSwingResponse.model_validate_json(json_str)

        assert restored == original

    def test_example_data_validates(self):
        """The example from Config should validate successfully."""
        example = {
            "swing_id": "abc123",
            "high_bar_index": 100,
            "high_price": 6166.0,
            "low_bar_index": 200,
            "low_price": 4832.0,
            "direction": "bull",
            "status": "active",
            "formed_at_bar": 210,
            "parent_ids": [],
            "child_ids": ["def456", "ghi789"],
            "depth": 0,
            "fib_0": 4832.0,
            "fib_0382": 5341.98,
            "fib_0618": 5657.02,
            "fib_1": 6166.0,
            "fib_2": 7500.0,
        }
        swing = HierarchicalSwingResponse.model_validate(example)
        assert swing.swing_id == "abc123"

    def test_missing_required_field_raises_error(self):
        """Missing required fields should raise ValidationError."""
        with pytest.raises(ValidationError):
            HierarchicalSwingResponse(
                swing_id="test",
                high_bar_index=100,
                # Missing most required fields
            )

    def test_multiple_parents_allowed(self):
        """DAG structure allows multiple parents."""
        swing = HierarchicalSwingResponse(
            swing_id="child",
            high_bar_index=100,
            high_price=100.0,
            low_bar_index=110,
            low_price=95.0,
            direction="bull",
            status="active",
            formed_at_bar=115,
            parent_ids=["parent1", "parent2", "parent3"],
            child_ids=[],
            depth=2,
            fib_0=95.0,
            fib_0382=96.91,
            fib_0618=98.09,
            fib_1=100.0,
            fib_2=105.0,
        )
        assert len(swing.parent_ids) == 3


class TestSwingEventResponse:
    """Tests for SwingEventResponse schema."""

    def test_swing_formed_event(self):
        """SWING_FORMED event with parent_ids."""
        event = SwingEventResponse(
            event_type="SWING_FORMED",
            bar_index=100,
            swing_id="swing123",
            explanation="Bull swing formed after 0.287 extension breached",
            parent_ids=["parent1"],
        )
        assert event.event_type == "SWING_FORMED"
        assert event.parent_ids == ["parent1"]
        assert event.violation_price is None

    def test_swing_invalidated_event(self):
        """SWING_INVALIDATED event with violation details."""
        event = SwingEventResponse(
            event_type="SWING_INVALIDATED",
            bar_index=200,
            swing_id="swing123",
            explanation="Defended pivot violated by 15 points",
            violation_price=4817.0,
            excess_amount=15.0,
        )
        assert event.event_type == "SWING_INVALIDATED"
        assert event.violation_price == 4817.0
        assert event.excess_amount == 15.0

    def test_level_cross_event(self):
        """LEVEL_CROSS event with level info."""
        event = SwingEventResponse(
            event_type="LEVEL_CROSS",
            bar_index=150,
            swing_id="swing123",
            explanation="Price crossed 0.618 level",
            level=0.618,
            previous_level=0.5,
        )
        assert event.event_type == "LEVEL_CROSS"
        assert event.level == 0.618
        assert event.previous_level == 0.5

    def test_swing_completed_event(self):
        """SWING_COMPLETED event."""
        event = SwingEventResponse(
            event_type="SWING_COMPLETED",
            bar_index=300,
            swing_id="swing123",
            explanation="Price reached 2.0 extension target",
        )
        assert event.event_type == "SWING_COMPLETED"

    def test_optional_timestamp(self):
        """Timestamp field is optional."""
        event = SwingEventResponse(
            event_type="SWING_FORMED",
            bar_index=100,
            swing_id="test",
            explanation="Test event",
        )
        assert event.timestamp is None

        event_with_ts = SwingEventResponse(
            event_type="SWING_FORMED",
            bar_index=100,
            timestamp="2025-01-15T10:30:00",
            swing_id="test",
            explanation="Test event with timestamp",
        )
        assert event_with_ts.timestamp == "2025-01-15T10:30:00"

    def test_serialization_round_trip(self):
        """Serialization preserves all fields including optionals."""
        original = SwingEventResponse(
            event_type="SWING_INVALIDATED",
            bar_index=250,
            timestamp="2025-01-15T14:00:00",
            swing_id="test_swing",
            explanation="Test invalidation",
            violation_price=100.5,
            excess_amount=2.5,
        )

        data = original.model_dump()
        restored = SwingEventResponse.model_validate(data)

        assert restored == original


class TestCalibrationSwingResponseV2:
    """Tests for CalibrationSwingResponseV2 schema."""

    def test_valid_calibration_swing(self):
        """Valid calibration swing data."""
        swing = CalibrationSwingResponseV2(
            swing_id="cal_swing_1",
            high_bar_index=50,
            high_price=5500.0,
            low_bar_index=100,
            low_price=5200.0,
            direction="bear",
            status="active",
            depth=1,
            parent_ids=["root_swing"],
            fib_0=5500.0,
            fib_0382=5385.4,
            fib_1=5200.0,
            fib_2=4900.0,
            is_active=True,
        )
        assert swing.is_active is True
        assert swing.depth == 1

    def test_inactive_swing(self):
        """Inactive swing (invalidated or completed)."""
        swing = CalibrationSwingResponseV2(
            swing_id="inactive_swing",
            high_bar_index=10,
            high_price=100.0,
            low_bar_index=20,
            low_price=90.0,
            direction="bull",
            status="invalidated",
            depth=2,
            parent_ids=["p1", "p2"],
            fib_0=90.0,
            fib_0382=93.82,
            fib_1=100.0,
            fib_2=110.0,
            is_active=False,
        )
        assert swing.is_active is False
        assert swing.status == "invalidated"

    def test_serialization_round_trip(self):
        """Serialization and deserialization work correctly."""
        original = CalibrationSwingResponseV2(
            swing_id="test",
            high_bar_index=0,
            high_price=100.0,
            low_bar_index=10,
            low_price=50.0,
            direction="bull",
            status="forming",
            depth=0,
            parent_ids=[],
            fib_0=50.0,
            fib_0382=69.1,
            fib_1=100.0,
            fib_2=150.0,
            is_active=True,
        )

        json_str = original.model_dump_json()
        restored = CalibrationSwingResponseV2.model_validate_json(json_str)

        assert restored == original


class TestCalibrationResponseV2:
    """Tests for CalibrationResponseV2 schema."""

    def test_empty_calibration(self):
        """Calibration with no swings found."""
        response = CalibrationResponseV2(
            swings=[],
            total_bars=10000,
            calibration_bars=5000,
            max_depth=0,
            swing_count_by_depth={},
        )
        assert len(response.swings) == 0
        assert response.max_depth == 0

    def test_calibration_with_swings(self):
        """Calibration with hierarchical swings."""
        swing1 = CalibrationSwingResponseV2(
            swing_id="root",
            high_bar_index=100,
            high_price=6000.0,
            low_bar_index=200,
            low_price=5000.0,
            direction="bull",
            status="active",
            depth=0,
            parent_ids=[],
            fib_0=5000.0,
            fib_0382=5382.0,
            fib_1=6000.0,
            fib_2=7000.0,
            is_active=True,
        )
        swing2 = CalibrationSwingResponseV2(
            swing_id="child1",
            high_bar_index=150,
            high_price=5800.0,
            low_bar_index=180,
            low_price=5400.0,
            direction="bear",
            status="active",
            depth=1,
            parent_ids=["root"],
            fib_0=5800.0,
            fib_0382=5647.2,
            fib_1=5400.0,
            fib_2=5000.0,
            is_active=True,
        )

        response = CalibrationResponseV2(
            swings=[swing1, swing2],
            total_bars=50000,
            calibration_bars=10000,
            max_depth=1,
            swing_count_by_depth={"0": 1, "1": 1},
        )

        assert len(response.swings) == 2
        assert response.max_depth == 1
        assert response.swing_count_by_depth["0"] == 1
        assert response.swing_count_by_depth["1"] == 1

    def test_serialization_round_trip(self):
        """Full calibration response serialization."""
        swing = CalibrationSwingResponseV2(
            swing_id="test",
            high_bar_index=0,
            high_price=100.0,
            low_bar_index=10,
            low_price=90.0,
            direction="bull",
            status="active",
            depth=0,
            parent_ids=[],
            fib_0=90.0,
            fib_0382=93.82,
            fib_1=100.0,
            fib_2=110.0,
            is_active=True,
        )

        original = CalibrationResponseV2(
            swings=[swing],
            total_bars=1000,
            calibration_bars=500,
            max_depth=0,
            swing_count_by_depth={"0": 1},
        )

        json_str = original.model_dump_json()
        restored = CalibrationResponseV2.model_validate_json(json_str)

        assert restored.total_bars == original.total_bars
        assert len(restored.swings) == len(original.swings)
        assert restored.swings[0].swing_id == original.swings[0].swing_id

    def test_deep_hierarchy(self):
        """Calibration with multiple depth levels."""
        swings = []
        for depth in range(5):
            swing = CalibrationSwingResponseV2(
                swing_id=f"swing_depth_{depth}",
                high_bar_index=depth * 10,
                high_price=100.0 - depth * 5,
                low_bar_index=depth * 10 + 5,
                low_price=95.0 - depth * 5,
                direction="bull",
                status="active",
                depth=depth,
                parent_ids=[f"swing_depth_{depth-1}"] if depth > 0 else [],
                fib_0=95.0 - depth * 5,
                fib_0382=96.91 - depth * 5,
                fib_1=100.0 - depth * 5,
                fib_2=105.0 - depth * 5,
                is_active=True,
            )
            swings.append(swing)

        response = CalibrationResponseV2(
            swings=swings,
            total_bars=100000,
            calibration_bars=20000,
            max_depth=4,
            swing_count_by_depth={"0": 1, "1": 1, "2": 1, "3": 1, "4": 1},
        )

        assert response.max_depth == 4
        assert len(response.swings) == 5


class TestSchemaInteroperability:
    """Tests for schema interoperability and edge cases."""

    def test_swing_from_event_ids_match(self):
        """Swing IDs in events should be traceable to swing responses."""
        swing = HierarchicalSwingResponse(
            swing_id="swing_abc",
            high_bar_index=100,
            high_price=100.0,
            low_bar_index=110,
            low_price=95.0,
            direction="bull",
            status="active",
            formed_at_bar=115,
            parent_ids=[],
            child_ids=[],
            depth=0,
            fib_0=95.0,
            fib_0382=96.91,
            fib_0618=98.09,
            fib_1=100.0,
            fib_2=105.0,
        )

        event = SwingEventResponse(
            event_type="SWING_FORMED",
            bar_index=115,
            swing_id="swing_abc",
            explanation="Swing formed",
            parent_ids=[],
        )

        assert event.swing_id == swing.swing_id

    def test_all_status_values(self):
        """All documented status values should work."""
        statuses = ["forming", "active", "invalidated", "completed"]

        for status in statuses:
            swing = HierarchicalSwingResponse(
                swing_id=f"swing_{status}",
                high_bar_index=100,
                high_price=100.0,
                low_bar_index=110,
                low_price=95.0,
                direction="bull",
                status=status,
                formed_at_bar=115,
                parent_ids=[],
                child_ids=[],
                depth=0,
                fib_0=95.0,
                fib_0382=96.91,
                fib_0618=98.09,
                fib_1=100.0,
                fib_2=105.0,
            )
            assert swing.status == status

    def test_all_direction_values(self):
        """Both bull and bear directions should work."""
        for direction in ["bull", "bear"]:
            swing = HierarchicalSwingResponse(
                swing_id=f"swing_{direction}",
                high_bar_index=100,
                high_price=100.0,
                low_bar_index=110,
                low_price=95.0,
                direction=direction,
                status="active",
                formed_at_bar=115,
                parent_ids=[],
                child_ids=[],
                depth=0,
                fib_0=95.0,
                fib_0382=96.91,
                fib_0618=98.09,
                fib_1=100.0,
                fib_2=105.0,
            )
            assert swing.direction == direction

    def test_all_event_types(self):
        """All documented event types should work."""
        event_types = ["SWING_FORMED", "SWING_INVALIDATED", "SWING_COMPLETED", "LEVEL_CROSS"]

        for event_type in event_types:
            event = SwingEventResponse(
                event_type=event_type,
                bar_index=100,
                swing_id="test",
                explanation=f"Test {event_type} event",
            )
            assert event.event_type == event_type
