"""
Tests for Issue #423: Backend ReferenceConfig API endpoints

Validates:
- GET /api/reference/config returns current config
- POST /api/reference/config accepts partial updates
- Config persists in replay cache for session
- Round-trip preserves values
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
            big_range_weight=config.big_range_weight,
            big_impulse_weight=config.big_impulse_weight,
            big_recency_weight=config.big_recency_weight,
            small_range_weight=config.small_range_weight,
            small_impulse_weight=config.small_impulse_weight,
            small_recency_weight=config.small_recency_weight,
            formation_fib_threshold=config.formation_fib_threshold,
        )

        assert response.big_range_weight == 0.5
        assert response.big_impulse_weight == 0.4
        assert response.big_recency_weight == 0.1
        assert response.small_range_weight == 0.2
        assert response.small_impulse_weight == 0.3
        assert response.small_recency_weight == 0.5
        assert response.formation_fib_threshold == 0.382

    def test_update_request_partial_fields(self):
        """ReferenceConfigUpdateRequest should support partial updates."""
        from src.replay_server.schemas import ReferenceConfigUpdateRequest

        # Only big_range_weight specified
        request = ReferenceConfigUpdateRequest(big_range_weight=0.6)
        assert request.big_range_weight == 0.6
        assert request.big_impulse_weight is None
        assert request.formation_fib_threshold is None

    def test_update_request_all_fields(self):
        """ReferenceConfigUpdateRequest should support all fields."""
        from src.replay_server.schemas import ReferenceConfigUpdateRequest

        request = ReferenceConfigUpdateRequest(
            big_range_weight=0.6,
            big_impulse_weight=0.3,
            big_recency_weight=0.1,
            small_range_weight=0.3,
            small_impulse_weight=0.4,
            small_recency_weight=0.3,
            formation_fib_threshold=0.5,
        )

        assert request.big_range_weight == 0.6
        assert request.big_impulse_weight == 0.3
        assert request.big_recency_weight == 0.1
        assert request.small_range_weight == 0.3
        assert request.small_impulse_weight == 0.4
        assert request.small_recency_weight == 0.3
        assert request.formation_fib_threshold == 0.5


class TestReferenceConfigWithSalienceWeights:
    """Test ReferenceConfig.with_salience_weights method."""

    def test_partial_weight_update(self):
        """with_salience_weights should only update provided fields."""
        config = ReferenceConfig.default()

        # Only update big_range_weight
        updated = config.with_salience_weights(big_range_weight=0.7)

        assert updated.big_range_weight == 0.7
        assert updated.big_impulse_weight == 0.4  # unchanged
        assert updated.big_recency_weight == 0.1  # unchanged
        assert updated.small_range_weight == 0.2  # unchanged

    def test_all_weights_update(self):
        """with_salience_weights should update all provided fields."""
        config = ReferenceConfig.default()

        updated = config.with_salience_weights(
            big_range_weight=0.6,
            big_impulse_weight=0.3,
            big_recency_weight=0.1,
            small_range_weight=0.3,
            small_impulse_weight=0.4,
            small_recency_weight=0.3,
        )

        assert updated.big_range_weight == 0.6
        assert updated.big_impulse_weight == 0.3
        assert updated.big_recency_weight == 0.1
        assert updated.small_range_weight == 0.3
        assert updated.small_impulse_weight == 0.4
        assert updated.small_recency_weight == 0.3

    def test_formation_threshold_update(self):
        """with_formation_threshold should update formation_fib_threshold."""
        config = ReferenceConfig.default()

        updated = config.with_formation_threshold(0.5)

        assert updated.formation_fib_threshold == 0.5
        # Other fields should be unchanged
        assert updated.big_range_weight == 0.5
        assert updated.big_impulse_weight == 0.4


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

        assert response.big_range_weight == 0.5
        assert response.big_impulse_weight == 0.4
        assert response.big_recency_weight == 0.1
        assert response.small_range_weight == 0.2
        assert response.small_impulse_weight == 0.3
        assert response.small_recency_weight == 0.5
        assert response.formation_fib_threshold == 0.382

    def test_update_config_partial(self):
        """POST /api/reference/config should apply partial updates."""
        import asyncio
        from src.replay_server.routers.reference import update_reference_config
        from src.replay_server.schemas import ReferenceConfigUpdateRequest
        from src.replay_server.routers.cache import get_replay_cache

        cache = get_replay_cache()
        cache.clear()

        request = ReferenceConfigUpdateRequest(big_range_weight=0.7)
        response = asyncio.get_event_loop().run_until_complete(update_reference_config(request))

        assert response.big_range_weight == 0.7
        assert response.big_impulse_weight == 0.4  # unchanged
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
            big_range_weight=0.6,
            formation_fib_threshold=0.5,
        )
        asyncio.get_event_loop().run_until_complete(update_reference_config(request))

        # Get config should return updated values
        response = asyncio.get_event_loop().run_until_complete(get_reference_config())

        assert response.big_range_weight == 0.6
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
            big_range_weight=0.8,
            big_impulse_weight=0.15,
            big_recency_weight=0.05,
            small_range_weight=0.4,
            small_impulse_weight=0.35,
            small_recency_weight=0.25,
            formation_fib_threshold=0.45,
        )
        asyncio.get_event_loop().run_until_complete(update_reference_config(request))

        # Get and verify all values
        response = asyncio.get_event_loop().run_until_complete(get_reference_config())

        assert response.big_range_weight == 0.8
        assert response.big_impulse_weight == 0.15
        assert response.big_recency_weight == 0.05
        assert response.small_range_weight == 0.4
        assert response.small_impulse_weight == 0.35
        assert response.small_recency_weight == 0.25
        assert response.formation_fib_threshold == 0.45
