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
from ...swing_analysis.dag.leg import Leg
from ...swing_analysis.detection_config import DetectionConfig
from ...swing_analysis.events import (
    DetectionEvent,
    LegCreatedEvent,
    LegPrunedEvent,
    OriginBreachedEvent,
    PivotBreachedEvent,
)
from ...swing_analysis.types import Bar
from ...swing_analysis.reference_frame import ReferenceFrame
from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceSwing
from ...swing_analysis.bar_aggregator import BarAggregator
from ..schemas import (
    BarResponse,
    LegResponse,  # Unified schema (Issue #398)
    CalibrationSwingResponse,  # Legacy alias to LegResponse
    ReplayAdvanceRequest,
    ReplayReverseRequest,
    ReplayBarResponse,
    ReplayEventResponse,
    ReplaySwingState,
    ReplayAdvanceResponse,
    AggregatedBarsResponse,
    PlaybackFeedbackRequest,
    PlaybackFeedbackResponse,
    # Hierarchical models (Issue #166)
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
    # Detection config models (Issue #288, #404: symmetric config)
    SwingConfigUpdateRequest,
    SwingConfigResponse,
)

from .helpers import (
    size_to_scale,
    leg_to_response,
    event_to_response,
    format_trigger_explanation,
    event_to_lifecycle_event,
    calculate_scale_thresholds,
    build_swing_state,
    build_aggregated_bars,
    build_dag_state,
    compute_tree_statistics,
    group_legs_by_depth,
)

if TYPE_CHECKING:
    from ..api import AppState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["replay"])



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
# Endpoints
# ============================================================================


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
        config = DetectionConfig.default()
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
            largest_range=0.0, largest_leg_id=None, median_range=0.0,
            smallest_range=0.0,
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

    # Run calibration using LegDetector
    calibration_bars = s.source_bars[:actual_bar_count]
    config = DetectionConfig.default()
    ref_layer = ReferenceLayer(config)
    detector, events = calibrate(calibration_bars, config)

    logger.info(f"Calibration processing took {time.time() - calibrate_start:.2f}s")

    current_price = calibration_bars[-1].close

    # Get all legs from DAG
    all_legs = detector.state.active_legs
    active_legs = [leg for leg in all_legs if leg.status == "active"]

    logger.info(
        f"Calibration complete: {len(all_legs)} legs, "
        f"{len(active_legs)} active"
    )

    # Calculate scale thresholds for compatibility
    scale_thresholds = calculate_scale_thresholds(all_legs)

    # Compute tree statistics
    tree_stats = compute_tree_statistics(
        all_legs=all_legs,
        active_legs=active_legs,
        calibration_bar_count=actual_bar_count,
        recent_lookback=10,
    )

    # Group legs by depth
    swings_by_depth = group_legs_by_depth(all_legs, scale_thresholds)
    active_swings_by_depth = group_legs_by_depth(active_legs, scale_thresholds)

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
        f"{len(active_legs)} active legs, "
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

    # Handle from_index resync (#310): if FE is behind BE, replay to sync
    from_index = request.from_index
    if from_index is not None and from_index != _replay_cache["last_bar_index"]:
        from datetime import datetime as dt_cls  # Local import to avoid shadowing issues
        logger.info(
            f"Resync needed: BE at {_replay_cache['last_bar_index']}, "
            f"FE at {from_index}. Replaying to sync."
        )

        # Get preserved config from current detector
        old_detector = _replay_cache["detector"]
        config = old_detector.config

        # Create fresh detector with same config (like reverse_replay)
        detector = LegDetector(config)
        ref_layer = ReferenceLayer(config)

        # Clear lifecycle events - we'll rebuild them during replay
        _replay_cache["lifecycle_events"] = []

        # Replay all bars up to from_index
        bars_to_process = s.source_bars[:from_index + 1] if from_index >= 0 else []
        for bar in bars_to_process:
            timestamp = dt_cls.fromtimestamp(bar.timestamp) if bar.timestamp else dt_cls.now()

            # Process bar
            events = detector.process_bar(bar)

            # Track formation for reference layer warmup (#397)
            ref_layer.track_formation(detector.state.active_legs, bar)

            # Capture lifecycle events during replay
            csv_index = s.window_offset + bar.index
            ts_iso = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
            for event in events:
                lifecycle_event = event_to_lifecycle_event(event, bar.index, csv_index, ts_iso)
                if lifecycle_event:
                    _replay_cache["lifecycle_events"].append(lifecycle_event)

        # Update cache with fresh detector
        _replay_cache["detector"] = detector
        _replay_cache["last_bar_index"] = from_index
        _replay_cache["reference_layer"] = ref_layer

        # Update app state
        s.playback_index = from_index
        s.hierarchical_detector = detector

        logger.info(f"Resync complete: BE now at {from_index}")

    # Validate request (only warn, don't resync again)
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
        active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
        scale_thresholds = _replay_cache.get("scale_thresholds", {})

        # Build optional fields
        aggregated_bars = None
        if request.include_aggregated_bars:
            source_resolution = _replay_cache.get("source_resolution", s.resolution_minutes)
            aggregated_bars = build_aggregated_bars(
                s.source_bars, request.include_aggregated_bars, source_resolution
            )
        dag_state = build_dag_state(detector, s.window_offset) if request.include_dag_state else None

        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=build_swing_state(active_legs, scale_thresholds),
            current_bar_index=len(s.source_bars) - 1,
            current_price=current_bar.close,
            end_of_data=True,
            csv_index=s.window_offset + len(s.source_bars) - 1,
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

        # Process bar with detector (DAG events)
        events = detector.process_bar(bar)

        # Track formation for reference layer warmup (#397)
        # Without this, reference layer only sees legs when update() is called,
        # missing legs that formed and got pruned while in DAG view
        if ref_layer is not None:
            ref_layer.track_formation(detector.state.active_legs, bar)

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
            # Find the leg associated with this event
            leg = None
            leg_id = getattr(event, 'leg_id', None)
            if leg_id:
                for l in detector.state.active_legs:
                    if l.leg_id == leg_id:
                        leg = l
                        break

            event_response = event_to_response(event, leg, scale_thresholds)
            all_events.append(event_response)

        # Capture lifecycle events for Follow Leg feature (#267)
        csv_index = s.window_offset + bar.index
        timestamp = datetime.fromtimestamp(bar.timestamp).isoformat()
        for event in events:
            lifecycle_event = event_to_lifecycle_event(event, bar.index, csv_index, timestamp)
            if lifecycle_event:
                _replay_cache["lifecycle_events"].append(lifecycle_event)

        # Snapshot DAG state after each bar for high-speed playback (#283)
        if request.include_per_bar_dag_states:
            per_bar_dag_states.append(build_dag_state(detector, s.window_offset))

    # Update cache state
    _replay_cache["last_bar_index"] = end_idx - 1
    s.playback_index = end_idx - 1

    # Build current swing state from active legs
    active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
    swing_state = build_swing_state(active_legs, scale_thresholds)

    current_bar = s.source_bars[end_idx - 1]
    end_of_data = end_idx >= len(s.source_bars)

    # Build optional aggregated bars (for batched playback)
    aggregated_bars = None
    if request.include_aggregated_bars:
        source_resolution = _replay_cache.get("source_resolution", s.resolution_minutes)
        aggregated_bars = build_aggregated_bars(
            s.source_bars,
            request.include_aggregated_bars,
            source_resolution,
            limit=end_idx,
        )

    # Build optional DAG state (for batched playback)
    dag_state = None
    if request.include_dag_state:
        dag_state = build_dag_state(detector, s.window_offset)

    # Include per-bar DAG states for high-speed playback (#283)
    dag_states = per_bar_dag_states if request.include_per_bar_dag_states else None

    return ReplayAdvanceResponse(
        new_bars=new_bars,
        events=all_events,
        swing_state=swing_state,
        current_bar_index=end_idx - 1,
        current_price=current_bar.close,
        end_of_data=end_of_data,
        csv_index=s.window_offset + end_idx - 1,
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
        active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
        scale_thresholds = _replay_cache.get("scale_thresholds", {})

        dag_state = build_dag_state(detector, s.window_offset) if request.include_dag_state else None

        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=build_swing_state(active_legs, scale_thresholds),
            current_bar_index=0,
            current_price=current_bar.close,
            end_of_data=False,
            csv_index=s.window_offset,
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

    # Clear lifecycle events - we'll rebuild them during replay (#299)
    # This ensures events have correct deterministic IDs after BE reset
    _replay_cache["lifecycle_events"] = []

    # Replay all bars up to target
    bars_to_process = s.source_bars[:target_idx + 1]
    for bar in bars_to_process:
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # Process bar
        events = detector.process_bar(bar)

        # Track formation for reference layer warmup (#397)
        ref_layer.track_formation(detector.state.active_legs, bar)

        # Capture lifecycle events during replay (#299)
        # This ensures Follow Leg feature works correctly after step-back
        csv_index = s.window_offset + bar.index
        ts_iso = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        for event in events:
            lifecycle_event = event_to_lifecycle_event(event, bar.index, csv_index, ts_iso)
            if lifecycle_event:
                _replay_cache["lifecycle_events"].append(lifecycle_event)

    # Update cache
    _replay_cache["detector"] = detector
    _replay_cache["last_bar_index"] = target_idx
    _replay_cache["reference_layer"] = ref_layer

    # Update app state
    s.playback_index = target_idx
    s.hierarchical_detector = detector

    # Build response
    current_bar = s.source_bars[target_idx]
    active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
    scale_thresholds = _replay_cache.get("scale_thresholds", {})
    swing_state = build_swing_state(active_legs, scale_thresholds)

    # Build optional aggregated bars
    aggregated_bars = None
    if request.include_aggregated_bars:
        source_resolution = _replay_cache.get("source_resolution", s.resolution_minutes)
        aggregated_bars = build_aggregated_bars(
            s.source_bars,
            request.include_aggregated_bars,
            source_resolution,
            limit=target_idx + 1,
        )

    dag_state = build_dag_state(detector, s.window_offset) if request.include_dag_state else None

    return ReplayAdvanceResponse(
        new_bars=[],  # No new bars on reverse
        events=[],    # No events on reverse (full replay)
        swing_state=swing_state,
        current_bar_index=target_idx,
        current_price=current_bar.close,
        end_of_data=False,
        csv_index=s.window_offset + target_idx,
        aggregated_bars=aggregated_bars,
        dag_state=dag_state,
        dag_states=None,
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
    from ..api import get_state

    global _replay_cache

    detector = _replay_cache.get("detector")
    if detector is None:
        raise HTTPException(
            status_code=400,
            detail="Must calibrate first. Call /api/replay/calibrate."
        )

    s = get_state()
    window_offset = s.window_offset
    state = detector.state

    # Convert active legs to response with csv indices (#300)
    active_legs = [
        DagLegResponse(
            leg_id=leg.leg_id,
            direction=leg.direction,
            pivot_price=float(leg.pivot_price),
            pivot_index=window_offset + leg.pivot_index,  # Convert to csv_index (#300)
            origin_price=float(leg.origin_price),
            origin_index=window_offset + leg.origin_index,  # Convert to csv_index (#300)
            retracement_pct=float(leg.retracement_pct),
            formed=False,  # Formation computed by Reference Layer at runtime (#394)
            status=leg.status,
            bar_count=leg.bar_count,
            origin_breached=leg.max_origin_breach is not None,  # #345: structural gate
            # Impulsiveness and spikiness replace raw impulse (#241)
            impulsiveness=leg.impulsiveness,
            spikiness=leg.spikiness,
            # Hierarchy fields for exploration (#250, #251)
            parent_leg_id=leg.parent_leg_id,
            # Segment impulse tracking (#307)
            impulse_to_deepest=leg.impulse_to_deepest,
            impulse_back=leg.impulse_back,
            net_segment_impulse=leg.net_segment_impulse,
        )
        for leg in state.active_legs
    ]

    # Convert pending origins with csv indices (#300)
    pending_origins = {
        direction: DagPendingOrigin(
            price=float(origin.price),
            bar_index=window_offset + origin.bar_index,  # Convert to csv_index (#300)
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
            "bull": {"engulfed_breach_threshold": 0.1},
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

    # Start with current config (preserve existing settings)
    new_config = detector.config

    # Apply global threshold updates (#404: all thresholds are symmetric)
    if request.stale_extension_threshold is not None:
        new_config = new_config.with_stale_extension(request.stale_extension_threshold)
    if request.origin_range_threshold is not None or request.origin_time_threshold is not None:
        new_config = new_config.with_origin_prune(
            origin_range_prune_threshold=request.origin_range_threshold,
            origin_time_prune_threshold=request.origin_time_threshold,
        )
    if request.max_turns is not None:
        new_config = new_config.with_max_turns(request.max_turns)
    if request.engulfed_breach_threshold is not None:
        new_config = new_config.with_engulfed(request.engulfed_breach_threshold)

    # Update detector config (keeps current state, applies to future bars)
    detector.update_config(new_config)

    # Update reference layer with new config, preserving accumulated state
    old_ref_layer = _replay_cache.get("reference_layer")
    new_ref_layer = ReferenceLayer(new_config)
    if old_ref_layer is not None:
        new_ref_layer.copy_state_from(old_ref_layer)
    _replay_cache["reference_layer"] = new_ref_layer

    logger.info(
        f"Config updated (continuing from current position): "
        f"{len([leg for leg in detector.state.active_legs if leg.status == 'active'])} active legs"
    )

    # Build response with current config values (#404: symmetric config)
    return SwingConfigResponse(
        stale_extension_threshold=new_config.stale_extension_threshold,
        origin_range_threshold=new_config.origin_range_prune_threshold,
        origin_time_threshold=new_config.origin_time_prune_threshold,
        max_turns=new_config.max_turns,
        engulfed_breach_threshold=new_config.engulfed_breach_threshold,
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
        config = DetectionConfig.default()

    # #404: symmetric config
    return SwingConfigResponse(
        stale_extension_threshold=config.stale_extension_threshold,
        origin_range_threshold=config.origin_range_prune_threshold,
        origin_time_threshold=config.origin_time_prune_threshold,
        max_turns=config.max_turns,
        engulfed_breach_threshold=config.engulfed_breach_threshold,
    )


# ============================================================================
# Reference State Endpoint (#375 - Reference Layer UI)
# ============================================================================


from pydantic import BaseModel


class ReferenceSwingResponse(BaseModel):
    """API response for a single reference swing."""
    leg_id: str
    scale: str
    depth: int
    location: float
    salience_score: float
    direction: str
    origin_price: float
    origin_index: int
    pivot_price: float
    pivot_index: int


class ReferenceStateApiResponse(BaseModel):
    """API response for reference layer state."""
    references: List[ReferenceSwingResponse]
    by_scale: Dict[str, List[ReferenceSwingResponse]]
    by_depth: Dict[int, List[ReferenceSwingResponse]]
    by_direction: Dict[str, List[ReferenceSwingResponse]]
    direction_imbalance: Optional[str]
    is_warming_up: bool
    warmup_progress: List[int]
    tracked_leg_ids: List[str] = []  # Leg IDs tracked for level crossing


class FibLevelResponse(BaseModel):
    """API response for a single fib level."""
    price: float
    ratio: float
    leg_id: str
    scale: str
    direction: str


class ActiveLevelsResponse(BaseModel):
    """API response for all active fib levels."""
    levels_by_ratio: Dict[str, List[FibLevelResponse]]  # Keyed by ratio as string


class TrackLegRequest(BaseModel):
    """Request to track a leg for level crossing."""
    leg_id: str


def _reference_swing_to_response(ref: 'ReferenceSwing') -> ReferenceSwingResponse:
    """Convert ReferenceSwing to API response."""
    from ...swing_analysis.reference_layer import ReferenceSwing
    return ReferenceSwingResponse(
        leg_id=ref.leg.leg_id,
        scale=ref.scale,
        depth=ref.depth,
        location=ref.location,
        salience_score=ref.salience_score,
        direction=ref.leg.direction,
        origin_price=float(ref.leg.origin_price),
        origin_index=ref.leg.origin_index,
        pivot_price=float(ref.leg.pivot_price),
        pivot_index=ref.leg.pivot_index,
    )


@router.get("/api/reference-state", response_model=ReferenceStateApiResponse)
async def get_reference_state(bar_index: Optional[int] = Query(None)):
    """
    Get reference layer state at a given bar index.

    The reference layer filters DAG legs through formation, location, and
    breach checks, then annotates qualifying legs with scale and salience.

    Args:
        bar_index: Optional bar index for state. Uses current playback position if not provided.

    Returns:
        ReferenceStateApiResponse with all valid references and groupings.
    """
    from ..api import get_state
    from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceState

    global _replay_cache

    try:
        state = get_state()
    except Exception:
        # Return empty state if not initialized
        return ReferenceStateApiResponse(
            references=[],
            by_scale={'S': [], 'M': [], 'L': [], 'XL': []},
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=[0, 50],
        )

    detector = _replay_cache.get("detector")
    if detector is None:
        return ReferenceStateApiResponse(
            references=[],
            by_scale={'S': [], 'M': [], 'L': [], 'XL': []},
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=[0, 50],
        )

    # Get or create reference layer
    reference_layer = _replay_cache.get("reference_layer")
    if reference_layer is None:
        reference_layer = ReferenceLayer()
        _replay_cache["reference_layer"] = reference_layer

    # Determine the target bar index
    target_index = bar_index
    if target_index is None:
        target_index = _replay_cache.get("last_bar_index", 0)

    # Get bar at target index
    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return ReferenceStateApiResponse(
            references=[],
            by_scale={'S': [], 'M': [], 'L': [], 'XL': []},
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=[0, 50],
        )

    # Get active legs from detector
    active_legs = detector.state.active_legs

    # Update reference layer and get state
    ref_state: ReferenceState = reference_layer.update(active_legs, bar)

    # Convert to API response
    refs_response = [_reference_swing_to_response(r) for r in ref_state.references]

    by_scale_response = {
        scale: [_reference_swing_to_response(r) for r in refs]
        for scale, refs in ref_state.by_scale.items()
    }

    by_depth_response = {
        depth: [_reference_swing_to_response(r) for r in refs]
        for depth, refs in ref_state.by_depth.items()
    }

    by_direction_response = {
        direction: [_reference_swing_to_response(r) for r in refs]
        for direction, refs in ref_state.by_direction.items()
    }

    return ReferenceStateApiResponse(
        references=refs_response,
        by_scale=by_scale_response,
        by_depth=by_depth_response,
        by_direction=by_direction_response,
        direction_imbalance=ref_state.direction_imbalance,
        is_warming_up=ref_state.is_warming_up,
        warmup_progress=list(ref_state.warmup_progress),
        tracked_leg_ids=list(reference_layer.get_tracked_leg_ids()),
    )


@router.get("/api/reference/levels", response_model=ActiveLevelsResponse)
async def get_reference_levels(bar_index: Optional[int] = Query(None)):
    """
    Get all fib levels from valid references.

    Returns fib levels (0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2) for each
    valid reference. Used for hover preview and sticky level display.

    Args:
        bar_index: Optional bar index for state. Uses current playback position if not provided.

    Returns:
        ActiveLevelsResponse with levels grouped by fib ratio.
    """
    from ..api import get_state
    from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceState

    global _replay_cache

    try:
        state = get_state()
    except Exception:
        return ActiveLevelsResponse(levels_by_ratio={})

    detector = _replay_cache.get("detector")
    if detector is None:
        return ActiveLevelsResponse(levels_by_ratio={})

    reference_layer = _replay_cache.get("reference_layer")
    if reference_layer is None:
        reference_layer = ReferenceLayer()
        _replay_cache["reference_layer"] = reference_layer

    target_index = bar_index
    if target_index is None:
        target_index = _replay_cache.get("last_bar_index", 0)

    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return ActiveLevelsResponse(levels_by_ratio={})

    active_legs = detector.state.active_legs
    ref_state: ReferenceState = reference_layer.update(active_legs, bar)

    # Get active levels
    levels_dict = reference_layer.get_active_levels(ref_state)

    # Convert to response format
    levels_by_ratio: Dict[str, List[FibLevelResponse]] = {}
    for ratio, level_infos in levels_dict.items():
        ratio_key = str(ratio)
        levels_by_ratio[ratio_key] = [
            FibLevelResponse(
                price=info.price,
                ratio=info.ratio,
                leg_id=info.reference.leg.leg_id,
                scale=info.reference.scale,
                direction=info.reference.leg.direction,
            )
            for info in level_infos
        ]

    return ActiveLevelsResponse(levels_by_ratio=levels_by_ratio)


@router.post("/api/reference/track/{leg_id}")
async def track_leg_for_crossing(leg_id: str):
    """
    Add a leg to level crossing tracking.

    When tracked, the leg's fib levels become "sticky" - they persist
    on the chart even when the mouse moves away. Multiple legs can be
    tracked simultaneously.

    Args:
        leg_id: The leg_id to start tracking.

    Returns:
        Success message with current tracked leg count.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer

    global _replay_cache

    reference_layer = _replay_cache.get("reference_layer")
    if reference_layer is None:
        reference_layer = ReferenceLayer()
        _replay_cache["reference_layer"] = reference_layer

    reference_layer.add_crossing_tracking(leg_id)

    return {
        "success": True,
        "leg_id": leg_id,
        "tracked_count": len(reference_layer.get_tracked_leg_ids()),
    }


@router.delete("/api/reference/track/{leg_id}")
async def untrack_leg_for_crossing(leg_id: str):
    """
    Remove a leg from level crossing tracking.

    The leg's fib levels will no longer be sticky and will only appear
    on hover.

    Args:
        leg_id: The leg_id to stop tracking.

    Returns:
        Success message with current tracked leg count.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer

    global _replay_cache

    reference_layer = _replay_cache.get("reference_layer")
    if reference_layer is None:
        return {
            "success": True,
            "leg_id": leg_id,
            "tracked_count": 0,
        }

    reference_layer.remove_crossing_tracking(leg_id)

    return {
        "success": True,
        "leg_id": leg_id,
        "tracked_count": len(reference_layer.get_tracked_leg_ids()),
    }
