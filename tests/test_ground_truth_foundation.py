"""
Tests for Ground Truth Annotator Foundation

Tests the BarAggregator.aggregate_to_target_bars() method and
the ground_truth_annotator module (models and storage).
"""

import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.swing_analysis.bar_aggregator import BarAggregator
from src.swing_analysis.bull_reference_detector import Bar
from src.ground_truth_annotator.models import (
    SwingAnnotation, AnnotationSession, SwingFeedback, ReviewSession, REVIEW_PHASES
)
from src.ground_truth_annotator.storage import AnnotationStorage, ReviewStorage
from src.ground_truth_annotator.main import parse_offset


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_bars():
    """Create sample bars for aggregation testing."""
    bars = []
    base_timestamp = 1700000000  # Fixed timestamp for reproducibility
    for i in range(1000):
        bars.append(Bar(
            index=i,
            timestamp=base_timestamp + i * 60,  # 1-minute bars
            open=100.0 + i * 0.1,
            high=100.5 + i * 0.1,
            low=99.5 + i * 0.1,
            close=100.25 + i * 0.1
        ))
    return bars


@pytest.fixture
def large_bar_set():
    """Create 50K bars for large dataset aggregation testing."""
    bars = []
    base_timestamp = 1700000000
    for i in range(50000):
        bars.append(Bar(
            index=i,
            timestamp=base_timestamp + i * 60,
            open=4500.0 + (i % 100) * 0.25,
            high=4505.0 + (i % 100) * 0.25,
            low=4495.0 + (i % 100) * 0.25,
            close=4502.0 + (i % 100) * 0.25
        ))
    return bars


@pytest.fixture
def storage_dir():
    """Create a temporary directory for storage testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def storage(storage_dir):
    """Create an AnnotationStorage instance with temp directory."""
    return AnnotationStorage(storage_dir)


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


# ============================================================================
# aggregate_to_target_bars() Tests
# ============================================================================

class TestAggregateToTargetBars:
    """Tests for BarAggregator.aggregate_to_target_bars()"""

    def test_returns_original_when_fewer_than_target(self, sample_bars):
        """Should return all source bars when count <= target."""
        aggregator = BarAggregator(sample_bars[:100])
        result = aggregator.aggregate_to_target_bars(200)

        assert len(result) == 100
        assert result[0].open == sample_bars[0].open
        assert result[-1].close == sample_bars[99].close

    def test_returns_original_when_equal_to_target(self, sample_bars):
        """Should return all source bars when count == target."""
        aggregator = BarAggregator(sample_bars[:100])
        result = aggregator.aggregate_to_target_bars(100)

        assert len(result) == 100

    def test_aggregation_1000_to_50(self, sample_bars):
        """Test 20:1 compression ratio (1000 bars to ~50)."""
        aggregator = BarAggregator(sample_bars)
        result = aggregator.aggregate_to_target_bars(50)

        # Should be approximately 50 bars (1000 / 20 = 50)
        assert len(result) == 50  # Exactly 50 with 20 bars each

    def test_aggregation_1000_to_200(self, sample_bars):
        """Test 5:1 compression ratio (1000 bars to ~200)."""
        aggregator = BarAggregator(sample_bars)
        result = aggregator.aggregate_to_target_bars(200)

        # Should be approximately 200 bars
        assert 195 <= len(result) <= 205

    def test_aggregation_1000_to_800(self, sample_bars):
        """Test light compression (1000 bars to ~800)."""
        aggregator = BarAggregator(sample_bars)
        result = aggregator.aggregate_to_target_bars(800)

        # With 1000/800 = 1.25, we get groups of 1, resulting in 1000 bars
        # Actually 1000 // 800 = 1, so every bar is its own group
        assert len(result) == 1000

    def test_aggregation_50k_to_50(self, large_bar_set):
        """Test 1000:1 compression (50K bars to ~50)."""
        aggregator = BarAggregator(large_bar_set)
        result = aggregator.aggregate_to_target_bars(50)

        assert len(result) == 50

    def test_aggregation_50k_to_200(self, large_bar_set):
        """Test 250:1 compression (50K bars to ~200)."""
        aggregator = BarAggregator(large_bar_set)
        result = aggregator.aggregate_to_target_bars(200)

        assert len(result) == 200

    def test_aggregation_50k_to_800(self, large_bar_set):
        """Test ~62:1 compression (50K bars to ~800)."""
        aggregator = BarAggregator(large_bar_set)
        result = aggregator.aggregate_to_target_bars(800)

        # 50000 // 800 = 62 bars per candle
        # 50000 / 62 = 806 output bars
        assert 795 <= len(result) <= 810

    def test_ohlc_aggregation_rules(self, sample_bars):
        """Verify OHLC aggregation follows standard rules."""
        aggregator = BarAggregator(sample_bars[:100])
        result = aggregator.aggregate_to_target_bars(10)

        # First aggregated bar should combine bars 0-9
        first_agg = result[0]
        first_group = sample_bars[:10]

        assert first_agg.open == first_group[0].open  # First bar's open
        assert first_agg.close == first_group[-1].close  # Last bar's close
        assert first_agg.high == max(b.high for b in first_group)
        assert first_agg.low == min(b.low for b in first_group)

    def test_aggregated_bars_have_correct_indices(self, sample_bars):
        """Verify aggregated bars have sequential indices."""
        aggregator = BarAggregator(sample_bars)
        result = aggregator.aggregate_to_target_bars(100)

        for i, bar in enumerate(result):
            assert bar.index == i

    def test_invalid_target_count(self, sample_bars):
        """Should raise ValueError for invalid target counts."""
        aggregator = BarAggregator(sample_bars)

        with pytest.raises(ValueError):
            aggregator.aggregate_to_target_bars(0)

        with pytest.raises(ValueError):
            aggregator.aggregate_to_target_bars(-10)


# ============================================================================
# SwingAnnotation Model Tests
# ============================================================================

class TestSwingAnnotation:
    """Tests for SwingAnnotation dataclass."""

    def test_create_annotation(self, sample_annotation):
        """Test annotation creation with factory method."""
        assert sample_annotation.scale == "M"
        assert sample_annotation.direction == "bull"
        assert sample_annotation.start_bar_index == 10
        assert sample_annotation.end_bar_index == 25
        assert sample_annotation.start_price == Decimal("4500.25")
        assert sample_annotation.end_price == Decimal("4550.75")
        assert sample_annotation.annotation_id  # UUID generated
        assert sample_annotation.created_at  # Timestamp generated

    def test_to_dict_serialization(self, sample_annotation):
        """Test serialization to dictionary."""
        data = sample_annotation.to_dict()

        assert data['scale'] == "M"
        assert data['direction'] == "bull"
        assert data['start_price'] == "4500.25"
        assert data['end_price'] == "4550.75"
        assert 'annotation_id' in data
        assert 'created_at' in data

    def test_from_dict_deserialization(self, sample_annotation):
        """Test deserialization from dictionary."""
        data = sample_annotation.to_dict()
        restored = SwingAnnotation.from_dict(data)

        assert restored.scale == sample_annotation.scale
        assert restored.direction == sample_annotation.direction
        assert restored.start_bar_index == sample_annotation.start_bar_index
        assert restored.end_bar_index == sample_annotation.end_bar_index
        assert restored.start_price == sample_annotation.start_price
        assert restored.end_price == sample_annotation.end_price
        assert restored.annotation_id == sample_annotation.annotation_id

    def test_roundtrip_serialization(self, sample_annotation):
        """Test that to_dict -> from_dict preserves all fields."""
        data = sample_annotation.to_dict()
        restored = SwingAnnotation.from_dict(data)

        assert restored.annotation_id == sample_annotation.annotation_id
        assert restored.scale == sample_annotation.scale
        assert restored.direction == sample_annotation.direction
        assert restored.start_source_index == sample_annotation.start_source_index
        assert restored.end_source_index == sample_annotation.end_source_index


# ============================================================================
# AnnotationSession Model Tests
# ============================================================================

class TestAnnotationSession:
    """Tests for AnnotationSession dataclass."""

    def test_create_session(self):
        """Test session creation with factory method."""
        session = AnnotationSession.create(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200
        )

        assert session.data_file == "test_data.csv"
        assert session.resolution == "1m"
        assert session.window_size == 200
        assert session.session_id  # UUID generated
        assert session.created_at  # Timestamp generated
        assert session.annotations == []
        assert session.completed_scales == []

    def test_add_annotation(self, sample_annotation):
        """Test adding annotation to session."""
        session = AnnotationSession.create("test.csv", "1m", 200)
        session.add_annotation(sample_annotation)

        assert len(session.annotations) == 1
        assert session.annotations[0] == sample_annotation

    def test_remove_annotation(self, sample_annotation):
        """Test removing annotation from session."""
        session = AnnotationSession.create("test.csv", "1m", 200)
        session.add_annotation(sample_annotation)

        result = session.remove_annotation(sample_annotation.annotation_id)

        assert result is True
        assert len(session.annotations) == 0

    def test_remove_nonexistent_annotation(self):
        """Test removing annotation that doesn't exist."""
        session = AnnotationSession.create("test.csv", "1m", 200)
        result = session.remove_annotation("nonexistent-id")

        assert result is False

    def test_get_annotations_by_scale(self, sample_annotation):
        """Test filtering annotations by scale."""
        session = AnnotationSession.create("test.csv", "1m", 200)
        session.add_annotation(sample_annotation)

        # Add another annotation with different scale
        ann2 = SwingAnnotation.create(
            scale="L",
            direction="bear",
            start_bar_index=30,
            end_bar_index=45,
            start_source_index=300,
            end_source_index=450,
            start_price=Decimal("4550.00"),
            end_price=Decimal("4520.00"),
            window_id="window-1"
        )
        session.add_annotation(ann2)

        m_annotations = session.get_annotations_by_scale("M")
        l_annotations = session.get_annotations_by_scale("L")
        s_annotations = session.get_annotations_by_scale("S")

        assert len(m_annotations) == 1
        assert len(l_annotations) == 1
        assert len(s_annotations) == 0

    def test_mark_scale_complete(self):
        """Test marking scales as complete."""
        session = AnnotationSession.create("test.csv", "1m", 200)

        assert not session.is_scale_complete("M")
        session.mark_scale_complete("M")
        assert session.is_scale_complete("M")

        # Should not duplicate
        session.mark_scale_complete("M")
        assert session.completed_scales.count("M") == 1

    def test_session_serialization(self, sample_annotation):
        """Test session serialization to dictionary."""
        session = AnnotationSession.create("test.csv", "1m", 200)
        session.add_annotation(sample_annotation)
        session.mark_scale_complete("M")

        data = session.to_dict()

        assert data['data_file'] == "test.csv"
        assert data['resolution'] == "1m"
        assert data['window_size'] == 200
        assert len(data['annotations']) == 1
        assert "M" in data['completed_scales']

    def test_session_deserialization(self, sample_annotation):
        """Test session deserialization from dictionary."""
        session = AnnotationSession.create("test.csv", "1m", 200)
        session.add_annotation(sample_annotation)
        session.mark_scale_complete("M")

        data = session.to_dict()
        restored = AnnotationSession.from_dict(data)

        assert restored.session_id == session.session_id
        assert restored.data_file == session.data_file
        assert len(restored.annotations) == 1
        assert restored.is_scale_complete("M")


# ============================================================================
# AnnotationStorage Tests
# ============================================================================

class TestAnnotationStorage:
    """Tests for AnnotationStorage class."""

    def test_create_session(self, storage):
        """Test creating a new session through storage."""
        session = storage.create_session(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200
        )

        assert session.data_file == "test_data.csv"
        assert session.session_id

        # Verify persisted
        loaded = storage.get_session(session.session_id)
        assert loaded is not None
        assert loaded.data_file == "test_data.csv"

    def test_get_nonexistent_session(self, storage):
        """Test getting a session that doesn't exist."""
        result = storage.get_session("nonexistent-session-id")
        assert result is None

    def test_save_and_retrieve_annotation(self, storage, sample_annotation):
        """Test saving and retrieving annotations."""
        session = storage.create_session("test.csv", "1m", 200)

        storage.save_annotation(session.session_id, sample_annotation)

        annotations = storage.get_annotations(session.session_id)
        assert len(annotations) == 1
        assert annotations[0].scale == "M"

    def test_get_annotations_filtered_by_scale(self, storage, sample_annotation):
        """Test getting annotations filtered by scale."""
        session = storage.create_session("test.csv", "1m", 200)
        storage.save_annotation(session.session_id, sample_annotation)

        m_annotations = storage.get_annotations(session.session_id, scale="M")
        l_annotations = storage.get_annotations(session.session_id, scale="L")

        assert len(m_annotations) == 1
        assert len(l_annotations) == 0

    def test_delete_annotation(self, storage, sample_annotation):
        """Test deleting an annotation."""
        session = storage.create_session("test.csv", "1m", 200)
        storage.save_annotation(session.session_id, sample_annotation)

        result = storage.delete_annotation(
            session.session_id,
            sample_annotation.annotation_id
        )

        assert result is True
        annotations = storage.get_annotations(session.session_id)
        assert len(annotations) == 0

    def test_delete_nonexistent_annotation(self, storage):
        """Test deleting annotation that doesn't exist."""
        session = storage.create_session("test.csv", "1m", 200)

        result = storage.delete_annotation(session.session_id, "nonexistent-id")
        assert result is False

    def test_list_sessions(self, storage):
        """Test listing all sessions."""
        storage.create_session("test1.csv", "1m", 200)
        storage.create_session("test2.csv", "5m", 400)

        sessions = storage.list_sessions()

        assert len(sessions) == 2
        files = {s.data_file for s in sessions}
        assert "test1.csv" in files
        assert "test2.csv" in files

    def test_delete_session(self, storage):
        """Test deleting a session."""
        session = storage.create_session("test.csv", "1m", 200)
        session_id = session.session_id

        result = storage.delete_session(session_id)

        assert result is True
        assert storage.get_session(session_id) is None

    def test_persistence_across_restarts(self, storage_dir):
        """Test that data persists when storage is recreated."""
        # Create first storage instance and add data
        storage1 = AnnotationStorage(storage_dir)
        session = storage1.create_session("test.csv", "1m", 200)
        session_id = session.session_id

        annotation = SwingAnnotation.create(
            scale="L",
            direction="bull",
            start_bar_index=5,
            end_bar_index=20,
            start_source_index=50,
            end_source_index=200,
            start_price=Decimal("4500.00"),
            end_price=Decimal("4600.00"),
            window_id="w1"
        )
        storage1.save_annotation(session_id, annotation)

        # Create new storage instance (simulating restart)
        storage2 = AnnotationStorage(storage_dir)

        # Verify data persisted
        loaded_session = storage2.get_session(session_id)
        assert loaded_session is not None
        assert loaded_session.data_file == "test.csv"
        assert len(loaded_session.annotations) == 1

    def test_update_session_completed_scales(self, storage):
        """Test updating session to mark scales complete."""
        session = storage.create_session("test.csv", "1m", 200)
        session.mark_scale_complete("M")
        session.mark_scale_complete("L")

        storage.update_session(session)

        loaded = storage.get_session(session.session_id)
        assert loaded.is_scale_complete("M")
        assert loaded.is_scale_complete("L")
        assert not loaded.is_scale_complete("S")

    def test_export_json(self, storage, sample_annotation):
        """Test exporting session as JSON."""
        session = storage.create_session("test.csv", "1m", 200)
        storage.save_annotation(session.session_id, sample_annotation)

        exported = storage.export_session(session.session_id, format="json")

        data = json.loads(exported)
        assert data['data_file'] == "test.csv"
        assert len(data['annotations']) == 1

    def test_export_csv(self, storage, sample_annotation):
        """Test exporting session as CSV."""
        session = storage.create_session("test.csv", "1m", 200)
        storage.save_annotation(session.session_id, sample_annotation)

        exported = storage.export_session(session.session_id, format="csv")

        lines = exported.strip().split("\n")
        assert len(lines) == 2  # Header + 1 annotation
        assert "annotation_id" in lines[0]
        assert "M,bull" in lines[1]  # scale, direction

    def test_export_invalid_format(self, storage):
        """Test exporting with invalid format raises error."""
        session = storage.create_session("test.csv", "1m", 200)

        with pytest.raises(ValueError):
            storage.export_session(session.session_id, format="xml")

    def test_save_annotation_invalid_session(self, storage, sample_annotation):
        """Test saving annotation to nonexistent session raises error."""
        with pytest.raises(ValueError):
            storage.save_annotation("nonexistent-id", sample_annotation)

    def test_get_annotations_invalid_session(self, storage):
        """Test getting annotations from nonexistent session raises error."""
        with pytest.raises(ValueError):
            storage.get_annotations("nonexistent-id")


# ============================================================================
# SwingFeedback Model Tests
# ============================================================================

@pytest.fixture
def sample_feedback():
    """Create a sample SwingFeedback for testing."""
    return SwingFeedback.create(
        swing_type="match",
        swing_reference={"annotation_id": "test-ann-123"},
        verdict="correct",
        comment="Properly detected swing",
        category=None
    )


@pytest.fixture
def sample_fp_feedback():
    """Create a sample false positive feedback for testing."""
    return SwingFeedback.create(
        swing_type="false_positive",
        swing_reference={"start_index": 100, "end_index": 150, "direction": "bull"},
        verdict="noise",
        comment="Too small to be significant",
        category="too_small"
    )


@pytest.fixture
def sample_fn_feedback():
    """Create a sample false negative feedback for testing."""
    return SwingFeedback.create(
        swing_type="false_negative",
        swing_reference={"annotation_id": "missed-ann-456"},
        verdict="valid_missed",
        comment="Clear swing that should have been detected",
        category="pattern"
    )


class TestSwingFeedback:
    """Tests for SwingFeedback dataclass."""

    def test_create_feedback(self, sample_feedback):
        """Test feedback creation with factory method."""
        assert sample_feedback.swing_type == "match"
        assert sample_feedback.swing_reference == {"annotation_id": "test-ann-123"}
        assert sample_feedback.verdict == "correct"
        assert sample_feedback.comment == "Properly detected swing"
        assert sample_feedback.category is None
        assert sample_feedback.feedback_id  # UUID generated
        assert sample_feedback.created_at  # Timestamp generated

    def test_create_feedback_with_category(self, sample_fp_feedback):
        """Test feedback creation with optional category."""
        assert sample_fp_feedback.swing_type == "false_positive"
        assert sample_fp_feedback.verdict == "noise"
        assert sample_fp_feedback.category == "too_small"

    def test_to_dict_serialization(self, sample_feedback):
        """Test serialization to dictionary."""
        data = sample_feedback.to_dict()

        assert data['swing_type'] == "match"
        assert data['verdict'] == "correct"
        assert data['swing_reference'] == {"annotation_id": "test-ann-123"}
        assert 'feedback_id' in data
        assert 'created_at' in data

    def test_from_dict_deserialization(self, sample_feedback):
        """Test deserialization from dictionary."""
        data = sample_feedback.to_dict()
        restored = SwingFeedback.from_dict(data)

        assert restored.swing_type == sample_feedback.swing_type
        assert restored.verdict == sample_feedback.verdict
        assert restored.swing_reference == sample_feedback.swing_reference
        assert restored.feedback_id == sample_feedback.feedback_id

    def test_roundtrip_serialization(self, sample_fp_feedback):
        """Test that to_dict -> from_dict preserves all fields."""
        data = sample_fp_feedback.to_dict()
        restored = SwingFeedback.from_dict(data)

        assert restored.feedback_id == sample_fp_feedback.feedback_id
        assert restored.swing_type == sample_fp_feedback.swing_type
        assert restored.verdict == sample_fp_feedback.verdict
        assert restored.comment == sample_fp_feedback.comment
        assert restored.category == sample_fp_feedback.category

    def test_optional_fields_serialization(self):
        """Test that None values for optional fields are handled correctly."""
        feedback = SwingFeedback.create(
            swing_type="match",
            swing_reference={"id": "x"},
            verdict="correct"
        )
        data = feedback.to_dict()
        restored = SwingFeedback.from_dict(data)

        assert restored.comment is None
        assert restored.category is None


# ============================================================================
# ReviewSession Model Tests
# ============================================================================

@pytest.fixture
def review_session():
    """Create a sample ReviewSession for testing."""
    return ReviewSession.create(session_id="test-session-123")


class TestReviewSession:
    """Tests for ReviewSession dataclass."""

    def test_create_session(self, review_session):
        """Test session creation with factory method."""
        assert review_session.session_id == "test-session-123"
        assert review_session.phase == "matches"
        assert review_session.match_feedback == []
        assert review_session.fp_feedback == []
        assert review_session.fn_feedback == []
        assert review_session.fp_sample_indices == []
        assert review_session.review_id  # UUID generated
        assert review_session.started_at  # Timestamp generated
        assert review_session.completed_at is None

    def test_add_match_feedback(self, review_session, sample_feedback):
        """Test adding match feedback."""
        review_session.add_feedback(sample_feedback)

        assert len(review_session.match_feedback) == 1
        assert review_session.match_feedback[0] == sample_feedback
        assert len(review_session.fp_feedback) == 0
        assert len(review_session.fn_feedback) == 0

    def test_add_fp_feedback(self, review_session, sample_fp_feedback):
        """Test adding false positive feedback."""
        review_session.add_feedback(sample_fp_feedback)

        assert len(review_session.match_feedback) == 0
        assert len(review_session.fp_feedback) == 1
        assert review_session.fp_feedback[0] == sample_fp_feedback
        assert len(review_session.fn_feedback) == 0

    def test_add_fn_feedback(self, review_session, sample_fn_feedback):
        """Test adding false negative feedback."""
        review_session.add_feedback(sample_fn_feedback)

        assert len(review_session.match_feedback) == 0
        assert len(review_session.fp_feedback) == 0
        assert len(review_session.fn_feedback) == 1
        assert review_session.fn_feedback[0] == sample_fn_feedback

    def test_add_multiple_feedback(self, review_session, sample_feedback, sample_fp_feedback, sample_fn_feedback):
        """Test adding multiple types of feedback."""
        review_session.add_feedback(sample_feedback)
        review_session.add_feedback(sample_fp_feedback)
        review_session.add_feedback(sample_fn_feedback)

        assert len(review_session.match_feedback) == 1
        assert len(review_session.fp_feedback) == 1
        assert len(review_session.fn_feedback) == 1

    def test_advance_phase_matches_to_fp(self, review_session):
        """Test advancing from matches to fp_sample phase."""
        assert review_session.phase == "matches"

        result = review_session.advance_phase()

        assert result is True
        assert review_session.phase == "fp_sample"
        assert review_session.completed_at is None

    def test_advance_phase_full_sequence(self, review_session):
        """Test advancing through all phases."""
        phases_seen = [review_session.phase]

        while review_session.advance_phase():
            phases_seen.append(review_session.phase)

        assert phases_seen == REVIEW_PHASES
        assert review_session.completed_at is not None

    def test_advance_phase_when_complete(self, review_session):
        """Test that advance_phase returns False when already complete."""
        # Advance to complete
        while review_session.phase != "complete":
            review_session.advance_phase()

        result = review_session.advance_phase()

        assert result is False
        assert review_session.phase == "complete"

    def test_to_dict_serialization(self, review_session, sample_feedback):
        """Test serialization to dictionary."""
        review_session.add_feedback(sample_feedback)
        review_session.fp_sample_indices = [0, 5, 10]

        data = review_session.to_dict()

        assert data['session_id'] == "test-session-123"
        assert data['phase'] == "matches"
        assert len(data['match_feedback']) == 1
        assert data['fp_sample_indices'] == [0, 5, 10]
        assert 'review_id' in data
        assert 'started_at' in data

    def test_from_dict_deserialization(self, review_session, sample_feedback):
        """Test deserialization from dictionary."""
        review_session.add_feedback(sample_feedback)
        review_session.advance_phase()

        data = review_session.to_dict()
        restored = ReviewSession.from_dict(data)

        assert restored.review_id == review_session.review_id
        assert restored.session_id == review_session.session_id
        assert restored.phase == "fp_sample"
        assert len(restored.match_feedback) == 1

    def test_roundtrip_with_completed_at(self, review_session):
        """Test roundtrip serialization preserves completed_at."""
        # Advance to complete
        while review_session.phase != "complete":
            review_session.advance_phase()

        data = review_session.to_dict()
        restored = ReviewSession.from_dict(data)

        assert restored.completed_at is not None
        assert restored.phase == "complete"

    def test_empty_feedback_lists_serialization(self, review_session):
        """Test serialization with empty feedback lists."""
        data = review_session.to_dict()
        restored = ReviewSession.from_dict(data)

        assert restored.match_feedback == []
        assert restored.fp_feedback == []
        assert restored.fn_feedback == []


# ============================================================================
# ReviewStorage Tests
# ============================================================================

@pytest.fixture
def review_storage(storage_dir):
    """Create a ReviewStorage instance with temp directory."""
    return ReviewStorage(storage_dir)


class TestReviewStorage:
    """Tests for ReviewStorage class."""

    def test_create_review(self, review_storage):
        """Test creating a new review session through storage."""
        review = review_storage.create_review(session_id="test-session-123")

        assert review.session_id == "test-session-123"
        assert review.review_id
        assert review.phase == "matches"

        # Verify persisted
        loaded = review_storage.get_review("test-session-123")
        assert loaded is not None
        assert loaded.session_id == "test-session-123"

    def test_get_nonexistent_review(self, review_storage):
        """Test getting a review that doesn't exist returns None."""
        result = review_storage.get_review("nonexistent-session-id")
        assert result is None

    def test_save_and_retrieve_review(self, review_storage, sample_feedback):
        """Test saving and retrieving reviews with feedback."""
        review = review_storage.create_review("test-session-456")
        review.add_feedback(sample_feedback)
        review_storage.save_review(review)

        loaded = review_storage.get_review("test-session-456")
        assert len(loaded.match_feedback) == 1
        assert loaded.match_feedback[0].verdict == "correct"

    def test_review_path_format(self, review_storage):
        """Test that review file path follows {session_id}_review.json format."""
        path = review_storage._review_path("my-session-id")
        assert path.name == "my-session-id_review.json"

    def test_delete_review(self, review_storage):
        """Test deleting a review session."""
        review = review_storage.create_review("test-session-789")
        session_id = review.session_id

        result = review_storage.delete_review(session_id)

        assert result is True
        assert review_storage.get_review(session_id) is None

    def test_delete_nonexistent_review(self, review_storage):
        """Test deleting review that doesn't exist returns False."""
        result = review_storage.delete_review("nonexistent-id")
        assert result is False

    def test_persistence_across_restarts(self, storage_dir, sample_feedback, sample_fp_feedback):
        """Test that data persists when storage is recreated."""
        # Create first storage instance and add data
        storage1 = ReviewStorage(storage_dir)
        review = storage1.create_review("persist-test-session")
        review.add_feedback(sample_feedback)
        review.add_feedback(sample_fp_feedback)
        review.advance_phase()
        storage1.save_review(review)

        # Create new storage instance (simulating restart)
        storage2 = ReviewStorage(storage_dir)

        # Verify data persisted
        loaded = storage2.get_review("persist-test-session")
        assert loaded is not None
        assert loaded.phase == "fp_sample"
        assert len(loaded.match_feedback) == 1
        assert len(loaded.fp_feedback) == 1

    def test_export_json(self, review_storage, sample_feedback):
        """Test exporting review as JSON."""
        review = review_storage.create_review("export-test")
        review.add_feedback(sample_feedback)
        review_storage.save_review(review)

        exported = review_storage.export_review("export-test", format="json")

        data = json.loads(exported)
        assert data['session_id'] == "export-test"
        assert len(data['match_feedback']) == 1

    def test_export_csv(self, review_storage, sample_feedback, sample_fp_feedback):
        """Test exporting review as CSV."""
        review = review_storage.create_review("csv-export-test")
        review.add_feedback(sample_feedback)
        review.add_feedback(sample_fp_feedback)
        review_storage.save_review(review)

        exported = review_storage.export_review("csv-export-test", format="csv")

        lines = exported.strip().split("\n")
        assert len(lines) == 3  # Header + 2 feedback entries
        assert "feedback_id" in lines[0]
        assert "swing_type" in lines[0]

    def test_export_invalid_format(self, review_storage):
        """Test exporting with invalid format raises error."""
        review_storage.create_review("format-test")

        with pytest.raises(ValueError):
            review_storage.export_review("format-test", format="xml")

    def test_export_nonexistent_review(self, review_storage):
        """Test exporting nonexistent review raises error."""
        with pytest.raises(ValueError):
            review_storage.export_review("nonexistent-session")

    def test_uses_same_directory_as_annotation_storage(self, storage_dir):
        """Test ReviewStorage uses same default directory as AnnotationStorage."""
        ann_storage = AnnotationStorage(storage_dir)
        rev_storage = ReviewStorage(storage_dir)

        assert ann_storage._storage_dir == rev_storage._storage_dir


# ============================================================================
# parse_offset Tests
# ============================================================================

class TestParseOffset:
    """Tests for the parse_offset function in main.py."""

    def test_parse_offset_random_returns_valid_range(self):
        """Test 'random' returns value in valid range."""
        # Run multiple times to verify random behavior stays in bounds
        for _ in range(100):
            offset = parse_offset("random", total_bars=10000, window_size=5000)
            # max_offset = 10000 - 5000 = 5000
            assert 0 <= offset <= 5000

    def test_parse_offset_random_case_insensitive(self):
        """Test 'random' is case insensitive."""
        for variant in ["random", "Random", "RANDOM", "RaNdOm"]:
            offset = parse_offset(variant, total_bars=1000, window_size=100)
            assert 0 <= offset <= 900

    def test_parse_offset_integer_returns_that_integer(self):
        """Test integer string returns that integer."""
        assert parse_offset("0", total_bars=1000, window_size=100) == 0
        assert parse_offset("500", total_bars=1000, window_size=100) == 500
        assert parse_offset("1234", total_bars=2000, window_size=100) == 1234

    def test_parse_offset_zero_default(self):
        """Test default value is 0."""
        # When using explicit "0"
        assert parse_offset("0", total_bars=1000, window_size=100) == 0

    def test_parse_offset_random_with_small_window(self):
        """Test random with window_size >= total_bars returns 0."""
        # When window_size equals total_bars, max_offset = 0
        offset = parse_offset("random", total_bars=100, window_size=100)
        assert offset == 0

        # When window_size > total_bars, max_offset = 0
        offset = parse_offset("random", total_bars=100, window_size=200)
        assert offset == 0

    def test_parse_offset_random_produces_variety(self):
        """Test random actually produces different values."""
        offsets = set()
        for _ in range(100):
            offset = parse_offset("random", total_bars=100000, window_size=1000)
            offsets.add(offset)

        # Should produce multiple different values (very likely with large range)
        assert len(offsets) > 1


# ============================================================================
# AnnotationSession window_offset Tests
# ============================================================================

class TestAnnotationSessionWindowOffset:
    """Tests for AnnotationSession window_offset field."""

    def test_create_session_with_window_offset(self):
        """Test session creation with window_offset parameter."""
        session = AnnotationSession.create(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200,
            window_offset=5000
        )

        assert session.window_offset == 5000

    def test_create_session_default_window_offset(self):
        """Test session creation with default window_offset (0)."""
        session = AnnotationSession.create(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200
        )

        assert session.window_offset == 0

    def test_session_serialization_includes_window_offset(self):
        """Test window_offset is included in to_dict."""
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=200,
            window_offset=1234
        )

        data = session.to_dict()

        assert 'window_offset' in data
        assert data['window_offset'] == 1234

    def test_session_deserialization_restores_window_offset(self):
        """Test window_offset is restored from from_dict."""
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=200,
            window_offset=5678
        )

        data = session.to_dict()
        restored = AnnotationSession.from_dict(data)

        assert restored.window_offset == 5678

    def test_session_deserialization_handles_missing_window_offset(self):
        """Test from_dict handles legacy data without window_offset."""
        # Simulate legacy data without window_offset field
        data = {
            'session_id': 'test-session-id',
            'data_file': 'test.csv',
            'resolution': '1m',
            'window_size': 200,
            'created_at': '2025-01-01T00:00:00+00:00',
            'annotations': [],
            'completed_scales': []
            # No window_offset field
        }

        session = AnnotationSession.from_dict(data)

        assert session.window_offset == 0  # Default value


class TestAnnotationStorageWindowOffset:
    """Tests for AnnotationStorage with window_offset."""

    def test_create_session_with_window_offset(self, storage):
        """Test creating session with window_offset through storage."""
        session = storage.create_session(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200,
            window_offset=10000
        )

        assert session.window_offset == 10000

        # Verify persisted
        loaded = storage.get_session(session.session_id)
        assert loaded.window_offset == 10000

    def test_persistence_with_window_offset(self, storage_dir):
        """Test window_offset persists across storage restarts."""
        # Create first storage instance and add data
        storage1 = AnnotationStorage(storage_dir)
        session = storage1.create_session(
            data_file="test.csv",
            resolution="1m",
            window_size=200,
            window_offset=7890
        )
        session_id = session.session_id

        # Create new storage instance (simulating restart)
        storage2 = AnnotationStorage(storage_dir)

        # Verify data persisted
        loaded_session = storage2.get_session(session_id)
        assert loaded_session is not None
        assert loaded_session.window_offset == 7890


# ============================================================================
# AnnotationSession status Tests
# ============================================================================

class TestAnnotationSessionStatus:
    """Tests for AnnotationSession status field."""

    def test_create_session_has_default_status(self):
        """Test session creation has default 'in_progress' status."""
        session = AnnotationSession.create(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200
        )

        assert session.status == "in_progress"

    def test_session_status_can_be_changed(self):
        """Test session status can be updated to keep or discard."""
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=200
        )

        session.status = "keep"
        assert session.status == "keep"

        session.status = "discard"
        assert session.status == "discard"

    def test_session_serialization_includes_status(self):
        """Test status is included in to_dict."""
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=200
        )
        session.status = "keep"

        data = session.to_dict()

        assert 'status' in data
        assert data['status'] == "keep"

    def test_session_deserialization_restores_status(self):
        """Test status is restored from from_dict."""
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=200
        )
        session.status = "discard"

        data = session.to_dict()
        restored = AnnotationSession.from_dict(data)

        assert restored.status == "discard"

    def test_session_deserialization_handles_missing_status(self):
        """Test from_dict handles legacy data without status field."""
        # Simulate legacy data without status field
        data = {
            'session_id': 'test-session-id',
            'data_file': 'test.csv',
            'resolution': '1m',
            'window_size': 200,
            'created_at': '2025-01-01T00:00:00+00:00',
            'annotations': [],
            'completed_scales': [],
            'window_offset': 0
            # No status field
        }

        session = AnnotationSession.from_dict(data)

        assert session.status == "in_progress"  # Default value


class TestAnnotationStorageStatus:
    """Tests for AnnotationStorage with status field."""

    def test_session_status_persistence(self, storage):
        """Test that status persists when updating session."""
        session = storage.create_session(
            data_file="test_data.csv",
            resolution="1m",
            window_size=200
        )

        # Update status
        session.status = "keep"
        storage.update_session(session)

        # Reload and verify
        loaded = storage.get_session(session.session_id)
        assert loaded.status == "keep"

    def test_status_persistence_across_restarts(self, storage_dir):
        """Test status persists across storage restarts."""
        # Create first storage instance and add data
        storage1 = AnnotationStorage(storage_dir)
        session = storage1.create_session(
            data_file="test.csv",
            resolution="1m",
            window_size=200
        )
        session.status = "discard"
        storage1.update_session(session)
        session_id = session.session_id

        # Create new storage instance (simulating restart)
        storage2 = AnnotationStorage(storage_dir)

        # Verify data persisted
        loaded_session = storage2.get_session(session_id)
        assert loaded_session is not None
        assert loaded_session.status == "discard"

    def test_export_json_includes_status(self, storage):
        """Test exported JSON includes status field."""
        session = storage.create_session(
            data_file="test.csv",
            resolution="1m",
            window_size=200
        )
        session.status = "keep"
        storage.update_session(session)

        exported = storage.export_session(session.session_id, format="json")
        data = json.loads(exported)

        assert 'status' in data
        assert data['status'] == "keep"
