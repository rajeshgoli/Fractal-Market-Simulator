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
        pivot_breach_threshold: Fraction of leg range beyond pivot that
            triggers pruning of formed legs. Default 0.10 (10%) (#208).
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
    pivot_breach_threshold: float = 0.10
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
        enable_pivot_breach_prune: Whether to prune and replace formed legs when
            pivot is breached beyond threshold. Default True.

    Example:
        >>> config = SwingConfig.default()
        >>> config.bull.formation_fib
        0.287
    """
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)
    origin_range_prune_threshold: float = 0.0  # Disabled by default; set > 0 to enable
    origin_time_prune_threshold: float = 0.0  # Disabled by default; set > 0 to enable
    stale_extension_threshold: float = 3.0
    emit_level_crosses: bool = False
    # Pruning algorithm toggles (#288)
    enable_engulfed_prune: bool = True
    enable_inner_structure_prune: bool = False
    enable_pivot_breach_prune: bool = True

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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
            enable_pivot_breach_prune=self.enable_pivot_breach_prune,
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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
            enable_pivot_breach_prune=self.enable_pivot_breach_prune,
        )

    def with_origin_prune(
        self,
        origin_range_prune_threshold: float = None,
        origin_time_prune_threshold: float = None,
    ) -> "SwingConfig":
        """
        Create a new config with modified origin-proximity prune thresholds (#294).

        Since SwingConfig is frozen, this creates a new instance.

        Args:
            origin_range_prune_threshold: Range threshold for consolidation.
                0.05 means legs within 5% relative range difference are candidates.
                0.0 disables range-based proximity pruning.
            origin_time_prune_threshold: Time threshold for consolidation.
                0.10 means legs formed within 10% of older leg's age are candidates.
                0.0 disables time-based proximity pruning.
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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
            enable_pivot_breach_prune=self.enable_pivot_breach_prune,
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
            stale_extension_threshold=stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
            enable_pivot_breach_prune=self.enable_pivot_breach_prune,
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
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=emit_level_crosses,
            enable_engulfed_prune=self.enable_engulfed_prune,
            enable_inner_structure_prune=self.enable_inner_structure_prune,
            enable_pivot_breach_prune=self.enable_pivot_breach_prune,
        )

    def with_prune_toggles(
        self,
        enable_engulfed_prune: bool = None,
        enable_inner_structure_prune: bool = None,
        enable_pivot_breach_prune: bool = None,
    ) -> "SwingConfig":
        """
        Create a new config with modified pruning algorithm toggles.

        Since SwingConfig is frozen, this creates a new instance.
        Only provided parameters are modified; others keep their current values.

        Args:
            enable_engulfed_prune: Enable/disable engulfed leg deletion.
            enable_inner_structure_prune: Enable/disable inner structure pruning.
            enable_pivot_breach_prune: Enable/disable pivot breach replacement.
        """
        return SwingConfig(
            bull=self.bull,
            bear=self.bear,
            origin_range_prune_threshold=self.origin_range_prune_threshold,
            origin_time_prune_threshold=self.origin_time_prune_threshold,
            stale_extension_threshold=self.stale_extension_threshold,
            emit_level_crosses=self.emit_level_crosses,
            enable_engulfed_prune=enable_engulfed_prune if enable_engulfed_prune is not None else self.enable_engulfed_prune,
            enable_inner_structure_prune=enable_inner_structure_prune if enable_inner_structure_prune is not None else self.enable_inner_structure_prune,
            enable_pivot_breach_prune=enable_pivot_breach_prune if enable_pivot_breach_prune is not None else self.enable_pivot_breach_prune,
        )
