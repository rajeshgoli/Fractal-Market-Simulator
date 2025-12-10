#!/usr/bin/env python3
"""
Visualization Renderer Demo

Standalone demo script that showcases the 4-panel visualization renderer
with sample market data and swing structures.

Usage:
    python examples/renderer_demo.py
    
Author: Generated for Market Simulator Project
"""

import sys
import os
import matplotlib
matplotlib.use('TkAgg')  # Use TkAgg backend for interactive display

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

from src.legacy.bull_reference_detector import Bar
from src.analysis.scale_calibrator import ScaleConfig
from src.analysis.bar_aggregator import BarAggregator
from src.analysis.swing_state_manager import ActiveSwing
from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.visualization.renderer import VisualizationRenderer
from src.visualization.config import RenderConfig


def create_sample_data(num_bars=200):
    """Create realistic sample OHLC data."""
    np.random.seed(42)  # For reproducible demo
    
    bars = []
    base_price = 4100.0
    timestamp = int(datetime(2023, 1, 1).timestamp())
    
    for i in range(num_bars):
        # Create price movement with some volatility
        price_change = np.random.normal(0, 2.0) + 0.1 * np.sin(i * 0.1)
        base_price += price_change
        
        # Create OHLC with realistic relationships
        spread = np.random.uniform(3, 8)
        open_price = base_price + np.random.uniform(-2, 2)
        close_price = base_price + np.random.uniform(-2, 2)
        
        high_price = max(open_price, close_price) + np.random.uniform(0, spread/2)
        low_price = min(open_price, close_price) - np.random.uniform(0, spread/2)
        
        bars.append(Bar(
            index=i,
            timestamp=timestamp + i * 60,  # 1-minute bars
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price
        ))
    
    return bars


def create_sample_swings():
    """Create sample active swings for demonstration."""
    return [
        ActiveSwing(
            swing_id="demo-s-bull-001",
            scale="S",
            high_price=4115.0,
            low_price=4095.0,
            high_timestamp=1672531200,
            low_timestamp=1672530600,
            is_bull=True,
            state="active",
            levels={
                "-0.1": 4093.0,
                "0": 4095.0,
                "0.382": 4102.6,
                "0.5": 4105.0,
                "0.618": 4107.4,
                "1.0": 4115.0,
                "1.382": 4122.6,
                "1.618": 4127.4,
                "2.0": 4135.0
            }
        ),
        ActiveSwing(
            swing_id="demo-m-bear-001",
            scale="M",
            high_price=4140.0,
            low_price=4080.0,
            high_timestamp=1672530000,
            low_timestamp=1672532400,
            is_bull=False,
            state="active",
            levels={
                "-0.1": 4146.0,
                "0": 4140.0,
                "0.382": 4117.1,
                "0.5": 4110.0,
                "0.618": 4102.9,
                "1.0": 4080.0,
                "1.382": 4057.1,
                "1.618": 4043.2,
                "2.0": 4020.0
            }
        ),
        ActiveSwing(
            swing_id="demo-l-bull-001",
            scale="L",
            high_price=4150.0,
            low_price=4050.0,
            high_timestamp=1672529400,
            low_timestamp=1672532400,
            is_bull=True,
            state="completed",
            levels={
                "-0.1": 4040.0,
                "0": 4050.0,
                "0.382": 4088.2,
                "0.5": 4100.0,
                "0.618": 4111.8,
                "1.0": 4150.0,
                "1.382": 4188.2,
                "1.618": 4211.8,
                "2.0": 4250.0
            }
        ),
        ActiveSwing(
            swing_id="demo-xl-bear-001",
            scale="XL",
            high_price=4200.0,
            low_price=4000.0,
            high_timestamp=1672528800,
            low_timestamp=1672532400,
            is_bull=False,
            state="active",
            levels={
                "-0.1": 4220.0,
                "0": 4200.0,
                "0.382": 4123.6,
                "0.5": 4100.0,
                "0.618": 4076.4,
                "1.0": 4000.0,
                "1.382": 3723.6,
                "1.618": 3676.4,
                "2.0": 3800.0
            }
        )
    ]


def create_sample_events():
    """Create sample structural events."""
    return [
        StructuralEvent(
            event_type=EventType.LEVEL_CROSS_UP,
            severity=EventSeverity.MINOR,
            timestamp=1672531800,
            source_bar_idx=150,
            level_name="0.618",
            level_price=4107.4,
            swing_id="demo-s-bull-001",
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
            source_bar_idx=180,
            level_name="2.0",
            level_price=4250.0,
            swing_id="demo-l-bull-001",
            scale="L",
            bar_open=4248.0,
            bar_high=4252.0,
            bar_low=4247.0,
            bar_close=4251.0,
            description="Bull swing completed at 2x extension"
        )
    ]


def main():
    """Main demo function."""
    print("Visualization Renderer Demo")
    print("===========================")
    
    # Create sample data
    print("Creating sample data...")
    bars = create_sample_data(200)
    
    # Setup configuration
    scale_config = ScaleConfig(
        boundaries={"S": (0, 25), "M": (25, 60), "L": (60, 120), "XL": (120, float('inf'))},
        aggregations={"S": 1, "M": 1, "L": 5, "XL": 5},
        used_defaults=False,
        swing_count=20,
        median_durations={"S": 12, "M": 25, "L": 45, "XL": 80}
    )
    
    render_config = RenderConfig(
        figure_size=(14, 10),
        max_visible_bars=100
    )
    
    # Initialize components
    print("Initializing components...")
    bar_aggregator = BarAggregator(bars)
    renderer = VisualizationRenderer(scale_config, bar_aggregator, render_config)
    
    # Initialize display
    print("Setting up visualization...")
    renderer.initialize_display()
    
    # Create sample swings and events
    active_swings = create_sample_swings()
    recent_events = create_sample_events()
    
    # Update display
    print("Updating display with sample data...")
    current_bar_idx = 150
    
    renderer.update_display(
        current_bar_idx=current_bar_idx,
        active_swings=active_swings,
        recent_events=recent_events,
        highlighted_events=[e for e in recent_events if e.severity == EventSeverity.MAJOR]
    )
    
    print(f"Demo visualization shows:")
    print(f"  - {len(bars)} total bars")
    print(f"  - {len(active_swings)} active swings across scales")
    print(f"  - {len(recent_events)} recent events")
    print(f"  - Current position: bar {current_bar_idx}")
    print("\nPress Ctrl+C to exit when you're done viewing.")
    
    # Show the plot
    plt.show()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo finished.")
    except Exception as e:
        print(f"Error running demo: {e}")
        import traceback
        traceback.print_exc()