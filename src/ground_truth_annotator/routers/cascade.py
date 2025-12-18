"""
Cascade router for Ground Truth Annotator.

Provides endpoints for XL -> L -> M -> S cascade workflow:
- GET /api/cascade/state - Get current cascade state
- POST /api/cascade/advance - Advance to next scale
- POST /api/cascade/skip - Skip remaining scales
- GET /api/cascade/reference - Get reference annotations from larger scale
"""

from typing import List

from fastapi import APIRouter, HTTPException

from ..schemas import (
    CascadeStateResponse,
    CascadeTransitionResponse,
    ScaleInfo,
    AnnotationResponse,
)
from .annotations import _annotation_to_response

router = APIRouter(prefix="/api/cascade", tags=["cascade"])


@router.get("/state", response_model=CascadeStateResponse)
async def get_cascade_state():
    """Get current cascade workflow state."""
    from ..api import get_state

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


@router.post("/advance", response_model=CascadeTransitionResponse)
async def advance_cascade():
    """Mark current scale complete and advance to next scale."""
    from ..api import get_state

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


@router.post("/skip", response_model=CascadeTransitionResponse)
async def skip_remaining_scales():
    """Skip remaining scales and proceed to review.

    Marks the current scale as complete and all remaining scales as skipped.
    Use this for "Skip to FP Review" workflow when user wants to skip M/S
    annotation after completing XL/L.
    """
    from ..api import get_state

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


@router.get("/reference", response_model=List[AnnotationResponse])
async def get_reference_annotations():
    """Get annotations from the reference scale (completed larger scale)."""
    from ..api import get_state

    s = get_state()

    if not s.cascade_controller:
        raise HTTPException(
            status_code=400,
            detail="Cascade mode not enabled."
        )

    annotations = s.cascade_controller.get_reference_annotations()

    return [_annotation_to_response(ann) for ann in annotations]
