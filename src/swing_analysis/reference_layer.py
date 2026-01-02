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
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Tuple, Set

from .detection_config import DetectionConfig
from .events import LevelCrossEvent
from .reference_frame import ReferenceFrame
from .reference_config import ReferenceConfig
from .types import Bar
from .dag.leg import Leg
from .dag.range_distribution import RollingBinDistribution


# Standard fib levels used for level crossing detection
STANDARD_FIB_LEVELS = [0.0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0]

# Maximum number of legs that can be tracked for level crossing (performance limit)
MAX_TRACKED_LEGS = 10


class FilterReason(Enum):
    """
    Reason why a leg was filtered from valid references.

    Used by get_all_with_status() to explain why each leg didn't become
    a valid trading reference. VALID indicates the leg passed all filters.

    Filter conditions (evaluated in order):
    1. COLD_START - System warming up (< min_swings_for_scale formed legs)
    2. NOT_FORMED - Price hasn't reached formation threshold (38.2% retracement)
    3. PIVOT_BREACHED - Location < 0 (price past defended pivot)
    4. COMPLETED - Location > 2 (past 2× extension target)
    5. ORIGIN_BREACHED - Scale-dependent tolerance exceeded
       - S/M: 0% (any touch)
       - L/XL: 15% trade breach OR 10% close breach

    Example:
        >>> leg = create_leg(...)
        >>> status = ref_layer.get_all_with_status([leg], bar)[0]
        >>> if status.reason == FilterReason.NOT_FORMED:
        ...     print(f"Needs to reach {status.threshold:.1%} formation")
    """
    VALID = "valid"                   # Leg passes all filters
    COLD_START = "cold_start"         # Not enough data for scale classification
    NOT_FORMED = "not_formed"         # Price hasn't reached formation threshold
    PIVOT_BREACHED = "pivot_breached" # Location < 0 (past defended pivot)
    COMPLETED = "completed"           # Location > 2 (past 2× extension)
    ORIGIN_BREACHED = "origin_breached"  # Scale-dependent tolerance exceeded


@dataclass
class FilteredLeg:
    """
    A DAG leg with its filter status for observability.

    Unlike ReferenceSwing which only contains valid references, FilteredLeg
    wraps ANY active leg with its filter reason. This enables the Reference
    Observation UI to show why each leg was filtered.

    Attributes:
        leg: The underlying DAG leg.
        reason: Why this leg was filtered (or VALID if it passed).
        scale: Size classification ('S', 'M', 'L', 'XL').
        location: Current price position in reference frame (0-2 range).
        threshold: The threshold that was violated (for breach reasons).
            - For NOT_FORMED: formation_fib_threshold (0.382)
            - For ORIGIN_BREACHED: the tolerance exceeded
            - None for other reasons.

    Example:
        >>> status = FilteredLeg(
        ...     leg=leg,
        ...     reason=FilterReason.NOT_FORMED,
        ...     scale='M',
        ...     location=0.28,
        ...     threshold=0.382,
        ... )
        >>> print(f"Leg needs to reach {status.threshold:.1%} (currently at {status.location:.1%})")
        Leg needs to reach 38.2% (currently at 28.0%)
    """
    leg: Leg
    reason: FilterReason
    scale: str                        # 'S' | 'M' | 'L' | 'XL'
    location: float                   # Current price in reference frame
    threshold: Optional[float] = None # Violated threshold (for breach reasons)


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
class ConfluenceZone:
    """
    A cluster of fib levels from different references.

    When levels from multiple references fall within a small tolerance,
    they form a confluence zone - an area of increased significance.

    Attributes:
        center_price: Average price of all levels in the zone.
        min_price: Lowest price level in the zone.
        max_price: Highest price level in the zone.
        levels: List of LevelInfo that form this zone.
        reference_count: Number of unique references contributing.
        reference_ids: Set of leg_ids for participating references.

    Example:
        >>> zone = ConfluenceZone(
        ...     center_price=4150.25,
        ...     min_price=4149.50,
        ...     max_price=4151.00,
        ...     levels=[level1, level2, level3],
        ...     reference_count=3,
        ...     reference_ids={'leg_bear_1', 'leg_bull_2', 'leg_bear_3'},
        ... )
        >>> zone.reference_count
        3
    """
    center_price: float           # Average price of levels in zone
    min_price: float              # Lowest level price
    max_price: float              # Highest level price
    levels: List[LevelInfo]       # Participating levels
    reference_count: int          # Number of unique references
    reference_ids: Set[str]       # Leg IDs of participating references


@dataclass
class LevelTouch:
    """
    Record of a fib level being touched/crossed by price.

    A level is "touched" when price trades at or through it. Used by the
    Structure Panel to track which levels have been tested.

    Attributes:
        level: The LevelInfo that was touched.
        bar_index: Bar index when touch occurred.
        touch_price: The price at which the touch was detected.
        cross_direction: 'up' if price crossed from below, 'down' if from above.
    """
    level: LevelInfo
    bar_index: int
    touch_price: float
    cross_direction: str  # 'up' | 'down'


@dataclass
class StructurePanelData:
    """
    Data for the Structure Panel showing level touch history.

    Three sections per spec:
    1. Touched this session - Historical record of which levels were hit
    2. Currently active - Levels within striking distance of current price
    3. Current bar - Levels touched on most recent bar

    Attributes:
        touched_this_session: All level touches recorded during the session.
        currently_active: Levels within striking distance (configurable threshold).
        current_bar_touches: Levels touched on the most recent bar.
        current_price: Current price for reference.
    """
    touched_this_session: List[LevelTouch]
    currently_active: List[LevelInfo]
    current_bar_touches: List[LevelTouch]
    current_price: float


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
        >>> config = DetectionConfig.default()
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
        config: DetectionConfig = None,
        reference_config: ReferenceConfig = None,
    ):
        """
        Initialize the Reference layer.

        Args:
            config: DetectionConfig with thresholds. If None, uses defaults.
            reference_config: ReferenceConfig for scale classification and
                salience computation. If None, uses defaults.
        """
        self.config = config or DetectionConfig.default()
        self.reference_config = reference_config or ReferenceConfig.default()
        # Range distribution for scale classification (sorted for O(log n) percentile)
        # All-time distribution; DAG pruning handles recency per spec
        self._range_distribution: List[Decimal] = []
        # Median-normalized bin distribution (#434) for O(1) scale classification
        # Uses rolling window with periodic median recomputation
        self._bin_distribution: RollingBinDistribution = RollingBinDistribution(
            window_duration_days=self.reference_config.bin_window_duration_days,
            recompute_interval_legs=self.reference_config.bin_recompute_interval,
        )
        # Track which legs have formed as references (price reached formation threshold)
        # Once formed, stays formed until fatally breached
        self._formed_refs: Set[str] = set()
        # Track which legs are monitored for level crossings (opt-in per leg)
        self._tracked_for_crossing: Set[str] = set()
        # Track last known fib level for each tracked leg (for cross detection)
        self._last_level: Dict[str, float] = {}
        # Track which leg_ids have been added to range distribution (to avoid duplicates)
        self._seen_leg_ids: Set[str] = set()
        # Structure Panel: level touches recorded during the session
        self._session_level_touches: List[LevelTouch] = []
        # Track last known price to detect touch directions
        self._last_price: Optional[float] = None
        # Accumulated level crossing events (cleared after retrieval)
        self._pending_cross_events: List[LevelCrossEvent] = []

    def copy_state_from(self, other: 'ReferenceLayer') -> None:
        """
        Copy accumulated state from another ReferenceLayer instance.

        Used when recreating the reference layer with new config to preserve
        the warmup progress and formed leg tracking. Without this, switching
        views that trigger config sync would reset the warmup count.

        Args:
            other: The ReferenceLayer to copy state from.
        """
        self._range_distribution = other._range_distribution.copy()
        # Copy bin distribution state (#434)
        self._bin_distribution = RollingBinDistribution.from_dict(
            other._bin_distribution.to_dict()
        )
        self._formed_refs = other._formed_refs.copy()
        self._tracked_for_crossing = other._tracked_for_crossing.copy()
        self._last_level = other._last_level.copy()
        self._seen_leg_ids = other._seen_leg_ids.copy()
        self._session_level_touches = other._session_level_touches.copy()
        self._last_price = other._last_price
        self._pending_cross_events = other._pending_cross_events.copy()

    def track_formation(self, legs: List[Leg], bar: Bar) -> None:
        """
        Lightweight formation tracking for per-bar updates during DAG advances.

        This method checks formation status for all legs and updates the range
        distribution without computing the full ReferenceState. Call this on
        every bar during playback to ensure formation tracking stays current.

        After #394, formation tracking moved from DAG layer to Reference layer.
        Without per-bar tracking, the reference layer only sees legs when
        update() is called (in Levels at Play view), missing many legs that
        formed and got pruned while in DAG view.

        Also updates bin distribution for formed legs' extended ranges (#434).

        Args:
            legs: Active legs from DAG.
            bar: Current bar with OHLC.
        """
        current_price = Decimal(str(bar.close))
        timestamp = bar.timestamp if bar.timestamp else 0.0
        for leg in legs:
            was_already_formed = leg.leg_id in self._formed_refs
            self._is_formed_for_reference(leg, current_price, timestamp)
            # Update bin distribution on pivot extension for already-formed legs (#434)
            if was_already_formed and leg.leg_id in self._seen_leg_ids:
                self._update_bin_distribution(leg.leg_id, float(leg.range))

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
        Classify leg into S/M/L/XL based on range percentile or bin distribution.

        When use_bin_distribution is enabled (#434), uses median-normalized bins:
        - Bins 0-7 (< 5× median) → S
        - Bin 8 (5-10× median) → M
        - Bin 9 (10-25× median) → L
        - Bin 10 (25×+ median) → XL

        When disabled, uses percentile-based thresholds from ReferenceConfig:
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
            >>> # After populating distribution with 100 values...
            >>> ref_layer._classify_scale(Decimal("95"))  # Top 10%
            'XL'
        """
        # Use bin distribution if enabled (#434)
        if self.reference_config.use_bin_distribution:
            return self._bin_distribution.get_scale(float(leg_range))

        # Legacy percentile-based classification
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

    def _add_to_range_distribution(
        self,
        leg_range: Decimal,
        leg_id: str = "",
        timestamp: float = 0.0,
    ) -> None:
        """
        Add a leg range to the distribution.

        For legacy sorted list: Uses bisect.insort for O(log n) insertion.
        For bin distribution (#434): Uses O(1) bin count update.

        The distribution is all-time; DAG pruning handles recency per spec.

        Args:
            leg_range: Absolute range of the leg to add.
            leg_id: Unique leg identifier (for bin distribution tracking).
            timestamp: Leg creation timestamp (for bin distribution window).
        """
        # Legacy sorted list (always maintained for backwards compatibility)
        bisect.insort(self._range_distribution, leg_range)

        # Bin distribution (#434)
        if self.reference_config.use_bin_distribution and leg_id:
            self._bin_distribution.add_leg(leg_id, float(leg_range), timestamp)

    def _update_bin_distribution(self, leg_id: str, new_range: float) -> None:
        """
        Update a leg's range in the bin distribution when pivot extends (#434).

        O(1) operation: decrement old bin, increment new bin.

        Args:
            leg_id: Unique leg identifier.
            new_range: New range value after pivot extension.
        """
        if self.reference_config.use_bin_distribution:
            self._bin_distribution.update_leg(leg_id, new_range)

    def _remove_from_bin_distribution(self, leg_id: str) -> None:
        """
        Remove a leg from the bin distribution (#434).

        Called when a leg is pruned.

        Args:
            leg_id: Unique leg identifier.
        """
        if self.reference_config.use_bin_distribution:
            self._bin_distribution.remove_leg(leg_id)

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

    def _is_formed_for_reference(
        self,
        leg: Leg,
        current_price: Decimal,
        timestamp: float = 0.0,
    ) -> bool:
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
            timestamp: Bar timestamp for bin distribution tracking (#434)

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
                self._add_to_range_distribution(leg.range, leg.leg_id, timestamp)
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

        Two modes:
        1. Combine mode (range_counter_weight == 0): Weighted sum of range, impulse, recency
        2. Standalone mode (range_counter_weight > 0): Range × Counter (structural importance)

        Combine mode weights (scale-dependent):
        - L/XL: range=0.5, impulse=0.4, recency=0.1
        - S/M: range=0.2, impulse=0.3, recency=0.5

        Standalone mode: range × origin_counter_trend_range
        - Measures structural importance: how big is the leg × how big was the counter-trend
        - Larger legs that survived larger counter-trends score higher

        Args:
            leg: The leg to score
            scale: Scale classification
            current_bar_index: Current bar index for recency calculation

        Returns:
            Salience score (higher = more relevant)
        """
        # Check for Range×Counter standalone mode
        if self.reference_config.range_counter_weight > 0:
            # Standalone mode: use range × origin_counter_trend_range
            counter_range = leg.origin_counter_trend_range or 0.0
            raw_score = float(leg.range) * counter_range
            # Normalize by max observed (use range distribution as proxy)
            max_range = float(max(self._range_distribution)) if self._range_distribution else 1.0
            # Normalize: divide by max_range² to keep in reasonable 0-1 range
            if max_range > 0:
                return min(raw_score / (max_range * max_range), 1.0)
            return 0.0

        # Combine mode: weighted sum of components
        # Range score: normalized against distribution
        range_score = self._normalize_range(float(leg.range))

        # Impulse score: percentile from DAG
        use_impulse = leg.impulsiveness is not None
        impulse_score = leg.impulsiveness / 100 if use_impulse else 0

        # Recency score: fixed decay
        age = current_bar_index - leg.origin_index
        recency_score = 1 / (1 + age / 1000)

        # Depth score: root legs (depth 0) score higher
        # Use inverse depth with decay: 1 / (1 + depth * 0.5)
        depth = leg.depth if hasattr(leg, 'depth') and leg.depth is not None else 0
        depth_score = 1.0 / (1.0 + depth * 0.5)

        # Scale-dependent weights for range, impulse, recency
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

        # Add depth weight (same for all scales)
        weights['depth'] = self.reference_config.depth_weight

        # Normalize weights if impulse is missing
        if not use_impulse:
            total = weights['range'] + weights['recency'] + weights['depth']
            if total > 0:
                weights['range'] /= total
                weights['recency'] /= total
                weights['depth'] /= total
            weights['impulse'] = 0

        return (weights['range'] * range_score +
                weights['impulse'] * impulse_score +
                weights['recency'] * recency_score +
                weights['depth'] * depth_score)

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

    def get_confluence_zones(
        self,
        state: ReferenceState,
        tolerance_pct: Optional[float] = None,
    ) -> List[ConfluenceZone]:
        """
        Find where fib levels from different references cluster.

        When levels from multiple references fall within the tolerance,
        they form a confluence zone - an area of increased significance.

        Algorithm:
        1. Collect all levels from all valid references
        2. Sort by price
        3. Cluster adjacent levels within tolerance
        4. Only include clusters from 2+ unique references

        Args:
            state: ReferenceState from update() containing valid references.
            tolerance_pct: Percentage tolerance for clustering (e.g., 0.001 = 0.1%).
                If None, uses config default.

        Returns:
            List of ConfluenceZone, each containing clustered levels.

        Example:
            >>> zones = ref_layer.get_confluence_zones(state, tolerance_pct=0.001)
            >>> for zone in zones:
            ...     print(f"Confluence at {zone.center_price:.2f}: {zone.reference_count} refs")
        """
        tolerance = tolerance_pct if tolerance_pct is not None else self.reference_config.confluence_tolerance_pct

        # Collect all levels with their source reference
        all_levels: List[LevelInfo] = []
        levels_by_ratio = self.get_active_levels(state)
        for ratio_levels in levels_by_ratio.values():
            all_levels.extend(ratio_levels)

        if len(all_levels) < 2:
            return []

        # Sort by price
        all_levels.sort(key=lambda lvl: lvl.price)

        # Cluster adjacent levels within tolerance
        zones: List[ConfluenceZone] = []
        current_cluster: List[LevelInfo] = [all_levels[0]]

        for i in range(1, len(all_levels)):
            prev_price = current_cluster[-1].price
            curr_price = all_levels[i].price

            # Calculate tolerance based on the average of the two prices
            avg_price = (prev_price + curr_price) / 2
            allowed_distance = avg_price * tolerance

            if abs(curr_price - prev_price) <= allowed_distance:
                # Within tolerance, add to current cluster
                current_cluster.append(all_levels[i])
            else:
                # New cluster starts, finalize previous
                if len(current_cluster) >= 2:
                    zone = self._create_confluence_zone(current_cluster)
                    if zone.reference_count >= 2:
                        zones.append(zone)
                current_cluster = [all_levels[i]]

        # Don't forget the last cluster
        if len(current_cluster) >= 2:
            zone = self._create_confluence_zone(current_cluster)
            if zone.reference_count >= 2:
                zones.append(zone)

        return zones

    def _create_confluence_zone(self, levels: List[LevelInfo]) -> ConfluenceZone:
        """
        Create a ConfluenceZone from a list of clustered levels.

        Args:
            levels: List of LevelInfo that form the cluster.

        Returns:
            ConfluenceZone with computed center, bounds, and reference info.
        """
        prices = [lvl.price for lvl in levels]
        ref_ids = {lvl.reference.leg.leg_id for lvl in levels}

        return ConfluenceZone(
            center_price=sum(prices) / len(prices),
            min_price=min(prices),
            max_price=max(prices),
            levels=levels,
            reference_count=len(ref_ids),
            reference_ids=ref_ids,
        )

    def get_structure_panel_data(
        self,
        state: ReferenceState,
        bar: Bar,
    ) -> StructurePanelData:
        """
        Get data for the Structure Panel.

        Three sections per spec:
        1. Touched this session - Historical record of which levels were hit
        2. Currently active - Levels within striking distance of current price
        3. Current bar - Levels touched on most recent bar

        Level "testing" = touch/cross (not proximity). A level is tested
        when price actually trades at or through it.

        Args:
            state: ReferenceState from update().
            bar: Current bar with OHLC.

        Returns:
            StructurePanelData with all three sections populated.
        """
        current_price = float(bar.close)
        bar_high = float(bar.high)
        bar_low = float(bar.low)

        # Get all active levels
        levels_by_ratio = self.get_active_levels(state)
        all_levels: List[LevelInfo] = []
        for ratio_levels in levels_by_ratio.values():
            all_levels.extend(ratio_levels)

        # Detect level touches on current bar
        current_bar_touches: List[LevelTouch] = []
        for level in all_levels:
            # A level is touched if price traded through it on this bar
            if bar_low <= level.price <= bar_high:
                # Determine cross direction based on where price came from
                cross_direction = 'up' if self._last_price is not None and self._last_price < level.price else 'down'
                touch = LevelTouch(
                    level=level,
                    bar_index=bar.index,
                    touch_price=level.price,
                    cross_direction=cross_direction,
                )
                current_bar_touches.append(touch)
                self._session_level_touches.append(touch)

        # Update last price for next call
        self._last_price = current_price

        # Currently active: levels within striking distance
        distance_threshold = current_price * self.reference_config.active_level_distance_pct
        currently_active: List[LevelInfo] = [
            level for level in all_levels
            if abs(level.price - current_price) <= distance_threshold
        ]

        return StructurePanelData(
            touched_this_session=self._session_level_touches.copy(),
            currently_active=currently_active,
            current_bar_touches=current_bar_touches,
            current_price=current_price,
        )

    def clear_session_touches(self) -> None:
        """
        Clear the session level touch history.

        Call this when starting a new session or restarting playback.
        """
        self._session_level_touches.clear()
        self._last_price = None

    def add_crossing_tracking(self, leg_id: str) -> Tuple[bool, Optional[str]]:
        """
        Add a leg to level crossing monitoring.

        When a leg is tracked, level crossing events can be detected
        for that specific leg. Use remove_crossing_tracking() to stop.

        A maximum of MAX_TRACKED_LEGS (10) can be tracked at once.
        If the limit is reached, this call will fail.

        Args:
            leg_id: The leg_id to start tracking.

        Returns:
            Tuple of (success: bool, error_message: Optional[str]).
            If success is False, error_message contains the reason.
        """
        if leg_id in self._tracked_for_crossing:
            return (True, None)  # Already tracked

        if len(self._tracked_for_crossing) >= MAX_TRACKED_LEGS:
            return (False, f"Maximum of {MAX_TRACKED_LEGS} tracked legs reached")

        self._tracked_for_crossing.add(leg_id)
        return (True, None)

    def remove_crossing_tracking(self, leg_id: str) -> None:
        """
        Remove a leg from level crossing monitoring.

        Also cleans up the last level tracking state for that leg.

        Args:
            leg_id: The leg_id to stop tracking.
        """
        self._tracked_for_crossing.discard(leg_id)
        # Clean up last level tracking
        self._last_level.pop(leg_id, None)

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

    def _quantize_to_fib_level(self, location: float) -> float:
        """
        Quantize a location to the nearest standard fib level.

        Standard fib levels: 0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0

        If location is beyond the standard range, returns the nearest boundary.

        Args:
            location: Current price location in reference frame (0-2+ range).

        Returns:
            The nearest standard fib level.
        """
        if location < 0:
            return 0.0
        if location > 2.0:
            return 2.0

        # Find the nearest standard fib level
        min_diff = float('inf')
        nearest_level = 0.0
        for level in STANDARD_FIB_LEVELS:
            diff = abs(location - level)
            if diff < min_diff:
                min_diff = diff
                nearest_level = level

        return nearest_level

    def _detect_fib_levels_between(
        self,
        prev_location: float,
        curr_location: float,
    ) -> List[Tuple[float, str]]:
        """
        Detect which fib levels were crossed between two locations.

        Args:
            prev_location: Previous location in reference frame.
            curr_location: Current location in reference frame.

        Returns:
            List of (level, cross_direction) tuples for each crossed level.
            cross_direction is 'up' if price moved from below to above,
            'down' if price moved from above to below.
        """
        if prev_location == curr_location:
            return []

        crossed_levels: List[Tuple[float, str]] = []
        direction = 'up' if curr_location > prev_location else 'down'

        # Get levels in the range between previous and current
        min_loc = min(prev_location, curr_location)
        max_loc = max(prev_location, curr_location)

        for level in STANDARD_FIB_LEVELS:
            # A level is crossed if it's strictly between prev and curr
            # (inclusive on one side to catch the case where we landed exactly on it)
            if min_loc < level <= max_loc or min_loc <= level < max_loc:
                # Check if actually crossed (not just touched from same side)
                if prev_location < level <= curr_location:
                    crossed_levels.append((level, 'up'))
                elif curr_location < level <= prev_location:
                    crossed_levels.append((level, 'down'))
                elif prev_location <= level < curr_location:
                    crossed_levels.append((level, 'up'))
                elif curr_location <= level < prev_location:
                    crossed_levels.append((level, 'down'))

        return crossed_levels

    def detect_level_crossings(
        self,
        legs: List[Leg],
        bar: Bar,
    ) -> List[LevelCrossEvent]:
        """
        Detect level crossings for all tracked legs on the current bar.

        For each tracked leg, computes the current location and compares
        to the last known level. If the location crossed one or more fib
        levels, emits LevelCrossEvent for each crossing.

        Args:
            legs: Active legs from DAG.
            bar: Current bar with OHLC.

        Returns:
            List of LevelCrossEvent for all crossings detected this bar.
        """
        if not self._tracked_for_crossing:
            return []

        events: List[LevelCrossEvent] = []
        current_price = Decimal(str(bar.close))

        # Build leg lookup for tracked legs
        leg_by_id = {leg.leg_id: leg for leg in legs}

        for leg_id in list(self._tracked_for_crossing):
            leg = leg_by_id.get(leg_id)
            if leg is None:
                # Leg no longer exists, remove from tracking
                self.remove_crossing_tracking(leg_id)
                continue

            # Compute current location
            location = self._compute_location(leg, current_price)

            # Get previous level (or None if first time tracking)
            prev_level = self._last_level.get(leg_id)

            if prev_level is not None:
                # Detect crossings between previous quantized level and current location
                prev_quantized = prev_level
                crossings = self._detect_fib_levels_between(prev_quantized, location)

                for level_crossed, cross_direction in crossings:
                    event = LevelCrossEvent(
                        bar_index=bar.index,
                        timestamp=datetime.now(),
                        leg_id=leg_id,
                        direction=leg.direction,
                        level_crossed=level_crossed,
                        cross_direction=cross_direction,
                    )
                    events.append(event)
                    self._pending_cross_events.append(event)

            # Update last level to current quantized level
            self._last_level[leg_id] = self._quantize_to_fib_level(location)

        return events

    def get_pending_cross_events(self, clear: bool = True) -> List[LevelCrossEvent]:
        """
        Get all pending level crossing events.

        Events accumulate from detect_level_crossings() calls. Use this method
        to retrieve and optionally clear them.

        Args:
            clear: If True (default), clears pending events after returning.

        Returns:
            List of LevelCrossEvent that have been emitted since last clear.
        """
        events = self._pending_cross_events.copy()
        if clear:
            self._pending_cross_events.clear()
        return events

    def clear_crossing_state(self) -> None:
        """
        Clear all level crossing tracking state.

        Clears:
        - All tracked legs
        - Last level history
        - Pending crossing events

        Use this when resetting playback or starting a new session.
        """
        self._tracked_for_crossing.clear()
        self._last_level.clear()
        self._pending_cross_events.clear()

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
        timestamp = bar.timestamp if bar.timestamp else 0.0

        # Check formation for all legs first (this updates range distribution
        # for newly formed legs, which affects cold start progress)
        for leg in legs:
            was_already_formed = leg.leg_id in self._formed_refs
            self._is_formed_for_reference(leg, current_price, timestamp)
            # Update bin distribution on pivot extension for already-formed legs (#434)
            if was_already_formed and leg.leg_id in self._seen_leg_ids:
                self._update_bin_distribution(leg.leg_id, float(leg.range))

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

    def get_all_with_status(self, legs: List[Leg], bar: Bar) -> List[FilteredLeg]:
        """
        Get all legs with their filter status for observability.

        Unlike update() which returns only valid references, this method returns
        every active leg with its filter reason. Used by the Reference Observation
        UI to show why each leg was filtered.

        Filter evaluation order:
        1. Cold Start - If < min_swings_for_scale formed, all legs get COLD_START
        2. Not Formed - Leg hasn't reached formation threshold (38.2%)
        3. Pivot Breached - Location < 0 (past defended pivot)
        4. Completed - Location > 2 (past 2× extension target)
        5. Origin Breached - Scale-dependent tolerance exceeded
        6. VALID - Passed all filters

        Args:
            legs: Active legs from DAG.
            bar: Current bar with OHLC.

        Returns:
            List of FilteredLeg for every input leg, with reason explaining
            filter status.

        Example:
            >>> legs = detector.state.active_legs
            >>> statuses = ref_layer.get_all_with_status(legs, bar)
            >>> for s in statuses:
            ...     if s.reason != FilterReason.VALID:
            ...         print(f"{s.leg.leg_id}: {s.reason.value}")
        """
        current_price = Decimal(str(bar.close))
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))
        timestamp = bar.timestamp if bar.timestamp else 0.0
        results: List[FilteredLeg] = []

        # Check formation for all legs first (populates _formed_refs)
        for leg in legs:
            was_already_formed = leg.leg_id in self._formed_refs
            self._is_formed_for_reference(leg, current_price, timestamp)
            # Update bin distribution on pivot extension for already-formed legs (#434)
            if was_already_formed and leg.leg_id in self._seen_leg_ids:
                self._update_bin_distribution(leg.leg_id, float(leg.range))

        for leg in legs:
            scale = self._classify_scale(leg.range)
            location = self._compute_location(leg, current_price)

            # Cold start: return all legs with COLD_START reason
            if self.is_cold_start:
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.COLD_START,
                    scale=scale,
                    location=min(location, 2.0),
                    threshold=None,
                ))
                continue

            # Not formed: hasn't reached formation threshold
            if leg.leg_id not in self._formed_refs:
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.NOT_FORMED,
                    scale=scale,
                    location=min(location, 2.0),
                    threshold=self.reference_config.formation_fib_threshold,
                ))
                continue

            # Compute extreme location for breach checks
            if leg.direction == 'bear':
                extreme_location = self._compute_location(leg, bar_low)
            else:
                extreme_location = self._compute_location(leg, bar_high)
            bar_close_location = location

            # Pivot breached: location < 0
            if extreme_location < 0:
                self._formed_refs.discard(leg.leg_id)
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.PIVOT_BREACHED,
                    scale=scale,
                    location=min(location, 2.0),
                    threshold=None,
                ))
                continue

            # Completed: location > 2
            if extreme_location > 2:
                self._formed_refs.discard(leg.leg_id)
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.COMPLETED,
                    scale=scale,
                    location=min(location, 2.0),
                    threshold=2.0,
                ))
                continue

            # Origin breached: scale-dependent tolerance
            if scale in ('S', 'M'):
                tolerance = self.reference_config.small_origin_tolerance
                if extreme_location > (1.0 + tolerance):
                    self._formed_refs.discard(leg.leg_id)
                    results.append(FilteredLeg(
                        leg=leg,
                        reason=FilterReason.ORIGIN_BREACHED,
                        scale=scale,
                        location=min(location, 2.0),
                        threshold=1.0 + tolerance,
                    ))
                    continue
            else:  # L, XL
                trade_tolerance = self.reference_config.big_trade_breach_tolerance
                close_tolerance = self.reference_config.big_close_breach_tolerance
                if extreme_location > (1.0 + trade_tolerance):
                    self._formed_refs.discard(leg.leg_id)
                    results.append(FilteredLeg(
                        leg=leg,
                        reason=FilterReason.ORIGIN_BREACHED,
                        scale=scale,
                        location=min(location, 2.0),
                        threshold=1.0 + trade_tolerance,
                    ))
                    continue
                if bar_close_location > (1.0 + close_tolerance):
                    self._formed_refs.discard(leg.leg_id)
                    results.append(FilteredLeg(
                        leg=leg,
                        reason=FilterReason.ORIGIN_BREACHED,
                        scale=scale,
                        location=min(location, 2.0),
                        threshold=1.0 + close_tolerance,
                    ))
                    continue

            # Passed all filters - VALID
            results.append(FilteredLeg(
                leg=leg,
                reason=FilterReason.VALID,
                scale=scale,
                location=min(location, 2.0),
                threshold=None,
            ))

        return results
