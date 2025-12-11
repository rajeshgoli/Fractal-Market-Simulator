"""
Historical Data Loader

Provides enhanced data loading functionality for systematic validation of swing detection
logic across diverse historical market datasets.

Features:
- Date range filtering for historical analysis
- Multi-resolution support (1m, 5m, 1d)
- Automatic dataset discovery and validation
- Graceful error handling for missing data

Author: Generated for Market Simulator Project
"""

import os
import glob
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Import existing components
from .ohlc_loader import load_ohlc
from ..swing_analysis.bull_reference_detector import Bar

logger = logging.getLogger(__name__)


def load_historical_data(
    symbol: str,
    resolution: str,
    start_date: datetime,
    end_date: datetime,
    data_folder: str = "Data/Historical"
) -> List[Bar]:
    """
    Load historical data for specified symbol, resolution, and date range.
    
    Args:
        symbol: Market symbol (e.g., "ES", "NQ")
        resolution: Data resolution ("1m", "5m", "1d")
        start_date: Start date for data filtering
        end_date: End date for data filtering
        data_folder: Base folder containing historical data
        
    Returns:
        List of Bar objects within specified date range
        
    Raises:
        FileNotFoundError: No data files found for symbol/resolution
        ValueError: Invalid date range or resolution
        RuntimeError: Data loading or processing errors
    """
    # Validate inputs
    if start_date >= end_date:
        raise ValueError("Start date must be before end date")
    
    if resolution not in ["1m", "5m", "1d"]:
        raise ValueError(f"Invalid resolution '{resolution}'. Must be one of: 1m, 5m, 1d")
    
    # Find data files
    data_files = discover_historical_files(symbol, resolution, data_folder)
    if not data_files:
        raise FileNotFoundError(
            f"No {resolution} data files found for symbol '{symbol}' in '{data_folder}'"
        )
    
    # Load and filter data
    all_bars = []
    loading_stats = {
        'files_loaded': 0,
        'files_skipped': 0,
        'total_bars_before_dedup': 0,
        'bars_from_files': []  # List of (filename, bar_count) tuples
    }

    for file_path in data_files:
        try:
            df, gaps = load_ohlc(file_path)

            # Filter by date range
            mask = (df.index >= start_date) & (df.index <= end_date)
            filtered_df = df[mask]

            if len(filtered_df) == 0:
                loading_stats['files_skipped'] += 1
                continue

            # Convert to Bar objects
            file_bars = []
            for bar_index, (idx, row) in enumerate(filtered_df.iterrows()):
                bar = Bar(
                    index=bar_index,
                    timestamp=int(idx.timestamp()),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close'])
                )
                file_bars.append(bar)

            all_bars.extend(file_bars)
            loading_stats['files_loaded'] += 1
            loading_stats['bars_from_files'].append((os.path.basename(file_path), len(file_bars)))

        except Exception as e:
            # Log warning and continue with other files
            logger.warning(f"Failed to load {os.path.basename(file_path)}: {e}")
            loading_stats['files_skipped'] += 1
            continue

    if not all_bars:
        raise RuntimeError(
            f"No data loaded for {symbol} {resolution} between {start_date} and {end_date}"
        )

    loading_stats['total_bars_before_dedup'] = len(all_bars)

    # Sort by timestamp and remove duplicates across files
    all_bars.sort(key=lambda bar: bar.timestamp)

    # Remove duplicate timestamps (common when files have overlapping date ranges)
    seen_timestamps = set()
    unique_bars = []
    duplicates_removed = 0

    for bar in all_bars:
        if bar.timestamp not in seen_timestamps:
            seen_timestamps.add(bar.timestamp)
            unique_bars.append(bar)
        else:
            duplicates_removed += 1

    all_bars = unique_bars

    # Re-index bars after sorting and deduplication
    for i, bar in enumerate(all_bars):
        bar.index = i

    # Log aggregated summary of duplicate handling
    if duplicates_removed > 0:
        logger.info(
            f"Data loading summary for {symbol} {resolution}:\n"
            f"  Files loaded: {loading_stats['files_loaded']} "
            f"(skipped {loading_stats['files_skipped']} files outside date range)\n"
            f"  Total bars from files: {loading_stats['total_bars_before_dedup']:,}\n"
            f"  Duplicate timestamps removed: {duplicates_removed:,}\n"
            f"  Final unique bars: {len(all_bars):,}\n"
            f"  Note: Duplicates occur when multiple data files cover overlapping date ranges.\n"
            f"        This is expected behavior - first occurrence is kept for each timestamp."
        )
    else:
        logger.debug(
            f"Data loading summary: {loading_stats['files_loaded']} files, "
            f"{len(all_bars):,} bars (no duplicates)"
        )

    return all_bars


def discover_historical_files(
    symbol: str, 
    resolution: str, 
    data_folder: str
) -> List[str]:
    """
    Discover available historical data files for given symbol and resolution.
    
    Args:
        symbol: Market symbol
        resolution: Data resolution
        data_folder: Base data folder
        
    Returns:
        List of file paths matching the criteria
    """
    # Create folder path
    base_path = Path(data_folder)
    if not base_path.exists():
        # Try relative to current project
        base_path = Path(f"test_data")  # Fallback to test data
        if not base_path.exists():
            return []
    
    # Multiple possible naming patterns
    patterns = [
        f"{symbol}_{resolution}_*.csv",
        f"{symbol}-{resolution}_*.csv", 
        f"{symbol}_{resolution}.csv",
        f"{symbol}-{resolution}.csv",
        f"{symbol.lower()}_{resolution}_*.csv",
        f"{symbol.lower()}-{resolution}_*.csv",
        f"{symbol.lower()}_{resolution}.csv",
        f"{symbol.lower()}-{resolution}.csv"
    ]
    
    files = []
    for pattern in patterns:
        matches = glob.glob(str(base_path / pattern))
        files.extend(matches)
    
    # If no symbol-specific files, try generic files for test purposes
    if not files and base_path.name == "test_data":
        generic_patterns = ["*.csv"]
        for pattern in generic_patterns:
            matches = glob.glob(str(base_path / pattern))
            files.extend(matches)
    
    # Remove duplicates and sort
    files = list(set(files))
    files.sort()
    
    return files


def get_available_date_ranges(
    symbol: str,
    resolution: str, 
    data_folder: str = "Data/Historical"
) -> List[Tuple[datetime, datetime]]:
    """
    Get available date ranges for specified symbol and resolution.
    
    Args:
        symbol: Market symbol
        resolution: Data resolution
        data_folder: Base data folder
        
    Returns:
        List of (start_date, end_date) tuples for available data
    """
    data_files = discover_historical_files(symbol, resolution, data_folder)
    date_ranges = []
    
    for file_path in data_files:
        try:
            df, _ = load_ohlc(file_path)
            if len(df) > 0:
                start_date = df.index.min().to_pydatetime()
                end_date = df.index.max().to_pydatetime()
                date_ranges.append((start_date, end_date))
        except Exception:
            # Skip files that can't be loaded
            continue
    
    return date_ranges


def get_data_summary(symbol: str, resolution: Optional[str] = None, data_folder: str = "Data/Historical") -> dict:
    """
    Get comprehensive summary of available data for a symbol.
    
    Args:
        symbol: Market symbol
        resolution: Optional specific resolution filter
        data_folder: Base data folder
        
    Returns:
        Dictionary with data availability information
    """
    summary = {
        'symbol': symbol,
        'data_folder': data_folder,
        'resolutions': {},
        'total_files': 0,
        'errors': []
    }
    
    resolutions_to_check = [resolution] if resolution else ["1m", "5m", "1d"]
    
    for res in resolutions_to_check:
        try:
            data_files = discover_historical_files(symbol, res, data_folder)
            summary['total_files'] += len(data_files)
            
            if not data_files:
                summary['resolutions'][res] = {
                    'available': False,
                    'files': [],
                    'date_ranges': [],
                    'total_bars': 0,
                    'earliest': None,
                    'latest': None
                }
                continue
                
            date_ranges = []
            total_bars = 0
            earliest_date = None
            latest_date = None
            
            for file_path in data_files:
                try:
                    df, _ = load_ohlc(file_path)
                    if len(df) > 0:
                        file_start = df.index.min().to_pydatetime()
                        file_end = df.index.max().to_pydatetime()
                        date_ranges.append((file_start, file_end, len(df), os.path.basename(file_path)))
                        total_bars += len(df)
                        
                        if earliest_date is None or file_start < earliest_date:
                            earliest_date = file_start
                        if latest_date is None or file_end > latest_date:
                            latest_date = file_end
                            
                except Exception as e:
                    summary['errors'].append(f"Failed to read {os.path.basename(file_path)}: {e}")
                    
            summary['resolutions'][res] = {
                'available': len(date_ranges) > 0,
                'files': [os.path.basename(f) for f in data_files],
                'date_ranges': date_ranges,
                'total_bars': total_bars,
                'earliest': earliest_date,
                'latest': latest_date
            }
            
        except Exception as e:
            summary['errors'].append(f"Error checking {res} resolution: {e}")
            
    return summary


def format_data_summary(summary: dict, verbose: bool = False) -> str:
    """
    Format data summary for human-readable output.
    
    Args:
        summary: Data summary from get_data_summary()
        verbose: Include detailed file information
        
    Returns:
        Formatted string
    """
    lines = []
    lines.append(f"Data Summary for Symbol: {summary['symbol']}")
    lines.append(f"Data Folder: {summary['data_folder']}")
    lines.append(f"Total Files Found: {summary['total_files']}")
    lines.append("")
    
    if summary['errors']:
        lines.append("Errors:")
        for error in summary['errors']:
            lines.append(f"  - {error}")
        lines.append("")
    
    for resolution, info in summary['resolutions'].items():
        lines.append(f"Resolution: {resolution}")
        
        if not info['available']:
            lines.append(f"  Status: No data available")
            lines.append("")
            continue
            
        lines.append(f"  Status: Available")
        lines.append(f"  Files: {len(info['files'])}")
        lines.append(f"  Total Bars: {info['total_bars']:,}")
        
        if info['earliest'] and info['latest']:
            lines.append(f"  Date Range: {info['earliest'].strftime('%Y-%m-%d %H:%M:%S UTC')} to {info['latest'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
        if verbose and info['date_ranges']:
            lines.append(f"  File Details:")
            for start, end, bars, filename in info['date_ranges']:
                lines.append(f"    - {filename}: {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')} ({bars:,} bars)")
                
        lines.append("")
    
    return "\n".join(lines)


def validate_data_availability(
    symbol: str,
    resolution: str,
    start_date: datetime,
    end_date: datetime,
    data_folder: str = "Data/Historical"
) -> Tuple[bool, str]:
    """
    Validate that data is available for the specified parameters.
    
    Args:
        symbol: Market symbol
        resolution: Data resolution
        start_date: Start date
        end_date: End date
        data_folder: Base data folder
        
    Returns:
        Tuple of (is_available, enhanced_status_message)
    """
    try:
        # Check if any files exist
        data_files = discover_historical_files(symbol, resolution, data_folder)
        if not data_files:
            # Get summary for better error message
            summary = get_data_summary(symbol, data_folder=data_folder)
            available_resolutions = [r for r, info in summary['resolutions'].items() if info['available']]
            
            if available_resolutions:
                return False, (
                    f"No {resolution} data files found for {symbol}, but data is available for: {', '.join(available_resolutions)}.\n"
                    f"Run 'python3 -m src.cli.main list-data --symbol {symbol}' to see all available data."
                )
            else:
                return False, (
                    f"No data files found for {symbol} at any resolution.\n"
                    f"Check that data files exist in '{data_folder}' directory."
                )
        
        # Check date range availability
        date_ranges = get_available_date_ranges(symbol, resolution, data_folder)
        if not date_ranges:
            return False, f"No valid data found in {len(data_files)} {resolution} files for {symbol}"
        
        # Check if requested range overlaps with available data
        overlapping_ranges = []
        for available_start, available_end in date_ranges:
            if (start_date <= available_end and end_date >= available_start):
                overlapping_ranges.append((available_start, available_end))
                
        if overlapping_ranges:
            return True, f"Data available ({len(date_ranges)} file ranges found)"
        
        # Enhanced error message with available date ranges
        earliest_date = min(start for start, _ in date_ranges)
        latest_date = max(end for _, end in date_ranges)
        
        return False, (
            f"Requested range {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} "
            f"does not overlap with available {resolution} data for {symbol}.\n"
            f"Available data spans: {earliest_date.strftime('%Y-%m-%d %H:%M UTC')} to {latest_date.strftime('%Y-%m-%d %H:%M UTC')}.\n"
            f"Run 'python3 -m src.cli.main list-data --symbol {symbol} --resolution {resolution} --verbose' for detailed file information."
        )
        
    except Exception as e:
        return False, f"Validation error: {e}"