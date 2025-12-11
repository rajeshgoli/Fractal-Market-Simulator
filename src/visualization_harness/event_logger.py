"""
Event Logger Module

Comprehensive event logging system that captures, stores, and provides
filtered access to all structural events with export capabilities.

Key Features:
- Rich event logging with market context
- Flexible filtering and search capabilities
- Export to CSV/JSON with configurable filters
- Real-time display integration
- Auto-tagging and manual annotation support

Author: Generated for Market Simulator Project
"""

import logging
import uuid
import json
import csv
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Callable, Set, Any
from datetime import datetime

from src.swing_analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.swing_analysis.swing_state_manager import ActiveSwing
from .filters import LogFilter, apply_filters


@dataclass
class EventLogEntry:
    """Enhanced event log entry with contextual information."""
    
    # Core event data (from StructuralEvent)
    event_id: str                       # Unique identifier for this log entry
    event_type: EventType
    severity: EventSeverity
    timestamp: int                      # Market timestamp
    source_bar_idx: int
    level_name: str
    level_price: float
    swing_id: str
    scale: str
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    description: str
    
    # Additional context
    log_timestamp: datetime = field(default_factory=datetime.now)  # When logged
    session_id: str = ""                # Playback session identifier
    sequence_number: int = 0            # Order within session
    
    # Market context
    swing_age_bars: Optional[int] = None          # How long swing was active
    price_distance_pct: Optional[float] = None   # Distance from swing extreme
    market_volatility: Optional[float] = None    # Recent price volatility measure
    
    # Derived insights
    tags: Set[str] = field(default_factory=set)  # User or auto tags
    notes: str = ""                               # User annotations
    
    @classmethod
    def from_structural_event(cls, 
                             event: StructuralEvent, 
                             session_id: str = "",
                             sequence_number: int = 0,
                             market_context: Optional[Dict] = None) -> 'EventLogEntry':
        """Create EventLogEntry from StructuralEvent."""
        
        entry = cls(
            event_id=str(uuid.uuid4()),
            event_type=event.event_type,
            severity=event.severity,
            timestamp=event.timestamp,
            source_bar_idx=event.source_bar_idx,
            level_name=event.level_name,
            level_price=event.level_price,
            swing_id=event.swing_id,
            scale=event.scale,
            bar_open=event.bar_open,
            bar_high=event.bar_high,
            bar_low=event.bar_low,
            bar_close=event.bar_close,
            description=event.description,
            session_id=session_id,
            sequence_number=sequence_number
        )
        
        # Add market context if provided
        if market_context:
            entry.swing_age_bars = market_context.get("swing_age_bars")
            entry.price_distance_pct = market_context.get("price_distance_pct")
            entry.market_volatility = market_context.get("market_volatility")
        
        return entry


class EventLogger:
    """Comprehensive event logging with filtering, search, and export capabilities."""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize event logger.
        
        Args:
            session_id: Unique identifier for this playback session
        """
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.events: List[EventLogEntry] = []
        self.sequence_counter = 0
        
        # Indexing for fast lookups
        self._events_by_id: Dict[str, EventLogEntry] = {}
        self._events_by_swing: Dict[str, List[EventLogEntry]] = defaultdict(list)
        self._events_by_scale: Dict[str, List[EventLogEntry]] = defaultdict(list)
        
        # Performance tracking
        self._swing_start_times: Dict[str, int] = {}  # swing_id -> first bar seen
        
        # Callbacks
        self._update_callback: Optional[Callable[[EventLogEntry], None]] = None
        
        logging.info(f"EventLogger initialized for session {self.session_id}")
    
    def log_event(self, 
                  event: StructuralEvent,
                  market_context: Optional[Dict] = None) -> str:
        """
        Log a structural event with additional context.
        
        Args:
            event: Structural event from EventDetector
            market_context: Additional market state information
            
        Returns:
            Unique event_id for the logged entry
        """
        # Calculate enhanced market context
        enhanced_context = self._calculate_market_context(event, market_context)
        
        # Create log entry
        entry = EventLogEntry.from_structural_event(
            event=event,
            session_id=self.session_id,
            sequence_number=self.sequence_counter,
            market_context=enhanced_context
        )
        
        # Generate automatic tags
        entry.tags = self._generate_auto_tags(entry)
        
        # Add to storage
        self.events.append(entry)
        self.sequence_counter += 1
        
        # Update indexes
        self._events_by_id[entry.event_id] = entry
        self._events_by_swing[entry.swing_id].append(entry)
        self._events_by_scale[entry.scale].append(entry)
        
        # Track swing start times
        if entry.swing_id not in self._swing_start_times:
            self._swing_start_times[entry.swing_id] = entry.source_bar_idx
        
        # Trigger callback if set
        if self._update_callback:
            try:
                self._update_callback(entry)
            except Exception as e:
                logging.warning(f"Event callback failed: {e}")
        
        logging.debug(f"Logged event {entry.event_id}: {entry.description}")
        return entry.event_id
    
    def log_events_batch(self, 
                        events: List[StructuralEvent],
                        market_context: Optional[Dict] = None) -> List[str]:
        """Log multiple events in a single batch operation."""
        event_ids = []
        
        for event in events:
            event_id = self.log_event(event, market_context)
            event_ids.append(event_id)
        
        return event_ids
    
    def get_events(self, 
                   filter_criteria: Optional[LogFilter] = None,
                   limit: Optional[int] = None,
                   sort_by: str = "sequence_number") -> List[EventLogEntry]:
        """
        Retrieve events matching filter criteria.
        
        Args:
            filter_criteria: Filtering options (None = all events)
            limit: Maximum number of events to return
            sort_by: Sort field ("sequence_number", "timestamp", "severity")
            
        Returns:
            List of matching log entries
        """
        # Start with all events
        filtered_events = self.events.copy()
        
        # Apply filters
        if filter_criteria:
            filtered_events = apply_filters(filtered_events, filter_criteria)
        
        # Sort events
        if sort_by == "sequence_number":
            filtered_events.sort(key=lambda e: e.sequence_number)
        elif sort_by == "timestamp":
            filtered_events.sort(key=lambda e: e.timestamp)
        elif sort_by == "severity":
            # Sort by severity (MAJOR first)
            severity_order = {EventSeverity.MAJOR: 0, EventSeverity.MINOR: 1}
            filtered_events.sort(key=lambda e: (severity_order.get(e.severity, 2), e.sequence_number))
        
        # Apply limit
        if limit:
            filtered_events = filtered_events[:limit]
        
        return filtered_events
    
    def get_event_by_id(self, event_id: str) -> Optional[EventLogEntry]:
        """Retrieve specific event by ID."""
        return self._events_by_id.get(event_id)
    
    def get_event_statistics(self) -> Dict:
        """
        Get summary statistics about logged events.
        
        Returns:
            Dictionary with counts by type, severity, scale, etc.
        """
        stats = {
            "total_events": len(self.events),
            "session_id": self.session_id,
            "by_type": defaultdict(int),
            "by_severity": defaultdict(int),
            "by_scale": defaultdict(int),
            "by_level": defaultdict(int),
            "unique_swings": len(self._events_by_swing),
            "bar_range": None,
            "time_range": None
        }
        
        if self.events:
            # Calculate counts
            for event in self.events:
                stats["by_type"][event.event_type.value] += 1
                stats["by_severity"][event.severity.value] += 1
                stats["by_scale"][event.scale] += 1
                stats["by_level"][event.level_name] += 1
            
            # Calculate ranges
            stats["bar_range"] = (
                min(e.source_bar_idx for e in self.events),
                max(e.source_bar_idx for e in self.events)
            )
            stats["time_range"] = (
                min(e.timestamp for e in self.events),
                max(e.timestamp for e in self.events)
            )
        
        return stats
    
    def get_events_for_swing(self, swing_id: str) -> List[EventLogEntry]:
        """Get all events related to a specific swing."""
        return self._events_by_swing.get(swing_id, []).copy()
    
    def get_recent_events(self, count: int = 10) -> List[EventLogEntry]:
        """Get most recent N events for real-time display."""
        return self.events[-count:] if len(self.events) >= count else self.events.copy()
    
    def search_events(self, query: str) -> List[EventLogEntry]:
        """
        Full-text search across event descriptions and notes.
        
        Args:
            query: Search string (supports basic operators)
            
        Returns:
            Matching events sorted by relevance
        """
        query_lower = query.lower()
        matches = []
        
        for event in self.events:
            relevance = 0
            
            # Search in description (higher weight)
            if query_lower in event.description.lower():
                relevance += 3
            
            # Search in notes
            if query_lower in event.notes.lower():
                relevance += 2
            
            # Search in swing ID
            if query_lower in event.swing_id.lower():
                relevance += 2
            
            # Search in tags
            if any(query_lower in tag.lower() for tag in event.tags):
                relevance += 1
            
            if relevance > 0:
                matches.append((event, relevance))
        
        # Sort by relevance, then by sequence
        matches.sort(key=lambda x: (-x[1], x[0].sequence_number))
        
        return [match[0] for match in matches]
    
    def add_tag(self, event_id: str, tag: str) -> bool:
        """Add tag to specific event."""
        event = self.get_event_by_id(event_id)
        if event:
            event.tags.add(tag)
            return True
        return False
    
    def remove_tag(self, event_id: str, tag: str) -> bool:
        """Remove tag from specific event."""
        event = self.get_event_by_id(event_id)
        if event and tag in event.tags:
            event.tags.remove(tag)
            return True
        return False
    
    def add_note(self, event_id: str, note: str) -> bool:
        """Add or update note for specific event."""
        event = self.get_event_by_id(event_id)
        if event:
            event.notes = note
            return True
        return False
    
    def export_to_csv(self, 
                     filepath: str,
                     filter_criteria: Optional[LogFilter] = None) -> bool:
        """Export filtered events to CSV file."""
        try:
            events = self.get_events(filter_criteria)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                if not events:
                    return True
                
                # Define CSV headers
                headers = [
                    'event_id', 'timestamp', 'bar_idx', 'event_type', 'severity', 
                    'scale', 'swing_id', 'level_name', 'level_price', 'bar_close',
                    'description', 'swing_age_bars', 'price_distance_pct', 'tags', 'notes'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                
                for event in events:
                    row = {
                        'event_id': event.event_id,
                        'timestamp': event.timestamp,
                        'bar_idx': event.source_bar_idx,
                        'event_type': event.event_type.value,
                        'severity': event.severity.value,
                        'scale': event.scale,
                        'swing_id': event.swing_id,
                        'level_name': event.level_name,
                        'level_price': event.level_price,
                        'bar_close': event.bar_close,
                        'description': event.description,
                        'swing_age_bars': event.swing_age_bars,
                        'price_distance_pct': event.price_distance_pct,
                        'tags': ','.join(event.tags),
                        'notes': event.notes
                    }
                    writer.writerow(row)
            
            logging.info(f"Exported {len(events)} events to {filepath}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to export CSV: {e}")
            return False
    
    def export_to_json(self, 
                      filepath: str,
                      filter_criteria: Optional[LogFilter] = None) -> bool:
        """Export filtered events to JSON file."""
        try:
            events = self.get_events(filter_criteria)
            stats = self.get_event_statistics()
            
            export_data = {
                "session_id": self.session_id,
                "export_timestamp": datetime.now().isoformat(),
                "total_events": len(events),
                "filter_applied": asdict(filter_criteria) if filter_criteria else None,
                "statistics": stats,
                "events": []
            }
            
            # Convert events to dict format
            for event in events:
                event_dict = asdict(event)
                # Convert set to list for JSON serialization
                event_dict['tags'] = list(event.tags)
                # Convert datetime to ISO string
                event_dict['log_timestamp'] = event.log_timestamp.isoformat()
                # Convert enums to strings
                event_dict['event_type'] = event.event_type.value
                event_dict['severity'] = event.severity.value
                export_data["events"].append(event_dict)
            
            with open(filepath, 'w', encoding='utf-8') as jsonfile:
                json.dump(export_data, jsonfile, indent=2, ensure_ascii=False)
            
            logging.info(f"Exported {len(events)} events to {filepath}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to export JSON: {e}")
            return False
    
    def export_summary_report(self, filepath: str) -> bool:
        """Export summary statistics and insights to text report."""
        try:
            stats = self.get_event_statistics()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Event Log Summary Report\n")
                f.write(f"========================\n\n")
                f.write(f"Session: {self.session_id}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write(f"Overall Statistics:\n")
                f.write(f"- Total Events: {stats['total_events']}\n")
                f.write(f"- Unique Swings: {stats['unique_swings']}\n")
                
                if stats['bar_range']:
                    f.write(f"- Bar Range: {stats['bar_range'][0]} to {stats['bar_range'][1]}\n")
                
                f.write(f"\nBy Event Type:\n")
                for event_type, count in stats['by_type'].items():
                    f.write(f"- {event_type}: {count}\n")
                
                f.write(f"\nBy Severity:\n")
                for severity, count in stats['by_severity'].items():
                    f.write(f"- {severity}: {count}\n")
                
                f.write(f"\nBy Scale:\n")
                for scale, count in stats['by_scale'].items():
                    f.write(f"- {scale}: {count}\n")
                
                f.write(f"\nTop Level Names:\n")
                sorted_levels = sorted(stats['by_level'].items(), key=lambda x: x[1], reverse=True)
                for level, count in sorted_levels[:10]:
                    f.write(f"- {level}: {count}\n")
            
            logging.info(f"Exported summary report to {filepath}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to export summary: {e}")
            return False
    
    def clear_session(self) -> None:
        """Clear all events for current session."""
        count = len(self.events)
        self.events.clear()
        self.sequence_counter = 0
        self._events_by_id.clear()
        self._events_by_swing.clear()
        self._events_by_scale.clear()
        self._swing_start_times.clear()
        
        logging.info(f"Cleared {count} events from session")
    
    def set_update_callback(self, 
                           callback: Callable[[EventLogEntry], None]) -> None:
        """Set callback for real-time event notifications."""
        self._update_callback = callback
    
    def _calculate_market_context(self, 
                                 event: StructuralEvent,
                                 additional_context: Optional[Dict]) -> Dict:
        """Calculate additional market context for event."""
        context = {
            "swing_age_bars": None,      # Bars since swing became active
            "price_distance_pct": None,  # % distance from swing extreme
            "market_volatility": None,   # Recent volatility measure
            "scale_activity": {},        # Activity level per scale
            "concurrent_events": 0       # Other events at same bar
        }
        
        # Calculate swing age if swing_id available
        if event.swing_id in self._swing_start_times:
            context["swing_age_bars"] = event.source_bar_idx - self._swing_start_times[event.swing_id]
        
        # Calculate price distance from swing extreme
        if additional_context and "active_swings" in additional_context:
            for swing in additional_context["active_swings"]:
                if swing.swing_id == event.swing_id:
                    swing_range = abs(swing.high_price - swing.low_price)
                    if swing_range > 0:
                        if swing.is_bull:
                            distance = abs(event.bar_close - swing.low_price)
                        else:
                            distance = abs(event.bar_close - swing.high_price)
                        context["price_distance_pct"] = (distance / swing_range) * 100
                    break
        
        # Add additional context if provided
        if additional_context:
            context.update(additional_context)
        
        return context
    
    def _generate_auto_tags(self, entry: EventLogEntry) -> Set[str]:
        """Generate automatic tags based on event characteristics."""
        tags = set()
        
        # Severity tags
        tags.add(f"severity-{entry.severity.value}")
        
        # Event type tags  
        tags.add(f"type-{entry.event_type.value}")
        
        # Scale tags
        tags.add(f"scale-{entry.scale}")
        
        # Level tags
        if entry.level_name in ["-0.1", "2.0"]:
            tags.add("critical-level")
        elif entry.level_name in ["1.382", "1.5", "1.618"]:
            tags.add("decision-zone")
        elif entry.level_name in ["0.382", "0.5", "0.618"]:
            tags.add("retracement")
        elif entry.level_name in ["0", "1.0"]:
            tags.add("key-level")
        
        # Context-based tags
        if entry.swing_age_bars:
            if entry.swing_age_bars < 10:
                tags.add("new-swing")
            elif entry.swing_age_bars > 100:
                tags.add("mature-swing")
        
        if entry.price_distance_pct:
            if entry.price_distance_pct > 150:
                tags.add("extended-move")
            elif entry.price_distance_pct < 20:
                tags.add("early-stage")
        
        # Time-based tags (could add session time, market hours, etc.)
        tags.add(f"session-{entry.session_id}")
        
        return tags