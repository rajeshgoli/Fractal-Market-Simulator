#!/usr/bin/env python3
"""
Simple overhead estimation for threshold-based engulfed pruning.

Uses current behavior + tracks how many legs would be in the "retained" window.
"""

import sys
import time
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.detection_config import DetectionConfig
from swing_analysis.dag.leg_detector import LegDetector
from swing_analysis.types import Bar
from swing_analysis.events import LegPrunedEvent
from data.ohlc_loader import load_ohlc


def load_bars(filepath: str) -> List[Bar]:
    df, _ = load_ohlc(filepath)
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


def run_analysis(bars: List[Bar], threshold: float):
    """
    Track what the overhead would be with threshold-based engulfed pruning.

    Strategy: For each engulfed prune event, check if max breach < threshold.
    If so, this leg would have been retained. Track how many such legs
    accumulate at any point.
    """
    config = DetectionConfig.default()
    detector = LegDetector(config)

    # Track legs before they're pruned so we can get their breach values
    leg_data: Dict[str, dict] = {}

    # Track "would-be-retained" legs
    retained_legs: Dict[str, int] = {}  # leg_id -> bar when it was engulfed
    peak_retained = 0
    total_would_retain = 0
    total_would_prune = 0

    for bar in bars:
        # Capture leg state before processing
        for leg in detector.state.active_legs:
            leg_data[leg.leg_id] = {
                'range': float(leg.range),
                'max_origin_breach': leg.max_origin_breach,
                'max_pivot_breach': leg.max_pivot_breach,
            }

        # Process bar
        events = detector.process_bar(bar)

        # Check engulfed prune events
        for event in events:
            if isinstance(event, LegPrunedEvent) and event.reason == "engulfed":
                leg_id = event.leg_id
                if leg_id in leg_data:
                    info = leg_data[leg_id]
                    leg_range = info['range']
                    origin_breach = float(info['max_origin_breach'] or 0)
                    pivot_breach = float(info['max_pivot_breach'] or 0)

                    if leg_range > 0:
                        max_pct = max(origin_breach, pivot_breach) / leg_range

                        if max_pct < threshold:
                            # Would be retained
                            retained_legs[leg_id] = bar.index
                            total_would_retain += 1
                        else:
                            # Would still be pruned
                            total_would_prune += 1

        # Update peak
        if len(retained_legs) > peak_retained:
            peak_retained = len(retained_legs)

        # Simulate: retained legs would eventually exceed threshold
        # For simplicity, assume they'd be pruned within ~50 bars on average
        # (This is a rough estimate - in reality they'd be pruned when breach exceeds threshold)
        stale_threshold = 50
        to_remove = [lid for lid, bar_idx in retained_legs.items()
                     if bar.index - bar_idx > stale_threshold]
        for lid in to_remove:
            del retained_legs[lid]

    return {
        'total_would_retain': total_would_retain,
        'total_would_prune': total_would_prune,
        'peak_retained': peak_retained,
        'final_retained': len(retained_legs),
    }


def main():
    data_file = Path(__file__).parent.parent / "test_data" / "es-30m.csv"

    print(f"Loading {data_file}...")
    bars = load_bars(str(data_file))
    print(f"Loaded {len(bars):,} bars\n")

    # Also get baseline
    config = DetectionConfig.default()
    detector = LegDetector(config)
    start = time.perf_counter()
    peak_baseline = 0
    for bar in bars:
        detector.process_bar(bar)
        peak_baseline = max(peak_baseline, len(detector.state.active_legs))
    elapsed = time.perf_counter() - start

    print(f"Baseline (current behavior):")
    print(f"  Wall time:    {elapsed:.2f}s")
    print(f"  Final legs:   {len(detector.state.active_legs)}")
    print(f"  Peak legs:    {peak_baseline}")

    for threshold in [0.236, 0.382, 0.5]:
        print(f"\n{'='*60}")
        print(f"Threshold: {threshold}")
        print(f"{'='*60}")

        result = run_analysis(bars, threshold)

        print(f"  Would retain (temporarily): {result['total_would_retain']:,}")
        print(f"  Would still prune:          {result['total_would_prune']:,}")
        print(f"  Peak concurrent retained:   {result['peak_retained']}")

        total = result['total_would_retain'] + result['total_would_prune']
        retain_pct = (result['total_would_retain'] / total * 100) if total > 0 else 0
        print(f"  Retention rate:             {retain_pct:.1f}%")

        overhead_pct = (result['peak_retained'] / peak_baseline * 100) if peak_baseline > 0 else 0
        print(f"\n  Peak overhead vs baseline:  +{result['peak_retained']} legs (+{overhead_pct:.1f}%)")


if __name__ == "__main__":
    main()
