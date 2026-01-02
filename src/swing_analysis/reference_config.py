"""
Reference Layer Configuration

Configuration for the Reference Layer — a thin filter over DAG's active legs
that determines which legs qualify as valid trading references and their salience.

Separate from DetectionConfig because:
- Reference Layer is an independent consumer of DAG output
- Different lifecycle (can be changed without affecting detection)
- UI tunable parameters distinct from detection parameters

See Docs/Working/reference_layer_spec.md for full specification.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass(frozen=True)
class ReferenceConfig:
    """
    Configuration for the Reference Layer.

    The Reference Layer filters DAG legs to identify valid trading references
    and ranks them by salience. This config controls all tunable parameters.

    Attributes:
        xl_threshold: Percentile threshold for XL scale (top 10% = 0.90).
        l_threshold: Percentile threshold for L scale (top 40% = 0.60).
        m_threshold: Percentile threshold for M scale (top 70% = 0.30).
        min_swings_for_scale: Minimum swings before scale classification works.
            During cold start, all references are excluded from output.
        formation_fib_threshold: Fib level for price-based formation (38.2%).
            A leg becomes a valid reference when the confirming move reaches
            this threshold retracement.
        small_origin_tolerance: Origin breach tolerance for S/M scale references.
            Default 0% per north star (configurable for tuning).
        big_trade_breach_tolerance: L/XL invalidates if price TRADES beyond this.
            Default 15% per north star.
        big_close_breach_tolerance: L/XL invalidates if price CLOSES beyond this.
            Default 10% per north star.
        big_range_weight: Weight for range in L/XL salience calculation.
        big_impulse_weight: Weight for impulse in L/XL salience calculation.
        big_recency_weight: Weight for recency in L/XL salience calculation.
        small_range_weight: Weight for range in S/M salience calculation.
        small_impulse_weight: Weight for impulse in S/M salience calculation.
        small_recency_weight: Weight for recency in S/M salience calculation.
        use_depth_instead_of_scale: When True, use hierarchy depth for classification
            instead of percentile-based scale. For A/B testing.
        confluence_tolerance_pct: Percentage tolerance for level clustering.
            Levels within this percentage are grouped into confluence zones.

    Example:
        >>> config = ReferenceConfig.default()
        >>> config.formation_fib_threshold
        0.382
        >>> custom = config.with_formation_threshold(0.5)
        >>> custom.formation_fib_threshold
        0.5
    """

    # Scale thresholds (percentiles)
    xl_threshold: float = 0.90  # Top 10%
    l_threshold: float = 0.60   # Top 40%
    m_threshold: float = 0.30   # Top 70%

    # Cold start
    min_swings_for_scale: int = 50  # Exclude refs until this many swings

    # Formation threshold (fib level)
    formation_fib_threshold: float = 0.382  # 38.2% retracement

    # Origin breach tolerance (location past 1.0) — UI TUNABLE
    # Per north star (product_north_star.md lines 122-128):
    # S/M: default zero tolerance (configurable for tuning)
    small_origin_tolerance: float = 0.0   # 0% for S/M per north star
    # L/XL: two thresholds — trade breach (15%) and close breach (10%)
    big_trade_breach_tolerance: float = 0.15   # Invalidates if TRADES beyond 15%
    big_close_breach_tolerance: float = 0.10   # Invalidates if CLOSES beyond 10%

    # Salience weights (big swings: L/XL) — UI TUNABLE
    big_range_weight: float = 0.5
    big_impulse_weight: float = 0.4
    big_recency_weight: float = 0.1

    # Salience weights (small swings: S/M) — UI TUNABLE
    small_range_weight: float = 0.2
    small_impulse_weight: float = 0.3
    small_recency_weight: float = 0.5

    # Standalone salience mode: Range×Counter — UI TUNABLE
    # When > 0, uses range × origin_counter_trend_range for salience instead of
    # the weighted combination of range/impulse/recency. Standalone mode because
    # this metric has different normalization than the component weights.
    # 0.0 = disabled (use weighted components), > 0 = enabled (use Range×Counter)
    range_counter_weight: float = 0.0

    # Classification mode (for A/B testing)
    use_depth_instead_of_scale: bool = False

    # Confluence detection
    confluence_tolerance_pct: float = 0.001  # 0.1% — percentage-based

    # Structure Panel: "currently active" threshold (levels within striking distance)
    active_level_distance_pct: float = 0.005  # 0.5% — levels within this % are "active"

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
            xl_threshold=data.get("xl_threshold", 0.90),
            l_threshold=data.get("l_threshold", 0.60),
            m_threshold=data.get("m_threshold", 0.30),
            min_swings_for_scale=data.get("min_swings_for_scale", 50),
            formation_fib_threshold=data.get("formation_fib_threshold", 0.382),
            small_origin_tolerance=data.get("small_origin_tolerance", 0.0),
            big_trade_breach_tolerance=data.get("big_trade_breach_tolerance", 0.15),
            big_close_breach_tolerance=data.get("big_close_breach_tolerance", 0.10),
            big_range_weight=data.get("big_range_weight", 0.5),
            big_impulse_weight=data.get("big_impulse_weight", 0.4),
            big_recency_weight=data.get("big_recency_weight", 0.1),
            small_range_weight=data.get("small_range_weight", 0.2),
            small_impulse_weight=data.get("small_impulse_weight", 0.3),
            small_recency_weight=data.get("small_recency_weight", 0.5),
            range_counter_weight=data.get("range_counter_weight", 0.0),
            use_depth_instead_of_scale=data.get("use_depth_instead_of_scale", False),
            confluence_tolerance_pct=data.get("confluence_tolerance_pct", 0.001),
            active_level_distance_pct=data.get("active_level_distance_pct", 0.005),
        )

    def with_scale_thresholds(
        self,
        xl_threshold: float = None,
        l_threshold: float = None,
        m_threshold: float = None,
    ) -> "ReferenceConfig":
        """
        Create a new config with modified scale thresholds.

        Since ReferenceConfig is frozen, this creates a new instance.

        Args:
            xl_threshold: Percentile for XL (top 10% = 0.90).
            l_threshold: Percentile for L (top 40% = 0.60).
            m_threshold: Percentile for M (top 70% = 0.30).
        """
        return ReferenceConfig(
            xl_threshold=xl_threshold if xl_threshold is not None else self.xl_threshold,
            l_threshold=l_threshold if l_threshold is not None else self.l_threshold,
            m_threshold=m_threshold if m_threshold is not None else self.m_threshold,
            min_swings_for_scale=self.min_swings_for_scale,
            formation_fib_threshold=self.formation_fib_threshold,
            small_origin_tolerance=self.small_origin_tolerance,
            big_trade_breach_tolerance=self.big_trade_breach_tolerance,
            big_close_breach_tolerance=self.big_close_breach_tolerance,
            big_range_weight=self.big_range_weight,
            big_impulse_weight=self.big_impulse_weight,
            big_recency_weight=self.big_recency_weight,
            small_range_weight=self.small_range_weight,
            small_impulse_weight=self.small_impulse_weight,
            small_recency_weight=self.small_recency_weight,
            range_counter_weight=self.range_counter_weight,
            use_depth_instead_of_scale=self.use_depth_instead_of_scale,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
        )

    def with_formation_threshold(self, formation_fib_threshold: float) -> "ReferenceConfig":
        """
        Create a new config with modified formation threshold.

        Since ReferenceConfig is frozen, this creates a new instance.

        Args:
            formation_fib_threshold: Fib level for formation (e.g., 0.382, 0.5).
        """
        return ReferenceConfig(
            xl_threshold=self.xl_threshold,
            l_threshold=self.l_threshold,
            m_threshold=self.m_threshold,
            min_swings_for_scale=self.min_swings_for_scale,
            formation_fib_threshold=formation_fib_threshold,
            small_origin_tolerance=self.small_origin_tolerance,
            big_trade_breach_tolerance=self.big_trade_breach_tolerance,
            big_close_breach_tolerance=self.big_close_breach_tolerance,
            big_range_weight=self.big_range_weight,
            big_impulse_weight=self.big_impulse_weight,
            big_recency_weight=self.big_recency_weight,
            small_range_weight=self.small_range_weight,
            small_impulse_weight=self.small_impulse_weight,
            small_recency_weight=self.small_recency_weight,
            range_counter_weight=self.range_counter_weight,
            use_depth_instead_of_scale=self.use_depth_instead_of_scale,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
        )

    def with_tolerance(
        self,
        small_origin_tolerance: float = None,
        big_trade_breach_tolerance: float = None,
        big_close_breach_tolerance: float = None,
    ) -> "ReferenceConfig":
        """
        Create a new config with modified origin breach tolerances.

        Since ReferenceConfig is frozen, this creates a new instance.

        Args:
            small_origin_tolerance: Tolerance for S/M references (e.g., 0.0 = 0%).
            big_trade_breach_tolerance: L/XL TRADE breach tolerance (e.g., 0.15 = 15%).
            big_close_breach_tolerance: L/XL CLOSE breach tolerance (e.g., 0.10 = 10%).
        """
        return ReferenceConfig(
            xl_threshold=self.xl_threshold,
            l_threshold=self.l_threshold,
            m_threshold=self.m_threshold,
            min_swings_for_scale=self.min_swings_for_scale,
            formation_fib_threshold=self.formation_fib_threshold,
            small_origin_tolerance=small_origin_tolerance if small_origin_tolerance is not None else self.small_origin_tolerance,
            big_trade_breach_tolerance=big_trade_breach_tolerance if big_trade_breach_tolerance is not None else self.big_trade_breach_tolerance,
            big_close_breach_tolerance=big_close_breach_tolerance if big_close_breach_tolerance is not None else self.big_close_breach_tolerance,
            big_range_weight=self.big_range_weight,
            big_impulse_weight=self.big_impulse_weight,
            big_recency_weight=self.big_recency_weight,
            small_range_weight=self.small_range_weight,
            small_impulse_weight=self.small_impulse_weight,
            small_recency_weight=self.small_recency_weight,
            range_counter_weight=self.range_counter_weight,
            use_depth_instead_of_scale=self.use_depth_instead_of_scale,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
        )

    def with_salience_weights(
        self,
        big_range_weight: float = None,
        big_impulse_weight: float = None,
        big_recency_weight: float = None,
        small_range_weight: float = None,
        small_impulse_weight: float = None,
        small_recency_weight: float = None,
        range_counter_weight: float = None,
    ) -> "ReferenceConfig":
        """
        Create a new config with modified salience weights.

        Since ReferenceConfig is frozen, this creates a new instance.
        Big weights apply to L/XL swings, small weights to S/M swings.

        Args:
            big_range_weight: Range weight for L/XL (default 0.5).
            big_impulse_weight: Impulse weight for L/XL (default 0.4).
            big_recency_weight: Recency weight for L/XL (default 0.1).
            small_range_weight: Range weight for S/M (default 0.2).
            small_impulse_weight: Impulse weight for S/M (default 0.3).
            small_recency_weight: Recency weight for S/M (default 0.5).
            range_counter_weight: Range×Counter weight (default 0.0). When > 0,
                uses range × origin_counter_trend_range for salience (standalone mode).
        """
        return ReferenceConfig(
            xl_threshold=self.xl_threshold,
            l_threshold=self.l_threshold,
            m_threshold=self.m_threshold,
            min_swings_for_scale=self.min_swings_for_scale,
            formation_fib_threshold=self.formation_fib_threshold,
            small_origin_tolerance=self.small_origin_tolerance,
            big_trade_breach_tolerance=self.big_trade_breach_tolerance,
            big_close_breach_tolerance=self.big_close_breach_tolerance,
            big_range_weight=big_range_weight if big_range_weight is not None else self.big_range_weight,
            big_impulse_weight=big_impulse_weight if big_impulse_weight is not None else self.big_impulse_weight,
            big_recency_weight=big_recency_weight if big_recency_weight is not None else self.big_recency_weight,
            small_range_weight=small_range_weight if small_range_weight is not None else self.small_range_weight,
            small_impulse_weight=small_impulse_weight if small_impulse_weight is not None else self.small_impulse_weight,
            small_recency_weight=small_recency_weight if small_recency_weight is not None else self.small_recency_weight,
            range_counter_weight=range_counter_weight if range_counter_weight is not None else self.range_counter_weight,
            use_depth_instead_of_scale=self.use_depth_instead_of_scale,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
        )

    def with_depth_mode(self, use_depth_instead_of_scale: bool) -> "ReferenceConfig":
        """
        Create a new config with modified classification mode.

        Since ReferenceConfig is frozen, this creates a new instance.

        Args:
            use_depth_instead_of_scale: When True, use hierarchy depth for
                classification instead of percentile-based scale. For A/B testing.
        """
        return ReferenceConfig(
            xl_threshold=self.xl_threshold,
            l_threshold=self.l_threshold,
            m_threshold=self.m_threshold,
            min_swings_for_scale=self.min_swings_for_scale,
            formation_fib_threshold=self.formation_fib_threshold,
            small_origin_tolerance=self.small_origin_tolerance,
            big_trade_breach_tolerance=self.big_trade_breach_tolerance,
            big_close_breach_tolerance=self.big_close_breach_tolerance,
            big_range_weight=self.big_range_weight,
            big_impulse_weight=self.big_impulse_weight,
            big_recency_weight=self.big_recency_weight,
            small_range_weight=self.small_range_weight,
            small_impulse_weight=self.small_impulse_weight,
            small_recency_weight=self.small_recency_weight,
            range_counter_weight=self.range_counter_weight,
            use_depth_instead_of_scale=use_depth_instead_of_scale,
            confluence_tolerance_pct=self.confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
        )

    def with_confluence_tolerance(self, confluence_tolerance_pct: float) -> "ReferenceConfig":
        """
        Create a new config with modified confluence tolerance.

        Since ReferenceConfig is frozen, this creates a new instance.

        Args:
            confluence_tolerance_pct: Percentage tolerance for level clustering
                (e.g., 0.001 = 0.1%).
        """
        return ReferenceConfig(
            xl_threshold=self.xl_threshold,
            l_threshold=self.l_threshold,
            m_threshold=self.m_threshold,
            min_swings_for_scale=self.min_swings_for_scale,
            formation_fib_threshold=self.formation_fib_threshold,
            small_origin_tolerance=self.small_origin_tolerance,
            big_trade_breach_tolerance=self.big_trade_breach_tolerance,
            big_close_breach_tolerance=self.big_close_breach_tolerance,
            big_range_weight=self.big_range_weight,
            big_impulse_weight=self.big_impulse_weight,
            big_recency_weight=self.big_recency_weight,
            small_range_weight=self.small_range_weight,
            small_impulse_weight=self.small_impulse_weight,
            small_recency_weight=self.small_recency_weight,
            range_counter_weight=self.range_counter_weight,
            use_depth_instead_of_scale=self.use_depth_instead_of_scale,
            confluence_tolerance_pct=confluence_tolerance_pct,
            active_level_distance_pct=self.active_level_distance_pct,
        )
