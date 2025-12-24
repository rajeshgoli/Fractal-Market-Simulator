"""
Leg pruning logic for the DAG layer.

Handles all pruning operations:
- Origin-proximity pruning: consolidate legs close in (time, range) space (#294)
- Breach pruning: prune formed legs when pivot is breached (#208)
- Inner structure pruning: prune redundant legs from contained pivots (#264)
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

    def apply_origin_proximity_prune(
        self,
        state: DetectorState,
        direction: str,
        bar: Bar,
        timestamp: datetime,
    ) -> List[LegPrunedEvent]:
        """
        Apply origin-proximity based consolidation within pivot groups (#294, #298).

        **Complexity:** O(N log N) via time-bounded binary search (#306).

        The time_ratio formula bounds which older legs need checking:
            older_idx > (newer_idx - threshold * current_bar) / (1 - threshold)
        Binary search finds this bound in O(log N), reducing overall complexity
        from O(N^2) to O(N log N).

        **Step 1: Group by pivot** (pivot_price, pivot_index)
        Legs with different pivots are independent - a newer leg can validly have
        a larger range if it found a better pivot.

        **Step 2: Within each pivot group, prune newer leg if BOTH conditions are true:**
        - time_ratio < origin_time_prune_threshold: Legs formed around same time
        - range_ratio < origin_range_prune_threshold: Legs have similar ranges

        Where:
        - time_ratio = (bars_since_older_origin - bars_since_newer_origin) / bars_since_older_origin
        - range_ratio = |older_range - newer_range| / max(older_range, newer_range)

        Within a pivot group, newer leg should not be longer than older leg because
        all legs in the group share the same pivot, so range = |pivot - origin|.

        Active swing immunity: Legs with active swings are never pruned.

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

        current_bar = bar.index
        pruned_leg_ids: Set[str] = set()

        # Step 1: Group legs by pivot (pivot_price, pivot_index)
        pivot_groups: Dict[Tuple[Decimal, int], List[Leg]] = defaultdict(list)
        for leg in legs:
            key = (leg.pivot_price, leg.pivot_index)
            pivot_groups[key].append(leg)

        # Step 2: Within each pivot group, apply proximity pruning
        for pivot_key, group_legs in pivot_groups.items():
            if len(group_legs) <= 1:
                continue  # Single leg in group, nothing to prune

            # Sort by origin_index ascending (older legs first)
            group_legs.sort(key=lambda l: l.origin_index)

            # Track survivors within this pivot group
            # Use parallel arrays for O(log N) binary search (#306)
            survivors: List[Leg] = []
            survivor_indices: List[int] = []  # origin_index values, kept sorted

            for leg in group_legs:
                # Active swing immunity
                if leg.swing_id and leg.swing_id in active_swing_ids:
                    # Legs are processed in origin_index order, so append maintains sort
                    survivors.append(leg)
                    survivor_indices.append(leg.origin_index)
                    continue

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
                        prune_explanation = (
                            f"Pruned by older leg {older.leg_id} (same pivot): "
                            f"time_ratio={float(time_ratio):.3f} < {float(time_threshold):.3f}, "
                            f"range_ratio={float(range_ratio):.3f} < {float(range_threshold):.3f}"
                        )
                        break

                if should_prune:
                    leg.status = 'pruned'
                    pruned_leg_ids.add(leg.leg_id)
                    events.append(LegPrunedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id="",
                        leg_id=leg.leg_id,
                        reason="origin_proximity_prune",
                        explanation=prune_explanation,
                    ))
                else:
                    # Legs are processed in origin_index order, so append maintains sort
                    survivors.append(leg)
                    survivor_indices.append(leg.origin_index)

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
        # Skip if both engulfed and pivot breach pruning are disabled
        if not self.config.enable_engulfed_prune and not self.config.enable_pivot_breach_prune:
            return [], []

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
                if self.config.enable_engulfed_prune:
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
            if self.config.enable_pivot_breach_prune:
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
        if self.config.enable_engulfed_prune:
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
        # Skip if inner structure pruning is disabled
        if not self.config.enable_inner_structure_prune:
            return []

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

        # For each inner leg, find the smallest containing outer (immediate container)
        # and check if that outer is the largest at its pivot level.
        for inner in invalidated_legs:
            # Find all outers that contain this inner
            containing_outers: List[Leg] = []
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
                leg for leg in list(state.active_legs) + list(invalidated_legs)
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

                # #282: If an ACTIVE leg shares outer's pivot, the structure is still
                # relevant - don't prune. (The earlier "largest" check handles the case
                # where a larger invalidated leg shares the pivot.)
                active_at_outer_pivot = any(
                    leg.status == 'active'
                    and leg.direction == outer.direction
                    and leg.pivot_price == outer.pivot_price
                    and leg.leg_id != outer.leg_id
                    for leg in state.active_legs
                )
                if active_at_outer_pivot:
                    continue

                # No swing immunity for inner_structure pruning (#264)
                # If the leg is structurally inner (contained in a larger structure)
                # and there's an outer-origin leg with the same pivot, the inner
                # leg is redundant regardless of whether it formed a swing.

                # Build detailed explanation showing the containment comparison
                # inner/outer are the same-direction legs that were invalidated
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
