"""
Replay router for Ground Truth Annotator.

Provides endpoints for Replay View functionality:
- GET /api/swings/windowed - Get windowed swing detection
- GET /api/replay/calibrate - Run calibration for Replay View
- POST /api/replay/advance - Advance playback
- POST /api/playback/feedback - Submit playback feedback

Also includes helper functions for swing detection and Fib level calculations.
"""

import logging
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ...swing_analysis.swing_detector import detect_swings
from ...swing_analysis.incremental_detector import (
    IncrementalSwingState,
    ActiveSwing,
    IncrementalEvent,
    advance_bar_incremental,
    initialize_from_calibration,
)
from ...swing_analysis.types import Bar
from ..storage import PlaybackFeedbackStorage
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


# Global cache for replay state (avoids recomputing swings every advance)
_replay_cache: Dict[str, Any] = {
    "last_bar_index": -1,
    "swing_state": {},  # swing_id -> swing dict with current status
    "fib_levels": {},  # swing_id -> last crossed fib level
    "incremental_state": None,  # IncrementalSwingState for O(active) detection
    "calibration_bar_count": 0,  # Calibration window size
    "scale_thresholds": {},  # Scale -> size thresholds
    "calibration_swing_ids": set(),  # Structural IDs from calibration
}


# ============================================================================
# Helper Functions
# ============================================================================


def _is_swing_active(
    swing: dict,
    current_price: float,
    direction: str
) -> bool:
    """
    Determine if a swing is "active" at the current price.

    A swing is active if:
    1. Not yet invalidated (price hasn't violated the defended pivot)
    2. Not yet completed (price hasn't reached 2.0 extension)
    3. Current price is within the 0.382-2.0 zone

    Args:
        swing: Swing dict with high_price, low_price, size, fib levels
        current_price: Current market price
        direction: "bull" or "bear"

    Returns:
        True if the swing is active
    """
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    if direction == 'bull':
        # Bull swing: defended pivot is low, origin is high
        # Price moving up from low
        fib_0 = low  # Defended pivot
        fib_0382 = low + swing_range * 0.382
        fib_2 = low + swing_range * 2.0

        # Invalidated if price below defended pivot (with tolerance)
        if current_price < fib_0 * 0.999:
            return False

        # Completed if price reached 2.0 extension
        if current_price > fib_2:
            return False

        # Active if in 0.382-2.0 zone
        return fib_0382 <= current_price <= fib_2
    else:
        # Bear swing: defended pivot is high, origin is low
        # Price moving down from high
        fib_0 = high  # Defended pivot
        fib_0382 = high - swing_range * 0.382
        fib_2 = high - swing_range * 2.0

        # Invalidated if price above defended pivot (with tolerance)
        if current_price > fib_0 * 1.001:
            return False

        # Completed if price reached 2.0 extension
        if current_price < fib_2:
            return False

        # Active if in 0.382-2.0 zone
        return fib_2 <= current_price <= fib_0382


def _swing_to_calibration_response(
    swing: dict,
    swing_id: str,
    scale: str,
    rank: int,
    is_active: bool
) -> CalibrationSwingResponse:
    """Convert a swing dict to CalibrationSwingResponse."""
    direction = swing['direction']
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    # Calculate Fib levels based on direction
    if direction == 'bull':
        fib_0 = low
        fib_0382 = low + swing_range * 0.382
        fib_1 = high
        fib_2 = low + swing_range * 2.0
    else:
        fib_0 = high
        fib_0382 = high - swing_range * 0.382
        fib_1 = low
        fib_2 = high - swing_range * 2.0

    return CalibrationSwingResponse(
        id=swing_id,
        scale=scale,
        direction=direction,
        high_price=high,
        high_bar_index=swing['high_bar_index'],
        low_price=low,
        low_bar_index=swing['low_bar_index'],
        size=swing['size'],
        rank=rank,
        is_active=is_active,
        fib_0=fib_0,
        fib_0382=fib_0382,
        fib_1=fib_1,
        fib_2=fib_2,
    )


def _detect_swings_at_bar(
    source_bars: List[Bar],
    bar_index: int,
    scale_thresholds: Dict[str, float]
) -> Dict[str, List[dict]]:
    """
    Detect swings using data up to bar_index (inclusive).

    Returns swings organized by scale.
    """
    if bar_index < 10:
        return {"XL": [], "L": [], "M": [], "S": []}

    # Convert to DataFrame
    bar_data = []
    for bar in source_bars[:bar_index + 1]:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Run swing detection
    result = detect_swings(
        df,
        lookback=5,
        filter_redundant=True,
        current_bar_index=bar_index,
    )

    def assign_scale(size: float) -> str:
        """Assign swing to the largest scale it qualifies for."""
        if size >= scale_thresholds["XL"]:
            return "XL"
        elif size >= scale_thresholds["L"]:
            return "L"
        elif size >= scale_thresholds["M"]:
            return "M"
        return "S"

    swings_by_scale: Dict[str, List[dict]] = {
        "XL": [], "L": [], "M": [], "S": []
    }

    # Process bull references
    for i, ref in enumerate(result.get('bull_references', [])):
        scale = assign_scale(ref['size'])
        swing = {
            'id': f"swing-bull-{ref['high_bar_index']}-{ref['low_bar_index']}",
            'direction': 'bull',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': len(swings_by_scale[scale]) + 1,
            'scale': scale,
        }
        swings_by_scale[scale].append(swing)

    # Process bear references
    for i, ref in enumerate(result.get('bear_references', [])):
        scale = assign_scale(ref['size'])
        swing = {
            'id': f"swing-bear-{ref['low_bar_index']}-{ref['high_bar_index']}",
            'direction': 'bear',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': len(swings_by_scale[scale]) + 1,
            'scale': scale,
        }
        swings_by_scale[scale].append(swing)

    return swings_by_scale


def _compute_fib_levels(swing: dict) -> Dict[float, float]:
    """Compute all standard Fib levels for a swing."""
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    if swing['direction'] == 'bull':
        # Bull: defended pivot is low, origin is high
        return {
            0.0: low,
            0.236: low + swing_range * 0.236,
            0.382: low + swing_range * 0.382,
            0.5: low + swing_range * 0.5,
            0.618: low + swing_range * 0.618,
            0.786: low + swing_range * 0.786,
            1.0: high,
            1.236: low + swing_range * 1.236,
            1.382: low + swing_range * 1.382,
            1.5: low + swing_range * 1.5,
            1.618: low + swing_range * 1.618,
            2.0: low + swing_range * 2.0,
        }
    else:
        # Bear: defended pivot is high, origin is low
        return {
            0.0: high,
            0.236: high - swing_range * 0.236,
            0.382: high - swing_range * 0.382,
            0.5: high - swing_range * 0.5,
            0.618: high - swing_range * 0.618,
            0.786: high - swing_range * 0.786,
            1.0: low,
            1.236: high - swing_range * 1.236,
            1.382: high - swing_range * 1.382,
            1.5: high - swing_range * 1.5,
            1.618: high - swing_range * 1.618,
            2.0: high - swing_range * 2.0,
        }


def _get_current_fib_level(swing: dict, current_price: float) -> float:
    """Get the current Fib level that price is at."""
    fib_levels = _compute_fib_levels(swing)
    sorted_levels = sorted(fib_levels.keys())

    if swing['direction'] == 'bull':
        # Price moving up: find highest level below current price
        current_level = 0.0
        for level in sorted_levels:
            if current_price >= fib_levels[level]:
                current_level = level
            else:
                break
    else:
        # Price moving down: find highest level above current price
        current_level = 0.0
        for level in sorted_levels:
            if current_price <= fib_levels[level]:
                current_level = level
            else:
                break

    return current_level


def _swing_to_response(swing: dict, is_active: bool) -> CalibrationSwingResponse:
    """Convert swing dict to CalibrationSwingResponse."""
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    if swing['direction'] == 'bull':
        fib_0 = low
        fib_0382 = low + swing_range * 0.382
        fib_1 = high
        fib_2 = low + swing_range * 2.0
    else:
        fib_0 = high
        fib_0382 = high - swing_range * 0.382
        fib_1 = low
        fib_2 = high - swing_range * 2.0

    return CalibrationSwingResponse(
        id=swing['id'],
        scale=swing['scale'],
        direction=swing['direction'],
        high_price=high,
        high_bar_index=swing['high_bar_index'],
        low_price=low,
        low_bar_index=swing['low_bar_index'],
        size=swing['size'],
        rank=swing.get('rank', 1),
        is_active=is_active,
        fib_0=fib_0,
        fib_0382=fib_0382,
        fib_1=fib_1,
        fib_2=fib_2,
    )


def _format_trigger_explanation_dict(
    event_type: str,
    swing: dict,
    current_price: float,
    level: Optional[float] = None,
    previous_level: Optional[float] = None,
) -> str:
    """
    Generate a human-readable explanation for legacy dict-based swings.

    Args:
        event_type: SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED, LEVEL_CROSS
        swing: Dictionary with swing data (high_price, low_price, direction)
        current_price: Price at the time of the event
        level: For LEVEL_CROSS/SWING_COMPLETED, the level crossed
        previous_level: For LEVEL_CROSS, the previous level

    Returns:
        Human-readable explanation string
    """
    high_price = swing.get('high_price', 0)
    low_price = swing.get('low_price', 0)
    direction = swing.get('direction', 'bull')
    swing_range = high_price - low_price

    if swing_range <= 0:
        return ""

    if event_type == "SWING_FORMED":
        if direction == 'bull':
            fib_0382 = low_price + swing_range * 0.382
            fib_2 = low_price + swing_range * 2.0
            return (
                f"Price ({current_price:.2f}) entered zone above 0.382 ({fib_0382:.2f})\n"
                f"Active range: {fib_0382:.2f} -> {fib_2:.2f}"
            )
        else:
            fib_0382 = high_price - swing_range * 0.382
            fib_2 = high_price - swing_range * 2.0
            return (
                f"Price ({current_price:.2f}) entered zone below 0.382 ({fib_0382:.2f})\n"
                f"Active range: {fib_0382:.2f} -> {fib_2:.2f}"
            )

    elif event_type == "SWING_INVALIDATED":
        if direction == 'bull':
            pivot_type = "low"
            pivot_price = low_price
        else:
            pivot_type = "high"
            pivot_price = high_price
        return (
            f"Price ({current_price:.2f}) broke {pivot_type} ({pivot_price:.2f})\n"
            f"Pivot exceeded - swing invalidated"
        )

    elif event_type == "SWING_COMPLETED":
        if direction == 'bull':
            fib_2 = low_price + swing_range * 2.0
        else:
            fib_2 = high_price - swing_range * 2.0
        return (
            f"Price ({current_price:.2f}) reached 2x target ({fib_2:.2f})\n"
            f"Full extension achieved"
        )

    elif event_type == "LEVEL_CROSS":
        level_val = level or 0
        prev_val = previous_level or 0

        if direction == 'bull':
            level_price = low_price + swing_range * level_val
            prev_side = "below" if prev_val < level_val else "above"
            curr_side = "above" if prev_val < level_val else "below"
        else:
            level_price = high_price - swing_range * level_val
            prev_side = "above" if prev_val < level_val else "below"
            curr_side = "below" if prev_val < level_val else "above"

        return f"Crossed {level_val} ({level_price:.2f}): {prev_side} -> {curr_side}"

    return ""


def _diff_swing_states(
    prev_swings: Dict[str, dict],
    new_swings: Dict[str, dict],
    prev_fib_levels: Dict[str, float],
    current_price: float,
    bar_index: int,
    calibration_swing_ids: Optional[Set[str]] = None
) -> tuple[List[ReplayEventResponse], Dict[str, float]]:
    """
    Diff swing states and generate events.

    Args:
        prev_swings: Previous swing state by ID
        new_swings: New swing state by ID
        prev_fib_levels: Previous fib levels by swing ID
        current_price: Current price for fib calculations
        bar_index: Current bar index for event attribution
        calibration_swing_ids: Set of structural IDs from calibration to filter stale events

    Returns (events, new_fib_levels).
    """
    events = []
    new_fib_levels = {}

    prev_ids = set(prev_swings.keys())
    new_ids = set(new_swings.keys())

    # SWING_FORMED: New swings that weren't in previous state
    for swing_id in new_ids - prev_ids:
        swing = new_swings[swing_id]
        # Initialize fib level tracking regardless of event emission
        new_fib_levels[swing_id] = _get_current_fib_level(swing, current_price)

        # Skip SWING_FORMED if this swing was already valid during calibration
        # The swing_id from _detect_swings_at_bar matches the structural ID format
        if calibration_swing_ids and swing_id in calibration_swing_ids:
            continue

        events.append(ReplayEventResponse(
            type="SWING_FORMED",
            bar_index=bar_index,
            scale=swing['scale'],
            direction=swing['direction'],
            swing_id=swing_id,
            swing=_swing_to_response(swing, True),
            trigger_explanation=_format_trigger_explanation_dict(
                "SWING_FORMED", swing, current_price
            ),
        ))

    # SWING_INVALIDATED: Swings that disappeared
    # Include swing data so UI can show what was invalidated
    for swing_id in prev_ids - new_ids:
        swing = prev_swings[swing_id]
        events.append(ReplayEventResponse(
            type="SWING_INVALIDATED",
            bar_index=bar_index,
            scale=swing['scale'],
            direction=swing['direction'],
            swing_id=swing_id,
            swing=_swing_to_response(swing, False),  # is_active=False since invalidated
            trigger_explanation=_format_trigger_explanation_dict(
                "SWING_INVALIDATED", swing, current_price
            ),
        ))

    # Check continuing swings for LEVEL_CROSS and COMPLETION
    for swing_id in prev_ids & new_ids:
        swing = new_swings[swing_id]
        prev_level = prev_fib_levels.get(swing_id, 0.0)
        new_level = _get_current_fib_level(swing, current_price)
        new_fib_levels[swing_id] = new_level

        # SWING_COMPLETED: crossed 2.0 level
        if prev_level < 2.0 and new_level >= 2.0:
            events.append(ReplayEventResponse(
                type="SWING_COMPLETED",
                bar_index=bar_index,
                scale=swing['scale'],
                direction=swing['direction'],
                swing_id=swing_id,
                level=2.0,
                previous_level=prev_level,
                swing=_swing_to_response(swing, True),  # Include swing data for explanation
                trigger_explanation=_format_trigger_explanation_dict(
                    "SWING_COMPLETED", swing, current_price, level=2.0, previous_level=prev_level
                ),
            ))
        # LEVEL_CROSS: crossed a significant fib level
        elif new_level != prev_level and new_level > prev_level:
            # Only emit for significant levels
            significant_levels = [0.382, 0.5, 0.618, 1.0, 1.382, 1.618]
            for lvl in significant_levels:
                if prev_level < lvl <= new_level:
                    events.append(ReplayEventResponse(
                        type="LEVEL_CROSS",
                        bar_index=bar_index,
                        scale=swing['scale'],
                        direction=swing['direction'],
                        swing_id=swing_id,
                        level=lvl,
                        previous_level=prev_level,
                        swing=_swing_to_response(swing, True),  # Include swing data for explanation
                        trigger_explanation=_format_trigger_explanation_dict(
                            "LEVEL_CROSS", swing, current_price, level=lvl, previous_level=prev_level
                        ),
                    ))
                    break  # Only emit one level cross per bar

    return events, new_fib_levels


def _incremental_event_to_response(
    event: IncrementalEvent,
    is_active: bool = True
) -> ReplayEventResponse:
    """Convert IncrementalEvent to ReplayEventResponse."""
    swing_response = None
    if event.swing:
        swing = event.swing
        high = swing.high_price
        low = swing.low_price
        swing_range = high - low

        if swing.direction == 'bull':
            fib_0 = low
            fib_0382 = low + swing_range * 0.382
            fib_1 = high
            fib_2 = low + swing_range * 2.0
        else:
            fib_0 = high
            fib_0382 = high - swing_range * 0.382
            fib_1 = low
            fib_2 = high - swing_range * 2.0

        swing_response = CalibrationSwingResponse(
            id=swing.swing_id,
            scale=swing.scale,
            direction=swing.direction,
            high_price=high,
            high_bar_index=swing.high_bar_index,
            low_price=low,
            low_bar_index=swing.low_bar_index,
            size=swing.size,
            rank=swing.rank,
            is_active=is_active,
            fib_0=fib_0,
            fib_0382=fib_0382,
            fib_1=fib_1,
            fib_2=fib_2,
        )

    return ReplayEventResponse(
        type=event.event_type,
        bar_index=event.bar_index,
        scale=event.scale,
        direction=event.direction,
        swing_id=event.swing_id,
        swing=swing_response,
        level=event.level,
        previous_level=event.previous_level,
        trigger_explanation=event.trigger_explanation,
    )


def _active_swing_to_response(swing: ActiveSwing, is_active: bool) -> CalibrationSwingResponse:
    """Convert ActiveSwing to CalibrationSwingResponse."""
    high = swing.high_price
    low = swing.low_price
    swing_range = high - low

    if swing.direction == 'bull':
        fib_0 = low
        fib_0382 = low + swing_range * 0.382
        fib_1 = high
        fib_2 = low + swing_range * 2.0
    else:
        fib_0 = high
        fib_0382 = high - swing_range * 0.382
        fib_1 = low
        fib_2 = high - swing_range * 2.0

    return CalibrationSwingResponse(
        id=swing.swing_id,
        scale=swing.scale,
        direction=swing.direction,
        high_price=high,
        high_bar_index=swing.high_bar_index,
        low_price=low,
        low_bar_index=swing.low_bar_index,
        size=swing.size,
        rank=swing.rank,
        is_active=is_active,
        fib_0=fib_0,
        fib_0382=fib_0382,
        fib_1=fib_1,
        fib_2=fib_2,
    )


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

    Used by Replay View to show detected swings as playback progresses.
    Returns swings with Fib levels for chart overlay.
    """
    from ..api import get_state

    s = get_state()

    # Validate bar_end
    if bar_end < 10:
        # Need minimum bars for detection
        return SwingsWindowedResponse(bar_end=bar_end, swing_count=0, swings=[])
    if bar_end > len(s.source_bars):
        bar_end = len(s.source_bars)

    # Slice source bars to current position
    bars_subset = s.source_bars[:bar_end]

    # Convert to DataFrame for detect_swings
    bar_data = []
    for bar in bars_subset:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Run swing detection
    result = detect_swings(
        df,
        lookback=5,
        filter_redundant=True,
        current_bar_index=bar_end - 1,  # Pass current bar for proper detection
    )

    # Combine bull and bear references, sort by size, take top N
    all_swings = []

    for ref in result.get('bull_references', []):
        # Calculate Fib levels for bull (low is pivot, high is origin)
        swing_range = ref['high_price'] - ref['low_price']
        fib_0 = ref['low_price']  # Defended pivot
        fib_0382 = ref['low_price'] + swing_range * 0.382
        fib_1 = ref['high_price']  # Origin
        fib_2 = ref['low_price'] + swing_range * 2.0  # Completion target

        all_swings.append({
            'direction': 'bull',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': ref.get('rank', 0),
            'fib_0': fib_0,
            'fib_0382': fib_0382,
            'fib_1': fib_1,
            'fib_2': fib_2,
        })

    for ref in result.get('bear_references', []):
        # Calculate Fib levels for bear (high is pivot, low is origin)
        swing_range = ref['high_price'] - ref['low_price']
        fib_0 = ref['high_price']  # Defended pivot
        fib_0382 = ref['high_price'] - swing_range * 0.382
        fib_1 = ref['low_price']  # Origin
        fib_2 = ref['high_price'] - swing_range * 2.0  # Completion target

        all_swings.append({
            'direction': 'bear',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': ref.get('rank', 0),
            'fib_0': fib_0,
            'fib_0382': fib_0382,
            'fib_1': fib_1,
            'fib_2': fib_2,
        })

    # Sort by size descending, take top N
    all_swings.sort(key=lambda x: x['size'], reverse=True)
    top_swings = all_swings[:top_n]

    # Convert to response models with IDs
    swing_responses = []
    for i, swing in enumerate(top_swings):
        swing_responses.append(DetectedSwingResponse(
            id=f"swing-{bar_end}-{i}",
            direction=swing['direction'],
            high_price=swing['high_price'],
            high_bar_index=swing['high_bar_index'],
            low_price=swing['low_price'],
            low_bar_index=swing['low_bar_index'],
            size=swing['size'],
            rank=i + 1,
            fib_0=swing['fib_0'],
            fib_0382=swing['fib_0382'],
            fib_1=swing['fib_1'],
            fib_2=swing['fib_2'],
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
    Run calibration for Replay View.

    Loads the first N bars as the calibration window, detects swings at all
    scales, and identifies which swings are "active" at the end of the window.

    A swing is "active" if:
    - Not yet invalidated (swing point not violated)
    - Not yet completed (price hasn't reached 2.0 extension)
    - Current price is within 0.382-2.0 zone

    Args:
        bar_count: Number of bars for calibration window (default: 10000)

    Returns:
        CalibrationResponse with swings by scale and active swing lists
    """
    global _replay_cache
    from ..api import get_state

    s = get_state()

    # Determine actual calibration window size
    actual_bar_count = min(bar_count, len(s.source_bars))
    if actual_bar_count < 10:
        raise HTTPException(
            status_code=400,
            detail="Need at least 10 bars for calibration"
        )

    # Get calibration window bars
    calibration_bars = s.source_bars[:actual_bar_count]
    current_price = calibration_bars[-1].close

    # Convert to DataFrame for detect_swings
    bar_data = []
    for bar in calibration_bars:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Scale thresholds for assignment (swing goes to largest scale it qualifies for)
    scale_thresholds = {
        "XL": 100.0,
        "L": 40.0,
        "M": 15.0,
        "S": 0.0,
    }

    def assign_scale(size: float) -> str:
        """Assign swing to the largest scale it qualifies for."""
        if size >= scale_thresholds["XL"]:
            return "XL"
        elif size >= scale_thresholds["L"]:
            return "L"
        elif size >= scale_thresholds["M"]:
            return "M"
        return "S"

    # Run swing detection with current_bar_index at end of calibration window
    result = detect_swings(
        df,
        lookback=5,
        filter_redundant=True,
        current_bar_index=actual_bar_count - 1,
    )

    # Process all swings and assign to scales
    swings_by_scale: Dict[str, List[CalibrationSwingResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
    }
    active_swings_by_scale: Dict[str, List[CalibrationSwingResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
    }

    # Process bull references
    for i, ref in enumerate(result.get('bull_references', [])):
        scale = assign_scale(ref['size'])
        swing_id = f"cal-bull-{i}"
        ref['direction'] = 'bull'
        is_active = _is_swing_active(ref, current_price, 'bull')
        rank = len(swings_by_scale[scale]) + 1

        swing_response = _swing_to_calibration_response(
            ref, swing_id, scale, rank, is_active
        )
        swings_by_scale[scale].append(swing_response)

        if is_active:
            active_swings_by_scale[scale].append(swing_response)

    # Process bear references
    for i, ref in enumerate(result.get('bear_references', [])):
        scale = assign_scale(ref['size'])
        swing_id = f"cal-bear-{i}"
        ref['direction'] = 'bear'
        is_active = _is_swing_active(ref, current_price, 'bear')
        rank = len(swings_by_scale[scale]) + 1

        swing_response = _swing_to_calibration_response(
            ref, swing_id, scale, rank, is_active
        )
        swings_by_scale[scale].append(swing_response)

        if is_active:
            active_swings_by_scale[scale].append(swing_response)

    # Compute stats by scale
    stats_by_scale = {
        scale: CalibrationScaleStats(
            total_swings=len(swings_by_scale[scale]),
            active_swings=len(active_swings_by_scale[scale])
        )
        for scale in ["XL", "L", "M", "S"]
    }

    # Set playback state for backend-controlled data boundary
    s.calibration_bar_count = actual_bar_count
    s.playback_index = actual_bar_count - 1  # Last visible bar index

    # Build calibration swings dict for incremental state initialization
    # Include all swings (active check happens inside initialize_from_calibration)
    cal_swings_for_init: Dict[str, List[Dict]] = {"XL": [], "L": [], "M": [], "S": []}
    for scale in ["XL", "L", "M", "S"]:
        for swing_resp in active_swings_by_scale[scale]:
            cal_swings_for_init[scale].append({
                'id': swing_resp.id,
                'direction': swing_resp.direction,
                'high_price': swing_resp.high_price,
                'high_bar_index': swing_resp.high_bar_index,
                'low_price': swing_resp.low_price,
                'low_bar_index': swing_resp.low_bar_index,
                'size': swing_resp.size,
                'rank': swing_resp.rank,
                'is_active': True,
            })

    incremental_state = initialize_from_calibration(
        calibration_swings=cal_swings_for_init,
        source_bars=s.source_bars,
        calibration_bar_count=actual_bar_count,
        scale_thresholds=scale_thresholds,
        current_price=current_price,
        lookback=5,
        protection_tolerance=0.1,
    )

    # Store in cache
    _replay_cache["incremental_state"] = incremental_state
    _replay_cache["calibration_bar_count"] = actual_bar_count
    _replay_cache["scale_thresholds"] = scale_thresholds
    _replay_cache["last_bar_index"] = actual_bar_count - 1

    # Store structural IDs of all active calibration swings for stale event filtering
    # During playback, SWING_FORMED should not fire for swings already valid at calibration end
    calibration_swing_ids = set()
    for scale in ["XL", "L", "M", "S"]:
        for swing_resp in active_swings_by_scale[scale]:
            # Use structural ID format matching _detect_swings_at_bar
            if swing_resp.direction == 'bull':
                structural_id = f"swing-bull-{swing_resp.high_bar_index}-{swing_resp.low_bar_index}"
            else:
                structural_id = f"swing-bear-{swing_resp.low_bar_index}-{swing_resp.high_bar_index}"
            calibration_swing_ids.add(structural_id)
    _replay_cache["calibration_swing_ids"] = calibration_swing_ids

    # Also build swing_state and fib_levels for compatibility
    swing_state_dict = {}
    fib_levels_dict = {}
    for swing_id, swing in incremental_state.active_swings.items():
        swing_state_dict[swing_id] = swing.to_dict()
        fib_levels_dict[swing_id] = incremental_state.fib_levels.get(swing_id, 0.0)
    _replay_cache["swing_state"] = swing_state_dict
    _replay_cache["fib_levels"] = fib_levels_dict

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
    Advance playback beyond calibration window using O(active_swings) incremental detection.

    For each new bar, performs incremental operations:
    1. Check for new swing point confirmation at trailing edge (N - lookback)
    2. Pair new swing points with existing opposite points
    3. Check active swings for invalidation (pivot violation)
    4. Check active swings for fib level crosses

    This replaces the O(N log N) full detection per bar with O(active) operations,
    enabling smooth 10x playback at any aggregation level.

    Args:
        calibration_bar_count: Number of bars in calibration window
        current_bar_index: Current playback position (last visible bar)
        advance_by: Number of bars to advance (default: 1)

    Returns:
        new_bars: New bars to append to chart
        events: Events that occurred during advance
        swing_state: Current swing state at new position
        end_of_data: Whether we've reached the end of data
    """
    global _replay_cache
    from ..api import get_state

    s = get_state()

    # Validate inputs
    if request.calibration_bar_count < 10:
        raise HTTPException(status_code=400, detail="calibration_bar_count must be >= 10")
    if request.current_bar_index < request.calibration_bar_count - 1:
        raise HTTPException(
            status_code=400,
            detail="current_bar_index must be >= calibration_bar_count - 1"
        )

    # Calculate new bar range
    start_index = request.current_bar_index + 1
    end_index = min(start_index + request.advance_by, len(s.source_bars))

    # Check for end of data
    if start_index >= len(s.source_bars):
        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=ReplaySwingState(),
            current_bar_index=request.current_bar_index,
            current_price=s.source_bars[request.current_bar_index].close if request.current_bar_index < len(s.source_bars) else 0,
            end_of_data=True,
        )

    # Scale thresholds
    scale_thresholds = _replay_cache.get("scale_thresholds") or {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}

    # Get incremental state (should be initialized by calibration)
    incremental_state: Optional[IncrementalSwingState] = _replay_cache.get("incremental_state")

    # Check if we need to fallback to legacy detection
    # This happens if:
    # 1. No incremental state (calibration not called)
    # 2. Cache miss (position jumped, state is stale)
    use_incremental = (
        incremental_state is not None and
        _replay_cache["last_bar_index"] == request.current_bar_index and
        len(incremental_state.highs) == request.current_bar_index + 1
    )

    if not use_incremental:
        # Fallback to legacy O(N log N) detection for cache miss
        # This should be rare - only happens if client sends out-of-sequence requests
        if _replay_cache["last_bar_index"] != request.current_bar_index:
            swings_by_scale = _detect_swings_at_bar(
                s.source_bars, request.current_bar_index, scale_thresholds
            )
            swing_state_dict = {}
            fib_levels_dict = {}
            current_price = s.source_bars[request.current_bar_index].close
            for scale in ["XL", "L", "M", "S"]:
                for swing in swings_by_scale[scale]:
                    swing_state_dict[swing['id']] = swing
                    fib_levels_dict[swing['id']] = _get_current_fib_level(swing, current_price)

            _replay_cache["swing_state"] = swing_state_dict
            _replay_cache["fib_levels"] = fib_levels_dict
            _replay_cache["last_bar_index"] = request.current_bar_index

    # Process each new bar
    new_bars = []
    all_events = []

    for bar_index in range(start_index, end_index):
        bar = s.source_bars[bar_index]
        new_bars.append(ReplayBarResponse(
            index=bar_index,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        ))

        if use_incremental and incremental_state is not None:
            # Use O(active) incremental detection
            inc_events = advance_bar_incremental(
                bar_high=bar.high,
                bar_low=bar.low,
                bar_close=bar.close,
                state=incremental_state
            )

            # Convert IncrementalEvents to ReplayEventResponse
            for event in inc_events:
                is_active = event.event_type != "SWING_INVALIDATED"
                all_events.append(_incremental_event_to_response(event, is_active))

            # Update cache with incremental state
            swing_state_dict = {}
            fib_levels_dict = {}
            for swing_id, swing in incremental_state.active_swings.items():
                swing_state_dict[swing_id] = swing.to_dict()
                fib_levels_dict[swing_id] = incremental_state.fib_levels.get(swing_id, 0.0)

            _replay_cache["swing_state"] = swing_state_dict
            _replay_cache["fib_levels"] = fib_levels_dict
            _replay_cache["last_bar_index"] = bar_index

        else:
            # Fallback: O(N log N) full detection per bar
            new_swings_by_scale = _detect_swings_at_bar(
                s.source_bars, bar_index, scale_thresholds
            )

            new_swing_state_dict = {}
            for scale in ["XL", "L", "M", "S"]:
                for swing in new_swings_by_scale[scale]:
                    new_swing_state_dict[swing['id']] = swing

            current_price = bar.close
            events, new_fib_levels = _diff_swing_states(
                _replay_cache["swing_state"],
                new_swing_state_dict,
                _replay_cache["fib_levels"],
                current_price,
                bar_index,
                calibration_swing_ids=_replay_cache.get("calibration_swing_ids")
            )
            all_events.extend(events)

            _replay_cache["swing_state"] = new_swing_state_dict
            _replay_cache["fib_levels"] = new_fib_levels
            _replay_cache["last_bar_index"] = bar_index

    # Build final swing state response
    final_bar_index = end_index - 1
    final_price = s.source_bars[final_bar_index].close

    # Group swings by scale for response
    swing_state_response = ReplaySwingState()

    if use_incremental and incremental_state is not None:
        # Build from incremental state
        for swing_id, swing in incremental_state.active_swings.items():
            fib_level = swing.get_fib_level(final_price)
            is_active = 0.382 <= fib_level <= 2.0
            swing_response = _active_swing_to_response(swing, is_active)
            scale = swing.scale
            if scale == "XL":
                swing_state_response.XL.append(swing_response)
            elif scale == "L":
                swing_state_response.L.append(swing_response)
            elif scale == "M":
                swing_state_response.M.append(swing_response)
            else:
                swing_state_response.S.append(swing_response)
    else:
        # Build from legacy cache
        for swing_id, swing in _replay_cache["swing_state"].items():
            is_active = _is_swing_active(swing, final_price, swing['direction'])
            swing_response = _swing_to_response(swing, is_active)
            scale = swing['scale']
            if scale == "XL":
                swing_state_response.XL.append(swing_response)
            elif scale == "L":
                swing_state_response.L.append(swing_response)
            elif scale == "M":
                swing_state_response.M.append(swing_response)
            else:
                swing_state_response.S.append(swing_response)

    # Update playback_index for backend-controlled data boundary
    s.playback_index = final_bar_index

    return ReplayAdvanceResponse(
        new_bars=new_bars,
        events=all_events,
        swing_state=swing_state_response,
        current_bar_index=final_bar_index,
        current_price=final_price,
        end_of_data=final_bar_index >= len(s.source_bars) - 1,
    )


@router.post("/api/playback/feedback", response_model=PlaybackFeedbackResponse)
async def submit_playback_feedback(request: PlaybackFeedbackRequest):
    """
    Submit playback feedback observation.

    Captures free-form text feedback during Replay View playback at any time.
    Creates a playback session if none exists for the current data file.

    Request body:
        - text: Free-form observation text
        - playback_bar: Current playback bar index
        - snapshot: Rich context snapshot (state, swing counts, etc.)

    Returns:
        - success: Whether the observation was saved
        - observation_id: UUID of the created observation
        - message: Human-readable result message
    """
    from ..api import get_state

    s = get_state()

    # Initialize feedback storage if needed
    if s.playback_feedback_storage is None:
        s.playback_feedback_storage = PlaybackFeedbackStorage()

    # Validate text is not empty
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Observation text cannot be empty")

    # Build rich context dict from snapshot
    snapshot = request.snapshot
    context = {
        "state": snapshot.state,
        "window_offset": snapshot.window_offset,
        "bars_since_calibration": snapshot.bars_since_calibration,
        "current_bar_index": snapshot.current_bar_index,
        "calibration_bar_count": snapshot.calibration_bar_count,
        "swings_found": {
            "XL": snapshot.swings_found.XL,
            "L": snapshot.swings_found.L,
            "M": snapshot.swings_found.M,
            "S": snapshot.swings_found.S,
        },
        "swings_invalidated": snapshot.swings_invalidated,
        "swings_completed": snapshot.swings_completed,
    }

    # Add optional event context if present
    if snapshot.event_context:
        event_ctx = {}
        if snapshot.event_context.event_type:
            event_ctx["event_type"] = snapshot.event_context.event_type
        if snapshot.event_context.scale:
            event_ctx["scale"] = snapshot.event_context.scale
        if snapshot.event_context.swing:
            event_ctx["swing"] = snapshot.event_context.swing
        if snapshot.event_context.detection_bar_index is not None:
            event_ctx["detection_bar_index"] = snapshot.event_context.detection_bar_index
        if event_ctx:
            context["event_context"] = event_ctx

    # Add observation
    observation = s.playback_feedback_storage.add_observation(
        data_file=s.data_file or "unknown",
        playback_bar=request.playback_bar,
        event_context=context,
        text=text,
        offset=s.window_offset,
    )

    return PlaybackFeedbackResponse(
        success=True,
        observation_id=observation.observation_id,
        message="Observation saved successfully",
    )
