"""
Main entry point for the Ground Truth Annotator.

Usage:
    python -m src.ground_truth_annotator.main --data test.csv --resolution 1m --window 50000
    python -m src.ground_truth_annotator.main --data es-1m.csv --port 8001 --scale S

Cascade mode (XL → L → M → S progression):
    python -m src.ground_truth_annotator.main --data test.csv --cascade
"""

import argparse
import logging
import random
import sys
import time

import uvicorn

from .api import app, init_app
from ..data.ohlc_loader import get_file_metrics
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


def parse_offset(offset_str: str, total_bars: int, window_size: int) -> int:
    """
    Parse offset argument, handling 'random' keyword.

    Args:
        offset_str: The offset value - either 'random' or an integer string
        total_bars: Total number of bars in the data file
        window_size: Number of bars in the window

    Returns:
        Integer offset into the data
    """
    if offset_str.lower() == 'random':
        max_offset = max(0, total_bars - window_size)
        return random.randint(0, max_offset) if max_offset > 0 else 0
    return int(offset_str)


def main():
    parser = argparse.ArgumentParser(
        description="Ground Truth Annotator - Two-click swing annotation tool"
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
        default="annotation_sessions",
        help="Directory for storing annotation sessions"
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
        default=50000,
        help="Total bars to work with (default: 50000)"
    )
    parser.add_argument(
        "--scale",
        type=str,
        default="S",
        choices=["S", "M", "L", "XL"],
        help="Scale to annotate (default: S)"
    )
    parser.add_argument(
        "--target-bars",
        type=int,
        default=200,
        help="Target bars to display in chart (default: 200)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--cascade",
        action="store_true",
        help="Enable XL → L → M → S cascade workflow (overrides --scale and --target-bars)"
    )
    parser.add_argument(
        "--offset",
        type=str,
        default="0",
        help="Start offset in bars. Use 'random' for random position, or integer for fixed offset (default: 0)"
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
    print("Ground Truth Annotator")
    print(f"{'='*60}")

    offset = 0  # Default offset
    try:
        metrics = get_file_metrics(args.data)

        # Calculate offset
        offset = parse_offset(args.offset, metrics.total_bars, args.window)

        print(f"Data file:   {args.data}")
        print(f"Resolution:  {args.resolution}")
        print(f"Total bars:  {format_number(metrics.total_bars)}")
        print(f"Window:      {format_number(args.window)} bars")
        print(f"Offset:      {format_number(offset)} {'(random)' if args.offset.lower() == 'random' else ''}")
        if args.cascade:
            print(f"Mode:        CASCADE (XL → L → M → S)")
        else:
            print(f"Scale:       {args.scale}")
            print(f"Target bars: {args.target_bars}")
        if metrics.first_timestamp and metrics.last_timestamp:
            print(f"Date range:  {metrics.first_timestamp.strftime('%Y-%m-%d')} to {metrics.last_timestamp.strftime('%Y-%m-%d')}")
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
            resolution_minutes=resolution_minutes,
            window_size=args.window,
            scale=args.scale,
            target_bars=args.target_bars,
            cascade=args.cascade,
            window_offset=offset
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
    print("\nOpen the URL above in your browser to start annotating.\n")

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
