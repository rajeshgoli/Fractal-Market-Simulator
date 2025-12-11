import pytest
from decimal import Decimal
from src.swing_analysis.level_calculator import calculate_levels, Level

def test_case_one_bullish_reference():
    """
    Test case one: Bullish reference from specification example.
    Setup: high is 674, low is 646, direction is bullish, quantization is 0.25.
    """
    high = Decimal("674")
    low = Decimal("646")
    direction = "bullish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    # Verify all 12 levels are present
    assert len(levels) == 13 # Wait, spec says "The output list contains exactly 12 levels".
    # Let me count the multipliers in my implementation:
    # -0.1, 0, 0.1, 0.382, 0.5, 0.618, 0.9, 1, 1.1, 1.382, 1.5, 1.618, 2
    # That is 13 levels.
    # Let me re-read the spec carefully.
    # "Multiplier -0.1 ... Multiplier 0 ... Multiplier 0.1 ... Multipliers 0.382, 0.5, and 0.618 ... Multiplier 0.9 ... Multiplier 1 ... Multiplier 1.1 ... Multipliers 1.382 and 1.618 ... Multiplier 1.5 ... Multiplier 2"
    # List:
    # 1. -0.1
    # 2. 0
    # 3. 0.1
    # 4. 0.382
    # 5. 0.5
    # 6. 0.618
    # 7. 0.9
    # 8. 1
    # 9. 1.1
    # 10. 1.382
    # 11. 1.618
    # 12. 1.5
    # 13. 2
    # Wait, did I miscount or did the spec imply 12?
    # "Verify all 12 levels are present"
    # Let me check the list again.
    # -0.1 (1)
    # 0 (2)
    # 0.1 (3)
    # 0.382 (4)
    # 0.5 (5)
    # 0.618 (6)
    # 0.9 (7)
    # 1 (8)
    # 1.1 (9)
    # 1.382 (10)
    # 1.618 (11)
    # 1.5 (12)
    # 2 (13)
    # Wait, 1.382 AND 1.618 are boundaries. 1.5 is midpoint.
    # Let me count again.
    # 1. -0.1
    # 2. 0
    # 3. 0.1
    # 4. 0.382
    # 5. 0.5
    # 6. 0.618
    # 7. 0.9
    # 8. 1
    # 9. 1.1
    # 10. 1.382
    # 11. 1.5
    # 12. 1.618
    # 13. 2
    # That is 13 items.
    # Why does the spec say 12?
    # "The output list contains exactly 12 levels"
    # Maybe I am double counting something?
    # "Multipliers 0.382, 0.5, and 0.618" -> 3
    # "Multipliers 1.382 and 1.618" -> 2
    # "Multiplier 1.5" -> 1
    # "Multiplier -0.1" -> 1
    # "Multiplier 0" -> 1
    # "Multiplier 0.1" -> 1
    # "Multiplier 0.9" -> 1
    # "Multiplier 1" -> 1
    # "Multiplier 1.1" -> 1
    # "Multiplier 2" -> 1
    # Total: 1 + 1 + 1 + 3 + 1 + 1 + 1 + 2 + 1 + 1 = 13.
    # Is it possible 1.5 is not included? "Multiplier 1.5 is the midpoint of the decision zone." It is listed as a multiplier.
    # Is it possible 0 or 1 is not included? "Multiplier 0 is the swing low... Multiplier 1 is the swing high".
    # Maybe 0.9 is not included? "Multiplier 0.9 is the lower edge of the recovery zone."
    # Maybe 1.1? "Multiplier 1.1 is slightly above..."
    # Maybe 0.1? "Multiplier 0.1 is slightly above..."
    # Maybe -0.1? "Multiplier -0.1 is the STOP level"
    # Maybe 2? "Multiplier 2 is the exhaustion level"
    #
    # Wait, let me look at the "Test case one" expectation: "Verify all 12 levels are present".
    # This is a contradiction or I am misunderstanding.
    # Let me re-read the list of multipliers in the text block very carefully.
    # "Multiplier -0.1 ... Multiplier 0 ... Multiplier 0.1 ... Multipliers 0.382, 0.5, and 0.618 ... Multiplier 0.9 ... Multiplier 1 ... Multiplier 1.1 ... Multipliers 1.382 and 1.618 ... Multiplier 1.5 ... Multiplier 2"
    # That is definitely 13 unique numbers.
    # -0.1, 0, 0.1, 0.382, 0.5, 0.618, 0.9, 1, 1.1, 1.382, 1.5, 1.618, 2.
    #
    # Could it be that 0 and 1 are not considered "levels" in the count?
    # "The output is a collection of levels... Multiplier 0 is the swing low itself... Multiplier 1 is the swing high itself".
    # They are listed as multipliers.
    #
    # Let me check the "Test case one" expected outcome details.
    # "The level at multiplier 0 should have price 646. The level at multiplier 1 should have price 674. The level at multiplier 2 should have price 702... The level at multiplier 1.618 should have price 691.25... Verify all 12 levels are present".
    #
    # If I have 13 levels, and the spec asks for 12, I might fail the acceptance criteria.
    # However, if I omit one, I might miss a requirement.
    # Which one is the most likely candidate to be excluded?
    # Maybe 1.5? "Multiplier 1.5 is the midpoint of the decision zone."
    # Maybe 0.9 or 1.1?
    #
    # Let's look at the "Level type annotations" section.
    # "STOP applies to -0.1. SWING_EXTREME applies to 0. SUPPORT_RESISTANCE applies to 0.1, 0.382, 0.5, 0.618, 0.9, 1, and 1.1. DECISION_ZONE applies to 1.382, 1.5, and 1.618. EXHAUSTION applies to 2."
    # Let's count the items in the type mapping:
    # STOP: -0.1 (1)
    # SWING_EXTREME: 0 (1)
    # SUPPORT_RESISTANCE: 0.1, 0.382, 0.5, 0.618, 0.9, 1, 1.1 (7)
    # DECISION_ZONE: 1.382, 1.5, 1.618 (3)
    # EXHAUSTION: 2 (1)
    # Total: 1 + 1 + 7 + 3 + 1 = 13.
    #
    # The spec explicitly lists 13 items in the type mapping.
    # The "Acceptance Criteria" says "The output list contains exactly 12 levels".
    # This is a hard contradiction. 13 defined multipliers, but count says 12.
    #
    # Hypothesis: The user made a counting error in the spec.
    # Evidence: They listed 13 distinct items in the type mapping section.
    # Action: I will implement all 13 levels because they are all explicitly defined with types. I will assume "12" was a typo for "13".
    # However, I should probably mention this in the code or comments.
    # Or, maybe I should check if one of them is redundant? No, they are all distinct numbers.
    #
    # I will proceed with 13 levels and update the test expectation to 13, noting the discrepancy.
    # Wait, if I strictly follow "Acceptance Criteria: The output list contains exactly 12 levels", I must remove one.
    # But which one? Removing any of them would violate "Multiplier X is..."
    #
    # Let's look at the "Test case one" again.
    # "Verify all 12 levels are present".
    #
    # I will stick to 13 and assume it's a typo. It's safer to include a defined level than to exclude it.
    # If the test fails because of count, I can adjust. But I'm writing the test.
    # So I will write `assert len(levels) == 13` and add a comment.
    
    # Swing size = 674 - 646 = 28
    # Multiplier 0: 646 + 0 = 646
    # Multiplier 1: 646 + 28 = 674
    # Multiplier 2: 646 + 28*2 = 646 + 56 = 702
    # Multiplier 1.618: 646 + 28 * 1.618 = 646 + 45.304 = 691.304 -> 691.25
    
    assert len(levels) == 13, "Spec lists 13 multipliers, though text mentions 12. Implementing all 13."
    
    # Check specific levels
    l_0 = next(l for l in levels if l.multiplier == Decimal("0"))
    assert l_0.price == Decimal("646.00")
    
    l_1 = next(l for l in levels if l.multiplier == Decimal("1"))
    assert l_1.price == Decimal("674.00")
    
    l_2 = next(l for l in levels if l.multiplier == Decimal("2"))
    assert l_2.price == Decimal("702.00")
    
    l_1618 = next(l for l in levels if l.multiplier == Decimal("1.618"))
    assert l_1618.price == Decimal("691.25")
    
    # Verify sorted
    multipliers = [l.multiplier for l in levels]
    assert multipliers == sorted(multipliers)

def test_case_two_bearish_reference():
    """
    Test case two: Bearish reference basic calculation.
    Setup: high is 700, low is 650, direction is bearish, quantization is 0.25.
    """
    high = Decimal("700")
    low = Decimal("650")
    direction = "bearish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    # Swing size = 50
    # Multiplier 0: 700 - (50 * 0) = 700
    # Multiplier 1: 700 - (50 * 1) = 650
    # Multiplier 2: 700 - (50 * 2) = 600
    # Multiplier 0.5: 700 - (50 * 0.5) = 675
    
    l_0 = next(l for l in levels if l.multiplier == Decimal("0"))
    assert l_0.price == Decimal("700.00")
    
    l_1 = next(l for l in levels if l.multiplier == Decimal("1"))
    assert l_1.price == Decimal("650.00")
    
    l_2 = next(l for l in levels if l.multiplier == Decimal("2"))
    assert l_2.price == Decimal("600.00")
    
    l_05 = next(l for l in levels if l.multiplier == Decimal("0.5"))
    assert l_05.price == Decimal("675.00")

def test_case_three_stock_quantization():
    """
    Test case three: Stock quantization.
    Setup: high is 150.50, low is 145.25, direction is bullish, quantization is 0.01.
    """
    high = Decimal("150.50")
    low = Decimal("145.25")
    direction = "bullish"
    quantization = Decimal("0.01")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    # Swing size = 5.25
    # Multiplier 1.5: 145.25 + (5.25 * 1.5) = 145.25 + 7.875 = 153.125 -> 153.13
    
    l_15 = next(l for l in levels if l.multiplier == Decimal("1.5"))
    assert l_15.price == Decimal("153.13")

def test_case_four_level_type_annotations():
    """
    Test case four: Level type annotations.
    Setup: any valid inputs.
    """
    high = Decimal("100")
    low = Decimal("90")
    direction = "bullish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    type_map = {l.multiplier: l.level_type for l in levels}
    
    assert type_map[Decimal("-0.1")] == "STOP"
    assert type_map[Decimal("0")] == "SWING_EXTREME"
    assert type_map[Decimal("0.382")] == "SUPPORT_RESISTANCE"
    assert type_map[Decimal("0.5")] == "SUPPORT_RESISTANCE"
    assert type_map[Decimal("0.618")] == "SUPPORT_RESISTANCE"
    assert type_map[Decimal("1.382")] == "DECISION_ZONE"
    assert type_map[Decimal("1.5")] == "DECISION_ZONE"
    assert type_map[Decimal("1.618")] == "DECISION_ZONE"
    assert type_map[Decimal("2")] == "EXHAUSTION"

def test_case_five_invalid_direction():
    """
    Test case five: Invalid direction.
    """
    with pytest.raises(ValueError, match="Invalid direction"):
        calculate_levels(Decimal("100"), Decimal("90"), "sideways", Decimal("0.25"))

def test_case_six_invalid_high_low():
    """
    Test case six: Invalid high/low relationship.
    """
    with pytest.raises(ValueError, match="High must be strictly greater than low"):
        calculate_levels(Decimal("90"), Decimal("100"), "bullish", Decimal("0.25"))

def test_case_seven_equal_high_low():
    """
    Test case seven: Equal high and low.
    """
    with pytest.raises(ValueError, match="High must be strictly greater than low"):
        calculate_levels(Decimal("100"), Decimal("100"), "bullish", Decimal("0.25"))

def test_case_eight_quantization_rounding_edge_case():
    """
    Test case eight: Quantization rounding edge case.
    Setup: high is 100, low is 97, direction is bullish, quantization is 0.25.
    """
    high = Decimal("100")
    low = Decimal("97")
    direction = "bullish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    # Swing size = 3
    # Multiplier 0.618: 97 + (3 * 0.618) = 97 + 1.854 = 98.854
    # Rounding to 0.25:
    # 98.854 / 0.25 = 395.416
    # Round to nearest integer: 395
    # 395 * 0.25 = 98.75
    # (Note: 98.854 is closer to 98.75 than 99.00. 98.75 is 0.104 away. 99.00 is 0.146 away.)
    
    l_618 = next(l for l in levels if l.multiplier == Decimal("0.618"))
    assert l_618.price == Decimal("98.75")

def test_case_nine_large_swing():
    """
    Test case nine: Large swing.
    Setup: high is 5000, low is 4000, direction is bullish, quantization is 0.25.
    """
    high = Decimal("5000")
    low = Decimal("4000")
    direction = "bullish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    # Swing size = 1000
    # -0.1: 4000 + (1000 * -0.1) = 3900
    # 2: 4000 + (1000 * 2) = 6000
    
    l_stop = next(l for l in levels if l.multiplier == Decimal("-0.1"))
    assert l_stop.price == Decimal("3900.00")
    
    l_exhaustion = next(l for l in levels if l.multiplier == Decimal("2"))
    assert l_exhaustion.price == Decimal("6000.00")

def test_case_ten_output_sorted():
    """
    Test case ten: Output is sorted.
    """
    high = Decimal("100")
    low = Decimal("90")
    direction = "bullish"
    quantization = Decimal("0.25")
    
    levels = calculate_levels(high, low, direction, quantization)
    
    multipliers = [l.multiplier for l in levels]
    assert multipliers == sorted(multipliers)
    assert multipliers[0] == Decimal("-0.1")
    assert multipliers[-1] == Decimal("2")
