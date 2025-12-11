"""
Event Log Display Module

Real-time event log display component for UI integration with color coding,
formatting, and live updates.

Author: Generated for Market Simulator Project
"""

from typing import List, Optional, Dict
from datetime import datetime

from src.swing_analysis.event_detector import EventType, EventSeverity
from .event_logger import EventLogger, EventLogEntry


class EventLogDisplay:
    """Real-time event log display component for UI integration."""
    
    def __init__(self, logger: EventLogger, max_display_count: int = 20):
        """Initialize display with logger reference."""
        self.logger = logger
        self.max_display_count = max_display_count
        self.last_displayed_sequence = -1
        
        # Color scheme for different event types and severities
        self.colors = {
            # ANSI color codes for terminal output
            "major": "\033[91m",      # Bright red
            "minor": "\033[94m",      # Blue
            "completion": "\033[93m", # Yellow
            "invalidation": "\033[95m", # Magenta
            "cross_up": "\033[92m",   # Green
            "cross_down": "\033[96m", # Cyan
            "reset": "\033[0m",       # Reset
            "bold": "\033[1m",        # Bold
            "dim": "\033[2m"          # Dim
        }
        
        # Set up callback for real-time updates
        self.logger.set_update_callback(self._on_new_event)
    
    def update_display(self) -> List[EventLogEntry]:
        """Get events for current display update."""
        # Get recent events since last display
        recent_events = self.logger.get_recent_events(self.max_display_count)
        
        # Filter to only new events if tracking sequence
        if self.last_displayed_sequence >= 0:
            new_events = [
                event for event in recent_events 
                if event.sequence_number > self.last_displayed_sequence
            ]
        else:
            new_events = recent_events
        
        # Update tracking
        if recent_events:
            self.last_displayed_sequence = max(e.sequence_number for e in recent_events)
        
        return new_events
    
    def format_event_for_display(self, entry: EventLogEntry, use_colors: bool = True) -> str:
        """Format event for console or UI display."""
        # Get timestamp
        dt = datetime.fromtimestamp(entry.timestamp)
        time_str = dt.strftime("%H:%M:%S")
        
        # Get color
        color = ""
        reset = ""
        if use_colors:
            color = self.get_color_for_event(entry)
            reset = self.colors["reset"]
        
        # Format based on event type
        if entry.event_type in [EventType.COMPLETION, EventType.INVALIDATION]:
            # Major events - more detailed format
            severity_str = entry.severity.value.upper()
            status = "COMPLETED" if entry.event_type == EventType.COMPLETION else "INVALIDATED"
            
            formatted = (
                f"{color}[{time_str}] {severity_str} | {entry.scale}-Scale | "
                f"{entry.event_type.value.upper()} | "
                f"Swing {entry.swing_id[:12]}: {status} at {entry.level_name} "
                f"({entry.level_price:.2f}){reset}"
            )
        else:
            # Level crossings - simpler format
            direction = "↑" if entry.event_type == EventType.LEVEL_CROSS_UP else "↓"
            
            formatted = (
                f"{color}[{time_str}] {entry.severity.value.upper()} | {entry.scale}-Scale | "
                f"Level {entry.level_name} crossed {direction} at {entry.level_price:.2f}{reset}"
            )
        
        return formatted
    
    def format_event_for_table(self, entry: EventLogEntry) -> Dict[str, str]:
        """Format event for tabular display (e.g., in GUI)."""
        dt = datetime.fromtimestamp(entry.timestamp)
        
        return {
            "Time": dt.strftime("%H:%M:%S"),
            "Bar": str(entry.source_bar_idx),
            "Severity": entry.severity.value.upper(),
            "Scale": entry.scale,
            "Type": entry.event_type.value.replace("_", " ").title(),
            "Level": entry.level_name,
            "Price": f"{entry.level_price:.2f}",
            "Swing": entry.swing_id[:12] + "..." if len(entry.swing_id) > 12 else entry.swing_id,
            "Description": entry.description[:50] + "..." if len(entry.description) > 50 else entry.description
        }
    
    def get_color_for_event(self, entry: EventLogEntry) -> str:
        """Get appropriate color for event based on type/severity."""
        # Severity-based coloring first
        if entry.severity == EventSeverity.MAJOR:
            if entry.event_type == EventType.COMPLETION:
                return self.colors["completion"]
            elif entry.event_type == EventType.INVALIDATION:
                return self.colors["invalidation"]
            else:
                return self.colors["major"]
        
        # Event type-based coloring
        if entry.event_type == EventType.LEVEL_CROSS_UP:
            return self.colors["cross_up"]
        elif entry.event_type == EventType.LEVEL_CROSS_DOWN:
            return self.colors["cross_down"]
        else:
            return self.colors["minor"]
    
    def print_recent_events(self, count: int = 10, use_colors: bool = True) -> None:
        """Print recent events to console."""
        events = self.logger.get_recent_events(count)
        
        if not events:
            print("No events to display")
            return
        
        print(f"\nRecent Events ({len(events)}):")
        print("-" * 80)
        
        for event in events:
            formatted = self.format_event_for_display(event, use_colors)
            print(formatted)
    
    def print_event_summary(self) -> None:
        """Print summary statistics."""
        stats = self.logger.get_event_statistics()
        
        print(f"\nEvent Log Summary:")
        print(f"Session: {stats['session_id']}")
        print(f"Total Events: {stats['total_events']}")
        print(f"Unique Swings: {stats['unique_swings']}")
        
        if stats['bar_range']:
            print(f"Bar Range: {stats['bar_range'][0]} to {stats['bar_range'][1]}")
        
        print(f"\nBy Severity:")
        for severity, count in stats['by_severity'].items():
            print(f"  {severity}: {count}")
        
        print(f"\nBy Scale:")
        for scale, count in stats['by_scale'].items():
            print(f"  {scale}: {count}")
    
    def print_filtered_events(self, 
                             filter_criteria, 
                             limit: int = 20,
                             use_colors: bool = True) -> None:
        """Print events matching filter criteria."""
        events = self.logger.get_events(filter_criteria, limit)
        
        if not events:
            print("No events match the filter criteria")
            return
        
        print(f"\nFiltered Events ({len(events)}):")
        print("-" * 80)
        
        for event in events:
            formatted = self.format_event_for_display(event, use_colors)
            print(formatted)
    
    def get_live_feed(self, max_events: int = 50) -> List[str]:
        """Get formatted live feed of recent events for real-time display."""
        events = self.logger.get_recent_events(max_events)
        formatted_events = []
        
        for event in reversed(events):  # Most recent first
            formatted = self.format_event_for_display(event, use_colors=False)
            formatted_events.append(formatted)
        
        return formatted_events
    
    def export_formatted_log(self, filepath: str, use_colors: bool = False) -> bool:
        """Export formatted event log to text file."""
        try:
            events = self.logger.get_events()  # All events
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Event Log - Session {self.logger.session_id}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                
                for event in events:
                    formatted = self.format_event_for_display(event, use_colors)
                    f.write(formatted + "\n")
                
                # Add summary
                f.write("\n" + "=" * 80 + "\n")
                stats = self.logger.get_event_statistics()
                f.write(f"Total Events: {stats['total_events']}\n")
                f.write(f"By Severity: {dict(stats['by_severity'])}\n")
                f.write(f"By Scale: {dict(stats['by_scale'])}\n")
            
            return True
            
        except Exception as e:
            print(f"Error exporting formatted log: {e}")
            return False
    
    def _on_new_event(self, entry: EventLogEntry) -> None:
        """Callback for new events - can be extended for real-time UI updates."""
        # This could trigger UI updates, sound notifications, etc.
        # For now, just print to console if in verbose mode
        pass
    
    def create_event_dashboard(self) -> str:
        """Create a dashboard-style summary for display."""
        stats = self.logger.get_event_statistics()
        recent = self.logger.get_recent_events(5)
        
        dashboard = []
        dashboard.append("╔══════════════════════════════════════════════════════════════╗")
        dashboard.append(f"║                    Event Log Dashboard                      ║")
        dashboard.append("╠══════════════════════════════════════════════════════════════╣")
        dashboard.append(f"║ Session: {stats['session_id']:<46} ║")
        dashboard.append(f"║ Total Events: {stats['total_events']:<43} ║")
        dashboard.append(f"║ Unique Swings: {stats['unique_swings']:<42} ║")
        dashboard.append("╠══════════════════════════════════════════════════════════════╣")
        dashboard.append("║ By Severity:                                               ║")
        
        for severity, count in stats['by_severity'].items():
            dashboard.append(f"║   {severity}: {count:<51} ║")
        
        dashboard.append("╠══════════════════════════════════════════════════════════════╣")
        dashboard.append("║ Recent Events:                                             ║")
        
        for event in recent[-3:]:  # Last 3 events
            dt = datetime.fromtimestamp(event.timestamp)
            time_str = dt.strftime("%H:%M:%S")
            desc = event.description[:45] + "..." if len(event.description) > 45 else event.description
            dashboard.append(f"║ [{time_str}] {desc:<45} ║")
        
        dashboard.append("╚══════════════════════════════════════════════════════════════╝")
        
        return "\n".join(dashboard)


class EventLogFilter:
    """Helper class for creating common display filters."""
    
    @staticmethod
    def last_n_minutes(minutes: int, current_timestamp: int):
        """Filter for events in last N minutes."""
        from .filters import LogFilter
        start_time = current_timestamp - (minutes * 60)
        return LogFilter(start_timestamp=start_time)
    
    @staticmethod
    def major_events_only():
        """Filter for major events only."""
        from .filters import LogFilter
        return LogFilter(severities={EventSeverity.MAJOR})
    
    @staticmethod
    def specific_scale(scale: str):
        """Filter for specific scale."""
        from .filters import LogFilter
        return LogFilter(scales={scale})
    
    @staticmethod
    def critical_levels():
        """Filter for critical level events."""
        from .filters import LogFilter
        return LogFilter(level_names={"-0.1", "2.0"})