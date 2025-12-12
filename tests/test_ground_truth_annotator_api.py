"""
Tests for Ground Truth Annotator API.
"""

import tempfile
import shutil
from pathlib import Path
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.ground_truth_annotator import api
from src.ground_truth_annotator.api import app, init_app, state


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    storage_dir = tempfile.mkdtemp()
    yield storage_dir
    shutil.rmtree(storage_dir)


@pytest.fixture
def test_data_path():
    """Path to test data file."""
    return "test_data/test.csv"


@pytest.fixture
def client(temp_storage, test_data_path):
    """Create test client with initialized app."""
    # Reset global state
    api.state = None

    init_app(
        data_file=test_data_path,
        storage_dir=temp_storage,
        resolution_minutes=1,
        window_size=500,
        scale="S",
        target_bars=50
    )

    with TestClient(app) as client:
        yield client


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["initialized"] is True


class TestBarsEndpoint:
    """Tests for /api/bars endpoint."""

    def test_get_bars_returns_list(self, client):
        response = client.get("/api/bars")
        assert response.status_code == 200
        bars = response.json()
        assert isinstance(bars, list)
        assert len(bars) == 50  # target_bars

    def test_bar_has_required_fields(self, client):
        response = client.get("/api/bars")
        bars = response.json()
        bar = bars[0]

        assert "index" in bar
        assert "timestamp" in bar
        assert "open" in bar
        assert "high" in bar
        assert "low" in bar
        assert "close" in bar
        assert "source_start_index" in bar
        assert "source_end_index" in bar

    def test_bars_ordered_by_index(self, client):
        response = client.get("/api/bars")
        bars = response.json()

        for i, bar in enumerate(bars):
            assert bar["index"] == i


class TestSessionEndpoint:
    """Tests for /api/session endpoint."""

    def test_get_session_returns_state(self, client):
        response = client.get("/api/session")
        assert response.status_code == 200
        session = response.json()

        assert "session_id" in session
        assert session["scale"] == "S"
        assert session["annotation_count"] == 0

    def test_session_has_required_fields(self, client):
        response = client.get("/api/session")
        session = response.json()

        required_fields = [
            "session_id", "data_file", "resolution", "window_size",
            "scale", "created_at", "annotation_count", "completed_scales"
        ]
        for field in required_fields:
            assert field in session, f"Missing field: {field}"


class TestAnnotationsEndpoint:
    """Tests for /api/annotations endpoints."""

    def test_list_annotations_empty_initially(self, client):
        response = client.get("/api/annotations")
        assert response.status_code == 200
        annotations = response.json()
        assert annotations == []

    def test_create_annotation_valid(self, client):
        response = client.post("/api/annotations", json={
            "start_bar_index": 5,
            "end_bar_index": 15
        })
        assert response.status_code == 200
        annotation = response.json()

        assert "annotation_id" in annotation
        assert annotation["start_bar_index"] == 5
        assert annotation["end_bar_index"] == 15
        assert annotation["scale"] == "S"
        assert annotation["direction"] in ["bull", "bear"]

    def test_create_annotation_invalid_same_bar(self, client):
        response = client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 10
        })
        assert response.status_code == 400
        assert "different" in response.text.lower()

    def test_create_annotation_invalid_index(self, client):
        response = client.post("/api/annotations", json={
            "start_bar_index": -1,
            "end_bar_index": 10
        })
        assert response.status_code == 400

    def test_create_annotation_out_of_range(self, client):
        response = client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 999
        })
        assert response.status_code == 400

    def test_annotation_persists_in_list(self, client):
        # Create annotation
        client.post("/api/annotations", json={
            "start_bar_index": 3,
            "end_bar_index": 8
        })

        # Verify in list
        response = client.get("/api/annotations")
        annotations = response.json()
        assert len(annotations) == 1
        assert annotations[0]["start_bar_index"] == 3
        assert annotations[0]["end_bar_index"] == 8

    def test_delete_annotation(self, client):
        # Create annotation
        create_response = client.post("/api/annotations", json={
            "start_bar_index": 5,
            "end_bar_index": 10
        })
        annotation_id = create_response.json()["annotation_id"]

        # Delete it
        delete_response = client.delete(f"/api/annotations/{annotation_id}")
        assert delete_response.status_code == 200

        # Verify removed
        list_response = client.get("/api/annotations")
        assert list_response.json() == []

    def test_delete_nonexistent_annotation(self, client):
        response = client.delete("/api/annotations/nonexistent-id")
        assert response.status_code == 404


class TestDirectionInference:
    """Tests for swing direction inference."""

    def test_bull_reference_when_price_goes_down(self, client):
        # Get bars to check prices
        bars_response = client.get("/api/bars")
        bars = bars_response.json()

        # Find a case where start.high > end.high (downswing = bull reference)
        start_idx = None
        end_idx = None
        for i in range(len(bars) - 5):
            if bars[i]["high"] > bars[i + 5]["high"]:
                start_idx = i
                end_idx = i + 5
                break

        if start_idx is None:
            pytest.skip("No downward price movement found in test data")

        response = client.post("/api/annotations", json={
            "start_bar_index": start_idx,
            "end_bar_index": end_idx
        })
        annotation = response.json()
        assert annotation["direction"] == "bull"

    def test_bear_reference_when_price_goes_up(self, client):
        # Get bars to check prices
        bars_response = client.get("/api/bars")
        bars = bars_response.json()

        # Find a case where start.high <= end.high (upswing = bear reference)
        start_idx = None
        end_idx = None
        for i in range(len(bars) - 5):
            if bars[i]["high"] <= bars[i + 5]["high"]:
                start_idx = i
                end_idx = i + 5
                break

        if start_idx is None:
            pytest.skip("No upward price movement found in test data")

        response = client.post("/api/annotations", json={
            "start_bar_index": start_idx,
            "end_bar_index": end_idx
        })
        annotation = response.json()
        assert annotation["direction"] == "bear"


class TestAggregationMapping:
    """Tests for source-to-aggregated bar mapping."""

    def test_aggregation_map_covers_all_bars(self, client):
        bars_response = client.get("/api/bars")
        bars = bars_response.json()

        for bar in bars:
            assert bar["source_start_index"] >= 0
            assert bar["source_end_index"] >= bar["source_start_index"]

    def test_source_indices_sequential(self, client):
        bars_response = client.get("/api/bars")
        bars = bars_response.json()

        # Each bar's source end should be before or at next bar's source start
        for i in range(len(bars) - 1):
            assert bars[i]["source_end_index"] < bars[i + 1]["source_end_index"]


class TestRootEndpoint:
    """Tests for serving the frontend."""

    def test_root_serves_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ground Truth Annotator" in response.text
