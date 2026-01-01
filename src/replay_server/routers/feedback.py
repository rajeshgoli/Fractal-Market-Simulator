"""
Feedback router for Replay View.

Provides endpoints for playback feedback/observation submission.

Endpoints:
- POST /api/feedback/submit - Submit playback feedback
"""

import base64
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import (
    PlaybackFeedbackRequest,
    PlaybackFeedbackResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])


@router.post("/api/feedback/submit", response_model=PlaybackFeedbackResponse)
async def submit_feedback(request: PlaybackFeedbackRequest):
    """
    Submit playback feedback/observation.

    Stores the observation with context snapshot for later analysis.
    Screenshots are saved to ground_truth/screenshots/ if provided.
    """
    from ..api import get_state

    s = get_state()

    if s.playback_feedback_storage is None:
        raise HTTPException(
            status_code=500,
            detail="Feedback storage not initialized"
        )

    if not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Feedback text cannot be empty"
        )

    # Store observation
    observation = s.playback_feedback_storage.add_observation(
        data_file=s.data_file or "unknown",
        text=request.text,
        playback_bar=request.playback_bar,
        snapshot=request.snapshot.model_dump(),
        offset=s.window_offset,
    )

    # Save screenshot if provided
    if request.screenshot_data:
        try:
            screenshots_dir = Path("ground_truth/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Build filename: {timestamp}_{mode}_{source}_{feedback_id}.png
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            mode = request.snapshot.mode or "unknown"
            source = Path(s.data_file or "unknown").stem
            filename = f"{timestamp}_{mode}_{source}_{observation.observation_id}.png"

            # Decode and save
            screenshot_bytes = base64.b64decode(request.screenshot_data)
            screenshot_path = screenshots_dir / filename
            screenshot_path.write_bytes(screenshot_bytes)
            logger.info(f"Saved screenshot: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")
            # Don't fail the request if screenshot save fails

    return PlaybackFeedbackResponse(
        success=True,
        observation_id=observation.observation_id,
        message=f"Feedback recorded at bar {request.playback_bar}",
    )
