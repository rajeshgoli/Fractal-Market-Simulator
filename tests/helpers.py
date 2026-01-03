"""
Shared test utilities for swing analysis tests.

These are plain utility functions, not pytest fixtures.
"""

from datetime import datetime
from decimal import Decimal
from typing import List

import pandas as pd

from src.swing_analysis.dag import HierarchicalDetector
from src.swing_analysis.detection_config import DetectionConfig
from src.swing_analysis.types import Bar


def batch_process_bars(bars: List[Bar], config: DetectionConfig = None):
    """
    Process bars through detector and return detector + all events.

    Args:
        bars: List of Bar objects to process
        config: Optional DetectionConfig (uses default if not provided)

    Returns:
        Tuple of (detector, all_events)
    """
    detector = HierarchicalDetector(config or DetectionConfig.default())
    all_events = []
    for bar in bars:
        events = detector.process_bar(bar)
        all_events.extend(events)
    return detector, all_events


def dataframe_to_bars(df: pd.DataFrame) -> List[Bar]:
    """
    Convert DataFrame with OHLC columns to Bar list.

    Args:
        df: DataFrame with columns for open, high, low, close.
            Optionally includes 'datetime' column for timestamps.

    Returns:
        List of Bar objects with sequential indices starting at 0.
    """
    bars = []
    col_map = {c.lower(): c for c in df.columns}

    for idx, row in df.iterrows():
        # Handle timestamp - prefer datetime column, fallback to index
        if 'datetime' in col_map:
            ts = row[col_map['datetime']]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            elif isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()
        elif isinstance(idx, (datetime, pd.Timestamp)):
            ts = idx if isinstance(idx, datetime) else idx.to_pydatetime()
        else:
            ts = datetime.now()

        # Ensure timestamp is a proper datetime, not pandas Timestamp
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()

        # Convert datetime to Unix timestamp (int) as Bar expects
        ts_int = int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts)

        bars.append(Bar(
            index=len(bars),
            timestamp=ts_int,
            open=Decimal(str(row[col_map.get('open', 'Open')])),
            high=Decimal(str(row[col_map.get('high', 'High')])),
            low=Decimal(str(row[col_map.get('low', 'Low')])),
            close=Decimal(str(row[col_map.get('close', 'Close')])),
        ))
    return bars
