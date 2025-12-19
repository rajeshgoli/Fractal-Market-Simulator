# Swing Analysis Module
#
# Core market structure detection and analysis algorithms.

from .types import Bar
from .level_calculator import calculate_levels
from .bar_aggregator import BarAggregator
from .swing_state_manager import SwingStateManager, ScaleConfig
from .event_detector import EventDetector, ActiveSwing, StructuralEvent
from .reference_frame import ReferenceFrame

# Hierarchical detector (new architecture)
from .hierarchical_detector import HierarchicalDetector, calibrate
from .swing_node import SwingNode
from .swing_config import SwingConfig

# Reference layer (post-DAG filtering)
from .reference_layer import ReferenceLayer, ReferenceSwingInfo, InvalidationResult

# Backward compatibility adapters
from .adapters import (
    ReferenceSwing,
    SeparationDetails,
    detect_swings_compat as detect_swings,
    swing_node_to_reference_swing,
)
