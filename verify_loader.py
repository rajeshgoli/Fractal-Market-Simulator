import sys
import os
# Add current directory to path so we can import src
sys.path.append(os.getcwd())

from src.data.ohlc_loader import load_ohlc, detect_format

def verify():
    filepath = "test.csv"
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Detecting format for {filepath}...")
    try:
        fmt = detect_format(filepath)
        print(f"Detected format: {fmt}")
    except Exception as e:
        print(f"Error detecting format: {e}")
        return

    print("Loading OHLC data...")
    try:
        df, gaps = load_ohlc(filepath)
        print(f"Successfully loaded {len(df)} rows.")
        print("First 5 rows:")
        print(df.head())
        print("\nLast 5 rows:")
        print(df.tail())
        
        print(f"\nDetected {len(gaps)} gaps.")
        if gaps:
            print("First 5 gaps:")
            for g in gaps[:5]:
                print(f"Start: {g[0]}, End: {g[1]}, Duration: {g[2]} min")
                
    except Exception as e:
        print(f"Error loading data: {e}")

if __name__ == "__main__":
    verify()
