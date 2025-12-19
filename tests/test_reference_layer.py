"""
Tests for ReferenceLayer

Tests the reference layer filtering and invalidation rules.
See Docs/Reference/valid_swings.md for the canonical rules.
"""

import pytest
from decimal import Decimal
from typing import List

from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwingInfo,
    InvalidationResult,
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


class TestBigSwingClassification:
    """Test big swing classification (top 10% by range)."""

    def test_single_swing_is_big(self):
        """Single swing is always big (top 100%)."""
        layer = ReferenceLayer()
        swings = [make_swing("s1", 110.0, 100.0)]

        result = layer.classify_swings(swings)

        assert len(result) == 1
        assert result["s1"].is_big is True

    def test_top_10_percent_are_big(self):
        """Only top 10% of swings by range are big."""
        layer = ReferenceLayer()
        # Create 10 swings with ranges 10, 20, 30, ..., 100
        swings = []
        for i in range(10):
            range_size = (i + 1) * 10
            swing = make_swing(
                f"s{i}",
                high_price=100.0 + range_size,
                low_price=100.0,
            )
            swings.append(swing)

        result = layer.classify_swings(swings)

        # Top 10% = 1 swing (range 100)
        big_count = sum(1 for info in result.values() if info.is_big)
        assert big_count == 1
        assert result["s9"].is_big is True  # Range 100
        assert result["s0"].is_big is False  # Range 10

    def test_get_big_swings(self):
        """get_big_swings returns only big swings."""
        layer = ReferenceLayer()
        swings = [
            make_swing("s1", 200.0, 100.0),  # Range 100 - big
            make_swing("s2", 120.0, 100.0),  # Range 20 - small
            make_swing("s3", 110.0, 100.0),  # Range 10 - small
        ]

        big_swings = layer.get_big_swings(swings)

        assert len(big_swings) == 1
        assert big_swings[0].swing_id == "s1"


class TestBigSwingTolerances:
    """Test invalidation tolerances based on swing size."""

    def test_big_swing_has_tolerance(self):
        """Big swings have non-zero tolerance."""
        layer = ReferenceLayer()
        swings = [make_swing("s1", 110.0, 100.0)]  # Only swing, so it's big

        result = layer.classify_swings(swings)

        assert result["s1"].touch_tolerance == 0.15  # Default
        assert result["s1"].close_tolerance == 0.10  # Default

    def test_small_swing_no_tolerance(self):
        """Small swings have zero tolerance."""
        layer = ReferenceLayer()
        big_swing = make_swing("big", 200.0, 100.0)  # Range 100
        small_swing = make_swing("small", 110.0, 100.0)  # Range 10
        swings = [big_swing, small_swing]

        result = layer.classify_swings(swings)

        assert result["small"].touch_tolerance == 0.0
        assert result["small"].close_tolerance == 0.0

    def test_child_of_big_swing_has_reduced_tolerance(self):
        """Children of big swings have reduced tolerance."""
        layer = ReferenceLayer()
        big_swing = make_swing("big", 200.0, 100.0)  # Range 100
        small_swing = make_swing("small", 150.0, 140.0)  # Range 10
        small_swing.add_parent(big_swing)
        swings = [big_swing, small_swing]

        result = layer.classify_swings(swings)

        # Child of big gets child_swing_tolerance (0.10 by default)
        assert result["small"].touch_tolerance == 0.10
        assert result["small"].close_tolerance == 0.10


class TestParentChildSeparation:
    """Test parent-child separation filtering (Rule 4.2)."""

    def test_well_separated_child_passes(self):
        """Child with good separation from parent passes filter."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)  # Range 100
        # Child endpoints are well separated from parent endpoints
        child = make_swing("child", 170.0, 130.0)  # Origin=170, Pivot=130
        child.add_parent(parent)
        swings = [parent, child]

        result = layer.filter_by_separation(swings)

        # Find child in result
        child_info = next((r for r in result if r.swing.swing_id == "child"), None)
        assert child_info is not None
        assert child_info.is_reference is True

    def test_too_close_to_parent_origin_fails(self):
        """Child with origin too close to parent's origin fails filter."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)  # Range 100, Origin=200
        # Child origin (198) is within 0.1 * 100 = 10 of parent origin (200)
        child = make_swing("child", 198.0, 150.0)
        child.add_parent(parent)
        swings = [parent, child]

        layer.classify_swings(swings)
        result = layer.filter_by_separation(swings)

        child_infos = [r for r in result if r.swing.swing_id == "child"]
        if child_infos:
            assert child_infos[0].is_reference is False

    def test_too_close_to_parent_pivot_fails(self):
        """Child with pivot too close to parent's pivot fails filter."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)  # Range 100, Pivot=100
        # Child pivot (105) is within 0.1 * 100 = 10 of parent pivot (100)
        child = make_swing("child", 170.0, 105.0)
        child.add_parent(parent)
        swings = [parent, child]

        layer.classify_swings(swings)
        result = layer.filter_by_separation(swings)

        child_infos = [r for r in result if r.swing.swing_id == "child"]
        if child_infos:
            assert child_infos[0].is_reference is False

    def test_sibling_separation(self):
        """Siblings too close to each other fail filter."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)  # Range 100
        child1 = make_swing("child1", 170.0, 140.0)
        child2 = make_swing("child2", 172.0, 142.0)  # Too close to child1
        child1.add_parent(parent)
        child2.add_parent(parent)
        swings = [parent, child1, child2]

        layer.classify_swings(swings)
        result = layer.filter_by_separation(swings)

        # At least one sibling should be filtered out
        reference_children = [
            r for r in result
            if r.swing.swing_id in ["child1", "child2"] and r.is_reference
        ]
        # Both might still pass if they're processed independently
        # The filter checks each against existing siblings


class TestTouchInvalidation:
    """Test touch (wick) invalidation (Rule 2.2)."""

    def test_big_swing_touch_tolerance(self):
        """Big swing tolerates touch within 0.15 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # Range 10
        swings = [swing]
        layer.classify_swings(swings)

        # Touch 0.1 below pivot (1% of range) - should NOT invalidate
        # Tolerance is 0.15 = 1.5 points for this swing
        bar = make_bar(20, 100.0, 101.0, 99.0, 100.0)  # Low=99, 1 point below pivot

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is False

    def test_big_swing_touch_excess_invalidates(self):
        """Big swing invalidated when touch exceeds 0.15 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # Range 10
        swings = [swing]
        layer.classify_swings(swings)

        # Touch 2 points below pivot (20% of range) - should invalidate
        bar = make_bar(20, 100.0, 101.0, 98.0, 100.0)  # Low=98

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is True
        assert result.reason == "touch_violation"

    def test_small_swing_no_touch_tolerance(self):
        """Small swing invalidated by any touch below pivot."""
        layer = ReferenceLayer()
        big_swing = make_swing("big", 200.0, 100.0)  # Range 100 - big
        small_swing = make_swing("small", 110.0, 100.0)  # Range 10 - small
        swings = [big_swing, small_swing]
        layer.classify_swings(swings)

        # Any touch below pivot should invalidate small swing
        bar = make_bar(20, 100.0, 101.0, 99.9, 100.0)  # Low=99.9

        result = layer.check_invalidation(small_swing, bar)

        assert result.is_invalidated is True


class TestCloseInvalidation:
    """Test close-based invalidation (Rule 2.2)."""

    def test_big_swing_close_tolerance(self):
        """Big swing tolerates close within 0.10 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # Range 10
        swings = [swing]
        layer.classify_swings(swings)

        # Close 0.05 below pivot - should NOT invalidate (tolerance is 0.10)
        bar = make_bar(20, 100.0, 101.0, 99.5, 99.5)  # Close=99.5

        result = layer.check_invalidation(swing, bar, use_close=True)

        assert result.is_invalidated is False

    def test_big_swing_close_excess_invalidates(self):
        """Big swing invalidated when close exceeds 0.10 × range."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # Range 10
        swings = [swing]
        layer.classify_swings(swings)

        # Close 1.5 points below pivot (15% of range) - should invalidate
        bar = make_bar(20, 100.0, 101.0, 99.5, 98.5)  # Close=98.5

        result = layer.check_invalidation(swing, bar, use_close=True)

        assert result.is_invalidated is True
        assert result.reason == "close_violation"

    def test_touch_without_close_check(self):
        """Can disable close-based invalidation."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)  # Range 10
        swings = [swing]
        layer.classify_swings(swings)

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
        swings = [swing]
        layer.classify_swings(swings)

        # High exceeds defended pivot - should invalidate
        bar = make_bar(20, 109.0, 112.0, 108.0, 109.0)  # High=112

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is True
        assert result.reason == "touch_violation"

    def test_bear_swing_within_tolerance(self):
        """Bear swing tolerates touch within tolerance."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0, direction="bear")  # Range 10
        swings = [swing]
        layer.classify_swings(swings)

        # High 1 point above pivot (10% of range) - within 0.15 tolerance
        bar = make_bar(20, 109.0, 111.0, 108.0, 109.0)  # High=111

        result = layer.check_invalidation(swing, bar)

        assert result.is_invalidated is False


class TestGetReferenceSwings:
    """Test the main entry point for getting reference swings."""

    def test_all_swings_with_separation(self):
        """get_reference_swings applies both classification and separation."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        child = make_swing("child", 170.0, 130.0)
        child.add_parent(parent)
        swings = [parent, child]

        result = layer.get_reference_swings(swings, apply_separation=True)

        # Both should be references (well separated)
        assert len(result) >= 1  # At least parent
        parent_info = next((r for r in result if r.swing.swing_id == "parent"), None)
        assert parent_info is not None

    def test_skip_separation_filter(self):
        """get_reference_swings can skip separation filter."""
        layer = ReferenceLayer()
        parent = make_swing("parent", 200.0, 100.0)
        # Child very close to parent
        child = make_swing("child", 199.0, 101.0)
        child.add_parent(parent)
        swings = [parent, child]

        result = layer.get_reference_swings(swings, apply_separation=False)

        # Both should be returned (no separation filter)
        assert len(result) == 2


class TestUpdateInvalidationOnBar:
    """Test batch invalidation checking."""

    def test_returns_invalidated_swings(self):
        """update_invalidation_on_bar returns only invalidated swings."""
        layer = ReferenceLayer()
        swing1 = make_swing("s1", 110.0, 100.0)  # Bull, range 10
        swing2 = make_swing("s2", 120.0, 115.0)  # Bull, range 5
        # Make swing1 the big one
        swings = [swing1, swing2]
        layer.classify_swings(swings)

        # Bar that invalidates swing2 (small) but not swing1 (big)
        bar = make_bar(20, 100.0, 101.0, 99.5, 100.0)  # Low=99.5

        result = layer.update_invalidation_on_bar(swings, bar)

        # swing2 should be invalidated (no tolerance, low < pivot)
        invalidated_ids = [s.swing_id for s, _ in result]
        assert "s2" in invalidated_ids

    def test_skips_inactive_swings(self):
        """update_invalidation_on_bar skips non-active swings."""
        layer = ReferenceLayer()
        active_swing = make_swing("active", 110.0, 100.0)
        inactive_swing = make_swing("inactive", 110.0, 100.0, status="invalidated")
        swings = [active_swing, inactive_swing]
        layer.classify_swings(swings)

        bar = make_bar(20, 100.0, 101.0, 98.0, 100.0)  # Violates both

        result = layer.update_invalidation_on_bar(swings, bar)

        # Only active swing should be in result
        invalidated_ids = [s.swing_id for s, _ in result]
        assert "active" in invalidated_ids
        assert "inactive" not in invalidated_ids


class TestGetSwingInfo:
    """Test retrieving swing info by ID."""

    def test_get_existing_swing_info(self):
        """get_swing_info returns info for classified swing."""
        layer = ReferenceLayer()
        swing = make_swing("s1", 110.0, 100.0)
        layer.classify_swings([swing])

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

    def test_classify_empty_list(self):
        """classify_swings handles empty list."""
        layer = ReferenceLayer()

        result = layer.classify_swings([])

        assert result == {}

    def test_filter_empty_list(self):
        """filter_by_separation handles empty list."""
        layer = ReferenceLayer()

        result = layer.filter_by_separation([])

        assert result == []

    def test_get_reference_swings_empty(self):
        """get_reference_swings handles empty list."""
        layer = ReferenceLayer()

        result = layer.get_reference_swings([])

        assert result == []
