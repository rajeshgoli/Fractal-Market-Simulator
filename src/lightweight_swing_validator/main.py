"""
Main entry point for the lightweight swing validator.

Usage:
    python -m src.lightweight_swing_validator.main --data test_data/test.csv
    python -m src.lightweight_swing_validator.main --data test_data/es-1m.csv --port 8080
    python -m src.lightweight_swing_validator.main --data es-5m.csv --resolution 5m --window 50000
"""

import argparse
import logging
import sys
import time

import uvicorn

from .api import app, init_app
from ..data.ohlc_loader import get_file_metrics
from .progressive_loader import LARGE_FILE_THRESHOLD
from ..swing_analysis.resolution import SUPPORTED_RESOLUTIONS, parse_resolution

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def format_number(n: int) -> str:
    """Format large numbers with K/M suffixes."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def main():
    parser = argparse.ArgumentParser(
        description="Lightweight Swing Validator - Human-in-the-loop swing detection validation"
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to OHLC CSV data file"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run server on (default: 8000)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--storage-dir",
        default="validation_results",
        help="Directory for storing validation results"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible sampling"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default="1m",
        choices=SUPPORTED_RESOLUTIONS,
        help=f"Source data resolution (default: 1m). Supported: {', '.join(SUPPORTED_RESOLUTIONS)}"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help="Calibration window size in bars (default: auto based on resolution)"
    )

    args = parser.parse_args()

    # Parse resolution
    try:
        resolution_minutes = parse_resolution(args.resolution)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Quick file metrics first
    print(f"\n{'='*60}")
    print("Lightweight Swing Validator")
    print(f"{'='*60}")

    try:
        metrics = get_file_metrics(args.data)
        is_large = metrics.total_bars > LARGE_FILE_THRESHOLD

        print(f"Data file:   {args.data}")
        print(f"Resolution:  {args.resolution}")
        print(f"Total bars:  {format_number(metrics.total_bars)}")
        if args.window:
            print(f"Cal window:  {format_number(args.window)} bars")
        if metrics.first_timestamp and metrics.last_timestamp:
            print(f"Date range:  {metrics.first_timestamp.strftime('%Y-%m-%d')} to {metrics.last_timestamp.strftime('%Y-%m-%d')}")

        if is_large:
            print(f"\nLarge dataset detected ({format_number(metrics.total_bars)} bars)")
            print("Using progressive loading for fast startup...")
            print("(Additional time windows will load in background)")
        print()
    except FileNotFoundError:
        logger.error(f"Data file not found: {args.data}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to read file metrics: {e}")
        sys.exit(1)

    # Initialize the application
    start_time = time.time()
    try:
        init_app(
            data_file=args.data,
            storage_dir=args.storage_dir,
            seed=args.seed,
            resolution_minutes=resolution_minutes,
            calibration_window=args.window
        )
        init_time = time.time() - start_time
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Print startup message
    print(f"Initialization: {init_time:.2f}s")
    print(f"Server:         http://{args.host}:{args.port}")
    print(f"Storage:        {args.storage_dir}/")
    print(f"{'='*60}")
    print("\nOpen the URL above in your browser to start validating.\n")

    # Run the server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
