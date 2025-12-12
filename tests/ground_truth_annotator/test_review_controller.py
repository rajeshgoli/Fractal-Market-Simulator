"""
Tests for ReviewController

Tests FP sampling, phase management, and feedback handling.
"""

import tempfile
from decimal import Decimal

import pytest

from src.ground_truth_annotator.models import (
    SwingAnnotation, AnnotationSession, SwingFeedback, ReviewSession
)
from src.ground_truth_annotator.storage import AnnotationStorage, ReviewStorage
from src.ground_truth_annotator.comparison_analyzer import ComparisonResult, DetectedSwing
from src.ground_truth_annotator.review_controller import ReviewController


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def storage_dir():
    """Create a temporary directory for storage testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def annotation_storage(storage_dir):
    """Create an AnnotationStorage instance with temp directory."""
    return AnnotationStorage(storage_dir)


@pytest.fixture
def review_storage(storage_dir):
    """Create a ReviewStorage instance with temp directory."""
    return ReviewStorage(storage_dir)


@pytest.fixture
def sample_annotation():
    """Create a sample annotation for testing."""
    return SwingAnnotation.create(
        scale="M",
        direction="bull",
        start_bar_index=10,
        end_bar_index=25,
        start_source_index=100,
        end_source_index=250,
        start_price=Decimal("4500.25"),
        end_price=Decimal("4550.75"),
        window_id="window-1"
    )


@pytest.fixture
def sample_detected_swing():
    """Create a sample detected swing for testing."""
    return DetectedSwing(
        direction="bull",
        start_index=100,
        end_index=250,
        high_price=4550.75,
        low_price=4500.25,
        size=50.50,
        rank=1
    )


def make_detected_swing(direction: str, start: int, end: int, rank: int = 1) -> DetectedSwing:
    """Helper to create detected swings."""
    return DetectedSwing(
        direction=direction,
        start_index=start,
        end_index=end,
        high_price=4550.0 + rank * 10,
        low_price=4500.0 + rank * 10,
        size=50.0 + rank,
        rank=rank
    )


def make_annotation(scale: str, direction: str, start: int, end: int) -> SwingAnnotation:
    """Helper to create annotations."""
    return SwingAnnotation.create(
        scale=scale,
        direction=direction,
        start_bar_index=start // 10,
        end_bar_index=end // 10,
        start_source_index=start,
        end_source_index=end,
        start_price=Decimal("4500.00"),
        end_price=Decimal("4550.00"),
        window_id="window-1"
    )


@pytest.fixture
def comparison_results_with_matches(sample_annotation, sample_detected_swing):
    """Create comparison results with matches."""
    return {
        "M": ComparisonResult(
            scale="M",
            matches=[(sample_annotation, sample_detected_swing)],
            false_negatives=[],
            false_positives=[]
        )
    }


@pytest.fixture
def comparison_results_with_all_types():
    """Create comparison results with matches, FPs, and FNs."""
    # Create annotations
    match_ann = make_annotation("M", "bull", 100, 200)
    fn_ann = make_annotation("L", "bear", 300, 400)

    # Create detected swings
    match_swing = make_detected_swing("bull", 100, 200, 1)
    fp_swing = make_detected_swing("bull", 500, 600, 2)

    return {
        "M": ComparisonResult(
            scale="M",
            matches=[(match_ann, match_swing)],
            false_negatives=[],
            false_positives=[fp_swing]
        ),
        "L": ComparisonResult(
            scale="L",
            matches=[],
            false_negatives=[fn_ann],
            false_positives=[]
        )
    }


@pytest.fixture
def comparison_results_many_fps():
    """Create comparison results with many false positives for sampling tests."""
    fps_by_scale = {
        "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(10)],
        "L": [make_detected_swing("bear", i * 100 + 1000, i * 100 + 1050, i) for i in range(15)],
        "M": [make_detected_swing("bull", i * 100 + 2000, i * 100 + 2050, i) for i in range(20)],
        "S": [make_detected_swing("bear", i * 100 + 3000, i * 100 + 3050, i) for i in range(5)],
    }

    return {
        scale: ComparisonResult(
            scale=scale,
            matches=[],
            false_negatives=[],
            false_positives=fps
        )
        for scale, fps in fps_by_scale.items()
    }


@pytest.fixture
def controller(annotation_storage, review_storage, comparison_results_with_all_types):
    """Create a ReviewController for testing."""
    session = annotation_storage.create_session("test.csv", "1m", 200)
    return ReviewController(
        session_id=session.session_id,
        annotation_storage=annotation_storage,
        review_storage=review_storage,
        comparison_results=comparison_results_with_all_types
    )


# ============================================================================
# FP Sampling Tests
# ============================================================================

class TestFPSampling:
    """Tests for false positive sampling algorithm."""

    def test_sample_all_when_under_target(self):
        """Returns all FPs if total < 20."""
        fps_by_scale = {
            "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(5)],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(3)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        assert len(sampled) == 8  # 5 + 3
        assert len(indices) == 8
        # Verify all FPs are included
        assert len([s for s, scale in sampled if scale == "XL"]) == 5
        assert len([s for s, scale in sampled if scale == "L"]) == 3

    def test_sample_exactly_at_target(self):
        """Returns all FPs when exactly at target."""
        fps_by_scale = {
            "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(10)],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(10)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        assert len(sampled) == 20

    def test_sample_stratified_by_scale(self):
        """Each scale gets proportional allocation."""
        fps_by_scale = {
            "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(10)],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(30)],
            "M": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(10)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        assert len(sampled) == 20

        # Count by scale
        xl_count = len([s for s, scale in sampled if scale == "XL"])
        l_count = len([s for s, scale in sampled if scale == "L"])
        m_count = len([s for s, scale in sampled if scale == "M"])

        # L should have more since it has more FPs
        assert l_count >= xl_count
        assert l_count >= m_count

    def test_sample_minimum_per_scale(self):
        """At least 2 per scale with FPs."""
        fps_by_scale = {
            "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(3)],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(50)],
            "M": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(3)],
            "S": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(3)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        # Count by scale
        xl_count = len([s for s, scale in sampled if scale == "XL"])
        l_count = len([s for s, scale in sampled if scale == "L"])
        m_count = len([s for s, scale in sampled if scale == "M"])
        s_count = len([s for s, scale in sampled if scale == "S"])

        # Each scale with FPs should have at least 2 (or all if less than 2)
        assert xl_count >= 2
        assert m_count >= 2
        assert s_count >= 2
        # L has 50, so should have room for at least 2
        assert l_count >= 2

    def test_sample_caps_at_target(self):
        """Never returns more than target."""
        fps_by_scale = {
            "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(100)],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(100)],
            "M": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(100)],
            "S": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(100)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        assert len(sampled) <= 20
        assert len(indices) <= 20

    def test_sample_empty_scales_handled(self):
        """Empty scales don't cause issues."""
        fps_by_scale = {
            "XL": [],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(10)],
            "M": [],
            "S": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(5)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        assert len(sampled) == 15  # All from L and S
        # No XL or M in samples
        assert len([s for s, scale in sampled if scale == "XL"]) == 0
        assert len([s for s, scale in sampled if scale == "M"]) == 0

    def test_sample_indices_are_valid(self):
        """Returned indices correctly reference original FPs."""
        fps_by_scale = {
            "XL": [make_detected_swing("bull", i * 100, i * 100 + 50, i) for i in range(5)],
            "L": [make_detected_swing("bear", i * 100, i * 100 + 50, i) for i in range(5)],
        }

        sampled, indices = ReviewController.sample_false_positives(fps_by_scale, target=20)

        # Build flat list for verification
        all_fps = []
        for scale in ["XL", "L", "M", "S"]:
            all_fps.extend(fps_by_scale.get(scale, []))

        # Verify indices point to valid FPs
        for idx in indices:
            assert 0 <= idx < len(all_fps)


# ============================================================================
# Phase Management Tests
# ============================================================================

class TestPhaseManagement:
    """Tests for review phase transitions."""

    def test_initial_phase_is_matches(self, controller):
        """Starts at matches phase."""
        assert controller.get_current_phase() == "matches"

    def test_advance_phase_order(self, controller):
        """Phase advances in correct order: matches → fp_sample → fn_feedback → complete."""
        phases_seen = [controller.get_current_phase()]

        while controller.advance_phase():
            phases_seen.append(controller.get_current_phase())

        assert phases_seen == ["matches", "fp_sample", "fn_feedback", "complete"]

    def test_cannot_advance_past_complete(self, controller):
        """Returns False when already complete."""
        # Advance to complete
        while controller.get_current_phase() != "complete":
            controller.advance_phase()

        result = controller.advance_phase()

        assert result is False
        assert controller.get_current_phase() == "complete"

    def test_is_complete(self, controller):
        """is_complete() returns True only when phase is complete."""
        assert not controller.is_complete()

        # Advance through all phases
        while controller.advance_phase():
            pass

        assert controller.is_complete()

    def test_phase_persists_across_controller_instances(
        self,
        annotation_storage,
        review_storage,
        comparison_results_with_all_types
    ):
        """Phase is persisted and loaded correctly."""
        session = annotation_storage.create_session("test.csv", "1m", 200)

        # Create first controller and advance phase
        controller1 = ReviewController(
            session_id=session.session_id,
            annotation_storage=annotation_storage,
            review_storage=review_storage,
            comparison_results=comparison_results_with_all_types
        )
        controller1.get_or_create_review()
        controller1.advance_phase()

        assert controller1.get_current_phase() == "fp_sample"

        # Create second controller for same session
        controller2 = ReviewController(
            session_id=session.session_id,
            annotation_storage=annotation_storage,
            review_storage=review_storage,
            comparison_results=comparison_results_with_all_types
        )

        # Should load existing review with advanced phase
        assert controller2.get_current_phase() == "fp_sample"


# ============================================================================
# Feedback Tests
# ============================================================================

class TestFeedback:
    """Tests for feedback submission."""

    def test_submit_match_feedback(self, controller):
        """Feedback stored in correct list for matches."""
        matches = controller.get_matches()
        assert len(matches) >= 1

        annotation_id = matches[0]["annotation"]["annotation_id"]

        feedback = controller.submit_feedback(
            swing_type="match",
            swing_reference={"annotation_id": annotation_id},
            verdict="correct",
            comment="Good detection"
        )

        assert feedback.swing_type == "match"
        assert feedback.verdict == "correct"

        # Verify it's in the review session
        review = controller.get_or_create_review()
        assert len(review.match_feedback) == 1
        assert review.match_feedback[0].feedback_id == feedback.feedback_id

    def test_submit_fp_feedback(self, controller):
        """Feedback stored with correct reference for FPs."""
        controller.advance_phase()  # Move to fp_sample phase

        fp_list = controller.get_fp_sample()
        if not fp_list:
            pytest.skip("No FPs in test data")

        feedback = controller.submit_feedback(
            swing_type="false_positive",
            swing_reference={"sample_index": 0},
            verdict="noise",
            comment="Too small",
            category="too_small"
        )

        assert feedback.swing_type == "false_positive"
        assert feedback.verdict == "noise"

        review = controller.get_or_create_review()
        assert len(review.fp_feedback) == 1

    def test_fn_requires_comment(self, controller):
        """Raises ValueError if FN submitted without comment."""
        fn_list = controller.get_false_negatives()
        if not fn_list:
            pytest.skip("No FNs in test data")

        annotation_id = fn_list[0]["annotation"]["annotation_id"]

        with pytest.raises(ValueError, match="requires a comment"):
            controller.submit_feedback(
                swing_type="false_negative",
                swing_reference={"annotation_id": annotation_id},
                verdict="valid_missed",
                comment=None  # Missing required comment
            )

    def test_fn_with_comment_succeeds(self, controller):
        """FN feedback with comment is accepted."""
        fn_list = controller.get_false_negatives()
        if not fn_list:
            pytest.skip("No FNs in test data")

        annotation_id = fn_list[0]["annotation"]["annotation_id"]

        feedback = controller.submit_feedback(
            swing_type="false_negative",
            swing_reference={"annotation_id": annotation_id},
            verdict="valid_missed",
            comment="Detector needs adjustment for this pattern"
        )

        assert feedback.swing_type == "false_negative"
        assert feedback.comment is not None

    def test_get_summary_counts(self, controller):
        """Summary reflects actual feedback counts."""
        # Submit some feedback
        matches = controller.get_matches()
        if matches:
            controller.submit_feedback(
                swing_type="match",
                swing_reference={"annotation_id": matches[0]["annotation"]["annotation_id"]},
                verdict="correct"
            )

        summary = controller.get_summary()

        assert "session_id" in summary
        assert "review_id" in summary
        assert "phase" in summary
        assert summary["matches"]["reviewed"] == 1
        assert summary["matches"]["correct"] == 1

    def test_feedback_persists_across_instances(
        self,
        annotation_storage,
        review_storage,
        comparison_results_with_all_types
    ):
        """Feedback persists when controller is recreated."""
        session = annotation_storage.create_session("test.csv", "1m", 200)

        # Submit feedback with first controller
        controller1 = ReviewController(
            session_id=session.session_id,
            annotation_storage=annotation_storage,
            review_storage=review_storage,
            comparison_results=comparison_results_with_all_types
        )

        matches = controller1.get_matches()
        if matches:
            controller1.submit_feedback(
                swing_type="match",
                swing_reference={"annotation_id": matches[0]["annotation"]["annotation_id"]},
                verdict="correct"
            )

        # Verify with second controller
        controller2 = ReviewController(
            session_id=session.session_id,
            annotation_storage=annotation_storage,
            review_storage=review_storage,
            comparison_results=comparison_results_with_all_types
        )

        review = controller2.get_or_create_review()
        assert len(review.match_feedback) == 1


# ============================================================================
# Phase Progress Tests
# ============================================================================

class TestPhaseProgress:
    """Tests for phase progress tracking."""

    def test_get_phase_progress_matches(self, controller):
        """Progress tracking for matches phase."""
        completed, total = controller.get_phase_progress()

        assert completed == 0
        assert total >= 0  # May have matches or not

    def test_get_phase_progress_updates_on_feedback(self, controller):
        """Progress updates when feedback is submitted."""
        matches = controller.get_matches()
        if not matches:
            pytest.skip("No matches in test data")

        initial_completed, total = controller.get_phase_progress()
        assert initial_completed == 0

        controller.submit_feedback(
            swing_type="match",
            swing_reference={"annotation_id": matches[0]["annotation"]["annotation_id"]},
            verdict="correct"
        )

        completed, _ = controller.get_phase_progress()
        assert completed == 1

    def test_get_phase_progress_complete_phase(self, controller):
        """Progress for complete phase returns (0, 0)."""
        while controller.advance_phase():
            pass

        completed, total = controller.get_phase_progress()
        assert completed == 0
        assert total == 0


# ============================================================================
# Get Methods Tests
# ============================================================================

class TestGetMethods:
    """Tests for data retrieval methods."""

    def test_get_matches_structure(self, controller):
        """get_matches returns correct structure."""
        matches = controller.get_matches()

        if matches:
            match = matches[0]
            assert "annotation" in match
            assert "system_swing" in match
            assert "scale" in match
            assert "feedback" in match

            assert "annotation_id" in match["annotation"]
            assert "direction" in match["system_swing"]
            assert "start_index" in match["system_swing"]

    def test_get_fp_sample_structure(self, controller):
        """get_fp_sample returns correct structure."""
        fp_sample = controller.get_fp_sample()

        if fp_sample:
            fp = fp_sample[0]
            assert "system_swing" in fp
            assert "scale" in fp
            assert "sample_index" in fp
            assert "feedback" in fp

    def test_get_false_negatives_structure(self, controller):
        """get_false_negatives returns correct structure."""
        fn_list = controller.get_false_negatives()

        if fn_list:
            fn = fn_list[0]
            assert "annotation" in fn
            assert "scale" in fn
            assert "feedback" in fn

    def test_get_matches_includes_feedback(self, controller):
        """get_matches includes feedback when present."""
        matches = controller.get_matches()
        if not matches:
            pytest.skip("No matches in test data")

        # Initially no feedback
        assert matches[0]["feedback"] is None

        # Submit feedback
        controller.submit_feedback(
            swing_type="match",
            swing_reference={"annotation_id": matches[0]["annotation"]["annotation_id"]},
            verdict="correct"
        )

        # Now should include feedback
        matches = controller.get_matches()
        assert matches[0]["feedback"] is not None
        assert matches[0]["feedback"]["verdict"] == "correct"


# ============================================================================
# Summary Tests
# ============================================================================

class TestSummary:
    """Tests for review summary generation."""

    def test_summary_structure(self, controller):
        """Summary has correct structure."""
        summary = controller.get_summary()

        assert "session_id" in summary
        assert "review_id" in summary
        assert "phase" in summary
        assert "matches" in summary
        assert "false_positives" in summary
        assert "false_negatives" in summary
        assert "started_at" in summary
        assert "completed_at" in summary

        # Match details
        assert "total" in summary["matches"]
        assert "reviewed" in summary["matches"]
        assert "correct" in summary["matches"]
        assert "incorrect" in summary["matches"]

        # FP details
        assert "sampled" in summary["false_positives"]
        assert "reviewed" in summary["false_positives"]
        assert "noise" in summary["false_positives"]
        assert "valid" in summary["false_positives"]

        # FN details
        assert "total" in summary["false_negatives"]
        assert "explained" in summary["false_negatives"]

    def test_summary_completed_at_when_complete(self, controller):
        """completed_at is set when review is complete."""
        summary = controller.get_summary()
        assert summary["completed_at"] is None

        # Complete review
        while controller.advance_phase():
            pass

        summary = controller.get_summary()
        assert summary["completed_at"] is not None


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for full review workflow."""

    def test_full_review_workflow(
        self,
        annotation_storage,
        review_storage,
        comparison_results_with_all_types
    ):
        """Test complete review workflow from start to finish."""
        session = annotation_storage.create_session("test.csv", "1m", 200)

        controller = ReviewController(
            session_id=session.session_id,
            annotation_storage=annotation_storage,
            review_storage=review_storage,
            comparison_results=comparison_results_with_all_types
        )

        # Phase 1: Review matches
        assert controller.get_current_phase() == "matches"
        matches = controller.get_matches()
        for match in matches:
            controller.submit_feedback(
                swing_type="match",
                swing_reference={"annotation_id": match["annotation"]["annotation_id"]},
                verdict="correct"
            )

        controller.advance_phase()

        # Phase 2: Review FP sample
        assert controller.get_current_phase() == "fp_sample"
        fp_sample = controller.get_fp_sample()
        for idx, fp in enumerate(fp_sample):
            controller.submit_feedback(
                swing_type="false_positive",
                swing_reference={"sample_index": idx},
                verdict="noise"
            )

        controller.advance_phase()

        # Phase 3: Review FNs
        assert controller.get_current_phase() == "fn_feedback"
        fn_list = controller.get_false_negatives()
        for fn in fn_list:
            controller.submit_feedback(
                swing_type="false_negative",
                swing_reference={"annotation_id": fn["annotation"]["annotation_id"]},
                verdict="valid_missed",
                comment="Pattern needs tuning"
            )

        controller.advance_phase()

        # Complete
        assert controller.get_current_phase() == "complete"
        assert controller.is_complete()

        # Verify summary
        summary = controller.get_summary()
        assert summary["phase"] == "complete"
        assert summary["completed_at"] is not None
