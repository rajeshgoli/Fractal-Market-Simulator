"""
Reference Layer Configuration

Configuration for the Reference Layer — a thin filter over DAG's active legs
that determines which legs qualify as valid trading references and their salience.

Separate from DetectionConfig because:
- Reference Layer is an independent consumer of DAG output
- Different lifecycle (can be changed without affecting detection)
- UI tunable parameters distinct from detection parameters

See #436 for bin-based classification migration.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass(frozen=True)
class ReferenceConfig:
    """
    Configuration for the Reference Layer.

    The Reference Layer filters DAG legs to identify valid trading references
    and ranks them by salience. This config controls all tunable parameters.

    Bin-Based Classification (#436):
        Legs are classified by median-normalized bin index (0-10).
        - Bins 0-7: < 5× median (normal references, zero breach tolerance)
        - Bin 8: 5-10× median (significant references)
        - Bin 9: 10-25× median (large references)
        - Bin 10: 25×+ median (exceptional references)

    Attributes:
        significant_bin_threshold: Bin index threshold for "significant" refs.
            Refs with bin >= this threshold get breach tolerance. Default 8.
        min_swings_for_classification: Minimum legs before classification works.
            During cold start, all references are excluded from output.
        formation_fib_threshold: Fib level for price-based formation (38.2%).
            A leg becomes a valid reference when the confirming move reaches
            this threshold retracement.
        origin_breach_tolerance: Breach tolerance for bins < significant_bin_threshold.
            Default 0.0 (zero tolerance per north star).
        significant_trade_breach_tolerance: Trade breach tolerance for significant refs.
            Invalidates if price TRADES beyond this. Default 15%.
        significant_close_breach_tolerance: Close breach tolerance for significant refs.
            Invalidates if price CLOSES beyond this. Default 10%.
        range_weight: Weight for range in salience calculation.
        impulse_weight: Weight for impulse in salience calculation.
        recency_weight: Weight for recency in salience calculation.
        depth_weight: Weight for hierarchy depth (root legs score higher).
        recency_decay_bars: Half-life for recency scoring. Recency formula:
            1 / (1 + age / recency_decay_bars). Default 1000 bars.
        depth_decay_factor: Decay per depth level. Depth formula:
            1 / (1 + depth * depth_decay_factor). Default 0.5.
        range_counter_weight: When > 0, uses range × counter for salience (standalone mode).
        top_n: Display limit for UI.
        confluence_tolerance_pct: Percentage tolerance for level clustering.
        active_level_distance_pct: Threshold for "currently active" levels.
        bin_window_duration_days: Rolling window for bin distribution.
        bin_recompute_interval: Recompute median every N legs added.

    Example:
        >>> config = ReferenceConfig.default()
        >>> config.formation_fib_threshold
        0.382
        >>> config.significant_bin_threshold
        8
    """

    # Bin classification (#436)
    significant_bin_threshold: int = 8  # Bins >= 8 get breach tolerance

    # Cold start
    min_swings_for_classification: int = 50  # Exclude refs until this many legs

    # Formation threshold (fib level)
    formation_fib_threshold: float = 0.382  # 38.2% retracement

    # Origin breach tolerance — bin-based (#436)
    # Bins < significant_bin_threshold: zero tolerance (or configurable)
    origin_breach_tolerance: float = 0.0   # 0% for small refs per north star
    # Bins >= significant_bin_threshold: two thresholds
    significant_trade_breach_tolerance: float = 0.15   # Invalidates if TRADES beyond 15%
    significant_close_breach_tolerance: float = 0.10   # Invalidates if CLOSES beyond 10%

    # Salience weights — unified (no scale-dependent weights) (#436)
    range_weight: float = 0.4
    impulse_weight: float = 0.4
    recency_weight: float = 0.1
    depth_weight: float = 0.1

    # Salience decay parameters (#438)
    recency_decay_bars: int = 1000  # Half-life for recency scoring
    depth_decay_factor: float = 0.5  # Decay per depth level

    # Standalone salience mode: Range×Counter — UI TUNABLE
    # When > 0, uses range × origin_counter_trend_range for salience instead of
    # the weighted combination of range/impulse/recency. Standalone mode because
    # this metric has different normalization than the component weights.
    # 0.0 = disabled (use weighted components), > 0 = enabled (use Range×Counter)
    range_counter_weight: float = 0.0

    # Display limit: how many references to show in UI — UI TUNABLE
    top_n: int = 5

    # Confluence detection
    confluence_tolerance_pct: float = 0.001  # 0.1% — percentage-based

    # Structure Panel: "currently active" threshold (levels within striking distance)
    active_level_distance_pct: float = 0.005  # 0.5% — levels within this % are "active"

    # Bin distribution configuration (#434)
    # Rolling window duration for bin distribution (in days)
    bin_window_duration_days: int = 90
    # Recompute median every N legs added
    bin_recompute_interval: int = 100

    @classmethod
    def default(cls) -> "ReferenceConfig":
        """Create a config with default values."""
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReferenceConfig":
        """Create from dictionary."""
        return cls(
            significant_bin_threshold=data.get("significant_bin_threshold", 8),
            min_swings_for_classification=data.get("min_swings_for_classification", 50),
            formation_fib_threshold=data.get("formation_fib_threshold", 0.382),
            origin_breach_tolerance=data.get("origin_breach_tolerance", 0.0),
            significant_trade_breach_tolerance=data.get("significant_trade_breach_tolerance", 0.15),
            significant_close_breach_tolerance=data.get("significant_close_breach_tolerance", 0.10),
            range_weight=data.get("range_weight", 0.4),
            impulse_weight=data.get("impulse_weight", 0.4),
            recency_weight=data.get("recency_weight", 0.1),
            depth_weight=data.get("depth_weight", 0.1),
            recency_decay_bars=data.get("recency_decay_bars", 1000),
            depth_decay_factor=data.get("depth_decay_factor", 0.5),
            range_counter_weight=data.get("range_counter_weight", 0.0),
            top_n=data.get("top_n", 5),
            confluence_tolerance_pct=data.get("confluence_tolerance_pct", 0.001),
            active_level_distance_pct=data.get("active_level_distance_pct", 0.005),
            bin_window_duration_days=data.get("bin_window_duration_days", 90),
            bin_recompute_interval=data.get("bin_recompute_interval", 100),
        )

    def with_formation_threshold(self, formation_fib_threshold: float) -> "ReferenceConfig":
        """Create a new config with modified formation threshold."""
        return ReferenceConfig(
            significant_bin_threshold=self.significant_bin_threshold,
            min_swings_for_classification=self.min_swings_for_classification,
            formation_fib_threshold=formation_fib_threshold,
            origin_breach_tolerance=self.origin_breach_tolerance,
            significant_trade_breach_tolerance=self.significant_trade_breach_tolerance,
            significant_close_breach_tolerance=self.significant_close_breach_tolerance,
            range_weight=self.range_weight,
            impulse_weight=self.impulse_weight,
            recency_weight=self.recency_weight,
            depth_weight=self.depth_weight,
            recency_decay_bars=self.recency_decay_bars,
            depth_decay_factor=self.depth_decay_factor,
            range_counter_weight=self.range_counter_weight,
            top_n=self.top_n,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
            bin_window_duration_days=self.bin_window_duration_days,
            bin_recompute_interval=self.bin_recompute_interval,
        )

    def with_breach_tolerance(
        self,
        origin_breach_tolerance: float = None,
        significant_trade_breach_tolerance: float = None,
        significant_close_breach_tolerance: float = None,
    ) -> "ReferenceConfig":
        """Create a new config with modified breach tolerances."""
        return ReferenceConfig(
            significant_bin_threshold=self.significant_bin_threshold,
            min_swings_for_classification=self.min_swings_for_classification,
            formation_fib_threshold=self.formation_fib_threshold,
            origin_breach_tolerance=origin_breach_tolerance if origin_breach_tolerance is not None else self.origin_breach_tolerance,
            significant_trade_breach_tolerance=significant_trade_breach_tolerance if significant_trade_breach_tolerance is not None else self.significant_trade_breach_tolerance,
            significant_close_breach_tolerance=significant_close_breach_tolerance if significant_close_breach_tolerance is not None else self.significant_close_breach_tolerance,
            range_weight=self.range_weight,
            impulse_weight=self.impulse_weight,
            recency_weight=self.recency_weight,
            depth_weight=self.depth_weight,
            recency_decay_bars=self.recency_decay_bars,
            depth_decay_factor=self.depth_decay_factor,
            range_counter_weight=self.range_counter_weight,
            top_n=self.top_n,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
            bin_window_duration_days=self.bin_window_duration_days,
            bin_recompute_interval=self.bin_recompute_interval,
        )

    def with_salience_weights(
        self,
        range_weight: float = None,
        impulse_weight: float = None,
        recency_weight: float = None,
        depth_weight: float = None,
        recency_decay_bars: int = None,
        depth_decay_factor: float = None,
        range_counter_weight: float = None,
        top_n: int = None,
    ) -> "ReferenceConfig":
        """Create a new config with modified salience weights."""
        return ReferenceConfig(
            significant_bin_threshold=self.significant_bin_threshold,
            min_swings_for_classification=self.min_swings_for_classification,
            formation_fib_threshold=self.formation_fib_threshold,
            origin_breach_tolerance=self.origin_breach_tolerance,
            significant_trade_breach_tolerance=self.significant_trade_breach_tolerance,
            significant_close_breach_tolerance=self.significant_close_breach_tolerance,
            range_weight=range_weight if range_weight is not None else self.range_weight,
            impulse_weight=impulse_weight if impulse_weight is not None else self.impulse_weight,
            recency_weight=recency_weight if recency_weight is not None else self.recency_weight,
            depth_weight=depth_weight if depth_weight is not None else self.depth_weight,
            recency_decay_bars=recency_decay_bars if recency_decay_bars is not None else self.recency_decay_bars,
            depth_decay_factor=depth_decay_factor if depth_decay_factor is not None else self.depth_decay_factor,
            range_counter_weight=range_counter_weight if range_counter_weight is not None else self.range_counter_weight,
            top_n=top_n if top_n is not None else self.top_n,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
            bin_window_duration_days=self.bin_window_duration_days,
            bin_recompute_interval=self.bin_recompute_interval,
        )

    def with_confluence_tolerance(self, confluence_tolerance_pct: float) -> "ReferenceConfig":
        """Create a new config with modified confluence tolerance."""
        return ReferenceConfig(
            significant_bin_threshold=self.significant_bin_threshold,
            min_swings_for_classification=self.min_swings_for_classification,
            formation_fib_threshold=self.formation_fib_threshold,
            origin_breach_tolerance=self.origin_breach_tolerance,
            significant_trade_breach_tolerance=self.significant_trade_breach_tolerance,
            significant_close_breach_tolerance=self.significant_close_breach_tolerance,
            range_weight=self.range_weight,
            impulse_weight=self.impulse_weight,
            recency_weight=self.recency_weight,
            depth_weight=self.depth_weight,
            recency_decay_bars=self.recency_decay_bars,
            depth_decay_factor=self.depth_decay_factor,
            range_counter_weight=self.range_counter_weight,
            top_n=self.top_n,
            confluence_tolerance_pct=confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
            bin_window_duration_days=self.bin_window_duration_days,
            bin_recompute_interval=self.bin_recompute_interval,
        )
