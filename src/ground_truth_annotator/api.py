"""
FastAPI backend for the Ground Truth Annotator.

Provides REST API endpoints for:
- Serving aggregated bars for chart display
- Creating, listing, and deleting annotations
- Session state management
- Cascade workflow (XL → L → M → S scale progression)
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cascade_controller import CascadeController
from .comparison_analyzer import ComparisonAnalyzer, ComparisonResult
from .models import AnnotationSession, SwingAnnotation
from .review_controller import ReviewController
from .storage import AnnotationStorage, ReviewStorage
from ..data.ohlc_loader import load_ohlc
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.bull_reference_detector import Bar

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


class ScaleInfo(BaseModel):
    """Information about a single scale."""
    scale: str
    target_bars: Optional[int]
    actual_bars: int
    compression_ratio: float
    annotation_count: int
    is_complete: bool


class CascadeStateResponse(BaseModel):
    """Cascade workflow state."""
    current_scale: str
    current_scale_index: int
    reference_scale: Optional[str]
    completed_scales: List[str]
    scales_remaining: int
    is_complete: bool
    scale_info: Dict[str, ScaleInfo]


class CascadeAdvanceResponse(BaseModel):
    """Response from advancing cascade."""
    success: bool
    previous_scale: str
    current_scale: str
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


class FeedbackSubmit(BaseModel):
    """Request to submit feedback."""
    swing_type: str  # "match" | "false_positive" | "false_negative"
    swing_reference: dict  # {"annotation_id": str} or {"sample_index": int}
    verdict: str  # "correct" | "incorrect" | "noise" | "valid_missed" | "explained"
    comment: Optional[str] = None
    category: Optional[str] = None


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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "initialized": state is not None,
    }


@app.get("/api/bars", response_model=List[BarResponse])
async def get_bars(scale: Optional[str] = Query(None, description="Scale to get bars for (XL, L, M, S)")):
    """
    Get aggregated bars for chart display.

    Returns bars aggregated to the target count for efficient visualization.
    If scale is provided and cascade mode is active, returns bars for that scale.
    """
    s = get_state()

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

    return AnnotationResponse(
        annotation_id=annotation.annotation_id,
        scale=annotation.scale,
        direction=annotation.direction,
        start_bar_index=annotation.start_bar_index,
        end_bar_index=annotation.end_bar_index,
        start_source_index=annotation.start_source_index,
        end_source_index=annotation.end_source_index,
        start_price=str(annotation.start_price),
        end_price=str(annotation.end_price),
        created_at=annotation.created_at.isoformat(),
        window_id=annotation.window_id
    )


@app.get("/api/annotations", response_model=List[AnnotationResponse])
async def list_annotations():
    """List all annotations for current scale."""
    s = get_state()

    annotations = s.storage.get_annotations(s.session.session_id, scale=s.scale)

    return [
        AnnotationResponse(
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
        for ann in annotations
    ]


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
        completed_scales=s.session.completed_scales
    )


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
        scales_remaining=cascade_state["scales_remaining"],
        is_complete=cascade_state["is_complete"],
        scale_info=scale_info_models,
    )


@app.post("/api/cascade/advance", response_model=CascadeAdvanceResponse)
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

    return CascadeAdvanceResponse(
        success=success,
        previous_scale=previous_scale,
        current_scale=current_scale,
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

    return [
        AnnotationResponse(
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
        for ann in annotations
    ]


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
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)
        s.comparison_results = analyzer.compare_session(s.session, s.source_bars)
        # Also update the comparison report
        s.comparison_report = analyzer.generate_report(s.comparison_results)
    return s.comparison_results


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
    - For FPs: verdict = "noise" or "valid_missed", optional category
    - For FNs: verdict = "explained", comment REQUIRED

    Returns {"status": "ok", "feedback_id": str}
    """
    s = get_state()
    controller = _get_review_controller(s)

    try:
        feedback = controller.submit_feedback(
            swing_type=request.swing_type,
            swing_reference=request.swing_reference,
            verdict=request.verdict,
            comment=request.comment,
            category=request.category
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
            comment = (fb.get("comment") or "").replace(",", ";").replace("\n", " ")
            lines.append(
                f"match,{m['annotation']['annotation_id']},{m['scale']},"
                f"{m['annotation']['direction']},{m['annotation']['start_source_index']},"
                f"{m['annotation']['end_source_index']},{fb.get('verdict', '')},"
                f"{fb.get('category', '')},{comment}"
            )

        # False positives
        for fp in fps:
            fb = fp.get("feedback") or {}
            comment = (fb.get("comment") or "").replace(",", ";").replace("\n", " ")
            lines.append(
                f"false_positive,fp_{fp['sample_index']},{fp['scale']},"
                f"{fp['system_swing']['direction']},{fp['system_swing']['start_index']},"
                f"{fp['system_swing']['end_index']},{fb.get('verdict', '')},"
                f"{fb.get('category', '')},{comment}"
            )

        # False negatives
        for fn in fns:
            fb = fn.get("feedback") or {}
            comment = (fb.get("comment") or "").replace(",", ";").replace("\n", " ")
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


def init_app(
    data_file: str,
    storage_dir: str = "annotation_sessions",
    resolution_minutes: int = 1,
    window_size: int = 50000,
    scale: str = "S",
    target_bars: int = 200,
    cascade: bool = False
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
    """
    global state

    logger.info(f"Loading data from {data_file}...")

    # Load source data
    df, gaps = load_ohlc(data_file)

    # Limit to window size
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
        window_size=len(source_bars)
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
        review_storage=review_storage
    )

    logger.info(f"Initialized annotator with {len(source_bars)} bars, scale={scale}")


# Mount static files directory
module_dir = Path(__file__).parent
static_dir = module_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
