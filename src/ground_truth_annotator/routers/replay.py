"""
Replay router using HierarchicalDetector.

Provides endpoints for Replay View functionality:
- GET /api/swings/windowed - Get windowed swing detection
- GET /api/replay/calibrate - Run calibration for Replay View
- POST /api/replay/advance - Advance playback
- POST /api/playback/feedback - Submit playback feedback

Uses HierarchicalDetector for incremental swing detection with hierarchical
parent relationships. Maintains backward compatibility with legacy S/M/L/XL
scale format by mapping depth to scale.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query

from ...swing_analysis.hierarchical_detector import (
    HierarchicalDetector,
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
)
from ...swing_analysis.adapters import (
    _group_by_legacy_scale,
    swing_node_to_reference_swing,
)
from ...swing_analysis.types import Bar
from ...swing_analysis.reference_frame import ReferenceFrame
from ..schemas import (
    DetectedSwingResponse,
    SwingsWindowedResponse,
    CalibrationSwingResponse,
    CalibrationScaleStats,
    CalibrationResponse,
    ReplayAdvanceRequest,
    ReplayBarResponse,
    ReplayEventResponse,
    ReplaySwingState,
    ReplayAdvanceResponse,
    PlaybackFeedbackRequest,
    PlaybackFeedbackResponse,
)

if TYPE_CHECKING:
    from ..api import AppState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["replay"])


# Global cache for replay state
_replay_cache: Dict[str, Any] = {
    "last_bar_index": -1,
    "detector": None,  # HierarchicalDetector instance
    "calibration_bar_count": 0,
    "calibration_events": [],  # Events from calibration
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
        swing: SwingNode from HierarchicalDetector.
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
        event: SwingEvent from HierarchicalDetector.
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
# Endpoints
# ============================================================================


@router.get("/api/swings/windowed", response_model=SwingsWindowedResponse)
async def get_windowed_swings(
    bar_end: int = Query(..., description="Source bar index to detect swings up to"),
    top_n: int = Query(2, description="Number of top swings to return"),
):
    """
    Run swing detection on bars[0:bar_end] and return top N swings.

    Uses HierarchicalDetector for detection.
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

    # Get active swings
    active_swings = detector.get_active_swings()

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


@router.get("/api/replay/calibrate", response_model=CalibrationResponse)
async def calibrate_replay(
    bar_count: int = Query(10000, description="Number of bars for calibration window"),
):
    """
    Run calibration for Replay View using HierarchicalDetector.

    Processes the first N bars and returns detected swings grouped by scale.
    """
    global _replay_cache
    from ..api import get_state

    s = get_state()

    actual_bar_count = min(bar_count, len(s.source_bars))
    if actual_bar_count < 10:
        raise HTTPException(
            status_code=400,
            detail="Need at least 10 bars for calibration"
        )

    # Run calibration using HierarchicalDetector
    calibration_bars = s.source_bars[:actual_bar_count]
    detector, events = calibrate(calibration_bars)

    current_price = calibration_bars[-1].close

    # Get all swings (active and inactive)
    all_swings = detector.state.active_swings
    active_swings = detector.get_active_swings()

    # Calculate scale thresholds based on swing sizes
    scale_thresholds = _calculate_scale_thresholds(all_swings)

    # Group swings by scale
    swings_by_scale = _group_swings_by_scale(all_swings, scale_thresholds, current_price)
    active_swings_by_scale = _group_swings_by_scale(active_swings, scale_thresholds, current_price)

    # Compute stats
    stats_by_scale = {
        scale: CalibrationScaleStats(
            total_swings=len(swings_by_scale[scale]),
            active_swings=len(active_swings_by_scale[scale])
        )
        for scale in ["XL", "L", "M", "S"]
    }

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

    logger.info(
        f"Calibration complete: {actual_bar_count} bars, "
        f"{len(active_swings)} active swings"
    )

    return CalibrationResponse(
        calibration_bar_count=actual_bar_count,
        current_price=current_price,
        swings_by_scale=swings_by_scale,
        active_swings_by_scale=active_swings_by_scale,
        scale_thresholds=scale_thresholds,
        stats_by_scale=stats_by_scale,
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
        active_swings = detector.get_active_swings()
        scale_thresholds = _replay_cache.get("scale_thresholds", {})

        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=_build_swing_state(active_swings, scale_thresholds),
            current_bar_index=len(s.source_bars) - 1,
            current_price=current_bar.close,
            end_of_data=True,
        )

    # Process new bars incrementally
    new_bars: List[ReplayBarResponse] = []
    all_events: List[ReplayEventResponse] = []
    scale_thresholds = _replay_cache.get("scale_thresholds", {})

    for idx in range(start_idx, end_idx):
        bar = s.source_bars[idx]

        # Process bar with detector
        events = detector.process_bar(bar)

        # Add bar to response
        new_bars.append(ReplayBarResponse(
            index=bar.index,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
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

    # Update cache state
    _replay_cache["last_bar_index"] = end_idx - 1
    s.playback_index = end_idx - 1

    # Build current swing state
    active_swings = detector.get_active_swings()
    swing_state = _build_swing_state(active_swings, scale_thresholds)

    current_bar = s.source_bars[end_idx - 1]
    end_of_data = end_idx >= len(s.source_bars)

    return ReplayAdvanceResponse(
        new_bars=new_bars,
        events=all_events,
        swing_state=swing_state,
        current_bar_index=end_idx - 1,
        current_price=current_bar.close,
        end_of_data=end_of_data,
    )


def _build_swing_state(
    active_swings: List[SwingNode],
    scale_thresholds: Dict[str, float],
) -> ReplaySwingState:
    """
    Build ReplaySwingState from active swings.

    Args:
        active_swings: List of active SwingNode objects.
        scale_thresholds: Size thresholds for scale assignment.

    Returns:
        ReplaySwingState grouped by scale.
    """
    by_scale: Dict[str, List[CalibrationSwingResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
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
        by_scale[response.scale].append(response)

    return ReplaySwingState(
        XL=by_scale["XL"],
        L=by_scale["L"],
        M=by_scale["M"],
        S=by_scale["S"],
    )


@router.post("/api/playback/feedback", response_model=PlaybackFeedbackResponse)
async def submit_feedback(request: PlaybackFeedbackRequest):
    """
    Submit playback feedback/observation.

    Stores the observation with context snapshot for later analysis.
    """
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

    return PlaybackFeedbackResponse(
        success=True,
        observation_id=observation.observation_id,
        message=f"Feedback recorded at bar {request.playback_bar}",
    )
