"""
Reference Layer router for Replay View.

Provides endpoints for Reference Layer state, active levels, and level tracking.

Endpoints:
- GET /api/reference/state - Get reference layer state
- GET /api/reference/levels - Get all fib levels from valid references
- POST /api/reference/track/{leg_id} - Add leg to crossing tracking
- DELETE /api/reference/track/{leg_id} - Remove leg from crossing tracking
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from ..schemas import (
    ReferenceSwingResponse,
    ReferenceStateApiResponse,
    FibLevelResponse,
    ActiveLevelsResponse,
    FilteredLegResponse,
    FilterStatsResponse,
    ConfluenceZoneLevelResponse,
    ConfluenceZoneResponse,
    ConfluenceZonesResponse,
    LevelTouchResponse,
    StructurePanelResponse,
    TopReferenceResponse,
    TelemetryPanelResponse,
    LevelCrossEventResponse,
    CrossingEventsResponse,
    TrackLegResponse,
    ReferenceConfigResponse,
    ReferenceConfigUpdateRequest,
)
from .cache import get_replay_cache, is_initialized

router = APIRouter(tags=["reference"])


def _reference_swing_to_response(ref_swing) -> ReferenceSwingResponse:
    """Convert ReferenceSwing to API response."""
    return ReferenceSwingResponse(
        leg_id=ref_swing.leg.leg_id,
        scale=ref_swing.scale,
        depth=ref_swing.leg.depth,
        location=ref_swing.location,
        salience_score=ref_swing.salience_score,
        direction=ref_swing.leg.direction,
        origin_price=float(ref_swing.leg.origin_price),
        origin_index=ref_swing.leg.origin_index,
        pivot_price=float(ref_swing.leg.pivot_price),
        pivot_index=ref_swing.leg.pivot_index,
        impulsiveness=ref_swing.leg.impulsiveness,
    )


def _filtered_leg_to_response(filtered_leg) -> FilteredLegResponse:
    """Convert FilteredLeg to API response."""
    return FilteredLegResponse(
        leg_id=filtered_leg.leg.leg_id,
        direction=filtered_leg.leg.direction,
        origin_price=float(filtered_leg.leg.origin_price),
        origin_index=filtered_leg.leg.origin_index,
        pivot_price=float(filtered_leg.leg.pivot_price),
        pivot_index=filtered_leg.leg.pivot_index,
        scale=filtered_leg.scale,
        filter_reason=filtered_leg.reason.value,
        location=filtered_leg.location,
        threshold=filtered_leg.threshold,
    )


def _compute_filter_stats(all_statuses, valid_leg_ids: set) -> FilterStatsResponse:
    """Compute filter statistics from all leg statuses."""
    total = len(all_statuses)
    valid_count = len(valid_leg_ids)

    # Count by reason
    by_reason = {
        'not_formed': 0,
        'pivot_breached': 0,
        'origin_breached': 0,
        'completed': 0,
        'cold_start': 0,
    }

    for status in all_statuses:
        reason = status.reason.value
        if reason != 'valid' and reason in by_reason:
            by_reason[reason] += 1

    return FilterStatsResponse(
        total_legs=total,
        valid_count=valid_count,
        pass_rate=valid_count / total if total > 0 else 0.0,
        by_reason=by_reason,
    )


def _level_cross_event_to_response(event) -> LevelCrossEventResponse:
    """Convert LevelCrossEvent to API response."""
    return LevelCrossEventResponse(
        leg_id=event.leg_id,
        direction=event.direction,
        level_crossed=event.level_crossed,
        cross_direction=event.cross_direction,
        bar_index=event.bar_index,
        timestamp=event.timestamp.isoformat(),
    )


def _empty_response() -> ReferenceStateApiResponse:
    """Return an empty reference state response."""
    return ReferenceStateApiResponse(
        references=[],
        by_scale={'S': [], 'M': [], 'L': [], 'XL': []},
        by_depth={},
        by_direction={'bull': [], 'bear': []},
        direction_imbalance=None,
        is_warming_up=True,
        warmup_progress=[0, 50],
        filtered_legs=[],
        filter_stats=FilterStatsResponse(
            total_legs=0,
            valid_count=0,
            pass_rate=0.0,
            by_reason={'not_formed': 0, 'pivot_breached': 0, 'origin_breached': 0, 'completed': 0, 'cold_start': 0},
        ),
        crossing_events=[],
    )


@router.get("/api/reference/state", response_model=ReferenceStateApiResponse)
async def get_reference_state(bar_index: Optional[int] = Query(None)):
    """
    Get reference layer state at a given bar index.

    The reference layer filters DAG legs through formation, location, and
    breach checks, then annotates qualifying legs with scale and salience.

    Args:
        bar_index: Optional bar index for state. Uses current playback position if not provided.

    Returns:
        ReferenceStateApiResponse with all valid references, groupings,
        filtered legs, and filter statistics for observation mode.
    """
    from ..api import get_state
    from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceState, FilterReason

    cache = get_replay_cache()

    try:
        state = get_state()
    except Exception:
        return _empty_response()

    if not is_initialized():
        return _empty_response()

    # Get or create reference layer
    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    # Determine the target bar index
    target_index = bar_index
    if target_index is None:
        target_index = cache.get("last_bar_index", 0)

    # Get bar at target index
    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return _empty_response()

    # Get active legs from detector
    detector = cache["detector"]
    active_legs = detector.state.active_legs

    # Update reference layer and get state
    ref_layer = cache["reference_layer"]
    ref_state: ReferenceState = ref_layer.update(active_legs, bar)

    # Get all legs with filter status for observation mode
    all_statuses = ref_layer.get_all_with_status(active_legs, bar)

    # Build valid leg IDs set for stats
    valid_leg_ids = {r.leg.leg_id for r in ref_state.references}

    # Get only filtered (non-valid) legs for response
    filtered_legs = [
        _filtered_leg_to_response(s)
        for s in all_statuses
        if s.reason != FilterReason.VALID
    ]

    # Compute filter statistics
    filter_stats = _compute_filter_stats(all_statuses, valid_leg_ids)

    # Detect level crossings for tracked legs
    crossing_events = ref_layer.detect_level_crossings(active_legs, bar)

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

    crossing_events_response = [
        _level_cross_event_to_response(e) for e in crossing_events
    ]

    return ReferenceStateApiResponse(
        references=refs_response,
        by_scale=by_scale_response,
        by_depth=by_depth_response,
        by_direction=by_direction_response,
        direction_imbalance=ref_state.direction_imbalance,
        is_warming_up=ref_state.is_warming_up,
        warmup_progress=list(ref_state.warmup_progress),
        tracked_leg_ids=list(ref_layer.get_tracked_leg_ids()),
        filtered_legs=filtered_legs,
        filter_stats=filter_stats,
        crossing_events=crossing_events_response,
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

    cache = get_replay_cache()

    try:
        state = get_state()
    except Exception:
        return ActiveLevelsResponse(levels_by_ratio={})

    if not is_initialized():
        return ActiveLevelsResponse(levels_by_ratio={})

    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    target_index = bar_index
    if target_index is None:
        target_index = cache.get("last_bar_index", 0)

    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return ActiveLevelsResponse(levels_by_ratio={})

    detector = cache["detector"]
    active_legs = detector.state.active_legs
    ref_layer = cache["reference_layer"]
    ref_state: ReferenceState = ref_layer.update(active_legs, bar)

    # Get active levels
    levels_dict = ref_layer.get_active_levels(ref_state)

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


@router.post("/api/reference/track/{leg_id}", response_model=TrackLegResponse)
async def track_leg_for_crossing(leg_id: str):
    """
    Add a leg to level crossing tracking.

    When tracked, the leg's fib levels become "sticky" - they persist
    on the chart even when the mouse moves away. Additionally, level
    crossing events will be emitted when price crosses fib levels for
    this leg.

    A maximum of 10 legs can be tracked at once for performance reasons.

    Args:
        leg_id: The leg_id to start tracking.

    Returns:
        TrackLegResponse with success status and tracked count.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer

    cache = get_replay_cache()

    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    ref_layer = cache["reference_layer"]
    success, error = ref_layer.add_crossing_tracking(leg_id)

    return TrackLegResponse(
        success=success,
        leg_id=leg_id,
        tracked_count=len(ref_layer.get_tracked_leg_ids()),
        error=error,
    )


@router.delete("/api/reference/track/{leg_id}", response_model=TrackLegResponse)
async def untrack_leg_for_crossing(leg_id: str):
    """
    Remove a leg from level crossing tracking.

    The leg's fib levels will no longer be sticky and will only appear on hover.
    Level crossing events will no longer be emitted for this leg.

    Args:
        leg_id: The leg_id to stop tracking.

    Returns:
        TrackLegResponse with success status and tracked count.
    """
    cache = get_replay_cache()

    if cache.get("reference_layer") is None:
        return TrackLegResponse(
            success=True,
            leg_id=leg_id,
            tracked_count=0,
            error=None,
        )

    ref_layer = cache["reference_layer"]
    ref_layer.remove_crossing_tracking(leg_id)

    return TrackLegResponse(
        success=True,
        leg_id=leg_id,
        tracked_count=len(ref_layer.get_tracked_leg_ids()),
        error=None,
    )


@router.get("/api/reference/crossings", response_model=CrossingEventsResponse)
async def get_crossing_events():
    """
    Get pending level crossing events.

    Returns all crossing events that have accumulated since the last call.
    Events are cleared after retrieval to prevent duplicates.

    Use this endpoint for polling-based crossing detection, or rely on
    the crossing_events field in the /api/reference/state response for
    per-bar crossing detection.

    Returns:
        CrossingEventsResponse with all pending events and tracked count.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer

    cache = get_replay_cache()

    if cache.get("reference_layer") is None:
        return CrossingEventsResponse(events=[], tracked_count=0)

    ref_layer = cache["reference_layer"]
    pending_events = ref_layer.get_pending_cross_events(clear=True)

    return CrossingEventsResponse(
        events=[_level_cross_event_to_response(e) for e in pending_events],
        tracked_count=len(ref_layer.get_tracked_leg_ids()),
    )


@router.get("/api/reference/confluence", response_model=ConfluenceZonesResponse)
async def get_confluence_zones(
    bar_index: Optional[int] = Query(None),
    tolerance_pct: Optional[float] = Query(None, description="Clustering tolerance (0.001 = 0.1%)"),
):
    """
    Get confluence zones - clustered fib levels from multiple references.

    When levels from different references fall within the tolerance, they form
    a confluence zone - an area of increased significance.

    Args:
        bar_index: Optional bar index for state. Uses current playback position if not provided.
        tolerance_pct: Optional tolerance override (default 0.001 = 0.1%).

    Returns:
        ConfluenceZonesResponse with all detected confluence zones.
    """
    from ..api import get_state
    from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceState

    cache = get_replay_cache()

    try:
        state = get_state()
    except Exception:
        return ConfluenceZonesResponse(zones=[], tolerance_pct=0.001)

    if not is_initialized():
        return ConfluenceZonesResponse(zones=[], tolerance_pct=0.001)

    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    target_index = bar_index
    if target_index is None:
        target_index = cache.get("last_bar_index", 0)

    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return ConfluenceZonesResponse(zones=[], tolerance_pct=0.001)

    detector = cache["detector"]
    active_legs = detector.state.active_legs
    ref_layer = cache["reference_layer"]
    ref_state: ReferenceState = ref_layer.update(active_legs, bar)

    # Get confluence zones
    zones = ref_layer.get_confluence_zones(ref_state, tolerance_pct=tolerance_pct)
    actual_tolerance = tolerance_pct if tolerance_pct is not None else ref_layer.reference_config.confluence_tolerance_pct

    # Convert to response format
    zone_responses = []
    for zone in zones:
        levels = [
            ConfluenceZoneLevelResponse(
                price=lvl.price,
                ratio=lvl.ratio,
                leg_id=lvl.reference.leg.leg_id,
                scale=lvl.reference.scale,
                direction=lvl.reference.leg.direction,
            )
            for lvl in zone.levels
        ]
        zone_responses.append(ConfluenceZoneResponse(
            center_price=zone.center_price,
            min_price=zone.min_price,
            max_price=zone.max_price,
            levels=levels,
            reference_count=zone.reference_count,
            reference_ids=list(zone.reference_ids),
        ))

    return ConfluenceZonesResponse(zones=zone_responses, tolerance_pct=actual_tolerance)


@router.get("/api/reference/structure", response_model=StructurePanelResponse)
async def get_structure_panel(bar_index: Optional[int] = Query(None)):
    """
    Get Structure Panel data - level touch history and active levels.

    Three sections per spec:
    1. Touched this session - Historical record of which levels were hit
    2. Currently active - Levels within striking distance of current price
    3. Current bar - Levels touched on most recent bar

    Args:
        bar_index: Optional bar index for state. Uses current playback position if not provided.

    Returns:
        StructurePanelResponse with all three sections populated.
    """
    from ..api import get_state
    from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceState

    cache = get_replay_cache()

    empty_response = StructurePanelResponse(
        touched_this_session=[],
        currently_active=[],
        current_bar_touches=[],
        current_price=0.0,
        active_level_distance_pct=0.005,
    )

    try:
        state = get_state()
    except Exception:
        return empty_response

    if not is_initialized():
        return empty_response

    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    target_index = bar_index
    if target_index is None:
        target_index = cache.get("last_bar_index", 0)

    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return empty_response

    detector = cache["detector"]
    active_legs = detector.state.active_legs
    ref_layer = cache["reference_layer"]
    ref_state: ReferenceState = ref_layer.update(active_legs, bar)

    # Get structure panel data
    panel_data = ref_layer.get_structure_panel_data(ref_state, bar)

    # Convert to response format
    def touch_to_response(touch) -> LevelTouchResponse:
        return LevelTouchResponse(
            price=touch.level.price,
            ratio=touch.level.ratio,
            leg_id=touch.level.reference.leg.leg_id,
            scale=touch.level.reference.scale,
            direction=touch.level.reference.leg.direction,
            bar_index=touch.bar_index,
            touch_price=touch.touch_price,
            cross_direction=touch.cross_direction,
        )

    def level_to_response(level) -> FibLevelResponse:
        return FibLevelResponse(
            price=level.price,
            ratio=level.ratio,
            leg_id=level.reference.leg.leg_id,
            scale=level.reference.scale,
            direction=level.reference.leg.direction,
        )

    return StructurePanelResponse(
        touched_this_session=[touch_to_response(t) for t in panel_data.touched_this_session],
        currently_active=[level_to_response(l) for l in panel_data.currently_active],
        current_bar_touches=[touch_to_response(t) for t in panel_data.current_bar_touches],
        current_price=panel_data.current_price,
        active_level_distance_pct=ref_layer.reference_config.active_level_distance_pct,
    )


@router.post("/api/reference/structure/clear")
async def clear_session_touches():
    """
    Clear the session level touch history.

    Call this when starting a new session or restarting playback.

    Returns:
        Success message.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer

    cache = get_replay_cache()

    if cache.get("reference_layer") is None:
        return {"success": True, "message": "No session touches to clear"}

    ref_layer = cache["reference_layer"]
    ref_layer.clear_session_touches()

    return {"success": True, "message": "Session touches cleared"}


@router.get("/api/reference/telemetry", response_model=TelemetryPanelResponse)
async def get_telemetry_panel(bar_index: Optional[int] = Query(None)):
    """
    Get Telemetry Panel data - reference stats, top references.

    Shows real-time reference state like DAG's market structure panel:
    - Reference counts by scale
    - Direction imbalance
    - Top references (biggest, most impulsive)

    Args:
        bar_index: Optional bar index for state. Uses current playback position if not provided.

    Returns:
        TelemetryPanelResponse with all telemetry data.
    """
    from ..api import get_state
    from ...swing_analysis.reference_layer import ReferenceLayer, ReferenceState

    cache = get_replay_cache()

    empty_response = TelemetryPanelResponse(
        counts_by_scale={'S': 0, 'M': 0, 'L': 0, 'XL': 0},
        total_count=0,
        bull_count=0,
        bear_count=0,
        direction_imbalance=None,
        imbalance_ratio=None,
        biggest_reference=None,
        most_impulsive=None,
    )

    try:
        state = get_state()
    except Exception:
        return empty_response

    if not is_initialized():
        return empty_response

    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    target_index = bar_index
    if target_index is None:
        target_index = cache.get("last_bar_index", 0)

    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return empty_response

    detector = cache["detector"]
    active_legs = detector.state.active_legs
    ref_layer = cache["reference_layer"]
    ref_state: ReferenceState = ref_layer.update(active_legs, bar)

    # Counts by scale
    counts_by_scale = {scale: len(refs) for scale, refs in ref_state.by_scale.items()}
    total_count = len(ref_state.references)

    # Direction counts
    bull_refs = ref_state.by_direction.get('bull', [])
    bear_refs = ref_state.by_direction.get('bear', [])
    bull_count = len(bull_refs)
    bear_count = len(bear_refs)

    # Imbalance ratio
    imbalance_ratio = None
    if ref_state.direction_imbalance == 'bull' and bear_count > 0:
        ratio = bull_count / bear_count
        imbalance_ratio = f"{ratio:.1f}:1"
    elif ref_state.direction_imbalance == 'bear' and bull_count > 0:
        ratio = bear_count / bull_count
        imbalance_ratio = f"{ratio:.1f}:1"

    # Biggest reference (by range)
    biggest_reference = None
    if ref_state.references:
        biggest = max(ref_state.references, key=lambda r: float(r.leg.range))
        biggest_reference = TopReferenceResponse(
            leg_id=biggest.leg.leg_id,
            scale=biggest.scale,
            direction=biggest.leg.direction,
            range_value=float(biggest.leg.range),
            impulsiveness=biggest.leg.impulsiveness,
            salience_score=biggest.salience_score,
        )

    # Most impulsive reference
    most_impulsive = None
    refs_with_impulse = [r for r in ref_state.references if r.leg.impulsiveness is not None]
    if refs_with_impulse:
        impulsive = max(refs_with_impulse, key=lambda r: r.leg.impulsiveness)
        most_impulsive = TopReferenceResponse(
            leg_id=impulsive.leg.leg_id,
            scale=impulsive.scale,
            direction=impulsive.leg.direction,
            range_value=float(impulsive.leg.range),
            impulsiveness=impulsive.leg.impulsiveness,
            salience_score=impulsive.salience_score,
        )

    return TelemetryPanelResponse(
        counts_by_scale=counts_by_scale,
        total_count=total_count,
        bull_count=bull_count,
        bear_count=bear_count,
        direction_imbalance=ref_state.direction_imbalance,
        imbalance_ratio=imbalance_ratio,
        biggest_reference=biggest_reference,
        most_impulsive=most_impulsive,
    )


# ============================================================================
# Reference Config Endpoints (Issue #423)
# ============================================================================


@router.get("/api/reference/config", response_model=ReferenceConfigResponse)
async def get_reference_config():
    """
    Get current reference layer configuration.

    Returns the current configuration values being used by the reference layer.
    If no reference layer is initialized, returns the default configuration.

    Returns:
        ReferenceConfigResponse with all current config values.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer
    from ...swing_analysis.reference_config import ReferenceConfig

    cache = get_replay_cache()

    # Get reference layer config or use defaults
    if cache.get("reference_layer") is not None:
        config = cache["reference_layer"].reference_config
    else:
        config = ReferenceConfig.default()

    return ReferenceConfigResponse(
        big_range_weight=config.big_range_weight,
        big_impulse_weight=config.big_impulse_weight,
        big_recency_weight=config.big_recency_weight,
        small_range_weight=config.small_range_weight,
        small_impulse_weight=config.small_impulse_weight,
        small_recency_weight=config.small_recency_weight,
        range_counter_weight=config.range_counter_weight,
        formation_fib_threshold=config.formation_fib_threshold,
    )


@router.post("/api/reference/config", response_model=ReferenceConfigResponse)
async def update_reference_config(request: ReferenceConfigUpdateRequest):
    """
    Update reference layer configuration.

    Accepts partial updates - only provided fields are modified.
    Returns the full updated configuration.

    This endpoint allows changing salience weights and formation threshold.
    The new config applies immediately to future reference calculations.

    Args:
        request: ReferenceConfigUpdateRequest with fields to update.

    Returns:
        ReferenceConfigResponse with all current config values after update.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer
    from ...swing_analysis.reference_config import ReferenceConfig

    cache = get_replay_cache()

    # Get or create reference layer
    if cache.get("reference_layer") is None:
        cache["reference_layer"] = ReferenceLayer()

    ref_layer = cache["reference_layer"]
    current_config = ref_layer.reference_config

    # Apply salience weight updates
    new_config = current_config.with_salience_weights(
        big_range_weight=request.big_range_weight,
        big_impulse_weight=request.big_impulse_weight,
        big_recency_weight=request.big_recency_weight,
        small_range_weight=request.small_range_weight,
        small_impulse_weight=request.small_impulse_weight,
        small_recency_weight=request.small_recency_weight,
        range_counter_weight=request.range_counter_weight,
    )

    # Apply formation threshold update
    if request.formation_fib_threshold is not None:
        new_config = new_config.with_formation_threshold(request.formation_fib_threshold)

    # Update reference layer config (preserves accumulated state)
    ref_layer.reference_config = new_config

    return ReferenceConfigResponse(
        big_range_weight=new_config.big_range_weight,
        big_impulse_weight=new_config.big_impulse_weight,
        big_recency_weight=new_config.big_recency_weight,
        small_range_weight=new_config.small_range_weight,
        small_impulse_weight=new_config.small_impulse_weight,
        small_recency_weight=new_config.small_recency_weight,
        range_counter_weight=new_config.range_counter_weight,
        formation_fib_threshold=new_config.formation_fib_threshold,
    )
