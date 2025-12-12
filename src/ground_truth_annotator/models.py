"""
Data Models for Ground Truth Annotation

Defines the core data structures for storing expert swing annotations
and managing annotation sessions.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional


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

    @classmethod
    def create(
        cls,
        data_file: str,
        resolution: str,
        window_size: int
    ) -> 'AnnotationSession':
        """Factory method to create a new session with auto-generated ID and timestamp."""
        return cls(
            session_id=str(uuid.uuid4()),
            data_file=data_file,
            resolution=resolution,
            window_size=window_size,
            created_at=datetime.now(timezone.utc),
            annotations=[],
            completed_scales=[]
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
            'created_at': self.created_at.isoformat(),
            'annotations': [a.to_dict() for a in self.annotations],
            'completed_scales': self.completed_scales
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
            completed_scales=data.get('completed_scales', [])
        )
        return session
