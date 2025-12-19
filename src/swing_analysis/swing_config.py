"""
Swing Detection Configuration

Centralized configuration for all swing detection parameters.
Extracts magic numbers from the codebase into a single, serializable config.

See Docs/Reference/valid_swings.md for the canonical rules these parameters implement.
"""

from dataclasses import dataclass, field, asdict
import json
from typing import Any, Dict


@dataclass(frozen=True)
class DirectionConfig:
    """
    Parameters for one direction (bull or bear).

    These parameters control swing detection and invalidation behavior
    for a single direction. Bull and bear can have different configs
    if asymmetric behavior is desired.

    Attributes:
        formation_fib: Fib extension from defended pivot required to confirm
            swing formation. Default 0.287 per valid_swings.md Rule 3.
        self_separation: Minimum separation between candidate origins (1s)
            as a fraction of swing range. Default 0.10 per Rule 4.1.
        big_swing_threshold: Percentile threshold for "big" swings.
            0.10 means top 10% by range are big swings.
        big_swing_price_tolerance: Invalidation tolerance for big swings
            as fraction of range (price-based). Default 0.15 per Rule 2.2.
        big_swing_close_tolerance: Invalidation tolerance for big swings
            as fraction of range (close-based). Default 0.10 per Rule 2.2.
        child_swing_tolerance: Invalidation tolerance for children of big
            swings as fraction of range. Default 0.10.
    """
    formation_fib: float = 0.287
    self_separation: float = 0.10
    big_swing_threshold: float = 0.10
    big_swing_price_tolerance: float = 0.15
    big_swing_close_tolerance: float = 0.10
    child_swing_tolerance: float = 0.10


@dataclass(frozen=True)
class SwingConfig:
    """
    All configurable parameters for swing detection.

    This config centralizes all magic numbers used in swing detection.
    It supports serialization to/from JSON for persistence and replay.

    Attributes:
        bull: Configuration for bull swing detection.
        bear: Configuration for bear swing detection.
        lookback_bars: Number of bars to look back for candidate extrema.

    Example:
        >>> config = SwingConfig.default()
        >>> config.bull.formation_fib
        0.287
        >>> json_str = config.to_json()
        >>> restored = SwingConfig.from_json(json_str)
        >>> restored == config
        True
    """
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)
    lookback_bars: int = 50

    @classmethod
    def default(cls) -> "SwingConfig":
        """Create a config with default values."""
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bull": asdict(self.bull),
            "bear": asdict(self.bear),
            "lookback_bars": self.lookback_bars,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SwingConfig":
        """Create from dictionary."""
        bull_data = data.get("bull", {})
        bear_data = data.get("bear", {})
        return cls(
            bull=DirectionConfig(**bull_data) if bull_data else DirectionConfig(),
            bear=DirectionConfig(**bear_data) if bear_data else DirectionConfig(),
            lookback_bars=data.get("lookback_bars", 50),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "SwingConfig":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def with_bull(self, **kwargs: Any) -> "SwingConfig":
        """
        Create a new config with modified bull parameters.

        Since SwingConfig is frozen, this creates a new instance.

        Example:
            >>> config = SwingConfig.default()
            >>> custom = config.with_bull(formation_fib=0.382)
            >>> custom.bull.formation_fib
            0.382
        """
        bull_dict = asdict(self.bull)
        bull_dict.update(kwargs)
        return SwingConfig(
            bull=DirectionConfig(**bull_dict),
            bear=self.bear,
            lookback_bars=self.lookback_bars,
        )

    def with_bear(self, **kwargs: Any) -> "SwingConfig":
        """
        Create a new config with modified bear parameters.

        Since SwingConfig is frozen, this creates a new instance.
        """
        bear_dict = asdict(self.bear)
        bear_dict.update(kwargs)
        return SwingConfig(
            bull=self.bull,
            bear=DirectionConfig(**bear_dict),
            lookback_bars=self.lookback_bars,
        )

    def with_lookback(self, lookback_bars: int) -> "SwingConfig":
        """
        Create a new config with modified lookback.

        Since SwingConfig is frozen, this creates a new instance.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            lookback_bars=lookback_bars,
        )
