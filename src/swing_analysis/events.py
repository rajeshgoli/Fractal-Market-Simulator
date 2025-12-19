"""
Swing Detection Events

Defines event types emitted by the hierarchical swing detector.
Each event captures a significant state change in the swing lifecycle.

See Docs/Working/swing_detection_rewrite_spec.md for design rationale.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .swing_node import SwingNode


@dataclass
class SwingEvent:
    """
    Base event from swing detector.

    All swing events share these common fields for identification and timing.

    Attributes:
        event_type: Discriminator for event type routing/filtering.
        bar_index: Bar index when the event occurred.
        timestamp: Datetime when the event occurred.
        swing_id: Unique identifier of the affected swing.
    """

    event_type: str
    bar_index: int
    timestamp: datetime
    swing_id: str


@dataclass
class SwingFormedEvent(SwingEvent):
    """
    Emitted when a new swing is confirmed.

    A swing is confirmed when price breaches the configurable formation fib
    (default 0.287) from the defended pivot, with proper structural separation.

    Attributes:
        event_type: Always "SWING_FORMED".
        high_bar_index: Bar index of the swing high.
        high_price: Price at the swing high.
        low_bar_index: Bar index of the swing low.
        low_price: Price at the swing low.
        direction: "bull" or "bear".
        parent_ids: IDs of parent swings in the hierarchy.

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = SwingFormedEvent(
        ...     bar_index=100,
        ...     timestamp=datetime.now(),
        ...     swing_id="abc12345",
        ...     high_bar_index=80,
        ...     high_price=Decimal("5100.00"),
        ...     low_bar_index=100,
        ...     low_price=Decimal("5000.00"),
        ...     direction="bull",
        ...     parent_ids=["parent01"],
        ... )
        >>> event.event_type
        'SWING_FORMED'
    """

    event_type: Literal["SWING_FORMED"] = field(default="SWING_FORMED", init=False)
    high_bar_index: int = 0
    high_price: Decimal = field(default_factory=lambda: Decimal("0"))
    low_bar_index: int = 0
    low_price: Decimal = field(default_factory=lambda: Decimal("0"))
    direction: str = ""
    parent_ids: List[str] = field(default_factory=list)

    def get_explanation(self) -> str:
        """
        Human-readable explanation of why swing formed.

        Returns:
            Explanation string describing the formation trigger.
        """
        swing_range = abs(self.high_price - self.low_price)

        if self.direction == "bull":
            # Bull: defended pivot is low, price rises toward high
            fib_0382 = self.low_price + swing_range * Decimal("0.382")
            fib_2 = self.low_price + swing_range * Decimal("2.0")
            current_price = self.low_price + swing_range * Decimal("0.287")
            return (
                f"Price entered zone above 0.382 ({fib_0382:.2f})\n"
                f"Active range: {fib_0382:.2f} -> {fib_2:.2f}"
            )
        else:
            # Bear: defended pivot is high, price falls toward low
            fib_0382 = self.high_price - swing_range * Decimal("0.382")
            fib_2 = self.high_price - swing_range * Decimal("2.0")
            return (
                f"Price entered zone below 0.382 ({fib_0382:.2f})\n"
                f"Active range: {fib_0382:.2f} -> {fib_2:.2f}"
            )


@dataclass
class SwingInvalidatedEvent(SwingEvent):
    """
    Emitted when a swing's defended pivot is violated.

    Invalidation occurs when price breaches the defended pivot (0 level)
    beyond the applicable tolerance. Tolerance depends on hierarchy distance
    to the nearest "big swing".

    Attributes:
        event_type: Always "SWING_INVALIDATED".
        violation_price: Price at which the violation occurred.
        excess_amount: How far past the pivot the price went.
        reason: Why the swing was invalidated ("leg_invalidated", "tolerance_exceeded", etc.)

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = SwingInvalidatedEvent(
        ...     bar_index=200,
        ...     timestamp=datetime.now(),
        ...     swing_id="abc12345",
        ...     violation_price=Decimal("4990.00"),
        ...     excess_amount=Decimal("10.00"),
        ...     reason="leg_invalidated",
        ... )
        >>> event.event_type
        'SWING_INVALIDATED'
    """

    event_type: Literal["SWING_INVALIDATED"] = field(
        default="SWING_INVALIDATED", init=False
    )
    violation_price: Decimal = field(default_factory=lambda: Decimal("0"))
    excess_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    reason: str = ""  # Why invalidated: "leg_invalidated", "tolerance_exceeded", etc. (#174)

    def get_explanation(self) -> str:
        """
        Human-readable explanation of violation.

        Returns:
            Explanation string describing the invalidation trigger.
        """
        return (
            f"Price ({self.violation_price:.2f}) broke pivot by "
            f"{abs(self.excess_amount):.2f} pts\n"
            f"Pivot exceeded - swing invalidated"
        )


@dataclass
class SwingCompletedEvent(SwingEvent):
    """
    Emitted when a swing reaches 2.0 target.

    Completion indicates the swing has achieved its full extension target,
    measuring a 200% move from the defended pivot toward the origin direction.

    Attributes:
        event_type: Always "SWING_COMPLETED".
        completion_price: Price at which completion occurred.

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = SwingCompletedEvent(
        ...     bar_index=300,
        ...     timestamp=datetime.now(),
        ...     swing_id="abc12345",
        ...     completion_price=Decimal("5200.00"),
        ... )
        >>> event.event_type
        'SWING_COMPLETED'
    """

    event_type: Literal["SWING_COMPLETED"] = field(
        default="SWING_COMPLETED", init=False
    )
    completion_price: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class LevelCrossEvent(SwingEvent):
    """
    Emitted when price crosses a Fib level.

    Level crosses are tracked for significant Fibonacci ratios:
    0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0

    Attributes:
        event_type: Always "LEVEL_CROSS".
        level: The Fib level that was crossed (e.g., 0.618).
        previous_level: The previous Fib level the price was at.
        price: Price at which the cross occurred.

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = LevelCrossEvent(
        ...     bar_index=150,
        ...     timestamp=datetime.now(),
        ...     swing_id="abc12345",
        ...     level=0.618,
        ...     previous_level=0.5,
        ...     price=Decimal("5061.80"),
        ... )
        >>> event.event_type
        'LEVEL_CROSS'
    """

    event_type: Literal["LEVEL_CROSS"] = field(default="LEVEL_CROSS", init=False)
    level: float = 0.0
    previous_level: float = 0.0
    price: Decimal = field(default_factory=lambda: Decimal("0"))

    def get_explanation(self) -> str:
        """
        Human-readable explanation of level cross.

        Returns:
            Explanation string describing the level transition.
        """
        if self.level > self.previous_level:
            direction = "up"
            from_side = "below"
            to_side = "above"
        else:
            direction = "down"
            from_side = "above"
            to_side = "below"

        return (
            f"Price ({self.price:.2f}) crossed {direction} from "
            f"{self.previous_level:.3f} to {self.level:.3f}\n"
            f"Moved from {from_side} to {to_side} {self.level:.3f} level"
        )


@dataclass
class LegCreatedEvent(SwingEvent):
    """
    Emitted when a new candidate leg is formed.

    A leg is a directional price movement that may eventually form into a swing
    if it reaches the formation threshold (0.382). Legs are the pre-formation
    stage of swings.

    Attributes:
        event_type: Always "LEG_CREATED".
        leg_id: Unique identifier for this leg.
        direction: "bull" or "bear".
        pivot_price: The defended pivot price (must hold).
        pivot_index: Bar index where pivot was established.
        origin_price: Current origin price.
        origin_index: Bar index of origin.

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = LegCreatedEvent(
        ...     bar_index=50,
        ...     timestamp=datetime.now(),
        ...     swing_id="",  # Leg doesn't have swing_id yet
        ...     leg_id="leg_abc123",
        ...     direction="bull",
        ...     pivot_price=Decimal("5000.00"),
        ...     pivot_index=40,
        ...     origin_price=Decimal("5100.00"),
        ...     origin_index=50,
        ... )
        >>> event.event_type
        'LEG_CREATED'
    """

    event_type: Literal["LEG_CREATED"] = field(default="LEG_CREATED", init=False)
    leg_id: str = ""
    direction: str = ""  # 'bull' or 'bear'
    pivot_price: Decimal = field(default_factory=lambda: Decimal("0"))
    pivot_index: int = 0
    origin_price: Decimal = field(default_factory=lambda: Decimal("0"))
    origin_index: int = 0


@dataclass
class LegPrunedEvent(SwingEvent):
    """
    Emitted when a leg is removed due to staleness or dominance.

    Legs are pruned when they become stale (price has moved 2x the leg's range
    without the leg changing) or when a dominant leg makes them redundant.

    Attributes:
        event_type: Always "LEG_PRUNED".
        leg_id: Unique identifier for the pruned leg.
        reason: Why pruned ("staleness" or "dominance").

    Example:
        >>> from datetime import datetime
        >>> event = LegPrunedEvent(
        ...     bar_index=100,
        ...     timestamp=datetime.now(),
        ...     swing_id="",
        ...     leg_id="leg_abc123",
        ...     reason="staleness",
        ... )
        >>> event.event_type
        'LEG_PRUNED'
    """

    event_type: Literal["LEG_PRUNED"] = field(default="LEG_PRUNED", init=False)
    leg_id: str = ""
    reason: str = ""  # 'staleness', 'dominance'


@dataclass
class LegInvalidatedEvent(SwingEvent):
    """
    Emitted when a leg falls below 0.382 threshold (decisive invalidation).

    A leg is invalidated when price moves 38.2% of the leg's range beyond the
    defended pivot. When a leg is invalidated, its origin is preserved as an
    orphaned origin for potential sibling swing formation.

    Attributes:
        event_type: Always "LEG_INVALIDATED".
        leg_id: Unique identifier for the invalidated leg.
        invalidation_price: Price at which invalidation occurred.

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = LegInvalidatedEvent(
        ...     bar_index=75,
        ...     timestamp=datetime.now(),
        ...     swing_id="",
        ...     leg_id="leg_abc123",
        ...     invalidation_price=Decimal("4961.80"),
        ... )
        >>> event.event_type
        'LEG_INVALIDATED'
    """

    event_type: Literal["LEG_INVALIDATED"] = field(
        default="LEG_INVALIDATED", init=False
    )
    leg_id: str = ""
    invalidation_price: Decimal = field(default_factory=lambda: Decimal("0"))
