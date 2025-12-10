"""
Event Logging Filters Module

Provides filtering utilities and criteria classes for event log queries,
including time-based, content-based, and numerical filters.

Author: Generated for Market Simulator Project
"""

from dataclasses import dataclass
from typing import Optional, Set, List
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.analysis.event_detector import EventType, EventSeverity


@dataclass
class LogFilter:
    """Filtering criteria for event log queries."""
    
    # Time filters
    start_bar_idx: Optional[int] = None
    end_bar_idx: Optional[int] = None
    start_timestamp: Optional[int] = None
    end_timestamp: Optional[int] = None
    
    # Event filters
    event_types: Optional[Set[EventType]] = None
    severities: Optional[Set[EventSeverity]] = None
    scales: Optional[Set[str]] = None
    
    # Content filters
    swing_ids: Optional[Set[str]] = None
    tags: Optional[Set[str]] = None
    description_contains: Optional[str] = None
    
    # Numerical filters
    min_level_price: Optional[float] = None
    max_level_price: Optional[float] = None
    level_names: Optional[Set[str]] = None
    
    def matches_time_range(self, bar_idx: int, timestamp: int) -> bool:
        """Check if event matches time range filters."""
        if self.start_bar_idx is not None and bar_idx < self.start_bar_idx:
            return False
        if self.end_bar_idx is not None and bar_idx > self.end_bar_idx:
            return False
        if self.start_timestamp is not None and timestamp < self.start_timestamp:
            return False
        if self.end_timestamp is not None and timestamp > self.end_timestamp:
            return False
        return True
    
    def matches_event_criteria(self, event_type: EventType, severity: EventSeverity, scale: str) -> bool:
        """Check if event matches basic event criteria."""
        if self.event_types is not None and event_type not in self.event_types:
            return False
        if self.severities is not None and severity not in self.severities:
            return False
        if self.scales is not None and scale not in self.scales:
            return False
        return True
    
    def matches_content(self, swing_id: str, tags: Set[str], description: str) -> bool:
        """Check if event matches content filters."""
        if self.swing_ids is not None and swing_id not in self.swing_ids:
            return False
        if self.tags is not None and not self.tags.intersection(tags):
            return False
        if self.description_contains is not None and self.description_contains.lower() not in description.lower():
            return False
        return True
    
    def matches_numerical(self, level_price: float, level_name: str) -> bool:
        """Check if event matches numerical filters."""
        if self.min_level_price is not None and level_price < self.min_level_price:
            return False
        if self.max_level_price is not None and level_price > self.max_level_price:
            return False
        if self.level_names is not None and level_name not in self.level_names:
            return False
        return True
    
    @classmethod
    def create_for_scale(cls, scale: str) -> 'LogFilter':
        """Create filter for specific scale."""
        return cls(scales={scale})
    
    @classmethod
    def create_for_major_events(cls) -> 'LogFilter':
        """Create filter for major events only."""
        return cls(severities={EventSeverity.MAJOR})
    
    @classmethod
    def create_for_time_range(cls, start_bar: int, end_bar: int) -> 'LogFilter':
        """Create filter for specific time range."""
        return cls(start_bar_idx=start_bar, end_bar_idx=end_bar)
    
    @classmethod
    def create_for_swing(cls, swing_id: str) -> 'LogFilter':
        """Create filter for specific swing."""
        return cls(swing_ids={swing_id})


class FilterBuilder:
    """Builder class for constructing complex log filters."""
    
    def __init__(self):
        self.filter = LogFilter()
    
    def time_range(self, start_bar: Optional[int] = None, end_bar: Optional[int] = None) -> 'FilterBuilder':
        """Set time range filter."""
        self.filter.start_bar_idx = start_bar
        self.filter.end_bar_idx = end_bar
        return self
    
    def timestamp_range(self, start_ts: Optional[int] = None, end_ts: Optional[int] = None) -> 'FilterBuilder':
        """Set timestamp range filter."""
        self.filter.start_timestamp = start_ts
        self.filter.end_timestamp = end_ts
        return self
    
    def event_types(self, *types: EventType) -> 'FilterBuilder':
        """Set event type filter."""
        self.filter.event_types = set(types)
        return self
    
    def severities(self, *severities: EventSeverity) -> 'FilterBuilder':
        """Set severity filter."""
        self.filter.severities = set(severities)
        return self
    
    def scales(self, *scales: str) -> 'FilterBuilder':
        """Set scale filter."""
        self.filter.scales = set(scales)
        return self
    
    def swing_ids(self, *swing_ids: str) -> 'FilterBuilder':
        """Set swing ID filter."""
        self.filter.swing_ids = set(swing_ids)
        return self
    
    def tags(self, *tags: str) -> 'FilterBuilder':
        """Set tag filter."""
        self.filter.tags = set(tags)
        return self
    
    def description_contains(self, text: str) -> 'FilterBuilder':
        """Set description content filter."""
        self.filter.description_contains = text
        return self
    
    def level_price_range(self, min_price: Optional[float] = None, max_price: Optional[float] = None) -> 'FilterBuilder':
        """Set level price range filter."""
        self.filter.min_level_price = min_price
        self.filter.max_level_price = max_price
        return self
    
    def level_names(self, *names: str) -> 'FilterBuilder':
        """Set level name filter."""
        self.filter.level_names = set(names)
        return self
    
    def build(self) -> LogFilter:
        """Build the final filter."""
        return self.filter


def apply_filters(entries: List, log_filter: LogFilter) -> List:
    """
    Apply log filter to a list of event log entries.
    
    Args:
        entries: List of EventLogEntry objects
        log_filter: Filter to apply
        
    Returns:
        Filtered list of entries
    """
    if not log_filter:
        return entries
    
    filtered = []
    
    for entry in entries:
        # Time range check
        if not log_filter.matches_time_range(entry.source_bar_idx, entry.timestamp):
            continue
        
        # Event criteria check
        if not log_filter.matches_event_criteria(entry.event_type, entry.severity, entry.scale):
            continue
        
        # Content check
        if not log_filter.matches_content(entry.swing_id, entry.tags, entry.description):
            continue
        
        # Numerical check
        if not log_filter.matches_numerical(entry.level_price, entry.level_name):
            continue
        
        filtered.append(entry)
    
    return filtered


def quick_filters():
    """Provide common quick filter presets."""
    return {
        "major_events": LogFilter.create_for_major_events(),
        "completions": LogFilter(event_types={EventType.COMPLETION}),
        "invalidations": LogFilter(event_types={EventType.INVALIDATION}),
        "level_crossings": LogFilter(event_types={EventType.LEVEL_CROSS_UP, EventType.LEVEL_CROSS_DOWN}),
        "s_scale": LogFilter.create_for_scale("S"),
        "m_scale": LogFilter.create_for_scale("M"),
        "l_scale": LogFilter.create_for_scale("L"),
        "xl_scale": LogFilter.create_for_scale("XL"),
        "critical_levels": LogFilter(level_names={"-0.1", "2.0"}),
        "decision_zone": LogFilter(level_names={"1.382", "1.5", "1.618"}),
    }