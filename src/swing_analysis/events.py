"""
Detection Events

Defines event types emitted by the hierarchical detector.
Each event captures a significant state change in the leg lifecycle.

See Docs/Working/swing_detection_rewrite_spec.md for design rationale.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional


@dataclass
class DetectionEvent:
    """
    Base event from detector.

    All detection events share these common fields for identification and timing.

    Attributes:
        event_type: Discriminator for event type routing/filtering.
        bar_index: Bar index when the event occurred.
        timestamp: Datetime when the event occurred.
    """

    event_type: str
    bar_index: int
    timestamp: datetime


@dataclass
class LegCreatedEvent(DetectionEvent):
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
class LegPrunedEvent(DetectionEvent):
    """
    Emitted when a leg is removed due to staleness or pruning rules.

    Prune reasons:
    - "staleness": Leg hasn't changed in 10 bars while price moved 2x its range
    - "origin_proximity_prune": Leg is too close to an older leg in (time, range) space (#294)
    - "extension_prune": Invalidated leg has reached 3x extension
    - "pivot_breach": Formed leg's pivot was breached beyond threshold
    - "engulfed": Leg's origin was breached and pivot threshold exceeded
    - "inner_structure": Leg from inner structure pivot pruned when outer exists

    Attributes:
        event_type: Always "LEG_PRUNED".
        leg_id: Unique identifier for the pruned leg.
        reason: Why the leg was pruned.

    Example:
        >>> from datetime import datetime
        >>> event = LegPrunedEvent(
        ...     bar_index=100,
        ...     timestamp=datetime.now(),
        ...     leg_id="leg_abc123",
        ...     reason="staleness",
        ... )
        >>> event.event_type
        'LEG_PRUNED'
    """

    event_type: Literal["LEG_PRUNED"] = field(default="LEG_PRUNED", init=False)
    leg_id: str = ""
    reason: str = ""
    explanation: str = ""  # Optional detailed explanation (e.g., comparison values)


@dataclass
class LegInvalidatedEvent(DetectionEvent):
    """
    Emitted when a leg falls below 0.382 threshold (decisive invalidation).

    A leg is invalidated when price moves 38.2% of the leg's range beyond the
    defended pivot.

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


@dataclass
class OriginBreachedEvent(DetectionEvent):
    """
    Emitted when a leg's origin is first breached (price crosses origin).

    This is distinct from invalidation (-0.382 threshold). Origin breach
    means price has crossed back past the origin point, compromising the
    leg's structural integrity but not yet invalidating it.

    Attributes:
        event_type: Always "ORIGIN_BREACHED".
        leg_id: Unique identifier for the leg.
        breach_price: Price at which breach occurred.
        breach_amount: How far past origin (absolute value).

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = OriginBreachedEvent(
        ...     bar_index=50,
        ...     timestamp=datetime.now(),
        ...     leg_id="leg_abc123",
        ...     breach_price=Decimal("4950.00"),
        ...     breach_amount=Decimal("2.50"),
        ... )
        >>> event.event_type
        'ORIGIN_BREACHED'
    """

    event_type: Literal["ORIGIN_BREACHED"] = field(
        default="ORIGIN_BREACHED", init=False
    )
    leg_id: str = ""
    breach_price: Decimal = field(default_factory=lambda: Decimal("0"))
    breach_amount: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class PivotBreachedEvent(DetectionEvent):
    """
    Emitted when a formed leg's pivot is first breached (price crosses pivot).

    This tracks when price extends past a formed leg's pivot point. Only
    emitted for formed legs - forming legs have extending pivots.

    Attributes:
        event_type: Always "PIVOT_BREACHED".
        leg_id: Unique identifier for the leg.
        breach_price: Price at which breach occurred.
        breach_amount: How far past pivot (absolute value).

    Example:
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> event = PivotBreachedEvent(
        ...     bar_index=60,
        ...     timestamp=datetime.now(),
        ...     leg_id="leg_abc123",
        ...     breach_price=Decimal("5010.00"),
        ...     breach_amount=Decimal("5.00"),
        ... )
        >>> event.event_type
        'PIVOT_BREACHED'
    """

    event_type: Literal["PIVOT_BREACHED"] = field(
        default="PIVOT_BREACHED", init=False
    )
    leg_id: str = ""
    breach_price: Decimal = field(default_factory=lambda: Decimal("0"))
    breach_amount: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class LevelCrossEvent(DetectionEvent):
    """
    Emitted when a tracked leg's price crosses a fib level.

    This event is emitted by the Reference Layer for legs that are being
    tracked for level crossings (opt-in via add_crossing_tracking).

    Standard fib levels: 0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0

    Attributes:
        event_type: Always "LEVEL_CROSS".
        leg_id: Unique identifier for the tracked leg.
        direction: "bull" or "bear" (the leg's direction).
        level_crossed: The fib level that was crossed (e.g., 0.618).
        cross_direction: "up" if price crossed from below, "down" if from above.

    Example:
        >>> from datetime import datetime
        >>> event = LevelCrossEvent(
        ...     bar_index=100,
        ...     timestamp=datetime.now(),
        ...     leg_id="leg_bear_5000.00_50",
        ...     direction="bear",
        ...     level_crossed=0.618,
        ...     cross_direction="up",
        ... )
        >>> event.event_type
        'LEVEL_CROSS'
        >>> event.level_crossed
        0.618
    """

    event_type: Literal["LEVEL_CROSS"] = field(default="LEVEL_CROSS", init=False)
    leg_id: str = ""
    direction: str = ""  # 'bull' or 'bear'
    level_crossed: float = 0.0  # The fib level (0, 0.382, 0.5, etc.)
    cross_direction: str = ""  # 'up' or 'down'
