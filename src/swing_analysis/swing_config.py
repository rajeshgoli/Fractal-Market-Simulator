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
        invalidation_threshold: Fraction of leg range beyond origin that
            marks decisive invalidation. Default 0.382 (#203).
        pivot_breach_threshold: Fraction of leg range beyond pivot that
            triggers pruning of formed legs. Default 0.10 (10%) (#208).
        engulfed_breach_threshold: Combined breach fraction (origin + pivot)
            that marks a leg as engulfed and deletes it. Default 0.20 (#208).
    """
    formation_fib: float = 0.287
    self_separation: float = 0.10
    big_swing_threshold: float = 0.10
    big_swing_price_tolerance: float = 0.15
    big_swing_close_tolerance: float = 0.10
    child_swing_tolerance: float = 0.10
    invalidation_threshold: float = 0.382
    pivot_breach_threshold: float = 0.10
    engulfed_breach_threshold: float = 0.20


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
        staleness_threshold: DEPRECATED - No longer used after #203.
        subtree_prune_threshold: Threshold for pruning small legs/origins (default 0.0).
            Legs/origins smaller than this fraction of a containing parent are pruned.
            0.0 disables pruning, 0.1 would prune legs < 10% of parent.
        proximity_prune_threshold: Threshold for proximity-based leg consolidation (#203).
            Legs within this relative difference of each other are consolidated.
            Default 0.05 (5%). Set to 0.0 to disable.
        stale_extension_threshold: Multiplier for removing invalidated legs (#203).
            Invalidated legs are pruned when price moves N × their range beyond origin.
            Default 3.0 (3× extension).

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
    staleness_threshold: float = 2.0  # DEPRECATED: kept for backwards compatibility
    subtree_prune_threshold: float = 0.0
    proximity_prune_threshold: float = 0.05
    stale_extension_threshold: float = 3.0

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
            "staleness_threshold": self.staleness_threshold,
            "subtree_prune_threshold": self.subtree_prune_threshold,
            "proximity_prune_threshold": self.proximity_prune_threshold,
            "stale_extension_threshold": self.stale_extension_threshold,
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
            staleness_threshold=data.get("staleness_threshold", 2.0),
            subtree_prune_threshold=data.get("subtree_prune_threshold", 0.0),
            proximity_prune_threshold=data.get("proximity_prune_threshold", 0.05),
            stale_extension_threshold=data.get("stale_extension_threshold", 3.0),
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
            staleness_threshold=self.staleness_threshold,
            subtree_prune_threshold=self.subtree_prune_threshold,
            proximity_prune_threshold=self.proximity_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
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
            staleness_threshold=self.staleness_threshold,
            subtree_prune_threshold=self.subtree_prune_threshold,
            proximity_prune_threshold=self.proximity_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
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
            staleness_threshold=self.staleness_threshold,
            subtree_prune_threshold=self.subtree_prune_threshold,
            proximity_prune_threshold=self.proximity_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_staleness(self, staleness_threshold: float) -> "SwingConfig":
        """
        DEPRECATED: staleness_threshold is no longer used after #203.

        Create a new config with modified staleness threshold.

        Since SwingConfig is frozen, this creates a new instance.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            lookback_bars=self.lookback_bars,
            staleness_threshold=staleness_threshold,
            subtree_prune_threshold=self.subtree_prune_threshold,
            proximity_prune_threshold=self.proximity_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_subtree_prune(self, subtree_prune_threshold: float) -> "SwingConfig":
        """
        Create a new config with modified subtree prune threshold.

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            subtree_prune_threshold: Fraction threshold for pruning small legs/origins.
                0.0 disables pruning, 0.1 prunes legs < 10% of parent.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            lookback_bars=self.lookback_bars,
            staleness_threshold=self.staleness_threshold,
            subtree_prune_threshold=subtree_prune_threshold,
            proximity_prune_threshold=self.proximity_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_proximity_prune(self, proximity_prune_threshold: float) -> "SwingConfig":
        """
        Create a new config with modified proximity prune threshold (#203).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            proximity_prune_threshold: Relative difference threshold for consolidation.
                0.05 means legs within 5% relative difference are consolidated.
                0.0 disables proximity pruning.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            lookback_bars=self.lookback_bars,
            staleness_threshold=self.staleness_threshold,
            subtree_prune_threshold=self.subtree_prune_threshold,
            proximity_prune_threshold=proximity_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_stale_extension(self, stale_extension_threshold: float) -> "SwingConfig":
        """
        Create a new config with modified stale extension threshold (#203).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            stale_extension_threshold: Multiplier for removing invalidated legs.
                3.0 means invalidated legs are pruned at 3× extension beyond origin.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            lookback_bars=self.lookback_bars,
            staleness_threshold=self.staleness_threshold,
            subtree_prune_threshold=self.subtree_prune_threshold,
            proximity_prune_threshold=self.proximity_prune_threshold,
            stale_extension_threshold=stale_extension_threshold,
        )
