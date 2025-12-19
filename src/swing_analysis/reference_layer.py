"""
Reference Layer for Swing Filtering and Invalidation

Post-processes DAG output to produce "useful" trading references.
The DAG tracks structural extremas; the Reference layer applies semantic
rules from Docs/Reference/valid_swings.md.

Key responsibilities:
1. Separation filtering (Rules 4.1, 4.2)
2. Big swing classification (top 10% by range)
3. Differentiated invalidation (big swings get tolerance, small swings don't)

Design: Option A (post-filter DAG output) per DAG spec.
- DAG produces all swings
- Reference layer filters/annotates
- Clean separation, DAG stays simple

See Docs/Reference/valid_swings.md for the canonical rules.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Set, Dict, Tuple

from .swing_config import SwingConfig, DirectionConfig
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
        is_big: Whether this is a "big swing" (top 10% by range).
        touch_tolerance: Invalidation tolerance for touch (wick) violations.
        close_tolerance: Invalidation tolerance for close violations.
        is_reference: Whether this swing passes all filters to be a trading reference.
        filter_reason: If not a reference, why it was filtered out.
    """
    swing: SwingNode
    is_big: bool = False
    touch_tolerance: float = 0.0
    close_tolerance: float = 0.0
    is_reference: bool = True
    filter_reason: Optional[str] = None


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


class ReferenceLayer:
    """
    Filters and annotates DAG output to produce trading references.

    The Reference layer applies semantic rules to the structural swings
    produced by the DAG (HierarchicalDetector). It does not modify the
    DAG's internal state — it operates on snapshots of DAG output.

    Key operations:
    1. classify_swings(): Compute big/small classification, set tolerances
    2. filter_by_separation(): Apply Rules 4.1 and 4.2
    3. check_invalidation(): Apply Rule 2.2 with touch/close thresholds
    4. get_reference_swings(): Get all swings that pass filters

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
        >>> for swing in reference_swings:
        ...     result = ref_layer.check_invalidation(swing, bar)
        ...     if result.is_invalidated:
        ...         print(f"{swing.swing_id} invalidated: {result.reason}")
    """

    def __init__(self, config: SwingConfig = None):
        """
        Initialize the Reference layer.

        Args:
            config: SwingConfig with thresholds. If None, uses defaults.
        """
        self.config = config or SwingConfig.default()
        self._classified_swings: Dict[str, ReferenceSwingInfo] = {}
        self._big_swing_threshold: Optional[Decimal] = None

    def classify_swings(self, swings: List[SwingNode]) -> Dict[str, ReferenceSwingInfo]:
        """
        Classify swings and compute their tolerances.

        Determines which swings are "big" (top 10% by range) and sets
        appropriate invalidation tolerances based on Rule 2.2.

        Big swing tolerances:
        - Touch (wick) violation: 0.15 × range
        - Close violation: 0.10 × range

        Small swing tolerances:
        - Touch: 0 (any violation invalidates)
        - Close: 0 (any violation invalidates)

        Args:
            swings: List of SwingNode from the DAG.

        Returns:
            Dict mapping swing_id to ReferenceSwingInfo with classifications.
        """
        if not swings:
            self._classified_swings = {}
            self._big_swing_threshold = None
            return {}

        # Compute big swing threshold (top 10% by range)
        # "Top 10%" means the count of big swings is 10% of total
        # For 10 swings: 1 is big. For 100 swings: 10 are big.
        ranges = sorted([s.range for s in swings], reverse=True)
        num_big = max(1, int(len(ranges) * 0.10 + 0.5))  # Round to nearest, min 1
        if num_big > len(ranges):
            num_big = len(ranges)
        # Threshold is the range of the smallest "big" swing
        self._big_swing_threshold = ranges[num_big - 1]

        # First pass: identify big swings
        big_swing_ids = set()
        for swing in swings:
            if swing.range >= self._big_swing_threshold:
                big_swing_ids.add(swing.swing_id)

        # Second pass: set tolerances (now we know which are big)
        result = {}
        for swing in swings:
            is_big = swing.swing_id in big_swing_ids

            # Get direction-specific config
            dir_config = self.config.bull if swing.is_bull else self.config.bear

            if is_big:
                touch_tolerance = dir_config.big_swing_price_tolerance
                close_tolerance = dir_config.big_swing_close_tolerance
            else:
                # Check if child of big swing
                has_big_parent = self._has_big_parent_in_set(swing, big_swing_ids)
                if has_big_parent:
                    touch_tolerance = dir_config.child_swing_tolerance
                    close_tolerance = dir_config.child_swing_tolerance
                else:
                    touch_tolerance = 0.0
                    close_tolerance = 0.0

            info = ReferenceSwingInfo(
                swing=swing,
                is_big=is_big,
                touch_tolerance=touch_tolerance,
                close_tolerance=close_tolerance,
                is_reference=True,
            )
            result[swing.swing_id] = info

        self._classified_swings = result
        return result

    def _has_big_parent(self, swing: SwingNode) -> bool:
        """Check if swing has a big parent within 2 levels."""
        for parent in swing.parents:
            if parent.swing_id in self._classified_swings:
                if self._classified_swings[parent.swing_id].is_big:
                    return True
            # Check grandparents
            for grandparent in parent.parents:
                if grandparent.swing_id in self._classified_swings:
                    if self._classified_swings[grandparent.swing_id].is_big:
                        return True
        return False

    def _has_big_parent_in_set(self, swing: SwingNode, big_swing_ids: set) -> bool:
        """Check if swing has a big parent within 2 levels using precomputed set."""
        for parent in swing.parents:
            if parent.swing_id in big_swing_ids:
                return True
            # Check grandparents
            for grandparent in parent.parents:
                if grandparent.swing_id in big_swing_ids:
                    return True
        return False

    def filter_by_separation(
        self,
        swings: List[SwingNode],
        parent_separation_fib: float = 0.1,
    ) -> List[ReferenceSwingInfo]:
        """
        Apply separation filtering (Rules 4.1 and 4.2).

        Rule 4.1 (Self-separation): Origin must be at least 0.1 × range
        away from other candidate origins.

        Rule 4.2 (Parent-child separation): Child's endpoints must be
        at least 0.1 × parent range away from:
        - Parent's 0 and 1
        - Any sibling's 0 and 1

        Args:
            swings: List of SwingNode from the DAG.
            parent_separation_fib: Minimum separation as fraction of parent range.
                Default 0.1 per valid_swings.md Rule 4.2.

        Returns:
            List of ReferenceSwingInfo that pass separation filters.
        """
        # First classify if not already done
        if not self._classified_swings:
            self.classify_swings(swings)

        filtered = []
        for swing in swings:
            info = self._classified_swings.get(swing.swing_id)
            if info is None:
                continue

            # Check parent-child separation (Rule 4.2)
            passes_separation = self._check_parent_child_separation(
                swing, parent_separation_fib
            )

            if not passes_separation:
                info.is_reference = False
                info.filter_reason = "parent_child_separation"
            else:
                filtered.append(info)

        return filtered

    def _check_parent_child_separation(
        self,
        swing: SwingNode,
        min_fib: float = 0.1,
    ) -> bool:
        """
        Check Rule 4.2: Parent-child separation.

        Child swing's 0 or 1 must be at least min_fib × parent range away from:
        - Parent's 0 and 1
        - Any sibling swing's 0 and 1

        Args:
            swing: The child swing to check.
            min_fib: Minimum separation as fraction of parent range.

        Returns:
            True if separation is sufficient, False otherwise.
        """
        for parent in swing.parents:
            parent_range = parent.range
            min_separation = Decimal(str(min_fib)) * parent_range

            # Check separation from parent's endpoints
            child_points = [swing.defended_pivot, swing.origin]
            parent_points = [parent.defended_pivot, parent.origin]

            for child_pt in child_points:
                for parent_pt in parent_points:
                    if abs(child_pt - parent_pt) < min_separation:
                        return False

            # Check separation from siblings
            for sibling in parent.children:
                if sibling.swing_id == swing.swing_id:
                    continue
                if sibling.direction != swing.direction:
                    continue

                sibling_points = [sibling.defended_pivot, sibling.origin]
                for child_pt in child_points:
                    for sib_pt in sibling_points:
                        if abs(child_pt - sib_pt) < min_separation:
                            return False

        return True

    def check_invalidation(
        self,
        swing: SwingNode,
        bar: Bar,
        use_close: bool = True,
    ) -> InvalidationResult:
        """
        Check if a swing should be invalidated by this bar (Rule 2.2).

        Applies differentiated invalidation based on swing size:
        - Big swings: touch tolerance 0.15, close tolerance 0.10
        - Small swings: no tolerance (any violation invalidates)

        Args:
            swing: The swing to check.
            bar: Current bar with high, low, close prices.
            use_close: Whether to also check close-based invalidation.
                If False, only touch (wick) violations are checked.

        Returns:
            InvalidationResult with invalidation status and details.
        """
        # Get classification info
        info = self._classified_swings.get(swing.swing_id)
        if info is None:
            # Not classified yet, use default (no tolerance)
            touch_tolerance = 0.0
            close_tolerance = 0.0
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

    def get_reference_swings(
        self,
        swings: List[SwingNode],
        apply_separation: bool = True,
    ) -> List[ReferenceSwingInfo]:
        """
        Get all swings that pass reference layer filters.

        This is the main entry point for filtering DAG output.
        Applies classification and optionally separation filtering.

        Args:
            swings: List of SwingNode from the DAG.
            apply_separation: Whether to apply parent-child separation filter.

        Returns:
            List of ReferenceSwingInfo that pass all filters.
        """
        # Classify all swings
        self.classify_swings(swings)

        if apply_separation:
            return self.filter_by_separation(swings)
        else:
            # Return all classified swings marked as reference
            return [
                info for info in self._classified_swings.values()
                if info.is_reference
            ]

    def get_swing_info(self, swing_id: str) -> Optional[ReferenceSwingInfo]:
        """
        Get classification info for a specific swing.

        Args:
            swing_id: The swing's unique identifier.

        Returns:
            ReferenceSwingInfo if swing has been classified, None otherwise.
        """
        return self._classified_swings.get(swing_id)

    def get_big_swings(self, swings: List[SwingNode]) -> List[SwingNode]:
        """
        Get only the "big swings" (top 10% by range).

        Args:
            swings: List of SwingNode from the DAG.

        Returns:
            List of SwingNode that are classified as big.
        """
        self.classify_swings(swings)
        return [
            info.swing for info in self._classified_swings.values()
            if info.is_big
        ]

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
        # Ensure classification is current
        self.classify_swings(swings)

        invalidated = []
        for swing in swings:
            if swing.status != "active":
                continue

            result = self.check_invalidation(swing, bar)
            if result.is_invalidated:
                invalidated.append((swing, result))

        return invalidated
