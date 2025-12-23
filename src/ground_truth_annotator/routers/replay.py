"""
Replay router using LegDetector.

Provides endpoints for Replay View functionality:
- GET /api/swings/windowed - Get windowed swing detection
- GET /api/replay/calibrate - Run calibration for Replay View
- POST /api/replay/advance - Advance playback
- POST /api/playback/feedback - Submit playback feedback

Uses LegDetector for incremental swing detection with hierarchical
parent relationships. Maintains backward compatibility with legacy S/M/L/XL
scale format by mapping depth to scale.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query

from ...swing_analysis.dag import (
    LegDetector,
    HierarchicalDetector,  # Backward compatibility alias
    calibrate,
)
from ...swing_analysis.swing_config import SwingConfig
from ...swing_analysis.swing_node import SwingNode
from ...swing_analysis.events import (
    SwingEvent,
    SwingFormedEvent,
    SwingInvalidatedEvent,
    SwingCompletedEvent,
    LevelCrossEvent,
    LegCreatedEvent,
    LegPrunedEvent,
    LegInvalidatedEvent,
    OriginBreachedEvent,
    PivotBreachedEvent,
)
from ...swing_analysis.types import Bar
from ...swing_analysis.reference_frame import ReferenceFrame
from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceSwingInfo
from ...swing_analysis.bar_aggregator import BarAggregator
from ..schemas import (
    BarResponse,
    DetectedSwingResponse,
    SwingsWindowedResponse,
    CalibrationSwingResponse,
    CalibrationScaleStats,
    CalibrationResponse,
    ReplayAdvanceRequest,
    ReplayReverseRequest,
    ReplayBarResponse,
    ReplayEventResponse,
    ReplaySwingState,
    ReplayAdvanceResponse,
    AggregatedBarsResponse,
    PlaybackFeedbackRequest,
    PlaybackFeedbackResponse,
    # New hierarchical models (Issue #166)
    TreeStatistics,
    SwingsByDepth,
    CalibrationResponseHierarchical,
    # DAG state models (Issue #169)
    DagLegResponse,
    DagPendingOrigin,
    DagLegCounts,
    DagStateResponse,
    # Hierarchy exploration models (Issue #250)
    LegLineageResponse,
    # Follow Leg models (Issue #267)
    LifecycleEvent,
    FollowedLegsEventsResponse,
    # Detection config models (Issue #288)
    SwingConfigUpdateRequest,
    SwingConfigResponse,
    DirectionConfigResponse,
)

if TYPE_CHECKING:
    from ..api import AppState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["replay"])


# Scale to timeframe mapping (matches api.py) - standard timeframes
SCALE_TO_MINUTES = {
    "1M": 1, "1m": 1,
    "5M": 5, "5m": 5,
    "15M": 15, "15m": 15,
    "30M": 30, "30m": 30,
    "1H": 60, "1h": 60,
    "4H": 240, "4h": 240,
    "1D": 1440, "1d": 1440,
    "1W": 10080, "1w": 10080,
}

# Global cache for replay state
_replay_cache: Dict[str, Any] = {
    "last_bar_index": -1,
    "detector": None,  # LegDetector instance
    "calibration_bar_count": 0,
    "calibration_events": [],  # Events from calibration
    "reference_layer": None,  # ReferenceLayer for filtering and invalidation
    "aggregator": None,  # BarAggregator for incremental bar aggregation
    "source_resolution": 5,  # Source resolution in minutes
    "lifecycle_events": [],  # Lifecycle events for followed legs (#267)
}


# ============================================================================
# Helper Functions
# ============================================================================


def _depth_to_scale(depth: int, total_depth: int = 4) -> str:
    """
    Map hierarchy depth to legacy scale for compatibility.

    Lower depth = larger swings = higher scale.
    - depth 0 (root) -> XL
    - depth 1 -> L
    - depth 2 -> M
    - depth 3+ -> S

    Args:
        depth: Hierarchy depth from SwingNode.
        total_depth: Maximum depth for normalization.

    Returns:
        Scale string (XL, L, M, or S).
    """
    if depth == 0:
        return "XL"
    elif depth == 1:
        return "L"
    elif depth == 2:
        return "M"
    return "S"


def _size_to_scale(size: float, scale_thresholds: Dict[str, float]) -> str:
    """
    Map swing size to scale based on thresholds.

    Used during calibration when we need to group swings by size.

    Args:
        size: Swing size (high - low).
        scale_thresholds: Dict mapping scale to minimum size.

    Returns:
        Scale string (XL, L, M, or S).
    """
    if size >= scale_thresholds["XL"]:
        return "XL"
    elif size >= scale_thresholds["L"]:
        return "L"
    elif size >= scale_thresholds["M"]:
        return "M"
    return "S"


def _swing_node_to_calibration_response(
    swing: SwingNode,
    is_active: bool,
    rank: int = 1,
    scale_thresholds: Optional[Dict[str, float]] = None,
) -> CalibrationSwingResponse:
    """
    Convert SwingNode to CalibrationSwingResponse.

    Args:
        swing: SwingNode from LegDetector.
        is_active: Whether swing is currently active.
        rank: Swing rank by size.
        scale_thresholds: Optional thresholds for scale assignment.

    Returns:
        CalibrationSwingResponse for API response.
    """
    high = float(swing.high_price)
    low = float(swing.low_price)
    size = high - low

    # Determine scale - use size-based thresholds if available, else depth
    if scale_thresholds:
        scale = _size_to_scale(size, scale_thresholds)
    else:
        depth = swing.get_depth()
        scale = _depth_to_scale(depth)

    # Calculate Fib levels based on direction
    if swing.direction == "bull":
        # Bull: defending low
        fib_0 = low
        fib_0382 = low + size * 0.382
        fib_1 = high
        fib_2 = low + size * 2.0
    else:
        # Bear: defending high
        fib_0 = high
        fib_0382 = high - size * 0.382
        fib_1 = low
        fib_2 = high - size * 2.0

    return CalibrationSwingResponse(
        id=swing.swing_id,
        scale=scale,
        direction=swing.direction,
        high_price=high,
        high_bar_index=swing.high_bar_index,
        low_price=low,
        low_bar_index=swing.low_bar_index,
        size=size,
        rank=rank,
        is_active=is_active,
        depth=swing.get_depth(),
        parent_ids=[p.swing_id for p in swing.parents],
        fib_0=fib_0,
        fib_0382=fib_0382,
        fib_1=fib_1,
        fib_2=fib_2,
    )


def _event_to_response(
    event: SwingEvent,
    swing: Optional[SwingNode] = None,
    scale_thresholds: Optional[Dict[str, float]] = None,
) -> ReplayEventResponse:
    """
    Convert SwingEvent to ReplayEventResponse.

    Args:
        event: SwingEvent from LegDetector.
        swing: Optional SwingNode for context.
        scale_thresholds: Optional thresholds for scale assignment.

    Returns:
        ReplayEventResponse for API response.
    """
    # Determine event type string
    if isinstance(event, SwingFormedEvent):
        event_type = "SWING_FORMED"
        direction = event.direction
        depth = 0
        parent_ids = event.parent_ids
    elif isinstance(event, SwingInvalidatedEvent):
        event_type = "SWING_INVALIDATED"
        direction = swing.direction if swing else "bull"
        depth = swing.get_depth() if swing else 0
        parent_ids = [p.swing_id for p in swing.parents] if swing else []
    elif isinstance(event, SwingCompletedEvent):
        event_type = "SWING_COMPLETED"
        direction = swing.direction if swing else "bull"
        depth = swing.get_depth() if swing else 0
        parent_ids = [p.swing_id for p in swing.parents] if swing else []
    elif isinstance(event, LevelCrossEvent):
        event_type = "LEVEL_CROSS"
        direction = swing.direction if swing else "bull"
        depth = swing.get_depth() if swing else 0
        parent_ids = [p.swing_id for p in swing.parents] if swing else []
    else:
        event_type = "UNKNOWN"
        direction = "bull"
        depth = 0
        parent_ids = []

    # Determine scale from size or depth
    if swing and scale_thresholds:
        size = float(swing.high_price - swing.low_price)
        scale = _size_to_scale(size, scale_thresholds)
    else:
        scale = _depth_to_scale(depth)

    # Build swing response if we have swing data
    swing_response = None
    if swing:
        swing_response = _swing_node_to_calibration_response(
            swing,
            is_active=swing.status == "active",
            scale_thresholds=scale_thresholds,
        )

    # Build trigger explanation
    trigger_explanation = _format_trigger_explanation(event, swing)

    # Get level info for level cross events
    level = None
    previous_level = None
    if isinstance(event, LevelCrossEvent):
        level = event.level
        previous_level = event.previous_level
    elif isinstance(event, SwingCompletedEvent):
        level = 2.0

    return ReplayEventResponse(
        type=event_type,
        bar_index=event.bar_index,
        scale=scale,
        direction=direction,
        swing_id=event.swing_id,
        swing=swing_response,
        level=level,
        previous_level=previous_level,
        trigger_explanation=trigger_explanation,
        depth=depth,
        parent_ids=parent_ids,
    )


def _format_trigger_explanation(
    event: SwingEvent,
    swing: Optional[SwingNode],
) -> str:
    """
    Generate human-readable explanation for an event.

    Args:
        event: The swing event.
        swing: Optional swing node for context.

    Returns:
        Human-readable explanation string.
    """
    if swing is None:
        return ""

    high = float(swing.high_price)
    low = float(swing.low_price)
    size = high - low

    if size <= 0:
        return ""

    if isinstance(event, SwingFormedEvent):
        if swing.direction == "bull":
            fib_0382 = low + size * 0.382
            fib_2 = low + size * 2.0
            return (
                f"Bull swing formed: defending {low:.2f}\n"
                f"Active range: {fib_0382:.2f} -> {fib_2:.2f}"
            )
        else:
            fib_0382 = high - size * 0.382
            fib_2 = high - size * 2.0
            return (
                f"Bear swing formed: defending {high:.2f}\n"
                f"Active range: {fib_0382:.2f} -> {fib_2:.2f}"
            )

    elif isinstance(event, SwingInvalidatedEvent):
        pivot = low if swing.direction == "bull" else high
        pivot_type = "low" if swing.direction == "bull" else "high"
        return (
            f"Pivot {pivot_type} ({pivot:.2f}) violated\n"
            f"Excess: {float(event.excess_amount):.2f}"
        )

    elif isinstance(event, SwingCompletedEvent):
        if swing.direction == "bull":
            fib_2 = low + size * 2.0
        else:
            fib_2 = high - size * 2.0
        return f"Reached 2.0 target ({fib_2:.2f})"

    elif isinstance(event, LevelCrossEvent):
        level = event.level
        prev = event.previous_level
        if swing.direction == "bull":
            level_price = low + size * level
        else:
            level_price = high - size * level
        return f"Crossed {level} ({level_price:.2f}): {prev} -> {level}"

    return ""


def _event_to_lifecycle_event(
    event: SwingEvent,
    bar_index: int,
    csv_index: int,
    timestamp: str,
) -> Optional[LifecycleEvent]:
    """
    Convert a SwingEvent to a LifecycleEvent for Follow Leg tracking.

    Only converts relevant leg lifecycle events. Returns None for events
    that aren't tracked (like LEVEL_CROSS).

    Args:
        event: The swing event.
        bar_index: The bar index where event occurred.
        csv_index: The CSV row index.
        timestamp: ISO format timestamp.

    Returns:
        LifecycleEvent or None if event type not tracked.
    """
    # Map leg events to lifecycle events
    if isinstance(event, SwingFormedEvent):
        # SwingFormedEvent means a leg transitioned to formed state
        # The swing_id is the leg's swing_id
        return LifecycleEvent(
            leg_id=event.swing_id,
            event_type="formed",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Leg formed with pivot at {float(event.high_price):.2f}, "
                        f"range {abs(float(event.high_price) - float(event.low_price)):.2f} points"
        )

    elif isinstance(event, LegInvalidatedEvent):
        # Leg's origin was breached beyond threshold
        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type="invalidated",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Leg invalidated at price {float(event.invalidation_price):.2f}"
        )

    elif isinstance(event, LegPrunedEvent):
        # Map prune reasons to lifecycle event types
        reason = event.reason
        if reason == "engulfed":
            event_type = "engulfed"
            explanation = "Leg engulfed: both origin and pivot breached"
        elif reason == "pivot_breach":
            event_type = "pivot_breached"
            explanation = "Leg pruned: pivot breached"
        elif reason in ("turn_prune", "proximity_prune", "dominated_in_turn",
                       "extension_prune", "inner_structure"):
            event_type = "pruned"
            # Use event's explanation if provided, otherwise build generic one
            explanation = event.explanation if event.explanation else f"Pruned: {reason.replace('_', ' ')}"
        else:
            event_type = "pruned"
            explanation = event.explanation if event.explanation else f"Pruned: {reason}"

        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type=event_type,
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=explanation
        )

    elif isinstance(event, OriginBreachedEvent):
        # First time price crossed the leg's origin
        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type="origin_breached",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Origin breached at {float(event.breach_price):.2f} "
                        f"({float(event.breach_amount):.2f} past origin)"
        )

    elif isinstance(event, PivotBreachedEvent):
        # First time price crossed the leg's pivot (formed legs only)
        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type="pivot_breached",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Pivot breached at {float(event.breach_price):.2f} "
                        f"({float(event.breach_amount):.2f} past pivot)"
        )

    # Skip SwingInvalidatedEvent, SwingCompletedEvent, LevelCrossEvent for lifecycle
    # These are swing-level events, not leg-level events
    return None


def _calculate_scale_thresholds(swings: List[SwingNode]) -> Dict[str, float]:
    """
    Calculate size thresholds for S/M/L/XL scale assignment.

    Uses percentile-based thresholds:
    - XL: Top 10% (90th percentile)
    - L: Top 25% (75th percentile)
    - M: Top 50% (50th percentile)
    - S: Everything else

    Args:
        swings: List of SwingNode objects.

    Returns:
        Dict mapping scale to minimum size threshold.
    """
    if not swings:
        return {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}

    sizes = sorted([float(s.high_price - s.low_price) for s in swings], reverse=True)
    n = len(sizes)

    # Calculate percentile thresholds
    xl_idx = max(0, int(n * 0.10) - 1)
    l_idx = max(0, int(n * 0.25) - 1)
    m_idx = max(0, int(n * 0.50) - 1)

    return {
        "XL": sizes[xl_idx] if xl_idx < n else 100.0,
        "L": sizes[l_idx] if l_idx < n else 40.0,
        "M": sizes[m_idx] if m_idx < n else 15.0,
        "S": 0.0,
    }


def _group_swings_by_scale(
    swings: List[SwingNode],
    scale_thresholds: Dict[str, float],
    current_price: float,
) -> Dict[str, List[CalibrationSwingResponse]]:
    """
    Group swings by scale for API response.

    Args:
        swings: List of SwingNode objects.
        scale_thresholds: Size thresholds for scale assignment.
        current_price: Current price for activity check.

    Returns:
        Dict mapping scale to list of CalibrationSwingResponse.
    """
    result: Dict[str, List[CalibrationSwingResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
    }

    # Sort by size descending for ranking
    sorted_swings = sorted(
        swings,
        key=lambda s: float(s.high_price - s.low_price),
        reverse=True
    )

    for rank, swing in enumerate(sorted_swings, start=1):
        is_active = swing.status == "active"
        response = _swing_node_to_calibration_response(
            swing,
            is_active=is_active,
            rank=rank,
            scale_thresholds=scale_thresholds,
        )
        result[response.scale].append(response)

    return result


# ============================================================================
# Tree Statistics Helpers (Issue #166)
# ============================================================================


def _compute_tree_statistics(
    all_swings: List[SwingNode],
    active_swings: List[SwingNode],
    calibration_bar_count: int,
    recent_lookback: int = 10,
) -> TreeStatistics:
    """
    Compute tree structure statistics for hierarchical UI.

    Args:
        all_swings: All swings from the DAG.
        active_swings: Currently active (defended) swings.
        calibration_bar_count: Total bars in calibration window.
        recent_lookback: Number of bars to look back for "recently invalidated".

    Returns:
        TreeStatistics with hierarchy metrics.
    """
    import statistics

    if not all_swings:
        return TreeStatistics(
            root_swings=0,
            root_bull=0,
            root_bear=0,
            total_nodes=0,
            max_depth=0,
            avg_children=0.0,
            defended_by_depth={"1": 0, "2": 0, "3": 0, "deeper": 0},
            largest_range=0.0,
            largest_swing_id=None,
            median_range=0.0,
            smallest_range=0.0,
            recently_invalidated=0,
            roots_have_children=True,
            siblings_detected=False,
            no_orphaned_nodes=True,
        )

    # Root swings (no parents)
    root_swings = [s for s in all_swings if len(s.parents) == 0]
    root_bull = sum(1 for s in root_swings if s.direction == "bull")
    root_bear = sum(1 for s in root_swings if s.direction == "bear")

    # Max depth
    max_depth = max((s.get_depth() for s in all_swings), default=0)

    # Average children per node
    total_children = sum(len(s.children) for s in all_swings)
    avg_children = total_children / len(all_swings) if all_swings else 0.0

    # Defended swings by depth
    defended_by_depth = {"1": 0, "2": 0, "3": 0, "deeper": 0}
    for swing in active_swings:
        depth = swing.get_depth()
        if depth == 0:
            defended_by_depth["1"] += 1  # depth_1 = root (depth 0)
        elif depth == 1:
            defended_by_depth["2"] += 1
        elif depth == 2:
            defended_by_depth["3"] += 1
        else:
            defended_by_depth["deeper"] += 1

    # Range distribution
    ranges = [float(s.high_price - s.low_price) for s in all_swings]
    sorted_ranges = sorted(ranges, reverse=True)
    largest_range = sorted_ranges[0] if sorted_ranges else 0.0
    median_range = statistics.median(ranges) if ranges else 0.0
    smallest_range = sorted_ranges[-1] if sorted_ranges else 0.0

    # Find the largest swing ID
    largest_swing_id = None
    for swing in all_swings:
        if float(swing.high_price - swing.low_price) == largest_range:
            largest_swing_id = swing.swing_id
            break

    # Recently invalidated (swings invalidated after calibration_bar_count - recent_lookback)
    recent_threshold = max(0, calibration_bar_count - recent_lookback)
    recently_invalidated = sum(
        1 for s in all_swings
        if s.status == "invalidated"
        and hasattr(s, 'invalidated_at_bar')
        and s.invalidated_at_bar is not None
        and s.invalidated_at_bar >= recent_threshold
    )

    # Validation quick-checks
    # 1. All root swings have at least one child
    roots_have_children = all(len(s.children) > 0 for s in root_swings) if root_swings else True

    # 2. Siblings detected (swings sharing same defended pivot but different origins)
    siblings_detected = _check_siblings_exist(all_swings)

    # 3. No orphaned nodes (all non-root swings have parents)
    no_orphaned_nodes = all(
        len(s.parents) > 0 or s.get_depth() == 0
        for s in all_swings
    )

    return TreeStatistics(
        root_swings=len(root_swings),
        root_bull=root_bull,
        root_bear=root_bear,
        total_nodes=len(all_swings),
        max_depth=max_depth,
        avg_children=round(avg_children, 1),
        defended_by_depth=defended_by_depth,
        largest_range=round(largest_range, 2),
        largest_swing_id=largest_swing_id,
        median_range=round(median_range, 2),
        smallest_range=round(smallest_range, 2),
        recently_invalidated=recently_invalidated,
        roots_have_children=roots_have_children,
        siblings_detected=siblings_detected,
        no_orphaned_nodes=no_orphaned_nodes,
    )


def _check_siblings_exist(swings: List[SwingNode]) -> bool:
    """
    Check if sibling swings exist (same defended pivot, different origins).

    Siblings share the same anchor0 (defended pivot) but have different
    anchor1 (origin) values.

    Args:
        swings: List of all swings.

    Returns:
        True if siblings are detected.
    """
    # Group swings by defended pivot (anchor0) and direction
    pivot_groups: Dict[tuple, List[SwingNode]] = {}
    for swing in swings:
        if swing.direction == "bull":
            pivot = float(swing.low_price)  # defended pivot for bull
        else:
            pivot = float(swing.high_price)  # defended pivot for bear

        key = (pivot, swing.direction)
        if key not in pivot_groups:
            pivot_groups[key] = []
        pivot_groups[key].append(swing)

    # Check if any group has multiple swings with different origins
    for swings_in_group in pivot_groups.values():
        if len(swings_in_group) >= 2:
            # Get unique origins
            origins = set()
            for s in swings_in_group:
                if s.direction == "bull":
                    origins.add(float(s.high_price))
                else:
                    origins.add(float(s.low_price))
            if len(origins) >= 2:
                return True

    return False


def _group_swings_by_depth(
    swings: List[SwingNode],
    scale_thresholds: Dict[str, float],
) -> SwingsByDepth:
    """
    Group swings by hierarchy depth for the new UI.

    Args:
        swings: List of SwingNode objects.
        scale_thresholds: Size thresholds for scale assignment (backward compat).

    Returns:
        SwingsByDepth with swings grouped by depth level.
    """
    result = SwingsByDepth()

    # Sort by size descending for ranking
    sorted_swings = sorted(
        swings,
        key=lambda s: float(s.high_price - s.low_price),
        reverse=True
    )

    for rank, swing in enumerate(sorted_swings, start=1):
        is_active = swing.status == "active"
        response = _swing_node_to_calibration_response(
            swing,
            is_active=is_active,
            rank=rank,
            scale_thresholds=scale_thresholds,
        )

        depth = swing.get_depth()
        if depth == 0:
            result.depth_1.append(response)
        elif depth == 1:
            result.depth_2.append(response)
        elif depth == 2:
            result.depth_3.append(response)
        else:
            result.deeper.append(response)

    return result


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/api/swings/windowed", response_model=SwingsWindowedResponse)
async def get_windowed_swings(
    bar_end: int = Query(..., description="Source bar index to detect swings up to"),
    top_n: int = Query(2, description="Number of top swings to return"),
):
    """
    Run swing detection on bars[0:bar_end] and return top N swings.

    Uses LegDetector for detection.
    """
    from ..api import get_state

    s = get_state()

    if bar_end < 10:
        return SwingsWindowedResponse(bar_end=bar_end, swing_count=0, swings=[])
    if bar_end > len(s.source_bars):
        bar_end = len(s.source_bars)

    # Run calibration up to bar_end
    bars_to_process = s.source_bars[:bar_end]
    detector, _events = calibrate(bars_to_process)

    # Get active swings from DAG
    active_dag_swings = detector.get_active_swings()

    # Apply Reference layer filtering
    config = SwingConfig.default()
    ref_layer = ReferenceLayer(config)
    ref_infos = ref_layer.get_reference_swings(active_dag_swings)
    active_swings = [info.swing for info in ref_infos if info.is_reference]

    # Sort by size, take top N
    sorted_swings = sorted(
        active_swings,
        key=lambda x: float(x.high_price - x.low_price),
        reverse=True
    )[:top_n]

    # Convert to response
    swing_responses = []
    for rank, swing in enumerate(sorted_swings, start=1):
        high = float(swing.high_price)
        low = float(swing.low_price)
        size = high - low

        if swing.direction == "bull":
            fib_0 = low
            fib_0382 = low + size * 0.382
            fib_1 = high
            fib_2 = low + size * 2.0
        else:
            fib_0 = high
            fib_0382 = high - size * 0.382
            fib_1 = low
            fib_2 = high - size * 2.0

        swing_responses.append(DetectedSwingResponse(
            id=swing.swing_id,
            direction=swing.direction,
            high_price=high,
            high_bar_index=swing.high_bar_index,
            low_price=low,
            low_bar_index=swing.low_bar_index,
            size=size,
            rank=rank,
            scale=_depth_to_scale(swing.get_depth()),
            depth=swing.get_depth(),
            parent_ids=[p.swing_id for p in swing.parents],
            fib_0=fib_0,
            fib_0382=fib_0382,
            fib_1=fib_1,
            fib_2=fib_2,
        ))

    return SwingsWindowedResponse(
        bar_end=bar_end,
        swing_count=len(swing_responses),
        swings=swing_responses,
    )


@router.get("/api/replay/calibrate", response_model=CalibrationResponseHierarchical)
async def calibrate_replay(
    bar_count: int = Query(10000, description="Number of bars for calibration window"),
):
    """
    Run calibration for Replay View using LegDetector.

    Processes the first N bars and returns detected swings grouped by hierarchy
    depth with tree statistics. Also maintains legacy scale-based grouping for
    backward compatibility.

    For DAG visualization mode (bar_count=0), initializes detector without
    processing any bars, allowing incremental build via /api/replay/advance.
    """
    import time
    start_time = time.time()
    logger.info(f"Calibration request received: bar_count={bar_count}")

    global _replay_cache
    from ..api import get_state

    s = get_state()

    actual_bar_count = min(bar_count, len(s.source_bars))

    # DAG mode: Allow bar_count=0 for incremental build from scratch (#179)
    if actual_bar_count == 0:
        logger.info("DAG mode: initializing detector with 0 bars for incremental build")
        config = SwingConfig.default().with_proximity_prune(0.0)  # DEBUG: disable proximity pruning
        ref_layer = ReferenceLayer(config)
        detector = LegDetector(config)

        # Initialize cache for incremental advance
        _replay_cache["detector"] = detector
        _replay_cache["last_bar_index"] = -1  # No bars processed yet
        _replay_cache["calibration_bar_count"] = 0
        _replay_cache["calibration_events"] = []
        _replay_cache["scale_thresholds"] = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        _replay_cache["reference_layer"] = ref_layer
        _replay_cache["source_resolution"] = s.resolution_minutes

        # Update app state
        s.playback_index = -1
        s.calibration_bar_count = 0
        s.hierarchical_detector = detector

        # Return empty calibration response
        empty_tree_stats = TreeStatistics(
            root_swings=0, root_bull=0, root_bear=0, total_nodes=0,
            max_depth=0, avg_children=0.0,
            defended_by_depth={"1": 0, "2": 0, "3": 0, "deeper": 0},
            largest_range=0.0, largest_swing_id=None, median_range=0.0,
            smallest_range=0.0, recently_invalidated=0,
            roots_have_children=True, siblings_detected=False, no_orphaned_nodes=True,
        )
        empty_swings_by_depth = SwingsByDepth()

        logger.info("DAG mode: detector initialized, ready for incremental advance")
        return CalibrationResponseHierarchical(
            calibration_bar_count=0,
            current_price=s.source_bars[0].open if s.source_bars else 0.0,
            tree_stats=empty_tree_stats,
            swings_by_depth=empty_swings_by_depth,
            active_swings_by_depth=empty_swings_by_depth,
        )

    if actual_bar_count < 10:
        raise HTTPException(
            status_code=400,
            detail="Need at least 10 bars for calibration (use bar_count=0 for DAG mode)"
        )

    logger.info(f"Running calibration on {actual_bar_count} bars...")
    calibrate_start = time.time()

    # Run calibration using LegDetector with Reference layer (#175)
    # This ensures tolerance-based invalidation and completion are applied
    # during calibration, not just at response time.
    calibration_bars = s.source_bars[:actual_bar_count]
    config = SwingConfig.default()
    ref_layer = ReferenceLayer(config)
    detector, events = calibrate(calibration_bars, config, ref_layer=ref_layer)

    logger.info(f"Calibration processing took {time.time() - calibrate_start:.2f}s")

    current_price = calibration_bars[-1].close

    # Get all swings from DAG
    all_dag_swings = detector.state.active_swings
    active_dag_swings = detector.get_active_swings()

    # Apply Reference layer filtering (fixes #160)
    # Note: ref_layer was created above and passed to calibrate() for
    # tolerance-based invalidation/completion during calibration (#175)
    reference_swing_infos = ref_layer.get_reference_swings(active_dag_swings)

    # Extract the filtered SwingNode objects
    active_swings = [info.swing for info in reference_swing_infos if info.is_reference]

    # For "all swings" stat, use DAG output but note filtering
    all_swings = all_dag_swings

    logger.info(
        f"Reference layer: {len(active_dag_swings)} DAG swings -> "
        f"{len(active_swings)} reference swings"
    )

    # Calculate scale thresholds for compatibility
    scale_thresholds = _calculate_scale_thresholds(all_swings)

    # Compute tree statistics
    tree_stats = _compute_tree_statistics(
        all_swings=all_swings,
        active_swings=active_swings,
        calibration_bar_count=actual_bar_count,
        recent_lookback=10,
    )

    # Group swings by depth
    swings_by_depth = _group_swings_by_depth(all_swings, scale_thresholds)
    active_swings_by_depth = _group_swings_by_depth(active_swings, scale_thresholds)

    # Update app state
    s.playback_index = actual_bar_count - 1
    s.calibration_bar_count = actual_bar_count
    s.hierarchical_detector = detector

    # Update cache
    _replay_cache["detector"] = detector
    _replay_cache["last_bar_index"] = actual_bar_count - 1
    _replay_cache["calibration_bar_count"] = actual_bar_count
    _replay_cache["calibration_events"] = events
    _replay_cache["scale_thresholds"] = scale_thresholds
    _replay_cache["reference_layer"] = ref_layer
    _replay_cache["source_resolution"] = s.resolution_minutes

    total_time = time.time() - start_time
    logger.info(
        f"Calibration complete: {actual_bar_count} bars, "
        f"{len(active_swings)} active swings, "
        f"tree: {tree_stats.root_swings} roots, depth {tree_stats.max_depth}, "
        f"total time: {total_time:.2f}s"
    )

    return CalibrationResponseHierarchical(
        calibration_bar_count=actual_bar_count,
        current_price=current_price,
        tree_stats=tree_stats,
        swings_by_depth=swings_by_depth,
        active_swings_by_depth=active_swings_by_depth,
    )


@router.post("/api/replay/advance", response_model=ReplayAdvanceResponse)
async def advance_replay(request: ReplayAdvanceRequest):
    """
    Advance playback by processing additional bars.

    Uses detector.process_bar() for incremental detection.
    """
    global _replay_cache
    from ..api import get_state

    s = get_state()

    # Get or initialize detector
    detector = _replay_cache.get("detector")
    if detector is None:
        raise HTTPException(
            status_code=400,
            detail="Must calibrate before advancing. Call /api/replay/calibrate first."
        )

    # Validate request
    if request.current_bar_index != _replay_cache["last_bar_index"]:
        logger.warning(
            f"Bar index mismatch: expected {_replay_cache['last_bar_index']}, "
            f"got {request.current_bar_index}"
        )

    # Calculate new bar range
    start_idx = _replay_cache["last_bar_index"] + 1
    end_idx = min(start_idx + request.advance_by, len(s.source_bars))

    if start_idx >= len(s.source_bars):
        # End of data
        current_bar = s.source_bars[-1]
        active_dag_swings = detector.get_active_swings()
        scale_thresholds = _replay_cache.get("scale_thresholds", {})

        # Apply Reference layer filtering
        ref_layer = _replay_cache.get("reference_layer")
        if ref_layer:
            ref_infos = ref_layer.get_reference_swings(active_dag_swings)
            active_swings = [info.swing for info in ref_infos if info.is_reference]
        else:
            active_swings = active_dag_swings

        # Build optional fields
        aggregated_bars = None
        if request.include_aggregated_bars:
            source_resolution = _replay_cache.get("source_resolution", s.resolution_minutes)
            aggregated_bars = _build_aggregated_bars(
                s.source_bars, request.include_aggregated_bars, source_resolution
            )
        dag_state = _build_dag_state(detector) if request.include_dag_state else None

        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=_build_swing_state(active_swings, scale_thresholds),
            current_bar_index=len(s.source_bars) - 1,
            current_price=current_bar.close,
            end_of_data=True,
            aggregated_bars=aggregated_bars,
            dag_state=dag_state,
        )

    # Process new bars incrementally
    new_bars: List[ReplayBarResponse] = []
    all_events: List[ReplayEventResponse] = []
    scale_thresholds = _replay_cache.get("scale_thresholds", {})

    # Per-bar DAG states for high-speed playback (#283)
    per_bar_dag_states: List[DagStateResponse] = []

    # Get Reference layer from cache for tolerance-based checks (#175)
    ref_layer = _replay_cache.get("reference_layer")

    for idx in range(start_idx, end_idx):
        bar = s.source_bars[idx]

        # 1. Process bar with detector (DAG events)
        events = detector.process_bar(bar)

        # 2. Apply Reference layer invalidation/completion (#175)
        if ref_layer is not None:
            from datetime import datetime
            timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()
            active_swings = detector.get_active_swings()

            # Check invalidation (tolerance-based rules)
            invalidated = ref_layer.update_invalidation_on_bar(active_swings, bar)
            for swing, result in invalidated:
                swing.invalidate()
                events.append(SwingInvalidatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=swing.swing_id,
                    reason=f"reference_layer:{result.reason}",
                ))

            # Check completion (2× for small swings, big swings never complete)
            completed = ref_layer.update_completion_on_bar(active_swings, bar)
            for swing, result in completed:
                swing.complete()
                events.append(SwingCompletedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=swing.swing_id,
                    completion_price=result.completion_price,
                ))

        # Add bar to response
        new_bars.append(ReplayBarResponse(
            index=bar.index,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            csv_index=s.window_offset + bar.index,
        ))

        # Convert events to responses
        for event in events:
            # Find the swing associated with this event
            swing = None
            for s_node in detector.state.active_swings:
                if s_node.swing_id == event.swing_id:
                    swing = s_node
                    break

            event_response = _event_to_response(event, swing, scale_thresholds)
            all_events.append(event_response)

        # Capture lifecycle events for Follow Leg feature (#267)
        csv_index = s.window_offset + bar.index
        timestamp = datetime.fromtimestamp(bar.timestamp).isoformat()
        for event in events:
            lifecycle_event = _event_to_lifecycle_event(event, bar.index, csv_index, timestamp)
            if lifecycle_event:
                _replay_cache["lifecycle_events"].append(lifecycle_event)

        # Snapshot DAG state after each bar for high-speed playback (#283)
        if request.include_per_bar_dag_states:
            per_bar_dag_states.append(_build_dag_state(detector))

    # Update cache state
    _replay_cache["last_bar_index"] = end_idx - 1
    s.playback_index = end_idx - 1

    # Build current swing state with Reference layer filtering
    active_dag_swings = detector.get_active_swings()
    ref_layer = _replay_cache.get("reference_layer")
    if ref_layer:
        ref_infos = ref_layer.get_reference_swings(active_dag_swings)
        active_swings = [info.swing for info in ref_infos if info.is_reference]
    else:
        active_swings = active_dag_swings

    swing_state = _build_swing_state(active_swings, scale_thresholds)

    current_bar = s.source_bars[end_idx - 1]
    end_of_data = end_idx >= len(s.source_bars)

    # Build optional aggregated bars (for batched playback)
    aggregated_bars = None
    if request.include_aggregated_bars:
        source_resolution = _replay_cache.get("source_resolution", s.resolution_minutes)
        aggregated_bars = _build_aggregated_bars(
            s.source_bars,
            request.include_aggregated_bars,
            source_resolution,
            limit=end_idx,
        )

    # Build optional DAG state (for batched playback)
    dag_state = None
    if request.include_dag_state:
        dag_state = _build_dag_state(detector)

    # Include per-bar DAG states for high-speed playback (#283)
    dag_states = per_bar_dag_states if request.include_per_bar_dag_states else None

    return ReplayAdvanceResponse(
        new_bars=new_bars,
        events=all_events,
        swing_state=swing_state,
        current_bar_index=end_idx - 1,
        current_price=current_bar.close,
        end_of_data=end_of_data,
        aggregated_bars=aggregated_bars,
        dag_state=dag_state,
        dag_states=dag_states,
    )


@router.post("/api/replay/reverse", response_model=ReplayAdvanceResponse)
async def reverse_replay(request: ReplayReverseRequest):
    """
    Reverse playback by one bar.

    Implementation: resets detector and replays from bar 0 to current_bar_index - 1.
    This is intentionally simple (wasteful) but allows inspecting backend state
    when going backward without complex state management.

    Future optimization: snapshot every ~1k bars to avoid full replay.
    """
    global _replay_cache
    from ..api import get_state

    s = get_state()

    # Validate we have a detector
    if _replay_cache.get("detector") is None:
        raise HTTPException(
            status_code=400,
            detail="Must calibrate before reversing. Call /api/replay/calibrate first."
        )

    # Validate bar index
    current_idx = request.current_bar_index
    if current_idx != _replay_cache["last_bar_index"]:
        logger.warning(
            f"Bar index mismatch on reverse: cache has {_replay_cache['last_bar_index']}, "
            f"request has {current_idx}"
        )

    target_idx = current_idx - 1

    # Can't go before bar 0
    if target_idx < 0:
        # Already at start - return current state
        current_bar = s.source_bars[0] if s.source_bars else None
        if current_bar is None:
            raise HTTPException(status_code=400, detail="No bars loaded")

        detector = _replay_cache["detector"]
        active_dag_swings = detector.get_active_swings()
        scale_thresholds = _replay_cache.get("scale_thresholds", {})

        ref_layer = _replay_cache.get("reference_layer")
        if ref_layer:
            ref_infos = ref_layer.get_reference_swings(active_dag_swings)
            active_swings = [info.swing for info in ref_infos if info.is_reference]
        else:
            active_swings = active_dag_swings

        dag_state = _build_dag_state(detector) if request.include_dag_state else None

        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=_build_swing_state(active_swings, scale_thresholds),
            current_bar_index=0,
            current_price=current_bar.close,
            end_of_data=False,
            aggregated_bars=None,
            dag_state=dag_state,
            dag_states=None,
        )

    # Reset detector and replay from 0 to target_idx
    logger.info(f"Reversing: replaying bars 0 to {target_idx}")

    # Get preserved config from current detector
    old_detector = _replay_cache["detector"]
    config = old_detector.config

    # Create fresh detector with same config
    detector = LegDetector(config)
    ref_layer = ReferenceLayer(config)

    # Replay all bars up to target
    bars_to_process = s.source_bars[:target_idx + 1]
    for bar in bars_to_process:
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # Process bar
        events = detector.process_bar(bar)

        # Apply Reference layer invalidation/completion
        active_swings = detector.get_active_swings()

        invalidated = ref_layer.update_invalidation_on_bar(active_swings, bar)
        for swing, result in invalidated:
            swing.invalidate()

        completed = ref_layer.update_completion_on_bar(active_swings, bar)
        for swing, result in completed:
            swing.complete()

    # Update cache
    _replay_cache["detector"] = detector
    _replay_cache["last_bar_index"] = target_idx
    _replay_cache["reference_layer"] = ref_layer
    # Clear lifecycle events beyond target (they're no longer valid)
    _replay_cache["lifecycle_events"] = [
        e for e in _replay_cache["lifecycle_events"]
        if e.get("bar_index", 0) <= target_idx
    ]

    # Update app state
    s.playback_index = target_idx
    s.hierarchical_detector = detector

    # Build response
    current_bar = s.source_bars[target_idx]
    active_dag_swings = detector.get_active_swings()
    scale_thresholds = _replay_cache.get("scale_thresholds", {})

    if ref_layer:
        ref_infos = ref_layer.get_reference_swings(active_dag_swings)
        active_swings = [info.swing for info in ref_infos if info.is_reference]
    else:
        active_swings = active_dag_swings

    swing_state = _build_swing_state(active_swings, scale_thresholds)

    # Build optional aggregated bars
    aggregated_bars = None
    if request.include_aggregated_bars:
        source_resolution = _replay_cache.get("source_resolution", s.resolution_minutes)
        aggregated_bars = _build_aggregated_bars(
            s.source_bars,
            request.include_aggregated_bars,
            source_resolution,
            limit=target_idx + 1,
        )

    dag_state = _build_dag_state(detector) if request.include_dag_state else None

    return ReplayAdvanceResponse(
        new_bars=[],  # No new bars on reverse
        events=[],    # No events on reverse (full replay)
        swing_state=swing_state,
        current_bar_index=target_idx,
        current_price=current_bar.close,
        end_of_data=False,
        aggregated_bars=aggregated_bars,
        dag_state=dag_state,
        dag_states=None,
    )


def _build_swing_state(
    active_swings: List[SwingNode],
    scale_thresholds: Dict[str, float],
) -> ReplaySwingState:
    """
    Build ReplaySwingState from active swings.

    Args:
        active_swings: List of active SwingNode objects.
        scale_thresholds: Size thresholds for scale assignment (for compatibility).

    Returns:
        ReplaySwingState grouped by depth.
    """
    by_depth: Dict[str, List[CalibrationSwingResponse]] = {
        "depth_1": [], "depth_2": [], "depth_3": [], "deeper": []
    }

    sorted_swings = sorted(
        active_swings,
        key=lambda x: float(x.high_price - x.low_price),
        reverse=True
    )

    for rank, swing in enumerate(sorted_swings, start=1):
        response = _swing_node_to_calibration_response(
            swing,
            is_active=True,
            rank=rank,
            scale_thresholds=scale_thresholds,
        )
        depth = swing.get_depth()
        if depth == 0:
            by_depth["depth_1"].append(response)
        elif depth == 1:
            by_depth["depth_2"].append(response)
        elif depth == 2:
            by_depth["depth_3"].append(response)
        else:
            by_depth["deeper"].append(response)

    return ReplaySwingState(
        depth_1=by_depth["depth_1"],
        depth_2=by_depth["depth_2"],
        depth_3=by_depth["depth_3"],
        deeper=by_depth["deeper"],
    )


def _build_aggregated_bars(
    source_bars: List[Bar],
    scales: List[str],
    source_resolution: int,
    limit: Optional[int] = None,
) -> AggregatedBarsResponse:
    """
    Build aggregated bars for requested scales.

    Args:
        source_bars: All source bars.
        scales: List of scales to aggregate (e.g., ["S", "M"]).
        source_resolution: Source bar resolution in minutes.
        limit: Optional limit on number of source bars to use.

    Returns:
        AggregatedBarsResponse with bars for each requested scale.
    """
    bars_to_use = source_bars[:limit] if limit else source_bars
    if not bars_to_use:
        return {}

    # Create aggregator for the bars
    aggregator = BarAggregator(bars_to_use, source_resolution)

    result: AggregatedBarsResponse = {}

    for scale in scales:
        scale_upper = scale.upper()
        timeframe = SCALE_TO_MINUTES.get(scale_upper, source_resolution)
        effective_tf = max(timeframe, source_resolution)

        try:
            agg_bars = aggregator.get_bars(effective_tf)
            source_to_agg = aggregator._source_to_agg_mapping.get(effective_tf, {})

            # Build inverse mapping
            agg_to_source = {}
            for src_idx, agg_idx in source_to_agg.items():
                if agg_idx not in agg_to_source:
                    agg_to_source[agg_idx] = (src_idx, src_idx)
                else:
                    min_idx, max_idx = agg_to_source[agg_idx]
                    agg_to_source[agg_idx] = (min(min_idx, src_idx), max(max_idx, src_idx))

            bar_responses = []
            for i, agg_bar in enumerate(agg_bars):
                src_start, src_end = agg_to_source.get(i, (0, 0))
                bar_responses.append(BarResponse(
                    index=i,
                    timestamp=agg_bar.timestamp,
                    open=agg_bar.open,
                    high=agg_bar.high,
                    low=agg_bar.low,
                    close=agg_bar.close,
                    source_start_index=src_start,
                    source_end_index=src_end,
                ))

            result[scale] = bar_responses  # Use original scale key (preserves case)
        except Exception as e:
            logger.warning(f"Failed to aggregate bars for scale {scale}: {e}")

    return result


def _build_dag_state(detector: LegDetector) -> DagStateResponse:
    """
    Build DAG state response from detector.

    Args:
        detector: The LegDetector instance.

    Returns:
        DagStateResponse with current DAG state.
    """
    state = detector.state

    active_legs = [
        DagLegResponse(
            leg_id=leg.leg_id,
            direction=leg.direction,
            pivot_price=float(leg.pivot_price),
            pivot_index=leg.pivot_index,
            origin_price=float(leg.origin_price),
            origin_index=leg.origin_index,
            retracement_pct=float(leg.retracement_pct),
            formed=leg.formed,
            status=leg.status,
            bar_count=leg.bar_count,
            # Impulsiveness and spikiness replace raw impulse (#241)
            impulsiveness=leg.impulsiveness,
            spikiness=leg.spikiness,
            # Hierarchy fields for exploration (#250, #251)
            parent_leg_id=leg.parent_leg_id,
            swing_id=leg.swing_id,
        )
        for leg in state.active_legs
    ]

    pending_origins = {
        direction: DagPendingOrigin(
            price=float(origin.price),
            bar_index=origin.bar_index,
            direction=origin.direction,
            source=origin.source,
        ) if origin else None
        for direction, origin in state.pending_origins.items()
    }

    leg_counts = DagLegCounts(
        bull=sum(1 for leg in state.active_legs if leg.direction == 'bull'),
        bear=sum(1 for leg in state.active_legs if leg.direction == 'bear'),
    )

    return DagStateResponse(
        active_legs=active_legs,
        pending_origins=pending_origins,
        leg_counts=leg_counts,
    )


@router.post("/api/playback/feedback", response_model=PlaybackFeedbackResponse)
async def submit_feedback(request: PlaybackFeedbackRequest):
    """
    Submit playback feedback/observation.

    Stores the observation with context snapshot for later analysis.
    Screenshots are saved to ground_truth/screenshots/ if provided.
    """
    import base64
    from datetime import datetime
    from pathlib import Path
    from ..api import get_state

    s = get_state()

    if s.playback_feedback_storage is None:
        raise HTTPException(
            status_code=500,
            detail="Feedback storage not initialized"
        )

    if not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Feedback text cannot be empty"
        )

    # Store observation
    observation = s.playback_feedback_storage.add_observation(
        data_file=s.data_file or "unknown",
        text=request.text,
        playback_bar=request.playback_bar,
        snapshot=request.snapshot.model_dump(),
        offset=s.window_offset,
    )

    # Save screenshot if provided
    if request.screenshot_data:
        try:
            screenshots_dir = Path("ground_truth/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Build filename: {timestamp}_{mode}_{source}_{feedback_id}.png
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            mode = request.snapshot.mode or "unknown"
            source = Path(s.data_file or "unknown").stem
            filename = f"{timestamp}_{mode}_{source}_{observation.observation_id}.png"

            # Decode and save
            screenshot_bytes = base64.b64decode(request.screenshot_data)
            screenshot_path = screenshots_dir / filename
            screenshot_path.write_bytes(screenshot_bytes)
            logger.info(f"Saved screenshot: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")
            # Don't fail the request if screenshot save fails

    return PlaybackFeedbackResponse(
        success=True,
        observation_id=observation.observation_id,
        message=f"Feedback recorded at bar {request.playback_bar}",
    )


@router.get("/api/dag/state", response_model=DagStateResponse)
async def get_dag_state():
    """
    Get current DAG internal state for visualization.

    Exposes leg-level state from the detector for debugging and DAG visualization:
    - active_legs: Currently tracked legs (pre-formation candidate swings)
    - pending_origins: Potential origins for new legs awaiting temporal confirmation
    - leg_counts: Count of legs by direction
    """
    global _replay_cache

    detector = _replay_cache.get("detector")
    if detector is None:
        raise HTTPException(
            status_code=400,
            detail="Must calibrate first. Call /api/replay/calibrate."
        )

    state = detector.state

    # Convert active legs to response
    active_legs = [
        DagLegResponse(
            leg_id=leg.leg_id,
            direction=leg.direction,
            pivot_price=float(leg.pivot_price),
            pivot_index=leg.pivot_index,
            origin_price=float(leg.origin_price),
            origin_index=leg.origin_index,
            retracement_pct=float(leg.retracement_pct),
            formed=leg.formed,
            status=leg.status,
            bar_count=leg.bar_count,
            # Impulsiveness and spikiness replace raw impulse (#241)
            impulsiveness=leg.impulsiveness,
            spikiness=leg.spikiness,
            # Hierarchy fields for exploration (#250, #251)
            parent_leg_id=leg.parent_leg_id,
            swing_id=leg.swing_id,
        )
        for leg in state.active_legs
    ]

    # Convert pending origins
    pending_origins = {
        direction: DagPendingOrigin(
            price=float(origin.price),
            bar_index=origin.bar_index,
            direction=origin.direction,
            source=origin.source,
        ) if origin else None
        for direction, origin in state.pending_origins.items()
    }

    # Compute leg counts
    leg_counts = DagLegCounts(
        bull=sum(1 for leg in state.active_legs if leg.direction == 'bull'),
        bear=sum(1 for leg in state.active_legs if leg.direction == 'bear'),
    )

    return DagStateResponse(
        active_legs=active_legs,
        pending_origins=pending_origins,
        leg_counts=leg_counts,
    )


@router.get("/api/dag/lineage/{leg_id}", response_model=LegLineageResponse)
async def get_leg_lineage(leg_id: str):
    """
    Get full lineage for a leg (ancestors and descendants).

    Used by the frontend for hierarchy exploration mode (#250).
    Given a leg ID, returns:
    - ancestors: chain from this leg up to root (following parent_leg_id)
    - descendants: all legs whose ancestry includes this leg
    - depth: how deep this leg is in the hierarchy

    Args:
        leg_id: The leg ID to get lineage for.

    Returns:
        LegLineageResponse with ancestors, descendants, and depth.
    """
    global _replay_cache

    detector = _replay_cache.get("detector")
    if detector is None:
        raise HTTPException(
            status_code=400,
            detail="Must calibrate first. Call /api/replay/calibrate."
        )

    state = detector.state

    # Build a lookup dict for efficient access
    legs_by_id = {leg.leg_id: leg for leg in state.active_legs}

    # Check if leg exists
    if leg_id not in legs_by_id:
        raise HTTPException(
            status_code=404,
            detail=f"Leg with ID '{leg_id}' not found."
        )

    target_leg = legs_by_id[leg_id]

    # Build ancestors chain by following parent_leg_id
    ancestors: List[str] = []
    current_id = target_leg.parent_leg_id
    visited = {leg_id}  # Prevent cycles
    while current_id and current_id in legs_by_id and current_id not in visited:
        ancestors.append(current_id)
        visited.add(current_id)
        current_id = legs_by_id[current_id].parent_leg_id

    # Build descendants by finding all legs whose ancestor chain includes this leg
    # A leg is a descendant if we can trace its parent_leg_id chain back to leg_id
    descendants: List[str] = []

    # Build parent lookup for all legs
    def get_ancestors(lid: str) -> set:
        """Get all ancestor IDs for a leg."""
        result = set()
        current = legs_by_id.get(lid)
        if not current:
            return result
        cur_parent = current.parent_leg_id
        seen = {lid}
        while cur_parent and cur_parent in legs_by_id and cur_parent not in seen:
            result.add(cur_parent)
            seen.add(cur_parent)
            cur_parent = legs_by_id[cur_parent].parent_leg_id
        return result

    for lid, leg in legs_by_id.items():
        if lid == leg_id:
            continue
        # Check if leg_id is in this leg's ancestry
        leg_ancestors = get_ancestors(lid)
        if leg_id in leg_ancestors:
            descendants.append(lid)

    # Compute depth (0 = root)
    depth = len(ancestors)

    return LegLineageResponse(
        leg_id=leg_id,
        ancestors=ancestors,
        descendants=descendants,
        depth=depth,
    )


# ============================================================================
# Follow Leg Endpoints (Issue #267)
# ============================================================================


@router.get("/api/followed-legs/events", response_model=FollowedLegsEventsResponse)
async def get_followed_legs_events(
    leg_ids: str = Query(..., description="Comma-separated list of leg IDs to track"),
    since_bar: int = Query(..., description="Only return events from this bar index onwards"),
):
    """
    Get lifecycle events for followed legs.

    Returns events for the specified leg IDs that occurred at or after the
    since_bar index. Used by the Follow Leg feature to show event markers
    on candles.

    Events tracked:
    - formed: Leg transitioned from forming to formed
    - origin_breached: Price crossed origin beyond threshold
    - pivot_breached: Price crossed pivot beyond threshold
    - engulfed: Both origin and pivot breached
    - pruned: Leg removed from active set
    - invalidated: Leg breaches invalidation threshold

    Args:
        leg_ids: Comma-separated list of leg IDs to track.
        since_bar: Only return events from this bar index onwards.

    Returns:
        FollowedLegsEventsResponse with matching lifecycle events.
    """
    global _replay_cache

    # Parse leg IDs
    leg_id_set = set(lid.strip() for lid in leg_ids.split(",") if lid.strip())

    if not leg_id_set:
        return FollowedLegsEventsResponse(events=[])

    # Filter lifecycle events
    all_events = _replay_cache.get("lifecycle_events", [])
    filtered_events = [
        event for event in all_events
        if event.leg_id in leg_id_set and event.bar_index >= since_bar
    ]

    return FollowedLegsEventsResponse(events=filtered_events)


# ============================================================================
# Detection Config Endpoints (Issue #288)
# ============================================================================


@router.put("/api/replay/config", response_model=SwingConfigResponse)
async def update_detection_config(request: SwingConfigUpdateRequest):
    """
    Update swing detection configuration and re-calibrate.

    This endpoint allows changing detection thresholds (formation, invalidation,
    completion, etc.) and automatically re-runs calibration with the new config.

    The detector is reset and all bars are re-processed with the updated
    configuration, so the DAG state reflects the new thresholds.

    Args:
        request: SwingConfigUpdateRequest with new threshold values.
                 Only provided fields are updated; omitted fields keep defaults.

    Returns:
        SwingConfigResponse with the current configuration after update.

    Example:
        PUT /api/replay/config
        {
            "bull": {"formation_fib": 0.5},
            "stale_extension_threshold": 2.0
        }
    """
    global _replay_cache
    from ..api import get_state

    s = get_state()

    # Get current detector
    detector = _replay_cache.get("detector")
    if detector is None:
        raise HTTPException(
            status_code=400,
            detail="Must calibrate before updating config. Call /api/replay/calibrate first."
        )

    # Start with default config
    new_config = SwingConfig.default()

    # Apply bull direction updates
    if request.bull:
        if request.bull.formation_fib is not None:
            new_config = new_config.with_bull(formation_fib=request.bull.formation_fib)
        if request.bull.invalidation_threshold is not None:
            new_config = new_config.with_bull(invalidation_threshold=request.bull.invalidation_threshold)
        if request.bull.completion_fib is not None:
            new_config = new_config.with_bull(completion_fib=request.bull.completion_fib)
        if request.bull.pivot_breach_threshold is not None:
            new_config = new_config.with_bull(pivot_breach_threshold=request.bull.pivot_breach_threshold)
        if request.bull.engulfed_breach_threshold is not None:
            new_config = new_config.with_bull(engulfed_breach_threshold=request.bull.engulfed_breach_threshold)

    # Apply bear direction updates
    if request.bear:
        if request.bear.formation_fib is not None:
            new_config = new_config.with_bear(formation_fib=request.bear.formation_fib)
        if request.bear.invalidation_threshold is not None:
            new_config = new_config.with_bear(invalidation_threshold=request.bear.invalidation_threshold)
        if request.bear.completion_fib is not None:
            new_config = new_config.with_bear(completion_fib=request.bear.completion_fib)
        if request.bear.pivot_breach_threshold is not None:
            new_config = new_config.with_bear(pivot_breach_threshold=request.bear.pivot_breach_threshold)
        if request.bear.engulfed_breach_threshold is not None:
            new_config = new_config.with_bear(engulfed_breach_threshold=request.bear.engulfed_breach_threshold)

    # Apply global threshold updates
    if request.stale_extension_threshold is not None:
        new_config = new_config.with_stale_extension(request.stale_extension_threshold)
    if request.proximity_threshold is not None:
        new_config = new_config.with_proximity_prune(request.proximity_threshold)

    # Apply pruning algorithm toggles
    if any([
        request.enable_engulfed_prune is not None,
        request.enable_inner_structure_prune is not None,
        request.enable_turn_prune is not None,
        request.enable_pivot_breach_prune is not None,
        request.enable_domination_prune is not None,
    ]):
        new_config = new_config.with_prune_toggles(
            enable_engulfed_prune=request.enable_engulfed_prune,
            enable_inner_structure_prune=request.enable_inner_structure_prune,
            enable_turn_prune=request.enable_turn_prune,
            enable_pivot_breach_prune=request.enable_pivot_breach_prune,
            enable_domination_prune=request.enable_domination_prune,
        )

    # Update detector config and reset state
    detector.update_config(new_config)

    # Re-run calibration from the beginning
    calibration_bar_count = _replay_cache.get("calibration_bar_count", 0)
    if calibration_bar_count > 0 and calibration_bar_count <= len(s.source_bars):
        calibration_bars = s.source_bars[:calibration_bar_count]

        # Create new reference layer with updated config
        ref_layer = ReferenceLayer(new_config)

        # Re-process all calibration bars
        for bar in calibration_bars:
            detector.process_bar(bar)

        # Update cache
        _replay_cache["reference_layer"] = ref_layer
        _replay_cache["last_bar_index"] = calibration_bar_count - 1

        # Recalculate scale thresholds
        all_swings = detector.state.active_swings
        _replay_cache["scale_thresholds"] = _calculate_scale_thresholds(all_swings)

        # Clear lifecycle events (they're no longer valid with new config)
        _replay_cache["lifecycle_events"] = []

        logger.info(
            f"Config updated and re-calibrated: {calibration_bar_count} bars, "
            f"{len(detector.get_active_swings())} active swings"
        )

    # Build response with current config values
    return SwingConfigResponse(
        bull=DirectionConfigResponse(
            formation_fib=new_config.bull.formation_fib,
            invalidation_threshold=new_config.bull.invalidation_threshold,
            completion_fib=new_config.bull.completion_fib,
            pivot_breach_threshold=new_config.bull.pivot_breach_threshold,
            engulfed_breach_threshold=new_config.bull.engulfed_breach_threshold,
        ),
        bear=DirectionConfigResponse(
            formation_fib=new_config.bear.formation_fib,
            invalidation_threshold=new_config.bear.invalidation_threshold,
            completion_fib=new_config.bear.completion_fib,
            pivot_breach_threshold=new_config.bear.pivot_breach_threshold,
            engulfed_breach_threshold=new_config.bear.engulfed_breach_threshold,
        ),
        stale_extension_threshold=new_config.stale_extension_threshold,
        proximity_threshold=new_config.proximity_threshold,
        enable_engulfed_prune=new_config.enable_engulfed_prune,
        enable_inner_structure_prune=new_config.enable_inner_structure_prune,
        enable_turn_prune=new_config.enable_turn_prune,
        enable_pivot_breach_prune=new_config.enable_pivot_breach_prune,
        enable_domination_prune=new_config.enable_domination_prune,
    )


@router.get("/api/replay/config", response_model=SwingConfigResponse)
async def get_detection_config():
    """
    Get current swing detection configuration.

    Returns the current configuration values being used by the detector.
    If no detector is initialized, returns the default configuration.

    Returns:
        SwingConfigResponse with current configuration values.
    """
    global _replay_cache

    # Get detector config or use defaults
    detector = _replay_cache.get("detector")
    if detector is not None:
        config = detector.config
    else:
        config = SwingConfig.default()

    return SwingConfigResponse(
        bull=DirectionConfigResponse(
            formation_fib=config.bull.formation_fib,
            invalidation_threshold=config.bull.invalidation_threshold,
            completion_fib=config.bull.completion_fib,
            pivot_breach_threshold=config.bull.pivot_breach_threshold,
            engulfed_breach_threshold=config.bull.engulfed_breach_threshold,
        ),
        bear=DirectionConfigResponse(
            formation_fib=config.bear.formation_fib,
            invalidation_threshold=config.bear.invalidation_threshold,
            completion_fib=config.bear.completion_fib,
            pivot_breach_threshold=config.bear.pivot_breach_threshold,
            engulfed_breach_threshold=config.bear.engulfed_breach_threshold,
        ),
        stale_extension_threshold=config.stale_extension_threshold,
        proximity_threshold=config.proximity_threshold,
        enable_engulfed_prune=config.enable_engulfed_prune,
        enable_inner_structure_prune=config.enable_inner_structure_prune,
        enable_turn_prune=config.enable_turn_prune,
        enable_pivot_breach_prune=config.enable_pivot_breach_prune,
        enable_domination_prune=config.enable_domination_prune,
    )
