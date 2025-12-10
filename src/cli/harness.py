"""
Visualization Harness CLI

Command-line interface that integrates all visualization harness components
into a unified interactive market data analysis tool.

Usage:
    python -m src.cli.harness --data test.csv
    python -m src.cli.harness --data test.csv --session analysis_001
    python -m src.cli.harness --help

Author: Generated for Market Simulator Project
"""

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use('TkAgg')  # Ensure interactive backend
import matplotlib.pyplot as plt

# Project imports
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data.ohlc_loader import load_ohlc
from src.analysis.scale_calibrator import ScaleCalibrator
from src.analysis.bar_aggregator import BarAggregator
from src.analysis.swing_state_manager import SwingStateManager
from src.visualization.renderer import VisualizationRenderer
from src.visualization.config import RenderConfig
from src.playback.controller import PlaybackController
from src.playback.config import PlaybackConfig, PlaybackMode
from src.logging.event_logger import EventLogger
from src.logging.display import EventLogDisplay
from src.logging.filters import FilterBuilder
from src.legacy.bull_reference_detector import Bar


class VisualizationHarness:
    """Integrated visualization harness combining all components."""
    
    def __init__(self, 
                 data_file: str,
                 session_id: Optional[str] = None,
                 config_overrides: Optional[dict] = None):
        """
        Initialize the visualization harness.
        
        Args:
            data_file: Path to OHLC CSV data file
            session_id: Optional session identifier
            config_overrides: Optional configuration overrides
        """
        self.data_file = data_file
        self.session_id = session_id or f"session_{int(time.time())}"
        self.config_overrides = config_overrides or {}
        
        # Core components
        self.bars = None
        self.scale_config = None
        self.bar_aggregator = None
        self.swing_state_manager = None
        self.event_detector = None
        self.visualization_renderer = None
        self.playback_controller = None
        self.event_logger = None
        self.event_display = None
        
        # State management
        self.is_running = False
        self.current_bar_idx = 0
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def initialize(self) -> bool:
        """Initialize all harness components."""
        try:
            self.logger.info(f"Initializing harness for session {self.session_id}")
            
            # Load data
            self.logger.info(f"Loading OHLC data from {self.data_file}")
            df, gaps = load_ohlc(self.data_file)
            
            # Convert DataFrame to Bar objects
            self.bars = []
            for bar_index, (idx, row) in enumerate(df.iterrows()):
                bar = Bar(
                    index=bar_index,
                    timestamp=int(idx.timestamp()),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close'])
                )
                self.bars.append(bar)
            
            if not self.bars:
                raise ValueError(f"No data loaded from {self.data_file}")
            
            self.logger.info(f"Loaded {len(self.bars)} bars")
            
            # Calibrate scales
            self.logger.info("Calibrating structural scales...")
            calibrator = ScaleCalibrator()
            self.scale_config = calibrator.calibrate(self.bars)
            
            self.logger.info("Scale boundaries:")
            for scale, (min_pts, max_pts) in self.scale_config.boundaries.items():
                self.logger.info(f"  {scale}: {min_pts:.1f} - {max_pts} pts")
            
            # Initialize components
            self._initialize_analysis_components()
            self._initialize_visualization_components()
            self._initialize_playback_components()
            self._initialize_logging_components()

            # Render initial display with the bars used for initialization
            self._render_initial_display()

            self.logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize harness: {e}")
            return False
    
    def _initialize_analysis_components(self):
        """Initialize analysis pipeline components."""
        # Bar aggregator
        self.bar_aggregator = BarAggregator(self.bars)
        
        # Swing state manager (creates its own EventDetector internally)
        self.swing_state_manager = SwingStateManager(
            scale_config=self.scale_config
        )

        # Reference the event detector from swing state manager
        self.event_detector = self.swing_state_manager.event_detector
        
        # Initialize with first portion of data for swing detection
        self.init_bars = min(200, len(self.bars))
        self.swing_state_manager.initialize_with_bars(self.bars[:self.init_bars])

        self.logger.info(f"Analysis components initialized with {self.init_bars} bars")
    
    def _initialize_visualization_components(self):
        """Initialize visualization components."""
        # Create render config
        render_config = RenderConfig()
        
        # Apply any overrides
        if 'visualization' in self.config_overrides:
            for key, value in self.config_overrides['visualization'].items():
                setattr(render_config, key, value)
        
        # Create renderer
        self.visualization_renderer = VisualizationRenderer(
            scale_config=self.scale_config,
            bar_aggregator=self.bar_aggregator,
            render_config=render_config
        )

        # Initialize display
        self.visualization_renderer.initialize_display()
        self.visualization_renderer.set_interactive_mode(True)

        # Show the visualization window (makes it visible on screen)
        self.visualization_renderer.show_display()

        self.logger.info("Visualization components initialized")
    
    def _initialize_playback_components(self):
        """Initialize playback control components."""
        # Create playback config
        playback_config = PlaybackConfig()

        # Apply any overrides
        if 'playback' in self.config_overrides:
            for key, value in self.config_overrides['playback'].items():
                setattr(playback_config, key, value)

        # Create controller
        self.playback_controller = PlaybackController(
            total_bars=len(self.bars),
            config=playback_config
        )

        # Set step callback
        self.playback_controller.set_event_callback(self._on_playback_step)

        # Start playback from where initialization ended to avoid timestamp errors
        # The swing state manager was initialized with bars[0:init_bars], so playback
        # should continue from init_bars onwards
        self.playback_controller.current_bar_idx = self.init_bars - 1
        self.current_bar_idx = self.init_bars - 1

        self.logger.info(f"Playback components initialized, starting at bar {self.init_bars - 1}")
    
    def _initialize_logging_components(self):
        """Initialize event logging components."""
        # Create event logger
        self.event_logger = EventLogger(session_id=self.session_id)

        # Create display
        self.event_display = EventLogDisplay(self.event_logger)

        self.logger.info("Logging components initialized")

    def _render_initial_display(self):
        """Render initial visualization with the bars from initialization."""
        try:
            # Get active swings detected during initialization
            active_swings = self.swing_state_manager.get_active_swings()

            # Update visualization with initial state
            # Use init_bars - 1 as current position (last initialized bar)
            self.visualization_renderer.update_display(
                current_bar_idx=self.init_bars - 1,
                active_swings=active_swings,
                recent_events=[],
                highlighted_events=[]
            )

            self.logger.info(f"Initial display rendered with {len(active_swings)} active swings")

        except Exception as e:
            self.logger.error(f"Failed to render initial display: {e}")

    def _on_playback_step(self, bar_idx: int, recent_events: list):
        """Handle playback step updates."""
        try:
            if bar_idx >= len(self.bars):
                self.logger.warning(f"Bar index {bar_idx} exceeds data range")
                return
            
            self.current_bar_idx = bar_idx
            current_bar = self.bars[bar_idx]
            
            # Update swing state manager
            update_result = self.swing_state_manager.update_swings(current_bar, bar_idx)
            
            # Log events
            for event in update_result.events:
                self.event_logger.log_event(event)
            
            # Check for auto-pause conditions
            for event in update_result.events:
                if self.playback_controller.should_pause_for_event(event):
                    self.playback_controller.pause_playback(
                        f"Auto-paused: {event.event_type.value} on {event.scale}-scale"
                    )
                    break
            
            # Update visualization
            active_swings = self.swing_state_manager.get_active_swings()
            self.visualization_renderer.update_display(
                current_bar_idx=bar_idx,
                active_swings=active_swings,
                recent_events=update_result.events,
                highlighted_events=[e for e in update_result.events 
                                  if e.severity.value == 'major']
            )
            
        except Exception as e:
            self.logger.error(f"Error during playback step {bar_idx}: {e}")
    
    def run_interactive(self):
        """Run the harness in interactive mode."""
        self.is_running = True
        self.logger.info("Starting interactive visualization harness")
        
        # Print initial status
        self._print_status()
        self._print_help()
        
        try:
            while self.is_running:
                try:
                    command = input("\nharness> ").strip().lower()
                    self._handle_command(command)
                except KeyboardInterrupt:
                    print("\nUse 'quit' to exit properly")
                except EOFError:
                    break
                    
        except Exception as e:
            self.logger.error(f"Error in interactive mode: {e}")
        finally:
            self._cleanup()
    
    def _handle_command(self, command: str):
        """Handle interactive commands."""
        parts = command.split()
        if not parts:
            return
        
        cmd = parts[0]
        
        if cmd in ['help', 'h', '?']:
            self._print_help()
        
        elif cmd in ['status', 'stat']:
            self._print_status()
        
        elif cmd in ['play', 'start']:
            mode = PlaybackMode.AUTO
            if len(parts) > 1 and parts[1] == 'fast':
                mode = PlaybackMode.FAST
            self.playback_controller.start_playback(mode)
            print(f"Started {mode.value} playback")
        
        elif cmd in ['pause', 'stop']:
            self.playback_controller.pause_playback("User requested")
            print("Playback paused")
        
        elif cmd in ['step', 'next']:
            success = self.playback_controller.step_forward()
            if success:
                print(f"Stepped to bar {self.current_bar_idx}")
            else:
                print("At end of data")
        
        elif cmd in ['jump', 'goto']:
            if len(parts) > 1:
                try:
                    target_bar = int(parts[1])
                    success = self.playback_controller.jump_to_bar(target_bar)
                    if success:
                        print(f"Jumped to bar {target_bar}")
                    else:
                        print("Invalid bar index")
                except ValueError:
                    print("Invalid bar number")
            else:
                print("Usage: jump <bar_index>")
        
        elif cmd in ['speed']:
            if len(parts) > 1:
                try:
                    multiplier = float(parts[1])
                    self.playback_controller.set_playback_speed(multiplier)
                    print(f"Speed set to {multiplier}x")
                except ValueError:
                    print("Invalid speed multiplier")
            else:
                print("Usage: speed <multiplier>")
        
        elif cmd in ['events']:
            count = 10
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except ValueError:
                    pass
            self.event_display.print_recent_events(count)
        
        elif cmd in ['filter']:
            self._handle_filter_command(parts[1:])
        
        elif cmd in ['export']:
            self._handle_export_command(parts[1:])
        
        elif cmd in ['reset']:
            self.playback_controller.stop_playback()
            print("Playback reset to beginning")
        
        elif cmd in ['quit', 'exit', 'q']:
            self.is_running = False
            print("Exiting harness...")
        
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")
    
    def _handle_filter_command(self, args: list):
        """Handle filter commands for event display."""
        if not args:
            print("Available filters: major, scale <S|M|L|XL>, recent <N>")
            return
        
        filter_type = args[0]
        
        if filter_type == 'major':
            filter_obj = FilterBuilder().severities('MAJOR').build()
            self.event_display.print_filtered_events(filter_obj)
        
        elif filter_type == 'scale' and len(args) > 1:
            scale = args[1].upper()
            if scale in ['S', 'M', 'L', 'XL']:
                filter_obj = FilterBuilder().scales(scale).build()
                self.event_display.print_filtered_events(filter_obj)
            else:
                print("Invalid scale. Use S, M, L, or XL")
        
        elif filter_type == 'recent':
            count = 20
            if len(args) > 1:
                try:
                    count = int(args[1])
                except ValueError:
                    pass
            self.event_display.print_recent_events(count)
        
        else:
            print("Unknown filter type")
    
    def _handle_export_command(self, args: list):
        """Handle export commands."""
        if not args:
            print("Available exports: csv <file>, json <file>, summary <file>")
            return
        
        export_type = args[0]
        filename = args[1] if len(args) > 1 else f"export_{self.session_id}.{export_type}"
        
        try:
            if export_type == 'csv':
                success = self.event_logger.export_to_csv(filename)
            elif export_type == 'json':
                success = self.event_logger.export_to_json(filename)
            elif export_type == 'summary':
                success = self.event_logger.export_summary_report(filename)
            else:
                print("Unknown export type")
                return
            
            if success:
                print(f"Exported to {filename}")
            else:
                print("Export failed")
                
        except Exception as e:
            print(f"Export error: {e}")
    
    def _print_status(self):
        """Print current harness status."""
        status = self.playback_controller.get_status()
        stats = self.event_logger.get_event_statistics()
        
        print("\n" + "="*60)
        print("HARNESS STATUS")
        print("="*60)
        print(f"Session: {self.session_id}")
        print(f"Data File: {self.data_file}")
        print(f"Total Bars: {len(self.bars)}")
        print(f"Current Bar: {status.current_bar_idx} ({status.progress_percent:.1f}%)")
        print(f"Playback State: {status.state.value} ({status.mode.value} mode)")
        
        if status.bars_per_second > 0:
            print(f"Processing Rate: {status.bars_per_second:.1f} bars/sec")
        
        if status.last_pause_reason:
            print(f"Last Pause: {status.last_pause_reason}")
        
        print(f"\nEvent Statistics:")
        print(f"  Total Events: {stats['total_events']}")
        for event_type, count in stats['by_type'].items():
            print(f"    {event_type}: {count}")
        
        active_swings = self.swing_state_manager.get_swing_counts()
        print(f"\nActive Swings:")
        for scale, count in active_swings.items():
            print(f"  {scale}: {count}")
    
    def _print_help(self):
        """Print available commands."""
        print("\nAvailable Commands:")
        print("  help                    - Show this help message")
        print("  status                  - Show harness status")
        print("  play [fast]             - Start auto playback (optionally in fast mode)")
        print("  pause                   - Pause playback")
        print("  step                    - Step forward one bar")
        print("  jump <bar_idx>          - Jump to specific bar")
        print("  speed <multiplier>      - Set playback speed (e.g., 2.0 for 2x)")
        print("  reset                   - Reset to beginning")
        print("  events [count]          - Show recent events")
        print("  filter major            - Show major events only")
        print("  filter scale <S|M|L|XL> - Show events for specific scale")
        print("  export csv [file]       - Export events to CSV")
        print("  export json [file]      - Export events to JSON")
        print("  export summary [file]   - Export summary report")
        print("  quit                    - Exit harness")
    
    def _cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up harness...")
        
        if self.playback_controller:
            self.playback_controller.stop_playback()
        
        if self.visualization_renderer:
            self.visualization_renderer.set_interactive_mode(False)
        
        plt.close('all')


def setup_signal_handlers(harness):
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}. Shutting down gracefully...")
        harness.is_running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_argument_parser():
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Interactive Market Data Visualization Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --data test.csv
  %(prog)s --data market_data.csv --session analysis_001
  %(prog)s --data data.csv --auto-start --speed 2.0
  %(prog)s --data data.csv --export-only summary.txt
        """
    )
    
    parser.add_argument(
        '--data', '-d',
        required=True,
        help='Path to OHLC CSV data file'
    )
    
    parser.add_argument(
        '--session', '-s',
        help='Session identifier (default: auto-generated)'
    )
    
    parser.add_argument(
        '--auto-start',
        action='store_true',
        help='Start playback automatically'
    )
    
    parser.add_argument(
        '--speed',
        type=float,
        default=1.0,
        help='Playback speed multiplier (default: 1.0)'
    )
    
    parser.add_argument(
        '--fast-mode',
        action='store_true',
        help='Start in fast playback mode'
    )
    
    parser.add_argument(
        '--export-only',
        help='Export mode: run analysis and export to specified file, then exit'
    )
    
    parser.add_argument(
        '--max-bars',
        type=int,
        help='Maximum number of bars to process'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser


def main():
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate data file
    if not Path(args.data).exists():
        print(f"Error: Data file '{args.data}' not found")
        sys.exit(1)
    
    # Create configuration overrides
    config_overrides = {}
    if args.speed != 1.0:
        config_overrides['playback'] = {'auto_speed_ms': int(1000 / args.speed)}
    
    # Initialize harness
    try:
        harness = VisualizationHarness(
            data_file=args.data,
            session_id=args.session,
            config_overrides=config_overrides
        )
        
        # Setup signal handlers
        setup_signal_handlers(harness)
        
        # Initialize components
        if not harness.initialize():
            print("Failed to initialize harness")
            sys.exit(1)
        
        # Handle export-only mode
        if args.export_only:
            print("Running in export-only mode...")
            
            # Process all data
            total_bars = len(harness.bars)
            if args.max_bars:
                total_bars = min(total_bars, args.max_bars)
            
            print(f"Processing {total_bars} bars...")
            for i in range(total_bars):
                if i % 1000 == 0:
                    print(f"  Processed {i}/{total_bars} bars ({i/total_bars*100:.1f}%)")
                harness._on_playback_step(i, [])
            
            # Export results
            print(f"Exporting results to {args.export_only}...")
            success = harness.event_logger.export_summary_report(args.export_only)
            if success:
                print("Export completed successfully")
            else:
                print("Export failed")
                sys.exit(1)
            
            return
        
        # Handle auto-start
        if args.auto_start:
            mode = PlaybackMode.FAST if args.fast_mode else PlaybackMode.AUTO
            harness.playback_controller.start_playback(mode)
        
        # Run interactive mode
        harness.run_interactive()
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()