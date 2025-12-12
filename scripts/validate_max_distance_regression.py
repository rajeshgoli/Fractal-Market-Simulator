#!/usr/bin/env python3
"""
One-time throwaway script to validate max_pair_distance=2000 doesn't drop valid swings.

Compares swing detection results with and without max_pair_distance limit.
Expected runtime: 10s of minutes for 6M bars (O(N^2) without limit is slow).

DELETE THIS SCRIPT after validation completes - not permanent tooling.
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from src.data.ohlc_loader import load_ohlc
from src.swing_analysis.swing_detector import detect_swings


def format_reference(ref: dict) -> str:
    """Format a reference swing for display."""
    return f"H[{ref['high_bar_index']}]@{ref['high_price']:.2f} -> L[{ref['low_bar_index']}]@{ref['low_price']:.2f}"


def compare_references(ref1: dict, ref2: dict) -> bool:
    """Check if two references are the same."""
    return (ref1['high_bar_index'] == ref2['high_bar_index'] and
            ref1['low_bar_index'] == ref2['low_bar_index'] and
            ref1['high_price'] == ref2['high_price'] and
            ref1['low_price'] == ref2['low_price'])


def find_missing_references(full_refs: list, limited_refs: list) -> list:
    """Find references in full_refs that are not in limited_refs."""
    missing = []
    for ref in full_refs:
        found = any(compare_references(ref, lr) for lr in limited_refs)
        if not found:
            missing.append(ref)
    return missing


def run_validation(filepath: str, max_distance: int = 2000):
    """
    Run swing detection comparison.

    Args:
        filepath: Path to CSV data file
        max_distance: The max_pair_distance value being validated
    """
    print("=" * 70)
    print("REGRESSION VALIDATION: max_pair_distance heuristic")
    print("=" * 70)
    print()

    # Load data
    print(f"Loading data from: {filepath}")
    start = time.time()
    df, gaps = load_ohlc(filepath)
    load_time = time.time() - start
    print(f"Loaded {len(df):,} bars in {load_time:.1f}s")
    print()

    # Run raw detection (no filtering) - this is the true regression test
    # The filtering step is order-dependent and will differ when input sets differ
    print("Running swing detection WITHOUT max_pair_distance (baseline)...")
    print("  This may take several minutes for large datasets...")
    print("  (Using filter_redundant=False for accurate comparison)")
    start = time.time()
    result_full = detect_swings(df, lookback=5, filter_redundant=False, max_pair_distance=None)
    time_full = time.time() - start

    bull_full = result_full['bull_references']
    bear_full = result_full['bear_references']
    print(f"  Completed in {time_full:.1f}s")
    print(f"  Bull references: {len(bull_full)}")
    print(f"  Bear references: {len(bear_full)}")
    print()

    # Count references over the distance limit
    bull_over_limit = [r for r in bull_full if r['low_bar_index'] - r['high_bar_index'] > max_distance]
    bear_over_limit = [r for r in bear_full if r['high_bar_index'] - r['low_bar_index'] > max_distance]
    print(f"  References over {max_distance} bars apart:")
    print(f"    Bull: {len(bull_over_limit)}")
    print(f"    Bear: {len(bear_over_limit)}")
    print()

    # Run detection WITH max_pair_distance (optimized)
    print(f"Running swing detection WITH max_pair_distance={max_distance}...")
    start = time.time()
    result_limited = detect_swings(df, lookback=5, filter_redundant=False, max_pair_distance=max_distance)
    time_limited = time.time() - start

    bull_limited = result_limited['bull_references']
    bear_limited = result_limited['bear_references']
    print(f"  Completed in {time_limited:.1f}s")
    print(f"  Bull references: {len(bull_limited)}")
    print(f"  Bear references: {len(bear_limited)}")
    print()

    # Compare results
    print("=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)
    print()

    # Expected counts (full count minus those over the limit)
    expected_bull = len(bull_full) - len(bull_over_limit)
    expected_bear = len(bear_full) - len(bear_over_limit)

    print(f"Expected bull references (full - over_limit): {expected_bull}")
    print(f"Actual bull references with limit: {len(bull_limited)}")
    print(f"Expected bear references (full - over_limit): {expected_bear}")
    print(f"Actual bear references with limit: {len(bear_limited)}")
    print()

    # Check for exact match
    bull_match = expected_bull == len(bull_limited)
    bear_match = expected_bear == len(bear_limited)

    # Also verify the references within limit are identical
    # Filter out over-limit references from full results
    bull_within_limit = [r for r in bull_full if r['low_bar_index'] - r['high_bar_index'] <= max_distance]
    bear_within_limit = [r for r in bear_full if r['high_bar_index'] - r['low_bar_index'] <= max_distance]

    missing_bull = find_missing_references(bull_within_limit, bull_limited)
    missing_bear = find_missing_references(bear_within_limit, bear_limited)

    # Summary
    print(f"Bull references: {len(bull_limited)}/{len(bull_full)} ({len(bull_over_limit)} correctly dropped, {len(missing_bull)} unexpected)")
    print(f"Bear references: {len(bear_limited)}/{len(bear_full)} ({len(bear_over_limit)} correctly dropped, {len(missing_bear)} unexpected)")
    print()

    if bull_match and bear_match and not missing_bull and not missing_bear:
        print("=" * 70)
        print("RESULT: NO REGRESSION")
        print("=" * 70)
        print()
        print(f"max_pair_distance={max_distance} produces identical results.")
        print("All reference swings are within the distance limit.")
        print()
        print(f"Performance improvement: {time_full/time_limited:.1f}x faster")
        return True
    else:
        print("=" * 70)
        print("RESULT: REGRESSION DETECTED")
        print("=" * 70)
        print()

        if missing_bull:
            print(f"Missing bull references ({len(missing_bull)}):")
            for i, ref in enumerate(missing_bull[:10]):  # Show first 10
                distance = ref['low_bar_index'] - ref['high_bar_index']
                print(f"  {i+1}. {format_reference(ref)} (distance: {distance} bars)")
            if len(missing_bull) > 10:
                print(f"  ... and {len(missing_bull) - 10} more")
            print()

        if missing_bear:
            print(f"Missing bear references ({len(missing_bear)}):")
            for i, ref in enumerate(missing_bear[:10]):  # Show first 10
                distance = ref['high_bar_index'] - ref['low_bar_index']
                print(f"  {i+1}. {format_reference(ref)} (distance: {distance} bars)")
            if len(missing_bear) > 10:
                print(f"  ... and {len(missing_bear) - 10} more")
            print()

        # Analyze the distances of missing references
        all_missing = missing_bull + missing_bear
        if all_missing:
            distances = []
            for ref in missing_bull:
                distances.append(ref['low_bar_index'] - ref['high_bar_index'])
            for ref in missing_bear:
                distances.append(ref['high_bar_index'] - ref['low_bar_index'])

            print(f"Missing reference distances:")
            print(f"  Min: {min(distances)} bars")
            print(f"  Max: {max(distances)} bars")
            print(f"  Avg: {sum(distances)/len(distances):.0f} bars")

        return False


def main():
    """Main entry point."""
    # Default to the 6M bar dataset
    default_path = project_root / "test_data" / "es-1m.csv"

    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = str(default_path)

    if not Path(filepath).exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    # Optional: specify max_distance as second argument
    max_distance = 2000
    if len(sys.argv) > 2:
        max_distance = int(sys.argv[2])

    success = run_validation(filepath, max_distance)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
