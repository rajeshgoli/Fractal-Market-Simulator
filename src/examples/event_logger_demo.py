#!/usr/bin/env python3
"""
Event Logger Demo

Demonstrates the comprehensive event logging system with filtering,
search, and export capabilities.

Usage:
    python examples/event_logger_demo.py
    
Author: Generated for Market Simulator Project
"""

import sys
import os
import tempfile
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.visualization_harness.event_logger import EventLogger
from src.visualization_harness.display import EventLogDisplay
from src.visualization_harness.filters import FilterBuilder, LogFilter
from src.swing_analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.swing_analysis.swing_state_manager import ActiveSwing


def create_demo_events():
    """Create realistic demo events across different scales."""
    events = [
        # S Scale Events
        StructuralEvent(
            event_type=EventType.LEVEL_CROSS_UP,
            severity=EventSeverity.MINOR,
            timestamp=1672531800,
            source_bar_idx=50,
            level_name="0.618",
            level_price=4107.4,
            swing_id="s-bull-001",
            scale="S",
            bar_open=4106.0,
            bar_high=4109.0,
            bar_low=4105.5,
            bar_close=4108.0,
            description="S-scale bull swing: Level 0.618 crossed upward"
        ),
        
        # M Scale Events
        StructuralEvent(
            event_type=EventType.COMPLETION,
            severity=EventSeverity.MAJOR,
            timestamp=1672532400,
            source_bar_idx=75,
            level_name="2.0",
            level_price=4250.0,
            swing_id="m-bull-001",
            scale="M",
            bar_open=4248.0,
            bar_high=4252.0,
            bar_low=4247.0,
            bar_close=4251.0,
            description="M-scale bull swing completed at 2x extension"
        ),
        
        # L Scale Events
        StructuralEvent(
            event_type=EventType.LEVEL_CROSS_DOWN,
            severity=EventSeverity.MINOR,
            timestamp=1672533000,
            source_bar_idx=100,
            level_name="1.382",
            level_price=4200.0,
            swing_id="l-bear-001",
            scale="L",
            bar_open=4202.0,
            bar_high=4205.0,
            bar_low=4198.0,
            bar_close=4199.0,
            description="L-scale bear swing: Decision zone 1.382 broken"
        ),
        
        # Critical Level Event
        StructuralEvent(
            event_type=EventType.INVALIDATION,
            severity=EventSeverity.MAJOR,
            timestamp=1672533600,
            source_bar_idx=120,
            level_name="-0.1",
            level_price=4090.0,
            swing_id="s-bull-001",
            scale="S",
            bar_open=4092.0,
            bar_high=4093.0,
            bar_low=4089.0,
            bar_close=4089.5,
            description="S-scale bull swing INVALIDATED - close below critical -0.1 level"
        ),
        
        # XL Scale Event
        StructuralEvent(
            event_type=EventType.LEVEL_CROSS_UP,
            severity=EventSeverity.MINOR,
            timestamp=1672534200,
            source_bar_idx=150,
            level_name="1.0",
            level_price=4300.0,
            swing_id="xl-bull-001",
            scale="XL",
            bar_open=4298.0,
            bar_high=4302.0,
            bar_low=4296.0,
            bar_close=4301.0,
            description="XL-scale bull swing: Par level (1.0) reclaimed"
        ),
        
        # Another Major Event
        StructuralEvent(
            event_type=EventType.COMPLETION,
            severity=EventSeverity.MAJOR,
            timestamp=1672534800,
            source_bar_idx=180,
            level_name="2.0",
            level_price=4350.0,
            swing_id="l-bull-002",
            scale="L",
            bar_open=4348.0,
            bar_high=4352.0,
            bar_low=4347.0,
            bar_close=4350.5,
            description="L-scale bull swing achieved 2x extension target"
        )
    ]
    
    return events


def create_demo_swings():
    """Create sample active swings for market context."""
    return [
        ActiveSwing(
            swing_id="s-bull-001",
            scale="S",
            high_price=4110.0,
            low_price=4090.0,
            high_timestamp=1672531200,
            low_timestamp=1672530600,
            is_bull=True,
            state="active",
            levels={"0": 4090.0, "0.618": 4107.4, "1.0": 4110.0, "2.0": 4130.0}
        ),
        ActiveSwing(
            swing_id="m-bull-001",
            scale="M",
            high_price=4250.0,
            low_price=4150.0,
            high_timestamp=1672532400,
            low_timestamp=1672530000,
            is_bull=True,
            state="completed",
            levels={"0": 4150.0, "1.0": 4250.0, "2.0": 4350.0}
        )
    ]


def demonstrate_basic_logging():
    """Demonstrate basic event logging functionality."""
    print("\n" + "="*60)
    print("DEMONSTRATION: Basic Event Logging")
    print("="*60)
    
    # Create logger and events
    logger = EventLogger("demo_session_basic")
    events = create_demo_events()
    
    # Log events one by one
    print("Logging events...")
    for i, event in enumerate(events[:3], 1):
        event_id = logger.log_event(event)
        print(f"  {i}. Logged {event.event_type.value} event: {event_id[:8]}...")
    
    # Get statistics
    stats = logger.get_event_statistics()
    print(f"\nSession Statistics:")
    print(f"  Total Events: {stats['total_events']}")
    print(f"  Major Events: {stats['by_severity'].get('major', 0)}")
    print(f"  Minor Events: {stats['by_severity'].get('minor', 0)}")
    print(f"  Scales Involved: {', '.join(stats['by_scale'].keys())}")
    
    return logger


def demonstrate_filtering():
    """Demonstrate advanced filtering capabilities."""
    print("\n" + "="*60)
    print("DEMONSTRATION: Advanced Filtering")
    print("="*60)
    
    # Create logger with all events
    logger = EventLogger("demo_session_filtering")
    events = create_demo_events()
    logger.log_events_batch(events)
    
    # Filter 1: Major events only
    print("1. Major Events Only:")
    major_filter = FilterBuilder().severities(EventSeverity.MAJOR).build()
    major_events = logger.get_events(major_filter)
    for event in major_events:
        print(f"   - {event.event_type.value.upper()} on {event.scale}-scale at {event.level_name}")
    
    # Filter 2: S and M scale events
    print("\n2. S and M Scale Events:")
    sm_filter = FilterBuilder().scales("S", "M").build()
    sm_events = logger.get_events(sm_filter)
    for event in sm_events:
        print(f"   - {event.scale}-scale: {event.description[:50]}...")
    
    # Filter 3: Critical levels only
    print("\n3. Critical Level Events:")
    critical_filter = FilterBuilder().level_names("-0.1", "2.0").build()
    critical_events = logger.get_events(critical_filter)
    for event in critical_events:
        print(f"   - Level {event.level_name}: {event.description}")
    
    # Filter 4: Time range
    print("\n4. Events in Bar Range 100-200:")
    time_filter = FilterBuilder().time_range(100, 200).build()
    time_events = logger.get_events(time_filter)
    print(f"   - Found {len(time_events)} events in specified range")
    
    return logger


def demonstrate_search_and_annotations():
    """Demonstrate search and annotation features."""
    print("\n" + "="*60)
    print("DEMONSTRATION: Search & Annotations")
    print("="*60)
    
    # Create logger
    logger = EventLogger("demo_session_search")
    events = create_demo_events()
    logger.log_events_batch(events)
    
    # Add custom tags and notes
    print("Adding custom annotations...")
    for i, event in enumerate(logger.events):
        # Add tags based on importance
        if event.severity == EventSeverity.MAJOR:
            logger.add_tag(event.event_id, "important")
        if event.level_name in ["-0.1", "2.0"]:
            logger.add_tag(event.event_id, "critical-level")
        if event.scale in ["L", "XL"]:
            logger.add_tag(event.event_id, "higher-timeframe")
        
        # Add notes for key events
        if event.event_type == EventType.COMPLETION:
            logger.add_note(event.event_id, f"Target achieved on {event.scale}-scale swing")
        elif event.event_type == EventType.INVALIDATION:
            logger.add_note(event.event_id, "RISK: Swing structure compromised")
    
    # Demonstrate search
    print("\nSearch Results:")
    print("1. Search for 'bull':")
    bull_results = logger.search_events("bull")
    for result in bull_results[:2]:  # Show first 2
        print(f"   - {result.description}")
    
    print("\n2. Search for 'extension':")
    extension_results = logger.search_events("extension")
    for result in extension_results:
        print(f"   - {result.description}")
    
    # Show tagged events
    print("\n3. Events with 'critical-level' tag:")
    for event in logger.events:
        if "critical-level" in event.tags:
            print(f"   - {event.description}")
            if event.notes:
                print(f"     Note: {event.notes}")
    
    return logger


def demonstrate_display():
    """Demonstrate real-time display functionality."""
    print("\n" + "="*60)
    print("DEMONSTRATION: Real-time Display")
    print("="*60)
    
    # Create logger and display
    logger = EventLogger("demo_session_display")
    display = EventLogDisplay(logger, max_display_count=5)
    events = create_demo_events()
    
    # Simulate real-time logging
    print("Simulating real-time event feed:\n")
    for event in events:
        logger.log_event(event)
        
        # Format for display
        formatted = display.format_event_for_display(logger.events[-1], use_colors=False)
        print(formatted)
    
    print("\nEvent Dashboard:")
    print(display.create_event_dashboard())
    
    return logger, display


def demonstrate_export():
    """Demonstrate export capabilities."""
    print("\n" + "="*60)
    print("DEMONSTRATION: Export Capabilities")
    print("="*60)
    
    # Create logger with full dataset
    logger = EventLogger("demo_session_export")
    events = create_demo_events()
    logger.log_events_batch(events)
    
    # Add some annotations
    for event in logger.events:
        if event.severity == EventSeverity.MAJOR:
            logger.add_tag(event.event_id, "flagged-for-review")
    
    # Export to different formats
    with tempfile.TemporaryDirectory() as temp_dir:
        # CSV export
        csv_path = os.path.join(temp_dir, "demo_events.csv")
        logger.export_to_csv(csv_path)
        print(f"1. CSV export completed: {os.path.basename(csv_path)}")
        
        # JSON export with filter
        json_path = os.path.join(temp_dir, "major_events.json")
        major_filter = LogFilter(severities={EventSeverity.MAJOR})
        logger.export_to_json(json_path, major_filter)
        print(f"2. JSON export (major events only): {os.path.basename(json_path)}")
        
        # Summary report
        report_path = os.path.join(temp_dir, "session_summary.txt")
        logger.export_summary_report(report_path)
        print(f"3. Summary report: {os.path.basename(report_path)}")
        
        # Show sample content
        with open(report_path, 'r') as f:
            lines = f.readlines()
            print("\nSample from summary report:")
            for line in lines[:10]:  # First 10 lines
                print(f"   {line.rstrip()}")
            if len(lines) > 10:
                print(f"   ... ({len(lines)-10} more lines)")
    
    return logger


def demonstrate_market_context():
    """Demonstrate market context integration."""
    print("\n" + "="*60)
    print("DEMONSTRATION: Market Context Integration")
    print("="*60)
    
    logger = EventLogger("demo_session_context")
    events = create_demo_events()[:3]  # Use first 3 events
    swings = create_demo_swings()
    
    # Log with market context
    print("Logging events with market context...")
    for event in events:
        market_context = {
            "active_swings": swings,
            "market_volatility": 15.5,  # Mock volatility measure
            "session_high": 4310.0,
            "session_low": 4080.0
        }
        
        logger.log_event(event, market_context)
    
    # Show enhanced entries
    print("\nEnhanced event entries:")
    for event in logger.events:
        print(f"Event: {event.description[:40]}...")
        print(f"  Auto-tags: {', '.join(sorted(event.tags))}")
        if event.swing_age_bars:
            print(f"  Swing age: {event.swing_age_bars} bars")
        if event.price_distance_pct:
            print(f"  Distance from swing: {event.price_distance_pct:.1f}%")
        print()
    
    return logger


def main():
    """Run all demonstrations."""
    print("EVENT LOGGER DEMONSTRATION")
    print("Comprehensive event logging with filtering and export")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Run demonstrations
        demonstrate_basic_logging()
        demonstrate_filtering()
        demonstrate_search_and_annotations()
        demonstrate_display()
        demonstrate_export()
        demonstrate_market_context()
        
        print("\n" + "="*60)
        print("DEMONSTRATION COMPLETED SUCCESSFULLY")
        print("="*60)
        print("Key Features Demonstrated:")
        print("  ✓ Event logging with automatic tagging")
        print("  ✓ Flexible filtering and search")
        print("  ✓ Custom annotations (tags & notes)")
        print("  ✓ Real-time display formatting")
        print("  ✓ Export to CSV/JSON/TXT formats")
        print("  ✓ Market context integration")
        print("  ✓ Performance with batch operations")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()