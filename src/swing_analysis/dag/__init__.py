"""DAG-based leg detection layer.

This module provides the structural layer for swing detection using a DAG
(Directed Acyclic Graph) algorithm. It processes bars incrementally and
emits events for leg creation, swing formation, and level crosses.

Key Components:
- LegDetector: Main class for incremental swing detection
- Leg: Directional price movement with known temporal ordering
- PendingOrigin: Potential origin for a new leg awaiting confirmation
- DetectorState: Serializable state for pause/resume
- BarType: Classification of bar relationships
- LegPruner: Stateless helper for leg pruning operations

Example:
    >>> from swing_analysis.dag import LegDetector
    >>>
    >>> # Incremental detection
    >>> detector = LegDetector()
    >>> for bar in bars:
    ...     events = detector.process_bar(bar)
"""

from .leg_detector import LegDetector, HierarchicalDetector
from .leg import Leg, PendingOrigin
from .state import DetectorState, BarType
from .leg_pruner import LegPruner
from .range_distribution import RollingBinDistribution, BIN_MULTIPLIERS, NUM_BINS

__all__ = [
    # Main detector
    "LegDetector",
    "HierarchicalDetector",  # Backward compatibility alias
    # Data structures
    "Leg",
    "PendingOrigin",
    "DetectorState",
    "BarType",
    # Pruning
    "LegPruner",
    # Range distribution (#434)
    "RollingBinDistribution",
    "BIN_MULTIPLIERS",
    "NUM_BINS",
]
