"""
ReferenceFrame: Oriented coordinate system for bull/bear swings.

A ReferenceFrame provides a unified way to convert between price and ratio coordinates
for any reference swing, regardless of direction. The frame normalizes the coordinate
system so that:
- ratio = 0 is always the defended pivot
- ratio = 1 is always the origin extremum
- ratio = 2 is always the completion target

This abstraction simplifies discretization logic by eliminating direction-specific
branching in ratio calculations.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .swing_detector import ReferenceSwing


@dataclass(frozen=True)
class ReferenceFrame:
    """
    Oriented reference frame for Fibonacci ratio calculations.

    For a bull swing (downswing completed, now bullish):
        - anchor0 = low (defended pivot / stop level)
        - anchor1 = high (origin extremum)

    For a bear swing (upswing completed, now bearish):
        - anchor0 = high (defended pivot / stop level)
        - anchor1 = low (origin extremum)

    Interpretation of ratios:
        - ratio = 0: Defended pivot (where stops are placed)
        - ratio = 1: Origin extremum (swing start)
        - ratio = 2: Completion target (2x extension)
        - ratio < 0: Beyond defended pivot (stop-run territory)

    Attributes:
        anchor0: The defended pivot price (low for bull, high for bear)
        anchor1: The origin extremum price (high for bull, low for bear)
        direction: "BULL" or "BEAR"
    """

    anchor0: Decimal  # Defended pivot
    anchor1: Decimal  # Origin extremum
    direction: Literal["BULL", "BEAR"]

    def __post_init__(self) -> None:
        """Validate that anchor0 and anchor1 are different."""
        if self.anchor0 == self.anchor1:
            raise ValueError("anchor0 and anchor1 must be different (zero range)")

    @property
    def range(self) -> Decimal:
        """
        Signed range of the swing.

        Returns:
            anchor1 - anchor0 (positive for bull, negative for bear)
        """
        return self.anchor1 - self.anchor0

    def ratio(self, price: Decimal) -> Decimal:
        """
        Convert an absolute price to a ratio in this frame.

        Args:
            price: The price to convert

        Returns:
            The ratio (0 = defended pivot, 1 = origin, 2 = completion target)
        """
        return (price - self.anchor0) / self.range

    def price(self, ratio: Decimal) -> Decimal:
        """
        Convert a ratio to an absolute price in this frame.

        Args:
            ratio: The ratio to convert (0 = defended pivot, 1 = origin)

        Returns:
            The absolute price
        """
        return self.anchor0 + ratio * self.range

    @classmethod
    def from_swing(cls, swing: "ReferenceSwing") -> "ReferenceFrame":
        """
        Create a ReferenceFrame from a ReferenceSwing.

        The swing's direction determines how anchor0/anchor1 are assigned:
        - Bull: anchor0 = low (defended), anchor1 = high (origin)
        - Bear: anchor0 = high (defended), anchor1 = low (origin)

        Args:
            swing: A ReferenceSwing from swing_detector

        Returns:
            A ReferenceFrame with properly oriented anchors
        """
        if swing.direction == "bull":
            return cls(
                anchor0=Decimal(str(swing.low_price)),
                anchor1=Decimal(str(swing.high_price)),
                direction="BULL",
            )
        else:
            return cls(
                anchor0=Decimal(str(swing.high_price)),
                anchor1=Decimal(str(swing.low_price)),
                direction="BEAR",
            )

    def __repr__(self) -> str:
        """Human-readable representation."""
        return (
            f"ReferenceFrame({self.direction}: "
            f"anchor0={self.anchor0}, anchor1={self.anchor1}, range={self.range})"
        )
