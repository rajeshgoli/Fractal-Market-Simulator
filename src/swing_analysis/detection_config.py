"""
Detection Configuration

Centralized configuration for all detection parameters.
Extracts magic numbers from the codebase into a single config.

See Docs/Reference/valid_swings.md for the canonical rules these parameters implement.
"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class DirectionConfig:
    """
    Parameters for one direction (bull or bear).

    These parameters control detection and invalidation behavior
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
        engulfed_breach_threshold: Combined breach fraction (origin + pivot)
            that marks a leg as engulfed and deletes it. Default 0.0 (strict
            deletion while collecting impulse data for threshold tuning) (#236).
    """
    formation_fib: float = 0.236
    self_separation: float = 0.10
    big_swing_threshold: float = 0.10
    big_swing_price_tolerance: float = 0.15
    big_swing_close_tolerance: float = 0.10
    child_swing_tolerance: float = 0.10
    engulfed_breach_threshold: float = 0.0  # Strict: any engulfed leg is deleted (#236)


@dataclass(frozen=True)
class DetectionConfig:
    """
    All configurable parameters for leg detection.

    This config centralizes all magic numbers used in detection.

    Attributes:
        bull: Configuration for bull leg detection.
        bear: Configuration for bear leg detection.
        origin_range_prune_threshold: Threshold for origin-proximity consolidation by range (#294).
            Legs with similar ranges (relative difference < threshold) formed at similar
            times are consolidated. Set to 0 to disable.
        origin_time_prune_threshold: Threshold for origin-proximity consolidation by time (#294).
            Legs formed close together in time (relative to older leg's age) are candidates
            for consolidation. Set to 0 to disable.
        proximity_prune_strategy: Strategy for which leg survives proximity pruning (#319).
            'oldest': Keep oldest leg in each cluster (legacy geometric approach).
            'counter_trend': Keep leg with highest counter-trend range (market-structure
            aware, uses segment_deepest_price from parent).
        stale_extension_threshold: Multiplier for removing invalidated child legs (#203, #261).
            Invalidated legs WITH A PARENT are pruned when price moves N x their range
            beyond origin. Root legs (no parent) are never pruned, preserving the anchor
            that began the move.
        max_turns: Maximum legs to keep at each pivot by raw counter-heft (#404).
            Replaces the old three-mode system (min_turn_ratio, max_turns_per_pivot,
            max_turns_per_pivot_raw). Set to 0 to disable. Default: 10.

    Example:
        >>> config = DetectionConfig.default()
        >>> config.bull.formation_fib
        0.236
    """
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)
    origin_range_prune_threshold: float = 0.02
    origin_time_prune_threshold: float = 0.02
    proximity_prune_strategy: str = 'oldest'
    # #404: max_turns replaces min_turn_ratio + max_turns_per_pivot + max_turns_per_pivot_raw
    max_turns: int = 10
    stale_extension_threshold: float = 3.0

    @classmethod
    def default(cls) -> "DetectionConfig":
        """Create a config with default values."""
        return cls()

    def with_bull(self, **kwargs: Any) -> "DetectionConfig":
        """
        Create a new config with modified bull parameters.

        Since DetectionConfig is frozen, this creates a new instance.

        Example:
            >>> config = DetectionConfig.default()
            >>> custom = config.with_bull(formation_fib=0.382)
            >>> custom.bull.formation_fib
            0.382
        """
        bull_dict = asdict(self.bull)
        bull_dict.update(kwargs)
        return DetectionConfig(
            bull=DirectionConfig(**bull_dict),
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            max_turns=self.max_turns,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_bear(self, **kwargs: Any) -> "DetectionConfig":
        """
        Create a new config with modified bear parameters.

        Since DetectionConfig is frozen, this creates a new instance.
        """
        bear_dict = asdict(self.bear)
        bear_dict.update(kwargs)
        return DetectionConfig(
            bull=self.bull,
            bear=DirectionConfig(**bear_dict),
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            max_turns=self.max_turns,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_origin_prune(
        self,
        origin_range_prune_threshold: float = None,
        origin_time_prune_threshold: float = None,
        proximity_prune_strategy: str = None,
    ) -> "DetectionConfig":
        """
        Create a new config with modified origin-proximity prune thresholds (#294, #319).

        Since DetectionConfig is frozen, this creates a new instance.

        Args:
            origin_range_prune_threshold: Range threshold for consolidation.
                0.05 means legs within 5% relative range difference are candidates.
                0.0 disables range-based proximity pruning.
            origin_time_prune_threshold: Time threshold for consolidation.
                0.10 means legs formed within 10% of older leg's age are candidates.
                0.0 disables time-based proximity pruning.
            proximity_prune_strategy: Strategy for which leg wins in a cluster (#319).
                'oldest': Keep oldest leg (legacy behavior).
                'counter_trend': Keep leg with highest counter-trend range (default).
        """
        return DetectionConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=(
                origin_range_prune_threshold
                if origin_range_prune_threshold is not None
                else self.origin_range_prune_threshold
            ),
            origin_time_prune_threshold=(
                origin_time_prune_threshold
                if origin_time_prune_threshold is not None
                else self.origin_time_prune_threshold
            ),
            proximity_prune_strategy=(
                proximity_prune_strategy
                if proximity_prune_strategy is not None
                else self.proximity_prune_strategy
            ),
            max_turns=self.max_turns,
            stale_extension_threshold=self.stale_extension_threshold,
        )

    def with_stale_extension(self, stale_extension_threshold: float) -> "DetectionConfig":
        """
        Create a new config with modified stale extension threshold (#203, #261).

        Since DetectionConfig is frozen, this creates a new instance.

        Args:
            stale_extension_threshold: Multiplier for removing invalidated child legs.
                3.0 means invalidated legs with a parent are pruned at 3x extension
                beyond origin. Root legs (no parent) are never pruned by this rule.
        """
        return DetectionConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            max_turns=self.max_turns,
            stale_extension_threshold=stale_extension_threshold,
        )

    def with_max_turns(self, max_turns: int) -> "DetectionConfig":
        """
        Create a new config with modified max turns (#404).

        Since DetectionConfig is frozen, this creates a new instance.

        Args:
            max_turns: Maximum number of legs to keep at each pivot by raw
                counter-heft. Set to 0 to disable turn-based pruning.
        """
        return DetectionConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            max_turns=max_turns,
            stale_extension_threshold=self.stale_extension_threshold,
        )
