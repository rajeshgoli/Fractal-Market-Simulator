"""
Calibration functions for the DAG layer.

Provides batch processing of historical bars and DataFrame conversion utilities.
"""

from datetime import datetime
from typing import List, Tuple, Optional, Callable, TYPE_CHECKING

import pandas as pd

from ..swing_config import SwingConfig
from ..types import Bar
from ..events import SwingEvent

if TYPE_CHECKING:
    from .leg_detector import LegDetector


def calibrate(
    bars: List[Bar],
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple["LegDetector", List[SwingEvent]]:
    """
    Run detection on historical bars.

    This is process_bar() in a loop - guarantees identical behavior
    to incremental playback.

    Args:
        bars: Historical bars to process.
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> bars = [Bar(index=i, ...) for i in range(1000)]
        >>> detector, events = calibrate(bars)
        >>> print(f"Found {len(detector.state.active_legs)} active legs")
        >>> # Continue processing new bars
        >>> new_events = detector.process_bar(new_bar)

        >>> # With progress callback
        >>> def on_progress(current, total):
        ...     print(f"Processing bar {current}/{total}")
        >>> detector, events = calibrate(bars, progress_callback=on_progress)
    """
    # Import here to avoid circular import
    from .leg_detector import LegDetector

    config = config or SwingConfig.default()

    detector = LegDetector(config)
    all_events: List[SwingEvent] = []
    total = len(bars)

    for i, bar in enumerate(bars):
        # Process bar for DAG events (leg creation, pruning, invalidation)
        events = detector.process_bar(bar)
        all_events.extend(events)

        if progress_callback:
            progress_callback(i + 1, total)

    return detector, all_events


def dataframe_to_bars(df: pd.DataFrame) -> List[Bar]:
    """
    Convert DataFrame with OHLC columns to Bar list.

    Handles various column naming conventions commonly used in market data.

    Args:
        df: DataFrame with OHLC columns. Expects columns like:
            - open/Open, high/High, low/Low, close/Close
            - Optional: timestamp/date/time

    Returns:
        List of Bar objects suitable for process_bar() or calibrate().

    Example:
        >>> df = pd.read_csv("market_data.csv")
        >>> bars = dataframe_to_bars(df)
        >>> detector, events = calibrate(bars)
    """
    bars = []

    # Normalize column names to lowercase for consistent access
    col_map = {c.lower(): c for c in df.columns}

    for idx, row in df.iterrows():
        # Get timestamp - try various column names
        timestamp = None
        for ts_col in ["timestamp", "time", "date", "datetime"]:
            if ts_col in col_map:
                ts_value = row[col_map[ts_col]]
                # Convert to Unix timestamp if needed
                if isinstance(ts_value, (int, float)):
                    timestamp = float(ts_value)
                elif hasattr(ts_value, "timestamp"):
                    timestamp = ts_value.timestamp()
                break

        # Default timestamp if not found
        if timestamp is None:
            timestamp = 1700000000 + len(bars) * 60  # Generate sequential timestamps

        # Get OHLC values
        open_price = float(row[col_map.get("open", "open")])
        high_price = float(row[col_map.get("high", "high")])
        low_price = float(row[col_map.get("low", "low")])
        close_price = float(row[col_map.get("close", "close")])

        bars.append(
            Bar(
                index=idx if isinstance(idx, int) else len(bars),
                timestamp=int(timestamp),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
            )
        )

    return bars


def calibrate_from_dataframe(
    df: pd.DataFrame,
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple["LegDetector", List[SwingEvent]]:
    """
    Convenience wrapper for DataFrame input.

    Converts DataFrame to Bar list and runs calibration.

    Args:
        df: DataFrame with OHLC columns (open, high, low, close).
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> import pandas as pd
        >>> df = pd.read_csv("ES-5m.csv")
        >>> detector, events = calibrate_from_dataframe(df)
        >>> print(f"Detected {len(detector.state.active_legs)} active legs")
    """
    bars = dataframe_to_bars(df)
    return calibrate(bars, config, progress_callback)
