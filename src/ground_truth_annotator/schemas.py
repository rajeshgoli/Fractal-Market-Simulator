"""
Pydantic models for the Replay View API.

All request/response schemas for replay endpoints.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel


# ============================================================================
# Core Bar/Session Models
# ============================================================================


class BarResponse(BaseModel):
    """A single OHLC bar for chart display."""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    source_start_index: int
    source_end_index: int


class SessionResponse(BaseModel):
    """Session state returned by the API."""
    session_id: str
    data_file: str
    resolution: str
    window_size: int
    window_offset: int
    total_source_bars: int
    calibration_bar_count: Optional[int]
    scale: str
    created_at: str
    annotation_count: int
    completed_scales: List[str]


# ============================================================================
# Discretization Models (for compatibility)
# ============================================================================


class DiscretizationEventResponse(BaseModel):
    """A discretization event for API response."""
    bar: int
    timestamp: str
    swing_id: str
    event_type: str
    data: dict
    effort: Optional[dict] = None
    shock: Optional[dict] = None
    parent_context: Optional[dict] = None


class DiscretizationSwingResponse(BaseModel):
    """A discretization swing entry for API response."""
    swing_id: str
    scale: str
    direction: str
    anchor0: float
    anchor1: float
    anchor0_bar: int
    anchor1_bar: int
    formed_at_bar: int
    status: str
    terminated_at_bar: Optional[int] = None
    termination_reason: Optional[str] = None


class DiscretizationRunResponse(BaseModel):
    """Response from running discretization."""
    success: bool
    event_count: int
    swing_count: int
    scales_processed: List[str]
    message: str


class DiscretizationStateResponse(BaseModel):
    """Current discretization state."""
    has_log: bool
    event_count: int
    swing_count: int
    scales: List[str]
    config: Optional[dict] = None


# ============================================================================
# Replay/Swing Detection Models
# ============================================================================


class DetectedSwingResponse(BaseModel):
    """A detected swing for Replay View visualization."""
    id: str
    direction: str  # "bull" or "bear"
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    rank: int
    scale: Optional[str] = None  # Legacy scale (XL, L, M, S) - mapped from depth
    # Hierarchy info (new in hierarchical model)
    depth: int = 0  # Hierarchy depth (0 = root)
    parent_ids: List[str] = []  # Parent swing IDs
    # Fib levels for overlay
    fib_0: float  # Defended pivot (0)
    fib_0382: float  # First retracement
    fib_1: float  # Origin extremum (1.0)
    fib_2: float  # Completion target (2.0)


class SwingsWindowedResponse(BaseModel):
    """Response from windowed swing detection."""
    bar_end: int
    swing_count: int
    swings: List[DetectedSwingResponse]


# ============================================================================
# Calibration Models
# ============================================================================


class CalibrationSwingResponse(BaseModel):
    """A swing detected during calibration."""
    id: str
    scale: str  # Legacy scale for frontend compatibility
    direction: str  # "bull" or "bear"
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    rank: int
    is_active: bool
    # Hierarchy info (new)
    depth: int = 0  # Hierarchy depth (0 = root)
    parent_ids: List[str] = []  # Parent swing IDs
    # Fib levels for overlay
    fib_0: float
    fib_0382: float
    fib_1: float
    fib_2: float


class CalibrationScaleStats(BaseModel):
    """Statistics for a single scale during calibration."""
    total_swings: int
    active_swings: int


class CalibrationResponse(BaseModel):
    """Response from calibration endpoint."""
    calibration_bar_count: int
    current_price: float
    swings_by_scale: Dict[str, List[CalibrationSwingResponse]]
    active_swings_by_scale: Dict[str, List[CalibrationSwingResponse]]
    scale_thresholds: Dict[str, float]
    stats_by_scale: Dict[str, CalibrationScaleStats]


# ============================================================================
# Replay Advance Models
# ============================================================================


class ReplayAdvanceRequest(BaseModel):
    """Request to advance playback beyond calibration window."""
    calibration_bar_count: int
    current_bar_index: int
    advance_by: int = 1


class ReplayBarResponse(BaseModel):
    """A single OHLC bar returned during playback advance."""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class ReplayEventResponse(BaseModel):
    """A playback event triggered by swing state change."""
    type: str  # SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED, LEVEL_CROSS
    bar_index: int
    scale: str  # Legacy scale for frontend compatibility
    direction: str
    swing_id: str
    swing: Optional[CalibrationSwingResponse] = None
    level: Optional[float] = None  # For LEVEL_CROSS
    previous_level: Optional[float] = None  # For LEVEL_CROSS
    trigger_explanation: Optional[str] = None
    # Hierarchy info (new)
    depth: int = 0
    parent_ids: List[str] = []


class ReplaySwingState(BaseModel):
    """Current state of all swings at a given bar."""
    XL: List[CalibrationSwingResponse] = []
    L: List[CalibrationSwingResponse] = []
    M: List[CalibrationSwingResponse] = []
    S: List[CalibrationSwingResponse] = []


class ReplayAdvanceResponse(BaseModel):
    """Response from advance endpoint."""
    new_bars: List[ReplayBarResponse]
    events: List[ReplayEventResponse]
    swing_state: ReplaySwingState
    current_bar_index: int
    current_price: float
    end_of_data: bool


# ============================================================================
# Playback Feedback Models
# ============================================================================


class PlaybackFeedbackEventContext(BaseModel):
    """Event context for playback feedback."""
    event_type: Optional[str] = None
    scale: Optional[str] = None
    swing: Optional[Dict] = None
    detection_bar_index: Optional[int] = None


class SwingCountsByScale(BaseModel):
    """Swing counts broken down by scale."""
    XL: int = 0
    L: int = 0
    M: int = 0
    S: int = 0


class PlaybackFeedbackSnapshot(BaseModel):
    """Rich context snapshot for feedback capture."""
    state: str  # calibrating, calibration_complete, playing, paused
    window_offset: int
    bars_since_calibration: int
    current_bar_index: int
    calibration_bar_count: int
    swings_found: SwingCountsByScale
    swings_invalidated: int
    swings_completed: int
    event_context: Optional[PlaybackFeedbackEventContext] = None


class PlaybackFeedbackRequest(BaseModel):
    """Request to submit playback feedback."""
    text: str
    playback_bar: int
    snapshot: PlaybackFeedbackSnapshot


class PlaybackFeedbackResponse(BaseModel):
    """Response from feedback submission."""
    success: bool
    observation_id: str
    message: str
