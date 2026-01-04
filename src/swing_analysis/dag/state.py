"""
Detector state and bar type classification for the DAG layer.

Contains the serializable state for pause/resume functionality and
the bar type classification enum.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Optional

from ..types import Bar
from .leg import Leg, PendingOrigin


class BarType(Enum):
    """
    Classification of bar relationships for temporal ordering.

    Type 1: Inside bar (LH, HL) - bar contained within previous
    Type 2-Bull: Trending up (HH, HL) - higher high and higher low
    Type 2-Bear: Trending down (LH, LL) - lower high and lower low
    Type 3: Outside bar (HH, LL) - engulfing, high volatility
    """
    TYPE_1 = "inside"
    TYPE_2_BULL = "bull"
    TYPE_2_BEAR = "bear"
    TYPE_3 = "outside"


@dataclass
class DetectorState:
    """
    Serializable state for pause/resume.

    Contains all information needed to resume detection from a saved point.
    Can be serialized to JSON for persistence.

    Attributes:
        last_bar_index: Most recent bar index processed.
        all_swing_ranges: List of all swing ranges seen, for big swing calculation.
        _cached_big_threshold_bull: Cached big swing threshold for bull swings.
        _cached_big_threshold_bear: Cached big swing threshold for bear swings.
        _threshold_valid: Whether the cached thresholds are valid.

        # DAG-based algorithm state:
        prev_bar: Previous bar for type classification.
        active_legs: Currently tracked legs (bull and bear can coexist).
        pending_origins: Potential origins for new legs awaiting temporal confirmation.

        # Population tracking for percentile ranking (#241, #242):
        formed_leg_impulses: Sorted list of impulse values from legs.
            Used for O(log n) percentile lookup.
    """

    last_bar_index: int = -1
    all_swing_ranges: List[Decimal] = field(default_factory=list)
    # Cached big swing thresholds (performance optimization #155)
    _cached_big_threshold_bull: Optional[Decimal] = None
    _cached_big_threshold_bear: Optional[Decimal] = None
    _threshold_valid: bool = False

    # DAG-based algorithm state
    prev_bar: Optional[Bar] = None
    active_legs: List[Leg] = field(default_factory=list)
    pending_origins: Dict[str, Optional[PendingOrigin]] = field(
        default_factory=lambda: {'bull': None, 'bear': None}
    )

    # Turn tracking (#202): Track when each direction's turn started
    # The domination check should only apply within a turn, not across turns.
    # When a turn changes (e.g., TYPE_2_BEAR -> TYPE_2_BULL), the bull turn restarts.
    last_turn_bar: Dict[str, int] = field(
        default_factory=lambda: {'bull': -1, 'bear': -1}
    )
    prev_bar_type: Optional[str] = None  # 'bull', 'bear', or None

    # Population tracking for impulsiveness percentile ranking (#241, #242)
    # Kept sorted for O(log n) percentile lookup using bisect
    formed_leg_impulses: List[float] = field(default_factory=list)

    # Bootstrap tracking (#357): Track whether any leg of each direction has been created.
    # Used to distinguish "no counter-trend leg exists" (before bootstrap) from
    # "counter-trend legs existed but none at this pivot" (after bootstrap).
    # Legs created before bootstrap are exempt from turn ratio pruning (truly unknown).
    # Legs created after bootstrap with no counter-trend get _max_counter_leg_range = 0.0.
    _has_created_bull_leg: bool = False
    _has_created_bear_leg: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        # Serialize active legs
        legs_data = []
        for leg in self.active_legs:
            legs_data.append({
                "direction": leg.direction,
                "pivot_price": str(leg.pivot_price),
                "pivot_index": leg.pivot_index,
                "origin_price": str(leg.origin_price),
                "origin_index": leg.origin_index,
                "retracement_pct": str(leg.retracement_pct),
                "parent_leg_id": leg.parent_leg_id,
                "status": leg.status,
                "bar_count": leg.bar_count,
                "gap_count": leg.gap_count,
                "last_modified_bar": leg.last_modified_bar,
                "price_at_creation": str(leg.price_at_creation),
                "leg_id": leg.leg_id,
                "impulse": leg.impulse,
                "impulsiveness": leg.impulsiveness,
                "spikiness": leg.spikiness,
                "_moment_n": leg._moment_n,
                "_moment_sum_x": leg._moment_sum_x,
                "_moment_sum_x2": leg._moment_sum_x2,
                "_moment_sum_x3": leg._moment_sum_x3,
                # Segment impulse tracking (#307)
                "segment_deepest_price": str(leg.segment_deepest_price) if leg.segment_deepest_price is not None else None,
                "segment_deepest_index": leg.segment_deepest_index,
                "impulse_to_deepest": leg.impulse_to_deepest,
                "impulse_back": leg.impulse_back,
                # Counter-trend ratio (#336)
                "counter_trend_ratio": leg.counter_trend_ratio,
                "origin_counter_trend_range": leg.origin_counter_trend_range,
                # Hierarchy depth (#361)
                "depth": leg.depth,
                # Range bin index (#434)
                "range_bin_index": leg.range_bin_index,
                # Bin-normalized impulsiveness (#491)
                "bin_impulsiveness": leg.bin_impulsiveness,
            })

        # Serialize pending origins
        pending_origins_data = {}
        for direction, origin in self.pending_origins.items():
            if origin:
                pending_origins_data[direction] = {
                    "price": str(origin.price),
                    "bar_index": origin.bar_index,
                    "direction": origin.direction,
                    "source": origin.source,
                }
            else:
                pending_origins_data[direction] = None

        # Serialize prev_bar
        prev_bar_data = None
        if self.prev_bar:
            prev_bar_data = {
                "index": self.prev_bar.index,
                "timestamp": self.prev_bar.timestamp,
                "open": self.prev_bar.open,
                "high": self.prev_bar.high,
                "low": self.prev_bar.low,
                "close": self.prev_bar.close,
            }

        return {
            "last_bar_index": self.last_bar_index,
            "all_swing_ranges": [str(r) for r in self.all_swing_ranges],
            # Cache fields (will be recomputed on restore, but included for completeness)
            "_cached_big_threshold_bull": str(self._cached_big_threshold_bull) if self._cached_big_threshold_bull is not None else None,
            "_cached_big_threshold_bear": str(self._cached_big_threshold_bear) if self._cached_big_threshold_bear is not None else None,
            "_threshold_valid": self._threshold_valid,
            # DAG state
            "prev_bar": prev_bar_data,
            "active_legs": legs_data,
            "pending_origins": pending_origins_data,
            # Note: price_high_water/price_low_water removed in #203 (staleness removal)
            # Turn tracking (#202)
            "last_turn_bar": self.last_turn_bar,
            "prev_bar_type": self.prev_bar_type,
            # Population tracking (#241, #242)
            "formed_leg_impulses": self.formed_leg_impulses,
            # Bootstrap tracking (#357)
            "_has_created_bull_leg": self._has_created_bull_leg,
            "_has_created_bear_leg": self._has_created_bear_leg,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DetectorState":
        """Create from dictionary."""
        # Restore cache fields if present (they'll be recomputed on first use anyway)
        cached_bull = data.get("_cached_big_threshold_bull")
        cached_bear = data.get("_cached_big_threshold_bear")

        # Deserialize active legs
        active_legs = []
        for leg_data in data.get("active_legs", []):
            leg = Leg(
                direction=leg_data["direction"],
                pivot_price=Decimal(leg_data["pivot_price"]),
                pivot_index=leg_data["pivot_index"],
                origin_price=Decimal(leg_data["origin_price"]),
                origin_index=leg_data["origin_index"],
                retracement_pct=Decimal(leg_data.get("retracement_pct", "0")),
                parent_leg_id=leg_data.get("parent_leg_id"),
                status=leg_data.get("status", "active"),
                bar_count=leg_data.get("bar_count", 0),
                gap_count=leg_data.get("gap_count", 0),
                last_modified_bar=leg_data.get("last_modified_bar", 0),
                price_at_creation=Decimal(leg_data.get("price_at_creation", "0")),
                # Prefer stored leg_id for backward compatibility; if missing,
                # __post_init__ will compute deterministic ID from properties (#299)
                leg_id=leg_data.get("leg_id", ""),
                impulse=leg_data.get("impulse", 0.0),
                impulsiveness=leg_data.get("impulsiveness"),
                spikiness=leg_data.get("spikiness"),
                _moment_n=leg_data.get("_moment_n", 0),
                _moment_sum_x=leg_data.get("_moment_sum_x", 0.0),
                _moment_sum_x2=leg_data.get("_moment_sum_x2", 0.0),
                _moment_sum_x3=leg_data.get("_moment_sum_x3", 0.0),
                # Segment impulse tracking (#307)
                segment_deepest_price=Decimal(leg_data["segment_deepest_price"]) if leg_data.get("segment_deepest_price") else None,
                segment_deepest_index=leg_data.get("segment_deepest_index"),
                impulse_to_deepest=leg_data.get("impulse_to_deepest"),
                impulse_back=leg_data.get("impulse_back"),
                # Counter-trend ratio (#336)
                counter_trend_ratio=leg_data.get("counter_trend_ratio"),
                origin_counter_trend_range=leg_data.get("origin_counter_trend_range"),
                # Hierarchy depth (#361)
                depth=leg_data.get("depth", 0),
                # Range bin index (#434)
                range_bin_index=leg_data.get("range_bin_index"),
                # Bin-normalized impulsiveness (#491)
                bin_impulsiveness=leg_data.get("bin_impulsiveness"),
            )
            active_legs.append(leg)

        # Deserialize pending origins
        pending_origins: Dict[str, Optional[PendingOrigin]] = {'bull': None, 'bear': None}
        pending_origins_data = data.get("pending_origins", {})
        for direction in ['bull', 'bear']:
            origin_data = pending_origins_data.get(direction)
            if origin_data:
                pending_origins[direction] = PendingOrigin(
                    price=Decimal(origin_data["price"]),
                    bar_index=origin_data["bar_index"],
                    direction=origin_data["direction"],
                    source=origin_data["source"],
                )

        # Deserialize prev_bar
        prev_bar = None
        prev_bar_data = data.get("prev_bar")
        if prev_bar_data:
            prev_bar = Bar(
                index=prev_bar_data["index"],
                timestamp=prev_bar_data["timestamp"],
                open=prev_bar_data["open"],
                high=prev_bar_data["high"],
                low=prev_bar_data["low"],
                close=prev_bar_data["close"],
            )

        # Turn tracking (#202)
        last_turn_bar = data.get("last_turn_bar", {'bull': -1, 'bear': -1})
        prev_bar_type = data.get("prev_bar_type")

        # Population tracking (#241, #242)
        formed_leg_impulses = data.get("formed_leg_impulses", [])

        # Bootstrap tracking (#357)
        has_created_bull_leg = data.get("_has_created_bull_leg", False)
        has_created_bear_leg = data.get("_has_created_bear_leg", False)

        return cls(
            last_bar_index=data.get("last_bar_index", -1),
            all_swing_ranges=[
                Decimal(r) for r in data.get("all_swing_ranges", [])
            ],
            _cached_big_threshold_bull=Decimal(cached_bull) if cached_bull is not None else None,
            _cached_big_threshold_bear=Decimal(cached_bear) if cached_bear is not None else None,
            _threshold_valid=data.get("_threshold_valid", False),
            # DAG state
            prev_bar=prev_bar,
            active_legs=active_legs,
            pending_origins=pending_origins,
            # Turn tracking (#202)
            last_turn_bar=last_turn_bar,
            prev_bar_type=prev_bar_type,
            # Population tracking (#241, #242)
            formed_leg_impulses=formed_leg_impulses,
            # Bootstrap tracking (#357)
            _has_created_bull_leg=has_created_bull_leg,
            _has_created_bear_leg=has_created_bear_leg,
        )
