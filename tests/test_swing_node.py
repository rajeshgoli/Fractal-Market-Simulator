"""
Tests for SwingNode dataclass.

Tests the swing data structure including:
- Property calculations for bull and bear swings
- Status transitions
- ID generation uniqueness
"""

import pytest
from decimal import Decimal

from src.swing_analysis.swing_node import SwingNode


class TestSwingNodeBullProperties:
    """Test property calculations for bull swings."""

    def test_defended_pivot_is_low_for_bull(self):
        """Bull swings defend the low price."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        assert swing.defended_pivot == Decimal("5000.00")

    def test_origin_is_high_for_bull(self):
        """Bull swings originated from the high."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        assert swing.origin == Decimal("5100.00")

    def test_range_is_positive_for_bull(self):
        """Range is always positive."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        assert swing.range == Decimal("100.00")

    def test_is_bull_true_for_bull_swing(self):
        """is_bull returns True for bull swings."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        assert swing.is_bull is True
        assert swing.is_bear is False


class TestSwingNodeBearProperties:
    """Test property calculations for bear swings."""

    def test_defended_pivot_is_high_for_bear(self):
        """Bear swings defend the high price."""
        swing = SwingNode(
            swing_id="test002",
            high_bar_index=150,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bear",
            status="active",
            formed_at_bar=150,
        )
        assert swing.defended_pivot == Decimal("5100.00")

    def test_origin_is_low_for_bear(self):
        """Bear swings originated from the low."""
        swing = SwingNode(
            swing_id="test002",
            high_bar_index=150,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bear",
            status="active",
            formed_at_bar=150,
        )
        assert swing.origin == Decimal("5000.00")

    def test_range_is_positive_for_bear(self):
        """Range is always positive regardless of direction."""
        swing = SwingNode(
            swing_id="test002",
            high_bar_index=150,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bear",
            status="active",
            formed_at_bar=150,
        )
        assert swing.range == Decimal("100.00")

    def test_is_bear_true_for_bear_swing(self):
        """is_bear returns True for bear swings."""
        swing = SwingNode(
            swing_id="test002",
            high_bar_index=150,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bear",
            status="active",
            formed_at_bar=150,
        )
        assert swing.is_bear is True
        assert swing.is_bull is False


class TestSwingNodeStatusTransitions:
    """Test status transitions."""

    def test_initial_status_forming(self):
        """Swings can start in forming status."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="forming",
            formed_at_bar=150,
        )
        assert swing.status == "forming"
        assert swing.is_active is False

    def test_invalidate_changes_status(self):
        """invalidate() changes status to invalidated."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing.invalidate()
        assert swing.status == "invalidated"
        assert swing.is_invalidated is True
        assert swing.is_active is False

    def test_complete_changes_status(self):
        """complete() changes status to completed."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing.complete()
        assert swing.status == "completed"
        assert swing.is_completed is True
        assert swing.is_active is False

    def test_is_active_only_for_active_status(self):
        """is_active is True only for active status."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        assert swing.is_active is True

        swing.status = "forming"
        assert swing.is_active is False

        swing.status = "invalidated"
        assert swing.is_active is False

        swing.status = "completed"
        assert swing.is_active is False


class TestSwingNodeIdGeneration:
    """Test ID generation uniqueness."""

    def test_generate_id_returns_string(self):
        """generate_id returns a string."""
        id1 = SwingNode.generate_id()
        assert isinstance(id1, str)

    def test_generate_id_returns_8_characters(self):
        """generate_id returns 8-character string."""
        id1 = SwingNode.generate_id()
        assert len(id1) == 8

    def test_generate_id_uniqueness(self):
        """Multiple calls to generate_id produce unique values."""
        ids = [SwingNode.generate_id() for _ in range(1000)]
        assert len(set(ids)) == 1000

    def test_generate_id_format(self):
        """generate_id returns valid hex characters."""
        id1 = SwingNode.generate_id()
        # UUID first 8 chars are hex + optional hyphen position
        assert all(c in "0123456789abcdef-" for c in id1)


class TestSwingNodeEquality:
    """Test equality and hashing."""

    def test_equality_by_swing_id(self):
        """Swings with same swing_id are equal."""
        swing1 = SwingNode(
            swing_id="same_id",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing2 = SwingNode(
            swing_id="same_id",
            high_bar_index=200,  # Different bar index
            high_price=Decimal("5200.00"),  # Different price
            low_bar_index=250,
            low_price=Decimal("5100.00"),
            direction="bear",  # Different direction
            status="invalidated",  # Different status
            formed_at_bar=250,
        )
        assert swing1 == swing2

    def test_inequality_by_swing_id(self):
        """Swings with different swing_id are not equal."""
        swing1 = SwingNode(
            swing_id="id_one",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing2 = SwingNode(
            swing_id="id_two",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        assert swing1 != swing2

    def test_hash_consistency(self):
        """Swings with same swing_id have same hash."""
        swing1 = SwingNode(
            swing_id="same_id",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing2 = SwingNode(
            swing_id="same_id",
            high_bar_index=200,
            high_price=Decimal("5200.00"),
            low_bar_index=250,
            low_price=Decimal("5100.00"),
            direction="bear",
            status="invalidated",
            formed_at_bar=250,
        )
        assert hash(swing1) == hash(swing2)

    def test_usable_in_set(self):
        """Swings can be stored in sets."""
        swing1 = SwingNode(
            swing_id="id_one",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing2 = SwingNode(
            swing_id="id_two",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing_set = {swing1, swing2}
        assert len(swing_set) == 2

    def test_usable_as_dict_key(self):
        """Swings can be used as dict keys."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        swing_dict = {swing: "test_value"}
        assert swing_dict[swing] == "test_value"

    def test_equality_with_non_swing_returns_not_implemented(self):
        """Comparing with non-SwingNode returns NotImplemented."""
        swing = SwingNode(
            swing_id="test001",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        # This should not raise, Python will handle NotImplemented
        assert swing != "not a swing"
        assert swing != 123
        assert swing != None


class TestSwingNodeRepr:
    """Test string representation."""

    def test_repr_contains_key_info(self):
        """__repr__ includes swing_id, direction, prices, and status."""
        swing = SwingNode(
            swing_id="abc12345",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        repr_str = repr(swing)
        assert "abc12345" in repr_str
        assert "bull" in repr_str
        assert "5100" in repr_str
        assert "5000" in repr_str
        assert "active" in repr_str
