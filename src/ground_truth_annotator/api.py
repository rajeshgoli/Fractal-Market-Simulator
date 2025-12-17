"""
FastAPI backend for the Ground Truth Annotator.

Provides REST API endpoints for:
- Serving aggregated bars for chart display
- Creating, listing, and deleting annotations
- Session state management
- Cascade workflow (XL → L → M → S scale progression)
"""

import asyncio
import logging
import random
import threading
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cascade_controller import CascadeController
from .comparison_analyzer import ComparisonAnalyzer, ComparisonResult
from .csv_utils import escape_csv_field
from .models import AnnotationSession, SwingAnnotation
from .review_controller import ReviewController
from .storage import AnnotationStorage, ReviewStorage
from ..data.ohlc_loader import load_ohlc
from ..discretization import (
    Discretizer,
    DiscretizerConfig,
    DiscretizationLog,
    EventType,
)
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.types import Bar
from ..swing_analysis.swing_detector import detect_swings, ReferenceSwing

logger = logging.getLogger(__name__)


# Pydantic models for API
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


def _annotation_to_response(ann: SwingAnnotation) -> AnnotationResponse:
    """Convert domain model to API response."""
    return AnnotationResponse(
        annotation_id=ann.annotation_id,
        scale=ann.scale,
        direction=ann.direction,
        start_bar_index=ann.start_bar_index,
        end_bar_index=ann.end_bar_index,
        start_source_index=ann.start_source_index,
        end_source_index=ann.end_source_index,
        start_price=str(ann.start_price),
        end_price=str(ann.end_price),
        created_at=ann.created_at.isoformat(),
        window_id=ann.window_id
    )


class SessionResponse(BaseModel):
    """Session state returned by the API."""
    session_id: str
    data_file: str
    resolution: str
    window_size: int
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


# Review Mode API Models
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


class NextSessionResponse(BaseModel):
    """Response from creating a new session with random offset."""
    session_id: str
    offset: int
    redirect_url: str


# ============================================================================
# Discretization API Models
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


@dataclass
class AppState:
    """Application state."""
    source_bars: List[Bar]
    aggregated_bars: List[Bar]
    aggregation_map: dict  # aggregated_index -> (source_start, source_end)
    storage: AnnotationStorage
    session: AnnotationSession
    scale: str
    target_bars: int
    cascade_controller: Optional[CascadeController] = None
    aggregator: Optional[BarAggregator] = None
    comparison_report: Optional[dict] = None  # Latest comparison report
    review_storage: Optional[ReviewStorage] = None
    review_controller: Optional[ReviewController] = None
    comparison_results: Optional[Dict[str, ComparisonResult]] = None  # Cached comparison
    # Fields for session/next endpoint
    data_file: Optional[str] = None
    storage_dir: Optional[str] = None
    resolution_minutes: int = 1
    total_source_bars: int = 0  # Total bars in file (before offset/windowing)
    cascade_enabled: bool = False
    # Cached DataFrame to avoid re-reading file on next window
    cached_dataframe: Optional[pd.DataFrame] = None
    # Background precomputation tracking
    precompute_in_progress: bool = False
    precompute_thread: Optional[threading.Thread] = None
    # Discretization state
    discretization_log: Optional[DiscretizationLog] = None
    # Replay playback state (backend-controlled data boundary)
    playback_index: Optional[int] = None  # Current visible bar index (None = full dataset)
    calibration_bar_count: Optional[int] = None  # Bars loaded for calibration


# Global state
state: Optional[AppState] = None

app = FastAPI(
    title="Ground Truth Annotator",
    description="Two-click swing annotation tool",
    version="0.1.0",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_state() -> AppState:
    """Get the application state."""
    if state is None:
        raise HTTPException(
            status_code=500,
            detail="Application not initialized. Start server with --data flag."
        )
    return state


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the annotation UI."""
    module_dir = Path(__file__).parent
    index_path = module_dir / "static" / "index.html"

    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Ground Truth Annotator</h1><p>Frontend not found. Place index.html in static/</p>",
            status_code=200
        )

    with open(index_path, 'r') as f:
        return HTMLResponse(content=f.read())


@app.get("/review", response_class=HTMLResponse)
async def review_page():
    """Serve the Review Mode UI."""
    module_dir = Path(__file__).parent
    review_path = module_dir / "static" / "review.html"

    if not review_path.exists():
        return HTMLResponse(
            content="<h1>Review Mode</h1><p>review.html not found. Place review.html in static/</p>",
            status_code=200
        )

    with open(review_path, 'r') as f:
        return HTMLResponse(content=f.read())


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "initialized": state is not None,
    }


@app.get("/api/bars", response_model=List[BarResponse])
async def get_bars(
    scale: Optional[str] = Query(None, description="Scale to get bars for (XL, L, M, S)"),
    limit: Optional[int] = Query(None, description="Limit to first N source bars (for calibration window)")
):
    """
    Get aggregated bars for chart display.

    Returns bars aggregated to the target count for efficient visualization.
    Scale options: S (source), M (~800 bars), L (~200 bars), XL (~50 bars)

    If limit is specified, only bars derived from the first N source bars are returned.
    This is used during calibration to avoid loading bars beyond the calibration window.

    When playback_index is set (via /api/replay/calibrate or /api/replay/advance),
    it takes precedence over limit for determining the maximum visible source bar.
    """
    s = get_state()

    # Compute effective limit based on playback_index (backend-controlled data boundary)
    # playback_index is the last visible bar index, so effective_limit = playback_index + 1
    effective_limit = limit
    if s.playback_index is not None:
        playback_limit = s.playback_index + 1
        if effective_limit is not None:
            effective_limit = min(effective_limit, playback_limit)
        else:
            effective_limit = playback_limit
    # Use effective_limit instead of limit for all filtering below
    limit = effective_limit

    # If scale specified and cascade controller available, use cascade bars
    if scale and s.cascade_controller:
        try:
            scale_bars = s.cascade_controller.get_bars_for_scale(scale)
            agg_map = s.cascade_controller.get_aggregation_map(scale)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        bars = []
        for agg_bar in scale_bars:
            source_start, source_end = agg_map.get(agg_bar.index, (agg_bar.index, agg_bar.index))
            # Apply limit: only include bars where source_end_index < limit
            if limit is not None and source_end > limit - 1:
                break
            bars.append(BarResponse(
                index=agg_bar.index,
                timestamp=agg_bar.timestamp,
                open=agg_bar.open,
                high=agg_bar.high,
                low=agg_bar.low,
                close=agg_bar.close,
                source_start_index=source_start,
                source_end_index=source_end,
            ))
        return bars

    # Handle scale without cascade controller (e.g., Replay View)
    if scale and s.aggregator:
        # Scale target bar counts (matching CascadeController.SCALE_TARGET_BARS)
        scale_targets = {"XL": 50, "L": 200, "M": 800, "S": None}
        target = scale_targets.get(scale.upper())

        if scale.upper() == "S" or target is None:
            # S scale: return source bars directly with 1:1 mapping
            bars = []
            source_bars_to_use = s.source_bars[:limit] if limit is not None else s.source_bars
            for i, src_bar in enumerate(source_bars_to_use):
                bars.append(BarResponse(
                    index=i,
                    timestamp=src_bar.timestamp,
                    open=src_bar.open,
                    high=src_bar.high,
                    low=src_bar.low,
                    close=src_bar.close,
                    source_start_index=i,
                    source_end_index=i,
                ))
            return bars
        else:
            # Aggregate to target bar count
            # If limit specified, create a temporary aggregator for the limited source bars
            if limit is not None:
                from src.swing_analysis.bar_aggregator import BarAggregator
                limited_bars = s.source_bars[:limit]
                temp_aggregator = BarAggregator(limited_bars)
                agg_bars = temp_aggregator.aggregate_to_target_bars(target)
                source_bar_count = limit
            else:
                agg_bars = s.aggregator.aggregate_to_target_bars(target)
                source_bar_count = len(s.source_bars)

            bars_per_candle = source_bar_count // target if source_bar_count > target else 1
            bars = []
            for i, agg_bar in enumerate(agg_bars):
                source_start = i * bars_per_candle
                source_end = min(source_start + bars_per_candle - 1, source_bar_count - 1)
                bars.append(BarResponse(
                    index=i,
                    timestamp=agg_bar.timestamp,
                    open=agg_bar.open,
                    high=agg_bar.high,
                    low=agg_bar.low,
                    close=agg_bar.close,
                    source_start_index=source_start,
                    source_end_index=source_end,
                ))
            return bars

    # Default: return pre-computed aggregated bars
    bars = []
    for agg_bar in s.aggregated_bars:
        source_start, source_end = s.aggregation_map.get(agg_bar.index, (agg_bar.index, agg_bar.index))
        bars.append(BarResponse(
            index=agg_bar.index,
            timestamp=agg_bar.timestamp,
            open=agg_bar.open,
            high=agg_bar.high,
            low=agg_bar.low,
            close=agg_bar.close,
            source_start_index=source_start,
            source_end_index=source_end,
        ))

    return bars


@app.post("/api/annotations", response_model=AnnotationResponse)
async def create_annotation(request: AnnotationCreate):
    """
    Create a new swing annotation.

    Direction is inferred from price movement:
    - If start.high > end.high -> bull reference (downswing)
    - If start.low < end.low -> bear reference (upswing)
    """
    s = get_state()

    # Validate indices
    if request.start_bar_index < 0 or request.start_bar_index >= len(s.aggregated_bars):
        raise HTTPException(status_code=400, detail="Invalid start_bar_index")
    if request.end_bar_index < 0 or request.end_bar_index >= len(s.aggregated_bars):
        raise HTTPException(status_code=400, detail="Invalid end_bar_index")
    if request.start_bar_index == request.end_bar_index:
        raise HTTPException(status_code=400, detail="start and end must be different")

    start_bar = s.aggregated_bars[request.start_bar_index]
    end_bar = s.aggregated_bars[request.end_bar_index]

    # Get source indices
    start_source_start, start_source_end = s.aggregation_map.get(
        request.start_bar_index, (request.start_bar_index, request.start_bar_index)
    )
    end_source_start, end_source_end = s.aggregation_map.get(
        request.end_bar_index, (request.end_bar_index, request.end_bar_index)
    )

    # Infer direction from price movement
    # Bull reference = the swing before an upward move (swing went down)
    # Bear reference = the swing before a downward move (swing went up)
    if start_bar.high > end_bar.high:
        # Price went down: bull reference (downswing)
        direction = "bull"
        start_price = Decimal(str(start_bar.high))
        end_price = Decimal(str(end_bar.low))
    else:
        # Price went up: bear reference (upswing)
        direction = "bear"
        start_price = Decimal(str(start_bar.low))
        end_price = Decimal(str(end_bar.high))

    # Create annotation
    annotation = SwingAnnotation.create(
        scale=s.scale,
        direction=direction,
        start_bar_index=request.start_bar_index,
        end_bar_index=request.end_bar_index,
        start_source_index=start_source_start,
        end_source_index=end_source_end,
        start_price=start_price,
        end_price=end_price,
        window_id=s.session.session_id
    )

    # Save annotation
    s.storage.save_annotation(s.session.session_id, annotation)

    # Reload session to get updated annotation list
    s.session = s.storage.get_session(s.session.session_id)

    # Sync cascade controller's session if in cascade mode
    if s.cascade_controller:
        s.cascade_controller._session = s.session

    # Start background precomputation early (after first annotation)
    start_precomputation_if_ready(s)

    return _annotation_to_response(annotation)


@app.get("/api/annotations", response_model=List[AnnotationResponse])
async def list_annotations():
    """List all annotations for current scale."""
    s = get_state()

    annotations = s.storage.get_annotations(s.session.session_id, scale=s.scale)

    return [_annotation_to_response(ann) for ann in annotations]


@app.delete("/api/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """Delete an annotation by ID."""
    s = get_state()

    success = s.storage.delete_annotation(s.session.session_id, annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Reload session
    s.session = s.storage.get_session(s.session.session_id)

    # Sync cascade controller's session if in cascade mode
    if s.cascade_controller:
        s.cascade_controller._session = s.session

    return {"status": "ok", "annotation_id": annotation_id}


@app.get("/api/session", response_model=SessionResponse)
async def get_session():
    """Get current session state."""
    s = get_state()

    # If cascade mode, use cascade controller's current scale
    current_scale = s.scale
    if s.cascade_controller:
        current_scale = s.cascade_controller.get_current_scale()

    return SessionResponse(
        session_id=s.session.session_id,
        data_file=s.session.data_file,
        resolution=s.session.resolution,
        window_size=s.session.window_size,
        scale=current_scale,
        created_at=s.session.created_at.isoformat(),
        annotation_count=len(s.session.annotations),
        completed_scales=s.session.completed_scales,
        status=s.session.status
    )


@app.patch("/api/session/status")
async def update_session_status(request: SessionStatusUpdate):
    """
    Update the session status (keep/discard).

    Used to mark sessions as high-quality ("keep") or practice runs ("discard")
    at the end of annotation or review.
    """
    s = get_state()

    if request.status not in ("keep", "discard"):
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Must be 'keep' or 'discard'."
        )

    s.session.status = request.status
    s.storage.update_session(s.session)

    return {"status": "ok", "new_status": request.status}


@app.post("/api/session/finalize", response_model=SessionFinalizeResponse)
async def finalize_session(request: SessionFinalizeRequest):
    """
    Finalize session: keep (rename to clean timestamp) or discard (delete).

    - keep: Renames files to 'yyyy-mmm-dd-HHmm[-label].json'
    - discard: Deletes session and review files entirely

    Args:
        status: "keep" (save with clean name) or "discard" (delete files)
        label: Optional user-provided label (only used for "keep")

    Returns:
        New filenames for "keep", or confirmation message for "discard"
    """
    s = get_state()

    if request.status not in ("keep", "discard"):
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Must be 'keep' or 'discard'."
        )

    # Update session status first (in memory, will be persisted or deleted)
    s.session.status = request.status

    try:
        if request.status == "discard":
            # Delete review file first (if exists)
            if s.review_storage:
                s.review_storage.finalize_review(
                    session_id=s.session.session_id,
                    status="discard"
                )

            # Delete session file
            s.storage.finalize_session(
                session_id=s.session.session_id,
                status="discard"
            )

            return SessionFinalizeResponse(
                success=True,
                session_filename=None,
                review_filename=None,
                message="Session discarded (files deleted)"
            )

        # status == "keep": save session status then rename
        s.storage.update_session(s.session)

        # Update review session with metadata if it exists
        if s.review_controller:
            review = s.review_controller.get_or_create_review()
            review.difficulty = request.difficulty
            review.regime = request.regime
            review.session_comments = request.comments
            s.review_storage.save_review(review)

        # Finalize session file (rename to clean timestamp name)
        session_filename, new_path_id = s.storage.finalize_session(
            session_id=s.session.session_id,
            status="keep",
            label=request.label
        )

        # Finalize review file if it exists
        review_filename = None
        if s.review_storage:
            review_filename = s.review_storage.finalize_review(
                session_id=s.session.session_id,
                status="keep",
                new_path_id=new_path_id
            )

        return SessionFinalizeResponse(
            success=True,
            session_filename=session_filename,
            review_filename=review_filename,
            message=f"Session saved as {session_filename}"
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/cascade/state", response_model=CascadeStateResponse)
async def get_cascade_state():
    """Get current cascade workflow state."""
    s = get_state()

    if not s.cascade_controller:
        raise HTTPException(
            status_code=400,
            detail="Cascade mode not enabled. Start server with --cascade flag."
        )

    cascade_state = s.cascade_controller.get_cascade_state()

    # Convert scale_info to Pydantic models
    scale_info_models = {
        scale: ScaleInfo(**info)
        for scale, info in cascade_state["scale_info"].items()
    }

    return CascadeStateResponse(
        current_scale=cascade_state["current_scale"],
        current_scale_index=cascade_state["current_scale_index"],
        reference_scale=cascade_state["reference_scale"],
        completed_scales=cascade_state["completed_scales"],
        skipped_scales=cascade_state.get("skipped_scales", []),
        scales_remaining=cascade_state["scales_remaining"],
        is_complete=cascade_state["is_complete"],
        scale_info=scale_info_models,
    )


@app.post("/api/cascade/advance", response_model=CascadeTransitionResponse)
async def advance_cascade():
    """Mark current scale complete and advance to next scale."""
    s = get_state()

    if not s.cascade_controller:
        raise HTTPException(
            status_code=400,
            detail="Cascade mode not enabled. Start server with --cascade flag."
        )

    previous_scale = s.cascade_controller.get_current_scale()
    success = s.cascade_controller.advance_to_next_scale()
    current_scale = s.cascade_controller.get_current_scale()

    # Update state's scale to match cascade
    s.scale = current_scale

    # Persist session state
    s.storage.update_session(s.session)

    # Update aggregated bars for new scale
    if s.cascade_controller:
        s.aggregated_bars = s.cascade_controller.get_bars_for_scale(current_scale)
        s.aggregation_map = s.cascade_controller.get_aggregation_map(current_scale)

    return CascadeTransitionResponse(
        success=success,
        previous_scale=previous_scale,
        current_scale=current_scale,
        is_complete=s.cascade_controller.is_session_complete(),
    )


@app.post("/api/cascade/skip", response_model=CascadeTransitionResponse)
async def skip_remaining_scales():
    """Skip remaining scales and proceed to review.

    Marks the current scale as complete and all remaining scales as skipped.
    Use this for "Skip to FP Review" workflow when user wants to skip M/S
    annotation after completing XL/L.
    """
    s = get_state()

    if not s.cascade_controller:
        raise HTTPException(
            status_code=400,
            detail="Cascade mode not enabled. Start server with --cascade flag."
        )

    previous_scale = s.cascade_controller.get_current_scale()
    skipped_scales = s.cascade_controller.skip_remaining_scales()
    current_scale = s.cascade_controller.get_current_scale()

    # Update state's scale to match cascade
    s.scale = current_scale

    # Persist session state
    s.storage.update_session(s.session)

    # Update aggregated bars for final scale
    if s.cascade_controller:
        s.aggregated_bars = s.cascade_controller.get_bars_for_scale(current_scale)
        s.aggregation_map = s.cascade_controller.get_aggregation_map(current_scale)

    return CascadeTransitionResponse(
        success=True,
        previous_scale=previous_scale,
        current_scale=current_scale,
        skipped_scales=skipped_scales,
        is_complete=s.cascade_controller.is_session_complete(),
    )


@app.get("/api/cascade/reference", response_model=List[AnnotationResponse])
async def get_reference_annotations():
    """Get annotations from the reference scale (completed larger scale)."""
    s = get_state()

    if not s.cascade_controller:
        raise HTTPException(
            status_code=400,
            detail="Cascade mode not enabled."
        )

    annotations = s.cascade_controller.get_reference_annotations()

    return [_annotation_to_response(ann) for ann in annotations]


@app.post("/api/compare", response_model=ComparisonRunResponse)
async def run_comparison():
    """
    Run comparison between user annotations and system detection.

    Compares all annotations in the current session against system-detected
    swings on the source bars. Results are stored for later retrieval.
    """
    s = get_state()

    analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

    # Run comparison on all scales that have annotations
    results = analyzer.compare_session(s.session, s.source_bars)

    # Generate report
    report = analyzer.generate_report(results)

    # Store report in state
    s.comparison_report = report

    # Create summary response
    summary = ComparisonSummary(
        total_user_annotations=report['summary']['total_user_annotations'],
        total_system_detections=report['summary']['total_system_detections'],
        total_matches=report['summary']['total_matches'],
        total_false_negatives=report['summary']['total_false_negatives'],
        total_false_positives=report['summary']['total_false_positives'],
        overall_match_rate=report['summary']['overall_match_rate'],
    )

    # Format message
    match_pct = int(summary.overall_match_rate * 100)
    message = (
        f"Match rate: {match_pct}% | "
        f"{summary.total_false_negatives} false negatives | "
        f"{summary.total_false_positives} false positives"
    )

    return ComparisonRunResponse(
        success=True,
        summary=summary,
        message=message,
    )


@app.get("/api/compare/report", response_model=ComparisonReportResponse)
async def get_comparison_report():
    """
    Get the latest comparison report.

    Returns the full report from the most recent comparison run.
    Run POST /api/compare first to generate a report.
    """
    s = get_state()

    if s.comparison_report is None:
        raise HTTPException(
            status_code=404,
            detail="No comparison report available. Run POST /api/compare first."
        )

    report = s.comparison_report

    # Convert to response model
    summary = ComparisonSummary(**report['summary'])

    by_scale = {
        scale: ComparisonScaleResult(**data)
        for scale, data in report['by_scale'].items()
    }

    false_negatives = [
        FalseNegativeItem(**item)
        for item in report['false_negatives']
    ]

    false_positives = [
        FalsePositiveItem(**item)
        for item in report['false_positives']
    ]

    return ComparisonReportResponse(
        summary=summary,
        by_scale=by_scale,
        false_negatives=false_negatives,
        false_positives=false_positives,
    )


@app.get("/api/compare/export")
async def export_comparison(format: str = Query("json", description="Export format: json or csv")):
    """
    Export comparison report as JSON or CSV.

    Args:
        format: Export format - "json" (default) or "csv"

    Returns:
        Report data in requested format
    """
    s = get_state()

    if s.comparison_report is None:
        raise HTTPException(
            status_code=404,
            detail="No comparison report available. Run POST /api/compare first."
        )

    report = s.comparison_report

    if format == "json":
        return report

    elif format == "csv":
        # Build CSV content for false negatives and false positives
        lines = []

        # Header
        lines.append("type,scale,start,end,direction,annotation_id,size,rank")

        # False negatives
        for item in report['false_negatives']:
            lines.append(
                f"false_negative,{item['scale']},{item['start']},{item['end']},"
                f"{item['direction']},{item['annotation_id']},,"
            )

        # False positives
        for item in report['false_positives']:
            lines.append(
                f"false_positive,{item['scale']},{item['start']},{item['end']},"
                f"{item['direction']},,{item['size']},{item['rank']}"
            )

        csv_content = "\n".join(lines)

        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=comparison_report.csv"}
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use 'json' or 'csv'."
        )


# ============================================================================
# Review Mode Endpoints
# ============================================================================

def _ensure_comparison_run(s: AppState) -> Dict[str, ComparisonResult]:
    """Ensure comparison has been run and cached."""
    if s.comparison_results is None:
        # Wait for precomputation if in progress
        if s.precompute_in_progress and s.precompute_thread:
            logger.info("Waiting for background precomputation to complete...")
            s.precompute_thread.join(timeout=30)  # Wait up to 30 seconds

        # If still not available, run synchronously
        if s.comparison_results is None:
            analyzer = ComparisonAnalyzer(tolerance_pct=0.1)
            s.comparison_results = analyzer.compare_session(s.session, s.source_bars)
            # Also update the comparison report
            s.comparison_report = analyzer.generate_report(s.comparison_results)
    return s.comparison_results


def _precompute_comparison_background(s: AppState) -> None:
    """
    Run comparison analysis in background thread.

    This allows the UI to remain responsive while the comparison is computed.
    Results are stored in AppState.comparison_results for later use.
    """
    try:
        logger.info("Starting background precomputation of system swings...")
        s.precompute_in_progress = True

        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)
        results = analyzer.compare_session(s.session, s.source_bars)
        report = analyzer.generate_report(results)

        # Store results
        s.comparison_results = results
        s.comparison_report = report

        logger.info("Background precomputation complete")
    except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
        logger.error(f"Background precomputation failed: {e}")
    finally:
        s.precompute_in_progress = False


def start_precomputation_if_ready(s: AppState) -> None:
    """
    Start background precomputation if conditions are met.

    Triggers early (after first annotation) to maximize time for computation
    to complete before user enters review mode.
    """
    if s.precompute_in_progress:
        return
    if s.comparison_results is not None:
        return
    if len(s.session.annotations) == 0:
        return  # Wait for at least one annotation

    # Start background thread
    s.precompute_thread = threading.Thread(
        target=_precompute_comparison_background,
        args=(s,),
        daemon=True
    )
    s.precompute_thread.start()
    logger.info("Started background precomputation thread (triggered by annotation)")


def _get_review_controller(s: AppState) -> ReviewController:
    """Get or create the review controller."""
    if s.review_controller is None:
        raise HTTPException(
            status_code=404,
            detail="No review session. Start review with POST /api/review/start first."
        )
    return s.review_controller


@app.post("/api/review/start", response_model=ReviewStateResponse)
async def start_review():
    """
    Initialize Review Mode for current session.

    - Runs comparison if not already done
    - Creates ReviewSession
    - Samples false positives
    - Returns initial state
    """
    s = get_state()

    if s.review_storage is None:
        raise HTTPException(status_code=500, detail="Review storage not initialized")

    # Run comparison if needed
    comparison_results = _ensure_comparison_run(s)

    # Create or get review controller
    if s.review_controller is None:
        s.review_controller = ReviewController(
            session_id=s.session.session_id,
            annotation_storage=s.storage,
            review_storage=s.review_storage,
            comparison_results=comparison_results
        )

    # Get initial state
    review = s.review_controller.get_or_create_review()
    completed, total = s.review_controller.get_phase_progress()

    return ReviewStateResponse(
        review_id=review.review_id,
        session_id=review.session_id,
        phase=review.phase,
        progress={"completed": completed, "total": total},
        is_complete=s.review_controller.is_complete()
    )


@app.get("/api/review/state", response_model=ReviewStateResponse)
async def get_review_state():
    """Get current review session state and progress."""
    s = get_state()
    controller = _get_review_controller(s)

    review = controller.get_or_create_review()
    completed, total = controller.get_phase_progress()

    return ReviewStateResponse(
        review_id=review.review_id,
        session_id=review.session_id,
        phase=review.phase,
        progress={"completed": completed, "total": total},
        is_complete=controller.is_complete()
    )


@app.get("/api/review/matches", response_model=List[MatchItem])
async def get_matches():
    """
    Get matched swings for Phase 1 review.

    Returns all swings where user annotation matched system detection.
    """
    s = get_state()
    controller = _get_review_controller(s)

    matches = controller.get_matches()

    return [
        MatchItem(
            annotation_id=m["annotation"]["annotation_id"],
            scale=m["scale"],
            direction=m["annotation"]["direction"],
            start_index=m["annotation"]["start_source_index"],
            end_index=m["annotation"]["end_source_index"],
            start_price=m["annotation"]["start_price"],
            end_price=m["annotation"]["end_price"],
            system_start=m["system_swing"]["start_index"],
            system_end=m["system_swing"]["end_index"],
            feedback=m["feedback"]
        )
        for m in matches
    ]


@app.get("/api/review/fp-sample", response_model=List[FPSampleItem])
async def get_fp_sample():
    """
    Get sampled false positives for Phase 2 review.

    Returns 10-20 system detections that user didn't mark,
    stratified by scale.
    """
    s = get_state()
    controller = _get_review_controller(s)

    fps = controller.get_fp_sample()

    return [
        FPSampleItem(
            fp_index=fp["sample_index"],
            scale=fp["scale"],
            direction=fp["system_swing"]["direction"],
            start_index=fp["system_swing"]["start_index"],
            end_index=fp["system_swing"]["end_index"],
            high_price=fp["system_swing"]["high_price"],
            low_price=fp["system_swing"]["low_price"],
            size=fp["system_swing"]["size"],
            rank=fp["system_swing"]["rank"],
            feedback=fp["feedback"]
        )
        for fp in fps
    ]


@app.get("/api/review/fn-list", response_model=List[FNItem])
async def get_fn_list():
    """
    Get all false negatives for Phase 3 review.

    Returns all swings user marked that system missed.
    """
    s = get_state()
    controller = _get_review_controller(s)

    fns = controller.get_false_negatives()

    return [
        FNItem(
            annotation_id=fn["annotation"]["annotation_id"],
            scale=fn["scale"],
            direction=fn["annotation"]["direction"],
            start_index=fn["annotation"]["start_source_index"],
            end_index=fn["annotation"]["end_source_index"],
            start_price=fn["annotation"]["start_price"],
            end_price=fn["annotation"]["end_price"],
            feedback=fn["feedback"]
        )
        for fn in fns
    ]


@app.post("/api/review/feedback")
async def submit_feedback(request: FeedbackSubmit):
    """
    Submit feedback on a swing.

    - For matches: verdict = "correct" or "incorrect"
    - For FPs: verdict = "noise" or "valid_missed", optional category and better_reference
    - For FNs: verdict = "explained", comment REQUIRED

    Returns {"status": "ok", "feedback_id": str}
    """
    s = get_state()
    controller = _get_review_controller(s)

    # Convert better_reference from API model to domain model
    better_ref = None
    if request.better_reference:
        from .models import BetterReference
        better_ref = BetterReference(
            high_bar_index=request.better_reference.high_bar_index,
            low_bar_index=request.better_reference.low_bar_index,
            high_price=Decimal(request.better_reference.high_price),
            low_price=Decimal(request.better_reference.low_price)
        )

    try:
        feedback = controller.submit_feedback(
            swing_type=request.swing_type,
            swing_reference=request.swing_reference,
            verdict=request.verdict,
            comment=request.comment,
            category=request.category,
            better_reference=better_ref
        )
        return {"status": "ok", "feedback_id": feedback.feedback_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/review/advance", response_model=ReviewStateResponse)
async def advance_review_phase():
    """
    Mark current phase complete and advance to next.

    Validates:
    - Phase 3 (FN): All FNs must have feedback with comment

    Returns updated state.
    """
    s = get_state()
    controller = _get_review_controller(s)

    # Check if we can advance (FN phase requires all feedback)
    if controller.get_current_phase() == "fn_feedback":
        fns = controller.get_false_negatives()
        for fn in fns:
            if fn["feedback"] is None:
                raise HTTPException(
                    status_code=400,
                    detail="All false negatives must have feedback before advancing"
                )

    success = controller.advance_phase()

    if not success and controller.is_complete():
        # Already complete is not an error
        pass

    review = controller.get_or_create_review()
    completed, total = controller.get_phase_progress()

    return ReviewStateResponse(
        review_id=review.review_id,
        session_id=review.session_id,
        phase=review.phase,
        progress={"completed": completed, "total": total},
        is_complete=controller.is_complete()
    )


@app.get("/api/review/summary", response_model=ReviewSummaryResponse)
async def get_review_summary():
    """Get final review summary with all statistics."""
    s = get_state()
    controller = _get_review_controller(s)

    summary = controller.get_summary()

    return ReviewSummaryResponse(
        session_id=summary["session_id"],
        review_id=summary["review_id"],
        phase=summary["phase"],
        matches=summary["matches"],
        false_positives=summary["false_positives"],
        false_negatives=summary["false_negatives"],
        started_at=summary["started_at"],
        completed_at=summary["completed_at"]
    )


@app.get("/api/review/export")
async def export_review(format: str = Query("json")):
    """
    Export review feedback as JSON or CSV.

    JSON structure:
    {
        "session_id": str,
        "review_id": str,
        "data_file": str,
        "summary": {...},
        "matches": [...],
        "false_positives": [...],
        "false_negatives": [...]
    }
    """
    s = get_state()
    controller = _get_review_controller(s)

    summary = controller.get_summary()
    matches = controller.get_matches()
    fps = controller.get_fp_sample()
    fns = controller.get_false_negatives()

    if format == "json":
        return {
            "session_id": s.session.session_id,
            "review_id": summary["review_id"],
            "data_file": s.session.data_file,
            "summary": summary,
            "matches": matches,
            "false_positives": fps,
            "false_negatives": fns
        }

    elif format == "csv":
        # Build CSV content
        lines = []
        lines.append("type,annotation_id,scale,direction,start,end,verdict,category,comment")

        # Matches
        for m in matches:
            fb = m.get("feedback") or {}
            comment = escape_csv_field(fb.get("comment") or "")
            lines.append(
                f"match,{m['annotation']['annotation_id']},{m['scale']},"
                f"{m['annotation']['direction']},{m['annotation']['start_source_index']},"
                f"{m['annotation']['end_source_index']},{fb.get('verdict', '')},"
                f"{fb.get('category', '')},{comment}"
            )

        # False positives
        for fp in fps:
            fb = fp.get("feedback") or {}
            comment = escape_csv_field(fb.get("comment") or "")
            lines.append(
                f"false_positive,fp_{fp['sample_index']},{fp['scale']},"
                f"{fp['system_swing']['direction']},{fp['system_swing']['start_index']},"
                f"{fp['system_swing']['end_index']},{fb.get('verdict', '')},"
                f"{fb.get('category', '')},{comment}"
            )

        # False negatives
        for fn in fns:
            fb = fn.get("feedback") or {}
            comment = escape_csv_field(fb.get("comment") or "")
            lines.append(
                f"false_negative,{fn['annotation']['annotation_id']},{fn['scale']},"
                f"{fn['annotation']['direction']},{fn['annotation']['start_source_index']},"
                f"{fn['annotation']['end_source_index']},{fb.get('verdict', '')},"
                f"{fb.get('category', '')},{comment}"
            )

        csv_content = "\n".join(lines)

        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=review_export.csv"}
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use 'json' or 'csv'."
        )


# ============================================================================
# Session Flow Endpoints
# ============================================================================

@app.post("/api/session/next", response_model=NextSessionResponse)
async def start_next_session():
    """
    Create new annotation session with random window offset.

    Preserves current data file and settings, randomizes offset.
    Reinitializes the application state with the new session.
    Returns new session_id for redirect.
    """
    s = get_state()

    # Calculate random offset
    window_size = s.session.window_size
    max_offset = max(0, s.total_source_bars - window_size)
    new_offset = random.randint(0, max_offset) if max_offset > 0 else 0

    # Reinitialize app with new random offset (reuse cached DataFrame to avoid disk I/O)
    init_app(
        data_file=s.data_file,
        storage_dir=s.storage_dir,
        resolution_minutes=s.resolution_minutes,
        window_size=window_size,
        scale=s.scale,
        target_bars=s.target_bars,
        cascade=s.cascade_enabled,
        window_offset=new_offset,
        cached_df=s.cached_dataframe
    )

    # Get the new session from updated state
    new_state = get_state()

    return NextSessionResponse(
        session_id=new_state.session.session_id,
        offset=new_offset,
        redirect_url="/"
    )


# ============================================================================
# Discretization Endpoints
# ============================================================================


def _run_discretization(s: AppState) -> DiscretizationLog:
    """Run discretization on current window with detected swings.

    Each swing is assigned to exactly one scale - the LARGEST scale it qualifies for
    based on size thresholds. This prevents the same swing from appearing at multiple scales.
    """
    # Convert source bars to DataFrame for discretizer
    bar_data = []
    for bar in s.source_bars:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Detect swings once (not per scale)
    result = detect_swings(df, lookback=5, filter_redundant=True)

    # Scale thresholds - swing assigned to LARGEST scale where size >= threshold
    # Note: Scales ordered from largest to smallest for assignment priority
    scale_thresholds = [
        ("XL", 100),
        ("L", 40),
        ("M", 15),
        ("S", 0),
    ]

    def assign_scale(size: float) -> str:
        """Assign swing to the largest scale it qualifies for."""
        for scale, threshold in scale_thresholds:
            if size >= threshold:
                return scale
        return "S"  # Default to smallest scale

    # Initialize swings_by_scale with empty lists
    swings_by_scale: Dict[str, List[ReferenceSwing]] = {
        "XL": [],
        "L": [],
        "M": [],
        "S": [],
    }

    # Process bull references - assign each to exactly one scale
    for ref in result.get('bull_references', []):
        swing = ReferenceSwing(
            high_price=ref['high_price'],
            high_bar_index=ref['high_bar_index'],
            low_price=ref['low_price'],
            low_bar_index=ref['low_bar_index'],
            size=ref['size'],
            direction='bull',
            structurally_separated=ref.get('structurally_separated', False),
            containing_swing_id=ref.get('containing_swing_id'),
            separation_is_anchor=ref.get('separation_is_anchor', False),
            separation_distance_fib=ref.get('separation_distance_fib'),
            separation_minimum_fib=ref.get('separation_minimum_fib'),
            separation_from_swing_id=ref.get('separation_from_swing_id'),
        )
        scale = assign_scale(ref['size'])
        swings_by_scale[scale].append(swing)

    # Process bear references - assign each to exactly one scale
    for ref in result.get('bear_references', []):
        swing = ReferenceSwing(
            high_price=ref['high_price'],
            high_bar_index=ref['high_bar_index'],
            low_price=ref['low_price'],
            low_bar_index=ref['low_bar_index'],
            size=ref['size'],
            direction='bear',
            structurally_separated=ref.get('structurally_separated', False),
            containing_swing_id=ref.get('containing_swing_id'),
            separation_is_anchor=ref.get('separation_is_anchor', False),
            separation_distance_fib=ref.get('separation_distance_fib'),
            separation_minimum_fib=ref.get('separation_minimum_fib'),
            separation_from_swing_id=ref.get('separation_from_swing_id'),
        )
        scale = assign_scale(ref['size'])
        swings_by_scale[scale].append(swing)

    # Remove empty scales from the dict
    swings_by_scale = {k: v for k, v in swings_by_scale.items() if v}

    # Run discretization
    config = DiscretizerConfig()
    discretizer = Discretizer(config)
    log = discretizer.discretize(
        ohlc=df,
        swings=swings_by_scale,
        instrument="unknown",
        source_resolution=f"{s.resolution_minutes}m",
    )

    return log


@app.get("/api/discretization/state", response_model=DiscretizationStateResponse)
async def get_discretization_state():
    """Get current discretization state."""
    s = get_state()

    if s.discretization_log is None:
        return DiscretizationStateResponse(
            has_log=False,
            event_count=0,
            swing_count=0,
            scales=[],
            config=None,
        )

    log = s.discretization_log
    scales = list(set(swing.scale for swing in log.swings))

    return DiscretizationStateResponse(
        has_log=True,
        event_count=len(log.events),
        swing_count=len(log.swings),
        scales=scales,
        config=log.meta.config.to_dict() if log.meta else None,
    )


@app.post("/api/discretization/run", response_model=DiscretizationRunResponse)
async def run_discretization():
    """
    Run discretization on current window.

    Detects swings on the source bars and runs the discretizer to produce
    an event log with level crossings, completions, invalidations, etc.
    """
    s = get_state()

    try:
        log = _run_discretization(s)
        s.discretization_log = log

        scales = list(set(swing.scale for swing in log.swings))

        return DiscretizationRunResponse(
            success=True,
            event_count=len(log.events),
            swing_count=len(log.swings),
            scales_processed=scales,
            message=f"Discretization complete: {len(log.events)} events, {len(log.swings)} swings",
        )
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        logger.error(f"Discretization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Discretization failed: {e}")


@app.get("/api/discretization/swings", response_model=List[DiscretizationSwingResponse])
async def get_discretization_swings(
    scale: Optional[str] = Query(None, description="Filter by scale (XL, L, M, S)"),
    status: Optional[str] = Query(None, description="Filter by status (active, completed, invalidated)"),
):
    """Get all swings from the discretization log."""
    s = get_state()

    if s.discretization_log is None:
        raise HTTPException(
            status_code=404,
            detail="No discretization log. Run POST /api/discretization/run first."
        )

    swings = s.discretization_log.swings

    # Apply filters
    if scale:
        swings = [sw for sw in swings if sw.scale == scale]
    if status:
        swings = [sw for sw in swings if sw.status == status]

    return [
        DiscretizationSwingResponse(
            swing_id=sw.swing_id,
            scale=sw.scale,
            direction=sw.direction,
            anchor0=sw.anchor0,
            anchor1=sw.anchor1,
            anchor0_bar=sw.anchor0_bar,
            anchor1_bar=sw.anchor1_bar,
            formed_at_bar=sw.formed_at_bar,
            status=sw.status,
            terminated_at_bar=sw.terminated_at_bar,
            termination_reason=sw.termination_reason,
        )
        for sw in swings
    ]


@app.get("/api/discretization/events", response_model=List[DiscretizationEventResponse])
async def get_discretization_events(
    scale: Optional[str] = Query(None, description="Filter by swing scale"),
    event_type: Optional[str] = Query(None, description="Filter by event type (LEVEL_CROSS, COMPLETION, etc.)"),
    shock_threshold: Optional[float] = Query(None, description="Minimum range_multiple for shock"),
    levels_jumped_min: Optional[int] = Query(None, description="Minimum levels_jumped"),
    is_gap: Optional[bool] = Query(None, description="Filter for gap events only"),
    bar_start: Optional[int] = Query(None, description="Filter events from bar index"),
    bar_end: Optional[int] = Query(None, description="Filter events up to bar index"),
):
    """
    Get discretization events with optional filters.

    Filters can be combined. Shock-related filters (shock_threshold, levels_jumped_min, is_gap)
    filter based on the shock annotation attached to events.
    """
    s = get_state()

    if s.discretization_log is None:
        raise HTTPException(
            status_code=404,
            detail="No discretization log. Run POST /api/discretization/run first."
        )

    log = s.discretization_log
    events = log.events

    # Build swing lookup for scale filtering
    swing_scales = {sw.swing_id: sw.scale for sw in log.swings}

    # Apply filters
    filtered = []
    for event in events:
        # Scale filter
        if scale:
            swing_scale = swing_scales.get(event.swing_id)
            if swing_scale != scale:
                continue

        # Event type filter
        if event_type:
            if event.event_type.value != event_type:
                continue

        # Bar range filter
        if bar_start is not None and event.bar < bar_start:
            continue
        if bar_end is not None and event.bar > bar_end:
            continue

        # Shock-based filters
        if shock_threshold is not None:
            if event.shock is None or event.shock.range_multiple < shock_threshold:
                continue

        if levels_jumped_min is not None:
            if event.shock is None or event.shock.levels_jumped < levels_jumped_min:
                continue

        if is_gap is not None:
            if event.shock is None or event.shock.is_gap != is_gap:
                continue

        filtered.append(event)

    return [
        DiscretizationEventResponse(
            bar=ev.bar,
            timestamp=ev.timestamp,
            swing_id=ev.swing_id,
            event_type=ev.event_type.value,
            data=ev.data,
            effort=ev.effort.to_dict() if ev.effort else None,
            shock=ev.shock.to_dict() if ev.shock else None,
            parent_context=ev.parent_context.to_dict() if ev.parent_context else None,
        )
        for ev in filtered
    ]


@app.get("/api/discretization/levels")
async def get_discretization_levels(swing_id: str = Query(..., description="Swing ID to get levels for")):
    """
    Get Fibonacci levels for a specific swing.

    Returns the price levels from the swing's reference frame for overlay display.
    """
    s = get_state()

    if s.discretization_log is None:
        raise HTTPException(
            status_code=404,
            detail="No discretization log. Run POST /api/discretization/run first."
        )

    # Find the swing
    swing = None
    for sw in s.discretization_log.swings:
        if sw.swing_id == swing_id:
            swing = sw
            break

    if swing is None:
        raise HTTPException(status_code=404, detail=f"Swing {swing_id} not found")

    # Calculate levels from anchor points
    anchor0 = swing.anchor0  # Defended pivot
    anchor1 = swing.anchor1  # Origin extremum
    swing_range = anchor1 - anchor0

    # Standard discretization levels
    from ..swing_analysis.constants import DISCRETIZATION_LEVELS

    levels = []
    for ratio in DISCRETIZATION_LEVELS:
        price = anchor0 + swing_range * ratio
        levels.append({
            "ratio": ratio,
            "price": price,
            "label": str(ratio),
        })

    return {
        "swing_id": swing_id,
        "scale": swing.scale,
        "direction": swing.direction,
        "anchor0": anchor0,
        "anchor1": anchor1,
        "levels": levels,
    }


# ============================================================================
# Swing Detection Endpoints (for Replay View)
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


# ============================================================================
# Calibration API Models
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


class SwingsWindowedResponse(BaseModel):
    """Response from windowed swing detection."""
    bar_end: int
    swing_count: int
    swings: List[DetectedSwingResponse]


@app.get("/api/swings/windowed", response_model=SwingsWindowedResponse)
async def get_windowed_swings(
    bar_end: int = Query(..., description="Source bar index to detect swings up to"),
    top_n: int = Query(2, description="Number of top swings to return"),
):
    """
    Run swing detection on bars[0:bar_end] and return top N swings.

    Used by Replay View to show detected swings as playback progresses.
    Returns swings with Fib levels for chart overlay.
    """
    s = get_state()

    # Validate bar_end
    if bar_end < 10:
        # Need minimum bars for detection
        return SwingsWindowedResponse(bar_end=bar_end, swing_count=0, swings=[])
    if bar_end > len(s.source_bars):
        bar_end = len(s.source_bars)

    # Slice source bars to current position
    bars_subset = s.source_bars[:bar_end]

    # Convert to DataFrame for detect_swings
    bar_data = []
    for bar in bars_subset:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Run swing detection
    result = detect_swings(
        df,
        lookback=5,
        filter_redundant=True,
        current_bar_index=bar_end - 1,  # Pass current bar for proper detection
    )

    # Combine bull and bear references, sort by size, take top N
    all_swings = []

    for ref in result.get('bull_references', []):
        # Calculate Fib levels for bull (low is pivot, high is origin)
        swing_range = ref['high_price'] - ref['low_price']
        fib_0 = ref['low_price']  # Defended pivot
        fib_0382 = ref['low_price'] + swing_range * 0.382
        fib_1 = ref['high_price']  # Origin
        fib_2 = ref['low_price'] + swing_range * 2.0  # Completion target

        all_swings.append({
            'direction': 'bull',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': ref.get('rank', 0),
            'fib_0': fib_0,
            'fib_0382': fib_0382,
            'fib_1': fib_1,
            'fib_2': fib_2,
        })

    for ref in result.get('bear_references', []):
        # Calculate Fib levels for bear (high is pivot, low is origin)
        swing_range = ref['high_price'] - ref['low_price']
        fib_0 = ref['high_price']  # Defended pivot
        fib_0382 = ref['high_price'] - swing_range * 0.382
        fib_1 = ref['low_price']  # Origin
        fib_2 = ref['high_price'] - swing_range * 2.0  # Completion target

        all_swings.append({
            'direction': 'bear',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': ref.get('rank', 0),
            'fib_0': fib_0,
            'fib_0382': fib_0382,
            'fib_1': fib_1,
            'fib_2': fib_2,
        })

    # Sort by size descending, take top N
    all_swings.sort(key=lambda x: x['size'], reverse=True)
    top_swings = all_swings[:top_n]

    # Convert to response models with IDs
    swing_responses = []
    for i, swing in enumerate(top_swings):
        swing_responses.append(DetectedSwingResponse(
            id=f"swing-{bar_end}-{i}",
            direction=swing['direction'],
            high_price=swing['high_price'],
            high_bar_index=swing['high_bar_index'],
            low_price=swing['low_price'],
            low_bar_index=swing['low_bar_index'],
            size=swing['size'],
            rank=i + 1,
            fib_0=swing['fib_0'],
            fib_0382=swing['fib_0382'],
            fib_1=swing['fib_1'],
            fib_2=swing['fib_2'],
        ))

    return SwingsWindowedResponse(
        bar_end=bar_end,
        swing_count=len(swing_responses),
        swings=swing_responses,
    )


# ============================================================================
# Calibration Endpoints (for Replay View v2)
# ============================================================================


def _is_swing_active(
    swing: dict,
    current_price: float,
    direction: str
) -> bool:
    """
    Determine if a swing is "active" at the current price.

    A swing is active if:
    1. Not yet invalidated (price hasn't violated the defended pivot)
    2. Not yet completed (price hasn't reached 2.0 extension)
    3. Current price is within the 0.382-2.0 zone

    Args:
        swing: Swing dict with high_price, low_price, size, fib levels
        current_price: Current market price
        direction: "bull" or "bear"

    Returns:
        True if the swing is active
    """
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    if direction == 'bull':
        # Bull swing: defended pivot is low, origin is high
        # Price moving up from low
        fib_0 = low  # Defended pivot
        fib_0382 = low + swing_range * 0.382
        fib_2 = low + swing_range * 2.0

        # Invalidated if price below defended pivot (with tolerance)
        if current_price < fib_0 * 0.999:
            return False

        # Completed if price reached 2.0 extension
        if current_price > fib_2:
            return False

        # Active if in 0.382-2.0 zone
        return fib_0382 <= current_price <= fib_2
    else:
        # Bear swing: defended pivot is high, origin is low
        # Price moving down from high
        fib_0 = high  # Defended pivot
        fib_0382 = high - swing_range * 0.382
        fib_2 = high - swing_range * 2.0

        # Invalidated if price above defended pivot (with tolerance)
        if current_price > fib_0 * 1.001:
            return False

        # Completed if price reached 2.0 extension
        if current_price < fib_2:
            return False

        # Active if in 0.382-2.0 zone
        return fib_2 <= current_price <= fib_0382


def _swing_to_calibration_response(
    swing: dict,
    swing_id: str,
    scale: str,
    rank: int,
    is_active: bool
) -> CalibrationSwingResponse:
    """Convert a swing dict to CalibrationSwingResponse."""
    direction = swing['direction']
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    # Calculate Fib levels based on direction
    if direction == 'bull':
        fib_0 = low
        fib_0382 = low + swing_range * 0.382
        fib_1 = high
        fib_2 = low + swing_range * 2.0
    else:
        fib_0 = high
        fib_0382 = high - swing_range * 0.382
        fib_1 = low
        fib_2 = high - swing_range * 2.0

    return CalibrationSwingResponse(
        id=swing_id,
        scale=scale,
        direction=direction,
        high_price=high,
        high_bar_index=swing['high_bar_index'],
        low_price=low,
        low_bar_index=swing['low_bar_index'],
        size=swing['size'],
        rank=rank,
        is_active=is_active,
        fib_0=fib_0,
        fib_0382=fib_0382,
        fib_1=fib_1,
        fib_2=fib_2,
    )


@app.get("/api/replay/calibrate", response_model=CalibrationResponse)
async def calibrate_replay(
    bar_count: int = Query(10000, description="Number of bars for calibration window"),
):
    """
    Run calibration for Replay View.

    Loads the first N bars as the calibration window, detects swings at all
    scales, and identifies which swings are "active" at the end of the window.

    A swing is "active" if:
    - Not yet invalidated (swing point not violated)
    - Not yet completed (price hasn't reached 2.0 extension)
    - Current price is within 0.382-2.0 zone

    Args:
        bar_count: Number of bars for calibration window (default: 10000)

    Returns:
        CalibrationResponse with swings by scale and active swing lists
    """
    s = get_state()

    # Determine actual calibration window size
    actual_bar_count = min(bar_count, len(s.source_bars))
    if actual_bar_count < 10:
        raise HTTPException(
            status_code=400,
            detail="Need at least 10 bars for calibration"
        )

    # Get calibration window bars
    calibration_bars = s.source_bars[:actual_bar_count]
    current_price = calibration_bars[-1].close

    # Convert to DataFrame for detect_swings
    bar_data = []
    for bar in calibration_bars:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Scale thresholds for assignment (swing goes to largest scale it qualifies for)
    scale_thresholds = {
        "XL": 100.0,
        "L": 40.0,
        "M": 15.0,
        "S": 0.0,
    }

    def assign_scale(size: float) -> str:
        """Assign swing to the largest scale it qualifies for."""
        if size >= scale_thresholds["XL"]:
            return "XL"
        elif size >= scale_thresholds["L"]:
            return "L"
        elif size >= scale_thresholds["M"]:
            return "M"
        return "S"

    # Run swing detection with current_bar_index at end of calibration window
    result = detect_swings(
        df,
        lookback=5,
        filter_redundant=True,
        current_bar_index=actual_bar_count - 1,
    )

    # Process all swings and assign to scales
    swings_by_scale: Dict[str, List[CalibrationSwingResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
    }
    active_swings_by_scale: Dict[str, List[CalibrationSwingResponse]] = {
        "XL": [], "L": [], "M": [], "S": []
    }

    # Process bull references
    for i, ref in enumerate(result.get('bull_references', [])):
        scale = assign_scale(ref['size'])
        swing_id = f"cal-bull-{i}"
        ref['direction'] = 'bull'
        is_active = _is_swing_active(ref, current_price, 'bull')
        rank = len(swings_by_scale[scale]) + 1

        swing_response = _swing_to_calibration_response(
            ref, swing_id, scale, rank, is_active
        )
        swings_by_scale[scale].append(swing_response)

        if is_active:
            active_swings_by_scale[scale].append(swing_response)

    # Process bear references
    for i, ref in enumerate(result.get('bear_references', [])):
        scale = assign_scale(ref['size'])
        swing_id = f"cal-bear-{i}"
        ref['direction'] = 'bear'
        is_active = _is_swing_active(ref, current_price, 'bear')
        rank = len(swings_by_scale[scale]) + 1

        swing_response = _swing_to_calibration_response(
            ref, swing_id, scale, rank, is_active
        )
        swings_by_scale[scale].append(swing_response)

        if is_active:
            active_swings_by_scale[scale].append(swing_response)

    # Compute stats by scale
    stats_by_scale = {
        scale: CalibrationScaleStats(
            total_swings=len(swings_by_scale[scale]),
            active_swings=len(active_swings_by_scale[scale])
        )
        for scale in ["XL", "L", "M", "S"]
    }

    # Set playback state for backend-controlled data boundary
    s.calibration_bar_count = actual_bar_count
    s.playback_index = actual_bar_count - 1  # Last visible bar index

    return CalibrationResponse(
        calibration_bar_count=actual_bar_count,
        current_price=current_price,
        swings_by_scale=swings_by_scale,
        active_swings_by_scale=active_swings_by_scale,
        scale_thresholds=scale_thresholds,
        stats_by_scale=stats_by_scale,
    )


# ============================================================================
# Replay Advance Endpoint (Forward-Only Playback)
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


# Global cache for replay state (avoids recomputing swings every advance)
_replay_cache: Dict[str, any] = {
    "last_bar_index": -1,
    "swing_state": {},  # swing_id -> swing dict with current status
    "fib_levels": {},  # swing_id -> last crossed fib level
}


def _detect_swings_at_bar(
    source_bars: List[Bar],
    bar_index: int,
    scale_thresholds: Dict[str, float]
) -> Dict[str, List[dict]]:
    """
    Detect swings using data up to bar_index (inclusive).

    Returns swings organized by scale.
    """
    if bar_index < 10:
        return {"XL": [], "L": [], "M": [], "S": []}

    # Convert to DataFrame
    bar_data = []
    for bar in source_bars[:bar_index + 1]:
        bar_data.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
        })

    df = pd.DataFrame(bar_data)
    df.set_index(pd.RangeIndex(start=0, stop=len(df)), inplace=True)

    # Run swing detection
    result = detect_swings(
        df,
        lookback=5,
        filter_redundant=True,
        current_bar_index=bar_index,
    )

    def assign_scale(size: float) -> str:
        """Assign swing to the largest scale it qualifies for."""
        if size >= scale_thresholds["XL"]:
            return "XL"
        elif size >= scale_thresholds["L"]:
            return "L"
        elif size >= scale_thresholds["M"]:
            return "M"
        return "S"

    swings_by_scale: Dict[str, List[dict]] = {
        "XL": [], "L": [], "M": [], "S": []
    }

    # Process bull references
    for i, ref in enumerate(result.get('bull_references', [])):
        scale = assign_scale(ref['size'])
        swing = {
            'id': f"swing-bull-{ref['high_bar_index']}-{ref['low_bar_index']}",
            'direction': 'bull',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': len(swings_by_scale[scale]) + 1,
            'scale': scale,
        }
        swings_by_scale[scale].append(swing)

    # Process bear references
    for i, ref in enumerate(result.get('bear_references', [])):
        scale = assign_scale(ref['size'])
        swing = {
            'id': f"swing-bear-{ref['low_bar_index']}-{ref['high_bar_index']}",
            'direction': 'bear',
            'high_price': ref['high_price'],
            'high_bar_index': ref['high_bar_index'],
            'low_price': ref['low_price'],
            'low_bar_index': ref['low_bar_index'],
            'size': ref['size'],
            'rank': len(swings_by_scale[scale]) + 1,
            'scale': scale,
        }
        swings_by_scale[scale].append(swing)

    return swings_by_scale


def _compute_fib_levels(swing: dict) -> Dict[float, float]:
    """Compute all standard Fib levels for a swing."""
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    if swing['direction'] == 'bull':
        # Bull: defended pivot is low, origin is high
        return {
            0.0: low,
            0.236: low + swing_range * 0.236,
            0.382: low + swing_range * 0.382,
            0.5: low + swing_range * 0.5,
            0.618: low + swing_range * 0.618,
            0.786: low + swing_range * 0.786,
            1.0: high,
            1.236: low + swing_range * 1.236,
            1.382: low + swing_range * 1.382,
            1.5: low + swing_range * 1.5,
            1.618: low + swing_range * 1.618,
            2.0: low + swing_range * 2.0,
        }
    else:
        # Bear: defended pivot is high, origin is low
        return {
            0.0: high,
            0.236: high - swing_range * 0.236,
            0.382: high - swing_range * 0.382,
            0.5: high - swing_range * 0.5,
            0.618: high - swing_range * 0.618,
            0.786: high - swing_range * 0.786,
            1.0: low,
            1.236: high - swing_range * 1.236,
            1.382: high - swing_range * 1.382,
            1.5: high - swing_range * 1.5,
            1.618: high - swing_range * 1.618,
            2.0: high - swing_range * 2.0,
        }


def _get_current_fib_level(swing: dict, current_price: float) -> float:
    """Get the current Fib level that price is at."""
    fib_levels = _compute_fib_levels(swing)
    sorted_levels = sorted(fib_levels.keys())

    if swing['direction'] == 'bull':
        # Price moving up: find highest level below current price
        current_level = 0.0
        for level in sorted_levels:
            if current_price >= fib_levels[level]:
                current_level = level
            else:
                break
    else:
        # Price moving down: find highest level above current price
        current_level = 0.0
        for level in sorted_levels:
            if current_price <= fib_levels[level]:
                current_level = level
            else:
                break

    return current_level


def _swing_to_response(swing: dict, is_active: bool) -> CalibrationSwingResponse:
    """Convert swing dict to CalibrationSwingResponse."""
    high = swing['high_price']
    low = swing['low_price']
    swing_range = high - low

    if swing['direction'] == 'bull':
        fib_0 = low
        fib_0382 = low + swing_range * 0.382
        fib_1 = high
        fib_2 = low + swing_range * 2.0
    else:
        fib_0 = high
        fib_0382 = high - swing_range * 0.382
        fib_1 = low
        fib_2 = high - swing_range * 2.0

    return CalibrationSwingResponse(
        id=swing['id'],
        scale=swing['scale'],
        direction=swing['direction'],
        high_price=high,
        high_bar_index=swing['high_bar_index'],
        low_price=low,
        low_bar_index=swing['low_bar_index'],
        size=swing['size'],
        rank=swing.get('rank', 1),
        is_active=is_active,
        fib_0=fib_0,
        fib_0382=fib_0382,
        fib_1=fib_1,
        fib_2=fib_2,
    )


def _diff_swing_states(
    prev_swings: Dict[str, dict],
    new_swings: Dict[str, dict],
    prev_fib_levels: Dict[str, float],
    current_price: float,
    bar_index: int
) -> tuple[List[ReplayEventResponse], Dict[str, float]]:
    """
    Diff swing states and generate events.

    Returns (events, new_fib_levels).
    """
    events = []
    new_fib_levels = {}

    prev_ids = set(prev_swings.keys())
    new_ids = set(new_swings.keys())

    # SWING_FORMED: New swings that weren't in previous state
    for swing_id in new_ids - prev_ids:
        swing = new_swings[swing_id]
        events.append(ReplayEventResponse(
            type="SWING_FORMED",
            bar_index=bar_index,
            scale=swing['scale'],
            direction=swing['direction'],
            swing_id=swing_id,
            swing=_swing_to_response(swing, True),
        ))
        # Initialize fib level tracking
        new_fib_levels[swing_id] = _get_current_fib_level(swing, current_price)

    # SWING_INVALIDATED: Swings that disappeared
    for swing_id in prev_ids - new_ids:
        swing = prev_swings[swing_id]
        events.append(ReplayEventResponse(
            type="SWING_INVALIDATED",
            bar_index=bar_index,
            scale=swing['scale'],
            direction=swing['direction'],
            swing_id=swing_id,
        ))

    # Check continuing swings for LEVEL_CROSS and COMPLETION
    for swing_id in prev_ids & new_ids:
        swing = new_swings[swing_id]
        prev_level = prev_fib_levels.get(swing_id, 0.0)
        new_level = _get_current_fib_level(swing, current_price)
        new_fib_levels[swing_id] = new_level

        # SWING_COMPLETED: crossed 2.0 level
        if prev_level < 2.0 and new_level >= 2.0:
            events.append(ReplayEventResponse(
                type="SWING_COMPLETED",
                bar_index=bar_index,
                scale=swing['scale'],
                direction=swing['direction'],
                swing_id=swing_id,
                level=2.0,
                previous_level=prev_level,
            ))
        # LEVEL_CROSS: crossed a significant fib level
        elif new_level != prev_level and new_level > prev_level:
            # Only emit for significant levels
            significant_levels = [0.382, 0.5, 0.618, 1.0, 1.382, 1.618]
            for lvl in significant_levels:
                if prev_level < lvl <= new_level:
                    events.append(ReplayEventResponse(
                        type="LEVEL_CROSS",
                        bar_index=bar_index,
                        scale=swing['scale'],
                        direction=swing['direction'],
                        swing_id=swing_id,
                        level=lvl,
                        previous_level=prev_level,
                    ))
                    break  # Only emit one level cross per bar

    return events, new_fib_levels


@app.post("/api/replay/advance", response_model=ReplayAdvanceResponse)
async def advance_replay(request: ReplayAdvanceRequest):
    """
    Advance playback beyond calibration window.

    For each new bar:
    1. Load next bar from source (not previously visible)
    2. Re-run detection with new bar as current_bar_index
    3. Diff against previous swing state
    4. Fire events for changes (SWING_FORMED, INVALIDATION, COMPLETION, LEVEL_CROSS)

    Args:
        calibration_bar_count: Number of bars in calibration window
        current_bar_index: Current playback position (last visible bar)
        advance_by: Number of bars to advance (default: 1)

    Returns:
        new_bars: New bars to append to chart
        events: Events that occurred during advance
        swing_state: Current swing state at new position
        end_of_data: Whether we've reached the end of data
    """
    global _replay_cache
    s = get_state()

    # Validate inputs
    if request.calibration_bar_count < 10:
        raise HTTPException(status_code=400, detail="calibration_bar_count must be >= 10")
    if request.current_bar_index < request.calibration_bar_count - 1:
        raise HTTPException(
            status_code=400,
            detail="current_bar_index must be >= calibration_bar_count - 1"
        )

    # Calculate new bar range
    start_index = request.current_bar_index + 1
    end_index = min(start_index + request.advance_by, len(s.source_bars))

    # Check for end of data
    if start_index >= len(s.source_bars):
        return ReplayAdvanceResponse(
            new_bars=[],
            events=[],
            swing_state=ReplaySwingState(),
            current_bar_index=request.current_bar_index,
            current_price=s.source_bars[request.current_bar_index].close if request.current_bar_index < len(s.source_bars) else 0,
            end_of_data=True,
        )

    # Scale thresholds
    scale_thresholds = {"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0}

    # Initialize or update cache
    if _replay_cache["last_bar_index"] != request.current_bar_index:
        # Cache miss - need to compute current swing state
        swings_by_scale = _detect_swings_at_bar(
            s.source_bars, request.current_bar_index, scale_thresholds
        )
        # Build swing state dict
        swing_state_dict = {}
        fib_levels_dict = {}
        current_price = s.source_bars[request.current_bar_index].close
        for scale in ["XL", "L", "M", "S"]:
            for swing in swings_by_scale[scale]:
                swing_state_dict[swing['id']] = swing
                fib_levels_dict[swing['id']] = _get_current_fib_level(swing, current_price)

        _replay_cache["swing_state"] = swing_state_dict
        _replay_cache["fib_levels"] = fib_levels_dict
        _replay_cache["last_bar_index"] = request.current_bar_index

    # Process each new bar
    new_bars = []
    all_events = []

    for bar_index in range(start_index, end_index):
        bar = s.source_bars[bar_index]
        new_bars.append(ReplayBarResponse(
            index=bar_index,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        ))

        # Detect swings at this bar
        new_swings_by_scale = _detect_swings_at_bar(
            s.source_bars, bar_index, scale_thresholds
        )

        # Build new swing state dict
        new_swing_state_dict = {}
        for scale in ["XL", "L", "M", "S"]:
            for swing in new_swings_by_scale[scale]:
                new_swing_state_dict[swing['id']] = swing

        # Diff states
        current_price = bar.close
        events, new_fib_levels = _diff_swing_states(
            _replay_cache["swing_state"],
            new_swing_state_dict,
            _replay_cache["fib_levels"],
            current_price,
            bar_index
        )
        all_events.extend(events)

        # Update cache
        _replay_cache["swing_state"] = new_swing_state_dict
        _replay_cache["fib_levels"] = new_fib_levels
        _replay_cache["last_bar_index"] = bar_index

    # Build final swing state response
    final_bar_index = end_index - 1
    final_price = s.source_bars[final_bar_index].close

    # Group swings by scale for response
    swing_state_response = ReplaySwingState()
    for swing_id, swing in _replay_cache["swing_state"].items():
        is_active = _is_swing_active(swing, final_price, swing['direction'])
        swing_response = _swing_to_response(swing, is_active)
        scale = swing['scale']
        if scale == "XL":
            swing_state_response.XL.append(swing_response)
        elif scale == "L":
            swing_state_response.L.append(swing_response)
        elif scale == "M":
            swing_state_response.M.append(swing_response)
        else:
            swing_state_response.S.append(swing_response)

    # Update playback_index for backend-controlled data boundary
    s.playback_index = final_bar_index

    return ReplayAdvanceResponse(
        new_bars=new_bars,
        events=all_events,
        swing_state=swing_state_response,
        current_bar_index=final_bar_index,
        current_price=final_price,
        end_of_data=final_bar_index >= len(s.source_bars) - 1,
    )


@app.get("/replay", response_class=HTMLResponse)
async def replay_page():
    """Serve the Replay View UI - React frontend."""
    project_root = Path(__file__).parent.parent.parent
    react_index = project_root / "frontend" / "dist" / "index.html"

    if react_index.exists():
        with open(react_index, 'r') as f:
            return HTMLResponse(content=f.read())

    return HTMLResponse(
        content="<h1>Replay View</h1><p>React build not found. Run 'npm run build' in frontend/</p>",
        status_code=200
    )


def init_app(
    data_file: str,
    storage_dir: str = "annotation_sessions",
    resolution_minutes: int = 1,
    window_size: int = 50000,
    scale: str = "S",
    target_bars: int = 200,
    cascade: bool = False,
    window_offset: int = 0,
    cached_df: Optional[pd.DataFrame] = None
):
    """
    Initialize the application with data file.

    Args:
        data_file: Path to OHLC CSV data file
        storage_dir: Directory for storing annotation sessions
        resolution_minutes: Source data resolution in minutes
        window_size: Total bars to load
        scale: Scale to annotate (S, M, L, XL) - ignored if cascade=True
        target_bars: Target number of bars to display - ignored if cascade=True
        cascade: Enable XL → L → M → S cascade workflow
        window_offset: Offset into source data (for random window selection)
        cached_df: Optional cached DataFrame to avoid re-reading file from disk
    """
    global state

    # Load source data (use cache if available)
    if cached_df is not None:
        logger.info(f"Using cached DataFrame ({len(cached_df)} bars)")
        df = cached_df
    else:
        logger.info(f"Loading data from {data_file}...")
        df, gaps = load_ohlc(data_file)

    # Store total bars before any slicing (for session/next random offset)
    total_source_bars = len(df)

    # Keep a reference to the full DataFrame for caching
    full_df = df

    # Apply offset and limit to window size
    if window_offset > 0:
        df = df.iloc[window_offset:]
        logger.info(f"Applied offset of {window_offset} bars")

    if len(df) > window_size:
        df = df.head(window_size)
        logger.info(f"Limited to {window_size} bars")

    # Convert to Bar objects
    source_bars = []
    for idx, (timestamp, row) in enumerate(df.iterrows()):
        bar = Bar(
            index=idx,
            timestamp=int(timestamp.timestamp()),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )
        source_bars.append(bar)

    logger.info(f"Loaded {len(source_bars)} source bars")

    # Create aggregator
    aggregator = BarAggregator(source_bars, resolution_minutes)

    # Initialize storage
    storage = AnnotationStorage(storage_dir)

    # Create session
    resolution_str = f"{resolution_minutes}m"
    session = storage.create_session(
        data_file=data_file,
        resolution=resolution_str,
        window_size=len(source_bars),
        window_offset=window_offset
    )
    logger.info(f"Created session {session.session_id}")

    # Initialize cascade controller if cascade mode
    cascade_controller = None
    if cascade:
        cascade_controller = CascadeController(
            session=session,
            source_bars=source_bars,
            aggregator=aggregator
        )
        # Use cascade's current scale and bars
        scale = cascade_controller.get_current_scale()
        aggregated_bars = cascade_controller.get_bars_for_scale(scale)
        aggregation_map = cascade_controller.get_aggregation_map(scale)
        logger.info(f"Cascade mode enabled, starting at scale {scale}")
    else:
        # Non-cascade mode: use fixed aggregation
        aggregated_bars = aggregator.aggregate_to_target_bars(target_bars)
        logger.info(f"Aggregated to {len(aggregated_bars)} display bars")

        # Build aggregation map (agg_index -> source indices range)
        aggregation_map = {}
        if len(source_bars) > target_bars:
            bars_per_candle = len(source_bars) // target_bars
            for agg_idx in range(len(aggregated_bars)):
                source_start = agg_idx * bars_per_candle
                source_end = min(source_start + bars_per_candle - 1, len(source_bars) - 1)
                aggregation_map[agg_idx] = (source_start, source_end)
        else:
            # No aggregation - 1:1 mapping
            for i in range(len(source_bars)):
                aggregation_map[i] = (i, i)

    # Initialize review storage (controller created lazily on /api/review/start)
    review_storage = ReviewStorage(storage_dir)

    state = AppState(
        source_bars=source_bars,
        aggregated_bars=aggregated_bars,
        aggregation_map=aggregation_map,
        storage=storage,
        session=session,
        scale=scale,
        target_bars=target_bars,
        cascade_controller=cascade_controller,
        aggregator=aggregator,
        review_storage=review_storage,
        # Fields for session/next endpoint
        data_file=data_file,
        storage_dir=storage_dir,
        resolution_minutes=resolution_minutes,
        total_source_bars=total_source_bars,
        cascade_enabled=cascade,
        # Cache full DataFrame to avoid re-reading on next window
        cached_dataframe=full_df
    )

    logger.info(f"Initialized annotator with {len(source_bars)} bars, scale={scale}")


# Mount React frontend assets (from Vite build)
project_root = Path(__file__).parent.parent.parent
react_dist_dir = project_root / "frontend" / "dist"
react_assets_dir = react_dist_dir / "assets"
if react_assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(react_assets_dir)), name="react-assets")

# Serve vite.svg (React favicon)
@app.get("/vite.svg")
async def vite_svg():
    """Serve vite.svg for React frontend."""
    svg_path = react_dist_dir / "vite.svg"
    if svg_path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(svg_path), media_type="image/svg+xml")
    return HTMLResponse(content="", status_code=404)

# Mount static files directory (legacy vanilla JS)
module_dir = Path(__file__).parent
static_dir = module_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
