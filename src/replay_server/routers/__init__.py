"""
Router package for Replay View Server.

Routers (Issue #410 cleanup):
- dag.py: All DAG operations (init, advance, reverse, state, lineage, config, events)
- reference.py: Reference Layer state and level endpoints
- feedback.py: Playback feedback endpoint
- auth.py: OAuth authentication (Google, GitHub)
"""

from .dag import router as dag_router
from .reference import router as reference_router
from .feedback import router as feedback_router
from .auth import router as auth_router

__all__ = [
    "dag_router",
    "reference_router",
    "feedback_router",
    "auth_router",
]
