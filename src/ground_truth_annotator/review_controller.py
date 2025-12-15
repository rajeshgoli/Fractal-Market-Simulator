"""
Review Controller for Ground Truth Annotation

Manages the Review Mode workflow: matches → FP sample → FN feedback → complete.
Handles phase transitions, FP sampling, and progress tracking.
"""

import random
from typing import Any, Dict, List, Optional, Tuple

from .models import ReviewSession, SwingFeedback, BetterReference, REVIEW_PHASES
from .storage import AnnotationStorage, ReviewStorage
from .comparison_analyzer import ComparisonResult, DetectedSwing


class ReviewController:
    """
    Manages Review Mode workflow state.

    Coordinates between annotation data, comparison results, and review feedback.
    """

    PHASE_ORDER = REVIEW_PHASES  # ["matches", "fp_sample", "fn_feedback", "complete"]
    FP_SAMPLE_TARGET = 20  # Max FPs to sample for review

    def __init__(
        self,
        session_id: str,
        annotation_storage: AnnotationStorage,
        review_storage: ReviewStorage,
        comparison_results: Dict[str, ComparisonResult]
    ):
        """
        Initialize controller with annotation session and comparison results.

        Args:
            session_id: The annotation session to review
            annotation_storage: For accessing annotations
            review_storage: For persisting review feedback
            comparison_results: Pre-computed comparison (from ComparisonAnalyzer)
        """
        self._session_id = session_id
        self._annotation_storage = annotation_storage
        self._review_storage = review_storage
        self._comparison_results = comparison_results

        # Cache the review session
        self._review: Optional[ReviewSession] = None

        # Cache sampled FPs (populated on first get_or_create_review)
        self._fp_sample: List[Tuple[DetectedSwing, str]] = []  # (swing, scale) pairs

    def get_or_create_review(self) -> ReviewSession:
        """Get existing review or create new one. Samples FPs on creation."""
        if self._review is not None:
            return self._review

        # Try to load existing review
        self._review = self._review_storage.get_review(self._session_id)

        if self._review is None:
            # Create new review session
            self._review = self._review_storage.create_review(self._session_id)

            # Sample FPs and store indices
            fps_by_scale = self._collect_fps_by_scale()
            sampled, indices = self.sample_false_positives(fps_by_scale, self.FP_SAMPLE_TARGET)
            self._fp_sample = sampled
            self._review.fp_sample_indices = indices

            # Persist the new review with sample indices
            self._review_storage.save_review(self._review)
        else:
            # Reconstruct FP sample from stored indices
            self._reconstruct_fp_sample()

        return self._review

    def _collect_fps_by_scale(self) -> Dict[str, List[DetectedSwing]]:
        """Collect false positives organized by scale."""
        fps_by_scale: Dict[str, List[DetectedSwing]] = {}
        for scale, result in self._comparison_results.items():
            if result.false_positives:
                fps_by_scale[scale] = result.false_positives
        return fps_by_scale

    def _reconstruct_fp_sample(self) -> None:
        """Reconstruct FP sample from stored indices when loading existing review."""
        if self._review is None:
            return

        # The indices are stored per-scale in order: XL, L, M, S
        self._fp_sample = []
        fps_by_scale = self._collect_fps_by_scale()

        # We need to map stored indices back to FPs
        # indices are stored as flat list, need to map back
        # For simplicity, we'll re-sample but respect the original indices
        # Actually, store as (scale, local_index) tuples for proper reconstruction

        # For now, just collect all sampled FPs in order
        # The fp_sample_indices stores flattened indices across all scales
        all_fps: List[Tuple[DetectedSwing, str]] = []
        for scale in ["XL", "L", "M", "S"]:
            for fp in fps_by_scale.get(scale, []):
                all_fps.append((fp, scale))

        for idx in self._review.fp_sample_indices:
            if idx < len(all_fps):
                self._fp_sample.append(all_fps[idx])

    def get_current_phase(self) -> str:
        """Return current review phase."""
        review = self.get_or_create_review()
        return review.phase

    def get_phase_progress(self) -> Tuple[int, int]:
        """Return (completed_items, total_items) for current phase."""
        review = self.get_or_create_review()
        phase = review.phase

        if phase == "matches":
            total = sum(len(r.matches) for r in self._comparison_results.values())
            completed = len(review.match_feedback)
            return (completed, total)

        elif phase == "fp_sample":
            total = len(self._fp_sample)
            completed = len(review.fp_feedback)
            return (completed, total)

        elif phase == "fn_feedback":
            total = sum(len(r.false_negatives) for r in self._comparison_results.values())
            completed = len(review.fn_feedback)
            return (completed, total)

        elif phase == "complete":
            return (0, 0)

        return (0, 0)

    def get_matches(self) -> List[dict]:
        """
        Get matched swings for Phase 1 review.

        Returns list of dicts with:
        - annotation: SwingAnnotation data
        - system_swing: DetectedSwing data
        - feedback: existing SwingFeedback if any
        """
        review = self.get_or_create_review()
        matches_list = []

        for scale, result in self._comparison_results.items():
            for annotation, system_swing in result.matches:
                # Find existing feedback for this match
                feedback = self._find_feedback(
                    review.match_feedback,
                    "match",
                    annotation.annotation_id
                )

                matches_list.append({
                    "annotation": annotation.to_dict(),
                    "system_swing": {
                        "direction": system_swing.direction,
                        "start_index": system_swing.start_index,
                        "end_index": system_swing.end_index,
                        "high_price": system_swing.high_price,
                        "low_price": system_swing.low_price,
                        "size": system_swing.size,
                        "rank": system_swing.rank,
                    },
                    "scale": scale,
                    "feedback": feedback.to_dict() if feedback else None
                })

        return matches_list

    def get_fp_sample(self) -> List[dict]:
        """
        Get sampled false positives for Phase 2 review.

        Returns list of dicts with:
        - system_swing: DetectedSwing data
        - scale: which scale this FP is from
        - feedback: existing SwingFeedback if any
        """
        review = self.get_or_create_review()
        fp_list = []

        for idx, (swing, scale) in enumerate(self._fp_sample):
            # Find existing feedback for this FP
            feedback = self._find_fp_feedback(review.fp_feedback, idx)

            fp_list.append({
                "system_swing": {
                    "direction": swing.direction,
                    "start_index": swing.start_index,
                    "end_index": swing.end_index,
                    "high_price": swing.high_price,
                    "low_price": swing.low_price,
                    "size": swing.size,
                    "rank": swing.rank,
                },
                "scale": scale,
                "sample_index": idx,
                "feedback": feedback.to_dict() if feedback else None
            })

        return fp_list

    def get_false_negatives(self) -> List[dict]:
        """
        Get all false negatives for Phase 3 review.

        Returns list of dicts with:
        - annotation: SwingAnnotation data
        - feedback: existing SwingFeedback if any
        """
        review = self.get_or_create_review()
        fn_list = []

        for scale, result in self._comparison_results.items():
            for annotation in result.false_negatives:
                # Find existing feedback for this FN
                feedback = self._find_feedback(
                    review.fn_feedback,
                    "false_negative",
                    annotation.annotation_id
                )

                fn_list.append({
                    "annotation": annotation.to_dict(),
                    "scale": scale,
                    "feedback": feedback.to_dict() if feedback else None
                })

        return fn_list

    def _find_feedback(
        self,
        feedback_list: List[SwingFeedback],
        swing_type: str,
        annotation_id: str
    ) -> Optional[SwingFeedback]:
        """Find feedback by annotation_id in a feedback list."""
        for fb in feedback_list:
            if fb.swing_type == swing_type:
                ref = fb.swing_reference
                if ref.get("annotation_id") == annotation_id:
                    return fb
        return None

    def _find_fp_feedback(
        self,
        feedback_list: List[SwingFeedback],
        sample_index: int
    ) -> Optional[SwingFeedback]:
        """Find feedback by sample index for false positives."""
        for fb in feedback_list:
            if fb.swing_type == "false_positive":
                ref = fb.swing_reference
                if ref.get("sample_index") == sample_index:
                    return fb
        return None

    def submit_feedback(
        self,
        swing_type: str,
        swing_reference: dict,
        verdict: str,
        comment: Optional[str] = None,
        category: Optional[str] = None,
        better_reference: Optional[BetterReference] = None
    ) -> SwingFeedback:
        """
        Submit feedback for a swing.

        Args:
            swing_type: "match" | "false_positive" | "false_negative"
            swing_reference: Identifies which swing (annotation_id or FP index)
            verdict: "correct" | "incorrect" | "noise" | "valid_missed" | "explained"
            comment: Free text (required for FN)
            category: Optional categorization
            better_reference: Optional "what I would have chosen" for FP dismissals

        Raises:
            ValueError: If FN submitted without comment
        """
        if swing_type == "false_negative" and not comment:
            raise ValueError("False negative feedback requires a comment explaining the miss")

        review = self.get_or_create_review()

        feedback = SwingFeedback.create(
            swing_type=swing_type,
            swing_reference=swing_reference,
            verdict=verdict,
            comment=comment,
            category=category,
            better_reference=better_reference
        )

        review.add_feedback(feedback)
        self._review_storage.save_review(review)

        return feedback

    def advance_phase(self) -> bool:
        """
        Mark current phase complete and advance to next.

        Returns True if advanced, False if already complete.
        Validates all required feedback submitted before advancing.
        """
        review = self.get_or_create_review()

        if review.phase == "complete":
            return False

        # Advance the phase
        result = review.advance_phase()

        if result:
            self._review_storage.save_review(review)

        return result

    def is_complete(self) -> bool:
        """True if all phases complete."""
        review = self.get_or_create_review()
        return review.phase == "complete"

    def get_summary(self) -> dict:
        """
        Get review session summary.

        Returns:
            {
                "session_id": str,
                "review_id": str,
                "phase": str,
                "matches": {"total": int, "reviewed": int, "correct": int, "incorrect": int},
                "false_positives": {"sampled": int, "reviewed": int, "noise": int, "valid": int},
                "false_negatives": {"total": int, "explained": int},
                "started_at": str,
                "completed_at": str or None
            }
        """
        review = self.get_or_create_review()

        # Count matches
        total_matches = sum(len(r.matches) for r in self._comparison_results.values())
        correct_count = sum(1 for fb in review.match_feedback if fb.verdict == "correct")
        incorrect_count = sum(1 for fb in review.match_feedback if fb.verdict == "incorrect")

        # Count false positives
        sampled_count = len(self._fp_sample)
        noise_count = sum(1 for fb in review.fp_feedback if fb.verdict == "noise")
        valid_fp_count = sum(1 for fb in review.fp_feedback if fb.verdict != "noise")

        # Count false negatives
        total_fn = sum(len(r.false_negatives) for r in self._comparison_results.values())
        explained_count = len(review.fn_feedback)

        return {
            "session_id": self._session_id,
            "review_id": review.review_id,
            "phase": review.phase,
            "matches": {
                "total": total_matches,
                "reviewed": len(review.match_feedback),
                "correct": correct_count,
                "incorrect": incorrect_count
            },
            "false_positives": {
                "sampled": sampled_count,
                "reviewed": len(review.fp_feedback),
                "noise": noise_count,
                "valid": valid_fp_count
            },
            "false_negatives": {
                "total": total_fn,
                "explained": explained_count
            },
            "started_at": review.started_at.isoformat(),
            "completed_at": review.completed_at.isoformat() if review.completed_at else None
        }

    @staticmethod
    def sample_false_positives(
        fps_by_scale: Dict[str, List[DetectedSwing]],
        target: int = 20
    ) -> Tuple[List[Tuple[DetectedSwing, str]], List[int]]:
        """
        Sample FPs stratified by scale.

        Algorithm:
        1. If total FPs <= target, return all
        2. Otherwise, allocate proportionally with minimum 2 per scale
        3. Random sample within each scale's allocation
        4. Return (sampled_fps_with_scale, original_indices)
        """
        # Build flat list with global indices
        all_fps: List[Tuple[DetectedSwing, str, int]] = []  # (swing, scale, global_idx)
        for scale in ["XL", "L", "M", "S"]:
            for fp in fps_by_scale.get(scale, []):
                all_fps.append((fp, scale, len(all_fps)))

        total_fps = len(all_fps)

        if total_fps <= target:
            # Return all with indices
            sampled = [(fp, scale) for fp, scale, _ in all_fps]
            indices = [idx for _, _, idx in all_fps]
            return sampled, indices

        # Stratified sampling
        sampled: List[Tuple[DetectedSwing, str]] = []
        indices: List[int] = []
        scales = ["XL", "L", "M", "S"]

        # Calculate allocations
        remaining_target = target
        allocations: Dict[str, int] = {}

        for scale in scales:
            scale_fps = fps_by_scale.get(scale, [])
            if not scale_fps:
                allocations[scale] = 0
                continue

            # Proportional allocation, minimum 2 per scale with FPs
            proportion = len(scale_fps) / total_fps
            allocation = max(2, int(proportion * target))
            allocation = min(allocation, len(scale_fps))
            allocations[scale] = allocation

        # Adjust to not exceed target
        total_allocated = sum(allocations.values())
        if total_allocated > target:
            # Reduce proportionally, starting from largest allocations
            excess = total_allocated - target
            sorted_scales = sorted(
                [s for s in scales if allocations[s] > 2],
                key=lambda s: allocations[s],
                reverse=True
            )
            for scale in sorted_scales:
                if excess <= 0:
                    break
                reduce_by = min(excess, allocations[scale] - 2)
                allocations[scale] -= reduce_by
                excess -= reduce_by

        # Sample from each scale
        global_idx_offset = 0
        for scale in scales:
            scale_fps = fps_by_scale.get(scale, [])
            if not scale_fps:
                continue

            allocation = allocations[scale]
            if allocation > 0:
                # Random sample indices within this scale
                local_indices = random.sample(range(len(scale_fps)), allocation)
                for local_idx in local_indices:
                    sampled.append((scale_fps[local_idx], scale))
                    indices.append(global_idx_offset + local_idx)

            global_idx_offset += len(scale_fps)

        # Cap at target
        return sampled[:target], indices[:target]
