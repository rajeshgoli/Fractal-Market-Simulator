"""
Validation Module

Provides systematic validation capabilities for swing detection logic across
diverse historical market datasets.

Components:
- ValidationSession: Session management and progress tracking
- IssueCatalog: Issue documentation and classification system

Author: Generated for Market Simulator Project
"""

from .session import ValidationSession, ValidationProgress
from .issue_catalog import ValidationIssue, IssueCatalog

__all__ = ['ValidationSession', 'ValidationProgress', 'ValidationIssue', 'IssueCatalog']