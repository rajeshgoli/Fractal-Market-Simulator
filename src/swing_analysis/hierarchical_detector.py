"""
Hierarchical Swing Detector

Incremental swing detector with hierarchical model. Processes one bar at a time
via process_bar(). Calibration is just a loop calling process_bar() — no special
batch logic. This eliminates lookahead bugs and ensures identical behavior between
calibration and playback.

See Docs/Working/swing_detection_rewrite_spec.md for design rationale.
See Docs/Reference/valid_swings.md for the canonical rules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Optional, Callable, Set

import pandas as pd

from .swing_config import SwingConfig, DirectionConfig
from .swing_node import SwingNode
from .events import (
    SwingEvent,
    SwingFormedEvent,
    SwingInvalidatedEvent,
    SwingCompletedEvent,
    LevelCrossEvent,
)
from .reference_frame import ReferenceFrame
from .types import Bar
from .bar_aggregator import BarAggregator


# Fibonacci levels to track for level cross events
FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 2.0]

# Higher timeframes for multi-TF candidate generation (in minutes)
MULTI_TF_TIMEFRAMES = [60, 240, 1440]  # 1h, 4h, 1d

# Lookback limits for each timeframe (how many TF bars to keep as candidates)
MULTI_TF_LOOKBACKS = {
    60: 12,   # Last 12 1h bars = 12 hours
    240: 6,   # Last 6 4h bars = 24 hours
    1440: 5,  # Last 5 daily bars = 5 days
}


@dataclass
class DetectorState:
    """
    Serializable state for pause/resume.

    Contains all information needed to resume detection from a saved point.
    Can be serialized to JSON for persistence.

    Attributes:
        active_swings: List of currently active swing nodes.
        candidate_highs: Sliding window of (bar_index, price) for potential origins.
        candidate_lows: Sliding window of (bar_index, price) for potential pivots.
        last_bar_index: Most recent bar index processed.
        fib_levels_crossed: Map of swing_id -> last Fib level for cross tracking.
        all_swing_ranges: List of all swing ranges seen, for big swing calculation.
        seen_tf_bars: Map of timeframe -> set of aggregated bar indices already processed.
        _cached_big_threshold_bull: Cached big swing threshold for bull swings.
        _cached_big_threshold_bear: Cached big swing threshold for bear swings.
        _threshold_valid: Whether the cached thresholds are valid.
    """

    active_swings: List[SwingNode] = field(default_factory=list)
    candidate_highs: List[Tuple[int, Decimal]] = field(default_factory=list)
    candidate_lows: List[Tuple[int, Decimal]] = field(default_factory=list)
    last_bar_index: int = -1
    fib_levels_crossed: Dict[str, float] = field(default_factory=dict)
    all_swing_ranges: List[Decimal] = field(default_factory=list)
    seen_tf_bars: Dict[int, Set[int]] = field(default_factory=lambda: {60: set(), 240: set(), 1440: set()})
    # Cached big swing thresholds (performance optimization #155)
    _cached_big_threshold_bull: Optional[Decimal] = None
    _cached_big_threshold_bear: Optional[Decimal] = None
    _threshold_valid: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "active_swings": [
                {
                    "swing_id": s.swing_id,
                    "high_bar_index": s.high_bar_index,
                    "high_price": str(s.high_price),
                    "low_bar_index": s.low_bar_index,
                    "low_price": str(s.low_price),
                    "direction": s.direction,
                    "status": s.status,
                    "formed_at_bar": s.formed_at_bar,
                    "parent_ids": [p.swing_id for p in s.parents],
                }
                for s in self.active_swings
            ],
            "candidate_highs": [
                (idx, str(price)) for idx, price in self.candidate_highs
            ],
            "candidate_lows": [(idx, str(price)) for idx, price in self.candidate_lows],
            "last_bar_index": self.last_bar_index,
            "fib_levels_crossed": self.fib_levels_crossed,
            "all_swing_ranges": [str(r) for r in self.all_swing_ranges],
            "seen_tf_bars": {str(tf): list(bars) for tf, bars in self.seen_tf_bars.items()},
            # Cache fields (will be recomputed on restore, but included for completeness)
            "_cached_big_threshold_bull": str(self._cached_big_threshold_bull) if self._cached_big_threshold_bull is not None else None,
            "_cached_big_threshold_bear": str(self._cached_big_threshold_bear) if self._cached_big_threshold_bear is not None else None,
            "_threshold_valid": self._threshold_valid,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DetectorState":
        """Create from dictionary."""
        # First pass: create all swing nodes without parent links
        swing_map: Dict[str, SwingNode] = {}
        parent_map: Dict[str, List[str]] = {}

        for swing_data in data.get("active_swings", []):
            swing = SwingNode(
                swing_id=swing_data["swing_id"],
                high_bar_index=swing_data["high_bar_index"],
                high_price=Decimal(swing_data["high_price"]),
                low_bar_index=swing_data["low_bar_index"],
                low_price=Decimal(swing_data["low_price"]),
                direction=swing_data["direction"],
                status=swing_data["status"],
                formed_at_bar=swing_data["formed_at_bar"],
            )
            swing_map[swing.swing_id] = swing
            parent_map[swing.swing_id] = swing_data.get("parent_ids", [])

        # Second pass: link parents
        for swing_id, parent_ids in parent_map.items():
            swing = swing_map[swing_id]
            for parent_id in parent_ids:
                if parent_id in swing_map:
                    swing.add_parent(swing_map[parent_id])

        # Deserialize seen_tf_bars
        seen_tf_bars_raw = data.get("seen_tf_bars", {})
        seen_tf_bars = {60: set(), 240: set(), 1440: set()}
        for tf_str, bars_list in seen_tf_bars_raw.items():
            tf = int(tf_str)
            if tf in seen_tf_bars:
                seen_tf_bars[tf] = set(bars_list)

        # Restore cache fields if present (they'll be recomputed on first use anyway)
        cached_bull = data.get("_cached_big_threshold_bull")
        cached_bear = data.get("_cached_big_threshold_bear")

        return cls(
            active_swings=list(swing_map.values()),
            candidate_highs=[
                (idx, Decimal(price))
                for idx, price in data.get("candidate_highs", [])
            ],
            candidate_lows=[
                (idx, Decimal(price)) for idx, price in data.get("candidate_lows", [])
            ],
            last_bar_index=data.get("last_bar_index", -1),
            fib_levels_crossed=data.get("fib_levels_crossed", {}),
            all_swing_ranges=[
                Decimal(r) for r in data.get("all_swing_ranges", [])
            ],
            seen_tf_bars=seen_tf_bars,
            _cached_big_threshold_bull=Decimal(cached_bull) if cached_bull is not None else None,
            _cached_big_threshold_bear=Decimal(cached_bear) if cached_bear is not None else None,
            _threshold_valid=data.get("_threshold_valid", False),
        )


class HierarchicalDetector:
    """
    Incremental swing detector with hierarchical model.

    Processes one bar at a time via process_bar(). Calibration is just
    a loop calling process_bar() — no special batch logic.

    Key design principles:
    1. No lookahead — Algorithm only sees current and past bars
    2. Single code path — Calibration will just call this in a loop
    3. Independent invalidation — Each swing checks its own defended pivot
    4. DAG hierarchy — Swings can have multiple parents for structural context

    Example:
        >>> config = SwingConfig.default()
        >>> detector = HierarchicalDetector(config)
        >>> for bar in bars:
        ...     events = detector.process_bar(bar)
        ...     for event in events:
        ...         print(event.event_type, event.swing_id)
        >>> state = detector.get_state()
        >>> # Resume later
        >>> detector2 = HierarchicalDetector.from_state(state, config)
    """

    def __init__(
        self,
        config: SwingConfig = None,
        source_bars: Optional[List[Bar]] = None,
        source_resolution_minutes: int = 5,
    ):
        """
        Initialize detector with configuration.

        Args:
            config: SwingConfig with detection parameters.
                   If None, uses SwingConfig.default().
            source_bars: Optional list of source bars for multi-timeframe candidate
                        generation. When provided, enables performance optimization
                        that uses higher-timeframe bars (1h, 4h, 1d) as candidates
                        instead of all source bars.
            source_resolution_minutes: Resolution of source bars in minutes (default: 5).
                        Used for BarAggregator initialization.
        """
        self.config = config or SwingConfig.default()
        self.state = DetectorState()

        # Multi-timeframe candidate generation
        self.aggregator: Optional[BarAggregator] = None
        self._use_multi_tf = False

        if source_bars and len(source_bars) > 0:
            try:
                self.aggregator = BarAggregator(source_bars, source_resolution_minutes)
                self._use_multi_tf = True
            except ValueError:
                # Fall back to original behavior if aggregator can't be initialized
                self.aggregator = None
                self._use_multi_tf = False

    def process_bar(self, bar: Bar) -> List[SwingEvent]:
        """
        Process a single bar. Returns events generated.

        Order of operations:
        1. Check invalidations (independent per swing)
        2. Check completions
        3. Check level crosses
        4. Update candidate extrema (sliding window)
        5. Try to form new swings

        Args:
            bar: The bar to process (Bar dataclass from types.py)

        Returns:
            List of SwingEvent subclasses generated by this bar.
        """
        events: List[SwingEvent] = []
        self.state.last_bar_index = bar.index

        # Create timestamp from bar
        timestamp = datetime.fromtimestamp(bar.timestamp) if bar.timestamp else datetime.now()

        # 1. Check invalidations
        events.extend(self._check_invalidations(bar, timestamp))

        # 2. Check completions
        events.extend(self._check_completions(bar, timestamp))

        # 3. Check level crosses
        events.extend(self._check_level_crosses(bar, timestamp))

        # 4. Update candidates
        self._update_candidates(bar)

        # 5. Try to form new swings
        events.extend(self._try_form_swings(bar, timestamp))

        return events

    def _check_invalidations(
        self, bar: Bar, timestamp: datetime
    ) -> List[SwingInvalidatedEvent]:
        """
        Check each active swing for defended pivot violation.

        Uses tolerance based on distance to big swing per Rule 2.2.
        Includes quick rejection to avoid creating ReferenceFrame for
        swings that can't possibly be invalidated by this bar.

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of SwingInvalidatedEvent for any invalidated swings.
        """
        events = []
        # Pre-convert bar prices once
        bar_low = Decimal(str(bar.low))
        bar_high = Decimal(str(bar.high))

        for swing in self.state.active_swings:
            if swing.status != "active":
                continue

            # Quick rejection: can this swing possibly be invalidated?
            # Avoid expensive tolerance lookup and ReferenceFrame creation
            # if the bar's price can't possibly violate the defended pivot.
            if swing.is_bull:
                # Bull swing: invalidated if bar.low violates defended low
                # Quick check: if bar.low >= defended_pivot, can't be invalidated
                if bar_low >= swing.defended_pivot:
                    continue
            else:
                # Bear swing: invalidated if bar.high violates defended high
                # Quick check: if bar.high <= defended_pivot, can't be invalidated
                if bar_high <= swing.defended_pivot:
                    continue

            # Passed quick check - now do full invalidation check
            check_price = bar_low if swing.is_bull else bar_high
            tolerance = self._get_tolerance(swing)

            # Full check with tolerance using ReferenceFrame
            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            if frame.is_violated(check_price, tolerance):
                swing.invalidate()
                excess = abs(check_price - swing.defended_pivot)
                events.append(
                    SwingInvalidatedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        violation_price=check_price,
                        excess_amount=excess,
                    )
                )

        return events

    def _check_completions(
        self, bar: Bar, timestamp: datetime
    ) -> List[SwingCompletedEvent]:
        """
        Check each active swing for 2.0 target reached.

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of SwingCompletedEvent for any completed swings.
        """
        events = []
        for swing in self.state.active_swings:
            if swing.status != "active":
                continue

            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            # Check price: high for bull (checking if 2.0 extension is reached above)
            # low for bear (checking if 2.0 extension is reached below)
            check_price = Decimal(str(bar.high if swing.is_bull else bar.low))

            if frame.is_completed(check_price):
                swing.complete()
                events.append(
                    SwingCompletedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        completion_price=check_price,
                    )
                )

        return events

    def _check_level_crosses(
        self, bar: Bar, timestamp: datetime
    ) -> List[LevelCrossEvent]:
        """
        Check each active swing for Fib level crosses.

        Tracks the last level for each swing and emits events when
        the current price crosses into a new level band.

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of LevelCrossEvent for any level crosses.
        """
        events = []
        for swing in self.state.active_swings:
            if swing.status != "active":
                continue

            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            # Use close price for level cross tracking
            close_price = Decimal(str(bar.close))
            current_ratio = float(frame.ratio(close_price))

            # Find current level band
            current_level = self._find_level_band(current_ratio)
            previous_level = self.state.fib_levels_crossed.get(
                swing.swing_id, current_level
            )

            if current_level != previous_level:
                events.append(
                    LevelCrossEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        level=current_level,
                        previous_level=previous_level,
                        price=close_price,
                    )
                )
                self.state.fib_levels_crossed[swing.swing_id] = current_level

        return events

    def _find_level_band(self, ratio: float) -> float:
        """
        Find the Fib level band for a given ratio.

        Returns the highest Fib level that is <= the ratio.

        Args:
            ratio: Current ratio in the reference frame.

        Returns:
            The Fib level band (e.g., 0.382, 0.618, etc.)
        """
        level = FIB_LEVELS[0]
        for fib in FIB_LEVELS:
            if ratio >= fib:
                level = fib
            else:
                break
        return level

    def _update_candidates(self, bar: Bar) -> None:
        """
        Update sliding window of candidate extrema.

        Uses multi-timeframe candidate generation when aggregator is available
        (source_bars provided at init). Falls back to original behavior otherwise.

        Args:
            bar: Current bar being processed.
        """
        if self._use_multi_tf:
            self._update_candidates_multi_tf(bar)
        else:
            self._update_candidates_original(bar)

    def _update_candidates_original(self, bar: Bar) -> None:
        """
        Original candidate tracking: all bars in lookback window.

        Args:
            bar: Current bar being processed.
        """
        lookback = self.config.lookback_bars
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))

        # Add current bar's extrema
        self.state.candidate_highs.append((bar.index, bar_high))
        self.state.candidate_lows.append((bar.index, bar_low))

        # Remove old candidates outside lookback window
        # Keep lookback_bars worth of history (current bar + lookback-1 previous)
        cutoff = bar.index - lookback + 1
        self.state.candidate_highs = [
            (idx, price) for idx, price in self.state.candidate_highs if idx >= cutoff
        ]
        self.state.candidate_lows = [
            (idx, price) for idx, price in self.state.candidate_lows if idx >= cutoff
        ]

    def _update_candidates_multi_tf(self, bar: Bar) -> None:
        """
        Multi-timeframe candidate tracking for performance optimization.

        Instead of tracking all source bars, uses completed higher-timeframe
        bars (1h, 4h, 1d) as candidates. A 1h bar's high/low is the true
        maximum/minimum of 12 5m bars — a natural "dominant extremum".

        Key insight: Valid swing origins must be local maxima. If a 5m high
        is NOT a 1h high, it was exceeded within that hour, which means
        any swing using it as origin would violate Rule 2.1 (pre-formation).

        Causality: Only COMPLETED higher-TF bars are used. A 1h bar covering
        10:00-10:59 is complete only after the 10:55 5m bar.

        Hybrid approach: For short datasets or early bars before any higher-TF
        bars complete, also track source bars to ensure swing formation can occur.

        Args:
            bar: Current bar being processed.
        """
        if not self.aggregator:
            return self._update_candidates_original(bar)

        tf_candidates_added = 0

        # Check each higher timeframe for newly completed bars
        for tf_minutes in MULTI_TF_TIMEFRAMES:
            # Skip timeframes not available in aggregator
            if tf_minutes not in self.aggregator.available_timeframes:
                continue

            # Get the most recently CLOSED bar at this timeframe
            closed_bar = self.aggregator.get_closed_bar_at_source_time(
                tf_minutes, bar.index
            )

            if closed_bar is None:
                continue

            # Check if we've already processed this TF bar
            if closed_bar.index in self.state.seen_tf_bars[tf_minutes]:
                continue

            # Mark as seen
            self.state.seen_tf_bars[tf_minutes].add(closed_bar.index)
            tf_candidates_added += 1

            # Get the last source bar index covered by this TF bar
            # This preserves temporal ordering for swing formation
            # Pass current bar.index for causality (no lookahead)
            last_source_idx = self._get_last_source_idx_for_tf_bar(
                closed_bar, tf_minutes, bar.index
            )

            # Add this bar's extrema as candidates
            self.state.candidate_highs.append(
                (last_source_idx, Decimal(str(closed_bar.high)))
            )
            self.state.candidate_lows.append(
                (last_source_idx, Decimal(str(closed_bar.low)))
            )

        # Hybrid fallback: For short datasets or periods without TF bar completions,
        # also track source bars to ensure swings can form. This maintains the
        # performance benefit for large datasets while ensuring correctness for
        # small datasets or early calibration.
        # Keep a small window of recent source bars as candidates.
        total_tf_bars_seen = sum(len(bars) for bars in self.state.seen_tf_bars.values())
        if total_tf_bars_seen < 3:
            # Not enough TF bars yet - use source bar tracking as fallback
            bar_high = Decimal(str(bar.high))
            bar_low = Decimal(str(bar.low))
            self.state.candidate_highs.append((bar.index, bar_high))
            self.state.candidate_lows.append((bar.index, bar_low))

        # Prune old TF candidates based on per-TF lookback limits
        self._prune_old_tf_candidates()

    def _get_last_source_idx_for_tf_bar(
        self, tf_bar: Bar, tf_minutes: int, current_bar_index: int
    ) -> int:
        """
        Get the last source bar index covered by a timeframe bar.

        This is needed for temporal ordering in swing formation — the candidate's
        index must reflect when the extremum was "confirmed" (at the close of
        the higher-TF bar).

        IMPORTANT: To maintain causality (no lookahead), we limit the result to
        be at most the current bar index. The aggregator mapping might contain
        future information, but we only use what we've processed so far.

        Args:
            tf_bar: The timeframe bar.
            tf_minutes: Timeframe in minutes.
            current_bar_index: The current bar being processed (for causality).

        Returns:
            The last source bar index that maps to this TF bar, limited to
            current_bar_index for causality.
        """
        if not self.aggregator:
            return min(tf_bar.index, current_bar_index)

        mapping = self.aggregator._source_to_agg_mapping.get(tf_minutes, {})

        # Find max source index that maps to this TF bar, but limit to what
        # we've processed so far to avoid lookahead
        max_source_idx = 0
        for source_idx, agg_idx in mapping.items():
            if agg_idx == tf_bar.index and source_idx <= current_bar_index:
                max_source_idx = max(max_source_idx, source_idx)

        return max_source_idx

    def _prune_old_tf_candidates(self) -> None:
        """
        Remove candidates from TF bars older than their respective lookbacks.

        Each timeframe has its own lookback limit:
        - 1h: 12 bars (12 hours of candidates)
        - 4h: 6 bars (24 hours)
        - 1d: 5 bars (5 days)

        This naturally scales the candidate window with timeframe importance.
        """
        # Prune seen_tf_bars based on lookback limits
        for tf_minutes, max_count in MULTI_TF_LOOKBACKS.items():
            if len(self.state.seen_tf_bars[tf_minutes]) > max_count * 2:
                # Remove oldest entries
                sorted_bars = sorted(self.state.seen_tf_bars[tf_minutes])
                to_remove = sorted_bars[:-max_count]
                for bar_idx in to_remove:
                    self.state.seen_tf_bars[tf_minutes].discard(bar_idx)

        # Also limit total candidates to prevent unbounded growth
        # Keep roughly 50 candidates per side (similar to original lookback)
        max_candidates = 50
        if len(self.state.candidate_highs) > max_candidates * 2:
            # Keep the most recent candidates by source index
            self.state.candidate_highs = sorted(
                self.state.candidate_highs, key=lambda x: x[0]
            )[-max_candidates:]
        if len(self.state.candidate_lows) > max_candidates * 2:
            self.state.candidate_lows = sorted(
                self.state.candidate_lows, key=lambda x: x[0]
            )[-max_candidates:]

    def _try_form_swings(
        self, bar: Bar, timestamp: datetime
    ) -> List[SwingFormedEvent]:
        """
        Try to form new swings from candidate extrema.

        For bull swings: high (origin) occurs before low (defended pivot)
        For bear swings: low (origin) occurs before high (defended pivot)

        Args:
            bar: Current bar being processed.
            timestamp: Timestamp for events.

        Returns:
            List of SwingFormedEvent for any newly formed swings.
        """
        events: List[SwingFormedEvent] = []
        close_price = Decimal(str(bar.close))

        # Try bull swings: high (origin) before low (defended pivot)
        bull_events = self._try_form_direction_swings(
            bar, timestamp, close_price, "bull"
        )
        events.extend(bull_events)

        # Try bear swings: low (origin) before high (defended pivot)
        bear_events = self._try_form_direction_swings(
            bar, timestamp, close_price, "bear"
        )
        events.extend(bear_events)

        return events

    def _try_form_direction_swings(
        self,
        bar: Bar,
        timestamp: datetime,
        close_price: Decimal,
        direction: str,
    ) -> List[SwingFormedEvent]:
        """
        Try to form swings for one direction.

        Args:
            bar: Current bar.
            timestamp: Event timestamp.
            close_price: Current close price.
            direction: "bull" or "bear".

        Returns:
            List of SwingFormedEvent for newly formed swings.
        """
        events = []
        config = self.config.bull if direction == "bull" else self.config.bear

        if direction == "bull":
            # Bull: origin (high) before defended pivot (low)
            origins = self.state.candidate_highs
            pivots = self.state.candidate_lows
        else:
            # Bear: origin (low) before defended pivot (high)
            origins = self.state.candidate_lows
            pivots = self.state.candidate_highs

        # Find best candidate pairs
        formation_threshold = Decimal(str(config.formation_fib))

        for origin_idx, origin_price in origins:
            for pivot_idx, pivot_price in pivots:
                # Origin must come before pivot
                if origin_idx >= pivot_idx:
                    continue

                # Skip if range is effectively zero
                swing_range = abs(origin_price - pivot_price)
                if swing_range == 0:
                    continue

                # Inline formation check (avoids creating ReferenceFrame for rejected pairs)
                # For bull: ratio = (close - pivot) / range, check >= formation_fib
                # For bear: ratio = (pivot - close) / range, check >= formation_fib
                if direction == "bull":
                    ratio = (close_price - pivot_price) / swing_range
                else:
                    ratio = (pivot_price - close_price) / swing_range
                if ratio < formation_threshold:
                    continue

                # Check pre-formation protection (ABSOLUTE, no tolerance - Rule 2.1)
                if not self._check_pre_formation(bar, origin_idx, pivot_idx, origin_price, pivot_price, direction):
                    continue

                # Check separation from existing swings (Rule 4)
                if not self._check_separation(origin_price, pivot_price, swing_range, direction, config):
                    continue

                # Check for duplicate - don't form same swing twice
                if self._swing_exists(origin_idx, pivot_idx, direction):
                    continue

                # Form the swing
                if direction == "bull":
                    swing = SwingNode(
                        swing_id=SwingNode.generate_id(),
                        high_bar_index=origin_idx,
                        high_price=origin_price,
                        low_bar_index=pivot_idx,
                        low_price=pivot_price,
                        direction="bull",
                        status="active",
                        formed_at_bar=bar.index,
                    )
                else:
                    swing = SwingNode(
                        swing_id=SwingNode.generate_id(),
                        high_bar_index=pivot_idx,
                        high_price=pivot_price,
                        low_bar_index=origin_idx,
                        low_price=origin_price,
                        direction="bear",
                        status="active",
                        formed_at_bar=bar.index,
                    )

                # Find parents (active swings where this fits in their 0-2 range)
                parents = self._find_parents(swing)
                for parent in parents:
                    swing.add_parent(parent)

                # Track swing range for big swing calculations
                self.state.all_swing_ranges.append(swing.range)
                # Invalidate threshold cache since swing ranges changed
                self.state._threshold_valid = False
                self.state.active_swings.append(swing)

                # Initialize level tracking (reuse already-computed ratio)
                self.state.fib_levels_crossed[swing.swing_id] = self._find_level_band(
                    float(ratio)
                )

                events.append(
                    SwingFormedEvent(
                        bar_index=bar.index,
                        timestamp=timestamp,
                        swing_id=swing.swing_id,
                        high_bar_index=swing.high_bar_index,
                        high_price=swing.high_price,
                        low_bar_index=swing.low_bar_index,
                        low_price=swing.low_price,
                        direction=swing.direction,
                        parent_ids=[p.swing_id for p in parents],
                    )
                )

        return events

    def _check_pre_formation(
        self,
        bar: Bar,
        origin_idx: int,
        pivot_idx: int,
        origin_price: Decimal,
        pivot_price: Decimal,
        direction: str,
    ) -> bool:
        """
        Check pre-formation protection (Rule 2.1).

        NO tolerance - any violation rejects candidate. For the bars between
        origin and defended pivot, verify neither endpoint was exceeded.

        Args:
            bar: Current bar.
            origin_idx: Bar index of origin.
            pivot_idx: Bar index of defended pivot.
            origin_price: Price of origin.
            pivot_price: Price of defended pivot.
            direction: "bull" or "bear".

        Returns:
            True if pre-formation check passes, False if violated.
        """
        if direction == "bull":
            # Bull: origin is high, pivot is low
            # Check no high in between exceeded origin
            # Check no low in between undercut pivot
            for idx, price in self.state.candidate_highs:
                if origin_idx < idx < pivot_idx and price > origin_price:
                    return False
            for idx, price in self.state.candidate_lows:
                if origin_idx < idx < pivot_idx and price < pivot_price:
                    return False
        else:
            # Bear: origin is low, pivot is high
            # Check no low in between undercut origin
            # Check no high in between exceeded pivot
            for idx, price in self.state.candidate_lows:
                if origin_idx < idx < pivot_idx and price < origin_price:
                    return False
            for idx, price in self.state.candidate_highs:
                if origin_idx < idx < pivot_idx and price > pivot_price:
                    return False

        return True

    def _check_separation(
        self,
        origin_price: Decimal,
        pivot_price: Decimal,
        swing_range: Decimal,
        direction: str,
        config: DirectionConfig,
    ) -> bool:
        """
        Check separation from existing swings (Rule 4).

        Ensures the new swing's endpoints are sufficiently separated from
        existing swings to be structurally meaningful.

        Args:
            origin_price: Price of the new swing's origin.
            pivot_price: Price of the new swing's defended pivot.
            swing_range: Range of the new swing.
            direction: "bull" or "bear".
            config: DirectionConfig with separation parameters.

        Returns:
            True if separation is sufficient, False otherwise.
        """
        min_separation = Decimal(str(config.self_separation)) * swing_range

        for swing in self.state.active_swings:
            if swing.status != "active":
                continue
            if swing.direction != direction:
                continue

            # Check origin separation
            origin_distance = abs(origin_price - swing.origin)
            if origin_distance < min_separation:
                return False

            # Check pivot separation
            pivot_distance = abs(pivot_price - swing.defended_pivot)
            if pivot_distance < min_separation:
                return False

        return True

    def _swing_exists(self, origin_idx: int, pivot_idx: int, direction: str) -> bool:
        """
        Check if a swing with these endpoints already exists.

        Args:
            origin_idx: Bar index of origin.
            pivot_idx: Bar index of defended pivot.
            direction: "bull" or "bear".

        Returns:
            True if such a swing already exists in active_swings.
        """
        for swing in self.state.active_swings:
            if swing.direction != direction:
                continue
            if direction == "bull":
                if swing.high_bar_index == origin_idx and swing.low_bar_index == pivot_idx:
                    return True
            else:
                if swing.low_bar_index == origin_idx and swing.high_bar_index == pivot_idx:
                    return True
        return False

    def _find_parents(self, new_swing: SwingNode) -> List[SwingNode]:
        """
        Find parent swings for a new swing.

        A swing is a parent if the new swing's defended pivot is within
        the parent's 0-2 range.

        Args:
            new_swing: The newly formed swing.

        Returns:
            List of parent SwingNode objects.
        """
        parents = []
        new_pivot = new_swing.defended_pivot

        for swing in self.state.active_swings:
            if swing.status != "active":
                continue
            if swing.swing_id == new_swing.swing_id:
                continue

            frame = ReferenceFrame(
                anchor0=swing.defended_pivot,
                anchor1=swing.origin,
                direction="BULL" if swing.is_bull else "BEAR",
            )

            ratio = frame.ratio(new_pivot)
            # Parent if new swing's pivot is in 0-2 range
            if Decimal("0") <= ratio <= Decimal("2"):
                parents.append(swing)

        return parents

    def _get_tolerance(self, swing: SwingNode) -> float:
        """
        Get invalidation tolerance based on distance to big swing (Rule 2.2).

        - Big swing (top 10% by range): full tolerance (0.15 price)
        - Child of big swing: basic tolerance (0.10)
        - Other: no tolerance (0)

        Args:
            swing: The swing to get tolerance for.

        Returns:
            Tolerance as fraction of range.
        """
        config = self.config.bull if swing.is_bull else self.config.bear
        distance = self._distance_to_big_swing(swing, config)

        if distance == 0:
            # Big swing itself - full tolerance
            return config.big_swing_price_tolerance
        elif distance <= 2:
            # Child or grandchild of big swing - basic tolerance
            return config.child_swing_tolerance
        else:
            # No big swing ancestor - absolute (no tolerance)
            return 0.0

    def _distance_to_big_swing(
        self, swing: SwingNode, config: DirectionConfig
    ) -> int:
        """
        Calculate hierarchy distance to nearest big swing ancestor.

        Returns:
            0 if swing itself is big
            1 if parent is big
            2 if grandparent is big
            999 if no big swing ancestor within 2 levels
        """
        if self._is_big_swing(swing, config):
            return 0

        for parent in swing.parents:
            if self._is_big_swing(parent, config):
                return 1
            for grandparent in parent.parents:
                if self._is_big_swing(grandparent, config):
                    return 2

        return 999

    def _update_big_threshold_cache(self) -> None:
        """
        Recompute cached big swing thresholds.

        This is called when the cache is invalidated (after a new swing forms).
        Sorting all_swing_ranges once and caching the thresholds avoids
        repeated O(n log n) sorts in _is_big_swing().
        """
        if not self.state.all_swing_ranges:
            self.state._cached_big_threshold_bull = Decimal("0")
            self.state._cached_big_threshold_bear = Decimal("0")
        else:
            sorted_ranges = sorted(self.state.all_swing_ranges, reverse=True)

            # Bull threshold
            bull_idx = int(len(sorted_ranges) * self.config.bull.big_swing_threshold)
            bull_idx = max(0, min(bull_idx, len(sorted_ranges) - 1))
            self.state._cached_big_threshold_bull = sorted_ranges[bull_idx]

            # Bear threshold
            bear_idx = int(len(sorted_ranges) * self.config.bear.big_swing_threshold)
            bear_idx = max(0, min(bear_idx, len(sorted_ranges) - 1))
            self.state._cached_big_threshold_bear = sorted_ranges[bear_idx]

        self.state._threshold_valid = True

    def _is_big_swing(self, swing: SwingNode, config: DirectionConfig) -> bool:
        """
        Check if swing is a "big swing" (top percentile by range).

        Big swings are those whose range is in the top X% of all swings,
        where X is determined by config.big_swing_threshold.

        Uses cached thresholds to avoid O(n log n) sort on every call.

        Args:
            swing: The swing to check.
            config: DirectionConfig with big_swing_threshold.

        Returns:
            True if swing is in top percentile by range.
        """
        if not self.state.all_swing_ranges:
            return False

        # Recompute cache if invalidated
        if not self.state._threshold_valid:
            self._update_big_threshold_cache()

        # Use cached threshold based on swing direction
        threshold = (
            self.state._cached_big_threshold_bull
            if swing.is_bull
            else self.state._cached_big_threshold_bear
        )

        return swing.range >= threshold

    def get_active_swings(self) -> List[SwingNode]:
        """
        Get all currently active swings.

        Returns:
            List of SwingNode with status "active".
        """
        return [s for s in self.state.active_swings if s.status == "active"]

    def get_state(self) -> DetectorState:
        """
        Get serializable state for persistence.

        Returns:
            DetectorState that can be serialized to JSON.
        """
        return self.state

    @classmethod
    def from_state(
        cls, state: DetectorState, config: SwingConfig = None
    ) -> "HierarchicalDetector":
        """
        Restore from serialized state.

        Args:
            state: DetectorState to restore from.
            config: SwingConfig to use (defaults to default config).

        Returns:
            HierarchicalDetector initialized with the given state.
        """
        detector = cls(config)
        detector.state = state
        return detector


def calibrate(
    bars: List[Bar],
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    source_resolution_minutes: int = 5,
) -> Tuple["HierarchicalDetector", List[SwingEvent]]:
    """
    Run detection on historical bars.

    This is process_bar() in a loop — guarantees identical behavior
    to incremental playback. When called with bars, enables multi-timeframe
    candidate generation for improved performance.

    Args:
        bars: Historical bars to process.
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.
        source_resolution_minutes: Resolution of source bars in minutes (default: 5).
            Used for multi-timeframe aggregation.

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> bars = [Bar(index=i, ...) for i in range(1000)]
        >>> detector, events = calibrate(bars)
        >>> print(f"Found {len(detector.get_active_swings())} active swings")
        >>> # Continue processing new bars
        >>> new_events = detector.process_bar(new_bar)

        >>> # With progress callback
        >>> def on_progress(current, total):
        ...     print(f"Processing bar {current}/{total}")
        >>> detector, events = calibrate(bars, progress_callback=on_progress)
    """
    config = config or SwingConfig.default()

    # Initialize detector with source bars for multi-TF optimization
    detector = HierarchicalDetector(
        config, source_bars=bars, source_resolution_minutes=source_resolution_minutes
    )
    all_events: List[SwingEvent] = []
    total = len(bars)

    for i, bar in enumerate(bars):
        events = detector.process_bar(bar)
        all_events.extend(events)

        if progress_callback:
            progress_callback(i + 1, total)

    return detector, all_events


def dataframe_to_bars(df: pd.DataFrame) -> List[Bar]:
    """
    Convert DataFrame with OHLC columns to Bar list.

    Handles various column naming conventions commonly used in market data.

    Args:
        df: DataFrame with OHLC columns. Expects columns like:
            - open/Open, high/High, low/Low, close/Close
            - Optional: timestamp/date/time

    Returns:
        List of Bar objects suitable for process_bar() or calibrate().

    Example:
        >>> df = pd.read_csv("market_data.csv")
        >>> bars = dataframe_to_bars(df)
        >>> detector, events = calibrate(bars)
    """
    bars = []

    # Normalize column names to lowercase for consistent access
    col_map = {c.lower(): c for c in df.columns}

    for idx, row in df.iterrows():
        # Get timestamp - try various column names
        timestamp = None
        for ts_col in ["timestamp", "time", "date", "datetime"]:
            if ts_col in col_map:
                ts_value = row[col_map[ts_col]]
                # Convert to Unix timestamp if needed
                if isinstance(ts_value, (int, float)):
                    timestamp = float(ts_value)
                elif hasattr(ts_value, "timestamp"):
                    timestamp = ts_value.timestamp()
                break

        # Default timestamp if not found
        if timestamp is None:
            timestamp = 1700000000 + len(bars) * 60  # Generate sequential timestamps

        # Get OHLC values
        open_price = float(row[col_map.get("open", "open")])
        high_price = float(row[col_map.get("high", "high")])
        low_price = float(row[col_map.get("low", "low")])
        close_price = float(row[col_map.get("close", "close")])

        bars.append(
            Bar(
                index=idx if isinstance(idx, int) else len(bars),
                timestamp=int(timestamp),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
            )
        )

    return bars


def calibrate_from_dataframe(
    df: pd.DataFrame,
    config: SwingConfig = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    source_resolution_minutes: int = 5,
) -> Tuple["HierarchicalDetector", List[SwingEvent]]:
    """
    Convenience wrapper for DataFrame input.

    Converts DataFrame to Bar list and runs calibration.

    Args:
        df: DataFrame with OHLC columns (open, high, low, close).
        config: Detection configuration (defaults to SwingConfig.default()).
        progress_callback: Optional callback(current, total) for progress reporting.
        source_resolution_minutes: Resolution of source bars in minutes (default: 5).
            Used for multi-timeframe aggregation.

    Returns:
        Tuple of (detector with state, all events generated).

    Example:
        >>> import pandas as pd
        >>> df = pd.read_csv("ES-5m.csv")
        >>> detector, events = calibrate_from_dataframe(df)
        >>> print(f"Detected {len(detector.get_active_swings())} active swings")
    """
    bars = dataframe_to_bars(df)
    return calibrate(bars, config, progress_callback, source_resolution_minutes)
