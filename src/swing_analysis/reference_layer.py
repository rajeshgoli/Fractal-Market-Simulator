"""
Reference Layer for Swing Filtering and Invalidation

Post-processes DAG output to produce "useful" trading references.
The DAG tracks structural extremas; the Reference layer applies semantic
rules from Docs/Reference/valid_swings.md.

Key responsibilities:
1. Differentiated invalidation (big swings get tolerance, small swings don't)
2. Completion checking (small swings complete at 2×, big swings never complete)

Big vs Small definition (hierarchy-based):
- Big swing = any swing without a parent (root level)
- Small swing = any swing with a parent

Design: Option A (post-filter DAG output) per DAG spec.
- DAG produces all swings
- Reference layer filters/annotates
- Clean separation, DAG stays simple

See Docs/Reference/valid_swings.md for the canonical rules.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Dict, Tuple

from .swing_config import SwingConfig
from .swing_node import SwingNode
from .reference_frame import ReferenceFrame
from .types import Bar


@dataclass
class ReferenceSwingInfo:
    """
    Additional metadata for a reference swing.

    This wraps a SwingNode with reference-layer specific annotations.

    Attributes:
        swing: The underlying SwingNode from the DAG.
        touch_tolerance: Invalidation tolerance for touch (wick) violations.
        close_tolerance: Invalidation tolerance for close violations.
        is_reference: Whether this swing passes all filters to be a trading reference.
        filter_reason: If not a reference, why it was filtered out.
    """
    swing: SwingNode
    touch_tolerance: float = 0.0
    close_tolerance: float = 0.0
    is_reference: bool = True
    filter_reason: Optional[str] = None

    def is_big(self) -> bool:
        """
        Check if this is a big swing (no parents = root level).

        Returns:
            True if swing has no parents (root level), False otherwise.
        """
        return len(self.swing.parents) == 0


@dataclass
class InvalidationResult:
    """
    Result of checking swing invalidation.

    Attributes:
        is_invalidated: Whether the swing should be invalidated.
        reason: Reason for invalidation (touch or close violation).
        violation_price: The price that caused the violation.
        excess: How far beyond the tolerance the violation occurred.
    """
    is_invalidated: bool
    reason: Optional[str] = None
    violation_price: Optional[Decimal] = None
    excess: Optional[Decimal] = None


@dataclass
class CompletionResult:
    """
    Result of checking swing completion.

    Attributes:
        is_completed: Whether the swing should be marked complete.
        reason: Reason for completion.
        completion_price: The price that triggered completion.
    """
    is_completed: bool
    reason: Optional[str] = None
    completion_price: Optional[Decimal] = None


class ReferenceLayer:
    """
    Filters and annotates DAG output to produce trading references.

    The Reference layer applies semantic rules to the structural swings
    produced by the DAG (HierarchicalDetector). It does not modify the
    DAG's internal state — it operates on snapshots of DAG output.

    Key operations:
    1. get_reference_swings(): Get all swings with tolerances computed
    2. check_invalidation(): Apply Rule 2.2 with touch/close thresholds
    3. check_completion(): Apply completion rules (2× for small, never for big)

    Big vs Small (hierarchy-based definition):
    - Big swing = len(swing.parents) == 0 (root level)
    - Small swing = len(swing.parents) > 0 (has parent)

    Invalidation tolerances (Rule 2.2):
    - Small swings (has parent): No tolerance — any violation invalidates
    - Big swings (no parent): 0.15 touch tolerance, 0.10 close tolerance

    Completion rules:
    - Small swings (has parent): Complete at 2× extension
    - Big swings (no parent): Never complete — keep active indefinitely

    Example:
        >>> from swing_analysis.reference_layer import ReferenceLayer
        >>> from swing_analysis.hierarchical_detector import calibrate
        >>>
        >>> # Get swings from DAG
        >>> detector, events = calibrate(bars)
        >>> swings = detector.get_active_swings()
        >>>
        >>> # Apply reference layer filters
        >>> config = SwingConfig.default()
        >>> ref_layer = ReferenceLayer(config)
        >>> reference_swings = ref_layer.get_reference_swings(swings)
        >>>
        >>> # Check invalidation on new bar
        >>> for info in reference_swings:
        ...     result = ref_layer.check_invalidation(info.swing, bar)
        ...     if result.is_invalidated:
        ...         print(f"{info.swing.swing_id} invalidated: {result.reason}")
        >>>
        >>> # Check completion on new bar
        >>> for info in reference_swings:
        ...     result = ref_layer.check_completion(info.swing, bar)
        ...     if result.is_completed:
        ...         print(f"{info.swing.swing_id} completed")
    """

    # Tolerance constants for big swings (Rule 2.2)
    BIG_SWING_TOUCH_TOLERANCE = 0.15
    BIG_SWING_CLOSE_TOLERANCE = 0.10

    def __init__(self, config: SwingConfig = None):
        """
        Initialize the Reference layer.

        Args:
            config: SwingConfig with thresholds. If None, uses defaults.
        """
        self.config = config or SwingConfig.default()
        self._swing_info: Dict[str, ReferenceSwingInfo] = {}

    def _is_big_swing(self, swing: SwingNode) -> bool:
        """
        Check if a swing is a "big swing" (root level, no parents).

        Args:
            swing: The SwingNode to check.

        Returns:
            True if swing has no parents, False otherwise.
        """
        return len(swing.parents) == 0

    def _compute_tolerances(self, swing: SwingNode) -> Tuple[float, float]:
        """
        Compute invalidation tolerances for a swing.

        Big swings (no parent): Full tolerance (0.15 touch, 0.10 close)
        Small swings (has parent): Zero tolerance

        Args:
            swing: The SwingNode to compute tolerances for.

        Returns:
            Tuple of (touch_tolerance, close_tolerance).
        """
        if self._is_big_swing(swing):
            return self.BIG_SWING_TOUCH_TOLERANCE, self.BIG_SWING_CLOSE_TOLERANCE
        else:
            return 0.0, 0.0

    def get_reference_swings(
        self,
        swings: List[SwingNode],
    ) -> List[ReferenceSwingInfo]:
        """
        Get all swings with reference layer annotations.

        Computes tolerances for each swing based on hierarchy.

        Args:
            swings: List of SwingNode from the DAG.

        Returns:
            List of ReferenceSwingInfo with tolerances computed.
        """
        if not swings:
            self._swing_info = {}
            return []

        result = {}
        for swing in swings:
            touch_tol, close_tol = self._compute_tolerances(swing)

            info = ReferenceSwingInfo(
                swing=swing,
                touch_tolerance=touch_tol,
                close_tolerance=close_tol,
                is_reference=True,
            )
            result[swing.swing_id] = info

        self._swing_info = result

        return [
            info for info in self._swing_info.values()
            if info.is_reference
        ]

    def check_invalidation(
        self,
        swing: SwingNode,
        bar: Bar,
        use_close: bool = True,
    ) -> InvalidationResult:
        """
        Check if a swing should be invalidated by this bar (Rule 2.2).

        Applies differentiated invalidation based on hierarchy:
        - Big swings (no parent): touch tolerance 0.15, close tolerance 0.10
        - Small swings (has parent): no tolerance (any violation invalidates)

        Args:
            swing: The swing to check.
            bar: Current bar with high, low, close prices.
            use_close: Whether to also check close-based invalidation.
                If False, only touch (wick) violations are checked.

        Returns:
            InvalidationResult with invalidation status and details.
        """
        # Get or compute tolerances
        info = self._swing_info.get(swing.swing_id)
        if info is None:
            touch_tolerance, close_tolerance = self._compute_tolerances(swing)
        else:
            touch_tolerance = info.touch_tolerance
            close_tolerance = info.close_tolerance

        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))
        bar_close = Decimal(str(bar.close))

        # Create reference frame for ratio calculations
        frame = ReferenceFrame(
            anchor0=swing.defended_pivot,
            anchor1=swing.origin,
            direction="BULL" if swing.is_bull else "BEAR",
        )

        # Touch price (wick extreme)
        touch_price = bar_low if swing.is_bull else bar_high

        # Check touch (wick) violation first
        if frame.is_violated(touch_price, touch_tolerance):
            excess = abs(touch_price - swing.defended_pivot)
            return InvalidationResult(
                is_invalidated=True,
                reason="touch_violation",
                violation_price=touch_price,
                excess=excess,
            )

        # Check close violation (stricter threshold)
        if use_close and frame.is_violated(bar_close, close_tolerance):
            excess = abs(bar_close - swing.defended_pivot)
            return InvalidationResult(
                is_invalidated=True,
                reason="close_violation",
                violation_price=bar_close,
                excess=excess,
            )

        return InvalidationResult(is_invalidated=False)

    def check_completion(
        self,
        swing: SwingNode,
        bar: Bar,
    ) -> CompletionResult:
        """
        Check if a swing should be marked as completed.

        Completion rules (hierarchy-based):
        - Small swings (has parent): Complete at 2× extension
        - Big swings (no parent): Never complete — keep active indefinitely

        Args:
            swing: The swing to check.
            bar: Current bar with high, low, close prices.

        Returns:
            CompletionResult with completion status and details.
        """
        # Big swings never complete
        if self._is_big_swing(swing):
            return CompletionResult(is_completed=False)

        # Small swings complete at 2×
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))

        # Create reference frame
        frame = ReferenceFrame(
            anchor0=swing.defended_pivot,
            anchor1=swing.origin,
            direction="BULL" if swing.is_bull else "BEAR",
        )

        # Check completion at 2.0
        completion_price = bar_high if swing.is_bull else bar_low
        if frame.is_completed(completion_price):
            return CompletionResult(
                is_completed=True,
                reason="reached_2x_extension",
                completion_price=completion_price,
            )

        return CompletionResult(is_completed=False)

    def get_swing_info(self, swing_id: str) -> Optional[ReferenceSwingInfo]:
        """
        Get classification info for a specific swing.

        Args:
            swing_id: The swing's unique identifier.

        Returns:
            ReferenceSwingInfo if swing has been processed, None otherwise.
        """
        return self._swing_info.get(swing_id)

    def get_big_swings(self, swings: List[SwingNode]) -> List[SwingNode]:
        """
        Get only the "big swings" (root level, no parents).

        Args:
            swings: List of SwingNode from the DAG.

        Returns:
            List of SwingNode that have no parents.
        """
        return [s for s in swings if self._is_big_swing(s)]

    def update_invalidation_on_bar(
        self,
        swings: List[SwingNode],
        bar: Bar,
    ) -> List[Tuple[SwingNode, InvalidationResult]]:
        """
        Check all swings for invalidation on a new bar.

        Convenience method that applies check_invalidation to all swings
        and returns those that were invalidated.

        Args:
            swings: List of SwingNode to check.
            bar: Current bar.

        Returns:
            List of (swing, result) tuples for invalidated swings.
        """
        # Ensure info is current
        self.get_reference_swings(swings)

        invalidated = []
        for swing in swings:
            if swing.status != "active":
                continue

            result = self.check_invalidation(swing, bar)
            if result.is_invalidated:
                invalidated.append((swing, result))

        return invalidated

    def update_completion_on_bar(
        self,
        swings: List[SwingNode],
        bar: Bar,
    ) -> List[Tuple[SwingNode, CompletionResult]]:
        """
        Check all swings for completion on a new bar.

        Convenience method that applies check_completion to all swings
        and returns those that were completed.

        Args:
            swings: List of SwingNode to check.
            bar: Current bar.

        Returns:
            List of (swing, result) tuples for completed swings.
        """
        # Ensure info is current
        self.get_reference_swings(swings)

        completed = []
        for swing in swings:
            if swing.status != "active":
                continue

            result = self.check_completion(swing, bar)
            if result.is_completed:
                completed.append((swing, result))

        return completed
