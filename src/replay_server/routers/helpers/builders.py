"""
Builder helper functions for replay routers.

Provides functions to build complex response objects from detector state.
"""

import logging
import statistics
from typing import Dict, List, Optional

from ....swing_analysis.dag.leg import Leg
from ....swing_analysis.dag import LegDetector
from ....swing_analysis.types import Bar
from ....swing_analysis.bar_aggregator import BarAggregator
from ...schemas import (
    LegResponse,
    BarResponse,
    ReplaySwingState,
    AggregatedBarsResponse,
    TreeStatistics,
    LegsByDepth,
    DagLegResponse,
    DagPendingOrigin,
    DagLegCounts,
    DagStateResponse,
    RefStateSnapshot,
    ReferenceSwingResponse,
    FilteredLegResponse,
    FilterStatsResponse,
    LevelCrossEventResponse,
)
from .conversions import leg_to_response, size_to_scale

logger = logging.getLogger(__name__)

# Scale to timeframe mapping (matches api.py) - standard timeframes
SCALE_TO_MINUTES = {
    "1M": 1, "1m": 1,
    "5M": 5, "5m": 5,
    "15M": 15, "15m": 15,
    "30M": 30, "30m": 30,
    "1H": 60, "1h": 60,
    "4H": 240, "4h": 240,
    "1D": 1440, "1d": 1440,
    "1W": 10080, "1w": 10080,
}


def build_swing_state(
    active_legs: List[Leg],
    scale_thresholds: Dict[str, float],
) -> ReplaySwingState:
    """
    Build ReplaySwingState from active legs.

    Args:
        active_legs: List of active Leg objects.
        scale_thresholds: Size thresholds for scale assignment (for compatibility).

    Returns:
        ReplaySwingState grouped by depth.
    """
    by_depth: Dict[str, List[LegResponse]] = {
        "depth_1": [], "depth_2": [], "depth_3": [], "deeper": []
    }

    sorted_legs = sorted(
        active_legs,
        key=lambda leg: float(leg.range),
        reverse=True
    )

    for rank, leg in enumerate(sorted_legs, start=1):
        response = leg_to_response(
            leg,
            is_active=True,
            rank=rank,
            scale_thresholds=scale_thresholds,
        )
        by_depth["depth_1"].append(response)

    return ReplaySwingState(
        depth_1=by_depth["depth_1"],
        depth_2=by_depth["depth_2"],
        depth_3=by_depth["depth_3"],
        deeper=by_depth["deeper"],
    )


def build_aggregated_bars(
    source_bars: List[Bar],
    scales: List[str],
    source_resolution: int,
    limit: Optional[int] = None,
) -> AggregatedBarsResponse:
    """
    Build aggregated bars for requested scales.

    Args:
        source_bars: All source bars.
        scales: List of scales to aggregate (e.g., ["S", "M"]).
        source_resolution: Source bar resolution in minutes.
        limit: Optional limit on number of source bars to use.

    Returns:
        AggregatedBarsResponse with bars for each requested scale.
    """
    bars_to_use = source_bars[:limit] if limit else source_bars
    if not bars_to_use:
        return {}

    # Create aggregator for the bars
    aggregator = BarAggregator(bars_to_use, source_resolution)

    result: AggregatedBarsResponse = {}

    for scale in scales:
        scale_upper = scale.upper()
        timeframe = SCALE_TO_MINUTES.get(scale_upper, source_resolution)
        effective_tf = max(timeframe, source_resolution)

        try:
            agg_bars = aggregator.get_bars(effective_tf)
            source_to_agg = aggregator._source_to_agg_mapping.get(effective_tf, {})

            # Build inverse mapping
            agg_to_source = {}
            for src_idx, agg_idx in source_to_agg.items():
                if agg_idx not in agg_to_source:
                    agg_to_source[agg_idx] = (src_idx, src_idx)
                else:
                    min_idx, max_idx = agg_to_source[agg_idx]
                    agg_to_source[agg_idx] = (min(min_idx, src_idx), max(max_idx, src_idx))

            bar_responses = []
            for i, agg_bar in enumerate(agg_bars):
                src_start, src_end = agg_to_source.get(i, (0, 0))
                bar_responses.append(BarResponse(
                    index=i,
                    timestamp=agg_bar.timestamp,
                    open=agg_bar.open,
                    high=agg_bar.high,
                    low=agg_bar.low,
                    close=agg_bar.close,
                    source_start_index=src_start,
                    source_end_index=src_end,
                ))

            result[scale] = bar_responses  # Use original scale key (preserves case)
        except Exception as e:
            logger.warning(f"Failed to aggregate bars for scale {scale}: {e}")

    return result


def build_dag_state(detector: LegDetector, window_offset: int = 0) -> DagStateResponse:
    """
    Build DAG state response from detector.

    Args:
        detector: The LegDetector instance.
        window_offset: CSV offset to convert bar-relative indices to csv indices.

    Returns:
        DagStateResponse with current DAG state.
    """
    state = detector.state

    active_legs = [
        DagLegResponse(
            leg_id=leg.leg_id,
            direction=leg.direction,
            pivot_price=float(leg.pivot_price),
            pivot_index=window_offset + leg.pivot_index,
            origin_price=float(leg.origin_price),
            origin_index=window_offset + leg.origin_index,
            retracement_pct=float(leg.retracement_pct),
            status=leg.status,
            bar_count=leg.bar_count,
            origin_breached=leg.max_origin_breach is not None,
            impulsiveness=leg.impulsiveness,
            spikiness=leg.spikiness,
            parent_leg_id=leg.parent_leg_id,
            impulse_to_deepest=leg.impulse_to_deepest,
            impulse_back=leg.impulse_back,
            net_segment_impulse=leg.net_segment_impulse,
        )
        for leg in state.active_legs
    ]

    pending_origins = {
        direction: DagPendingOrigin(
            price=float(origin.price),
            bar_index=window_offset + origin.bar_index,
            direction=origin.direction,
            source=origin.source,
        ) if origin else None
        for direction, origin in state.pending_origins.items()
    }

    leg_counts = DagLegCounts(
        bull=sum(1 for leg in state.active_legs if leg.direction == 'bull'),
        bear=sum(1 for leg in state.active_legs if leg.direction == 'bear'),
    )

    return DagStateResponse(
        active_legs=active_legs,
        pending_origins=pending_origins,
        leg_counts=leg_counts,
    )


def check_siblings_exist(legs: List[Leg]) -> bool:
    """
    Check if sibling legs exist (same defended pivot, different origins).

    Siblings share the same pivot but have different origin values.

    Args:
        legs: List of all legs.

    Returns:
        True if siblings are detected.
    """
    # Group legs by pivot price and direction
    pivot_groups: Dict[tuple, List[Leg]] = {}
    for leg in legs:
        pivot = float(leg.pivot_price)
        key = (pivot, leg.direction)
        if key not in pivot_groups:
            pivot_groups[key] = []
        pivot_groups[key].append(leg)

    # Check if any group has multiple legs with different origins
    for legs_in_group in pivot_groups.values():
        if len(legs_in_group) >= 2:
            # Get unique origins
            origins = set(float(leg.origin_price) for leg in legs_in_group)
            if len(origins) >= 2:
                return True

    return False


def compute_tree_statistics(
    all_legs: List[Leg],
    active_legs: List[Leg],
    recent_lookback: int = 10,
) -> TreeStatistics:
    """
    Compute tree structure statistics for hierarchical UI.

    Note: Swing hierarchy was removed in #301. This function now computes
    simplified statistics without parent/child relationships. The leg hierarchy
    (parent_leg_id) is separate and still functional.

    Args:
        all_legs: All legs from the DAG.
        active_legs: Currently active legs.
        recent_lookback: Number of bars to look back for "recently invalidated".

    Returns:
        TreeStatistics with simplified metrics (swing hierarchy removed).
    """
    if not all_legs:
        return TreeStatistics(
            root_swings=0,
            root_bull=0,
            root_bear=0,
            total_nodes=0,
            max_depth=0,
            avg_children=0.0,
            defended_by_depth={"1": 0, "2": 0, "3": 0, "deeper": 0},
            largest_range=0.0,
            largest_leg_id=None,
            median_range=0.0,
            smallest_range=0.0,
            roots_have_children=True,
            siblings_detected=False,
            no_orphaned_nodes=True,
        )

    # All legs are now roots since swing hierarchy was removed (#301)
    root_bull = sum(1 for leg in all_legs if leg.direction == "bull")
    root_bear = sum(1 for leg in all_legs if leg.direction == "bear")

    # All legs at depth 0 since hierarchy removed
    max_depth = 0
    avg_children = 0.0

    # All active legs are at depth 1 (roots)
    defended_by_depth = {
        "1": len(active_legs),
        "2": 0,
        "3": 0,
        "deeper": 0
    }

    # Range distribution
    ranges = [float(leg.range) for leg in all_legs]
    sorted_ranges = sorted(ranges, reverse=True)
    largest_range = sorted_ranges[0] if sorted_ranges else 0.0
    median_range = statistics.median(ranges) if ranges else 0.0
    smallest_range = sorted_ranges[-1] if sorted_ranges else 0.0

    # Find the largest leg ID
    largest_leg_id = None
    for leg in all_legs:
        if float(leg.range) == largest_range:
            largest_leg_id = leg.leg_id
            break

    # Validation checks simplified (swing hierarchy removed #301)
    roots_have_children = True  # No hierarchy to validate
    siblings_detected = check_siblings_exist(all_legs)
    no_orphaned_nodes = True  # No hierarchy to validate

    return TreeStatistics(
        root_swings=len(all_legs),
        root_bull=root_bull,
        root_bear=root_bear,
        total_nodes=len(all_legs),
        max_depth=max_depth,
        avg_children=round(avg_children, 1),
        defended_by_depth=defended_by_depth,
        largest_range=round(largest_range, 2),
        largest_leg_id=largest_leg_id,  # #398: renamed from largest_swing_id
        median_range=round(median_range, 2),
        smallest_range=round(smallest_range, 2),
        roots_have_children=roots_have_children,
        siblings_detected=siblings_detected,
        no_orphaned_nodes=no_orphaned_nodes,
    )


def group_legs_by_depth(
    legs: List[Leg],
    scale_thresholds: Dict[str, float],
) -> LegsByDepth:
    """
    Group legs by hierarchy depth for the UI.

    Args:
        legs: List of Leg objects.
        scale_thresholds: Size thresholds for scale assignment (backward compat).

    Returns:
        LegsByDepth with legs grouped by depth level.
    """
    result = LegsByDepth()

    # Sort by size descending for ranking
    sorted_legs = sorted(
        legs,
        key=lambda leg: float(leg.range),
        reverse=True
    )

    for rank, leg in enumerate(sorted_legs, start=1):
        is_active = leg.status == "active"
        response = leg_to_response(
            leg,
            is_active=is_active,
            rank=rank,
            scale_thresholds=scale_thresholds,
        )
        result.depth_1.append(response)

    return result


def build_ref_state_snapshot(
    bar_index: int,
    ref_layer,
    ref_state,
    bar: Bar,
    active_legs: list,
) -> RefStateSnapshot:
    """
    Build full reference state snapshot for buffered playback (#456, #457, #458).

    Args:
        bar_index: The bar index this snapshot is for.
        ref_layer: The ReferenceLayer instance.
        ref_state: The ReferenceState from ref_layer.update().
        bar: The current bar (for price).
        active_legs: Active legs from detector (for crossing detection).

    Returns:
        RefStateSnapshot with full reference state for this bar.
    """
    from ....swing_analysis.reference_layer import FilterReason

    # Get formed leg IDs at this bar
    formed_ids = list(ref_layer.get_formed_leg_ids_at_bar(bar_index))

    # Convert references to response format (top N per pivot)
    references = []
    for ref_swing in ref_state.references:
        median_multiple = ref_layer._bin_distribution.get_median_multiple(
            float(ref_swing.leg.range)
        )
        references.append(ReferenceSwingResponse(
            leg_id=ref_swing.leg.leg_id,
            bin=ref_swing.bin,
            median_multiple=median_multiple,
            depth=ref_swing.leg.depth,
            location=ref_swing.location,
            salience_score=ref_swing.salience_score,
            direction=ref_swing.leg.direction,
            origin_price=float(ref_swing.leg.origin_price),
            origin_index=ref_swing.leg.origin_index,
            pivot_price=float(ref_swing.leg.pivot_price),
            pivot_index=ref_swing.leg.pivot_index,
            impulsiveness=ref_swing.leg.impulsiveness,
        ))

    # Convert active_filtered to response format (#457: valid refs that didn't make top N)
    active_filtered = []
    for ref_swing in ref_state.active_filtered:
        median_multiple = ref_layer._bin_distribution.get_median_multiple(
            float(ref_swing.leg.range)
        )
        active_filtered.append(ReferenceSwingResponse(
            leg_id=ref_swing.leg.leg_id,
            bin=ref_swing.bin,
            median_multiple=median_multiple,
            depth=ref_swing.leg.depth,
            location=ref_swing.location,
            salience_score=ref_swing.salience_score,
            direction=ref_swing.leg.direction,
            origin_price=float(ref_swing.leg.origin_price),
            origin_index=ref_swing.leg.origin_index,
            pivot_price=float(ref_swing.leg.pivot_price),
            pivot_index=ref_swing.leg.pivot_index,
            impulsiveness=ref_swing.leg.impulsiveness,
        ))

    # Get all legs with filter status for observation mode
    # Note: We need the active_legs from detector for this
    # The filtered_legs are computed from ref_state in the caller if needed
    filtered_legs = []

    # Determine auto-tracked leg and compute crossing events (#458)
    # If user has pinned a leg, use that. Otherwise auto-track top reference.
    auto_tracked_leg_id = None
    crossing_events = []

    tracked_leg_ids = ref_layer.get_tracked_leg_ids()
    if tracked_leg_ids:
        # User has pinned leg(s), use the first one
        auto_tracked_leg_id = next(iter(tracked_leg_ids))
        # Detect crossings for tracked legs
        raw_events = ref_layer.detect_level_crossings(active_legs, bar)
        crossing_events = [
            LevelCrossEventResponse(
                leg_id=e.leg_id,
                direction=e.direction,
                level_crossed=e.level_crossed,
                cross_direction=e.cross_direction,
                bar_index=e.bar_index,
                timestamp=e.timestamp.isoformat(),
            )
            for e in raw_events
        ]
    elif ref_state.references:
        # Auto-track top reference (no manual pin)
        top_ref = ref_state.references[0]
        auto_tracked_leg_id = top_ref.leg.leg_id

        # Temporarily add to tracking to compute crossings
        was_tracked = ref_layer.is_tracked_for_crossing(auto_tracked_leg_id)
        if not was_tracked:
            ref_layer.add_crossing_tracking(auto_tracked_leg_id)

        # Detect crossings
        raw_events = ref_layer.detect_level_crossings(active_legs, bar)
        crossing_events = [
            LevelCrossEventResponse(
                leg_id=e.leg_id,
                direction=e.direction,
                level_crossed=e.level_crossed,
                cross_direction=e.cross_direction,
                bar_index=e.bar_index,
                timestamp=e.timestamp.isoformat(),
            )
            for e in raw_events
        ]

        # Restore tracking state if we added it temporarily
        if not was_tracked:
            ref_layer.remove_crossing_tracking(auto_tracked_leg_id)

    # #472: Include filter_stats from ref_state
    filter_stats_response = None
    if ref_state.filter_stats is not None:
        filter_stats_response = FilterStatsResponse(
            total_legs=ref_state.filter_stats.total_legs,
            valid_count=ref_state.filter_stats.valid_count,
            pass_rate=ref_state.filter_stats.pass_rate,
            by_reason=ref_state.filter_stats.by_reason,
        )

    return RefStateSnapshot(
        bar_index=bar_index,
        formed_leg_ids=formed_ids,
        references=references,
        active_filtered=active_filtered,
        filtered_legs=filtered_legs,
        current_price=bar.close,
        is_warming_up=ref_state.is_warming_up,
        warmup_progress=list(ref_state.warmup_progress),
        median=ref_layer._bin_distribution.median,
        auto_tracked_leg_id=auto_tracked_leg_id,
        crossing_events=crossing_events,
        filter_stats=filter_stats_response,
    )
