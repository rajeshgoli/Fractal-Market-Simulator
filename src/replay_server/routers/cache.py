"""
Replay cache module for sharing state between router endpoints.

This module provides a centralized cache for the replay/DAG state,
including the detector instance, current position, and computed thresholds.

The cache is used by all split routers (dag.py, reference.py, config.py, etc.)
to access and modify shared state.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ...swing_analysis.dag import LegDetector
from ...swing_analysis.reference_layer import ReferenceLayer
from ...swing_analysis.events import DetectionEvent


@dataclass
class ReplayCache:
    """
    Centralized cache for replay/DAG state.

    All routers access this shared state through the module-level instance.
    """
    # Core detection state
    detector: Optional[LegDetector] = None
    reference_layer: Optional[ReferenceLayer] = None

    # Current position tracking
    last_bar_index: int = -1
    calibration_bar_count: int = 0

    # Events and thresholds
    calibration_events: List[DetectionEvent] = field(default_factory=list)
    lifecycle_events: List[Dict[str, Any]] = field(default_factory=list)
    scale_thresholds: Dict[str, float] = field(
        default_factory=lambda: {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
    )

    # Source data info
    source_resolution: int = 1  # Bar resolution in minutes

    def reset(self) -> None:
        """Reset the cache to initial state."""
        self.detector = None
        self.reference_layer = None
        self.last_bar_index = -1
        self.calibration_bar_count = 0
        self.calibration_events = []
        self.lifecycle_events = []
        self.scale_thresholds = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}
        self.source_resolution = 1

    def is_initialized(self) -> bool:
        """Check if the cache has been initialized with a detector."""
        return self.detector is not None


# Module-level cache instance - shared by all routers
_cache = ReplayCache()


def get_cache() -> ReplayCache:
    """Get the shared replay cache instance."""
    return _cache


def reset_cache() -> None:
    """Reset the shared cache to initial state."""
    _cache.reset()


# Legacy dict-style access for backward compatibility during migration
# Maps to the ReplayCache dataclass fields
_replay_cache: Dict[str, Any] = {}


def _sync_dict_to_cache() -> None:
    """Sync the legacy dict to the dataclass cache."""
    global _cache
    if "detector" in _replay_cache:
        _cache.detector = _replay_cache["detector"]
    if "reference_layer" in _replay_cache:
        _cache.reference_layer = _replay_cache["reference_layer"]
    if "last_bar_index" in _replay_cache:
        _cache.last_bar_index = _replay_cache["last_bar_index"]
    if "calibration_bar_count" in _replay_cache:
        _cache.calibration_bar_count = _replay_cache["calibration_bar_count"]
    if "calibration_events" in _replay_cache:
        _cache.calibration_events = _replay_cache["calibration_events"]
    if "lifecycle_events" in _replay_cache:
        _cache.lifecycle_events = _replay_cache["lifecycle_events"]
    if "scale_thresholds" in _replay_cache:
        _cache.scale_thresholds = _replay_cache["scale_thresholds"]
    if "source_resolution" in _replay_cache:
        _cache.source_resolution = _replay_cache["source_resolution"]


def _sync_cache_to_dict() -> None:
    """Sync the dataclass cache to the legacy dict."""
    global _replay_cache
    _replay_cache["detector"] = _cache.detector
    _replay_cache["reference_layer"] = _cache.reference_layer
    _replay_cache["last_bar_index"] = _cache.last_bar_index
    _replay_cache["calibration_bar_count"] = _cache.calibration_bar_count
    _replay_cache["calibration_events"] = _cache.calibration_events
    _replay_cache["lifecycle_events"] = _cache.lifecycle_events
    _replay_cache["scale_thresholds"] = _cache.scale_thresholds
    _replay_cache["source_resolution"] = _cache.source_resolution
