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
from typing import List, Optional, Dict, Tuple, Set

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
class LevelInfo:
    """
    A fib level with its source reference.

    Used for level-based queries like get_active_levels() and confluence zone
    detection. Each LevelInfo ties a price level back to its source reference
    for attribution.

    Attributes:
        price: The absolute price level.
        ratio: The fib ratio (0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2).
        reference: The ReferenceSwing that produced this level.

    Example:
        >>> level = LevelInfo(price=4105.0, ratio=0.382, reference=ref)
        >>> level.price
        4105.0
    """
    price: float                  # The price level
    ratio: float                  # The fib ratio (0, 0.382, 0.5, etc.)
    reference: 'ReferenceSwing'   # Source reference


@dataclass
class ReferenceState:
    """
    Complete reference layer output for a given bar.

    This is the top-level output of ReferenceLayer.update(). Contains all valid
    references sorted by salience, plus convenience groupings for UI display
    and analysis.

    Attributes:
        references: All valid references, ranked by salience (highest first).
        by_scale: References grouped by S/M/L/XL scale classification.
        by_depth: References grouped by hierarchy depth (0 = root).
        by_direction: References grouped by 'bull' or 'bear'.
        direction_imbalance: 'bull' if bull refs > 2× bear refs,
            'bear' if bear refs > 2× bull refs, None if balanced.

    Design Notes:
        - No internal limit on references (UI can limit display)
        - Grouping dicts are views into the references list (not copies)
        - direction_imbalance highlights when one direction dominates

    Example:
        >>> state = ReferenceState(
        ...     references=[ref1, ref2, ref3],
        ...     by_scale={'L': [ref1], 'M': [ref2, ref3]},
        ...     by_depth={0: [ref1], 1: [ref2, ref3]},
        ...     by_direction={'bull': [ref1, ref2], 'bear': [ref3]},
        ...     direction_imbalance='bull',
        ... )
        >>> len(state.references)
        3
        >>> state.direction_imbalance
        'bull'
    """
    references: List['ReferenceSwing']              # All valid, ranked by salience
    by_scale: Dict[str, List['ReferenceSwing']]     # Grouped by S/M/L/XL
    by_depth: Dict[int, List['ReferenceSwing']]     # Grouped by hierarchy depth
    by_direction: Dict[str, List['ReferenceSwing']] # Grouped by bull/bear
    direction_imbalance: Optional[str]              # 'bull' | 'bear' | None
    is_warming_up: bool = False                      # True if in cold start
    warmup_progress: Tuple[int, int] = (0, 50)       # (current_count, required_count)


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
        # Track which legs have formed as references (price reached formation threshold)
        # Once formed, stays formed until fatally breached
        self._formed_refs: Set[str] = set()
        # Track which legs are monitored for level crossings (opt-in per leg)
        self._tracked_for_crossing: Set[str] = set()
        # Track which leg_ids have been added to range distribution (to avoid duplicates)
        self._seen_leg_ids: Set[str] = set()

    @property
    def is_cold_start(self) -> bool:
        """
        True if not enough data for reliable scale classification.

        During cold start, update() returns an empty ReferenceState because
        scale percentiles are unreliable with insufficient data.

        Returns:
            True if distribution has fewer than min_swings_for_scale legs.
        """
        return len(self._range_distribution) < self.reference_config.min_swings_for_scale

    @property
    def cold_start_progress(self) -> Tuple[int, int]:
        """
        Returns (current_count, required_count) for cold start progress.

        Use this for UI display like "Warming up: 35/50 swings collected".

        Returns:
            Tuple of (current swings in distribution, required minimum).
        """
        return (len(self._range_distribution), self.reference_config.min_swings_for_scale)

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

    def _update_range_distribution(self, legs: List[Leg]) -> None:
        """
        Update range distribution with ranges from formed legs.

        Only includes formed legs (leg.formed == True) to match the
        population used for scale classification. Legs that haven't
        reached 38.2% retracement are not structurally confirmed and
        should not influence percentile boundaries.

        Range distribution is all-time (not windowed). DAG pruning
        naturally handles recency by removing old legs.

        Args:
            legs: List of active legs from the DAG.
        """
        for leg in legs:
            # Only track formed legs for scale classification
            if leg.formed and leg.leg_id not in self._seen_leg_ids:
                self._seen_leg_ids.add(leg.leg_id)
                self._add_to_range_distribution(leg.range)

    def _compute_location(self, leg: Leg, current_price: Decimal) -> float:
        """
        Compute location in reference frame.

        Location tells us where current price sits within the reference frame:
        - 0 = at defended pivot
        - 1 = at origin
        - 2 = at completion target (2x extension)
        - < 0 = pivot breached
        - > 2 = past completion

        For bull reference (bear leg, high→low):
        - Origin = HIGH (where bear move started)
        - Defended pivot = LOW (must hold for bullish setup)
        - 0 = pivot (low), 1 = origin (high), 2 = target below pivot

        For bear reference (bull leg, low→high):
        - Origin = LOW (where bull move started)
        - Defended pivot = HIGH (must hold for bearish setup)
        - 0 = pivot (high), 1 = origin (low), 2 = target above pivot

        Args:
            leg: The leg to compute location for
            current_price: Current price (typically bar close)

        Returns:
            Location as float (NOT capped — capping happens in output)
        """
        frame = ReferenceFrame(
            anchor0=leg.pivot_price,   # defended pivot = 0
            anchor1=leg.origin_price,  # origin = 1
            direction="BULL" if leg.direction == 'bear' else "BEAR"
        )
        return float(frame.ratio(current_price))

    def _is_formed_for_reference(self, leg: Leg, current_price: Decimal) -> bool:
        """
        Check if leg has reached formation threshold.

        Formation is PRICE-BASED, not age-based. A leg becomes a valid reference
        when the subsequent confirming move reaches the formation threshold
        (default 38.2%).

        Example: Bear leg from $110 (origin) to $100 (pivot), range = $10.
        - Formation threshold = 0.382 (38.2%)
        - Price must rise to $103.82 (38.2% retracement from pivot toward origin)
        - At that point, location = 0.382, swing is formed
        - Once formed, stays formed until fatally breached

        Args:
            leg: The leg to check
            current_price: Current price

        Returns:
            True if formed (or was previously formed)
        """
        # Once formed, always formed (until fatal breach removes it)
        if leg.leg_id in self._formed_refs:
            return True

        location = self._compute_location(leg, current_price)
        threshold = self.reference_config.formation_fib_threshold  # 0.382

        # Formation occurs when price retraces TO the threshold
        # Location 0 = pivot, Location 1 = origin
        # For formation, price must move from pivot toward origin by at least threshold
        # This means location must be >= threshold
        if location >= threshold:
            self._formed_refs.add(leg.leg_id)
            return True

        return False

    def _is_fatally_breached(
        self,
        leg: Leg,
        scale: str,
        location: float,
        bar_close_location: float
    ) -> bool:
        """
        Check if reference is fatally breached.

        A reference is fatally breached if ANY of these conditions are met:
        1. Pivot breach: location < 0 (price went past defended pivot)
        2. Completion: location > 2 (price completed 2x target)
        3. Origin breach: Scale-dependent (see below)

        Scale-dependent origin breach (per north star):
        - S/M: Default zero tolerance (configurable via small_origin_tolerance)
        - L/XL: Two thresholds — trade breach (15%) AND close breach (10%)

        Args:
            leg: The leg to check
            scale: Scale classification ('S', 'M', 'L', 'XL')
            location: Current price location in reference frame (from bar high/low)
            bar_close_location: Location of bar close (for L/XL close breach)

        Returns:
            True if fatally breached (should be removed from references)
        """
        # Pivot breach (location < 0)
        if location < 0:
            # Remove from formed refs if present
            self._formed_refs.discard(leg.leg_id)
            return True

        # Past completion (location > 2)
        if location > 2:
            self._formed_refs.discard(leg.leg_id)
            return True

        # Origin breach — scale-dependent per north star
        if scale in ('S', 'M'):
            # S/M: Default zero tolerance (configurable)
            if location > (1.0 + self.reference_config.small_origin_tolerance):
                self._formed_refs.discard(leg.leg_id)
                return True
        else:  # L, XL
            # L/XL: Two thresholds
            # Trade breach: invalidates if price TRADES beyond 15%
            if location > (1.0 + self.reference_config.big_trade_breach_tolerance):
                self._formed_refs.discard(leg.leg_id)
                return True
            # Close breach: invalidates if price CLOSES beyond 10%
            if bar_close_location > (1.0 + self.reference_config.big_close_breach_tolerance):
                self._formed_refs.discard(leg.leg_id)
                return True

        return False

    def _normalize_range(self, leg_range: float) -> float:
        """
        Normalize range to 0-1 based on distribution.

        Args:
            leg_range: Absolute range of the leg

        Returns:
            Normalized score from 0 to 1. Returns 0.5 if distribution is empty.
        """
        if not self._range_distribution:
            return 0.5
        max_range = float(max(self._range_distribution))
        if max_range == 0:
            return 0.5
        return min(leg_range / max_range, 1.0)

    def _compute_salience(self, leg: Leg, scale: str, current_bar_index: int) -> float:
        """
        Compute salience score for ranking references.

        North star: big, impulsive, and early (for large swings)
                    vs recent (for small swings).

        Components:
        1. range_score — Normalized range (0-1)
        2. impulse_score — leg.impulsiveness / 100 (0-1), skip if None
        3. recency_score — 1 / (1 + age/1000) decay function

        Scale-dependent weights:
        - L/XL: range=0.5, impulse=0.4, recency=0.1
        - S/M: range=0.2, impulse=0.3, recency=0.5

        Args:
            leg: The leg to score
            scale: Scale classification
            current_bar_index: Current bar index for recency calculation

        Returns:
            Salience score (higher = more relevant)
        """
        # Range score: normalized against distribution
        range_score = self._normalize_range(float(leg.range))

        # Impulse score: percentile from DAG
        use_impulse = leg.impulsiveness is not None
        impulse_score = leg.impulsiveness / 100 if use_impulse else 0

        # Recency score: fixed decay
        age = current_bar_index - leg.origin_index
        recency_score = 1 / (1 + age / 1000)

        # Scale-dependent weights
        if scale in ('L', 'XL'):
            weights = {
                'range': self.reference_config.big_range_weight,
                'impulse': self.reference_config.big_impulse_weight,
                'recency': self.reference_config.big_recency_weight
            }
        else:
            weights = {
                'range': self.reference_config.small_range_weight,
                'impulse': self.reference_config.small_impulse_weight,
                'recency': self.reference_config.small_recency_weight
            }

        # Normalize weights if impulse is missing
        if not use_impulse:
            total = weights['range'] + weights['recency']
            if total > 0:
                weights['range'] /= total
                weights['recency'] /= total
            weights['impulse'] = 0

        return (weights['range'] * range_score +
                weights['impulse'] * impulse_score +
                weights['recency'] * recency_score)

    def _group_by_scale(
        self,
        refs: List[ReferenceSwing],
    ) -> Dict[str, List[ReferenceSwing]]:
        """
        Group references by scale classification.

        Args:
            refs: List of ReferenceSwing to group.

        Returns:
            Dict mapping scale ('S', 'M', 'L', 'XL') to list of references.
        """
        result: Dict[str, List[ReferenceSwing]] = {'S': [], 'M': [], 'L': [], 'XL': []}
        for r in refs:
            result[r.scale].append(r)
        return result

    def _group_by_depth(
        self,
        refs: List[ReferenceSwing],
    ) -> Dict[int, List[ReferenceSwing]]:
        """
        Group references by hierarchy depth.

        Args:
            refs: List of ReferenceSwing to group.

        Returns:
            Dict mapping depth (0 = root) to list of references.
        """
        result: Dict[int, List[ReferenceSwing]] = {}
        for r in refs:
            if r.depth not in result:
                result[r.depth] = []
            result[r.depth].append(r)
        return result

    def _group_by_direction(
        self,
        refs: List[ReferenceSwing],
    ) -> Dict[str, List[ReferenceSwing]]:
        """
        Group references by direction.

        Args:
            refs: List of ReferenceSwing to group.

        Returns:
            Dict mapping direction ('bull', 'bear') to list of references.
        """
        result: Dict[str, List[ReferenceSwing]] = {'bull': [], 'bear': []}
        for r in refs:
            result[r.leg.direction].append(r)
        return result

    def update(self, legs: List[Leg], bar: Bar) -> ReferenceState:
        """
        Main entry point. Called each bar after DAG processes.

        One bar at a time. No look-ahead. Always assume real-time flow.

        Args:
            legs: Active legs from DAG.
            bar: Current bar with OHLC.

        Returns:
            ReferenceState with all valid references.
        """
        current_price = Decimal(str(bar.close))

        # Update range distribution with any new legs
        self._update_range_distribution(legs)

        # Cold start check: not enough swings for meaningful scale classification
        if self.is_cold_start:
            return ReferenceState(
                references=[],
                by_scale={'S': [], 'M': [], 'L': [], 'XL': []},
                by_depth={},
                by_direction={'bull': [], 'bear': []},
                direction_imbalance=None,
                is_warming_up=True,
                warmup_progress=self.cold_start_progress,
            )

        references: List[ReferenceSwing] = []
        for leg in legs:
            scale = self._classify_scale(leg.range)
            location = self._compute_location(leg, current_price)

            # Formation check (price-based)
            if not self._is_formed_for_reference(leg, current_price):
                continue

            # Compute location from bar extremes for breach check
            # For bull reference (bear leg): defended pivot is LOW, price must stay above
            # For bear reference (bull leg): defended pivot is HIGH, price must stay below
            bar_high = Decimal(str(bar.high))
            bar_low = Decimal(str(bar.low))

            if leg.direction == 'bear':
                # Bull reference: pivot is LOW, use bar_low for max breach check
                extreme_location = self._compute_location(leg, bar_low)
            else:
                # Bear reference: pivot is HIGH, use bar_high for max breach check
                extreme_location = self._compute_location(leg, bar_high)

            bar_close_location = location  # location is already computed from close

            # Validity check (location + tolerance)
            if self._is_fatally_breached(leg, scale, extreme_location, bar_close_location):
                # Already removed from formed refs by _is_fatally_breached
                continue

            salience = self._compute_salience(leg, scale, bar.index)

            references.append(ReferenceSwing(
                leg=leg,
                scale=scale,
                depth=leg.depth,
                location=min(location, 2.0),  # Cap at 2.0
                salience_score=salience,
            ))

        # Sort by salience (descending)
        references.sort(key=lambda r: r.salience_score, reverse=True)

        # Build groupings
        by_scale = self._group_by_scale(references)
        by_depth = self._group_by_depth(references)
        by_direction = self._group_by_direction(references)

        # Compute direction imbalance
        bull_count = len(by_direction.get('bull', []))
        bear_count = len(by_direction.get('bear', []))
        if bull_count > bear_count * 2:
            imbalance: Optional[str] = 'bull'
        elif bear_count > bull_count * 2:
            imbalance = 'bear'
        else:
            imbalance = None

        return ReferenceState(
            references=references,
            by_scale=by_scale,
            by_depth=by_depth,
            by_direction=by_direction,
            direction_imbalance=imbalance,
            is_warming_up=False,
            warmup_progress=self.cold_start_progress,
        )

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
