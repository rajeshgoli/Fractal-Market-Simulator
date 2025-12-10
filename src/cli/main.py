"""
Main CLI Module for Market Data Validation

Provides command-line interface for historical data validation and swing detection analysis.
Extends existing harness functionality with systematic validation capabilities.

Commands:
- harness: Run interactive visualization harness (existing functionality)
- list-data: List available historical data for specified symbol (aliases: describe, inspect)
- validate: Run systematic validation across historical data

Author: Generated for Market Simulator Project
"""

import argparse
import sys
import logging
from datetime import datetime
from pathlib import Path

# Project imports
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.cli.harness import VisualizationHarness
from src.data.loader import load_historical_data, validate_data_availability, get_data_summary, format_data_summary
from src.validation.session import ValidationSession
from src.validation.issue_catalog import ValidationIssue
from src.legacy.bull_reference_detector import Bar


def run_harness_command(args):
    """Run the existing visualization harness."""
    # Import and run existing harness functionality
    from src.cli.harness import main as harness_main
    
    # Override sys.argv to pass arguments to harness
    original_argv = sys.argv
    try:
        sys.argv = ['harness'] + args.harness_args
        harness_main()
    finally:
        sys.argv = original_argv


def run_list_data_command(args):
    """List available historical data for specified symbol."""
    try:
        summary = get_data_summary(
            symbol=args.symbol,
            resolution=args.resolution,
            data_folder=getattr(args, 'data_folder', 'Data/Historical')
        )
        
        output = format_data_summary(summary, verbose=args.verbose)
        print(output)
        
        # Return success/failure based on whether any data was found
        has_data = any(info['available'] for info in summary['resolutions'].values())
        return has_data
        
    except Exception as e:
        print(f"Error listing data: {e}")
        return False


def run_validation_command(args):
    """Run systematic validation across historical data."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting validation for {args.symbol} {args.resolution}")
    logger.info(f"Date range: {args.start} to {args.end}")
    
    try:
        # Parse dates with timezone awareness
        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')
        
        # Make dates timezone-aware to match data
        from datetime import timezone
        start_date = start_date.replace(tzinfo=timezone.utc)
        end_date = end_date.replace(tzinfo=timezone.utc)
        
        # Validate data availability
        is_available, message = validate_data_availability(
            args.symbol, args.resolution, start_date, end_date
        )
        
        if not is_available:
            logger.error(f"Data validation failed: {message}")
            print(f"Error: {message}")
            return False
        
        logger.info(f"Data availability: {message}")
        
        # Load historical data with verbose logging if requested
        if args.verbose:
            print(f"Loading {args.symbol} {args.resolution} data from {args.start} to {args.end}...")
            summary = get_data_summary(args.symbol, args.resolution)
            if summary['resolutions'].get(args.resolution, {}).get('available'):
                res_info = summary['resolutions'][args.resolution]
                print(f"Found {len(res_info['files'])} data files:")
                for start, end, bars, filename in res_info['date_ranges']:
                    print(f"  - {filename}: {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')} ({bars:,} bars)")
        else:
            print(f"Loading {args.symbol} {args.resolution} data from {args.start} to {args.end}...")
            
        bars = load_historical_data(args.symbol, args.resolution, start_date, end_date)
        if args.verbose:
            print(f"Loaded {len(bars)} bars after date filtering")
            if bars:
                first_bar = datetime.fromtimestamp(bars[0].timestamp)
                last_bar = datetime.fromtimestamp(bars[-1].timestamp)
                print(f"Filtered data range: {first_bar.strftime('%Y-%m-%d %H:%M:%S UTC')} to {last_bar.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print(f"Loaded {len(bars)} bars")
        
        # Initialize validation session
        session = ValidationSession(
            symbol=args.symbol,
            resolution=args.resolution,
            start_date=start_date,
            end_date=end_date
        )
        
        # Create validation harness with historical data
        validation_harness = ValidationHarness(
            bars=bars,
            session=session,
            auto_pause=args.auto_pause
        )
        
        # Run validation
        success = validation_harness.run_validation()
        
        if success:
            # Export findings if requested
            if args.output:
                session.export_findings(args.output)
                print(f"Validation findings exported to {args.output}")
            
            print("Validation completed successfully")
            return True
        else:
            print("Validation failed")
            return False
            
    except Exception as e:
        logger.error(f"Validation error: {e}")
        print(f"Error: {e}")
        return False


class ValidationHarness:
    """Specialized harness for systematic validation."""
    
    def __init__(self, bars, session, auto_pause=True):
        """
        Initialize validation harness.
        
        Args:
            bars: List of Bar objects to validate
            session: ValidationSession instance
            auto_pause: Enable auto-pause on major events
        """
        self.bars = bars
        self.session = session
        self.auto_pause = auto_pause
        self.logger = logging.getLogger(__name__)
        
        # Initialize core harness with minimal config
        self.core_harness = None
        
    def run_validation(self) -> bool:
        """
        Run systematic validation process.
        
        Returns:
            True if validation completed successfully
        """
        try:
            self.session.start_session(
                symbol=self.session.symbol,
                date_range=(self.session.start_date, self.session.end_date)
            )
            
            # Create temporary data file for harness
            temp_file = self._create_temp_data_file()
            
            # Initialize core harness
            self.core_harness = VisualizationHarness(
                data_file=temp_file,
                session_id=f"validation_{self.session.session_id}",
                config_overrides={'playback': {'auto_speed_ms': 100}}
            )
            
            if not self.core_harness.initialize():
                self.logger.error("Failed to initialize validation harness")
                return False
            
            # Run validation interactively or automatically
            return self._run_validation_process()
            
        except Exception as e:
            self.logger.error(f"Validation run error: {e}")
            return False
        finally:
            self._cleanup()
    
    def _create_temp_data_file(self) -> str:
        """Create temporary CSV file with validation data."""
        import tempfile
        import csv
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        
        # Write CSV header
        writer = csv.writer(temp_file)
        writer.writerow(['time', 'open', 'high', 'low', 'close'])
        
        # Write bar data
        for bar in self.bars:
            writer.writerow([bar.timestamp, bar.open, bar.high, bar.low, bar.close])
        
        temp_file.close()
        return temp_file.name
    
    def _run_validation_process(self) -> bool:
        """Run the validation process with expert interaction."""
        self._print_startup_message()
        
        # Override harness event callback to capture issues
        original_callback = self.core_harness._on_playback_step
        
        def validation_callback(bar_idx, recent_events):
            # Call original processing
            original_callback(bar_idx, recent_events)
            
            # Check for auto-pause conditions
            if self.auto_pause and recent_events:
                major_events = [e for e in recent_events if e.severity.value == 'major']
                if major_events:
                    self.core_harness.playback_controller.pause_playback(
                        f"Auto-paused: {major_events[0].event_type.value} event"
                    )
                    print(f"\\nAuto-paused at bar {bar_idx} for expert review")
                    self._prompt_for_issue_logging(bar_idx, major_events)
        
        self.core_harness._on_playback_step = validation_callback
        
        # Run interactive validation
        return self._run_interactive_validation()
    
    def _run_interactive_validation(self) -> bool:
        """Run interactive validation with expert input."""
        try:
            while True:
                try:
                    command = input("\\nvalidation> ").strip().lower()
                    
                    if self._handle_validation_command(command):
                        continue
                    else:
                        break
                        
                except KeyboardInterrupt:
                    print("\\nUse 'quit' to exit properly")
                except EOFError:
                    break
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Interactive validation error: {e}")
            return False
    
    def _handle_validation_command(self, command: str) -> bool:
        """
        Handle validation-specific commands.
        
        Returns:
            True to continue, False to exit
        """
        parts = command.split()
        if not parts:
            return True
        
        cmd = parts[0]
        
        # Delegate standard playback commands to harness
        if cmd in ['play', 'pause', 'step', 'jump', 'speed', 'status']:
            self.core_harness._handle_command(command)
            return True
        
        # Handle validation-specific commands
        elif cmd == 'log':
            self._handle_log_command(parts[1:])
            return True
        
        elif cmd in ['quit', 'exit', 'q']:
            return False
        
        elif cmd in ['help', 'h', '?']:
            self._print_validation_help()
            return True
        
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")
            return True
    
    def _handle_log_command(self, args: list):
        """Handle issue logging command."""
        if not args:
            print("Usage: log <issue_type> [description]")
            print("Issue types: accuracy, level, event, consistency, performance")
            return
        
        issue_type = args[0]
        description = " ".join(args[1:]) if len(args) > 1 else ""
        
        if not description:
            description = input("Issue description: ").strip()
        
        if description:
            current_bar_idx = self.core_harness.current_bar_idx
            current_bar = self.bars[current_bar_idx]
            timestamp = datetime.fromtimestamp(current_bar.timestamp)
            
            self.session.log_issue(timestamp, issue_type, description)
            print(f"Logged {issue_type} issue at bar {current_bar_idx}")
        else:
            print("Issue logging cancelled")
    
    def _prompt_for_issue_logging(self, bar_idx: int, events: list):
        """Prompt expert to log issues during auto-pause."""
        print(f"Major events detected:")
        for event in events:
            print(f"  - {event.event_type.value} on {event.scale}-scale")
        
        response = input("Log issue? (y/n/description): ").strip()
        
        if response.lower() in ['y', 'yes']:
            self._handle_log_command(['accuracy'])
        elif response and response.lower() not in ['n', 'no']:
            # Use response as description
            timestamp = datetime.fromtimestamp(self.bars[bar_idx].timestamp)
            self.session.log_issue(timestamp, 'accuracy', response)
            print(f"Logged issue at bar {bar_idx}")
    
    def _print_startup_message(self):
        """Print clear startup message explaining what happened and what to do."""
        print("\n" + "=" * 70)
        print("VALIDATION SESSION STARTED")
        print("=" * 70)
        print()
        print("What just happened:")
        print("  - Historical data loaded and processed")
        print("  - Scale calibration complete (S, M, L, XL boundaries computed)")
        print("  - Swing state manager initialized")
        print("  - 4-panel visualization window launched (check for matplotlib window)")
        print()
        print("What you should see:")
        print("  - A matplotlib window with 4 panels showing different scales")
        print("  - Each panel displays OHLC candlesticks with Fibonacci level overlays")
        print("  - The visualization updates as you step through the data")
        print()
        print("Core workflow:")
        print("  1. Use 'step' to advance one bar at a time and watch swings update")
        print("  2. Use 'play' for auto-advance (pauses on major events)")
        print("  3. Use 'log <type>' to record any detection issues you observe")
        print("  4. Use 'quit' when done to export your findings")
        print()
        print("Quick start: Type 'step' to see the first bar, or 'play' to auto-advance.")
        print("Type 'help' at any time for full command reference.")
        print("=" * 70)
        print()

    def _print_validation_help(self):
        """Print validation-specific help."""
        print("\n" + "=" * 70)
        print("VALIDATION HARNESS HELP")
        print("=" * 70)
        print()
        print("PLAYBACK COMMANDS:")
        print("  play              Start auto-playback (pauses on major events)")
        print("  play fast         Start fast playback mode")
        print("  pause             Pause playback")
        print("  step [N]          Step forward N bars (default: 1)")
        print("  jump <bar_idx>    Jump to specific bar index")
        print("  speed <mult>      Set playback speed multiplier (e.g., 2.0)")
        print("  status            Show current position and harness state")
        print()
        print("VALIDATION COMMANDS:")
        print("  log <type> [desc] Log a validation issue at current bar")
        print("  help, h, ?        Show this help message")
        print("  quit, exit, q     End validation and save session")
        print()
        print("ISSUE TYPES for 'log' command:")
        print("  accuracy          Swing identification errors (wrong high/low)")
        print("  level             Fibonacci level computation problems")
        print("  event             Completion/invalidation trigger issues")
        print("  consistency       Multi-scale relationship problems")
        print("  performance       Response time or memory issues")
        print()
        print("EXAMPLE WORKFLOWS:")
        print()
        print("  Manual review:")
        print("    validation> step 50        # Advance 50 bars")
        print("    validation> step           # Advance 1 bar")
        print("    validation> log accuracy   # Log issue if swing looks wrong")
        print()
        print("  Auto-play review:")
        print("    validation> play           # Start auto-advance")
        print("    [system auto-pauses on major events]")
        print("    validation> log level Issue with 1.618 calculation")
        print("    validation> play           # Resume")
        print()
        print("=" * 70)
    
    def _cleanup(self):
        """Clean up validation resources."""
        if self.core_harness:
            self.core_harness._cleanup()


def create_parser():
    """Create argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="Market Data Validation and Visualization CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Harness subcommand (existing functionality)
    harness_parser = subparsers.add_parser(
        'harness',
        help='Run interactive visualization harness'
    )
    harness_parser.add_argument(
        'harness_args',
        nargs='*',
        help='Arguments to pass to harness (see harness --help)'
    )
    
    # List-data subcommand (data discovery)
    list_data_parser = subparsers.add_parser(
        'list-data',
        help='List available historical data for specified symbol',
        aliases=['describe', 'inspect']
    )
    list_data_parser.add_argument(
        '--symbol',
        default='ES',
        help='Market symbol (default: ES)'
    )
    list_data_parser.add_argument(
        '--resolution',
        choices=['1m', '5m', '1d'],
        help='Filter by specific resolution (default: show all)'
    )
    list_data_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed file information'
    )
    
    # Validate subcommand (new functionality)
    validate_parser = subparsers.add_parser(
        'validate',
        help='Run systematic validation across historical data'
    )
    validate_parser.add_argument(
        '--symbol',
        default='ES',
        help='Market symbol (default: ES)'
    )
    validate_parser.add_argument(
        '--resolution',
        choices=['1m', '5m', '1d'],
        required=True,
        help='Data resolution'
    )
    validate_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD format)'
    )
    validate_parser.add_argument(
        '--end', 
        required=True,
        help='End date (YYYY-MM-DD format)'
    )
    validate_parser.add_argument(
        '--auto-pause',
        action='store_true',
        default=True,
        help='Enable auto-pause on major events (default: true)'
    )
    validate_parser.add_argument(
        '--output',
        help='Output file for validation findings'
    )
    validate_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    
    # If no command specified, show help
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    if args.command == 'harness':
        run_harness_command(args)
    elif args.command in ['list-data', 'describe', 'inspect']:
        success = run_list_data_command(args)
        sys.exit(0 if success else 1)
    elif args.command == 'validate':
        success = run_validation_command(args)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()