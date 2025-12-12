"""
Ground Truth Annotator Module

Provides data models and storage for expert annotation of market swings.
Used to create validated ground truth datasets for swing detection comparison.
"""

from .models import SwingAnnotation, AnnotationSession
from .storage import AnnotationStorage

__all__ = ['SwingAnnotation', 'AnnotationSession', 'AnnotationStorage']
