"""
Resolution Configuration Module

Provides resolution-agnostic configuration for the market simulator.
Converts resolution strings to minutes and derives appropriate timeframes
for multi-scale analysis.

Supported resolutions: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


# Resolution string to minutes mapping
RESOLUTION_MINUTES: Dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
    "1mo": 43200,  # ~30 days
}

# All supported resolution strings
SUPPORTED_RESOLUTIONS: List[str] = list(RESOLUTION_MINUTES.keys())


@dataclass
class ResolutionConfig:
    """Configuration derived from source data resolution."""

    source_resolution: str  # Original resolution string (e.g., "5m")
    source_minutes: int     # Source resolution in minutes

    # Aggregation timeframes available (only >= source resolution)
    available_timeframes: List[int]

    # Default scale aggregations for this resolution
    default_aggregations: Dict[str, int]

    # Allowed aggregation values for this resolution
    allowed_aggregations: List[int]

    def __post_init__(self):
        """Validate configuration."""
        if self.source_minutes not in self.available_timeframes:
            raise ValueError(
                f"Source resolution {self.source_minutes}m not in available timeframes"
            )


def parse_resolution(resolution: str) -> int:
    """
    Parse resolution string to minutes.

    Args:
        resolution: Resolution string (e.g., "5m", "1h", "1d")

    Returns:
        Resolution in minutes

    Raises:
        ValueError: If resolution is not supported
    """
    resolution = resolution.lower().strip()

    if resolution not in RESOLUTION_MINUTES:
        raise ValueError(
            f"Unsupported resolution '{resolution}'. "
            f"Supported: {', '.join(SUPPORTED_RESOLUTIONS)}"
        )

    return RESOLUTION_MINUTES[resolution]


def get_available_timeframes(source_minutes: int) -> List[int]:
    """
    Get available aggregation timeframes for a given source resolution.

    Only timeframes >= source resolution are available.

    Args:
        source_minutes: Source data resolution in minutes

    Returns:
        List of available timeframe values in minutes
    """
    # Standard analysis timeframes
    all_timeframes = [1, 5, 15, 30, 60, 240, 1440, 10080]

    # Filter to timeframes >= source resolution
    return [tf for tf in all_timeframes if tf >= source_minutes]


def get_default_aggregations(source_minutes: int) -> Dict[str, int]:
    """
    Get default scale aggregations for a given source resolution.

    The aggregations are scaled relative to the source resolution:
    - S: Source resolution (finest available)
    - M: Next standard timeframe up (or same if already large)
    - L: Further up the timeframe ladder
    - XL: Largest reasonable timeframe for the scale

    Args:
        source_minutes: Source data resolution in minutes

    Returns:
        Dict mapping scale names to aggregation minutes
    """
    available = get_available_timeframes(source_minutes)

    # Pick aggregations from available timeframes
    # Goal: S=smallest, then progressively larger for M, L, XL
    if len(available) >= 4:
        return {
            "S": available[0],
            "M": available[min(1, len(available)-1)],
            "L": available[min(2, len(available)-1)],
            "XL": available[min(3, len(available)-1)],
        }
    elif len(available) == 3:
        return {
            "S": available[0],
            "M": available[1],
            "L": available[2],
            "XL": available[2],
        }
    elif len(available) == 2:
        return {
            "S": available[0],
            "M": available[1],
            "L": available[1],
            "XL": available[1],
        }
    else:
        # Only one timeframe available
        return {
            "S": available[0],
            "M": available[0],
            "L": available[0],
            "XL": available[0],
        }


def get_allowed_aggregations(source_minutes: int) -> List[int]:
    """
    Get allowed aggregation values for scale calibration.

    Args:
        source_minutes: Source data resolution in minutes

    Returns:
        List of allowed aggregation values in minutes
    """
    return get_available_timeframes(source_minutes)


def create_resolution_config(resolution: str) -> ResolutionConfig:
    """
    Create a complete resolution configuration from a resolution string.

    Args:
        resolution: Resolution string (e.g., "5m", "1h")

    Returns:
        ResolutionConfig with all derived settings
    """
    source_minutes = parse_resolution(resolution)

    return ResolutionConfig(
        source_resolution=resolution,
        source_minutes=source_minutes,
        available_timeframes=get_available_timeframes(source_minutes),
        default_aggregations=get_default_aggregations(source_minutes),
        allowed_aggregations=get_allowed_aggregations(source_minutes),
    )


def get_gap_threshold_minutes(source_minutes: int, tolerance_factor: float = 1.5) -> float:
    """
    Get the gap detection threshold for a given source resolution.

    A gap is detected when consecutive bars are separated by more than
    the expected interval (source resolution * tolerance factor).

    Args:
        source_minutes: Source data resolution in minutes
        tolerance_factor: Multiplier for gap threshold (default 1.5)

    Returns:
        Gap threshold in minutes
    """
    return source_minutes * tolerance_factor


def format_minutes(minutes: int) -> str:
    """
    Format minutes into human-readable resolution string.

    Args:
        minutes: Duration in minutes

    Returns:
        Formatted string (e.g., "5m", "1h", "1d")
    """
    if minutes < 60:
        return f"{minutes}m"
    elif minutes < 1440:
        hours = minutes // 60
        return f"{hours}h"
    elif minutes < 10080:
        days = minutes // 1440
        return f"{days}d"
    elif minutes < 43200:
        weeks = minutes // 10080
        return f"{weeks}w"
    else:
        months = minutes // 43200
        return f"{months}mo"
