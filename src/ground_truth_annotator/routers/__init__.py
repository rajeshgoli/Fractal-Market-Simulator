"""
Ground Truth Annotator API routers.

This package contains modular FastAPI routers for each functional domain:
- annotations: CRUD operations for swing annotations
- session: Session state management
- cascade: XL -> L -> M -> S cascade workflow
- comparison: User vs system swing comparison
- review: Review mode for validating annotations
- discretization: Discretization event log generation
- replay: Replay View playback and swing detection
"""

from .annotations import router as annotations_router
from .session import router as session_router
from .cascade import router as cascade_router
from .comparison import router as comparison_router
from .review import router as review_router
from .discretization import router as discretization_router
from .replay import router as replay_router

__all__ = [
    "annotations_router",
    "session_router",
    "cascade_router",
    "comparison_router",
    "review_router",
    "discretization_router",
    "replay_router",
]
