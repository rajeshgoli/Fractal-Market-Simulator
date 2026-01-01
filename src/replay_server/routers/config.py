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
    DirectionConfigResponse,
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

    return SwingConfigResponse(
        bull=DirectionConfigResponse(
            engulfed_breach_threshold=config.bull.engulfed_breach_threshold,
        ),
        bear=DirectionConfigResponse(
            engulfed_breach_threshold=config.bear.engulfed_breach_threshold,
        ),
        stale_extension_threshold=config.stale_extension_threshold,
        origin_range_threshold=config.origin_range_prune_threshold,
        origin_time_threshold=config.origin_time_prune_threshold,
        min_branch_ratio=config.min_branch_ratio,
        min_turn_ratio=config.min_turn_ratio,
        max_turns_per_pivot=config.max_turns_per_pivot,
        max_turns_per_pivot_raw=config.max_turns_per_pivot_raw,
        enable_engulfed_prune=config.enable_engulfed_prune,
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

    # Apply bull direction updates
    if request.bull:
        if request.bull.engulfed_breach_threshold is not None:
            new_config = new_config.with_bull(engulfed_breach_threshold=request.bull.engulfed_breach_threshold)

    # Apply bear direction updates
    if request.bear:
        if request.bear.engulfed_breach_threshold is not None:
            new_config = new_config.with_bear(engulfed_breach_threshold=request.bear.engulfed_breach_threshold)

    # Apply global threshold updates
    if request.stale_extension_threshold is not None:
        new_config = new_config.with_stale_extension(request.stale_extension_threshold)
    if request.origin_range_threshold is not None or request.origin_time_threshold is not None:
        new_config = new_config.with_origin_prune(
            origin_range_prune_threshold=request.origin_range_threshold,
            origin_time_prune_threshold=request.origin_time_threshold,
        )

    # Apply min branch ratio for origin domination (#337)
    if request.min_branch_ratio is not None:
        new_config = new_config.with_min_branch_ratio(request.min_branch_ratio)

    # Apply min turn ratio for sibling pruning (#341)
    if request.min_turn_ratio is not None:
        new_config = new_config.with_min_turn_ratio(request.min_turn_ratio)

    # Apply max turns per pivot for top-k mode (#342)
    if request.max_turns_per_pivot is not None:
        new_config = new_config.with_max_turns_per_pivot(request.max_turns_per_pivot)

    # Apply max turns per pivot raw for raw counter-heft mode (#355)
    if request.max_turns_per_pivot_raw is not None:
        new_config = new_config.with_max_turns_per_pivot_raw(request.max_turns_per_pivot_raw)

    # Apply pruning algorithm toggles
    if request.enable_engulfed_prune is not None:
        new_config = new_config.with_prune_toggles(
            enable_engulfed_prune=request.enable_engulfed_prune,
        )

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

    # Build response with current config values
    return SwingConfigResponse(
        bull=DirectionConfigResponse(
            engulfed_breach_threshold=new_config.bull.engulfed_breach_threshold,
        ),
        bear=DirectionConfigResponse(
            engulfed_breach_threshold=new_config.bear.engulfed_breach_threshold,
        ),
        stale_extension_threshold=new_config.stale_extension_threshold,
        origin_range_threshold=new_config.origin_range_prune_threshold,
        origin_time_threshold=new_config.origin_time_prune_threshold,
        min_branch_ratio=new_config.min_branch_ratio,
        min_turn_ratio=new_config.min_turn_ratio,
        max_turns_per_pivot=new_config.max_turns_per_pivot,
        max_turns_per_pivot_raw=new_config.max_turns_per_pivot_raw,
        enable_engulfed_prune=new_config.enable_engulfed_prune,
    )
