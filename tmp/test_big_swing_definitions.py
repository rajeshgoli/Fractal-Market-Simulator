#!/usr/bin/env python3
"""
Empirical test: Compare big swing definitions.

Definition A (range-based): Top 10% by range - per valid_swings.md Rule 2.2
Definition B (hierarchy-based): No parents - current ReferenceLayer implementation

Run against 20 random 10K samples and report differences.
"""

import sys
import random
from pathlib import Path
from decimal import Decimal
from typing import List, Tuple, Dict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.hierarchical_detector import calibrate, HierarchicalDetector
from swing_analysis.swing_node import SwingNode
from swing_analysis.swing_config import SwingConfig
from swing_analysis.types import Bar


def generate_random_bars(n: int, seed: int) -> List[Bar]:
    """Generate n random OHLC bars with some trend structure."""
    random.seed(seed)
    bars = []
    price = 5000.0

    for i in range(n):
        # Random walk with some momentum
        change = random.gauss(0, 20)
        price = max(100, price + change)

        # Generate OHLC
        open_price = price + random.gauss(0, 5)
        high = max(open_price, price) + abs(random.gauss(0, 15))
        low = min(open_price, price) - abs(random.gauss(0, 15))
        close = price + random.gauss(0, 5)

        # Ensure OHLC validity
        high = max(high, open_price, close)
        low = min(low, open_price, close)

        bars.append(Bar(
            index=i,
            timestamp=1700000000 + i * 60,
            open=open_price,
            high=high,
            low=low,
            close=close,
        ))

    return bars


def is_big_by_range(swing: SwingNode, all_swings: List[SwingNode], threshold: float = 0.10) -> bool:
    """Definition A: Big if in top 10% by range."""
    if not all_swings:
        return False

    ranges = sorted([s.range for s in all_swings], reverse=True)
    cutoff_idx = max(0, int(len(ranges) * threshold) - 1)
    cutoff = ranges[cutoff_idx] if cutoff_idx < len(ranges) else Decimal("0")

    return swing.range >= cutoff


def is_big_by_hierarchy(swing: SwingNode) -> bool:
    """Definition B: Big if no parents (root level)."""
    return len(swing.parents) == 0


def compare_definitions(swings: List[SwingNode]) -> Dict:
    """Compare the two definitions on a set of swings."""
    results = {
        "total_swings": len(swings),
        "big_by_range": 0,
        "big_by_hierarchy": 0,
        "both_big": 0,
        "range_only": 0,
        "hierarchy_only": 0,
        "neither": 0,
        "disagreements": [],
    }

    for swing in swings:
        by_range = is_big_by_range(swing, swings)
        by_hierarchy = is_big_by_hierarchy(swing)

        if by_range:
            results["big_by_range"] += 1
        if by_hierarchy:
            results["big_by_hierarchy"] += 1

        if by_range and by_hierarchy:
            results["both_big"] += 1
        elif by_range and not by_hierarchy:
            results["range_only"] += 1
            results["disagreements"].append({
                "swing_id": swing.swing_id[:8],
                "range": float(swing.range),
                "depth": swing.get_depth(),
                "parents": len(swing.parents),
                "issue": "big by range but has parents"
            })
        elif by_hierarchy and not by_range:
            results["hierarchy_only"] += 1
            results["disagreements"].append({
                "swing_id": swing.swing_id[:8],
                "range": float(swing.range),
                "depth": swing.get_depth(),
                "parents": len(swing.parents),
                "issue": "root level but not top 10% by range"
            })
        else:
            results["neither"] += 1

    return results


def run_test():
    print("=" * 70)
    print("Big Swing Definition Comparison Test")
    print("=" * 70)
    print()
    print("Definition A (range-based): Top 10% by range - per valid_swings.md")
    print("Definition B (hierarchy-based): No parents - current ReferenceLayer")
    print()
    print("Running 20 random 1K bar samples...")
    print()

    config = SwingConfig.default()

    total_disagreements = 0
    total_swings = 0
    sample_results = []

    for sample_idx in range(20):
        seed = 42 + sample_idx
        bars = generate_random_bars(1000, seed)

        detector, events = calibrate(bars, config)
        swings = detector.state.active_swings

        results = compare_definitions(swings)
        sample_results.append(results)

        total_swings += results["total_swings"]
        disagreement_count = results["range_only"] + results["hierarchy_only"]
        total_disagreements += disagreement_count

        print(f"Sample {sample_idx + 1:2d} (seed={seed}): "
              f"{results['total_swings']:3d} swings, "
              f"{results['big_by_range']:3d} big(range), "
              f"{results['big_by_hierarchy']:3d} big(hierarchy), "
              f"{disagreement_count:3d} disagreements")

        # Show first few disagreements per sample
        if results["disagreements"][:2]:
            for d in results["disagreements"][:2]:
                print(f"    -> {d['swing_id']}: {d['issue']} "
                      f"(range={d['range']:.1f}, depth={d['depth']}, parents={d['parents']})")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    avg_swings = total_swings / 20
    avg_disagreements = total_disagreements / 20

    print(f"Average swings per sample: {avg_swings:.1f}")
    print(f"Average disagreements per sample: {avg_disagreements:.1f}")
    print(f"Total disagreements across all samples: {total_disagreements}")

    if total_disagreements > 0:
        print()
        print("IMPACT ANALYSIS:")
        print("-" * 40)

        # Count by type
        range_only_total = sum(r["range_only"] for r in sample_results)
        hierarchy_only_total = sum(r["hierarchy_only"] for r in sample_results)

        print(f"  Big by range but has parents: {range_only_total}")
        print(f"    -> These would get NO tolerance under hierarchy definition")
        print(f"    -> But SHOULD get tolerance per valid_swings.md")
        print()
        print(f"  Root level but not top 10% by range: {hierarchy_only_total}")
        print(f"    -> These would get tolerance under hierarchy definition")
        print(f"    -> But should NOT per valid_swings.md")
    else:
        print()
        print("No disagreements found - definitions are equivalent on test data.")

    print()
    print("=" * 70)
    print("RECOMMENDATION:")
    print("=" * 70)
    if total_disagreements > 0:
        print("Definitions produce DIFFERENT results.")
        print("Per valid_swings.md Rule 2.2, range-based (top 10%) is canonical.")
        print("ReferenceLayer._is_big_swing() should use range-based definition.")
    else:
        print("Definitions are equivalent on random data.")
        print("However, canonical definition is range-based per valid_swings.md.")


if __name__ == "__main__":
    run_test()
