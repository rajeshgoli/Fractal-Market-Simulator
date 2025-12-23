"""
Pydantic models for the Replay View API.

All request/response schemas for replay endpoints.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


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
    include_aggregated_bars: Optional[List[str]] = None  # Scales to include (e.g., ["S", "M"])
    include_dag_state: bool = False  # Whether to include DAG state (at final bar only)
    include_per_bar_dag_states: bool = False  # Whether to include per-bar DAG states (#283)


class ReplayReverseRequest(BaseModel):
    """Request to reverse playback by one bar.

    Implementation: resets detector and replays from bar 0 to current_bar_index - 1.
    """
    current_bar_index: int
    include_aggregated_bars: Optional[List[str]] = None
    include_dag_state: bool = False


class ReplayBarResponse(BaseModel):
    """A single OHLC bar returned during playback advance."""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    csv_index: int  # Original row index in source CSV file


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
    """Current state of all swings at a given bar, grouped by depth."""
    depth_1: List[CalibrationSwingResponse] = []  # Root swings (depth 0)
    depth_2: List[CalibrationSwingResponse] = []  # Depth 1
    depth_3: List[CalibrationSwingResponse] = []  # Depth 2
    deeper: List[CalibrationSwingResponse] = []  # Depth 3+


AggregatedBarsResponse = Dict[str, List[BarResponse]]
"""Aggregated bars by scale for chart display.

Uses a dictionary to support arbitrary timeframe keys (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W).
"""


class ReplayAdvanceResponse(BaseModel):
    """Response from advance endpoint."""
    new_bars: List[ReplayBarResponse]
    events: List[ReplayEventResponse]
    swing_state: ReplaySwingState
    current_bar_index: int
    current_price: float
    end_of_data: bool
    csv_index: int  # Authoritative CSV row index (window_offset + current_bar_index)
    # Optional fields for batched playback (reduces API calls)
    aggregated_bars: Optional[AggregatedBarsResponse] = None
    dag_state: Optional["DagStateResponse"] = None  # DAG state at final bar only
    dag_states: Optional[List["DagStateResponse"]] = None  # Per-bar DAG states (#283)


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


class ReplayContext(BaseModel):
    """Replay mode-specific context."""
    selected_swing: Optional[Dict] = None
    calibration_state: Optional[str] = None


class DagFeedbackLeg(BaseModel):
    """A leg captured in feedback snapshot."""
    leg_id: str
    direction: str  # "bull" or "bear"
    pivot_price: float
    pivot_index: int
    origin_price: float
    origin_index: int
    range: float  # |origin_price - pivot_price|


class DagFeedbackOrigin(BaseModel):
    """An origin captured in feedback snapshot."""
    price: float
    bar_index: int


class DagFeedbackPendingOrigin(BaseModel):
    """A pending origin captured in feedback snapshot."""
    price: float
    bar_index: int


class DagContext(BaseModel):
    """DAG mode-specific context with full leg/origin/pivot data for debugging."""
    active_legs: List[DagFeedbackLeg] = []
    pending_origins: Optional[Dict[str, Optional[DagFeedbackPendingOrigin]]] = None


# ============================================================================
# Feedback Attachment Models
# ============================================================================


class FeedbackAttachmentLeg(BaseModel):
    """A leg attachment in feedback."""
    type: str = "leg"
    leg_id: str
    direction: str  # "bull" or "bear"
    pivot_price: float
    origin_price: float
    pivot_index: int
    origin_index: int
    csv_index: Optional[int] = None  # Current bar's CSV index when attached


class FeedbackAttachmentPendingOrigin(BaseModel):
    """A pending origin attachment in feedback."""
    type: str = "pending_origin"
    direction: str  # "bull" or "bear"
    price: float
    bar_index: int
    source: str  # "high", "low", "open", "close"
    csv_index: Optional[int] = None  # CSV index of the pending origin bar


class FeedbackAttachmentLifecycleEvent(BaseModel):
    """A lifecycle event attachment in feedback (for Follow Leg feature)."""
    type: str = "lifecycle_event"
    leg_id: str
    leg_direction: str  # "bull" or "bear"
    event_type: str  # formed, origin_breached, pivot_breached, engulfed, pruned, invalidated
    bar_index: int
    csv_index: int
    timestamp: str  # ISO format timestamp
    explanation: str


class PlaybackFeedbackSnapshot(BaseModel):
    """Rich context snapshot for feedback capture."""
    state: str  # calibrating, calibration_complete, playing, paused
    csv_index: int  # Authoritative CSV row index for current position
    bars_since_calibration: int
    current_bar_index: int
    calibration_bar_count: int
    swings_found: SwingCountsByScale
    swings_invalidated: int
    swings_completed: int
    event_context: Optional[PlaybackFeedbackEventContext] = None
    # Mode (replay or dag)
    mode: Optional[str] = None
    # Mode-specific context
    replay_context: Optional[ReplayContext] = None
    dag_context: Optional[DagContext] = None
    # Attachments (legs, pending origins, lifecycle events)
    attachments: Optional[List[Union[
        FeedbackAttachmentLeg,
        FeedbackAttachmentPendingOrigin,
        FeedbackAttachmentLifecycleEvent
    ]]] = None


class PlaybackFeedbackRequest(BaseModel):
    """Request to submit playback feedback."""
    text: str
    playback_bar: int
    snapshot: PlaybackFeedbackSnapshot
    screenshot_data: Optional[str] = None  # Base64 encoded PNG


class PlaybackFeedbackResponse(BaseModel):
    """Response from feedback submission."""
    success: bool
    observation_id: str
    message: str


# ============================================================================
# Hierarchical Swing Models (V2 - Rewrite Phase 3)
# ============================================================================


class HierarchicalSwingResponse(BaseModel):
    """Response schema for a swing in the hierarchical model.

    Replaces scale-based classification with tree hierarchy.
    """
    swing_id: str
    high_bar_index: int
    high_price: float
    low_bar_index: int
    low_price: float
    direction: str  # "bull" or "bear"
    status: str  # "forming", "active", "invalidated", "completed"
    formed_at_bar: int

    # Hierarchy info (replaces scale)
    parent_ids: List[str]
    child_ids: List[str]
    depth: int  # Hierarchy depth (0 = root)

    # Fib levels (computed)
    fib_0: float  # Defended pivot
    fib_0382: float
    fib_0618: float
    fib_1: float  # Origin
    fib_2: float  # Target

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "swing_id": "abc123",
                "high_bar_index": 100,
                "high_price": 6166.0,
                "low_bar_index": 200,
                "low_price": 4832.0,
                "direction": "bull",
                "status": "active",
                "formed_at_bar": 210,
                "parent_ids": [],
                "child_ids": ["def456", "ghi789"],
                "depth": 0,
                "fib_0": 4832.0,
                "fib_0382": 5341.98,
                "fib_0618": 5657.02,
                "fib_1": 6166.0,
                "fib_2": 7500.0,
            }
        }
    )


class SwingEventResponse(BaseModel):
    """Response schema for swing events in hierarchical model."""
    event_type: str  # SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED, LEVEL_CROSS
    bar_index: int
    timestamp: Optional[str] = None
    swing_id: str
    explanation: str  # Human-readable trigger explanation

    # Event-specific fields (optional based on type)
    parent_ids: Optional[List[str]] = None  # For SWING_FORMED
    violation_price: Optional[float] = None  # For SWING_INVALIDATED
    excess_amount: Optional[float] = None  # For SWING_INVALIDATED
    level: Optional[float] = None  # For LEVEL_CROSS
    previous_level: Optional[float] = None  # For LEVEL_CROSS


class CalibrationSwingResponseV2(BaseModel):
    """Updated calibration swing response with hierarchy info.

    V2 schema removes scale dependency and uses hierarchy depth.
    """
    swing_id: str
    high_bar_index: int
    high_price: float
    low_bar_index: int
    low_price: float
    direction: str
    status: str

    # Hierarchy (replaces scale)
    depth: int
    parent_ids: List[str]

    # Fib levels
    fib_0: float
    fib_0382: float
    fib_1: float
    fib_2: float

    # Activity status
    is_active: bool


class CalibrationResponseV2(BaseModel):
    """Updated calibration response for hierarchical model.

    V2 schema groups swings by hierarchy depth instead of scale.
    """
    swings: List[CalibrationSwingResponseV2]
    total_bars: int
    calibration_bars: int

    # Hierarchy stats (replaces per-scale stats)
    max_depth: int
    swing_count_by_depth: Dict[str, int]  # {"0": 2, "1": 5, "2": 12, ...}


# ============================================================================
# Tree Statistics Models (Hierarchical UI - Issue #166)
# ============================================================================


class TreeStatistics(BaseModel):
    """Tree structure statistics for hierarchical calibration UI.

    Replaces S/M/L/XL scale-based display with hierarchy-based display.
    """
    root_swings: int  # Swings with no parents (depth 0)
    root_bull: int  # Bull swings at root level
    root_bear: int  # Bear swings at root level
    total_nodes: int  # Total swing count
    max_depth: int  # Maximum hierarchy depth
    avg_children: float  # Average children per node

    # Defended swings grouped by depth
    defended_by_depth: Dict[str, int]  # {"1": 12, "2": 38, "3": 94, "deeper": 186}

    # Range distribution
    largest_range: float  # Largest swing range in points
    largest_swing_id: Optional[str] = None  # ID of largest swing
    median_range: float  # Median swing range
    smallest_range: float  # Smallest swing range

    # Recently invalidated count
    recently_invalidated: int  # Swings invalidated in last N bars

    # Validation quick-checks
    roots_have_children: bool  # All root swings have at least one child
    siblings_detected: bool  # Sibling swings exist (same 0, different 1s)
    no_orphaned_nodes: bool  # All non-root swings have parents


class SwingsByDepth(BaseModel):
    """Swings grouped by hierarchy depth for the new UI."""
    depth_1: List[CalibrationSwingResponse] = []  # Root swings (depth 0)
    depth_2: List[CalibrationSwingResponse] = []  # Depth 1
    depth_3: List[CalibrationSwingResponse] = []  # Depth 2
    deeper: List[CalibrationSwingResponse] = []  # Depth 3+


class CalibrationResponseHierarchical(BaseModel):
    """Calibration response with hierarchical tree statistics.

    This is the response format for issue #166 that uses
    hierarchy-based display instead of scale-based (S/M/L/XL).
    """
    calibration_bar_count: int
    current_price: float

    # Tree statistics
    tree_stats: TreeStatistics

    # Swings grouped by depth
    swings_by_depth: SwingsByDepth
    active_swings_by_depth: SwingsByDepth


# ============================================================================
# DAG State Models (Issue #169 - DAG Visualization)
# ============================================================================


class DagLegResponse(BaseModel):
    """A leg in the DAG (pre-formation candidate swing)."""
    leg_id: str
    direction: str  # "bull" or "bear"
    pivot_price: float
    pivot_index: int
    origin_price: float
    origin_index: int
    retracement_pct: float
    formed: bool
    status: str  # "active", "stale", or "invalidated"
    bar_count: int
    # Impulsiveness (0-100): Percentile rank of raw impulse vs all formed legs (#241)
    # More interpretable than raw impulse - 90+ is very impulsive, 10- is gradual
    impulsiveness: Optional[float] = None
    # Spikiness (0-100): Sigmoid-normalized skewness of bar contributions (#241)
    # 50 = neutral, 90+ = spike-driven, 10- = evenly distributed
    spikiness: Optional[float] = None
    # Parent leg ID for hierarchy exploration (#250, #251)
    parent_leg_id: Optional[str] = None
    # Swing ID if this leg has formed into a swing
    swing_id: Optional[str] = None


class DagPendingOrigin(BaseModel):
    """A potential origin for a new leg awaiting temporal confirmation.

    For bull legs: tracks LOWs (bull origin = where upward move starts)
    For bear legs: tracks HIGHs (bear origin = where downward move starts)
    """
    price: float
    bar_index: int
    direction: str  # "bull" or "bear"
    source: str  # "high", "low", "open", "close"


class DagLegCounts(BaseModel):
    """Leg counts by direction."""
    bull: int
    bear: int


class DagStateResponse(BaseModel):
    """Response from DAG state endpoint for visualization.

    Exposes internal detector state for debugging and visualization.
    """
    active_legs: List[DagLegResponse]
    pending_origins: Dict[str, Optional[DagPendingOrigin]]
    leg_counts: DagLegCounts


# ============================================================================
# Hierarchy Exploration Models (Issue #250 - Hierarchy Exploration Mode)
# ============================================================================


class LegLineageResponse(BaseModel):
    """Response from lineage endpoint for hierarchy exploration.

    Given a leg ID, returns full ancestry chain and all descendants.
    Used by the frontend to highlight the selected leg's hierarchy.
    """
    # The leg being queried
    leg_id: str
    # Full ancestry chain from this leg up to root (parent, grandparent, ...)
    # Ordered from immediate parent to root
    ancestors: List[str]
    # All descendants (children, grandchildren, etc.)
    # Flat list of all leg IDs descended from this leg
    descendants: List[str]
    # Depth in hierarchy (0 = root, 1 = has one parent, etc.)
    depth: int


# ============================================================================
# Follow Leg Models (Issue #267 - Follow Leg Feature)
# ============================================================================


class LifecycleEvent(BaseModel):
    """A lifecycle event for a followed leg.

    Tracks significant state changes for legs being followed by the user.
    """
    leg_id: str
    event_type: str  # formed, origin_breached, pivot_breached, engulfed, pruned, invalidated
    bar_index: int
    csv_index: int
    timestamp: str  # ISO format
    explanation: str


class FollowedLegsEventsRequest(BaseModel):
    """Request for lifecycle events of followed legs."""
    leg_ids: List[str]
    since_bar: int


class FollowedLegsEventsResponse(BaseModel):
    """Response with lifecycle events for followed legs."""
    events: List[LifecycleEvent]


# ============================================================================
# Detection Config Models (Issue #288 - Detection Config UI Panel)
# ============================================================================


class DirectionConfigRequest(BaseModel):
    """Per-direction detection configuration parameters.

    These control swing detection thresholds for bull or bear directions.
    All values are floats representing Fibonacci ratios (0.0 - 1.0+).
    """
    formation_fib: Optional[float] = None  # Formation threshold (default: 0.287)
    invalidation_threshold: Optional[float] = None  # Invalidation threshold (default: 0.382)
    pivot_breach_threshold: Optional[float] = None  # Pivot breach threshold (default: 0.10)
    engulfed_breach_threshold: Optional[float] = None  # Engulfed threshold (default: 0.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "formation_fib": 0.382,
                "invalidation_threshold": 0.382,
                "completion_fib": 2.0,
                "pivot_breach_threshold": 0.10,
                "engulfed_breach_threshold": 0.20,
            }
        }
    )


class SwingConfigUpdateRequest(BaseModel):
    """Request to update swing detection configuration.

    Allows updating bull/bear direction configs and global thresholds.
    Only provided fields are updated; omitted fields keep their defaults.
    """
    bull: Optional[DirectionConfigRequest] = None
    bear: Optional[DirectionConfigRequest] = None
    # Global thresholds
    stale_extension_threshold: Optional[float] = None  # 3x extension prune (default: 3.0)
    origin_range_threshold: Optional[float] = None  # Origin proximity range threshold (#294)
    origin_time_threshold: Optional[float] = None  # Origin proximity time threshold (#294)
    # Pruning algorithm toggles
    enable_engulfed_prune: Optional[bool] = None  # Enable engulfed leg deletion (default: True)
    enable_inner_structure_prune: Optional[bool] = None  # Enable inner structure pruning (default: True)
    enable_turn_prune: Optional[bool] = None  # Enable turn-based consolidation (default: True)
    enable_pivot_breach_prune: Optional[bool] = None  # Enable pivot breach replacement (default: True)
    enable_domination_prune: Optional[bool] = None  # Enable domination pruning (default: True)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bull": {
                    "formation_fib": 0.382,
                    "invalidation_threshold": 0.382
                },
                "bear": {
                    "formation_fib": 0.382,
                    "invalidation_threshold": 0.382
                },
                "stale_extension_threshold": 3.0,
                "origin_range_threshold": 0.05,
                "origin_time_threshold": 0.10,
                "enable_engulfed_prune": True,
                "enable_inner_structure_prune": True,
                "enable_turn_prune": True,
                "enable_pivot_breach_prune": True,
                "enable_domination_prune": True
            }
        }
    )


class DirectionConfigResponse(BaseModel):
    """Per-direction configuration values in response."""
    formation_fib: float
    invalidation_threshold: float
    pivot_breach_threshold: float
    engulfed_breach_threshold: float


class SwingConfigResponse(BaseModel):
    """Response with current swing detection configuration.

    Returns all current values after an update, or the current defaults.
    """
    bull: DirectionConfigResponse
    bear: DirectionConfigResponse
    stale_extension_threshold: float
    origin_range_threshold: float  # Origin proximity range threshold (#294)
    origin_time_threshold: float  # Origin proximity time threshold (#294)
    # Pruning algorithm toggles
    enable_engulfed_prune: bool
    enable_inner_structure_prune: bool
    enable_turn_prune: bool
    enable_pivot_breach_prune: bool
    enable_domination_prune: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bull": {
                    "formation_fib": 0.382,
                    "invalidation_threshold": 0.382,
                    "pivot_breach_threshold": 0.10,
                    "engulfed_breach_threshold": 0.20
                },
                "bear": {
                    "formation_fib": 0.382,
                    "invalidation_threshold": 0.382,
                    "pivot_breach_threshold": 0.10,
                    "engulfed_breach_threshold": 0.20
                },
                "stale_extension_threshold": 3.0,
                "origin_range_threshold": 0.05,
                "origin_time_threshold": 0.10,
                "enable_engulfed_prune": True,
                "enable_inner_structure_prune": True,
                "enable_turn_prune": True,
                "enable_pivot_breach_prune": True,
                "enable_domination_prune": True
            }
        }
    )
