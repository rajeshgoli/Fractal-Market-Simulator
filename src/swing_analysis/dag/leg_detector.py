"""
DAG-Based Leg Detector (Structural Layer)

The DAG layer is responsible for structural tracking of price extremas. It processes
one bar at a time via process_bar() and emits events for swing formation and Fib
level crosses.

**This layer handles:**
- Leg tracking with 0.382 invalidation threshold
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
    LegInvalidatedEvent,
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

        This fixes the bug where bars with HH+EL (higher high, equal low) or
        EH+LL (equal high, lower low) were classified as Type 1 and didn't
        extend pivots, causing legs to show stale pivot values.

        Args:
            bar: Current bar
            bar_high: Current bar's high as Decimal
            bar_low: Current bar's low as Decimal
        """
        # Extend bull leg pivots on new highs (only if origin not breached #208)
        for leg in self.state.active_legs:
            if leg.direction == 'bull' and leg.status == 'active':
                if bar_high > leg.pivot_price and leg.max_origin_breach is None:
                    leg.pivot_price = bar_high
                    leg.pivot_index = bar.index
                    leg.last_modified_bar = bar.index
                    # Recalculate impulse when pivot extends (#236)
                    leg.impulse = _calculate_impulse(leg.range, leg.origin_index, leg.pivot_index)

        # Extend bear leg pivots on new lows (only if origin not breached #208)
        for leg in self.state.active_legs:
            if leg.direction == 'bear' and leg.status == 'active':
                if bar_low < leg.pivot_price and leg.max_origin_breach is None:
                    leg.pivot_price = bar_low
                    leg.pivot_index = bar.index
                    leg.last_modified_bar = bar.index
                    # Recalculate impulse when pivot extends (#236)
                    leg.impulse = _calculate_impulse(leg.range, leg.origin_index, leg.pivot_index)

    def _update_breach_tracking(
        self,
        bar: Bar,
        bar_high: Decimal,
        bar_low: Decimal,
        timestamp: datetime
    ) -> List[SwingEvent]:
        """
        Update breach tracking for all active legs (#208).

        Tracks maximum breach beyond origin and pivot for each leg.
        - Origin breach: price moved past the origin (invalidating direction)
        - Pivot breach: price moved past the pivot (violating defended level)

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
            List of OriginBreachedEvent and PivotBreachedEvent for first-time breaches.
        """
        events: List[SwingEvent] = []

        for leg in self.state.active_legs:
            # Skip legs that are completely done (stale/pruned)
            # But include 'invalidated' legs - they can still become engulfed
            if leg.status not in ('active', 'invalidated'):
                continue

            # Origin breach tracking (active legs only - invalidated already have origin breach)
            if leg.status == 'active':
                if leg.direction == 'bull':
                    # Bull origin (low) breached when price goes below it
                    if bar_low < leg.origin_price:
                        breach = leg.origin_price - bar_low
                        was_first_breach = leg.max_origin_breach is None
                        if was_first_breach or breach > leg.max_origin_breach:
                            leg.max_origin_breach = breach
                        # Emit event on FIRST breach only
                        if was_first_breach:
                            events.append(OriginBreachedEvent(
                                bar_index=bar.index,
                                timestamp=timestamp,
                                swing_id="",
                                leg_id=leg.leg_id,
                                breach_price=bar_low,
                                breach_amount=breach,
                            ))
                else:  # bear
                    # Bear origin (high) breached when price goes above it
                    if bar_high > leg.origin_price:
                        breach = bar_high - leg.origin_price
                        was_first_breach = leg.max_origin_breach is None
                        if was_first_breach or breach > leg.max_origin_breach:
                            leg.max_origin_breach = breach
                        # Emit event on FIRST breach only
                        if was_first_breach:
                            events.append(OriginBreachedEvent(
                                bar_index=bar.index,
                                timestamp=timestamp,
                                swing_id="",
                                leg_id=leg.leg_id,
                                breach_price=bar_high,
                                breach_amount=breach,
                            ))

            # Pivot breach tracking (formed legs, including invalidated)
            # Once formed, the pivot is frozen as a structural reference
            # Price going past it = breach (for unformed legs, it would just extend)
            # Invalidated legs need pivot breach tracked for engulfed detection
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
                                swing_id="",
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
                                swing_id="",
                                leg_id=leg.leg_id,
                                breach_price=bar_low,
                                breach_amount=breach,
                            ))

        return events

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

        # Prune legs with breached pivots or engulfed legs (#208)
        # This must happen BEFORE pivot extension so we can create replacement
        # legs at the new extreme (bar_high/bar_low) before the original pivot extends
        prune_events, create_events = self._pruner.prune_breach_legs(
            self.state, bar, timestamp
        )
        events.extend(prune_events)
        events.extend(create_events)

        # Extend leg pivots on new extremes (#188, #192, #197)
        # This must happen BEFORE bar type classification because bars with
        # HH+EL or EH+LL fall through to Type 1 which didn't extend pivots.
        # Origins are FIXED (where move started) and do NOT extend.
        # Only pivots (current defended extreme) extend as price moves.
        self._extend_leg_pivots(bar, bar_high, bar_low)

        # Update breach tracking for all legs (#208)
        # Returns breach events for first-time origin/pivot breaches
        breach_events = self._update_breach_tracking(bar, bar_high, bar_low, timestamp)
        events.extend(breach_events)

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

        # Increment bar count for all active legs
        for leg in self.state.active_legs:
            if leg.status == 'active':
                leg.bar_count += 1

        # Check 3x extension pruning for invalidated legs (#203)
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

        # Prune bear legs on turn (#181): Type 2-Bull signals turn, prune redundant bear legs
        turn_prune_events = self._pruner.prune_legs_on_turn(self.state, 'bear', bar, timestamp)
        events.extend(turn_prune_events)

        # Check if we can start a bull leg from the pending bull origin
        # prev_low is the origin (starting point) for a bull swing extending up
        # Only create if there isn't already a bull leg with the same origin
        if self.state.pending_origins.get('bull'):
            pending = self.state.pending_origins['bull']
            # Check if we already have a bull leg from this origin
            existing_bull_leg = any(
                leg.direction == 'bull' and leg.status == 'active'
                and leg.origin_price == pending.price and leg.origin_index == pending.bar_index
                for leg in self.state.active_legs
            )
            # Skip if dominated by existing leg with better origin (#194)
            if self._pruner.would_leg_be_dominated(self.state, 'bull', pending.price):
                existing_bull_leg = True
            # Pivot extension handled by _extend_leg_pivots (#188)
            if not existing_bull_leg:
                # Create new bull leg: origin at LOW -> pivot at HIGH
                leg_range = abs(bar_high - pending.price)
                new_leg = Leg(
                    direction='bull',
                    origin_price=pending.price,  # LOW - where upward move started
                    origin_index=pending.bar_index,
                    pivot_price=bar_high,  # HIGH - current defended extreme
                    pivot_index=bar.index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                    impulse=_calculate_impulse(leg_range, pending.bar_index, bar.index),
                )
                self.state.active_legs.append(new_leg)
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
                # Prune existing legs dominated by this better origin (#204)
                events.extend(self._pruner.prune_dominated_legs_in_turn(self.state, new_leg, bar, timestamp))

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

        # Check for decisive invalidations
        events.extend(self._check_leg_invalidations(bar, timestamp, bar_high, bar_low))

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

        # Prune bull legs on turn (#181): Type 2-Bear signals turn, prune redundant bull legs
        turn_prune_events = self._pruner.prune_legs_on_turn(self.state, 'bull', bar, timestamp)
        events.extend(turn_prune_events)

        # Start new bear leg for potential bear swing
        # (tracking downward movement for possible bear retracement later)
        if self.state.pending_origins.get('bear'):
            pending = self.state.pending_origins['bear']
            # Only create if we don't already have a bear leg with this origin
            existing_bear_leg = any(
                leg.direction == 'bear' and leg.status == 'active'
                and leg.origin_price == pending.price and leg.origin_index == pending.bar_index
                for leg in self.state.active_legs
            )
            # Skip if dominated by existing leg with better origin (#194)
            if self._pruner.would_leg_be_dominated(self.state, 'bear', pending.price):
                existing_bear_leg = True
            # Pivot extension handled by _extend_leg_pivots (#188)
            if not existing_bear_leg:
                leg_range = abs(pending.price - bar_low)
                new_bear_leg = Leg(
                    direction='bear',
                    origin_price=pending.price,  # HIGH - where downward move started
                    origin_index=pending.bar_index,
                    pivot_price=bar_low,  # LOW - current defended extreme
                    pivot_index=bar.index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                    impulse=_calculate_impulse(leg_range, pending.bar_index, bar.index),
                )
                self.state.active_legs.append(new_bear_leg)
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
                # Prune existing legs dominated by this better origin (#204)
                events.extend(self._pruner.prune_dominated_legs_in_turn(self.state, new_bear_leg, bar, timestamp))

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

        # Check for decisive invalidations
        events.extend(self._check_leg_invalidations(bar, timestamp, bar_high, bar_low))

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
                if (pending_bear.bar_index < pending_bull.bar_index
                    and not self._pruner.would_leg_be_dominated(self.state, 'bear', pending_bear.price)):
                    leg_range = abs(pending_bear.price - pending_bull.price)
                    new_bear_leg = Leg(
                        direction='bear',
                        origin_price=pending_bear.price,  # HIGH - where downward move started
                        origin_index=pending_bear.bar_index,
                        pivot_price=pending_bull.price,  # LOW - current defended extreme
                        pivot_index=pending_bull.bar_index,
                        price_at_creation=bar_close,
                        last_modified_bar=bar.index,
                        impulse=_calculate_impulse(leg_range, pending_bear.bar_index, pending_bull.bar_index),
                    )
                    self.state.active_legs.append(new_bear_leg)
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
                    # Prune existing legs dominated by this better origin (#204)
                    events.extend(self._pruner.prune_dominated_legs_in_turn(self.state, new_bear_leg, bar, timestamp))

            # Create bull leg if LOW came before HIGH (price moved up)
            # Bull swing: origin=LOW (starting point), pivot=HIGH (defended extreme)
            # Temporal order: origin_index < pivot_index (#195)
            if pending_bear and pending_bull:
                # pending_bull = LOW, pending_bear = HIGH
                # If LOW came before HIGH, this is a BULL structure
                # Skip if dominated by existing leg with better origin (#194)
                if (pending_bull.bar_index < pending_bear.bar_index
                    and not self._pruner.would_leg_be_dominated(self.state, 'bull', pending_bull.price)):
                    leg_range = abs(pending_bear.price - pending_bull.price)
                    new_bull_leg = Leg(
                        direction='bull',
                        origin_price=pending_bull.price,  # LOW - where upward move started
                        origin_index=pending_bull.bar_index,
                        pivot_price=pending_bear.price,  # HIGH - current defended extreme
                        pivot_index=pending_bear.bar_index,
                        price_at_creation=bar_close,
                        last_modified_bar=bar.index,
                        impulse=_calculate_impulse(leg_range, pending_bull.bar_index, pending_bear.bar_index),
                    )
                    self.state.active_legs.append(new_bull_leg)
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
                    # Prune existing legs dominated by this better origin (#204)
                    events.extend(self._pruner.prune_dominated_legs_in_turn(self.state, new_bull_leg, bar, timestamp))

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
        for leg in self.state.active_legs:
            if leg.direction == 'bull' and leg.status == 'active':
                if leg.range > 0:
                    retracement = (bar_high - leg.origin_price) / leg.range
                    leg.retracement_pct = retracement

        # Update retracement for bear legs using bar.low (prev.H was before bar.L)
        # Bear: origin=HIGH, pivot=LOW, retracement = (origin - current) / range
        for leg in self.state.active_legs:
            if leg.direction == 'bear' and leg.status == 'active':
                if leg.range > 0:
                    retracement = (leg.origin_price - bar_low) / leg.range
                    leg.retracement_pct = retracement

        # Check for formations (can use H/L for inside bars)
        events.extend(self._check_leg_formations_with_extremes(bar, timestamp, bar_high, bar_low))

        # Check for decisive invalidations
        events.extend(self._check_leg_invalidations(bar, timestamp, bar_high, bar_low))

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

        # Check invalidations
        events.extend(self._check_leg_invalidations(bar, timestamp, bar_high, bar_low))

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
            if leg.status != 'active' or leg.formed:
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
            if leg.status != 'active' or leg.formed:
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
        if leg.direction == 'bull':
            swing = SwingNode(
                swing_id=SwingNode.generate_id(),
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
                swing_id=SwingNode.generate_id(),
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

        # Find parents
        parents = self._find_parents(swing)
        for parent in parents:
            swing.add_parent(parent)

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
            parent_ids=[p.swing_id for p in parents],
        )

    def _check_leg_invalidations(
        self, bar: Bar, timestamp: datetime, bar_high: Decimal, bar_low: Decimal
    ) -> List[SwingEvent]:
        """
        Check for decisive invalidation of legs (#203).

        A leg is decisively invalidated when price moves beyond the
        configured invalidation threshold (default 0.382) of the leg's range
        beyond the defended pivot.

        When a leg is invalidated:
        - Its status is set to 'invalidated' but it remains in active_legs (#203)
        - If the leg formed into a swing, that swing is also invalidated (#174)

        Invalidated legs remain visible until 3x extension prune (#203).

        Returns:
            List of LegInvalidatedEvent and SwingInvalidatedEvent for any
            legs/swings invalidated.
        """
        events: List[SwingEvent] = []
        invalidated_legs: List[Leg] = []
        invalidation_prices: Dict[str, Decimal] = {}  # leg_id -> price at invalidation

        for leg in self.state.active_legs:
            if leg.status != 'active':
                continue

            if leg.range == 0:
                continue

            # Get per-direction invalidation threshold (#203)
            if leg.direction == 'bull':
                invalidation_threshold = Decimal(str(self.config.bull.invalidation_threshold))
            else:
                invalidation_threshold = Decimal(str(self.config.bear.invalidation_threshold))

            threshold_amount = invalidation_threshold * leg.range

            # Invalidation happens when price breaches threshold beyond the origin
            # (the origin is the defended level that must hold)
            # Bull: origin=LOW, invalidation if price drops below origin - threshold
            # Bear: origin=HIGH, invalidation if price rises above origin + threshold
            if leg.direction == 'bull':
                invalidation_price = leg.origin_price - threshold_amount
                if bar_low < invalidation_price:
                    leg.status = 'invalidated'
                    invalidated_legs.append(leg)
                    invalidation_prices[leg.leg_id] = bar_low
            else:  # bear
                invalidation_price = leg.origin_price + threshold_amount
                if bar_high > invalidation_price:
                    leg.status = 'invalidated'
                    invalidated_legs.append(leg)
                    invalidation_prices[leg.leg_id] = bar_high

        # Emit events for invalidated legs
        for leg in invalidated_legs:
            # Emit LegInvalidatedEvent (#168)
            events.append(LegInvalidatedEvent(
                bar_index=bar.index,
                timestamp=timestamp,
                swing_id=leg.swing_id or "",
                leg_id=leg.leg_id,
                invalidation_price=invalidation_prices.get(leg.leg_id, Decimal("0")),
            ))

            # Propagate invalidation to swing if leg formed into one (#174)
            if leg.swing_id:
                for swing in self.state.active_swings:
                    if swing.swing_id == leg.swing_id and swing.status == 'active':
                        swing.invalidate()
                        events.append(SwingInvalidatedEvent(
                            bar_index=bar.index,
                            timestamp=timestamp,
                            swing_id=swing.swing_id,
                            reason="leg_invalidated",
                        ))
                        break

        # Prune inner structure legs when bear legs are invalidated (#264, #279)
        # When contained legs are invalidated, prune the counter-direction
        # legs from inner pivots (they're redundant to outer-origin legs)
        #
        # #279 fix: Containment pairs are invalidated SEQUENTIALLY (inner first,
        # then outer) because inner.origin < outer.origin. We must check newly
        # invalidated legs against ALREADY invalidated legs, not just same-bar.
        if invalidated_legs:
            # Gather ALL invalidated legs (current bar + previously invalidated)
            all_invalidated = [
                leg for leg in self.state.active_legs
                if leg.status == 'invalidated'
            ]
            if len(all_invalidated) >= 2:
                inner_prune_events = self._pruner.prune_inner_structure_legs(
                    self.state, all_invalidated, bar, timestamp
                )
                events.extend(inner_prune_events)

        # NOTE: Invalidated legs are NOT removed here (#203)
        # They remain visible until 3x extension prune in _check_extension_prune()

        return events

    def _check_extension_prune(self, bar: Bar, timestamp: datetime) -> List[LegPrunedEvent]:
        """
        Prune invalidated legs that have reached 3x extension (#203).

        Invalidated legs remain visible until price moves 3x their range
        beyond the origin. This allows them to serve as counter-trend references.

        Returns:
            List of LegPrunedEvent for legs pruned due to extension.
        """
        events: List[LegPrunedEvent] = []
        extension_threshold = Decimal(str(self.config.stale_extension_threshold))
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))
        pruned_legs: List[Leg] = []

        for leg in self.state.active_legs:
            if leg.status != 'invalidated':
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

        # Emit LegPrunedEvent for each pruned leg
        for leg in pruned_legs:
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
            if leg.direction == direction and leg.status == 'active':
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

        # 1. Check level crosses (structural tracking)
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

    def _find_parents(self, new_swing: SwingNode) -> List[SwingNode]:
        """
        Find parent swings for a new swing.

        A swing is a parent if the new swing's defended pivot is within
        the parent's 0-2 range.

        Args:
            new_swing: The newly formed swing.

        Returns:
            List of parent SwingNode objects.
        """
        parents = []
        new_pivot = new_swing.defended_pivot

        for swing in self.state.active_swings:
            if swing.status != "active":
                continue
            if swing.swing_id == new_swing.swing_id:
                continue

            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            ratio = frame.ratio(new_pivot)
            # Parent if new swing's pivot is in 0-2 range
            if Decimal("0") <= ratio <= Decimal("2"):
                parents.append(swing)

        return parents

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


# Backward compatibility alias
HierarchicalDetector = LegDetector
