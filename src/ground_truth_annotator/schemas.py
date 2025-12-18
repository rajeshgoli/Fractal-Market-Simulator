"""
Pydantic models for the Ground Truth Annotator API.

All request/response schemas used across routers are defined here
to avoid circular imports and provide a single source of truth.
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
    total_source_bars: int  # Total bars in file (before offset/windowing)
    calibration_bar_count: Optional[int]  # Bars used for calibration (if calibrated)
    scale: str
    created_at: str
    annotation_count: int
    completed_scales: List[str]
    status: str


class SessionStatusUpdate(BaseModel):
    """Request to update session status."""
    status: str  # "keep" or "discard"


class SessionFinalizeRequest(BaseModel):
    """Request to finalize session with timestamp-based filename."""
    status: str  # "keep" or "discard"
    label: Optional[str] = None  # Optional user-provided label
    difficulty: Optional[int] = None  # 1-5 difficulty rating
    regime: Optional[str] = None  # "bull" | "bear" | "chop"
    comments: Optional[str] = None  # Free-form comments


class SessionFinalizeResponse(BaseModel):
    """Response from finalizing session."""
    success: bool
    session_filename: Optional[str]  # None if discarded
    review_filename: Optional[str]   # None if discarded or no review
    message: str


class NextSessionResponse(BaseModel):
    """Response from creating a new session with random offset."""
    session_id: str
    offset: int
    redirect_url: str


# ============================================================================
# Annotation Models
# ============================================================================


class AnnotationCreate(BaseModel):
    """Request to create a new annotation."""
    start_bar_index: int
    end_bar_index: int


class AnnotationResponse(BaseModel):
    """An annotation returned by the API."""
    annotation_id: str
    scale: str
    direction: str
    start_bar_index: int
    end_bar_index: int
    start_source_index: int
    end_source_index: int
    start_price: str
    end_price: str
    created_at: str
    window_id: str


# ============================================================================
# Cascade Models
# ============================================================================


class ScaleInfo(BaseModel):
    """Information about a single scale."""
    scale: str
    target_bars: Optional[int]
    actual_bars: int
    compression_ratio: float
    annotation_count: int
    is_complete: bool
    is_skipped: bool = False


class CascadeStateResponse(BaseModel):
    """Cascade workflow state."""
    current_scale: str
    current_scale_index: int
    reference_scale: Optional[str]
    completed_scales: List[str]
    skipped_scales: List[str] = []
    scales_remaining: int
    is_complete: bool
    scale_info: Dict[str, ScaleInfo]


class CascadeTransitionResponse(BaseModel):
    """Response from cascade state change (advance or skip)."""
    success: bool
    previous_scale: str  # Scale before transition
    current_scale: str   # Scale after transition
    skipped_scales: List[str] = []  # Empty for advance, populated for skip
    is_complete: bool


# ============================================================================
# Comparison Models
# ============================================================================


class ComparisonScaleResult(BaseModel):
    """Comparison result for a single scale."""
    user_annotations: int
    system_detections: int
    matches: int
    false_negatives: int
    false_positives: int
    match_rate: float


class ComparisonSummary(BaseModel):
    """Summary statistics from comparison."""
    total_user_annotations: int
    total_system_detections: int
    total_matches: int
    total_false_negatives: int
    total_false_positives: int
    overall_match_rate: float


class FalseNegativeItem(BaseModel):
    """A false negative (user marked, system missed)."""
    scale: str
    start: int
    end: int
    direction: str
    annotation_id: str


class FalsePositiveItem(BaseModel):
    """A false positive (system found, user didn't mark)."""
    scale: str
    start: int
    end: int
    direction: str
    size: float
    rank: int


class ComparisonReportResponse(BaseModel):
    """Full comparison report."""
    summary: ComparisonSummary
    by_scale: Dict[str, ComparisonScaleResult]
    false_negatives: List[FalseNegativeItem]
    false_positives: List[FalsePositiveItem]


class ComparisonRunResponse(BaseModel):
    """Response from running comparison."""
    success: bool
    summary: ComparisonSummary
    message: str


# ============================================================================
# Review Mode Models
# ============================================================================


class ReviewStateResponse(BaseModel):
    """Current review session state."""
    review_id: str
    session_id: str
    phase: str  # "matches" | "fp_sample" | "fn_feedback" | "complete"
    progress: dict  # {"completed": int, "total": int}
    is_complete: bool


class MatchItem(BaseModel):
    """A matched swing for review."""
    annotation_id: str
    scale: str
    direction: str
    start_index: int
    end_index: int
    start_price: str
    end_price: str
    system_start: int
    system_end: int
    feedback: Optional[dict]  # Existing feedback if any


class FPSampleItem(BaseModel):
    """A sampled false positive for review."""
    fp_index: int  # Index in the sample (for reference)
    scale: str
    direction: str
    start_index: int
    end_index: int
    high_price: float
    low_price: float
    size: float
    rank: int
    feedback: Optional[dict]


class FNItem(BaseModel):
    """A false negative for review."""
    annotation_id: str
    scale: str
    direction: str
    start_index: int
    end_index: int
    start_price: str
    end_price: str
    feedback: Optional[dict]


class BetterReferenceSubmit(BaseModel):
    """Optional better reference when dismissing FP."""
    high_bar_index: int
    low_bar_index: int
    high_price: str
    low_price: str


class FeedbackSubmit(BaseModel):
    """Request to submit feedback."""
    swing_type: str  # "match" | "false_positive" | "false_negative"
    swing_reference: dict  # {"annotation_id": str} or {"sample_index": int}
    verdict: str  # "correct" | "incorrect" | "noise" | "valid_missed" | "explained"
    comment: Optional[str] = None
    category: Optional[str] = None
    better_reference: Optional[BetterReferenceSubmit] = None  # "What I would have chosen instead"


class ReviewSummaryResponse(BaseModel):
    """Final review summary."""
    session_id: str
    review_id: str
    phase: str
    matches: dict  # {"total": int, "reviewed": int, "correct": int, "incorrect": int}
    false_positives: dict  # {"sampled": int, "reviewed": int, "noise": int, "valid": int}
    false_negatives: dict  # {"total": int, "explained": int}
    started_at: str
    completed_at: Optional[str]


# ============================================================================
# Discretization Models
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


class DiscretizationFilterParams(BaseModel):
    """Filter parameters for discretization events."""
    scale: Optional[str] = None
    event_type: Optional[str] = None
    shock_threshold: Optional[float] = None  # Minimum range_multiple
    levels_jumped_min: Optional[int] = None
    is_gap: Optional[bool] = None


# ============================================================================
# Replay/Swing Detection Models
# ============================================================================


class DetectedSwingResponse(BaseModel):
    """A detected swing for Replay View visualization."""
    id: str  # Generated ID for reference
    direction: str  # "bull" or "bear"
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    rank: int
    scale: Optional[str] = None  # Optional scale (XL, L, M, S)
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
    scale: str
    direction: str  # "bull" or "bear"
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    rank: int
    is_active: bool  # Whether swing is active at calibration end
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
    advance_by: int = 1  # Number of bars to advance (default: 1)


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
    scale: str
    direction: str
    swing_id: str
    swing: Optional[CalibrationSwingResponse] = None  # For SWING_FORMED
    level: Optional[float] = None  # For LEVEL_CROSS (e.g., 0.382, 0.618)
    previous_level: Optional[float] = None  # For LEVEL_CROSS
    trigger_explanation: Optional[str] = None  # Human-readable explanation of why event fired


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
    """Event context for playback feedback (optional, only during linger)."""
    event_type: Optional[str] = None  # SWING_FORMED, SWING_COMPLETED, LEVEL_CROSS, etc.
    scale: Optional[str] = None  # S, M, L, XL
    swing: Optional[Dict] = None  # Swing details if applicable
    detection_bar_index: Optional[int] = None  # When swing was detected


class SwingCountsByScale(BaseModel):
    """Swing counts broken down by scale."""
    XL: int = 0
    L: int = 0
    M: int = 0
    S: int = 0


class PlaybackFeedbackSnapshot(BaseModel):
    """Rich context snapshot for always-on feedback capture."""
    # Current state
    state: str  # calibrating, calibration_complete, playing, paused
    # Session offset
    window_offset: int
    # Bars elapsed since calibration
    bars_since_calibration: int
    # Current bar index
    current_bar_index: int
    # Calibration bar count
    calibration_bar_count: int
    # Swing counts by scale
    swings_found: SwingCountsByScale
    # Event-related counts
    swings_invalidated: int
    swings_completed: int
    # Optional event context (if during linger)
    event_context: Optional[PlaybackFeedbackEventContext] = None


class PlaybackFeedbackRequest(BaseModel):
    """Request to submit playback feedback."""
    text: str  # Free-form observation text
    playback_bar: int  # Current playback position
    snapshot: PlaybackFeedbackSnapshot  # Rich context snapshot


class PlaybackFeedbackResponse(BaseModel):
    """Response from feedback submission."""
    success: bool
    observation_id: str
    message: str
