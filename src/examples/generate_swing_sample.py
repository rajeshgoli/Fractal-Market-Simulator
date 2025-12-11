import pandas as pd
import json
from src.swing_analysis.swing_detector import detect_swings

def generate_sample():
    # Construct a sample DataFrame with valid bull and bear references
    # Similar to Test 10 but cleaner
    prices = [6700.0] * 100
    
    # 1. Bear Reference Setup
    # Low at 10: 6600
    prices[10] = 6600
    for i in range(1, 6): prices[10-i]=6610; prices[10+i]=6610
    
    # High at 30: 6800
    prices[30] = 6800
    for i in range(1, 6): prices[30-i]=6790; prices[30+i]=6790
    
    # Bear Ref: 6600 -> 6800. Size 200.
    # 0.382 down = 6800 - 76.4 = 6723.6.
    # 2x down = 6800 - 400 = 6400.
    # Need price between 6400 and 6723.6. Let's say 6700.
    
    # 2. Bull Reference Setup
    # High at 50: 6750
    prices[50] = 6750
    for i in range(1, 6): prices[50-i]=6740; prices[50+i]=6740
    
    # Low at 70: 6650
    prices[70] = 6650
    for i in range(1, 6): prices[70-i]=6660; prices[70+i]=6660
    
    # Bull Ref: 6750 -> 6650. Size 100.
    # 0.382 up = 6650 + 38.2 = 6688.2.
    # 2x up = 6650 + 200 = 6850.
    # Need price between 6688.2 and 6850. Let's say 6700.
    
    # Current Price 6700.
    prices[-1] = 6700.0
    
    data = []
    for p in prices:
        data.append({'open': float(p), 'high': float(p), 'low': float(p), 'close': float(p)})
    df = pd.DataFrame(data)
    
    result = detect_swings(df, lookback=5)
    
    with open("sample_output.json", "w") as f:
        json.dump(result, f, indent=4)

if __name__ == "__main__":
    generate_sample()
