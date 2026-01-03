"""
Feedback router for Replay View.

Provides endpoints for playback feedback/observation submission and retrieval.
Observations are stored in SQLite with per-user isolation and LRU cleanup.

Endpoints:
- POST /api/feedback/submit - Submit playback feedback
- GET /api/feedback/mine - Get user's observations
- GET /api/feedback/screenshot/{observation_id} - Get observation screenshot
"""

import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ..db import add_observation, get_user_observations, get_observation_screenshot
from ..schemas import (
    PlaybackFeedbackRequest,
    PlaybackFeedbackResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])


def get_user_id(request: Request) -> Optional[str]:
    """Get user_id from request state (set by auth middleware)."""
    return getattr(request.state, "user_id", None)


@router.post("/api/feedback/submit", response_model=PlaybackFeedbackResponse)
async def submit_feedback(request: Request, feedback: PlaybackFeedbackRequest):
    """
    Submit playback feedback/observation.

    Stores the observation in SQLite with context snapshot and optional screenshot.
    Screenshots are stored as BLOBs directly in the database.

    In multi-tenant mode, observations are associated with the authenticated user.
    In local mode, observations are stored under a 'local' user ID.
    """
    if not feedback.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Feedback text cannot be empty"
        )

    # Get user_id from auth context (None in local mode)
    user_id = get_user_id(request)

    # Serialize snapshot to JSON
    event_context = json.dumps(feedback.snapshot.model_dump())

    # Decode screenshot if provided
    screenshot_bytes = None
    if feedback.screenshot_data:
        try:
            screenshot_bytes = base64.b64decode(feedback.screenshot_data)
        except Exception as e:
            logger.warning(f"Failed to decode screenshot: {e}")
            # Don't fail the request if screenshot decode fails

    # Store in SQLite
    try:
        observation_id = add_observation(
            user_id=user_id,
            bar_index=feedback.playback_bar,
            event_context=event_context,
            text=feedback.text,
            screenshot=screenshot_bytes,
        )
    except Exception as e:
        logger.error(f"Failed to store observation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to store observation"
        )

    return PlaybackFeedbackResponse(
        success=True,
        observation_id=str(observation_id),
        message=f"Feedback recorded at bar {feedback.playback_bar}",
    )


@router.get("/api/feedback/mine")
async def get_my_observations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Max observations to return")
):
    """
    Get the current user's observations.

    Returns observations ordered by most recent first.
    In multi-tenant mode, returns observations for the authenticated user.
    In local mode, returns observations for the 'local' user.
    """
    user_id = get_user_id(request)

    try:
        observations = get_user_observations(user_id=user_id, limit=limit)
    except Exception as e:
        logger.error(f"Failed to retrieve observations: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve observations"
        )

    return {
        "observations": observations,
        "count": len(observations),
    }


@router.get("/api/feedback/screenshot/{observation_id}")
async def get_screenshot(
    request: Request,
    observation_id: int,
):
    """
    Get the screenshot for an observation.

    Returns the PNG image if available, 404 if not found or no screenshot.
    Users can only access their own observations.
    """
    user_id = get_user_id(request)

    try:
        screenshot = get_observation_screenshot(observation_id, user_id)
    except Exception as e:
        logger.error(f"Failed to retrieve screenshot: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve screenshot"
        )

    if screenshot is None:
        raise HTTPException(
            status_code=404,
            detail="Screenshot not found"
        )

    return Response(
        content=screenshot,
        media_type="image/png",
    )
