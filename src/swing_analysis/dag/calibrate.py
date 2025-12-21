"""
Calibration functions for the DAG layer.

Provides batch processing of historical bars and DataFrame conversion utilities.
"""

from datetime import datetime
from typing import List, Tuple, Optional, Callable, TYPE_CHECKING

import pandas as pd

from ..swing_config import SwingConfig
from ..types import Bar
from ..events import SwingEvent, SwingInvalidatedEvent, SwingCompletedEvent

if TYPE_CHECKING:
    from .leg_detector import LegDetector
    from ..reference_layer import ReferenceLayer


def calibrate(
    bars: List[Bar],
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    ref_layer: Optional["ReferenceLayer"] = None,
) -> Tuple["LegDetector", List[SwingEvent]]:
    """
    Run detection on historical bars.

    This is process_bar() in a loop - guarantees identical behavior
    to incremental playback.

    When a ReferenceLayer is provided, invalidation and completion checks
    are applied after each bar according to the Reference layer rules
    (tolerance-based invalidation for big swings, 2x completion for small swings).
    See Docs/Working/DAG_spec.md for the pipeline integration spec.

    Args:
        bars: Historical bars to process.
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.
        ref_layer: Optional ReferenceLayer for tolerance-based invalidation and
            completion. If provided, swings are pruned according to Reference
            layer rules during calibration (not just at response time).

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> bars = [Bar(index=i, ...) for i in range(1000)]
        >>> detector, events = calibrate(bars)
        >>> print(f"Found {len(detector.get_active_swings())} active swings")
        >>> # Continue processing new bars
        >>> new_events = detector.process_bar(new_bar)

        >>> # With progress callback
        >>> def on_progress(current, total):
        ...     print(f"Processing bar {current}/{total}")
        >>> detector, events = calibrate(bars, progress_callback=on_progress)

        >>> # With Reference layer for tolerance-based invalidation
        >>> from swing_analysis.reference_layer import ReferenceLayer
        >>> ref_layer = ReferenceLayer(config)
        >>> detector, events = calibrate(bars, ref_layer=ref_layer)
    """
    # Import here to avoid circular import
    from .leg_detector import LegDetector

    config = config or SwingConfig.default()

    detector = LegDetector(config)
    all_events: List[SwingEvent] = []
    total = len(bars)

    for i, bar in enumerate(bars):
        # Create timestamp for events
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # 1. Process bar for DAG events (formation, structural invalidation, level cross)
        events = detector.process_bar(bar)
        all_events.extend(events)

        # 2. Apply Reference layer invalidation/completion if provided (#175)
        if ref_layer is not None:
            active_swings = detector.get_active_swings()

            # Check invalidation (tolerance-based rules)
            invalidated = ref_layer.update_invalidation_on_bar(active_swings, bar)
            for swing, result in invalidated:
                swing.invalidate()
                all_events.append(SwingInvalidatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=swing.swing_id,
                    reason=f"reference_layer:{result.reason}",
                ))

            # Check completion (2x for small swings, big swings never complete)
            completed = ref_layer.update_completion_on_bar(active_swings, bar)
            for swing, result in completed:
                swing.complete()
                all_events.append(SwingCompletedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=swing.swing_id,
                    completion_price=result.completion_price,
                ))

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
    ref_layer: Optional["ReferenceLayer"] = None,
) -> Tuple["LegDetector", List[SwingEvent]]:
    """
    Convenience wrapper for DataFrame input.

    Converts DataFrame to Bar list and runs calibration.

    Args:
        df: DataFrame with OHLC columns (open, high, low, close).
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.
        ref_layer: Optional ReferenceLayer for tolerance-based invalidation and
            completion. If provided, swings are pruned according to Reference
            layer rules during calibration (not just at response time).

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> import pandas as pd
        >>> df = pd.read_csv("ES-5m.csv")
        >>> detector, events = calibrate_from_dataframe(df)
        >>> print(f"Detected {len(detector.get_active_swings())} active swings")

        >>> # With Reference layer for tolerance-based invalidation
        >>> from swing_analysis.reference_layer import ReferenceLayer
        >>> ref_layer = ReferenceLayer()
        >>> detector, events = calibrate_from_dataframe(df, ref_layer=ref_layer)
    """
    bars = dataframe_to_bars(df)
    return calibrate(bars, config, progress_callback, ref_layer)
