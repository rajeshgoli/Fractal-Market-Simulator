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
from typing import List, Optional
import sys
import os

# Import existing Bar type
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from bull_reference_detector import Bar


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
        
        Per spec section 9:
        - Invalidation occurs when price closes below -0.1 level
        - OR when price wicks below -0.15 level (even if closes above)
        
        For bear swings, directions are reversed.
        
        Returns:
            StructuralEvent if invalidation detected, None otherwise
        """
        if "-0.1" not in swing.levels:
            return None
            
        stop_level = swing.levels["-0.1"]
        swing_size = abs(swing.high_price - swing.low_price)
        tolerance = swing_size * 0.001
        
        # Calculate wick threshold level
        if swing.is_bull:
            wick_threshold = swing.low_price + (swing_size * self.invalidation_wick_threshold)
        else:
            wick_threshold = swing.high_price - (swing_size * self.invalidation_wick_threshold)
        
        invalidated = False
        reason = ""
        
        if swing.is_bull:
            # Bull swing invalidates if:
            # 1. Closes below -0.1 level, OR
            # 2. Wicks below -0.15 level
            if bar.close < (stop_level - tolerance):
                invalidated = True
                reason = "close below -0.1 threshold"
            elif bar.low < (wick_threshold - tolerance):
                invalidated = True
                reason = "wick below -0.15 threshold"
        else:
            # Bear swing invalidates if:
            # 1. Closes above -0.1 level (upward), OR
            # 2. Wicks above -0.15 level (upward)
            if bar.close > (stop_level + tolerance):
                invalidated = True
                reason = "close above -0.1 threshold"
            elif bar.high > (wick_threshold + tolerance):
                invalidated = True
                reason = "wick above -0.15 threshold"
        
        if not invalidated:
            return None
            
        description = f"{'Bull' if swing.is_bull else 'Bear'} swing {swing.swing_id}: INVALIDATED - {reason}"
        
        return StructuralEvent(
            event_type=EventType.INVALIDATION,
            severity=EventSeverity.MAJOR,
            timestamp=bar.timestamp,
            source_bar_idx=source_bar_idx,
            level_name="-0.1",
            level_price=stop_level,
            swing_id=swing.swing_id,
            scale=swing.scale,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            description=description
        )