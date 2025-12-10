import sys
import os
import pandas as pd

# Add current directory to path
sys.path.append(os.getcwd())

from src.data.ohlc_loader import load_ohlc
from swing_detector import detect_swings

def main():
    filepath = "test.csv"
    output_file = "valid_swings.txt"
    
    print(f"Loading data from {filepath}...")
    try:
        df, gaps = load_ohlc(filepath)
        print(f"Loaded {len(df)} rows.")
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    print("Detecting swings (lookback=5)...")
    try:
        # detect_swings expects a DataFrame. 
        # It uses .iloc, so the datetime index is fine.
        result = detect_swings(df, lookback=5)
        
        bull_refs = result["bull_references"]
        bear_refs = result["bear_references"]
        
        print(f"Found {len(bull_refs)} valid bull swings.")
        print(f"Found {len(bear_refs)} valid bear swings.")
        
        with open(output_file, "w") as f:
            f.write("Valid Bull Swings:\n")
            for ref in bull_refs:
                # ref is a dictionary
                f.write(f"High: {ref['high_price']}, Low: {ref['low_price']}, Size: {ref['size']}\n")
            
            f.write("\nValid Bear Swings:\n")
            for ref in bear_refs:
                f.write(f"High: {ref['high_price']}, Low: {ref['low_price']}, Size: {ref['size']}\n")
                
        print(f"Output saved to {output_file}")
        
    except Exception as e:
        print(f"Error detecting swings: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
