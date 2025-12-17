# Swing Analysis Module
#
# Core market structure detection and analysis algorithms.

from .types import Bar
from .swing_detector import detect_swings, ReferenceSwing
from .level_calculator import calculate_levels
from .scale_calibrator import ScaleCalibrator
from .bar_aggregator import BarAggregator
from .swing_state_manager import SwingStateManager
from .event_detector import EventDetector, ActiveSwing, StructuralEvent
from .reference_frame import ReferenceFrame
