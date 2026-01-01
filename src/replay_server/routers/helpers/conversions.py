"""
Conversion helper functions for replay routers.

Provides functions to convert Leg objects to API response formats.
"""

from typing import Dict, List, Optional

from ....swing_analysis.dag.leg import Leg
from ....swing_analysis.events import (
    DetectionEvent,
    LegCreatedEvent,
    LegPrunedEvent,
    OriginBreachedEvent,
    PivotBreachedEvent,
)
from ...schemas import (
    LegResponse,
    ReplayEventResponse,
    LifecycleEvent,
)


def size_to_scale(size: float, scale_thresholds: Dict[str, float]) -> str:
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


def leg_to_response(
    leg: Leg,
    is_active: bool,
    rank: int = 1,
    scale_thresholds: Optional[Dict[str, float]] = None,
    include_fib_levels: bool = True,
) -> LegResponse:
    """
    Convert Leg to LegResponse (unified schema).

    Args:
        leg: Leg from LegDetector.
        is_active: Whether leg is currently active.
        rank: Leg rank by size.
        scale_thresholds: Optional thresholds for scale assignment.
        include_fib_levels: Whether to compute and include fib levels.

    Returns:
        LegResponse for API response.
    """
    origin_price = float(leg.origin_price)
    pivot_price = float(leg.pivot_price)
    range_size = abs(pivot_price - origin_price)

    # Determine scale - use size-based thresholds if available, otherwise None
    scale = None
    if scale_thresholds:
        scale = size_to_scale(range_size, scale_thresholds)

    # Calculate Fib levels if requested
    fib_levels = None
    if include_fib_levels and range_size > 0:
        if leg.direction == "bull":
            # Bull: origin=low, pivot=high
            fib_levels = {
                "0": origin_price,
                "0.382": origin_price + range_size * 0.382,
                "0.5": origin_price + range_size * 0.5,
                "0.618": origin_price + range_size * 0.618,
                "1": pivot_price,
                "1.382": origin_price + range_size * 1.382,
                "1.618": origin_price + range_size * 1.618,
                "2": origin_price + range_size * 2.0,
            }
        else:
            # Bear: origin=high, pivot=low
            fib_levels = {
                "0": origin_price,
                "0.382": origin_price - range_size * 0.382,
                "0.5": origin_price - range_size * 0.5,
                "0.618": origin_price - range_size * 0.618,
                "1": pivot_price,
                "1.382": origin_price - range_size * 1.382,
                "1.618": origin_price - range_size * 1.618,
                "2": origin_price - range_size * 2.0,
            }

    return LegResponse(
        leg_id=leg.leg_id,
        direction=leg.direction,
        origin_price=origin_price,
        origin_index=leg.origin_index,
        pivot_price=pivot_price,
        pivot_index=leg.pivot_index,
        range=range_size,
        rank=rank,
        is_active=is_active,
        depth=leg.depth,
        parent_leg_id=leg.parent_leg_id,
        fib_levels=fib_levels,
        scale=scale,
    )


def format_trigger_explanation(
    event: DetectionEvent,
    leg: Optional[Leg],
) -> str:
    """
    Generate human-readable explanation for an event.

    Args:
        event: The swing event.
        leg: Optional leg for context.

    Returns:
        Human-readable explanation string.
    """
    # Handle leg events first - they don't require leg context
    if isinstance(event, LegCreatedEvent):
        pivot_price = float(event.pivot_price)
        origin_price = float(event.origin_price)
        range_size = abs(origin_price - pivot_price)
        return (
            f"Leg created: {event.direction}\n"
            f"Pivot: {pivot_price:.2f}, Origin: {origin_price:.2f}, Range: {range_size:.2f}"
        )

    if isinstance(event, LegPrunedEvent):
        # Pass through reason and explanation from the event
        reason = event.reason.replace("_", " ").title()
        if event.explanation:
            return f"Pruned ({reason}): {event.explanation}"
        return f"Pruned: {reason}"

    if isinstance(event, OriginBreachedEvent):
        breach_price = float(event.breach_price)
        return f"Origin breached at {breach_price:.2f}"

    # Leg-based events require leg context
    if leg is None:
        return ""

    return ""


def event_to_response(
    event: DetectionEvent,
    leg: Optional[Leg] = None,
    scale_thresholds: Optional[Dict[str, float]] = None,
) -> ReplayEventResponse:
    """
    Convert DetectionEvent to ReplayEventResponse.

    Args:
        event: DetectionEvent from LegDetector.
        leg: Optional Leg for context.
        scale_thresholds: Optional thresholds for scale assignment.

    Returns:
        ReplayEventResponse for API response.
    """
    # Determine event type string
    if isinstance(event, LegCreatedEvent):
        event_type = "LEG_CREATED"
        direction = event.direction
    elif isinstance(event, LegPrunedEvent):
        event_type = "LEG_PRUNED"
        direction = leg.direction if leg else "bull"
    elif isinstance(event, OriginBreachedEvent):
        event_type = "ORIGIN_BREACHED"
        direction = leg.direction if leg else "bull"
    else:
        event_type = "UNKNOWN"
        direction = "bull"

    # Get hierarchy info from leg
    depth = leg.depth if leg else 0
    parent_leg_id = leg.parent_leg_id if leg else None

    # Determine scale from size or default to "M"
    if leg and scale_thresholds:
        size = float(leg.range)
        scale = size_to_scale(size, scale_thresholds)
    else:
        scale = "M"

    # Build swing response if we have leg data
    swing_response = None
    if leg:
        swing_response = leg_to_response(
            leg,
            is_active=leg.status == "active",
            scale_thresholds=scale_thresholds,
        )

    # Build trigger explanation
    trigger_explanation = format_trigger_explanation(event, leg)

    # Get leg_id from event
    leg_id = getattr(event, 'leg_id', None)
    if leg_id is None and leg:
        leg_id = leg.leg_id

    return ReplayEventResponse(
        type=event_type,
        bar_index=event.bar_index,
        scale=scale,
        direction=direction,
        leg_id=leg_id or "",
        swing=swing_response,
        trigger_explanation=trigger_explanation,
        depth=depth,
        parent_leg_id=parent_leg_id,
    )


def event_to_lifecycle_event(
    event: DetectionEvent,
    bar_index: int,
    csv_index: int,
    timestamp: str,
) -> Optional[LifecycleEvent]:
    """
    Convert a DetectionEvent to a LifecycleEvent for Follow Leg tracking.

    Only converts relevant leg lifecycle events. Returns None for events
    that aren't tracked.

    Args:
        event: The swing event.
        bar_index: The bar index where event occurred.
        csv_index: The CSV row index.
        timestamp: ISO format timestamp.

    Returns:
        LifecycleEvent or None if event type not tracked.
    """
    # Map leg events to lifecycle events
    if isinstance(event, LegCreatedEvent):
        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type="created",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Leg created: {event.direction}, "
                        f"origin {float(event.origin_price):.2f}, "
                        f"pivot {float(event.pivot_price):.2f}"
        )

    elif isinstance(event, OriginBreachedEvent):
        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type="origin_breached",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Origin breached at price {float(event.breach_price):.2f}"
        )

    elif isinstance(event, LegPrunedEvent):
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

    elif isinstance(event, PivotBreachedEvent):
        return LifecycleEvent(
            leg_id=event.leg_id,
            event_type="pivot_breached",
            bar_index=bar_index,
            csv_index=csv_index,
            timestamp=timestamp,
            explanation=f"Pivot breached at {float(event.breach_price):.2f} "
                        f"({float(event.breach_amount):.2f} past pivot)"
        )

    return None


def calculate_scale_thresholds(legs: List[Leg]) -> Dict[str, float]:
    """
    Calculate size thresholds for S/M/L/XL scale assignment.

    Uses percentile-based thresholds:
    - XL: Top 10% (90th percentile)
    - L: Top 25% (75th percentile)
    - M: Top 50% (50th percentile)
    - S: Everything else

    Args:
        legs: List of Leg objects.

    Returns:
        Dict mapping scale to minimum size threshold.
    """
    if not legs:
        return {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}

    sizes = sorted([float(leg.range) for leg in legs], reverse=True)
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


def group_legs_by_scale(
    legs: List[Leg],
    scale_thresholds: Dict[str, float],
    current_price: float,
) -> Dict[str, List[LegResponse]]:
    """
    Group legs by scale for API response.

    Args:
        legs: List of Leg objects.
        scale_thresholds: Size thresholds for scale assignment.
        current_price: Current price for activity check.

    Returns:
        Dict mapping scale to list of LegResponse.
    """
    result: Dict[str, List[LegResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
    }

    # Sort by size descending for ranking
    sorted_legs = sorted(
        legs,
        key=lambda leg: float(leg.range),
        reverse=True
    )

    for rank, leg in enumerate(sorted_legs, start=1):
        is_active = leg.status == "active"
        response = leg_to_response(
            leg,
            is_active=is_active,
            rank=rank,
            scale_thresholds=scale_thresholds,
        )
        if response.scale:
            result[response.scale].append(response)

    return result
