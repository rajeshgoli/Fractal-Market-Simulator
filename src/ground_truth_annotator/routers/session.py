"""
Session router for Ground Truth Annotator.

Provides endpoints for session state management:
- GET /api/session - Get current session state
- PATCH /api/session/status - Update session status
- POST /api/session/finalize - Finalize session (keep/discard)
- POST /api/session/next - Create new session with random offset
"""

import random

from fastapi import APIRouter, HTTPException

from ..schemas import (
    SessionResponse,
    SessionStatusUpdate,
    SessionFinalizeRequest,
    SessionFinalizeResponse,
    NextSessionResponse,
)

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("", response_model=SessionResponse)
async def get_session():
    """Get current session state."""
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    # If cascade mode, use cascade controller's current scale
    current_scale = s.scale
    if s.cascade_controller:
        current_scale = s.cascade_controller.get_current_scale()

    return SessionResponse(
        session_id=session.session_id,
        data_file=session.data_file,
        resolution=session.resolution,
        window_size=session.window_size,
        window_offset=session.window_offset,
        total_source_bars=s.total_source_bars,
        calibration_bar_count=s.calibration_bar_count,
        scale=current_scale,
        created_at=session.created_at.isoformat(),
        annotation_count=len(session.annotations),
        completed_scales=session.completed_scales,
        status=session.status
    )


@router.patch("/status")
async def update_session_status(request: SessionStatusUpdate):
    """
    Update the session status (keep/discard).

    Used to mark sessions as high-quality ("keep") or practice runs ("discard")
    at the end of annotation or review.
    """
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    if request.status not in ("keep", "discard"):
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Must be 'keep' or 'discard'."
        )

    session.status = request.status
    s.storage.update_session(session)

    return {"status": "ok", "new_status": request.status}


@router.post("/finalize", response_model=SessionFinalizeResponse)
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
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    if request.status not in ("keep", "discard"):
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Must be 'keep' or 'discard'."
        )

    # Update session status first (in memory, will be persisted or deleted)
    session.status = request.status

    try:
        if request.status == "discard":
            # Delete review file first (if exists)
            if s.review_storage:
                s.review_storage.finalize_review(
                    session_id=session.session_id,
                    status="discard"
                )

            # Delete session file
            s.storage.finalize_session(
                session_id=session.session_id,
                status="discard"
            )

            return SessionFinalizeResponse(
                success=True,
                session_filename=None,
                review_filename=None,
                message="Session discarded (files deleted)"
            )

        # status == "keep": save session status then rename
        s.storage.update_session(session)

        # Update review session with metadata if it exists
        if s.review_controller:
            review = s.review_controller.get_or_create_review()
            review.difficulty = request.difficulty
            review.regime = request.regime
            review.session_comments = request.comments
            s.review_storage.save_review(review)

        # Finalize session file (rename to clean timestamp name)
        session_filename, new_path_id = s.storage.finalize_session(
            session_id=session.session_id,
            status="keep",
            label=request.label
        )

        # Finalize review file if it exists
        review_filename = None
        if s.review_storage:
            review_filename = s.review_storage.finalize_review(
                session_id=session.session_id,
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


@router.post("/next", response_model=NextSessionResponse)
async def start_next_session():
    """
    Create new annotation session with random window offset.

    Preserves current data file and settings, randomizes offset.
    Reinitializes the application state with the new session.
    Returns new session_id for redirect.
    """
    from ..api import get_state, get_or_create_session, init_app

    s = get_state()

    # Calculate random offset (use source_bars length as window size)
    window_size = len(s.source_bars)
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

    # Get the new session from updated state (create it for annotation workflow)
    new_state = get_state()
    new_session = get_or_create_session(new_state)

    return NextSessionResponse(
        session_id=new_session.session_id,
        offset=new_offset,
        redirect_url="/"
    )
