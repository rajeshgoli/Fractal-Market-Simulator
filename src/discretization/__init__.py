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

from .discretizer import (
    Discretizer,
    DiscretizerConfig,
    DISCRETIZER_VERSION,
)

from .io import (
    write_log,
    read_log,
    compare_configs,
    compare_configs_detail,
    config_compatible,
    get_default_config,
)

__all__ = [
    # Discretizer
    "Discretizer",
    "DiscretizerConfig",
    "DISCRETIZER_VERSION",
    # Configuration (schema)
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
    # I/O
    "write_log",
    "read_log",
    "compare_configs",
    "compare_configs_detail",
    "config_compatible",
    "get_default_config",
]
