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
from .dag import BIN_MULTIPLIERS
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

    Filter conditions (evaluated in order) — Issue #454:
    1. COLD_START - System warming up (< min_swings_for_scale formed legs)
    2. NOT_FORMED - Price hasn't reached formation threshold (23.6% retracement)
    3. PIVOT_BREACHED - Location < -pivot_breach_tolerance (price past defended pivot)
       - Bins < 8: Uses pivot_breach_tolerance (default 0%)
       - Bins >= 8: Uses significant_trade_breach_tolerance (15%) or close (10%)
    4. COMPLETED - Location > completion_threshold (past extension target)
    5. ACTIVE_NOT_SALIENT - Valid reference, but didn't make per-pivot top N (#457)

    Note: Origin breach was removed in #454. A reference leg should remain valid
    as long as the pivot holds — origin breach just means you're in breakout zone.

    Example:
        >>> leg = create_leg(...)
        >>> status = ref_layer.get_all_with_status([leg], bar)[0]
        >>> if status.reason == FilterReason.NOT_FORMED:
        ...     print(f"Needs to reach {status.threshold:.1%} formation")
    """
    VALID = "valid"                   # Leg passes all filters
    COLD_START = "cold_start"         # Not enough data for scale classification
    NOT_FORMED = "not_formed"         # Price hasn't reached formation threshold
    PIVOT_BREACHED = "pivot_breached" # Location < -tolerance (past defended pivot)
    COMPLETED = "completed"           # Location > completion_threshold
    ACTIVE_NOT_SALIENT = "active_not_salient"  # Valid ref, didn't make per-pivot top N (#457)


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
        bin: Median-normalized bin index (0-10). See BIN_MULTIPLIERS for ranges.
        location: Current price position in reference frame (0-2 range).
        threshold: The threshold that was violated (for breach reasons).
            - For NOT_FORMED: formation_fib_threshold (0.382)
            - For ORIGIN_BREACHED: the tolerance exceeded
            - None for other reasons.

    Example:
        >>> status = FilteredLeg(
        ...     leg=leg,
        ...     reason=FilterReason.NOT_FORMED,
        ...     bin=8,
        ...     location=0.28,
        ...     threshold=0.382,
        ... )
        >>> print(f"Leg needs to reach {status.threshold:.1%} (currently at {status.location:.1%})")
        Leg needs to reach 38.2% (currently at 28.0%)
    """
    leg: Leg
    reason: FilterReason
    bin: int                          # 0-10 median-normalized bin index (#436)
    location: float                   # Current price in reference frame
    threshold: Optional[float] = None # Violated threshold (for breach reasons)


@dataclass
class FilterStats:
    """
    Statistics about filter outcomes for observability (#472).

    Computed as a byproduct of update() without requiring get_all_with_status().
    Enables Filters panel to display filter stats during playback.

    Attributes:
        total_legs: Total number of legs evaluated.
        valid_count: Number of legs that passed all filters (became references).
        pass_rate: Ratio of valid_count to total_legs (0.0-1.0).
        by_reason: Count of legs per filter reason.

    Example:
        >>> stats = FilterStats(
        ...     total_legs=100,
        ...     valid_count=30,
        ...     pass_rate=0.30,
        ...     by_reason={'not_formed': 50, 'pivot_breached': 15, 'completed': 5}
        ... )
    """
    total_legs: int
    valid_count: int
    pass_rate: float
    by_reason: Dict[str, int]


@dataclass
class ReferenceSwing:
    """
    A DAG leg that qualifies as a valid trading reference.

    This is the primary output of the Reference Layer. Each ReferenceSwing
    wraps a Leg from the DAG with reference-layer specific annotations.

    The Reference Layer filters DAG legs through formation, location, and
    breach checks, then annotates qualifying legs with bin and salience.

    Attributes:
        leg: The underlying DAG leg (not a copy).
        bin: Median-normalized bin index (0-10). See BIN_MULTIPLIERS for ranges.
            Frontend displays as median multiple (e.g., "2×" for bin 6).
            Bins 0-7: < 5× median (small), Bin 8: 5-10× (significant),
            Bin 9: 10-25× (large), Bin 10: 25×+ (exceptional).
        depth: Hierarchy depth from DAG (0 = root, 1+ = nested).
        location: Current price position in reference frame (0-2 range).
            0 = at defended pivot, 1 = at origin, 2 = at completion target.
            Capped at 2.0 in output per spec.
        salience_score: Relevance ranking (higher = more relevant).
            Computed from range, impulse, and recency.

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
        ...     bin=9,
        ...     depth=0,
        ...     location=0.382,
        ...     salience_score=0.75,
        ... )
        >>> ref.bin
        9
        >>> ref.location
        0.382
    """
    leg: Leg                      # The underlying DAG leg
    bin: int                      # 0-10 median-normalized bin index (#436)
    depth: int                    # Hierarchy depth from DAG
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
        references: Top N per pivot, ranked by salience (highest first).
        active_filtered: Valid references that didn't make per-pivot top N (#457).
            These are fully valid references with salience scores — they just
            didn't make the cut. Can return to top N as salience shifts.
        by_bin: References grouped by bin index (0-10).
        significant: References with bin >= 8 (5× median or larger).
        by_depth: References grouped by hierarchy depth (0 = root).
        by_direction: References grouped by 'bull' or 'bear'.
        direction_imbalance: 'bull' if bull refs > 2× bear refs,
            'bear' if bear refs > 2× bull refs, None if balanced.

    Design Notes:
        - references contains top N per pivot (configurable via top_n)
        - active_filtered contains valid refs that didn't make top N
        - Both lists are sorted by salience (highest first)
        - Grouping dicts are views into the references list (not copies)
        - direction_imbalance highlights when one direction dominates
        - significant threshold is bin >= 8 (5× median), configurable

    Example:
        >>> state = ReferenceState(
        ...     references=[ref1, ref2, ref3],
        ...     active_filtered=[ref4, ref5],
        ...     by_bin={9: [ref1], 8: [ref2, ref3]},
        ...     significant=[ref1, ref2, ref3],
        ...     by_depth={0: [ref1], 1: [ref2, ref3]},
        ...     by_direction={'bull': [ref1, ref2], 'bear': [ref3]},
        ...     direction_imbalance='bull',
        ... )
        >>> len(state.references)
        3
        >>> len(state.active_filtered)
        2
    """
    references: List['ReferenceSwing']              # Top N per pivot, ranked by salience
    active_filtered: List['ReferenceSwing']         # Valid refs that didn't make top N (#457)
    by_bin: Dict[int, List['ReferenceSwing']]       # Grouped by bin index (0-10)
    significant: List['ReferenceSwing']             # Bin >= 8 (5× median or larger)
    by_depth: Dict[int, List['ReferenceSwing']]     # Grouped by hierarchy depth
    by_direction: Dict[str, List['ReferenceSwing']] # Grouped by bull/bear
    direction_imbalance: Optional[str]              # 'bull' | 'bear' | None
    is_warming_up: bool = False                      # True if in cold start
    warmup_progress: Tuple[int, int] = (0, 50)       # (current_count, required_count)
    filter_stats: Optional['FilterStats'] = None     # Filter statistics (#472)


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
        >>> from swing_analysis.dag import LegDetector
        >>>
        >>> # Get legs from DAG
        >>> detector = LegDetector()
        >>> for bar in bars:
        ...     events = detector.process_bar(bar)
        >>> legs = detector.state.active_legs
        >>>
        >>> # Apply reference layer filters
        >>> config = DetectionConfig.default()
        >>> ref_layer = ReferenceLayer(config)
        >>>
        >>> # Update on each bar
        >>> state = ref_layer.update(legs, bar)
        >>> for ref in state.references:
        ...     print(f"{ref.leg.leg_id}: bin={ref.bin}, salience={ref.salience_score:.2f}")
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
        # Median-normalized bin distribution (#434) for O(1) scale classification
        # Uses rolling window with periodic median recomputation
        self._bin_distribution: RollingBinDistribution = RollingBinDistribution(
            window_duration_days=self.reference_config.bin_window_duration_days,
            recompute_interval_legs=self.reference_config.bin_recompute_interval,
        )
        # Track which legs have formed as references (price reached formation threshold)
        # Maps leg_id -> (pivot_price, formation_bar_index) at time of formation
        # Formation is nullified if pivot extends past this price (Issue #448)
        # Formation bar index used to filter by bar for per-bar state queries (#451)
        self._formed_refs: Dict[str, Tuple[Decimal, int]] = {}
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
        bar_index = bar.index if hasattr(bar, 'index') else 0
        for leg in legs:
            was_already_formed = leg.leg_id in self._formed_refs
            self._is_formed_for_reference(leg, current_price, timestamp, bar_index)
            # Update bin distribution on pivot extension for already-formed legs (#434)
            if was_already_formed and leg.leg_id in self._seen_leg_ids:
                self._update_bin_distribution(leg.leg_id, float(leg.range))

    @property
    def is_cold_start(self) -> bool:
        """
        True if not enough data for reliable bin classification.

        During cold start, update() returns an empty ReferenceState because
        median-normalized bins are unreliable with insufficient data.

        Returns:
            True if distribution has fewer than min_swings_for_classification legs.
        """
        return self._bin_distribution.total_count < self.reference_config.min_swings_for_classification

    @property
    def cold_start_progress(self) -> Tuple[int, int]:
        """
        Returns (current_count, required_count) for cold start progress.

        Use this for UI display like "Warming up: 35/50 swings collected".

        Returns:
            Tuple of (current swings in distribution, required minimum).
        """
        return (self._bin_distribution.total_count, self.reference_config.min_swings_for_classification)

    def is_formed_at_bar(self, leg_id: str, bar_index: int) -> bool:
        """
        Check if a leg was formed at or before the given bar index (#451).

        Used for per-bar reference state queries during buffered playback.
        A leg is considered formed at bar N if its formation_bar <= N.

        Args:
            leg_id: The leg ID to check.
            bar_index: The bar index to check formation at.

        Returns:
            True if the leg was formed at or before the given bar index.
        """
        if leg_id not in self._formed_refs:
            return False
        _pivot_price, formation_bar = self._formed_refs[leg_id]
        return formation_bar <= bar_index

    def get_formed_leg_ids_at_bar(self, bar_index: int) -> Set[str]:
        """
        Get set of leg IDs that were formed at or before the given bar (#451).

        Used for per-bar reference state queries during buffered playback.

        Args:
            bar_index: The bar index to filter formation at.

        Returns:
            Set of leg IDs that were formed at or before the given bar.
        """
        return {
            leg_id for leg_id, (_, formation_bar) in self._formed_refs.items()
            if formation_bar <= bar_index
        }

    def _get_bin_index(self, leg_range: Decimal) -> int:
        """
        Get bin index for a leg range using median-normalized bins (#436).

        Bin ranges (multiples of median):
        - Bin 0: 0-0.3×, Bin 1: 0.3-0.5×, Bin 2: 0.5-0.75×, Bin 3: 0.75-1×
        - Bin 4: 1-1.5×, Bin 5: 1.5-2×, Bin 6: 2-3×, Bin 7: 3-5×
        - Bin 8: 5-10× (significant), Bin 9: 10-25× (large), Bin 10: 25×+ (exceptional)

        Args:
            leg_range: Absolute range of the leg to classify.

        Returns:
            Bin index (0-10).

        Example:
            >>> config = ReferenceConfig.default()
            >>> ref_layer = ReferenceLayer(reference_config=config)
            >>> # After populating distribution with 100 values...
            >>> ref_layer._get_bin_index(Decimal("95"))  # Large range
            9
        """
        return self._bin_distribution.get_bin_index(float(leg_range))

    def _update_bin_distribution(self, leg_id: str, new_range: float) -> None:
        """
        Update a leg's range in the bin distribution when pivot extends (#434).

        O(1) operation: decrement old bin, increment new bin.

        Args:
            leg_id: Unique leg identifier.
            new_range: New range value after pivot extension.
        """
        self._bin_distribution.update_leg(leg_id, new_range)

    def _update_bin_classifications(self, legs: List[Leg]) -> None:
        """
        Set range_bin_index and bin_impulsiveness on formed legs (#491).

        For each formed leg:
        1. Sets range_bin_index from bin distribution
        2. Computes bin_impulsiveness: percentile rank of impulse within same bin

        Bin-normalized impulsiveness is more useful than global impulsiveness
        because it compares apples to apples - a highly impulsive small leg is
        different from a highly impulsive large leg.

        Args:
            legs: Active legs from DAG.
        """
        # First pass: classify all formed legs into bins and collect impulses per bin
        bin_impulses: Dict[int, List[float]] = {}
        legs_with_bins: List[Tuple[Leg, int]] = []

        for leg in legs:
            # Only process formed legs with valid impulse
            if leg.leg_id not in self._formed_refs:
                continue
            if leg.impulse is None or leg.impulse <= 0:
                continue

            bin_idx = self._get_bin_index(leg.range)
            leg.range_bin_index = bin_idx
            legs_with_bins.append((leg, bin_idx))

            if bin_idx not in bin_impulses:
                bin_impulses[bin_idx] = []
            bin_impulses[bin_idx].append(leg.impulse)

        # Sort impulses per bin for percentile lookup
        for bin_idx in bin_impulses:
            bin_impulses[bin_idx].sort()

        # Second pass: compute bin_impulsiveness for each leg
        for leg, bin_idx in legs_with_bins:
            impulses = bin_impulses.get(bin_idx, [])
            if not impulses or leg.impulse is None:
                leg.bin_impulsiveness = None
                continue

            # Compute percentile rank within the bin using bisect
            count_below = bisect.bisect_left(impulses, leg.impulse)
            count_equal = bisect.bisect_right(impulses, leg.impulse) - count_below
            # Use midpoint of the range where value would be inserted
            # This gives (count_below + count_equal/2) / total
            percentile = (count_below + count_equal / 2) / len(impulses) * 100
            leg.bin_impulsiveness = percentile

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

    def _update_max_location(self, leg: Leg, location: float) -> None:
        """
        Track maximum location ever reached for this leg (#467).

        Used to derive completion status at runtime. Once a leg's max_location
        reaches the completion_threshold, the leg is permanently completed
        and cannot re-form as a reference.

        Args:
            leg: The leg to update.
            location: Current location in reference frame.
        """
        if leg.ref.max_location is None or location > leg.ref.max_location:
            leg.ref.max_location = location

    def _is_completed(self, leg: Leg) -> bool:
        """
        Check if leg is permanently completed based on max_location (#467).

        Completion is terminal — a completed reference should never re-form.
        This is derived from max_location rather than stored as a boolean,
        so if completion_threshold changes (e.g., from 2× to 3×), legs between
        the thresholds automatically become non-completed.

        Args:
            leg: The leg to check.

        Returns:
            True if leg has ever reached completion_threshold.
        """
        max_loc = leg.ref.max_location or 0
        return max_loc >= self.reference_config.completion_threshold

    def _is_formed_for_reference(
        self,
        leg: Leg,
        current_price: Decimal,
        timestamp: float = 0.0,
        bar_index: int = 0,
    ) -> bool:
        """
        Check if leg has reached formation threshold.

        Formation is PRICE-BASED, not age-based. A leg becomes a valid reference
        when the subsequent confirming move reaches the formation threshold
        (default 23.6%).

        Example: Bear leg from $110 (origin) to $100 (pivot), range = $10.
        - Formation threshold = 0.236 (23.6%)
        - Price must rise to $102.36 (23.6% retracement from pivot toward origin)
        - At that point, location = 0.236, swing is formed

        IMPORTANT (Issue #448): Formation is nullified when pivot extends.
        If the leg's current pivot has extended past the pivot at which it was
        formed, formation is cleared and must be re-achieved at the new level.
        This prevents legs from appearing as "formed" when their pivots have
        extended far beyond the original formation point.

        IMPORTANT (Issue #467): Completed references never re-form.
        If a leg's max_location ever reached completion_threshold, it is
        permanently completed. Even if price returns below the threshold,
        the leg should never re-enter _formed_refs.

        Args:
            leg: The leg to check
            current_price: Current price
            timestamp: Bar timestamp for bin distribution tracking (#434)
            bar_index: Current bar index for formation tracking (#451)

        Returns:
            True if formed at current pivot level
        """
        location = self._compute_location(leg, current_price)

        # Track max_location for completion detection (#467)
        self._update_max_location(leg, location)

        # Completed references never re-form (#467)
        # Check this BEFORE checking _formed_refs to prevent re-entry
        if self._is_completed(leg):
            # Ensure it's removed from _formed_refs if still there
            self._formed_refs.pop(leg.leg_id, None)
            return False

        # Check if previously formed
        if leg.leg_id in self._formed_refs:
            formation_pivot, _formation_bar = self._formed_refs[leg.leg_id]
            # Check if pivot has extended past formation pivot (Issue #448)
            # Bull leg: pivot extends higher; Bear leg: pivot extends lower
            pivot_extended = (
                (leg.direction == 'bull' and leg.pivot_price > formation_pivot) or
                (leg.direction == 'bear' and leg.pivot_price < formation_pivot)
            )
            if pivot_extended:
                # Pivot extended - nullify formation, must re-form at new level
                del self._formed_refs[leg.leg_id]
            else:
                # Pivot unchanged - still formed
                return True

        threshold = self.reference_config.formation_fib_threshold

        # Formation occurs when price retraces TO the threshold
        # Location 0 = pivot, Location 1 = origin
        # For formation, price must move from pivot toward origin by at least threshold
        # This means location must be >= threshold
        if location >= threshold:
            # Store pivot price and bar index at formation (Issue #448, #451)
            self._formed_refs[leg.leg_id] = (leg.pivot_price, bar_index)
            # Add to bin distribution on first formation (#372, #439)
            if leg.leg_id not in self._seen_leg_ids:
                self._seen_leg_ids.add(leg.leg_id)
                self._bin_distribution.add_leg(leg.leg_id, float(leg.range), timestamp)
            return True

        return False

    def _is_fatally_breached(
        self,
        leg: Leg,
        bin_index: int,
        location: float,
        bar_close_location: float
    ) -> Optional[FilterReason]:
        """
        Check if reference is fatally breached.

        A reference is fatally breached if ANY of these conditions are met (#454):
        1. Pivot breach: location < -pivot_breach_tolerance
           - Bins < 8: Uses pivot_breach_tolerance (default 0%)
           - Bins >= 8: Uses significant_trade_breach_tolerance (15%) or close (10%)
        2. Completion: location > completion_threshold (default 2)

        Note: Origin breach was removed in #454. A reference should remain valid
        as long as the pivot holds — origin breach just means you're in breakout zone.

        Args:
            leg: The leg to check
            bin_index: Median-normalized bin index (0-10)
            location: Current price location in reference frame (from bar high/low)
            bar_close_location: Location of bar close (for significant close breach)

        Returns:
            FilterReason if fatally breached (PIVOT_BREACHED or COMPLETED), None otherwise.
            (#472: Changed from bool to Optional[FilterReason] to enable filter_stats tracking in update())
        """
        completion_threshold = self.reference_config.completion_threshold

        # Pivot breach — bin-dependent (#436, #454: now uses config tolerance)
        if bin_index < self.reference_config.significant_bin_threshold:
            # Small refs: pivot breach when location < -pivot_breach_tolerance
            pivot_tolerance = self.reference_config.pivot_breach_tolerance
            if location < -pivot_tolerance:
                self._formed_refs.pop(leg.leg_id, None)
                return FilterReason.PIVOT_BREACHED
        else:
            # Significant refs (bin >= 8): two thresholds for pivot breach
            # Trade breach: invalidates if price TRADES beyond pivot by 15%
            if location < -self.reference_config.significant_trade_breach_tolerance:
                self._formed_refs.pop(leg.leg_id, None)
                return FilterReason.PIVOT_BREACHED
            # Close breach: invalidates if price CLOSES beyond pivot by 10%
            if bar_close_location < -self.reference_config.significant_close_breach_tolerance:
                self._formed_refs.pop(leg.leg_id, None)
                return FilterReason.PIVOT_BREACHED

        # Past completion (#467): Check both current location AND max_location
        # - location > threshold: current bar triggered completion (strict >)
        # - _is_completed: leg was completed on a previous bar (>= via max_location)
        if location > completion_threshold or self._is_completed(leg):
            self._formed_refs.pop(leg.leg_id, None)
            return FilterReason.COMPLETED

        return None

    def _get_max_range(self) -> float:
        """
        Get the normalization factor for range-based scores (median × 25).

        Returns:
            max_range value, or 1.0 if distribution is empty/zero.
        """
        if self._bin_distribution.total_count == 0:
            return 1.0
        max_range = self._bin_distribution.median * BIN_MULTIPLIERS[-2]  # Bin 10 edge
        return max_range if max_range > 0 else 1.0

    def _compute_salience(self, leg: Leg, current_bar_index: int) -> float:
        """
        Compute salience score for ranking references.

        Unified additive formula (#442) — all 6 weights are additive peers:
        - Range: leg size normalized via median × 25
        - Counter: counter-trend range normalized via median × 25
        - Range×Counter: product normalized via (median × 25)²
        - Impulse: percentile from DAG (0-1)
        - Recency: decay based on age
        - Depth: inverse depth score

        No clamping — exceptional legs (>25× median) can score >1.0 in range
        components, which allows them to rank appropriately higher.

        Args:
            leg: The leg to score
            current_bar_index: Current bar index for recency calculation

        Returns:
            Salience score (higher = more relevant)
        """
        max_val = self._get_max_range()

        # Range-based components (#442) — normalized via median × 25
        # No clamping: exceptional values should score exceptionally high
        range_score = float(leg.range) / max_val

        counter_range = float(leg.origin_counter_trend_range or 0)
        counter_score = counter_range / max_val

        # Range×Counter: normalized via (median × 25)²
        range_counter_score = (float(leg.range) * counter_range) / (max_val * max_val)

        # Impulse score: percentile from DAG (already 0-100, scale to 0-1)
        use_impulse = leg.impulsiveness is not None
        impulse_score = leg.impulsiveness / 100 if use_impulse else 0

        # Recency score: configurable decay (#438)
        age = current_bar_index - leg.origin_index
        recency_decay = self.reference_config.recency_decay_bars
        recency_score = 1 / (1 + age / recency_decay)

        # Depth score: root legs (depth 0) score higher
        # Use inverse depth with configurable decay (#438)
        depth = leg.depth if hasattr(leg, 'depth') and leg.depth is not None else 0
        depth_decay = self.reference_config.depth_decay_factor
        depth_score = 1.0 / (1.0 + depth * depth_decay)

        # Unified weights (#436, #442) — all are additive peers
        weights = {
            'range': self.reference_config.range_weight,
            'counter': self.reference_config.counter_weight,
            'range_counter': self.reference_config.range_counter_weight,
            'impulse': self.reference_config.impulse_weight,
            'recency': self.reference_config.recency_weight,
            'depth': self.reference_config.depth_weight,
        }

        # Normalize weights if impulse is missing (redistribute impulse weight to others)
        if not use_impulse and weights['impulse'] > 0:
            redistributed = weights['impulse']
            total_others = (weights['range'] + weights['counter'] + weights['range_counter'] +
                           weights['recency'] + weights['depth'])
            if total_others > 0:
                # Redistribute impulse weight proportionally
                factor = 1 + redistributed / total_others
                weights['range'] *= factor
                weights['counter'] *= factor
                weights['range_counter'] *= factor
                weights['recency'] *= factor
                weights['depth'] *= factor
            weights['impulse'] = 0

        return (weights['range'] * range_score +
                weights['counter'] * counter_score +
                weights['range_counter'] * range_counter_score +
                weights['impulse'] * impulse_score +
                weights['recency'] * recency_score +
                weights['depth'] * depth_score)

    def _group_by_bin(
        self,
        refs: List[ReferenceSwing],
    ) -> Dict[int, List[ReferenceSwing]]:
        """
        Group references by bin index.

        Args:
            refs: List of ReferenceSwing to group.

        Returns:
            Dict mapping bin index (0-10) to list of references.
        """
        result: Dict[int, List[ReferenceSwing]] = {}
        for r in refs:
            if r.bin not in result:
                result[r.bin] = []
            result[r.bin].append(r)
        return result

    def _filter_significant(
        self,
        refs: List[ReferenceSwing],
    ) -> List[ReferenceSwing]:
        """
        Filter references to only significant ones (bin >= significant_bin_threshold).

        Args:
            refs: List of ReferenceSwing to filter.

        Returns:
            List of references with bin >= significant_bin_threshold.
        """
        threshold = self.reference_config.significant_bin_threshold
        return [r for r in refs if r.bin >= threshold]

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

    def _apply_per_pivot_top_n(
        self,
        all_refs: List[ReferenceSwing],
        top_n: int,
    ) -> Tuple[List[ReferenceSwing], List[ReferenceSwing]]:
        """
        Apply per-pivot top N filtering (#457).

        Groups references by their defended pivot (direction-appropriate: HIGH for
        bull legs, LOW for bear legs) and keeps only the top N by salience per group.

        This is NON-DESTRUCTIVE — re-evaluated each bar. A reference filtered out
        at bar 100 can surface at bar 200 if its salience rises.

        Args:
            all_refs: All valid references, already sorted by salience descending.
            top_n: Number of references to keep per pivot group.

        Returns:
            Tuple of (top_refs, filtered_refs):
            - top_refs: References that made the per-pivot top N cut
            - filtered_refs: Valid references that didn't make the cut
        """
        if top_n <= 0:
            # No limit - all refs are top refs
            return (list(all_refs), [])

        # Group by pivot key: (pivot_price, pivot_index)
        # Bull legs: pivot = HIGH (defended), Bear legs: pivot = LOW (defended)
        pivot_groups: Dict[Tuple[Decimal, int], List[ReferenceSwing]] = {}

        for ref in all_refs:
            pivot_key = (ref.leg.pivot_price, ref.leg.pivot_index)
            if pivot_key not in pivot_groups:
                pivot_groups[pivot_key] = []
            pivot_groups[pivot_key].append(ref)

        # Each pivot group is already sorted by salience (inherited from input sort)
        # Keep top N from each group
        top_refs: List[ReferenceSwing] = []
        filtered_refs: List[ReferenceSwing] = []

        for pivot_key, group in pivot_groups.items():
            # Group is sorted by salience (descending) since input was sorted
            for i, ref in enumerate(group):
                if i < top_n:
                    top_refs.append(ref)
                else:
                    filtered_refs.append(ref)

        # Re-sort both lists by salience for consistent output
        top_refs.sort(key=lambda r: r.salience_score, reverse=True)
        filtered_refs.sort(key=lambda r: r.salience_score, reverse=True)

        return (top_refs, filtered_refs)

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
        Uses completion_threshold from config for the upper boundary (#454).

        Args:
            location: Current price location in reference frame (0-2+ range).

        Returns:
            The nearest standard fib level.
        """
        completion_threshold = self.reference_config.completion_threshold
        if location < 0:
            return 0.0
        if location > completion_threshold:
            return completion_threshold

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

    def update(
        self,
        legs: List[Leg],
        bar: Bar,
        build_response: bool = True,
        max_bar_index: Optional[int] = None,
    ) -> Optional[ReferenceState]:
        """
        Main entry point. Called each bar after DAG processes.

        One bar at a time. No look-ahead. Always assume real-time flow.

        Args:
            legs: Active legs from DAG.
            bar: Current bar with OHLC.
            build_response: If True (default), build and return full ReferenceState.
                If False, only perform side effects (formation tracking, breach
                removal, bin distribution updates) and return None. Use False
                during bulk advances for performance (#437).
            max_bar_index: If provided, only include legs that were formed at or
                before this bar index in the response (#451). Used for historical
                bar queries during buffered playback.

        Returns:
            ReferenceState with all valid references, or None if build_response=False.
        """
        current_price = Decimal(str(bar.close))
        timestamp = bar.timestamp if bar.timestamp else 0.0
        bar_index = bar.index if hasattr(bar, 'index') else 0

        # Check formation for all legs first (this updates range distribution
        # for newly formed legs, which affects cold start progress)
        for leg in legs:
            was_already_formed = leg.leg_id in self._formed_refs
            self._is_formed_for_reference(leg, current_price, timestamp, bar_index)
            # Update bin distribution on pivot extension for already-formed legs (#434)
            if was_already_formed and leg.leg_id in self._seen_leg_ids:
                self._update_bin_distribution(leg.leg_id, float(leg.range))

        # Cold start check: not enough swings for meaningful bin classification
        if self.is_cold_start:
            if not build_response:
                return None
            # #472: Include filter_stats even during cold start
            cold_start_stats = FilterStats(
                total_legs=len(legs),
                valid_count=0,
                pass_rate=0.0,
                by_reason={FilterReason.COLD_START.value: len(legs)},
            )
            return ReferenceState(
                references=[],
                active_filtered=[],
                by_bin={},
                significant=[],
                by_depth={},
                by_direction={'bull': [], 'bear': []},
                direction_imbalance=None,
                is_warming_up=True,
                warmup_progress=self.cold_start_progress,
                filter_stats=cold_start_stats,
            )

        # === SIDE EFFECTS: Breach checking (removes invalid refs from _formed_refs) ===
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))

        # #472: Track filter counts as byproduct of breach checking
        breach_counts: Dict[str, int] = {}

        for leg in legs:
            if leg.leg_id not in self._formed_refs:
                continue

            bin_index = self._get_bin_index(leg.range)

            # Compute locations from both bar extremes (#467)
            # Bear leg (bull reference): bar_low for breach, bar_high for completion
            # Bull leg (bear reference): bar_high for breach, bar_low for completion
            if leg.direction == 'bear':
                breach_extreme_location = self._compute_location(leg, bar_low)
                completion_extreme_location = self._compute_location(leg, bar_high)
            else:
                breach_extreme_location = self._compute_location(leg, bar_high)
                completion_extreme_location = self._compute_location(leg, bar_low)

            # Track max_location from completion extreme (#467)
            self._update_max_location(leg, completion_extreme_location)

            bar_close_location = self._compute_location(leg, current_price)

            # Side effect: removes from _formed_refs if fatally breached
            # #472: Returns FilterReason instead of bool for tracking
            breach_reason = self._is_fatally_breached(leg, bin_index, breach_extreme_location, bar_close_location)
            if breach_reason is not None:
                reason_key = breach_reason.value
                breach_counts[reason_key] = breach_counts.get(reason_key, 0) + 1

        # Time-based eviction - keeps distribution fresh (rolling 90-day window)
        self._bin_distribution.evict_old_legs(timestamp)

        # Update bin classifications and compute bin_impulsiveness (#491)
        self._update_bin_classifications(legs)

        # Early return for bulk advances - side effects done, skip response building
        if not build_response:
            return None

        # === RESPONSE BUILDING: Only when build_response=True ===
        references: List[ReferenceSwing] = []
        # #472: Count legs not formed
        not_formed_count = 0
        for leg in legs:
            if leg.leg_id not in self._formed_refs:
                not_formed_count += 1
                continue

            # Filter by formation bar if max_bar_index is provided (#451)
            # Only include legs that were formed at or before the requested bar
            if max_bar_index is not None:
                _pivot_price, formation_bar = self._formed_refs[leg.leg_id]
                if formation_bar > max_bar_index:
                    not_formed_count += 1  # Count as not formed for this bar query
                    continue  # Skip legs formed after the requested bar

            bin_index = self._get_bin_index(leg.range)
            location = self._compute_location(leg, current_price)
            completion_threshold = self.reference_config.completion_threshold

            salience = self._compute_salience(leg, bar.index)

            references.append(ReferenceSwing(
                leg=leg,
                bin=bin_index,
                depth=leg.depth,
                location=min(location, completion_threshold),  # Cap at completion_threshold (#454)
                salience_score=salience,
            ))

        # Sort by salience (descending)
        references.sort(key=lambda r: r.salience_score, reverse=True)

        # Apply per-pivot top N filtering (#457)
        # top_n from config determines how many refs to keep per pivot
        top_n = self.reference_config.top_n
        top_refs, active_filtered = self._apply_per_pivot_top_n(references, top_n)

        # Build groupings (#436) - based on top refs only
        by_bin = self._group_by_bin(top_refs)
        significant = self._filter_significant(top_refs)
        by_depth = self._group_by_depth(top_refs)
        by_direction = self._group_by_direction(top_refs)

        # Compute direction imbalance (based on top refs)
        bull_count = len(by_direction.get('bull', []))
        bear_count = len(by_direction.get('bear', []))
        if bull_count > bear_count * 2:
            imbalance: Optional[str] = 'bull'
        elif bear_count > bull_count * 2:
            imbalance = 'bear'
        else:
            imbalance = None

        # #472: Build filter_stats from tracked counts
        by_reason: Dict[str, int] = {}
        if not_formed_count > 0:
            by_reason[FilterReason.NOT_FORMED.value] = not_formed_count
        # Add breach counts
        by_reason.update(breach_counts)
        # Count active_not_salient (valid refs that didn't make per-pivot top N)
        if len(active_filtered) > 0:
            by_reason[FilterReason.ACTIVE_NOT_SALIENT.value] = len(active_filtered)

        total_legs = len(legs)
        valid_count = len(top_refs)
        filter_stats = FilterStats(
            total_legs=total_legs,
            valid_count=valid_count,
            pass_rate=valid_count / total_legs if total_legs > 0 else 0.0,
            by_reason=by_reason,
        )

        return ReferenceState(
            references=top_refs,
            active_filtered=active_filtered,
            by_bin=by_bin,
            significant=significant,
            by_depth=by_depth,
            by_direction=by_direction,
            direction_imbalance=imbalance,
            is_warming_up=False,
            warmup_progress=self.cold_start_progress,
            filter_stats=filter_stats,
        )

    def get_all_with_status(self, legs: List[Leg], bar: Bar) -> List[FilteredLeg]:
        """
        Get all legs with their filter status for observability.

        Unlike update() which returns only valid references, this method returns
        every active leg with its filter reason. Used by the Reference Observation
        UI to show why each leg was filtered.

        Filter evaluation order (#436):
        1. Cold Start - If < min_swings_for_classification formed, all legs get COLD_START
        2. Not Formed - Leg hasn't reached formation threshold (38.2%)
        3. Pivot Breached - Location < 0 (past defended pivot)
        4. Completed - Location > 2 (past 2× extension target)
        5. Origin Breached - Bin-dependent tolerance exceeded
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
        bar_index = bar.index if hasattr(bar, 'index') else 0
        results: List[FilteredLeg] = []

        # Check formation for all legs first (populates _formed_refs)
        for leg in legs:
            was_already_formed = leg.leg_id in self._formed_refs
            self._is_formed_for_reference(leg, current_price, timestamp, bar_index)
            # Update bin distribution on pivot extension for already-formed legs (#434)
            if was_already_formed and leg.leg_id in self._seen_leg_ids:
                self._update_bin_distribution(leg.leg_id, float(leg.range))

        for leg in legs:
            bin_index = self._get_bin_index(leg.range)
            location = self._compute_location(leg, current_price)
            completion_threshold = self.reference_config.completion_threshold

            # Cold start: return all legs with COLD_START reason
            if self.is_cold_start:
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.COLD_START,
                    bin=bin_index,
                    location=min(location, completion_threshold),
                    threshold=None,
                ))
                continue

            # Compute both bar extremes for breach and completion checks (#467)
            # Bear leg (bull reference): bar_low for breach, bar_high for completion
            # Bull leg (bear reference): bar_high for breach, bar_low for completion
            if leg.direction == 'bear':
                breach_extreme_location = self._compute_location(leg, bar_low)
                completion_extreme_location = self._compute_location(leg, bar_high)
            else:
                breach_extreme_location = self._compute_location(leg, bar_high)
                completion_extreme_location = self._compute_location(leg, bar_low)
            bar_close_location = location

            # Track max_location from completion extreme (#467)
            self._update_max_location(leg, completion_extreme_location)

            # Check completion FIRST (#467): If leg was ever completed, report COMPLETED
            # This catches both "completing this bar" and "was completed before"
            if self._is_completed(leg):
                self._formed_refs.pop(leg.leg_id, None)
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.COMPLETED,
                    bin=bin_index,
                    location=min(location, completion_threshold),
                    threshold=completion_threshold,
                ))
                continue

            # Not formed: hasn't reached formation threshold
            if leg.leg_id not in self._formed_refs:
                results.append(FilteredLeg(
                    leg=leg,
                    reason=FilterReason.NOT_FORMED,
                    bin=bin_index,
                    location=min(location, completion_threshold),
                    threshold=self.reference_config.formation_fib_threshold,
                ))
                continue

            # Pivot breached — bin-dependent (#436, #454: uses config tolerance)
            if bin_index < self.reference_config.significant_bin_threshold:
                # Small refs: pivot breach when location < -pivot_breach_tolerance
                pivot_tolerance = self.reference_config.pivot_breach_tolerance
                if breach_extreme_location < -pivot_tolerance:
                    self._formed_refs.pop(leg.leg_id, None)
                    results.append(FilteredLeg(
                        leg=leg,
                        reason=FilterReason.PIVOT_BREACHED,
                        bin=bin_index,
                        location=min(location, completion_threshold),
                        threshold=-pivot_tolerance,
                    ))
                    continue
            else:
                # Significant refs (bin >= 8): two thresholds for pivot breach
                trade_tolerance = self.reference_config.significant_trade_breach_tolerance
                close_tolerance = self.reference_config.significant_close_breach_tolerance
                if breach_extreme_location < -trade_tolerance:
                    self._formed_refs.pop(leg.leg_id, None)
                    results.append(FilteredLeg(
                        leg=leg,
                        reason=FilterReason.PIVOT_BREACHED,
                        bin=bin_index,
                        location=min(location, completion_threshold),
                        threshold=-trade_tolerance,
                    ))
                    continue
                if bar_close_location < -close_tolerance:
                    self._formed_refs.pop(leg.leg_id, None)
                    results.append(FilteredLeg(
                        leg=leg,
                        reason=FilterReason.PIVOT_BREACHED,
                        bin=bin_index,
                        location=min(location, completion_threshold),
                        threshold=-close_tolerance,
                    ))
                    continue

            # Passed all filters - VALID
            # Note: Origin breach removed in #454 - legs stay valid while pivot holds
            results.append(FilteredLeg(
                leg=leg,
                reason=FilterReason.VALID,
                bin=bin_index,
                location=min(location, completion_threshold),
                threshold=None,
            ))

        return results
