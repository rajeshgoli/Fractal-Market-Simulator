"""
Discretization Pipeline

Converts continuous OHLC + detected swings into a log of structural events.
This enables measurement of market structure rules as falsifiable hypotheses.
"""

from .schema import (
    # Configuration
    DiscretizationConfig,
    # Metadata
    DiscretizationMeta,
    # Side-channels
    EffortAnnotation,
    ShockAnnotation,
    ParentContext,
    # Core schema
    SwingEntry,
    DiscretizationEvent,
    DiscretizationLog,
    # Event types
    EventType,
    # Validation
    validate_log,
    ValidationError,
    # Schema version
    SCHEMA_VERSION,
)

__all__ = [
    # Configuration
    "DiscretizationConfig",
    # Metadata
    "DiscretizationMeta",
    # Side-channels
    "EffortAnnotation",
    "ShockAnnotation",
    "ParentContext",
    # Core schema
    "SwingEntry",
    "DiscretizationEvent",
    "DiscretizationLog",
    # Event types
    "EventType",
    # Validation
    "validate_log",
    "ValidationError",
    # Schema version
    "SCHEMA_VERSION",
]
