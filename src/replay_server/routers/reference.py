"""
Reference Layer router for Replay View.

Provides endpoints for Reference Layer state, active levels, and level tracking.

Endpoints:
- GET /api/reference-state - Get reference layer state
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
)
from .cache import get_cache

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


@router.get("/api/reference-state", response_model=ReferenceStateApiResponse)
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

    cache = get_cache()

    try:
        state = get_state()
    except Exception:
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
        )

    if not cache.is_initialized():
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
        )

    # Get or create reference layer
    if cache.reference_layer is None:
        cache.reference_layer = ReferenceLayer()

    # Determine the target bar index
    target_index = bar_index
    if target_index is None:
        target_index = cache.last_bar_index

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
            filtered_legs=[],
            filter_stats=FilterStatsResponse(
                total_legs=0,
                valid_count=0,
                pass_rate=0.0,
                by_reason={'not_formed': 0, 'pivot_breached': 0, 'origin_breached': 0, 'completed': 0, 'cold_start': 0},
            ),
        )

    # Get active legs from detector
    active_legs = cache.detector.state.active_legs

    # Update reference layer and get state
    ref_state: ReferenceState = cache.reference_layer.update(active_legs, bar)

    # Get all legs with filter status for observation mode
    all_statuses = cache.reference_layer.get_all_with_status(active_legs, bar)

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
        tracked_leg_ids=list(cache.reference_layer.get_tracked_leg_ids()),
        filtered_legs=filtered_legs,
        filter_stats=filter_stats,
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

    cache = get_cache()

    try:
        state = get_state()
    except Exception:
        return ActiveLevelsResponse(levels_by_ratio={})

    if not cache.is_initialized():
        return ActiveLevelsResponse(levels_by_ratio={})

    if cache.reference_layer is None:
        cache.reference_layer = ReferenceLayer()

    target_index = bar_index
    if target_index is None:
        target_index = cache.last_bar_index

    if target_index >= 0 and target_index < len(state.source_bars):
        bar = state.source_bars[target_index]
    elif len(state.source_bars) > 0:
        bar = state.source_bars[-1]
    else:
        return ActiveLevelsResponse(levels_by_ratio={})

    active_legs = cache.detector.state.active_legs
    ref_state: ReferenceState = cache.reference_layer.update(active_legs, bar)

    # Get active levels
    levels_dict = cache.reference_layer.get_active_levels(ref_state)

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
    on the chart even when the mouse moves away.

    Args:
        leg_id: The leg_id to start tracking.

    Returns:
        Success message with current tracked leg count.
    """
    from ...swing_analysis.reference_layer import ReferenceLayer

    cache = get_cache()

    if cache.reference_layer is None:
        cache.reference_layer = ReferenceLayer()

    cache.reference_layer.add_crossing_tracking(leg_id)

    return {
        "success": True,
        "leg_id": leg_id,
        "tracked_count": len(cache.reference_layer.get_tracked_leg_ids()),
    }


@router.delete("/api/reference/track/{leg_id}")
async def untrack_leg_for_crossing(leg_id: str):
    """
    Remove a leg from level crossing tracking.

    The leg's fib levels will no longer be sticky and will only appear on hover.

    Args:
        leg_id: The leg_id to stop tracking.

    Returns:
        Success message with current tracked leg count.
    """
    cache = get_cache()

    if cache.reference_layer is None:
        return {
            "success": True,
            "leg_id": leg_id,
            "tracked_count": 0,
        }

    cache.reference_layer.remove_crossing_tracking(leg_id)

    return {
        "success": True,
        "leg_id": leg_id,
        "tracked_count": len(cache.reference_layer.get_tracked_leg_ids()),
    }
