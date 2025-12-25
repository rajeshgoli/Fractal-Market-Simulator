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
        invalidation_threshold: Fraction of leg range beyond origin that
            marks decisive invalidation. Default 0.382 (#203).
        engulfed_breach_threshold: Combined breach fraction (origin + pivot)
            that marks a leg as engulfed and deletes it. Default 0.0 (strict
            deletion while collecting impulse data for threshold tuning) (#236).
    """
    formation_fib: float = 0.287
    self_separation: float = 0.10
    big_swing_threshold: float = 0.10
    big_swing_price_tolerance: float = 0.15
    big_swing_close_tolerance: float = 0.10
    child_swing_tolerance: float = 0.10
    invalidation_threshold: float = 0.382
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
            times are consolidated. Default 0.0 (disabled). Set > 0 to enable (e.g., 0.05 = 5%).
        origin_time_prune_threshold: Threshold for origin-proximity consolidation by time (#294).
            Legs formed close together in time (relative to older leg's age) are candidates
            for consolidation. Default 0.0 (disabled). Set > 0 to enable (e.g., 0.10 = 10%).
        proximity_prune_strategy: Strategy for which leg survives proximity pruning (#319).
            'oldest': Keep oldest leg in each cluster (legacy geometric approach).
            'counter_trend': Keep leg with highest counter-trend range (market-structure
            aware, uses segment_deepest_price from parent). Default 'counter_trend'.
        stale_extension_threshold: Multiplier for removing invalidated child legs (#203, #261).
            Invalidated legs WITH A PARENT are pruned when price moves N x their range
            beyond origin. Root legs (no parent) are never pruned, preserving the anchor
            that began the move. Default 3.0.
        emit_level_crosses: Whether to emit LevelCrossEvent when price crosses Fib
            levels. Default False (disabled for performance). Set to True when
            level cross events are needed. Can be toggled mid-stream via update_config().
        enable_engulfed_prune: Whether to delete legs that are breached on both
            origin and pivot sides. Default True.
        enable_inner_structure_prune: Whether to prune counter-direction legs from
            inner structure pivots when outer structure invalidates. Default False.

    Example:
        >>> config = SwingConfig.default()
        >>> config.bull.formation_fib
        0.287
    """
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)
    origin_range_prune_threshold: float = 0.0  # Disabled by default; set > 0 to enable
    origin_time_prune_threshold: float = 0.0  # Disabled by default; set > 0 to enable
    # Proximity pruning strategy (#319): 'oldest' (legacy) or 'counter_trend' (default)
    # 'oldest': Keep oldest leg in each cluster (purely geometric)
    # 'counter_trend': Keep leg with highest counter-trend range (market-structure aware)
    proximity_prune_strategy: str = 'counter_trend'
    # Branch ratio for origin domination (#337): prevents insignificant child legs
    # A new leg's counter-trend must be >= min_branch_ratio * parent's counter-trend.
    # This scales naturally through the hierarchy (children of children can be smaller).
    # E.g., 0.1 means child's counter-trend must be at least 10% of parent's.
    # Default 0.0 (disabled). Set > 0 to enable branch ratio domination.
    min_branch_ratio: float = 0.0
    stale_extension_threshold: float = 3.0
    emit_level_crosses: bool = False
    # Pruning algorithm toggles (#288)
    enable_engulfed_prune: bool = True
    enable_inner_structure_prune: bool = False

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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
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
            stale_extension_threshold=stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
        )

    def with_level_crosses(self, emit_level_crosses: bool) -> "SwingConfig":
        """
        Create a new config with modified level cross emission setting.

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            emit_level_crosses: Whether to emit LevelCrossEvent when price
                crosses Fib levels. Set to False to skip level cross checks
                (~55% of process_bar time) when events are not needed.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
        )

    def with_prune_toggles(
        self,
        enable_engulfed_prune: bool = None,
        enable_inner_structure_prune: bool = None,
    ) -> "SwingConfig":
        """
        Create a new config with modified pruning algorithm toggles.

        Since SwingConfig is frozen, this creates a new instance.
        Only provided parameters are modified; others keep their current values.

        Args:
            enable_engulfed_prune: Enable/disable engulfed leg deletion.
            enable_inner_structure_prune: Enable/disable inner structure pruning.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            proximity_prune_strategy=self.proximity_prune_strategy,
            min_branch_ratio=self.min_branch_ratio,
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=enable_engulfed_prune if enable_engulfed_prune is not None else self.enable_engulfed_prune,
            enable_inner_structure_prune=enable_inner_structure_prune if enable_inner_structure_prune is not None else self.enable_inner_structure_prune,
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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
        )
