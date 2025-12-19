"""
Tests for the replay router using HierarchicalDetector.

Verifies:
- Calibration endpoint returns proper format
- Advance endpoint processes bars incrementally
- Response schemas include hierarchy info (depth, parent_ids)
"""

import pytest
from decimal import Decimal
from typing import List

from src.swing_analysis.types import Bar
from src.swing_analysis.swing_node import SwingNode
from src.swing_analysis.hierarchical_detector import HierarchicalDetector, calibrate
from src.swing_analysis.swing_config import SwingConfig
from src.ground_truth_annotator.routers.replay import (
    _depth_to_scale,
    _size_to_scale,
    _swing_node_to_calibration_response,
    _calculate_scale_thresholds,
    _build_swing_state,
    # Tree statistics helpers (Issue #166)
    _compute_tree_statistics,
    _check_siblings_exist,
    _group_swings_by_depth,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_bars() -> List[Bar]:
    """Generate sample bars for testing."""
    bars = []
    base_price = 5000.0

    for i in range(100):
        # Create some price movement
        offset = 10 * ((i % 20) - 10)  # Oscillate around base
        bars.append(Bar(
            index=i,
            timestamp=1700000000 + i * 60,
            open=base_price + offset,
            high=base_price + offset + 5,
            low=base_price + offset - 5,
            close=base_price + offset + 2,
        ))

    return bars


@pytest.fixture
def sample_swing_node() -> SwingNode:
    """Create a sample SwingNode for testing."""
    return SwingNode(
        swing_id="test1234",
        high_bar_index=10,
        high_price=Decimal("5100.00"),
        low_bar_index=20,
        low_price=Decimal("5000.00"),
        direction="bull",
        status="active",
        formed_at_bar=20,
    )


# ============================================================================
# Test Helper Functions
# ============================================================================


class TestDepthToScale:
    """Tests for _depth_to_scale helper."""

    def test_depth_0_is_xl(self):
        """Depth 0 (root) maps to XL."""
        assert _depth_to_scale(0) == "XL"

    def test_depth_1_is_l(self):
        """Depth 1 maps to L."""
        assert _depth_to_scale(1) == "L"

    def test_depth_2_is_m(self):
        """Depth 2 maps to M."""
        assert _depth_to_scale(2) == "M"

    def test_depth_3_is_s(self):
        """Depth 3 maps to S."""
        assert _depth_to_scale(3) == "S"

    def test_depth_10_is_s(self):
        """Deep depth maps to S."""
        assert _depth_to_scale(10) == "S"


class TestSizeToScale:
    """Tests for _size_to_scale helper."""

    def test_large_size_is_xl(self):
        """Large size maps to XL."""
        thresholds = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        assert _size_to_scale(150.0, thresholds) == "XL"

    def test_medium_size_is_m(self):
        """Medium size maps to M."""
        thresholds = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        assert _size_to_scale(25.0, thresholds) == "M"

    def test_small_size_is_s(self):
        """Small size maps to S."""
        thresholds = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        assert _size_to_scale(5.0, thresholds) == "S"

    def test_exact_threshold_is_xl(self):
        """Exact XL threshold maps to XL."""
        thresholds = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        assert _size_to_scale(100.0, thresholds) == "XL"


class TestSwingNodeToCalibrationResponse:
    """Tests for _swing_node_to_calibration_response."""

    def test_converts_swing_node(self, sample_swing_node):
        """Converts SwingNode to CalibrationSwingResponse."""
        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
            rank=1,
        )

        assert response.id == "test1234"
        assert response.direction == "bull"
        assert response.high_price == 5100.0
        assert response.low_price == 5000.0
        assert response.is_active is True
        assert response.rank == 1

    def test_includes_fib_levels_bull(self, sample_swing_node):
        """Bull swing has correct Fib levels."""
        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
        )

        size = 100.0  # 5100 - 5000
        assert response.fib_0 == 5000.0  # defending low
        assert response.fib_0382 == pytest.approx(5038.2)  # low + 38.2%
        assert response.fib_1 == 5100.0  # origin (high)
        assert response.fib_2 == 5200.0  # low + 200%

    def test_includes_fib_levels_bear(self):
        """Bear swing has correct Fib levels."""
        bear_swing = SwingNode(
            swing_id="bear1234",
            high_bar_index=20,
            high_price=Decimal("5100.00"),
            low_bar_index=10,
            low_price=Decimal("5000.00"),
            direction="bear",
            status="active",
            formed_at_bar=20,
        )

        response = _swing_node_to_calibration_response(
            bear_swing,
            is_active=True,
        )

        assert response.fib_0 == 5100.0  # defending high
        assert response.fib_0382 == pytest.approx(5061.8)  # high - 38.2%
        assert response.fib_1 == 5000.0  # origin (low)
        assert response.fib_2 == 4900.0  # high - 200%

    def test_includes_depth(self, sample_swing_node):
        """Response includes depth field."""
        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
        )

        assert response.depth == 0  # No parents = depth 0

    def test_includes_parent_ids(self, sample_swing_node):
        """Response includes parent_ids field."""
        # Create parent
        parent = SwingNode(
            swing_id="parent12",
            high_bar_index=5,
            high_price=Decimal("5200.00"),
            low_bar_index=15,
            low_price=Decimal("4900.00"),
            direction="bull",
            status="active",
            formed_at_bar=15,
        )
        sample_swing_node.add_parent(parent)

        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
        )

        assert "parent12" in response.parent_ids

    def test_uses_scale_thresholds_when_provided(self, sample_swing_node):
        """Uses size-based scale when thresholds provided."""
        thresholds = {"XL": 200.0, "L": 100.0, "M": 50.0, "S": 0.0}

        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
            scale_thresholds=thresholds,
        )

        # Size is 100, which is >= L threshold
        assert response.scale == "L"


class TestCalculateScaleThresholds:
    """Tests for _calculate_scale_thresholds."""

    def test_empty_input_returns_defaults(self):
        """Empty input returns default thresholds."""
        result = _calculate_scale_thresholds([])

        assert "XL" in result
        assert "L" in result
        assert "M" in result
        assert "S" in result
        assert result["S"] == 0.0

    def test_single_swing(self):
        """Single swing calculates thresholds."""
        swing = SwingNode(
            swing_id="single",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=20,
        )

        result = _calculate_scale_thresholds([swing])

        # With single swing, all percentile thresholds = same value
        assert result["XL"] == 100.0
        assert result["S"] == 0.0

    def test_multiple_swings_distribution(self):
        """Multiple swings create percentile-based thresholds."""
        swings = []
        for i, size in enumerate([10, 20, 30, 40, 50, 60, 70, 80, 90, 100]):
            swings.append(SwingNode(
                swing_id=f"swing{i}",
                high_bar_index=10,
                high_price=Decimal(str(5000 + size)),
                low_bar_index=20,
                low_price=Decimal("5000.00"),
                direction="bull",
                status="active",
                formed_at_bar=20,
            ))

        result = _calculate_scale_thresholds(swings)

        # XL should be ~top 10% = largest
        assert result["XL"] >= 90.0
        # S should always be 0
        assert result["S"] == 0.0


class TestBuildSwingState:
    """Tests for _build_swing_state."""

    def test_groups_by_scale(self):
        """Builds ReplaySwingState grouped by scale."""
        swings = [
            SwingNode(
                swing_id="xl_swing",
                high_bar_index=10,
                high_price=Decimal("5200.00"),
                low_bar_index=20,
                low_price=Decimal("5000.00"),  # size=200
                direction="bull",
                status="active",
                formed_at_bar=20,
            ),
            SwingNode(
                swing_id="s_swing",
                high_bar_index=10,
                high_price=Decimal("5010.00"),
                low_bar_index=20,
                low_price=Decimal("5000.00"),  # size=10
                direction="bull",
                status="active",
                formed_at_bar=20,
            ),
        ]

        thresholds = {"XL": 100.0, "L": 50.0, "M": 20.0, "S": 0.0}
        result = _build_swing_state(swings, thresholds)

        assert len(result.XL) == 1
        assert result.XL[0].id == "xl_swing"
        assert len(result.S) == 1
        assert result.S[0].id == "s_swing"


# ============================================================================
# Test HierarchicalDetector Integration
# ============================================================================


class TestHierarchicalDetectorIntegration:
    """Tests for HierarchicalDetector usage in replay."""

    def test_calibrate_returns_detector_and_events(self, sample_bars):
        """calibrate() returns tuple of (detector, events)."""
        detector, events = calibrate(sample_bars)

        assert isinstance(detector, HierarchicalDetector)
        assert isinstance(events, list)

    def test_detector_process_bar_returns_events(self, sample_bars):
        """process_bar() returns list of events."""
        detector, _ = calibrate(sample_bars[:50])

        events = detector.process_bar(sample_bars[50])

        assert isinstance(events, list)

    def test_get_active_swings_returns_swing_nodes(self, sample_bars):
        """get_active_swings() returns SwingNode list."""
        detector, _ = calibrate(sample_bars)

        active = detector.get_active_swings()

        assert isinstance(active, list)
        for swing in active:
            assert isinstance(swing, SwingNode)

    def test_calibration_then_advance(self, sample_bars):
        """Can calibrate then advance incrementally."""
        # Calibrate on first 80 bars
        detector, cal_events = calibrate(sample_bars[:80])
        initial_count = len(detector.get_active_swings())

        # Advance through remaining bars
        advance_events = []
        for bar in sample_bars[80:]:
            events = detector.process_bar(bar)
            advance_events.extend(events)

        # Should have processed all bars
        assert detector.state.last_bar_index == 99
        # Events were generated
        assert len(cal_events) + len(advance_events) >= 0  # May or may not have events


# ============================================================================
# Test Response Schema Compatibility
# ============================================================================


class TestResponseSchemaCompatibility:
    """Tests that responses maintain frontend compatibility."""

    def test_calibration_response_has_legacy_scales(self, sample_swing_node):
        """CalibrationSwingResponse has scale field."""
        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
        )

        assert hasattr(response, 'scale')
        assert response.scale in ["XL", "L", "M", "S"]

    def test_calibration_response_has_hierarchy_info(self, sample_swing_node):
        """CalibrationSwingResponse has depth and parent_ids."""
        response = _swing_node_to_calibration_response(
            sample_swing_node,
            is_active=True,
        )

        assert hasattr(response, 'depth')
        assert hasattr(response, 'parent_ids')
        assert isinstance(response.depth, int)
        assert isinstance(response.parent_ids, list)

    def test_swing_state_has_all_scales(self):
        """ReplaySwingState has XL, L, M, S fields."""
        swings = []
        thresholds = {"XL": 100.0, "L": 50.0, "M": 20.0, "S": 0.0}

        result = _build_swing_state(swings, thresholds)

        assert hasattr(result, 'XL')
        assert hasattr(result, 'L')
        assert hasattr(result, 'M')
        assert hasattr(result, 'S')


# ============================================================================
# Test Tree Statistics (Issue #166)
# ============================================================================


class TestComputeTreeStatistics:
    """Tests for _compute_tree_statistics helper."""

    def test_empty_swings_returns_defaults(self):
        """Empty input returns default stats."""
        result = _compute_tree_statistics([], [], 1000)

        assert result.root_swings == 0
        assert result.total_nodes == 0
        assert result.max_depth == 0
        assert result.avg_children == 0.0

    def test_single_root_swing(self):
        """Single swing is counted as root."""
        swing = SwingNode(
            swing_id="root1",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=20,
        )

        result = _compute_tree_statistics([swing], [swing], 1000)

        assert result.root_swings == 1
        assert result.root_bull == 1
        assert result.root_bear == 0
        assert result.total_nodes == 1
        assert result.max_depth == 0

    def test_counts_root_directions(self):
        """Counts bull and bear roots separately."""
        bull_swing = SwingNode(
            swing_id="bull1",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=20,
        )
        bear_swing = SwingNode(
            swing_id="bear1",
            high_bar_index=30,
            high_price=Decimal("5200.00"),
            low_bar_index=40,
            low_price=Decimal("5050.00"),
            direction="bear",
            status="active",
            formed_at_bar=40,
        )

        result = _compute_tree_statistics([bull_swing, bear_swing], [bull_swing], 1000)

        assert result.root_swings == 2
        assert result.root_bull == 1
        assert result.root_bear == 1

    def test_computes_avg_children(self):
        """Computes average children per node."""
        parent = SwingNode(
            swing_id="parent1",
            high_bar_index=10,
            high_price=Decimal("5200.00"),
            low_bar_index=50,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=50,
        )
        child1 = SwingNode(
            swing_id="child1",
            high_bar_index=15,
            high_price=Decimal("5150.00"),
            low_bar_index=25,
            low_price=Decimal("5050.00"),
            direction="bull",
            status="active",
            formed_at_bar=25,
        )
        child2 = SwingNode(
            swing_id="child2",
            high_bar_index=30,
            high_price=Decimal("5120.00"),
            low_bar_index=40,
            low_price=Decimal("5040.00"),
            direction="bull",
            status="active",
            formed_at_bar=40,
        )
        child1.add_parent(parent)
        child2.add_parent(parent)

        result = _compute_tree_statistics([parent, child1, child2], [parent], 1000)

        # parent has 2 children, child1 and child2 have 0 each
        # avg = 2 / 3 = 0.7 (rounded to 1 decimal)
        assert result.avg_children == 0.7

    def test_computes_range_distribution(self):
        """Computes largest, median, smallest ranges."""
        swings = [
            SwingNode(
                swing_id=f"swing{i}",
                high_bar_index=10 + i * 10,
                high_price=Decimal(str(5000 + size)),
                low_bar_index=15 + i * 10,
                low_price=Decimal("5000.00"),
                direction="bull",
                status="active",
                formed_at_bar=15 + i * 10,
            )
            for i, size in enumerate([10, 50, 100])  # sizes: 10, 50, 100
        ]

        result = _compute_tree_statistics(swings, [], 1000)

        assert result.largest_range == 100.0
        assert result.median_range == 50.0
        assert result.smallest_range == 10.0

    def test_defended_by_depth(self):
        """Groups defended swings by depth."""
        # Create parent and child
        parent = SwingNode(
            swing_id="parent1",
            high_bar_index=10,
            high_price=Decimal("5200.00"),
            low_bar_index=50,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=50,
        )
        child = SwingNode(
            swing_id="child1",
            high_bar_index=15,
            high_price=Decimal("5150.00"),
            low_bar_index=25,
            low_price=Decimal("5050.00"),
            direction="bull",
            status="active",
            formed_at_bar=25,
        )
        child.add_parent(parent)

        result = _compute_tree_statistics([parent, child], [parent, child], 1000)

        assert result.defended_by_depth["1"] == 1  # parent at depth 0
        assert result.defended_by_depth["2"] == 1  # child at depth 1

    def test_validation_roots_have_children(self):
        """Validates that root swings have children."""
        # Root without children
        root_no_child = SwingNode(
            swing_id="root1",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=20,
        )

        result = _compute_tree_statistics([root_no_child], [], 1000)
        assert result.roots_have_children is False

        # Root with children
        root_with_child = SwingNode(
            swing_id="root2",
            high_bar_index=10,
            high_price=Decimal("5200.00"),
            low_bar_index=50,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=50,
        )
        child = SwingNode(
            swing_id="child1",
            high_bar_index=15,
            high_price=Decimal("5150.00"),
            low_bar_index=25,
            low_price=Decimal("5050.00"),
            direction="bull",
            status="active",
            formed_at_bar=25,
        )
        child.add_parent(root_with_child)

        result2 = _compute_tree_statistics([root_with_child, child], [], 1000)
        assert result2.roots_have_children is True


class TestCheckSiblingsExist:
    """Tests for _check_siblings_exist helper."""

    def test_no_siblings_single_swing(self):
        """Single swing has no siblings."""
        swing = SwingNode(
            swing_id="single",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=20,
        )

        assert _check_siblings_exist([swing]) is False

    def test_siblings_same_pivot_different_origin(self):
        """Swings with same defended pivot but different origins are siblings."""
        # Two bull swings defending the same low (5000) but different highs
        sibling1 = SwingNode(
            swing_id="sibling1",
            high_bar_index=10,
            high_price=Decimal("5100.00"),  # origin 1
            low_bar_index=20,
            low_price=Decimal("5000.00"),  # defended pivot
            direction="bull",
            status="active",
            formed_at_bar=20,
        )
        sibling2 = SwingNode(
            swing_id="sibling2",
            high_bar_index=15,
            high_price=Decimal("5150.00"),  # origin 2 (different)
            low_bar_index=20,
            low_price=Decimal("5000.00"),  # same defended pivot
            direction="bull",
            status="active",
            formed_at_bar=25,
        )

        assert _check_siblings_exist([sibling1, sibling2]) is True

    def test_not_siblings_different_pivot(self):
        """Swings with different defended pivots are not siblings."""
        swing1 = SwingNode(
            swing_id="swing1",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),  # pivot 1
            direction="bull",
            status="active",
            formed_at_bar=20,
        )
        swing2 = SwingNode(
            swing_id="swing2",
            high_bar_index=30,
            high_price=Decimal("5200.00"),
            low_bar_index=40,
            low_price=Decimal("5050.00"),  # pivot 2 (different)
            direction="bull",
            status="active",
            formed_at_bar=40,
        )

        assert _check_siblings_exist([swing1, swing2]) is False


class TestGroupSwingsByDepth:
    """Tests for _group_swings_by_depth helper."""

    def test_empty_swings(self):
        """Empty input returns empty groups."""
        thresholds = {"XL": 100.0, "L": 50.0, "M": 20.0, "S": 0.0}
        result = _group_swings_by_depth([], thresholds)

        assert result.depth_1 == []
        assert result.depth_2 == []
        assert result.depth_3 == []
        assert result.deeper == []

    def test_root_swing_in_depth_1(self):
        """Root swing (no parents) goes to depth_1."""
        swing = SwingNode(
            swing_id="root1",
            high_bar_index=10,
            high_price=Decimal("5100.00"),
            low_bar_index=20,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=20,
        )
        thresholds = {"XL": 100.0, "L": 50.0, "M": 20.0, "S": 0.0}

        result = _group_swings_by_depth([swing], thresholds)

        assert len(result.depth_1) == 1
        assert result.depth_1[0].id == "root1"

    def test_child_swing_in_depth_2(self):
        """Child swing (depth 1) goes to depth_2."""
        parent = SwingNode(
            swing_id="parent1",
            high_bar_index=10,
            high_price=Decimal("5200.00"),
            low_bar_index=50,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=50,
        )
        child = SwingNode(
            swing_id="child1",
            high_bar_index=15,
            high_price=Decimal("5150.00"),
            low_bar_index=25,
            low_price=Decimal("5050.00"),
            direction="bull",
            status="active",
            formed_at_bar=25,
        )
        child.add_parent(parent)
        thresholds = {"XL": 100.0, "L": 50.0, "M": 20.0, "S": 0.0}

        result = _group_swings_by_depth([parent, child], thresholds)

        assert len(result.depth_1) == 1  # parent
        assert len(result.depth_2) == 1  # child
        assert result.depth_1[0].id == "parent1"
        assert result.depth_2[0].id == "child1"

    def test_deep_swing_in_deeper(self):
        """Deep swings (depth 3+) go to deeper group."""
        # Create chain: root -> child1 -> child2 -> child3 (depth 3)
        root = SwingNode(
            swing_id="root",
            high_bar_index=10,
            high_price=Decimal("5300.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=100,
        )
        child1 = SwingNode(
            swing_id="child1",
            high_bar_index=20,
            high_price=Decimal("5250.00"),
            low_bar_index=40,
            low_price=Decimal("5050.00"),
            direction="bull",
            status="active",
            formed_at_bar=40,
        )
        child2 = SwingNode(
            swing_id="child2",
            high_bar_index=50,
            high_price=Decimal("5200.00"),
            low_bar_index=70,
            low_price=Decimal("5100.00"),
            direction="bull",
            status="active",
            formed_at_bar=70,
        )
        child3 = SwingNode(
            swing_id="child3",
            high_bar_index=75,
            high_price=Decimal("5150.00"),
            low_bar_index=85,
            low_price=Decimal("5120.00"),
            direction="bull",
            status="active",
            formed_at_bar=85,
        )
        child1.add_parent(root)
        child2.add_parent(child1)
        child3.add_parent(child2)

        thresholds = {"XL": 100.0, "L": 50.0, "M": 20.0, "S": 0.0}

        result = _group_swings_by_depth([root, child1, child2, child3], thresholds)

        assert len(result.depth_1) == 1  # root (depth 0)
        assert len(result.depth_2) == 1  # child1 (depth 1)
        assert len(result.depth_3) == 1  # child2 (depth 2)
        assert len(result.deeper) == 1   # child3 (depth 3)
        assert result.deeper[0].id == "child3"
