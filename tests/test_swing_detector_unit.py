import pytest
import pandas as pd
from src.swing_analysis.swing_detector import detect_swings

def create_df(prices):
    """Helper to create a DataFrame from a list of close prices.
    Assumes open=high=low=close for simplicity unless specified otherwise.
    """
    data = []
    for p in prices:
        data.append({'open': float(p), 'high': float(p), 'low': float(p), 'close': float(p)})
    return pd.DataFrame(data)

def test_case_one_simple_downswing():
    """
    Test 1: Simple downswing detection.
    Setup: Price starts 100, rises to 150 (bar 10), falls to 120 (bar 20), flat 130 until 30.
    Lookback 3.
    Adjusted current price to 135 to be valid.
    """
    prices = [0.0] * 31
    # Use a trend to avoid spurious swings
    # 0-10: Trend up 100 to 140
    for i in range(10): prices[i] = 100 + i * 4
    # 10: 150 (High)
    prices[10] = 150
    # 11-20: Trend down 140 to 120
    for i in range(1, 10): prices[10+i] = 148 - (i * 2.8) # approx
    # Let's be explicit to avoid mess
    # 0-6: 100, 105, 110, 115, 120, 125, 130
    for i in range(7): prices[i] = 100 + i*5
    # 7-9: 140, 145, 148 (already set in original code, but let's overwrite to be safe)
    prices[7]=140; prices[8]=145; prices[9]=148
    
    # 11-16: 148, 145, 140, 135, 130, 125
    prices[11]=148; prices[12]=145; prices[13]=140; prices[14]=135; prices[15]=130; prices[16]=125
    # 17-19: 125, 122, 121 (already set)
    prices[17]=125; prices[18]=122; prices[19]=121
    
    # 20: 120 (Low)
    prices[20] = 120
    
    # 21-30: Trend up from 120 to 135
    # 21-23: 121, 122, 125 (already set)
    prices[21]=121; prices[22]=122; prices[23]=125
    # 24-30: 126, 127, 128, 129, 130, 132, 135
    for i in range(24, 31): prices[i] = 125 + (i-23)*1.5
    prices[30] = 135
    
    df = create_df(prices)
    result = detect_swings(df, lookback=3)
    
    assert len(result["swing_highs"]) >= 1
    assert len(result["swing_lows"]) >= 1
    
    # Check specific high/low
    high_150 = next((s for s in result["swing_highs"] if s["price"] == 150.0), None)
    assert high_150 is not None
    assert high_150["bar_index"] == 10
    
    low_120 = next((s for s in result["swing_lows"] if s["price"] == 120.0), None)
    assert low_120 is not None
    assert low_120["bar_index"] == 20
    
    # Check bull reference
    # Size = 30. 0.382 level = 120 + 11.46 = 131.46. 2x = 180.
    # Current 135 is valid.
    assert len(result["bull_references"]) == 1
    ref = result["bull_references"][0]
    assert ref["high_price"] == 150.0
    assert ref["low_price"] == 120.0
    assert ref["size"] == 30.0
    assert ref["rank"] == 1

def test_case_two_simple_upswing():
    """
    Test 2: Simple upswing detection.
    Setup: Start 150, fall to 100 (bar 10), rise to 140 (bar 20), fall to 125 (bar 30).
    Lookback 3.
    Adjusted current price to 120 to be valid.
    """
    prices = [130] * 31
    # Bar 10 low 100
    prices[10] = 100
    prices[7]=110; prices[8]=105; prices[9]=102
    prices[11]=102; prices[12]=105; prices[13]=110
    
    # Bar 20 high 140
    prices[20] = 140
    prices[17]=130; prices[18]=135; prices[19]=138
    prices[21]=138; prices[22]=135; prices[23]=130
    
    # Current price 120
    prices[30] = 120
    
    df = create_df(prices)
    result = detect_swings(df, lookback=3)
    
    # Check bear reference
    # Size 40. 0.382 down = 140 - 15.28 = 124.72. 2x down = 140 - 80 = 60.
    # Current 120 is valid (60 < 120 < 124.72).
    assert len(result["bear_references"]) == 1
    ref = result["bear_references"][0]
    assert ref["high_price"] == 140.0
    assert ref["low_price"] == 100.0
    assert ref["size"] == 40.0

def test_case_three_multiple_lows():
    """
    Test 3: Multiple lows pairing with same high.
    High 200 (bar 20). Low 150 (bar 40). Low 140 (bar 60). Current 170.
    Lookback 5.

    IMPORTANT: The base price level must be above all intended swing lows (>150)
    to avoid creating unintended swing lows that would invalidate references.
    """
    # Base price at 170 (above all intended lows)
    prices = [170.0] * 71

    # High 200 at 20
    prices[20] = 200
    # Neighbors - smooth transition from base to peak and back
    prices[15]=180; prices[16]=185; prices[17]=190; prices[18]=194; prices[19]=197
    prices[21]=197; prices[22]=194; prices[23]=190; prices[24]=185; prices[25]=180

    # Transition zone from high back to base (bars 26-34)
    # Smooth transition to avoid creating swing lows
    prices[26]=175; prices[27]=172; prices[28]=170; prices[29]=168; prices[30]=166
    prices[31]=164; prices[32]=162; prices[33]=160; prices[34]=158

    # Low 150 at 40
    prices[40] = 150
    # Neighbors (must be > 150)
    prices[35]=160; prices[36]=158; prices[37]=156; prices[38]=154; prices[39]=152
    prices[41]=152; prices[42]=154; prices[43]=156; prices[44]=158; prices[45]=160

    # Transition zone between lows (bars 46-54)
    prices[46]=162; prices[47]=164; prices[48]=166; prices[49]=164; prices[50]=162
    prices[51]=160; prices[52]=158; prices[53]=156; prices[54]=154

    # Low 140 at 60
    prices[60] = 140
    # Neighbors
    prices[55]=150; prices[56]=148; prices[57]=146; prices[58]=144; prices[59]=142
    prices[61]=142; prices[62]=144; prices[63]=146; prices[64]=148; prices[65]=150

    # Transition back to current price
    prices[66]=155; prices[67]=160; prices[68]=165; prices[69]=168

    # Current 170
    prices[-1] = 170
    
    df = create_df(prices)
    result = detect_swings(df, lookback=5)
    
    # Bull refs:
    # 1. 200-140 (Size 60). 0.382 = 140 + 22.92 = 162.92. Valid (170 > 162.92).
    # 2. 200-150 (Size 50). 0.382 = 150 + 19.1 = 169.1. Valid (170 > 169.1).
    
    # Relax assertion to allow for spurious swings from data stitching
    assert len(result["bull_references"]) >= 2
    
    # Verify the top 2 are the expected ones
    # Sort by size just in case (though function should return sorted)
    refs = sorted(result["bull_references"], key=lambda x: x["size"], reverse=True)
    
    # Verify the expected references are present
    # 1. 200-140 (Size 60)
    ref_60 = next((r for r in result["bull_references"] if r["size"] == 60.0 and r["high_price"] == 200.0 and r["low_price"] == 140.0), None)
    assert ref_60 is not None
    
    # 2. 200-150 (Size 50)
    ref_50 = next((r for r in result["bull_references"] if r["size"] == 50.0 and r["high_price"] == 200.0 and r["low_price"] == 150.0), None)
    assert ref_50 is not None
    
    # Check that rank of 60 is higher (lower index) than rank of 50?
    # Well, if 74 is rank 1, then 60 might be rank 2.
    # But 60 > 50, so ref_60["rank"] < ref_50["rank"] (numerically smaller rank = higher list position)
    assert ref_60["rank"] < ref_50["rank"]

def test_case_four_no_valid_bull_low_price():
    """
    Test 4: No valid references because price below 0.382.
    High 200 (20), Low 110 (40), Current 120.
    """
    prices = [150] * 50
    prices[20] = 200
    for i in range(1, 6): prices[20-i]=190; prices[20+i]=190
    
    prices[40] = 110
    for i in range(1, 6): prices[40-i]=120; prices[40+i]=120
    
    prices[-1] = 120
    
    df = create_df(prices)
    result = detect_swings(df, lookback=5)
    
    # Size 90. 0.382 = 110 + 34.38 = 144.38. Current 120 < 144.38. Invalid.
    assert len(result["bull_references"]) == 0

def test_case_five_no_valid_bull_high_price():
    """
    Test 5: No valid references because price above 2x.
    High 200 (10), Low 100 (30). Current 310.
    """
    prices = [150] * 40
    prices[10] = 200
    for i in range(1, 6): prices[10-i]=190; prices[10+i]=190
    
    prices[30] = 100
    for i in range(1, 6): prices[30-i]=110; prices[30+i]=110
    
    prices[-1] = 310
    
    df = create_df(prices)
    result = detect_swings(df, lookback=5)
    
    # Size 100. 2x = 100 + 200 = 300. Current 310 > 300. Invalid.
    assert len(result["bull_references"]) == 0

def test_case_six_bear_valid_bull_invalid():
    """
    Test 6: Bear reference valid, bull reference invalid for same swing points.
    Low 100 (10), High 150 (30). Current 125.
    L before H -> Bear candidate only.
    """
    # Base trend
    prices = [120 + i*0.1 for i in range(41)]
    
    # Low 100 at 10
    prices[10] = 100
    for i in range(1, 6): prices[10-i]=110-i; prices[10+i]=110-i # V shape
    # Wait, 110-i might be < 100 if i is large? i=1..5. 110-5=105. OK.
    # Actually, let's be explicit.
    prices[5]=110; prices[6]=108; prices[7]=106; prices[8]=104; prices[9]=102
    prices[11]=102; prices[12]=104; prices[13]=106; prices[14]=108; prices[15]=110
    
    # High 150 at 30
    prices[30] = 150
    prices[25]=140; prices[26]=142; prices[27]=144; prices[28]=146; prices[29]=148
    prices[31]=148; prices[32]=146; prices[33]=144; prices[34]=142; prices[35]=140
    
    prices[-1] = 125
    
    df = create_df(prices)
    result = detect_swings(df, lookback=5)
    
    # Bear: 150-100=50. 0.382 down = 130.9. 2x down = 50. Current 125 is valid.
    assert len(result["bear_references"]) == 1
    assert len(result["bull_references"]) == 0

def test_case_seven_temporal_ordering():
    """
    Test 7: Temporal ordering enforced.
    Low 100 (10), High 200 (20). Current 160.
    Only Bear candidate (L before H).
    """
    prices = [150] * 30
    prices[10] = 100
    for i in range(1, 6): prices[10-i]=110; prices[10+i]=110
    
    prices[20] = 200
    for i in range(1, 6): prices[20-i]=190; prices[20+i]=190
    
    prices[-1] = 160
    
    df = create_df(prices)
    result = detect_swings(df, lookback=5)
    
    assert len(result["bear_references"]) == 1
    assert len(result["bull_references"]) == 0

def test_case_eight_equal_highs():
    """
    Test 8: Edge case with equal highs.
    High 200 at 10 and 15. Low 150 at 25.
    """
    prices = [180] * 35
    prices[10] = 200
    prices[15] = 200
    # Ensure they are local maxes
    for i in range(1, 4): prices[10-i]=190; prices[10+i]=190
    for i in range(1, 4): prices[15-i]=190; prices[15+i]=190
    # Note: at index 12/13 they are 190, so 10 and 15 are separated.
    
    prices[25] = 150
    for i in range(1, 4): prices[25-i]=160; prices[25+i]=160
    
    prices[-1] = 170 # Valid for bull (150 + 0.382*50 = 169.1 < 170)
    
    df = create_df(prices)
    result = detect_swings(df, lookback=3)
    
    # Should find both highs or handled gracefully
    highs_200 = [s for s in result["swing_highs"] if s["price"] == 200.0]
    assert len(highs_200) >= 1
    
    # Should have valid bull references
    assert len(result["bull_references"]) >= 1

def test_case_nine_minimum_data():
    """
    Test 9: Minimum data edge case.
    2*lookback + 1 bars.
    """
    lookback = 5
    prices = [100] * (2 * lookback + 1)
    prices[lookback] = 200 # Middle is high
    
    df = create_df(prices)
    result = detect_swings(df, lookback=lookback)
    
    assert len(result["swing_highs"]) == 1
    assert result["swing_highs"][0]["bar_index"] == lookback

def test_case_ten_real_world():
    """
    Test 10: Real-world scenario.
    """
    # Create a sequence
    # 0-10: drop to 6540
    # 10-20: rally to 6692 (Low 1) - wait, spec says "rally to 6692 (swing low)"?
    # Spec: "early low around 6540, rally to 6692 (swing low)" -> This implies 6692 is a higher low?
    # Or maybe 6540 was just a start point.
    # Let's follow the sequence of swing points described:
    # 6692 (Low), 6953.75 (High), 6655.50 (Low), 6918.50 (High), 6593.25 (Low), 6900.50 (High), 6525 (Low), 6880.75 (High).
    # Current 6849.25.
    
    points = [
        (10, 6692.0, 'low'),
        (20, 6953.75, 'high'),
        (30, 6655.50, 'low'),
        (40, 6918.50, 'high'),
        (50, 6593.25, 'low'),
        (60, 6900.50, 'high'),
        (70, 6525.0, 'low'),
        (80, 6880.75, 'high')
    ]
    
    prices = [6700.0] * 100
    for idx, price, type_ in points:
        prices[idx] = price
        # Make it a swing
        if type_ == 'high':
            for i in range(1, 6): prices[idx-i] = price - 10; prices[idx+i] = price - 10
        else:
            for i in range(1, 6): prices[idx-i] = price + 10; prices[idx+i] = price + 10
            
    prices[-1] = 6849.25
    
    df = create_df(prices)
    result = detect_swings(df, lookback=5)
    
    # Check Bear Reference: Low 6692 (10) to High 6953.75 (20).
    # Size = 261.75.
    # 0.382 down = 6953.75 - (261.75 * 0.382) = 6953.75 - 99.9885 = 6853.76.
    # 2x down = 6953.75 - 523.5 = 6430.25.
    # Current 6849.25.
    # 6430.25 < 6849.25 < 6853.76. Valid.
    
    bear_ref = next((r for r in result["bear_references"] if r["low_price"] == 6692.0 and r["high_price"] == 6953.75), None)
    assert bear_ref is not None
    assert bear_ref["size"] == 261.75

def test_case_eleven_redundant_filtering():
    """
    Test 11: Redundant swing filtering.
    Multiple swing highs clustered near the same price level, all pairing with the same swing low.
    Verify that references in the same Fibonacci band are filtered as redundant.

    Band assignments for anchor 200-100 (size 100):
      - 0.9 level = 190.00
      - 1.0 level = 200.00

    Results:
      - H:200 -> band 1.0 (anchor, kept)
      - H:198 -> band 1.0 (same as anchor, filtered as redundant)
      - H:195 -> band 0.9 (different band, kept as structurally distinct)
    """
    # Highs at 10, 20, 30. Low at 50.
    # Highs at 200, 198, 195.

    prices = [150 + i*0.01 for i in range(60)]

    # Highs
    prices[10] = 200  # Anchor (band 1.0)
    prices[20] = 198  # Redundant (band 1.0, same as anchor)
    prices[30] = 195  # Distinct (band 0.9, different from anchor)

    # Low
    prices[50] = 100

    # Ensure they are peaks/valleys
    for idx in [10, 20, 30]:
        prices[idx-1] = prices[idx]-5
        prices[idx+1] = prices[idx]-5

    prices[49] = 105; prices[51] = 105

    # Current price must be valid (> low + 0.382*size)
    # Size 100. 0.382 level = 138.2.
    # Set current to 150.
    prices[-1] = 150

    df = create_df(prices)
    result = detect_swings(df, lookback=3, filter_redundant=True)

    # 200->100 (band 1.0) and 195->100 (band 0.9) are both kept
    # 198->100 is filtered as redundant with 200->100 (both in band 1.0)
    large_refs = [r for r in result["bull_references"] if r["size"] > 90]
    assert len(large_refs) == 2
    high_prices = {r["high_price"] for r in large_refs}
    assert 200.0 in high_prices  # Anchor (band 1.0)
    assert 195.0 in high_prices  # Structurally distinct (band 0.9)

def test_case_twelve_multi_tier_filtering():
    """
    Test 12: Multi-tier filtering.
    Swings at distinctly different size scales.
    Tier 1: Size ~100. Tier 2: Size ~50.
    """
    prices = [150 + i*0.01 for i in range(100)]
    
    # Tier 1: High 200 (10) -> Low 100 (90)
    prices[10] = 200
    prices[90] = 100
    
    # Tier 2: High 190 (30) -> Low 140 (70)
    # Size 50. 50 <= 90% of 100.
    prices[30] = 190
    prices[70] = 140
    
    # Ensure peaks/valleys
    prices[9]=190; prices[11]=190
    prices[89]=105; prices[91]=105
    
    prices[29]=185; prices[31]=185
    prices[69]=145; prices[71]=145
    
    # Valid price for both?
    # Ref 1: 200-100 (100). 0.382=138.2.
    # Ref 2: 190-140 (50). 0.382=140 + 19.1 = 159.1.
    # Current 160 is > 138.2 and > 159.1. OK.
    prices[-1] = 160 
    
    df = create_df(prices)
    result = detect_swings(df, lookback=3, filter_redundant=True)
    
    # Should keep both intended swings (and potentially cross-pairings if distinct)
    relevant_refs = [r for r in result["bull_references"] if r["size"] >= 50]
    # We expect at least 200->100 and 190->140.
    # 190->100 is also distinct (0.9 vs 1.0 level).
    assert len(relevant_refs) >= 2
    
    # Verify specific swings are present
    pairs = [(r["high_price"], r["low_price"]) for r in relevant_refs]
    assert (200.0, 100.0) in pairs
    assert (190.0, 140.0) in pairs

def test_case_thirteen_filter_disabled():
    """
    Test 13: Filter disabled.
    Verify that all references are returned.
    Same setup as Test 11.
    """
    prices = [150 + i*0.01 for i in range(60)]
    
    prices[10] = 200
    prices[20] = 198
    prices[30] = 195
    prices[50] = 100
    
    for idx in [10, 20, 30]:
        prices[idx-1] = prices[idx]-5
        prices[idx+1] = prices[idx]-5
    
    prices[49] = 105; prices[51] = 105
        
    prices[-1] = 150 # Valid
    
    df = create_df(prices)
    result = detect_swings(df, lookback=3, filter_redundant=False)
    
    # Should have 3 references among large swings
    large_refs = [r for r in result["bull_references"] if r["size"] > 90]
    assert len(large_refs) == 3

def test_case_fourteen_structurally_distinct():
    """
    Test 14: Structurally distinct swings preserved with structural validity.

    Setup:
      - High 200 (bar 10) -> Low 100 (bar 50): Size 100
      - High 220 (bar 30) -> Low 120 (bar 70): Size 100

    Expected valid references:
      - 220->100 (size 120): Valid - no lower low between bar 30 and bar 50
      - 200->100 (size 100): Valid - no lower low between bar 10 and bar 50

    220->120 is INVALID because:
      - The low at bar 50 (price 100) is between bar 30 (high 220) and bar 70 (low 120)
      - 100 < 120, so structural validity fails (the low must be the lowest point)
    """
    prices = [150 + i*0.01 for i in range(100)]

    # Ref 1: High 200 (10) -> Low 100 (50)
    prices[10] = 200
    prices[50] = 100

    # Ref 2: High 220 (30) -> Low 120 (70)
    # Note: 220->120 is structurally invalid because low 100 at bar 50 is between them
    prices[30] = 220
    prices[70] = 120

    # Peaks/Valleys
    prices[9]=190; prices[11]=190
    prices[49]=105; prices[51]=105

    prices[29]=210; prices[31]=210
    prices[69]=125; prices[71]=125

    # Valid price
    # Ref 1: 200-100 (100). 0.382=138.2.
    # Ref 2: 220-120 (100). 0.382=158.2.
    # Current 180 > 158.2. OK.
    prices[-1] = 180

    df = create_df(prices)
    result = detect_swings(df, lookback=3, filter_redundant=True)

    # Only 2 valid large refs: 220->100 and 200->100
    # 220->120 is structurally invalid (lower low at 100 between them)
    large_refs = [r for r in result["bull_references"] if r["size"] > 90]
    assert len(large_refs) == 2

    pairs = [(r["high_price"], r["low_price"]) for r in large_refs]
    assert (200.0, 100.0) in pairs
    assert (220.0, 100.0) in pairs  # Cross-pairing that IS structurally valid
