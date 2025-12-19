"""
Tests for ReferenceLayer

Tests the reference layer filtering and invalidation rules.
See Docs/Reference/valid_swings.md for the canonical rules.

Big vs Small (hierarchy-based definition):
- Big swing = len(swing.parents) == 0 (root level)
- Small swing = len(swing.parents) > 0 (has parent)
"""

import pytest
from decimal import Decimal
from typing import List

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwingInfo,
    InvalidationResult,
    CompletionResult,
)
from src.swing_analysis.swing_config import SwingConfig, DirectionConfig
from src.swing_analysis.swing_node import SwingNode
from src.swing_analysis.types import Bar


def make_bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    timestamp: int = None,
) -> Bar:
    """Helper to create Bar objects for testing."""
    return Bar(
        index=index,
        timestamp=timestamp or 1700000000 + index * 60,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def make_swing(
    swing_id: str,
    high_price: float,
    low_price: float,
    direction: str = "bull",
    high_bar_index: int = 0,
    low_bar_index: int = 10,
    formed_at_bar: int = 10,
    status: str = "active",
) -> SwingNode:
    """Helper to create SwingNode objects for testing."""
    return SwingNode(
        swing_id=swing_id,
        high_bar_index=high_bar_index,
        high_price=Decimal(str(high_price)),
        low_bar_index=low_bar_index,
        low_price=Decimal(str(low_price)),
        direction=direction,
        status=status,
        formed_at_bar=formed_at_bar,
    )


class TestReferenceLayerInitialization:
    """Test ReferenceLayer initialization."""

    def test_default_config(self):
        """ReferenceLayer initializes with default config."""
        layer = ReferenceLayer()
        assert layer.config is not None
        assert layer.config.bull.big_swing_threshold == 0.10

    def test_custom_config(self):
        """ReferenceLayer accepts custom config."""
        config = SwingConfig.default().with_bull(big_swing_threshold=0.20)
        layer = ReferenceLayer(config)
        assert layer.config.bull.big_swing_threshold == 0.20


class TestRangeBasedBigSwing:
    """Test big swing detection based on range (top 10% by range = big)."""

    def test_single_swing_is_big(self):
        """Single swing is always big (top 100% = top 10%)."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)

        result = layer.get_reference_swings([swing])

        assert len(result) == 1
        assert result[0].is_big() is True

    def test_larger_swing_is_big(self):
        """Larger swing is big, smaller is not (range-based)."""
        layer = ReferenceLayer()
        large = make_swing("large", 200.0, 100.0)  # range 100
        small = make_swing("small", 170.0, 130.0)  # range 40

        result = layer.get_reference_swings([large, small])

        large_info = next((r for r in result if r.swing.swing_id == "large"), None)
        small_info = next((r for r in result if r.swing.swing_id == "small"), None)
        assert large_info.is_big() is True
        assert small_info.is_big() is False

    def test_get_big_swings_returns_top_by_range(self):
        """get_big_swings returns swings in top 10% by range."""
        layer = ReferenceLayer()
        large = make_swing("large", 200.0, 100.0)  # range 100
        small = make_swing("small", 170.0, 130.0)  # range 40

        big_swings = layer.get_big_swings([large, small])

        assert len(big_swings) == 1
        assert big_swings[0].swing_id == "large"

    def test_top_10_percent_are_big(self):
        """With 10 swings, only the top 1 (10%) is big."""
        layer = ReferenceLayer()
        # Create 10 swings with different ranges
        swings = []
        for i in range(10):
            swing = make_swing(f"s{i}", 100.0 + (i + 1) * 10, 100.0)  # ranges 10-100
            swings.append(swing)

        result = layer.get_reference_swings(swings)
        big_count = sum(1 for info in result if info.is_big())

        # Top 10% of 10 = 1 swing (the one with range 100)
        assert big_count == 1
        # The biggest swing (s9, range 100) should be big
        s9_info = next((r for r in result if r.swing.swing_id == "s9"), None)
        assert s9_info.is_big() is True


class TestRangeBasedTolerances:
    """Test invalidation tolerances based on range (top 10% = big = has tolerance)."""

    def test_big_swing_has_tolerance(self):
        """Big swings (top 10% by range) have non-zero tolerance."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # Single swing = big

        result = layer.get_reference_swings([swing])

        assert result[0].touch_tolerance == 0.15
        assert result[0].close_tolerance == 0.10

    def test_small_swing_no_tolerance(self):
        """Small swings (not in top 10% by range) have zero tolerance."""
        layer = ReferenceLayer()
        large = make_swing("large", 200.0, 100.0)  # range 100 = big
        small = make_swing("small", 170.0, 130.0)  # range 40 = small

        result = layer.get_reference_swings([large, small])

        small_info = next((r for r in result if r.swing.swing_id == "small"), None)
        assert small_info.touch_tolerance == 0.0
        assert small_info.close_tolerance == 0.0


class TestTouchInvalidation:
    """Test touch (wick) invalidation (Rule 2.2)."""

    def test_big_swing_touch_tolerance(self):
        """Big swing tolerates touch within 0.15 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # No parents = big, range 10
        layer.get_reference_swings([swing])

        # Touch 0.1 below pivot (1% of range) - should NOT invalidate
        # Tolerance is 0.15 = 1.5 points for this swing
        bar = make_bar(20, 100.0, 101.0, 99.0, 100.0)  # Low=99, 1 point below pivot

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is False

    def test_big_swing_touch_excess_invalidates(self):
        """Big swing invalidated when touch exceeds 0.15 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # No parents = big, range 10
        layer.get_reference_swings([swing])

        # Touch 2 points below pivot (20% of range) - should invalidate
        bar = make_bar(20, 100.0, 101.0, 98.0, 100.0)  # Low=98

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is True
        assert result.reason == "touch_violation"

    def test_small_swing_no_touch_tolerance(self):
        """Small swing invalidated by any touch below pivot."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        child = make_swing("child", 150.0, 140.0)  # Range 10
        child.add_parent(parent)
        layer.get_reference_swings([parent, child])

        # Any touch below pivot should invalidate small swing
        bar = make_bar(20, 140.0, 141.0, 139.9, 140.0)  # Low=139.9

        result = layer.check_invalidation(child, bar)

        assert result.is_invalidated is True


class TestCloseInvalidation:
    """Test close-based invalidation (Rule 2.2)."""

    def test_big_swing_close_tolerance(self):
        """Big swing tolerates close within 0.10 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # No parents = big, range 10
        layer.get_reference_swings([swing])

        # Close 0.05 below pivot - should NOT invalidate (tolerance is 0.10)
        bar = make_bar(20, 100.0, 101.0, 99.5, 99.5)  # Close=99.5

        result = layer.check_invalidation(swing, bar, use_close=True)

        assert result.is_invalidated is False

    def test_big_swing_close_excess_invalidates(self):
        """Big swing invalidated when close exceeds 0.10 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # No parents = big, range 10
        layer.get_reference_swings([swing])

        # Close 1.5 points below pivot (15% of range) - should invalidate
        bar = make_bar(20, 100.0, 101.0, 99.5, 98.5)  # Close=98.5

        result = layer.check_invalidation(swing, bar, use_close=True)

        assert result.is_invalidated is True
        assert result.reason == "close_violation"

    def test_touch_without_close_check(self):
        """Can disable close-based invalidation."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # No parents = big, range 10
        layer.get_reference_swings([swing])

        # Touch is valid, close is not - but close check is disabled
        bar = make_bar(20, 100.0, 101.0, 99.5, 98.5)  # Low=99.5 OK, Close=98.5 BAD

        result = layer.check_invalidation(swing, bar, use_close=False)

        # Touch is within tolerance (0.5 < 1.5), so should not invalidate
        assert result.is_invalidated is False


class TestBearSwingInvalidation:
    """Test invalidation for bear swings."""

    def test_bear_swing_touch_check(self):
        """Bear swing invalidated when high exceeds defended pivot."""
        layer = ReferenceLayer()
        # Bear swing: defending high at 110, origin at low 100
        swing = make_swing("s1", 110.0, 100.0, direction="bear")
        layer.get_reference_swings([swing])

        # High exceeds defended pivot - should invalidate
        bar = make_bar(20, 109.0, 112.0, 108.0, 109.0)  # High=112

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is True
        assert result.reason == "touch_violation"

    def test_bear_swing_within_tolerance(self):
        """Bear swing tolerates touch within tolerance."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0, direction="bear")  # No parents, range 10
        layer.get_reference_swings([swing])

        # High 1 point above pivot (10% of range) - within 0.15 tolerance
        bar = make_bar(20, 109.0, 111.0, 108.0, 109.0)  # High=111

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is False


class TestCompletion:
    """Test completion rules based on hierarchy."""

    def test_small_swing_completes_at_2x(self):
        """Small swing (has parent) completes at 2× extension."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        # Child bull swing: pivot=140, origin=150, range=10
        # 2× target = pivot + 2*(origin - pivot) = 140 + 2*10 = 160
        child = make_swing("child", 150.0, 140.0)
        child.add_parent(parent)
        layer.get_reference_swings([parent, child])

        # Bar that hits 2× target
        bar = make_bar(20, 158.0, 161.0, 157.0, 160.0)  # High=161 > 160

        result = layer.check_completion(child, bar)

        assert result.is_completed is True
        assert result.reason == "reached_2x_extension"

    def test_small_swing_not_completed_before_2x(self):
        """Small swing does not complete before reaching 2× extension."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        child = make_swing("child", 150.0, 140.0)  # 2× target = 160
        child.add_parent(parent)
        layer.get_reference_swings([parent, child])

        # Bar below 2× target
        bar = make_bar(20, 155.0, 158.0, 154.0, 157.0)  # High=158 < 160

        result = layer.check_completion(child, bar)

        assert result.is_completed is False

    def test_big_swing_never_completes(self):
        """Big swing (no parent) never completes."""
        layer = ReferenceLayer()
        # Bull swing: pivot=100, origin=110, range=10, 2× target = 120
        swing = make_swing("s1", 110.0, 100.0)  # No parents = big
        layer.get_reference_swings([swing])

        # Bar that would normally trigger 2× completion
        bar = make_bar(20, 118.0, 125.0, 117.0, 122.0)  # High=125 > 120

        result = layer.check_completion(swing, bar)

        assert result.is_completed is False

    def test_bear_small_swing_completes_at_2x(self):
        """Bear small swing completes at 2× extension (going down)."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        # Bear child: pivot=160 (high), origin=150 (low), range=10
        # 2× target = pivot - 2*(pivot - origin) = 160 - 2*10 = 140
        child = make_swing("child", 160.0, 150.0, direction="bear")
        child.add_parent(parent)
        layer.get_reference_swings([parent, child])

        # Bar that hits 2× target (going down)
        bar = make_bar(20, 142.0, 143.0, 138.0, 141.0)  # Low=138 < 140

        result = layer.check_completion(child, bar)

        assert result.is_completed is True


class TestGetReferenceSwings:
    """Test the main entry point for getting reference swings."""

    def test_get_reference_swings_returns_all(self):
        """get_reference_swings returns all swings with annotations."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        child = make_swing("child", 170.0, 130.0)
        child.add_parent(parent)
        swings = [parent, child]

        result = layer.get_reference_swings(swings)

        # Both should be returned as references
        assert len(result) == 2
        parent_info = next((r for r in result if r.swing.swing_id == "parent"), None)
        assert parent_info is not None
        child_info = next((r for r in result if r.swing.swing_id == "child"), None)
        assert child_info is not None


class TestUpdateInvalidationOnBar:
    """Test batch invalidation checking."""

    def test_returns_invalidated_swings(self):
        """update_invalidation_on_bar returns only invalidated swings."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)  # Big, has tolerance
        child = make_swing("child", 110.0, 100.0)  # Small after adding parent
        child.add_parent(parent)
        swings = [parent, child]

        # Bar that invalidates child (small, no tolerance) but not parent (big)
        # Child pivot = 100, any violation invalidates
        bar = make_bar(20, 100.0, 101.0, 99.5, 100.0)  # Low=99.5 < pivot

        result = layer.update_invalidation_on_bar(swings, bar)

        # child should be invalidated (no tolerance, low < pivot)
        invalidated_ids = [s.swing_id for s, _ in result]
        assert "child" in invalidated_ids

    def test_skips_inactive_swings(self):
        """update_invalidation_on_bar skips non-active swings."""
        layer = ReferenceLayer()
        active_swing = make_swing("active", 110.0, 100.0)
        inactive_swing = make_swing("inactive", 110.0, 100.0, status="invalidated")
        swings = [active_swing, inactive_swing]

        bar = make_bar(20, 100.0, 101.0, 98.0, 100.0)  # Violates both

        result = layer.update_invalidation_on_bar(swings, bar)

        # Only active swing should be in result
        invalidated_ids = [s.swing_id for s, _ in result]
        assert "active" in invalidated_ids
        assert "inactive" not in invalidated_ids


class TestUpdateCompletionOnBar:
    """Test batch completion checking."""

    def test_returns_completed_swings(self):
        """update_completion_on_bar returns only completed swings."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)  # Big, never completes
        # Child: pivot=140, origin=150, range=10, 2× target=160
        child = make_swing("child", 150.0, 140.0)
        child.add_parent(parent)
        swings = [parent, child]

        # Bar that reaches 2× for child
        bar = make_bar(20, 158.0, 162.0, 157.0, 161.0)  # High=162 > 160

        result = layer.update_completion_on_bar(swings, bar)

        # Only child should complete
        completed_ids = [s.swing_id for s, _ in result]
        assert "child" in completed_ids
        assert "parent" not in completed_ids

    def test_skips_inactive_swings(self):
        """update_completion_on_bar skips non-active swings."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        active_child = make_swing("active", 150.0, 140.0)
        active_child.add_parent(parent)
        inactive_child = make_swing("inactive", 150.0, 140.0, status="completed")
        inactive_child.add_parent(parent)
        swings = [parent, active_child, inactive_child]

        bar = make_bar(20, 158.0, 165.0, 157.0, 163.0)  # High=165 > 160

        result = layer.update_completion_on_bar(swings, bar)

        completed_ids = [s.swing_id for s, _ in result]
        assert "active" in completed_ids
        assert "inactive" not in completed_ids


class TestGetSwingInfo:
    """Test retrieving swing info by ID."""

    def test_get_existing_swing_info(self):
        """get_swing_info returns info for processed swing."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)
        layer.get_reference_swings([swing])

        info = layer.get_swing_info("s1")

        assert info is not None
        assert info.swing.swing_id == "s1"

    def test_get_unknown_swing_info(self):
        """get_swing_info returns None for unknown swing."""
        layer = ReferenceLayer()

        info = layer.get_swing_info("unknown")

        assert info is None


class TestEmptyInput:
    """Test edge cases with empty input."""

    def test_get_reference_swings_empty(self):
        """get_reference_swings handles empty list."""
        layer = ReferenceLayer()

        result = layer.get_reference_swings([])

        assert result == []

    def test_get_big_swings_empty(self):
        """get_big_swings handles empty list."""
        layer = ReferenceLayer()

        result = layer.get_big_swings([])

        assert result == []
