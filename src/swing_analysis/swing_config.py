"""
Swing Detection Configuration

Centralized configuration for all swing detection parameters.
Extracts magic numbers from the codebase into a single config.

See Docs/Reference/valid_swings.md for the canonical rules these parameters implement.
"""

from dataclasses import dataclass, field, asdict
from typing import Any


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
class SwingConfig:
    """
    All configurable parameters for swing detection.

    This config centralizes all magic numbers used in swing detection.

    Attributes:
        bull: Configuration for bull swing detection.
        bear: Configuration for bear swing detection.
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
        enable_engulfed_prune: Whether to delete legs that are breached on both
            origin and pivot sides.

    Example:
        >>> config = SwingConfig.default()
        >>> config.bull.formation_fib
        0.287
    """
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)
    origin_range_prune_threshold: float = 0.02
    origin_time_prune_threshold: float = 0.02
    proximity_prune_strategy: str = 'oldest'
    min_branch_ratio: float = 0.0
    min_turn_ratio: float = 0.0
    # Turn ratio mode selection (mutually exclusive):
    #   - min_turn_ratio > 0: threshold mode (prune legs below ratio)
    #   - max_turns_per_pivot > 0: top-k by ratio
    #   - max_turns_per_pivot_raw > 0: top-k by raw counter-heft
    max_turns_per_pivot: int = 0
    max_turns_per_pivot_raw: int = 10
    stale_extension_threshold: float = 3.0
    # Pruning algorithm toggles (#288)
    enable_engulfed_prune: bool = True

    @classmethod
    def default(cls) -> "SwingConfig":
        """Create a config with default values."""
        return cls()

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
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
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
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )

    def with_origin_prune(
        self,
        origin_range_prune_threshold: float = None,
        origin_time_prune_threshold: float = None,
        proximity_prune_strategy: str = None,
    ) -> "SwingConfig":
        """
        Create a new config with modified origin-proximity prune thresholds (#294, #319).

        Since SwingConfig is frozen, this creates a new instance.

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
        return SwingConfig(
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
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )

    def with_stale_extension(self, stale_extension_threshold: float) -> "SwingConfig":
        """
        Create a new config with modified stale extension threshold (#203, #261).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            stale_extension_threshold: Multiplier for removing invalidated child legs.
                3.0 means invalidated legs with a parent are pruned at 3x extension
                beyond origin. Root legs (no parent) are never pruned by this rule.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )

    def with_prune_toggles(
        self,
        enable_engulfed_prune: bool = None,
    ) -> "SwingConfig":
        """
        Create a new config with modified pruning algorithm toggles.

        Since SwingConfig is frozen, this creates a new instance.
        Only provided parameters are modified; others keep their current values.

        Args:
            enable_engulfed_prune: Enable/disable engulfed leg deletion.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=enable_engulfed_prune if enable_engulfed_prune is not None else self.enable_engulfed_prune,
        )

    def with_min_branch_ratio(self, min_branch_ratio: float) -> "SwingConfig":
        """
        Create a new config with modified min branch ratio threshold (#337).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            min_branch_ratio: Minimum ratio of child's counter-trend to parent's.
                A new leg's counter-trend must be >= min_branch_ratio * parent's.
                0.1 means child's counter-trend must be at least 10% of parent's.
                0.0 disables branch ratio domination.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )

    def with_min_turn_ratio(self, min_turn_ratio: float) -> "SwingConfig":
        """
        Create a new config with modified min turn ratio threshold (#341).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            min_turn_ratio: Minimum turn ratio for sibling pruning at shared pivots.
                When a new leg forms at origin O, counter-legs with pivot=O and
                turn_ratio < min_turn_ratio are pruned.
                0.5 means legs cannot extend more than 2x their counter-trend.
                0.0 disables turn ratio pruning.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )

    def with_max_turns_per_pivot(self, max_turns_per_pivot: int) -> "SwingConfig":
        """
        Create a new config with modified max turns per pivot (#342).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            max_turns_per_pivot: Maximum number of legs to keep at each pivot
                in top-k mode. Only active when min_turn_ratio == 0.
                0 disables top-k mode (uses threshold mode if min_turn_ratio > 0).
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=max_turns_per_pivot,
            max_turns_per_pivot_raw=self.max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )

    def with_max_turns_per_pivot_raw(self, max_turns_per_pivot_raw: int) -> "SwingConfig":
        """
        Create a new config with modified max turns per pivot (raw mode) (#355).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            max_turns_per_pivot_raw: Maximum number of legs to keep at each pivot
                in raw counter-heft mode. Only active when min_turn_ratio == 0
                and max_turns_per_pivot == 0.
                Sorts by raw _max_counter_leg_range instead of ratio.
                0 disables raw counter-heft mode.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            min_turn_ratio=self.min_turn_ratio,
            max_turns_per_pivot=self.max_turns_per_pivot,
            max_turns_per_pivot_raw=max_turns_per_pivot_raw,
            stale_extension_threshold=self.stale_extension_threshold,
            enable_engulfed_prune=self.enable_engulfed_prune,
        )
