"""
Swing State Manager Module

Manages active swings across all four structural scales (S, M, L, XL) and handles
state transitions based on events from the Event Detector. Integrates swing detection,
level calculation, and event detection to maintain a complete picture of market structure.

Key Features:
- Multi-scale swing lifecycle management (S, M, L, XL scales)
- State transitions: active -> completed/invalidated
- Swing replacement logic (±20% size similarity)
- Integration with SwingDetector, LevelCalculator, and EventDetector
- Performance optimized for <500ms per step on large datasets

Author: Generated for Market Simulator Project
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
import pandas as pd

# Import existing modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.legacy.bull_reference_detector import Bar
from src.legacy.swing_detector import detect_swings
from src.legacy.level_calculator import calculate_levels
from src.analysis.scale_calibrator import ScaleConfig
from src.analysis.bar_aggregator import BarAggregator
from src.analysis.event_detector import EventDetector, EventType, StructuralEvent, ActiveSwing


@dataclass
class SwingUpdateResult:
    """Result of processing a new bar through the swing state manager."""
    events: List[StructuralEvent]          # All events detected this bar
    new_swings: List[ActiveSwing]          # Newly detected swings
    state_changes: List[Tuple[str, str, str]]  # (swing_id, old_state, new_state)
    removed_swings: List[str]              # swing_ids of removed swings


class SwingStateManager:
    """Manages active swings across scales and their state transitions."""
    
    def __init__(self, scale_config: ScaleConfig):
        """
        Initialize the swing state manager.
        
        Args:
            scale_config: Scale boundaries and aggregation settings from calibrator
        """
        self.scale_config = scale_config
        self.event_detector = EventDetector()
        
        # Active swings organized by scale
        self.active_swings: Dict[str, List[ActiveSwing]] = {
            scale: [] for scale in ['S', 'M', 'L', 'XL']
        }
        
        # Historical swing tracking for replacement logic
        self.completed_swings: Dict[str, List[ActiveSwing]] = {
            scale: [] for scale in ['S', 'M', 'L', 'XL']
        }
        self.invalidated_swings: Dict[str, List[ActiveSwing]] = {
            scale: [] for scale in ['S', 'M', 'L', 'XL']
        }
        
        # Bar aggregator for multi-timeframe swing detection
        self.bar_aggregator: Optional[BarAggregator] = None
        
        # Performance tracking
        self.total_bars_processed = 0
        
        # Lookback settings per scale (can be adjusted for performance)
        self.lookback_settings = {
            'S': 5,
            'M': 7,
            'L': 10,
            'XL': 15
        }
        
    def initialize_with_bars(self, source_bars: List[Bar]) -> None:
        """
        Initialize the aggregator and detect initial swings from historical data.
        
        Args:
            source_bars: List of source bars for initialization
        """
        if not source_bars:
            return
            
        # Initialize bar aggregator
        self.bar_aggregator = BarAggregator(source_bars)
        
        # Detect initial swings for each scale
        for scale in ['S', 'M', 'L', 'XL']:
            timeframe = self.scale_config.aggregations[scale]
            aggregated_bars = self.bar_aggregator.get_bars(timeframe)
            
            if len(aggregated_bars) > 20:  # Need sufficient data for swing detection
                self._detect_initial_swings_for_scale(aggregated_bars, scale)
    
    def update_swings(self, bar: Bar, source_bar_idx: int) -> SwingUpdateResult:
        """
        Process new bar, detect swings, update states, and return events.
        
        Args:
            bar: New OHLC bar to process
            source_bar_idx: Index of this bar in the source series
            
        Returns:
            SwingUpdateResult with events and state changes
        """
        self.total_bars_processed += 1
        
        events = []
        new_swings = []
        state_changes = []
        removed_swings = []
        
        if self.bar_aggregator is None:
            return SwingUpdateResult(events, new_swings, state_changes, removed_swings)
        
        # Update bar aggregator with new bar
        self.bar_aggregator._append_bar(bar)
        
        # Process each scale independently
        for scale in ['S', 'M', 'L', 'XL']:
            scale_result = self._process_scale(bar, source_bar_idx, scale)
            
            events.extend(scale_result.events)
            new_swings.extend(scale_result.new_swings)
            state_changes.extend(scale_result.state_changes)
            removed_swings.extend(scale_result.removed_swings)
        
        return SwingUpdateResult(events, new_swings, state_changes, removed_swings)
    
    def get_active_swings(self, scale: Optional[str] = None) -> List[ActiveSwing]:
        """
        Get currently active swings for visualization.
        
        Args:
            scale: Specific scale to get swings for, or None for all scales
            
        Returns:
            List of active swings
        """
        if scale is not None:
            return self.active_swings.get(scale, [])
        
        # Return all active swings across scales
        all_swings = []
        for scale_swings in self.active_swings.values():
            all_swings.extend(scale_swings)
        return all_swings
    
    def get_swing_counts(self) -> Dict[str, Dict[str, int]]:
        """Get swing counts by scale and state for monitoring."""
        counts = {}
        for scale in ['S', 'M', 'L', 'XL']:
            counts[scale] = {
                'active': len(self.active_swings[scale]),
                'completed': len(self.completed_swings[scale]),
                'invalidated': len(self.invalidated_swings[scale])
            }
        return counts
    
    def _process_scale(self, bar: Bar, source_bar_idx: int, scale: str) -> SwingUpdateResult:
        """Process a single scale for the given bar."""
        events = []
        new_swings = []
        state_changes = []
        removed_swings = []
        
        timeframe = self.scale_config.aggregations[scale]
        
        # Get current aggregated bar for this scale
        current_agg_bar = self.bar_aggregator.get_bar_at_source_time(timeframe, source_bar_idx)
        previous_agg_bar = None
        
        if source_bar_idx > 0:
            previous_agg_bar = self.bar_aggregator.get_bar_at_source_time(timeframe, source_bar_idx - 1)
        
        # Detect events for existing swings
        if current_agg_bar and self.active_swings[scale]:
            scale_events = self.event_detector.detect_events(
                current_agg_bar, 
                source_bar_idx,
                self.active_swings[scale],
                previous_agg_bar
            )
            events.extend(scale_events)
            
            # Process state changes based on events
            for event in scale_events:
                if event.event_type == EventType.COMPLETION:
                    state_changes.extend(self._handle_completion(event, scale))
                elif event.event_type == EventType.INVALIDATION:
                    state_changes.extend(self._handle_invalidation(event, scale))
        
        # Detect new swings (only on closed bars to avoid flickering)
        if current_agg_bar:
            closed_bar = self.bar_aggregator.get_closed_bar_at_source_time(timeframe, source_bar_idx)
            if closed_bar:
                new_scale_swings = self._detect_new_swings(scale, timeframe)
                new_swings.extend(new_scale_swings)
                
                # Check for swing replacements
                removed_ids = self._check_swing_replacements(scale, new_scale_swings)
                removed_swings.extend(removed_ids)
        
        return SwingUpdateResult(events, new_swings, state_changes, removed_swings)
    
    def _detect_initial_swings_for_scale(self, bars: List[Bar], scale: str) -> None:
        """Detect initial swings for a scale from historical data."""
        # Convert bars to DataFrame for swing detector
        df_data = []
        for bar in bars:
            df_data.append({
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close
            })
        
        if len(df_data) < 20:
            return
            
        df = pd.DataFrame(df_data)
        
        # Detect swings using existing swing detector
        lookback = self.lookback_settings[scale]
        swing_result = detect_swings(df, lookback=lookback, filter_redundant=True)
        
        # Convert to ActiveSwing objects
        bull_refs = swing_result.get('bull_references', [])
        bear_refs = swing_result.get('bear_references', [])
        
        for ref in bull_refs:
            if self._is_swing_in_scale(ref['size'], scale):
                active_swing = self._create_active_swing(ref, scale, is_bull=True)
                if active_swing:
                    self.active_swings[scale].append(active_swing)
        
        for ref in bear_refs:
            if self._is_swing_in_scale(ref['size'], scale):
                active_swing = self._create_active_swing(ref, scale, is_bull=False)
                if active_swing:
                    self.active_swings[scale].append(active_swing)
    
    def _detect_new_swings(self, scale: str, timeframe: int) -> List[ActiveSwing]:
        """Detect new swings for a scale using recent data."""
        new_swings = []
        
        # Get recent aggregated bars for swing detection
        all_bars = self.bar_aggregator.get_bars(timeframe)
        
        if len(all_bars) < 30:  # Need sufficient recent data
            return new_swings
        
        # Use last 100 bars for swing detection to catch new formations
        recent_bars = all_bars[-100:] if len(all_bars) > 100 else all_bars
        
        # Convert to DataFrame
        df_data = []
        for bar in recent_bars:
            df_data.append({
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close
            })
        
        df = pd.DataFrame(df_data)
        
        # Detect swings
        lookback = self.lookback_settings[scale]
        swing_result = detect_swings(df, lookback=lookback, filter_redundant=True)
        
        # Check for new swings not already tracked
        bull_refs = swing_result.get('bull_references', [])
        bear_refs = swing_result.get('bear_references', [])
        
        existing_swing_timestamps = set()
        for swing in self.active_swings[scale]:
            existing_swing_timestamps.add((swing.high_timestamp, swing.low_timestamp))
        
        for ref in bull_refs:
            if (self._is_swing_in_scale(ref['size'], scale) and 
                (ref.get('high_timestamp'), ref.get('low_timestamp')) not in existing_swing_timestamps):
                active_swing = self._create_active_swing(ref, scale, is_bull=True)
                if active_swing:
                    new_swings.append(active_swing)
        
        for ref in bear_refs:
            if (self._is_swing_in_scale(ref['size'], scale) and 
                (ref.get('high_timestamp'), ref.get('low_timestamp')) not in existing_swing_timestamps):
                active_swing = self._create_active_swing(ref, scale, is_bull=False)
                if active_swing:
                    new_swings.append(active_swing)
        
        # Add new swings to active list
        self.active_swings[scale].extend(new_swings)
        
        return new_swings
    
    def _create_active_swing(self, swing_ref: dict, scale: str, is_bull: bool) -> Optional[ActiveSwing]:
        """Create an ActiveSwing object from a swing reference."""
        try:
            high_price = float(swing_ref['high_price'])
            low_price = float(swing_ref['low_price'])
            
            # Calculate Fibonacci levels
            direction = "bullish" if is_bull else "bearish"
            levels = calculate_levels(
                high=Decimal(str(high_price)),
                low=Decimal(str(low_price)),
                direction=direction,
                quantization=Decimal("0.25")
            )
            
            # Convert to dict format
            level_dict = {str(level.multiplier): float(level.price) for level in levels}
            
            # Generate unique ID
            swing_id = f"{scale}-{('bull' if is_bull else 'bear')}-{uuid.uuid4().hex[:8]}"
            
            return ActiveSwing(
                swing_id=swing_id,
                scale=scale,
                high_price=high_price,
                low_price=low_price,
                high_timestamp=swing_ref.get('high_timestamp', 0),
                low_timestamp=swing_ref.get('low_timestamp', 0),
                is_bull=is_bull,
                state="active",
                levels=level_dict
            )
            
        except Exception as e:
            logging.warning(f"Failed to create active swing: {e}")
            return None
    
    def _is_swing_in_scale(self, swing_size: float, scale: str) -> bool:
        """Check if a swing size belongs to the given scale."""
        boundaries = self.scale_config.boundaries[scale]
        return boundaries[0] <= swing_size < boundaries[1]
    
    def _handle_completion(self, event: StructuralEvent, scale: str) -> List[Tuple[str, str, str]]:
        """Handle swing completion event."""
        state_changes = []
        
        for i, swing in enumerate(self.active_swings[scale]):
            if swing.swing_id == event.swing_id:
                # Move to completed state
                swing.state = "completed"
                self.completed_swings[scale].append(swing)
                state_changes.append((swing.swing_id, "active", "completed"))
                break
        
        return state_changes
    
    def _handle_invalidation(self, event: StructuralEvent, scale: str) -> List[Tuple[str, str, str]]:
        """Handle swing invalidation event."""
        state_changes = []
        
        for i, swing in enumerate(self.active_swings[scale]):
            if swing.swing_id == event.swing_id:
                # Move to invalidated state
                swing.state = "invalidated"
                self.invalidated_swings[scale].append(swing)
                self.active_swings[scale].pop(i)
                state_changes.append((swing.swing_id, "active", "invalidated"))
                break
        
        return state_changes
    
    def _check_swing_replacements(self, scale: str, new_swings: List[ActiveSwing]) -> List[str]:
        """Check for swing replacements based on ±20% size similarity."""
        removed_ids = []
        
        for new_swing in new_swings:
            new_size = abs(new_swing.high_price - new_swing.low_price)
            
            # Check against existing swings of similar size
            for i in range(len(self.active_swings[scale]) - 1, -1, -1):
                existing_swing = self.active_swings[scale][i]
                
                # Skip the new swing itself
                if existing_swing.swing_id == new_swing.swing_id:
                    continue
                
                existing_size = abs(existing_swing.high_price - existing_swing.low_price)
                size_ratio = abs(new_size - existing_size) / existing_size
                
                # If within ±20% and same direction, replace the older swing
                if (size_ratio <= 0.20 and 
                    existing_swing.is_bull == new_swing.is_bull and
                    existing_swing.state == "active"):
                    
                    removed_ids.append(existing_swing.swing_id)
                    self.active_swings[scale].pop(i)
                    
                    logging.debug(f"Replaced swing {existing_swing.swing_id} with {new_swing.swing_id} "
                                f"(size ratio: {size_ratio:.3f})")
        
        return removed_ids