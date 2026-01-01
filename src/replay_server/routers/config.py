"""
Detection config router for Replay View.

Provides endpoints for detection configuration management.

Endpoints:
- GET /api/replay/config - Get current detection configuration
- PUT /api/replay/config - Update detection configuration
"""

import logging

from fastapi import APIRouter, HTTPException

from ...swing_analysis.detection_config import DetectionConfig
from ...swing_analysis.reference_layer import ReferenceLayer
from ..schemas import (
    SwingConfigUpdateRequest,
    SwingConfigResponse,
)
from .cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


@router.get("/api/replay/config", response_model=SwingConfigResponse)
async def get_detection_config():
    """
    Get current swing detection configuration.

    Returns the current configuration values being used by the detector.
    If no detector is initialized, returns the default configuration.

    Returns:
        SwingConfigResponse with current configuration values.
    """
    cache = get_cache()

    # Get detector config or use defaults
    if cache.is_initialized():
        config = cache.detector.config
    else:
        config = DetectionConfig.default()

    # #404: Symmetric config - engulfed threshold at DetectionConfig level
    return SwingConfigResponse(
        stale_extension_threshold=config.stale_extension_threshold,
        origin_range_threshold=config.origin_range_prune_threshold,
        origin_time_threshold=config.origin_time_prune_threshold,
        max_turns=config.max_turns,
        engulfed_breach_threshold=config.engulfed_breach_threshold,
    )


@router.put("/api/replay/config", response_model=SwingConfigResponse)
async def update_detection_config(request: SwingConfigUpdateRequest):
    """
    Update swing detection configuration and re-calibrate.

    This endpoint allows changing detection thresholds (formation, invalidation,
    completion, etc.) and automatically re-runs calibration with the new config.

    The detector is reset and all bars are re-processed with the updated
    configuration, so the DAG state reflects the new thresholds.

    Args:
        request: SwingConfigUpdateRequest with new threshold values.
                 Only provided fields are updated; omitted fields keep defaults.

    Returns:
        SwingConfigResponse with the current configuration after update.
    """
    cache = get_cache()

    if not cache.is_initialized():
        raise HTTPException(
            status_code=400,
            detail="Must calibrate before updating config. Call /api/replay/calibrate first."
        )

    detector = cache.detector

    # Start with current config (preserve existing settings)
    new_config = detector.config

    # Apply global threshold updates (#404: all symmetric)
    if request.stale_extension_threshold is not None:
        new_config = new_config.with_stale_extension(request.stale_extension_threshold)
    if request.origin_range_threshold is not None or request.origin_time_threshold is not None:
        new_config = new_config.with_origin_prune(
            origin_range_prune_threshold=request.origin_range_threshold,
            origin_time_prune_threshold=request.origin_time_threshold,
        )
    if request.max_turns is not None:
        new_config = new_config.with_max_turns(request.max_turns)
    if request.engulfed_breach_threshold is not None:
        new_config = new_config.with_engulfed(request.engulfed_breach_threshold)

    # Update detector config (keeps current state, applies to future bars)
    detector.update_config(new_config)

    # Update reference layer with new config, preserving accumulated state
    old_ref_layer = cache.reference_layer
    new_ref_layer = ReferenceLayer(new_config)
    if old_ref_layer is not None:
        new_ref_layer.copy_state_from(old_ref_layer)
    cache.reference_layer = new_ref_layer

    logger.info(
        f"Config updated (continuing from current position): "
        f"{len([leg for leg in detector.state.active_legs if leg.status == 'active'])} active legs"
    )

    # Build response with current config values (#404: symmetric)
    return SwingConfigResponse(
        stale_extension_threshold=new_config.stale_extension_threshold,
        origin_range_threshold=new_config.origin_range_prune_threshold,
        origin_time_threshold=new_config.origin_time_prune_threshold,
        max_turns=new_config.max_turns,
        engulfed_breach_threshold=new_config.engulfed_breach_threshold,
    )
