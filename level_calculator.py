from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import List

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
