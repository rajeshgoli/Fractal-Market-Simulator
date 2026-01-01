#!/usr/bin/env python3
"""
Profile engulfed leg retention impact.

Compares:
1. Current behavior (immediate engulfed prune)
2. Delayed behavior (disable engulfed prune to simulate retention)

Metrics:
- Final active_legs count
- Peak leg count during processing
- Wall-clock time
- Engulfed prune event count
"""

import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.detection_config import DetectionConfig
from swing_analysis.dag.calibrate import calibrate
from swing_analysis.dag.leg_detector import LegDetector
from swing_analysis.types import Bar
from swing_analysis.events import LegPrunedEvent
from data.ohlc_loader import load_ohlc


@dataclass
class ProfileResult:
    """Results from a profiling run."""
    name: str
    wall_time_seconds: float
    final_leg_count: int
    peak_leg_count: int
    total_events: int
    engulfed_prune_count: int
    other_prune_count: int
    bars_processed: int


def load_bars(filepath: str, limit: int = None) -> List[Bar]:
    """Load bars from CSV file."""
    df, _ = load_ohlc(filepath)

    if limit:
        df = df.head(limit)

    bars = []
    for i, (timestamp, row) in enumerate(df.iterrows()):
        bars.append(Bar(
            index=i,
            timestamp=int(timestamp.timestamp()),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
        ))

    return bars


def run_profile(
    bars: List[Bar],
    config: DetectionConfig,
    name: str
) -> ProfileResult:
    """Run calibration and collect metrics."""

    detector = LegDetector(config)
    all_events = []
    peak_leg_count = 0

    start_time = time.perf_counter()

    for bar in bars:
        events = detector.process_bar(bar)
        all_events.extend(events)

        # Track peak
        current_count = len(detector.state.active_legs)
        if current_count > peak_leg_count:
            peak_leg_count = current_count

    elapsed = time.perf_counter() - start_time

    # Count prune events by reason
    engulfed_count = sum(
        1 for e in all_events
        if isinstance(e, LegPrunedEvent) and e.reason == "engulfed"
    )
    other_prune_count = sum(
        1 for e in all_events
        if isinstance(e, LegPrunedEvent) and e.reason != "engulfed"
    )

    return ProfileResult(
        name=name,
        wall_time_seconds=elapsed,
        final_leg_count=len(detector.state.active_legs),
        peak_leg_count=peak_leg_count,
        total_events=len(all_events),
        engulfed_prune_count=engulfed_count,
        other_prune_count=other_prune_count,
        bars_processed=len(bars),
    )


def main():
    # Data file - use 30m for reasonable size
    data_file = Path(__file__).parent.parent / "test_data" / "es-30m.csv"

    if not data_file.exists():
        print(f"Error: Data file not found: {data_file}")
        sys.exit(1)

    print(f"Loading data from {data_file}...")
    bars = load_bars(str(data_file))
    print(f"Loaded {len(bars):,} bars\n")

    # Config 1: Current behavior (engulfed prune enabled)
    config_current = DetectionConfig.default()

    # Config 2: Delayed behavior (engulfed prune disabled)
    config_delayed = DetectionConfig.default().with_prune_toggles(enable_engulfed_prune=False)

    print("=" * 70)
    print("PROFILING ENGULFED LEG RETENTION IMPACT")
    print("=" * 70)

    # Run both profiles
    print("\n[1/2] Running with IMMEDIATE engulfed pruning (current behavior)...")
    result_current = run_profile(bars, config_current, "Current (immediate prune)")

    print("[2/2] Running with DISABLED engulfed pruning (simulating max retention)...")
    result_delayed = run_profile(bars, config_delayed, "Delayed (no engulfed prune)")

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    def print_result(r: ProfileResult):
        print(f"\n{r.name}:")
        print(f"  Wall time:         {r.wall_time_seconds:.2f}s")
        print(f"  Bars processed:    {r.bars_processed:,}")
        print(f"  Final leg count:   {r.final_leg_count:,}")
        print(f"  Peak leg count:    {r.peak_leg_count:,}")
        print(f"  Engulfed prunes:   {r.engulfed_prune_count:,}")
        print(f"  Other prunes:      {r.other_prune_count:,}")
        print(f"  Total events:      {r.total_events:,}")

    print_result(result_current)
    print_result(result_delayed)

    # Comparison
    print("\n" + "=" * 70)
    print("COMPARISON (delayed vs current)")
    print("=" * 70)

    time_diff = result_delayed.wall_time_seconds - result_current.wall_time_seconds
    time_pct = (time_diff / result_current.wall_time_seconds) * 100

    leg_diff = result_delayed.final_leg_count - result_current.final_leg_count
    leg_pct = (leg_diff / max(result_current.final_leg_count, 1)) * 100

    peak_diff = result_delayed.peak_leg_count - result_current.peak_leg_count
    peak_pct = (peak_diff / max(result_current.peak_leg_count, 1)) * 100

    print(f"\n  Wall time change:      {time_diff:+.2f}s ({time_pct:+.1f}%)")
    print(f"  Final leg count change: {leg_diff:+,} ({leg_pct:+.1f}%)")
    print(f"  Peak leg count change:  {peak_diff:+,} ({peak_pct:+.1f}%)")
    print(f"\n  Engulfed prunes avoided: {result_current.engulfed_prune_count:,}")

    # Assessment
    print("\n" + "=" * 70)
    print("ASSESSMENT")
    print("=" * 70)

    if result_current.engulfed_prune_count == 0:
        print("\n  ⚠️  No engulfed prunes detected - check if feature is working")
    elif time_pct > 50:
        print(f"\n  ⚠️  Significant performance impact: {time_pct:.1f}% slower")
        print("     Consider if Reference Layer benefit justifies the cost")
    elif time_pct > 20:
        print(f"\n  ⚠️  Moderate performance impact: {time_pct:.1f}% slower")
        print("     May be acceptable with proper threshold tuning")
    else:
        print(f"\n  ✓  Minimal performance impact: {time_pct:.1f}% change")
        print("     Delayed engulfed pruning appears viable")


if __name__ == "__main__":
    main()
