#!/usr/bin/env python3
"""
Architect Profiling Script

Measures performance bottlenecks for the visualization harness with realistic data sizes.
Target: Profile with 100K+ bars of ES 1m data.
"""

import cProfile
import pstats
import io
import time
import sys
import os
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.ohlc_loader import load_ohlc
from src.analysis.scale_calibrator import ScaleCalibrator
from src.analysis.bar_aggregator import BarAggregator
from src.analysis.swing_state_manager import SwingStateManager
from src.analysis.event_detector import EventDetector
from src.legacy.bull_reference_detector import Bar
import pandas as pd


def measure_time(func, *args, **kwargs):
    """Measure execution time of a function."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def df_to_bars(df: pd.DataFrame, limit: int = None) -> list:
    """Convert DataFrame to list of Bar objects."""
    bars = []
    if limit:
        df = df.head(limit)
    for idx, row in df.iterrows():
        # idx is the timestamp (from index)
        ts = int(idx.timestamp()) if hasattr(idx, 'timestamp') else int(idx)
        bar = Bar(
            index=len(bars),
            timestamp=ts,
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )
        bars.append(bar)
    return bars


def profile_data_loading(filepath: str, limit: int = None):
    """Profile OHLC data loading."""
    print(f"\n{'='*60}")
    print("PROFILING: Data Loading")
    print(f"{'='*60}")

    result, load_elapsed = measure_time(load_ohlc, filepath)
    df, gaps = result
    print(f"  CSV load time: {load_elapsed*1000:.1f}ms")

    bars, elapsed = measure_time(df_to_bars, df, limit)

    print(f"  Bars loaded: {len(bars):,}")
    print(f"  Time: {elapsed*1000:.1f}ms")
    print(f"  Rate: {len(bars)/elapsed:,.0f} bars/sec")

    return bars


def profile_scale_calibration(bars):
    """Profile scale calibration."""
    print(f"\n{'='*60}")
    print("PROFILING: Scale Calibration")
    print(f"{'='*60}")

    calibrator = ScaleCalibrator()
    config, elapsed = measure_time(calibrator.calibrate, bars, "ES")

    print(f"  Swings found: {config.swing_count}")
    print(f"  Used defaults: {config.used_defaults}")
    print(f"  Time: {elapsed*1000:.1f}ms")
    print(f"  Boundaries: {config.boundaries}")

    return config


def profile_bar_aggregation(bars):
    """Profile bar aggregation initialization."""
    print(f"\n{'='*60}")
    print("PROFILING: Bar Aggregation (Initialization)")
    print(f"{'='*60}")

    aggregator, elapsed = measure_time(BarAggregator, bars)

    print(f"  Source bars: {aggregator.source_bar_count:,}")
    print(f"  Time: {elapsed*1000:.1f}ms")

    # Show compression ratios
    info = aggregator.get_aggregation_info()
    for tf, tf_info in info['timeframes'].items():
        print(f"  {tf}m: {tf_info['bar_count']:,} bars (ratio: {tf_info['compression_ratio']:.1f}x)")

    return aggregator


def profile_swing_state_manager_init(bars, scale_config):
    """Profile swing state manager initialization."""
    print(f"\n{'='*60}")
    print("PROFILING: Swing State Manager (Initialization)")
    print(f"{'='*60}")

    manager = SwingStateManager(scale_config)
    _, elapsed = measure_time(manager.initialize_with_bars, bars)

    counts = manager.get_swing_counts()
    total_active = sum(c['active'] for c in counts.values())

    print(f"  Time: {elapsed*1000:.1f}ms")
    print(f"  Total active swings: {total_active}")
    for scale, c in counts.items():
        print(f"    {scale}: {c['active']} active")

    return manager


def profile_per_bar_update(manager, bars, num_bars=1000):
    """Profile per-bar update performance."""
    print(f"\n{'='*60}")
    print(f"PROFILING: Per-Bar Updates ({num_bars} bars)")
    print(f"{'='*60}")

    # Start from middle of dataset
    start_idx = len(bars) // 2
    end_idx = min(start_idx + num_bars, len(bars))
    actual_bars = end_idx - start_idx

    times = []
    event_counts = []

    for i in range(start_idx, end_idx):
        bar = bars[i]
        start = time.perf_counter()
        result = manager.update_swings(bar, i)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)  # ms
        event_counts.append(len(result.events))

    avg_time = sum(times) / len(times)
    max_time = max(times)
    min_time = min(times)
    p95_time = sorted(times)[int(len(times) * 0.95)]
    total_events = sum(event_counts)

    print(f"  Bars processed: {actual_bars}")
    print(f"  Avg time/bar: {avg_time:.2f}ms")
    print(f"  P95 time/bar: {p95_time:.2f}ms")
    print(f"  Max time/bar: {max_time:.2f}ms")
    print(f"  Min time/bar: {min_time:.2f}ms")
    print(f"  Total events: {total_events}")
    print(f"  Target (<500ms): {'PASS' if p95_time < 500 else 'FAIL'}")

    # Estimate time for full month (30 trading days * 23 hours * 60 mins = 41,400 bars)
    bars_per_month = 41400
    estimated_month = (avg_time * bars_per_month) / 1000 / 60  # minutes
    print(f"\n  Estimated time for 1 month ({bars_per_month:,} bars): {estimated_month:.1f} minutes")


def profile_event_detection_isolated(bars, scale_config, num_bars=1000):
    """Profile event detection in isolation."""
    print(f"\n{'='*60}")
    print(f"PROFILING: Event Detection (Isolated, {num_bars} bars)")
    print(f"{'='*60}")

    # Create mock active swings
    from src.analysis.event_detector import ActiveSwing, EventDetector

    detector = EventDetector()

    # Create some test swings
    mock_swings = []
    for i in range(10):  # 10 active swings (typical S-scale scenario)
        swing = ActiveSwing(
            swing_id=f"test-{i}",
            scale="S",
            high_price=bars[i*100].high,
            low_price=bars[i*100].low,
            high_timestamp=bars[i*100].timestamp,
            low_timestamp=bars[i*100+10].timestamp,
            is_bull=True,
            state="active",
            levels={
                "0": bars[i*100].low,
                "0.382": bars[i*100].low + 0.382 * (bars[i*100].high - bars[i*100].low),
                "0.5": bars[i*100].low + 0.5 * (bars[i*100].high - bars[i*100].low),
                "0.618": bars[i*100].low + 0.618 * (bars[i*100].high - bars[i*100].low),
                "1": bars[i*100].high,
                "1.618": bars[i*100].low + 1.618 * (bars[i*100].high - bars[i*100].low),
                "2": bars[i*100].low + 2.0 * (bars[i*100].high - bars[i*100].low),
            }
        )
        mock_swings.append(swing)

    start_idx = len(bars) // 2
    times = []

    for i in range(start_idx, min(start_idx + num_bars, len(bars))):
        bar = bars[i]
        prev_bar = bars[i-1] if i > 0 else None

        start = time.perf_counter()
        events = detector.detect_events(bar, i, mock_swings, prev_bar)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    avg_time = sum(times) / len(times)
    max_time = max(times)

    print(f"  Active swings tested: {len(mock_swings)}")
    print(f"  Levels per swing: {len(mock_swings[0].levels)}")
    print(f"  Avg time/bar: {avg_time:.4f}ms")
    print(f"  Max time/bar: {max_time:.4f}ms")
    print(f"  Complexity: O(swings * levels) = O({len(mock_swings)} * {len(mock_swings[0].levels)}) = O({len(mock_swings) * len(mock_swings[0].levels)})")


def profile_swing_detection_standalone(bars, num_bars=100):
    """Profile the swing detection algorithm in isolation."""
    print(f"\n{'='*60}")
    print(f"PROFILING: Swing Detection (Standalone)")
    print(f"{'='*60}")

    import pandas as pd
    from src.legacy.swing_detector import detect_swings

    # Test with different data sizes
    test_sizes = [100, 500, 1000, 5000]

    for size in test_sizes:
        if size > len(bars):
            continue

        # Convert to DataFrame
        df_data = []
        for bar in bars[:size]:
            df_data.append({
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close
            })
        df = pd.DataFrame(df_data)

        # Time the detection
        start = time.perf_counter()
        result = detect_swings(df, lookback=5, filter_redundant=True)
        elapsed = time.perf_counter() - start

        bull_count = len(result.get('bull_references', []))
        bear_count = len(result.get('bear_references', []))
        highs = len(result.get('swing_highs', []))
        lows = len(result.get('swing_lows', []))

        print(f"\n  Size: {size} bars")
        print(f"    Time: {elapsed*1000:.1f}ms")
        print(f"    Swing highs: {highs}, Swing lows: {lows}")
        print(f"    Bull refs: {bull_count}, Bear refs: {bear_count}")
        print(f"    Rate: {size/elapsed:.0f} bars/sec")


def run_cprofile_analysis(bars, scale_config, num_bars=100):
    """Run cProfile to identify hotspots."""
    print(f"\n{'='*60}")
    print("PROFILING: cProfile Hotspot Analysis")
    print(f"{'='*60}")

    manager = SwingStateManager(scale_config)
    manager.initialize_with_bars(bars[:1000])  # Small init

    # Profile update loop
    pr = cProfile.Profile()
    pr.enable()

    start_idx = 1000
    for i in range(start_idx, min(start_idx + num_bars, len(bars))):
        manager.update_swings(bars[i], i)

    pr.disable()

    # Print stats
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(20)  # Top 20 functions
    print(s.getvalue())


def main():
    print("="*60)
    print("ARCHITECT PERFORMANCE PROFILE")
    print(f"Date: {datetime.now().isoformat()}")
    print("="*60)

    # Find ES 1m data file
    data_paths = [
        "test_data/es-1m.csv",
        "test_data/ES-1m.csv",
        "Data/Historical/ES-1m.csv",
        "Data/Historical/es-1m.csv",
        "test.csv"
    ]

    data_file = None
    for path in data_paths:
        if os.path.exists(path):
            data_file = path
            break

    if not data_file:
        print("ERROR: No ES data file found")
        return

    print(f"\nUsing data file: {data_file}")

    # Load data (limit to 150K for reasonable profiling time)
    bars = profile_data_loading(data_file, limit=150000)

    if len(bars) < 1000:
        print("ERROR: Insufficient data for profiling")
        return

    # Profile components
    scale_config = profile_scale_calibration(bars[:10000])  # Use subset for calibration
    aggregator = profile_bar_aggregation(bars)

    # Profile swing detection standalone
    profile_swing_detection_standalone(bars)

    # Profile swing state manager
    manager = profile_swing_state_manager_init(bars[:10000], scale_config)

    # Profile per-bar updates
    profile_per_bar_update(manager, bars, num_bars=500)

    # Profile event detection
    profile_event_detection_isolated(bars, scale_config)

    # cProfile hotspot analysis
    run_cprofile_analysis(bars, scale_config, num_bars=50)

    print(f"\n{'='*60}")
    print("PROFILING COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
