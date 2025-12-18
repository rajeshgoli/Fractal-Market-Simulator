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


# ============================================================================
# Cascade Mode Tests
# ============================================================================

@pytest.fixture
def cascade_client(temp_storage, test_data_path):
    """Create test client with cascade mode enabled."""
    # Reset global state
    api.state = None

    init_app(
        data_file=test_data_path,
        storage_dir=temp_storage,
        resolution_minutes=1,
        window_size=500,
        scale="S",
        target_bars=50,
        cascade=True
    )

    with TestClient(app) as client:
        yield client


class TestCascadeStateEndpoint:
    """Tests for /api/cascade/state endpoint."""

    def test_cascade_state_not_available_without_flag(self, client):
        """Should return 400 when cascade mode not enabled."""
        response = client.get("/api/cascade/state")
        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]

    def test_cascade_state_returns_initial_state(self, cascade_client):
        """Should return initial cascade state."""
        response = cascade_client.get("/api/cascade/state")
        assert response.status_code == 200
        data = response.json()

        assert data["current_scale"] == "XL"
        assert data["current_scale_index"] == 0
        assert data["reference_scale"] is None
        assert data["completed_scales"] == []
        assert data["is_complete"] is False
        assert "scale_info" in data

    def test_cascade_state_scale_info_structure(self, cascade_client):
        """Scale info should have correct structure."""
        response = cascade_client.get("/api/cascade/state")
        data = response.json()

        for scale in ["XL", "L", "M", "S"]:
            assert scale in data["scale_info"]
            info = data["scale_info"][scale]
            assert "actual_bars" in info
            assert "compression_ratio" in info
            assert "is_complete" in info


class TestCascadeAdvanceEndpoint:
    """Tests for /api/cascade/advance endpoint."""

    def test_advance_not_available_without_flag(self, client):
        """Should return 400 when cascade mode not enabled."""
        response = client.post("/api/cascade/advance")
        assert response.status_code == 400

    def test_advance_moves_to_next_scale(self, cascade_client):
        """Advance should move from XL to L."""
        # Initial state
        state = cascade_client.get("/api/cascade/state").json()
        assert state["current_scale"] == "XL"

        # Advance
        response = cascade_client.post("/api/cascade/advance")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["previous_scale"] == "XL"
        assert data["current_scale"] == "L"

    def test_advance_through_all_scales(self, cascade_client):
        """Should be able to advance through all scales."""
        scales = ["XL", "L", "M", "S"]

        for i, expected_next in enumerate(scales[1:] + [scales[-1]]):
            response = cascade_client.post("/api/cascade/advance")
            data = response.json()

            if i < 3:  # First 3 advances succeed
                assert data["success"] is True
            else:  # Last advance returns False
                assert data["success"] is False

        # Final state check
        state = cascade_client.get("/api/cascade/state").json()
        assert state["is_complete"] is True


class TestCascadeReferenceEndpoint:
    """Tests for /api/cascade/reference endpoint."""

    def test_reference_not_available_without_flag(self, client):
        """Should return 400 when cascade mode not enabled."""
        response = client.get("/api/cascade/reference")
        assert response.status_code == 400

    def test_reference_empty_initially(self, cascade_client):
        """Reference should be empty at start (no completed scales)."""
        response = cascade_client.get("/api/cascade/reference")
        assert response.status_code == 200
        assert response.json() == []

    def test_reference_includes_completed_scale_annotations(self, cascade_client):
        """After adding annotations and advancing, reference should include them."""
        # Create an annotation in XL
        bars = cascade_client.get("/api/bars?scale=XL").json()
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })

        # Advance to L
        cascade_client.post("/api/cascade/advance")

        # Reference should now include the XL annotation
        response = cascade_client.get("/api/cascade/reference")
        annotations = response.json()
        assert len(annotations) == 1
        assert annotations[0]["scale"] == "XL"


class TestCascadeBarsEndpoint:
    """Tests for /api/bars with scale parameter."""

    def test_get_bars_with_scale_parameter(self, cascade_client):
        """Should return bars aggregated for specific scale."""
        # Get XL bars
        xl_response = cascade_client.get("/api/bars?scale=XL")
        xl_bars = xl_response.json()

        # Get L bars
        l_response = cascade_client.get("/api/bars?scale=L")
        l_bars = l_response.json()

        # XL should have fewer bars than L
        assert len(xl_bars) < len(l_bars)

    def test_get_bars_invalid_scale(self, cascade_client):
        """Should return 400 for invalid scale."""
        response = cascade_client.get("/api/bars?scale=INVALID")
        assert response.status_code == 400


class TestCascadeSessionEndpoint:
    """Tests for /api/session with cascade mode."""

    def test_session_reflects_cascade_scale(self, cascade_client):
        """Session should reflect current cascade scale."""
        # Initial
        response = cascade_client.get("/api/session")
        assert response.json()["scale"] == "XL"

        # After advance
        cascade_client.post("/api/cascade/advance")
        response = cascade_client.get("/api/session")
        assert response.json()["scale"] == "L"


# ============================================================================
# Comparison Endpoint Tests
# ============================================================================

class TestComparisonRunEndpoint:
    """Tests for POST /api/compare endpoint."""

    def test_run_comparison_no_annotations(self, client):
        """Should run comparison even with no annotations."""
        response = client.post("/api/compare")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "summary" in data
        assert "message" in data

    def test_run_comparison_returns_summary(self, client):
        """Should return summary with expected fields."""
        response = client.post("/api/compare")
        data = response.json()
        summary = data["summary"]

        assert "total_user_annotations" in summary
        assert "total_system_detections" in summary
        assert "total_matches" in summary
        assert "total_false_negatives" in summary
        assert "total_false_positives" in summary
        assert "overall_match_rate" in summary

    def test_run_comparison_with_annotations(self, client):
        """Should include annotations in comparison."""
        # Create some annotations
        client.post("/api/annotations", json={
            "start_bar_index": 5,
            "end_bar_index": 15
        })
        client.post("/api/annotations", json={
            "start_bar_index": 20,
            "end_bar_index": 30
        })

        response = client.post("/api/compare")
        data = response.json()

        assert data["summary"]["total_user_annotations"] >= 2

    def test_run_comparison_message_format(self, client):
        """Message should contain match rate and counts."""
        response = client.post("/api/compare")
        data = response.json()

        assert "Match rate:" in data["message"]
        assert "false negatives" in data["message"]
        assert "false positives" in data["message"]


class TestComparisonReportEndpoint:
    """Tests for GET /api/compare/report endpoint."""

    def test_report_404_without_prior_compare(self, client):
        """Should return 404 if no comparison has been run."""
        response = client.get("/api/compare/report")
        assert response.status_code == 404
        assert "Run POST /api/compare first" in response.json()["detail"]

    def test_report_available_after_compare(self, client):
        """Should return report after comparison is run."""
        # Run comparison
        client.post("/api/compare")

        # Get report
        response = client.get("/api/compare/report")
        assert response.status_code == 200
        data = response.json()

        assert "summary" in data
        assert "by_scale" in data
        assert "false_negatives" in data
        assert "false_positives" in data

    def test_report_by_scale_structure(self, client):
        """Report should have per-scale breakdown."""
        client.post("/api/compare")
        response = client.get("/api/compare/report")
        data = response.json()

        # Should have all four scales
        for scale in ["XL", "L", "M", "S"]:
            assert scale in data["by_scale"]
            scale_data = data["by_scale"][scale]
            assert "user_annotations" in scale_data
            assert "system_detections" in scale_data
            assert "matches" in scale_data
            assert "match_rate" in scale_data


class TestComparisonExportEndpoint:
    """Tests for GET /api/compare/export endpoint."""

    def test_export_404_without_prior_compare(self, client):
        """Should return 404 if no comparison has been run."""
        response = client.get("/api/compare/export")
        assert response.status_code == 404

    def test_export_json_format(self, client):
        """Should export as JSON by default."""
        client.post("/api/compare")
        response = client.get("/api/compare/export?format=json")
        assert response.status_code == 200

        data = response.json()
        assert "summary" in data
        assert "by_scale" in data

    def test_export_csv_format(self, client):
        """Should export as CSV when requested."""
        # Create annotation to have some data
        client.post("/api/annotations", json={
            "start_bar_index": 5,
            "end_bar_index": 15
        })
        client.post("/api/compare")

        response = client.get("/api/compare/export?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

        # Should contain CSV header
        content = response.text
        assert "type,scale,start,end,direction" in content

    def test_export_invalid_format(self, client):
        """Should return 400 for invalid format."""
        client.post("/api/compare")
        response = client.get("/api/compare/export?format=xml")
        assert response.status_code == 400
        assert "Unsupported format" in response.json()["detail"]


class TestComparisonWithCascade:
    """Tests for comparison in cascade mode."""

    def test_cascade_comparison_all_scales(self, cascade_client):
        """Comparison should work in cascade mode."""
        response = cascade_client.post("/api/compare")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True

    def test_cascade_comparison_after_advancing(self, cascade_client):
        """Comparison should include annotations from all scales."""
        # Add XL annotation
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })

        # Advance to L
        cascade_client.post("/api/cascade/advance")

        # Add L annotation
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 20
        })

        # Run comparison
        response = cascade_client.post("/api/compare")
        data = response.json()

        # Should have counted both annotations
        assert data["summary"]["total_user_annotations"] >= 2


# ============================================================================
# Review Mode API Tests
# ============================================================================

class TestReviewStartEndpoint:
    """Tests for POST /api/review/start endpoint."""

    def test_start_review_creates_session(self, cascade_client):
        """POST /api/review/start creates ReviewSession."""
        response = cascade_client.post("/api/review/start")
        assert response.status_code == 200
        data = response.json()

        assert "review_id" in data
        assert "session_id" in data
        assert data["phase"] == "matches"
        assert "progress" in data
        assert "completed" in data["progress"]
        assert "total" in data["progress"]
        assert data["is_complete"] is False

    def test_start_review_idempotent(self, cascade_client):
        """Starting review twice returns same session."""
        response1 = cascade_client.post("/api/review/start")
        data1 = response1.json()

        response2 = cascade_client.post("/api/review/start")
        data2 = response2.json()

        assert data1["review_id"] == data2["review_id"]
        assert data1["session_id"] == data2["session_id"]

    def test_start_review_runs_comparison(self, cascade_client):
        """Starting review runs comparison automatically."""
        # Add an annotation first
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })

        response = cascade_client.post("/api/review/start")
        assert response.status_code == 200

        # Comparison report should now be available
        report_response = cascade_client.get("/api/compare/report")
        assert report_response.status_code == 200


class TestReviewStateEndpoint:
    """Tests for GET /api/review/state endpoint."""

    def test_get_review_state(self, cascade_client):
        """GET /api/review/state returns current phase."""
        # Start review first
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/state")
        assert response.status_code == 200
        data = response.json()

        assert "phase" in data
        assert data["phase"] == "matches"
        assert "progress" in data

    def test_get_review_state_404_without_start(self, cascade_client):
        """Should return 404 if review not started."""
        response = cascade_client.get("/api/review/state")
        assert response.status_code == 404
        assert "No review session" in response.json()["detail"]


class TestReviewMatchesEndpoint:
    """Tests for GET /api/review/matches endpoint."""

    def test_get_matches(self, cascade_client):
        """Returns matched swings with annotation data."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/matches")
        assert response.status_code == 200
        matches = response.json()
        assert isinstance(matches, list)

    def test_matches_structure(self, cascade_client):
        """Matches have correct structure."""
        # Add annotation that might match
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/matches")
        matches = response.json()

        # If there are matches, verify structure
        if matches:
            m = matches[0]
            assert "annotation_id" in m
            assert "scale" in m
            assert "direction" in m
            assert "start_index" in m
            assert "end_index" in m
            assert "system_start" in m
            assert "system_end" in m
            assert "feedback" in m


class TestReviewFPSampleEndpoint:
    """Tests for GET /api/review/fp-sample endpoint."""

    def test_get_fp_sample(self, cascade_client):
        """Returns stratified FP sample."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/fp-sample")
        assert response.status_code == 200
        fps = response.json()
        assert isinstance(fps, list)

    def test_fp_sample_structure(self, cascade_client):
        """FP sample has correct structure."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/fp-sample")
        fps = response.json()

        # If there are FPs, verify structure
        if fps:
            fp = fps[0]
            assert "fp_index" in fp
            assert "scale" in fp
            assert "direction" in fp
            assert "start_index" in fp
            assert "end_index" in fp
            assert "high_price" in fp
            assert "low_price" in fp
            assert "size" in fp
            assert "rank" in fp
            assert "feedback" in fp

    def test_fp_sample_limited(self, cascade_client):
        """FP sample should be capped at 20."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/fp-sample")
        fps = response.json()

        # Should not exceed sample limit
        assert len(fps) <= 20


class TestReviewFNListEndpoint:
    """Tests for GET /api/review/fn-list endpoint."""

    def test_get_fn_list(self, cascade_client):
        """Returns all false negatives."""
        # Create annotation that system likely missed
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 12
        })
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/fn-list")
        assert response.status_code == 200
        fns = response.json()
        assert isinstance(fns, list)

    def test_fn_list_structure(self, cascade_client):
        """FN list has correct structure."""
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 12
        })
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/fn-list")
        fns = response.json()

        # If there are FNs, verify structure
        if fns:
            fn = fns[0]
            assert "annotation_id" in fn
            assert "scale" in fn
            assert "direction" in fn
            assert "start_index" in fn
            assert "end_index" in fn
            assert "start_price" in fn
            assert "end_price" in fn
            assert "feedback" in fn


class TestReviewFeedbackEndpoint:
    """Tests for POST /api/review/feedback endpoint."""

    def test_submit_match_feedback(self, cascade_client):
        """Accept/reject match."""
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })
        cascade_client.post("/api/review/start")

        matches = cascade_client.get("/api/review/matches").json()
        if matches:
            response = cascade_client.post("/api/review/feedback", json={
                "swing_type": "match",
                "swing_reference": {"annotation_id": matches[0]["annotation_id"]},
                "verdict": "correct"
            })
            assert response.status_code == 200
            assert "feedback_id" in response.json()

    def test_submit_fp_feedback_noise(self, cascade_client):
        """Mark FP as noise."""
        cascade_client.post("/api/review/start")

        fps = cascade_client.get("/api/review/fp-sample").json()
        if fps:
            response = cascade_client.post("/api/review/feedback", json={
                "swing_type": "false_positive",
                "swing_reference": {"sample_index": fps[0]["fp_index"]},
                "verdict": "noise"
            })
            assert response.status_code == 200

    def test_submit_fp_feedback_valid(self, cascade_client):
        """Mark FP as actually valid."""
        cascade_client.post("/api/review/start")

        fps = cascade_client.get("/api/review/fp-sample").json()
        if fps:
            response = cascade_client.post("/api/review/feedback", json={
                "swing_type": "false_positive",
                "swing_reference": {"sample_index": fps[0]["fp_index"]},
                "verdict": "valid_missed",
                "category": "too_small"
            })
            assert response.status_code == 200

    def test_submit_fn_feedback_requires_comment(self, cascade_client):
        """400 error if no comment for FN."""
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 12
        })
        cascade_client.post("/api/review/start")

        fns = cascade_client.get("/api/review/fn-list").json()
        if fns:
            response = cascade_client.post("/api/review/feedback", json={
                "swing_type": "false_negative",
                "swing_reference": {"annotation_id": fns[0]["annotation_id"]},
                "verdict": "explained"
                # No comment - should fail
            })
            assert response.status_code == 400
            assert "comment" in response.json()["detail"].lower()

    def test_submit_fn_feedback_with_comment(self, cascade_client):
        """Success with comment for FN."""
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 12
        })
        cascade_client.post("/api/review/start")

        fns = cascade_client.get("/api/review/fn-list").json()
        if fns:
            response = cascade_client.post("/api/review/feedback", json={
                "swing_type": "false_negative",
                "swing_reference": {"annotation_id": fns[0]["annotation_id"]},
                "verdict": "explained",
                "comment": "This is a valid swing that the system missed because..."
            })
            assert response.status_code == 200


class TestReviewAdvanceEndpoint:
    """Tests for POST /api/review/advance endpoint."""

    def test_advance_from_matches(self, cascade_client):
        """Advances to fp_sample."""
        cascade_client.post("/api/review/start")

        response = cascade_client.post("/api/review/advance")
        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == "fp_sample"

    def test_advance_from_fp_sample(self, cascade_client):
        """Advances to fn_feedback."""
        cascade_client.post("/api/review/start")
        cascade_client.post("/api/review/advance")  # matches -> fp_sample

        response = cascade_client.post("/api/review/advance")
        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == "fn_feedback"

    def test_advance_from_fn_requires_all_feedback(self, cascade_client):
        """400 if FNs missing comments."""
        # Create annotation that will be FN
        cascade_client.post("/api/annotations", json={
            "start_bar_index": 10,
            "end_bar_index": 12
        })
        cascade_client.post("/api/review/start")

        # Advance to fn_feedback phase
        cascade_client.post("/api/review/advance")  # matches -> fp_sample
        cascade_client.post("/api/review/advance")  # fp_sample -> fn_feedback

        # Check if there are FNs
        fns = cascade_client.get("/api/review/fn-list").json()
        if fns:
            # Try to advance without feedback - should fail
            response = cascade_client.post("/api/review/advance")
            assert response.status_code == 400
            assert "feedback" in response.json()["detail"].lower()

    def test_advance_to_complete(self, cascade_client):
        """Final phase transition."""
        cascade_client.post("/api/review/start")

        # Advance through all phases (no FNs in this case)
        cascade_client.post("/api/review/advance")  # matches -> fp_sample
        cascade_client.post("/api/review/advance")  # fp_sample -> fn_feedback
        response = cascade_client.post("/api/review/advance")  # fn_feedback -> complete

        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == "complete"
        assert data["is_complete"] is True


class TestReviewSummaryEndpoint:
    """Tests for GET /api/review/summary endpoint."""

    def test_get_summary(self, cascade_client):
        """Returns summary with all statistics."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/summary")
        assert response.status_code == 200
        data = response.json()

        assert "session_id" in data
        assert "review_id" in data
        assert "phase" in data
        assert "matches" in data
        assert "false_positives" in data
        assert "false_negatives" in data
        assert "started_at" in data

    def test_summary_match_counts(self, cascade_client):
        """Summary has correct count structure."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/summary")
        data = response.json()

        assert "total" in data["matches"]
        assert "reviewed" in data["matches"]
        assert "correct" in data["matches"]
        assert "incorrect" in data["matches"]

        assert "sampled" in data["false_positives"]
        assert "reviewed" in data["false_positives"]
        assert "noise" in data["false_positives"]
        assert "valid" in data["false_positives"]

        assert "total" in data["false_negatives"]
        assert "explained" in data["false_negatives"]


class TestReviewExportEndpoint:
    """Tests for GET /api/review/export endpoint."""

    def test_export_json(self, cascade_client):
        """Returns structured JSON."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/export?format=json")
        assert response.status_code == 200
        data = response.json()

        assert "session_id" in data
        assert "review_id" in data
        assert "data_file" in data
        assert "summary" in data
        assert "matches" in data
        assert "false_positives" in data
        assert "false_negatives" in data

    def test_export_csv(self, cascade_client):
        """Returns CSV format."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/export?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

        # Check CSV header
        content = response.text
        assert "type,annotation_id,scale,direction,start,end,verdict,category,comment" in content

    def test_export_invalid_format(self, cascade_client):
        """400 for invalid format."""
        cascade_client.post("/api/review/start")

        response = cascade_client.get("/api/review/export?format=xml")
        assert response.status_code == 400


class TestSessionFinalizeEndpoint:
    """Tests for POST /api/session/finalize endpoint."""

    def test_finalize_keep_creates_clean_filename(self, client, temp_storage):
        """Keep should rename to clean timestamp filename."""
        response = client.post("/api/session/finalize", json={
            "status": "keep"
        })
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["session_filename"] is not None
        # Should be clean timestamp format (no 'inprogress-' prefix)
        assert not data["session_filename"].startswith("inprogress-")
        # Should end with .json
        assert data["session_filename"].endswith(".json")
        # Should contain timestamp pattern
        assert "-" in data["session_filename"]

    def test_finalize_keep_with_label(self, client, temp_storage):
        """Keep with label should include label in filename."""
        response = client.post("/api/session/finalize", json={
            "status": "keep",
            "label": "trending market"
        })
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        # Label should be sanitized (spaces -> underscores, lowercase)
        assert "trending_market" in data["session_filename"]

    def test_finalize_discard_deletes_files(self, client, temp_storage):
        """Discard should delete session files."""
        from pathlib import Path

        # Create an annotation to trigger session creation (lazy session)
        client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })

        # Get initial file count
        storage_path = Path(temp_storage)
        initial_files = list(storage_path.glob("*.json"))
        assert len(initial_files) > 0  # Should have inprogress file after annotation

        response = client.post("/api/session/finalize", json={
            "status": "discard"
        })
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["session_filename"] is None
        assert data["message"] == "Session discarded (files deleted)"

        # Verify file was deleted
        remaining_files = list(storage_path.glob("*.json"))
        assert len(remaining_files) < len(initial_files)

    def test_finalize_invalid_status(self, client):
        """Should reject invalid status."""
        response = client.post("/api/session/finalize", json={
            "status": "invalid"
        })
        assert response.status_code == 400
        assert "keep" in response.json()["detail"].lower()

    def test_finalize_keep_includes_review_file(self, cascade_client, temp_storage):
        """Keep should also rename review file if it exists."""
        # Start review to create review file
        cascade_client.post("/api/review/start")

        response = cascade_client.post("/api/session/finalize", json={
            "status": "keep"
        })
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["session_filename"] is not None
        assert data["review_filename"] is not None
        # Review filename should match session pattern
        assert "_review.json" in data["review_filename"]


class TestInprogressFilename:
    """Tests for inprogress filename on session creation."""

    def test_lazy_session_creates_inprogress_filename(self, temp_storage, test_data_path):
        """Sessions created lazily (on first annotation) should have inprogress- prefix."""
        from pathlib import Path
        from starlette.testclient import TestClient

        # Reset and init app (session NOT created yet - lazy)
        api.state = None
        init_app(
            data_file=test_data_path,
            storage_dir=temp_storage,
            resolution_minutes=1,
            window_size=500,
            scale="S",
            target_bars=50
        )

        # Check files in storage - should be empty initially
        storage_path = Path(temp_storage)
        initial_files = list(storage_path.glob("*.json"))
        assert len(initial_files) == 0  # No session file yet (lazy creation)

        # Create an annotation to trigger session creation
        client = TestClient(api.app)
        response = client.post("/api/annotations", json={
            "start_bar_index": 0,
            "end_bar_index": 5
        })
        assert response.status_code == 200

        # Now check files - should have inprogress file
        json_files = list(storage_path.glob("*.json"))
        inprogress_files = [f for f in json_files if f.name.startswith("inprogress-")]
        assert len(inprogress_files) == 1

    def test_replay_only_does_not_create_session(self, temp_storage, test_data_path):
        """Replay-only usage should NOT create orphan session files (#119)."""
        from pathlib import Path
        from starlette.testclient import TestClient

        # Reset and init app (session NOT created yet - lazy)
        api.state = None
        init_app(
            data_file=test_data_path,
            storage_dir=temp_storage,
            resolution_minutes=1,
            window_size=500,
            scale="S",
            target_bars=50
        )

        # Check files in storage - should be empty initially
        storage_path = Path(temp_storage)
        initial_files = list(storage_path.glob("*.json"))
        assert len(initial_files) == 0  # No session file yet (lazy creation)

        # Use replay endpoints (calibrate and advance) - no session needed
        client = TestClient(api.app)

        # Call calibrate endpoint
        response = client.get("/api/replay/calibrate?bar_count=100")
        assert response.status_code == 200

        # Call advance endpoint
        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": 100,
            "current_bar_index": 99,
            "advance_by": 5
        })
        assert response.status_code == 200

        # Check files in storage - should STILL be empty (replay doesn't need session)
        final_files = list(storage_path.glob("*.json"))
        assert len(final_files) == 0  # Still no session file - fixes #119


class TestReviewFlowIntegration:
    """Integration tests for complete review workflow."""

    def test_complete_review_flow(self, cascade_client):
        """Test complete review flow from start to finish."""
        # Start review
        start_response = cascade_client.post("/api/review/start")
        assert start_response.status_code == 200
        assert start_response.json()["phase"] == "matches"

        # Get matches and submit feedback for first one if any
        matches = cascade_client.get("/api/review/matches").json()
        if matches:
            cascade_client.post("/api/review/feedback", json={
                "swing_type": "match",
                "swing_reference": {"annotation_id": matches[0]["annotation_id"]},
                "verdict": "correct"
            })

        # Advance to FP phase
        cascade_client.post("/api/review/advance")
        state = cascade_client.get("/api/review/state").json()
        assert state["phase"] == "fp_sample"

        # Get FPs and submit feedback for first one if any
        fps = cascade_client.get("/api/review/fp-sample").json()
        if fps:
            cascade_client.post("/api/review/feedback", json={
                "swing_type": "false_positive",
                "swing_reference": {"sample_index": fps[0]["fp_index"]},
                "verdict": "noise"
            })

        # Advance to FN phase
        cascade_client.post("/api/review/advance")
        state = cascade_client.get("/api/review/state").json()
        assert state["phase"] == "fn_feedback"

        # Submit feedback for all FNs (required for advancement)
        fns = cascade_client.get("/api/review/fn-list").json()
        for fn in fns:
            cascade_client.post("/api/review/feedback", json={
                "swing_type": "false_negative",
                "swing_reference": {"annotation_id": fn["annotation_id"]},
                "verdict": "explained",
                "comment": "Test explanation"
            })

        # Advance to complete
        cascade_client.post("/api/review/advance")
        state = cascade_client.get("/api/review/state").json()
        assert state["phase"] == "complete"
        assert state["is_complete"] is True

        # Get final summary
        summary = cascade_client.get("/api/review/summary").json()
        assert summary["phase"] == "complete"
        assert summary["completed_at"] is not None

        # Export should work
        export = cascade_client.get("/api/review/export?format=json").json()
        assert "summary" in export


class TestWindowedSwingsEndpoint:
    """Tests for /api/swings/windowed endpoint."""

    def test_windowed_swings_returns_response(self, client):
        """Test that windowed swings endpoint returns valid response."""
        response = client.get("/api/swings/windowed?bar_end=100")
        assert response.status_code == 200
        data = response.json()
        assert "bar_end" in data
        assert "swing_count" in data
        assert "swings" in data
        assert data["bar_end"] == 100

    def test_windowed_swings_with_small_bar_end_returns_empty(self, client):
        """Test that small bar_end returns empty list (need minimum bars)."""
        response = client.get("/api/swings/windowed?bar_end=5")
        assert response.status_code == 200
        data = response.json()
        assert data["swing_count"] == 0
        assert data["swings"] == []

    def test_windowed_swings_returns_detected_swings(self, client):
        """Test that swings are detected and returned with correct structure."""
        response = client.get("/api/swings/windowed?bar_end=200&top_n=2")
        assert response.status_code == 200
        data = response.json()

        # May or may not have swings depending on data
        if data["swing_count"] > 0:
            swing = data["swings"][0]
            # Check required fields
            assert "id" in swing
            assert "direction" in swing
            assert "high_price" in swing
            assert "high_bar_index" in swing
            assert "low_price" in swing
            assert "low_bar_index" in swing
            assert "size" in swing
            assert "rank" in swing
            # Check Fib level fields
            assert "fib_0" in swing
            assert "fib_0382" in swing
            assert "fib_1" in swing
            assert "fib_2" in swing
            # Check direction is valid
            assert swing["direction"] in ["bull", "bear"]

    def test_windowed_swings_top_n_limits_results(self, client):
        """Test that top_n parameter limits number of swings returned."""
        response = client.get("/api/swings/windowed?bar_end=300&top_n=1")
        assert response.status_code == 200
        data = response.json()
        assert data["swing_count"] <= 1

    def test_windowed_swings_fib_levels_calculated_correctly(self, client):
        """Test that Fib levels are calculated correctly based on direction."""
        response = client.get("/api/swings/windowed?bar_end=300&top_n=5")
        assert response.status_code == 200
        data = response.json()

        for swing in data["swings"]:
            swing_range = swing["high_price"] - swing["low_price"]
            if swing["direction"] == "bull":
                # Bull: low is pivot (fib_0), high is origin (fib_1)
                assert abs(swing["fib_0"] - swing["low_price"]) < 0.01
                assert abs(swing["fib_1"] - swing["high_price"]) < 0.01
            else:
                # Bear: high is pivot (fib_0), low is origin (fib_1)
                assert abs(swing["fib_0"] - swing["high_price"]) < 0.01
                assert abs(swing["fib_1"] - swing["low_price"]) < 0.01


class TestDiscretizationScaleAssignment:
    """Tests for swing scale assignment during discretization."""

    def test_discretization_run_succeeds(self, client):
        """Test that discretization runs without error."""
        response = client.post("/api/discretization/run")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_discretization_swings_have_unique_scales(self, client):
        """Test that each swing appears at exactly one scale (no duplicates across scales)."""
        # Run discretization
        client.post("/api/discretization/run")

        # Get all swings
        response = client.get("/api/discretization/swings")
        assert response.status_code == 200
        swings = response.json()

        # Track swings by their (high_bar, low_bar, direction) signature
        # Each unique swing should only appear once
        seen_signatures = {}
        for swing in swings:
            # Create a unique signature for this swing
            signature = (
                swing["anchor0_bar"],
                swing["anchor1_bar"],
                swing["direction"],
            )
            if signature in seen_signatures:
                # This swing already appeared at another scale - fail!
                existing_scale = seen_signatures[signature]
                pytest.fail(
                    f"Swing at bars ({swing['anchor0_bar']}, {swing['anchor1_bar']}) "
                    f"appears at both {existing_scale} and {swing['scale']} scales"
                )
            seen_signatures[signature] = swing["scale"]

    def test_discretization_scale_thresholds_respected(self, client):
        """Test that swings are assigned to scales based on size thresholds."""
        # Run discretization
        client.post("/api/discretization/run")

        # Get all swings
        response = client.get("/api/discretization/swings")
        assert response.status_code == 200
        swings = response.json()

        # Scale thresholds (from _run_discretization)
        thresholds = {
            "XL": 100,
            "L": 40,
            "M": 15,
            "S": 0,
        }

        for swing in swings:
            scale = swing["scale"]
            size = abs(swing["anchor1"] - swing["anchor0"])  # Approximate size

            # Check swing is at the correct scale based on its size
            if scale == "XL":
                assert size >= thresholds["XL"], f"XL swing has size {size} < 100"
            elif scale == "L":
                assert size >= thresholds["L"], f"L swing has size {size} < 40"
                assert size < thresholds["XL"], f"L swing has size {size} >= 100 (should be XL)"
            elif scale == "M":
                assert size >= thresholds["M"], f"M swing has size {size} < 15"
                assert size < thresholds["L"], f"M swing has size {size} >= 40 (should be L)"
            elif scale == "S":
                assert size >= thresholds["S"], f"S swing has size {size} < 0"
                assert size < thresholds["M"], f"S swing has size {size} >= 15 (should be M)"


class TestCalibrationEndpoint:
    """Tests for the calibration endpoint (Replay View v2)."""

    def test_calibrate_returns_response(self, client):
        """Test that calibration returns a valid response."""
        response = client.get("/api/replay/calibrate")
        assert response.status_code == 200
        data = response.json()

        # Check required top-level fields
        assert "calibration_bar_count" in data
        assert "current_price" in data
        assert "swings_by_scale" in data
        assert "active_swings_by_scale" in data
        assert "scale_thresholds" in data
        assert "stats_by_scale" in data

    def test_calibrate_with_bar_count_param(self, client):
        """Test that bar_count parameter is respected."""
        response = client.get("/api/replay/calibrate?bar_count=100")
        assert response.status_code == 200
        data = response.json()

        # Bar count should be at most 100
        assert data["calibration_bar_count"] <= 100

    def test_calibrate_swings_by_scale_structure(self, client):
        """Test that swings_by_scale has correct structure."""
        response = client.get("/api/replay/calibrate")
        assert response.status_code == 200
        data = response.json()

        # All scales should be present
        for scale in ["XL", "L", "M", "S"]:
            assert scale in data["swings_by_scale"]
            assert scale in data["active_swings_by_scale"]
            assert scale in data["stats_by_scale"]
            assert scale in data["scale_thresholds"]

    def test_calibrate_swing_has_required_fields(self, client):
        """Test that detected swings have all required fields."""
        response = client.get("/api/replay/calibrate")
        assert response.status_code == 200
        data = response.json()

        # Find any swing to check structure
        for scale in ["XL", "L", "M", "S"]:
            swings = data["swings_by_scale"][scale]
            if swings:
                swing = swings[0]
                assert "id" in swing
                assert "scale" in swing
                assert "direction" in swing
                assert "high_price" in swing
                assert "high_bar_index" in swing
                assert "low_price" in swing
                assert "low_bar_index" in swing
                assert "size" in swing
                assert "rank" in swing
                assert "is_active" in swing
                assert "fib_0" in swing
                assert "fib_0382" in swing
                assert "fib_1" in swing
                assert "fib_2" in swing
                return  # Only need to check one swing

    def test_calibrate_stats_structure(self, client):
        """Test that stats_by_scale has correct structure."""
        response = client.get("/api/replay/calibrate")
        assert response.status_code == 200
        data = response.json()

        for scale in ["XL", "L", "M", "S"]:
            stats = data["stats_by_scale"][scale]
            assert "total_swings" in stats
            assert "active_swings" in stats
            # Active swings should be <= total swings
            assert stats["active_swings"] <= stats["total_swings"]

    def test_calibrate_active_swings_have_is_active_true(self, client):
        """Test that all swings in active_swings_by_scale have is_active=True."""
        response = client.get("/api/replay/calibrate")
        assert response.status_code == 200
        data = response.json()

        for scale in ["XL", "L", "M", "S"]:
            for swing in data["active_swings_by_scale"][scale]:
                assert swing["is_active"] is True

    def test_calibrate_scale_thresholds(self, client):
        """Test that scale thresholds are correct."""
        response = client.get("/api/replay/calibrate")
        assert response.status_code == 200
        data = response.json()

        thresholds = data["scale_thresholds"]
        assert thresholds["XL"] == 100.0
        assert thresholds["L"] == 40.0
        assert thresholds["M"] == 15.0
        assert thresholds["S"] == 0.0


# ============================================================================
# Replay Advance Endpoint Tests
# ============================================================================


class TestReplayAdvanceEndpoint:
    """Tests for POST /api/replay/advance endpoint."""

    def test_advance_returns_new_bars(self, client):
        """Test that advance endpoint returns new bars."""
        # First run calibration to set up state
        cal_response = client.get("/api/replay/calibrate?bar_count=100")
        assert cal_response.status_code == 200
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]

        # Advance by 1 bar
        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": calibration_bar_count - 1,
            "advance_by": 1
        })

        assert response.status_code == 200
        data = response.json()

        assert "new_bars" in data
        assert "events" in data
        assert "swing_state" in data
        assert "current_bar_index" in data
        assert "current_price" in data
        assert "end_of_data" in data

    def test_advance_new_bar_has_required_fields(self, client):
        """Test that new bars have all required fields."""
        cal_response = client.get("/api/replay/calibrate?bar_count=100")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]

        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": calibration_bar_count - 1,
            "advance_by": 1
        })

        data = response.json()

        if len(data["new_bars"]) > 0:
            bar = data["new_bars"][0]
            assert "index" in bar
            assert "timestamp" in bar
            assert "open" in bar
            assert "high" in bar
            assert "low" in bar
            assert "close" in bar

    def test_advance_increments_position(self, client):
        """Test that advance increments current_bar_index correctly."""
        cal_response = client.get("/api/replay/calibrate?bar_count=100")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]
        start_index = calibration_bar_count - 1

        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": start_index,
            "advance_by": 1
        })

        data = response.json()

        # If not end of data, should have advanced by 1
        if not data["end_of_data"]:
            assert data["current_bar_index"] == start_index + 1

    def test_advance_multiple_bars(self, client):
        """Test advancing by multiple bars at once."""
        cal_response = client.get("/api/replay/calibrate?bar_count=100")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]
        start_index = calibration_bar_count - 1

        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": start_index,
            "advance_by": 5
        })

        data = response.json()

        # Should have up to 5 new bars
        if not data["end_of_data"]:
            assert len(data["new_bars"]) <= 5
            assert data["current_bar_index"] == start_index + len(data["new_bars"])

    def test_advance_swing_state_structure(self, client):
        """Test that swing_state has correct structure."""
        cal_response = client.get("/api/replay/calibrate?bar_count=100")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]

        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": calibration_bar_count - 1,
            "advance_by": 1
        })

        data = response.json()
        swing_state = data["swing_state"]

        # Should have all four scales
        assert "XL" in swing_state
        assert "L" in swing_state
        assert "M" in swing_state
        assert "S" in swing_state

    def test_advance_event_structure(self, client):
        """Test that events have correct structure when present."""
        cal_response = client.get("/api/replay/calibrate?bar_count=50")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]

        # Advance by many bars to hopefully trigger some events
        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": calibration_bar_count - 1,
            "advance_by": 100
        })

        data = response.json()

        for event in data["events"]:
            assert "type" in event
            assert "bar_index" in event
            assert "scale" in event
            assert "direction" in event
            assert "swing_id" in event
            # Type should be one of the valid event types
            assert event["type"] in ["SWING_FORMED", "SWING_INVALIDATED", "SWING_COMPLETED", "LEVEL_CROSS"]

    def test_advance_validation_calibration_bar_count(self, client):
        """Test validation for calibration_bar_count."""
        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": 5,  # Less than 10
            "current_bar_index": 10,
            "advance_by": 1
        })

        assert response.status_code == 400
        assert "calibration_bar_count must be >= 10" in response.json()["detail"]

    def test_advance_validation_current_bar_index(self, client):
        """Test validation for current_bar_index."""
        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": 100,
            "current_bar_index": 50,  # Less than calibration_bar_count - 1
            "advance_by": 1
        })

        assert response.status_code == 400
        assert "current_bar_index must be >= calibration_bar_count - 1" in response.json()["detail"]

    def test_advance_end_of_data(self, client):
        """Test that end_of_data is True when reaching end."""
        # Get total bar count
        session = client.get("/api/session").json()
        total_bars = session["window_size"]

        # Run calibration with smaller bar count
        cal_response = client.get("/api/replay/calibrate?bar_count=50")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]

        # Try to advance beyond total bars
        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": total_bars - 1,
            "advance_by": 1
        })

        data = response.json()
        assert data["end_of_data"] is True
        assert len(data["new_bars"]) == 0

    def test_advance_returns_current_price(self, client):
        """Test that current_price is returned correctly."""
        cal_response = client.get("/api/replay/calibrate?bar_count=100")
        cal_data = cal_response.json()
        calibration_bar_count = cal_data["calibration_bar_count"]

        response = client.post("/api/replay/advance", json={
            "calibration_bar_count": calibration_bar_count,
            "current_bar_index": calibration_bar_count - 1,
            "advance_by": 1
        })

        data = response.json()

        # Current price should be a positive number
        assert data["current_price"] > 0

        # If we have new bars, current price should match the last bar's close
        if len(data["new_bars"]) > 0:
            last_bar = data["new_bars"][-1]
            assert data["current_price"] == last_bar["close"]
