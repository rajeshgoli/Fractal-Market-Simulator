"""
Tests for Issue #423: Backend ReferenceConfig API endpoints

Validates:
- GET /api/reference/config returns current config
- POST /api/reference/config accepts partial updates
- Config persists in replay cache for session
- Round-trip preserves values

Updated for #436 scale->bin migration:
- Unified weights (range_weight, impulse_weight, recency_weight, depth_weight)
- Removed scale-dependent weights (big_*, small_*)
- Removed use_bin_distribution (bins always used)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.swing_analysis.reference_config import ReferenceConfig


class TestReferenceConfigSchemas:
    """Test Pydantic schemas for reference config."""

    def test_response_schema_matches_config(self):
        """ReferenceConfigResponse should match ReferenceConfig structure."""
        from src.replay_server.schemas import ReferenceConfigResponse

        config = ReferenceConfig.default()
        response = ReferenceConfigResponse(
            range_weight=config.range_weight,
            impulse_weight=config.impulse_weight,
            recency_weight=config.recency_weight,
            depth_weight=config.depth_weight,
            range_counter_weight=config.range_counter_weight,
            top_n=config.top_n,
            formation_fib_threshold=config.formation_fib_threshold,
            origin_breach_tolerance=config.origin_breach_tolerance,
            significant_bin_threshold=config.significant_bin_threshold,
        )

        assert response.range_weight == 0.4
        assert response.impulse_weight == 0.4
        assert response.recency_weight == 0.1
        assert response.depth_weight == 0.1
        assert response.range_counter_weight == 0.0
        assert response.top_n == 5
        assert response.formation_fib_threshold == 0.382
        assert response.origin_breach_tolerance == 0.0
        assert response.significant_bin_threshold == 8

    def test_update_request_partial_fields(self):
        """ReferenceConfigUpdateRequest should support partial updates."""
        from src.replay_server.schemas import ReferenceConfigUpdateRequest

        # Only range_weight specified
        request = ReferenceConfigUpdateRequest(range_weight=0.6)
        assert request.range_weight == 0.6
        assert request.impulse_weight is None
        assert request.formation_fib_threshold is None

    def test_update_request_all_fields(self):
        """ReferenceConfigUpdateRequest should support all fields."""
        from src.replay_server.schemas import ReferenceConfigUpdateRequest

        request = ReferenceConfigUpdateRequest(
            range_weight=0.6,
            impulse_weight=0.3,
            recency_weight=0.05,
            depth_weight=0.05,
            formation_fib_threshold=0.5,
        )

        assert request.range_weight == 0.6
        assert request.impulse_weight == 0.3
        assert request.recency_weight == 0.05
        assert request.depth_weight == 0.05
        assert request.formation_fib_threshold == 0.5


class TestReferenceConfigWithSalienceWeights:
    """Test ReferenceConfig.with_salience_weights method."""

    def test_partial_weight_update(self):
        """with_salience_weights should only update provided fields."""
        config = ReferenceConfig.default()

        # Only update range_weight
        updated = config.with_salience_weights(range_weight=0.7)

        assert updated.range_weight == 0.7
        assert updated.impulse_weight == 0.4  # unchanged
        assert updated.recency_weight == 0.1  # unchanged
        assert updated.depth_weight == 0.1    # unchanged

    def test_all_weights_update(self):
        """with_salience_weights should update all provided fields."""
        config = ReferenceConfig.default()

        updated = config.with_salience_weights(
            range_weight=0.6,
            impulse_weight=0.3,
            recency_weight=0.05,
            depth_weight=0.05,
        )

        assert updated.range_weight == 0.6
        assert updated.impulse_weight == 0.3
        assert updated.recency_weight == 0.05
        assert updated.depth_weight == 0.05

    def test_formation_threshold_update(self):
        """with_formation_threshold should update formation_fib_threshold."""
        config = ReferenceConfig.default()

        updated = config.with_formation_threshold(0.5)

        assert updated.formation_fib_threshold == 0.5
        # Other fields should be unchanged
        assert updated.range_weight == 0.4
        assert updated.impulse_weight == 0.4


class TestReferenceConfigEndpoints:
    """Test reference config API endpoints."""

    def test_get_config_returns_defaults(self):
        """GET /api/reference/config should return defaults when no layer exists."""
        import asyncio
        from src.replay_server.routers.reference import get_reference_config
        from src.replay_server.routers.cache import get_replay_cache

        cache = get_replay_cache()
        cache.clear()  # Ensure no reference layer

        response = asyncio.get_event_loop().run_until_complete(get_reference_config())

        assert response.range_weight == 0.4
        assert response.impulse_weight == 0.4
        assert response.recency_weight == 0.1
        assert response.depth_weight == 0.1
        assert response.formation_fib_threshold == 0.382
        assert response.significant_bin_threshold == 8

    def test_update_config_partial(self):
        """POST /api/reference/config should apply partial updates."""
        import asyncio
        from src.replay_server.routers.reference import update_reference_config
        from src.replay_server.schemas import ReferenceConfigUpdateRequest
        from src.replay_server.routers.cache import get_replay_cache

        cache = get_replay_cache()
        cache.clear()

        request = ReferenceConfigUpdateRequest(range_weight=0.7)
        response = asyncio.get_event_loop().run_until_complete(update_reference_config(request))

        assert response.range_weight == 0.7
        assert response.impulse_weight == 0.4  # unchanged
        assert response.formation_fib_threshold == 0.382  # unchanged

    def test_update_config_persists(self):
        """Config updates should persist in replay cache."""
        import asyncio
        from src.replay_server.routers.reference import (
            get_reference_config,
            update_reference_config,
        )
        from src.replay_server.schemas import ReferenceConfigUpdateRequest
        from src.replay_server.routers.cache import get_replay_cache

        cache = get_replay_cache()
        cache.clear()

        # Update config
        request = ReferenceConfigUpdateRequest(
            range_weight=0.6,
            formation_fib_threshold=0.5,
        )
        asyncio.get_event_loop().run_until_complete(update_reference_config(request))

        # Get config should return updated values
        response = asyncio.get_event_loop().run_until_complete(get_reference_config())

        assert response.range_weight == 0.6
        assert response.formation_fib_threshold == 0.5

    def test_round_trip(self):
        """Config should round-trip through API correctly."""
        import asyncio
        from src.replay_server.routers.reference import (
            get_reference_config,
            update_reference_config,
        )
        from src.replay_server.schemas import ReferenceConfigUpdateRequest
        from src.replay_server.routers.cache import get_replay_cache

        cache = get_replay_cache()
        cache.clear()

        # Update with specific values
        request = ReferenceConfigUpdateRequest(
            range_weight=0.5,
            impulse_weight=0.3,
            recency_weight=0.1,
            depth_weight=0.1,
            formation_fib_threshold=0.45,
        )
        asyncio.get_event_loop().run_until_complete(update_reference_config(request))

        # Get and verify all values
        response = asyncio.get_event_loop().run_until_complete(get_reference_config())

        assert response.range_weight == 0.5
        assert response.impulse_weight == 0.3
        assert response.recency_weight == 0.1
        assert response.depth_weight == 0.1
        assert response.formation_fib_threshold == 0.45
