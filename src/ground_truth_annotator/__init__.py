"""
Ground Truth Annotator Module

Provides data models and storage for expert annotation of market swings.
Used to create validated ground truth datasets for swing detection comparison.

Key components:
- SwingAnnotation: A single annotated swing
- AnnotationSession: Collection of annotations with metadata
- AnnotationStorage: JSON-backed persistence layer
- CascadeController: XL → L → M → S scale progression workflow
"""

from .models import SwingAnnotation, AnnotationSession
from .storage import AnnotationStorage
from .cascade_controller import CascadeController

__all__ = [
    'SwingAnnotation',
    'AnnotationSession',
    'AnnotationStorage',
    'CascadeController',
]
