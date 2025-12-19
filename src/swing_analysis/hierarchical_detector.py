"""
Hierarchical Swing Detector (DAG-Based Algorithm)

Incremental swing detector with hierarchical model. Processes one bar at a time
via process_bar(). Uses a DAG-based streaming approach that achieves O(n log k)
complexity instead of O(n × k³).

Core insight: Instead of generating O(k²) candidate pairs and filtering by rules,
build a structure where rules are enforced by construction. Temporal ordering is
established through bar relationships, not post-hoc filtering.

See Docs/Working/DAG_spec.md for full specification.
See Docs/Working/Performance_question.md for design rationale.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Tuple, Optional, Callable, Set, Literal

import pandas as pd

from .swing_config import SwingConfig, DirectionConfig
from .swing_node import SwingNode
from .events import (
    SwingEvent,
    SwingFormedEvent,
    SwingInvalidatedEvent,
    SwingCompletedEvent,
    LevelCrossEvent,
)
from .reference_frame import ReferenceFrame
from .types import Bar


# Fibonacci levels to track for level cross events
FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 2.0]


class BarType(Enum):
    """
    Classification of bar relationships for temporal ordering.

    Type 1: Inside bar (LH, HL) - bar contained within previous
    Type 2-Bull: Trending up (HH, HL) - higher high and higher low
    Type 2-Bear: Trending down (LH, LL) - lower high and lower low
    Type 3: Outside bar (HH, LL) - engulfing, high volatility
    """
    TYPE_1 = "inside"
    TYPE_2_BULL = "bull"
    TYPE_2_BEAR = "bear"
    TYPE_3 = "outside"


@dataclass
class Leg:
    """
    A directional price movement with known temporal ordering.

    Bull leg: Low (defended pivot) → High (origin)
    Bear leg: High (defended pivot) → Low (origin)

    Attributes:
        direction: 'bull' or 'bear'
        pivot_price: The defended pivot price (must hold)
        pivot_index: Bar index where pivot was established
        origin_price: Current origin price (extends as leg grows)
        origin_index: Bar index of origin
        retracement_pct: Current retracement percentage toward pivot
        formed: Whether 38.2% threshold has been reached
        parent_leg_id: ID of parent leg if this is a child
        status: 'active', 'stale', or 'invalidated'
        bar_count: Number of bars since leg started
        gap_count: Number of gap bars in this leg
        last_modified_bar: Bar index when leg was last modified
        price_at_creation: Price when leg was created (for staleness)
    """
    direction: Literal['bull', 'bear']
    pivot_price: Decimal
    pivot_index: int
    origin_price: Decimal
    origin_index: int
    retracement_pct: Decimal = Decimal("0")
    formed: bool = False
    parent_leg_id: Optional[str] = None
    status: Literal['active', 'stale', 'invalidated'] = 'active'
    bar_count: int = 0
    gap_count: int = 0
    last_modified_bar: int = 0
    price_at_creation: Decimal = Decimal("0")
    leg_id: str = field(default_factory=lambda: SwingNode.generate_id())

    @property
    def range(self) -> Decimal:
        """Absolute range of the leg."""
        return abs(self.origin_price - self.pivot_price)


@dataclass
class PendingPivot:
    """
    A potential defended pivot awaiting temporal confirmation.

    Created when a bar establishes a new extreme. Confirmed when
    subsequent bar establishes temporal ordering.

    Attributes:
        price: The pivot price
        bar_index: Bar index where this was established
        direction: What leg type this could start ('bull' or 'bear')
        source: Which price component ('high', 'low', 'open', 'close')
    """
    price: Decimal
    bar_index: int
    direction: Literal['bull', 'bear']
    source: Literal['high', 'low', 'open', 'close']


@dataclass
class DetectorState:
    """
    Serializable state for pause/resume.

    Contains all information needed to resume detection from a saved point.
    Can be serialized to JSON for persistence.

    Attributes:
        active_swings: List of currently active swing nodes.
        last_bar_index: Most recent bar index processed.
        fib_levels_crossed: Map of swing_id -> last Fib level for cross tracking.
        all_swing_ranges: List of all swing ranges seen, for big swing calculation.
        _cached_big_threshold_bull: Cached big swing threshold for bull swings.
        _cached_big_threshold_bear: Cached big swing threshold for bear swings.
        _threshold_valid: Whether the cached thresholds are valid.

        # DAG-based algorithm state:
        prev_bar: Previous bar for type classification.
        active_legs: Currently tracked legs (bull and bear can coexist).
        pending_pivots: Potential pivots awaiting temporal confirmation.
        price_high_water: Highest price seen since last leg modification.
        price_low_water: Lowest price seen since last leg modification.
    """

    active_swings: List[SwingNode] = field(default_factory=list)
    last_bar_index: int = -1
    fib_levels_crossed: Dict[str, float] = field(default_factory=dict)
    all_swing_ranges: List[Decimal] = field(default_factory=list)
    # Cached big swing thresholds (performance optimization #155)
    _cached_big_threshold_bull: Optional[Decimal] = None
    _cached_big_threshold_bear: Optional[Decimal] = None
    _threshold_valid: bool = False

    # DAG-based algorithm state
    prev_bar: Optional[Bar] = None
    active_legs: List[Leg] = field(default_factory=list)
    pending_pivots: Dict[str, Optional[PendingPivot]] = field(
        default_factory=lambda: {'bull': None, 'bear': None}
    )
    price_high_water: Optional[Decimal] = None
    price_low_water: Optional[Decimal] = None

    # Orphaned origins (#163): preserved origins from invalidated legs
    # Format: direction -> List[(origin_price, origin_bar_index)]
    # When a leg is invalidated, its origin is preserved here for potential
    # sibling swing formation with the same defended pivot.
    orphaned_origins: Dict[str, List[Tuple[Decimal, int]]] = field(
        default_factory=lambda: {'bull': [], 'bear': []}
    )

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        # Serialize active legs
        legs_data = []
        for leg in self.active_legs:
            legs_data.append({
                "direction": leg.direction,
                "pivot_price": str(leg.pivot_price),
                "pivot_index": leg.pivot_index,
                "origin_price": str(leg.origin_price),
                "origin_index": leg.origin_index,
                "retracement_pct": str(leg.retracement_pct),
                "formed": leg.formed,
                "parent_leg_id": leg.parent_leg_id,
                "status": leg.status,
                "bar_count": leg.bar_count,
                "gap_count": leg.gap_count,
                "last_modified_bar": leg.last_modified_bar,
                "price_at_creation": str(leg.price_at_creation),
                "leg_id": leg.leg_id,
            })

        # Serialize pending pivots
        pending_pivots_data = {}
        for direction, pivot in self.pending_pivots.items():
            if pivot:
                pending_pivots_data[direction] = {
                    "price": str(pivot.price),
                    "bar_index": pivot.bar_index,
                    "direction": pivot.direction,
                    "source": pivot.source,
                }
            else:
                pending_pivots_data[direction] = None

        # Serialize prev_bar
        prev_bar_data = None
        if self.prev_bar:
            prev_bar_data = {
                "index": self.prev_bar.index,
                "timestamp": self.prev_bar.timestamp,
                "open": self.prev_bar.open,
                "high": self.prev_bar.high,
                "low": self.prev_bar.low,
                "close": self.prev_bar.close,
            }

        return {
            "active_swings": [
                {
                    "swing_id": s.swing_id,
                    "high_bar_index": s.high_bar_index,
                    "high_price": str(s.high_price),
                    "low_bar_index": s.low_bar_index,
                    "low_price": str(s.low_price),
                    "direction": s.direction,
                    "status": s.status,
                    "formed_at_bar": s.formed_at_bar,
                    "parent_ids": [p.swing_id for p in s.parents],
                }
                for s in self.active_swings
            ],
            "last_bar_index": self.last_bar_index,
            "fib_levels_crossed": self.fib_levels_crossed,
            "all_swing_ranges": [str(r) for r in self.all_swing_ranges],
            # Cache fields (will be recomputed on restore, but included for completeness)
            "_cached_big_threshold_bull": str(self._cached_big_threshold_bull) if self._cached_big_threshold_bull is not None else None,
            "_cached_big_threshold_bear": str(self._cached_big_threshold_bear) if self._cached_big_threshold_bear is not None else None,
            "_threshold_valid": self._threshold_valid,
            # DAG state
            "prev_bar": prev_bar_data,
            "active_legs": legs_data,
            "pending_pivots": pending_pivots_data,
            "price_high_water": str(self.price_high_water) if self.price_high_water is not None else None,
            "price_low_water": str(self.price_low_water) if self.price_low_water is not None else None,
            # Orphaned origins (#163)
            "orphaned_origins": {
                direction: [(str(price), idx) for price, idx in origins]
                for direction, origins in self.orphaned_origins.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DetectorState":
        """Create from dictionary."""
        # First pass: create all swing nodes without parent links
        swing_map: Dict[str, SwingNode] = {}
        parent_map: Dict[str, List[str]] = {}

        for swing_data in data.get("active_swings", []):
            swing = SwingNode(
                swing_id=swing_data["swing_id"],
                high_bar_index=swing_data["high_bar_index"],
                high_price=Decimal(swing_data["high_price"]),
                low_bar_index=swing_data["low_bar_index"],
                low_price=Decimal(swing_data["low_price"]),
                direction=swing_data["direction"],
                status=swing_data["status"],
                formed_at_bar=swing_data["formed_at_bar"],
            )
            swing_map[swing.swing_id] = swing
            parent_map[swing.swing_id] = swing_data.get("parent_ids", [])

        # Second pass: link parents
        for swing_id, parent_ids in parent_map.items():
            swing = swing_map[swing_id]
            for parent_id in parent_ids:
                if parent_id in swing_map:
                    swing.add_parent(swing_map[parent_id])

        # Restore cache fields if present (they'll be recomputed on first use anyway)
        cached_bull = data.get("_cached_big_threshold_bull")
        cached_bear = data.get("_cached_big_threshold_bear")

        # Deserialize active legs
        active_legs = []
        for leg_data in data.get("active_legs", []):
            leg = Leg(
                direction=leg_data["direction"],
                pivot_price=Decimal(leg_data["pivot_price"]),
                pivot_index=leg_data["pivot_index"],
                origin_price=Decimal(leg_data["origin_price"]),
                origin_index=leg_data["origin_index"],
                retracement_pct=Decimal(leg_data.get("retracement_pct", "0")),
                formed=leg_data.get("formed", False),
                parent_leg_id=leg_data.get("parent_leg_id"),
                status=leg_data.get("status", "active"),
                bar_count=leg_data.get("bar_count", 0),
                gap_count=leg_data.get("gap_count", 0),
                last_modified_bar=leg_data.get("last_modified_bar", 0),
                price_at_creation=Decimal(leg_data.get("price_at_creation", "0")),
                leg_id=leg_data.get("leg_id", SwingNode.generate_id()),
            )
            active_legs.append(leg)

        # Deserialize pending pivots
        pending_pivots: Dict[str, Optional[PendingPivot]] = {'bull': None, 'bear': None}
        pending_pivots_data = data.get("pending_pivots", {})
        for direction in ['bull', 'bear']:
            pivot_data = pending_pivots_data.get(direction)
            if pivot_data:
                pending_pivots[direction] = PendingPivot(
                    price=Decimal(pivot_data["price"]),
                    bar_index=pivot_data["bar_index"],
                    direction=pivot_data["direction"],
                    source=pivot_data["source"],
                )

        # Deserialize prev_bar
        prev_bar = None
        prev_bar_data = data.get("prev_bar")
        if prev_bar_data:
            prev_bar = Bar(
                index=prev_bar_data["index"],
                timestamp=prev_bar_data["timestamp"],
                open=prev_bar_data["open"],
                high=prev_bar_data["high"],
                low=prev_bar_data["low"],
                close=prev_bar_data["close"],
            )

        # Deserialize price water marks
        price_high_water = data.get("price_high_water")
        price_low_water = data.get("price_low_water")

        # Deserialize orphaned origins (#163)
        orphaned_origins_raw = data.get("orphaned_origins", {'bull': [], 'bear': []})
        orphaned_origins: Dict[str, List[Tuple[Decimal, int]]] = {'bull': [], 'bear': []}
        for direction in ['bull', 'bear']:
            origins_list = orphaned_origins_raw.get(direction, [])
            orphaned_origins[direction] = [
                (Decimal(price), idx) for price, idx in origins_list
            ]

        return cls(
            active_swings=list(swing_map.values()),
            last_bar_index=data.get("last_bar_index", -1),
            fib_levels_crossed=data.get("fib_levels_crossed", {}),
            all_swing_ranges=[
                Decimal(r) for r in data.get("all_swing_ranges", [])
            ],
            _cached_big_threshold_bull=Decimal(cached_bull) if cached_bull is not None else None,
            _cached_big_threshold_bear=Decimal(cached_bear) if cached_bear is not None else None,
            _threshold_valid=data.get("_threshold_valid", False),
            # DAG state
            prev_bar=prev_bar,
            active_legs=active_legs,
            pending_pivots=pending_pivots,
            price_high_water=Decimal(price_high_water) if price_high_water is not None else None,
            price_low_water=Decimal(price_low_water) if price_low_water is not None else None,
            orphaned_origins=orphaned_origins,
        )


class HierarchicalDetector:
    """
    Incremental swing detector with hierarchical model.

    Processes one bar at a time via process_bar(). Calibration is just
    a loop calling process_bar() — no special batch logic.

    Key design principles:
    1. No lookahead — Algorithm only sees current and past bars
    2. Single code path — Calibration will just call this in a loop
    3. Independent invalidation — Each swing checks its own defended pivot
    4. DAG hierarchy — Swings can have multiple parents for structural context

    Example:
        >>> config = SwingConfig.default()
        >>> detector = HierarchicalDetector(config)
        >>> for bar in bars:
        ...     events = detector.process_bar(bar)
        ...     for event in events:
        ...         print(event.event_type, event.swing_id)
        >>> state = detector.get_state()
        >>> # Resume later
        >>> detector2 = HierarchicalDetector.from_state(state, config)
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

    def _update_dag_state(self, bar: Bar, timestamp: datetime) -> List[SwingFormedEvent]:
        """
        Update DAG state with new bar using streaming leg tracking.

        This is the core of the O(n log k) algorithm. Instead of generating
        O(k²) candidate pairs, we track active legs and update them as bars
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

        # Initialize water marks if needed
        if self.state.price_high_water is None:
            self.state.price_high_water = bar_high
        if self.state.price_low_water is None:
            self.state.price_low_water = bar_low

        # Update water marks
        self.state.price_high_water = max(self.state.price_high_water, bar_high)
        self.state.price_low_water = min(self.state.price_low_water, bar_low)

        # First bar initialization
        if self.state.prev_bar is None:
            self._initialize_first_bar(bar, bar_open, bar_close)
            self.state.prev_bar = bar
            return events

        # Classify bar type
        bar_type = self._classify_bar_type(bar, self.state.prev_bar)
        prev_high = Decimal(str(self.state.prev_bar.high))
        prev_low = Decimal(str(self.state.prev_bar.low))

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

        # Check staleness and prune
        self._check_staleness(bar)

        # Prune orphaned origins (#163)
        self._prune_orphaned_origins(bar)

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

        # Set pending pivots at bar extremes
        # High could be a defended pivot for future bear swings
        self.state.pending_pivots['bear'] = PendingPivot(
            price=bar_high, bar_index=bar.index, direction='bear', source='high'
        )
        # Low could be a defended pivot for future bull swings
        self.state.pending_pivots['bull'] = PendingPivot(
            price=bar_low, bar_index=bar.index, direction='bull', source='low'
        )

    def _process_type2_bull(
        self, bar: Bar, timestamp: datetime,
        bar_high: Decimal, bar_low: Decimal, bar_close: Decimal,
        prev_high: Decimal, prev_low: Decimal
    ) -> List[SwingFormedEvent]:
        """
        Process Type 2-Bull bar (HH, HL - trending up).

        Establishes temporal order: prev_bar.L occurred before bar.H.
        This confirms a BEAR swing structure: prev_bar.L → bar.H (low origin → high pivot).

        Also extends any existing bull legs (tracking upward movement).
        """
        events = []

        # Extend existing bull legs (tracking upward movement from defended lows)
        for leg in self.state.active_legs:
            if leg.direction == 'bull' and leg.status == 'active':
                if bar_high > leg.origin_price:
                    leg.origin_price = bar_high
                    leg.origin_index = bar.index
                    leg.last_modified_bar = bar.index

        # Type 2-Bull confirms temporal order: prev_low → bar_high
        # This creates a BEAR swing structure (low origin → high pivot)
        # Start new bear leg from prev_low if we have a pending pivot
        if self.state.pending_pivots.get('bear'):
            pending = self.state.pending_pivots['bear']
            # Create new bear leg: prev_high (defended) → prev_low (origin) extended by bar
            # Actually, for bear swing: high is defended pivot, low is origin
            # Type 2-Bull tells us prev_low came before bar_high
            # So we now have potential bear structure: new bar_high (pivot) ← prev_low (origin)
            # But we need price to retrace DOWN to form a bear swing
            pass  # Bear swings form differently

        # Check if we can start a bull leg from the pending bull pivot
        # prev_low could be the defended pivot for a bull swing extending up
        # Only create if there isn't already a bull leg with the same pivot
        if self.state.pending_pivots.get('bull'):
            pending = self.state.pending_pivots['bull']
            # Check if we already have a bull leg from this pivot
            existing_bull_leg = None
            for leg in self.state.active_legs:
                if (leg.direction == 'bull' and leg.status == 'active'
                    and leg.pivot_price == pending.price and leg.pivot_index == pending.bar_index):
                    existing_bull_leg = leg
                    break

            if existing_bull_leg:
                # Extend the existing leg if new origin is better
                if bar_high > existing_bull_leg.origin_price:
                    existing_bull_leg.origin_price = bar_high
                    existing_bull_leg.origin_index = bar.index
                    existing_bull_leg.last_modified_bar = bar.index
            else:
                # Create new bull leg: prev_low (defended pivot) → bar_high (origin)
                new_leg = Leg(
                    direction='bull',
                    pivot_price=pending.price,
                    pivot_index=pending.bar_index,
                    origin_price=bar_high,
                    origin_index=bar.index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                )
                self.state.active_legs.append(new_leg)

        # Update pending pivots
        # New high could be a defended pivot for future bear swings
        self.state.pending_pivots['bear'] = PendingPivot(
            price=bar_high, bar_index=bar.index, direction='bear', source='high'
        )
        # New higher low could be a defended pivot for future bull swings
        self.state.pending_pivots['bull'] = PendingPivot(
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
    ) -> List[SwingFormedEvent]:
        """
        Process Type 2-Bear bar (LH, LL - trending down).

        Establishes temporal order: prev_bar.H occurred before bar.L.
        This confirms a BULL swing structure: prev_bar.H → bar.L (high origin → low pivot).
        A bull swing has: origin at high, defended pivot at low.

        Also extends any existing bear legs (tracking downward movement).
        """
        events = []

        # Extend existing bear legs (tracking downward movement from defended highs)
        for leg in self.state.active_legs:
            if leg.direction == 'bear' and leg.status == 'active':
                if bar_low < leg.origin_price:
                    leg.origin_price = bar_low
                    leg.origin_index = bar.index
                    leg.last_modified_bar = bar.index

        # Type 2-Bear confirms temporal order: prev_high → bar_low
        # This creates a BULL swing structure: origin=prev_high, pivot=bar_low
        # Create a bull leg with the pending high as origin and current low as pivot
        if self.state.pending_pivots.get('bear'):
            pending = self.state.pending_pivots['bear']
            # For bull swing: pivot (defended) is at LOW, origin is at HIGH
            # Only create if we don't already have a bull leg with this origin
            existing_bull_leg = None
            for leg in self.state.active_legs:
                if (leg.direction == 'bull' and leg.status == 'active'
                    and leg.origin_price == pending.price and leg.origin_index == pending.bar_index):
                    existing_bull_leg = leg
                    break

            if existing_bull_leg:
                # Update pivot if this is a lower low
                if bar_low < existing_bull_leg.pivot_price:
                    existing_bull_leg.pivot_price = bar_low
                    existing_bull_leg.pivot_index = bar.index
                    existing_bull_leg.last_modified_bar = bar.index
            else:
                new_leg = Leg(
                    direction='bull',
                    pivot_price=bar_low,
                    pivot_index=bar.index,
                    origin_price=pending.price,  # prev_high
                    origin_index=pending.bar_index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                )
                self.state.active_legs.append(new_leg)

        # Also start new bear leg for potential bear swing
        # (tracking downward movement for possible bear retracement later)
        if self.state.pending_pivots.get('bear'):
            pending = self.state.pending_pivots['bear']
            # Only create if we don't already have a bear leg with this pivot
            existing_bear_leg = None
            for leg in self.state.active_legs:
                if (leg.direction == 'bear' and leg.status == 'active'
                    and leg.pivot_price == pending.price and leg.pivot_index == pending.bar_index):
                    existing_bear_leg = leg
                    break

            if existing_bear_leg:
                # Extend to lower origin if applicable
                if bar_low < existing_bear_leg.origin_price:
                    existing_bear_leg.origin_price = bar_low
                    existing_bear_leg.origin_index = bar.index
                    existing_bear_leg.last_modified_bar = bar.index
            else:
                new_bear_leg = Leg(
                    direction='bear',
                    pivot_price=pending.price,  # prev_high is defended
                    pivot_index=pending.bar_index,
                    origin_price=bar_low,  # current low is origin
                    origin_index=bar.index,
                    price_at_creation=bar_close,
                    last_modified_bar=bar.index,
                )
                self.state.active_legs.append(new_bear_leg)

        # Update pending pivots
        # New low could be a defended pivot for future bull swings
        self.state.pending_pivots['bull'] = PendingPivot(
            price=bar_low, bar_index=bar.index, direction='bull', source='low'
        )
        # New lower high could be a defended pivot for future bear swings
        self.state.pending_pivots['bear'] = PendingPivot(
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
    ) -> List[SwingFormedEvent]:
        """
        Process Type 1 bar (inside bar - LH, HL) or bars with equal H/L.

        Inside bars still have valid temporal ordering between bars:
        - prev_bar.H came before bar.L (can establish bear swing structure)
        - prev_bar.L came before bar.H (can establish bull swing structure)

        We should create legs from pending pivots if they haven't been consumed yet.
        """
        events = []
        prev_bar = self.state.prev_bar
        if prev_bar:
            pending_bear = self.state.pending_pivots.get('bear')  # High pivot
            pending_bull = self.state.pending_pivots.get('bull')  # Low pivot

            # Create bull leg if we have both high origin and low pivot
            # Bull swing: origin=HIGH, pivot=LOW (defended)
            if pending_bear and pending_bull:
                # We have pending high (origin) and pending low (pivot)
                # Check if origin came before pivot temporally
                if pending_bear.bar_index <= pending_bull.bar_index:
                    new_bull_leg = Leg(
                        direction='bull',
                        pivot_price=pending_bull.price,  # low as defended pivot
                        pivot_index=pending_bull.bar_index,
                        origin_price=pending_bear.price,  # high as origin
                        origin_index=pending_bear.bar_index,
                        price_at_creation=bar_close,
                        last_modified_bar=bar.index,
                    )
                    self.state.active_legs.append(new_bull_leg)

            # Create bear leg if we have both low origin and high pivot
            # Bear swing: origin=LOW, pivot=HIGH (defended)
            if pending_bear and pending_bull:
                # We have pending low (origin) and pending high (pivot)
                if pending_bull.bar_index <= pending_bear.bar_index:
                    new_bear_leg = Leg(
                        direction='bear',
                        pivot_price=pending_bear.price,  # high as defended pivot
                        pivot_index=pending_bear.bar_index,
                        origin_price=pending_bull.price,  # low as origin
                        origin_index=pending_bull.bar_index,
                        price_at_creation=bar_close,
                        last_modified_bar=bar.index,
                    )
                    self.state.active_legs.append(new_bear_leg)

            # Update pending pivots to current bar's extremes (for next iteration)
            self.state.pending_pivots['bear'] = PendingPivot(
                price=bar_high, bar_index=bar.index, direction='bear', source='high'
            )
            self.state.pending_pivots['bull'] = PendingPivot(
                price=bar_low, bar_index=bar.index, direction='bull', source='low'
            )

        # Update retracement for bull legs using bar.high (prev.L was before bar.H)
        for leg in self.state.active_legs:
            if leg.direction == 'bull' and leg.status == 'active':
                if leg.range > 0:
                    retracement = (bar_high - leg.pivot_price) / leg.range
                    leg.retracement_pct = retracement

        # Update retracement for bear legs using bar.low (prev.H was before bar.L)
        for leg in self.state.active_legs:
            if leg.direction == 'bear' and leg.status == 'active':
                if leg.range > 0:
                    retracement = (leg.pivot_price - bar_low) / leg.range
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
    ) -> List[SwingFormedEvent]:
        """
        Process Type 3 bar (outside bar - HH, LL).

        High volatility decision point. Both directions extended.
        Keep both branches until decisive resolution.
        """
        events = []

        # Extend bull legs (new high)
        for leg in self.state.active_legs:
            if leg.direction == 'bull' and leg.status == 'active':
                if bar_high > leg.origin_price:
                    leg.origin_price = bar_high
                    leg.origin_index = bar.index
                    leg.last_modified_bar = bar.index

        # Extend bear legs (new low)
        for leg in self.state.active_legs:
            if leg.direction == 'bear' and leg.status == 'active':
                if bar_low < leg.origin_price:
                    leg.origin_price = bar_low
                    leg.origin_index = bar.index
                    leg.last_modified_bar = bar.index

        # Update pending pivots to new extremes
        self.state.pending_pivots['bull'] = PendingPivot(
            price=bar_low, bar_index=bar.index, direction='bull', source='low'
        )
        self.state.pending_pivots['bear'] = PendingPivot(
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

            # Calculate retracement
            if leg.direction == 'bull':
                retracement = (check_price - leg.pivot_price) / leg.range
            else:
                retracement = (leg.pivot_price - check_price) / leg.range

            leg.retracement_pct = retracement

            if retracement >= formation_threshold:
                leg.formed = True
                event = self._form_swing_from_leg(leg, bar, timestamp)
                if event:
                    events.append(event)
                    # Form sibling swings from orphaned origins (#163)
                    sibling_events = self._form_sibling_swings_from_orphaned_origins(
                        leg, bar, timestamp, check_price
                    )
                    events.extend(sibling_events)

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
            if leg.direction == 'bull':
                retracement = (bar_high - leg.pivot_price) / leg.range
            else:
                retracement = (leg.pivot_price - bar_low) / leg.range

            leg.retracement_pct = retracement

            if retracement >= formation_threshold:
                leg.formed = True
                event = self._form_swing_from_leg(leg, bar, timestamp)
                if event:
                    events.append(event)
                    # Form sibling swings from orphaned origins (#163)
                    # Use close price for formation check (consistent with other formations)
                    close_price = Decimal(str(bar.close))
                    sibling_events = self._form_sibling_swings_from_orphaned_origins(
                        leg, bar, timestamp, close_price
                    )
                    events.extend(sibling_events)

        return events

    def _form_swing_from_leg(
        self, leg: Leg, bar: Bar, timestamp: datetime
    ) -> Optional[SwingFormedEvent]:
        """
        Create a SwingNode from a formed leg and add to active swings.

        No separation check needed at formation — DAG pruning (10% rule) already
        ensures surviving origins are sufficiently separated (#163).

        Returns:
            SwingFormedEvent or None if swing already exists
        """
        # Create SwingNode
        if leg.direction == 'bull':
            swing = SwingNode(
                swing_id=SwingNode.generate_id(),
                high_bar_index=leg.origin_index,
                high_price=leg.origin_price,
                low_bar_index=leg.pivot_index,
                low_price=leg.pivot_price,
                direction="bull",
                status="active",
                formed_at_bar=bar.index,
            )
        else:
            swing = SwingNode(
                swing_id=SwingNode.generate_id(),
                high_bar_index=leg.pivot_index,
                high_price=leg.pivot_price,
                low_bar_index=leg.origin_index,
                low_price=leg.origin_price,
                direction="bear",
                status="active",
                formed_at_bar=bar.index,
            )

        # Find parents
        parents = self._find_parents(swing)
        for parent in parents:
            swing.add_parent(parent)

        # Track swing range and add to active swings
        self.state.all_swing_ranges.append(swing.range)
        self.state._threshold_valid = False
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

    def _form_sibling_swings_from_orphaned_origins(
        self, leg: Leg, bar: Bar, timestamp: datetime, close_price: Decimal
    ) -> List[SwingFormedEvent]:
        """
        Form sibling swings from orphaned origins that share the same defended pivot (#163).

        When a leg forms, check if any orphaned origins can also form valid swings
        with the same defended pivot. This enables detection of nested swings like
        L2, L4, L5, L7 from valid_swings.md.

        Args:
            leg: The leg that just formed (provides the defended pivot)
            bar: Current bar
            timestamp: Event timestamp
            close_price: Current close price for formation check

        Returns:
            List of SwingFormedEvent for any sibling swings formed
        """
        events: List[SwingFormedEvent] = []
        config = self.config.bull if leg.direction == 'bull' else self.config.bear
        formation_threshold = Decimal(str(config.formation_fib))

        # Get orphaned origins for this direction
        orphaned = self.state.orphaned_origins.get(leg.direction, [])
        if not orphaned:
            return events

        pivot_price = leg.pivot_price
        pivot_index = leg.pivot_index

        # Track which origins we successfully used (to remove them)
        used_origins: List[Tuple[Decimal, int]] = []

        for origin_price, origin_index in orphaned:
            # Origin must be temporally before pivot
            if origin_index >= pivot_index:
                continue

            # Calculate swing range
            swing_range = abs(origin_price - pivot_price)
            if swing_range == 0:
                continue

            # Check formation threshold
            if leg.direction == 'bull':
                # Bull: ratio = (close - pivot) / range
                ratio = (close_price - pivot_price) / swing_range
            else:
                # Bear: ratio = (pivot - close) / range
                ratio = (pivot_price - close_price) / swing_range

            if ratio < formation_threshold:
                continue

            # No separation check needed — 10% pruning already ensures
            # orphaned origins are sufficiently separated (#163)

            # Check if this exact swing already exists
            swing_exists = False
            for swing in self.state.active_swings:
                if swing.direction != leg.direction:
                    continue
                if leg.direction == 'bull':
                    if swing.high_bar_index == origin_index and swing.low_bar_index == pivot_index:
                        swing_exists = True
                        break
                else:
                    if swing.low_bar_index == origin_index and swing.high_bar_index == pivot_index:
                        swing_exists = True
                        break

            if swing_exists:
                continue

            # Create the sibling swing
            if leg.direction == 'bull':
                swing = SwingNode(
                    swing_id=SwingNode.generate_id(),
                    high_bar_index=origin_index,
                    high_price=origin_price,
                    low_bar_index=pivot_index,
                    low_price=pivot_price,
                    direction="bull",
                    status="active",
                    formed_at_bar=bar.index,
                )
            else:
                swing = SwingNode(
                    swing_id=SwingNode.generate_id(),
                    high_bar_index=pivot_index,
                    high_price=pivot_price,
                    low_bar_index=origin_index,
                    low_price=origin_price,
                    direction="bear",
                    status="active",
                    formed_at_bar=bar.index,
                )

            # Find parents
            parents = self._find_parents(swing)
            for parent in parents:
                swing.add_parent(parent)

            # Track and add swing
            self.state.all_swing_ranges.append(swing.range)
            self.state._threshold_valid = False
            self.state.active_swings.append(swing)

            # Initialize level tracking
            self.state.fib_levels_crossed[swing.swing_id] = self._find_level_band(float(ratio))

            events.append(SwingFormedEvent(
                bar_index=bar.index,
                timestamp=timestamp,
                swing_id=swing.swing_id,
                high_bar_index=swing.high_bar_index,
                high_price=swing.high_price,
                low_bar_index=swing.low_bar_index,
                low_price=swing.low_price,
                direction=swing.direction,
                parent_ids=[p.swing_id for p in parents],
            ))

            used_origins.append((origin_price, origin_index))

        # Remove used orphaned origins
        for origin in used_origins:
            if origin in self.state.orphaned_origins[leg.direction]:
                self.state.orphaned_origins[leg.direction].remove(origin)

        return events

    def _check_leg_invalidations(
        self, bar: Bar, timestamp: datetime, bar_high: Decimal, bar_low: Decimal
    ) -> List[SwingFormedEvent]:
        """
        Check for decisive invalidation (0.382 rule) of legs.

        A leg is decisively invalidated when price moves 38.2% of the
        leg's range beyond the defended pivot.

        When a leg is invalidated, its origin is preserved as an "orphaned origin"
        for potential sibling swing formation (#163).
        """
        invalidation_threshold = Decimal("0.382")
        invalidated_legs: List[Leg] = []

        for leg in self.state.active_legs:
            if leg.status != 'active':
                continue

            if leg.range == 0:
                continue

            threshold_amount = invalidation_threshold * leg.range

            if leg.direction == 'bull':
                invalidation_price = leg.pivot_price - threshold_amount
                if bar_low < invalidation_price:
                    leg.status = 'invalidated'
                    invalidated_legs.append(leg)
            else:  # bear
                invalidation_price = leg.pivot_price + threshold_amount
                if bar_high > invalidation_price:
                    leg.status = 'invalidated'
                    invalidated_legs.append(leg)

        # Preserve origins from invalidated legs (#163)
        # These can form sibling swings with the same defended pivot later
        for leg in invalidated_legs:
            origin_tuple = (leg.origin_price, leg.origin_index)
            # Add to orphaned origins if not already present
            if origin_tuple not in self.state.orphaned_origins[leg.direction]:
                self.state.orphaned_origins[leg.direction].append(origin_tuple)

        # Remove invalidated legs
        self.state.active_legs = [leg for leg in self.state.active_legs if leg.status != 'invalidated']

        return []  # Leg invalidation doesn't emit events (only swing invalidation does)

    def _check_staleness(self, bar: Bar) -> None:
        """
        Apply staleness pruning (2x rule).

        A leg is stale when price has moved 2x the leg's range without
        the leg changing.
        """
        staleness_threshold = Decimal(str(self.config.staleness_threshold))

        for leg in self.state.active_legs:
            if leg.status != 'active':
                continue

            if leg.range == 0:
                continue

            # Calculate price movement since leg was last modified
            if leg.direction == 'bull':
                # For bull leg, check how far price has moved down
                if self.state.price_low_water is not None:
                    price_move = leg.price_at_creation - self.state.price_low_water
                else:
                    price_move = Decimal("0")
            else:
                # For bear leg, check how far price has moved up
                if self.state.price_high_water is not None:
                    price_move = self.state.price_high_water - leg.price_at_creation
                else:
                    price_move = Decimal("0")

            # Check if stale (moved 2x without modification)
            if price_move > staleness_threshold * leg.range:
                if leg.last_modified_bar < bar.index - 10:  # Haven't changed in 10 bars
                    leg.status = 'stale'

        # Remove stale legs
        self.state.active_legs = [leg for leg in self.state.active_legs if leg.status != 'stale']

    def _prune_orphaned_origins(self, bar: Bar) -> None:
        """
        Apply 10% pruning to orphaned origins each bar (#163).

        For each direction:
        1. Current low (for bull) / high (for bear) is working 0
        2. For all orphaned 1s: calculate range from that 1 to working 0
        3. If any two orphaned 1s are within 10% of the larger range → prune the smaller
        4. As 0 extends, threshold grows, naturally eliminating noise

        This ensures only structurally significant origins survive for sibling
        swing formation.
        """
        bar_low = Decimal(str(bar.low))
        bar_high = Decimal(str(bar.high))
        prune_threshold = Decimal("0.1")

        for direction in ['bull', 'bear']:
            origins = self.state.orphaned_origins[direction]
            if not origins:
                continue

            # Working 0 is the current extreme in direction of defended pivot
            # Bull: defended pivot is LOW, so working 0 = current low
            # Bear: defended pivot is HIGH, so working 0 = current high
            working_0 = bar_low if direction == 'bull' else bar_high

            # Sort origins: for bull, highest first; for bear, lowest first
            # (we want to prefer origins that create larger ranges)
            sorted_origins = sorted(
                origins,
                key=lambda x: x[0],  # sort by price
                reverse=(direction == 'bull')
            )

            survivors: List[Tuple[Decimal, int]] = []
            for origin_price, origin_idx in sorted_origins:
                # Calculate range from this origin to working 0
                current_range = abs(origin_price - working_0)
                if current_range == 0:
                    continue

                # Calculate threshold: 10% of current range
                threshold = prune_threshold * current_range

                # Check if this origin is sufficiently separated from survivors
                is_separated = True
                for survivor_price, _ in survivors:
                    if abs(origin_price - survivor_price) < threshold:
                        is_separated = False
                        break

                if is_separated:
                    survivors.append((origin_price, origin_idx))

            self.state.orphaned_origins[direction] = survivors

    def process_bar(self, bar: Bar) -> List[SwingEvent]:
        """
        Process a single bar. Returns events generated.

        Uses DAG-based streaming algorithm for O(n log k) complexity.
        This replaces the previous O(n × k³) candidate pairing approach.

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

        # 1. Check invalidations of formed swings
        events.extend(self._check_invalidations(bar, timestamp))

        # 2. Check completions
        events.extend(self._check_completions(bar, timestamp))

        # 3. Check level crosses
        events.extend(self._check_level_crosses(bar, timestamp))

        # 4. Update DAG state and form new swings (O(1) per bar)
        dag_events = self._update_dag_state(bar, timestamp)
        events.extend(dag_events)

        return events

    def _check_invalidations(
        self, bar: Bar, timestamp: datetime
    ) -> List[SwingInvalidatedEvent]:
        """
        Check each active swing for defended pivot violation.

        Uses tolerance based on distance to big swing per Rule 2.2.
        Includes quick rejection to avoid creating ReferenceFrame for
        swings that can't possibly be invalidated by this bar.

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of SwingInvalidatedEvent for any invalidated swings.
        """
        events = []
        # Pre-convert bar prices once
        bar_low = Decimal(str(bar.low))
        bar_high = Decimal(str(bar.high))

        for swing in self.state.active_swings:
            if swing.status != "active":
                continue

            # Quick rejection: can this swing possibly be invalidated?
            # Avoid expensive tolerance lookup and ReferenceFrame creation
            # if the bar's price can't possibly violate the defended pivot.
            if swing.is_bull:
                # Bull swing: invalidated if bar.low violates defended low
                # Quick check: if bar.low >= defended_pivot, can't be invalidated
                if bar_low >= swing.defended_pivot:
                    continue
            else:
                # Bear swing: invalidated if bar.high violates defended high
                # Quick check: if bar.high <= defended_pivot, can't be invalidated
                if bar_high <= swing.defended_pivot:
                    continue

            # Passed quick check - now do full invalidation check
            check_price = bar_low if swing.is_bull else bar_high
            tolerance = self._get_tolerance(swing)

            # Full check with tolerance using ReferenceFrame
            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            if frame.is_violated(check_price, tolerance):
                swing.invalidate()
                excess = abs(check_price - swing.defended_pivot)
                events.append(
                    SwingInvalidatedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        violation_price=check_price,
                        excess_amount=excess,
                    )
                )

        return events

    def _check_completions(
        self, bar: Bar, timestamp: datetime
    ) -> List[SwingCompletedEvent]:
        """
        Check each active swing for 2.0 target reached.

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of SwingCompletedEvent for any completed swings.
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

            # Check price: high for bull (checking if 2.0 extension is reached above)
            # low for bear (checking if 2.0 extension is reached below)
            check_price = Decimal(str(bar.high if swing.is_bull else bar.low))

            if frame.is_completed(check_price):
                swing.complete()
                events.append(
                    SwingCompletedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        completion_price=check_price,
                    )
                )

        return events

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

    def _get_tolerance(self, swing: SwingNode) -> float:
        """
        Get invalidation tolerance based on distance to big swing (Rule 2.2).

        - Big swing (top 10% by range): full tolerance (0.15 price)
        - Child of big swing: basic tolerance (0.10)
        - Other: no tolerance (0)

        Args:
            swing: The swing to get tolerance for.

        Returns:
            Tolerance as fraction of range.
        """
        config = self.config.bull if swing.is_bull else self.config.bear
        distance = self._distance_to_big_swing(swing, config)

        if distance == 0:
            # Big swing itself - full tolerance
            return config.big_swing_price_tolerance
        elif distance <= 2:
            # Child or grandchild of big swing - basic tolerance
            return config.child_swing_tolerance
        else:
            # No big swing ancestor - absolute (no tolerance)
            return 0.0

    def _distance_to_big_swing(
        self, swing: SwingNode, config: DirectionConfig
    ) -> int:
        """
        Calculate hierarchy distance to nearest big swing ancestor.

        Returns:
            0 if swing itself is big
            1 if parent is big
            2 if grandparent is big
            999 if no big swing ancestor within 2 levels
        """
        if self._is_big_swing(swing, config):
            return 0

        for parent in swing.parents:
            if self._is_big_swing(parent, config):
                return 1
            for grandparent in parent.parents:
                if self._is_big_swing(grandparent, config):
                    return 2

        return 999

    def _update_big_threshold_cache(self) -> None:
        """
        Recompute cached big swing thresholds.

        This is called when the cache is invalidated (after a new swing forms).
        Sorting all_swing_ranges once and caching the thresholds avoids
        repeated O(n log n) sorts in _is_big_swing().
        """
        if not self.state.all_swing_ranges:
            self.state._cached_big_threshold_bull = Decimal("0")
            self.state._cached_big_threshold_bear = Decimal("0")
        else:
            sorted_ranges = sorted(self.state.all_swing_ranges, reverse=True)

            # Bull threshold
            bull_idx = int(len(sorted_ranges) * self.config.bull.big_swing_threshold)
            bull_idx = max(0, min(bull_idx, len(sorted_ranges) - 1))
            self.state._cached_big_threshold_bull = sorted_ranges[bull_idx]

            # Bear threshold
            bear_idx = int(len(sorted_ranges) * self.config.bear.big_swing_threshold)
            bear_idx = max(0, min(bear_idx, len(sorted_ranges) - 1))
            self.state._cached_big_threshold_bear = sorted_ranges[bear_idx]

        self.state._threshold_valid = True

    def _is_big_swing(self, swing: SwingNode, config: DirectionConfig) -> bool:
        """
        Check if swing is a "big swing" (top percentile by range).

        Big swings are those whose range is in the top X% of all swings,
        where X is determined by config.big_swing_threshold.

        Uses cached thresholds to avoid O(n log n) sort on every call.

        Args:
            swing: The swing to check.
            config: DirectionConfig with big_swing_threshold.

        Returns:
            True if swing is in top percentile by range.
        """
        if not self.state.all_swing_ranges:
            return False

        # Recompute cache if invalidated
        if not self.state._threshold_valid:
            self._update_big_threshold_cache()

        # Use cached threshold based on swing direction
        threshold = (
            self.state._cached_big_threshold_bull
            if swing.is_bull
            else self.state._cached_big_threshold_bear
        )

        return swing.range >= threshold

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
    ) -> "HierarchicalDetector":
        """
        Restore from serialized state.

        Args:
            state: DetectorState to restore from.
            config: SwingConfig to use (defaults to default config).

        Returns:
            HierarchicalDetector initialized with the given state.
        """
        detector = cls(config)
        detector.state = state
        return detector


def calibrate(
    bars: List[Bar],
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple["HierarchicalDetector", List[SwingEvent]]:
    """
    Run detection on historical bars.

    This is process_bar() in a loop — guarantees identical behavior
    to incremental playback.

    Args:
        bars: Historical bars to process.
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> bars = [Bar(index=i, ...) for i in range(1000)]
        >>> detector, events = calibrate(bars)
        >>> print(f"Found {len(detector.get_active_swings())} active swings")
        >>> # Continue processing new bars
        >>> new_events = detector.process_bar(new_bar)

        >>> # With progress callback
        >>> def on_progress(current, total):
        ...     print(f"Processing bar {current}/{total}")
        >>> detector, events = calibrate(bars, progress_callback=on_progress)
    """
    config = config or SwingConfig.default()

    detector = HierarchicalDetector(config)
    all_events: List[SwingEvent] = []
    total = len(bars)

    for i, bar in enumerate(bars):
        events = detector.process_bar(bar)
        all_events.extend(events)

        if progress_callback:
            progress_callback(i + 1, total)

    return detector, all_events


def dataframe_to_bars(df: pd.DataFrame) -> List[Bar]:
    """
    Convert DataFrame with OHLC columns to Bar list.

    Handles various column naming conventions commonly used in market data.

    Args:
        df: DataFrame with OHLC columns. Expects columns like:
            - open/Open, high/High, low/Low, close/Close
            - Optional: timestamp/date/time

    Returns:
        List of Bar objects suitable for process_bar() or calibrate().

    Example:
        >>> df = pd.read_csv("market_data.csv")
        >>> bars = dataframe_to_bars(df)
        >>> detector, events = calibrate(bars)
    """
    bars = []

    # Normalize column names to lowercase for consistent access
    col_map = {c.lower(): c for c in df.columns}

    for idx, row in df.iterrows():
        # Get timestamp - try various column names
        timestamp = None
        for ts_col in ["timestamp", "time", "date", "datetime"]:
            if ts_col in col_map:
                ts_value = row[col_map[ts_col]]
                # Convert to Unix timestamp if needed
                if isinstance(ts_value, (int, float)):
                    timestamp = float(ts_value)
                elif hasattr(ts_value, "timestamp"):
                    timestamp = ts_value.timestamp()
                break

        # Default timestamp if not found
        if timestamp is None:
            timestamp = 1700000000 + len(bars) * 60  # Generate sequential timestamps

        # Get OHLC values
        open_price = float(row[col_map.get("open", "open")])
        high_price = float(row[col_map.get("high", "high")])
        low_price = float(row[col_map.get("low", "low")])
        close_price = float(row[col_map.get("close", "close")])

        bars.append(
            Bar(
                index=idx if isinstance(idx, int) else len(bars),
                timestamp=int(timestamp),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
            )
        )

    return bars


def calibrate_from_dataframe(
    df: pd.DataFrame,
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple["HierarchicalDetector", List[SwingEvent]]:
    """
    Convenience wrapper for DataFrame input.

    Converts DataFrame to Bar list and runs calibration.

    Args:
        df: DataFrame with OHLC columns (open, high, low, close).
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> import pandas as pd
        >>> df = pd.read_csv("ES-5m.csv")
        >>> detector, events = calibrate_from_dataframe(df)
        >>> print(f"Detected {len(detector.get_active_swings())} active swings")
    """
    bars = dataframe_to_bars(df)
    return calibrate(bars, config, progress_callback)
