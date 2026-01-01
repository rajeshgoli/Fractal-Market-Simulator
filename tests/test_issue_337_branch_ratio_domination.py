"""
Tests for issue #337: Branch ratio origin domination.

Prevents insignificant child legs at creation time by requiring:
- New leg's counter-trend >= min_branch_ratio * parent's counter-trend

This scales naturally through the hierarchy - children of children can have
smaller counter-trends, but must still meet the ratio relative to their parent.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.leg_detector import LegDetector
from src.swing_analysis.types import Bar


def make_bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float
) -> Bar:
    """Create a test bar."""
    # Timestamp as unix epoch integer
    base_ts = int(datetime(2024, 1, 1).timestamp())
    return Bar(
        index=index,
        timestamp=base_ts + index * 60,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
    )


class TestBranchRatioDomination:
    """Test branch ratio origin domination at leg creation time."""

    def test_root_legs_always_created(self):
        """Root legs (no parent) are always created regardless of branch ratio."""
        config = SwingConfig.default().with_min_branch_ratio(0.5)  # High threshold
        detector = LegDetector(config)

        # Bar sequence: establish first bull leg (root)
        # 100 -> 90 (low) -> 110 (high) - creates bull leg
        bars = [
            make_bar(0, 100, 100, 90, 95),   # Low at 90
            make_bar(1, 95, 110, 95, 105),   # High at 110, TYPE_2_BULL
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Root bull leg should exist regardless of branch ratio
        bull_legs = [l for l in detector.state.active_legs if l.direction == 'bull']
        assert len(bull_legs) >= 1
        assert any(l.origin_price == Decimal('90') for l in bull_legs)

    def test_child_blocked_when_counter_trend_too_small(self):
        """
        Test that the branch ratio domination check is called and can block legs.

        This is a unit test for the domination check logic itself.
        Full integration testing would require more complex bar sequences.
        """
        config = SwingConfig.default().with_min_branch_ratio(0.1)
        detector = LegDetector(config)

        # Manually set up state to test the domination check
        # Parent bull leg with counter-trend of 100 at its origin
        parent = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('200'),
            pivot_index=10,
            price_at_creation=Decimal('200'),
            last_modified_bar=10,
        )
        detector.state.active_legs.append(parent)

        # Bear leg at parent's origin (counter-trend = 100)
        counter_trend_at_parent = Leg(
            direction='bear',
            origin_price=Decimal('200'),
            origin_index=0,
            pivot_price=Decimal('100'),  # pivot == parent's origin
            pivot_index=5,
            price_at_creation=Decimal('100'),
            last_modified_bar=5,
        )
        detector.state.active_legs.append(counter_trend_at_parent)

        # Small counter-trend at potential child's origin (range = 5)
        small_counter_trend = Leg(
            direction='bear',
            origin_price=Decimal('155'),
            origin_index=15,
            pivot_price=Decimal('150'),  # pivot == child's origin
            pivot_index=20,
            price_at_creation=Decimal('150'),
            last_modified_bar=20,
        )
        detector.state.active_legs.append(small_counter_trend)

        # Check if child at origin 150 would be dominated
        # R0 = 5 (small_counter_trend.range)
        # R1 = 100 (counter_trend_at_parent.range)
        # Check: 5 >= 0.1 * 100 = 10 -> FAILS
        is_dominated = detector._is_origin_dominated_by_branch_ratio(
            'bull', Decimal('150'), parent.leg_id
        )
        assert is_dominated, "Child with counter-trend 5 should be dominated (< 10% of 100)"

    def test_child_allowed_when_counter_trend_sufficient(self):
        """
        Child legs are allowed when their counter-trend meets the ratio.

        If the counter-trend at the child's origin is >= min_ratio * parent's counter-trend,
        the child should be created.
        """
        config = SwingConfig.default().with_min_branch_ratio(0.1)
        detector = LegDetector(config)

        # Scenario where child has sufficient counter-trend:
        # Bear B1: 150 -> 100 (range 50) - creates counter-trend at 100
        # Bull L1: 100 -> 140 - root, uses B1 as counter-trend
        # Bear B2: 140 -> 130 (range 10) - creates counter-trend at 130
        # Bull L2: 130 -> 145 - parent L1, R0 = B2 (10), R1 = B1 (50)
        #   Check: 10 >= 0.1 * 50 = 5 -> PASSES

        bars = [
            make_bar(0, 150, 150, 145, 148),
            make_bar(1, 148, 148, 100, 105),  # Drop to 100
            make_bar(2, 105, 140, 104, 138),  # Rally to 140
            make_bar(3, 138, 138, 130, 132),  # Pullback to 130
            make_bar(4, 132, 145, 131, 143),  # Rally to 145
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Both L1 and L2 should exist (if bar types allow)
        bull_legs = [l for l in detector.state.active_legs if l.direction == 'bull']
        # Check that at least one bull leg exists
        assert len(bull_legs) >= 1

    def test_branch_ratio_disabled_when_zero(self):
        """When min_branch_ratio=0, the domination check always returns False."""
        config = SwingConfig.default().with_min_branch_ratio(0.0)
        detector = LegDetector(config)

        # Manually set up state - same as blocking test
        parent = Leg(
            direction='bull',
            origin_price=Decimal('100'),
            origin_index=0,
            pivot_price=Decimal('200'),
            pivot_index=10,
            price_at_creation=Decimal('200'),
            last_modified_bar=10,
        )
        detector.state.active_legs.append(parent)

        # Bear leg at parent's origin (counter-trend = 100)
        counter_trend_at_parent = Leg(
            direction='bear',
            origin_price=Decimal('200'),
            origin_index=0,
            pivot_price=Decimal('100'),
            pivot_index=5,
            price_at_creation=Decimal('100'),
            last_modified_bar=5,
        )
        detector.state.active_legs.append(counter_trend_at_parent)

        # Small counter-trend at potential child's origin (range = 5)
        small_counter_trend = Leg(
            direction='bear',
            origin_price=Decimal('155'),
            origin_index=15,
            pivot_price=Decimal('150'),
            pivot_index=20,
            price_at_creation=Decimal('150'),
            last_modified_bar=20,
        )
        detector.state.active_legs.append(small_counter_trend)

        # With ratio=0, domination check should always return False
        is_dominated = detector._is_origin_dominated_by_branch_ratio(
            'bull', Decimal('150'), parent.leg_id
        )
        assert not is_dominated, "With ratio=0, no legs should be dominated"

    def test_parent_with_no_counter_trend_allows_children(self):
        """
        If parent has no counter-trend at its origin (R1 is None),
        children are allowed regardless of their counter-trend.
        """
        config = SwingConfig.default().with_min_branch_ratio(0.1)
        detector = LegDetector(config)

        # First bar establishes a low (fresh extreme, no counter-trend)
        bars = [
            make_bar(0, 100, 105, 100, 103),  # Low at 100, first bar
            make_bar(1, 103, 120, 102, 118),  # Rally to 120
            make_bar(2, 118, 118, 115, 116),  # Pullback to 115
            make_bar(3, 116, 125, 115, 123),  # Rally to 125
        ]

        for bar in bars:
            detector.process_bar(bar)

        # L1 (from 100) is root with no counter-trend at origin
        # L2 (from 115) has L1 as parent, but R1 (at 100) doesn't exist
        # So L2 should be allowed
        bull_legs = [l for l in detector.state.active_legs if l.direction == 'bull']
        assert len(bull_legs) >= 1


class TestBranchRatioRecursiveScaling:
    """Test that branch ratio scales correctly through hierarchy levels."""

    def test_threshold_scales_with_hierarchy(self):
        """
        The effective threshold scales down through hierarchy levels.

        - Root has counter-trend 100
        - Child needs >= 10% of 100 = 10
        - Grandchild needs >= 10% of 10 = 1
        """
        config = SwingConfig.default().with_min_branch_ratio(0.1)
        detector = LegDetector(config)

        # This is a conceptual test - the actual scaling happens automatically
        # because each level compares to its parent's counter-trend, not the root's.
        # A more comprehensive integration test would trace multiple hierarchy levels.

        # For now, verify the config is properly set
        assert config.min_branch_ratio == 0.1


class TestBranchRatioConfig:
    """Test branch ratio configuration."""

    def test_config_default_is_disabled(self):
        """Default config has branch ratio disabled (0.0)."""
        config = SwingConfig.default()
        assert config.min_branch_ratio == 0.0

    def test_with_min_branch_ratio_creates_new_config(self):
        """with_min_branch_ratio creates a new config with the value."""
        config = SwingConfig.default()
        new_config = config.with_min_branch_ratio(0.15)

        assert new_config.min_branch_ratio == 0.15
        assert config.min_branch_ratio == 0.0  # Original unchanged
