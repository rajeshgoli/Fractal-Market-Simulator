"""
Leg pruning logic for the DAG layer.

Handles all pruning operations:
- Turn pruning: consolidate legs on direction change
- Subtree pruning: apply 10% rule across origin groups
- Proximity pruning: consolidate similar-sized legs
- Domination pruning: prune legs with worse origins
"""

import bisect
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Set, TYPE_CHECKING

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
        always have the largest range and survive turn pruning.

        Creating dominated legs is wasteful - they will be pruned at turn.

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
            if leg.direction != direction or leg.status != 'active':
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

    def prune_dominated_legs_in_turn(
        self,
        state: DetectorState,
        new_leg: Leg,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune existing legs dominated by a newly created leg (#204).

        When a new leg is created with a better origin than existing legs,
        those worse legs should be pruned. This is the reverse of
        would_leg_be_dominated - that prevents creating worse legs, this removes
        existing worse legs when a better one is found.

        For trading: having a leg with origin 2 points worse means stop losses
        would be placed incorrectly, potentially getting stopped out on noise.

        Note: This prunes ALL dominated legs regardless of turn boundaries.
        Turn boundaries are respected for leg CREATION (to allow nested structure),
        but not for pruning (to consolidate origins within the same move).

        Immunity: Legs that have formed into active swings are never pruned.

        Args:
            state: Current detector state (mutated)
            new_leg: The newly created leg with a better origin
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs
        """
        events: List[LegPrunedEvent] = []
        direction = new_leg.direction
        new_origin = new_leg.origin_price

        # Build set of active swing IDs for immunity check
        active_swing_ids = {
            swing.swing_id for swing in state.active_swings
            if swing.status == 'active'
        }

        pruned_leg_ids: Set[str] = set()

        for leg in state.active_legs:
            if leg.leg_id == new_leg.leg_id:
                continue  # Don't prune self
            if leg.direction != direction or leg.status != 'active':
                continue
            # Active swing immunity - legs with active swings are never pruned
            if leg.swing_id and leg.swing_id in active_swing_ids:
                continue

            # Check if this leg is dominated by new_leg
            # Bull: lower origin is better, so prune if existing origin > new origin
            # Bear: higher origin is better, so prune if existing origin < new origin
            is_dominated = False
            if direction == 'bull' and leg.origin_price > new_origin:
                is_dominated = True
            if direction == 'bear' and leg.origin_price < new_origin:
                is_dominated = True

            if is_dominated:
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",
                    leg_id=leg.leg_id,
                    reason="dominated_in_turn",
                ))

        # Remove pruned legs from active_legs
        if pruned_leg_ids:
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_leg_ids
            ]

        return events

    def prune_legs_on_turn(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune legs with recursive 10% rule, multi-origin preservation, and proximity consolidation.

        1. Group legs by origin
        2. For each origin group: keep ONLY the largest (prune others)
           - On tie, keep earliest pivot bar (#190)
        3. Recursive 10% across origins: prune small contained origins (#185)
        4. Proximity consolidation: prune legs within threshold of survivors (#203)
        5. Active swing immunity: legs with active swings are never pruned

        This preserves nested structure while compressing noise.

        Args:
            state: Current detector state (mutated)
            direction: 'bull' or 'bear' - which legs to prune
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs
        """
        events: List[LegPrunedEvent] = []

        # Get active legs of the specified direction
        legs = [
            leg for leg in state.active_legs
            if leg.direction == direction and leg.status == 'active'
        ]

        if len(legs) <= 1:
            return events  # Nothing to prune

        # Build set of active swing IDs for immunity check
        active_swing_ids = {
            swing.swing_id for swing in state.active_swings
            if swing.status == 'active'
        }

        # Group by origin (same origin_price and origin_index)
        origin_groups: Dict[Tuple[Decimal, int], List[Leg]] = defaultdict(list)
        for leg in legs:
            key = (leg.origin_price, leg.origin_index)
            origin_groups[key].append(leg)

        pruned_leg_ids: Set[str] = set()

        # Step 1: Within each origin group, keep ONLY the largest
        # (Prune all others except those with active swings)
        best_per_origin: Dict[Tuple[Decimal, int], Leg] = {}

        for origin_key, group in origin_groups.items():
            # Find the largest in this origin group; on tie, keep earliest pivot (fixes #190)
            largest = max(group, key=lambda l: (l.range, -l.pivot_index))
            best_per_origin[origin_key] = largest

            if len(group) <= 1:
                continue

            # Prune all legs except the largest (old behavior from #181)
            for leg in group:
                if leg.leg_id == largest.leg_id:
                    continue
                # Active swing immunity: never prune legs with active swings
                if leg.swing_id and leg.swing_id in active_swing_ids:
                    continue
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",
                    leg_id=leg.leg_id,
                    reason="turn_prune",
                ))

        # Step 2: Recursive 10% across origins (subtree pruning)
        # Apply 10% rule to prune small origin groups whose best leg is
        # contained within a larger origin's best leg range
        events.extend(self._apply_recursive_subtree_prune(
            state, direction, bar, timestamp, best_per_origin, pruned_leg_ids, active_swing_ids
        ))

        # Step 3: Proximity-based consolidation (#203)
        # Prune legs that are too similar to survivors (within relative difference threshold)
        events.extend(self._apply_proximity_prune(
            state, direction, bar, timestamp, best_per_origin, pruned_leg_ids, active_swing_ids
        ))

        # Remove pruned legs from active_legs
        state.active_legs = [
            leg for leg in state.active_legs
            if leg.leg_id not in pruned_leg_ids
        ]

        return events

    def _apply_recursive_subtree_prune(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
        best_per_origin: Dict[Tuple[Decimal, int], Leg],
        pruned_leg_ids: Set[str],
        active_swing_ids: Set[str],
    ) -> List[LegPrunedEvent]:
        """
        Apply recursive 10% rule across origin groups (#185).

        For each origin's best leg, check if smaller origins are contained
        within its range. If a contained origin's best leg is <10% of the
        parent, prune all legs from that origin.

        Active swing immunity: Legs with active swings are never pruned.
        If an origin has any active swings, the entire origin is immune.

        This creates fractal compression: detailed near active zone, sparse further back.

        Args:
            state: Current detector state
            direction: 'bull' or 'bear'
            bar: Current bar
            timestamp: Timestamp for events
            best_per_origin: Dict mapping origin -> best leg for that origin
            pruned_leg_ids: Set to track pruned leg IDs (mutated)
            active_swing_ids: Set of swing IDs that are currently active

        Returns:
            List of LegPrunedEvent for pruned legs with reason="subtree_prune"
        """
        events: List[LegPrunedEvent] = []
        prune_threshold = Decimal(str(self.config.subtree_prune_threshold))

        # Skip subtree pruning if threshold is 0 (disabled)
        if prune_threshold == 0:
            return events

        # Sort origins by their best leg's range (descending)
        sorted_origins = sorted(
            best_per_origin.items(),
            key=lambda x: x[1].range,
            reverse=True
        )

        # Track surviving origins
        pruned_origins: Set[Tuple[Decimal, int]] = set()

        # Build map of origins with active swings (immune from subtree pruning)
        immune_origins: Set[Tuple[Decimal, int]] = set()
        for leg in state.active_legs:
            if leg.direction == direction and leg.swing_id and leg.swing_id in active_swing_ids:
                immune_origins.add((leg.origin_price, leg.origin_index))

        for i, (parent_origin, parent_leg) in enumerate(sorted_origins):
            if parent_origin in pruned_origins:
                continue

            parent_threshold = prune_threshold * parent_leg.range

            # Check smaller origins for containment
            for child_origin, child_leg in sorted_origins[i + 1:]:
                if child_origin in pruned_origins:
                    continue
                if child_leg.leg_id in pruned_leg_ids:
                    continue
                # Active swing immunity: don't prune origins with active swings
                if child_origin in immune_origins:
                    continue

                # Check if child is contained within parent's range
                if direction == 'bull':
                    # Bull: origin=LOW, pivot=HIGH
                    # Contained if child's origin >= parent's origin (both LOWs)
                    # and child's pivot <= parent's pivot (both HIGHs)
                    in_range = (child_leg.origin_price >= parent_leg.origin_price and
                                child_leg.pivot_price <= parent_leg.pivot_price)
                else:
                    # Bear: origin=HIGH, pivot=LOW
                    # Contained if child's origin <= parent's origin (both HIGHs)
                    # and child's pivot >= parent's pivot (both LOWs)
                    in_range = (child_leg.origin_price <= parent_leg.origin_price and
                                child_leg.pivot_price >= parent_leg.pivot_price)

                # If contained and < 10% of parent, prune
                if in_range and child_leg.range < parent_threshold:
                    pruned_origins.add(child_origin)

                    # Prune all legs from this origin (except those with active swings)
                    for leg in state.active_legs:
                        if leg.leg_id in pruned_leg_ids:
                            continue
                        if leg.direction != direction:
                            continue
                        if (leg.origin_price, leg.origin_index) == child_origin:
                            # Active swing immunity check
                            if leg.swing_id and leg.swing_id in active_swing_ids:
                                continue
                            leg.status = 'pruned'
                            pruned_leg_ids.add(leg.leg_id)
                            events.append(LegPrunedEvent(
                                bar_index=bar.index,
                                timestamp=timestamp,
                                swing_id="",
                                leg_id=leg.leg_id,
                                reason="subtree_prune",
                            ))

        return events

    def _apply_proximity_prune(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
        best_per_origin: Dict[Tuple[Decimal, int], Leg],
        pruned_leg_ids: Set[str],
        active_swing_ids: Set[str],
    ) -> List[LegPrunedEvent]:
        """
        Apply proximity-based consolidation (#203).

        Prunes legs that are too similar to larger survivors.
        Uses relative difference: |range_a - range_b| / max(range_a, range_b)

        Algorithm:
        1. Sort remaining legs by range (descending)
        2. Keep first (largest) as survivor
        3. For each remaining leg:
           - If relative_diff(leg, nearest_survivor) < threshold: prune
           - Else: add to survivors

        Uses bisect for O(log N) nearest-neighbor lookup in sorted survivor list.

        Active swing immunity: Legs with active swings are never pruned.

        Args:
            state: Current detector state
            direction: 'bull' or 'bear'
            bar: Current bar
            timestamp: Timestamp for events
            best_per_origin: Dict mapping origin -> best leg for that origin
            pruned_leg_ids: Set to track pruned leg IDs (mutated)
            active_swing_ids: Set of swing IDs that are currently active

        Returns:
            List of LegPrunedEvent for pruned legs with reason="proximity_prune"
        """
        events: List[LegPrunedEvent] = []
        prune_threshold = Decimal(str(self.config.proximity_prune_threshold))

        # Skip proximity pruning if threshold is 0 (disabled)
        if prune_threshold == 0:
            return events

        # Get remaining legs (not already pruned)
        remaining_legs = [
            leg for origin, leg in best_per_origin.items()
            if leg.leg_id not in pruned_leg_ids
        ]

        if len(remaining_legs) <= 1:
            return events

        # Sort by range descending
        remaining_legs.sort(key=lambda l: l.range, reverse=True)

        # Track survivors as (range, leg) for binary search
        # survivor_ranges is kept sorted ascending for bisect
        survivor_ranges: List[Decimal] = []
        survivor_legs: List[Leg] = []

        # First leg (largest) is always a survivor
        first_leg = remaining_legs[0]
        survivor_ranges.append(first_leg.range)
        survivor_legs.append(first_leg)

        # Process remaining legs
        for leg in remaining_legs[1:]:
            if leg.leg_id in pruned_leg_ids:
                continue

            # Active swing immunity
            if leg.swing_id and leg.swing_id in active_swing_ids:
                # Immune legs become survivors
                pos = bisect.bisect_left(survivor_ranges, leg.range)
                survivor_ranges.insert(pos, leg.range)
                survivor_legs.insert(pos, leg)
                continue

            # Find nearest survivor using binary search
            pos = bisect.bisect_left(survivor_ranges, leg.range)

            # Check neighbors (pos-1 and pos) to find nearest
            min_rel_diff = Decimal("1.0")  # Max possible relative diff

            if pos > 0:
                left_range = survivor_ranges[pos - 1]
                rel_diff = abs(leg.range - left_range) / max(leg.range, left_range)
                if rel_diff < min_rel_diff:
                    min_rel_diff = rel_diff

            if pos < len(survivor_ranges):
                right_range = survivor_ranges[pos]
                rel_diff = abs(leg.range - right_range) / max(leg.range, right_range)
                if rel_diff < min_rel_diff:
                    min_rel_diff = rel_diff

            # If too close to a survivor, prune
            if min_rel_diff < prune_threshold:
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",
                    leg_id=leg.leg_id,
                    reason="proximity_prune",
                ))
            else:
                # This leg is distinct, add to survivors
                # Insert at correct position to maintain sorted order
                bisect.insort(survivor_ranges, leg.range)
                # Find position again for leg insertion
                new_pos = bisect.bisect_left(survivor_ranges, leg.range)
                survivor_legs.insert(new_pos, leg)

        return events
