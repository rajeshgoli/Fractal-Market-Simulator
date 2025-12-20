"""
DAG-Based Swing Detector (Structural Layer)

The DAG layer is responsible for structural tracking of price extremas. It processes
one bar at a time via process_bar() and emits events for swing formation and Fib
level crosses.

**This layer handles:**
- Leg tracking with 0.382 invalidation threshold
- Swing formation detection
- Level cross event tracking
- Parent-child relationship assignment
- Orphaned origin preservation for sibling detection

**This layer does NOT handle (see reference_layer.py):**
- Swing invalidation (tolerance-based rules)
- Swing completion (big swings never complete)
- Big swing classification (top 10% by range)

The separation allows the DAG to stay simple and O(n log k), while semantic/trading
rules can evolve independently in the Reference layer.

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
    LegCreatedEvent,
    LegPrunedEvent,
    LegInvalidatedEvent,
)
from .reference_frame import ReferenceFrame
from .types import Bar

# Import ReferenceLayer for type hints (avoid circular import)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .reference_layer import ReferenceLayer


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
    swing_id: Optional[str] = None  # Set when leg forms into swing (#174)

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
                "swing_id": leg.swing_id,
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
                swing_id=leg_data.get("swing_id"),
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

        # Check staleness and prune (#168: now emits LegPrunedEvent)
        staleness_events = self._check_staleness(bar, timestamp)
        events.extend(staleness_events)

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
    ) -> List[SwingEvent]:
        """
        Process Type 2-Bull bar (HH, HL - trending up).

        Establishes temporal order: prev_bar.L occurred before bar.H.
        This confirms a BEAR swing structure: prev_bar.L → bar.H (low origin → high pivot).

        Also extends any existing bull legs (tracking upward movement).
        """
        events: List[SwingEvent] = []

        # Prune bear legs on turn (#181): Type 2-Bull signals turn, prune redundant bear legs
        turn_prune_events = self._prune_legs_on_turn('bear', bar, timestamp)
        events.extend(turn_prune_events)

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
                # Emit LegCreatedEvent (#168)
                events.append(LegCreatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",  # Leg doesn't have swing_id yet
                    leg_id=new_leg.leg_id,
                    direction=new_leg.direction,
                    pivot_price=new_leg.pivot_price,
                    pivot_index=new_leg.pivot_index,
                    origin_price=new_leg.origin_price,
                    origin_index=new_leg.origin_index,
                ))

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
    ) -> List[SwingEvent]:
        """
        Process Type 2-Bear bar (LH, LL - trending down).

        Establishes temporal order: prev_bar.H occurred before bar.L.
        This confirms a BULL swing structure: prev_bar.H → bar.L (high origin → low pivot).
        A bull swing has: origin at high, defended pivot at low.

        Also extends any existing bear legs (tracking downward movement).
        """
        events: List[SwingEvent] = []

        # Prune bull legs on turn (#181): Type 2-Bear signals turn, prune redundant bull legs
        turn_prune_events = self._prune_legs_on_turn('bull', bar, timestamp)
        events.extend(turn_prune_events)

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
                # Emit LegCreatedEvent (#168)
                events.append(LegCreatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",
                    leg_id=new_leg.leg_id,
                    direction=new_leg.direction,
                    pivot_price=new_leg.pivot_price,
                    pivot_index=new_leg.pivot_index,
                    origin_price=new_leg.origin_price,
                    origin_index=new_leg.origin_index,
                ))

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
                # Emit LegCreatedEvent (#168)
                events.append(LegCreatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id="",
                    leg_id=new_bear_leg.leg_id,
                    direction=new_bear_leg.direction,
                    pivot_price=new_bear_leg.pivot_price,
                    pivot_index=new_bear_leg.pivot_index,
                    origin_price=new_bear_leg.origin_price,
                    origin_index=new_bear_leg.origin_index,
                ))

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
    ) -> List[SwingEvent]:
        """
        Process Type 1 bar (inside bar - LH, HL) or bars with equal H/L.

        Inside bars still have valid temporal ordering between bars:
        - prev_bar.H came before bar.L (can establish bear swing structure)
        - prev_bar.L came before bar.H (can establish bull swing structure)

        We should create legs from pending pivots if they haven't been consumed yet.
        """
        events: List[SwingEvent] = []
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
                    # Emit LegCreatedEvent (#168)
                    events.append(LegCreatedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id="",
                        leg_id=new_bull_leg.leg_id,
                        direction=new_bull_leg.direction,
                        pivot_price=new_bull_leg.pivot_price,
                        pivot_index=new_bull_leg.pivot_index,
                        origin_price=new_bull_leg.origin_price,
                        origin_index=new_bull_leg.origin_index,
                    ))

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
                    # Emit LegCreatedEvent (#168)
                    events.append(LegCreatedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id="",
                        leg_id=new_bear_leg.leg_id,
                        direction=new_bear_leg.direction,
                        pivot_price=new_bear_leg.pivot_price,
                        pivot_index=new_bear_leg.pivot_index,
                        origin_price=new_bear_leg.origin_price,
                        origin_index=new_bear_leg.origin_index,
                    ))

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
    ) -> List[SwingEvent]:
        """
        Process Type 3 bar (outside bar - HH, LL).

        High volatility decision point. Both directions extended.
        Keep both branches until decisive resolution.
        """
        events: List[SwingEvent] = []

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

        # Link leg to swing (#174)
        leg.swing_id = swing.swing_id

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

            # Add to active swings
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
    ) -> List[SwingEvent]:
        """
        Check for decisive invalidation (0.382 rule) of legs.

        A leg is decisively invalidated when price moves 38.2% of the
        leg's range beyond the defended pivot.

        When a leg is invalidated:
        - Its origin is preserved as an "orphaned origin" for sibling swing formation (#163)
        - If the leg formed into a swing, that swing is also invalidated (#174)

        Returns:
            List of LegInvalidatedEvent and SwingInvalidatedEvent for any
            legs/swings invalidated.
        """
        events: List[SwingEvent] = []
        invalidation_threshold = Decimal("0.382")
        invalidated_legs: List[Leg] = []
        invalidation_prices: Dict[str, Decimal] = {}  # leg_id -> price at invalidation

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
                    invalidation_prices[leg.leg_id] = bar_low
            else:  # bear
                invalidation_price = leg.pivot_price + threshold_amount
                if bar_high > invalidation_price:
                    leg.status = 'invalidated'
                    invalidated_legs.append(leg)
                    invalidation_prices[leg.leg_id] = bar_high

        # Preserve origins from invalidated legs (#163)
        # These can form sibling swings with the same defended pivot later
        for leg in invalidated_legs:
            origin_tuple = (leg.origin_price, leg.origin_index)
            # Add to orphaned origins if not already present
            if origin_tuple not in self.state.orphaned_origins[leg.direction]:
                self.state.orphaned_origins[leg.direction].append(origin_tuple)

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

        # Remove invalidated legs
        self.state.active_legs = [leg for leg in self.state.active_legs if leg.status != 'invalidated']

        return events

    def _check_staleness(self, bar: Bar, timestamp: datetime) -> List[LegPrunedEvent]:
        """
        Apply staleness pruning (2x rule).

        A leg is stale when price has moved 2x the leg's range without
        the leg changing.

        Returns:
            List of LegPrunedEvent for any legs pruned due to staleness.
        """
        events: List[LegPrunedEvent] = []
        staleness_threshold = Decimal(str(self.config.staleness_threshold))
        stale_legs: List[Leg] = []

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
                    stale_legs.append(leg)

        # Emit LegPrunedEvent for each stale leg (#168)
        for leg in stale_legs:
            events.append(LegPrunedEvent(
                bar_index=bar.index,
                timestamp=timestamp,
                swing_id="",
                leg_id=leg.leg_id,
                reason="staleness",
            ))

        # Remove stale legs
        self.state.active_legs = [leg for leg in self.state.active_legs if leg.status != 'stale']

        return events

    def _prune_legs_on_turn(
        self, direction: str, bar: Bar, timestamp: datetime
    ) -> List[LegPrunedEvent]:
        """
        Prune legs with recursive 10% rule and multi-origin preservation (#185).

        Replaces #181's "keep only longest" with a more nuanced approach:

        1. Group legs by origin
        2. For each origin group: keep largest + legs >= 10% of largest
        3. Multi-origin preservation: always keep at least one leg per origin
        4. Recursive 10% across origins: apply 10% rule globally to prune small origins
        5. Active swing immunity: legs with active swings are never pruned

        This preserves nested structure while compressing noise.

        Args:
            direction: 'bull' or 'bear' - which legs to prune
            bar: Current bar (for event metadata)
            timestamp: Timestamp for events

        Returns:
            List of LegPrunedEvent for pruned legs
        """
        from collections import defaultdict

        events: List[LegPrunedEvent] = []
        prune_threshold = Decimal("0.1")

        # Get active legs of the specified direction
        legs = [
            leg for leg in self.state.active_legs
            if leg.direction == direction and leg.status == 'active'
        ]

        if len(legs) <= 1:
            return events  # Nothing to prune

        # Build set of active swing IDs for immunity check
        active_swing_ids = {
            swing.swing_id for swing in self.state.active_swings
            if swing.status == 'active'
        }

        # Group by origin (same origin_price and origin_index)
        origin_groups: Dict[Tuple[Decimal, int], List[Leg]] = defaultdict(list)
        for leg in legs:
            key = (leg.origin_price, leg.origin_index)
            origin_groups[key].append(leg)

        pruned_leg_ids: Set[str] = set()

        # Step 1: Within each origin group, apply 10% rule
        # Keep largest + all legs >= 10% of largest (not just one)
        # Active swing immunity: legs with active swings are never pruned
        best_per_origin: Dict[Tuple[Decimal, int], Leg] = {}

        for origin_key, group in origin_groups.items():
            # Find the largest in this origin group
            largest = max(group, key=lambda l: l.range)
            best_per_origin[origin_key] = largest

            if len(group) <= 1:
                continue

            threshold = prune_threshold * largest.range

            # Prune legs < 10% of largest within same origin
            for leg in group:
                if leg.leg_id == largest.leg_id:
                    continue
                # Active swing immunity: never prune legs with active swings
                if leg.swing_id and leg.swing_id in active_swing_ids:
                    continue
                if leg.range < threshold:
                    leg.status = 'pruned'
                    pruned_leg_ids.add(leg.leg_id)
                    events.append(LegPrunedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id="",
                        leg_id=leg.leg_id,
                        reason="10pct_prune",
                    ))

        # Step 2: Recursive 10% across origins (subtree pruning)
        # Apply 10% rule to prune small origin groups whose best leg is
        # contained within a larger origin's best leg range
        events.extend(self._apply_recursive_subtree_prune(
            direction, bar, timestamp, best_per_origin, pruned_leg_ids, active_swing_ids
        ))

        # Remove pruned legs from active_legs
        self.state.active_legs = [
            leg for leg in self.state.active_legs
            if leg.leg_id not in pruned_leg_ids
        ]

        return events

    def _apply_recursive_subtree_prune(
        self,
        direction: str,
        bar: Bar,
        timestamp: datetime,
        best_per_origin: Dict[Tuple[Decimal, int], "Leg"],
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
        prune_threshold = Decimal("0.1")

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
        for leg in self.state.active_legs:
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
                    # Bull: pivot is low, origin is high
                    in_range = (parent_leg.pivot_price <= child_leg.pivot_price and
                                child_leg.origin_price <= parent_leg.origin_price)
                else:
                    # Bear: pivot is high, origin is low
                    in_range = (parent_leg.origin_price <= child_leg.origin_price and
                                child_leg.pivot_price <= parent_leg.pivot_price)

                # If contained and < 10% of parent, prune
                if in_range and child_leg.range < parent_threshold:
                    pruned_origins.add(child_origin)

                    # Prune all legs from this origin (except those with active swings)
                    for leg in self.state.active_legs:
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

        # 1. Check level crosses (structural tracking)
        events.extend(self._check_level_crosses(bar, timestamp))

        # 4. Update DAG state and form new swings (O(1) per bar)
        dag_events = self._update_dag_state(bar, timestamp)
        events.extend(dag_events)

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
    ref_layer: Optional["ReferenceLayer"] = None,
) -> Tuple["HierarchicalDetector", List[SwingEvent]]:
    """
    Run detection on historical bars.

    This is process_bar() in a loop — guarantees identical behavior
    to incremental playback.

    When a ReferenceLayer is provided, invalidation and completion checks
    are applied after each bar according to the Reference layer rules
    (tolerance-based invalidation for big swings, 2× completion for small swings).
    See Docs/Working/DAG_spec.md for the pipeline integration spec.

    Args:
        bars: Historical bars to process.
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.
        ref_layer: Optional ReferenceLayer for tolerance-based invalidation and
            completion. If provided, swings are pruned according to Reference
            layer rules during calibration (not just at response time).

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

        >>> # With Reference layer for tolerance-based invalidation
        >>> from swing_analysis.reference_layer import ReferenceLayer
        >>> ref_layer = ReferenceLayer(config)
        >>> detector, events = calibrate(bars, ref_layer=ref_layer)
    """
    config = config or SwingConfig.default()

    detector = HierarchicalDetector(config)
    all_events: List[SwingEvent] = []
    total = len(bars)

    for i, bar in enumerate(bars):
        # Create timestamp for events
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # 1. Process bar for DAG events (formation, structural invalidation, level cross)
        events = detector.process_bar(bar)
        all_events.extend(events)

        # 2. Apply Reference layer invalidation/completion if provided (#175)
        if ref_layer is not None:
            active_swings = detector.get_active_swings()

            # Check invalidation (tolerance-based rules)
            invalidated = ref_layer.update_invalidation_on_bar(active_swings, bar)
            for swing, result in invalidated:
                swing.invalidate()
                all_events.append(SwingInvalidatedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=swing.swing_id,
                    reason=f"reference_layer:{result.reason}",
                ))

            # Check completion (2× for small swings, big swings never complete)
            completed = ref_layer.update_completion_on_bar(active_swings, bar)
            for swing, result in completed:
                swing.complete()
                all_events.append(SwingCompletedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=swing.swing_id,
                    completion_price=result.completion_price,
                ))

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
    ref_layer: Optional["ReferenceLayer"] = None,
) -> Tuple["HierarchicalDetector", List[SwingEvent]]:
    """
    Convenience wrapper for DataFrame input.

    Converts DataFrame to Bar list and runs calibration.

    Args:
        df: DataFrame with OHLC columns (open, high, low, close).
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.
        ref_layer: Optional ReferenceLayer for tolerance-based invalidation and
            completion. If provided, swings are pruned according to Reference
            layer rules during calibration (not just at response time).

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> import pandas as pd
        >>> df = pd.read_csv("ES-5m.csv")
        >>> detector, events = calibrate_from_dataframe(df)
        >>> print(f"Detected {len(detector.get_active_swings())} active swings")

        >>> # With Reference layer for tolerance-based invalidation
        >>> from swing_analysis.reference_layer import ReferenceLayer
        >>> ref_layer = ReferenceLayer()
        >>> detector, events = calibrate_from_dataframe(df, ref_layer=ref_layer)
    """
    bars = dataframe_to_bars(df)
    return calibrate(bars, config, progress_callback, ref_layer)
