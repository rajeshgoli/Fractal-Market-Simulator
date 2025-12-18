"""
Review router for Ground Truth Annotator.

Provides endpoints for review mode (validating annotations):
- POST /api/review/start - Initialize review mode
- GET /api/review/state - Get current review state
- GET /api/review/matches - Get matched swings
- GET /api/review/fp-sample - Get sampled false positives
- GET /api/review/fn-list - Get false negatives
- POST /api/review/feedback - Submit feedback
- POST /api/review/advance - Advance to next phase
- GET /api/review/summary - Get final summary
- GET /api/review/export - Export review data
"""

from decimal import Decimal
from typing import List, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..csv_utils import escape_csv_field
from ..models import BetterReference
from ..review_controller import ReviewController
from ..schemas import (
    ReviewStateResponse,
    MatchItem,
    FPSampleItem,
    FNItem,
    FeedbackSubmit,
    ReviewSummaryResponse,
)
from .comparison import _ensure_comparison_run

if TYPE_CHECKING:
    from ..api import AppState

router = APIRouter(prefix="/api/review", tags=["review"])


def _get_review_controller(s: "AppState") -> ReviewController:
    """Get or create the review controller."""
    if s.review_controller is None:
        raise HTTPException(
            status_code=404,
            detail="No review session. Start review with POST /api/review/start first."
        )
    return s.review_controller


@router.post("/start", response_model=ReviewStateResponse)
async def start_review():
    """
    Initialize Review Mode for current session.

    - Runs comparison if not already done
    - Creates ReviewSession
    - Samples false positives
    - Returns initial state
    """
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    if s.review_storage is None:
        raise HTTPException(status_code=500, detail="Review storage not initialized")

    # Run comparison if needed
    comparison_results = _ensure_comparison_run(s)

    # Create or get review controller
    if s.review_controller is None:
        s.review_controller = ReviewController(
            session_id=session.session_id,
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


@router.get("/state", response_model=ReviewStateResponse)
async def get_review_state():
    """Get current review session state and progress."""
    from ..api import get_state

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


@router.get("/matches", response_model=List[MatchItem])
async def get_matches():
    """
    Get matched swings for Phase 1 review.

    Returns all swings where user annotation matched system detection.
    """
    from ..api import get_state

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


@router.get("/fp-sample", response_model=List[FPSampleItem])
async def get_fp_sample():
    """
    Get sampled false positives for Phase 2 review.

    Returns 10-20 system detections that user didn't mark,
    stratified by scale.
    """
    from ..api import get_state

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


@router.get("/fn-list", response_model=List[FNItem])
async def get_fn_list():
    """
    Get all false negatives for Phase 3 review.

    Returns all swings user marked that system missed.
    """
    from ..api import get_state

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


@router.post("/feedback")
async def submit_feedback(request: FeedbackSubmit):
    """
    Submit feedback on a swing.

    - For matches: verdict = "correct" or "incorrect"
    - For FPs: verdict = "noise" or "valid_missed", optional category and better_reference
    - For FNs: verdict = "explained", comment REQUIRED

    Returns {"status": "ok", "feedback_id": str}
    """
    from ..api import get_state

    s = get_state()
    controller = _get_review_controller(s)

    # Convert better_reference from API model to domain model
    better_ref = None
    if request.better_reference:
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


@router.post("/advance", response_model=ReviewStateResponse)
async def advance_review_phase():
    """
    Mark current phase complete and advance to next.

    Validates:
    - Phase 3 (FN): All FNs must have feedback with comment

    Returns updated state.
    """
    from ..api import get_state

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


@router.get("/summary", response_model=ReviewSummaryResponse)
async def get_review_summary():
    """Get final review summary with all statistics."""
    from ..api import get_state

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


@router.get("/export")
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
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)
    controller = _get_review_controller(s)

    summary = controller.get_summary()
    matches = controller.get_matches()
    fps = controller.get_fp_sample()
    fns = controller.get_false_negatives()

    if format == "json":
        return {
            "session_id": session.session_id,
            "review_id": summary["review_id"],
            "data_file": session.data_file,
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
