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
from typing import Literal


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

    def is_violated(self, price: Decimal, tolerance: float = 0) -> bool:
        """
        Check if defended pivot (0) is violated within tolerance.

        A swing is violated when price moves beyond the defended pivot
        (ratio < 0). The tolerance parameter allows for a small exceedance
        before considering it a true violation.

        Args:
            price: Current price to check
            tolerance: Fraction of range allowed beyond 0 (e.g., 0.10 = 10%)
                      Must be non-negative.

        Returns:
            True if price is below -tolerance in ratio terms

        Examples:
            >>> frame = ReferenceFrame(Decimal("5000"), Decimal("5100"), "BULL")
            >>> frame.is_violated(Decimal("4990"))  # -0.1 ratio, no tolerance
            True
            >>> frame.is_violated(Decimal("4990"), tolerance=0.15)  # within tolerance
            False
        """
        ratio = self.ratio(price)
        return ratio < Decimal(str(-tolerance))

    def is_formed(self, price: Decimal, formation_fib: float = 0.287) -> bool:
        """
        Check if price has breached formation threshold.

        A swing is "formed" when price moves beyond the formation_fib
        level from the defended pivot toward the target. This confirms
        the swing is structurally significant.

        Args:
            price: Current price to check
            formation_fib: Fib level that triggers formation (default 0.287)

        Returns:
            True if price is at or beyond formation_fib

        Examples:
            >>> frame = ReferenceFrame(Decimal("5000"), Decimal("5100"), "BULL")
            >>> frame.is_formed(Decimal("5020"))  # ratio 0.2
            False
            >>> frame.is_formed(Decimal("5030"))  # ratio 0.3
            True
        """
        ratio = self.ratio(price)
        return ratio >= Decimal(str(formation_fib))

    def is_completed(self, price: Decimal) -> bool:
        """
        Check if swing has reached 2.0 target.

        A swing is completed when price reaches or exceeds the 2x extension
        level, indicating full structural completion.

        Args:
            price: Current price to check

        Returns:
            True if price is at or beyond 2.0 extension

        Examples:
            >>> frame = ReferenceFrame(Decimal("5000"), Decimal("5100"), "BULL")
            >>> frame.is_completed(Decimal("5190"))  # ratio 1.9
            False
            >>> frame.is_completed(Decimal("5200"))  # ratio 2.0
            True
        """
        ratio = self.ratio(price)
        return ratio >= Decimal("2.0")

    def get_fib_price(self, level: float) -> Decimal:
        """
        Get the absolute price for a given Fib level.

        Convenience method for getting prices at standard Fib levels
        without manually calling price() with Decimal conversion.

        Args:
            level: Fib level (0, 0.382, 0.5, 0.618, 1.0, 2.0, etc.)

        Returns:
            Absolute price at that level

        Examples:
            >>> frame = ReferenceFrame(Decimal("5000"), Decimal("5100"), "BULL")
            >>> frame.get_fib_price(0)
            Decimal('5000')
            >>> frame.get_fib_price(0.618)
            Decimal('5061.8')
            >>> frame.get_fib_price(2.0)
            Decimal('5200.0')
        """
        return self.price(Decimal(str(level)))

    def __repr__(self) -> str:
        """Human-readable representation."""
        return (
            f"ReferenceFrame({self.direction}: "
            f"anchor0={self.anchor0}, anchor1={self.anchor1}, range={self.range})"
        )
