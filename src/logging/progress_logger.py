"""
Progress Logger Module

Provides periodic progress reporting and high-signal event logging
for the visualization harness during playback.

Key Features:
- Periodic progress reports at configurable intervals
- Immediate logging of major events (completions, invalidations)
- Event counts and summaries between reports
- Timestamp formatting for human readability

Author: Generated for Market Simulator Project
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.logging.event_logger import EventLogger, EventLogEntry


class ProgressLogger:
    """
    Periodic progress and high-signal event logging.

    Provides CLI feedback during long-running validation sessions
    without overwhelming the console with per-bar logging.
    """

    def __init__(self,
                 event_logger: Optional[EventLogger] = None,
                 interval_bars: int = 100,
                 log_major_events: bool = True):
        """
        Initialize progress logger.

        Args:
            event_logger: Optional EventLogger to hook into for real-time events
            interval_bars: Number of bars between progress reports (default: 100)
            log_major_events: Whether to immediately log major events (default: True)
        """
        self.event_logger = event_logger
        self.interval_bars = interval_bars
        self.log_major_events = log_major_events

        # Progress tracking
        self.last_report_bar = 0
        self.events_since_last_report: List[StructuralEvent] = []
        self.total_events_logged = 0

        # Statistics tracking
        self.event_counts: Dict[str, int] = defaultdict(int)
        self.major_event_count = 0
        self.minor_event_count = 0

        # Logger
        self.logger = logging.getLogger(__name__)

        # Register callback if event logger provided
        if self.event_logger:
            self.event_logger.set_update_callback(self._on_event)

    def _on_event(self, entry: EventLogEntry) -> None:
        """
        Handle real-time event notification from EventLogger.

        Args:
            entry: EventLogEntry from the event logger
        """
        # Track event
        self.total_events_logged += 1
        self.event_counts[entry.event_type.value] += 1

        if entry.severity == EventSeverity.MAJOR:
            self.major_event_count += 1
        else:
            self.minor_event_count += 1

        # Log major events immediately
        if self.log_major_events and entry.severity == EventSeverity.MAJOR:
            self._log_major_event(entry)

    def on_event(self, event: StructuralEvent) -> None:
        """
        Handle direct event notification (alternative to EventLogger callback).

        Args:
            event: StructuralEvent to process
        """
        self.events_since_last_report.append(event)
        self.event_counts[event.event_type.value] += 1

        if event.severity == EventSeverity.MAJOR:
            self.major_event_count += 1
            if self.log_major_events:
                self._log_major_event_direct(event)
        else:
            self.minor_event_count += 1

    def check_progress(self,
                       current_bar_idx: int,
                       total_bars: int,
                       timestamp: float) -> bool:
        """
        Check if progress report is due and emit if so.

        Args:
            current_bar_idx: Current bar index in playback
            total_bars: Total number of bars in dataset
            timestamp: Unix timestamp of current bar

        Returns:
            True if a progress report was emitted, False otherwise
        """
        if current_bar_idx - self.last_report_bar >= self.interval_bars:
            self._emit_progress_report(current_bar_idx, total_bars, timestamp)
            self.last_report_bar = current_bar_idx
            self.events_since_last_report.clear()
            return True
        return False

    def _emit_progress_report(self,
                              bar_idx: int,
                              total: int,
                              timestamp: float) -> None:
        """
        Emit periodic progress report to log.

        Args:
            bar_idx: Current bar index
            total: Total bars in dataset
            timestamp: Unix timestamp of current bar
        """
        # Format timestamp
        ts_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
        pct = (bar_idx / max(1, total)) * 100

        # Count events by type since last report
        event_counts = defaultdict(int)
        for event in self.events_since_last_report:
            event_counts[event.event_type.value] += 1

        # Build counts string
        if event_counts:
            counts_str = ", ".join(f"{k}:{v}" for k, v in event_counts.items())
        else:
            counts_str = "none"

        # Log progress
        self.logger.info(
            f"Progress: bar {bar_idx}/{total} ({pct:.1f}%) | "
            f"timestamp: {ts_str} | events: {counts_str}"
        )

    def _log_major_event(self, entry: EventLogEntry) -> None:
        """
        Log major event immediately with full context.

        Args:
            entry: EventLogEntry from event logger
        """
        # Format swing ID (first 8 chars for brevity)
        swing_id_short = entry.swing_id[:8] if entry.swing_id else "unknown"

        self.logger.info(
            f"MAJOR EVENT [{entry.scale}]: {entry.event_type.value} "
            f"at bar {entry.source_bar_idx} - "
            f"crossed {entry.level_name} on swing {swing_id_short} "
            f"@ {entry.level_price:.2f}"
        )

    def _log_major_event_direct(self, event: StructuralEvent) -> None:
        """
        Log major event directly from StructuralEvent.

        Args:
            event: StructuralEvent to log
        """
        # Format swing ID (first 8 chars for brevity)
        swing_id_short = event.swing_id[:8] if event.swing_id else "unknown"

        self.logger.info(
            f"MAJOR EVENT [{event.scale}]: {event.event_type.value} "
            f"at bar {event.source_bar_idx} - "
            f"crossed {event.level_name} on swing {swing_id_short} "
            f"@ {event.level_price:.2f}"
        )

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for current session.

        Returns:
            Dictionary with event counts and statistics
        """
        return {
            'total_events': sum(self.event_counts.values()),
            'major_events': self.major_event_count,
            'minor_events': self.minor_event_count,
            'by_type': dict(self.event_counts),
            'last_report_bar': self.last_report_bar,
        }

    def reset(self) -> None:
        """Reset all counters and tracking state."""
        self.last_report_bar = 0
        self.events_since_last_report.clear()
        self.event_counts.clear()
        self.major_event_count = 0
        self.minor_event_count = 0
        self.total_events_logged = 0
