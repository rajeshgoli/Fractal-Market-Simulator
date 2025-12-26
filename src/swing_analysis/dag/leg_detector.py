"""
DAG-Based Leg Detector (Structural Layer)

The DAG layer is responsible for structural tracking of price extremas. It processes
one bar at a time via process_bar() and emits events for swing formation and Fib
level crosses.

**This layer handles:**
- Leg tracking with origin breach as structural gate (#345)
- Swing formation detection
- Level cross event tracking
- Parent-child relationship assignment

**This layer does NOT handle (see reference_layer.py):**
- Swing invalidation (tolerance-based rules)
- Swing completion (big swings never complete)
- Big swing classification (top 10% by range)

The separation allows the DAG to stay simple and O(n log k), while semantic/trading
rules can evolve independently in the Reference layer.

See Docs/Working/DAG_spec.md for full specification.
See Docs/Working/Performance_question.md for design rationale.
"""

import bisect
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING

from ..swing_config import SwingConfig
from ..swing_node import SwingNode
from ..reference_frame import ReferenceFrame
from ..types import Bar
from ..events import (
    SwingEvent,
    SwingFormedEvent,
    SwingInvalidatedEvent,
    LevelCrossEvent,
    LegCreatedEvent,
    LegPrunedEvent,
    OriginBreachedEvent,
    PivotBreachedEvent,
)
from .leg import Leg, PendingOrigin
from .state import DetectorState, BarType
from .leg_pruner import LegPruner

if TYPE_CHECKING:
    from ..reference_layer import ReferenceLayer


# Fibonacci levels to track for level cross events
FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 2.0]


def _calculate_impulse(range_value: Decimal, origin_index: int, pivot_index: int) -> float:
    """
    Calculate impulse score (points per bar) for a leg (#236).

    Impulse measures the intensity of a price move: high-impulse moves
    are sharp and fast, low-impulse moves are slow and gradual.

    Args:
        range_value: Absolute price range of the leg (|origin - pivot|)
        origin_index: Bar index where the leg originated
        pivot_index: Bar index of the current pivot

    Returns:
        Impulse as points per bar. Returns 0.0 if bar_count is 0.
    """
    bar_count = abs(pivot_index - origin_index)
    if bar_count == 0:
        return 0.0
    return float(range_value) / bar_count


def _calculate_impulsiveness(raw_impulse: float, formed_impulses: List[float]) -> Optional[float]:
    """
    Calculate impulsiveness (0-100) as percentile rank of raw impulse (#241, #243).

    Uses binary search for O(log n) percentile lookup against sorted population.

    Args:
        raw_impulse: Raw impulse value (points per bar)
        formed_impulses: Sorted list of impulse values from all formed legs

    Returns:
        Percentile rank (0-100) or None if population is empty.
    """
    if not formed_impulses:
        return None

    # Find position where raw_impulse would be inserted
    position = bisect.bisect_left(formed_impulses, raw_impulse)

    # Percentile = (count of values below) / total * 100
    return (position / len(formed_impulses)) * 100


def _calculate_segment_impulse(
    parent: Leg,
    child_origin_price: Decimal,
    child_origin_index: int
) -> None:
    """
    Calculate and store segment impulse on parent when first child forms (#307).

    The segment is: parent.origin -> parent.pivot (deepest) -> child.origin

    Args:
        parent: The parent leg to update with segment impulse.
        child_origin_price: Origin price of the child leg.
        child_origin_index: Bar index of the child's origin.
    """
    # The deepest point is the parent's current pivot (before child takes over)
    deepest_price = parent.pivot_price
    deepest_index = parent.pivot_index

    # Impulse TO deepest (the primary move)
    range_to_deepest = abs(parent.origin_price - deepest_price)
    bars_to_deepest = abs(deepest_index - parent.origin_index)
    impulse_to_deepest = float(range_to_deepest) / bars_to_deepest if bars_to_deepest > 0 else 0.0

    # Impulse BACK to child origin (the counter-move)
    range_back = abs(deepest_price - child_origin_price)
    bars_back = abs(child_origin_index - deepest_index)
    impulse_back = float(range_back) / bars_back if bars_back > 0 else 0.0

    # Store on parent
    parent.segment_deepest_price = deepest_price
    parent.segment_deepest_index = deepest_index
    parent.impulse_to_deepest = impulse_to_deepest
    parent.impulse_back = impulse_back


def _update_segment_impulse_for_new_child(
    parent: Leg,
    new_child_origin_price: Decimal,
    new_child_origin_index: int
) -> None:
    """
    Update segment impulse when a new child forms at a higher origin (#307).

    Two cases:
    1. Parent's pivot extended deeper than stored deepest -> recalculate BOTH
    2. Parent's pivot same as stored deepest -> only update impulse_back

    Args:
        parent: The parent leg to update.
        new_child_origin_price: Origin price of the new child.
        new_child_origin_index: Bar index of the new child's origin.
    """
    if parent.segment_deepest_price is None:
        # No segment established yet - treat as first child
        _calculate_segment_impulse(parent, new_child_origin_price, new_child_origin_index)
        return

    current_pivot = parent.pivot_price
    current_pivot_index = parent.pivot_index

    # Check if pivot extended deeper
    pivot_extended_deeper = (
        (parent.direction == 'bear' and current_pivot < parent.segment_deepest_price) or
        (parent.direction == 'bull' and current_pivot > parent.segment_deepest_price)
    )

    if pivot_extended_deeper:
        # Deepest changed! Recalculate BOTH impulse components
        parent.segment_deepest_price = current_pivot
        parent.segment_deepest_index = current_pivot_index

        # Recalculate impulse_to_deepest
        range_to_deepest = abs(parent.origin_price - current_pivot)
        bars_to_deepest = abs(current_pivot_index - parent.origin_index)
        parent.impulse_to_deepest = float(range_to_deepest) / bars_to_deepest if bars_to_deepest > 0 else 0.0

    # Always recalculate impulse_back with new child origin
    range_back = abs(parent.segment_deepest_price - new_child_origin_price)
    bars_back = abs(new_child_origin_index - parent.segment_deepest_index)
    parent.impulse_back = float(range_back) / bars_back if bars_back > 0 else 0.0


def _calculate_spikiness(n: int, sum_x: float, sum_x2: float, sum_x3: float) -> Optional[float]:
    """
    Calculate spikiness (0-100) from running moments using Fisher's skewness (#241, #244).

    Spikiness measures whether the move was spike-driven or evenly distributed:
    - 50 = neutral (symmetric distribution)
    - 70+ = moderately spiky
    - 90+ = very spiky (outlier bars drove the move)
    - 30- = moderately smooth
    - 10- = very smooth (evenly distributed)

    Uses sigmoid normalization: spikiness = 100 / (1 + exp(-skewness))

    Args:
        n: Number of bar contributions tracked
        sum_x: Sum of contributions
        sum_x2: Sum of squared contributions
        sum_x3: Sum of cubed contributions

    Returns:
        Spikiness (0-100) or None if n < 3 (skewness undefined).
    """
    import math

    # Need at least 3 samples for meaningful skewness
    if n < 3:
        return None

    # Calculate mean and variance from moments
    mean = sum_x / n
    variance = (sum_x2 / n) - mean * mean

    # Guard against near-zero variance (would cause division by zero)
    if variance < 1e-10:
        return 50.0  # Neutral if all contributions are identical

    std_dev = math.sqrt(variance)

    # Calculate third central moment for skewness
    # E[(X - μ)³] = E[X³] - 3μE[X²] + 2μ³
    third_moment = (sum_x3 / n) - 3 * mean * (sum_x2 / n) + 2 * mean ** 3

    # Fisher's skewness = third_moment / std_dev³
    skewness = third_moment / (std_dev ** 3)

    # Sigmoid normalization to 0-100 range
    # This maps any skewness value to a bounded 0-100 scale
    spikiness = 100 / (1 + math.exp(-skewness))

    return spikiness


class LegDetector:
    """
    DAG-based leg detector for the structural layer.

    Detects and tracks legs incrementally. Forms swings when legs
    reach the formation threshold (default 38.2% retracement).

    Processes one bar at a time via process_bar(). Calibration is just
    a loop calling process_bar() - no special batch logic.

    Key design principles:
    1. No lookahead - Algorithm only sees current and past bars
    2. Single code path - Calibration will just call this in a loop
    3. Independent invalidation - Each swing checks its own defended pivot
    4. DAG hierarchy - Swings can have multiple parents for structural context

    Example:
        >>> config = SwingConfig.default()
        >>> detector = LegDetector(config)
        >>> for bar in bars:
        ...     events = detector.process_bar(bar)
        ...     for event in events:
        ...         print(event.event_type, event.swing_id)
        >>> state = detector.get_state()
        >>> # Resume later
        >>> detector2 = LegDetector.from_state(state, config)
    """

    def __init__(self, config: SwingConfig = None):
        """
        Initialize detector with configuration.

        Args:
            config: SwingConfig with detection parameters.
                   If None, uses SwingConfig.default().
        """
        self.config = config or SwingConfig.default()
        self.state = DetectorState()
        self._pruner = LegPruner(self.config)

    def _classify_bar_type(self, bar: Bar, prev_bar: Bar) -> BarType:
        """
        Classify the relationship between current and previous bar.

        Types:
        - Type 1 (Inside): LH and HL - bar contained within previous
        - Type 2-Bull: HH and HL - trending up, establishes temporal order
        - Type 2-Bear: LH and LL - trending down, establishes temporal order
        - Type 3 (Outside): HH and LL - engulfing, high volatility

        Args:
            bar: Current bar
            prev_bar: Previous bar

        Returns:
            BarType enum value
        """
        higher_high = bar.high > prev_bar.high
        higher_low = bar.low > prev_bar.low
        lower_high = bar.high < prev_bar.high
        lower_low = bar.low < prev_bar.low

        # Handle equal highs/lows - treat as not exceeding
        if bar.high == prev_bar.high:
            higher_high = False
            lower_high = False
        if bar.low == prev_bar.low:
            higher_low = False
            lower_low = False

        if higher_high and higher_low:
            return BarType.TYPE_2_BULL
        elif lower_high and lower_low:
            return BarType.TYPE_2_BEAR
        elif higher_high and lower_low:
            return BarType.TYPE_3
        else:  # lower_high and higher_low (inside bar)
            return BarType.TYPE_1

    def _extend_leg_pivots(self, bar: Bar, bar_high: Decimal, bar_low: Decimal) -> None:
        """
        Extend leg pivots when price makes new extremes (#188, #197).

        Terminology (correct):
        - Origin: Where the move started (fixed, does NOT extend)
        - Pivot: Current defended extreme (extends as leg grows)

        Bull leg: origin at LOW (fixed) -> pivot at HIGH (extends on new highs)
        Bear leg: origin at HIGH (fixed) -> pivot at LOW (extends on new lows)

        IMPORTANT (#208): Pivots only extend if the origin has never been breached.
        If the origin was breached, the leg is structurally compromised and
        pivot extension is disabled.

        IMPORTANT (#338): When a leg's pivot extends, also update the pending origin
        for the opposite direction. This ensures bear legs form at bull pivots
        (and vice versa), which is required for branch ratio domination (#337)
        to find matching counter-trend legs.

        This fixes the bug where bars with HH+EL (higher high, equal low) or
        EH+LL (equal high, lower low) were classified as Type 1 and didn't
        extend pivots, causing legs to show stale pivot values.

        Args:
            bar: Current bar
            bar_high: Current bar's high as Decimal
            bar_low: Current bar's low as Decimal
        """
        # Extend bull leg pivots on new highs (only if origin not breached #208, #345)
        for leg in self.state.active_legs:
            # Only extend legs that are structurally live (no origin breach)
            if leg.direction == 'bull' and leg.max_origin_breach is None:
                if bar_high > leg.pivot_price:
                    leg.update_pivot(bar_high, bar.index)
                    leg.last_modified_bar = bar.index
                    # Recalculate impulse when pivot extends (#236)
                    leg.impulse = _calculate_impulse(leg.range, leg.origin_index, leg.pivot_index)
                    # Update pending bear origin to this pivot (#338)
                    # This ensures bear legs form at bull pivots where R0 will match
                    self.state.pending_origins['bear'] = PendingOrigin(
                        price=bar_high, bar_index=bar.index, direction='bear', source='pivot_extension'
                    )

        # Extend bear leg pivots on new lows (only if origin not breached #208, #345)
        for leg in self.state.active_legs:
            # Only extend legs that are structurally live (no origin breach)
            if leg.direction == 'bear' and leg.max_origin_breach is None:
                if bar_low < leg.pivot_price:
                    leg.update_pivot(bar_low, bar.index)
                    leg.last_modified_bar = bar.index
                    # Recalculate impulse when pivot extends (#236)
                    leg.impulse = _calculate_impulse(leg.range, leg.origin_index, leg.pivot_index)
                    # Update pending bull origin to this pivot (#338)
                    # This ensures bull legs form at bear pivots where R0 will match
                    self.state.pending_origins['bull'] = PendingOrigin(
                        price=bar_low, bar_index=bar.index, direction='bull', source='pivot_extension'
                    )

    def _find_origin_counter_trend_range(self, direction: str, origin_price: Decimal) -> Optional[float]:
        """
        Find the range of the longest opposite-direction leg at this origin (#336).

        For a new bull leg with origin at price P, find the longest bear leg
        whose pivot is at P. This represents the counter-trend pressure that
        accumulated at this price level before the new leg starts.

        The value is captured once at leg creation and never changes, even if
        the opposite leg is later pruned.

        NOTE: We do NOT filter by status because the opposite leg may have been
        invalidated by the time this leg is created. We want the range of the
        biggest leg that EVER existed at this pivot, regardless of current status.

        Args:
            direction: Direction of the new leg ('bull' or 'bear')
            origin_price: Origin price of the new leg

        Returns:
            Range of longest opposite leg at this origin, or None if no matches
        """
        opposite_direction = 'bear' if direction == 'bull' else 'bull'

        # Don't filter by status - we want ANY leg that ever existed at this pivot
        # The leg may be invalidated but still in active_legs
        matching_legs = [
            leg for leg in self.state.active_legs
            if leg.direction == opposite_direction
            and leg.pivot_price == origin_price
        ]

        if matching_legs:
            longest = max(matching_legs, key=lambda l: l.range)
            return float(longest.range)
        return None

    def _update_breach_tracking(
        self,
        bar: Bar,
        bar_high: Decimal,
        bar_low: Decimal,
        timestamp: datetime
    ) -> Tuple[List[SwingEvent], List[Leg]]:
        """
        Update breach tracking for all active legs (#208, #345).

        Tracks maximum breach beyond origin and pivot for each leg.
        - Origin breach: price moved past the origin (structural gate for behavior)
        - Pivot breach: price moved past the pivot (violating defended level)

        Origin breach is now the sole structural gate (#345):
        - When origin is breached, the leg is structurally compromised
        - Extensions and formations are disabled for origin-breached legs
        - If the leg has a swing, the swing is also invalidated

        Pivot breach is only tracked for FORMED legs. Once formed, the pivot
        is frozen as a structural reference. Price going past it = breach.
        For unformed legs, price movement past pivot is extension, not breach.

        Origin breach and pivot breach are independent - either can happen
        without the other. If BOTH happen, the leg is "engulfed".

        Args:
            bar: Current bar being processed
            bar_high: Current bar's high as Decimal
            bar_low: Current bar's low as Decimal
            timestamp: Timestamp for events

        Returns:
            Tuple of (events, newly_breached_legs) where events include
            OriginBreachedEvent, PivotBreachedEvent, and SwingInvalidatedEvent.
        """
        events: List[SwingEvent] = []
        newly_breached_legs: List[Leg] = []

        for leg in self.state.active_legs:
            # Skip legs that are completely done (stale/pruned)
            if leg.status != 'active':
                continue

            # Origin breach tracking (only for legs not yet breached)
            if leg.max_origin_breach is None:
                origin_just_breached = False
                breach_price = Decimal("0")
                if leg.direction == 'bull':
                    # Bull origin (low) breached when price goes below it
                    if bar_low < leg.origin_price:
                        breach = leg.origin_price - bar_low
                        leg.max_origin_breach = breach
                        origin_just_breached = True
                        breach_price = bar_low
                else:  # bear
                    # Bear origin (high) breached when price goes above it
                    if bar_high > leg.origin_price:
                        breach = bar_high - leg.origin_price
                        leg.max_origin_breach = breach
                        origin_just_breached = True
                        breach_price = bar_high

                if origin_just_breached:
                    newly_breached_legs.append(leg)
                    events.append(OriginBreachedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=leg.swing_id or "",
                        leg_id=leg.leg_id,
                        breach_price=breach_price,
                        breach_amount=leg.max_origin_breach,
                    ))
                    # Propagate to swing if leg formed into one (#174, #345)
                    if leg.swing_id:
                        for swing in self.state.active_swings:
                            if swing.swing_id == leg.swing_id and swing.status == 'active':
                                swing.invalidate()
                                events.append(SwingInvalidatedEvent(
                                    bar_index=bar.index,
                                    timestamp=timestamp,
                                    swing_id=swing.swing_id,
                                    reason="origin_breached",
                                ))
                                break
            else:
                # Update max_origin_breach if current breach is larger
                if leg.direction == 'bull':
                    if bar_low < leg.origin_price:
                        breach = leg.origin_price - bar_low
                        if breach > leg.max_origin_breach:
                            leg.max_origin_breach = breach
                else:  # bear
                    if bar_high > leg.origin_price:
                        breach = bar_high - leg.origin_price
                        if breach > leg.max_origin_breach:
                            leg.max_origin_breach = breach

            # Pivot breach tracking (formed legs only)
            # Once formed, the pivot is frozen as a structural reference
            # Price going past it = breach (for unformed legs, it would just extend)
            if leg.formed and leg.range > 0:
                if leg.direction == 'bull':
                    # Bull pivot (HIGH) breached when price goes above it
                    if bar_high > leg.pivot_price:
                        breach = bar_high - leg.pivot_price
                        was_first_breach = leg.max_pivot_breach is None
                        if was_first_breach or breach > leg.max_pivot_breach:
                            leg.max_pivot_breach = breach
                        # Emit event on FIRST breach only
                        if was_first_breach:
                            events.append(PivotBreachedEvent(
                                bar_index=bar.index,
                                timestamp=timestamp,
                                swing_id=leg.swing_id or "",
                                leg_id=leg.leg_id,
                                breach_price=bar_high,
                                breach_amount=breach,
                            ))
                else:  # bear
                    # Bear pivot (LOW) breached when price goes below it
                    if bar_low < leg.pivot_price:
                        breach = leg.pivot_price - bar_low
                        was_first_breach = leg.max_pivot_breach is None
                        if was_first_breach or breach > leg.max_pivot_breach:
                            leg.max_pivot_breach = breach
                        # Emit event on FIRST breach only
                        if was_first_breach:
                            events.append(PivotBreachedEvent(
                                bar_index=bar.index,
                                timestamp=timestamp,
                                swing_id=leg.swing_id or "",
                                leg_id=leg.leg_id,
                                breach_price=bar_low,
                                breach_amount=breach,
                            ))

        return events, newly_breached_legs

    def _update_dag_state(self, bar: Bar, timestamp: datetime) -> List[SwingFormedEvent]:
        """
        Update DAG state with new bar using streaming leg tracking.

        This is the core of the O(n log k) algorithm. Instead of generating
        O(k^2) candidate pairs, we track active legs and update them as bars
        arrive.

        Args:
            bar: Current bar being processed
            timestamp: Timestamp for events

        Returns:
            List of SwingFormedEvent for any newly formed swings
        """
        events: List[SwingFormedEvent] = []
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))
        bar_close = Decimal(str(bar.close))
        bar_open = Decimal(str(bar.open))

        # Prune engulfed legs (both origin and pivot breached) (#208, #305)
        engulfed_events = self._pruner.prune_engulfed_legs(
            self.state, bar, timestamp
        )
        events.extend(engulfed_events)

        # Extend leg pivots on new extremes (#188, #192, #197)
        # This must happen BEFORE bar type classification because bars with
        # HH+EL or EH+LL fall through to Type 1 which didn't extend pivots.
        # Origins are FIXED (where move started) and do NOT extend.
        # Only pivots (current defended extreme) extend as price moves.
        self._extend_leg_pivots(bar, bar_high, bar_low)

        # Note: CTR pruning removed in #337 - replaced by branch ratio origin domination
        # which prevents insignificant legs at creation time rather than pruning after.

        # Update breach tracking for all legs (#208, #345)
        # Returns breach events and list of newly breached legs for inner structure pruning
        breach_events, newly_breached_legs = self._update_breach_tracking(bar, bar_high, bar_low, timestamp)
        events.extend(breach_events)

        # Prune inner structure legs when legs get origin-breached (#264, #279, #345)
        if newly_breached_legs:
            # Gather ALL origin-breached legs (current bar + previously breached)
            all_breached = [
                leg for leg in self.state.active_legs
                if leg.max_origin_breach is not None
            ]
            if len(all_breached) >= 2:
                inner_prune_events = self._pruner.prune_inner_structure_legs(
                    self.state, all_breached, bar, timestamp
                )
                events.extend(inner_prune_events)

        # First bar initialization
        if self.state.prev_bar is None:
            self._initialize_first_bar(bar, bar_open, bar_close)
            self.state.prev_bar = bar
            return events

        # Classify bar type
        bar_type = self._classify_bar_type(bar, self.state.prev_bar)
        prev_high = Decimal(str(self.state.prev_bar.high))
        prev_low = Decimal(str(self.state.prev_bar.low))

        # Turn detection (#202): Track when direction changes
        # When transitioning from bear to bull (or vice versa), mark this bar
        # as the start of a new turn. Domination checks should only apply
        # within a turn, not across turns.
        #
        # Key insight: Only set last_turn_bar when transitioning FROM the opposite
        # direction. The first TYPE_2_BULL ever seen does NOT start a new turn -
        # it continues the initial state. Only when we see TYPE_2_BEAR followed
        # by TYPE_2_BULL do we mark a new bull turn.
        current_directional_type = None
        if bar_type == BarType.TYPE_2_BULL:
            current_directional_type = 'bull'
        elif bar_type == BarType.TYPE_2_BEAR:
            current_directional_type = 'bear'

        if current_directional_type:
            # Check for turn transition - only when coming FROM the opposite direction
            if self.state.prev_bar_type and self.state.prev_bar_type != current_directional_type:
                # Direction changed! This bar starts a new turn for this direction.
                # IMPORTANT: Use the pending origin's bar index as the turn boundary,
                # not the current bar. The pending origin was set during the opposite
                # direction's turn and will be used to create the first leg of this turn.
                # That leg should be considered part of the new turn for domination checks.
                pending = self.state.pending_origins.get(current_directional_type)
                if pending:
                    self.state.last_turn_bar[current_directional_type] = pending.bar_index
                else:
                    self.state.last_turn_bar[current_directional_type] = bar.index
            # Note: We intentionally do NOT set last_turn_bar on first directional bar
            # of each type. The first TYPE_2_BULL doesn't create a turn boundary -
            # all legs from the beginning are part of the same initial structure.
            # Update prev_bar_type
            self.state.prev_bar_type = current_directional_type

        # Process based on bar type
        if bar_type == BarType.TYPE_2_BULL:
            events.extend(self._process_type2_bull(bar, timestamp, bar_high, bar_low, bar_close, prev_high, prev_low))
        elif bar_type == BarType.TYPE_2_BEAR:
            events.extend(self._process_type2_bear(bar, timestamp, bar_high, bar_low, bar_close, prev_high, prev_low))
        elif bar_type == BarType.TYPE_1:
            events.extend(self._process_type1(bar, timestamp, bar_high, bar_low, bar_close))
        elif bar_type == BarType.TYPE_3:
            events.extend(self._process_type3(bar, timestamp, bar_high, bar_low, bar_close, prev_high, prev_low))

        # Increment bar count for all live legs (origin not breached) (#345)
        for leg in self.state.active_legs:
            if leg.status == 'active' and leg.max_origin_breach is None:
                leg.bar_count += 1

        # Check 3x extension pruning for origin-breached legs (#203, #345)
        extension_prune_events = self._check_extension_prune(bar, timestamp)
        events.extend(extension_prune_events)

        # Store current bar as previous for next iteration
        self.state.prev_bar = bar

        return events

    def _initialize_first_bar(self, bar: Bar, bar_open: Decimal, bar_close: Decimal) -> None:
        """
        Initialize state from first bar.

        We cannot create legs from the first bar alone since we don't know
        intra-bar temporal ordering of H and L. Instead, we set up pending
        pivots at the bar's extremes for use when the next bar arrives.

        The next bar's relationship (Type 1/2-Bull/2-Bear/3) will tell us
        the temporal ordering and allow leg creation.
        """
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))

        # Set pending origins at bar extremes
        # High could be origin for future bear legs (bear origin = HIGH)
        self.state.pending_origins['bear'] = PendingOrigin(
            price=bar_high, bar_index=bar.index, direction='bear', source='high'
        )
        # Low could be origin for future bull legs (bull origin = LOW)
        self.state.pending_origins['bull'] = PendingOrigin(
            price=bar_low, bar_index=bar.index, direction='bull', source='low'
        )

    def _process_type2_bull(
        self, bar: Bar, timestamp: datetime,
        bar_high: Decimal, bar_low: Decimal, bar_close: Decimal,
        prev_high: Decimal, prev_low: Decimal
    ) -> List[SwingEvent]:
        """
        Process Type 2-Bull bar (HH, HL - trending up).

        Establishes temporal order: prev_bar.L occurred before bar.H.
        This confirms a BEAR swing structure: prev_bar.L -> bar.H (low origin -> high pivot).

        Also extends any existing bull legs (tracking upward movement).
        """
        events: List[SwingEvent] = []

        # Apply origin-proximity pruning for bear legs (#294)
        proximity_prune_events = self._pruner.apply_origin_proximity_prune(self.state, 'bear', bar, timestamp)
        events.extend(proximity_prune_events)

        # Note: CTR pruning moved to process_bar() after _extend_leg_pivots (#336)

        # Check if we can start a bull leg from the pending bull origin
        # prev_low is the origin (starting point) for a bull swing extending up
        # Only create if there isn't already a bull leg with the same origin
        if self.state.pending_origins.get('bull'):
            pending = self.state.pending_origins['bull']
            # Check if we already have a live bull leg from this origin (#345)
            # Origin-breached legs don't block new leg creation at the same price
            existing_bull_leg = any(
                leg.direction == 'bull' and leg.max_origin_breach is None
                and leg.origin_price == pending.price and leg.origin_index == pending.bar_index
                for leg in self.state.active_legs
            )
            # Skip if dominated by existing leg with better origin (#194)
            if self._pruner.would_leg_be_dominated(self.state, 'bull', pending.price):
                existing_bull_leg = True
            # Pivot extension handled by _extend_leg_pivots (#188)
            if not existing_bull_leg:
                # Find parent BEFORE creating leg (leg not yet in active_legs)
                parent_leg_id = self._find_parent_for_leg('bull', pending.price, pending.bar_index)
                # Check branch ratio domination (#337)
                if self._is_origin_dominated_by_branch_ratio('bull', pending.price, parent_leg_id):
                    existing_bull_leg = True  # Skip creation
            if not existing_bull_leg:
                # Create new bull leg: origin at LOW -> pivot at HIGH
                leg_range = abs(bar_high - pending.price)
                parent_leg_id = self._find_parent_for_leg('bull', pending.price, pending.bar_index)
                # Capture counter-trend range at origin (#336)
                origin_ctr = self._find_origin_counter_trend_range('bull', pending.price)
                new_leg = Leg(
                    direction='bull',
                    origin_price=pending.price,  # LOW - where upward move started
                    origin_index=pending.bar_index,
                    pivot_price=bar_high,  # HIGH - current defended extreme
                    pivot_index=bar.index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                    impulse=_calculate_impulse(leg_range, pending.bar_index, bar.index),
                    parent_leg_id=parent_leg_id,  # Hierarchy assignment (#281)
                    origin_counter_trend_range=origin_ctr,  # (#336)
                    _max_counter_leg_range=origin_ctr,  # (#341) Turn ratio denominator
                )
                self.state.active_legs.append(new_leg)
                # Prune counter-legs at origin with low turn ratio (#341)
                turn_ratio_events = self._pruner.prune_by_turn_ratio(
                    self.state, new_leg, bar, timestamp
                )
                events.extend(turn_ratio_events)
                # Update parent's segment impulse when child forms (#307)
                if parent_leg_id:
                    parent = self._find_leg_by_id(parent_leg_id)
                    if parent:
                        _update_segment_impulse_for_new_child(
                            parent, pending.price, pending.bar_index
                        )
                # Clear pending origin after leg creation (#197)
                self.state.pending_origins['bull'] = None
                # Emit LegCreatedEvent (#168)
                events.append(LegCreatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",  # Leg doesn't have swing_id yet
                    leg_id=new_leg.leg_id,
                    direction=new_leg.direction,
                    origin_price=new_leg.origin_price,
                    origin_index=new_leg.origin_index,
                    pivot_price=new_leg.pivot_price,
                    pivot_index=new_leg.pivot_index,
                ))

        # Update pending origins only if more extreme AND not worse than active leg origins (#200)
        # Bear origin: only update if this high is higher (tracking swing highs for bear legs)
        existing_bear = self.state.pending_origins.get('bear')
        if (existing_bear is None or bar_high > existing_bear.price) and self._should_track_pending_origin('bear', bar_high):
            self.state.pending_origins['bear'] = PendingOrigin(
                price=bar_high, bar_index=bar.index, direction='bear', source='high'
            )
        # Bull origin: only update if this low is lower (tracking swing lows for bull legs)
        existing_bull = self.state.pending_origins.get('bull')
        if (existing_bull is None or bar_low < existing_bull.price) and self._should_track_pending_origin('bull', bar_low):
            self.state.pending_origins['bull'] = PendingOrigin(
                price=bar_low, bar_index=bar.index, direction='bull', source='low'
            )

        # Check for formations using close price (don't know H/L order within bar)
        events.extend(self._check_leg_formations(bar, timestamp, bar_close))

        return events

    def _process_type2_bear(
        self, bar: Bar, timestamp: datetime,
        bar_high: Decimal, bar_low: Decimal, bar_close: Decimal,
        prev_high: Decimal, prev_low: Decimal
    ) -> List[SwingEvent]:
        """
        Process Type 2-Bear bar (LH, LL - trending down).

        TYPE_2_BEAR signals a downtrend, so we only create bear legs here.
        Bull legs are NOT created in TYPE_2_BEAR because:
        1. Price is trending down, so expecting upward movement doesn't make sense
        2. Creating bull legs here would result in inverted temporal order
           (origin_index < pivot_index instead of pivot_index < origin_index)

        See issue #195 for details on the temporal order bug this fixes.
        """
        events: List[SwingEvent] = []

        # Apply origin-proximity pruning for bull legs (#294)
        proximity_prune_events = self._pruner.apply_origin_proximity_prune(self.state, 'bull', bar, timestamp)
        events.extend(proximity_prune_events)

        # Note: CTR pruning moved to process_bar() after _extend_leg_pivots (#336)

        # Start new bear leg for potential bear swing
        # (tracking downward movement for possible bear retracement later)
        if self.state.pending_origins.get('bear'):
            pending = self.state.pending_origins['bear']
            # Only create if we don't already have a live bear leg with this origin (#345)
            # Origin-breached legs don't block new leg creation at the same price
            existing_bear_leg = any(
                leg.direction == 'bear' and leg.max_origin_breach is None
                and leg.origin_price == pending.price and leg.origin_index == pending.bar_index
                for leg in self.state.active_legs
            )
            # Skip if dominated by existing leg with better origin (#194)
            if self._pruner.would_leg_be_dominated(self.state, 'bear', pending.price):
                existing_bear_leg = True
            # Pivot extension handled by _extend_leg_pivots (#188)
            if not existing_bear_leg:
                # Find parent BEFORE creating leg (leg not yet in active_legs)
                parent_leg_id = self._find_parent_for_leg('bear', pending.price, pending.bar_index)
                # Check branch ratio domination (#337)
                if self._is_origin_dominated_by_branch_ratio('bear', pending.price, parent_leg_id):
                    existing_bear_leg = True  # Skip creation
            if not existing_bear_leg:
                leg_range = abs(pending.price - bar_low)
                parent_leg_id = self._find_parent_for_leg('bear', pending.price, pending.bar_index)
                # Capture counter-trend range at origin (#336)
                origin_ctr = self._find_origin_counter_trend_range('bear', pending.price)
                new_bear_leg = Leg(
                    direction='bear',
                    origin_price=pending.price,  # HIGH - where downward move started
                    origin_index=pending.bar_index,
                    pivot_price=bar_low,  # LOW - current defended extreme
                    pivot_index=bar.index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                    impulse=_calculate_impulse(leg_range, pending.bar_index, bar.index),
                    parent_leg_id=parent_leg_id,  # Hierarchy assignment (#281)
                    origin_counter_trend_range=origin_ctr,  # (#336)
                    _max_counter_leg_range=origin_ctr,  # (#341) Turn ratio denominator
                )
                self.state.active_legs.append(new_bear_leg)
                # Prune counter-legs at origin with low turn ratio (#341)
                turn_ratio_events = self._pruner.prune_by_turn_ratio(
                    self.state, new_bear_leg, bar, timestamp
                )
                events.extend(turn_ratio_events)
                # Update parent's segment impulse when child forms (#307)
                if parent_leg_id:
                    parent = self._find_leg_by_id(parent_leg_id)
                    if parent:
                        _update_segment_impulse_for_new_child(
                            parent, pending.price, pending.bar_index
                        )
                # Clear pending origin after leg creation (#197)
                self.state.pending_origins['bear'] = None
                # Emit LegCreatedEvent (#168)
                events.append(LegCreatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",
                    leg_id=new_bear_leg.leg_id,
                    direction=new_bear_leg.direction,
                    origin_price=new_bear_leg.origin_price,
                    origin_index=new_bear_leg.origin_index,
                    pivot_price=new_bear_leg.pivot_price,
                    pivot_index=new_bear_leg.pivot_index,
                ))

        # Update pending origins only if more extreme AND not worse than active leg origins (#200)
        # Bull origin: only update if this low is lower (tracking swing lows for bull legs)
        existing_bull = self.state.pending_origins.get('bull')
        if (existing_bull is None or bar_low < existing_bull.price) and self._should_track_pending_origin('bull', bar_low):
            self.state.pending_origins['bull'] = PendingOrigin(
                price=bar_low, bar_index=bar.index, direction='bull', source='low'
            )
        # Bear origin: only update if this high is higher (tracking swing highs for bear legs)
        existing_bear = self.state.pending_origins.get('bear')
        if (existing_bear is None or bar_high > existing_bear.price) and self._should_track_pending_origin('bear', bar_high):
            self.state.pending_origins['bear'] = PendingOrigin(
                price=bar_high, bar_index=bar.index, direction='bear', source='high'
            )

        # Check for formations using close price
        events.extend(self._check_leg_formations(bar, timestamp, bar_close))

        return events

    def _process_type1(
        self, bar: Bar, timestamp: datetime,
        bar_high: Decimal, bar_low: Decimal, bar_close: Decimal
    ) -> List[SwingEvent]:
        """
        Process Type 1 bar (inside bar - LH, HL) or bars with equal H/L.

        Inside bars still have valid temporal ordering between bars:
        - prev_bar.H came before bar.L (can establish bear swing structure)
        - prev_bar.L came before bar.H (can establish bull swing structure)

        We should create legs from pending origins if they haven't been consumed yet.
        """
        events: List[SwingEvent] = []
        prev_bar = self.state.prev_bar
        if prev_bar:
            pending_bear = self.state.pending_origins.get('bear')  # High origin (for bear legs)
            pending_bull = self.state.pending_origins.get('bull')  # Low origin (for bull legs)

            # Create bear leg if HIGH came before LOW (price moved down)
            # Bear swing: origin=HIGH (starting point), pivot=LOW (defended extreme)
            # Temporal order: origin_index < pivot_index (#195)
            if pending_bear and pending_bull:
                # pending_bear = HIGH, pending_bull = LOW
                # If HIGH came before LOW, this is a BEAR structure
                # Skip if dominated by existing leg with better origin (#194)
                should_create_bear = (
                    pending_bear.bar_index < pending_bull.bar_index
                    and not self._pruner.would_leg_be_dominated(self.state, 'bear', pending_bear.price)
                )
                if should_create_bear:
                    # Find parent and check branch ratio domination (#337)
                    parent_leg_id = self._find_parent_for_leg('bear', pending_bear.price, pending_bear.bar_index)
                    if self._is_origin_dominated_by_branch_ratio('bear', pending_bear.price, parent_leg_id):
                        should_create_bear = False
                if should_create_bear:
                    leg_range = abs(pending_bear.price - pending_bull.price)
                    parent_leg_id = self._find_parent_for_leg('bear', pending_bear.price, pending_bear.bar_index)
                    # Capture counter-trend range at origin (#336)
                    origin_ctr = self._find_origin_counter_trend_range('bear', pending_bear.price)
                    new_bear_leg = Leg(
                        direction='bear',
                        origin_price=pending_bear.price,  # HIGH - where downward move started
                        origin_index=pending_bear.bar_index,
                        pivot_price=pending_bull.price,  # LOW - current defended extreme
                        pivot_index=pending_bull.bar_index,
                        price_at_creation=bar_close,
                        last_modified_bar=bar.index,
                        impulse=_calculate_impulse(leg_range, pending_bear.bar_index, pending_bull.bar_index),
                        parent_leg_id=parent_leg_id,  # Hierarchy assignment (#281)
                        origin_counter_trend_range=origin_ctr,  # (#336)
                        _max_counter_leg_range=origin_ctr,  # (#341) Turn ratio denominator
                    )
                    self.state.active_legs.append(new_bear_leg)
                    # Prune counter-legs at origin with low turn ratio (#341)
                    turn_ratio_events = self._pruner.prune_by_turn_ratio(
                        self.state, new_bear_leg, bar, timestamp
                    )
                    events.extend(turn_ratio_events)
                    # Update parent's segment impulse when child forms (#307)
                    if parent_leg_id:
                        parent = self._find_leg_by_id(parent_leg_id)
                        if parent:
                            _update_segment_impulse_for_new_child(
                                parent, pending_bear.price, pending_bear.bar_index
                            )
                    # Clear pending origins after leg creation (#197)
                    self.state.pending_origins['bear'] = None
                    self.state.pending_origins['bull'] = None
                    # Emit LegCreatedEvent (#168)
                    events.append(LegCreatedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id="",
                        leg_id=new_bear_leg.leg_id,
                        direction=new_bear_leg.direction,
                        origin_price=new_bear_leg.origin_price,
                        origin_index=new_bear_leg.origin_index,
                        pivot_price=new_bear_leg.pivot_price,
                        pivot_index=new_bear_leg.pivot_index,
                    ))

            # Create bull leg if LOW came before HIGH (price moved up)
            # Bull swing: origin=LOW (starting point), pivot=HIGH (defended extreme)
            # Temporal order: origin_index < pivot_index (#195)
            if pending_bear and pending_bull:
                # pending_bull = LOW, pending_bear = HIGH
                # If LOW came before HIGH, this is a BULL structure
                # Skip if dominated by existing leg with better origin (#194)
                should_create_bull = (
                    pending_bull.bar_index < pending_bear.bar_index
                    and not self._pruner.would_leg_be_dominated(self.state, 'bull', pending_bull.price)
                )
                if should_create_bull:
                    # Find parent and check branch ratio domination (#337)
                    parent_leg_id = self._find_parent_for_leg('bull', pending_bull.price, pending_bull.bar_index)
                    if self._is_origin_dominated_by_branch_ratio('bull', pending_bull.price, parent_leg_id):
                        should_create_bull = False
                if should_create_bull:
                    leg_range = abs(pending_bear.price - pending_bull.price)
                    parent_leg_id = self._find_parent_for_leg('bull', pending_bull.price, pending_bull.bar_index)
                    # Capture counter-trend range at origin (#336)
                    origin_ctr = self._find_origin_counter_trend_range('bull', pending_bull.price)
                    new_bull_leg = Leg(
                        direction='bull',
                        origin_price=pending_bull.price,  # LOW - where upward move started
                        origin_index=pending_bull.bar_index,
                        pivot_price=pending_bear.price,  # HIGH - current defended extreme
                        pivot_index=pending_bear.bar_index,
                        price_at_creation=bar_close,
                        last_modified_bar=bar.index,
                        impulse=_calculate_impulse(leg_range, pending_bull.bar_index, pending_bear.bar_index),
                        parent_leg_id=parent_leg_id,  # Hierarchy assignment (#281)
                        origin_counter_trend_range=origin_ctr,  # (#336)
                        _max_counter_leg_range=origin_ctr,  # (#341) Turn ratio denominator
                    )
                    self.state.active_legs.append(new_bull_leg)
                    # Prune counter-legs at origin with low turn ratio (#341)
                    turn_ratio_events = self._pruner.prune_by_turn_ratio(
                        self.state, new_bull_leg, bar, timestamp
                    )
                    events.extend(turn_ratio_events)
                    # Update parent's segment impulse when child forms (#307)
                    if parent_leg_id:
                        parent = self._find_leg_by_id(parent_leg_id)
                        if parent:
                            _update_segment_impulse_for_new_child(
                                parent, pending_bull.price, pending_bull.bar_index
                            )
                    # Clear pending origins after leg creation (#197)
                    self.state.pending_origins['bull'] = None
                    self.state.pending_origins['bear'] = None
                    # Emit LegCreatedEvent (#168)
                    events.append(LegCreatedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id="",
                        leg_id=new_bull_leg.leg_id,
                        direction=new_bull_leg.direction,
                        origin_price=new_bull_leg.origin_price,
                        origin_index=new_bull_leg.origin_index,
                        pivot_price=new_bull_leg.pivot_price,
                        pivot_index=new_bull_leg.pivot_index,
                    ))

            # Update pending origins only if more extreme AND not worse than active leg origins (#200)
            # Bear origin: only update if this high is higher (tracking swing highs for bear legs)
            existing_bear = self.state.pending_origins.get('bear')
            if (existing_bear is None or bar_high > existing_bear.price) and self._should_track_pending_origin('bear', bar_high):
                self.state.pending_origins['bear'] = PendingOrigin(
                    price=bar_high, bar_index=bar.index, direction='bear', source='high'
                )
            # Bull origin: only update if this low is lower (tracking swing lows for bull legs)
            existing_bull = self.state.pending_origins.get('bull')
            if (existing_bull is None or bar_low < existing_bull.price) and self._should_track_pending_origin('bull', bar_low):
                self.state.pending_origins['bull'] = PendingOrigin(
                    price=bar_low, bar_index=bar.index, direction='bull', source='low'
                )

        # Update retracement for bull legs using bar.high (prev.L was before bar.H)
        # Bull: origin=LOW, pivot=HIGH, retracement = (current - origin) / range
        # Only update for legs with live origin (#345)
        for leg in self.state.active_legs:
            if leg.direction == 'bull' and leg.max_origin_breach is None:
                if leg.range > 0:
                    retracement = (bar_high - leg.origin_price) / leg.range
                    leg.retracement_pct = retracement

        # Update retracement for bear legs using bar.low (prev.H was before bar.L)
        # Bear: origin=HIGH, pivot=LOW, retracement = (origin - current) / range
        # Only update for legs with live origin (#345)
        for leg in self.state.active_legs:
            if leg.direction == 'bear' and leg.max_origin_breach is None:
                if leg.range > 0:
                    retracement = (leg.origin_price - bar_low) / leg.range
                    leg.retracement_pct = retracement

        # Check for formations (can use H/L for inside bars)
        events.extend(self._check_leg_formations_with_extremes(bar, timestamp, bar_high, bar_low))

        return events

    def _process_type3(
        self, bar: Bar, timestamp: datetime,
        bar_high: Decimal, bar_low: Decimal, bar_close: Decimal,
        prev_high: Decimal, prev_low: Decimal
    ) -> List[SwingEvent]:
        """
        Process Type 3 bar (outside bar - HH, LL).

        High volatility decision point. Both directions extended.
        Keep both branches until decisive resolution.
        """
        events: List[SwingEvent] = []

        # Update pending origins only if more extreme AND not worse than active leg origins (#200)
        # Bull origin: only update if this low is lower (tracking swing lows for bull legs)
        existing_bull = self.state.pending_origins.get('bull')
        if (existing_bull is None or bar_low < existing_bull.price) and self._should_track_pending_origin('bull', bar_low):
            self.state.pending_origins['bull'] = PendingOrigin(
                price=bar_low, bar_index=bar.index, direction='bull', source='low'
            )
        # Bear origin: only update if this high is higher (tracking swing highs for bear legs)
        existing_bear = self.state.pending_origins.get('bear')
        if (existing_bear is None or bar_high > existing_bear.price) and self._should_track_pending_origin('bear', bar_high):
            self.state.pending_origins['bear'] = PendingOrigin(
                price=bar_high, bar_index=bar.index, direction='bear', source='high'
            )

        # Check for formations using close (conservative - don't know H/L order)
        events.extend(self._check_leg_formations(bar, timestamp, bar_close))

        return events

    def _check_leg_formations(
        self, bar: Bar, timestamp: datetime, check_price: Decimal
    ) -> List[SwingFormedEvent]:
        """
        Check if any legs have reached 38.2% retracement threshold.

        Args:
            bar: Current bar
            timestamp: Event timestamp
            check_price: Price to use for retracement calculation (usually close)

        Returns:
            List of SwingFormedEvent for newly formed swings
        """
        events = []
        formation_threshold = Decimal(str(self.config.bull.formation_fib))

        for leg in self.state.active_legs:
            # Skip legs that are origin-breached (#345) - can't form swings
            if leg.status != 'active' or leg.formed or leg.max_origin_breach is not None:
                continue

            if leg.range == 0:
                continue

            # Calculate retracement (extension from origin toward pivot)
            # Bull: origin=LOW, retracement = (current - origin) / range
            # Bear: origin=HIGH, retracement = (origin - current) / range
            if leg.direction == 'bull':
                retracement = (check_price - leg.origin_price) / leg.range
            else:
                retracement = (leg.origin_price - check_price) / leg.range

            leg.retracement_pct = retracement

            if retracement >= formation_threshold:
                leg.formed = True
                event = self._form_swing_from_leg(leg, bar, timestamp)
                if event:
                    events.append(event)

        return events

    def _check_leg_formations_with_extremes(
        self, bar: Bar, timestamp: datetime, bar_high: Decimal, bar_low: Decimal
    ) -> List[SwingFormedEvent]:
        """
        Check formations using H/L directly (for inside bars where temporal order is known).
        """
        events = []
        formation_threshold = Decimal(str(self.config.bull.formation_fib))

        for leg in self.state.active_legs:
            # Skip legs that are origin-breached (#345) - can't form swings
            if leg.status != 'active' or leg.formed or leg.max_origin_breach is not None:
                continue

            if leg.range == 0:
                continue

            # For bull legs, use bar.high (prev.L was before bar.H for inside bars)
            # For bear legs, use bar.low (prev.H was before bar.L for inside bars)
            # Bull: origin=LOW, retracement = (current - origin) / range
            # Bear: origin=HIGH, retracement = (origin - current) / range
            if leg.direction == 'bull':
                retracement = (bar_high - leg.origin_price) / leg.range
            else:
                retracement = (leg.origin_price - bar_low) / leg.range

            leg.retracement_pct = retracement

            if retracement >= formation_threshold:
                leg.formed = True
                event = self._form_swing_from_leg(leg, bar, timestamp)
                if event:
                    events.append(event)

        return events

    def _form_swing_from_leg(
        self, leg: Leg, bar: Bar, timestamp: datetime
    ) -> Optional[SwingFormedEvent]:
        """
        Create a SwingNode from a formed leg and add to active swings.

        No separation check needed at formation - DAG pruning (10% rule) already
        ensures surviving origins are sufficiently separated (#163).

        Returns:
            SwingFormedEvent or None if swing already exists
        """
        # Create SwingNode
        # Bull leg: origin at LOW -> pivot at HIGH
        # Bear leg: origin at HIGH -> pivot at LOW
        # Use deterministic swing_id derived from leg properties (#299)
        deterministic_swing_id = Leg.make_swing_id(
            leg.direction, leg.origin_price, leg.origin_index
        )
        if leg.direction == 'bull':
            swing = SwingNode(
                swing_id=deterministic_swing_id,
                low_bar_index=leg.origin_index,  # origin is at LOW
                low_price=leg.origin_price,
                high_bar_index=leg.pivot_index,  # pivot is at HIGH
                high_price=leg.pivot_price,
                direction="bull",
                status="active",
                formed_at_bar=bar.index,
            )
        else:
            swing = SwingNode(
                swing_id=deterministic_swing_id,
                high_bar_index=leg.origin_index,  # origin is at HIGH
                high_price=leg.origin_price,
                low_bar_index=leg.pivot_index,  # pivot is at LOW
                low_price=leg.pivot_price,
                direction="bear",
                status="active",
                formed_at_bar=bar.index,
            )

        # Link leg to swing (#174)
        leg.swing_id = swing.swing_id

        # Record impulse in formed population for percentile ranking (#241, #242)
        bisect.insort(self.state.formed_leg_impulses, leg.impulse)

        # Add to active swings
        self.state.active_swings.append(swing)

        # Initialize level tracking
        ratio = float(leg.retracement_pct)
        self.state.fib_levels_crossed[swing.swing_id] = self._find_level_band(ratio)

        return SwingFormedEvent(
            bar_index=bar.index,
            timestamp=timestamp,
            swing_id=swing.swing_id,
            high_bar_index=swing.high_bar_index,
            high_price=swing.high_price,
            low_bar_index=swing.low_bar_index,
            low_price=swing.low_price,
            direction=swing.direction,
            parent_ids=[],  # Swing hierarchy removed (#301)
        )

    def _check_extension_prune(self, bar: Bar, timestamp: datetime) -> List[LegPrunedEvent]:
        """
        Prune origin-breached child legs that have reached 3x extension (#203, #261, #345).

        Origin-breached legs with a parent are pruned when price moves 3x their range
        beyond the origin. Root legs (no parent) are never pruned by this rule,
        preserving the anchor that began the move as historical reference.

        Returns:
            List of LegPrunedEvent for legs pruned due to extension.
        """
        events: List[LegPrunedEvent] = []
        extension_threshold = Decimal(str(self.config.stale_extension_threshold))
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))
        pruned_legs: List[Leg] = []

        for leg in self.state.active_legs:
            # Only check origin-breached legs (#345)
            if leg.max_origin_breach is None:
                continue

            # Only prune child legs; root legs (no parent) are preserved (#261)
            if leg.parent_leg_id is None:
                continue

            if leg.range == 0:
                continue

            # Calculate extension beyond origin
            # Bull leg: origin=LOW, check how far below origin price has gone
            # Bear leg: origin=HIGH, check how far above origin price has gone
            extension_amount = extension_threshold * leg.range

            if leg.direction == 'bull':
                prune_price = leg.origin_price - extension_amount
                if bar_low < prune_price:
                    leg.status = 'stale'
                    pruned_legs.append(leg)
            else:  # bear
                prune_price = leg.origin_price + extension_amount
                if bar_high > prune_price:
                    leg.status = 'stale'
                    pruned_legs.append(leg)

        # Reparent children and emit LegPrunedEvent for each pruned leg (#281)
        for leg in pruned_legs:
            self._pruner.reparent_children(self.state, leg)
            events.append(LegPrunedEvent(
                bar_index=bar.index,
                timestamp=timestamp,
                swing_id=leg.swing_id or "",
                leg_id=leg.leg_id,
                reason="extension_prune",
            ))

        # Remove pruned legs
        self.state.active_legs = [leg for leg in self.state.active_legs if leg.status != 'stale']

        return events

    def _should_track_pending_origin(self, direction: str, price: Decimal) -> bool:
        """
        Check if we should track this as a pending origin (#200).

        Returns False if an active leg already has a better origin:
        - For bull: active bull leg with origin_price <= price (lower origin is better)
        - For bear: active bear leg with origin_price >= price (higher origin is better)

        When an active leg has a better origin, tracking a worse pending origin
        is pointless - if the leg survives, the pending origin won't be used;
        if the leg is invalidated, the orphaned origin is still better.

        IMPORTANT (#202): This check only applies when we're in the SAME direction's
        turn. During an opposite direction's turn (e.g., bear turn for bull pending
        origins), always track the pending origin since the old legs are from a
        previous turn and shouldn't block tracking for the next turn.
        """
        # #202: If we're currently in the opposite direction's turn, always track.
        # This allows pending origins to accumulate during retracements.
        # For example, during a bear turn, always track bull pending origins
        # so they're available when the new bull turn starts.
        opposite = 'bear' if direction == 'bull' else 'bull'
        if self.state.prev_bar_type == opposite:
            # We're in the opposite direction's turn - always track
            return True

        # Get the turn boundary - only legs from current turn matter
        turn_start = self.state.last_turn_bar.get(direction, -1)

        for leg in self.state.active_legs:
            # Only consider legs with live origin (not breached) (#345)
            if leg.direction == direction and leg.max_origin_breach is None:
                # #202: Skip legs from previous turns
                if leg.origin_index < turn_start:
                    continue
                if direction == 'bull' and leg.origin_price <= price:
                    return False  # Active bull leg has lower/equal origin
                elif direction == 'bear' and leg.origin_price >= price:
                    return False  # Active bear leg has higher/equal origin
        return True

    def process_bar(self, bar: Bar) -> List[SwingEvent]:
        """
        Process a single bar. Returns events generated.

        Uses DAG-based streaming algorithm for O(n log k) complexity.
        This replaces the previous O(n x k^3) candidate pairing approach.

        Order of operations:
        1. Check invalidations of formed swings (independent per swing)
        2. Check completions of formed swings
        3. Check level crosses for formed swings
        4. Update DAG state (leg tracking, formation, pruning)

        Args:
            bar: The bar to process (Bar dataclass from types.py)

        Returns:
            List of SwingEvent subclasses generated by this bar.
        """
        events: List[SwingEvent] = []
        self.state.last_bar_index = bar.index

        # Create timestamp from bar
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # 1. Check level crosses (structural tracking) - skip if disabled
        if self.config.emit_level_crosses:
            events.extend(self._check_level_crosses(bar, timestamp))

        # 4. Update DAG state and form new swings (O(1) per bar)
        dag_events = self._update_dag_state(bar, timestamp)
        events.extend(dag_events)

        # 5. Update running moments and spikiness for live legs (#241, #244)
        # Must happen after _update_dag_state where bar_count is incremented
        self._update_leg_moments_and_spikiness(bar)

        # 6. Update impulsiveness for all live legs (#241, #243)
        # Live legs have max_origin_breach=None (origin not yet violated)
        self._update_live_leg_impulsiveness()

        return events

    def _update_live_leg_impulsiveness(self) -> None:
        """
        Update impulsiveness for all live legs (#241, #243).

        A leg is "live" if its origin has never been breached (max_origin_breach is None).
        Once a leg stops being live, its impulsiveness is frozen and not updated.

        Impulsiveness is the percentile rank (0-100) of the leg's raw impulse
        against all formed legs in the population.
        """
        for leg in self.state.active_legs:
            # Only update live legs (origin never breached)
            if leg.max_origin_breach is not None:
                continue

            # Calculate impulsiveness as percentile rank
            leg.impulsiveness = _calculate_impulsiveness(
                leg.impulse,
                self.state.formed_leg_impulses
            )

    def _update_leg_moments_and_spikiness(self, bar: 'Bar') -> None:
        """
        Update running moments and spikiness for all live legs (#241, #244).

        Per-bar contribution:
        - Bull leg: contribution = bar.close - prev_bar.high
        - Bear leg: contribution = prev_bar.low - bar.close

        Skips the first bar after leg creation (no prev_bar baseline).
        Only updates live legs (max_origin_breach is None).

        Args:
            bar: Current bar being processed.
        """
        if self.state.prev_bar is None:
            return

        prev_high = float(self.state.prev_bar.high)
        prev_low = float(self.state.prev_bar.low)
        bar_close = float(bar.close)

        for leg in self.state.active_legs:
            # Only update live legs
            if leg.max_origin_breach is not None:
                continue

            # Skip first bar of leg (no contribution baseline)
            # bar_count is incremented AFTER this runs, so bar_count >= 1 means
            # we have at least one prior bar in this leg
            if leg.bar_count < 1:
                continue

            # Calculate contribution based on direction
            if leg.direction == 'bull':
                # Bull: how much did this bar advance beyond prev high?
                contribution = bar_close - prev_high
            else:
                # Bear: how much did this bar drop below prev low?
                contribution = prev_low - bar_close

            # Update running moments
            leg._moment_n += 1
            leg._moment_sum_x += contribution
            leg._moment_sum_x2 += contribution * contribution
            leg._moment_sum_x3 += contribution * contribution * contribution

            # Recalculate spikiness from updated moments
            leg.spikiness = _calculate_spikiness(
                leg._moment_n,
                leg._moment_sum_x,
                leg._moment_sum_x2,
                leg._moment_sum_x3
            )

    def _check_level_crosses(
        self, bar: Bar, timestamp: datetime
    ) -> List[LevelCrossEvent]:
        """
        Check each active swing for Fib level crosses.

        Tracks the last level for each swing and emits events when
        the current price crosses into a new level band.

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of LevelCrossEvent for any level crosses.
        """
        events = []
        for swing in self.state.active_swings:
            if swing.status != "active":
                continue

            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            # Use close price for level cross tracking
            close_price = Decimal(str(bar.close))
            current_ratio = float(frame.ratio(close_price))

            # Find current level band
            current_level = self._find_level_band(current_ratio)
            previous_level = self.state.fib_levels_crossed.get(
                swing.swing_id, current_level
            )

            if current_level != previous_level:
                events.append(
                    LevelCrossEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        level=current_level,
                        previous_level=previous_level,
                        price=close_price,
                    )
                )
                self.state.fib_levels_crossed[swing.swing_id] = current_level

        return events

    def _find_level_band(self, ratio: float) -> float:
        """
        Find the Fib level band for a given ratio.

        Returns the highest Fib level that is <= the ratio.

        Args:
            ratio: Current ratio in the reference frame.

        Returns:
            The Fib level band (e.g., 0.382, 0.618, etc.)
        """
        level = FIB_LEVELS[0]
        for fib in FIB_LEVELS:
            if ratio >= fib:
                level = fib
            else:
                break
        return level

    def _find_leg_by_id(self, leg_id: str) -> Optional[Leg]:
        """
        Find a leg by its ID in active_legs.

        Args:
            leg_id: The leg ID to find.

        Returns:
            Leg if found, None otherwise.
        """
        for leg in self.state.active_legs:
            if leg.leg_id == leg_id:
                return leg
        return None

    def _find_parent_for_leg(self, direction: str, origin_price: Decimal, origin_index: int) -> Optional[str]:
        """
        Find parent leg_id for a new leg using time-price ordering (#281).

        Parent-child relationships are based on same-direction, time-price ordering:
        - Bull: parent = max(origin_price) among eligible legs with lower origin prices
        - Bear: parent = min(origin_price) among eligible legs with higher origin prices

        Eligibility constraint: Only legs whose origin has not been breached can be parents.

        Args:
            direction: 'bull' or 'bear'
            origin_price: Origin price of the new leg
            origin_index: Origin bar index of the new leg

        Returns:
            leg_id of parent leg, or None if no eligible parent found
        """
        eligible = [
            leg for leg in self.state.active_legs
            if leg.direction == direction
            and leg.max_origin_breach is None  # Rule: non-breached only (#345)
            and leg.origin_index < origin_index  # Earlier in time
        ]

        if not eligible:
            return None

        if direction == 'bull':
            # Bull: parent has lower origin price (lower low is ancestor)
            eligible = [l for l in eligible if l.origin_price < origin_price]
            if not eligible:
                return None
            # Select max origin_price; on tie, latest origin_index
            parent = max(eligible, key=lambda l: (l.origin_price, l.origin_index))
        else:  # bear
            # Bear: parent has higher origin price (higher high is ancestor)
            eligible = [l for l in eligible if l.origin_price > origin_price]
            if not eligible:
                return None
            # Select min origin_price; on tie, latest origin_index (negate for min)
            parent = min(eligible, key=lambda l: (l.origin_price, -l.origin_index))

        return parent.leg_id

    def _is_origin_dominated_by_branch_ratio(
        self,
        direction: str,
        origin_price: Decimal,
        parent_leg_id: Optional[str],
    ) -> bool:
        """
        Check if a new leg's origin is dominated by branch ratio (#337).

        A new leg's counter-trend at its origin must be at least min_branch_ratio
        times the counter-trend at its parent's origin. This prevents insignificant
        child legs from being created within larger structures.

        The check scales naturally through the hierarchy:
        - Root legs (no parent) are always allowed
        - Child legs need counter-trend >= 10% of parent's counter-trend
        - Grandchild legs need counter-trend >= 10% of child's counter-trend
        - And so on...

        Args:
            direction: 'bull' or 'bear'
            origin_price: Origin price of the new leg
            parent_leg_id: ID of the parent leg, or None if root

        Returns:
            True if origin is dominated (should NOT create leg)
            False if origin is valid (should create leg)
        """
        # Root legs are always allowed
        if parent_leg_id is None:
            return False

        # Check if branch ratio domination is enabled
        min_ratio = self.config.min_branch_ratio
        if min_ratio <= 0:
            return False  # Disabled

        # Find the parent leg
        parent = self._find_leg_by_id(parent_leg_id)
        if parent is None:
            return False  # Parent not found, allow

        # Find R0 = counter-trend at new leg's origin
        # (largest opposite-direction leg whose pivot == new origin)
        r0_range = self._find_counter_trend_range_at_price(direction, origin_price)

        # Find R1 = counter-trend at parent's origin
        r1_range = self._find_counter_trend_range_at_price(direction, parent.origin_price)

        # If parent has no counter-trend, allow child (parent is root-like)
        if r1_range is None:
            return False

        # If new origin has no counter-trend, it's dominated
        if r0_range is None:
            return True

        # Check: R0 >= min_ratio * R1
        # If not, origin is dominated
        return r0_range < min_ratio * r1_range

    def _find_counter_trend_range_at_price(
        self,
        direction: str,
        price: Decimal,
    ) -> Optional[float]:
        """
        Find the range of the largest counter-direction leg at a price level.

        For a bull leg at price P, find the largest bear leg whose pivot == P.
        For a bear leg at price P, find the largest bull leg whose pivot == P.

        Args:
            direction: Direction of the leg we're checking ('bull' or 'bear')
            price: Price level to check

        Returns:
            Range of largest counter-direction leg at this price, or None if none
        """
        opposite_direction = 'bear' if direction == 'bull' else 'bull'

        matching_legs = [
            leg for leg in self.state.active_legs
            if leg.direction == opposite_direction
            and leg.pivot_price == price
        ]

        if matching_legs:
            longest = max(matching_legs, key=lambda l: l.range)
            return float(longest.range)
        return None

    def get_active_swings(self) -> List[SwingNode]:
        """
        Get all currently active swings.

        Returns:
            List of SwingNode with status "active".
        """
        return [s for s in self.state.active_swings if s.status == "active"]

    def get_state(self) -> DetectorState:
        """
        Get serializable state for persistence.

        Returns:
            DetectorState that can be serialized to JSON.
        """
        return self.state

    @classmethod
    def from_state(
        cls, state: DetectorState, config: SwingConfig = None
    ) -> "LegDetector":
        """
        Restore from serialized state.

        Args:
            state: DetectorState to restore from.
            config: SwingConfig to use (defaults to default config).

        Returns:
            LegDetector initialized with the given state.
        """
        detector = cls(config)
        detector.state = state
        return detector

    def update_config(self, config: SwingConfig) -> None:
        """
        Update the detector's configuration.

        This replaces the config while preserving existing state (legs, swings).
        The new config applies to future bar processing only.

        Args:
            config: New SwingConfig to use.

        Example:
            >>> detector = LegDetector()
            >>> # Change formation threshold
            >>> new_config = SwingConfig.default().with_bull(formation_fib=0.382)
            >>> detector.update_config(new_config)
            >>> # Future bars use new config, existing legs preserved
        """
        self.config = config
        self._pruner = LegPruner(self.config)


# Backward compatibility alias
HierarchicalDetector = LegDetector
