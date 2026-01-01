"""
Router package for Replay View Server.

Split routers (Issue #398):
- replay.py: Core advance/reverse/calibrate endpoints
- dag.py: DAG state and lineage endpoints
- reference.py: Reference Layer state and level endpoints
- config.py: Detection config endpoints
- feedback.py: Playback feedback endpoint
"""

from .replay import router as replay_router
from .dag import router as dag_router
from .reference import router as reference_router
from .config import router as config_router
from .feedback import router as feedback_router

__all__ = [
    "replay_router",
    "dag_router",
    "reference_router",
    "config_router",
    "feedback_router",
]
