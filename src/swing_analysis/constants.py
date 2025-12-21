"""Centralized constants for swing analysis."""

# Extended Fibonacci level set for discretization event logging.
# Includes negative values for stop-run detection and extension levels.

DISCRETIZATION_LEVELS = [
    -0.15,   # Deep stop-run (L/XL invalidation threshold)
    -0.10,   # Stop-run (S/M invalidation threshold)
     0.00,   # Defended pivot
     0.236,  # Shallow retracement
     0.382,  # Standard retracement
     0.50,   # Half retracement
     0.618,  # Golden retracement
     0.786,  # Deep retracement
     1.00,   # Origin
     1.236,  # Shallow extension
     1.382,  # Standard extension / Decision zone start
     1.50,   # Decision zone
     1.618,  # Golden extension / Decision zone end
     1.786,  # Deep extension
     2.00,   # Completion target
     2.236,  # Extended completion
]

# Version identifier for corpus comparability.
# Bump this when modifying DISCRETIZATION_LEVELS to track which level set
# was used to produce a given event log.
DISCRETIZATION_LEVEL_SET_VERSION = "v1.0"
