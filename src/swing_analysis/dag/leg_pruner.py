"""
Leg pruning logic for the DAG layer.

Handles all pruning operations:
- Origin-proximity pruning: consolidate legs close in (time, range) space (#294)
- Engulfed pruning: delete legs breached on both origin and pivot sides (#208)
- Inner structure pruning: prune redundant legs from contained pivots (#264)
"""

import bisect
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Set, Optional, Tuple, TYPE_CHECKING

from ..swing_config import SwingConfig
from ..swing_node import SwingNode
from ..types import Bar
from ..events import LegPrunedEvent
from .leg import Leg
from .state import DetectorState

if TYPE_CHECKING:
    pass


class LegPruner:
    """
    Stateless helper for leg pruning operations.

    All methods take state/legs as parameters rather than storing state,
    making the pruning logic reusable and testable.
    """

    def __init__(self, config: SwingConfig):
        """
        Initialize with configuration.

        Args:
            config: SwingConfig with pruning parameters.
        """
        self.config = config

    def would_leg_be_dominated(
        self,
        state: DetectorState,
        direction: str,
        origin_price: Decimal,
    ) -> bool:
        """
        Check if a new leg would be dominated by an existing leg (#194).

        A leg is dominated if an existing active leg of the same direction has
        a better or equal origin. Since all legs of the same direction converge
        to the same pivot (via extend), the leg with the best origin will
        always have the largest range.

        Creating dominated legs is wasteful.

        IMPORTANT (#202): This check only applies within a single turn.
        Legs from previous turns (origin_index < last_turn_bar) don't dominate
        legs in the current turn. This allows nested subtrees to form after
        directional reversals.

        Args:
            state: Current detector state
            direction: 'bull' or 'bear'
            origin_price: The origin price of the potential new leg

        Returns:
            True if an existing leg dominates (new leg would be pruned)
        """
        # Get the turn boundary - only legs from current turn can dominate
        turn_start = state.last_turn_bar.get(direction, -1)

        for leg in state.active_legs:
            # Only consider active legs with live origin (not breached) (#345)
            # Stale legs don't dominate - they're no longer actively tracking price
            if leg.direction != direction or leg.status == 'stale' or leg.max_origin_breach is not None:
                continue
            # #202: Skip legs from previous turns - they don't dominate current turn
            if leg.origin_index < turn_start:
                continue
            # Bull: lower origin is better (origin=LOW, larger range)
            # Bear: higher origin is better (origin=HIGH, larger range)
            if direction == 'bull' and leg.origin_price <= origin_price:
                return True
            if direction == 'bear' and leg.origin_price >= origin_price:
                return True
        return False

    def apply_origin_proximity_prune(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Apply origin-proximity based consolidation within pivot groups (#294, #298, #319).

        Two strategies are available (configured via proximity_prune_strategy):

        **'oldest' (legacy):** O(N log N) via time-bounded binary search.
        Keeps the oldest leg in each proximity cluster.

        **'counter_trend' (default):** O(N^2) for cluster building.
        Keeps the leg with highest counter-trend range — the level where price
        traveled furthest against the trend to establish the origin.

        **Step 1: Group by pivot** (pivot_price, pivot_index)
        Legs with different pivots are independent - a newer leg can validly have
        a larger range if it found a better pivot.

        **Step 2: Within each pivot group:**
        - Build proximity clusters (legs within time/range thresholds)
        - Apply strategy to select winner per cluster
        - Prune non-winners

        Args:
            state: Current detector state (mutated)
            direction: 'bull' or 'bear' - which legs to prune
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs with reason="origin_proximity_prune"
        """
        events: List[LegPrunedEvent] = []
        range_threshold = Decimal(str(self.config.origin_range_prune_threshold))
        time_threshold = Decimal(str(self.config.origin_time_prune_threshold))

        # Skip proximity pruning if either threshold is 0 (disabled)
        if range_threshold == 0 or time_threshold == 0:
            return events

        # Get live (non-breached) legs of the specified direction (#345)
        legs = [
            leg for leg in state.active_legs
            if leg.direction == direction and leg.max_origin_breach is None
        ]

        if len(legs) <= 1:
            return events  # Nothing to prune

        current_bar = bar.index
        pruned_leg_ids: Set[str] = set()
        # Track swing transfers: pruned_leg_id -> survivor_leg that inherits the swing
        swing_transfers: Dict[str, Leg] = {}

        # Step 1: Group legs by pivot (pivot_price, pivot_index)
        pivot_groups: Dict[Tuple[Decimal, int], List[Leg]] = defaultdict(list)
        for leg in legs:
            key = (leg.pivot_price, leg.pivot_index)
            pivot_groups[key].append(leg)

        # Choose strategy
        strategy = self.config.proximity_prune_strategy

        # Step 2: Process each pivot group
        for pivot_key, group_legs in pivot_groups.items():
            if len(group_legs) <= 1:
                continue  # Single leg in group, nothing to prune

            if strategy == 'counter_trend':
                # Counter-trend scoring: build clusters, score by counter-trend range
                events.extend(self._apply_counter_trend_prune(
                    state, group_legs, range_threshold, time_threshold,
                    current_bar, bar, timestamp, pruned_leg_ids, swing_transfers
                ))
            else:
                # Legacy 'oldest' strategy
                events.extend(self._apply_oldest_wins_prune(
                    state, group_legs, range_threshold, time_threshold,
                    current_bar, bar, timestamp, pruned_leg_ids, swing_transfers
                ))

        # Transfer swings from pruned legs to their survivor legs
        for pruned_leg in state.active_legs:
            if pruned_leg.leg_id in swing_transfers:
                survivor = swing_transfers[pruned_leg.leg_id]
                # Transfer swing_id to survivor if survivor doesn't already have one
                if pruned_leg.swing_id and not survivor.swing_id:
                    survivor.swing_id = pruned_leg.swing_id

        # Reparent children of pruned legs before removal (#281)
        for leg in state.active_legs:
            if leg.leg_id in pruned_leg_ids:
                self.reparent_children(state, leg)

        # Remove pruned legs from active_legs
        if pruned_leg_ids:
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_leg_ids
            ]

        return events

    def _apply_oldest_wins_prune(
        self,
        state: DetectorState,
        group_legs: List[Leg],
        range_threshold: Decimal,
        time_threshold: Decimal,
        current_bar: int,
        bar: Bar,
        timestamp: datetime,
        pruned_leg_ids: Set[str],
        swing_transfers: Dict[str, Leg],
    ) -> List[LegPrunedEvent]:
        """
        Apply oldest-wins proximity pruning (legacy strategy).

        O(N log N) via time-bounded binary search (#306).
        """
        events: List[LegPrunedEvent] = []

        # Sort by origin_index ascending (older legs first)
        group_legs.sort(key=lambda l: l.origin_index)

        # Track survivors within this pivot group
        # Use parallel arrays for O(log N) binary search (#306)
        survivors: List[Leg] = []
        survivor_indices: List[int] = []  # origin_index values, kept sorted

        for leg in group_legs:
            # Calculate lower bound for older legs that could satisfy time proximity
            # From time_ratio < threshold:
            #   (newer_idx - older_idx) / (current_bar - older_idx) < threshold
            # Rearranging: older_idx > (newer_idx - threshold * current_bar) / (1 - threshold)
            if time_threshold < Decimal("1"):
                min_older_idx = int(
                    (leg.origin_index - float(time_threshold) * current_bar)
                    / (1 - float(time_threshold))
                )
            else:
                min_older_idx = -1  # No bound, check all (edge case)

            # Binary search for first survivor with origin_index >= min_older_idx
            start_pos = bisect.bisect_left(survivor_indices, min_older_idx)

            # Only check survivors in bounded window [start_pos:]
            should_prune = False
            prune_by_leg: Optional[Leg] = None
            prune_explanation = ""

            for i in range(start_pos, len(survivors)):
                older = survivors[i]

                # Calculate bars since origin for both legs
                bars_since_older = current_bar - older.origin_index
                bars_since_newer = current_bar - leg.origin_index

                # Avoid division by zero
                if bars_since_older <= 0:
                    continue

                # Time ratio: how close in time were they formed?
                # 0 = same time, 1 = newer is at current bar while older is distant
                time_ratio = Decimal(bars_since_older - bars_since_newer) / Decimal(bars_since_older)

                # Range ratio: relative difference in range
                max_range = max(older.range, leg.range)
                if max_range == 0:
                    continue

                range_diff = abs(older.range - leg.range)
                range_ratio = range_diff / max_range

                # Prune if BOTH conditions are true
                if time_ratio < time_threshold and range_ratio < range_threshold:
                    should_prune = True
                    prune_by_leg = older
                    prune_explanation = (
                        f"Pruned by older leg {older.leg_id} (same pivot): "
                        f"time_ratio={float(time_ratio):.3f} < {float(time_threshold):.3f}, "
                        f"range_ratio={float(range_ratio):.3f} < {float(range_threshold):.3f}"
                    )
                    break

            if should_prune:
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                # Track swing transfer if pruned leg has a swing
                if leg.swing_id:
                    swing_transfers[leg.leg_id] = prune_by_leg
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="origin_proximity_prune",
                    explanation=prune_explanation,
                ))
            else:
                # Legs are processed in origin_index order, so append maintains sort
                survivors.append(leg)
                survivor_indices.append(leg.origin_index)

        return events

    def _apply_counter_trend_prune(
        self,
        state: DetectorState,
        group_legs: List[Leg],
        range_threshold: Decimal,
        time_threshold: Decimal,
        current_bar: int,
        bar: Bar,
        timestamp: datetime,
        pruned_leg_ids: Set[str],
        swing_transfers: Dict[str, Leg],
    ) -> List[LegPrunedEvent]:
        """
        Apply counter-trend scoring proximity pruning (#319).

        Builds proximity clusters and keeps the leg with highest counter-trend
        range in each cluster — the level where price traveled furthest against
        the trend to establish the origin.

        Counter-trend range = |leg.origin_price - parent.segment_deepest_price|
        Fallback to leg.range when parent data unavailable.
        """
        events: List[LegPrunedEvent] = []

        # Build proximity clusters
        clusters = self._build_proximity_clusters(
            group_legs, range_threshold, time_threshold, current_bar
        )

        # For each cluster, keep highest counter-trend scorer
        for cluster in clusters:
            if len(cluster) <= 1:
                continue

            # Score each leg
            scored = self._score_legs_by_counter_trend(cluster, state)

            # Sort by score descending, then by origin_index ascending (tie-breaker)
            scored.sort(key=lambda x: (-x[1], x[0].origin_index))

            # Keep the best, prune the rest
            best_leg, best_score = scored[0]

            for leg, score in scored[1:]:
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                # Track swing transfer if pruned leg has a swing
                if leg.swing_id:
                    swing_transfers[leg.leg_id] = best_leg
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="origin_proximity_prune",
                    explanation=(
                        f"Cluster winner: {best_leg.leg_id} "
                        f"(counter_trend={best_score:.2f} vs {score:.2f})"
                    ),
                ))

        return events

    def _build_proximity_clusters(
        self,
        legs: List[Leg],
        range_threshold: Decimal,
        time_threshold: Decimal,
        current_bar: int,
    ) -> List[List[Leg]]:
        """
        Group legs into proximity clusters using union-find (#319).

        Two legs are in the same cluster if:
        - time_ratio < time_threshold (formed around same time)
        - range_ratio < range_threshold (similar ranges)

        Args:
            legs: Legs to cluster (all share same pivot)
            range_threshold: Max relative range difference
            time_threshold: Max relative time difference
            current_bar: Current bar index

        Returns:
            List of clusters, each cluster is a list of legs
        """
        n = len(legs)
        if n <= 1:
            return [legs] if legs else []

        # Sort by origin_index for consistent processing
        legs = sorted(legs, key=lambda l: l.origin_index)

        # Union-find structure
        parent = list(range(n))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Check all pairs for proximity
        for i in range(n):
            for j in range(i + 1, n):
                leg_i, leg_j = legs[i], legs[j]

                # Time ratio
                bars_since_i = current_bar - leg_i.origin_index
                bars_since_j = current_bar - leg_j.origin_index

                if bars_since_i <= 0:
                    continue

                time_ratio = Decimal(abs(bars_since_i - bars_since_j)) / Decimal(bars_since_i)

                # Range ratio
                max_range = max(leg_i.range, leg_j.range)
                if max_range == 0:
                    continue

                range_ratio = abs(leg_i.range - leg_j.range) / max_range

                # If both conditions met, same cluster
                if time_ratio < time_threshold and range_ratio < range_threshold:
                    union(i, j)

        # Build clusters
        clusters_dict: Dict[int, List[Leg]] = defaultdict(list)
        for i, leg in enumerate(legs):
            clusters_dict[find(i)].append(leg)

        return list(clusters_dict.values())

    def _score_legs_by_counter_trend(
        self,
        cluster: List[Leg],
        state: DetectorState,
    ) -> List[Tuple[Leg, float]]:
        """
        Score each leg by counter-trend range (#319).

        Counter-trend range = distance from parent's segment_deepest_price
        to this leg's origin. Higher = more significant level (price traveled
        further against the trend to reach it).

        Fallback for legs without parent data:
        - Use the leg's own range (bigger legs are more significant)

        Args:
            cluster: Legs to score
            state: Detector state for parent lookup

        Returns:
            List of (leg, score) tuples
        """
        scored: List[Tuple[Leg, float]] = []

        # Build parent lookup
        leg_by_id = {l.leg_id: l for l in state.active_legs}

        for leg in cluster:
            score = 0.0

            if leg.parent_leg_id and leg.parent_leg_id in leg_by_id:
                parent = leg_by_id[leg.parent_leg_id]

                if parent.segment_deepest_price is not None:
                    # Counter-trend range: how far price moved to reach this origin
                    counter_range = abs(float(leg.origin_price) - float(parent.segment_deepest_price))
                    score = counter_range
                else:
                    # Parent exists but no segment data - use leg's own range
                    score = float(leg.range)
            else:
                # No parent (root leg) - use leg's own range as fallback
                score = float(leg.range)

            scored.append((leg, score))

        return scored

    def prune_engulfed_legs(
        self,
        state: DetectorState,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Delete engulfed legs (#208).

        A leg is "engulfed" when both origin AND pivot have been breached over time.
        This means price has gone past both ends of the leg, making it structurally
        meaningless (inside a larger range).

        Note: The original #208 design included a "pivot breach replacement" path
        for legs where pivot was breached but origin was not. That code path was
        unreachable because pivot extension happens before breach tracking — if
        origin is not breached, pivot extends rather than getting breached.
        See Docs/Archive/pivot_breach_analysis.md for the full analysis.

        Args:
            state: Current detector state (mutated)
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs with reason="engulfed"
        """
        if not self.config.enable_engulfed_prune:
            return []

        prune_events: List[LegPrunedEvent] = []
        legs_to_prune: List[Leg] = []

        # Check formed legs for engulfed condition (#345)
        # Engulfed: both origin AND pivot have been breached at some point
        for leg in state.active_legs:
            if not leg.formed or leg.range == 0:
                continue

            # Engulfed: both origin AND pivot have been breached
            if leg.max_pivot_breach is not None and leg.max_origin_breach is not None:
                legs_to_prune.append(leg)
                prune_events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="engulfed",
                ))

        # Reparent children before removal (#281)
        for leg in legs_to_prune:
            self.reparent_children(state, leg)
            leg.status = 'stale'

        # Remove pruned legs from active_legs
        if legs_to_prune:
            pruned_ids = {leg.leg_id for leg in legs_to_prune}
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_ids
            ]

        return prune_events

    def prune_inner_structure_legs(
        self,
        state: DetectorState,
        breached_legs: List[Leg],
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune counter-direction legs from inner structure pivots (#264, #345).

        When multiple bear (or bull) legs have their origin breached, some may
        be strictly contained inside others. The counter-direction legs originating
        from inner structure pivots are redundant when an outer-origin leg exists
        with the same current pivot.

        Example (bear direction):
        - H1=6100 → L1=5900 (outer bear leg)
        - H2=6050 → L2=5950 (inner bear leg, strictly contained in H1→L1)
        - At H4=6150: Both are origin-breached
        - Bull leg L2→H4 is redundant because L1→H4 exists and covers the structure
        - Prune L2→H4, keep L1→H4

        Containment definition (same direction):
        Bear: B_inner contained in B_outer iff inner.origin < outer.origin AND inner.pivot > outer.pivot
        Bull: B_inner contained in B_outer iff inner.origin > outer.origin AND inner.pivot < outer.pivot

        Only prunes if the outer-origin counter-leg exists with the same pivot.

        Args:
            state: Current detector state (mutated)
            breached_legs: Legs with origin breached (max_origin_breach is not None)
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs with reason="inner_structure"
        """
        # Skip if inner structure pruning is disabled
        if not self.config.enable_inner_structure_prune:
            return []

        events: List[LegPrunedEvent] = []
        pruned_leg_ids: Set[str] = set()

        # Group breached legs by direction
        bear_breached = [leg for leg in breached_legs if leg.direction == 'bear']
        bull_breached = [leg for leg in breached_legs if leg.direction == 'bull']

        # Process bear breached legs -> prune inner bull legs
        events.extend(self._prune_inner_structure_for_direction(
            state, bear_breached, 'bull', bar, timestamp, pruned_leg_ids
        ))

        # Process bull breached legs -> prune inner bear legs
        events.extend(self._prune_inner_structure_for_direction(
            state, bull_breached, 'bear', bar, timestamp, pruned_leg_ids
        ))

        # Reparent children of pruned legs before removal (#281)
        for leg in state.active_legs:
            if leg.leg_id in pruned_leg_ids:
                self.reparent_children(state, leg)

        # Remove pruned legs from active_legs
        if pruned_leg_ids:
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_leg_ids
            ]

        return events

    def _prune_inner_structure_for_direction(
        self,
        state: DetectorState,
        breached_legs: List[Leg],
        counter_direction: str,
        bar: Bar,
        timestamp: datetime,
        pruned_leg_ids: Set[str],
    ) -> List[LegPrunedEvent]:
        """
        Prune inner structure legs for a specific direction pair (#345).

        No swing immunity for inner_structure pruning - if a leg is structurally
        inner (contained in a larger structure) and there's an outer-origin leg
        with the same pivot, the inner leg is redundant regardless of swing status.

        Args:
            state: Current detector state
            breached_legs: Origin-breached legs of one direction (e.g., bear)
            counter_direction: The counter direction to prune ('bull' if breached are 'bear')
            bar: Current bar
            timestamp: Timestamp for events
            pruned_leg_ids: Set to track pruned leg IDs (mutated)

        Returns:
            List of LegPrunedEvent for pruned legs
        """
        events: List[LegPrunedEvent] = []

        if len(breached_legs) < 2:
            return events  # Need at least 2 legs to have containment

        # Get live counter-direction legs (the ones we might prune) (#345)
        counter_legs = [
            leg for leg in state.active_legs
            if leg.direction == counter_direction and leg.max_origin_breach is None
        ]

        if not counter_legs:
            return events

        # For each inner leg, find the smallest containing outer (immediate container)
        # and check if that outer is the largest at its pivot level.
        for inner in breached_legs:
            # Find all outers that contain this inner
            containing_outers: List[Leg] = []
            for outer in breached_legs:
                if inner.leg_id == outer.leg_id:
                    continue

                # Check strict containment
                # For bear legs: inner contained in outer means:
                #   inner.origin (HIGH) < outer.origin (HIGH) AND
                #   inner.pivot (LOW) > outer.pivot (LOW)
                # For bull legs: inner contained in outer means:
                #   inner.origin (LOW) > outer.origin (LOW) AND
                #   inner.pivot (HIGH) < outer.pivot (HIGH)
                is_contained = False
                if inner.direction == 'bear':
                    is_contained = (
                        inner.origin_price < outer.origin_price and
                        inner.pivot_price > outer.pivot_price
                    )
                else:  # bull
                    is_contained = (
                        inner.origin_price > outer.origin_price and
                        inner.pivot_price < outer.pivot_price
                    )

                if is_contained:
                    containing_outers.append(outer)

            if not containing_outers:
                continue  # inner is not contained in any outer

            # #282: Find the smallest containing outer (closest origin to inner)
            # For bear: smallest outer has smallest origin (lowest HIGH above inner)
            # For bull: smallest outer has largest origin (highest LOW below inner)
            if inner.direction == 'bear':
                outer = min(containing_outers, key=lambda l: l.origin_price)
            else:
                outer = max(containing_outers, key=lambda l: l.origin_price)

            # #282: Only prune if outer is the largest at its pivot.
            # If a larger leg shares outer's pivot, the inner is part of a larger
            # structure and shouldn't be pruned.
            all_at_outer_pivot = [
                leg for leg in list(state.active_legs) + list(breached_legs)
                if leg.direction == outer.direction
                and leg.pivot_price == outer.pivot_price
            ]
            largest_at_outer_pivot = max(all_at_outer_pivot, key=lambda l: l.range)
            if largest_at_outer_pivot.leg_id != outer.leg_id:
                continue  # outer is not the largest - skip

            # inner is contained in outer (and outer is largest at its pivot)
            # Find counter-direction legs originating from inner's pivot
            # Bull legs have origin at LOW (which is inner bear's pivot)
            # Bear legs have origin at HIGH (which is inner bull's pivot)
            for inner_leg in counter_legs:
                if inner_leg.leg_id in pruned_leg_ids:
                    continue

                # Check if this counter-leg originates from inner's pivot
                if inner_leg.origin_price != inner.pivot_price:
                    continue

                # Check if there's an outer-origin counter-leg with the same pivot (#345)
                outer_leg_exists = any(
                    leg.origin_price == outer.pivot_price and
                    leg.pivot_price == inner_leg.pivot_price and
                    leg.max_origin_breach is None and
                    leg.leg_id not in pruned_leg_ids
                    for leg in counter_legs
                )

                if not outer_leg_exists:
                    continue

                # #282: If a live (non-breached) leg shares outer's pivot, the structure
                # is still relevant - don't prune. (The earlier "largest" check handles
                # the case where a larger breached leg shares the pivot.) (#345)
                live_at_outer_pivot = any(
                    leg.max_origin_breach is None
                    and leg.direction == outer.direction
                    and leg.pivot_price == outer.pivot_price
                    and leg.leg_id != outer.leg_id
                    for leg in state.active_legs
                )
                if live_at_outer_pivot:
                    continue

                # No swing immunity for inner_structure pruning (#264)
                # If the leg is structurally inner (contained in a larger structure)
                # and there's an outer-origin leg with the same pivot, the inner
                # leg is redundant regardless of whether it formed a swing.

                # Build detailed explanation showing the containment comparison
                # inner/outer are the same-direction legs that were breached
                # inner_leg is the counter-direction leg being pruned
                explanation = (
                    f"Inner {inner.direction} ({float(inner.origin_price):.2f}→"
                    f"{float(inner.pivot_price):.2f}, range={float(inner.range):.2f}) "
                    f"contained in outer {outer.direction} ({float(outer.origin_price):.2f}→"
                    f"{float(outer.pivot_price):.2f}, range={float(outer.range):.2f}). "
                    f"Pruned {counter_direction} leg origin={float(inner_leg.origin_price):.2f} "
                    f"(from inner pivot) - outer-origin leg exists."
                )

                # Prune the inner-origin counter-leg
                inner_leg.status = 'pruned'
                pruned_leg_ids.add(inner_leg.leg_id)
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=inner_leg.swing_id or "",
                    leg_id=inner_leg.leg_id,
                    reason="inner_structure",
                    explanation=explanation,
                ))

        return events

    def reparent_children(self, state: DetectorState, pruned_leg: Leg) -> None:
        """
        Reparent children of a pruned leg to its parent (grandparent) (#281).

        When a leg is pruned, any legs that had it as parent need to be
        reparented to the pruned leg's parent. This maintains the hierarchy
        chain without gaps.

        Example:
        - Before: L4 (root) -> L5 -> L6
        - If L5 is pruned: L4 (root) -> L6 (reparented)
        - If the root is pruned: L6 becomes root (parent_leg_id = None)

        Args:
            state: Current detector state (mutated)
            pruned_leg: The leg being pruned
        """
        for leg in state.active_legs:
            if leg.parent_leg_id == pruned_leg.leg_id:
                leg.parent_leg_id = pruned_leg.parent_leg_id  # Could be None (root)

    def apply_min_counter_trend_prune(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune legs with insufficient counter-trend ratio (#336).

        This filter removes legs whose counter-trend pressure is too small relative
        to their total range. It operates independently of proximity clustering.

        Counter-trend ratio = longest_opposite_range / leg.range

        Where longest_opposite_range is the range of the longest opposite-direction
        leg whose pivot equals this leg's origin. This measures how much counter-trend
        pressure accumulated at the pivot before this leg started.

        Example:
            At pivot 100, bull legs exist: 50→100, 60→100, 70→100
            New bear leg: 100→20 (range=80)
            longest_opposite_range = 50 (from the 50→100 bull leg)
            ratio = 50/80 = 0.625 (62.5%)

        Legs with ratio < min_counter_trend_ratio are pruned as insignificant
        (insufficient counter-trend pressure to justify this structural level).

        Args:
            state: Current detector state (mutated)
            direction: 'bull' or 'bear' - which legs to check
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs with reason="min_counter_trend"
        """
        events: List[LegPrunedEvent] = []
        min_ratio = self.config.min_counter_trend_ratio

        # Get formed legs of the specified direction (with live origin) (#345)
        legs_to_check = [
            leg for leg in state.active_legs
            if leg.direction == direction and leg.max_origin_breach is None and leg.formed
        ]

        # Determine opposite direction
        opposite_direction = 'bear' if direction == 'bull' else 'bull'

        pruned_leg_ids: Set[str] = set()

        for leg in legs_to_check:
            if leg.range == 0:
                continue

            # Calculate counter-trend ratio (#336):
            # Use the stored origin_counter_trend_range (captured at leg creation)
            # This is the range of the longest opposite leg at this origin when leg formed
            # The opposite leg may have been pruned since, but we use the captured value
            if leg.origin_counter_trend_range is not None:
                ratio = leg.origin_counter_trend_range / float(leg.range)
            else:
                # No opposite legs at this origin when leg was created - passes by default
                ratio = 1.0

            # Always store the ratio on the leg for display/inspection
            leg.counter_trend_ratio = ratio

            # Prune if threshold is enabled and ratio is below it
            if min_ratio > 0 and ratio < min_ratio:
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                opposite_range = leg.origin_counter_trend_range or 0.0
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="min_counter_trend",
                    explanation=(
                        f"CTR ratio {ratio:.3f} < {min_ratio:.3f} threshold "
                        f"(opposite_range={opposite_range:.2f}, leg_range={float(leg.range):.2f})"
                    ),
                ))

        # Reparent children of pruned legs before removal
        for leg in state.active_legs:
            if leg.leg_id in pruned_leg_ids:
                self.reparent_children(state, leg)

        # Remove pruned legs
        if pruned_leg_ids:
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_leg_ids
            ]

        return events

    def prune_by_turn_ratio(
        self,
        state: DetectorState,
        new_leg: Leg,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune counter-legs at the new leg's origin based on turn ratio (#341, #342, #344).

        Two mutually exclusive modes:
        1. **Threshold mode** (min_turn_ratio > 0): Prune if turn_ratio < threshold
        2. **Top-k mode** (min_turn_ratio == 0, max_turns_per_pivot > 0): Keep only
           the k highest-ratio legs at each pivot

        **#344 Exemption**: The largest leg (by range) at the shared pivot is always
        exempt from turn-ratio pruning. This is because the largest leg represents
        primary structure — it has the lowest turn ratio (range is in denominator)
        but is the most significant level at this pivot.

        When a new leg forms at origin O, for each counter-leg whose pivot == O:
        - turn_ratio = counter_leg._max_counter_leg_range / counter_leg.range

        This filters horizontally (siblings at shared pivots) rather than vertically
        (parent-child via branch ratio). It removes legs that have extended far
        beyond what their structural context justified.

        Args:
            state: Current detector state (mutated)
            new_leg: The newly created leg (trigger for pruning)
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned counter-legs with reason="turn_ratio"
        """
        events: List[LegPrunedEvent] = []
        min_turn_ratio = self.config.min_turn_ratio
        max_turns_per_pivot = self.config.max_turns_per_pivot

        # Determine mode:
        # - Threshold mode: min_turn_ratio > 0 (ignores max_turns_per_pivot)
        # - Top-k mode: min_turn_ratio == 0 and max_turns_per_pivot > 0
        # - Disabled: both are 0
        use_threshold_mode = min_turn_ratio > 0
        use_topk_mode = not use_threshold_mode and max_turns_per_pivot > 0

        if not use_threshold_mode and not use_topk_mode:
            return events  # Disabled

        # Find counter-legs: opposite direction, pivot == new_leg.origin (#345)
        opposite_direction = 'bear' if new_leg.direction == 'bull' else 'bull'
        counter_legs = [
            leg for leg in state.active_legs
            if leg.direction == opposite_direction
            and leg.pivot_price == new_leg.origin_price
            and leg.max_origin_breach is None  # Only consider live legs
            and leg.leg_id != new_leg.leg_id  # Exclude self (shouldn't match anyway)
        ]

        if not counter_legs:
            return events

        # #344: Exempt the largest leg from pruning - it's primary structure
        # The biggest leg has the lowest turn ratio (since range is in denominator)
        # but represents the most significant structure at this pivot
        largest_leg = max(counter_legs, key=lambda l: l.range)
        pruneable_legs = [leg for leg in counter_legs if leg.leg_id != largest_leg.leg_id]

        # If only one leg, nothing to prune (the largest is exempt)
        if not pruneable_legs:
            return events

        pruned_leg_ids: Set[str] = set()

        if use_threshold_mode:
            # Threshold mode: prune legs with turn_ratio < min_turn_ratio
            for counter_leg in pruneable_legs:
                if counter_leg.range == 0:
                    continue

                # If _max_counter_leg_range is None, the leg was created before this
                # feature - skip it (don't prune legacy legs)
                if counter_leg._max_counter_leg_range is None:
                    continue

                turn_ratio = counter_leg._max_counter_leg_range / float(counter_leg.range)

                if turn_ratio < min_turn_ratio:
                    counter_leg.status = 'pruned'
                    pruned_leg_ids.add(counter_leg.leg_id)
                    events.append(LegPrunedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=counter_leg.swing_id or "",
                        leg_id=counter_leg.leg_id,
                        reason="turn_ratio",
                        explanation=(
                            f"Turn ratio {turn_ratio:.3f} < {min_turn_ratio:.3f} threshold "
                            f"(max_counter={counter_leg._max_counter_leg_range:.2f}, "
                            f"leg_range={float(counter_leg.range):.2f})"
                        ),
                    ))
        else:
            # Top-k mode: keep only max_turns_per_pivot highest-ratio legs
            # Score each leg by turn_ratio (skip legacy legs without _max_counter_leg_range)
            # Note: largest leg is already exempt, only score pruneable_legs
            scored_legs: List[Tuple[Leg, float]] = []
            for counter_leg in pruneable_legs:
                if counter_leg.range == 0:
                    continue
                if counter_leg._max_counter_leg_range is None:
                    # Legacy leg - give it a neutral score so it's not pruned
                    # but also not favored over legs with actual ratios
                    scored_legs.append((counter_leg, float('inf')))
                    continue
                turn_ratio = counter_leg._max_counter_leg_range / float(counter_leg.range)
                scored_legs.append((counter_leg, turn_ratio))

            if len(scored_legs) <= max_turns_per_pivot:
                # Not enough legs to prune
                return events

            # Sort by turn_ratio descending (highest ratio = most significant)
            scored_legs.sort(key=lambda x: -x[1])

            # Keep top k, prune the rest
            legs_to_prune = scored_legs[max_turns_per_pivot:]

            for counter_leg, turn_ratio in legs_to_prune:
                # Don't prune legacy legs (inf ratio)
                if turn_ratio == float('inf'):
                    continue

                counter_leg.status = 'pruned'
                pruned_leg_ids.add(counter_leg.leg_id)
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=counter_leg.swing_id or "",
                    leg_id=counter_leg.leg_id,
                    reason="turn_ratio_topk",
                    explanation=(
                        f"Turn ratio {turn_ratio:.3f} not in top-{max_turns_per_pivot} "
                        f"(max_counter={counter_leg._max_counter_leg_range:.2f}, "
                        f"leg_range={float(counter_leg.range):.2f})"
                    ),
                ))

        # Reparent children of pruned legs before removal
        for leg in state.active_legs:
            if leg.leg_id in pruned_leg_ids:
                self.reparent_children(state, leg)

        # Remove pruned legs
        if pruned_leg_ids:
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_leg_ids
            ]

        return events
