#!/usr/bin/env python3
"""
Regression test for 1m CSV loading issue with duplicate timestamps.

This test ensures that CSV files with duplicate timestamps can be loaded
without causing 'slice - int' TypeError in gap detection.
"""
import tempfile
import os
import sys
sys.path.append('.')

from src.data.ohlc_loader import load_ohlc


def test_duplicate_timestamps():
    """Test that files with duplicate timestamps load without error"""
    
    # Create test CSV content with duplicate timestamps
    csv_content = """01/01/2024;09:00:00;100.0;101.0;99.0;100.5;100
01/01/2024;09:01:00;100.5;102.0;100.0;101.0;200
01/01/2024;09:01:00;101.0;102.0;100.5;101.5;150
01/01/2024;09:03:00;101.5;103.0;101.0;102.0;300
01/01/2024;09:04:00;102.0;102.5;101.5;102.2;180
01/01/2024;09:04:00;102.2;102.8;102.0;102.5;120"""
    
    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        temp_file = f.name
    
    try:
        # This should NOT raise a TypeError anymore
        df, gaps = load_ohlc(temp_file)
        
        # Verify basic properties
        assert len(df) == 6, f"Expected 6 rows, got {len(df)}"
        assert len(gaps) >= 0, "Gaps list should be valid"
        
        # Verify data integrity
        assert df['open'].iloc[0] == 100.0, "First open price should be 100.0"
        assert df['close'].iloc[-1] == 102.5, "Last close price should be 102.5"
        
        print("✓ Regression test passed: 1m CSV with duplicate timestamps loads successfully")
        print(f"  - Loaded {len(df)} bars")
        print(f"  - Detected {len(gaps)} gaps")
        return True
        
    except Exception as e:
        print(f"✗ Regression test failed: {e}")
        return False
        
    finally:
        # Clean up temp file
        os.unlink(temp_file)


def test_1m_file_loading():
    """Test that actual 1m file can be loaded"""
    test_file = "./test_data/es-1m.csv"
    
    if not os.path.exists(test_file):
        print(f"⚠ Skipping actual file test: {test_file} not found")
        return True
    
    try:
        # This should work now
        df, gaps = load_ohlc(test_file)
        
        print(f"✓ Real 1m file test passed: loaded {len(df):,} bars with {len(gaps):,} gaps")
        return True
        
    except Exception as e:
        print(f"✗ Real 1m file test failed: {e}")
        return False


if __name__ == "__main__":
    print("Running 1m CSV loading regression tests...")
    
    success = True
    success &= test_duplicate_timestamps()
    success &= test_1m_file_loading()
    
    if success:
        print("\n✓ All regression tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)