"""Centralized constants for swing analysis."""

# Extended symmetric FIB grid for structural separation
# Standard levels have asymmetric gaps; extended grid fills voids where valid reversals occur
SEPARATION_FIB_LEVELS = [
    0.236, 0.382, 0.5, 0.618, 0.786, 1.0,
    1.236, 1.382, 1.5, 1.618, 1.786, 2.0
]

# Extended FIB ratios for confluence scoring (includes 0.0 for origin)
CONFLUENCE_FIB_RATIOS = [0.0] + SEPARATION_FIB_LEVELS
