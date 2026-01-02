"""
Rolling Bin Distribution for Median-Normalized Scale Classification.

Implements adaptive bins with O(1) updates for scale classification.
Fixes the distribution/classification mismatch identified in #428:
- Old approach: used formation-time ranges in distribution, extended ranges for classification
- New approach: bins track current extended ranges, updated on pivot extension

Key features:
- Median-normalized bins: edges = median × [0, 0.3, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10, 25, ∞]
- Rolling window: 90 days of legs (configurable)
- Periodic median recomputation: every N legs (not per-update)
- O(1) add/update/remove operations
- Instrument-agnostic: adapts to any price scale via median normalization

See #428 investigation and #434 design spec for details.
"""

import bisect
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Deque, List, Tuple, Dict, Optional, Any


# Bin multipliers relative to median
# These define the bin edges: edge[i] = median × multiplier[i]
BIN_MULTIPLIERS = [0.0, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 25.0, float('inf')]

# Number of bins (one less than number of edges)
NUM_BINS = len(BIN_MULTIPLIERS) - 1  # 11 bins


@dataclass
class RollingBinDistribution:
    """
    Median-normalized bin distribution with rolling window for scale classification.

    Replaces the sorted list approach in ReferenceLayer with O(1) updates:
    - add_leg(): Add a new leg's range to the distribution
    - update_leg(): Update a leg's range when pivot extends (O(1) bin count update)
    - remove_leg(): Remove a leg from the distribution (on pruning)

    Bins are defined as multiples of the rolling median:
    - Bin 0: 0 - 0.3× median (tiny)
    - Bin 1: 0.3 - 0.5× median (very small)
    - Bin 2: 0.5 - 0.75× median (small)
    - Bin 3: 0.75 - 1× median (below average)
    - Bin 4: 1 - 1.5× median (average)
    - Bin 5: 1.5 - 2× median (above average)
    - Bin 6: 2 - 3× median (notable)
    - Bin 7: 3 - 5× median (significant)
    - Bin 8: 5 - 10× median (large) → M
    - Bin 9: 10 - 25× median (very large) → L
    - Bin 10: 25×+ median (exceptional) → XL

    Scale mapping (backwards compatibility):
    - S: bins 0-7 (< 5× median)
    - M: bin 8 (5-10× median)
    - L: bin 9 (10-25× median)
    - XL: bin 10 (25×+ median)

    Attributes:
        window_duration_days: Days of legs to keep in the rolling window.
        recompute_interval_legs: Recompute median every N legs added.
        window: Deque of (leg_id, range) tuples for the rolling window.
        bin_counts: Count of legs in each bin.
        median: Current rolling median.
        legs_since_recompute: Counter for triggering median recomputation.
        leg_ranges: Dict mapping leg_id to current range for O(1) lookup.
        leg_timestamps: Dict mapping leg_id to timestamp for window eviction.
    """

    # Configuration
    window_duration_days: int = 90
    recompute_interval_legs: int = 100

    # State (mutable, not frozen)
    window: Deque[Tuple[str, float, float]] = field(
        default_factory=lambda: deque()
    )  # (leg_id, range, timestamp)
    bin_counts: List[int] = field(
        default_factory=lambda: [0] * NUM_BINS
    )
    median: float = 10.0  # Default median until we have data
    legs_since_recompute: int = 0

    # Leg tracking
    leg_ranges: Dict[str, float] = field(default_factory=dict)  # leg_id -> current range
    _warmup_complete: bool = False  # True after first median computation

    def __post_init__(self) -> None:
        """Ensure bin_counts is initialized correctly."""
        if len(self.bin_counts) != NUM_BINS:
            self.bin_counts = [0] * NUM_BINS

    @property
    def bin_edges(self) -> List[float]:
        """
        Compute bin edges from current median.

        Returns:
            List of bin edges: [0, median*0.3, median*0.5, ..., inf]
        """
        return [m * self.median if m != float('inf') else float('inf')
                for m in BIN_MULTIPLIERS]

    @property
    def total_count(self) -> int:
        """Total number of legs in the distribution."""
        return sum(self.bin_counts)

    def get_bin_index(self, range_val: float) -> int:
        """
        Get bin index for a range value.

        Uses binary search on bin edges for O(log num_bins) lookup.
        In practice, with 12 edges this is effectively O(1).

        Args:
            range_val: Leg range value.

        Returns:
            Bin index (0 to NUM_BINS-1).
        """
        edges = self.bin_edges
        # bisect_right gives us the insertion point, which is the bin index
        idx = bisect.bisect_right(edges, range_val) - 1
        # Clamp to valid bin range
        return max(0, min(idx, NUM_BINS - 1))

    def get_scale(self, range_val: float) -> str:
        """
        Get S/M/L/XL scale classification for backwards compatibility.

        Mapping:
        - Bins 0-7 (< 5× median) → S
        - Bin 8 (5-10× median) → M
        - Bin 9 (10-25× median) → L
        - Bin 10 (25×+ median) → XL

        Args:
            range_val: Leg range value.

        Returns:
            Scale string: 'S', 'M', 'L', or 'XL'.
        """
        bin_idx = self.get_bin_index(range_val)

        if bin_idx <= 7:  # 0 - 5× median
            return 'S'
        elif bin_idx == 8:  # 5 - 10× median
            return 'M'
        elif bin_idx == 9:  # 10 - 25× median
            return 'L'
        else:  # 25×+ median
            return 'XL'

    def get_percentile(self, range_val: float) -> float:
        """
        Compute approximate percentile from bin counts.

        Args:
            range_val: Leg range value.

        Returns:
            Percentile (0-100). Returns 50.0 if distribution is empty.
        """
        if self.total_count == 0:
            return 50.0

        bin_idx = self.get_bin_index(range_val)

        # Count legs in bins below this one
        count_below = sum(self.bin_counts[:bin_idx])

        # Add half of current bin (approximation for within-bin position)
        count_below += self.bin_counts[bin_idx] / 2

        return (count_below / self.total_count) * 100

    def add_leg(
        self,
        leg_id: str,
        range_val: float,
        timestamp: float = 0.0,
    ) -> None:
        """
        Add a leg to the distribution.

        O(1) for bin count update. May trigger O(window) median recomputation
        every recompute_interval_legs legs.

        Args:
            leg_id: Unique leg identifier.
            range_val: Leg range value (|origin - pivot|).
            timestamp: Leg creation timestamp for window eviction.
        """
        # Skip if already tracked
        if leg_id in self.leg_ranges:
            return

        # Store in lookup
        self.leg_ranges[leg_id] = range_val

        # Add to window
        self.window.append((leg_id, range_val, timestamp))

        # Update bin count
        bin_idx = self.get_bin_index(range_val)
        self.bin_counts[bin_idx] += 1

        # Maybe recompute median
        self.legs_since_recompute += 1
        if self.legs_since_recompute >= self.recompute_interval_legs:
            self._recompute_median()

    def update_leg(
        self,
        leg_id: str,
        new_range: float,
    ) -> None:
        """
        Update a leg's range when its pivot extends.

        O(1) operation: decrement old bin, increment new bin.

        Args:
            leg_id: Unique leg identifier.
            new_range: New range value after pivot extension.
        """
        if leg_id not in self.leg_ranges:
            return

        old_range = self.leg_ranges[leg_id]
        if old_range == new_range:
            return

        # Update bin counts
        old_bin = self.get_bin_index(old_range)
        new_bin = self.get_bin_index(new_range)

        if old_bin != new_bin:
            self.bin_counts[old_bin] -= 1
            self.bin_counts[new_bin] += 1

        # Update stored range
        self.leg_ranges[leg_id] = new_range

        # Update in window (for median recomputation)
        for i, (lid, _, ts) in enumerate(self.window):
            if lid == leg_id:
                self.window[i] = (leg_id, new_range, ts)
                break

    def remove_leg(self, leg_id: str) -> None:
        """
        Remove a leg from the distribution (on pruning).

        O(1) for bin count update, O(window) for deque removal.

        Args:
            leg_id: Unique leg identifier.
        """
        if leg_id not in self.leg_ranges:
            return

        old_range = self.leg_ranges[leg_id]
        old_bin = self.get_bin_index(old_range)

        # Update bin count
        self.bin_counts[old_bin] -= 1

        # Remove from tracking
        del self.leg_ranges[leg_id]

        # Remove from window (O(n) but infrequent)
        self.window = deque(
            (lid, r, ts) for lid, r, ts in self.window if lid != leg_id
        )

    def _recompute_median(self) -> None:
        """
        Recompute median from current window.

        O(window) operation, called every recompute_interval_legs legs.
        After recomputing median, remaps all legs to new bin edges.
        """
        if not self.window:
            return

        # Extract ranges from window
        ranges = sorted(r for _, r, _ in self.window)

        if not ranges:
            return

        # Compute median
        n = len(ranges)
        if n % 2 == 0:
            self.median = (ranges[n // 2 - 1] + ranges[n // 2]) / 2
        else:
            self.median = ranges[n // 2]

        # Guard against zero median
        if self.median <= 0:
            self.median = 10.0

        # Remap all legs to new bin edges
        self._remap_counts()

        self.legs_since_recompute = 0
        self._warmup_complete = True

    def _remap_counts(self) -> None:
        """
        Remap all legs to new bin edges after median change.

        O(window) operation.
        """
        self.bin_counts = [0] * NUM_BINS

        for leg_id, range_val in self.leg_ranges.items():
            bin_idx = self.get_bin_index(range_val)
            self.bin_counts[bin_idx] += 1

    def evict_old_legs(self, current_timestamp: float) -> List[str]:
        """
        Evict legs older than window_duration_days from the distribution.

        Should be called periodically (e.g., once per day of bars processed).

        Args:
            current_timestamp: Current timestamp in seconds.

        Returns:
            List of evicted leg IDs.
        """
        cutoff = current_timestamp - (self.window_duration_days * 24 * 60 * 60)
        evicted: List[str] = []

        while self.window and self.window[0][2] < cutoff:
            leg_id, range_val, _ = self.window.popleft()
            if leg_id in self.leg_ranges:
                old_bin = self.get_bin_index(range_val)
                self.bin_counts[old_bin] -= 1
                del self.leg_ranges[leg_id]
                evicted.append(leg_id)

        return evicted

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary for persistence.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        return {
            "window_duration_days": self.window_duration_days,
            "recompute_interval_legs": self.recompute_interval_legs,
            "window": [(lid, r, ts) for lid, r, ts in self.window],
            "bin_counts": self.bin_counts.copy(),
            "median": self.median,
            "legs_since_recompute": self.legs_since_recompute,
            "leg_ranges": self.leg_ranges.copy(),
            "_warmup_complete": self._warmup_complete,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RollingBinDistribution":
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict().

        Returns:
            Restored RollingBinDistribution instance.
        """
        dist = cls(
            window_duration_days=data.get("window_duration_days", 90),
            recompute_interval_legs=data.get("recompute_interval_legs", 100),
        )
        dist.window = deque(
            tuple(item) for item in data.get("window", [])
        )
        dist.bin_counts = data.get("bin_counts", [0] * NUM_BINS)
        dist.median = data.get("median", 10.0)
        dist.legs_since_recompute = data.get("legs_since_recompute", 0)
        dist.leg_ranges = data.get("leg_ranges", {})
        dist._warmup_complete = data.get("_warmup_complete", False)
        return dist

    def get_bin_stats(self) -> Dict[str, Any]:
        """
        Get statistics about bin distribution.

        Useful for debugging and visualization.

        Returns:
            Dictionary with bin counts, edges, and median.
        """
        edges = self.bin_edges
        return {
            "median": self.median,
            "total_count": self.total_count,
            "bins": [
                {
                    "index": i,
                    "range": f"{edges[i]:.2f} - {edges[i+1]:.2f}",
                    "multiplier_range": f"{BIN_MULTIPLIERS[i]}× - {BIN_MULTIPLIERS[i+1]}×",
                    "count": self.bin_counts[i],
                    "scale": self._bin_to_scale(i),
                }
                for i in range(NUM_BINS)
            ],
        }

    def _bin_to_scale(self, bin_idx: int) -> str:
        """Map bin index to scale for stats display."""
        if bin_idx <= 7:
            return 'S'
        elif bin_idx == 8:
            return 'M'
        elif bin_idx == 9:
            return 'L'
        else:
            return 'XL'

    def get_median_multiple(self, range_val: float) -> float:
        """
        Get the median multiple for a range value.

        This is the primary display value for the frontend (#436).
        Shows how many times larger than median a leg's range is.

        Args:
            range_val: Leg range value.

        Returns:
            Median multiple (e.g., 2.5 means 2.5× median).
        """
        if self.median <= 0:
            return 1.0
        return range_val / self.median

    def format_median_multiple(self, range_val: float) -> str:
        """
        Format median multiple for display.

        Args:
            range_val: Leg range value.

        Returns:
            Formatted string like "2.5×" or "0.3×".
        """
        multiple = self.get_median_multiple(range_val)
        if multiple >= 10:
            return f"{multiple:.0f}×"
        elif multiple >= 1:
            return f"{multiple:.1f}×"
        else:
            return f"{multiple:.2f}×"

    def get_bin_label(self, bin_idx: int) -> str:
        """
        Get a human-readable label for a bin index.

        Args:
            bin_idx: Bin index (0-10).

        Returns:
            Label like "2-3×" or "25×+".
        """
        if bin_idx < 0 or bin_idx >= NUM_BINS:
            return "?"
        low = BIN_MULTIPLIERS[bin_idx]
        high = BIN_MULTIPLIERS[bin_idx + 1]
        if high == float('inf'):
            return f"{low:.0f}×+"
        elif low == 0:
            return f"<{high}×"
        else:
            return f"{low}-{high}×"
