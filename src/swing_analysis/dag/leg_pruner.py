"""
Leg pruning logic for the DAG layer.

Handles all pruning operations:
- Turn pruning: consolidate legs on direction change
- Proximity pruning: consolidate similar-sized legs
- Domination pruning: prune legs with worse origins
- Breach pruning: prune formed legs when pivot is breached (#208)
"""

import bisect
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Set, TYPE_CHECKING

from ..swing_config import SwingConfig
from ..swing_node import SwingNode
from ..types import Bar
from ..events import LegPrunedEvent, LegCreatedEvent
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
        Prune existing legs dominated by a newly created leg (#204, #207).

        When a new leg is created with a better origin than existing legs,
        those worse legs should be pruned. This is the reverse of
        would_leg_be_dominated - that prevents creating worse legs, this removes
        existing worse legs when a better one is found.

        For trading: having a leg with origin 2 points worse means stop losses
        would be placed incorrectly, potentially getting stopped out on noise.

        IMPORTANT (#207): Turn boundaries are respected for BOTH creation AND pruning.
        Legs from different turns represent independent structural phases and must
        coexist. A leg from turn A should never be pruned by a leg from turn B.

        Definition of "same turn": Legs are in the same turn if their origin_index
        is >= the last_turn_bar[direction] value when they were created.

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

        # Get the turn boundary - only prune legs from the SAME turn (#207)
        turn_start = state.last_turn_bar.get(direction, -1)

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
            # #207: Skip legs from previous turns - they represent different structures
            if leg.origin_index < turn_start:
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

    def prune_legs_on_turn(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune legs with multi-origin preservation and proximity consolidation.

        1. Group legs by origin
        2. For each origin group: keep ONLY the largest (prune others)
           - On tie, keep earliest pivot bar (#190)
        3. Proximity consolidation: prune legs within threshold of survivors (#203)
        4. Active swing immunity: legs with active swings are never pruned

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

        # Step 2: Proximity-based consolidation (#203)
        # Prune legs that are too similar to survivors (within relative difference threshold)
        events.extend(self._apply_proximity_prune(
            state, direction, bar, timestamp, best_per_origin, pruned_leg_ids, active_swing_ids
        ))

        # Reparent children of pruned legs before removal (#281)
        for leg in state.active_legs:
            if leg.leg_id in pruned_leg_ids:
                self.reparent_children(state, leg)

        # Remove pruned legs from active_legs
        state.active_legs = [
            leg for leg in state.active_legs
            if leg.leg_id not in pruned_leg_ids
        ]

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
        Apply proximity-based consolidation (#203, #208).

        Prunes legs that are too similar to larger survivors within the same
        pivot group. Legs with different pivots represent different swing
        highs/lows and should NOT be consolidated just because they have
        similar ranges.

        Algorithm:
        1. Group remaining legs by pivot (pivot_price, pivot_index)
        2. Within each pivot group:
           a. Sort by range (descending)
           b. Keep first (largest) as survivor
           c. For each remaining leg:
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

        # Group legs by pivot - legs with different pivots track different swing points
        # and should NOT be consolidated based on range similarity alone
        pivot_groups: Dict[Tuple[Decimal, int], List[Leg]] = defaultdict(list)
        for leg in remaining_legs:
            pivot_key = (leg.pivot_price, leg.pivot_index)
            pivot_groups[pivot_key].append(leg)

        # Process each pivot group independently
        for pivot_key, legs_in_group in pivot_groups.items():
            if len(legs_in_group) <= 1:
                continue  # Nothing to prune in single-leg groups

            # Sort by range descending within this pivot group
            legs_in_group.sort(key=lambda l: l.range, reverse=True)

            # Track survivors as (range, leg) for binary search
            # survivor_ranges is kept sorted ascending for bisect
            survivor_ranges: List[Decimal] = []

            # First leg (largest) is always a survivor
            first_leg = legs_in_group[0]
            survivor_ranges.append(first_leg.range)

            # Process remaining legs in this pivot group
            for leg in legs_in_group[1:]:
                if leg.leg_id in pruned_leg_ids:
                    continue

                # Active swing immunity
                if leg.swing_id and leg.swing_id in active_swing_ids:
                    # Immune legs become survivors
                    pos = bisect.bisect_left(survivor_ranges, leg.range)
                    survivor_ranges.insert(pos, leg.range)
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

                # If too close to a survivor in same pivot group, prune
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
                    bisect.insort(survivor_ranges, leg.range)

        return events

    def prune_breach_legs(
        self,
        state: DetectorState,
        bar: Bar,
        timestamp: datetime,
    ) -> Tuple[List[LegPrunedEvent], List[LegCreatedEvent]]:
        """
        Prune formed legs when pivot is breached, and delete engulfed legs (#208).

        This method checks all active, formed legs for two conditions:

        1. **Engulfed**: Origin was ever breached AND pivot breach threshold exceeded
           - The leg is structurally compromised (price went against it)
           - Action: Delete immediately, no replacement

        2. **Pivot Breach**: Pivot breach threshold exceeded AND origin NEVER breached
           - Also requires: current bar made new extreme in leg direction
           - The pivot is no longer a valid reference level
           - Action: Prune original, create replacement with new pivot

        Replacement legs:
        - Have the same origin (price and index) as the original
        - Have their pivot at the new extreme (bar_high for bull, bar_low for bear)
        - Start with formed=False (must go through formation checks)
        - Can continue extending as price moves in that direction

        Args:
            state: Current detector state (mutated)
            bar: Current bar (for event metadata and new pivot location)
            timestamp: Timestamp for events

        Returns:
            Tuple of (LegPrunedEvent list, LegCreatedEvent list)
        """
        prune_events: List[LegPrunedEvent] = []
        create_events: List[LegCreatedEvent] = []

        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))

        legs_to_prune: List[Leg] = []
        legs_to_replace: List[Tuple[Leg, Decimal, str]] = []  # (leg, new_pivot, reason)

        for leg in state.active_legs:
            if leg.status != 'active' or not leg.formed:
                continue

            if leg.range == 0:
                continue

            # Check if pivot breach threshold was exceeded (retracement went too deep)
            # max_pivot_breach is set when retracement exceeds threshold per R1
            if leg.max_pivot_breach is None:
                continue  # No pivot breach detected yet

            # Engulfed: origin was ever breached AND pivot threshold exceeded
            # Single code path for all engulfed cases
            if leg.max_origin_breach is not None:
                legs_to_prune.append(leg)
                prune_events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="engulfed",
                ))
                continue

            # Pivot breach with replacement: origin NEVER breached
            # Only trigger if current bar made new extreme in leg direction
            # AND the extension past pivot exceeds the threshold
            if leg.direction == 'bull':
                # Bull: need new high that exceeds pivot by threshold
                pivot_threshold = Decimal(str(self.config.bull.pivot_breach_threshold))
                extension_threshold = leg.pivot_price + (pivot_threshold * leg.range)
                if bar_high > extension_threshold:
                    legs_to_replace.append((leg, bar_high, "pivot_breach"))
            else:
                # Bear: need new low that exceeds pivot by threshold
                pivot_threshold = Decimal(str(self.config.bear.pivot_breach_threshold))
                extension_threshold = leg.pivot_price - (pivot_threshold * leg.range)
                if bar_low < extension_threshold:
                    legs_to_replace.append((leg, bar_low, "pivot_breach"))

        # Also check invalidated legs for engulfed condition
        # Invalidated legs already have origin breached; if pivot also breached, they're engulfed
        # This cleans up noise from legs that were invalidated but still visible
        for leg in state.active_legs:
            if leg.status != 'invalidated' or not leg.formed:
                continue

            if leg.range == 0:
                continue

            # Invalidated legs by definition have origin breach
            # Check if pivot breach also occurred -> engulfed
            if leg.max_pivot_breach is not None and leg.max_origin_breach is not None:
                legs_to_prune.append(leg)
                prune_events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="engulfed",
                ))

        # Process legs to prune (engulfed - no replacement)
        # Reparent children before removal (#281)
        for leg in legs_to_prune:
            self.reparent_children(state, leg)
            leg.status = 'stale'

        # Process legs to replace (pivot breach)
        for leg, new_pivot, reason in legs_to_replace:
            # Check if a replacement leg already exists from same origin
            existing_replacement = any(
                l.direction == leg.direction
                and l.status == 'active'
                and l.origin_price == leg.origin_price
                and l.origin_index == leg.origin_index
                and l.leg_id != leg.leg_id
                for l in state.active_legs
            )

            if not existing_replacement:
                # Create replacement leg with new pivot
                # Inherit parent from original leg (#281)
                new_leg = Leg(
                    direction=leg.direction,
                    origin_price=leg.origin_price,
                    origin_index=leg.origin_index,
                    pivot_price=new_pivot,
                    pivot_index=bar.index,
                    formed=False,  # Must go through formation checks
                    price_at_creation=Decimal(str(bar.close)),
                    last_modified_bar=bar.index,
                    bar_count=0,
                    gap_count=0,
                    parent_leg_id=leg.parent_leg_id,  # Inherit parent from original (#281)
                )
                state.active_legs.append(new_leg)

                create_events.append(LegCreatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",  # New leg doesn't have swing_id yet
                    leg_id=new_leg.leg_id,
                    direction=new_leg.direction,
                    origin_price=new_leg.origin_price,
                    origin_index=new_leg.origin_index,
                    pivot_price=new_leg.pivot_price,
                    pivot_index=new_leg.pivot_index,
                ))

            # Reparent children before pruning original leg (#281)
            self.reparent_children(state, leg)
            # Prune the original leg
            leg.status = 'stale'
            prune_events.append(LegPrunedEvent(
                bar_index=bar.index,
                timestamp=timestamp,
                swing_id=leg.swing_id or "",
                leg_id=leg.leg_id,
                reason=reason,
            ))

        # Remove pruned legs from active_legs
        pruned_ids = {leg.leg_id for leg in legs_to_prune}
        pruned_ids.update(leg.leg_id for leg, _, _ in legs_to_replace)
        if pruned_ids:
            state.active_legs = [
                leg for leg in state.active_legs
                if leg.leg_id not in pruned_ids
            ]

        return prune_events, create_events

    def prune_inner_structure_legs(
        self,
        state: DetectorState,
        invalidated_legs: List[Leg],
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Prune counter-direction legs from inner structure pivots (#264).

        When multiple bear (or bull) legs are invalidated simultaneously, some may
        be strictly contained inside others. The counter-direction legs originating
        from inner structure pivots are redundant when an outer-origin leg exists
        with the same current pivot.

        Example (bear direction):
        - H1=6100 → L1=5900 (outer bear leg)
        - H2=6050 → L2=5950 (inner bear leg, strictly contained in H1→L1)
        - At H4=6150: Both are invalidated (origin breached)
        - Bull leg L2→H4 is redundant because L1→H4 exists and covers the structure
        - Prune L2→H4, keep L1→H4

        Containment definition (same direction):
        Bear: B_inner contained in B_outer iff inner.origin < outer.origin AND inner.pivot > outer.pivot
        Bull: B_inner contained in B_outer iff inner.origin > outer.origin AND inner.pivot < outer.pivot

        Only prunes if the outer-origin counter-leg exists with the same pivot.

        Args:
            state: Current detector state (mutated)
            invalidated_legs: Legs that were just invalidated in this bar
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs with reason="inner_structure"
        """
        events: List[LegPrunedEvent] = []
        pruned_leg_ids: Set[str] = set()

        # Group invalidated legs by direction
        bear_invalidated = [leg for leg in invalidated_legs if leg.direction == 'bear']
        bull_invalidated = [leg for leg in invalidated_legs if leg.direction == 'bull']

        # Process bear invalidated legs -> prune inner bull legs
        events.extend(self._prune_inner_structure_for_direction(
            state, bear_invalidated, 'bull', bar, timestamp, pruned_leg_ids
        ))

        # Process bull invalidated legs -> prune inner bear legs
        events.extend(self._prune_inner_structure_for_direction(
            state, bull_invalidated, 'bear', bar, timestamp, pruned_leg_ids
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
        invalidated_legs: List[Leg],
        counter_direction: str,
        bar: Bar,
        timestamp: datetime,
        pruned_leg_ids: Set[str],
    ) -> List[LegPrunedEvent]:
        """
        Prune inner structure legs for a specific direction pair.

        No swing immunity for inner_structure pruning - if a leg is structurally
        inner (contained in a larger structure) and there's an outer-origin leg
        with the same pivot, the inner leg is redundant regardless of swing status.

        Args:
            state: Current detector state
            invalidated_legs: Invalidated legs of one direction (e.g., bear)
            counter_direction: The counter direction to prune ('bull' if invalidated are 'bear')
            bar: Current bar
            timestamp: Timestamp for events
            pruned_leg_ids: Set to track pruned leg IDs (mutated)

        Returns:
            List of LegPrunedEvent for pruned legs
        """
        events: List[LegPrunedEvent] = []

        if len(invalidated_legs) < 2:
            return events  # Need at least 2 legs to have containment

        # Get active counter-direction legs (the ones we might prune)
        counter_legs = [
            leg for leg in state.active_legs
            if leg.direction == counter_direction and leg.status == 'active'
        ]

        if not counter_legs:
            return events

        # For each pair of invalidated legs, check containment
        for i, inner in enumerate(invalidated_legs):
            for outer in invalidated_legs:
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

                if not is_contained:
                    continue

                # inner is contained in outer
                # Find counter-direction legs originating from inner's pivot
                # Bull legs have origin at LOW (which is inner bear's pivot)
                # Bear legs have origin at HIGH (which is inner bull's pivot)
                for inner_leg in counter_legs:
                    if inner_leg.leg_id in pruned_leg_ids:
                        continue

                    # Check if this counter-leg originates from inner's pivot
                    if inner_leg.origin_price != inner.pivot_price:
                        continue

                    # Check if there's an outer-origin counter-leg with the same pivot
                    outer_leg_exists = any(
                        leg.origin_price == outer.pivot_price and
                        leg.pivot_price == inner_leg.pivot_price and
                        leg.status == 'active' and
                        leg.leg_id not in pruned_leg_ids
                        for leg in counter_legs
                    )

                    if not outer_leg_exists:
                        continue

                    # No swing immunity for inner_structure pruning (#264)
                    # If the leg is structurally inner (contained in a larger structure)
                    # and there's an outer-origin leg with the same pivot, the inner
                    # leg is redundant regardless of whether it formed a swing.

                    # Prune the inner-origin counter-leg
                    inner_leg.status = 'pruned'
                    pruned_leg_ids.add(inner_leg.leg_id)
                    events.append(LegPrunedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=inner_leg.swing_id or "",
                        leg_id=inner_leg.leg_id,
                        reason="inner_structure",
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
