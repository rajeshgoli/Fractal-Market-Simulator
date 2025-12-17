"""
Tests for CascadeController

Tests the XL → L → M → S scale progression workflow for ground truth annotation.
"""

import tempfile
from decimal import Decimal

import pytest

from src.swing_analysis.bar_aggregator import BarAggregator
from src.swing_analysis.types import Bar
from src.ground_truth_annotator.models import SwingAnnotation, AnnotationSession
from src.ground_truth_annotator.cascade_controller import CascadeController


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_bars():
    """Create 10K sample bars for cascade testing."""
    bars = []
    base_timestamp = 1700000000
    for i in range(10000):
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
def large_bars():
    """Create 50K sample bars for full cascade testing."""
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
def session():
    """Create a fresh annotation session."""
    return AnnotationSession.create(
        data_file="test_data.csv",
        resolution="1m",
        window_size=10000
    )


@pytest.fixture
def aggregator(sample_bars):
    """Create a BarAggregator with sample bars."""
    return BarAggregator(sample_bars, source_resolution_minutes=1)


@pytest.fixture
def cascade_controller(session, sample_bars, aggregator):
    """Create a CascadeController for testing."""
    return CascadeController(
        session=session,
        source_bars=sample_bars,
        aggregator=aggregator
    )


# ============================================================================
# Basic Initialization Tests
# ============================================================================

class TestCascadeControllerInit:
    """Tests for CascadeController initialization."""

    def test_init_starts_at_xl(self, cascade_controller):
        """Should start at XL scale."""
        assert cascade_controller.get_current_scale() == "XL"
        assert cascade_controller.get_current_scale_index() == 0

    def test_init_no_completed_scales(self, cascade_controller):
        """Should have no completed scales initially."""
        assert cascade_controller.get_completed_scales() == []

    def test_init_no_reference_scale(self, cascade_controller):
        """Should have no reference scale initially."""
        assert cascade_controller.get_reference_scale() is None

    def test_scale_order_is_correct(self, cascade_controller):
        """Scale order should be XL → L → M → S."""
        assert CascadeController.SCALE_ORDER == ["XL", "L", "M", "S"]

    def test_target_bars_configured(self, cascade_controller):
        """Target bars should be configured for each scale."""
        targets = CascadeController.SCALE_TARGET_BARS
        assert targets["XL"] == 50
        assert targets["L"] == 200
        assert targets["M"] == 800
        assert targets["S"] is None  # Source resolution


# ============================================================================
# Scale Bar Aggregation Tests
# ============================================================================

class TestScaleBars:
    """Tests for scale-specific bar aggregation."""

    def test_get_xl_bars_aggregated(self, cascade_controller, sample_bars):
        """XL scale should have ~50 bars."""
        xl_bars = cascade_controller.get_bars_for_scale("XL")
        # Should be approximately 50 bars for 10K source
        assert len(xl_bars) <= 60
        assert len(xl_bars) >= 40

    def test_get_l_bars_aggregated(self, cascade_controller, sample_bars):
        """L scale should have ~200 bars."""
        l_bars = cascade_controller.get_bars_for_scale("L")
        assert len(l_bars) <= 220
        assert len(l_bars) >= 180

    def test_get_m_bars_aggregated(self, cascade_controller, sample_bars):
        """M scale should have ~800 bars."""
        m_bars = cascade_controller.get_bars_for_scale("M")
        assert len(m_bars) <= 850
        assert len(m_bars) >= 750

    def test_get_s_bars_is_source(self, cascade_controller, sample_bars):
        """S scale should return source bars."""
        s_bars = cascade_controller.get_bars_for_scale("S")
        assert len(s_bars) == len(sample_bars)

    def test_invalid_scale_raises_error(self, cascade_controller):
        """Invalid scale should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid scale"):
            cascade_controller.get_bars_for_scale("INVALID")


# ============================================================================
# Scale Progression Tests
# ============================================================================

class TestScaleProgression:
    """Tests for XL → L → M → S progression."""

    def test_advance_from_xl_to_l(self, cascade_controller):
        """Advancing from XL should move to L."""
        result = cascade_controller.advance_to_next_scale()
        assert result is True
        assert cascade_controller.get_current_scale() == "L"
        assert "XL" in cascade_controller.get_completed_scales()

    def test_advance_through_all_scales(self, cascade_controller):
        """Should be able to advance through all scales."""
        # XL -> L
        cascade_controller.advance_to_next_scale()
        assert cascade_controller.get_current_scale() == "L"

        # L -> M
        cascade_controller.advance_to_next_scale()
        assert cascade_controller.get_current_scale() == "M"

        # M -> S
        cascade_controller.advance_to_next_scale()
        assert cascade_controller.get_current_scale() == "S"

        # S is last scale
        result = cascade_controller.advance_to_next_scale()
        assert result is False  # Can't advance further
        assert cascade_controller.get_current_scale() == "S"

    def test_session_complete_after_all_scales(self, cascade_controller):
        """Session should be complete after all scales finished."""
        assert not cascade_controller.is_session_complete()

        for _ in range(4):  # Advance through all 4 scales
            cascade_controller.advance_to_next_scale()

        assert cascade_controller.is_session_complete()

    def test_progress_tracking(self, cascade_controller):
        """Progress should track completed vs total."""
        assert cascade_controller.get_progress() == (0, 4)

        cascade_controller.advance_to_next_scale()
        assert cascade_controller.get_progress() == (1, 4)

        cascade_controller.advance_to_next_scale()
        assert cascade_controller.get_progress() == (2, 4)


# ============================================================================
# Reference Scale Tests
# ============================================================================

class TestReferenceScale:
    """Tests for reference scale functionality."""

    def test_no_reference_at_start(self, cascade_controller):
        """No reference scale at XL (nothing completed yet)."""
        assert cascade_controller.get_reference_scale() is None
        assert cascade_controller.get_reference_annotations() == []

    def test_reference_is_previous_completed(self, cascade_controller):
        """After advancing, reference should be previous scale."""
        cascade_controller.advance_to_next_scale()  # Now at L
        assert cascade_controller.get_reference_scale() == "XL"

        cascade_controller.advance_to_next_scale()  # Now at M
        assert cascade_controller.get_reference_scale() == "L"

    def test_reference_annotations_returns_scale_annotations(
        self, cascade_controller
    ):
        """Reference annotations should return annotations from reference scale."""
        # Add an XL annotation
        annotation = SwingAnnotation.create(
            scale="XL",
            direction="bull",
            start_bar_index=5,
            end_bar_index=15,
            start_source_index=500,
            end_source_index=1500,
            start_price=Decimal("4500.00"),
            end_price=Decimal("4550.00"),
            window_id=cascade_controller.session.session_id
        )
        cascade_controller.session.add_annotation(annotation)

        # Advance to L
        cascade_controller.advance_to_next_scale()

        # Reference should include XL annotation
        ref_annotations = cascade_controller.get_reference_annotations()
        assert len(ref_annotations) == 1
        assert ref_annotations[0].scale == "XL"


# ============================================================================
# Aggregation Map Tests
# ============================================================================

class TestAggregationMap:
    """Tests for aggregation index mapping."""

    def test_aggregation_map_exists_for_all_scales(self, cascade_controller):
        """Aggregation map should exist for all scales."""
        for scale in ["XL", "L", "M", "S"]:
            agg_map = cascade_controller.get_aggregation_map(scale)
            assert isinstance(agg_map, dict)

    def test_aggregation_map_maps_to_source(self, cascade_controller, sample_bars):
        """Aggregation map should map agg index to source range."""
        xl_map = cascade_controller.get_aggregation_map("XL")

        # Check first entry
        if 0 in xl_map:
            source_start, source_end = xl_map[0]
            assert source_start >= 0
            assert source_end < len(sample_bars)
            assert source_start <= source_end

    def test_s_scale_map_is_1_to_1(self, cascade_controller, sample_bars):
        """S scale aggregation map should be 1:1."""
        s_map = cascade_controller.get_aggregation_map("S")

        # First few entries should be identity mapping
        for i in range(min(10, len(sample_bars))):
            assert s_map[i] == (i, i)


# ============================================================================
# Cascade State Tests
# ============================================================================

class TestCascadeState:
    """Tests for get_cascade_state() method."""

    def test_cascade_state_initial(self, cascade_controller):
        """Initial cascade state should reflect XL start."""
        state = cascade_controller.get_cascade_state()

        assert state["current_scale"] == "XL"
        assert state["current_scale_index"] == 0
        assert state["reference_scale"] is None
        assert state["completed_scales"] == []
        assert state["scales_remaining"] == 4
        assert state["is_complete"] is False

    def test_cascade_state_after_advance(self, cascade_controller):
        """Cascade state should update after advancing."""
        cascade_controller.advance_to_next_scale()
        state = cascade_controller.get_cascade_state()

        assert state["current_scale"] == "L"
        assert state["current_scale_index"] == 1
        assert state["reference_scale"] == "XL"
        assert "XL" in state["completed_scales"]
        assert state["scales_remaining"] == 3
        assert state["is_complete"] is False

    def test_cascade_state_includes_scale_info(self, cascade_controller):
        """Cascade state should include info for all scales."""
        state = cascade_controller.get_cascade_state()

        assert "scale_info" in state
        for scale in ["XL", "L", "M", "S"]:
            assert scale in state["scale_info"]
            info = state["scale_info"][scale]
            assert "actual_bars" in info
            assert "compression_ratio" in info
            assert "annotation_count" in info
            assert "is_complete" in info


# ============================================================================
# Scale Info Tests
# ============================================================================

class TestScaleInfo:
    """Tests for get_scale_info() method."""

    def test_scale_info_structure(self, cascade_controller):
        """Scale info should have expected fields."""
        info = cascade_controller.get_scale_info("XL")

        assert info["scale"] == "XL"
        assert info["target_bars"] == 50
        assert "actual_bars" in info
        assert "compression_ratio" in info
        assert info["annotation_count"] == 0
        assert info["is_complete"] is False

    def test_scale_info_tracks_completion(self, cascade_controller):
        """Scale info should track completion status."""
        info_before = cascade_controller.get_scale_info("XL")
        assert info_before["is_complete"] is False

        cascade_controller.advance_to_next_scale()

        info_after = cascade_controller.get_scale_info("XL")
        assert info_after["is_complete"] is True


# ============================================================================
# Reset Tests
# ============================================================================

class TestResetToScale:
    """Tests for reset_to_scale() method."""

    def test_reset_clears_subsequent_scales(self, cascade_controller):
        """Resetting should clear completion for subsequent scales."""
        # Advance to M
        cascade_controller.advance_to_next_scale()  # XL -> L
        cascade_controller.advance_to_next_scale()  # L -> M

        assert cascade_controller.get_current_scale() == "M"
        assert "XL" in cascade_controller.get_completed_scales()
        assert "L" in cascade_controller.get_completed_scales()

        # Reset to L
        cascade_controller.reset_to_scale("L")

        assert cascade_controller.get_current_scale() == "L"
        assert "XL" in cascade_controller.get_completed_scales()
        assert "L" not in cascade_controller.get_completed_scales()

    def test_reset_to_xl_clears_all(self, cascade_controller):
        """Resetting to XL should clear all completed scales."""
        # Advance through all
        for _ in range(3):
            cascade_controller.advance_to_next_scale()

        cascade_controller.reset_to_scale("XL")

        assert cascade_controller.get_current_scale() == "XL"
        assert cascade_controller.get_completed_scales() == []


# ============================================================================
# Resume Session Tests
# ============================================================================

class TestResumeSession:
    """Tests for resuming a session with existing progress."""

    def test_resume_from_completed_scales(self, sample_bars, aggregator):
        """Controller should resume at correct scale from session state."""
        # Create session with completed scales
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=10000
        )
        session.mark_scale_complete("XL")
        session.mark_scale_complete("L")

        # Create controller - should resume at M
        controller = CascadeController(
            session=session,
            source_bars=sample_bars,
            aggregator=aggregator
        )

        assert controller.get_current_scale() == "M"
        assert controller.get_completed_scales() == ["XL", "L"]


# ============================================================================
# Large Dataset Tests
# ============================================================================

class TestLargeDataset:
    """Tests with 50K bar datasets."""

    def test_50k_bars_xl_target(self, large_bars):
        """50K bars should aggregate to ~50 XL bars."""
        aggregator = BarAggregator(large_bars, source_resolution_minutes=1)
        session = AnnotationSession.create(
            data_file="test.csv",
            resolution="1m",
            window_size=50000
        )
        controller = CascadeController(
            session=session,
            source_bars=large_bars,
            aggregator=aggregator
        )

        xl_bars = controller.get_bars_for_scale("XL")
        # 50K / 50 = 1000:1 compression
        assert len(xl_bars) >= 45
        assert len(xl_bars) <= 55


# ============================================================================
# Skip Remaining Scales Tests (Issue #67)
# ============================================================================

class TestSkipRemainingScales:
    """Tests for skip_remaining_scales() method."""

    def test_skip_from_xl_marks_lms_as_skipped(self, cascade_controller):
        """Skipping from XL should mark L, M, S as skipped."""
        assert cascade_controller.get_current_scale() == "XL"

        skipped = cascade_controller.skip_remaining_scales()

        assert skipped == ["L", "M", "S"]
        assert "XL" in cascade_controller.session.completed_scales
        assert cascade_controller.session.is_scale_skipped("L")
        assert cascade_controller.session.is_scale_skipped("M")
        assert cascade_controller.session.is_scale_skipped("S")

    def test_skip_from_l_marks_ms_as_skipped(self, cascade_controller):
        """Skipping from L should mark M, S as skipped."""
        cascade_controller.advance_to_next_scale()  # XL -> L
        assert cascade_controller.get_current_scale() == "L"

        skipped = cascade_controller.skip_remaining_scales()

        assert skipped == ["M", "S"]
        assert "XL" in cascade_controller.session.completed_scales
        assert "L" in cascade_controller.session.completed_scales
        assert cascade_controller.session.is_scale_skipped("M")
        assert cascade_controller.session.is_scale_skipped("S")

    def test_skip_from_m_marks_s_as_skipped(self, cascade_controller):
        """Skipping from M should mark only S as skipped."""
        cascade_controller.advance_to_next_scale()  # XL -> L
        cascade_controller.advance_to_next_scale()  # L -> M
        assert cascade_controller.get_current_scale() == "M"

        skipped = cascade_controller.skip_remaining_scales()

        assert skipped == ["S"]
        assert "M" in cascade_controller.session.completed_scales
        assert cascade_controller.session.is_scale_skipped("S")

    def test_skip_from_s_returns_empty(self, cascade_controller):
        """Skipping from S should return empty list (nothing to skip)."""
        # Advance to S
        for _ in range(3):
            cascade_controller.advance_to_next_scale()
        assert cascade_controller.get_current_scale() == "S"

        skipped = cascade_controller.skip_remaining_scales()

        assert skipped == []
        assert "S" in cascade_controller.session.completed_scales

    def test_skip_marks_session_complete(self, cascade_controller):
        """Session should be complete after skipping."""
        cascade_controller.skip_remaining_scales()

        assert cascade_controller.is_session_complete()

    def test_cascade_state_includes_skipped_scales(self, cascade_controller):
        """Cascade state should include skipped_scales."""
        cascade_controller.advance_to_next_scale()  # XL -> L
        cascade_controller.skip_remaining_scales()

        state = cascade_controller.get_cascade_state()

        assert "skipped_scales" in state
        assert state["skipped_scales"] == ["M", "S"]

    def test_scale_info_includes_is_skipped(self, cascade_controller):
        """Scale info should include is_skipped field."""
        cascade_controller.advance_to_next_scale()  # XL -> L
        cascade_controller.skip_remaining_scales()

        m_info = cascade_controller.get_scale_info("M")
        s_info = cascade_controller.get_scale_info("S")
        xl_info = cascade_controller.get_scale_info("XL")

        assert m_info["is_skipped"] is True
        assert s_info["is_skipped"] is True
        assert xl_info["is_skipped"] is False

    def test_reset_clears_skipped_scales(self, cascade_controller):
        """Resetting should clear skipped_scales."""
        cascade_controller.advance_to_next_scale()  # XL -> L
        cascade_controller.skip_remaining_scales()  # Skip M, S

        assert cascade_controller.session.is_scale_skipped("M")
        assert cascade_controller.session.is_scale_skipped("S")

        cascade_controller.reset_to_scale("L")

        assert not cascade_controller.session.is_scale_skipped("M")
        assert not cascade_controller.session.is_scale_skipped("S")
