from decimal import Decimal
from src.swing_analysis.level_calculator import calculate_levels

def generate_example():
    high = Decimal("674")
    low = Decimal("646")
    direction = "bullish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    with open("example_output.txt", "w") as f:
        for level in levels:
            f.write(f"multiplier={level.multiplier} price={level.price} type={level.level_type}\n")

if __name__ == "__main__":
    generate_example()
