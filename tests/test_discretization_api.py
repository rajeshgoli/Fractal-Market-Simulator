"""
Tests for discretization API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from src.ground_truth_annotator import api
from src.swing_analysis.types import Bar


@pytest.fixture
def sample_bars():
    """Create sample bars for testing."""
    bars = []
    base_price = 5000.0
    for i in range(100):
        # Create some price movement for swing detection
        price_offset = (i % 20 - 10) * 2  # Oscillating pattern
        high = base_price + price_offset + 5
        low = base_price + price_offset - 5
        bars.append(Bar(
            index=i,
            timestamp=1700000000 + i * 60,
            open=base_price + price_offset,
            high=high,
            low=low,
            close=base_price + price_offset + (2 if i % 2 == 0 else -2),
        ))
    return bars


@pytest.fixture
def initialized_app(sample_bars, tmp_path):
    """Initialize the app with sample bars."""
    # Reset global state
    api.state = None

    # Create aggregation map
    aggregation_map = {i: (i, i) for i in range(len(sample_bars))}

    # Create storage and session
    storage = api.AnnotationStorage(str(tmp_path))
    session = storage.create_session(
        data_file="test.csv",
        resolution="1m",
        window_size=len(sample_bars)
    )

    # Initialize state
    api.state = api.AppState(
        source_bars=sample_bars,
        aggregated_bars=sample_bars,
        aggregation_map=aggregation_map,
        storage=storage,
        session=session,
        scale="M",
        target_bars=100,
        cascade_controller=None,
        aggregator=None,
        comparison_report=None,
        review_storage=api.ReviewStorage(str(tmp_path)),
        review_controller=None,
        comparison_results=None,
        data_file="test.csv",
        storage_dir=str(tmp_path),
        resolution_minutes=1,
        total_source_bars=len(sample_bars),
        cascade_enabled=False,
        cached_dataframe=None,
        precompute_in_progress=False,
        precompute_thread=None,
        discretization_log=None,
    )

    yield TestClient(api.app)

    # Cleanup
    api.state = None


class TestDiscretizationState:
    """Tests for GET /api/discretization/state."""

    def test_state_no_log_initially(self, initialized_app):
        """State returns has_log=False when no discretization has been run."""
        response = initialized_app.get("/api/discretization/state")
        assert response.status_code == 200

        data = response.json()
        assert data["has_log"] is False
        assert data["event_count"] == 0
        assert data["swing_count"] == 0
        assert data["scales"] == []

    def test_state_has_log_after_run(self, initialized_app):
        """State returns has_log=True after discretization is run."""
        # Run discretization first
        run_response = initialized_app.post("/api/discretization/run")
        assert run_response.status_code == 200

        # Check state
        response = initialized_app.get("/api/discretization/state")
        assert response.status_code == 200

        data = response.json()
        assert data["has_log"] is True


class TestDiscretizationRun:
    """Tests for POST /api/discretization/run."""

    def test_run_discretization_success(self, initialized_app):
        """Run discretization returns success."""
        response = initialized_app.post("/api/discretization/run")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "event_count" in data
        assert "swing_count" in data
        assert "scales_processed" in data
        assert "message" in data

    def test_run_discretization_idempotent(self, initialized_app):
        """Running discretization multiple times works."""
        response1 = initialized_app.post("/api/discretization/run")
        assert response1.status_code == 200

        response2 = initialized_app.post("/api/discretization/run")
        assert response2.status_code == 200


class TestDiscretizationSwings:
    """Tests for GET /api/discretization/swings."""

    def test_swings_404_without_run(self, initialized_app):
        """Getting swings returns 404 if discretization not run."""
        response = initialized_app.get("/api/discretization/swings")
        assert response.status_code == 404

    def test_swings_returns_list(self, initialized_app):
        """Getting swings returns a list after discretization."""
        # Run discretization first
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/swings")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_swings_filter_by_scale(self, initialized_app):
        """Swings can be filtered by scale."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/swings?scale=XL")
        assert response.status_code == 200
        # All returned swings should have scale XL (or empty if none match)
        for swing in response.json():
            assert swing["scale"] == "XL"

    def test_swings_filter_by_status(self, initialized_app):
        """Swings can be filtered by status."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/swings?status=active")
        assert response.status_code == 200
        for swing in response.json():
            assert swing["status"] == "active"

    def test_swings_structure(self, initialized_app):
        """Swings have expected structure."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/swings")
        assert response.status_code == 200

        swings = response.json()
        if swings:
            swing = swings[0]
            assert "swing_id" in swing
            assert "scale" in swing
            assert "direction" in swing
            assert "anchor0" in swing
            assert "anchor1" in swing
            assert "formed_at_bar" in swing
            assert "status" in swing


class TestDiscretizationEvents:
    """Tests for GET /api/discretization/events."""

    def test_events_404_without_run(self, initialized_app):
        """Getting events returns 404 if discretization not run."""
        response = initialized_app.get("/api/discretization/events")
        assert response.status_code == 404

    def test_events_returns_list(self, initialized_app):
        """Getting events returns a list after discretization."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_events_filter_by_scale(self, initialized_app):
        """Events can be filtered by scale."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events?scale=XL")
        assert response.status_code == 200
        # Should not raise error

    def test_events_filter_by_event_type(self, initialized_app):
        """Events can be filtered by event type."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events?event_type=LEVEL_CROSS")
        assert response.status_code == 200
        for event in response.json():
            assert event["event_type"] == "LEVEL_CROSS"

    def test_events_filter_by_shock_threshold(self, initialized_app):
        """Events can be filtered by shock threshold."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events?shock_threshold=2.0")
        assert response.status_code == 200
        for event in response.json():
            assert event.get("shock") is not None
            assert event["shock"]["range_multiple"] >= 2.0

    def test_events_filter_by_bar_range(self, initialized_app):
        """Events can be filtered by bar range."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events?bar_start=10&bar_end=50")
        assert response.status_code == 200
        for event in response.json():
            assert 10 <= event["bar"] <= 50

    def test_events_filter_bar_start_only(self, initialized_app):
        """Events can be filtered with only bar_start (open-ended to right)."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events?bar_start=20")
        assert response.status_code == 200
        for event in response.json():
            assert event["bar"] >= 20

    def test_events_filter_bar_end_only(self, initialized_app):
        """Events can be filtered with only bar_end (open-ended to left)."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events?bar_end=30")
        assert response.status_code == 200
        for event in response.json():
            assert event["bar"] <= 30

    def test_events_filter_bar_range_empty(self, initialized_app):
        """Out-of-range bar queries return empty list."""
        initialized_app.post("/api/discretization/run")

        # Use a very high bar range that won't have any events
        response = initialized_app.get("/api/discretization/events?bar_start=999999&bar_end=999999")
        assert response.status_code == 200
        assert response.json() == []

    def test_events_structure(self, initialized_app):
        """Events have expected structure."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/events")
        assert response.status_code == 200

        events = response.json()
        if events:
            event = events[0]
            assert "bar" in event
            assert "timestamp" in event
            assert "swing_id" in event
            assert "event_type" in event
            assert "data" in event


class TestDiscretizationLevels:
    """Tests for GET /api/discretization/levels."""

    def test_levels_404_without_run(self, initialized_app):
        """Getting levels returns 404 if discretization not run."""
        response = initialized_app.get("/api/discretization/levels?swing_id=test")
        assert response.status_code == 404

    def test_levels_404_invalid_swing(self, initialized_app):
        """Getting levels for invalid swing returns 404."""
        initialized_app.post("/api/discretization/run")

        response = initialized_app.get("/api/discretization/levels?swing_id=nonexistent")
        assert response.status_code == 404

    def test_levels_for_valid_swing(self, initialized_app):
        """Getting levels for valid swing returns level data."""
        initialized_app.post("/api/discretization/run")

        # Get a swing ID first
        swings_response = initialized_app.get("/api/discretization/swings")
        swings = swings_response.json()

        if swings:
            swing_id = swings[0]["swing_id"]
            response = initialized_app.get(f"/api/discretization/levels?swing_id={swing_id}")
            assert response.status_code == 200

            data = response.json()
            assert "swing_id" in data
            assert "scale" in data
            assert "direction" in data
            assert "anchor0" in data
            assert "anchor1" in data
            assert "levels" in data
            assert isinstance(data["levels"], list)

            # Check level structure
            if data["levels"]:
                level = data["levels"][0]
                assert "ratio" in level
                assert "price" in level
                assert "label" in level


