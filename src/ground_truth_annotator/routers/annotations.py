"""
Annotations router for Ground Truth Annotator.

Provides CRUD endpoints for swing annotations:
- POST /api/annotations - Create a new annotation
- GET /api/annotations - List all annotations for current scale
- DELETE /api/annotations/{annotation_id} - Delete an annotation
"""

from decimal import Decimal
from typing import List

from fastapi import APIRouter, HTTPException

from ..models import SwingAnnotation
from ..schemas import AnnotationCreate, AnnotationResponse

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


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


@router.post("", response_model=AnnotationResponse)
async def create_annotation(request: AnnotationCreate):
    """
    Create a new swing annotation.

    Direction is inferred from price movement:
    - If start.high > end.high -> bull reference (downswing)
    - If start.low < end.low -> bear reference (upswing)
    """
    # Import here to avoid circular imports
    from ..api import get_state, get_or_create_session, start_precomputation_if_ready

    s = get_state()
    session = get_or_create_session(s)

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
        window_id=session.session_id
    )

    # Save annotation
    s.storage.save_annotation(session.session_id, annotation)

    # Reload session to get updated annotation list
    s.session = s.storage.get_session(session.session_id)

    # Sync cascade controller's session if in cascade mode
    if s.cascade_controller:
        s.cascade_controller._session = s.session

    # Start background precomputation early (after first annotation)
    start_precomputation_if_ready(s)

    return _annotation_to_response(annotation)


@router.get("", response_model=List[AnnotationResponse])
async def list_annotations():
    """List all annotations for current scale."""
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    annotations = s.storage.get_annotations(session.session_id, scale=s.scale)

    return [_annotation_to_response(ann) for ann in annotations]


@router.delete("/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """Delete an annotation by ID."""
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    success = s.storage.delete_annotation(session.session_id, annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Reload session
    s.session = s.storage.get_session(session.session_id)

    # Sync cascade controller's session if in cascade mode
    if s.cascade_controller:
        s.cascade_controller._session = s.session

    return {"status": "ok", "annotation_id": annotation_id}
