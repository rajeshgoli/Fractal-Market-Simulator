import pandas as pd
import numpy as np
from typing import Tuple, List, Optional
import os
import logging
from datetime import datetime

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

    except Exception as e:
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
    # Gap > 1 minute
    gaps = []
    if len(df) > 1:
        time_diff = df.index.to_series().diff()
        # Expected diff is 1 minute (60 seconds)
        # Gap if diff > 1 minute + tolerance? Spec says "consecutive timestamps differ by more than 1 minute".
        # So > 60 seconds? Or > 1 minute interval?
        # "For 1-minute data, a gap is any period where consecutive timestamps differ by more than 1 minute."
        # So if diff is 2 minutes, that's a 1 minute gap (one missing bar).
        # Let's say threshold is > 65 seconds to be safe against minor jitter, or strict > 60s?
        # Spec implies strict.
        
        gap_mask = time_diff > pd.Timedelta(minutes=1)
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
