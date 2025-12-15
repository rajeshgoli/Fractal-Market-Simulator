import bisect
import math
from decimal import Decimal
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from .level_calculator import calculate_levels, Level


class SparseTable:
    """
    Sparse Table for O(1) Range Minimum/Maximum Queries.

    Preprocessing: O(N log N) time and space
    Query: O(1) time

    Used to efficiently check if any value in a range is below/above a threshold.
    """

    def __init__(self, values: List[float], mode: str = 'min'):
        """
        Build sparse table from values.

        Args:
            values: List of values to build the table from
            mode: 'min' for range minimum queries, 'max' for range maximum
        """
        self.n = len(values)
        self.mode = mode

        if self.n == 0:
            self.log_table = []
            self.table = []
            return

        # Precompute log values
        self.log_table = [0] * (self.n + 1)
        for i in range(2, self.n + 1):
            self.log_table[i] = self.log_table[i // 2] + 1

        self.k = self.log_table[self.n] + 1 if self.n > 0 else 1

        # Build sparse table
        # table[j][i] = min/max of range [i, i + 2^j - 1]
        self.table = [[float('inf') if mode == 'min' else float('-inf')] * self.n for _ in range(self.k)]

        # Initialize with original values
        for i in range(self.n):
            self.table[0][i] = values[i]

        # Build table
        compare = min if mode == 'min' else max
        for j in range(1, self.k):
            length = 1 << j  # 2^j
            for i in range(self.n - length + 1):
                self.table[j][i] = compare(
                    self.table[j - 1][i],
                    self.table[j - 1][i + (1 << (j - 1))]
                )

    def query(self, left: int, right: int) -> Optional[float]:
        """
        Query min/max in range [left, right) (exclusive right).

        Returns None if range is empty or invalid.
        """
        if left >= right or left < 0 or right > self.n:
            return None

        length = right - left
        if length == 0:
            return None

        k = self.log_table[length]
        compare = min if self.mode == 'min' else max

        return compare(
            self.table[k][left],
            self.table[k][right - (1 << k)]
        )

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
        except Exception:
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

def detect_swings(df: pd.DataFrame, lookback: int = 5, filter_redundant: bool = True,
                  quantization: float = 0.25, max_pair_distance: Optional[int] = None,
                  protection_tolerance: float = 0.1, max_rank: Optional[int] = None) -> Dict[str, Any]:
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
        max_rank: If set, only return top N swings per direction (bull and bear).
            Reduces noise from secondary structures. Default None returns all swings.

    Returns:
        A dictionary containing current price, detected swing points, and valid reference swings.
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

    # Build sparse tables on ALL bar data for O(1) protection queries
    # These check if swing points were violated by subsequent price action
    all_lows_min_table = SparseTable(lows.tolist(), mode='min') if protection_tolerance is not None else None
    all_highs_max_table = SparseTable(highs.tolist(), mode='max') if protection_tolerance is not None else None

    # Convert to list of dicts format
    swing_highs = [{"price": float(highs[i]), "bar_index": int(i)} for i in swing_high_indices]
    swing_lows = [{"price": float(lows[i]), "bar_index": int(i)} for i in swing_low_indices]

    bull_references = []
    bear_references = []

    # 2. Pair and Validate Swings
    # Pre-compute sorted index/price arrays for O(log N) binary search lookups
    # Both arrays are already sorted by bar_index due to chronological detection order
    low_indices = [l["bar_index"] for l in swing_lows]
    low_prices = [l["price"] for l in swing_lows]
    high_indices = [h["bar_index"] for h in swing_highs]
    high_prices = [h["price"] for h in swing_highs]

    # Build sparse tables for O(1) range min/max queries
    low_min_table = SparseTable(low_prices, mode='min')
    high_max_table = SparseTable(high_prices, mode='max')

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

            # EXPENSIVE CHECK: structural validity using O(1) RMQ
            # The Low must be the lowest point between High and Low.
            interval_start = start_j
            interval_end = j  # Current position (exclusive)

            is_valid_structure = True
            if interval_start < interval_end:
                interval_min = low_min_table.query(interval_start, interval_end)
                if interval_min is not None and interval_min < low_price:
                    is_valid_structure = False

            if not is_valid_structure:
                continue

            # PRE-FORMATION PROTECTION: high not violated before low forms
            # If a higher high appeared between high_idx and low_idx, this reference is invalid
            if protection_tolerance is not None and all_highs_max_table is not None:
                max_between = all_highs_max_table.query(high_idx + 1, low_idx)
                if max_between is not None and max_between > high_price:
                    continue  # High was violated before low formed

            # POST-FORMATION PROTECTION: swing low not violated by subsequent price action
            if protection_tolerance is not None and all_lows_min_table is not None:
                violation_threshold = low_price - (protection_tolerance * size)
                # Check all bars after the swing low
                min_subsequent_low = all_lows_min_table.query(low_idx + 1, len(lows))
                if min_subsequent_low is not None and min_subsequent_low < violation_threshold:
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

            # EXPENSIVE CHECK: structural validity using O(1) RMQ
            # The High must be the highest point between Low and High.
            interval_start = start_j
            interval_end = j  # Current position (exclusive)

            is_valid_structure = True
            if interval_start < interval_end:
                interval_max = high_max_table.query(interval_start, interval_end)
                if interval_max is not None and interval_max > high_price:
                    is_valid_structure = False

            if not is_valid_structure:
                continue

            # PRE-FORMATION PROTECTION: low not violated before high forms
            # If a lower low appeared between low_idx and high_idx, this reference is invalid
            if protection_tolerance is not None and all_lows_min_table is not None:
                min_between = all_lows_min_table.query(low_idx + 1, high_idx)
                if min_between is not None and min_between < low_price:
                    continue  # Low was violated before high formed

            # POST-FORMATION PROTECTION: swing high not violated by subsequent price action
            if protection_tolerance is not None and all_highs_max_table is not None:
                violation_threshold = high_price + (protection_tolerance * size)
                # Check all bars after the swing high
                max_subsequent_high = all_highs_max_table.query(high_idx + 1, len(highs))
                if max_subsequent_high is not None and max_subsequent_high > violation_threshold:
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

    # 3. Filter Redundant Swings (Optional)
    if filter_redundant:
        quant_dec = Decimal(str(quantization))
        bull_references = filter_swings(bull_references, "bullish", quant_dec)
        bear_references = filter_swings(bear_references, "bearish", quant_dec)

    # 4. Sort and Rank
    # Sort by size descending
    bull_references.sort(key=lambda x: x["size"], reverse=True)
    for idx, ref in enumerate(bull_references):
        ref["rank"] = idx + 1

    bear_references.sort(key=lambda x: x["size"], reverse=True)
    for idx, ref in enumerate(bear_references):
        ref["rank"] = idx + 1

    # 5. Filter by max_rank (optional)
    if max_rank is not None:
        bull_references = bull_references[:max_rank]
        bear_references = bear_references[:max_rank]

    return {
        "current_price": current_price,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "bull_references": bull_references,
        "bear_references": bear_references
    }