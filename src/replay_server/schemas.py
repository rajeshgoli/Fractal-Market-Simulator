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
    scale: str
    created_at: str
    annotation_count: int
    completed_scales: List[str]


# ============================================================================
# Unified Leg Response (Issue #398 - Schema Unification)
# ============================================================================


class LegResponse(BaseModel):
    """Unified leg response using origin/pivot terminology.

    Uses consistent terminology:
    - Origin: where the move started (fixed)
    - Pivot: defended extreme (extends)

    For bull legs: origin=LOW, pivot=HIGH
    For bear legs: origin=HIGH, pivot=LOW
    """
    leg_id: str
    direction: str  # "bull" or "bear"
    origin_price: float
    origin_index: int
    pivot_price: float
    pivot_index: int
    range: float  # |origin_price - pivot_price|
    rank: int = 1
    is_active: bool = True
    # Hierarchy info
    depth: int = 0  # Hierarchy depth (0 = root)
    parent_leg_id: Optional[str] = None  # Parent leg ID
    # Optional fib levels (computed on request)
    fib_levels: Optional[Dict[str, float]] = None
    # Scale for Reference Layer (computed at runtime, not stored)
    scale: Optional[str] = None  # "S", "M", "L", "XL"


# ============================================================================
# Replay Advance Models
# ============================================================================


class ReplayAdvanceRequest(BaseModel):
    """Request to advance playback."""
    current_bar_index: int
    advance_by: int = 1
    include_aggregated_bars: Optional[List[str]] = None  # Scales to include (e.g., ["S", "M"])
    include_dag_state: bool = False  # Whether to include DAG state (at final bar only)
    include_per_bar_dag_states: bool = False  # Whether to include per-bar DAG states (#283)
    include_per_bar_ref_states: bool = False  # Whether to include per-bar Reference states (#451)
    from_index: Optional[int] = None  # FE position for resync if BE diverged (#310)


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
    type: str  # SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED
    bar_index: int
    scale: str  # Legacy scale for frontend compatibility
    direction: str
    leg_id: str  # ID of the affected leg
    swing: Optional[LegResponse] = None
    trigger_explanation: Optional[str] = None
    # Hierarchy info
    depth: int = 0
    parent_leg_id: Optional[str] = None


class ReplaySwingState(BaseModel):
    """Current state of all swings at a given bar, grouped by depth."""
    depth_1: List[LegResponse] = []  # Root swings (depth 0)
    depth_2: List[LegResponse] = []  # Depth 1
    depth_3: List[LegResponse] = []  # Depth 2
    deeper: List[LegResponse] = []  # Depth 3+


AggregatedBarsResponse = Dict[str, List[BarResponse]]
"""Aggregated bars by scale for chart display.

Uses a dictionary to support arbitrary timeframe keys (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W).
"""


class RefStateSnapshot(BaseModel):
    """Full per-bar reference state for buffered playback (#451, #456, #457, #458, #472).

    Contains complete reference layer state for a specific bar index.
    Used by frontend during high-speed playback to avoid per-bar API calls.
    Matches the DAG pattern where dag_states[] provides full DagStateResponse per bar.
    """
    bar_index: int  # The bar index this snapshot is for
    formed_leg_ids: List[str]  # Leg IDs that were formed at or before this bar
    # Full reference state (#456) - enables batched fetching like DAG
    references: List["ReferenceSwingResponse"] = []  # Top N per pivot, sorted by salience
    active_filtered: List["ReferenceSwingResponse"] = []  # Valid refs that didn't make top N (#457)
    filtered_legs: List["FilteredLegResponse"] = []  # Filtered legs for observation mode
    current_price: float = 0.0  # Bar close price for location calculation
    is_warming_up: bool = True  # Cold start indicator
    warmup_progress: List[int] = [0, 50]  # [current, target]
    median: float = 0.0  # Current rolling median for context
    # Auto-tracking fields (#458) - eliminate per-bar track API calls
    auto_tracked_leg_id: Optional[str] = None  # Which leg the algorithm auto-tracks (top reference if no pin)
    crossing_events: List["LevelCrossEventResponse"] = []  # Level crossings for auto-tracked leg at this bar
    # Filter statistics (#472) - enables Filters panel during playback
    filter_stats: Optional["FilterStatsResponse"] = None  # Filter breakdown statistics


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
    ref_states: Optional[List[RefStateSnapshot]] = None  # Per-bar Reference states (#451)


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


class FeedbackDetectionConfig(BaseModel):
    """Detection config captured in feedback snapshot.

    Records the symmetric detection config at time of observation for reproducibility.
    #404: Config is now symmetric - engulfed_breach_threshold is global, not per-direction.
    """
    stale_extension_threshold: float
    origin_range_threshold: float
    origin_time_threshold: float
    max_turns: int  # Max legs to keep at each pivot by heft (#404)
    engulfed_breach_threshold: float  # Symmetric engulfed threshold (#404)


class PlaybackFeedbackSnapshot(BaseModel):
    """Rich context snapshot for feedback capture."""
    state: str  # playing, paused
    csv_index: int  # Authoritative CSV row index for current position
    current_bar_index: int
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
    # Detection config at time of observation (#320)
    detection_config: Optional[FeedbackDetectionConfig] = None


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
# Tree Statistics Models (Hierarchical UI - Issue #166)
# ============================================================================


class TreeStatistics(BaseModel):
    """Tree structure statistics for hierarchical UI.

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
    largest_range: float  # Largest leg range in points
    largest_leg_id: Optional[str] = None  # ID of largest leg (#398: renamed from largest_swing_id)
    median_range: float  # Median swing range
    smallest_range: float  # Smallest swing range

    # Validation quick-checks
    roots_have_children: bool  # All root swings have at least one child
    siblings_detected: bool  # Sibling swings exist (same 0, different 1s)
    no_orphaned_nodes: bool  # All non-root swings have parents


class LegsByDepth(BaseModel):
    """Legs grouped by hierarchy depth for the UI."""
    depth_1: List[LegResponse] = []  # Root legs (depth 0)
    depth_2: List[LegResponse] = []  # Depth 1
    depth_3: List[LegResponse] = []  # Depth 2
    deeper: List[LegResponse] = []  # Depth 3+


class DagInitResponse(BaseModel):
    """Response from DAG init endpoint with tree statistics.

    This is the response format for issue #166 that uses
    hierarchy-based display instead of scale-based (S/M/L/XL).
    """
    current_price: float

    # Tree statistics
    tree_stats: TreeStatistics

    # Legs grouped by depth
    legs_by_depth: LegsByDepth
    active_legs_by_depth: LegsByDepth


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
    status: str  # "active" or "stale" (#345: invalidated status removed)
    bar_count: int
    # #345: Origin breach tracking - true if origin has been breached (structural invalidation)
    origin_breached: bool = False
    # Raw impulse: price change per bar (range / bar_count) (#491)
    impulse: Optional[float] = None
    # Range: |origin_price - pivot_price| (#491)
    range: Optional[float] = None
    # Hierarchy depth: 0 = root, 1+ = nested under parent (#491)
    depth: int = 0
    # Range bin index: 0-10, median-normalized bin classification (#491)
    bin: Optional[int] = None
    # Impulsiveness (0-100): Percentile rank of raw impulse vs all formed legs (#241)
    # More interpretable than raw impulse - 90+ is very impulsive, 10- is gradual
    impulsiveness: Optional[float] = None
    # Bin-normalized impulsiveness (0-100): Percentile rank of impulse within same bin (#491)
    # More meaningful than global impulsiveness - compares apples to apples
    bin_impulsiveness: Optional[float] = None
    # Spikiness (0-100): Sigmoid-normalized skewness of bar contributions (#241)
    # 50 = neutral, 90+ = spike-driven, 10- = evenly distributed
    spikiness: Optional[float] = None
    # Parent leg ID for hierarchy exploration (#250, #251)
    parent_leg_id: Optional[str] = None
    # Segment impulse tracking (#307): Two-impulse model for parent segments
    # When children form under this leg, tracks: origin -> deepest -> child_origin
    # impulse_to_deepest: Price change per bar from origin to deepest point
    impulse_to_deepest: Optional[float] = None
    # impulse_back: Price change per bar from deepest back to child origin
    impulse_back: Optional[float] = None
    # net_segment_impulse: impulse_to_deepest - impulse_back (sustained conviction)
    # Positive = sustained move, negative = gave back progress
    net_segment_impulse: Optional[float] = None


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
    direction: Optional[str] = None  # bull or bear (may be None for legacy events)
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
    """Per-direction detection configuration parameters (#345, #394: formation_fib removed).

    These control swing detection thresholds for bull or bear directions.
    All values are floats representing Fibonacci ratios (0.0 - 1.0+).
    """
    engulfed_breach_threshold: Optional[float] = None  # Engulfed threshold (default: 0.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "engulfed_breach_threshold": 0.0,
            }
        }
    )


class SwingConfigUpdateRequest(BaseModel):
    """Request to update swing detection configuration.

    All thresholds are symmetric (apply to both bull and bear).
    Only provided fields are updated; omitted fields keep their defaults.
    """
    # Global thresholds (#404: symmetric config)
    stale_extension_threshold: Optional[float] = None  # 3x extension prune (default: 3.0)
    origin_range_threshold: Optional[float] = None  # Origin proximity range threshold (#294)
    origin_time_threshold: Optional[float] = None  # Origin proximity time threshold (#294)
    max_turns: Optional[int] = None  # Max legs per pivot (#404)
    engulfed_breach_threshold: Optional[float] = None  # Symmetric engulfed threshold (#404)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "stale_extension_threshold": 3.0,
                "origin_range_threshold": 0.02,
                "origin_time_threshold": 0.02,
                "max_turns": 10,
                "engulfed_breach_threshold": 0.236
            }
        }
    )


class SwingConfigResponse(BaseModel):
    """Response with current swing detection configuration.

    Returns all current values after an update, or the current defaults.
    #404: Symmetric config - engulfed threshold applies to both directions.
    """
    stale_extension_threshold: float
    origin_range_threshold: float  # Origin proximity range threshold (#294)
    origin_time_threshold: float  # Origin proximity time threshold (#294)
    max_turns: int  # Max legs per pivot (#404)
    engulfed_breach_threshold: float  # Symmetric engulfed threshold (#404)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "stale_extension_threshold": 3.0,
                "origin_range_threshold": 0.02,
                "origin_time_threshold": 0.02,
                "max_turns": 10,
                "engulfed_breach_threshold": 0.236
            }
        }
    )


# ============================================================================
# Reference Layer Models (Issue #375, #388 - Reference Layer UI)
# ============================================================================


class ReferenceSwingResponse(BaseModel):
    """API response for a single reference swing from the Reference Layer (#436)."""
    leg_id: str
    bin: int  # 0-10 median-normalized bin index (#436)
    median_multiple: float  # e.g., 2.5 means 2.5× median range (#436)
    depth: int
    location: float  # 0.0 - 2.0 (where current price is within leg range)
    salience_score: float
    direction: str  # "bull" or "bear"
    origin_price: float
    origin_index: int
    pivot_price: float
    pivot_index: int
    impulsiveness: Optional[float] = None  # Impulsiveness score (Issue #415)


class ReferenceStateApiResponse(BaseModel):
    """API response for reference layer state (#436, #457)."""
    references: List[ReferenceSwingResponse]  # Top N per pivot, sorted by salience
    active_filtered: List[ReferenceSwingResponse] = []  # Valid refs that didn't make top N (#457)
    by_bin: Dict[int, List[ReferenceSwingResponse]]  # Grouped by bin index (#436)
    significant: List[ReferenceSwingResponse]  # Bin >= 8 (5× median or larger) (#436)
    by_depth: Dict[int, List[ReferenceSwingResponse]]
    by_direction: Dict[str, List[ReferenceSwingResponse]]
    direction_imbalance: Optional[str]  # "bull", "bear", or None
    is_warming_up: bool
    warmup_progress: List[int]  # [current, target]
    tracked_leg_ids: List[str] = []  # Leg IDs tracked for level crossing
    median: float = 0.0  # Current rolling median for context (#436)
    # Reference Observation Mode (Issue #400)
    filtered_legs: List['FilteredLegResponse'] = []  # All non-valid legs with reasons
    filter_stats: Optional['FilterStatsResponse'] = None  # Filter breakdown statistics
    # Level Crossing Events (Issue #416, #417)
    crossing_events: List['LevelCrossEventResponse'] = []  # Events from this bar


class FibLevelResponse(BaseModel):
    """API response for a single fib level from Reference Layer (#436)."""
    price: float
    ratio: float
    leg_id: str
    bin: int  # 0-10 median-normalized bin index (#436)
    median_multiple: float = 1.0  # Ratio to running median (#436)
    direction: str  # "bull" or "bear"


class ActiveLevelsResponse(BaseModel):
    """API response for all active fib levels from valid references."""
    levels_by_ratio: Dict[str, List[FibLevelResponse]]  # Keyed by ratio as string


# ============================================================================
# Reference Observation Models (Issue #400 - Reference Observation Mode)
# ============================================================================


class FilteredLegResponse(BaseModel):
    """API response for a filtered leg with filter reason (#436, #454)."""
    leg_id: str
    direction: str  # "bull" or "bear"
    origin_price: float
    origin_index: int
    pivot_price: float
    pivot_index: int
    bin: int  # 0-10 median-normalized bin index (#436)
    filter_reason: str  # "valid", "cold_start", "not_formed", "pivot_breached", "completed" (#454: removed origin_breached)
    location: float  # 0.0 - completion_threshold (current price position in reference frame)
    threshold: Optional[float] = None  # Violated threshold (for breach reasons)


class FilterStatsResponse(BaseModel):
    """API response for filter statistics."""
    total_legs: int
    valid_count: int
    pass_rate: float
    by_reason: Dict[str, int]  # Counts by filter reason


# ============================================================================
# Confluence Zone Models (Issue #415 - Reference Layer P3)
# ============================================================================


class ConfluenceZoneLevelResponse(BaseModel):
    """A fib level participating in a confluence zone (#436)."""
    price: float
    ratio: float
    leg_id: str
    bin: int  # 0-10 median-normalized bin index (#436)
    median_multiple: float = 1.0  # Ratio to running median (#436)
    direction: str


class ConfluenceZoneResponse(BaseModel):
    """API response for a confluence zone - clustered fib levels from multiple references."""
    center_price: float
    min_price: float
    max_price: float
    levels: List[ConfluenceZoneLevelResponse]
    reference_count: int
    reference_ids: List[str]


class ConfluenceZonesResponse(BaseModel):
    """API response for all confluence zones from valid references."""
    zones: List[ConfluenceZoneResponse]
    tolerance_pct: float  # The tolerance used for clustering


# ============================================================================
# Structure Panel Models (Issue #415 - Reference Layer P3)
# ============================================================================


class LevelTouchResponse(BaseModel):
    """API response for a level touch/cross event (#436)."""
    price: float
    ratio: float
    leg_id: str
    bin: int  # 0-10 median-normalized bin index (#436)
    median_multiple: float = 1.0  # Ratio to running median (#436)
    direction: str
    bar_index: int
    touch_price: float
    cross_direction: str  # 'up' | 'down'


class StructurePanelResponse(BaseModel):
    """
    API response for Structure Panel data.

    Three sections per spec:
    1. Touched this session - Historical record of which levels were hit
    2. Currently active - Levels within striking distance of current price
    3. Current bar - Levels touched on most recent bar
    """
    touched_this_session: List[LevelTouchResponse]
    currently_active: List[FibLevelResponse]
    current_bar_touches: List[LevelTouchResponse]
    current_price: float
    active_level_distance_pct: float  # The threshold used for "striking distance"


# ============================================================================
# Telemetry Panel Models (Issue #415 - Reference Layer P3)
# ============================================================================


class TopReferenceResponse(BaseModel):
    """API response for a top reference (biggest or most impulsive) (#436)."""
    leg_id: str
    bin: int  # 0-10 median-normalized bin index (#436)
    direction: str
    range_value: float
    impulsiveness: Optional[float]
    salience_score: float


class TelemetryPanelResponse(BaseModel):
    """
    API response for Telemetry Panel data (#436).

    Shows real-time reference state like DAG's market structure panel:
    - Reference counts by bin
    - Direction imbalance
    - Top references (biggest, most impulsive)
    """
    counts_by_bin: Dict[int, int]  # {8: 5, 9: 3, 10: 1} (#436)
    significant_count: int  # Bin >= 8 (#436)
    total_count: int
    bull_count: int
    bear_count: int
    direction_imbalance: Optional[str]  # "bull" | "bear" | None
    imbalance_ratio: Optional[str]  # e.g., "3:1"
    median: float  # Current rolling median (#436)
    biggest_reference: Optional[TopReferenceResponse]
    most_impulsive: Optional[TopReferenceResponse]


# ============================================================================
# Level Crossing Models (Issue #416, #417 - Reference Layer P4)
# ============================================================================


class LevelCrossEventResponse(BaseModel):
    """
    API response for a level crossing event.

    Emitted when price crosses a fib level for a tracked leg.
    """
    leg_id: str
    direction: str  # "bull" or "bear"
    level_crossed: float  # The fib level (0, 0.382, 0.5, etc.)
    cross_direction: str  # "up" or "down"
    bar_index: int
    timestamp: str  # ISO format


class CrossingEventsResponse(BaseModel):
    """
    API response for level crossing events.

    Contains all crossing events detected since last retrieval.
    """
    events: List[LevelCrossEventResponse]
    tracked_count: int  # Number of legs being tracked


class TrackLegResponse(BaseModel):
    """
    API response for track/untrack leg operations.
    """
    success: bool
    leg_id: str
    tracked_count: int
    error: Optional[str] = None  # Error message if success is False


# ============================================================================
# Reference Config Models (Issue #423 - ReferenceConfig API)
# ============================================================================


class ReferenceConfigUpdateRequest(BaseModel):
    """
    Request to update reference layer configuration (#436, #442, #454).

    All fields are optional - only provided fields are updated.
    Used by POST /api/reference/config to apply partial updates.
    Uses unified additive weights (no special modes).
    """
    # Unified salience weights (#436, #442)
    range_weight: Optional[float] = None
    impulse_weight: Optional[float] = None
    recency_weight: Optional[float] = None
    depth_weight: Optional[float] = None
    # Counter-trend range weight (#442) — normalized via median × 25
    counter_weight: Optional[float] = None
    # Range × Counter product weight (#442) — normalized via (median × 25)²
    range_counter_weight: Optional[float] = None

    # Display limit: how many references to show
    top_n: Optional[int] = None

    # Formation threshold
    formation_fib_threshold: Optional[float] = None

    # Pivot breach tolerance (#454: renamed from origin_breach_tolerance)
    # For bins < significant_bin_threshold, leg is breached when location < -tolerance
    pivot_breach_tolerance: Optional[float] = None

    # Completion threshold (#454)
    completion_threshold: Optional[float] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "range_weight": 0.4,
                "impulse_weight": 0.4,
                "recency_weight": 0.1,
                "depth_weight": 0.1,
                "counter_weight": 0.0,
                "range_counter_weight": 0.0,
                "formation_fib_threshold": 0.5,
                "pivot_breach_tolerance": 0.0,
                "completion_threshold": 2.0,
                "top_n": 5,
            }
        }
    )


class ReferenceConfigResponse(BaseModel):
    """
    Response with current reference layer configuration (#436, #442, #454).

    Returns all current values after an update, or the current defaults.
    Uses unified additive weights (no special modes).
    """
    # Unified salience weights (#436, #442)
    range_weight: float
    impulse_weight: float
    recency_weight: float
    depth_weight: float
    # Counter-trend range weight (#442)
    counter_weight: float
    # Range × Counter product weight (#442)
    range_counter_weight: float

    # Display limit: how many references to show
    top_n: int

    # Formation threshold
    formation_fib_threshold: float

    # Pivot breach tolerance (#454: renamed from origin_breach_tolerance)
    # For bins < significant_bin_threshold, leg is breached when location < -tolerance
    pivot_breach_tolerance: float

    # Completion threshold (#454)
    completion_threshold: float

    # Bin classification
    significant_bin_threshold: int  # Bins >= this get breach tolerance (#436)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "range_weight": 0.4,
                "impulse_weight": 0.4,
                "recency_weight": 0.1,
                "depth_weight": 0.1,
                "counter_weight": 0.0,
                "range_counter_weight": 0.0,
                "top_n": 5,
                "formation_fib_threshold": 0.382,
                "pivot_breach_tolerance": 0.0,
                "completion_threshold": 2.0,
                "significant_bin_threshold": 8,
            }
        }
    )
