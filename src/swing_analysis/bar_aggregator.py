"""
Bar Aggregator Module

Converts 1-minute OHLC bars into aggregated timeframes for multi-scale visualization.
Pre-computes all aggregations during initialization for fast retrieval during playback.

Key Features:
- Pre-computation of all standard timeframes (1, 5, 15, 30, 60, 240 minutes)
- Natural boundary alignment for aggregated bars
- Efficient O(1) retrieval for synchronized playback
- Distinction between closed and incomplete bars for Fibonacci calculations
- Bidirectional index mapping between source and aggregated bars

Author: Generated for Market Simulator Project
"""

import bisect
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import pandas as pd

from .bull_reference_detector import Bar


@dataclass
class AggregatedBars:
    """Container for pre-computed bar aggregations across timeframes."""
    timeframe_minutes: int
    bars: List[Bar]  # Aggregated bars in chronological order
    
    def __len__(self) -> int:
        return len(self.bars)


class BarAggregator:
    """Pre-computes and provides efficient access to aggregated OHLC bars."""
    
    STANDARD_TIMEFRAMES = [1, 5, 15, 30, 60, 240]  # minutes
    
    def __init__(self, source_bars: List[Bar]):
        """
        Initialize with 1-minute source bars and pre-compute all aggregations.
        
        Args:
            source_bars: List of 1-minute OHLC bars in chronological order
        """
        if not source_bars:
            raise ValueError("Source bars cannot be empty")
            
        # Store source bars
        self._source_bars = source_bars.copy()
        
        # Verify chronological order
        for i in range(1, len(self._source_bars)):
            if self._source_bars[i].timestamp <= self._source_bars[i-1].timestamp:
                raise ValueError(f"Source bars must be in chronological order. "
                               f"Bar {i} timestamp {self._source_bars[i].timestamp} <= "
                               f"Bar {i-1} timestamp {self._source_bars[i-1].timestamp}")
        
        # Pre-compute all aggregations
        self._aggregations: Dict[int, AggregatedBars] = {}
        self._source_to_agg_mapping: Dict[int, Dict[int, int]] = {}
        
        for timeframe in self.STANDARD_TIMEFRAMES:
            self._aggregate_timeframe(timeframe)
    
    def _aggregate_timeframe(self, timeframe_minutes: int) -> None:
        """Pre-compute aggregation for a specific timeframe."""
        if timeframe_minutes == 1:
            # 1-minute is just the source bars
            self._aggregations[1] = AggregatedBars(
                timeframe_minutes=1, 
                bars=self._source_bars.copy()
            )
            # Simple 1:1 mapping for 1-minute
            self._source_to_agg_mapping[1] = {i: i for i in range(len(self._source_bars))}
            return
        
        aggregated_bars = []
        source_to_agg_map = {}
        period_seconds = timeframe_minutes * 60
        
        # Group source bars by aggregation periods
        periods = self._group_bars_by_periods(timeframe_minutes)
        
        for period_start_time, period_bars in periods:
            if not period_bars:
                continue
                
            # Create aggregated bar using OHLC rules
            agg_bar = self._create_aggregated_bar(period_bars, len(aggregated_bars))
            aggregated_bars.append(agg_bar)
            
            # Update source-to-aggregated mapping
            agg_index = len(aggregated_bars) - 1
            for source_bar in period_bars:
                source_to_agg_map[source_bar.index] = agg_index
        
        self._aggregations[timeframe_minutes] = AggregatedBars(
            timeframe_minutes=timeframe_minutes,
            bars=aggregated_bars
        )
        self._source_to_agg_mapping[timeframe_minutes] = source_to_agg_map
    
    def _group_bars_by_periods(self, timeframe_minutes: int) -> List[Tuple[int, List[Bar]]]:
        """
        Group source bars into aggregation periods aligned to natural boundaries.
        
        Returns:
            List of (period_start_timestamp, bars_in_period) tuples
        """
        period_seconds = timeframe_minutes * 60
        periods = []
        current_period_start = None
        current_period_bars = []
        
        for bar in self._source_bars:
            # Calculate the aligned period start for this bar
            period_start = self._get_period_start(bar.timestamp, timeframe_minutes)
            
            if current_period_start is None:
                # First period
                current_period_start = period_start
                current_period_bars = [bar]
            elif period_start == current_period_start:
                # Same period
                current_period_bars.append(bar)
            else:
                # New period - save current and start new
                periods.append((current_period_start, current_period_bars))
                current_period_start = period_start
                current_period_bars = [bar]
        
        # Add final period
        if current_period_bars:
            periods.append((current_period_start, current_period_bars))
        
        return periods
    
    def _get_period_start(self, timestamp: int, timeframe_minutes: int) -> int:
        """
        Calculate the aligned period start timestamp for natural boundaries.
        
        Examples:
        - 5-minute bars align to :00, :05, :10, etc.
        - 15-minute bars align to :00, :15, :30, :45
        - 60-minute bars align to the hour
        - 240-minute bars align to 4-hour boundaries
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        if timeframe_minutes == 5:
            # Align to 5-minute boundaries
            aligned_minute = (dt.minute // 5) * 5
            aligned_dt = dt.replace(minute=aligned_minute, second=0, microsecond=0)
        elif timeframe_minutes == 15:
            # Align to 15-minute boundaries
            aligned_minute = (dt.minute // 15) * 15
            aligned_dt = dt.replace(minute=aligned_minute, second=0, microsecond=0)
        elif timeframe_minutes == 30:
            # Align to 30-minute boundaries
            aligned_minute = (dt.minute // 30) * 30
            aligned_dt = dt.replace(minute=aligned_minute, second=0, microsecond=0)
        elif timeframe_minutes == 60:
            # Align to hourly boundaries
            aligned_dt = dt.replace(minute=0, second=0, microsecond=0)
        elif timeframe_minutes == 240:
            # Align to 4-hour boundaries (00:00, 04:00, 08:00, 12:00, 16:00, 20:00)
            aligned_hour = (dt.hour // 4) * 4
            aligned_dt = dt.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes} minutes")
        
        return int(aligned_dt.timestamp())
    
    def _create_aggregated_bar(self, period_bars: List[Bar], agg_index: int) -> Bar:
        """
        Create an aggregated bar from a period's source bars using OHLC rules.
        
        OHLC Aggregation Rules:
        - Open: Open of the first bar in the period
        - High: Maximum high across all bars in the period
        - Low: Minimum low across all bars in the period
        - Close: Close of the last bar in the period
        - Timestamp: Timestamp of the first bar in the period
        """
        if not period_bars:
            raise ValueError("Cannot create aggregated bar from empty period")
        
        # Sort by timestamp to ensure correct order
        sorted_bars = sorted(period_bars, key=lambda b: b.timestamp)
        
        return Bar(
            index=agg_index,
            timestamp=sorted_bars[0].timestamp,  # First bar's timestamp
            open=sorted_bars[0].open,           # First bar's open
            high=max(bar.high for bar in sorted_bars),  # Maximum high
            low=min(bar.low for bar in sorted_bars),    # Minimum low
            close=sorted_bars[-1].close         # Last bar's close
        )
    
    def get_bars(self, timeframe_minutes: int, 
                 start_idx: int = 0, 
                 end_idx: Optional[int] = None) -> List[Bar]:
        """
        Retrieve aggregated bars for a specific timeframe.
        
        Args:
            timeframe_minutes: One of STANDARD_TIMEFRAMES
            start_idx: Starting index in the aggregated series
            end_idx: Ending index (exclusive), None for all remaining
            
        Returns:
            List of aggregated bars for the requested range
        """
        if timeframe_minutes not in self.STANDARD_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes}. "
                           f"Must be one of {self.STANDARD_TIMEFRAMES}")
        
        aggregation = self._aggregations[timeframe_minutes]
        
        if start_idx < 0 or start_idx >= len(aggregation.bars):
            return []
        
        if end_idx is None:
            return aggregation.bars[start_idx:]
        else:
            return aggregation.bars[start_idx:end_idx]
    
    def get_bar_at_source_time(self, timeframe_minutes: int, 
                                source_bar_idx: int) -> Optional[Bar]:
        """
        Get the aggregated bar that contains a specific source bar.
        
        This is the key method for synchronized playback - given the current
        position in the source data, find the corresponding aggregated bar.
        
        Args:
            timeframe_minutes: Target aggregation timeframe
            source_bar_idx: Index in the original 1-minute source bars
            
        Returns:
            The aggregated bar containing this source bar, or None if incomplete
        """
        if timeframe_minutes not in self.STANDARD_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes}")
        
        if source_bar_idx < 0 or source_bar_idx >= len(self._source_bars):
            return None
        
        # Get the mapping for this timeframe
        mapping = self._source_to_agg_mapping[timeframe_minutes]
        
        if source_bar_idx not in mapping:
            return None
        
        agg_idx = mapping[source_bar_idx]
        aggregation = self._aggregations[timeframe_minutes]
        
        if agg_idx >= len(aggregation.bars):
            return None
            
        return aggregation.bars[agg_idx]
    
    def get_closed_bar_at_source_time(self, timeframe_minutes: int,
                                       source_bar_idx: int) -> Optional[Bar]:
        """
        Get the most recent CLOSED aggregated bar at a source position.
        
        Per specification: only closed bars are used for Fibonacci calculations.
        A bar is considered closed if it's complete (all constituent source bars present)
        and not the current incomplete period.
        
        Args:
            timeframe_minutes: Target aggregation timeframe  
            source_bar_idx: Index in the original 1-minute source bars
            
        Returns:
            The most recent closed bar, or None if none exist yet
        """
        if timeframe_minutes not in self.STANDARD_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes}")
        
        if source_bar_idx < 0 or source_bar_idx >= len(self._source_bars):
            return None
        
        # For 1-minute timeframe, previous bar is always closed
        if timeframe_minutes == 1:
            if source_bar_idx > 0:
                return self._source_bars[source_bar_idx - 1]
            else:
                return None
        
        # Get the current aggregated bar containing this source bar
        current_agg_bar = self.get_bar_at_source_time(timeframe_minutes, source_bar_idx)
        if current_agg_bar is None:
            return None
        
        # Check if this is the last aggregated bar (potentially incomplete)
        aggregation = self._aggregations[timeframe_minutes]
        current_agg_idx = current_agg_bar.index
        
        # If there are more aggregated bars after the current one, current is closed
        if current_agg_idx < len(aggregation.bars) - 1:
            return current_agg_bar
        
        # If this is the last aggregated bar, it might be incomplete
        # Return the previous closed bar if it exists
        if current_agg_idx > 0:
            return aggregation.bars[current_agg_idx - 1]
        
        return None
    
    @property
    def source_bar_count(self) -> int:
        """Number of source bars loaded."""
        return len(self._source_bars)
    
    def aggregated_bar_count(self, timeframe_minutes: int) -> int:
        """Number of aggregated bars for a specific timeframe."""
        if timeframe_minutes not in self.STANDARD_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes}")
        
        return len(self._aggregations[timeframe_minutes].bars)
    
    def get_aggregation_info(self) -> Dict:
        """Get summary information about all aggregations for debugging."""
        info = {
            'source_bar_count': self.source_bar_count,
            'timeframes': {}
        }
        
        for timeframe in self.STANDARD_TIMEFRAMES:
            if timeframe in self._aggregations:
                agg = self._aggregations[timeframe]
                info['timeframes'][timeframe] = {
                    'bar_count': len(agg.bars),
                    'compression_ratio': len(self._source_bars) / len(agg.bars) if agg.bars else 0,
                    'first_timestamp': agg.bars[0].timestamp if agg.bars else None,
                    'last_timestamp': agg.bars[-1].timestamp if agg.bars else None
                }
        
        return info
    
    def _append_bar(self, new_bar: Bar) -> None:
        """
        Append a new source bar and update aggregations efficiently.
        
        Args:
            new_bar: New source bar to append
        """
        # Validate timestamp ordering
        if self._source_bars and new_bar.timestamp <= self._source_bars[-1].timestamp:
            raise ValueError(f"New bar timestamp {new_bar.timestamp} must be greater than "
                           f"last bar timestamp {self._source_bars[-1].timestamp}")
        
        # Add to source bars
        new_bar.index = len(self._source_bars)
        self._source_bars.append(new_bar)
        
        # Update aggregations for each timeframe
        for timeframe in self.STANDARD_TIMEFRAMES:
            self._update_aggregation_with_new_bar(timeframe, new_bar)
    
    def _update_aggregation_with_new_bar(self, timeframe_minutes: int, new_bar: Bar) -> None:
        """Update a specific timeframe aggregation with a new source bar."""
        if timeframe_minutes == 1:
            # 1-minute is direct mapping
            self._aggregations[1].bars.append(new_bar)
            self._source_to_agg_mapping[1][new_bar.index] = new_bar.index
            return
        
        aggregation = self._aggregations[timeframe_minutes]
        source_to_agg_map = self._source_to_agg_mapping[timeframe_minutes]
        
        if not aggregation.bars:
            # First bar for this timeframe
            period_start = self._get_period_start(new_bar.timestamp, timeframe_minutes)
            agg_bar = Bar(
                timestamp=period_start,
                open=new_bar.open,
                high=new_bar.high,
                low=new_bar.low,
                close=new_bar.close,
                index=0
            )
            aggregation.bars.append(agg_bar)
            source_to_agg_map[new_bar.index] = 0
            return
        
        # Get the period this bar belongs to
        period_start = self._get_period_start(new_bar.timestamp, timeframe_minutes)
        last_agg_bar = aggregation.bars[-1]
        
        if period_start == last_agg_bar.timestamp:
            # Update existing aggregated bar
            last_agg_bar.high = max(last_agg_bar.high, new_bar.high)
            last_agg_bar.low = min(last_agg_bar.low, new_bar.low)
            last_agg_bar.close = new_bar.close
            source_to_agg_map[new_bar.index] = len(aggregation.bars) - 1
        else:
            # Create new aggregated bar
            agg_bar = Bar(
                timestamp=period_start,
                open=new_bar.open,
                high=new_bar.high,
                low=new_bar.low,
                close=new_bar.close,
                index=len(aggregation.bars)
            )
            aggregation.bars.append(agg_bar)
            source_to_agg_map[new_bar.index] = len(aggregation.bars) - 1