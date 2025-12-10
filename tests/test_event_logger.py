"""
Test Suite for Event Logger

Tests the comprehensive event logging system including filtering,
search, export capabilities, and real-time display integration.

Author: Generated for Market Simulator Project
"""

import pytest
import json
import csv
import tempfile
import os
from datetime import datetime
from unittest.mock import Mock, patch

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.logging.event_logger import EventLogger, EventLogEntry
from src.logging.filters import LogFilter, FilterBuilder, apply_filters
from src.logging.display import EventLogDisplay
from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.analysis.swing_state_manager import ActiveSwing


class TestEventLogger:
    """Test suite for EventLogger class."""

    @pytest.fixture
    def logger(self):
        """Create test event logger."""
        return EventLogger(session_id="test_session")

    @pytest.fixture
    def sample_events(self):
        """Create sample structural events."""
        return [
            StructuralEvent(
                event_type=EventType.LEVEL_CROSS_UP,
                severity=EventSeverity.MINOR,
                timestamp=1672531800,
                source_bar_idx=50,
                level_name="0.618",
                level_price=4107.4,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4106.0,
                bar_high=4109.0,
                bar_low=4105.5,
                bar_close=4108.0,
                description="Level 0.618 crossed upward"
            ),
            StructuralEvent(
                event_type=EventType.COMPLETION,
                severity=EventSeverity.MAJOR,
                timestamp=1672532400,
                source_bar_idx=75,
                level_name="2.0",
                level_price=4250.0,
                swing_id="test-swing-2",
                scale="L",
                bar_open=4248.0,
                bar_high=4252.0,
                bar_low=4247.0,
                bar_close=4251.0,
                description="Bull swing completed at 2x extension"
            ),
            StructuralEvent(
                event_type=EventType.INVALIDATION,
                severity=EventSeverity.MAJOR,
                timestamp=1672533000,
                source_bar_idx=100,
                level_name="-0.1",
                level_price=4090.0,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4092.0,
                bar_high=4093.0,
                bar_low=4089.0,
                bar_close=4089.5,
                description="Bull swing invalidated - close below -0.1"
            )
        ]

    @pytest.fixture
    def sample_swings(self):
        """Create sample active swings for context."""
        return [
            ActiveSwing(
                swing_id="test-swing-1",
                scale="S",
                high_price=4110.0,
                low_price=4090.0,
                high_timestamp=1672530000,
                low_timestamp=1672529000,
                is_bull=True,
                state="active",
                levels={"0": 4090.0, "0.618": 4107.4, "1.0": 4110.0, "2.0": 4130.0}
            )
        ]

    def test_initialization(self, logger):
        """Test logger initialization."""
        assert logger.session_id == "test_session"
        assert len(logger.events) == 0
        assert logger.sequence_counter == 0

    def test_log_single_event(self, logger, sample_events):
        """Test logging a single event."""
        event = sample_events[0]
        event_id = logger.log_event(event)
        
        assert len(logger.events) == 1
        assert logger.sequence_counter == 1
        assert event_id in logger._events_by_id
        
        logged_entry = logger.events[0]
        assert logged_entry.event_type == event.event_type
        assert logged_entry.severity == event.severity
        assert logged_entry.swing_id == event.swing_id
        assert len(logged_entry.tags) > 0  # Should have auto-generated tags

    def test_log_events_batch(self, logger, sample_events):
        """Test batch logging of events."""
        event_ids = logger.log_events_batch(sample_events[:2])
        
        assert len(logger.events) == 2
        assert len(event_ids) == 2
        assert logger.sequence_counter == 2
        
        # Verify order
        assert logger.events[0].sequence_number == 0
        assert logger.events[1].sequence_number == 1

    def test_get_events_no_filter(self, logger, sample_events):
        """Test retrieving all events without filter."""
        logger.log_events_batch(sample_events)
        
        events = logger.get_events()
        assert len(events) == 3
        
        # Default sort by sequence number
        assert events[0].sequence_number < events[1].sequence_number < events[2].sequence_number

    def test_get_events_with_limit(self, logger, sample_events):
        """Test retrieving events with limit."""
        logger.log_events_batch(sample_events)
        
        events = logger.get_events(limit=2)
        assert len(events) == 2

    def test_get_events_sorted_by_severity(self, logger, sample_events):
        """Test retrieving events sorted by severity."""
        logger.log_events_batch(sample_events)
        
        events = logger.get_events(sort_by="severity")
        
        # MAJOR events should come first
        assert events[0].severity == EventSeverity.MAJOR
        assert events[1].severity == EventSeverity.MAJOR
        assert events[2].severity == EventSeverity.MINOR

    def test_get_event_by_id(self, logger, sample_events):
        """Test retrieving specific event by ID."""
        event_id = logger.log_event(sample_events[0])
        
        retrieved = logger.get_event_by_id(event_id)
        assert retrieved is not None
        assert retrieved.event_id == event_id
        
        # Test non-existent ID
        assert logger.get_event_by_id("non-existent") is None

    def test_get_events_for_swing(self, logger, sample_events):
        """Test retrieving events for specific swing."""
        logger.log_events_batch(sample_events)
        
        swing_1_events = logger.get_events_for_swing("test-swing-1")
        assert len(swing_1_events) == 2  # Cross up and invalidation
        
        swing_2_events = logger.get_events_for_swing("test-swing-2")
        assert len(swing_2_events) == 1  # Completion only

    def test_get_recent_events(self, logger, sample_events):
        """Test retrieving recent events."""
        logger.log_events_batch(sample_events)
        
        recent = logger.get_recent_events(2)
        assert len(recent) == 2
        
        # Should be the last 2 events
        assert recent[0].sequence_number == 1
        assert recent[1].sequence_number == 2

    def test_search_events(self, logger, sample_events):
        """Test full-text search of events."""
        logger.log_events_batch(sample_events)
        
        # Search in description
        results = logger.search_events("crossed")
        assert len(results) == 1
        assert results[0].description.lower().find("crossed") >= 0
        
        # Search in swing ID
        results = logger.search_events("swing-1")
        assert len(results) == 2  # Two events for swing-1

    def test_add_remove_tags(self, logger, sample_events):
        """Test adding and removing tags."""
        event_id = logger.log_event(sample_events[0])
        
        # Add tag
        result = logger.add_tag(event_id, "custom-tag")
        assert result is True
        
        event = logger.get_event_by_id(event_id)
        assert "custom-tag" in event.tags
        
        # Remove tag
        result = logger.remove_tag(event_id, "custom-tag")
        assert result is True
        assert "custom-tag" not in event.tags
        
        # Test non-existent event
        assert logger.add_tag("non-existent", "tag") is False

    def test_add_notes(self, logger, sample_events):
        """Test adding notes to events."""
        event_id = logger.log_event(sample_events[0])
        
        result = logger.add_note(event_id, "Custom note")
        assert result is True
        
        event = logger.get_event_by_id(event_id)
        assert event.notes == "Custom note"
        
        # Test non-existent event
        assert logger.add_note("non-existent", "note") is False

    def test_event_statistics(self, logger, sample_events):
        """Test event statistics calculation."""
        logger.log_events_batch(sample_events)
        
        stats = logger.get_event_statistics()
        
        assert stats["total_events"] == 3
        assert stats["by_severity"]["major"] == 2
        assert stats["by_severity"]["minor"] == 1
        assert stats["by_scale"]["S"] == 2
        assert stats["by_scale"]["L"] == 1
        assert stats["unique_swings"] == 2

    def test_market_context_calculation(self, logger, sample_events, sample_swings):
        """Test market context calculation with active swings."""
        market_context = {
            "active_swings": sample_swings
        }
        
        event_id = logger.log_event(sample_events[0], market_context)
        event = logger.get_event_by_id(event_id)
        
        # Should calculate price distance
        assert event.price_distance_pct is not None
        assert event.price_distance_pct > 0

    def test_auto_tag_generation(self, logger, sample_events):
        """Test automatic tag generation."""
        logger.log_event(sample_events[0])  # MINOR cross up
        logger.log_event(sample_events[1])  # MAJOR completion
        
        minor_event = logger.events[0]
        major_event = logger.events[1]
        
        # Check severity tags
        assert "severity-minor" in minor_event.tags
        assert "severity-major" in major_event.tags
        
        # Check type tags
        assert "type-level_cross_up" in minor_event.tags
        assert "type-completion" in major_event.tags
        
        # Check scale tags
        assert "scale-S" in minor_event.tags
        assert "scale-L" in major_event.tags
        
        # Check level tags
        assert "critical-level" in major_event.tags  # 2.0 level

    def test_export_csv(self, logger, sample_events):
        """Test CSV export functionality."""
        logger.log_events_batch(sample_events)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            filepath = f.name
        
        try:
            result = logger.export_to_csv(filepath)
            assert result is True
            
            # Verify file contents
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
            assert len(rows) == 3
            assert 'event_id' in rows[0]
            assert 'event_type' in rows[0]
            assert rows[0]['severity'] == 'minor'
            
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_export_json(self, logger, sample_events):
        """Test JSON export functionality."""
        logger.log_events_batch(sample_events)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            result = logger.export_to_json(filepath)
            assert result is True
            
            # Verify file contents
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            assert data['session_id'] == 'test_session'
            assert data['total_events'] == 3
            assert len(data['events']) == 3
            assert 'statistics' in data
            
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_export_summary_report(self, logger, sample_events):
        """Test summary report export."""
        logger.log_events_batch(sample_events)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            filepath = f.name
        
        try:
            result = logger.export_summary_report(filepath)
            assert result is True
            
            # Verify file exists and has content
            with open(filepath, 'r') as f:
                content = f.read()
            
            assert 'Event Log Summary Report' in content
            assert 'test_session' in content
            assert 'Total Events: 3' in content
            
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_clear_session(self, logger, sample_events):
        """Test clearing session data."""
        logger.log_events_batch(sample_events)
        assert len(logger.events) == 3
        
        logger.clear_session()
        assert len(logger.events) == 0
        assert logger.sequence_counter == 0
        assert len(logger._events_by_id) == 0

    def test_update_callback(self, logger, sample_events):
        """Test update callback functionality."""
        callback = Mock()
        logger.set_update_callback(callback)
        
        logger.log_event(sample_events[0])
        
        callback.assert_called_once()
        args = callback.call_args[0]
        assert isinstance(args[0], EventLogEntry)


class TestLogFilter:
    """Test suite for LogFilter class."""

    @pytest.fixture
    def sample_entries(self):
        """Create sample log entries for filter testing."""
        entries = []
        
        # Create diverse entries
        for i in range(5):
            entry = EventLogEntry(
                event_id=f"event-{i}",
                event_type=EventType.LEVEL_CROSS_UP if i % 2 == 0 else EventType.COMPLETION,
                severity=EventSeverity.MINOR if i % 2 == 0 else EventSeverity.MAJOR,
                timestamp=1672531800 + i * 60,
                source_bar_idx=50 + i * 10,
                level_name="0.618" if i % 2 == 0 else "2.0",
                level_price=4100.0 + i * 5,
                swing_id=f"swing-{i // 2}",
                scale="S" if i < 3 else "M",
                bar_open=4100.0,
                bar_high=4105.0,
                bar_low=4095.0,
                bar_close=4102.0,
                description=f"Test event {i}",
                session_id="test",
                sequence_number=i
            )
            entries.append(entry)
        
        return entries

    def test_time_range_filter(self, sample_entries):
        """Test time range filtering."""
        filter_obj = LogFilter(start_bar_idx=55, end_bar_idx=75)
        
        filtered = apply_filters(sample_entries, filter_obj)
        # Entries have bar indices: 50, 60, 70, 80, 90
        # Filter is 55-75, so should match bars 60, 70 = 2 entries
        assert len(filtered) == 2
        
        for entry in filtered:
            assert 55 <= entry.source_bar_idx <= 75

    def test_event_type_filter(self, sample_entries):
        """Test event type filtering."""
        filter_obj = LogFilter(event_types={EventType.COMPLETION})
        
        filtered = apply_filters(sample_entries, filter_obj)
        assert len(filtered) == 2  # Events 1 and 3
        
        for entry in filtered:
            assert entry.event_type == EventType.COMPLETION

    def test_scale_filter(self, sample_entries):
        """Test scale filtering."""
        filter_obj = LogFilter(scales={"S"})
        
        filtered = apply_filters(sample_entries, filter_obj)
        assert len(filtered) == 3  # First 3 events are S scale
        
        for entry in filtered:
            assert entry.scale == "S"

    def test_multiple_filters(self, sample_entries):
        """Test combining multiple filters."""
        filter_obj = LogFilter(
            severities={EventSeverity.MAJOR},
            scales={"M"}
        )
        
        filtered = apply_filters(sample_entries, filter_obj)
        assert len(filtered) == 1  # Only event 3 matches both criteria

    def test_filter_builder(self):
        """Test FilterBuilder class."""
        filter_obj = (FilterBuilder()
                     .severities(EventSeverity.MAJOR)
                     .scales("S", "M")
                     .time_range(start_bar=10, end_bar=100)
                     .build())
        
        assert filter_obj.severities == {EventSeverity.MAJOR}
        assert filter_obj.scales == {"S", "M"}
        assert filter_obj.start_bar_idx == 10
        assert filter_obj.end_bar_idx == 100


class TestEventLogDisplay:
    """Test suite for EventLogDisplay class."""

    @pytest.fixture
    def logger_with_events(self):
        """Create logger with sample events."""
        logger = EventLogger("display_test")
        
        # Create sample events inline
        events = [
            StructuralEvent(
                event_type=EventType.LEVEL_CROSS_UP,
                severity=EventSeverity.MINOR,
                timestamp=1672531800,
                source_bar_idx=50,
                level_name="0.618",
                level_price=4107.4,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4106.0,
                bar_high=4109.0,
                bar_low=4105.5,
                bar_close=4108.0,
                description="Level 0.618 crossed upward"
            ),
            StructuralEvent(
                event_type=EventType.COMPLETION,
                severity=EventSeverity.MAJOR,
                timestamp=1672532400,
                source_bar_idx=75,
                level_name="2.0",
                level_price=4250.0,
                swing_id="test-swing-2",
                scale="L",
                bar_open=4248.0,
                bar_high=4252.0,
                bar_low=4247.0,
                bar_close=4251.0,
                description="Bull swing completed at 2x extension"
            ),
            StructuralEvent(
                event_type=EventType.INVALIDATION,
                severity=EventSeverity.MAJOR,
                timestamp=1672533000,
                source_bar_idx=100,
                level_name="-0.1",
                level_price=4090.0,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4092.0,
                bar_high=4093.0,
                bar_low=4089.0,
                bar_close=4089.5,
                description="Bull swing invalidated - close below -0.1"
            )
        ]
        
        logger.log_events_batch(events)
        return logger

    @pytest.fixture
    def display(self, logger_with_events):
        """Create display with populated logger."""
        return EventLogDisplay(logger_with_events)

    def test_initialization(self, display, logger_with_events):
        """Test display initialization."""
        assert display.logger == logger_with_events
        assert display.max_display_count == 20
        assert display.last_displayed_sequence == -1

    def test_format_event_for_display(self, display, logger_with_events):
        """Test event formatting for display."""
        event = logger_with_events.events[0]
        
        # Format with colors
        formatted_color = display.format_event_for_display(event, use_colors=True)
        assert event.scale in formatted_color
        assert event.level_name in formatted_color
        
        # Format without colors
        formatted_plain = display.format_event_for_display(event, use_colors=False)
        assert formatted_plain != formatted_color
        assert event.scale in formatted_plain

    def test_format_event_for_table(self, display, logger_with_events):
        """Test event formatting for tabular display."""
        event = logger_with_events.events[0]
        
        table_data = display.format_event_for_table(event)
        
        assert "Time" in table_data
        assert "Scale" in table_data
        assert "Type" in table_data
        assert table_data["Scale"] == event.scale

    def test_get_color_for_event(self, display, logger_with_events):
        """Test color assignment for events."""
        minor_event = logger_with_events.events[0]  # MINOR severity
        major_event = logger_with_events.events[1]  # MAJOR completion
        
        minor_color = display.get_color_for_event(minor_event)
        major_color = display.get_color_for_event(major_event)
        
        assert minor_color != major_color
        assert minor_color  # Should not be empty
        assert major_color  # Should not be empty

    def test_update_display(self, display, logger_with_events):
        """Test display update tracking."""
        # Initial update should return all events
        new_events = display.update_display()
        assert len(new_events) == 3
        
        # Add another event
        new_event = StructuralEvent(
            event_type=EventType.LEVEL_CROSS_DOWN,
            severity=EventSeverity.MINOR,
            timestamp=1672534000,
            source_bar_idx=120,
            level_name="0.5",
            level_price=4080.0,
            swing_id="test-swing-3",
            scale="M",
            bar_open=4082.0,
            bar_high=4084.0,
            bar_low=4078.0,
            bar_close=4080.5,
            description="Level 0.5 crossed downward"
        )
        
        logger_with_events.log_event(new_event)
        
        # Update should only return new event
        new_events = display.update_display()
        assert len(new_events) == 1
        assert new_events[0].event_type == EventType.LEVEL_CROSS_DOWN

    def test_create_dashboard(self, display):
        """Test dashboard creation."""
        dashboard = display.create_event_dashboard()
        
        assert "Event Log Dashboard" in dashboard
        assert "display_test" in dashboard  # Session ID
        assert "║" in dashboard  # Box drawing characters


class TestEventLogIntegration:
    """Integration tests for event logging components."""

    def test_end_to_end_workflow(self):
        """Test complete workflow from logging to export."""
        # Create sample events inline
        sample_events = [
            StructuralEvent(
                event_type=EventType.LEVEL_CROSS_UP,
                severity=EventSeverity.MINOR,
                timestamp=1672531800,
                source_bar_idx=50,
                level_name="0.618",
                level_price=4107.4,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4106.0,
                bar_high=4109.0,
                bar_low=4105.5,
                bar_close=4108.0,
                description="Level 0.618 crossed upward"
            ),
            StructuralEvent(
                event_type=EventType.COMPLETION,
                severity=EventSeverity.MAJOR,
                timestamp=1672532400,
                source_bar_idx=75,
                level_name="2.0",
                level_price=4250.0,
                swing_id="test-swing-2",
                scale="L",
                bar_open=4248.0,
                bar_high=4252.0,
                bar_low=4247.0,
                bar_close=4251.0,
                description="Bull swing completed at 2x extension"
            )
        ]
        
        # Create logger and display
        logger = EventLogger("integration_test")
        display = EventLogDisplay(logger)
        
        # Log events
        logger.log_events_batch(sample_events)
        
        # Add tags and notes
        event_id = logger.events[0].event_id
        logger.add_tag(event_id, "important")
        logger.add_note(event_id, "First event note")
        
        # Search events
        search_results = logger.search_events("crossed")
        assert len(search_results) > 0
        
        # Filter events
        major_filter = LogFilter(severities={EventSeverity.MAJOR})
        major_events = logger.get_events(major_filter)
        assert len(major_events) == 1  # Only 1 major event in our sample
        
        # Export data
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            result = logger.export_to_json(filepath)
            assert result is True
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_performance_with_many_events(self):
        """Test performance with large number of events."""
        logger = EventLogger("performance_test")
        
        # Create many events
        events = []
        for i in range(1000):
            event = StructuralEvent(
                event_type=EventType.LEVEL_CROSS_UP,
                severity=EventSeverity.MINOR,
                timestamp=1672531800 + i,
                source_bar_idx=i,
                level_name="0.618",
                level_price=4100.0 + i * 0.1,
                swing_id=f"swing-{i // 10}",
                scale="S",
                bar_open=4100.0,
                bar_high=4105.0,
                bar_low=4095.0,
                bar_close=4102.0,
                description=f"Event {i}"
            )
            events.append(event)
        
        # Batch log - should be fast
        import time
        start_time = time.time()
        logger.log_events_batch(events)
        end_time = time.time()
        
        # Should process 1000 events quickly
        assert end_time - start_time < 5.0  # Less than 5 seconds
        assert len(logger.events) == 1000
        
        # Search should be reasonably fast
        start_time = time.time()
        results = logger.search_events("Event 500")
        end_time = time.time()
        
        assert len(results) == 1
        assert end_time - start_time < 1.0  # Less than 1 second


if __name__ == "__main__":
    pytest.main([__file__, "-v"])