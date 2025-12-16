from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from .constants import CONFLUENCE_FIB_RATIOS


@dataclass
class Level:
    multiplier: Decimal
    price: Decimal
    level_type: str

def calculate_levels(
    high: Decimal,
    low: Decimal,
    direction: str,
    quantization: Decimal
) -> List[Level]:
    """
    Computes structural price levels from a reference swing.

    Args:
        high: The high price of the swing.
        low: The low price of the swing.
        direction: "bullish" or "bearish".
        quantization: The increment to round prices to (e.g., 0.25).

    Returns:
        A list of Level objects sorted by multiplier.

    Raises:
        ValueError: If direction is invalid or high <= low.
    """
    # Validate inputs
    if direction not in ("bullish", "bearish"):
        raise ValueError(f"Invalid direction: {direction}. Must be 'bullish' or 'bearish'.")
    
    if high <= low:
        raise ValueError("High must be strictly greater than low.")

    swing_size = high - low
    
    # Define multipliers and their types
    # STOP applies to -0.1
    # SWING_EXTREME applies to 0
    # SUPPORT_RESISTANCE applies to 0.1, 0.382, 0.5, 0.618, 0.9, 1, 1.1
    # DECISION_ZONE applies to 1.382, 1.5, 1.618
    # EXHAUSTION applies to 2
    level_definitions = [
        (Decimal("-0.1"), "STOP"),
        (Decimal("0"), "SWING_EXTREME"),
        (Decimal("0.1"), "SUPPORT_RESISTANCE"),
        (Decimal("0.382"), "SUPPORT_RESISTANCE"),
        (Decimal("0.5"), "SUPPORT_RESISTANCE"),
        (Decimal("0.618"), "SUPPORT_RESISTANCE"),
        (Decimal("0.9"), "SUPPORT_RESISTANCE"),
        (Decimal("1"), "SUPPORT_RESISTANCE"),
        (Decimal("1.1"), "SUPPORT_RESISTANCE"),
        (Decimal("1.382"), "DECISION_ZONE"),
        (Decimal("1.5"), "DECISION_ZONE"),
        (Decimal("1.618"), "DECISION_ZONE"),
        (Decimal("2"), "EXHAUSTION"),
    ]

    levels = []

    for mult, l_type in level_definitions:
        if direction == "bullish":
            # level_price = low + (swing_size * multiplier)
            raw_price = low + (swing_size * mult)
        else: # bearish
            # level_price = high - (swing_size * multiplier)
            # Note: The spec says "The same multipliers apply, but their directional meaning flips."
            # "For example, the 2x level now represents downside exhaustion rather than upside exhaustion."
            # Formula: level_price = high - (swing_size * multiplier)
            raw_price = high - (swing_size * mult)
        
        # Quantize the price
        # Formula for rounding to nearest increment:
        # (value / quantization).quantize(1, ROUND_HALF_UP) * quantization
        
        # We need to do this carefully with Decimal
        # First divide by quantization
        scaled = raw_price / quantization
        # Round to nearest integer (Decimal('1'))
        rounded_scaled = scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        # Multiply back
        final_price = rounded_scaled * quantization
        
        levels.append(Level(multiplier=mult, price=final_price, level_type=l_type))

    # Sort by multiplier
    levels.sort(key=lambda x: x.multiplier)

    return levels


def calculate_fib_confluence_score(
    endpoint_price: float,
    containing_swing: Dict[str, Any],
    direction: str = "bullish",
    tolerance_pct: float = 0.005
) -> float:
    """
    Score how close a price is to any FIB level of the containing swing.

    Endpoints that land on FIB levels of larger swings are structurally
    significant - price respects them because market participants watch them.

    Args:
        endpoint_price: The price to score
        containing_swing: Dict with 'high_price' and 'low_price' keys
        direction: "bullish" or "bearish" for level calculation
        tolerance_pct: How close to a level counts as "on" the level (default 0.5%)

    Returns:
        Score from 0.0 (no confluence) to 1.0 (exactly on level)
    """
    if not containing_swing:
        return 0.0

    high = containing_swing.get('high_price', 0)
    low = containing_swing.get('low_price', 0)
    swing_size = high - low

    if swing_size <= 0:
        return 0.0

    # Calculate tolerance in price units
    tolerance = tolerance_pct * swing_size

    # Calculate FIB level prices using extended ratios
    fib_prices = []
    for ratio in CONFLUENCE_FIB_RATIOS:
        if direction == "bullish":
            level_price = low + (swing_size * ratio)
        else:
            level_price = high - (swing_size * ratio)
        fib_prices.append(level_price)

    # Find minimum distance to any FIB level
    min_distance = float('inf')
    for level_price in fib_prices:
        distance = abs(endpoint_price - level_price)
        min_distance = min(min_distance, distance)

    # Convert to score (1.0 = on level, 0.0 = beyond tolerance)
    if min_distance <= tolerance:
        return 1.0 - (min_distance / tolerance)
    else:
        return 0.0


def score_swing_fib_confluence(
    swing: Dict[str, Any],
    containing_swing: Optional[Dict[str, Any]],
    direction: str = "bull"
) -> Dict[str, Any]:
    """
    Add FIB confluence scores to a swing dictionary.

    Calculates scores for both the high and low endpoints of the swing.

    Args:
        swing: Swing dictionary with 'high_price' and 'low_price' keys
        containing_swing: The larger-scale swing containing this one
        direction: "bull" or "bear"

    Returns:
        Updated swing dictionary with 'fib_confluence_score' added
    """
    if not containing_swing:
        swing['fib_confluence_score'] = 0.0
        return swing

    # Map direction to calculate_levels direction
    calc_direction = "bullish" if direction == "bull" else "bearish"

    # Score both endpoints
    high_score = calculate_fib_confluence_score(
        swing.get('high_price', 0),
        containing_swing,
        calc_direction
    )
    low_score = calculate_fib_confluence_score(
        swing.get('low_price', 0),
        containing_swing,
        calc_direction
    )

    # Use average of both endpoint scores
    # (Both endpoints landing on FIB levels is stronger than just one)
    swing['fib_confluence_score'] = (high_score + low_score) / 2

    return swing
