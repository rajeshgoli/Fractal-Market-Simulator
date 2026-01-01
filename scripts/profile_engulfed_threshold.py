#!/usr/bin/env python3
"""
Sandbox profiler for engulfed threshold tuning.

Simulates threshold-based engulfed pruning by:
1. Running with engulfed pruning ENABLED (current behavior)
2. Capturing each engulfed leg's state at prune time
3. Analyzing: what threshold would have caught it? How quickly?

This avoids modifying core code while giving us the data we need.
"""

import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import defaultdict
from decimal import Decimal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.detection_config import DetectionConfig
from swing_analysis.dag.leg_detector import LegDetector
from swing_analysis.types import Bar
from swing_analysis.events import LegPrunedEvent
from data.ohlc_loader import load_ohlc


@dataclass
class EngulfedLegSnapshot:
    """Snapshot of a leg at engulfed prune time."""
    leg_id: str
    range: float
    max_origin_breach: float
    max_pivot_breach: float
    origin_breach_pct: float  # max_origin_breach / range
    pivot_breach_pct: float   # max_pivot_breach / range
    max_breach_pct: float     # max of the two
    bar_index: int


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


def run_with_engulfed_tracking(bars: List[Bar], config: DetectionConfig) -> List[EngulfedLegSnapshot]:
    """
    Run detection and capture snapshots of legs at engulfed prune time.

    We hook into the process by checking state before/after each bar.
    """
    detector = LegDetector(config)
    snapshots: List[EngulfedLegSnapshot] = []

    # Track legs we've seen
    seen_legs: Dict[str, dict] = {}

    for bar in bars:
        # Snapshot current legs before processing
        for leg in detector.state.active_legs:
            if leg.leg_id not in seen_legs:
                seen_legs[leg.leg_id] = {
                    'range': float(leg.range),
                    'last_origin_breach': leg.max_origin_breach,
                    'last_pivot_breach': leg.max_pivot_breach,
                }
            else:
                # Update breach tracking
                seen_legs[leg.leg_id]['last_origin_breach'] = leg.max_origin_breach
                seen_legs[leg.leg_id]['last_pivot_breach'] = leg.max_pivot_breach

        # Process bar
        events = detector.process_bar(bar)

        # Check for engulfed prunes
        for event in events:
            if isinstance(event, LegPrunedEvent) and event.reason == "engulfed":
                leg_id = event.leg_id
                if leg_id in seen_legs:
                    info = seen_legs[leg_id]
                    leg_range = info['range']
                    origin_breach = float(info['last_origin_breach'] or 0)
                    pivot_breach = float(info['last_pivot_breach'] or 0)

                    if leg_range > 0:
                        origin_pct = origin_breach / leg_range
                        pivot_pct = pivot_breach / leg_range
                        max_pct = max(origin_pct, pivot_pct)

                        snapshots.append(EngulfedLegSnapshot(
                            leg_id=leg_id,
                            range=leg_range,
                            max_origin_breach=origin_breach,
                            max_pivot_breach=pivot_breach,
                            origin_breach_pct=origin_pct,
                            pivot_breach_pct=pivot_pct,
                            max_breach_pct=max_pct,
                            bar_index=bar.index,
                        ))

    return snapshots


def analyze_thresholds(snapshots: List[EngulfedLegSnapshot]) -> None:
    """Analyze what thresholds would catch the engulfed legs."""

    if not snapshots:
        print("No engulfed legs captured!")
        return

    print(f"\nAnalyzed {len(snapshots):,} engulfed legs\n")

    # Threshold analysis
    thresholds = [0.0, 0.1, 0.236, 0.382, 0.5, 0.618, 1.0]

    print("=" * 70)
    print("THRESHOLD ANALYSIS")
    print("=" * 70)
    print("\nLegs that would be pruned at each threshold:")
    print("(Threshold = max(origin_breach, pivot_breach) / range)")
    print()

    cumulative = 0
    for thresh in thresholds:
        count = sum(1 for s in snapshots if s.max_breach_pct <= thresh)
        pct = (count / len(snapshots)) * 100
        delta = count - cumulative
        print(f"  {thresh:.3f}: {count:>6,} legs ({pct:>5.1f}%) — +{delta:,} from previous")
        cumulative = count

    # Range distribution of engulfed legs
    print("\n" + "=" * 70)
    print("RANGE DISTRIBUTION OF ENGULFED LEGS")
    print("=" * 70)

    ranges = [s.range for s in snapshots]
    ranges.sort()

    percentiles = [10, 25, 50, 75, 90, 95, 99]
    print("\nRange percentiles:")
    for p in percentiles:
        idx = int(len(ranges) * p / 100)
        val = ranges[min(idx, len(ranges) - 1)]
        print(f"  {p:>2}th percentile: {val:>10.2f} points")

    print(f"\n  Min:  {min(ranges):>10.2f}")
    print(f"  Max:  {max(ranges):>10.2f}")
    print(f"  Mean: {sum(ranges)/len(ranges):>10.2f}")

    # Breach distribution
    print("\n" + "=" * 70)
    print("BREACH DISTRIBUTION AT PRUNE TIME")
    print("=" * 70)

    max_breaches = [s.max_breach_pct for s in snapshots]
    max_breaches.sort()

    print("\nMax breach % percentiles (max of origin/pivot breach as % of range):")
    for p in percentiles:
        idx = int(len(max_breaches) * p / 100)
        val = max_breaches[min(idx, len(max_breaches) - 1)]
        print(f"  {p:>2}th percentile: {val:>6.1%}")

    # Small legs analysis
    print("\n" + "=" * 70)
    print("SMALL LEGS ANALYSIS")
    print("=" * 70)

    # Define "small" as bottom 50% by range
    median_range = ranges[len(ranges) // 2]
    small_legs = [s for s in snapshots if s.range <= median_range]
    large_legs = [s for s in snapshots if s.range > median_range]

    print(f"\nMedian range: {median_range:.2f} points")
    print(f"Small legs (≤ median): {len(small_legs):,}")
    print(f"Large legs (> median):  {len(large_legs):,}")

    # What threshold catches small vs large legs?
    print("\nSmall legs breach distribution:")
    small_breaches = sorted([s.max_breach_pct for s in small_legs])
    for p in [50, 90, 99]:
        if small_breaches:
            idx = int(len(small_breaches) * p / 100)
            val = small_breaches[min(idx, len(small_breaches) - 1)]
            print(f"  {p}th percentile breach: {val:.1%}")

    print("\nLarge legs breach distribution:")
    large_breaches = sorted([s.max_breach_pct for s in large_legs])
    for p in [50, 90, 99]:
        if large_breaches:
            idx = int(len(large_breaches) * p / 100)
            val = large_breaches[min(idx, len(large_breaches) - 1)]
            print(f"  {p}th percentile breach: {val:.1%}")

    # Recommendation
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)

    # Find threshold that catches 90% of legs
    target_pct = 0.90
    target_count = int(len(snapshots) * target_pct)

    sorted_snapshots = sorted(snapshots, key=lambda s: s.max_breach_pct)
    if target_count < len(sorted_snapshots):
        threshold_90 = sorted_snapshots[target_count].max_breach_pct
    else:
        threshold_90 = sorted_snapshots[-1].max_breach_pct

    # Find threshold for 95%
    target_95 = int(len(snapshots) * 0.95)
    if target_95 < len(sorted_snapshots):
        threshold_95 = sorted_snapshots[target_95].max_breach_pct
    else:
        threshold_95 = sorted_snapshots[-1].max_breach_pct

    print(f"\n  Threshold to catch 90% of engulfed legs: {threshold_90:.3f} ({threshold_90:.1%})")
    print(f"  Threshold to catch 95% of engulfed legs: {threshold_95:.3f} ({threshold_95:.1%})")

    # How does 0.236 perform?
    caught_at_236 = sum(1 for s in snapshots if s.max_breach_pct <= 0.236)
    pct_236 = (caught_at_236 / len(snapshots)) * 100
    retained_at_236 = len(snapshots) - caught_at_236

    print(f"\n  At 0.236 threshold:")
    print(f"    Caught: {caught_at_236:,} ({pct_236:.1f}%)")
    print(f"    Retained for Reference Layer: {retained_at_236:,} ({100-pct_236:.1f}%)")


def main():
    data_file = Path(__file__).parent.parent / "test_data" / "es-30m.csv"

    if not data_file.exists():
        print(f"Error: Data file not found: {data_file}")
        sys.exit(1)

    print(f"Loading data from {data_file}...")
    bars = load_bars(str(data_file))
    print(f"Loaded {len(bars):,} bars")

    config = DetectionConfig.default()

    print("\nRunning detection with engulfed tracking...")
    start = time.perf_counter()
    snapshots = run_with_engulfed_tracking(bars, config)
    elapsed = time.perf_counter() - start
    print(f"Completed in {elapsed:.1f}s")

    analyze_thresholds(snapshots)


if __name__ == "__main__":
    main()
