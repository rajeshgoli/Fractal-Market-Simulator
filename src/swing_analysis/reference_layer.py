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
        >>> # Get legs from DAG
        >>> detector, events = calibrate(bars)
        >>> legs = detector.state.active_legs
        >>>
        >>> # Apply reference layer filters
        >>> config = SwingConfig.default()
        >>> ref_layer = ReferenceLayer(config)
        >>>
        >>> # Update on each bar
        >>> state = ref_layer.update(legs, bar)
        >>> for ref in state.references:
        ...     print(f"{ref.leg.leg_id}: scale={ref.scale}, salience={ref.salience_score:.2f}")
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
            # Add to range distribution on first formation (#372)
            if leg.leg_id not in self._seen_leg_ids:
                self._seen_leg_ids.add(leg.leg_id)
                self._add_to_range_distribution(leg.range)
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

    def get_active_levels(self, state: ReferenceState) -> Dict[float, List[LevelInfo]]:
        """
        Get key price levels from all valid references.

        Returns dict keyed by fib ratio with LevelInfo including source reference.
        Used for level visualization and confluence detection.

        Args:
            state: ReferenceState from update() containing valid references.

        Returns:
            Dict mapping fib ratio to list of LevelInfo for that ratio.
            Each LevelInfo contains the price, ratio, and source reference.

        Example:
            >>> state = ref_layer.update(legs, bar)
            >>> levels = ref_layer.get_active_levels(state)
            >>> levels[0.382]  # All 38.2% levels from valid references
            [LevelInfo(price=4105.0, ratio=0.382, reference=ref1), ...]
        """
        levels: Dict[float, List[LevelInfo]] = {}
        ratios = [0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2]

        for ref in state.references:
            frame = ReferenceFrame(
                anchor0=ref.leg.pivot_price,
                anchor1=ref.leg.origin_price,
                direction="BULL" if ref.leg.direction == 'bear' else "BEAR"
            )
            for ratio in ratios:
                price = float(frame.get_fib_price(ratio))
                if ratio not in levels:
                    levels[ratio] = []
                levels[ratio].append(LevelInfo(
                    price=price,
                    ratio=ratio,
                    reference=ref,
                ))

        return levels

    def add_crossing_tracking(self, leg_id: str) -> None:
        """
        Add a leg to level crossing monitoring.

        When a leg is tracked, level crossing events can be detected
        for that specific leg. Use remove_crossing_tracking() to stop.

        Args:
            leg_id: The leg_id to start tracking.
        """
        self._tracked_for_crossing.add(leg_id)

    def remove_crossing_tracking(self, leg_id: str) -> None:
        """
        Remove a leg from level crossing monitoring.

        Args:
            leg_id: The leg_id to stop tracking.
        """
        self._tracked_for_crossing.discard(leg_id)

    def is_tracked_for_crossing(self, leg_id: str) -> bool:
        """
        Check if a leg is being tracked for level crossings.

        Args:
            leg_id: The leg_id to check.

        Returns:
            True if the leg is currently tracked.
        """
        return leg_id in self._tracked_for_crossing

    def get_tracked_leg_ids(self) -> Set[str]:
        """
        Get all leg IDs currently being tracked for level crossings.

        Returns:
            Set of leg_ids that are tracked.
        """
        return self._tracked_for_crossing.copy()

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

        # Check formation for all legs first (this updates range distribution
        # for newly formed legs, which affects cold start progress)
        for leg in legs:
            self._is_formed_for_reference(leg, current_price)

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

            # Formation check (already computed above, just checking membership)
            if leg.leg_id not in self._formed_refs:
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
