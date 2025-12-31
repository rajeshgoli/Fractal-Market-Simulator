"""
Reference Layer for Swing Filtering and Invalidation

Post-processes DAG output to produce "useful" trading references.
The DAG tracks structural extremas; the Reference layer applies semantic
rules from Docs/Reference/valid_swings.md.

Key responsibilities:
1. Differentiated invalidation (big swings get tolerance, small swings don't)
2. Completion checking (small swings complete at 2×, big swings never complete)

Big vs Small definition (range-based per valid_swings.md Rule 2.2):
- Big swing = top 10% by range (historically called XL)
- Small swing = all other swings

Design: Option A (post-filter DAG output) per DAG spec.
- DAG produces all swings with uniform 0.382 invalidation
- Reference layer filters/annotates with semantic rules
- Clean separation, DAG stays simple

See Docs/Reference/valid_swings.md for the canonical rules.
"""

import bisect
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Dict, Tuple

from .swing_config import SwingConfig
from .swing_node import SwingNode
from .reference_frame import ReferenceFrame
from .reference_config import ReferenceConfig
from .types import Bar
from .dag.leg import Leg


@dataclass
class ReferenceSwing:
    """
    A DAG leg that qualifies as a valid trading reference.

    This is the primary output of the Reference Layer. Each ReferenceSwing
    wraps a Leg from the DAG with reference-layer specific annotations.

    The Reference Layer filters DAG legs through formation, location, and
    breach checks, then annotates qualifying legs with scale and salience.

    Attributes:
        leg: The underlying DAG leg (not a copy).
        scale: Size classification ('S', 'M', 'L', or 'XL') based on
            range percentile within historical population.
        depth: Hierarchy depth from DAG (0 = root, 1+ = nested).
            Used for A/B testing scale vs hierarchy classification.
        location: Current price position in reference frame (0-2 range).
            0 = at defended pivot, 1 = at origin, 2 = at completion target.
            Capped at 2.0 in output per spec.
        salience_score: Relevance ranking (higher = more relevant).
            Computed from range, impulse, and recency with scale-dependent
            weights.

    Example:
        >>> from swing_analysis.reference_layer import ReferenceSwing
        >>> from swing_analysis.dag.leg import Leg
        >>> from decimal import Decimal
        >>>
        >>> leg = Leg(
        ...     direction='bear',
        ...     origin_price=Decimal("110"),
        ...     origin_index=100,
        ...     pivot_price=Decimal("100"),
        ...     pivot_index=105,
        ... )
        >>> ref = ReferenceSwing(
        ...     leg=leg,
        ...     scale='L',
        ...     depth=0,
        ...     location=0.382,
        ...     salience_score=0.75,
        ... )
        >>> ref.scale
        'L'
        >>> ref.location
        0.382
    """
    leg: Leg                      # The underlying DAG leg
    scale: str                    # 'S' | 'M' | 'L' | 'XL' (percentile-based)
    depth: int                    # Hierarchy depth from DAG (for A/B testing)
    location: float               # Current price in reference frame (0-2 range, capped)
    salience_score: float         # Higher = more relevant reference


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
        Check if this is a big swing.

        Note: This is set during get_reference_swings() based on range-based
        definition (top 10% by range per valid_swings.md Rule 2.2).

        Returns:
            True if swing is in top 10% by range, False otherwise.
        """
        # This is computed by ReferenceLayer and stored in tolerances
        # A swing is big if it has non-zero tolerance
        return self.touch_tolerance > 0


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
    produced by the DAG (LegDetector). It does not modify the
    DAG's internal state — it operates on snapshots of DAG output.

    Key operations:
    1. get_reference_swings(): Get all swings with tolerances computed
    2. check_invalidation(): Apply Rule 2.2 with touch/close thresholds
    3. check_completion(): Apply completion rules (2× for small, never for big)

    Big vs Small (range-based definition per valid_swings.md Rule 2.2):
    - Big swing = top 10% by range (historically called XL)
    - Small swing = all other swings

    Invalidation tolerances (Rule 2.2):
    - Small swings: No tolerance — any violation invalidates
    - Big swings: 0.15 touch tolerance, 0.10 close tolerance

    Completion rules:
    - Small swings: Complete at 2× extension
    - Big swings: Never complete — keep active indefinitely

    Example:
        >>> from swing_analysis.reference_layer import ReferenceLayer
        >>> from swing_analysis.dag import calibrate
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

    # Big swing threshold (top X% by range)
    BIG_SWING_PERCENTILE = 0.10  # Top 10%

    def __init__(
        self,
        config: SwingConfig = None,
        reference_config: ReferenceConfig = None,
    ):
        """
        Initialize the Reference layer.

        Args:
            config: SwingConfig with thresholds. If None, uses defaults.
            reference_config: ReferenceConfig for scale classification and
                salience computation. If None, uses defaults.
        """
        self.config = config or SwingConfig.default()
        self.reference_config = reference_config or ReferenceConfig.default()
        self._swing_info: Dict[str, ReferenceSwingInfo] = {}
        self._big_swing_threshold: Optional[Decimal] = None
        # Range distribution for scale classification (sorted for O(log n) percentile)
        # All-time distribution; DAG pruning handles recency per spec
        self._range_distribution: List[Decimal] = []

    def _compute_big_swing_threshold(self, swings: List[SwingNode]) -> Decimal:
        """
        Compute the range threshold for big swing classification.

        Big swings are those in the top 10% by range per valid_swings.md Rule 2.2.

        Args:
            swings: List of SwingNode to compute threshold from.

        Returns:
            The minimum range for a swing to be considered "big".
        """
        if not swings:
            return Decimal("0")

        ranges = sorted([s.range for s in swings], reverse=True)
        cutoff_idx = max(0, int(len(ranges) * self.BIG_SWING_PERCENTILE) - 1)

        if cutoff_idx >= len(ranges):
            return ranges[-1] if ranges else Decimal("0")

        return ranges[cutoff_idx]

    def _is_big_swing(self, swing: SwingNode) -> bool:
        """
        Check if a swing is a "big swing" (top 10% by range).

        Per valid_swings.md Rule 2.2: Big swings are those whose range is
        in the top 10% of all reference swings (historically called XL).

        Note: _big_swing_threshold must be computed first via get_reference_swings().

        Args:
            swing: The SwingNode to check.

        Returns:
            True if swing's range >= big swing threshold, False otherwise.
        """
        if self._big_swing_threshold is None:
            return False
        return swing.range >= self._big_swing_threshold

    def _compute_tolerances(self, swing: SwingNode) -> Tuple[float, float]:
        """
        Compute invalidation tolerances for a swing.

        Big swings (top 10% by range): Full tolerance (0.15 touch, 0.10 close)
        Small swings: Zero tolerance

        Args:
            swing: The SwingNode to compute tolerances for.

        Returns:
            Tuple of (touch_tolerance, close_tolerance).
        """
        if self._is_big_swing(swing):
            return self.BIG_SWING_TOUCH_TOLERANCE, self.BIG_SWING_CLOSE_TOLERANCE
        else:
            return 0.0, 0.0

    def _compute_percentile(self, leg_range: Decimal) -> float:
        """
        Compute percentile rank of leg_range in the range distribution.

        Uses bisect for O(log n) lookup in the sorted distribution.
        The percentile indicates what fraction of historical ranges are
        smaller than the given range.

        Args:
            leg_range: Absolute range of the leg to classify.

        Returns:
            Percentile value from 0 to 100. Returns 50.0 if distribution
            is empty (default to middle).

        Example:
            >>> ref_layer._range_distribution = [Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")]
            >>> ref_layer._compute_percentile(Decimal("12"))  # 2 of 4 are below
            50.0
        """
        if not self._range_distribution:
            return 50.0  # Default to middle

        # Use bisect_left for count of values strictly less than leg_range
        count_below = bisect.bisect_left(self._range_distribution, leg_range)
        return (count_below / len(self._range_distribution)) * 100

    def _classify_scale(self, leg_range: Decimal) -> str:
        """
        Classify leg into S/M/L/XL based on range percentile.

        Scale thresholds from ReferenceConfig:
        - XL: Top 10% (percentile >= 90)
        - L:  60-90% (percentile >= 60)
        - M:  30-60% (percentile >= 30)
        - S:  Bottom 30% (percentile < 30)

        Args:
            leg_range: Absolute range of the leg to classify.

        Returns:
            Scale string: 'S', 'M', 'L', or 'XL'.

        Example:
            >>> config = ReferenceConfig.default()
            >>> ref_layer = ReferenceLayer(reference_config=config)
            >>> # After populating _range_distribution with 100 values...
            >>> ref_layer._classify_scale(Decimal("95"))  # Top 10%
            'XL'
        """
        percentile = self._compute_percentile(leg_range)

        # Convert threshold ratios to percentiles (e.g., 0.90 -> 90.0)
        xl_pct = self.reference_config.xl_threshold * 100
        l_pct = self.reference_config.l_threshold * 100
        m_pct = self.reference_config.m_threshold * 100

        if percentile >= xl_pct:
            return 'XL'
        elif percentile >= l_pct:
            return 'L'
        elif percentile >= m_pct:
            return 'M'
        else:
            return 'S'

    def _add_to_range_distribution(self, leg_range: Decimal) -> None:
        """
        Add a leg range to the sorted distribution.

        Uses bisect.insort for O(log n) insertion while maintaining sorted order.
        The distribution is all-time; DAG pruning handles recency per spec.

        Args:
            leg_range: Absolute range of the leg to add.
        """
        bisect.insort(self._range_distribution, leg_range)

    def get_reference_swings(
        self,
        swings: List[SwingNode],
    ) -> List[ReferenceSwingInfo]:
        """
        Get all swings with reference layer annotations.

        Computes tolerances for each swing based on range-based big swing
        classification per valid_swings.md Rule 2.2.

        Args:
            swings: List of SwingNode from the DAG.

        Returns:
            List of ReferenceSwingInfo with tolerances computed.
        """
        if not swings:
            self._swing_info = {}
            self._big_swing_threshold = None
            return []

        # Compute big swing threshold FIRST (top 10% by range)
        self._big_swing_threshold = self._compute_big_swing_threshold(swings)

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

        Applies differentiated invalidation based on range:
        - Big swings (top 10% by range): touch tolerance 0.15, close tolerance 0.10
        - Small swings: no tolerance (any violation invalidates)

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

        Completion rules (range-based per valid_swings.md):
        - Small swings: Complete at 2× extension
        - Big swings (top 10% by range): Never complete — keep active indefinitely

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
        Get only the "big swings" (top 10% by range).

        Per valid_swings.md Rule 2.2: Big swings are those whose range is
        in the top 10% of all reference swings (historically called XL).

        Note: Threshold is computed from the provided swings list.

        Args:
            swings: List of SwingNode from the DAG.

        Returns:
            List of SwingNode in top 10% by range.
        """
        # Ensure threshold is computed
        if self._big_swing_threshold is None:
            self._big_swing_threshold = self._compute_big_swing_threshold(swings)

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
