from decimal import Decimal
from typing import List, Dict, Any
import pandas as pd
from .level_calculator import calculate_levels, Level

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

def detect_swings(df: pd.DataFrame, lookback: int = 5, filter_redundant: bool = True, quantization: float = 0.25) -> Dict[str, Any]:
    """
    Identifies swing highs and lows and pairs them to find valid reference swings.

    Args:
        df: DataFrame with columns 'open', 'high', 'low', 'close'.
        lookback: Number of bars before and after to check for swing points.
        filter_redundant: Whether to apply structural filtering to remove redundant swings.
        quantization: Tick size for Fibonacci level calculation.

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
    
    swing_highs = []
    swing_lows = []
    
    # 1. Detect Swing Points
    # Iterate from lookback to len(df) - lookback
    # Note: range is exclusive at the end, so we go up to len(df) - lookback
    for i in range(lookback, len(df) - lookback):
        # Check for Swing High
        current_high = df.iloc[i]['high']
        is_high = True
        # Check N bars before
        for j in range(1, lookback + 1):
            if df.iloc[i - j]['high'] > current_high:
                is_high = False
                break
        # Check N bars after
        if is_high:
            for j in range(1, lookback + 1):
                if df.iloc[i + j]['high'] > current_high:
                    is_high = False
                    break
        
        if is_high:
            swing_highs.append({"price": float(current_high), "bar_index": i})

        # Check for Swing Low
        current_low = df.iloc[i]['low']
        is_low = True
        # Check N bars before
        for j in range(1, lookback + 1):
            if df.iloc[i - j]['low'] < current_low:
                is_low = False
                break
        # Check N bars after
        if is_low:
            for j in range(1, lookback + 1):
                if df.iloc[i + j]['low'] < current_low:
                    is_low = False
                    break
        
        if is_low:
            swing_lows.append({"price": float(current_low), "bar_index": i})

    bull_references = []
    bear_references = []

    # 2. Pair and Validate Swings
    
    # Bull References: High BEFORE Low (Downswing)
    for high_swing in swing_highs:
        for low_swing in swing_lows:
            if high_swing["bar_index"] < low_swing["bar_index"]:
                # Candidate found
                high_price = high_swing["price"]
                low_price = low_swing["price"]
                size = high_price - low_price

                if size <= 0:
                    continue  # skip invalid geometric configuration

                # STRICT VALIDITY CHECK:
                # The Low must be the lowest point between High and Low.
                # If there is a lower low in between, then this is not a valid single swing.
                # We can check against other swing_lows in the interval.
                is_valid_structure = True
                for intermediate_low in swing_lows:
                    if high_swing["bar_index"] < intermediate_low["bar_index"] < low_swing["bar_index"]:
                        if intermediate_low["price"] < low_price:
                            is_valid_structure = False
                            break
                    # Optimization: if intermediate_low index > low_index, stop (assuming sorted list? No, not guaranteed sorted by index)
                    # swing_lows is appended in chronological order, so it IS sorted by index.
                    if intermediate_low["bar_index"] >= low_swing["bar_index"]:
                        break
                
                if not is_valid_structure:
                    continue

                # Validation: low + 0.382 * size < current < low + 2.0 * size
                level_0382 = low_price + (0.382 * size)
                level_2x = low_price + (2.0 * size)
                
                if level_0382 < current_price < level_2x:
                    bull_references.append({
                        "high_price": high_price,
                        "high_bar_index": high_swing["bar_index"],
                        "low_price": low_price,
                        "low_bar_index": low_swing["bar_index"],
                        "size": size,
                        "level_0382": level_0382,
                        "level_2x": level_2x,
                        "rank": 0 # Placeholder
                    })

    # Bear References: Low BEFORE High (Upswing)
    for low_swing in swing_lows:
        for high_swing in swing_highs:
            if low_swing["bar_index"] < high_swing["bar_index"]:
                # Candidate found
                high_price = high_swing["price"]
                low_price = low_swing["price"]
                size = high_price - low_price

                if size <= 0:
                    continue  # skip invalid geometric configuration
                
                # STRICT VALIDITY CHECK:
                # The High must be the highest point between Low and High.
                is_valid_structure = True
                for intermediate_high in swing_highs:
                    if low_swing["bar_index"] < intermediate_high["bar_index"] < high_swing["bar_index"]:
                        if intermediate_high["price"] > high_price:
                            is_valid_structure = False
                            break
                    if intermediate_high["bar_index"] >= high_swing["bar_index"]:
                        break
                
                if not is_valid_structure:
                    continue

                # Validation: high - 2.0 * size < current < high - 0.382 * size
                level_0382 = high_price - (0.382 * size)
                level_2x = high_price - (2.0 * size)
                
                if level_2x < current_price < level_0382:
                    bear_references.append({
                        "high_price": high_price,
                        "high_bar_index": high_swing["bar_index"],
                        "low_price": low_price,
                        "low_bar_index": low_swing["bar_index"],
                        "size": size,
                        "level_0382": level_0382,
                        "level_2x": level_2x,
                        "rank": 0 # Placeholder
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

    return {
        "current_price": current_price,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "bull_references": bull_references,
        "bear_references": bear_references
    }