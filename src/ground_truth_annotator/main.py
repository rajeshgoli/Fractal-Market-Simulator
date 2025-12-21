"""
Main entry point for the Replay View Server.

Usage:
    python -m src.ground_truth_annotator.main --data test.csv --resolution 1m --window 50000
"""

import argparse
import logging
import random
import sys
import time
from datetime import datetime

import pandas as pd
import uvicorn

from .api import app, init_app
from ..data.ohlc_loader import get_file_metrics, load_ohlc

# Resolution constants (inlined from deleted resolution.py)
SUPPORTED_RESOLUTIONS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

RESOLUTION_TO_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def parse_resolution(resolution: str) -> int:
    """Parse resolution string to minutes."""
    if resolution not in RESOLUTION_TO_MINUTES:
        raise ValueError(
            f"Unsupported resolution: {resolution}. "
            f"Supported: {', '.join(SUPPORTED_RESOLUTIONS)}"
        )
    return RESOLUTION_TO_MINUTES[resolution]

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
        offset_str: Either 'random' or an integer string
        total_bars: Total number of bars in the data file
        window_size: Number of bars in the window

    Returns:
        Integer offset into the data
    """
    if offset_str.lower() == 'random':
        max_offset = max(0, total_bars - window_size)
        return random.randint(0, max_offset) if max_offset > 0 else 0
    return int(offset_str)


def parse_start_date(date_str: str) -> datetime:
    """
    Parse flexible date formats.

    Supported formats:
        - 2020-Jan-01, 2020-jan-01
        - 2020-01-01
        - 01-Jan-2020
        - Jan-01-2020

    Args:
        date_str: Date string in various formats

    Returns:
        datetime object

    Raises:
        ValueError: If date cannot be parsed
    """
    formats = [
        "%Y-%b-%d",    # 2020-Jan-01
        "%Y-%m-%d",    # 2020-01-01
        "%d-%b-%Y",    # 01-Jan-2020
        "%b-%d-%Y",    # Jan-01-2020
        "%Y/%m/%d",    # 2020/01/01
        "%m/%d/%Y",    # 01/01/2020
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(
        f"Could not parse date '{date_str}'. "
        f"Try formats like: 2020-Jan-01, 2020-01-01, 01-Jan-2020"
    )


def find_offset_for_date(data_file: str, start_date: datetime) -> int:
    """
    Find the bar index offset for a given start date.

    Args:
        data_file: Path to the OHLC data file
        start_date: Target start date

    Returns:
        Integer offset (bar index)

    Raises:
        ValueError: If no bars exist at or after the start date
    """
    df, _ = load_ohlc(data_file)

    if df.index.tz is not None:
        start_dt = pd.Timestamp(start_date, tz='UTC')
    else:
        start_dt = pd.Timestamp(start_date)

    mask = df.index >= start_dt
    if not mask.any():
        raise ValueError(
            f"No data found at or after {start_date.strftime('%Y-%m-%d')}. "
            f"Data range: {df.index.min()} to {df.index.max()}"
        )

    first_match_idx = df.index.get_indexer([df.index[mask][0]])[0]
    return int(first_match_idx)


def main():
    parser = argparse.ArgumentParser(
        description="Replay View Server - Swing detection with HierarchicalDetector"
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
        help="Total bars for calibration window (default: 50000)"
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
        "--offset",
        type=str,
        default="0",
        help="Start offset in bars. Use 'random' for random position, or integer (default: 0)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Filter data to start at this date. Formats: 2020-Jan-01, 2020-01-01. Overrides --offset."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["calibration", "dag"],
        default="calibration",
        help="Visualization mode: 'calibration' (default) for swing calibration, 'dag' for DAG build visualization"
    )

    args = parser.parse_args()

    # Parse resolution
    try:
        resolution_minutes = parse_resolution(args.resolution)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Print startup info
    print(f"\n{'='*60}")
    mode_label = "DAG Build" if args.mode == "dag" else "Calibration"
    print(f"Replay View Server — {mode_label} Mode")
    print(f"{'='*60}")

    offset = 0
    start_date_used = None
    try:
        metrics = get_file_metrics(args.data)

        if args.start_date:
            try:
                start_date_used = parse_start_date(args.start_date)
                offset = find_offset_for_date(args.data, start_date_used)
            except ValueError as e:
                logger.error(str(e))
                sys.exit(1)
        else:
            offset = parse_offset(args.offset, metrics.total_bars, args.window)

        print(f"Data file:   {args.data}")
        print(f"Resolution:  {args.resolution}")
        print(f"Total bars:  {format_number(metrics.total_bars)}")
        print(f"Window:      {format_number(args.window)} bars")
        if start_date_used:
            print(f"Start date:  {start_date_used.strftime('%Y-%m-%d')}")
            print(f"Offset:      {format_number(offset)} (from start date)")
        else:
            print(f"Offset:      {format_number(offset)} {'(random)' if args.offset.lower() == 'random' else ''}")
        print(f"Target bars: {args.target_bars}")
        if metrics.first_timestamp and metrics.last_timestamp:
            print(f"Date range:  {metrics.first_timestamp.strftime('%Y-%m-%d')} to {metrics.last_timestamp.strftime('%Y-%m-%d')}")
        print()
    except FileNotFoundError:
        logger.error(f"Data file not found: {args.data}")
        sys.exit(1)
    except (ValueError, OSError, pd.errors.ParserError) as e:
        logger.error(f"Failed to read file metrics: {e}")
        sys.exit(1)

    # Initialize the application
    start_time = time.time()
    try:
        init_app(
            data_file=args.data,
            resolution_minutes=resolution_minutes,
            window_size=args.window,
            target_bars=args.target_bars,
            window_offset=offset,
            mode=args.mode
        )
        init_time = time.time() - start_time
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}")
        sys.exit(1)
    except (ValueError, OSError, RuntimeError, TypeError) as e:
        logger.error(f"Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"Initialization: {init_time:.2f}s")
    print(f"Server:         http://{args.host}:{args.port}/replay")
    print(f"{'='*60}")
    print("\nOpen the URL above in your browser to start replay.\n")

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
