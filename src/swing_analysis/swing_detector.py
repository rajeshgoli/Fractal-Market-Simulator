import bisect
import decimal
import math
from dataclasses import dataclass, asdict, field
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple, Literal
import numpy as np
import pandas as pd
from .constants import SEPARATION_FIB_LEVELS
from .level_calculator import calculate_levels, Level, score_swing_fib_confluence


@dataclass
class SeparationDetails:
    """Details about structural separation between swings."""
    is_separated: bool
    is_anchor: bool  # True if first swing (no previous to compare)
    containing_swing_id: Optional[str] = None
    from_swing_id: Optional[str] = None  # The swing we measured separation from
    distance_fib: Optional[float] = None  # Actual distance in FIB terms
    minimum_fib: Optional[float] = None   # Threshold used (0.236)


@dataclass
class ReferenceSwing:
    """
    A detected reference swing with all computed properties.

    Reference swings are high-low pairs used to calculate Fibonacci levels.
    - Bull Reference: High BEFORE Low (downswing completed, now bullish)
    - Bear Reference: Low BEFORE High (upswing completed, now bearish)
    """
    # Required fields
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    direction: Literal["bull", "bear"]

    # Level calculations (FIB levels)
    level_0382: float = 0.0
    level_2x: float = 0.0

    # Ranking (computed during filtering)
    rank: int = 0
    impulse: float = 0.0
    size_rank: Optional[int] = None
    impulse_rank: Optional[int] = None
    combined_score: Optional[float] = None

    # Structural properties (computed during Phase 3 filtering)
    structurally_separated: bool = False
    containing_swing_id: Optional[str] = None
    fib_confluence_score: float = 0.0

    # Separation details (for explanation in SWING_FORMED events)
    separation_is_anchor: bool = False  # True if first swing (no previous to compare)
    separation_distance_fib: Optional[float] = None  # Actual distance in fib terms
    separation_minimum_fib: Optional[float] = None   # Threshold used (0.236)
    separation_from_swing_id: Optional[str] = None   # Swing we measured from

    @property
    def span(self) -> int:
        """Number of bars in the swing."""
        return abs(self.high_bar_index - self.low_bar_index) + 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        result = asdict(self)
        # Remove direction from dict output for backward compatibility
        # (existing code doesn't expect direction field in the dict)
        del result['direction']
        return result


def _build_suffix_min(values: np.ndarray) -> np.ndarray:
    """
    Build array where suffix_min[i] = min(values[i:]).

    O(N) preprocessing, O(1) query for suffix minimum.

    Args:
        values: 1D numpy array

    Returns:
        Array where suffix_min[i] = min of all values from index i to end
    """
    if len(values) == 0:
        return np.array([])
    return np.minimum.accumulate(values[::-1])[::-1]


def _build_suffix_max(values: np.ndarray) -> np.ndarray:
    """
    Build array where suffix_max[i] = max(values[i:]).

    O(N) preprocessing, O(1) query for suffix maximum.

    Args:
        values: 1D numpy array

    Returns:
        Array where suffix_max[i] = max of all values from index i to end
    """
    if len(values) == 0:
        return np.array([])
    return np.maximum.accumulate(values[::-1])[::-1]


def _range_min(values: np.ndarray, start: int, end: int) -> Optional[float]:
    """
    Get minimum value in range [start, end).

    Args:
        values: 1D numpy array
        start: Start index (inclusive)
        end: End index (exclusive)

    Returns:
        Minimum value in range, or None if range is invalid/empty
    """
    if start >= end or start < 0 or end > len(values):
        return None
    return float(np.min(values[start:end]))


def _range_max(values: np.ndarray, start: int, end: int) -> Optional[float]:
    """
    Get maximum value in range [start, end).

    Args:
        values: 1D numpy array
        start: Start index (inclusive)
        end: End index (exclusive)

    Returns:
        Maximum value in range, or None if range is invalid/empty
    """
    if start >= end or start < 0 or end > len(values):
        return None
    return float(np.max(values[start:end]))

def _detect_swing_points_vectorized(highs: np.ndarray, lows: np.ndarray, lookback: int) -> tuple:
    """
    Vectorized swing point detection using numpy rolling window operations.

    A swing high at index i requires: highs[i] >= all highs in [i-lookback, i+lookback]
    A swing low at index i requires: lows[i] <= all lows in [i-lookback, i+lookback]

    Args:
        highs: 1D numpy array of high prices
        lows: 1D numpy array of low prices
        lookback: Number of bars before/after to check

    Returns:
        Tuple of (swing_high_indices, swing_low_indices) as numpy arrays
    """
    n = len(highs)
    window_size = 2 * lookback + 1

    if n < window_size:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)

    # Use sliding_window_view for efficient rolling operations (numpy 1.20+)
    # This creates views without copying data
    high_windows = np.lib.stride_tricks.sliding_window_view(highs, window_size)
    low_windows = np.lib.stride_tricks.sliding_window_view(lows, window_size)

    # For each window, the center element is at index `lookback`
    # Find rolling max/min across each window
    rolling_max_high = np.max(high_windows, axis=1)
    rolling_min_low = np.min(low_windows, axis=1)

    # The window results correspond to positions [0, n-window_size]
    # which map to center positions [lookback, n-lookback-1]
    # Extract the center values for comparison
    center_highs = highs[lookback:n - lookback]
    center_lows = lows[lookback:n - lookback]

    # Swing high: center value equals the rolling max (it's >= all neighbors)
    is_swing_high = center_highs == rolling_max_high
    # Swing low: center value equals the rolling min (it's <= all neighbors)
    is_swing_low = center_lows == rolling_min_low

    # Convert boolean masks to indices, offset by lookback to get original positions
    swing_high_indices = np.where(is_swing_high)[0] + lookback
    swing_low_indices = np.where(is_swing_low)[0] + lookback

    return swing_high_indices, swing_low_indices


def get_level_band(price: float, levels: List[Level]) -> Decimal:
    """
    Determines which Fibonacci band a price falls into.
    Returns the multiplier of the lower bound of the band.
    """
    price_dec = Decimal(str(price))
    
    # If below the lowest level
    if price_dec < levels[0].price:
        return Decimal("-999") # "below_stop" represented as a number for simplicity
        
    # Find the closest level
    closest_level = levels[0]
    min_diff = abs(price_dec - levels[0].price)
    
    for level in levels[1:]:
        diff = abs(price_dec - level.price)
        if diff < min_diff:
            min_diff = diff
            closest_level = level
            
    return closest_level.multiplier

def filter_swings(references: List[Dict[str, Any]], direction: str, quantization: Decimal) -> List[Dict[str, Any]]:
    """
    Filters redundant swings using structural Fibonacci bands.
    """
    if not references:
        return []
        
    # Sort by size descending
    sorted_refs = sorted(references, key=lambda x: x["size"], reverse=True)
    
    kept_references = []
    remaining_refs = sorted_refs[:]
    
    while remaining_refs:
        # Take the largest as anchor
        anchor = remaining_refs[0]
        kept_references.append(anchor)
        
        # Compute levels for anchor
        try:
            levels = calculate_levels(
                high=Decimal(str(anchor["high_price"])),
                low=Decimal(str(anchor["low_price"])),
                direction=direction,
                quantization=quantization
            )
        except (ValueError, decimal.InvalidOperation, TypeError):
            # Fallback if calculation fails (shouldn't happen with valid data)
            remaining_refs.pop(0)
            continue

        # Identify anchor bands
        anchor_high_band = get_level_band(anchor["high_price"], levels)
        anchor_low_band = get_level_band(anchor["low_price"], levels)
        
        # Filter current tier
        next_tier_candidates = []
        
        # We already kept index 0. Check the rest.
        # We need to track which ones are redundant to remove them from this tier
        # AND which ones are significantly smaller to form the next tier.
        
        # Actually, the algorithm says:
        # Step 3: Check redundancy against KEPT references.
        # But we are doing it tier by tier.
        # "Take the largest... as anchor... For each remaining reference... determine if structurally distinct from ALL previously kept references."
        # "Two references are redundant if their highs fall in the same level band AND their lows fall in the same level band."
        # "When duplicates exist, keep the largest one." -> We are iterating by size, so the first one we see is the largest.
        
        # Let's refine the loop to match the spec exactly.
        
        # We need to process the list and decide for each item:
        # 1. Is it redundant with current anchor? If so, discard.
        # 2. Is it distinct? Keep it?
        # Wait, the spec says: "Step 4: ... check if there are remaining references that were not redundant but are significantly smaller... take the largest of them as a new anchor for a second tier."
        
        # This implies a recursive or iterative tier approach.
        
        # Let's try this:
        # 1. Start with all refs.
        # 2. Pick largest as anchor. Keep it.
        # 3. Filter the REST of the list:
        #    - If redundant with anchor (same bands), DISCARD.
        #    - If NOT redundant:
        #      - If "significantly smaller" (<= 90% of anchor size), save for NEXT TIER.
        #      - If NOT significantly smaller (similar size but distinct structure), KEEP and use as additional reference for redundancy checks?
        #      The spec says: "determine whether it is structurally distinct from all previously kept references."
        #      This implies we build a list of kept references in this tier.
        
        current_tier_kept = [anchor]
        next_tier_source = []
        
        anchor_size = anchor["size"]
        threshold = anchor_size * 0.9
        
        # Helper to check redundancy against a specific set of levels
        def is_redundant(ref, levels, anchor_high_band, anchor_low_band):
            h_band = get_level_band(ref["high_price"], levels)
            l_band = get_level_band(ref["low_price"], levels)
            return h_band == anchor_high_band and l_band == anchor_low_band

        # We need to check against ALL kept references in this tier?
        # "Take the anchor swing's levels... Two references are redundant if..."
        # It seems we only use the ANCHOR's levels for the entire tier.
        # "Step 3: ... take the anchor swing's levels. Find which level band..."
        
        # Let's track occupied bands in this tier.
        occupied_bands = {(anchor_high_band, anchor_low_band)}
        
        for i in range(1, len(remaining_refs)):
            candidate = remaining_refs[i]
            
            # Check redundancy against the ANCHOR of this tier
            if is_redundant(candidate, levels, anchor_high_band, anchor_low_band):
                continue # Redundant, discard
            
            # Not redundant. Check size.
            if candidate["size"] <= threshold:
                next_tier_source.append(candidate)
            else:
                # Distinct and similar size. Keep it.
                
                h_band = get_level_band(candidate["high_price"], levels)
                l_band = get_level_band(candidate["low_price"], levels)
                
                if (h_band, l_band) not in occupied_bands:
                    kept_references.append(candidate)
                    current_tier_kept.append(candidate) # Just to track if needed
                    occupied_bands.add((h_band, l_band))
                # Else redundant with another kept reference in this tier
        
        # Move to next tier
        remaining_refs = next_tier_source
        
    return kept_references


def _calculate_prominence(price: float, index: int, prices: np.ndarray, lookback: int,
                          is_high: bool) -> float:
    """
    Calculate the prominence of a swing point.

    Prominence measures how much a swing point "stands out" from its neighbors.
    For a swing high, it's the difference between the high and the second-highest
    point within the lookback window. For a swing low, it's the difference between
    the second-lowest and the low.

    Args:
        price: The price of the swing point
        index: Bar index of the swing point
        prices: Full price array (highs for swing highs, lows for swing lows)
        lookback: Number of bars before/after to consider
        is_high: True for swing high, False for swing low

    Returns:
        Prominence value (always >= 0)
    """
    n = len(prices)
    start = max(0, index - lookback)
    end = min(n, index + lookback + 1)

    window = prices[start:end]

    if len(window) < 2:
        return 0.0

    if is_high:
        # For swing high: gap between this high and second-highest
        sorted_vals = sorted(window, reverse=True)
        if prices[index] == sorted_vals[0]:
            # This is the max, prominence is gap to second-highest
            return sorted_vals[0] - sorted_vals[1]
        else:
            # Not actually the max in window (edge case)
            return 0.0
    else:
        # For swing low: gap between second-lowest and this low
        sorted_vals = sorted(window)
        if prices[index] == sorted_vals[0]:
            # This is the min, prominence is gap to second-lowest
            return sorted_vals[1] - sorted_vals[0]
        else:
            # Not actually the min in window (edge case)
            return 0.0


def _apply_prominence_filter(references: List[Dict[str, Any]], highs: np.ndarray,
                              lows: np.ndarray, lookback: int, median_candle: float,
                              min_prominence: float, direction: str) -> List[Dict[str, Any]]:
    """
    Filter swings that don't stand out prominently from surrounding points.

    Args:
        references: List of reference swing dictionaries
        highs: Full numpy array of high prices
        lows: Full numpy array of low prices
        lookback: Lookback window for prominence calculation
        median_candle: Median candle height
        min_prominence: Minimum prominence as multiple of median candle
        direction: 'bull' or 'bear' to determine which swing point to check

    Returns:
        Filtered list of references
    """
    if min_prominence is None or median_candle <= 0:
        return references

    threshold = min_prominence * median_candle
    filtered = []

    for ref in references:
        if direction == 'bull':
            # Bull reference: high before low (downswing). Check the swing low.
            # The low should stand out from surrounding lows.
            prominence = _calculate_prominence(
                ref["low_price"], ref["low_bar_index"], lows, lookback, is_high=False
            )
        else:
            # Bear reference: low before high (upswing). Check the swing high.
            # The high should stand out from surrounding highs.
            prominence = _calculate_prominence(
                ref["high_price"], ref["high_bar_index"], highs, lookback, is_high=True
            )

        if prominence >= threshold:
            filtered.append(ref)

    return filtered


def _adjust_to_best_extrema(swing: Dict[str, Any], highs: np.ndarray,
                            lows: np.ndarray, lookback: int) -> Dict[str, Any]:
    """
    Adjust swing endpoints to the best extrema in vicinity.

    For swing highs: find highest high within ±lookback bars
    For swing lows: find lowest low within ±lookback bars

    Args:
        swing: Reference swing dictionary with high_bar_index, low_bar_index, etc.
        highs: Full numpy array of high prices
        lows: Full numpy array of low prices
        lookback: Number of bars before/after to search for better extrema

    Returns:
        Adjusted swing dictionary with updated endpoints and recalculated size
    """
    adjusted = swing.copy()
    n = len(highs)

    # Adjust high endpoint - find highest high in vicinity
    high_idx = swing['high_bar_index']
    start = max(0, high_idx - lookback)
    end = min(n, high_idx + lookback + 1)

    window_highs = highs[start:end]
    best_high_offset = int(np.argmax(window_highs))
    best_high_idx = start + best_high_offset

    adjusted['high_bar_index'] = best_high_idx
    adjusted['high_price'] = float(highs[best_high_idx])

    # Adjust low endpoint - find lowest low in vicinity
    low_idx = swing['low_bar_index']
    start = max(0, low_idx - lookback)
    end = min(n, low_idx + lookback + 1)

    window_lows = lows[start:end]
    best_low_offset = int(np.argmin(window_lows))
    best_low_idx = start + best_low_offset

    adjusted['low_bar_index'] = best_low_idx
    adjusted['low_price'] = float(lows[best_low_idx])

    # Recalculate size
    adjusted['size'] = adjusted['high_price'] - adjusted['low_price']

    # Recalculate level references
    size = adjusted['size']
    if size > 0:
        adjusted['level_0382'] = adjusted['low_price'] + (0.382 * size)
        adjusted['level_2x'] = adjusted['low_price'] + (2.0 * size)

    return adjusted


def _apply_quota(references: List[Dict[str, Any]], quota: int) -> List[Dict[str, Any]]:
    """
    Rank swings by combined score and return top N.

    Combined score = 0.6 × size_rank + 0.4 × impulse_rank
    Lower combined score is better (closer to rank 1 in both dimensions).

    Args:
        references: List of reference swing dictionaries with 'size',
                   'high_bar_index', and 'low_bar_index' keys
        quota: Maximum number of swings to return

    Returns:
        Top N swings by combined score, with added fields:
        - impulse: size / span (measures how quickly the swing formed)
        - size_rank: rank by size (1 = largest)
        - impulse_rank: rank by impulse (1 = most impulsive)
        - combined_score: weighted combination of ranks (lower is better)
    """
    if not references or quota is None:
        return references

    SIZE_WEIGHT = 0.6
    IMPULSE_WEIGHT = 0.4

    # Calculate impulse for each swing
    for ref in references:
        span = abs(ref['high_bar_index'] - ref['low_bar_index']) + 1
        ref['impulse'] = ref['size'] / span if span > 0 else 0.0

    # Rank by size (1 = largest)
    by_size = sorted(references, key=lambda r: r['size'], reverse=True)
    for rank, ref in enumerate(by_size, 1):
        ref['size_rank'] = rank

    # Rank by impulse (1 = most impulsive)
    by_impulse = sorted(references, key=lambda r: r['impulse'], reverse=True)
    for rank, ref in enumerate(by_impulse, 1):
        ref['impulse_rank'] = rank

    # Combined score (lower is better)
    for ref in references:
        ref['combined_score'] = (SIZE_WEIGHT * ref['size_rank'] +
                                  IMPULSE_WEIGHT * ref['impulse_rank'])

    # Sort by combined score and take top N
    references.sort(key=lambda r: r['combined_score'])
    return references[:quota]


def _apply_protection_filter(references: List[Dict[str, Any]], direction: str,
                              highs: np.ndarray, lows: np.ndarray,
                              protection_tolerance: float,
                              suffix_max_highs: Optional[np.ndarray],
                              suffix_min_lows: Optional[np.ndarray]) -> List[Dict[str, Any]]:
    """
    Filter references where swing points are violated.

    Protection validation checks:
    - Pre-formation: Was the swing point violated before the pair formed?
    - Post-formation: Was the swing point violated after formation?

    Args:
        references: List of reference swing dictionaries
        direction: 'bull' or 'bear'
        highs: Full numpy array of high prices
        lows: Full numpy array of low prices
        protection_tolerance: Fraction of swing size for violation threshold
        suffix_max_highs: Precomputed suffix max array for highs (suffix_max[i] = max(highs[i:]))
        suffix_min_lows: Precomputed suffix min array for lows (suffix_min[i] = min(lows[i:]))

    Returns:
        Filtered list of references that pass protection validation
    """
    if protection_tolerance is None:
        return references

    filtered = []

    for ref in references:
        high_idx = ref['high_bar_index']
        low_idx = ref['low_bar_index']
        high_price = ref['high_price']
        low_price = ref['low_price']
        size = ref['size']

        if direction == 'bull':
            # Bull reference: High BEFORE Low (downswing)
            # Pre-formation: high not violated before low forms
            max_between = _range_max(highs, high_idx + 1, low_idx)
            if max_between is not None and max_between > high_price:
                continue  # High was violated before low formed

            # Post-formation: swing low not violated after formation
            if suffix_min_lows is not None and low_idx + 1 < len(suffix_min_lows):
                violation_threshold = low_price - (protection_tolerance * size)
                min_subsequent = suffix_min_lows[low_idx + 1]
                if min_subsequent < violation_threshold:
                    continue  # Low was violated
        else:
            # Bear reference: Low BEFORE High (upswing)
            # Pre-formation: low not violated before high forms
            min_between = _range_min(lows, low_idx + 1, high_idx)
            if min_between is not None and min_between < low_price:
                continue  # Low was violated before high formed

            # Post-formation: swing high not violated after formation
            if suffix_max_highs is not None and high_idx + 1 < len(suffix_max_highs):
                violation_threshold = high_price + (protection_tolerance * size)
                max_subsequent = suffix_max_highs[high_idx + 1]
                if max_subsequent > violation_threshold:
                    continue  # High was violated

        filtered.append(ref)

    return filtered


def _apply_size_filter(references: List[Dict[str, Any]], median_candle: float,
                       price_range: float, min_candle_ratio: Optional[float],
                       min_range_pct: Optional[float],
                       high_volatility_ratio: float = 3.0) -> List[Dict[str, Any]]:
    """
    Filter swings that are too small relative to context.

    A swing is kept if it passes ANY of these conditions (OR logic):
    - candle_ratio >= min_candle_ratio
    - range_pct >= min_range_pct
    - High volatility exception: span <= 2 bars AND size >= high_volatility_ratio * median_candle

    A swing is filtered only if it fails ALL conditions.

    Args:
        references: List of reference swing dictionaries with 'size' key
        median_candle: Median candle height in the window
        price_range: Total price range of the window (max - min)
        min_candle_ratio: Minimum size as multiple of median candle (or None to skip)
        min_range_pct: Minimum size as percentage of price range (or None to skip)
        high_volatility_ratio: Multiplier for high-volatility exception (default 3.0)

    Returns:
        Filtered list of references
    """
    # If neither filter is set, return unchanged
    if min_candle_ratio is None and min_range_pct is None:
        return references

    # Avoid division by zero
    if median_candle <= 0 or price_range <= 0:
        return references

    filtered = []
    for ref in references:
        size = ref["size"]

        # Calculate metrics
        candle_ratio = size / median_candle
        range_pct = (size / price_range) * 100

        # Calculate span in bars
        span = abs(ref["high_bar_index"] - ref["low_bar_index"]) + 1

        # OR logic: keep if any condition passes
        passes_candle = min_candle_ratio is None or candle_ratio >= min_candle_ratio
        passes_range = min_range_pct is None or range_pct >= min_range_pct

        # High volatility exception: 1-2 bar swings with large candles are significant
        passes_high_volatility = span <= 2 and candle_ratio >= high_volatility_ratio

        if passes_candle or passes_range or passes_high_volatility:
            filtered.append(ref)

    return filtered


def find_containing_swing(
    swing: Dict[str, Any],
    larger_swings: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Find the smallest swing from larger_swings that contains this swing.

    A containing swing has:
    - high >= swing.high
    - low <= swing.low
    - bar_index range overlaps

    Args:
        swing: The swing to find a container for
        larger_swings: List of swings at a larger scale

    Returns:
        The smallest containing swing, or None if no container found
    """
    if not larger_swings:
        return None

    swing_high = swing.get('high_price', 0)
    swing_low = swing.get('low_price', 0)
    swing_start = min(swing.get('high_bar_index', 0), swing.get('low_bar_index', 0))
    swing_end = max(swing.get('high_bar_index', 0), swing.get('low_bar_index', 0))

    candidates = []
    for ls in larger_swings:
        ls_high = ls.get('high_price', 0)
        ls_low = ls.get('low_price', 0)
        ls_start = min(ls.get('high_bar_index', 0), ls.get('low_bar_index', 0))
        ls_end = max(ls.get('high_bar_index', 0), ls.get('low_bar_index', 0))

        # Check if larger swing contains this swing
        if (ls_high >= swing_high and
            ls_low <= swing_low and
            ls_start <= swing_start and
            ls_end >= swing_end):
            candidates.append(ls)

    if not candidates:
        return None

    # Return smallest containing swing (most relevant context)
    return min(candidates, key=lambda s: s.get('size', float('inf')))


def _fallback_separation_check(
    swing: Dict[str, Any],
    previous_swings: List[Dict[str, Any]],
    lookback: int,
    median_candle: float
) -> bool:
    """
    Fallback separation check when no larger swing exists (XL scale or window edges).

    Uses N-bar separation and X% move criteria instead of FIB-based separation.

    Args:
        swing: The swing to check
        previous_swings: List of previous swings of the same direction
        lookback: Lookback parameter from detection
        median_candle: Median candle height in the window

    Returns:
        True if swing is sufficiently separated, False otherwise
    """
    if not previous_swings:
        return True  # No previous swings = automatically separated

    # Minimum separation thresholds
    min_bar_separation = 2 * lookback  # Non-overlapping detection windows
    min_price_separation = 0.236 * median_candle * lookback  # FIB-equivalent (smallest level)

    swing_low_idx = swing.get('low_bar_index', 0)
    swing_high_idx = swing.get('high_bar_index', 0)
    swing_low_price = swing.get('low_price', 0)
    swing_high_price = swing.get('high_price', 0)

    for prev in previous_swings:
        prev_high_idx = prev.get('high_bar_index', 0)
        prev_low_idx = prev.get('low_bar_index', 0)
        prev_high_price = prev.get('high_price', 0)
        prev_low_price = prev.get('low_price', 0)

        # Check separation between swing endpoints
        # For bull references (high->low), check separation from previous low to current high
        bar_sep = abs(swing_low_idx - prev_high_idx)
        price_sep = abs(swing_low_price - prev_high_price)

        # Too close in both time and price = not separated
        if bar_sep < min_bar_separation and price_sep < min_price_separation:
            return False

    return True


def is_structurally_separated(
    swing: Dict[str, Any],
    previous_swings: List[Dict[str, Any]],
    larger_swings: Optional[List[Dict[str, Any]]],
    lookback: int,
    median_candle: float
) -> SeparationDetails:
    """
    Check if swing is structurally separated from previous swings.

    For High B to register after High A:
    1. There must be a Low L between A and B
    2. L must be >= 1 FIB level from High A (on larger-scale grid)
    3. High B and L must be >= 1 FIB level apart

    Uses extended FIB grid (includes 0.236, 0.786, 1.236, 1.786) for
    better coverage of structural reversals.

    Args:
        swing: The swing to validate
        previous_swings: Previous swings of the same direction to check against
        larger_swings: Swings from the next larger scale (for FIB grid reference)
        lookback: Lookback parameter from detection
        median_candle: Median candle height

    Returns:
        SeparationDetails with is_separated, is_anchor, containing_swing_id,
        from_swing_id, distance_fib, and minimum_fib fields.
    """
    if not previous_swings:
        # No previous swings = automatically separated (anchor swing)
        return SeparationDetails(is_separated=True, is_anchor=True)

    if not larger_swings:
        # XL or window edge: use fallback
        is_sep = _fallback_separation_check(swing, previous_swings, lookback, median_candle)
        return SeparationDetails(is_separated=is_sep, is_anchor=False)

    # Get FIB grid from immediate larger swing
    containing = find_containing_swing(swing, larger_swings)
    if not containing:
        is_sep = _fallback_separation_check(swing, previous_swings, lookback, median_candle)
        return SeparationDetails(is_separated=is_sep, is_anchor=False)

    containing_id = containing.get('swing_id')
    swing_size = containing.get('size', 0)
    if swing_size <= 0:
        is_sep = _fallback_separation_check(swing, previous_swings, lookback, median_candle)
        return SeparationDetails(is_separated=is_sep, is_anchor=False, containing_swing_id=containing_id)

    # Minimum separation = 0.236 * containing swing size (smallest FIB level)
    minimum_fib = 0.236
    min_separation = minimum_fib * swing_size

    swing_low_price = swing.get('low_price', 0)
    swing_high_price = swing.get('high_price', 0)

    # Track the closest previous swing for reporting
    closest_prev_id = None
    min_distance_fib = float('inf')

    for prev in previous_swings:
        prev_id = prev.get('swing_id')
        prev_high_price = prev.get('high_price', 0)
        prev_low_price = prev.get('low_price', 0)

        # Check separation between swing endpoints
        # For bull references: compare current low to previous high
        separation = abs(swing_low_price - prev_high_price)
        distance_fib = separation / swing_size if swing_size > 0 else 0

        # Track the closest one
        if distance_fib < min_distance_fib:
            min_distance_fib = distance_fib
            closest_prev_id = prev_id

        if separation < min_separation:
            # Not structurally distinct - return details about the failing check
            return SeparationDetails(
                is_separated=False,
                is_anchor=False,
                containing_swing_id=containing_id,
                from_swing_id=prev_id,
                distance_fib=distance_fib,
                minimum_fib=minimum_fib,
            )

    # Passed all separation checks
    return SeparationDetails(
        is_separated=True,
        is_anchor=False,
        containing_swing_id=containing_id,
        from_swing_id=closest_prev_id,
        distance_fib=min_distance_fib if min_distance_fib != float('inf') else None,
        minimum_fib=minimum_fib,
    )


def _apply_structural_separation_filter(
    references: List[Dict[str, Any]],
    larger_swings: Optional[List[Dict[str, Any]]],
    lookback: int,
    median_candle: float,
    direction: str
) -> List[Dict[str, Any]]:
    """
    Filter swings that are not structurally separated from each other.

    Processes references in order (by detection) and filters those that
    are too close to previously accepted swings.

    Args:
        references: List of reference swing dictionaries
        larger_swings: Swings from the next larger scale
        lookback: Lookback parameter
        median_candle: Median candle height
        direction: 'bull' or 'bear'

    Returns:
        Filtered list of references with structural separation data added
    """
    if not references:
        return references

    filtered = []
    accepted_swings = []  # Track accepted swings for separation checks

    for ref in references:
        details = is_structurally_separated(
            ref, accepted_swings, larger_swings, lookback, median_candle
        )

        # Add structural separation metadata
        ref['structurally_separated'] = details.is_separated
        ref['containing_swing_id'] = details.containing_swing_id

        # Add separation explanation details
        ref['separation_is_anchor'] = details.is_anchor
        ref['separation_from_swing_id'] = details.from_swing_id
        ref['separation_distance_fib'] = details.distance_fib
        ref['separation_minimum_fib'] = details.minimum_fib

        if details.is_separated:
            filtered.append(ref)
            accepted_swings.append(ref)

    return filtered


def detect_swings(df: pd.DataFrame, lookback: int = 5, filter_redundant: bool = True,
                  quantization: float = 0.25, max_pair_distance: Optional[int] = None,
                  protection_tolerance: float = 0.1,
                  min_candle_ratio: Optional[float] = None,
                  min_range_pct: Optional[float] = None,
                  min_prominence: Optional[float] = None,
                  adjust_extrema: bool = True,
                  quota: Optional[int] = None,
                  larger_swings: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Identifies swing highs and lows and pairs them to find valid reference swings.

    Args:
        df: DataFrame with columns 'open', 'high', 'low', 'close'.
        lookback: Number of bars before and after to check for swing points.
        filter_redundant: Whether to apply structural filtering to remove redundant swings.
        quantization: Tick size for Fibonacci level calculation.
        max_pair_distance: Maximum bar distance between swing pairs. None for no limit.
            For large datasets (>100K bars), recommend setting to 2000-5000 for performance.
            This limits reference swing detection to swings within this bar distance.
        protection_tolerance: Fraction of swing size that the swing point can be violated
            before the reference is invalidated. Default 0.1 (10%). Set to None to disable.
        min_candle_ratio: Minimum swing size as multiple of median candle height.
            Swings smaller than this are filtered. Uses OR logic with min_range_pct.
        min_range_pct: Minimum swing size as percentage of window price range.
            Swings smaller than this are filtered. Uses OR logic with min_candle_ratio.
        min_prominence: Minimum prominence as multiple of median candle height.
            Filters swings where the swing point doesn't "stand out" from neighbors.
            Prominence is the gap between the extremum and second-best in lookback window.
        adjust_extrema: Whether to adjust swing endpoints to the best extrema in the
            vicinity (within ±lookback bars). Default True. Set to False to preserve
            original endpoint detection behavior.
        quota: If set, limit output to top N swings per direction using combined
            size+impulse ranking. Adds impulse, size_rank, impulse_rank, and
            combined_score fields to output.
        larger_swings: Optional list of swings from the next larger scale (e.g., XL swings
            when detecting L swings). Used for structural separation gate (Phase 3).
            When provided, swings must be >= 0.236 FIB level apart from previous swings
            relative to the containing larger swing. If None, fallback separation check
            uses N-bar and X% move criteria instead.

    Returns:
        A dictionary containing current price, detected swing points, and valid reference swings.
        When larger_swings is provided, each swing includes:
        - structurally_separated: bool indicating if swing passed separation gate
        - containing_swing_id: ID of the containing larger-scale swing (if found)
        - fib_confluence_score: score (0.0-1.0) for proximity to FIB levels (if scored)
    """
    # Validate input DataFrame
    if df.empty:
        return {
            "current_price": 0.0,
            "swing_highs": [],
            "swing_lows": [],
            "bull_references": [],
            "bear_references": []
        }
        
    current_price = float(df.iloc[-1]['close'])

    # 1. Detect Swing Points (vectorized)
    # Extract numpy arrays for fast operations
    highs = df['high'].values.astype(np.float64)
    lows = df['low'].values.astype(np.float64)

    swing_high_indices, swing_low_indices = _detect_swing_points_vectorized(highs, lows, lookback)

    # Build suffix arrays on ALL bar data for O(1) protection queries
    # These check if swing points were violated by subsequent price action
    suffix_min_lows = _build_suffix_min(lows) if protection_tolerance is not None else None
    suffix_max_highs = _build_suffix_max(highs) if protection_tolerance is not None else None

    # Calculate context metrics for size filtering
    candle_heights = highs - lows
    median_candle = float(np.median(candle_heights)) if len(candle_heights) > 0 else 0.0
    price_range = float(np.max(highs) - np.min(lows)) if len(highs) > 0 else 0.0

    # Convert to list of dicts format
    swing_highs = [{"price": float(highs[i]), "bar_index": int(i)} for i in swing_high_indices]
    swing_lows = [{"price": float(lows[i]), "bar_index": int(i)} for i in swing_low_indices]

    bull_references = []
    bear_references = []

    # 2. Pair and Validate Swings
    # Pre-compute sorted index/price arrays for O(log N) binary search lookups
    # Both arrays are already sorted by bar_index due to chronological detection order
    low_indices = [l["bar_index"] for l in swing_lows]
    low_prices = np.array([l["price"] for l in swing_lows])
    high_indices = [h["bar_index"] for h in swing_highs]
    high_prices = np.array([h["price"] for h in swing_highs])

    # Bull References: High BEFORE Low (Downswing)
    # O(H × D) where D = swings within max_pair_distance, with O(1) interval validation
    for high_swing in swing_highs:
        high_idx = high_swing["bar_index"]
        high_price = high_swing["price"]

        # Binary search: find first low_swing where bar_index > high_idx
        start_j = bisect.bisect_right(low_indices, high_idx)

        for j in range(start_j, len(swing_lows)):
            low_idx = low_indices[j]

            # EARLY TERMINATION: distance check (enables O(D) inner loop)
            bar_distance = low_idx - high_idx
            if max_pair_distance is not None and bar_distance > max_pair_distance:
                break  # All subsequent lows are even farther away

            low_price = low_prices[j]
            size = high_price - low_price

            # CHEAP CHECK 1: geometric validity
            if size <= 0:
                continue

            # CHEAP CHECK 2: price range validity (eliminates most pairs)
            level_0382 = low_price + (0.382 * size)
            level_2x = low_price + (2.0 * size)
            if not (level_0382 < current_price < level_2x):
                continue

            # EXPENSIVE CHECK: structural validity using numpy range query
            # The Low must be the lowest point between High and Low.
            is_valid_structure = True
            if start_j < j:
                interval_min = _range_min(low_prices, start_j, j)
                if interval_min is not None and interval_min < low_price:
                    is_valid_structure = False

            if not is_valid_structure:
                continue

            # INLINE PROTECTION (only when adjust_extrema=False for backward compatibility)
            # When adjust_extrema=True, protection is applied after adjustment
            if not adjust_extrema:
                # PRE-FORMATION PROTECTION: high not violated before low forms
                # If a higher high appeared between high_idx and low_idx, this reference is invalid
                if protection_tolerance is not None:
                    max_between = _range_max(highs, high_idx + 1, low_idx)
                    if max_between is not None and max_between > high_price:
                        continue  # High was violated before low formed

                # POST-FORMATION PROTECTION: swing low not violated by subsequent price action
                if protection_tolerance is not None and suffix_min_lows is not None:
                    violation_threshold = low_price - (protection_tolerance * size)
                    # Check all bars after the swing low (O(1) suffix query)
                    if low_idx + 1 < len(suffix_min_lows):
                        min_subsequent_low = suffix_min_lows[low_idx + 1]
                        if min_subsequent_low < violation_threshold:
                            continue  # Low was violated, skip this reference

            bull_references.append({
                "high_price": high_price,
                "high_bar_index": high_idx,
                "low_price": low_price,
                "low_bar_index": low_idx,
                "size": size,
                "level_0382": level_0382,
                "level_2x": level_2x,
                "rank": 0  # Placeholder
            })

    # Bear References: Low BEFORE High (Upswing)
    # O(L × D) where D = swings within max_pair_distance, with O(1) interval validation
    for low_swing in swing_lows:
        low_idx = low_swing["bar_index"]
        low_price = low_swing["price"]

        # Binary search: find first high_swing where bar_index > low_idx
        start_j = bisect.bisect_right(high_indices, low_idx)

        for j in range(start_j, len(swing_highs)):
            high_idx = high_indices[j]

            # EARLY TERMINATION: distance check (enables O(D) inner loop)
            bar_distance = high_idx - low_idx
            if max_pair_distance is not None and bar_distance > max_pair_distance:
                break  # All subsequent highs are even farther away

            high_price = high_prices[j]
            size = high_price - low_price

            # CHEAP CHECK 1: geometric validity
            if size <= 0:
                continue

            # CHEAP CHECK 2: price range validity (eliminates most pairs)
            level_0382 = high_price - (0.382 * size)
            level_2x = high_price - (2.0 * size)
            if not (level_2x < current_price < level_0382):
                continue

            # EXPENSIVE CHECK: structural validity using numpy range query
            # The High must be the highest point between Low and High.
            is_valid_structure = True
            if start_j < j:
                interval_max = _range_max(high_prices, start_j, j)
                if interval_max is not None and interval_max > high_price:
                    is_valid_structure = False

            if not is_valid_structure:
                continue

            # INLINE PROTECTION (only when adjust_extrema=False for backward compatibility)
            # When adjust_extrema=True, protection is applied after adjustment
            if not adjust_extrema:
                # PRE-FORMATION PROTECTION: low not violated before high forms
                # If a lower low appeared between low_idx and high_idx, this reference is invalid
                if protection_tolerance is not None:
                    min_between = _range_min(lows, low_idx + 1, high_idx)
                    if min_between is not None and min_between < low_price:
                        continue  # Low was violated before high formed

                # POST-FORMATION PROTECTION: swing high not violated by subsequent price action
                if protection_tolerance is not None and suffix_max_highs is not None:
                    violation_threshold = high_price + (protection_tolerance * size)
                    # Check all bars after the swing high (O(1) suffix query)
                    if high_idx + 1 < len(suffix_max_highs):
                        max_subsequent_high = suffix_max_highs[high_idx + 1]
                        if max_subsequent_high > violation_threshold:
                            continue  # High was violated, skip this reference

            bear_references.append({
                "high_price": high_price,
                "high_bar_index": high_idx,
                "low_price": low_price,
                "low_bar_index": low_idx,
                "size": size,
                "level_0382": level_0382,
                "level_2x": level_2x,
                "rank": 0  # Placeholder
            })

    # 3. Best Extrema Adjustment (when enabled)
    # Adjusts swing endpoints to the best extrema within ±lookback bars
    if adjust_extrema:
        bull_references = [
            _adjust_to_best_extrema(ref, highs, lows, lookback)
            for ref in bull_references
        ]
        bear_references = [
            _adjust_to_best_extrema(ref, highs, lows, lookback)
            for ref in bear_references
        ]

    # 4. Protection Validation (after adjustment when adjust_extrema=True)
    # Re-validates protection with potentially adjusted endpoints
    if adjust_extrema and protection_tolerance is not None:
        bull_references = _apply_protection_filter(
            bull_references, 'bull', highs, lows,
            protection_tolerance, suffix_max_highs, suffix_min_lows
        )
        bear_references = _apply_protection_filter(
            bear_references, 'bear', highs, lows,
            protection_tolerance, suffix_max_highs, suffix_min_lows
        )

    # 5. Apply Size Filter (after protection, before prominence)
    if min_candle_ratio is not None or min_range_pct is not None:
        bull_references = _apply_size_filter(
            bull_references, median_candle, price_range, min_candle_ratio, min_range_pct
        )
        bear_references = _apply_size_filter(
            bear_references, median_candle, price_range, min_candle_ratio, min_range_pct
        )

    # 6. Apply Prominence Filter (after size, before structural separation)
    if min_prominence is not None:
        bull_references = _apply_prominence_filter(
            bull_references, highs, lows, lookback, median_candle, min_prominence, 'bull'
        )
        bear_references = _apply_prominence_filter(
            bear_references, highs, lows, lookback, median_candle, min_prominence, 'bear'
        )

    # 7. Structural Separation Gate (Phase 3) - uses larger_swings context
    # Filters swings that are not structurally distinct (< 0.236 FIB level apart)
    if larger_swings is not None:
        bull_references = _apply_structural_separation_filter(
            bull_references, larger_swings, lookback, median_candle, 'bull'
        )
        bear_references = _apply_structural_separation_filter(
            bear_references, larger_swings, lookback, median_candle, 'bear'
        )

    # 8. Filter Redundant Swings (Optional)
    if filter_redundant:
        quant_dec = Decimal(str(quantization))
        bull_references = filter_swings(bull_references, "bullish", quant_dec)
        bear_references = filter_swings(bear_references, "bearish", quant_dec)

    # 9. Fib Confluence Scoring (Phase 3B) - score proximity to FIB levels
    # Only applied when larger_swings context is provided
    if larger_swings is not None:
        for ref in bull_references:
            containing = find_containing_swing(ref, larger_swings)
            score_swing_fib_confluence(ref, containing, direction='bull')
        for ref in bear_references:
            containing = find_containing_swing(ref, larger_swings)
            score_swing_fib_confluence(ref, containing, direction='bear')

    # 10. Apply Quota Filter (takes precedence over max_rank)
    # Quota uses combined size+impulse ranking for better swing selection
    if quota is not None:
        bull_references = _apply_quota(bull_references, quota)
        bear_references = _apply_quota(bear_references, quota)

    # 11. Sort and Rank
    # Sort by size descending (or by combined_score if quota was applied)
    if quota is not None:
        # Quota already sorted by combined_score, keep that order
        # Assign final rank based on position
        for idx, ref in enumerate(bull_references):
            ref["rank"] = idx + 1
        for idx, ref in enumerate(bear_references):
            ref["rank"] = idx + 1
    else:
        # Traditional ranking by size
        bull_references.sort(key=lambda x: x["size"], reverse=True)
        for idx, ref in enumerate(bull_references):
            ref["rank"] = idx + 1

        bear_references.sort(key=lambda x: x["size"], reverse=True)
        for idx, ref in enumerate(bear_references):
            ref["rank"] = idx + 1

    return {
        "current_price": current_price,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "bull_references": bull_references,
        "bear_references": bear_references
    }