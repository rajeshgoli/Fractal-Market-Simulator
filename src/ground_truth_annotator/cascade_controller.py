"""
Cascade Controller for Ground Truth Annotation

Manages the XL → L → M → S scale progression workflow where the user
annotates swings at progressively finer scales, with completed scales
shown as reference context.
"""

from typing import List, Optional, Tuple

from .models import AnnotationSession, SwingAnnotation
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.types import Bar


class CascadeController:
    """
    Manages XL → L → M → S workflow state.

    Controls scale progression, aggregation levels, and reference annotation
    display for the cascading annotation workflow.
    """

    SCALE_ORDER = ["XL", "L", "M", "S"]

    # Target bar counts for each scale
    # Designed for ~50K source bar windows
    SCALE_TARGET_BARS = {
        "XL": 50,    # ~1000:1 compression for 50K window
        "L": 200,    # ~250:1 compression
        "M": 800,    # ~62:1 compression
        "S": None,   # Source resolution (no aggregation)
    }

    def __init__(
        self,
        session: AnnotationSession,
        source_bars: List[Bar],
        aggregator: BarAggregator
    ):
        """
        Initialize cascade controller for a session.

        Args:
            session: The annotation session to manage
            source_bars: Source OHLC bars for the window
            aggregator: BarAggregator instance for bar aggregation
        """
        self._session = session
        self._source_bars = source_bars
        self._aggregator = aggregator

        # Determine starting scale based on completed scales
        self._current_scale_index = 0
        for i, scale in enumerate(self.SCALE_ORDER):
            if scale in session.completed_scales:
                self._current_scale_index = i + 1

        # Clamp to valid range
        if self._current_scale_index >= len(self.SCALE_ORDER):
            self._current_scale_index = len(self.SCALE_ORDER) - 1

        # Pre-compute aggregated bars for each scale
        self._scale_bars: dict = {}
        self._scale_aggregation_maps: dict = {}
        self._precompute_scale_bars()

    def _precompute_scale_bars(self) -> None:
        """Pre-compute aggregated bars for all scales."""
        for scale in self.SCALE_ORDER:
            target = self.SCALE_TARGET_BARS[scale]

            if target is None:
                # S scale: use source bars directly
                self._scale_bars[scale] = self._source_bars.copy()
                self._scale_aggregation_maps[scale] = {
                    i: (i, i) for i in range(len(self._source_bars))
                }
            else:
                # Aggregate to target count
                aggregated = self._aggregator.aggregate_to_target_bars(target)
                self._scale_bars[scale] = aggregated

                # Build aggregation map (agg_index -> source indices range)
                agg_map = {}
                if len(self._source_bars) > target:
                    bars_per_candle = len(self._source_bars) // target
                    for agg_idx in range(len(aggregated)):
                        source_start = agg_idx * bars_per_candle
                        source_end = min(
                            source_start + bars_per_candle - 1,
                            len(self._source_bars) - 1
                        )
                        agg_map[agg_idx] = (source_start, source_end)
                else:
                    # No aggregation needed
                    for i in range(len(aggregated)):
                        agg_map[i] = (i, i)

                self._scale_aggregation_maps[scale] = agg_map

    @property
    def session(self) -> AnnotationSession:
        """Get the annotation session."""
        return self._session

    def get_current_scale(self) -> str:
        """Return current scale being annotated."""
        return self.SCALE_ORDER[self._current_scale_index]

    def get_current_scale_index(self) -> int:
        """Return current scale index (0-3)."""
        return self._current_scale_index

    def get_completed_scales(self) -> List[str]:
        """Return list of completed scales."""
        return self._session.completed_scales.copy()

    def get_bars_for_scale(self, scale: str) -> List[Bar]:
        """
        Return appropriately aggregated bars for a scale.

        Args:
            scale: Scale identifier ("XL", "L", "M", "S")

        Returns:
            List of bars aggregated for the specified scale

        Raises:
            ValueError: If scale is invalid
        """
        if scale not in self.SCALE_ORDER:
            raise ValueError(f"Invalid scale: {scale}. Must be one of {self.SCALE_ORDER}")

        return self._scale_bars[scale].copy()

    def get_aggregation_map(self, scale: str) -> dict:
        """
        Get the aggregation map for a scale.

        Maps aggregated bar index to (source_start_index, source_end_index).

        Args:
            scale: Scale identifier

        Returns:
            Dict mapping agg_index -> (source_start, source_end)
        """
        if scale not in self.SCALE_ORDER:
            raise ValueError(f"Invalid scale: {scale}")

        return self._scale_aggregation_maps[scale].copy()

    def get_reference_scale(self) -> Optional[str]:
        """
        Get the reference scale to display (most recently completed).

        Returns:
            Scale string or None if no scales completed yet
        """
        if not self._session.completed_scales:
            return None

        # Return the scale immediately before current
        if self._current_scale_index > 0:
            return self.SCALE_ORDER[self._current_scale_index - 1]

        return None

    def get_reference_annotations(self) -> List[SwingAnnotation]:
        """
        Return annotations from completed larger scales for reference display.

        Returns:
            List of annotations from the reference scale (if any)
        """
        reference_scale = self.get_reference_scale()
        if reference_scale is None:
            return []

        return self._session.get_annotations_by_scale(reference_scale)

    def get_all_reference_annotations(self) -> List[SwingAnnotation]:
        """
        Return annotations from all completed scales.

        Returns:
            List of all annotations from completed scales
        """
        annotations = []
        for scale in self._session.completed_scales:
            annotations.extend(self._session.get_annotations_by_scale(scale))
        return annotations

    def advance_to_next_scale(self) -> bool:
        """
        Mark current scale complete and move to next.

        Returns:
            True if advanced to next scale, False if already at last scale
        """
        current_scale = self.get_current_scale()

        # Mark current scale as complete
        self._session.mark_scale_complete(current_scale)

        # Move to next scale if not at end
        if self._current_scale_index < len(self.SCALE_ORDER) - 1:
            self._current_scale_index += 1
            return True

        return False

    def skip_remaining_scales(self) -> List[str]:
        """
        Skip all remaining scales without review.

        Marks the current scale as complete (if annotated) and all remaining
        scales as skipped. Used for "Skip to FP Review" workflow.

        Returns:
            List of scales that were marked as skipped
        """
        current_scale = self.get_current_scale()
        skipped = []

        # Mark current scale as complete (user finished annotating it)
        self._session.mark_scale_complete(current_scale)

        # Mark all remaining scales as skipped
        for i in range(self._current_scale_index + 1, len(self.SCALE_ORDER)):
            scale = self.SCALE_ORDER[i]
            self._session.mark_scale_skipped(scale)
            skipped.append(scale)

        # Move to end
        self._current_scale_index = len(self.SCALE_ORDER) - 1

        return skipped

    def is_scale_complete(self, scale: str) -> bool:
        """Check if a specific scale has been completed."""
        return self._session.is_scale_complete(scale)

    def is_session_complete(self) -> bool:
        """True if all scales have been annotated or skipped."""
        return all(
            scale in self._session.completed_scales or scale in self._session.skipped_scales
            for scale in self.SCALE_ORDER
        )

    def get_progress(self) -> Tuple[int, int]:
        """
        Get annotation progress as (completed, total).

        Returns:
            Tuple of (completed_scales, total_scales)
        """
        completed = len(self._session.completed_scales)
        return (completed, len(self.SCALE_ORDER))

    def get_scale_info(self, scale: str) -> dict:
        """
        Get information about a specific scale.

        Args:
            scale: Scale identifier

        Returns:
            Dict with scale information
        """
        if scale not in self.SCALE_ORDER:
            raise ValueError(f"Invalid scale: {scale}")

        bars = self._scale_bars[scale]
        target = self.SCALE_TARGET_BARS[scale]
        annotations = self._session.get_annotations_by_scale(scale)

        return {
            "scale": scale,
            "target_bars": target,
            "actual_bars": len(bars),
            "compression_ratio": len(self._source_bars) / len(bars) if bars else 0,
            "annotation_count": len(annotations),
            "is_complete": self._session.is_scale_complete(scale),
            "is_skipped": self._session.is_scale_skipped(scale),
        }

    def get_cascade_state(self) -> dict:
        """
        Get full cascade state for API response.

        Returns:
            Dict with complete cascade state
        """
        completed, total = self.get_progress()
        current_scale = self.get_current_scale()
        reference_scale = self.get_reference_scale()

        return {
            "current_scale": current_scale,
            "current_scale_index": self._current_scale_index,
            "reference_scale": reference_scale,
            "completed_scales": self._session.completed_scales.copy(),
            "skipped_scales": self._session.skipped_scales.copy(),
            "scales_remaining": total - completed,
            "is_complete": self.is_session_complete(),
            "scale_info": {
                scale: self.get_scale_info(scale)
                for scale in self.SCALE_ORDER
            },
        }

    def reset_to_scale(self, scale: str) -> None:
        """
        Reset cascade state to a specific scale (for corrections).

        Removes the scale from completed and skipped lists, resets current index.

        Args:
            scale: Scale to reset to
        """
        if scale not in self.SCALE_ORDER:
            raise ValueError(f"Invalid scale: {scale}")

        scale_index = self.SCALE_ORDER.index(scale)

        # Remove this scale and all subsequent from completed and skipped
        for s in self.SCALE_ORDER[scale_index:]:
            if s in self._session.completed_scales:
                self._session.completed_scales.remove(s)
            if s in self._session.skipped_scales:
                self._session.skipped_scales.remove(s)

        self._current_scale_index = scale_index
