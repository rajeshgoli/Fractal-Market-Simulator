"""
DAG router for Replay View.

Provides all DAG-related endpoints:
- POST /api/dag/init - Initialize detector (replaces /api/replay/calibrate)
- POST /api/dag/advance - Advance playback
- POST /api/dag/reverse - Reverse playback
- GET /api/dag/state - Get current DAG state
- GET /api/dag/lineage/{leg_id} - Get leg lineage
- GET /api/dag/events - Get all lifecycle events
- GET /api/dag/followed-legs - Get events for followed legs
- GET /api/dag/config - Get detection config
- PUT /api/dag/config - Update detection config
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ...swing_analysis.dag import LegDetector
from ...swing_analysis.detection_config import DetectionConfig
from ...swing_analysis.reference_layer import ReferenceLayer
from ..schemas import (
    ReplayAdvanceRequest,
    ReplayReverseRequest,
    ReplayBarResponse,
    ReplayEventResponse,
    ReplayAdvanceResponse,
    RefStateSnapshot,
    TreeStatistics,
    SwingsByDepth,
    CalibrationResponseHierarchical,
    DagLegResponse,
    DagPendingOrigin,
    DagLegCounts,
    DagStateResponse,
    LegLineageResponse,
    LifecycleEvent,
    FollowedLegsEventsResponse,
    SwingConfigUpdateRequest,
    SwingConfigResponse,
)
from .helpers import (
    event_to_response,
    event_to_lifecycle_event,
    build_swing_state,
    build_aggregated_bars,
    build_dag_state,
    build_ref_state_snapshot,
)
from .cache import get_replay_cache, is_initialized

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dag"])


# ============================================================================
# Lazy Initialization Helper (#412)
# ============================================================================


def _ensure_initialized() -> None:
    """
    Ensure detector is initialized, creating a fresh one if needed.

    This enables lazy initialization - endpoints that need a detector
    can call this instead of requiring explicit /api/dag/init first.
    """
    from ..api import get_state

    cache = get_replay_cache()

    if cache.get("detector") is not None:
        return  # Already initialized

    s = get_state()

    logger.info("Lazy-initializing detector for DAG mode")

    # Preserve ReferenceConfig if it exists (#459)
    old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

    config = DetectionConfig.default()
    ref_layer = ReferenceLayer(config, reference_config=old_ref_config)
    detector = LegDetector(config)

    # Initialize cache for incremental advance
    cache["detector"] = detector
    cache["last_bar_index"] = -1
    cache["reference_layer"] = ref_layer
    cache["source_resolution"] = s.resolution_minutes
    cache["lifecycle_events"] = []

    # Update app state
    s.playback_index = -1
    s.hierarchical_detector = detector

    logger.info("Lazy init complete: detector ready for incremental advance")


# ============================================================================
# Init Endpoint (formerly /api/replay/calibrate)
# ============================================================================


@router.post("/api/dag/init", response_model=CalibrationResponseHierarchical)
async def init_dag():
    """
    Initialize detector for DAG playback.

    Creates a fresh LegDetector with empty state, ready for incremental
    bar processing via /api/dag/advance.

    Note: The bar_count parameter has been removed. Batch warmup is no longer
    supported - use /api/dag/advance with large step counts for bulk processing.
    """
    from ..api import get_state

    cache = get_replay_cache()
    s = get_state()

    logger.info("Initializing detector for DAG mode")

    # Preserve ReferenceConfig if it exists (#459)
    old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

    config = DetectionConfig.default()
    ref_layer = ReferenceLayer(config, reference_config=old_ref_config)
    detector = LegDetector(config)

    # Initialize cache for incremental advance
    cache["detector"] = detector
    cache["last_bar_index"] = -1
    cache["reference_layer"] = ref_layer
    cache["source_resolution"] = s.resolution_minutes
    cache["lifecycle_events"] = []

    # Update app state
    s.playback_index = -1
    s.hierarchical_detector = detector

    # Return empty response
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
        current_price=s.source_bars[0].open if s.source_bars else 0.0,
        tree_stats=empty_tree_stats,
        swings_by_depth=empty_swings_by_depth,
        active_swings_by_depth=empty_swings_by_depth,
    )


# ============================================================================
# Reset Endpoint (#412)
# ============================================================================


@router.post("/api/dag/reset", response_model=CalibrationResponseHierarchical)
async def reset_dag():
    """
    Reset detector state, starting fresh.

    Clears all existing state and creates a new empty detector.
    Use this when you want to restart detection from bar 0.
    """
    from ..api import get_state

    cache = get_replay_cache()
    s = get_state()

    logger.info("Resetting detector for DAG mode")

    # Preserve ReferenceConfig if it exists (#459)
    old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

    config = DetectionConfig.default()
    ref_layer = ReferenceLayer(config, reference_config=old_ref_config)
    detector = LegDetector(config)

    # Reset cache to initial state
    cache["detector"] = detector
    cache["last_bar_index"] = -1
    cache["reference_layer"] = ref_layer
    cache["source_resolution"] = s.resolution_minutes
    cache["lifecycle_events"] = []

    # Update app state
    s.playback_index = -1
    s.hierarchical_detector = detector

    # Return empty response
    empty_tree_stats = TreeStatistics(
        root_swings=0, root_bull=0, root_bear=0, total_nodes=0,
        max_depth=0, avg_children=0.0,
        defended_by_depth={"1": 0, "2": 0, "3": 0, "deeper": 0},
        largest_range=0.0, largest_leg_id=None, median_range=0.0,
        smallest_range=0.0,
        roots_have_children=True, siblings_detected=False, no_orphaned_nodes=True,
    )
    empty_swings_by_depth = SwingsByDepth()

    logger.info("DAG mode: detector reset, ready for incremental advance")
    return CalibrationResponseHierarchical(
        current_price=s.source_bars[0].open if s.source_bars else 0.0,
        tree_stats=empty_tree_stats,
        swings_by_depth=empty_swings_by_depth,
        active_swings_by_depth=empty_swings_by_depth,
    )


# ============================================================================
# Advance Endpoint (formerly /api/replay/advance)
# ============================================================================


@router.post("/api/dag/advance", response_model=ReplayAdvanceResponse)
async def advance_dag(request: ReplayAdvanceRequest):
    """
    Advance playback by processing additional bars.

    Uses detector.process_bar() for incremental detection.
    """
    from ..api import get_state

    cache = get_replay_cache()
    s = get_state()

    # Lazy init: auto-initialize detector if not present (#412)
    _ensure_initialized()
    detector = cache["detector"]

    # Handle from_index resync (#310): if FE is behind BE, replay to sync
    from_index = request.from_index
    if from_index is not None and from_index != cache["last_bar_index"]:
        logger.info(
            f"Resync needed: BE at {cache['last_bar_index']}, "
            f"FE at {from_index}. Replaying to sync."
        )

        # Get preserved config from current detector
        old_detector = cache["detector"]
        config = old_detector.config

        # Preserve ReferenceConfig (#459)
        old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

        # Create fresh detector with same config
        detector = LegDetector(config)
        ref_layer = ReferenceLayer(config, reference_config=old_ref_config)

        # Clear lifecycle events - we'll rebuild them during replay
        cache["lifecycle_events"] = []

        # Replay all bars up to from_index
        bars_to_process = s.source_bars[:from_index + 1] if from_index >= 0 else []
        for bar in bars_to_process:
            timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

            # Process bar
            events = detector.process_bar(bar)

            # Side effects only during bulk advance - skip response building (#437)
            ref_layer.update(detector.state.active_legs, bar, build_response=False)

            # Capture lifecycle events during replay
            csv_index = s.window_offset + bar.index
            ts_iso = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
            for event in events:
                lifecycle_event = event_to_lifecycle_event(event, bar.index, csv_index, ts_iso)
                if lifecycle_event:
                    cache["lifecycle_events"].append(lifecycle_event)

        # Update cache with fresh detector
        cache["detector"] = detector
        cache["last_bar_index"] = from_index
        cache["reference_layer"] = ref_layer

        # Update app state
        s.playback_index = from_index
        s.hierarchical_detector = detector

        logger.info(f"Resync complete: BE now at {from_index}")

    # Validate request (only warn, don't resync again)
    if request.current_bar_index != cache["last_bar_index"]:
        logger.warning(
            f"Bar index mismatch: expected {cache['last_bar_index']}, "
            f"got {request.current_bar_index}"
        )

    # Calculate new bar range
    start_idx = cache["last_bar_index"] + 1
    end_idx = min(start_idx + request.advance_by, len(s.source_bars))

    if start_idx >= len(s.source_bars):
        # End of data
        current_bar = s.source_bars[-1]
        active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
        # scale_thresholds removed (#412) - Reference Layer owns scale
        scale_thresholds: Dict[str, float] = {}

        # Build optional fields
        aggregated_bars = None
        if request.include_aggregated_bars:
            source_resolution = cache.get("source_resolution", s.resolution_minutes)
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
    # scale_thresholds removed (#412) - Reference Layer owns scale
    scale_thresholds: Dict[str, float] = {}

    # Per-bar DAG states for high-speed playback (#283)
    per_bar_dag_states: List[DagStateResponse] = []

    # Per-bar Reference states for buffered playback (#451)
    per_bar_ref_states: List[RefStateSnapshot] = []

    # Get Reference layer from cache for tolerance-based checks (#175)
    ref_layer = cache.get("reference_layer")

    for idx in range(start_idx, end_idx):
        bar = s.source_bars[idx]

        # Process bar with detector (DAG events)
        events = detector.process_bar(bar)

        # Update reference layer - build full response only when per-bar states requested (#456)
        ref_state = None
        if ref_layer is not None:
            if request.include_per_bar_ref_states:
                # Build full response for per-bar snapshots (#456)
                ref_state = ref_layer.update(detector.state.active_legs, bar, build_response=True)
            else:
                # Side effects only during bulk advance - skip response building (#437)
                ref_layer.update(detector.state.active_legs, bar, build_response=False)

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
                cache["lifecycle_events"].append(lifecycle_event)

        # Snapshot DAG state after each bar for high-speed playback (#283)
        if request.include_per_bar_dag_states:
            per_bar_dag_states.append(build_dag_state(detector, s.window_offset))

        # Snapshot full Reference state after each bar for buffered playback (#456, #458)
        if request.include_per_bar_ref_states and ref_layer is not None and ref_state is not None:
            per_bar_ref_states.append(build_ref_state_snapshot(
                bar.index,
                ref_layer,
                ref_state,
                bar,
                detector.state.active_legs,  # #458: for crossing detection
            ))

    # Update cache state
    cache["last_bar_index"] = end_idx - 1
    s.playback_index = end_idx - 1

    # Build current swing state from active legs
    active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
    swing_state = build_swing_state(active_legs, scale_thresholds)

    current_bar = s.source_bars[end_idx - 1]
    end_of_data = end_idx >= len(s.source_bars)

    # Build optional aggregated bars (for batched playback)
    aggregated_bars = None
    if request.include_aggregated_bars:
        source_resolution = cache.get("source_resolution", s.resolution_minutes)
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

    # Include per-bar Reference states for buffered playback (#451)
    ref_states = per_bar_ref_states if request.include_per_bar_ref_states else None

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
        ref_states=ref_states,
    )


# ============================================================================
# Reverse Endpoint (formerly /api/replay/reverse)
# ============================================================================


@router.post("/api/dag/reverse", response_model=ReplayAdvanceResponse)
async def reverse_dag(request: ReplayReverseRequest):
    """
    Reverse playback by one bar.

    Implementation: resets detector and replays from bar 0 to current_bar_index - 1.
    """
    from ..api import get_state

    cache = get_replay_cache()
    s = get_state()

    # Lazy init: auto-initialize detector if not present (#412)
    _ensure_initialized()

    # Validate bar index
    current_idx = request.current_bar_index
    if current_idx != cache["last_bar_index"]:
        logger.warning(
            f"Bar index mismatch on reverse: cache has {cache['last_bar_index']}, "
            f"request has {current_idx}"
        )

    target_idx = current_idx - 1

    # Can't go before bar 0
    if target_idx < 0:
        current_bar = s.source_bars[0] if s.source_bars else None
        if current_bar is None:
            raise HTTPException(status_code=400, detail="No bars loaded")

        detector = cache["detector"]
        active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
        # scale_thresholds removed (#412) - Reference Layer owns scale
        scale_thresholds: Dict[str, float] = {}

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
    old_detector = cache["detector"]
    config = old_detector.config

    # Preserve ReferenceConfig (#459)
    old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

    # Create fresh detector with same config
    detector = LegDetector(config)
    ref_layer = ReferenceLayer(config, reference_config=old_ref_config)

    # Clear lifecycle events - we'll rebuild them during replay (#299)
    cache["lifecycle_events"] = []

    # Replay all bars up to target
    bars_to_process = s.source_bars[:target_idx + 1]
    for bar in bars_to_process:
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # Process bar
        events = detector.process_bar(bar)

        # Side effects only during bulk advance - skip response building (#437)
        ref_layer.update(detector.state.active_legs, bar, build_response=False)

        # Capture lifecycle events during replay (#299)
        csv_index = s.window_offset + bar.index
        ts_iso = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        for event in events:
            lifecycle_event = event_to_lifecycle_event(event, bar.index, csv_index, ts_iso)
            if lifecycle_event:
                cache["lifecycle_events"].append(lifecycle_event)

    # Update cache
    cache["detector"] = detector
    cache["last_bar_index"] = target_idx
    cache["reference_layer"] = ref_layer

    # Update app state
    s.playback_index = target_idx
    s.hierarchical_detector = detector

    # Build response
    current_bar = s.source_bars[target_idx]
    active_legs = [leg for leg in detector.state.active_legs if leg.status == "active"]
    # scale_thresholds removed (#412) - Reference Layer owns scale
    scale_thresholds: Dict[str, float] = {}
    swing_state = build_swing_state(active_legs, scale_thresholds)

    # Build optional aggregated bars
    aggregated_bars = None
    if request.include_aggregated_bars:
        source_resolution = cache.get("source_resolution", s.resolution_minutes)
        aggregated_bars = build_aggregated_bars(
            s.source_bars,
            request.include_aggregated_bars,
            source_resolution,
            limit=target_idx + 1,
        )

    dag_state = build_dag_state(detector, s.window_offset) if request.include_dag_state else None

    return ReplayAdvanceResponse(
        new_bars=[],
        events=[],
        swing_state=swing_state,
        current_bar_index=target_idx,
        current_price=current_bar.close,
        end_of_data=False,
        csv_index=s.window_offset + target_idx,
        aggregated_bars=aggregated_bars,
        dag_state=dag_state,
        dag_states=None,
    )


# ============================================================================
# State Endpoint
# ============================================================================


@router.get("/api/dag/state", response_model=DagStateResponse)
async def get_dag_state():
    """
    Get current DAG internal state for visualization.

    Exposes leg-level state from the detector for debugging and DAG visualization:
    - active_legs: Currently tracked legs
    - pending_origins: Potential origins for new legs
    - leg_counts: Count of legs by direction
    """
    from ..api import get_state

    cache = get_replay_cache()

    # Lazy init: auto-initialize detector if not present (#412)
    _ensure_initialized()

    s = get_state()
    window_offset = s.window_offset
    detector = cache["detector"]
    state = detector.state

    # Convert active legs to response with csv indices (#300)
    active_legs = [
        DagLegResponse(
            leg_id=leg.leg_id,
            direction=leg.direction,
            pivot_price=float(leg.pivot_price),
            pivot_index=window_offset + leg.pivot_index,
            origin_price=float(leg.origin_price),
            origin_index=window_offset + leg.origin_index,
            retracement_pct=float(leg.retracement_pct),
            status=leg.status,
            bar_count=leg.bar_count,
            origin_breached=leg.max_origin_breach is not None,
            impulsiveness=leg.impulsiveness,
            spikiness=leg.spikiness,
            parent_leg_id=leg.parent_leg_id,
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
            bar_index=window_offset + origin.bar_index,
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


# ============================================================================
# Lineage Endpoint
# ============================================================================


@router.get("/api/dag/lineage/{leg_id}", response_model=LegLineageResponse)
async def get_leg_lineage(leg_id: str):
    """
    Get full lineage for a leg (ancestors and descendants).

    Used by the frontend for hierarchy exploration mode (#250).
    """
    cache = get_replay_cache()

    # Lazy init: auto-initialize detector if not present (#412)
    _ensure_initialized()

    detector = cache["detector"]
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
    visited = {leg_id}
    while current_id and current_id in legs_by_id and current_id not in visited:
        ancestors.append(current_id)
        visited.add(current_id)
        current_id = legs_by_id[current_id].parent_leg_id

    # Build descendants by finding all legs whose ancestor chain includes this leg
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

    descendants: List[str] = []
    for lid in legs_by_id:
        if lid == leg_id:
            continue
        leg_ancestors = get_ancestors(lid)
        if leg_id in leg_ancestors:
            descendants.append(lid)

    depth = len(ancestors)

    return LegLineageResponse(
        leg_id=leg_id,
        ancestors=ancestors,
        descendants=descendants,
        depth=depth,
    )


# ============================================================================
# Events Endpoints
# ============================================================================


@router.get("/api/dag/events", response_model=FollowedLegsEventsResponse)
async def get_all_lifecycle_events():
    """
    Get all lifecycle events from the current session.

    Returns all cached lifecycle events. Used to restore frontend state
    when switching views (DAG View -> Reference View -> DAG View).
    """
    cache = get_replay_cache()

    if cache.get("detector") is None:
        return FollowedLegsEventsResponse(events=[])

    lifecycle_events = cache.get("lifecycle_events", [])
    return FollowedLegsEventsResponse(events=lifecycle_events)


@router.get("/api/dag/followed-legs", response_model=FollowedLegsEventsResponse)
async def get_followed_legs_events(
    leg_ids: str = Query(..., description="Comma-separated list of leg IDs to track"),
    since_bar: int = Query(..., description="Only return events from this bar index onwards"),
):
    """
    Get lifecycle events for followed legs.

    Returns events for the specified leg IDs that occurred at or after the
    since_bar index. Used by the Follow Leg feature to show event markers.
    """
    cache = get_replay_cache()

    # Parse leg IDs
    leg_id_set = set(lid.strip() for lid in leg_ids.split(",") if lid.strip())

    if not leg_id_set:
        return FollowedLegsEventsResponse(events=[])

    # Filter lifecycle events
    lifecycle_events = cache.get("lifecycle_events", [])
    filtered_events = [
        event for event in lifecycle_events
        if event.leg_id in leg_id_set and event.bar_index >= since_bar
    ]

    return FollowedLegsEventsResponse(events=filtered_events)


# ============================================================================
# Config Endpoints (formerly /api/replay/config)
# ============================================================================


@router.get("/api/dag/config", response_model=SwingConfigResponse)
async def get_detection_config():
    """
    Get current swing detection configuration.

    Returns the current configuration values being used by the detector.
    If no detector is initialized, returns the default configuration.
    """
    cache = get_replay_cache()

    # Get detector config or use defaults
    if is_initialized():
        config = cache["detector"].config
    else:
        config = DetectionConfig.default()

    return SwingConfigResponse(
        stale_extension_threshold=config.stale_extension_threshold,
        origin_range_threshold=config.origin_range_prune_threshold,
        origin_time_threshold=config.origin_time_prune_threshold,
        max_turns=config.max_turns,
        engulfed_breach_threshold=config.engulfed_breach_threshold,
    )


@router.put("/api/dag/config", response_model=SwingConfigResponse)
async def update_detection_config(request: SwingConfigUpdateRequest):
    """
    Update swing detection configuration.

    This endpoint allows changing detection thresholds. The new config
    applies to future bars; existing legs are not re-processed.
    """
    cache = get_replay_cache()

    # Lazy init: auto-initialize detector if not present (#412)
    _ensure_initialized()

    detector = cache["detector"]

    # Start with current config (preserve existing settings)
    new_config = detector.config

    # Apply global threshold updates (#404: all symmetric)
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

    # Update reference layer with new config, preserving accumulated state and ReferenceConfig (#459)
    old_ref_layer = cache.get("reference_layer")
    old_ref_config = old_ref_layer.reference_config if old_ref_layer else None
    new_ref_layer = ReferenceLayer(new_config, reference_config=old_ref_config)
    if old_ref_layer is not None:
        new_ref_layer.copy_state_from(old_ref_layer)
    cache["reference_layer"] = new_ref_layer

    logger.info(
        f"Config updated (continuing from current position): "
        f"{len([leg for leg in detector.state.active_legs if leg.status == 'active'])} active legs"
    )

    return SwingConfigResponse(
        stale_extension_threshold=new_config.stale_extension_threshold,
        origin_range_threshold=new_config.origin_range_prune_threshold,
        origin_time_threshold=new_config.origin_time_prune_threshold,
        max_turns=new_config.max_turns,
        engulfed_breach_threshold=new_config.engulfed_breach_threshold,
    )
