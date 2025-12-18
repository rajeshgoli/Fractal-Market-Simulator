"""
Discretization router for Ground Truth Annotator.

Provides endpoints for discretization event log generation:
- GET /api/discretization/state - Get current discretization state
- POST /api/discretization/run - Run discretization
- GET /api/discretization/swings - Get discretization swings
- GET /api/discretization/events - Get discretization events
- GET /api/discretization/levels - Get Fib levels for a swing
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ...discretization import (
    Discretizer,
    DiscretizerConfig,
    DiscretizationLog,
)
from ...swing_analysis.swing_detector import detect_swings, ReferenceSwing
from ..schemas import (
    DiscretizationStateResponse,
    DiscretizationRunResponse,
    DiscretizationSwingResponse,
    DiscretizationEventResponse,
)

if TYPE_CHECKING:
    from ..api import AppState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discretization", tags=["discretization"])


def _run_discretization(s: "AppState") -> DiscretizationLog:
    """Run discretization on current window with detected swings.

    Each swing is assigned to exactly one scale - the LARGEST scale it qualifies for
    based on size thresholds. This prevents the same swing from appearing at multiple scales.
    """
    # Convert source bars to DataFrame for discretizer
    bar_data = []
    for bar in s.source_bars:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Detect swings once (not per scale)
    result = detect_swings(df, lookback=5, filter_redundant=True)

    # Scale thresholds - swing assigned to LARGEST scale where size >= threshold
    # Note: Scales ordered from largest to smallest for assignment priority
    scale_thresholds = [
        ("XL", 100),
        ("L", 40),
        ("M", 15),
        ("S", 0),
    ]

    def assign_scale(size: float) -> str:
        """Assign swing to the largest scale it qualifies for."""
        for scale, threshold in scale_thresholds:
            if size >= threshold:
                return scale
        return "S"  # Default to smallest scale

    # Initialize swings_by_scale with empty lists
    swings_by_scale: Dict[str, List[ReferenceSwing]] = {
        "XL": [],
        "L": [],
        "M": [],
        "S": [],
    }

    # Process bull references - assign each to exactly one scale
    for ref in result.get('bull_references', []):
        swing = ReferenceSwing(
            high_price=ref['high_price'],
            high_bar_index=ref['high_bar_index'],
            low_price=ref['low_price'],
            low_bar_index=ref['low_bar_index'],
            size=ref['size'],
            direction='bull',
            structurally_separated=ref.get('structurally_separated', False),
            containing_swing_id=ref.get('containing_swing_id'),
            separation_is_anchor=ref.get('separation_is_anchor', False),
            separation_distance_fib=ref.get('separation_distance_fib'),
            separation_minimum_fib=ref.get('separation_minimum_fib'),
            separation_from_swing_id=ref.get('separation_from_swing_id'),
        )
        scale = assign_scale(ref['size'])
        swings_by_scale[scale].append(swing)

    # Process bear references - assign each to exactly one scale
    for ref in result.get('bear_references', []):
        swing = ReferenceSwing(
            high_price=ref['high_price'],
            high_bar_index=ref['high_bar_index'],
            low_price=ref['low_price'],
            low_bar_index=ref['low_bar_index'],
            size=ref['size'],
            direction='bear',
            structurally_separated=ref.get('structurally_separated', False),
            containing_swing_id=ref.get('containing_swing_id'),
            separation_is_anchor=ref.get('separation_is_anchor', False),
            separation_distance_fib=ref.get('separation_distance_fib'),
            separation_minimum_fib=ref.get('separation_minimum_fib'),
            separation_from_swing_id=ref.get('separation_from_swing_id'),
        )
        scale = assign_scale(ref['size'])
        swings_by_scale[scale].append(swing)

    # Remove empty scales from the dict
    swings_by_scale = {k: v for k, v in swings_by_scale.items() if v}

    # Run discretization
    config = DiscretizerConfig()
    discretizer = Discretizer(config)
    log = discretizer.discretize(
        ohlc=df,
        swings=swings_by_scale,
        instrument="unknown",
        source_resolution=f"{s.resolution_minutes}m",
    )

    return log


@router.get("/state", response_model=DiscretizationStateResponse)
async def get_discretization_state():
    """Get current discretization state."""
    from ..api import get_state

    s = get_state()

    if s.discretization_log is None:
        return DiscretizationStateResponse(
            has_log=False,
            event_count=0,
            swing_count=0,
            scales=[],
            config=None,
        )

    log = s.discretization_log
    scales = list(set(swing.scale for swing in log.swings))

    return DiscretizationStateResponse(
        has_log=True,
        event_count=len(log.events),
        swing_count=len(log.swings),
        scales=scales,
        config=log.meta.config.to_dict() if log.meta else None,
    )


@router.post("/run", response_model=DiscretizationRunResponse)
async def run_discretization():
    """
    Run discretization on current window.

    Detects swings on the source bars and runs the discretizer to produce
    an event log with level crossings, completions, invalidations, etc.
    """
    from ..api import get_state

    s = get_state()

    try:
        log = _run_discretization(s)
        s.discretization_log = log

        scales = list(set(swing.scale for swing in log.swings))

        return DiscretizationRunResponse(
            success=True,
            event_count=len(log.events),
            swing_count=len(log.swings),
            scales_processed=scales,
            message=f"Discretization complete: {len(log.events)} events, {len(log.swings)} swings",
        )
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        logger.error(f"Discretization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Discretization failed: {e}")


@router.get("/swings", response_model=List[DiscretizationSwingResponse])
async def get_discretization_swings(
    scale: Optional[str] = Query(None, description="Filter by scale (XL, L, M, S)"),
    status: Optional[str] = Query(None, description="Filter by status (active, completed, invalidated)"),
):
    """Get all swings from the discretization log."""
    from ..api import get_state

    s = get_state()

    if s.discretization_log is None:
        raise HTTPException(
            status_code=404,
            detail="No discretization log. Run POST /api/discretization/run first."
        )

    swings = s.discretization_log.swings

    # Apply filters
    if scale:
        swings = [sw for sw in swings if sw.scale == scale]
    if status:
        swings = [sw for sw in swings if sw.status == status]

    return [
        DiscretizationSwingResponse(
            swing_id=sw.swing_id,
            scale=sw.scale,
            direction=sw.direction,
            anchor0=sw.anchor0,
            anchor1=sw.anchor1,
            anchor0_bar=sw.anchor0_bar,
            anchor1_bar=sw.anchor1_bar,
            formed_at_bar=sw.formed_at_bar,
            status=sw.status,
            terminated_at_bar=sw.terminated_at_bar,
            termination_reason=sw.termination_reason,
        )
        for sw in swings
    ]


@router.get("/events", response_model=List[DiscretizationEventResponse])
async def get_discretization_events(
    scale: Optional[str] = Query(None, description="Filter by swing scale"),
    event_type: Optional[str] = Query(None, description="Filter by event type (LEVEL_CROSS, COMPLETION, etc.)"),
    shock_threshold: Optional[float] = Query(None, description="Minimum range_multiple for shock"),
    levels_jumped_min: Optional[int] = Query(None, description="Minimum levels_jumped"),
    is_gap: Optional[bool] = Query(None, description="Filter for gap events only"),
    bar_start: Optional[int] = Query(None, description="Filter events from bar index"),
    bar_end: Optional[int] = Query(None, description="Filter events up to bar index"),
):
    """
    Get discretization events with optional filters.

    Filters can be combined. Shock-related filters (shock_threshold, levels_jumped_min, is_gap)
    filter based on the shock annotation attached to events.
    """
    from ..api import get_state

    s = get_state()

    if s.discretization_log is None:
        raise HTTPException(
            status_code=404,
            detail="No discretization log. Run POST /api/discretization/run first."
        )

    log = s.discretization_log
    events = log.events

    # Build swing lookup for scale filtering
    swing_scales = {sw.swing_id: sw.scale for sw in log.swings}

    # Apply filters
    filtered = []
    for event in events:
        # Scale filter
        if scale:
            swing_scale = swing_scales.get(event.swing_id)
            if swing_scale != scale:
                continue

        # Event type filter
        if event_type:
            if event.event_type.value != event_type:
                continue

        # Bar range filter
        if bar_start is not None and event.bar < bar_start:
            continue
        if bar_end is not None and event.bar > bar_end:
            continue

        # Shock-based filters
        if shock_threshold is not None:
            if event.shock is None or event.shock.range_multiple < shock_threshold:
                continue

        if levels_jumped_min is not None:
            if event.shock is None or event.shock.levels_jumped < levels_jumped_min:
                continue

        if is_gap is not None:
            if event.shock is None or event.shock.is_gap != is_gap:
                continue

        filtered.append(event)

    return [
        DiscretizationEventResponse(
            bar=ev.bar,
            timestamp=ev.timestamp,
            swing_id=ev.swing_id,
            event_type=ev.event_type.value,
            data=ev.data,
            effort=ev.effort.to_dict() if ev.effort else None,
            shock=ev.shock.to_dict() if ev.shock else None,
            parent_context=ev.parent_context.to_dict() if ev.parent_context else None,
        )
        for ev in filtered
    ]


@router.get("/levels")
async def get_discretization_levels(swing_id: str = Query(..., description="Swing ID to get levels for")):
    """
    Get Fibonacci levels for a specific swing.

    Returns the price levels from the swing's reference frame for overlay display.
    """
    from ..api import get_state
    from ...swing_analysis.constants import DISCRETIZATION_LEVELS

    s = get_state()

    if s.discretization_log is None:
        raise HTTPException(
            status_code=404,
            detail="No discretization log. Run POST /api/discretization/run first."
        )

    # Find the swing
    swing = None
    for sw in s.discretization_log.swings:
        if sw.swing_id == swing_id:
            swing = sw
            break

    if swing is None:
        raise HTTPException(status_code=404, detail=f"Swing {swing_id} not found")

    # Calculate levels from anchor points
    anchor0 = swing.anchor0  # Defended pivot
    anchor1 = swing.anchor1  # Origin extremum
    swing_range = anchor1 - anchor0

    levels = []
    for ratio in DISCRETIZATION_LEVELS:
        price = anchor0 + swing_range * ratio
        levels.append({
            "ratio": ratio,
            "price": price,
            "label": str(ratio),
        })

    return {
        "swing_id": swing_id,
        "scale": swing.scale,
        "direction": swing.direction,
        "anchor0": anchor0,
        "anchor1": anchor1,
        "levels": levels,
    }
