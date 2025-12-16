#!/usr/bin/env python3
"""
Discretizer Validation Script - Issue #79

Validates discretizer output on 3 representative date ranges:
- Sample 1: Trending (January 2017 uptrend)
- Sample 2: Ranging (July 2023 consolidation)
- Sample 3: Volatile (March 2020 COVID crash)

Outputs:
- Event logs saved to test_data/discretization_validation/
- Console summary of validation results
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from src.discretization import (
    Discretizer,
    DiscretizerConfig,
    write_log,
    read_log,
    EventType,
    validate_log,
)
from src.swing_analysis.swing_detector import detect_swings, ReferenceSwing


# Validation date ranges
DATE_RANGES = {
    "sample_1_trending": {
        "start": "2017-01-02",
        "end": "2017-01-31",
        "regime": "trending",
        "description": "January 2017 bull market uptrend",
    },
    "sample_2_ranging": {
        "start": "2023-07-01",
        "end": "2023-07-31",
        "regime": "ranging",
        "description": "July 2023 market consolidation",
    },
    "sample_3_volatile": {
        "start": "2020-03-01",
        "end": "2020-03-31",
        "regime": "volatile",
        "description": "March 2020 COVID crash",
    },
}

# Output directory
OUTPUT_DIR = Path("test_data/discretization_validation")


def load_es5m_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Load ES-5m data for a date range."""
    # Load full dataset
    df = pd.read_csv(
        "test_data/es-5m.csv",
        sep=";",
        header=None,
        names=["date", "time", "open", "high", "low", "close", "volume"],
    )

    # Parse datetime with dayfirst (DD/MM/YYYY format)
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"], dayfirst=True)

    # Filter to date range
    mask = (df["datetime"] >= start_date) & (df["datetime"] <= end_date)
    df = df[mask].copy()

    # Reset index and add timestamp column
    df = df.reset_index(drop=True)
    df["timestamp"] = df["datetime"].astype(np.int64) // 10**9  # Unix seconds

    return df


def run_swing_detection(df: pd.DataFrame) -> dict[str, list[ReferenceSwing]]:
    """Run swing detection for all scales."""
    # Create DataFrame with required columns
    ohlc = df[["open", "high", "low", "close"]].copy()

    # Scale-specific parameters from developer guide
    scale_params = {
        "XL": {"lookback": 60, "quota": 4},
        "L": {"lookback": 30, "quota": 6},
        "M": {"lookback": 15, "quota": 10},
        "S": {"lookback": 5, "quota": 15},
    }

    swings_by_scale = {}

    for scale, params in scale_params.items():
        result = detect_swings(
            ohlc,
            lookback=params["lookback"],
            filter_redundant=True,
            quota=params["quota"],
        )

        # Convert to ReferenceSwing objects
        swings = []
        for ref in result.get("bull_references", []):
            swings.append(ReferenceSwing(
                high_price=ref["high_price"],
                high_bar_index=ref["high_bar_index"],
                low_price=ref["low_price"],
                low_bar_index=ref["low_bar_index"],
                size=ref["size"],
                direction="bull",
                level_0382=ref.get("level_0382", 0.0),
                level_2x=ref.get("level_2x", 0.0),
                rank=ref.get("rank", 0),
            ))

        for ref in result.get("bear_references", []):
            swings.append(ReferenceSwing(
                high_price=ref["high_price"],
                high_bar_index=ref["high_bar_index"],
                low_price=ref["low_price"],
                low_bar_index=ref["low_bar_index"],
                size=ref["size"],
                direction="bear",
                level_0382=ref.get("level_0382", 0.0),
                level_2x=ref.get("level_2x", 0.0),
                rank=ref.get("rank", 0),
            ))

        swings_by_scale[scale] = swings

    return swings_by_scale


def validate_sample(sample_name: str, sample_config: dict) -> dict:
    """Validate discretizer on a single sample."""
    print(f"\n{'='*60}")
    print(f"Sample: {sample_name}")
    print(f"  Regime: {sample_config['regime']}")
    print(f"  Description: {sample_config['description']}")
    print(f"  Date range: {sample_config['start']} to {sample_config['end']}")
    print("="*60)

    # Load data
    print("\n[1] Loading OHLC data...")
    df = load_es5m_data(sample_config["start"], sample_config["end"])
    print(f"    Loaded {len(df)} bars")
    print(f"    Price range: {df['low'].min():.2f} - {df['high'].max():.2f}")

    # Run swing detection
    print("\n[2] Running swing detection...")
    swings_by_scale = run_swing_detection(df)
    for scale, swings in swings_by_scale.items():
        bull_count = sum(1 for s in swings if s.direction == "bull")
        bear_count = sum(1 for s in swings if s.direction == "bear")
        print(f"    {scale}: {len(swings)} swings ({bull_count} bull, {bear_count} bear)")

    # Run discretizer
    print("\n[3] Running discretizer...")
    discretizer = Discretizer()

    # Prepare OHLC DataFrame for discretizer
    ohlc_df = df[["timestamp", "open", "high", "low", "close"]].copy()

    log = discretizer.discretize(
        ohlc=ohlc_df,
        swings=swings_by_scale,
        instrument="ES",
        source_resolution="5m",
    )

    # Summarize events
    print(f"\n[4] Event summary:")
    print(f"    Total swings: {len(log.swings)}")
    print(f"    Total events: {len(log.events)}")

    # Count by event type
    event_counts = {}
    for event in log.events:
        event_type = event.event_type.value
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    for event_type, count in sorted(event_counts.items()):
        print(f"      {event_type}: {count}")

    # Validate log
    print("\n[5] Validating log schema...")
    errors = validate_log(log)
    if errors:
        print(f"    VALIDATION FAILED:")
        for error in errors:
            print(f"      - {error}")
    else:
        print("    PASSED - All validation checks passed")

    # Check config recording
    print("\n[6] Config verification:")
    print(f"    level_set_version: {log.meta.config.level_set_version}")
    print(f"    discretizer_version: {log.meta.config.discretizer_version}")
    print(f"    swing_detector_version: {log.meta.config.swing_detector_version}")
    print(f"    crossing_semantics: {log.meta.config.crossing_semantics}")
    print(f"    level_set: {log.meta.config.level_set}")

    # Analyze shock events
    print("\n[7] Shock event analysis:")
    shock_events = [e for e in log.events if e.shock and e.shock.levels_jumped >= 3]
    print(f"    Events with levels_jumped >= 3: {len(shock_events)}")

    high_range_events = [e for e in log.events if e.shock and e.shock.range_multiple > 2.0]
    print(f"    Events with range_multiple > 2.0: {len(high_range_events)}")

    gap_events = [e for e in log.events if e.shock and e.shock.is_gap]
    print(f"    Gap events: {len(gap_events)}")

    # Analyze effort annotations
    print("\n[8] Effort annotation analysis:")
    effort_events = [e for e in log.events if e.effort is not None]
    print(f"    Events with effort annotation: {len(effort_events)}")

    if effort_events:
        dwell_bars = [e.effort.dwell_bars for e in effort_events]
        print(f"    Dwell bars range: {min(dwell_bars)} - {max(dwell_bars)}")

        test_counts = [e.effort.test_count for e in effort_events if e.effort.test_count > 0]
        if test_counts:
            print(f"    Non-zero test_count events: {len(test_counts)}")

    # Analyze completions/invalidations
    print("\n[9] Completion/Invalidation analysis:")
    completions = [e for e in log.events if e.event_type == EventType.COMPLETION]
    invalidations = [e for e in log.events if e.event_type == EventType.INVALIDATION]
    print(f"    Completions: {len(completions)}")
    print(f"    Invalidations: {len(invalidations)}")

    # By scale
    for event_list, label in [(completions, "Completions"), (invalidations, "Invalidations")]:
        by_scale = {}
        for e in event_list:
            swing = next((s for s in log.swings if s.swing_id == e.swing_id), None)
            if swing:
                scale = swing.scale
                by_scale[scale] = by_scale.get(scale, 0) + 1
        if by_scale:
            print(f"    {label} by scale: {by_scale}")

    # Save log
    output_path = OUTPUT_DIR / f"{sample_name}.json"
    write_log(log, output_path)
    print(f"\n[10] Log saved to: {output_path}")

    # Verify we can read it back
    print("\n[11] Verifying read-back...")
    loaded_log = read_log(output_path)
    assert len(loaded_log.events) == len(log.events), "Event count mismatch"
    assert len(loaded_log.swings) == len(log.swings), "Swing count mismatch"
    print("    PASSED - Log can be read back correctly")

    return {
        "sample_name": sample_name,
        "bars": len(df),
        "swings": len(log.swings),
        "events": len(log.events),
        "event_counts": event_counts,
        "completions": len(completions),
        "invalidations": len(invalidations),
        "shock_events_3plus": len(shock_events),
        "gap_events": len(gap_events),
        "effort_events": len(effort_events),
        "validation_errors": errors,
    }


def main():
    print("Discretizer Validation - Issue #79")
    print(f"Output directory: {OUTPUT_DIR}")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    for sample_name, sample_config in DATE_RANGES.items():
        try:
            result = validate_sample(sample_name, sample_config)
            results[sample_name] = result
        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results[sample_name] = {"error": str(e)}

    # Summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)

    all_passed = True
    for sample_name, result in results.items():
        if "error" in result:
            print(f"\n{sample_name}: FAILED - {result['error']}")
            all_passed = False
        elif result.get("validation_errors"):
            print(f"\n{sample_name}: VALIDATION ERRORS")
            all_passed = False
        else:
            print(f"\n{sample_name}:")
            print(f"  Bars: {result['bars']}")
            print(f"  Swings: {result['swings']}")
            print(f"  Events: {result['events']}")
            print(f"  Completions: {result['completions']}")
            print(f"  Invalidations: {result['invalidations']}")
            print(f"  Shock events (3+ levels): {result['shock_events_3plus']}")
            print(f"  Gap events: {result['gap_events']}")

    print("\n" + "="*60)
    if all_passed:
        print("ALL SAMPLES PASSED VALIDATION")
    else:
        print("SOME SAMPLES FAILED - See details above")
    print("="*60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
