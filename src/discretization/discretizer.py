"""
Discretizer: Batch processor that converts OHLC + detected swings into structural event log.

Design principles:
- Batch-only (no streaming state between calls)
- Per-scale independence (no cross-scale coupling encoded in core logic)
- Config-driven levels and semantics (corpus comparability)
- Side-channels (effort, shock, parent context) for hypothesis testing

The discretizer logs events representing structural changes:
- LEVEL_CROSS: Price crossed a Fibonacci level
- LEVEL_TEST: Price approached but didn't cross a level
- COMPLETION: Price reached 2.0 extension
- INVALIDATION: Price crossed below threshold
- SWING_FORMED: New swing registered
- SWING_TERMINATED: Swing ended (completed or invalidated)
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Any, Deque, Dict, List, Literal, Optional, Tuple
import uuid

import pandas as pd

from .schema import (
    DiscretizationConfig,
    DiscretizationEvent,
    DiscretizationLog,
    DiscretizationMeta,
    EffortAnnotation,
    EventType,
    ParentContext,
    ShockAnnotation,
    SwingEntry,
)
from ..swing_analysis.constants import (
    DISCRETIZATION_LEVELS,
    DISCRETIZATION_LEVEL_SET_VERSION,
)
from ..swing_analysis.reference_frame import ReferenceFrame
from ..swing_analysis.swing_detector import ReferenceSwing


# Version identifier for discretizer implementation
DISCRETIZER_VERSION = "1.0"

# Default swing detector version (should be updated when detector changes)
DEFAULT_SWING_DETECTOR_VERSION = "v2.3"


@dataclass
class DiscretizerConfig:
    """
    Runtime configuration for discretization.

    Contains all tunable parameters for discretization runs.
    Converted to DiscretizationConfig for storage in output log.
    """

    # Level set configuration
    level_set: List[float] = field(default_factory=lambda: list(DISCRETIZATION_LEVELS))
    level_set_version: str = DISCRETIZATION_LEVEL_SET_VERSION

    # Crossing detection semantics
    crossing_semantics: Literal["close_cross", "open_close_cross", "wick_touch"] = "close_cross"
    crossing_tolerance_pct: float = 0.001  # 0.1% of swing size

    # Invalidation thresholds per scale (ratio below which swing is invalidated)
    invalidation_thresholds: Dict[str, float] = field(
        default_factory=lambda: {"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15}
    )

    # Rolling window sizes for range_multiple calculation
    rolling_window_sizes: Dict[str, int] = field(
        default_factory=lambda: {"S": 20, "M": 50, "L": 100, "XL": 200}
    )

    # Gap detection threshold (as fraction of price)
    gap_threshold_pct: float = 0.005  # 0.5% of price

    # Version tracking
    swing_detector_version: str = DEFAULT_SWING_DETECTOR_VERSION
    discretizer_version: str = DISCRETIZER_VERSION

    def to_output_config(self) -> DiscretizationConfig:
        """Convert to DiscretizationConfig for output log storage."""
        return DiscretizationConfig(
            level_set=self.level_set,
            level_set_version=self.level_set_version,
            crossing_semantics=self.crossing_semantics,
            crossing_tolerance_pct=self.crossing_tolerance_pct,
            invalidation_thresholds=self.invalidation_thresholds,
            swing_detector_version=self.swing_detector_version,
            discretizer_version=self.discretizer_version,
        )


@dataclass
class _BandDwellState:
    """Internal state for tracking band dwell time and test patterns."""

    band: str  # Current band (e.g., "0.382-0.5")
    entry_bar: int  # Bar index when entered this band
    test_count: int = 0  # Number of approach-retreat patterns
    max_probe_r: Optional[float] = None  # Deepest excursion past band boundary


@dataclass
class _ActiveSwingState:
    """Internal state for tracking an active swing during discretization."""

    swing_entry: SwingEntry
    frame: ReferenceFrame
    previous_ratio: Optional[float] = None
    previous_band: Optional[str] = None
    dwell_state: Optional[_BandDwellState] = None
    terminated: bool = False


def _get_band(ratio: float, level_set: List[float]) -> str:
    """
    Determine which Fibonacci band a ratio falls into.

    Args:
        ratio: The ratio value
        level_set: Sorted list of Fibonacci levels

    Returns:
        Band string in format "lower-upper" (e.g., "0.382-0.5")
    """
    sorted_levels = sorted(level_set)

    # Below lowest level
    if ratio < sorted_levels[0]:
        return f"<{sorted_levels[0]}"

    # Above highest level
    if ratio >= sorted_levels[-1]:
        return f">={sorted_levels[-1]}"

    # Find the band
    for i in range(len(sorted_levels) - 1):
        if sorted_levels[i] <= ratio < sorted_levels[i + 1]:
            return f"{sorted_levels[i]}-{sorted_levels[i + 1]}"

    return "unknown"


def _levels_between(
    from_ratio: float, to_ratio: float, level_set: List[float], tolerance: float
) -> List[float]:
    """
    Find all levels crossed when moving from one ratio to another.

    Args:
        from_ratio: Starting ratio
        to_ratio: Ending ratio
        level_set: List of Fibonacci levels to check
        tolerance: Tolerance for level crossing detection

    Returns:
        List of levels crossed, in order of crossing
    """
    if abs(from_ratio - to_ratio) < tolerance:
        return []

    crossed = []
    direction = 1 if to_ratio > from_ratio else -1

    for level in sorted(level_set):
        # Check if level is between from_ratio and to_ratio
        if direction > 0:
            # Moving up: level must be > from_ratio and <= to_ratio
            if from_ratio + tolerance < level <= to_ratio + tolerance:
                crossed.append(level)
        else:
            # Moving down: level must be < from_ratio and >= to_ratio
            if to_ratio - tolerance <= level < from_ratio - tolerance:
                crossed.append(level)

    # Order by crossing sequence
    if direction < 0:
        crossed.reverse()

    return crossed


class Discretizer:
    """
    Batch discretizer: OHLC + swings → structural event log.

    Design principles:
    - Batch-only (no streaming state between calls)
    - Per-scale independence (no cross-scale coupling encoded)
    - Config-driven levels and semantics (corpus comparability)
    - No lookahead (uses only data up to current bar)

    Usage:
        config = DiscretizerConfig()
        discretizer = Discretizer(config)
        log = discretizer.discretize(ohlc_df, swings_by_scale, instrument="ES")
    """

    def __init__(self, config: Optional[DiscretizerConfig] = None):
        """
        Initialize the discretizer.

        Args:
            config: Configuration for discretization. Uses defaults if not provided.
        """
        self.config = config or DiscretizerConfig()

    def discretize(
        self,
        ohlc: pd.DataFrame,
        swings: Dict[str, List[ReferenceSwing]],
        instrument: str = "unknown",
        source_resolution: str = "1m",
    ) -> DiscretizationLog:
        """
        Process OHLC and swings into event log.

        Args:
            ohlc: DataFrame with columns: timestamp, open, high, low, close
                  Index should be sequential bar indices.
            swings: Dict mapping scale ("XL", "L", "M", "S") to list of ReferenceSwing
            instrument: Instrument identifier (e.g., "ES")
            source_resolution: Source data resolution (e.g., "1m", "5m")

        Returns:
            DiscretizationLog with all events and swing entries
        """
        # Initialize state
        events: List[DiscretizationEvent] = []
        swing_entries: List[SwingEntry] = []
        active_swings: Dict[str, _ActiveSwingState] = {}  # swing_id -> state

        # Rolling range windows per scale for shock calculation
        rolling_windows: Dict[str, Deque[float]] = {
            scale: deque(maxlen=size)
            for scale, size in self.config.rolling_window_sizes.items()
        }

        # Track which swings are active at each scale (for parent context)
        active_by_scale: Dict[str, Optional[_ActiveSwingState]] = {
            "XL": None,
            "L": None,
            "M": None,
            "S": None,
        }

        # Build swing lookup by formation bar
        swings_by_bar: Dict[int, List[Tuple[str, ReferenceSwing]]] = {}
        for scale, swing_list in swings.items():
            for swing in swing_list:
                formed_bar = max(swing.high_bar_index, swing.low_bar_index)
                if formed_bar not in swings_by_bar:
                    swings_by_bar[formed_bar] = []
                swings_by_bar[formed_bar].append((scale, swing))

        # Tolerance for level crossing
        # (will be computed per-swing based on swing size)

        # Get date range from OHLC
        if len(ohlc) == 0:
            date_start = ""
            date_end = ""
        else:
            date_start = self._format_timestamp(ohlc.iloc[0]["timestamp"])
            date_end = self._format_timestamp(ohlc.iloc[-1]["timestamp"])

        prev_close = None

        # Process each bar
        for bar_idx, row in ohlc.iterrows():
            bar_timestamp = row["timestamp"]
            bar_open = float(row["open"])
            bar_high = float(row["high"])
            bar_low = float(row["low"])
            bar_close = float(row["close"])
            bar_range = bar_high - bar_low

            timestamp_str = self._format_timestamp(bar_timestamp)

            # Detect gap
            is_gap = False
            gap_size = 0.0
            if prev_close is not None:
                gap_size = abs(bar_open - prev_close)
                gap_threshold = prev_close * self.config.gap_threshold_pct
                is_gap = gap_size > gap_threshold

            # Update rolling windows for all scales
            for scale in rolling_windows:
                rolling_windows[scale].append(bar_range)

            # Check for new swings formed at this bar
            if bar_idx in swings_by_bar:
                for scale, swing in swings_by_bar[bar_idx]:
                    swing_id = str(uuid.uuid4())[:8]

                    # Create swing entry
                    direction = "BULL" if swing.direction == "bull" else "BEAR"
                    if direction == "BULL":
                        anchor0 = swing.low_price
                        anchor1 = swing.high_price
                        anchor0_bar = swing.low_bar_index
                        anchor1_bar = swing.high_bar_index
                    else:
                        anchor0 = swing.high_price
                        anchor1 = swing.low_price
                        anchor0_bar = swing.high_bar_index
                        anchor1_bar = swing.low_bar_index

                    entry = SwingEntry(
                        swing_id=swing_id,
                        scale=scale,
                        direction=direction,
                        anchor0=anchor0,
                        anchor1=anchor1,
                        anchor0_bar=anchor0_bar,
                        anchor1_bar=anchor1_bar,
                        formed_at_bar=bar_idx,
                        status="active",
                    )
                    swing_entries.append(entry)

                    # Create reference frame
                    frame = ReferenceFrame(
                        anchor0=Decimal(str(anchor0)),
                        anchor1=Decimal(str(anchor1)),
                        direction=direction,
                    )

                    # Initialize active state
                    state = _ActiveSwingState(
                        swing_entry=entry,
                        frame=frame,
                        previous_ratio=float(frame.ratio(Decimal(str(bar_close)))),
                    )

                    # Initialize band dwell tracking
                    current_ratio = float(frame.ratio(Decimal(str(bar_close))))
                    current_band = _get_band(current_ratio, self.config.level_set)
                    state.previous_band = current_band
                    state.dwell_state = _BandDwellState(band=current_band, entry_bar=bar_idx)

                    active_swings[swing_id] = state
                    active_by_scale[scale] = state

                    # Log SWING_FORMED event
                    events.append(
                        DiscretizationEvent(
                            bar=bar_idx,
                            timestamp=timestamp_str,
                            swing_id=swing_id,
                            event_type=EventType.SWING_FORMED,
                            data={
                                "swing_id": swing_id,
                                "scale": scale,
                                "direction": direction.lower(),
                                "anchor0": anchor0,
                                "anchor1": anchor1,
                            },
                        )
                    )

            # Process each active swing
            for swing_id, state in list(active_swings.items()):
                if state.terminated:
                    continue

                entry = state.swing_entry
                frame = state.frame
                scale = entry.scale

                # Calculate current ratio
                current_ratio = float(frame.ratio(Decimal(str(bar_close))))
                previous_ratio = state.previous_ratio if state.previous_ratio is not None else current_ratio

                # Calculate tolerance based on swing size
                swing_size = abs(float(frame.range))
                tolerance = swing_size * self.config.crossing_tolerance_pct

                # Calculate median range for shock annotation
                if rolling_windows[scale]:
                    median_range = median(rolling_windows[scale])
                else:
                    median_range = bar_range

                range_multiple = bar_range / median_range if median_range > 0 else 1.0
                gap_multiple = gap_size / median_range if is_gap and median_range > 0 else None

                # Determine current band
                current_band = _get_band(current_ratio, self.config.level_set)
                band_changed = current_band != state.previous_band

                # Check for level crossings
                crossed_levels = self._detect_level_crossings(
                    previous_ratio,
                    current_ratio,
                    bar_open,
                    bar_close,
                    bar_high,
                    bar_low,
                    tolerance,
                )

                # Build effort annotation if band changed
                effort = None
                if band_changed and state.dwell_state is not None:
                    dwell_bars = bar_idx - state.dwell_state.entry_bar
                    effort = EffortAnnotation(
                        dwell_bars=dwell_bars,
                        test_count=state.dwell_state.test_count,
                        max_probe_r=state.dwell_state.max_probe_r,
                    )
                    # Reset dwell state for new band
                    state.dwell_state = _BandDwellState(band=current_band, entry_bar=bar_idx)

                # Build shock annotation
                shock = ShockAnnotation(
                    levels_jumped=len(crossed_levels),
                    range_multiple=range_multiple,
                    gap_multiple=gap_multiple,
                    is_gap=is_gap,
                )

                # Build parent context (lookup larger scale swing)
                parent_context = self._get_parent_context(
                    scale, active_by_scale, bar_close
                )

                # Direction of movement
                cross_direction = "up" if current_ratio > previous_ratio else "down"

                # Log level crossings
                for level in crossed_levels:
                    events.append(
                        DiscretizationEvent(
                            bar=bar_idx,
                            timestamp=timestamp_str,
                            swing_id=swing_id,
                            event_type=EventType.LEVEL_CROSS,
                            data={
                                "from_ratio": previous_ratio,
                                "to_ratio": current_ratio,
                                "level_crossed": level,
                                "direction": cross_direction,
                            },
                            effort=effort if level == crossed_levels[0] else None,  # Attach effort to first crossing only
                            shock=shock,
                            parent_context=parent_context,
                        )
                    )

                # Check for completion (ratio >= 2.0)
                if current_ratio >= 2.0 and previous_ratio < 2.0:
                    events.append(
                        DiscretizationEvent(
                            bar=bar_idx,
                            timestamp=timestamp_str,
                            swing_id=swing_id,
                            event_type=EventType.COMPLETION,
                            data={"completion_ratio": current_ratio},
                            effort=effort if not crossed_levels else None,
                            shock=shock,
                            parent_context=parent_context,
                        )
                    )

                    # Log termination
                    events.append(
                        DiscretizationEvent(
                            bar=bar_idx,
                            timestamp=timestamp_str,
                            swing_id=swing_id,
                            event_type=EventType.SWING_TERMINATED,
                            data={"termination_type": "COMPLETED"},
                        )
                    )

                    # Update swing entry
                    entry.status = "completed"
                    entry.terminated_at_bar = bar_idx
                    entry.termination_reason = "completed"
                    state.terminated = True

                    # Clear from active by scale
                    if active_by_scale.get(scale) == state:
                        active_by_scale[scale] = None

                    continue

                # Check for invalidation
                threshold = self.config.invalidation_thresholds.get(scale, -0.10)
                if current_ratio < threshold:
                    events.append(
                        DiscretizationEvent(
                            bar=bar_idx,
                            timestamp=timestamp_str,
                            swing_id=swing_id,
                            event_type=EventType.INVALIDATION,
                            data={
                                "invalidation_ratio": current_ratio,
                                "threshold": threshold,
                            },
                            effort=effort if not crossed_levels else None,
                            shock=shock,
                            parent_context=parent_context,
                        )
                    )

                    # Log termination
                    events.append(
                        DiscretizationEvent(
                            bar=bar_idx,
                            timestamp=timestamp_str,
                            swing_id=swing_id,
                            event_type=EventType.SWING_TERMINATED,
                            data={"termination_type": "INVALIDATED"},
                        )
                    )

                    # Update swing entry
                    entry.status = "invalidated"
                    entry.terminated_at_bar = bar_idx
                    entry.termination_reason = f"invalidated at {current_ratio:.3f}"
                    state.terminated = True

                    # Clear from active by scale
                    if active_by_scale.get(scale) == state:
                        active_by_scale[scale] = None

                    continue

                # Update state for next bar
                state.previous_ratio = current_ratio
                state.previous_band = current_band

            prev_close = bar_close

        # Sort events by bar index (should already be sorted, but ensure)
        events.sort(key=lambda e: e.bar)

        # Build metadata
        meta = DiscretizationMeta(
            instrument=instrument,
            source_resolution=source_resolution,
            date_range_start=date_start,
            date_range_end=date_end,
            created_at=datetime.now(timezone.utc).isoformat(),
            config=self.config.to_output_config(),
        )

        return DiscretizationLog(
            meta=meta,
            swings=swing_entries,
            events=events,
        )

    def _detect_level_crossings(
        self,
        previous_ratio: float,
        current_ratio: float,
        bar_open: float,
        bar_close: float,
        bar_high: float,
        bar_low: float,
        tolerance: float,
    ) -> List[float]:
        """
        Detect level crossings based on configured semantics.

        Args:
            previous_ratio: Ratio at previous bar close
            current_ratio: Ratio at current bar close
            bar_open/close/high/low: Current bar OHLC
            tolerance: Tolerance for crossing detection

        Returns:
            List of levels crossed (in order of crossing)
        """
        if self.config.crossing_semantics == "close_cross":
            # Cross detected when close moves from one side to other
            return _levels_between(
                previous_ratio, current_ratio, self.config.level_set, tolerance
            )

        elif self.config.crossing_semantics == "open_close_cross":
            # Cross detected when bar opens on one side and closes on other
            # This is more restrictive - only counts if both open and close cross
            # We approximate by comparing open-to-close ratio movement within the bar
            # This is tricky since we only have ratios, not OHLC in ratio space
            # For now, fall back to close_cross semantics
            return _levels_between(
                previous_ratio, current_ratio, self.config.level_set, tolerance
            )

        elif self.config.crossing_semantics == "wick_touch":
            # Level is "crossed" if wick touches it
            # This requires knowing the ratio of high and low
            # More complex implementation - for now fall back to close_cross
            return _levels_between(
                previous_ratio, current_ratio, self.config.level_set, tolerance
            )

        return []

    def _get_parent_context(
        self,
        current_scale: str,
        active_by_scale: Dict[str, Optional[_ActiveSwingState]],
        current_price: float,
    ) -> Optional[ParentContext]:
        """
        Get parent-scale context for cross-scale analysis.

        Args:
            current_scale: The scale of the current event
            active_by_scale: Dict of active swings by scale
            current_price: Current bar close price

        Returns:
            ParentContext if a larger-scale swing is active, None otherwise
        """
        # Scale hierarchy: XL > L > M > S
        parent_scale_map = {"S": "M", "M": "L", "L": "XL", "XL": None}
        parent_scale = parent_scale_map.get(current_scale)

        if parent_scale is None:
            return None

        # Walk up the hierarchy to find an active parent
        while parent_scale is not None:
            parent_state = active_by_scale.get(parent_scale)
            if parent_state is not None and not parent_state.terminated:
                frame = parent_state.frame
                ratio = float(frame.ratio(Decimal(str(current_price))))
                band = _get_band(ratio, self.config.level_set)

                return ParentContext(
                    scale=parent_scale,
                    swing_id=parent_state.swing_entry.swing_id,
                    band=band,
                    direction=parent_state.swing_entry.direction,
                    ratio=ratio,
                )

            # Try next larger scale
            parent_scale = parent_scale_map.get(parent_scale)

        return None

    def _format_timestamp(self, ts: Any) -> str:
        """Format timestamp to ISO 8601."""
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        elif isinstance(ts, datetime):
            return ts.isoformat()
        elif isinstance(ts, str):
            return ts
        else:
            return str(ts)
