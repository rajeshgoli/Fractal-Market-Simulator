"""
Swing Node

Defines the SwingNode dataclass for the swing detection model.

See Docs/Working/swing_detection_rewrite_spec.md for design rationale.
See Docs/Reference/valid_swings.md for the canonical rules.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
import uuid


@dataclass
class SwingNode:
    """
    A swing node representing a price range structure.

    Represents a price range (high to low) used to predict future price action.
    Using a symmetric reference frame:
    - 0 = Defended pivot (low for bull, high for bear) - must never be violated
    - 1 = Origin (high for bull, low for bear) - the starting extremum
    - 2 = Target (completion level)

    Attributes:
        swing_id: Unique identifier for this swing.
        high_bar_index: Bar index where the high occurred.
        high_price: The high price of this swing.
        low_bar_index: Bar index where the low occurred.
        low_price: The low price of this swing.
        direction: "bull" (defending low, came from high) or
                   "bear" (defending high, came from low).
        status: Current lifecycle status:
            - "forming": Swing detected but not yet confirmed
            - "active": Confirmed and being tracked
            - "invalidated": Defended pivot was violated
            - "completed": Price reached 2.0 extension target
        formed_at_bar: Bar index when this swing was confirmed (status became "active").

    Example:
        >>> from decimal import Decimal
        >>> swing = SwingNode(
        ...     swing_id=SwingNode.generate_id(),
        ...     high_bar_index=100,
        ...     high_price=Decimal("5100.00"),
        ...     low_bar_index=150,
        ...     low_price=Decimal("5000.00"),
        ...     direction="bull",
        ...     status="active",
        ...     formed_at_bar=150,
        ... )
        >>> swing.defended_pivot
        Decimal('5000.00')
        >>> swing.origin
        Decimal('5100.00')
        >>> swing.range
        Decimal('100.00')
    """

    swing_id: str
    high_bar_index: int
    high_price: Decimal
    low_bar_index: int
    low_price: Decimal
    direction: Literal["bull", "bear"]
    status: Literal["forming", "active", "invalidated", "completed"]
    formed_at_bar: int

    @staticmethod
    def generate_id() -> str:
        """
        Generate a unique swing identifier.

        Returns a short UUID prefix (8 characters) for readability
        while maintaining sufficient uniqueness for practical use.

        Returns:
            8-character unique identifier string.
        """
        return str(uuid.uuid4())[:8]

    @property
    def defended_pivot(self) -> Decimal:
        """
        The price level that must hold (0 in reference frame).

        For bull swings, this is the low - if violated, the swing is invalidated.
        For bear swings, this is the high - if violated, the swing is invalidated.
        """
        return self.low_price if self.direction == "bull" else self.high_price

    @property
    def origin(self) -> Decimal:
        """
        The origin extremum (1 in reference frame).

        For bull swings, this is the high where the down move started.
        For bear swings, this is the low where the up move started.
        """
        return self.high_price if self.direction == "bull" else self.low_price

    @property
    def range(self) -> Decimal:
        """
        Absolute range of the swing.

        Always positive regardless of direction.
        """
        return abs(self.high_price - self.low_price)

    @property
    def is_bull(self) -> bool:
        """Check if this is a bull swing (defending low)."""
        return self.direction == "bull"

    @property
    def is_bear(self) -> bool:
        """Check if this is a bear swing (defending high)."""
        return self.direction == "bear"

    @property
    def is_active(self) -> bool:
        """Check if this swing is currently active."""
        return self.status == "active"

    @property
    def is_invalidated(self) -> bool:
        """Check if this swing has been invalidated."""
        return self.status == "invalidated"

    @property
    def is_completed(self) -> bool:
        """Check if this swing has completed (reached 2.0 target)."""
        return self.status == "completed"

    def invalidate(self) -> None:
        """
        Mark this swing as invalidated.

        Called when the defended pivot (0) is violated beyond tolerance.
        Note: This does NOT automatically cascade to children. Each swing
        is invalidated independently when its own defended pivot is violated.
        """
        self.status = "invalidated"

    def complete(self) -> None:
        """
        Mark this swing as completed.

        Called when price reaches the 2.0 extension target.
        """
        self.status = "completed"

    def __repr__(self) -> str:
        return (
            f"SwingNode({self.swing_id}, {self.direction}, "
            f"{self.high_price}->{self.low_price}, {self.status})"
        )

    def __eq__(self, other: object) -> bool:
        """Swings are equal if they have the same swing_id."""
        if not isinstance(other, SwingNode):
            return NotImplemented
        return self.swing_id == other.swing_id

    def __hash__(self) -> int:
        """Hash based on swing_id for use in sets and dicts."""
        return hash(self.swing_id)
