"""
Helper functions for replay routers.

Provides conversion functions for Leg to API response formats.
"""

from .conversions import (
    size_to_scale,
    leg_to_response,
    event_to_response,
    format_trigger_explanation,
    event_to_lifecycle_event,
    calculate_scale_thresholds,
    group_legs_by_scale,
)

from .builders import (
    build_swing_state,
    build_aggregated_bars,
    build_dag_state,
    build_ref_state_snapshot,
    compute_tree_statistics,
    group_legs_by_depth,
    check_siblings_exist,
)

__all__ = [
    # Conversion functions
    'size_to_scale',
    'leg_to_response',
    'event_to_response',
    'format_trigger_explanation',
    'event_to_lifecycle_event',
    'calculate_scale_thresholds',
    'group_legs_by_scale',
    # Builder functions
    'build_swing_state',
    'build_aggregated_bars',
    'build_dag_state',
    'build_ref_state_snapshot',
    'compute_tree_statistics',
    'group_legs_by_depth',
    'check_siblings_exist',
]
