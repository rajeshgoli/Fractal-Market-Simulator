import pandas as pd
import numpy as np
from typing import Tuple, List, Optional, NamedTuple
import os
import logging
from datetime import datetime


class FileMetrics(NamedTuple):
    """Quick metrics about a data file without loading all data."""
    total_bars: int
    file_size_bytes: int
    format: str
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]


def get_file_metrics(filepath: str) -> FileMetrics:
    """
    Get quick metrics about a data file without loading all data.

    Uses line counting and sampling for speed. Target: <100ms for any file size.

    Args:
        filepath: Path to the CSV file.

    Returns:
        FileMetrics with total bars, file size, format, and date range.

    Raises:
        FileNotFoundError, ValueError.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValueError("File is empty")

    fmt = detect_format(filepath)

    # Count lines efficiently (excluding header for format_b)
    # Use buffered reading for speed
    line_count = 0
    with open(filepath, 'rb') as f:
        # Read in chunks for speed
        buf_size = 1024 * 1024  # 1MB chunks
        while True:
            buf = f.read(buf_size)
            if not buf:
                break
            line_count += buf.count(b'\n')

    # Adjust for header
    has_header = fmt == "format_b"
    total_bars = line_count - (1 if has_header else 0)

    # Sample first and last timestamps
    first_timestamp = None
    last_timestamp = None

    try:
        # Read first few rows to get first timestamp
        if fmt == "format_a":
            df_head = pd.read_csv(
                filepath, sep=';', header=None, nrows=2,
                names=['date', 'time', 'open', 'high', 'low', 'close', 'volume']
            )
            if len(df_head) > 0:
                datetime_str = df_head['date'].iloc[0] + ' ' + df_head['time'].iloc[0]
                first_timestamp = datetime.strptime(datetime_str, '%d/%m/%Y %H:%M:%S')
        else:  # format_b
            df_head = pd.read_csv(filepath, sep=',', nrows=2)
            df_head.columns = df_head.columns.str.lower()
            if 'time' in df_head.columns and len(df_head) > 0:
                first_timestamp = datetime.utcfromtimestamp(df_head['time'].iloc[0])

        # Read last few rows to get last timestamp (skip to near end)
        skip_rows = max(0, total_bars - 5) + (1 if has_header else 0)
        if fmt == "format_a":
            df_tail = pd.read_csv(
                filepath, sep=';', header=None, skiprows=skip_rows,
                names=['date', 'time', 'open', 'high', 'low', 'close', 'volume']
            )
            if len(df_tail) > 0:
                datetime_str = df_tail['date'].iloc[-1] + ' ' + df_tail['time'].iloc[-1]
                last_timestamp = datetime.strptime(datetime_str, '%d/%m/%Y %H:%M:%S')
        else:  # format_b
            df_tail = pd.read_csv(filepath, sep=',', skiprows=skip_rows)
            df_tail.columns = df_tail.columns.str.lower()
            if 'time' in df_tail.columns and len(df_tail) > 0:
                last_timestamp = datetime.utcfromtimestamp(df_tail['time'].iloc[-1])
    except (KeyError, ValueError, IndexError, pd.errors.EmptyDataError):
        # If timestamp extraction fails, continue without them
        pass

    return FileMetrics(
        total_bars=total_bars,
        file_size_bytes=file_size,
        format=fmt,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp
    )


def load_ohlc_window(
    filepath: str,
    start_row: int,
    num_rows: int
) -> Tuple[pd.DataFrame, List[Tuple[pd.Timestamp, pd.Timestamp, float]]]:
    """
    Load a window of OHLC data from a CSV file.

    Efficiently loads a specific range of rows for progressive loading.

    Args:
        filepath: Path to the CSV file.
        start_row: Starting row index (0-based, excluding header).
        num_rows: Number of rows to load.

    Returns:
        Tuple containing:
            - DataFrame with columns: timestamp, open, high, low, close, volume.
            - List of gaps (start, end, duration_minutes).

    Raises:
        FileNotFoundError, ValueError.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    fmt = detect_format(filepath)

    try:
        if fmt == "format_a":
            # No header, so skiprows is just start_row
            df = pd.read_csv(
                filepath,
                sep=';',
                header=None,
                skiprows=start_row,
                nrows=num_rows,
                names=['date', 'time', 'open', 'high', 'low', 'close', 'volume'],
                dtype={
                    'date': str, 'time': str,
                    'open': 'float64', 'high': 'float64', 'low': 'float64', 'close': 'float64',
                    'volume': 'int64'
                },
                engine='c'
            )

            # Parse datetime
            datetime_str = df['date'] + ' ' + df['time']
            df['timestamp'] = pd.to_datetime(datetime_str, format='%d/%m/%Y %H:%M:%S', utc=True)
            df.drop(columns=['date', 'time'], inplace=True)

        else:  # format_b
            # Has header, so skiprows includes header (row 0) + start_row data rows
            # But we need the header for column names, so read header separately
            df = pd.read_csv(
                filepath,
                sep=',',
                skiprows=range(1, start_row + 1) if start_row > 0 else None,
                nrows=num_rows,
                engine='c'
            )

            # Normalize column names
            df.columns = df.columns.str.lower()

            required = {'time', 'open', 'high', 'low', 'close'}
            if not required.issubset(df.columns):
                raise ValueError(f"Missing required columns. Found: {df.columns.tolist()}")

            if 'volume' not in df.columns:
                df['volume'] = 0
            else:
                df['volume'] = df['volume'].fillna(0).astype('int64')

            df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df.drop(columns=['time'], inplace=True)

            cols = ['open', 'high', 'low', 'close']
            for c in cols:
                df[c] = df[c].astype('float64')

    except (KeyError, ValueError, TypeError, pd.errors.ParserError) as e:
        raise ValueError(f"Error parsing file: {e}")

    # Reorder and set index
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    # Remove duplicates
    duplicate_timestamps = df.index.duplicated(keep='last')
    if duplicate_timestamps.any():
        df = df[~duplicate_timestamps]

    # Validation
    valid_ohlc = (
        (df['low'] <= df['open']) & (df['open'] <= df['high']) &
        (df['low'] <= df['close']) & (df['close'] <= df['high'])
    )
    valid_vol = df['volume'] >= 0
    valid_mask = valid_ohlc & valid_vol

    if not valid_mask.all():
        invalid_count = (~valid_mask).sum()
        total_count = len(df)
        if invalid_count / total_count > 0.01:
            raise ValueError(f"Too many invalid rows: {invalid_count}/{total_count}")
        df = df[valid_mask]

    # Gap detection (uses 1.5x expected interval as threshold)
    gaps = []
    if len(df) > 1:
        time_diff = df.index.to_series().diff()
        gap_threshold_minutes = 1.5  # Default for 1m data
        gap_mask = time_diff > pd.Timedelta(minutes=gap_threshold_minutes)
        gap_indices = df.index[gap_mask]

        for end_time in gap_indices:
            loc = df.index.get_loc(end_time)
            if isinstance(loc, slice):
                loc = loc.start
            if loc > 0:
                start_time = df.index[loc - 1]
                duration = (end_time - start_time).total_seconds() / 60.0
                gaps.append((start_time, end_time, duration))

    return df, gaps


def detect_format(filepath: str) -> str:
    """
    Detects the format of the CSV file.
    
    Args:
        filepath: Path to the CSV file.
        
    Returns:
        "format_a" for Semicolon-Separated Historical Data.
        "format_b" for TradingView Comma-Separated Data.
        
    Raises:
        ValueError: If format cannot be detected.
    """
    try:
        with open(filepath, 'r') as f:
            # Read first few lines to be robust against header comments
            lines = [f.readline() for _ in range(10)]
            lines = [line.strip() for line in lines if line.strip()]
            
            if not lines:
                raise ValueError("File is empty")
                
            first_line = lines[0]
            
            # Check for Format A (Semicolon)
            if ';' in first_line:
                return "format_a"
            
            # Check for Format B (Comma + Header or Unix Timestamp)
            if ',' in first_line:
                # Check for header
                if "time" in first_line.lower() and "open" in first_line.lower():
                    return "format_b"
                
                # Check for numeric first field (Unix timestamp)
                parts = first_line.split(',')
                if parts[0].replace('.', '', 1).isdigit():
                    return "format_b"
                    
            raise ValueError("Could not detect CSV format. Expected semicolon-separated historical format or comma-separated TradingView format.")
            
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    except PermissionError:
        raise PermissionError(f"Permission denied: {filepath}")

def load_ohlc(filepath: str) -> Tuple[pd.DataFrame, List[Tuple[pd.Timestamp, pd.Timestamp, float]]]:
    """
    Loads OHLC data from a CSV file into a standardized DataFrame.
    
    Args:
        filepath: Path to the CSV file.
        
    Returns:
        Tuple containing:
            - DataFrame with columns: timestamp, open, high, low, close, volume.
            - List of gaps (start, end, duration_minutes).
            
    Raises:
        FileNotFoundError, PermissionError, ValueError.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
        
    if os.path.getsize(filepath) == 0:
        raise ValueError("File is empty")

    fmt = detect_format(filepath)
    
    try:
        if fmt == "format_a":
            # Format A: DD/MM/YYYY;HH:MM:SS;Open;High;Low;Close;Volume
            # No header
            df = pd.read_csv(
                filepath,
                sep=';',
                header=None,
                names=['date', 'time', 'open', 'high', 'low', 'close', 'volume'],
                dtype={
                    'date': str, 'time': str, 
                    'open': 'float64', 'high': 'float64', 'low': 'float64', 'close': 'float64', 
                    'volume': 'int64'
                },
                engine='c'
            )
            
            # Parse datetime
            # Vectorized string concatenation and parsing is faster than parse_dates for custom format
            datetime_str = df['date'] + ' ' + df['time']
            df['timestamp'] = pd.to_datetime(datetime_str, format='%d/%m/%Y %H:%M:%S', utc=True)
            
            # Drop temp columns
            df.drop(columns=['date', 'time'], inplace=True)
            
        else: # format_b
            # Format B: time,open,high,low,close,Volume
            # Header present
            df = pd.read_csv(
                filepath,
                sep=',',
                engine='c'
            )
            
            # Normalize column names to lowercase
            df.columns = df.columns.str.lower()
            
            # Ensure required columns exist
            required = {'time', 'open', 'high', 'low', 'close'}
            if not required.issubset(df.columns):
                raise ValueError(f"Missing required columns. Found: {df.columns.tolist()}")
            
            # Handle volume
            if 'volume' not in df.columns:
                df['volume'] = 0
            else:
                df['volume'] = df['volume'].fillna(0).astype('int64') 
            
            # Parse timestamp (Unix epoch)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df.drop(columns=['time'], inplace=True)
            
            # Ensure dtypes
            cols = ['open', 'high', 'low', 'close']
            for c in cols:
                df[c] = df[c].astype('float64')
            # Volume is already handled and cast to int64 above
            # df['volume'] = df['volume'].astype('int64')

    except (KeyError, ValueError, TypeError, pd.errors.ParserError) as e:
        # Catch parsing errors
        raise ValueError(f"Error parsing file: {e}")

    # Reorder columns
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    
    # Set index
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    
    # Remove duplicate timestamps - keep last occurrence for more recent data
    # Note: Duplicates are common when loading from multiple overlapping data files
    # or when source data has been concatenated. The "last" occurrence is kept as it
    # typically represents the most recent/corrected data point.
    duplicate_timestamps = df.index.duplicated(keep='last')
    if duplicate_timestamps.any():
        duplicate_count = duplicate_timestamps.sum()
        total_count = len(df)
        logger = logging.getLogger(__name__)
        # Only log at DEBUG level to avoid spam; aggregated summary shown elsewhere
        logger.debug(
            f"Duplicate timestamps in {os.path.basename(filepath)}: "
            f"{duplicate_count} removed (kept last occurrence), "
            f"{total_count - duplicate_count} unique bars remaining"
        )
        df = df[~duplicate_timestamps]
    
    # Validation
    # low <= open <= high and low <= close <= high
    # volume >= 0
    
    valid_ohlc = (
        (df['low'] <= df['open']) & (df['open'] <= df['high']) &
        (df['low'] <= df['close']) & (df['close'] <= df['high'])
    )
    valid_vol = df['volume'] >= 0
    
    valid_mask = valid_ohlc & valid_vol
    
    if not valid_mask.all():
        invalid_count = (~valid_mask).sum()
        total_count = len(df)
        
        if invalid_count / total_count > 0.01:
            raise ValueError(f"Too many invalid rows: {invalid_count}/{total_count} ({invalid_count/total_count:.2%})")
            
        # Log warning about dropping invalid rows
        logger = logging.getLogger(__name__)
        logger.warning(f"Dropping {invalid_count} invalid OHLC row(s) from {filepath}")
        
        # Drop invalid
        df = df[valid_mask]

    # Gap Detection
    # Gap threshold is configurable based on source resolution
    # Default: > 1 minute for 1m data (backwards compatible)
    gaps = []
    if len(df) > 1:
        time_diff = df.index.to_series().diff()
        # Gap detection uses 1.5x the expected interval as threshold
        # For 1m data: gap if diff > 1.5 minutes
        # This can be overridden by passing resolution_minutes to load_ohlc_with_resolution()
        gap_threshold_minutes = 1.5  # Default for 1m data

        gap_mask = time_diff > pd.Timedelta(minutes=gap_threshold_minutes)
        gap_indices = df.index[gap_mask]
        
        for end_time in gap_indices:
            # Find start time (previous row)
            # This is slow if we iterate. Vectorized approach?
            # We can get the index location
            loc = df.index.get_loc(end_time)
            
            # Handle case where get_loc returns a slice (duplicate timestamps)
            if isinstance(loc, slice):
                # Use the first occurrence of the duplicate timestamp
                loc = loc.start
                
            # Ensure we don't go below index 0
            if loc > 0:
                start_time = df.index[loc - 1]
                duration = (end_time - start_time).total_seconds() / 60.0
                # Gap duration is the missing time.
                # If t1=10:00, t2=10:02. Diff is 2 min. Gap is 1 min (10:01 is missing).
                # Spec: "gap_duration_minutes".
                gaps.append((start_time, end_time, duration))

    return df, gaps
