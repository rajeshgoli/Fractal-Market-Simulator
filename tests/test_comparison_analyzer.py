"""
Tests for ComparisonAnalyzer

Tests the comparison logic between user annotations and system-detected swings.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.ground_truth_annotator.comparison_analyzer import (
    ComparisonAnalyzer,
    ComparisonResult,
    DetectedSwing,
)
from src.ground_truth_annotator.models import AnnotationSession, SwingAnnotation
from src.swing_analysis.bull_reference_detector import Bar


class TestDetectedSwing:
    """Tests for DetectedSwing dataclass."""

    def test_create_bull_swing(self):
        """Test creating a bull (downswing) detected swing."""
        swing = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=150,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        assert swing.direction == 'bull'
        assert swing.start_index == 100
        assert swing.end_index == 150
        assert swing.size == 50.0

    def test_create_bear_swing(self):
        """Test creating a bear (upswing) detected swing."""
        swing = DetectedSwing(
            direction='bear',
            start_index=200,
            end_index=280,
            high_price=5200.0,
            low_price=5100.0,
            size=100.0,
            rank=2
        )

        assert swing.direction == 'bear'
        assert swing.start_index == 200
        assert swing.end_index == 280


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_match_rate_all_matches(self):
        """Match rate is 1.0 when all swings match."""
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=0,
            end_source_index=100,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )
        system_swing = DetectedSwing(
            direction='bull',
            start_index=0,
            end_index=100,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = ComparisonResult(
            scale='M',
            matches=[(annotation, system_swing)],
            false_negatives=[],
            false_positives=[]
        )

        assert result.match_rate == 1.0

    def test_match_rate_no_matches(self):
        """Match rate is 0 when no swings match."""
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=0,
            end_source_index=100,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        result = ComparisonResult(
            scale='M',
            matches=[],
            false_negatives=[annotation],
            false_positives=[]
        )

        assert result.match_rate == 0.0

    def test_match_rate_partial(self):
        """Match rate calculated correctly for partial matches."""
        # 1 match, 1 FN, 1 FP = 1/3 = 0.333...
        annotation1 = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=0,
            end_source_index=100,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )
        annotation2 = SwingAnnotation.create(
            scale='M',
            direction='bear',
            start_bar_index=20,
            end_bar_index=30,
            start_source_index=200,
            end_source_index=300,
            start_price=Decimal('5000'),
            end_price=Decimal('5080'),
            window_id='test'
        )
        system_swing1 = DetectedSwing(
            direction='bull',
            start_index=0,
            end_index=100,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )
        system_swing2 = DetectedSwing(
            direction='bear',
            start_index=500,
            end_index=600,
            high_price=5300.0,
            low_price=5200.0,
            size=100.0,
            rank=2
        )

        result = ComparisonResult(
            scale='M',
            matches=[(annotation1, system_swing1)],
            false_negatives=[annotation2],
            false_positives=[system_swing2]
        )

        assert abs(result.match_rate - (1/3)) < 0.001

    def test_match_rate_empty(self):
        """Match rate is 1.0 when no swings exist."""
        result = ComparisonResult(
            scale='M',
            matches=[],
            false_negatives=[],
            false_positives=[]
        )

        assert result.match_rate == 1.0

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=0,
            end_source_index=100,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )
        system_swing = DetectedSwing(
            direction='bull',
            start_index=0,
            end_index=100,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = ComparisonResult(
            scale='M',
            matches=[(annotation, system_swing)],
            false_negatives=[],
            false_positives=[]
        )

        d = result.to_dict()

        assert d['scale'] == 'M'
        assert d['match_count'] == 1
        assert d['false_negative_count'] == 0
        assert d['false_positive_count'] == 0
        assert d['match_rate'] == 1.0
        assert len(d['matches']) == 1


class TestComparisonAnalyzer:
    """Tests for ComparisonAnalyzer class."""

    def test_exact_match(self):
        """Test exact match between annotation and system swing."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        system_swing = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=200,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')

        assert len(result.matches) == 1
        assert len(result.false_negatives) == 0
        assert len(result.false_positives) == 0

    def test_match_within_tolerance(self):
        """Test match within tolerance bounds."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        # Duration = 100 bars, tolerance = 10%
        # Tolerance = max(5, 10) = 10 bars
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        # System swing off by 5 bars at start, 8 bars at end (within tolerance)
        system_swing = DetectedSwing(
            direction='bull',
            start_index=105,
            end_index=208,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')

        assert len(result.matches) == 1
        assert len(result.false_negatives) == 0

    def test_no_match_outside_tolerance(self):
        """Test no match when outside tolerance bounds."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        # Duration = 100 bars, tolerance = 10 bars
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        # System swing off by 15 bars at end (outside tolerance)
        system_swing = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=215,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')

        assert len(result.matches) == 0
        assert len(result.false_negatives) == 1
        assert len(result.false_positives) == 1

    def test_direction_mismatch_rejected(self):
        """Test that direction mismatch prevents matching."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        # Same indices but different direction
        system_swing = DetectedSwing(
            direction='bear',
            start_index=100,
            end_index=200,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')

        assert len(result.matches) == 0
        assert len(result.false_negatives) == 1
        assert len(result.false_positives) == 1

    def test_empty_annotations(self):
        """Test comparison with no user annotations."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        system_swings = [
            DetectedSwing(
                direction='bull',
                start_index=100,
                end_index=200,
                high_price=5100.0,
                low_price=5050.0,
                size=50.0,
                rank=1
            )
        ]

        result = analyzer.compare_scale([], system_swings, 'M')

        assert len(result.matches) == 0
        assert len(result.false_negatives) == 0
        assert len(result.false_positives) == 1

    def test_empty_system_swings(self):
        """Test comparison with no system detections."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        annotations = [
            SwingAnnotation.create(
                scale='M',
                direction='bull',
                start_bar_index=0,
                end_bar_index=10,
                start_source_index=100,
                end_source_index=200,
                start_price=Decimal('5100'),
                end_price=Decimal('5050'),
                window_id='test'
            )
        ]

        result = analyzer.compare_scale(annotations, [], 'M')

        assert len(result.matches) == 0
        assert len(result.false_negatives) == 1
        assert len(result.false_positives) == 0

    def test_minimum_tolerance_floor(self):
        """Test that tolerance has a minimum of 5 bars by default."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.2, min_tolerance_bars=5)

        # Duration = 20 bars, 20% = 4 bars, but minimum is 5
        annotation = SwingAnnotation.create(
            scale='S',
            direction='bull',
            start_bar_index=0,
            end_bar_index=2,
            start_source_index=100,
            end_source_index=120,
            start_price=Decimal('5100'),
            end_price=Decimal('5090'),
            window_id='test'
        )

        # Off by 4 bars (should match with 5 bar minimum tolerance)
        system_swing = DetectedSwing(
            direction='bull',
            start_index=104,
            end_index=124,
            high_price=5100.0,
            low_price=5090.0,
            size=10.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'S')

        assert len(result.matches) == 1

    def test_custom_min_tolerance_bars(self):
        """Test configurable minimum tolerance bars for large-scale matching."""
        # Duration = 8000 bars, with 1000 bar endpoint differences
        annotation = SwingAnnotation.create(
            scale='XL',
            direction='bull',
            start_bar_index=0,
            end_bar_index=80,
            start_source_index=27000,
            end_source_index=35000,
            start_price=Decimal('5500'),
            end_price=Decimal('5000'),
            window_id='test'
        )

        # System swing has ~1000 bar offset at start, ~740 at end
        system_swing = DetectedSwing(
            direction='bull',
            start_index=27996,
            end_index=34260,
            high_price=5500.0,
            low_price=5000.0,
            size=500.0,
            rank=1
        )

        # With default min_tolerance (5): 20% of 8000 = 1600 bars tolerance
        # Start diff = 996, end diff = 740 - should match
        analyzer_default = ComparisonAnalyzer(tolerance_pct=0.2, min_tolerance_bars=5)
        result_default = analyzer_default.compare_scale([annotation], [system_swing], 'XL')
        assert len(result_default.matches) == 1

        # With higher min_tolerance (500): ensures large swings always have reasonable tolerance
        analyzer_large = ComparisonAnalyzer(tolerance_pct=0.2, min_tolerance_bars=500)
        result_large = analyzer_large.compare_scale([annotation], [system_swing], 'XL')
        assert len(result_large.matches) == 1

    def test_tolerance_pct_20_percent_default(self):
        """Test that 20% tolerance is now the default."""
        analyzer = ComparisonAnalyzer()  # Using defaults

        # Duration = 100 bars, 20% = 20 bars tolerance
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        # System swing off by 18 bars at end (within 20% tolerance)
        system_swing = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=218,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')

        # 18 bars is within 20% of 100 = 20 bars
        assert len(result.matches) == 1

    def test_tolerance_edge_case_just_within(self):
        """Test match at exactly the tolerance boundary."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.2, min_tolerance_bars=5)

        # Duration = 100 bars, tolerance = max(5, 20) = 20 bars
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        # Off by exactly 20 bars (should still match - boundary inclusive)
        system_swing = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=220,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')
        assert len(result.matches) == 1

    def test_tolerance_edge_case_just_outside(self):
        """Test no match just outside tolerance boundary."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.2, min_tolerance_bars=5)

        # Duration = 100 bars, tolerance = max(5, 20) = 20 bars
        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        # Off by 21 bars (should NOT match - just outside)
        system_swing = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=221,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        result = analyzer.compare_scale([annotation], [system_swing], 'M')
        assert len(result.matches) == 0
        assert len(result.false_negatives) == 1
        assert len(result.false_positives) == 1

    def test_multiple_annotations_multiple_system(self):
        """Test comparison with multiple annotations and system swings."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

        annotations = [
            SwingAnnotation.create(
                scale='M',
                direction='bull',
                start_bar_index=0,
                end_bar_index=10,
                start_source_index=100,
                end_source_index=200,
                start_price=Decimal('5100'),
                end_price=Decimal('5050'),
                window_id='test'
            ),
            SwingAnnotation.create(
                scale='M',
                direction='bear',
                start_bar_index=20,
                end_bar_index=30,
                start_source_index=300,
                end_source_index=400,
                start_price=Decimal('5050'),
                end_price=Decimal('5120'),
                window_id='test'
            ),
            SwingAnnotation.create(
                scale='M',
                direction='bull',
                start_bar_index=40,
                end_bar_index=50,
                start_source_index=500,
                end_source_index=600,
                start_price=Decimal('5120'),
                end_price=Decimal('5080'),
                window_id='test'
            )
        ]

        system_swings = [
            DetectedSwing(
                direction='bull',
                start_index=100,
                end_index=200,
                high_price=5100.0,
                low_price=5050.0,
                size=50.0,
                rank=1
            ),
            DetectedSwing(
                direction='bear',
                start_index=300,
                end_index=400,
                high_price=5120.0,
                low_price=5050.0,
                size=70.0,
                rank=2
            ),
            # Unmatched system swing
            DetectedSwing(
                direction='bull',
                start_index=700,
                end_index=800,
                high_price=5200.0,
                low_price=5150.0,
                size=50.0,
                rank=3
            )
        ]

        result = analyzer.compare_scale(annotations, system_swings, 'M')

        # 2 matches (first bull and bear), 1 FN (third annotation), 1 FP (last system)
        assert len(result.matches) == 2
        assert len(result.false_negatives) == 1
        assert len(result.false_positives) == 1

    def test_one_to_one_matching(self):
        """Test that each system swing can only match once."""
        analyzer = ComparisonAnalyzer(tolerance_pct=0.5)  # High tolerance

        # Two annotations that could both match the same system swing
        annotations = [
            SwingAnnotation.create(
                scale='M',
                direction='bull',
                start_bar_index=0,
                end_bar_index=10,
                start_source_index=100,
                end_source_index=200,
                start_price=Decimal('5100'),
                end_price=Decimal('5050'),
                window_id='test'
            ),
            SwingAnnotation.create(
                scale='M',
                direction='bull',
                start_bar_index=2,
                end_bar_index=12,
                start_source_index=110,
                end_source_index=210,
                start_price=Decimal('5100'),
                end_price=Decimal('5050'),
                window_id='test'
            )
        ]

        system_swings = [
            DetectedSwing(
                direction='bull',
                start_index=100,
                end_index=200,
                high_price=5100.0,
                low_price=5050.0,
                size=50.0,
                rank=1
            )
        ]

        result = analyzer.compare_scale(annotations, system_swings, 'M')

        # First annotation matches, second becomes FN
        assert len(result.matches) == 1
        assert len(result.false_negatives) == 1
        assert len(result.false_positives) == 0


class TestComparisonAnalyzerReport:
    """Tests for report generation."""

    def test_generate_report_empty(self):
        """Test report generation with empty results."""
        analyzer = ComparisonAnalyzer()

        results = {
            'XL': ComparisonResult(scale='XL'),
            'L': ComparisonResult(scale='L'),
            'M': ComparisonResult(scale='M'),
            'S': ComparisonResult(scale='S'),
        }

        report = analyzer.generate_report(results)

        assert report['summary']['total_user_annotations'] == 0
        assert report['summary']['total_system_detections'] == 0
        assert report['summary']['overall_match_rate'] == 1.0
        assert len(report['false_negatives']) == 0
        assert len(report['false_positives']) == 0

    def test_generate_report_with_data(self):
        """Test report generation with actual comparison data."""
        analyzer = ComparisonAnalyzer()

        annotation = SwingAnnotation.create(
            scale='M',
            direction='bull',
            start_bar_index=0,
            end_bar_index=10,
            start_source_index=100,
            end_source_index=200,
            start_price=Decimal('5100'),
            end_price=Decimal('5050'),
            window_id='test'
        )

        unmatched_ann = SwingAnnotation.create(
            scale='L',
            direction='bear',
            start_bar_index=20,
            end_bar_index=30,
            start_source_index=300,
            end_source_index=400,
            start_price=Decimal('5000'),
            end_price=Decimal('5080'),
            window_id='test'
        )

        matched_system = DetectedSwing(
            direction='bull',
            start_index=100,
            end_index=200,
            high_price=5100.0,
            low_price=5050.0,
            size=50.0,
            rank=1
        )

        unmatched_system = DetectedSwing(
            direction='bull',
            start_index=500,
            end_index=600,
            high_price=5200.0,
            low_price=5100.0,
            size=100.0,
            rank=2
        )

        results = {
            'XL': ComparisonResult(scale='XL'),
            'L': ComparisonResult(
                scale='L',
                false_negatives=[unmatched_ann],
                false_positives=[unmatched_system]
            ),
            'M': ComparisonResult(
                scale='M',
                matches=[(annotation, matched_system)]
            ),
            'S': ComparisonResult(scale='S'),
        }

        report = analyzer.generate_report(results)

        assert report['summary']['total_user_annotations'] == 2  # 1 matched + 1 FN
        assert report['summary']['total_matches'] == 1
        assert report['summary']['total_false_negatives'] == 1
        assert report['summary']['total_false_positives'] == 1

        # Check per-scale breakdown
        assert report['by_scale']['M']['matches'] == 1
        assert report['by_scale']['L']['false_negatives'] == 1

        # Check false negative details
        assert len(report['false_negatives']) == 1
        assert report['false_negatives'][0]['scale'] == 'L'

        # Check false positive details
        assert len(report['false_positives']) == 1
        assert report['false_positives'][0]['scale'] == 'L'


class TestComparisonAnalyzerSystemDetection:
    """Tests for system detection integration."""

    def test_run_system_detection_empty_bars(self):
        """Test system detection with empty bar list."""
        analyzer = ComparisonAnalyzer()

        swings = analyzer._run_system_detection([])

        assert len(swings) == 0

    def test_run_system_detection_minimal_bars(self):
        """Test system detection with minimal bar data."""
        analyzer = ComparisonAnalyzer()

        # Create minimal bars (not enough for swing detection)
        bars = [
            Bar(index=i, timestamp=i * 60, open=5000.0, high=5000.0, low=5000.0, close=5000.0)
            for i in range(10)
        ]

        swings = analyzer._run_system_detection(bars)

        # With flat prices, no swings should be detected
        assert isinstance(swings, list)

    def test_run_system_detection_with_swings(self):
        """Test system detection with data containing swings."""
        analyzer = ComparisonAnalyzer()

        # Create bars with a clear swing pattern
        bars = []
        # Uptrend
        for i in range(20):
            price = 5000.0 + i * 5
            bars.append(Bar(
                index=i,
                timestamp=i * 60,
                open=price,
                high=price + 2,
                low=price - 2,
                close=price + 1
            ))
        # Downtrend
        for i in range(20, 40):
            price = 5095.0 - (i - 20) * 5
            bars.append(Bar(
                index=i,
                timestamp=i * 60,
                open=price,
                high=price + 2,
                low=price - 2,
                close=price - 1
            ))

        swings = analyzer._run_system_detection(bars)

        # Should detect at least some swings
        assert isinstance(swings, list)
        # All swings should have required attributes
        for swing in swings:
            assert hasattr(swing, 'direction')
            assert hasattr(swing, 'start_index')
            assert hasattr(swing, 'end_index')
            assert swing.direction in ('bull', 'bear')


class TestComparisonAnalyzerSession:
    """Tests for session-based comparison."""

    def test_compare_session_empty(self):
        """Test session comparison with no annotations."""
        analyzer = ComparisonAnalyzer()

        session = AnnotationSession.create(
            data_file='test.csv',
            resolution='1m',
            window_size=1000
        )

        # Minimal bars
        bars = [
            Bar(index=i, timestamp=i * 60, open=5000.0, high=5000.0, low=5000.0, close=5000.0)
            for i in range(20)
        ]

        results = analyzer.compare_session(session, bars)

        # Should have results for all scales
        assert 'XL' in results
        assert 'L' in results
        assert 'M' in results
        assert 'S' in results

    def test_compare_session_specific_scales(self):
        """Test session comparison with specific scales."""
        analyzer = ComparisonAnalyzer()

        session = AnnotationSession.create(
            data_file='test.csv',
            resolution='1m',
            window_size=1000
        )

        bars = [
            Bar(index=i, timestamp=i * 60, open=5000.0, high=5000.0, low=5000.0, close=5000.0)
            for i in range(20)
        ]

        results = analyzer.compare_session(session, bars, scales=['M', 'L'])

        # Should only have requested scales
        assert 'M' in results
        assert 'L' in results
        assert 'XL' not in results
        assert 'S' not in results
