#!/usr/bin/env python3
"""
Leg Investigation Harness

Reusable script for debugging leg detection issues. Tracks specific legs
through the detection process and logs breach tracking, formation, and
pruning events.

Usage:
    python scripts/investigate_leg.py --file test_data/es-5m.csv --offset 1172207 \
        --origin-price 4431.75 --origin-bar 203 --pivot-price 4427.25 --pivot-bar 206 \
        --direction bear --until-bar 270

    # Or use the config at the bottom of this file and run:
    python scripts/investigate_leg.py
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.ohlc_loader import load_ohlc_window
from swing_analysis.types import Bar
from swing_analysis.detection_config import DetectionConfig
from swing_analysis.dag.leg_detector import LegDetector
from swing_analysis.dag.leg import Leg


@dataclass
class LegTarget:
    """Specification of a leg to track."""
    direction: str  # 'bull' or 'bear'
    origin_price: Decimal
    origin_bar: int
    pivot_price: Decimal
    pivot_bar: int
    tolerance: Decimal = Decimal("0.5")  # Price tolerance for matching

    def matches(self, leg: Leg) -> bool:
        """Check if a leg matches this target specification."""
        if leg.direction != self.direction:
            return False
        if leg.origin_index != self.origin_bar:
            return False
        if abs(leg.origin_price - self.origin_price) > self.tolerance:
            return False
        # Pivot can extend, so just check it started at the right place
        # or is currently at the expected price
        if leg.pivot_index == self.pivot_bar or abs(leg.pivot_price - self.pivot_price) <= self.tolerance:
            return True
        return False


def find_matching_leg(legs: List[Leg], target: LegTarget) -> Optional[Leg]:
    """Find a leg matching the target specification."""
    for leg in legs:
        if target.matches(leg):
            return leg
    return None


def log_leg_state(bar_idx: int, leg: Leg, prefix: str = "") -> None:
    """Log the current state of a leg."""
    print(f"{prefix}Bar {bar_idx}: Leg {leg.leg_id[:8]}")
    print(f"  {prefix}Direction: {leg.direction}")
    print(f"  {prefix}Origin: {leg.origin_price} @ bar {leg.origin_index}")
    print(f"  {prefix}Pivot: {leg.pivot_price} @ bar {leg.pivot_index}")
    print(f"  {prefix}Range: {leg.range}")
    print(f"  {prefix}Status: {leg.status}")
    print(f"  {prefix}Formed: {leg.formed}")
    print(f"  {prefix}max_origin_breach: {leg.max_origin_breach}")
    print(f"  {prefix}max_pivot_breach: {leg.max_pivot_breach}")


def investigate(
    data_file: str,
    offset: int,
    target: LegTarget,
    until_bar: int = 300,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run the detector and track a specific leg through its lifecycle.

    Returns a summary dict with findings.
    """
    print(f"\n{'='*60}")
    print(f"LEG INVESTIGATION HARNESS")
    print(f"{'='*60}")
    print(f"Data file: {data_file}")
    print(f"Offset: {offset}")
    print(f"Target leg: {target.direction} origin={target.origin_price}@{target.origin_bar} "
          f"pivot={target.pivot_price}@{target.pivot_bar}")
    print(f"Running until bar: {until_bar}")
    print(f"{'='*60}\n")

    # Load data
    df, gaps = load_ohlc_window(data_file, offset, until_bar + 10)
    print(f"Loaded {len(df)} bars from offset {offset}")

    # Convert to Bar objects (timestamp is the index)
    bars = []
    for idx, (ts, row) in enumerate(df.iterrows()):
        bar = Bar(
            index=idx,
            timestamp=int(ts.timestamp()),
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
        )
        bars.append(bar)

    # Create detector
    config = DetectionConfig()
    detector = LegDetector(config)

    # Tracking variables
    findings = {
        "leg_found_at_bar": None,
        "leg_formed_at_bar": None,
        "origin_breach_at_bar": None,
        "origin_breach_value": None,
        "pivot_breach_at_bar": None,
        "pivot_breach_value": None,
        "leg_pruned_at_bar": None,
        "prune_reason": None,
        "final_state": None,
        "events": [],
    }

    tracked_leg_id: Optional[str] = None
    prev_formed = False
    prev_origin_breach = None
    prev_pivot_breach = None

    # Process bars
    for bar in bars:
        if bar.index > until_bar:
            break

        # Process the bar
        events = detector.process_bar(bar)

        # Debug: show legs created around target bars
        if verbose and bar.index in range(target.origin_bar - 2, target.pivot_bar + 5):
            print(f"\nBar {bar.index}: H={bar.high} L={bar.low} C={bar.close}")
            print(f"  Active {target.direction} legs:")
            for leg in detector.state.active_legs:
                if leg.direction == target.direction and leg.status == 'active':
                    print(f"    {leg.leg_id[:8]}: origin={leg.origin_price}@{leg.origin_index} "
                          f"pivot={leg.pivot_price}@{leg.pivot_index} formed={leg.formed}")

        # Log any relevant events
        for event in events:
            event_type = type(event).__name__
            if hasattr(event, 'leg_id'):
                findings["events"].append({
                    "bar": bar.index,
                    "type": event_type,
                    "leg_id": event.leg_id[:8] if event.leg_id else None,
                    "details": str(event),
                })
                if verbose and tracked_leg_id and event.leg_id == tracked_leg_id:
                    print(f"  EVENT @ bar {bar.index}: {event_type} - {event}")

        # Try to find our target leg
        leg = find_matching_leg(detector.state.active_legs, target)

        if leg is not None:
            # First time finding it?
            if tracked_leg_id is None:
                tracked_leg_id = leg.leg_id
                findings["leg_found_at_bar"] = bar.index
                print(f"\n>>> TARGET LEG FOUND at bar {bar.index} (ID: {leg.leg_id[:8]})")
                log_leg_state(bar.index, leg)

            # Track formation
            if not prev_formed and leg.formed:
                findings["leg_formed_at_bar"] = bar.index
                print(f"\n>>> LEG FORMED at bar {bar.index}")
                log_leg_state(bar.index, leg)
            prev_formed = leg.formed

            # Track origin breach
            if prev_origin_breach is None and leg.max_origin_breach is not None:
                findings["origin_breach_at_bar"] = bar.index
                findings["origin_breach_value"] = float(leg.max_origin_breach)
                print(f"\n>>> ORIGIN BREACH DETECTED at bar {bar.index}")
                print(f"    max_origin_breach = {leg.max_origin_breach}")
                print(f"    bar.high = {bar.high}, leg.origin = {leg.origin_price}")
                log_leg_state(bar.index, leg)
            elif leg.max_origin_breach != prev_origin_breach and leg.max_origin_breach is not None:
                print(f"    Bar {bar.index}: origin breach updated to {leg.max_origin_breach}")
            prev_origin_breach = leg.max_origin_breach

            # Track pivot breach
            if prev_pivot_breach is None and leg.max_pivot_breach is not None:
                findings["pivot_breach_at_bar"] = bar.index
                findings["pivot_breach_value"] = float(leg.max_pivot_breach)
                print(f"\n>>> PIVOT BREACH DETECTED at bar {bar.index}")
                print(f"    max_pivot_breach = {leg.max_pivot_breach}")
                print(f"    bar.low = {bar.low}, leg.pivot = {leg.pivot_price}")
                print(f"    leg.formed = {leg.formed}")
                log_leg_state(bar.index, leg)
            elif leg.max_pivot_breach != prev_pivot_breach and leg.max_pivot_breach is not None:
                print(f"    Bar {bar.index}: pivot breach updated to {leg.max_pivot_breach}")
            prev_pivot_breach = leg.max_pivot_breach

            # Verbose logging at key bars
            if verbose and bar.index in [target.origin_bar, target.pivot_bar,
                                          target.pivot_bar + 1, 210, 219, 240, 260, 261]:
                print(f"\n--- Bar {bar.index} state ---")
                print(f"    bar: O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
                log_leg_state(bar.index, leg, "    ")

        elif tracked_leg_id is not None:
            # Leg was being tracked but is now gone - it was pruned!
            findings["leg_pruned_at_bar"] = bar.index
            print(f"\n>>> LEG PRUNED at bar {bar.index}")
            print(f"    Last known state before pruning:")
            print(f"    max_origin_breach = {prev_origin_breach}")
            print(f"    max_pivot_breach = {prev_pivot_breach}")

            # Check events for prune reason
            for event in events:
                if hasattr(event, 'leg_id') and hasattr(event, 'reason'):
                    if event.leg_id == tracked_leg_id:
                        findings["prune_reason"] = event.reason
                        print(f"    Prune reason: {event.reason}")

            # Stop tracking
            tracked_leg_id = None

    # Final summary
    print(f"\n{'='*60}")
    print("INVESTIGATION SUMMARY")
    print(f"{'='*60}")

    if findings["leg_found_at_bar"] is not None:
        print(f"Leg found at bar: {findings['leg_found_at_bar']}")
        print(f"Leg formed at bar: {findings['leg_formed_at_bar']}")
        print(f"Origin breach at bar: {findings['origin_breach_at_bar']} (value: {findings['origin_breach_value']})")
        print(f"Pivot breach at bar: {findings['pivot_breach_at_bar']} (value: {findings['pivot_breach_value']})")
        print(f"Leg pruned at bar: {findings['leg_pruned_at_bar']}")
        print(f"Prune reason: {findings['prune_reason']}")

        if findings["leg_pruned_at_bar"] is None:
            print("\n!!! LEG WAS NOT PRUNED !!!")
            if findings["pivot_breach_at_bar"] is None:
                print("    ISSUE: max_pivot_breach was never set")
                if findings["leg_formed_at_bar"] is None:
                    print("    ROOT CAUSE: Leg never formed, so pivot breach tracking was disabled")
                else:
                    print("    INVESTIGATE: Leg formed but pivot breach not tracked")
            elif findings["origin_breach_at_bar"] is None:
                print("    ISSUE: max_origin_breach was never set")
            else:
                print("    INVESTIGATE: Both breaches set but leg not pruned as engulfed")
    else:
        print("!!! TARGET LEG WAS NEVER FOUND !!!")
        print("Check that the target specification matches the leg coordinates.")

    # Show final state of matching legs
    print(f"\n--- Final active legs matching direction '{target.direction}' ---")
    for leg in detector.state.active_legs:
        if leg.direction == target.direction and leg.status == 'active':
            if abs(leg.origin_price - target.origin_price) < Decimal("10"):
                log_leg_state(until_bar, leg)
                print()

    return findings


def main():
    parser = argparse.ArgumentParser(description="Investigate leg detection issues")
    parser.add_argument("--file", type=str, help="Data file path")
    parser.add_argument("--offset", type=int, help="Starting row offset")
    parser.add_argument("--direction", type=str, choices=["bull", "bear"], help="Leg direction")
    parser.add_argument("--origin-price", type=float, help="Origin price")
    parser.add_argument("--origin-bar", type=int, help="Origin bar index")
    parser.add_argument("--pivot-price", type=float, help="Pivot price")
    parser.add_argument("--pivot-bar", type=int, help="Pivot bar index")
    parser.add_argument("--until-bar", type=int, default=300, help="Run until this bar")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")

    args = parser.parse_args()

    # Use command line args if provided, otherwise use defaults below
    if args.file:
        data_file = args.file
        offset = args.offset
        target = LegTarget(
            direction=args.direction,
            origin_price=Decimal(str(args.origin_price)),
            origin_bar=args.origin_bar,
            pivot_price=Decimal(str(args.pivot_price)),
            pivot_bar=args.pivot_bar,
        )
        until_bar = args.until_bar
        verbose = not args.quiet
    else:
        # ============================================================
        # DEFAULT INVESTIGATION CONFIG - Edit these for quick testing
        # ============================================================
        data_file = "test_data/es-5m.csv"
        offset = 1172207
        target = LegTarget(
            direction="bear",
            origin_price=Decimal("4431.75"),
            origin_bar=204,  # Actual origin bar from data
            pivot_price=Decimal("4427.25"),
            pivot_bar=207,   # Pivot extended to here
        )
        until_bar = 270
        verbose = True
        # ============================================================

    investigate(data_file, offset, target, until_bar, verbose)


if __name__ == "__main__":
    main()
