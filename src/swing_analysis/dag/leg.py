"""
Leg and PendingOrigin data structures for the DAG layer.

These are the fundamental building blocks for tracking price movements
before they form into swings.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Literal

from ..swing_node import SwingNode


@dataclass
class Leg:
    """
    A directional price movement with known temporal ordering.

    Terminology:
    - Origin: Where the move started (fixed starting point)
    - Pivot: The defended extreme where price may turn (extends as leg grows)

    Bull leg: origin at LOW -> pivot at HIGH (upward movement)
    Bear leg: origin at HIGH -> pivot at LOW (downward movement)

    Attributes:
        direction: 'bull' or 'bear'
        origin_price: Where the move originated (fixed starting point)
        origin_index: Bar index where origin was established
        pivot_price: Current defended extreme (extends as leg grows)
        pivot_index: Bar index of current pivot
        retracement_pct: Current retracement percentage toward origin
        formed: Whether 38.2% threshold has been reached
        parent_leg_id: ID of parent leg if this is a child
        status: 'active', 'stale', or 'invalidated'
        bar_count: Number of bars since leg started
        gap_count: Number of gap bars in this leg
        last_modified_bar: Bar index when leg was last modified
        price_at_creation: Price when leg was created (for staleness)
        max_origin_breach: Maximum breach beyond origin (None if never breached)
        max_pivot_breach: Maximum breach beyond pivot (None if never breached)
    """
    direction: Literal['bull', 'bear']
    origin_price: Decimal
    origin_index: int
    pivot_price: Decimal
    pivot_index: int
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
    max_origin_breach: Optional[Decimal] = None  # Max breach beyond origin (None if never breached)
    max_pivot_breach: Optional[Decimal] = None  # Max breach beyond pivot (None if never breached)
    impulse: float = 0.0  # Points per bar (range / bar_count) - measures move intensity (#236)

    @property
    def range(self) -> Decimal:
        """Absolute range of the leg."""
        return abs(self.origin_price - self.pivot_price)

    @property
    def origin_breached(self) -> bool:
        """True if price has ever breached the origin."""
        return self.max_origin_breach is not None

    @property
    def pivot_breached(self) -> bool:
        """True if price has ever breached the pivot."""
        return self.max_pivot_breach is not None


@dataclass
class PendingOrigin:
    """
    A potential origin for a new leg awaiting temporal confirmation.

    Created when a bar establishes a new extreme that could be the starting
    point (origin) of a future leg. Confirmed when subsequent bar establishes
    temporal ordering.

    For bull legs: tracks LOWs (bull origin = where upward move starts)
    For bear legs: tracks HIGHs (bear origin = where downward move starts)

    Attributes:
        price: The origin price (LOW for bull, HIGH for bear)
        bar_index: Bar index where this was established
        direction: What leg type this could start ('bull' or 'bear')
        source: Which price component ('high', 'low', 'open', 'close')
    """
    price: Decimal
    bar_index: int
    direction: Literal['bull', 'bear']
    source: Literal['high', 'low', 'open', 'close']
