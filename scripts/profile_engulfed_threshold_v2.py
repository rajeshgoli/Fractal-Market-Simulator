#!/usr/bin/env python3
"""
Simulate threshold-based engulfed pruning.

Instead of disabling engulfed pruning entirely, simulate:
- Prune when BOTH sides breached AND at least one exceeds threshold
"""

import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Set
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.detection_config import DetectionConfig
from swing_analysis.dag.leg_detector import LegDetector
from swing_analysis.dag.leg_pruner import LegPruner
from swing_analysis.dag.state import DetectorState
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


class ThresholdSimulator:
    """
    Wraps LegDetector to simulate threshold-based engulfed pruning.

    Intercepts the engulfed check and applies threshold logic.
    """

    def __init__(self, config: DetectionConfig, threshold: float):
        self.detector = LegDetector(config)
        self.threshold = threshold
        self.engulfed_retained: Set[str] = set()  # Legs retained due to threshold

    def process_bar(self, bar: Bar):
        """Process bar with threshold-aware engulfed pruning."""
        # Process normally
        events = self.detector.process_bar(bar)

        # Check active legs for engulfed-but-below-threshold
        # (These would have been pruned but we're simulating retention)
        for leg in self.detector.state.active_legs:
            if leg.max_origin_breach is not None and leg.max_pivot_breach is not None:
                # This leg is engulfed
                if leg.range > 0:
                    origin_pct = float(leg.max_origin_breach) / float(leg.range)
                    pivot_pct = float(leg.max_pivot_breach) / float(leg.range)
                    max_pct = max(origin_pct, pivot_pct)

                    if max_pct < self.threshold:
                        # Would be retained under threshold logic
                        self.engulfed_retained.add(leg.leg_id)
                    elif leg.leg_id in self.engulfed_retained:
                        # Was retained, now exceeds threshold
                        self.engulfed_retained.discard(leg.leg_id)

        return events

    @property
    def state(self):
        return self.detector.state


def run_comparison(bars: List[Bar], threshold: float):
    """Compare current vs threshold-based behavior."""

    # Current behavior
    config = DetectionConfig.default()
    detector_current = LegDetector(config)

    start = time.perf_counter()
    peak_current = 0
    for bar in bars:
        detector_current.process_bar(bar)
        peak_current = max(peak_current, len(detector_current.state.active_legs))
    time_current = time.perf_counter() - start

    # Threshold behavior (disable engulfed prune, track manually)
    config_no_engulf = config.with_prune_toggles(enable_engulfed_prune=False)
    detector_thresh = LegDetector(config_no_engulf)

    # Track engulfed legs and simulate threshold pruning
    engulfed_count = 0
    would_retain = 0
    would_prune = 0
    peak_with_threshold = 0
    simulated_active: Set[str] = set()

    start = time.perf_counter()
    for bar in bars:
        detector_thresh.process_bar(bar)

        # Simulate threshold-based pruning
        legs_to_remove = []
        for leg in detector_thresh.state.active_legs:
            if leg.max_origin_breach is not None and leg.max_pivot_breach is not None:
                # Engulfed
                if leg.range > 0:
                    origin_pct = float(leg.max_origin_breach) / float(leg.range)
                    pivot_pct = float(leg.max_pivot_breach) / float(leg.range)
                    max_pct = max(origin_pct, pivot_pct)

                    if max_pct >= threshold:
                        # Would be pruned with threshold
                        legs_to_remove.append(leg.leg_id)
                        would_prune += 1
                    else:
                        # Retained (below threshold)
                        simulated_active.add(leg.leg_id)

        # Count legs that would remain active
        active_count = sum(
            1 for leg in detector_thresh.state.active_legs
            if leg.leg_id not in legs_to_remove or leg.leg_id in simulated_active
        )
        # Actually, let's just count non-engulfed + engulfed-below-threshold
        non_engulfed = sum(
            1 for leg in detector_thresh.state.active_legs
            if leg.max_origin_breach is None or leg.max_pivot_breach is None
        )
        engulfed_below_thresh = sum(
            1 for leg in detector_thresh.state.active_legs
            if leg.max_origin_breach is not None and leg.max_pivot_breach is not None
            and leg.range > 0
            and max(float(leg.max_origin_breach), float(leg.max_pivot_breach)) / float(leg.range) < threshold
        )
        simulated_count = non_engulfed + engulfed_below_thresh
        peak_with_threshold = max(peak_with_threshold, simulated_count)

    time_thresh = time.perf_counter() - start

    # Final count with threshold
    final_non_engulfed = sum(
        1 for leg in detector_thresh.state.active_legs
        if leg.max_origin_breach is None or leg.max_pivot_breach is None
    )
    final_engulfed_below = sum(
        1 for leg in detector_thresh.state.active_legs
        if leg.max_origin_breach is not None and leg.max_pivot_breach is not None
        and leg.range > 0
        and max(float(leg.max_origin_breach), float(leg.max_pivot_breach)) / float(leg.range) < threshold
    )

    print(f"\n{'='*70}")
    print(f"THRESHOLD: {threshold}")
    print(f"{'='*70}")
    print(f"\nCurrent behavior (immediate engulfed prune):")
    print(f"  Wall time:       {time_current:.2f}s")
    print(f"  Final legs:      {len(detector_current.state.active_legs)}")
    print(f"  Peak legs:       {peak_current}")

    print(f"\nWith {threshold} threshold:")
    print(f"  Final legs:      {final_non_engulfed + final_engulfed_below} (non-engulfed: {final_non_engulfed}, engulfed below thresh: {final_engulfed_below})")
    print(f"  Peak legs:       {peak_with_threshold}")
    print(f"  Additional legs: +{(final_non_engulfed + final_engulfed_below) - len(detector_current.state.active_legs)}")

    overhead = peak_with_threshold - peak_current
    overhead_pct = (overhead / peak_current) * 100 if peak_current > 0 else 0
    print(f"\n  Peak overhead:   +{overhead} legs (+{overhead_pct:.1f}%)")


def main():
    data_file = Path(__file__).parent.parent / "test_data" / "es-30m.csv"

    print(f"Loading {data_file}...")
    bars = load_bars(str(data_file))
    print(f"Loaded {len(bars):,} bars")

    for threshold in [0.236, 0.382, 0.5]:
        run_comparison(bars, threshold)


if __name__ == "__main__":
    main()
