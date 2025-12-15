"""
Comparison Analyzer for Ground Truth Annotations

Compares user-annotated ground truth against system-detected swings
to identify false negatives, false positives, and matching swings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .models import AnnotationSession, SwingAnnotation
from ..swing_analysis.bull_reference_detector import Bar
from ..swing_analysis.swing_detector import detect_swings


@dataclass
class DetectedSwing:
    """
    A system-detected swing in normalized format.

    Represents both bull and bear reference swings with consistent
    start/end indices regardless of direction.
    """
    direction: str          # "bull" or "bear"
    start_index: int        # Bar index where swing starts
    end_index: int          # Bar index where swing ends
    high_price: float
    low_price: float
    size: float
    rank: int


@dataclass
class ComparisonResult:
    """
    Result of comparing user annotations against system detection for a single scale.
    """
    scale: str
    false_negatives: List[SwingAnnotation] = field(default_factory=list)  # User marked, system missed
    false_positives: List[DetectedSwing] = field(default_factory=list)    # System found, user didn't mark
    matches: List[Tuple[SwingAnnotation, DetectedSwing]] = field(default_factory=list)  # Both found

    @property
    def match_rate(self) -> float:
        """Calculate match rate: matches / (matches + FN + FP)"""
        total = len(self.matches) + len(self.false_negatives) + len(self.false_positives)
        if total == 0:
            return 1.0  # No swings at all = perfect match
        return len(self.matches) / total

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'scale': self.scale,
            'false_negatives': [
                {
                    'annotation_id': ann.annotation_id,
                    'start_source_index': ann.start_source_index,
                    'end_source_index': ann.end_source_index,
                    'direction': ann.direction,
                    'start_price': str(ann.start_price),
                    'end_price': str(ann.end_price),
                }
                for ann in self.false_negatives
            ],
            'false_positives': [
                {
                    'start_index': swing.start_index,
                    'end_index': swing.end_index,
                    'direction': swing.direction,
                    'high_price': swing.high_price,
                    'low_price': swing.low_price,
                    'size': swing.size,
                    'rank': swing.rank,
                }
                for swing in self.false_positives
            ],
            'matches': [
                {
                    'annotation_id': ann.annotation_id,
                    'system_start': swing.start_index,
                    'system_end': swing.end_index,
                }
                for ann, swing in self.matches
            ],
            'match_count': len(self.matches),
            'false_negative_count': len(self.false_negatives),
            'false_positive_count': len(self.false_positives),
            'match_rate': self.match_rate,
        }


class ComparisonAnalyzer:
    """
    Compare user annotations against system detection.

    Uses tolerance-based matching to determine if a user annotation
    corresponds to a system-detected swing.
    """

    def __init__(self, tolerance_pct: float = 0.2, min_tolerance_bars: int = 5):
        """
        Initialize comparison analyzer.

        Args:
            tolerance_pct: Tolerance for matching swing boundaries as a
                          percentage of swing duration. Default 20%.
            min_tolerance_bars: Minimum tolerance in bars, regardless of span.
                               Default 5 bars. For large-scale comparisons,
                               consider setting to 500 for better matching.
        """
        self.tolerance_pct = tolerance_pct
        self.min_tolerance_bars = min_tolerance_bars

    def compare_scale(
        self,
        user_annotations: List[SwingAnnotation],
        system_swings: List[DetectedSwing],
        scale: str
    ) -> ComparisonResult:
        """
        Compare annotations for a single scale.

        Args:
            user_annotations: User-marked swings for this scale
            system_swings: System-detected swings
            scale: Scale identifier (S, M, L, XL)

        Returns:
            ComparisonResult with matches, false negatives, and false positives
        """
        result = ComparisonResult(scale=scale)

        # Track which system swings have been matched
        matched_system_indices = set()

        # For each user annotation, find matching system swing
        for annotation in user_annotations:
            matched_system = None
            matched_idx = None

            for idx, system_swing in enumerate(system_swings):
                if idx in matched_system_indices:
                    continue  # Already matched

                if self._swings_match(annotation, system_swing):
                    matched_system = system_swing
                    matched_idx = idx
                    break

            if matched_system is not None:
                result.matches.append((annotation, matched_system))
                matched_system_indices.add(matched_idx)
            else:
                result.false_negatives.append(annotation)

        # Any unmatched system swings are false positives
        for idx, system_swing in enumerate(system_swings):
            if idx not in matched_system_indices:
                result.false_positives.append(system_swing)

        return result

    def compare_session(
        self,
        session: AnnotationSession,
        bars: List[Bar],
        scales: Optional[List[str]] = None
    ) -> Dict[str, ComparisonResult]:
        """
        Run system detection and compare all scales.

        Args:
            session: Annotation session with user annotations
            bars: Source bars to run detection on
            scales: List of scales to compare. Default: all four scales.

        Returns:
            Dictionary mapping scale -> ComparisonResult
        """
        if scales is None:
            scales = ["XL", "L", "M", "S"]

        # Run system detection
        system_swings = self._run_system_detection(bars)

        results = {}
        for scale in scales:
            user_annotations = session.get_annotations_by_scale(scale)
            result = self.compare_scale(user_annotations, system_swings, scale)
            results[scale] = result

        return results

    def _swings_match(
        self,
        user_ann: SwingAnnotation,
        system_swing: DetectedSwing
    ) -> bool:
        """
        Check if user annotation matches system swing.

        Matching criteria:
        1. Same direction (bull/bear)
        2. Start indices within tolerance
        3. End indices within tolerance

        Tolerance is calculated as percentage of swing duration,
        with a configurable minimum.
        """
        # Direction must match
        if user_ann.direction != system_swing.direction:
            return False

        # Calculate tolerance in bars
        duration = abs(user_ann.end_source_index - user_ann.start_source_index)
        tolerance_bars = max(self.min_tolerance_bars, int(duration * self.tolerance_pct))

        # Check start index match
        start_match = abs(user_ann.start_source_index - system_swing.start_index) <= tolerance_bars

        # Check end index match
        end_match = abs(user_ann.end_source_index - system_swing.end_index) <= tolerance_bars

        return start_match and end_match

    def _run_system_detection(self, bars: List[Bar]) -> List[DetectedSwing]:
        """
        Run the swing detector on bars and normalize output.

        Returns list of DetectedSwing objects for comparison.
        """
        if not bars:
            return []

        # Convert to DataFrame for detect_swings
        df = pd.DataFrame({
            'open': [bar.open for bar in bars],
            'high': [bar.high for bar in bars],
            'low': [bar.low for bar in bars],
            'close': [bar.close for bar in bars]
        })

        # Run detection with standard parameters
        result = detect_swings(
            df,
            lookback=5,
            filter_redundant=True,
            max_pair_distance=2000 if len(bars) > 100_000 else None
        )

        detected_swings = []

        # Convert bull references (downswings: high -> low)
        for ref in result.get('bull_references', []):
            swing = DetectedSwing(
                direction='bull',
                start_index=ref['high_bar_index'],
                end_index=ref['low_bar_index'],
                high_price=ref['high_price'],
                low_price=ref['low_price'],
                size=ref['size'],
                rank=ref.get('rank', 0)
            )
            detected_swings.append(swing)

        # Convert bear references (upswings: low -> high)
        for ref in result.get('bear_references', []):
            swing = DetectedSwing(
                direction='bear',
                start_index=ref['low_bar_index'],
                end_index=ref['high_bar_index'],
                high_price=ref['high_price'],
                low_price=ref['low_price'],
                size=ref['size'],
                rank=ref.get('rank', 0)
            )
            detected_swings.append(swing)

        return detected_swings

    def generate_report(self, results: Dict[str, ComparisonResult]) -> dict:
        """
        Generate summary report from comparison results.

        Args:
            results: Dictionary of scale -> ComparisonResult

        Returns:
            Report dictionary with summary and per-scale breakdown
        """
        total_user = 0
        total_system = 0
        total_matches = 0
        total_fn = 0
        total_fp = 0

        by_scale = {}
        all_false_negatives = []
        all_false_positives = []

        for scale, result in results.items():
            # Count totals
            scale_user = len(result.matches) + len(result.false_negatives)
            scale_system = len(result.matches) + len(result.false_positives)

            total_user += scale_user
            total_system += scale_system
            total_matches += len(result.matches)
            total_fn += len(result.false_negatives)
            total_fp += len(result.false_positives)

            by_scale[scale] = {
                'user_annotations': scale_user,
                'system_detections': scale_system,
                'matches': len(result.matches),
                'false_negatives': len(result.false_negatives),
                'false_positives': len(result.false_positives),
                'match_rate': result.match_rate,
            }

            # Collect false negatives with scale info
            for ann in result.false_negatives:
                all_false_negatives.append({
                    'scale': scale,
                    'start': ann.start_source_index,
                    'end': ann.end_source_index,
                    'direction': ann.direction,
                    'annotation_id': ann.annotation_id,
                })

            # Collect false positives with scale info
            for swing in result.false_positives:
                all_false_positives.append({
                    'scale': scale,
                    'start': swing.start_index,
                    'end': swing.end_index,
                    'direction': swing.direction,
                    'size': swing.size,
                    'rank': swing.rank,
                })

        # Calculate overall match rate
        total_items = total_matches + total_fn + total_fp
        overall_match_rate = total_matches / total_items if total_items > 0 else 1.0

        return {
            'summary': {
                'total_user_annotations': total_user,
                'total_system_detections': total_system,
                'total_matches': total_matches,
                'total_false_negatives': total_fn,
                'total_false_positives': total_fp,
                'overall_match_rate': overall_match_rate,
            },
            'by_scale': by_scale,
            'false_negatives': all_false_negatives,
            'false_positives': all_false_positives,
        }
