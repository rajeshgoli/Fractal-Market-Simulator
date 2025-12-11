"""
Event Detector Module

Detects structural events (level crossings, completions, invalidations) from price action
relative to active reference swings and their Fibonacci levels.

Key Features:
- Level crossing detection (open/close basis, not wicks)
- Completion detection at 2x extension
- Invalidation detection (close below -0.1 or wick below -0.15)
- Event priority handling and state transition signaling
- Multi-swing event detection with scale independence

Author: Generated for Market Simulator Project
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Tuple
import sys
import os

# Import existing Bar type
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.legacy.bull_reference_detector import Bar


class EventType(Enum):
    """Classification of structural events."""
    # Minor events (logged, no pause)
    LEVEL_CROSS_UP = "level_cross_up"
    LEVEL_CROSS_DOWN = "level_cross_down"
    
    # Major events (logged, pause in auto mode)
    COMPLETION = "completion"          # Price reached 2x extension
    INVALIDATION = "invalidation"      # Price closed below -0.1 or wicked below -0.15


class EventSeverity(Enum):
    MINOR = "minor"
    MAJOR = "major"


@dataclass
class StructuralEvent:
    """A detected structural event."""
    event_type: EventType
    severity: EventSeverity
    timestamp: int                     # Bar timestamp when event occurred
    source_bar_idx: int               # Index in source bar series
    level_name: str                   # e.g., "1.618", "2.0", "-0.1"
    level_price: float                # Actual price of the level
    swing_id: str                     # Identifier for the reference swing
    scale: str                        # Scale where this swing belongs: S, M, L, XL
    bar_open: float                   # Bar OHLC for context
    bar_high: float
    bar_low: float
    bar_close: float
    description: str                  # Human-readable description


@dataclass
class ActiveSwing:
    """Reference swing with computed levels for event detection."""
    swing_id: str                     # Unique identifier
    scale: str                        # S, M, L, or XL
    high_price: float
    low_price: float
    high_timestamp: int
    low_timestamp: int
    is_bull: bool                     # True = bull reference (fighting upward from below)
    state: str                        # "active", "completed", "invalidated"
    levels: dict[str, float]          # Level name -> price mapping
    # Validation state tracking (added for Issue #13)
    encroachment_achieved: bool = False       # Has price retraced to 0.382 level?
    lowest_since_low: Optional[float] = None  # Track lowest price since L (for bull swing violation)
    highest_since_high: Optional[float] = None  # Track highest price since H (for bear swing violation)


class EventDetector:
    """Detects structural events based on price action relative to swing levels."""
    
    # Fibonacci levels to monitor
    LEVEL_NAMES = ["-0.1", "0", "0.1", "0.382", "0.5", "0.618", 
                   "1", "1.1", "1.382", "1.5", "1.618", "2"]
    
    def __init__(self, invalidation_wick_threshold: float = -0.15):
        """
        Initialize the event detector.
        
        Args:
            invalidation_wick_threshold: Level below which any wick triggers invalidation
                                        (default -0.15 per spec)
        """
        self.invalidation_wick_threshold = invalidation_wick_threshold
    
    def detect_events(self, 
                      bar: Bar, 
                      source_bar_idx: int,
                      active_swings: List[ActiveSwing],
                      previous_bar: Optional[Bar] = None) -> List[StructuralEvent]:
        """
        Detect all structural events for a single bar across all active swings.
        
        Args:
            bar: Current OHLC bar to analyze
            source_bar_idx: Index of this bar in the source series
            active_swings: List of currently active reference swings with levels
            previous_bar: Previous bar (needed for crossing detection)
            
        Returns:
            List of detected events, may be empty
        """
        events = []
        
        if not active_swings:
            return events
        
        for swing in active_swings:
            # Only process active swings
            if swing.state != "active":
                continue
                
            # Check for major events first (they take priority)
            invalidation_event = self.check_invalidation(bar, source_bar_idx, swing)
            if invalidation_event:
                events.append(invalidation_event)
                continue  # If invalidated, don't check for other events
                
            completion_event = self.check_completion(bar, source_bar_idx, swing)
            if completion_event:
                events.append(completion_event)
                # Still check for other level crossings, but skip 2.0 level
                
            # Check for level crossings
            for level_name in self.LEVEL_NAMES:
                if level_name not in swing.levels:
                    continue
                    
                # Skip 2 level if completion already detected
                if level_name == "2" and completion_event:
                    continue
                    
                crossing_event = self.check_level_crossing(
                    bar, previous_bar, swing.levels[level_name], level_name, swing
                )
                if crossing_event:
                    events.append(crossing_event)
        
        return events
    
    def check_level_crossing(self,
                             bar: Bar,
                             previous_bar: Optional[Bar],
                             level_price: float,
                             level_name: str,
                             swing: ActiveSwing) -> Optional[StructuralEvent]:
        """
        Check if a bar crosses through a specific level.
        
        Per spec section 7: A crossing occurs when a bar's range spans from 
        one side of the level to the other (opened on one side, closed on other).
        
        Returns:
            StructuralEvent if crossing detected, None otherwise
        """
        if previous_bar is None:
            return None
            
        # Get tolerance for level comparison (0.1% of swing size)
        swing_size = abs(swing.high_price - swing.low_price)
        tolerance = swing_size * 0.001
        
        # Check if bar opened on one side and closed on the other
        opened_below = bar.open < (level_price - tolerance)
        closed_above = bar.close > (level_price + tolerance)
        opened_above = bar.open > (level_price + tolerance)
        closed_below = bar.close < (level_price - tolerance)
        
        event_type = None
        direction = ""
        
        if opened_below and closed_above:
            event_type = EventType.LEVEL_CROSS_UP
            direction = "upward"
        elif opened_above and closed_below:
            event_type = EventType.LEVEL_CROSS_DOWN
            direction = "downward"
        
        if event_type is None:
            return None
            
        description = f"{'Bull' if swing.is_bull else 'Bear'} swing {swing.swing_id}: Level {level_name} crossed {direction} at {level_price:.2f}"
        
        return StructuralEvent(
            event_type=event_type,
            severity=EventSeverity.MINOR,
            timestamp=bar.timestamp,
            source_bar_idx=bar.index,
            level_name=level_name,
            level_price=level_price,
            swing_id=swing.swing_id,
            scale=swing.scale,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            description=description
        )
    
    def check_completion(self,
                         bar: Bar,
                         source_bar_idx: int,
                         swing: ActiveSwing) -> Optional[StructuralEvent]:
        """
        Check if price has reached the 2x extension level (completion).
        
        For bull swings: price closes at or above 2.0 level
        For bear swings: price closes at or below 2.0 level (measured downward)
        
        Returns:
            StructuralEvent if completion detected, None otherwise
        """
        if "2" not in swing.levels:
            return None
            
        level_price = swing.levels["2"]
        swing_size = abs(swing.high_price - swing.low_price)
        tolerance = swing_size * 0.001
        
        completion_reached = False
        
        if swing.is_bull:
            # Bull swing completes when close >= 2.0 level
            completion_reached = bar.close >= (level_price - tolerance)
        else:
            # Bear swing completes when close <= 2.0 level (downward measurement)
            completion_reached = bar.close <= (level_price + tolerance)
        
        if not completion_reached:
            return None
            
        description = f"{'Bull' if swing.is_bull else 'Bear'} swing {swing.swing_id}: COMPLETED at 2x extension ({level_price:.2f})"
        
        return StructuralEvent(
            event_type=EventType.COMPLETION,
            severity=EventSeverity.MAJOR,
            timestamp=bar.timestamp,
            source_bar_idx=source_bar_idx,
            level_name="2",
            level_price=level_price,
            swing_id=swing.swing_id,
            scale=swing.scale,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            description=description
        )
    
    def check_invalidation(self,
                           bar: Bar,
                           source_bar_idx: int,
                           swing: ActiveSwing) -> Optional[StructuralEvent]:
        """
        Check if the swing has been invalidated.

        Dispatches to scale-specific validation rules:
        - S/M scales: Strict validation (no trade below L)
        - L/XL scales: Softer validation (trade-through and close thresholds)

        Returns:
            StructuralEvent if invalidation detected, None otherwise
        """
        if swing.scale in ['S', 'M']:
            return self._check_invalidation_sm(bar, source_bar_idx, swing)
        else:  # L, XL
            return self._check_invalidation_lxl(bar, source_bar_idx, swing)

    def _check_invalidation_sm(self,
                               bar: Bar,
                               source_bar_idx: int,
                               swing: ActiveSwing) -> Optional[StructuralEvent]:
        """
        S/M swing invalidation rules (Issue #13):

        Bull swing invalidates if:
        - Price ever trades below L (the swing low)

        Bear swing invalidates if:
        - Price ever trades above H (the swing high)

        Note: The lowest_since_low / highest_since_high tracking is done by
        SwingStateManager before calling this method.

        Returns:
            StructuralEvent if invalidation detected, None otherwise
        """
        swing_size = abs(swing.high_price - swing.low_price)
        tolerance = swing_size * 0.001

        invalidated = False
        reason = ""
        level_price = swing.low_price if swing.is_bull else swing.high_price

        if swing.is_bull:
            # Bull swing invalidates if price ever trades below L
            # Check using tracked lowest price (more reliable) or current bar low
            lowest = swing.lowest_since_low if swing.lowest_since_low is not None else bar.low
            if lowest < (swing.low_price - tolerance):
                invalidated = True
                reason = "trade below swing low L (S/M strict rule)"
        else:
            # Bear swing invalidates if price ever trades above H
            highest = swing.highest_since_high if swing.highest_since_high is not None else bar.high
            if highest > (swing.high_price + tolerance):
                invalidated = True
                reason = "trade above swing high H (S/M strict rule)"

        if not invalidated:
            return None

        description = f"{'Bull' if swing.is_bull else 'Bear'} swing {swing.swing_id}: INVALIDATED - {reason}"

        return StructuralEvent(
            event_type=EventType.INVALIDATION,
            severity=EventSeverity.MAJOR,
            timestamp=bar.timestamp,
            source_bar_idx=source_bar_idx,
            level_name="L" if swing.is_bull else "H",
            level_price=level_price,
            swing_id=swing.swing_id,
            scale=swing.scale,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            description=description
        )

    def _check_invalidation_lxl(self,
                                bar: Bar,
                                source_bar_idx: int,
                                swing: ActiveSwing) -> Optional[StructuralEvent]:
        """
        L/XL swing invalidation rules (Issue #13):

        Bull swing invalidates if:
        - Price ever trades below L - 0.15 * delta (deep trade-through), OR
        - Price closes below L - 0.10 * delta (soft invalidation)

        Bear swing invalidates if:
        - Price ever trades above H + 0.15 * delta (deep trade-through), OR
        - Price closes above H + 0.10 * delta (soft invalidation)

        Note: The CLOSE check uses the aggregated bar at the swing's aggregation
        level (1H for L, 4H for XL), which is already provided by SwingStateManager.

        Returns:
            StructuralEvent if invalidation detected, None otherwise
        """
        swing_size = abs(swing.high_price - swing.low_price)
        tolerance = swing_size * 0.001

        invalidated = False
        reason = ""

        if swing.is_bull:
            # Calculate thresholds
            deep_threshold = swing.low_price - (0.15 * swing_size)
            soft_threshold = swing.low_price - (0.10 * swing_size)
            level_price = soft_threshold  # Report the soft threshold as the violated level

            # Check deep trade-through using tracked lowest price
            lowest = swing.lowest_since_low if swing.lowest_since_low is not None else bar.low
            if lowest < (deep_threshold - tolerance):
                invalidated = True
                reason = f"trade below L - 0.15*delta ({deep_threshold:.2f}) (L/XL deep threshold)"
                level_price = deep_threshold
            # Check soft close threshold (aggregation-level close)
            elif bar.close < (soft_threshold - tolerance):
                invalidated = True
                reason = f"close below L - 0.10*delta ({soft_threshold:.2f}) (L/XL soft threshold)"
                level_price = soft_threshold
        else:
            # Bear swing: symmetric rules
            deep_threshold = swing.high_price + (0.15 * swing_size)
            soft_threshold = swing.high_price + (0.10 * swing_size)
            level_price = soft_threshold

            # Check deep trade-through using tracked highest price
            highest = swing.highest_since_high if swing.highest_since_high is not None else bar.high
            if highest > (deep_threshold + tolerance):
                invalidated = True
                reason = f"trade above H + 0.15*delta ({deep_threshold:.2f}) (L/XL deep threshold)"
                level_price = deep_threshold
            # Check soft close threshold (aggregation-level close)
            elif bar.close > (soft_threshold + tolerance):
                invalidated = True
                reason = f"close above H + 0.10*delta ({soft_threshold:.2f}) (L/XL soft threshold)"
                level_price = soft_threshold

        if not invalidated:
            return None

        description = f"{'Bull' if swing.is_bull else 'Bear'} swing {swing.swing_id}: INVALIDATED - {reason}"

        return StructuralEvent(
            event_type=EventType.INVALIDATION,
            severity=EventSeverity.MAJOR,
            timestamp=bar.timestamp,
            source_bar_idx=source_bar_idx,
            level_name="L-0.10" if swing.is_bull else "H+0.10",
            level_price=level_price,
            swing_id=swing.swing_id,
            scale=swing.scale,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            description=description
        )