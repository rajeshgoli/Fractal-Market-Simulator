"""
Data Models for Ground Truth Annotation

Defines the core data structures for storing expert swing annotations
and managing annotation sessions, including review feedback.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class SwingAnnotation:
    """
    A single expert-annotated swing.

    Captures both the visual position (in aggregated view) and the precise
    source data position for accurate comparison with algorithm output.
    """
    annotation_id: str          # UUID
    scale: str                  # "S", "M", "L", "XL"
    direction: str              # "bull" or "bear"
    start_bar_index: int        # Index in aggregated view
    end_bar_index: int          # Index in aggregated view
    start_source_index: int     # Index in source data
    end_source_index: int       # Index in source data
    start_price: Decimal
    end_price: Decimal
    created_at: datetime
    window_id: str              # Which navigation window this was created in

    @classmethod
    def create(
        cls,
        scale: str,
        direction: str,
        start_bar_index: int,
        end_bar_index: int,
        start_source_index: int,
        end_source_index: int,
        start_price: Decimal,
        end_price: Decimal,
        window_id: str
    ) -> 'SwingAnnotation':
        """Factory method to create a new annotation with auto-generated ID and timestamp."""
        return cls(
            annotation_id=str(uuid.uuid4()),
            scale=scale,
            direction=direction,
            start_bar_index=start_bar_index,
            end_bar_index=end_bar_index,
            start_source_index=start_source_index,
            end_source_index=end_source_index,
            start_price=start_price,
            end_price=end_price,
            created_at=datetime.now(timezone.utc),
            window_id=window_id
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            'annotation_id': self.annotation_id,
            'scale': self.scale,
            'direction': self.direction,
            'start_bar_index': self.start_bar_index,
            'end_bar_index': self.end_bar_index,
            'start_source_index': self.start_source_index,
            'end_source_index': self.end_source_index,
            'start_price': str(self.start_price),
            'end_price': str(self.end_price),
            'created_at': self.created_at.isoformat(),
            'window_id': self.window_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SwingAnnotation':
        """Deserialize from dictionary."""
        return cls(
            annotation_id=data['annotation_id'],
            scale=data['scale'],
            direction=data['direction'],
            start_bar_index=data['start_bar_index'],
            end_bar_index=data['end_bar_index'],
            start_source_index=data['start_source_index'],
            end_source_index=data['end_source_index'],
            start_price=Decimal(data['start_price']),
            end_price=Decimal(data['end_price']),
            created_at=datetime.fromisoformat(data['created_at']),
            window_id=data['window_id']
        )


@dataclass
class AnnotationSession:
    """
    A complete annotation session tracking progress across scales.

    Maintains session metadata, all annotations created, and which scales
    have been marked as complete by the annotator.
    """
    session_id: str
    data_file: str              # Path or identifier for source data
    resolution: str             # Source data resolution (e.g., "1m", "5m")
    window_size: int            # Number of bars per annotation window
    created_at: datetime
    annotations: List[SwingAnnotation] = field(default_factory=list)
    completed_scales: List[str] = field(default_factory=list)
    window_offset: int = 0      # Offset into source data (for random window selection)
    status: str = "in_progress" # "in_progress" | "keep" | "discard"

    @classmethod
    def create(
        cls,
        data_file: str,
        resolution: str,
        window_size: int,
        window_offset: int = 0
    ) -> 'AnnotationSession':
        """Factory method to create a new session with auto-generated ID and timestamp."""
        return cls(
            session_id=str(uuid.uuid4()),
            data_file=data_file,
            resolution=resolution,
            window_size=window_size,
            created_at=datetime.now(timezone.utc),
            annotations=[],
            completed_scales=[],
            window_offset=window_offset
        )

    def add_annotation(self, annotation: SwingAnnotation) -> None:
        """Add an annotation to the session."""
        self.annotations.append(annotation)

    def remove_annotation(self, annotation_id: str) -> bool:
        """Remove an annotation by ID. Returns True if found and removed."""
        for i, ann in enumerate(self.annotations):
            if ann.annotation_id == annotation_id:
                self.annotations.pop(i)
                return True
        return False

    def get_annotations_by_scale(self, scale: str) -> List[SwingAnnotation]:
        """Get all annotations for a specific scale."""
        return [a for a in self.annotations if a.scale == scale]

    def mark_scale_complete(self, scale: str) -> None:
        """Mark a scale as completed by the annotator."""
        if scale not in self.completed_scales:
            self.completed_scales.append(scale)

    def is_scale_complete(self, scale: str) -> bool:
        """Check if a scale has been marked as complete."""
        return scale in self.completed_scales

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            'session_id': self.session_id,
            'data_file': self.data_file,
            'resolution': self.resolution,
            'window_size': self.window_size,
            'window_offset': self.window_offset,
            'created_at': self.created_at.isoformat(),
            'annotations': [a.to_dict() for a in self.annotations],
            'completed_scales': self.completed_scales,
            'status': self.status
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AnnotationSession':
        """Deserialize from dictionary."""
        session = cls(
            session_id=data['session_id'],
            data_file=data['data_file'],
            resolution=data['resolution'],
            window_size=data['window_size'],
            created_at=datetime.fromisoformat(data['created_at']),
            annotations=[SwingAnnotation.from_dict(a) for a in data.get('annotations', [])],
            completed_scales=data.get('completed_scales', []),
            window_offset=data.get('window_offset', 0),
            status=data.get('status', 'in_progress')
        )
        return session


@dataclass
class BetterReference:
    """
    Optional user-provided "better" reference when dismissing an FP.

    Captures what the user would have chosen instead of the detected swing.
    """
    high_bar_index: int           # Aggregated view index of the high point
    low_bar_index: int            # Aggregated view index of the low point
    high_price: Decimal           # Price at high point
    low_price: Decimal            # Price at low point

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            'high_bar_index': self.high_bar_index,
            'low_bar_index': self.low_bar_index,
            'high_price': str(self.high_price),
            'low_price': str(self.low_price)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BetterReference':
        """Deserialize from dictionary."""
        return cls(
            high_bar_index=data['high_bar_index'],
            low_bar_index=data['low_bar_index'],
            high_price=Decimal(data['high_price']),
            low_price=Decimal(data['low_price'])
        )


@dataclass
class SwingFeedback:
    """
    Feedback on a single swing (match, FP, or FN).

    Used in Review Mode to capture expert feedback on comparison results
    between annotations and detected swings.
    """
    feedback_id: str              # UUID
    swing_type: str               # "match" | "false_positive" | "false_negative"
    swing_reference: Dict[str, Any]  # annotation_id for user swings, or DetectedSwing data for system
    verdict: str                  # "correct" | "incorrect" | "noise" | "valid_missed" | "explained"
    comment: Optional[str]        # Free text explanation (required for FN, optional for FP)
    category: Optional[str]       # "too_small" | "wrong_direction" | "pattern" | "context" | etc.
    created_at: datetime
    better_reference: Optional[BetterReference] = None  # Optional "what I would have chosen" for FP dismissals

    @classmethod
    def create(
        cls,
        swing_type: str,
        swing_reference: Dict[str, Any],
        verdict: str,
        comment: Optional[str] = None,
        category: Optional[str] = None,
        better_reference: Optional[BetterReference] = None
    ) -> 'SwingFeedback':
        """Factory method with auto-generated ID and timestamp."""
        return cls(
            feedback_id=str(uuid.uuid4()),
            swing_type=swing_type,
            swing_reference=swing_reference,
            verdict=verdict,
            comment=comment,
            category=category,
            created_at=datetime.now(timezone.utc),
            better_reference=better_reference
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        result = {
            'feedback_id': self.feedback_id,
            'swing_type': self.swing_type,
            'swing_reference': self.swing_reference,
            'verdict': self.verdict,
            'comment': self.comment,
            'category': self.category,
            'created_at': self.created_at.isoformat()
        }
        if self.better_reference is not None:
            result['better_reference'] = self.better_reference.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SwingFeedback':
        """Deserialize from dictionary."""
        better_ref = None
        if data.get('better_reference'):
            better_ref = BetterReference.from_dict(data['better_reference'])

        return cls(
            feedback_id=data['feedback_id'],
            swing_type=data['swing_type'],
            swing_reference=data['swing_reference'],
            verdict=data['verdict'],
            comment=data.get('comment'),
            category=data.get('category'),
            created_at=datetime.fromisoformat(data['created_at']),
            better_reference=better_ref
        )


# Phase order for ReviewSession
REVIEW_PHASES = ["matches", "fp_sample", "fn_feedback", "complete"]

# Schema version for backward-compatible evolution
REVIEW_SCHEMA_VERSION = 1


@dataclass
class ReviewSession:
    """
    Review feedback for a single annotation session.

    Tracks the three-phase review process: matches, false positive sample,
    and false negative feedback.
    """
    review_id: str                        # UUID
    session_id: str                       # Links to AnnotationSession
    phase: str                            # "matches" | "fp_sample" | "fn_feedback" | "complete"
    match_feedback: List[SwingFeedback] = field(default_factory=list)
    fp_feedback: List[SwingFeedback] = field(default_factory=list)
    fn_feedback: List[SwingFeedback] = field(default_factory=list)
    fp_sample_indices: List[int] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    version: int = REVIEW_SCHEMA_VERSION  # Schema version for backward compatibility

    @classmethod
    def create(cls, session_id: str) -> 'ReviewSession':
        """Factory method to create new review session."""
        return cls(
            review_id=str(uuid.uuid4()),
            session_id=session_id,
            phase="matches",
            match_feedback=[],
            fp_feedback=[],
            fn_feedback=[],
            fp_sample_indices=[],
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            version=REVIEW_SCHEMA_VERSION
        )

    def add_feedback(self, feedback: SwingFeedback) -> None:
        """Add feedback to appropriate list based on swing_type."""
        if feedback.swing_type == "match":
            self.match_feedback.append(feedback)
        elif feedback.swing_type == "false_positive":
            self.fp_feedback.append(feedback)
        elif feedback.swing_type == "false_negative":
            self.fn_feedback.append(feedback)

    def advance_phase(self) -> bool:
        """
        Move to next phase. Returns False if already complete.

        Phase order: matches -> fp_sample -> fn_feedback -> complete
        """
        if self.phase == "complete":
            return False

        current_index = REVIEW_PHASES.index(self.phase)
        next_index = current_index + 1

        if next_index < len(REVIEW_PHASES):
            self.phase = REVIEW_PHASES[next_index]
            if self.phase == "complete":
                self.completed_at = datetime.now(timezone.utc)
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            'review_id': self.review_id,
            'session_id': self.session_id,
            'version': self.version,
            'phase': self.phase,
            'match_feedback': [f.to_dict() for f in self.match_feedback],
            'fp_feedback': [f.to_dict() for f in self.fp_feedback],
            'fn_feedback': [f.to_dict() for f in self.fn_feedback],
            'fp_sample_indices': self.fp_sample_indices,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewSession':
        """Deserialize from dictionary."""
        return cls(
            review_id=data['review_id'],
            session_id=data['session_id'],
            phase=data['phase'],
            match_feedback=[SwingFeedback.from_dict(f) for f in data.get('match_feedback', [])],
            fp_feedback=[SwingFeedback.from_dict(f) for f in data.get('fp_feedback', [])],
            fn_feedback=[SwingFeedback.from_dict(f) for f in data.get('fn_feedback', [])],
            fp_sample_indices=data.get('fp_sample_indices', []),
            started_at=datetime.fromisoformat(data['started_at']),
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            version=data.get('version', 1)  # Default to 1 for legacy data without version
        )
