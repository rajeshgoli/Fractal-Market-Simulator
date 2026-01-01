"""
DAG state router for Replay View.

Provides endpoints for DAG state inspection, hierarchy exploration,
and leg lifecycle event tracking.

Endpoints:
- GET /api/dag/state - Get current DAG internal state
- GET /api/dag/lineage/{leg_id} - Get leg lineage (ancestors/descendants)
- GET /api/dag/events - Get all lifecycle events (for view switch restoration)
- GET /api/followed-legs/events - Get lifecycle events for followed legs
"""

from typing import List

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    DagLegResponse,
    DagPendingOrigin,
    DagLegCounts,
    DagStateResponse,
    LegLineageResponse,
    FollowedLegsEventsResponse,
)
from .cache import get_cache

router = APIRouter(tags=["dag"])


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

    cache = get_cache()

    if not cache.is_initialized():
        raise HTTPException(
            status_code=400,
            detail="Must calibrate first. Call /api/replay/calibrate."
        )

    s = get_state()
    window_offset = s.window_offset
    state = cache.detector.state

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
    cache = get_cache()

    if not cache.is_initialized():
        raise HTTPException(
            status_code=400,
            detail="Must calibrate first. Call /api/replay/calibrate."
        )

    state = cache.detector.state

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


@router.get("/api/dag/events", response_model=FollowedLegsEventsResponse)
async def get_all_lifecycle_events():
    """
    Get all lifecycle events from the current session.

    Returns all cached lifecycle events. Used to restore frontend state
    when switching views (DAG View -> Reference View -> DAG View).

    The backend is authoritative for lifecycle events; this endpoint allows
    the frontend to resync after remounting without losing event history.

    Returns:
        FollowedLegsEventsResponse with all lifecycle events.
    """
    cache = get_cache()

    if not cache.is_initialized():
        return FollowedLegsEventsResponse(events=[])

    # Return all lifecycle events (already in LifecycleEvent format)
    return FollowedLegsEventsResponse(events=cache.lifecycle_events)


@router.get("/api/followed-legs/events", response_model=FollowedLegsEventsResponse)
async def get_followed_legs_events(
    leg_ids: str = Query(..., description="Comma-separated list of leg IDs to track"),
    since_bar: int = Query(..., description="Only return events from this bar index onwards"),
):
    """
    Get lifecycle events for followed legs.

    Returns events for the specified leg IDs that occurred at or after the
    since_bar index. Used by the Follow Leg feature to show event markers.

    Events tracked:
    - created: New leg created
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
    cache = get_cache()

    # Parse leg IDs
    leg_id_set = set(lid.strip() for lid in leg_ids.split(",") if lid.strip())

    if not leg_id_set:
        return FollowedLegsEventsResponse(events=[])

    # Filter lifecycle events
    filtered_events = [
        event for event in cache.lifecycle_events
        if event.leg_id in leg_id_set and event.bar_index >= since_bar
    ]

    return FollowedLegsEventsResponse(events=filtered_events)
