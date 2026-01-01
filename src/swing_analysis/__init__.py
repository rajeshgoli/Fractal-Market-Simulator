# Swing Analysis Module
#
# Core market structure detection and analysis algorithms.

from .types import Bar
from .bar_aggregator import BarAggregator
from .reference_frame import ReferenceFrame

# DAG-based leg detector (modularized architecture)
from .dag import (
    LegDetector,
    HierarchicalDetector,  # Backward compatibility alias
    calibrate,
    calibrate_from_dataframe,
    dataframe_to_bars,
    Leg,
    PendingOrigin,
    DetectorState,
    BarType,
    LegPruner,
)
from .swing_config import SwingConfig

# Reference layer (post-DAG filtering)
from .reference_layer import (
    ReferenceLayer,
    ReferenceSwing,
    ReferenceState,
    LevelInfo,
    InvalidationResult,
    CompletionResult,
)
