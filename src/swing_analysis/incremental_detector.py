"""
Incremental Swing Detector

Provides O(active_swings) per-bar swing detection for replay playback,
replacing the O(N log N) full detection that runs on every bar.

Key insight: Once calibrated, we only need to:
1. Check for new swing points at the trailing edge (N - lookback)
2. Pair new swing points with existing opposite points
3. Check active swings for invalidation (pivot violation)
4. Check active swings for fib level crosses

This reduces per-bar cost from ~130K ops to ~50 ops for typical datasets.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from sortedcontainers import SortedList


@dataclass
class SwingPoint:
    """A confirmed swing point (local extremum)."""
    point_type: str  # 'high' or 'low'
    bar_index: int
    price: float

    def __lt__(self, other: 'SwingPoint') -> bool:
        """Sort by bar_index for SortedList."""
        return self.bar_index < other.bar_index


@dataclass
class ActiveSwing:
    """An active swing being tracked for events."""
    swing_id: str
    direction: str  # 'bull' or 'bear'
    scale: str  # 'XL', 'L', 'M', 'S'
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    rank: int
    formation_bar: int  # Bar index when this swing was formed

    @property
    def swing_range(self) -> float:
        """Swing range (high - low)."""
        return self.high_price - self.low_price

    def get_fib_level(self, price: float) -> float:
        """Calculate current fib level for a price."""
        if self.direction == 'bull':
            # Bull: defended pivot is low, ratio increases as price rises
            return (price - self.low_price) / self.swing_range if self.swing_range > 0 else 0.0
        else:
            # Bear: defended pivot is high, ratio increases as price falls
            return (self.high_price - price) / self.swing_range if self.swing_range > 0 else 0.0

    def is_pivot_violated(self, bar_low: float, bar_high: float, tolerance: float) -> bool:
        """Check if the swing's defended pivot was violated."""
        if self.direction == 'bull':
            # Bull swing: defended pivot is low_price
            threshold = self.low_price - tolerance * self.swing_range
            return bar_low < threshold
        else:
            # Bear swing: defended pivot is high_price
            threshold = self.high_price + tolerance * self.swing_range
            return bar_high > threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'id': self.swing_id,
            'direction': self.direction,
            'scale': self.scale,
            'high_price': self.high_price,
            'high_bar_index': self.high_bar_index,
            'low_price': self.low_price,
            'low_bar_index': self.low_bar_index,
            'size': self.size,
            'rank': self.rank,
        }


@dataclass
class IncrementalEvent:
    """An event detected during incremental processing."""
    event_type: str  # SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED, LEVEL_CROSS
    bar_index: int
    scale: str
    direction: str
    swing_id: str
    swing: Optional[ActiveSwing] = None
    level: Optional[float] = None
    previous_level: Optional[float] = None


@dataclass
class IncrementalSwingState:
    """
    State for incremental swing detection.

    Initialized at calibration, updated per-bar during playback.
    """
    # Frozen at calibration
    median_candle: float
    price_range: float
    scale_thresholds: Dict[str, float]  # Scale -> minimum size threshold

    # Source bar data (appended per bar)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    closes: List[float] = field(default_factory=list)

    # Sorted swing points (for O(log N) lookup during pairing)
    swing_highs: SortedList = field(default_factory=SortedList)
    swing_lows: SortedList = field(default_factory=SortedList)

    # Active swings by ID
    active_swings: Dict[str, ActiveSwing] = field(default_factory=dict)

    # Fib level tracking for level cross detection
    fib_levels: Dict[str, float] = field(default_factory=dict)

    # Detection parameters
    lookback: int = 5
    protection_tolerance: float = 0.1
    max_pair_distance: int = 2000

    # Counters for swing ID generation
    _bull_counter: int = 0
    _bear_counter: int = 0

    def assign_scale(self, size: float) -> str:
        """Assign swing to largest scale it qualifies for."""
        if size >= self.scale_thresholds.get("XL", float('inf')):
            return "XL"
        elif size >= self.scale_thresholds.get("L", float('inf')):
            return "L"
        elif size >= self.scale_thresholds.get("M", float('inf')):
            return "M"
        return "S"

    def get_swings_by_scale(self) -> Dict[str, List[ActiveSwing]]:
        """Group active swings by scale."""
        result = {"XL": [], "L": [], "M": [], "S": []}
        for swing in self.active_swings.values():
            result[swing.scale].append(swing)
        return result


def is_swing_high(idx: int, highs: List[float], lookback: int) -> bool:
    """
    Check if bar at idx is a swing high.

    A swing high has the highest high in the ±lookback window.
    """
    n = len(highs)
    if idx < lookback or idx >= n - lookback:
        return False

    center_high = highs[idx]
    for i in range(idx - lookback, idx + lookback + 1):
        if i != idx and highs[i] > center_high:
            return False
        # Tie-breaking: earlier bar wins for equal values
        if i != idx and highs[i] == center_high and i < idx:
            return False

    return True


def is_swing_low(idx: int, lows: List[float], lookback: int) -> bool:
    """
    Check if bar at idx is a swing low.

    A swing low has the lowest low in the ±lookback window.
    """
    n = len(lows)
    if idx < lookback or idx >= n - lookback:
        return False

    center_low = lows[idx]
    for i in range(idx - lookback, idx + lookback + 1):
        if i != idx and lows[i] < center_low:
            return False
        # Tie-breaking: earlier bar wins for equal values
        if i != idx and lows[i] == center_low and i < idx:
            return False

    return True


def _check_pre_formation_protection(
    highs: List[float],
    lows: List[float],
    high_idx: int,
    low_idx: int,
    direction: str,
    tolerance: float
) -> bool:
    """
    Check pre-formation protection for a swing pair.

    For bull swing (high before low): highs between high_idx and low_idx
    must not exceed high_price significantly.

    For bear swing (low before high): lows between low_idx and high_idx
    must not go below low_price significantly.
    """
    if direction == 'bull':
        high_price = highs[high_idx]
        swing_range = high_price - lows[low_idx]
        threshold = high_price + tolerance * swing_range

        for i in range(high_idx + 1, low_idx):
            if highs[i] > threshold:
                return False
    else:
        low_price = lows[low_idx]
        swing_range = highs[high_idx] - low_price
        threshold = low_price - tolerance * swing_range

        for i in range(low_idx + 1, high_idx):
            if lows[i] < threshold:
                return False

    return True


def _pair_new_high(
    new_high: SwingPoint,
    state: IncrementalSwingState,
    current_bar: int
) -> List[IncrementalEvent]:
    """
    Pair a new swing high with previous lows to form bear swings.

    Bear swing: low BEFORE high (upswing).
    """
    events = []

    # Find candidate lows in pairing window
    min_idx = max(0, new_high.bar_index - state.max_pair_distance)

    for low_point in state.swing_lows:
        if low_point.bar_index < min_idx:
            continue
        if low_point.bar_index >= new_high.bar_index:
            break

        # Calculate swing properties
        size = new_high.price - low_point.price
        if size <= 0:
            continue

        # Check scale threshold (minimum size for S scale)
        scale = state.assign_scale(size)

        # Check pre-formation protection
        if not _check_pre_formation_protection(
            state.highs, state.lows,
            new_high.bar_index, low_point.bar_index,
            'bear', state.protection_tolerance
        ):
            continue

        # Check if current price is in valid range (0.382 to 2.0)
        current_price = state.closes[-1]
        fib_level = (new_high.price - current_price) / size
        if fib_level < 0.382 or fib_level > 2.0:
            continue

        # Create swing
        state._bear_counter += 1
        swing_id = f"inc-bear-{low_point.bar_index}-{new_high.bar_index}"

        swing = ActiveSwing(
            swing_id=swing_id,
            direction='bear',
            scale=scale,
            high_price=new_high.price,
            high_bar_index=new_high.bar_index,
            low_price=low_point.price,
            low_bar_index=low_point.bar_index,
            size=size,
            rank=len([s for s in state.active_swings.values() if s.scale == scale]) + 1,
            formation_bar=current_bar,
        )

        state.active_swings[swing_id] = swing
        state.fib_levels[swing_id] = fib_level

        events.append(IncrementalEvent(
            event_type="SWING_FORMED",
            bar_index=current_bar,
            scale=scale,
            direction='bear',
            swing_id=swing_id,
            swing=swing,
        ))

    return events


def _pair_new_low(
    new_low: SwingPoint,
    state: IncrementalSwingState,
    current_bar: int
) -> List[IncrementalEvent]:
    """
    Pair a new swing low with previous highs to form bull swings.

    Bull swing: high BEFORE low (downswing).
    """
    events = []

    # Find candidate highs in pairing window
    min_idx = max(0, new_low.bar_index - state.max_pair_distance)

    for high_point in state.swing_highs:
        if high_point.bar_index < min_idx:
            continue
        if high_point.bar_index >= new_low.bar_index:
            break

        # Calculate swing properties
        size = high_point.price - new_low.price
        if size <= 0:
            continue

        # Check scale threshold
        scale = state.assign_scale(size)

        # Check pre-formation protection
        if not _check_pre_formation_protection(
            state.highs, state.lows,
            high_point.bar_index, new_low.bar_index,
            'bull', state.protection_tolerance
        ):
            continue

        # Check if current price is in valid range (0.382 to 2.0)
        current_price = state.closes[-1]
        fib_level = (current_price - new_low.price) / size
        if fib_level < 0.382 or fib_level > 2.0:
            continue

        # Create swing
        state._bull_counter += 1
        swing_id = f"inc-bull-{high_point.bar_index}-{new_low.bar_index}"

        swing = ActiveSwing(
            swing_id=swing_id,
            direction='bull',
            scale=scale,
            high_price=high_point.price,
            high_bar_index=high_point.bar_index,
            low_price=new_low.price,
            low_bar_index=new_low.bar_index,
            size=size,
            rank=len([s for s in state.active_swings.values() if s.scale == scale]) + 1,
            formation_bar=current_bar,
        )

        state.active_swings[swing_id] = swing
        state.fib_levels[swing_id] = fib_level

        events.append(IncrementalEvent(
            event_type="SWING_FORMED",
            bar_index=current_bar,
            scale=scale,
            direction='bull',
            swing_id=swing_id,
            swing=swing,
        ))

    return events


def advance_bar_incremental(
    bar_high: float,
    bar_low: float,
    bar_close: float,
    state: IncrementalSwingState
) -> List[IncrementalEvent]:
    """
    Process a single new bar incrementally.

    This is the core O(active_swings) per-bar operation.

    Args:
        bar_high: New bar's high price
        bar_low: New bar's low price
        bar_close: New bar's close price
        state: Incremental swing state to update

    Returns:
        List of events that occurred on this bar
    """
    events = []
    current_bar = len(state.highs)  # Index of new bar

    # 1. Append new bar data
    state.highs.append(bar_high)
    state.lows.append(bar_low)
    state.closes.append(bar_close)

    # 2. Check for swing point confirmation at N - lookback
    check_idx = current_bar - state.lookback
    if check_idx >= state.lookback:  # Need full window on both sides
        # Check for new swing high
        if is_swing_high(check_idx, state.highs, state.lookback):
            point = SwingPoint('high', check_idx, state.highs[check_idx])
            state.swing_highs.add(point)
            # Pair with previous lows to form bear swings
            events.extend(_pair_new_high(point, state, current_bar))

        # Check for new swing low
        if is_swing_low(check_idx, state.lows, state.lookback):
            point = SwingPoint('low', check_idx, state.lows[check_idx])
            state.swing_lows.add(point)
            # Pair with previous highs to form bull swings
            events.extend(_pair_new_low(point, state, current_bar))

    # 3. Check all active swings for invalidation
    to_remove = []
    for swing_id, swing in state.active_swings.items():
        if swing.is_pivot_violated(bar_low, bar_high, state.protection_tolerance):
            to_remove.append(swing_id)
            events.append(IncrementalEvent(
                event_type="SWING_INVALIDATED",
                bar_index=current_bar,
                scale=swing.scale,
                direction=swing.direction,
                swing_id=swing_id,
                swing=swing,
            ))

    for swing_id in to_remove:
        del state.active_swings[swing_id]
        if swing_id in state.fib_levels:
            del state.fib_levels[swing_id]

    # 4. Check remaining swings for fib level crosses
    for swing_id, swing in state.active_swings.items():
        old_level = state.fib_levels.get(swing_id, 0.0)
        new_level = swing.get_fib_level(bar_close)
        state.fib_levels[swing_id] = new_level

        # Check for completion (crossed 2.0)
        if old_level < 2.0 <= new_level:
            events.append(IncrementalEvent(
                event_type="SWING_COMPLETED",
                bar_index=current_bar,
                scale=swing.scale,
                direction=swing.direction,
                swing_id=swing_id,
                swing=swing,
                level=2.0,
                previous_level=old_level,
            ))
        # Check for significant level crosses
        elif new_level > old_level:
            significant_levels = [0.382, 0.5, 0.618, 1.0, 1.382, 1.618]
            for lvl in significant_levels:
                if old_level < lvl <= new_level:
                    events.append(IncrementalEvent(
                        event_type="LEVEL_CROSS",
                        bar_index=current_bar,
                        scale=swing.scale,
                        direction=swing.direction,
                        swing_id=swing_id,
                        swing=swing,
                        level=lvl,
                        previous_level=old_level,
                    ))
                    break  # Only emit one level cross per bar per swing

    return events


def initialize_from_calibration(
    calibration_swings: Dict[str, List[Dict]],
    source_bars: List[Any],
    calibration_bar_count: int,
    scale_thresholds: Dict[str, float],
    current_price: float,
    lookback: int = 5,
    protection_tolerance: float = 0.1,
) -> IncrementalSwingState:
    """
    Initialize incremental state from calibration results.

    Args:
        calibration_swings: Dict of scale -> list of swing dicts from calibration
        source_bars: List of Bar objects
        calibration_bar_count: Number of bars in calibration window
        scale_thresholds: Scale -> minimum size thresholds
        current_price: Price at end of calibration
        lookback: Swing point detection lookback
        protection_tolerance: Pivot violation tolerance

    Returns:
        Initialized IncrementalSwingState
    """
    # Extract price data
    highs = [bar.high for bar in source_bars[:calibration_bar_count]]
    lows = [bar.low for bar in source_bars[:calibration_bar_count]]
    closes = [bar.close for bar in source_bars[:calibration_bar_count]]

    # Calculate statistics
    candle_sizes = [h - l for h, l in zip(highs, lows)]
    median_candle = float(np.median(candle_sizes)) if candle_sizes else 1.0
    price_range = max(highs) - min(lows) if highs else 1.0

    # Initialize state
    state = IncrementalSwingState(
        median_candle=median_candle,
        price_range=price_range,
        scale_thresholds=scale_thresholds,
        highs=highs,
        lows=lows,
        closes=closes,
        lookback=lookback,
        protection_tolerance=protection_tolerance,
    )

    # Detect all swing points in calibration window
    for i in range(lookback, calibration_bar_count - lookback):
        if is_swing_high(i, highs, lookback):
            state.swing_highs.add(SwingPoint('high', i, highs[i]))
        if is_swing_low(i, lows, lookback):
            state.swing_lows.add(SwingPoint('low', i, lows[i]))

    # Import active swings from calibration
    for scale, swings in calibration_swings.items():
        for swing_dict in swings:
            if not swing_dict.get('is_active', True):
                continue

            swing_id = swing_dict.get('id', f"cal-{swing_dict.get('direction')}-{swing_dict.get('high_bar_index')}-{swing_dict.get('low_bar_index')}")
            direction = swing_dict.get('direction', 'bull')

            swing = ActiveSwing(
                swing_id=swing_id,
                direction=direction,
                scale=scale,
                high_price=swing_dict['high_price'],
                high_bar_index=swing_dict['high_bar_index'],
                low_price=swing_dict['low_price'],
                low_bar_index=swing_dict['low_bar_index'],
                size=swing_dict.get('size', swing_dict['high_price'] - swing_dict['low_price']),
                rank=swing_dict.get('rank', 1),
                formation_bar=swing_dict.get('low_bar_index', 0) if direction == 'bull' else swing_dict.get('high_bar_index', 0),
            )

            state.active_swings[swing_id] = swing
            state.fib_levels[swing_id] = swing.get_fib_level(current_price)

    return state
