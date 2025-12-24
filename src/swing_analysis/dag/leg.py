"""
Leg and PendingOrigin data structures for the DAG layer.

These are the fundamental building blocks for tracking price movements
before they form into swings.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Literal


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
    # leg_id is now deterministic based on (direction, origin_price, origin_index)
    # This ensures IDs survive BE reset on step-back (#299)
    leg_id: str = field(default="")  # Computed in __post_init__
    swing_id: Optional[str] = None  # Set when leg forms into swing (#174)
    max_origin_breach: Optional[Decimal] = None  # Max breach beyond origin (None if never breached)
    max_pivot_breach: Optional[Decimal] = None  # Max breach beyond pivot (None if never breached)
    impulse: float = 0.0  # Points per bar (range / bar_count) - measures move intensity (#236)
    # Impulsiveness (0-100): Percentile rank of raw impulse against all formed legs (#241, #243)
    # Updated for live legs (max_origin_breach is None), frozen when leg stops being live
    impulsiveness: Optional[float] = None
    # Spikiness (0-100): Sigmoid-normalized skewness of bar contributions (#241, #244)
    # 50 = neutral (symmetric), 90+ = very spiky, 10- = very smooth
    spikiness: Optional[float] = None
    # Running moments for incremental spikiness calculation (#244)
    # These are O(1) space per leg and allow O(1) updates per bar
    _moment_n: int = 0  # Number of contributions tracked
    _moment_sum_x: float = 0.0  # Sum of contributions
    _moment_sum_x2: float = 0.0  # Sum of squared contributions
    _moment_sum_x3: float = 0.0  # Sum of cubed contributions
    _cached_range: Optional[Decimal] = None  # Cached range value for performance

    def __post_init__(self) -> None:
        """Compute deterministic leg_id if not provided."""
        if not self.leg_id:
            self.leg_id = self.make_leg_id(
                self.direction, self.origin_price, self.origin_index
            )
        # Initialize cached range
        self._cached_range = abs(self.origin_price - self.pivot_price)

    @staticmethod
    def make_leg_id(
        direction: str, origin_price: Decimal, origin_index: int
    ) -> str:
        """
        Generate deterministic leg ID from immutable properties.

        The tuple (direction, origin_price, origin_index) is unique because:
        - origin_index is a bar index - each bar processed once
        - Each bar can establish at most one pending origin per direction
        - Pending origin is cleared after leg creation

        Args:
            direction: 'bull' or 'bear'
            origin_price: Origin price (LOW for bull, HIGH for bear)
            origin_index: Bar index where origin was established

        Returns:
            Deterministic ID like "leg_bull_4425.50_1234"
        """
        return f"leg_{direction}_{origin_price}_{origin_index}"

    @staticmethod
    def make_swing_id(
        direction: str, origin_price: Decimal, origin_index: int
    ) -> str:
        """
        Generate deterministic swing ID from leg properties.

        Uses same base as leg_id but with "swing_" prefix.
        Called when a leg forms into a swing.

        Args:
            direction: 'bull' or 'bear'
            origin_price: Origin price of the forming leg
            origin_index: Origin bar index of the forming leg

        Returns:
            Deterministic ID like "swing_bull_4425.50_1234"
        """
        return f"swing_{direction}_{origin_price}_{origin_index}"

    @property
    def range(self) -> Decimal:
        """Absolute range of the leg (cached for performance)."""
        if self._cached_range is None:
            self._cached_range = abs(self.origin_price - self.pivot_price)
        return self._cached_range

    def update_pivot(self, new_pivot_price: Decimal, new_pivot_index: int) -> None:
        """Update pivot and invalidate range cache."""
        self.pivot_price = new_pivot_price
        self.pivot_index = new_pivot_index
        self._cached_range = abs(self.origin_price - new_pivot_price)

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
