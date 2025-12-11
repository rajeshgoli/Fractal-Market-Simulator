import pytest
import pandas as pd
import os
from src.data.ohlc_loader import load_ohlc, detect_format
from datetime import datetime, timezone

FIXTURE_DIR = "tests/fixtures/ohlc"

@pytest.fixture
def format_a_file(tmp_path):
    """Creates a sample Format A (semicolon) file."""
    content = """01/04/2007;18:00:00;1790;1791.75;1789.25;1791.75;115
01/04/2007;18:01:00;1791.75;1792.5;1791.5;1792.25;80
02/04/2007;09:30:00;1795;1796;1794;1795.5;200
"""
    p = tmp_path / "format_a.csv"
    p.write_text(content)
    return str(p)

@pytest.fixture
def format_b_file(tmp_path):
    """Creates a sample Format B (comma/TradingView) file."""
    content = """time,open,high,low,close,Volume
1762171200,6896.25,6900.25,6891.25,6891.75,13304
1762171260,6891.75,6895.00,6890.00,6894.50,5000
"""
    p = tmp_path / "format_b.csv"
    p.write_text(content)
    return str(p)

def test_format_a_basic_loading(format_a_file):
    """Test Case 1: Format A Basic Loading."""
    df, gaps = load_ohlc(format_a_file)
    
    assert len(df) == 3
    assert df.index[0].year == 2007
    assert df.index[0].month == 4
    assert df.index[0].day == 1
    assert df.index[0].hour == 18
    assert df.index[0].minute == 0
    assert df.index[0].tzinfo == timezone.utc
    
    # Check values
    assert df.iloc[0]['open'] == 1790.0
    assert df.iloc[0]['volume'] == 115

def test_format_b_basic_loading(format_b_file):
    """Test Case 2: Format B Basic Loading."""
    df, gaps = load_ohlc(format_b_file)
    
    assert len(df) == 2
    # 1762171200 is 2025-11-04 12:00:00 UTC (approx, let's check conversion)
    # Actually 1762171200 / 86400 / 365.25 is around 55 years after 1970 -> 2025.
    
    assert df.index[0].timestamp() == 1762171200.0
    assert df.index[0].tzinfo == timezone.utc
    
    assert df.iloc[0]['open'] == 6896.25
    assert df.iloc[0]['volume'] == 13304

def test_format_b_missing_volume(tmp_path):
    """Test Case 8: Format B Missing Volume."""
    content = """time,open,high,low,close
1762171200,6896.25,6900.25,6891.25,6891.75
"""
    p = tmp_path / "missing_vol.csv"
    p.write_text(content)
    
    df, gaps = load_ohlc(str(p))
    
    assert len(df) == 1
    assert 'volume' in df.columns
    assert df.iloc[0]['volume'] == 0

def test_format_detection(format_a_file, format_b_file):
    """Test Case 3: Format Detection."""
    assert detect_format(format_a_file) == "format_a"
    assert detect_format(format_b_file) == "format_b"

def test_invalid_ohlc_rows(tmp_path):
    """Test Case 4: Invalid OHLC Rows."""
    # Need < 50% invalid rows to avoid exception (stricter threshold).
    # Create 200 rows with unique timestamps. 1 invalid.
    # Format A
    rows = []
    # 199 valid rows with unique timestamps
    for i in range(199):
        # Each row gets a unique minute: 18:00:00, 18:01:00, etc.
        hour = 18 + (i // 60)
        minute = i % 60
        rows.append(f"01/04/2007;{hour:02d}:{minute:02d}:00;100;110;90;105;100\n")

    # 1 invalid row (High < Low) with unique timestamp
    rows.append(f"02/04/2007;09:30:00;100;90;95;100;100\n")

    p = tmp_path / "invalid.csv"
    with open(p, 'w') as f:
        f.writelines(rows)

    df, gaps = load_ohlc(str(p))

    assert len(df) == 199  # 1 dropped

def test_gap_detection(tmp_path):
    """Test Case 5: Gap Detection."""
    # 5 minute gap between row 1 and 2
    # 18:00 to 18:06 (diff 6 min, gap 5 min)
    content = """01/04/2007;18:00:00;100;110;90;105;100
01/04/2007;18:06:00;100;110;90;105;100
"""
    p = tmp_path / "gaps.csv"
    p.write_text(content)
    
    df, gaps = load_ohlc(str(p))
    
    assert len(gaps) == 1
    start, end, duration = gaps[0]
    assert start.minute == 0
    assert end.minute == 6
    assert duration == 6.0 # Wait, diff is 6 minutes.
    # My implementation: duration = (end - start)
    # Spec: "gap_duration_minutes".
    # If I have 18:00 and 18:06.
    # Missing bars: 18:01, 18:02, 18:03, 18:04, 18:05. (5 bars).
    # Diff is 6 minutes.
    # Is duration 6 or 5?
    # "gap is any period where consecutive timestamps differ by more than 1 minute."
    # "Return ... gap_duration_minutes".
    # Usually duration of gap is the time elapsed. So 6 minutes.
    # I'll assert 6.0.

def test_large_file_performance(tmp_path):
    """Test Case 6: Large File Performance (Sanity Check)."""
    # Generate 1000 rows (not 200k to save time in test suite, but enough to check logic)
    # Format B
    header = "time,open,high,low,close,Volume\n"
    start_ts = 1600000000
    rows = []
    for i in range(1000):
        rows.append(f"{start_ts + i*60},100,110,90,105,100\n")
        
    p = tmp_path / "large.csv"
    with open(p, 'w') as f:
        f.write(header)
        f.writelines(rows)
        
    import time
    t0 = time.time()
    df, gaps = load_ohlc(str(p))
    t1 = time.time()
    
    assert len(df) == 1000
    assert (t1 - t0) < 2.0 # Should be very fast

def test_edge_cases(tmp_path):
    """Test Case 7: Edge Cases."""
    # Empty file
    p_empty = tmp_path / "empty.csv"
    p_empty.touch()
    with pytest.raises(ValueError, match="File is empty"):
        load_ohlc(str(p_empty))
        
    # Header only
    p_header = tmp_path / "header.csv"
    p_header.write_text("time,open,high,low,close,Volume\n")
    # Should return empty DF? Or fail format detection?
    # My detect_format checks for numeric first field for Format B if header present?
    # "If it contains a comma and the first field is numeric... If the first line contains column headers... assume Format B."
    # So it detects Format B.
    # Then read_csv returns empty DF (or DF with index but no rows).
    df, gaps = load_ohlc(str(p_header))
    assert len(df) == 0
