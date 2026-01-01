"""
Replay cache module for sharing state between router endpoints.

This module provides a centralized cache dict for the replay/DAG state,
including the detector instance, current position, and computed thresholds.

The cache is used by all routers (dag.py, reference.py, feedback.py, etc.)
to access and modify shared state.
"""

from typing import Any, Dict


# Single source of truth for replay/DAG state
# Keys:
#   - detector: LegDetector instance
#   - reference_layer: ReferenceLayer instance
#   - last_bar_index: int (-1 = not started)
#   - lifecycle_events: List[Dict] - events for Follow Leg feature
#   - source_resolution: int (bar resolution in minutes)
#   - aggregator: BarAggregator instance (optional)
_replay_cache: Dict[str, Any] = {
    "last_bar_index": -1,
    "detector": None,
    "reference_layer": None,
    "aggregator": None,
    "source_resolution": 5,
    "lifecycle_events": [],
}


def get_replay_cache() -> Dict[str, Any]:
    """Get the shared replay cache dict."""
    return _replay_cache


def reset_replay_cache() -> None:
    """Reset the shared cache to initial state."""
    global _replay_cache
    _replay_cache["last_bar_index"] = -1
    _replay_cache["detector"] = None
    _replay_cache["reference_layer"] = None
    _replay_cache["aggregator"] = None
    _replay_cache["source_resolution"] = 5
    _replay_cache["lifecycle_events"] = []


def is_initialized() -> bool:
    """Check if the cache has been initialized with a detector."""
    return _replay_cache.get("detector") is not None
