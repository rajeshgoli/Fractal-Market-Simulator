#!/usr/bin/env python3
"""
Impulse Analysis Script for Issue #485.

Gathers empirical data on impulse metrics across bins to understand:
1. How impulse (range/bars) distributes by bin
2. Whether bin-normalization changes impulsiveness rankings
3. Segment impulse patterns for significant legs
4. Impulse decay over leg lifetime
5. Child formation count by bin
6. Segment velocity curves for significant parents

Usage:
    source venv/bin/activate
    python scripts/analyze_impulse.py
"""

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from statistics import mean, median, stdev
from typing import Dict, List, Optional, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swing_analysis.dag import LegDetector
from swing_analysis.dag.leg import Leg
from swing_analysis.dag.range_distribution import RollingBinDistribution
from swing_analysis.detection_config import DetectionConfig
from swing_analysis.events import LegCreatedEvent
from swing_analysis.reference_config import ReferenceConfig
from swing_analysis.reference_layer import ReferenceLayer
from swing_analysis.types import Bar
from data.ohlc_loader import load_ohlc


@dataclass
class LegSnapshot:
    """Snapshot of leg state at a point in time."""
    leg_id: str
    bin_index: int
    range_val: float
    impulse: float
    impulsiveness: Optional[float]
    bar_count: int
    origin_index: int
    pivot_index: int
    direction: str
    formed: bool
    has_children: bool = False
    impulse_to_deepest: Optional[float] = None
    impulse_back: Optional[float] = None


@dataclass
class LifetimeTracker:
    """Track impulse over a leg's lifetime."""
    leg_id: str
    direction: str
    # impulse at various bar counts: {bar_count: impulse}
    impulse_at_bars: Dict[int, float] = field(default_factory=dict)
    final_range: Optional[float] = None
    final_bin: Optional[int] = None

    def record(self, bar_count: int, impulse: float) -> None:
        """Record impulse at a specific bar count."""
        for milestone in [5, 10, 20, 50, 100]:
            if bar_count >= milestone and milestone not in self.impulse_at_bars:
                self.impulse_at_bars[milestone] = impulse


@dataclass
class ChildFormation:
    """Record of a child leg formation on a parent."""
    child_id: str
    child_origin_price: float
    child_origin_index: int
    parent_pivot_at_formation: float
    parent_pivot_index_at_formation: int
    bar_index: int


@dataclass
class ParentTracker:
    """Track parent leg state and child formations for experiments 5 & 6."""
    leg_id: str
    direction: str
    origin_price: float
    origin_index: int
    final_bin: Optional[int] = None
    children: List[ChildFormation] = field(default_factory=list)

    def add_child(self, child_id: str, child_origin_price: float, child_origin_index: int,
                  parent_pivot: float, parent_pivot_index: int, bar_index: int) -> None:
        """Record a child formation."""
        self.children.append(ChildFormation(
            child_id=child_id,
            child_origin_price=child_origin_price,
            child_origin_index=child_origin_index,
            parent_pivot_at_formation=parent_pivot,
            parent_pivot_index_at_formation=parent_pivot_index,
            bar_index=bar_index
        ))

    def compute_incremental_velocities(self) -> List[float]:
        """
        Compute incremental velocities between consecutive child formations.

        Velocity = |pivot_delta| / bar_delta
        where pivot_delta is the change in parent's pivot between child formations.
        """
        if len(self.children) < 2:
            return []

        velocities = []
        for i in range(1, len(self.children)):
            prev = self.children[i - 1]
            curr = self.children[i]

            pivot_delta = abs(curr.parent_pivot_at_formation - prev.parent_pivot_at_formation)
            bar_delta = curr.bar_index - prev.bar_index

            if bar_delta > 0:
                velocities.append(pivot_delta / bar_delta)

        return velocities

    def classify_velocity_pattern(self) -> Optional[str]:
        """
        Classify the velocity pattern as accelerating, decelerating, choppy, or steady.

        Returns:
            Pattern classification or None if insufficient data.
        """
        velocities = self.compute_incremental_velocities()
        if len(velocities) < 3:
            return None

        # Compute consecutive differences (acceleration)
        accelerations = [velocities[i] - velocities[i-1] for i in range(1, len(velocities))]

        positive_count = sum(1 for a in accelerations if a > 0)
        negative_count = sum(1 for a in accelerations if a < 0)
        total = len(accelerations)

        if total == 0:
            return "steady"

        pos_ratio = positive_count / total
        neg_ratio = negative_count / total

        # Check for sign changes (choppiness)
        sign_changes = 0
        for i in range(1, len(accelerations)):
            if (accelerations[i] > 0) != (accelerations[i-1] > 0):
                sign_changes += 1

        choppiness = sign_changes / (len(accelerations) - 1) if len(accelerations) > 1 else 0

        if choppiness > 0.6:
            return "choppy"
        elif pos_ratio > 0.7:
            return "accelerating"
        elif neg_ratio > 0.7:
            return "decelerating"
        else:
            return "steady"


def percentile(values: List[float], p: float) -> float:
    """Compute p-th percentile of values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_vals) else f
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def format_stats(values: List[float], label: str = "") -> str:
    """Format statistics for a list of values."""
    if not values:
        return f"{label}: N=0"
    n = len(values)
    avg = mean(values)
    med = median(values)
    std = stdev(values) if n > 1 else 0
    p90 = percentile(values, 90)
    min_v, max_v = min(values), max(values)
    return f"N={n}, mean={avg:.3f}, median={med:.3f}, std={std:.3f}, p90={p90:.3f}, min={min_v:.3f}, max={max_v:.3f}"


def compute_bin_local_percentile(impulse: float, bin_impulses: List[float]) -> float:
    """Compute percentile of impulse within a bin's impulses."""
    if not bin_impulses:
        return 50.0
    sorted_impulses = sorted(bin_impulses)
    import bisect
    pos = bisect.bisect_left(sorted_impulses, impulse)
    return (pos / len(sorted_impulses)) * 100


def main():
    print("=" * 70)
    print("IMPULSE ANALYSIS - Issue #485")
    print("=" * 70)

    # Load data
    data_file = Path(__file__).parent.parent / "test_data" / "es-30m.csv"
    print(f"\nLoading {data_file}...")
    df, gaps = load_ohlc(str(data_file))
    print(f"Loaded {len(df)} bars")

    # Initialize detector and reference layer
    config = DetectionConfig.default()
    ref_config = ReferenceConfig.default()
    detector = LegDetector(config)
    ref_layer = ReferenceLayer(config, ref_config)

    # Tracking structures
    # Experiment 1: impulse by bin
    impulse_by_bin: Dict[int, List[float]] = defaultdict(list)
    formed_legs_by_bin: Dict[int, List[LegSnapshot]] = defaultdict(list)

    # Experiment 2: bin-local vs global impulsiveness
    comparison_data: List[Tuple[str, int, float, float, float]] = []  # (leg_id, bin, impulse, global_pct, local_pct)

    # Experiment 3: segment impulse for significant legs (bin 8+)
    segment_data: List[Tuple[str, float, float, float]] = []  # (leg_id, impulse_to_deepest, impulse_back, net)

    # Experiment 4: lifetime tracking
    lifetime_trackers: Dict[str, LifetimeTracker] = {}
    lifetime_snapshots: Dict[str, List[Tuple[int, float]]] = defaultdict(list)  # leg_id -> [(bar_count, impulse), ...]

    # Experiments 5 & 6: parent-child tracking
    parent_trackers: Dict[str, ParentTracker] = {}  # parent_leg_id -> tracker
    seen_children: set = set()  # track children we've already recorded

    # All formed legs for global impulsiveness reference
    all_formed_impulses: List[float] = []

    # Process bars
    print("\nProcessing bars...")
    processed = 0
    last_percent = 0

    for idx, row in df.iterrows():
        bar = Bar(
            index=processed,
            timestamp=int(row.name.timestamp()),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )

        # Process bar
        events = detector.process_bar(bar)

        # Get current legs
        active_legs = detector.state.active_legs

        # Update reference layer to get bin classifications
        ref_state = ref_layer.update(active_legs, bar, build_response=True)

        # Track child formations at creation time (Experiments 5 & 6)
        # This captures ALL children including those that get pruned later
        if processed >= 5000:  # Wait for bin distribution to stabilize
            for event in events:
                if isinstance(event, LegCreatedEvent):
                    # Find the newly created leg in active_legs
                    new_leg = next((l for l in active_legs if l.leg_id == event.leg_id), None)
                    if new_leg and new_leg.parent_leg_id:
                        # This is a child leg - record the formation
                        parent_id = new_leg.parent_leg_id
                        # Find parent in active legs
                        parent_leg = next((l for l in active_legs if l.leg_id == parent_id), None)
                        if parent_leg:
                            # Ensure parent tracker exists
                            if parent_id not in parent_trackers:
                                parent_trackers[parent_id] = ParentTracker(
                                    leg_id=parent_id,
                                    direction=parent_leg.direction,
                                    origin_price=float(parent_leg.origin_price),
                                    origin_index=parent_leg.origin_index
                                )
                            # Record child formation with parent's current pivot
                            # Use event.leg_id to ensure we're tracking the right child
                            if event.leg_id not in seen_children:
                                seen_children.add(event.leg_id)
                                parent_trackers[parent_id].add_child(
                                    child_id=event.leg_id,
                                    child_origin_price=float(new_leg.origin_price),
                                    child_origin_index=new_leg.origin_index,
                                    parent_pivot=float(parent_leg.pivot_price),
                                    parent_pivot_index=parent_leg.pivot_index,
                                    bar_index=processed
                                )

        # Track formed legs (after warmup)
        if processed >= 5000:  # Wait for bin distribution to stabilize
            for leg in active_legs:
                if leg.retracement_pct >= Decimal("0.236"):  # Formed
                    range_val = float(leg.range)
                    # Get bin index from the distribution
                    bin_idx = ref_layer._bin_distribution.get_bin_index(range_val)
                    impulse = leg.impulse
                    bar_count = leg.bar_count if leg.bar_count > 0 else abs(leg.pivot_index - leg.origin_index)

                    # Track lifetime (Experiment 4)
                    if leg.leg_id not in lifetime_trackers:
                        lifetime_trackers[leg.leg_id] = LifetimeTracker(
                            leg_id=leg.leg_id,
                            direction=leg.direction
                        )
                    tracker = lifetime_trackers[leg.leg_id]
                    tracker.record(bar_count, impulse)
                    tracker.final_range = range_val
                    tracker.final_bin = bin_idx
                    lifetime_snapshots[leg.leg_id].append((bar_count, impulse))

                    # Track segment impulse for parents with children (Experiment 3)
                    if bin_idx >= 8 and leg.impulse_to_deepest is not None:
                        segment_data.append((
                            leg.leg_id,
                            leg.impulse_to_deepest,
                            leg.impulse_back or 0.0,
                            leg.net_segment_impulse or 0.0
                        ))

                    # Update parent tracker's final bin (for bin classification in output)
                    if leg.leg_id not in parent_trackers:
                        parent_trackers[leg.leg_id] = ParentTracker(
                            leg_id=leg.leg_id,
                            direction=leg.direction,
                            origin_price=float(leg.origin_price),
                            origin_index=leg.origin_index
                        )
                    parent_trackers[leg.leg_id].final_bin = bin_idx

        # Progress
        processed += 1
        pct = int(processed * 100 / len(df))
        if pct >= last_percent + 10:
            print(f"  {pct}% ({processed} bars)")
            last_percent = pct

    # Collect final stats from all legs that were ever formed
    print("\nCollecting statistics from formed legs...")

    # We need to process one more time to get all formed leg data
    # Reset and reprocess to collect formed leg data more cleanly
    detector2 = LegDetector(config)
    ref_layer2 = ReferenceLayer(config, ref_config)

    seen_legs: set = set()
    warmup_bars = 5000  # Wait for bin distribution to stabilize

    processed = 0
    for idx, row in df.iterrows():
        bar = Bar(
            index=processed,
            timestamp=int(row.name.timestamp()),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )

        events = detector2.process_bar(bar)
        active_legs = detector2.state.active_legs
        ref_layer2.update(active_legs, bar, build_response=False)

        # Only collect after warmup
        if processed >= warmup_bars:
            for leg in active_legs:
                if leg.retracement_pct >= Decimal("0.236") and leg.leg_id not in seen_legs:
                    seen_legs.add(leg.leg_id)
                    range_val = float(leg.range)

                    # Get bin index directly from the distribution
                    bin_idx = ref_layer2._bin_distribution.get_bin_index(range_val)
                    impulse = leg.impulse

                    # Experiment 1: Collect impulse by bin
                    impulse_by_bin[bin_idx].append(impulse)
                    all_formed_impulses.append(impulse)

                    # Snapshot for Experiment 2
                    has_children = leg.impulse_to_deepest is not None
                    snapshot = LegSnapshot(
                        leg_id=leg.leg_id,
                        bin_index=bin_idx,
                        range_val=range_val,
                        impulse=impulse,
                        impulsiveness=leg.impulsiveness,
                        bar_count=abs(leg.pivot_index - leg.origin_index),
                        origin_index=leg.origin_index,
                        pivot_index=leg.pivot_index,
                        direction=leg.direction,
                        formed=True,
                        has_children=has_children,
                        impulse_to_deepest=leg.impulse_to_deepest,
                        impulse_back=leg.impulse_back
                    )
                    formed_legs_by_bin[bin_idx].append(snapshot)

        processed += 1

    # Sort all_formed_impulses for percentile computation
    sorted_impulses = sorted(all_formed_impulses)

    # Generate results markdown
    print("\nGenerating results...")
    output_path = Path(__file__).parent.parent / "Docs" / "Working" / "impulse_analysis_results.md"

    with open(output_path, 'w') as f:
        f.write("# Impulse Analysis Results\n\n")
        f.write(f"**Data:** ES 30-minute ({len(df):,} bars)\n")
        f.write(f"**Total formed legs:** {len(all_formed_impulses):,}\n")
        f.write(f"**Generated:** Issue #485\n\n")

        # Experiment 1: Impulse Distribution by Bin
        f.write("---\n\n")
        f.write("## Experiment 1: Impulse Distribution by Bin\n\n")
        f.write("Raw impulse = range / bar_count (points per bar)\n\n")
        f.write("| Bin | Multiplier | Count | Mean | Median | Std | P90 | Min | Max |\n")
        f.write("|-----|------------|-------|------|--------|-----|-----|-----|-----|\n")

        from swing_analysis.dag.range_distribution import BIN_MULTIPLIERS

        for bin_idx in range(11):
            impulses = impulse_by_bin.get(bin_idx, [])
            mult_low = BIN_MULTIPLIERS[bin_idx]
            mult_high = BIN_MULTIPLIERS[bin_idx + 1]
            mult_str = f"{mult_low}×-{mult_high}×" if mult_high != float('inf') else f"{mult_low}×+"

            if impulses:
                avg = mean(impulses)
                med = median(impulses)
                std = stdev(impulses) if len(impulses) > 1 else 0
                p90 = percentile(impulses, 90)
                min_v, max_v = min(impulses), max(impulses)
                f.write(f"| {bin_idx} | {mult_str} | {len(impulses):,} | {avg:.3f} | {med:.3f} | {std:.3f} | {p90:.3f} | {min_v:.3f} | {max_v:.3f} |\n")
            else:
                f.write(f"| {bin_idx} | {mult_str} | 0 | - | - | - | - | - | - |\n")

        f.write("\n**Observation:** ")
        # Compute if small legs dominate high impulse
        bin_8_plus_impulses = []
        for b in range(8, 11):
            bin_8_plus_impulses.extend(impulse_by_bin.get(b, []))
        bin_0_7_impulses = []
        for b in range(8):
            bin_0_7_impulses.extend(impulse_by_bin.get(b, []))

        if bin_8_plus_impulses and bin_0_7_impulses:
            big_median = median(bin_8_plus_impulses)
            small_median = median(bin_0_7_impulses)
            f.write(f"Median impulse for bins 8+ is {big_median:.3f} vs {small_median:.3f} for bins 0-7. ")
            if small_median > big_median:
                f.write("Small legs have higher impulse (expected: range/bars favors short moves).\n")
            else:
                f.write("Larger legs have higher impulse (unexpected).\n")
        f.write("\n")

        # Experiment 2: Within-Bin Impulsiveness
        f.write("---\n\n")
        f.write("## Experiment 2: Within-Bin Impulsiveness\n\n")
        f.write("Compare global percentile rank vs bin-local percentile for bin 8+ legs.\n\n")

        # Collect bin 8+ legs with both percentiles
        bin_8_plus_legs = []
        for bin_idx in range(8, 11):
            for snapshot in formed_legs_by_bin.get(bin_idx, []):
                if snapshot.impulsiveness is not None:
                    # Compute bin-local percentile
                    bin_impulses = impulse_by_bin.get(bin_idx, [])
                    local_pct = compute_bin_local_percentile(snapshot.impulse, bin_impulses)
                    bin_8_plus_legs.append((
                        snapshot.leg_id,
                        bin_idx,
                        snapshot.impulse,
                        snapshot.impulsiveness,
                        local_pct
                    ))

        if bin_8_plus_legs:
            f.write(f"**Sample:** {len(bin_8_plus_legs):,} legs in bins 8-10\n\n")

            # Stats on difference
            differences = [abs(g - l) for _, _, _, g, l in bin_8_plus_legs]
            f.write(f"**Global vs Local Percentile Difference:**\n")
            f.write(f"- Mean absolute difference: {mean(differences):.1f} percentage points\n")
            f.write(f"- Median difference: {median(differences):.1f} percentage points\n")
            f.write(f"- Max difference: {max(differences):.1f} percentage points\n\n")

            # Count legs that change ranking significantly
            big_changes = sum(1 for d in differences if d > 20)
            f.write(f"**Legs with >20pp ranking change:** {big_changes:,} ({100*big_changes/len(differences):.1f}%)\n\n")

            # Sample table
            f.write("**Sample (first 20 legs):**\n\n")
            f.write("| Leg ID | Bin | Impulse | Global % | Local % | Diff |\n")
            f.write("|--------|-----|---------|----------|---------|------|\n")
            for leg_id, bin_idx, impulse, global_pct, local_pct in bin_8_plus_legs[:20]:
                diff = global_pct - local_pct
                short_id = leg_id.split("_")[-1][:8] + "..."
                f.write(f"| {short_id} | {bin_idx} | {impulse:.3f} | {global_pct:.1f} | {local_pct:.1f} | {diff:+.1f} |\n")
        else:
            f.write("No bin 8+ legs with impulsiveness data.\n")
        f.write("\n")

        # Experiment 3: Segment Impulse
        f.write("---\n\n")
        f.write("## Experiment 3: Segment Impulse for Significant Legs\n\n")
        f.write("For parent legs in bin 8+ that have children:\n")
        f.write("- impulse_to_deepest: Impulse of primary move (origin → deepest)\n")
        f.write("- impulse_back: Impulse of counter-move (deepest → child origin)\n")
        f.write("- net_segment_impulse: impulse_to_deepest - impulse_back\n\n")

        # Dedupe segment data
        seen_segment_legs = set()
        unique_segments = []
        for leg_id, itd, ib, net in segment_data:
            if leg_id not in seen_segment_legs:
                seen_segment_legs.add(leg_id)
                unique_segments.append((leg_id, itd, ib, net))

        if unique_segments:
            itd_vals = [itd for _, itd, _, _ in unique_segments]
            ib_vals = [ib for _, _, ib, _ in unique_segments]
            net_vals = [net for _, _, _, net in unique_segments]

            f.write(f"**Sample:** {len(unique_segments):,} parent legs with segment data\n\n")
            f.write("| Metric | Mean | Median | Std | Min | Max |\n")
            f.write("|--------|------|--------|-----|-----|-----|\n")

            for name, vals in [("impulse_to_deepest", itd_vals), ("impulse_back", ib_vals), ("net_segment_impulse", net_vals)]:
                if vals:
                    avg = mean(vals)
                    med = median(vals)
                    std = stdev(vals) if len(vals) > 1 else 0
                    min_v, max_v = min(vals), max(vals)
                    f.write(f"| {name} | {avg:.3f} | {med:.3f} | {std:.3f} | {min_v:.3f} | {max_v:.3f} |\n")

            f.write("\n")
            # Count positive vs negative net
            positive_net = sum(1 for n in net_vals if n > 0)
            negative_net = sum(1 for n in net_vals if n < 0)
            zero_net = len(net_vals) - positive_net - negative_net
            f.write(f"**Net segment impulse distribution:**\n")
            f.write(f"- Positive (sustained conviction): {positive_net:,} ({100*positive_net/len(net_vals):.1f}%)\n")
            f.write(f"- Negative (gave back progress): {negative_net:,} ({100*negative_net/len(net_vals):.1f}%)\n")
            f.write(f"- Zero: {zero_net:,} ({100*zero_net/len(net_vals):.1f}%)\n")
        else:
            f.write("No segment impulse data available.\n")
        f.write("\n")

        # Experiment 4: Impulse Stability
        f.write("---\n\n")
        f.write("## Experiment 4: Impulse Stability Over Leg Lifetime\n\n")
        f.write("Track impulse at bar counts 5, 10, 20, 50, 100 for legs that reach bin 8+.\n\n")

        # Filter to legs that reached bin 8+
        bin8_plus_trackers = [t for t in lifetime_trackers.values() if t.final_bin is not None and t.final_bin >= 8]

        if bin8_plus_trackers:
            f.write(f"**Sample:** {len(bin8_plus_trackers):,} legs that reached bin 8+\n\n")

            # Collect impulse at each milestone
            by_milestone: Dict[int, List[float]] = defaultdict(list)
            for tracker in bin8_plus_trackers:
                for milestone, impulse in tracker.impulse_at_bars.items():
                    by_milestone[milestone].append(impulse)

            f.write("| Bar Count | Legs | Mean Impulse | Median | Std |\n")
            f.write("|-----------|------|--------------|--------|-----|\n")
            for milestone in [5, 10, 20, 50, 100]:
                vals = by_milestone.get(milestone, [])
                if vals:
                    avg = mean(vals)
                    med = median(vals)
                    std = stdev(vals) if len(vals) > 1 else 0
                    f.write(f"| {milestone} | {len(vals):,} | {avg:.3f} | {med:.3f} | {std:.3f} |\n")
                else:
                    f.write(f"| {milestone} | 0 | - | - | - |\n")

            f.write("\n**Observation:** ")
            # Check if impulse decays
            impulse_5 = by_milestone.get(5, [])
            impulse_100 = by_milestone.get(100, [])
            if impulse_5 and impulse_100:
                med_5 = median(impulse_5)
                med_100 = median(impulse_100)
                if med_5 > med_100:
                    decay_pct = 100 * (med_5 - med_100) / med_5
                    f.write(f"Impulse decays as leg ages: median {med_5:.3f} at bar 5 → {med_100:.3f} at bar 100 ({decay_pct:.0f}% decay).\n")
                else:
                    f.write(f"Impulse does NOT decay: median {med_5:.3f} at bar 5 → {med_100:.3f} at bar 100.\n")

            # Early impulse vs final range correlation
            f.write("\n**Early impulse vs final range correlation:**\n")
            early_final_pairs = []
            for tracker in bin8_plus_trackers:
                if 10 in tracker.impulse_at_bars and tracker.final_range:
                    early_final_pairs.append((tracker.impulse_at_bars[10], tracker.final_range))

            if len(early_final_pairs) > 2:
                # Simple correlation
                x_vals = [x for x, _ in early_final_pairs]
                y_vals = [y for _, y in early_final_pairs]
                x_mean = mean(x_vals)
                y_mean = mean(y_vals)
                numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
                denom_x = sum((x - x_mean) ** 2 for x in x_vals) ** 0.5
                denom_y = sum((y - y_mean) ** 2 for y in y_vals) ** 0.5
                if denom_x > 0 and denom_y > 0:
                    corr = numerator / (denom_x * denom_y)
                    f.write(f"- Correlation between impulse at bar 10 and final range: {corr:.3f}\n")
                    if corr > 0.3:
                        f.write("- Positive correlation: Early high-impulse legs tend to have larger final ranges.\n")
                    elif corr < -0.3:
                        f.write("- Negative correlation: Early high-impulse legs tend to have smaller final ranges.\n")
                    else:
                        f.write("- Weak correlation: Early impulse doesn't strongly predict final range.\n")
        else:
            f.write("No bin 8+ legs to analyze.\n")

        # Experiment 5: Child Formation Count by Bin
        f.write("\n---\n\n")
        f.write("## Experiment 5: Child Formation Count by Bin\n\n")
        f.write("For parent legs in each bin, count how many children form.\n\n")

        # Group parents by bin and count children
        children_by_bin: Dict[int, List[int]] = defaultdict(list)
        for tracker in parent_trackers.values():
            if tracker.final_bin is not None and len(tracker.children) > 0:
                children_by_bin[tracker.final_bin].append(len(tracker.children))

        if any(children_by_bin.values()):
            f.write("| Bin | Parents | Mean Children | Median | Max | Total Children |\n")
            f.write("|-----|---------|---------------|--------|-----|----------------|\n")

            for bin_idx in range(11):
                child_counts = children_by_bin.get(bin_idx, [])
                if child_counts:
                    avg = mean(child_counts)
                    med = median(child_counts)
                    max_c = max(child_counts)
                    total = sum(child_counts)
                    f.write(f"| {bin_idx} | {len(child_counts):,} | {avg:.1f} | {med:.0f} | {max_c} | {total:,} |\n")
                else:
                    f.write(f"| {bin_idx} | 0 | - | - | - | - |\n")

            # Hypothesis check: bin 8+ should have ~50 children
            bin8_plus_children = []
            for b in range(8, 11):
                bin8_plus_children.extend(children_by_bin.get(b, []))

            if bin8_plus_children:
                f.write(f"\n**Bin 8+ summary:** {len(bin8_plus_children):,} parents, ")
                f.write(f"mean {mean(bin8_plus_children):.1f} children, ")
                f.write(f"median {median(bin8_plus_children):.0f}, ")
                f.write(f"max {max(bin8_plus_children)}\n")
                if mean(bin8_plus_children) >= 40:
                    f.write("→ Hypothesis confirmed: significant legs have many child events.\n")
                else:
                    f.write(f"→ Hypothesis NOT confirmed: mean children is {mean(bin8_plus_children):.1f}, not ~50.\n")
        else:
            f.write("No parent-child data available.\n")

        # Experiment 6: Segment Velocity Curve
        f.write("\n---\n\n")
        f.write("## Experiment 6: Segment Velocity Curve\n\n")
        f.write("For parent legs in bin 8+ with 10+ children, analyze velocity patterns.\n\n")
        f.write("Incremental velocity = |pivot_delta| / bar_delta between consecutive child formations.\n\n")

        # Filter to bin 8+ parents with 10+ children
        significant_parents = [
            t for t in parent_trackers.values()
            if t.final_bin is not None and t.final_bin >= 8 and len(t.children) >= 10
        ]

        if significant_parents:
            f.write(f"**Sample:** {len(significant_parents):,} parents with 10+ children in bin 8+\n\n")

            # Collect all velocity sequences and patterns
            all_velocities: List[float] = []
            pattern_counts: Dict[str, int] = defaultdict(int)

            for parent in significant_parents:
                velocities = parent.compute_incremental_velocities()
                all_velocities.extend(velocities)
                pattern = parent.classify_velocity_pattern()
                if pattern:
                    pattern_counts[pattern] += 1

            # Velocity statistics
            if all_velocities:
                f.write("**Velocity statistics across all segments:**\n\n")
                f.write("| Metric | Value |\n")
                f.write("|--------|-------|\n")
                f.write(f"| Count | {len(all_velocities):,} |\n")
                f.write(f"| Mean | {mean(all_velocities):.3f} |\n")
                f.write(f"| Median | {median(all_velocities):.3f} |\n")
                if len(all_velocities) > 1:
                    f.write(f"| Std | {stdev(all_velocities):.3f} |\n")
                f.write(f"| Min | {min(all_velocities):.3f} |\n")
                f.write(f"| Max | {max(all_velocities):.3f} |\n")
                f.write(f"| P10 | {percentile(all_velocities, 10):.3f} |\n")
                f.write(f"| P90 | {percentile(all_velocities, 90):.3f} |\n")
                f.write("\n")

            # Pattern distribution
            if pattern_counts:
                total_patterns = sum(pattern_counts.values())
                f.write("**Velocity pattern distribution:**\n\n")
                f.write("| Pattern | Count | Percentage |\n")
                f.write("|---------|-------|------------|\n")
                for pattern in ["accelerating", "decelerating", "choppy", "steady"]:
                    count = pattern_counts.get(pattern, 0)
                    pct = 100 * count / total_patterns if total_patterns > 0 else 0
                    f.write(f"| {pattern} | {count:,} | {pct:.1f}% |\n")
                f.write("\n")

                # Key finding
                dominant_pattern = max(pattern_counts, key=pattern_counts.get)
                dominant_pct = 100 * pattern_counts[dominant_pattern] / total_patterns
                f.write(f"**Key finding:** {dominant_pattern.capitalize()} is the most common pattern ({dominant_pct:.0f}%).\n")

                if pattern_counts.get("decelerating", 0) > pattern_counts.get("accelerating", 0):
                    f.write("→ Legs tend to slow down as they mature (decelerating velocity).\n")
                elif pattern_counts.get("accelerating", 0) > pattern_counts.get("decelerating", 0):
                    f.write("→ Legs tend to speed up as they grow (accelerating velocity).\n")
                elif pattern_counts.get("choppy", 0) > total_patterns * 0.4:
                    f.write("→ Velocity is highly variable (choppy) - hard to predict momentum.\n")

            # Sample velocity sequences for a few parents
            f.write("\n**Sample velocity sequences (first 5 parents):**\n\n")
            for i, parent in enumerate(significant_parents[:5]):
                velocities = parent.compute_incremental_velocities()
                pattern = parent.classify_velocity_pattern() or "N/A"
                short_id = parent.leg_id.split("_")[-1][:10]
                f.write(f"- `{short_id}` ({len(parent.children)} children, {pattern}): ")
                if len(velocities) <= 8:
                    f.write(f"[{', '.join(f'{v:.2f}' for v in velocities)}]\n")
                else:
                    # Show first 4 and last 4
                    first = ", ".join(f'{v:.2f}' for v in velocities[:4])
                    last = ", ".join(f'{v:.2f}' for v in velocities[-4:])
                    f.write(f"[{first}, ..., {last}]\n")
        else:
            f.write("No parents with 10+ children in bin 8+ available.\n")
            f.write("\nNote: This experiment requires parents with many child events for meaningful velocity curves.\n")

        f.write("\n---\n\n")
        f.write("## Summary & Unexpected Findings\n\n")

        # Key findings
        findings = []

        # Finding 1: Small legs dominate impulsiveness?
        if bin_0_7_impulses and bin_8_plus_impulses:
            small_med = median(bin_0_7_impulses)
            big_med = median(bin_8_plus_impulses)
            if small_med > big_med:
                findings.append(f"**Small legs have higher raw impulse** ({small_med:.3f} vs {big_med:.3f} median). This confirms the hypothesis that range/bars favors short-duration moves.")

        # Finding 2: Bin normalization impact
        if bin_8_plus_legs and differences:
            avg_diff = mean(differences)
            if avg_diff > 15:
                findings.append(f"**Bin normalization significantly changes rankings** (avg {avg_diff:.1f}pp difference). Within-bin impulsiveness may be more useful for comparing legs of similar scale.")
            else:
                findings.append(f"**Bin normalization has modest impact** (avg {avg_diff:.1f}pp difference). Global impulsiveness is reasonably stable across bins.")

        # Finding 3: Segment impulse patterns
        if unique_segments and net_vals:
            positive_pct = 100 * positive_net / len(net_vals)
            if positive_pct > 60:
                findings.append(f"**Most segments have positive net impulse** ({positive_pct:.0f}%). Primary moves are typically more impulsive than counter-moves.")
            elif positive_pct < 40:
                findings.append(f"**Many segments have negative net impulse** ({positive_pct:.0f}% positive). Counter-moves are often more impulsive than primary moves (unexpected).")

        # Finding 4: Impulse decay
        if bin8_plus_trackers and by_milestone:
            impulse_at_5 = by_milestone.get(5, [])
            impulse_at_100 = by_milestone.get(100, [])
            if impulse_at_5 and impulse_at_100:
                med_5 = median(impulse_at_5)
                med_100 = median(impulse_at_100)
                decay = (med_5 - med_100) / med_5 if med_5 > 0 else 0
                if decay > 0.3:
                    findings.append(f"**Impulse decays significantly over time** ({100*decay:.0f}% decay from bar 5 to 100). Early impulse is much higher than mature impulse.")

        # Finding 5: Child formation count
        if bin8_plus_children:
            avg_children = mean(bin8_plus_children)
            if avg_children >= 40:
                findings.append(f"**Significant legs have many child events** (mean {avg_children:.1f} children in bin 8+). Enough granularity for velocity analysis.")
            else:
                findings.append(f"**Child event count is lower than expected** (mean {avg_children:.1f} in bin 8+, not ~50). May limit velocity curve granularity.")

        # Finding 6: Velocity patterns
        if significant_parents and pattern_counts:
            total_p = sum(pattern_counts.values())
            choppy_pct = 100 * pattern_counts.get("choppy", 0) / total_p if total_p > 0 else 0
            decel_pct = 100 * pattern_counts.get("decelerating", 0) / total_p if total_p > 0 else 0
            if choppy_pct > 40:
                findings.append(f"**Velocity is highly variable** ({choppy_pct:.0f}% choppy). Incremental velocity from child events may not provide stable acceleration signal.")
            elif decel_pct > 40:
                findings.append(f"**Legs tend to decelerate** ({decel_pct:.0f}% decelerating). Velocity curves show legs slowing as they mature.")

        for i, finding in enumerate(findings, 1):
            f.write(f"{i}. {finding}\n\n")

        if not findings:
            f.write("No unexpected findings - results are consistent with expectations.\n")

    print(f"\nResults written to: {output_path}")
    print("Done!")


if __name__ == "__main__":
    main()
