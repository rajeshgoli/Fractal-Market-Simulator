"""
Test suite for Event Detector Module

Tests all aspects of structural event detection including level crossings,
completion detection, invalidation detection, and event priority handling.
"""

import pytest
import sys
import os
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.swing_analysis.event_detector import (
    EventDetector, EventType, EventSeverity, StructuralEvent, ActiveSwing
)
from src.swing_analysis.types import Bar
from src.swing_analysis.level_calculator import calculate_levels


# Global fixtures available to all test classes
@pytest.fixture
def detector():
    """Create a standard event detector instance."""
    return EventDetector()


@pytest.fixture
def sample_bull_swing():
    """Create a sample bull swing with computed levels."""
    # Bull swing from 100 to 150 (50-point range)
    high_price = 150.0
    low_price = 100.0
    
    # Calculate Fibonacci levels using the level calculator
    levels = calculate_levels(
        high=Decimal("150.0"),
        low=Decimal("100.0"),
        direction="bullish",
        quantization=Decimal("0.25")
    )
    
    # Convert to dict format
    level_dict = {str(level.multiplier): float(level.price) for level in levels}
    
    return ActiveSwing(
        swing_id="bull-M-001",
        scale="M",
        high_price=high_price,
        low_price=low_price,
        high_timestamp=1000,
        low_timestamp=500,
        is_bull=True,
        state="active",
        levels=level_dict
    )


@pytest.fixture
def sample_bear_swing():
    """Create a sample bear swing with computed levels."""
    # Bear swing from 200 to 150 (50-point range)
    high_price = 200.0
    low_price = 150.0
    
    # Calculate Fibonacci levels using the level calculator
    levels = calculate_levels(
        high=Decimal("200.0"),
        low=Decimal("150.0"),
        direction="bearish",
        quantization=Decimal("0.25")
    )
    
    # Convert to dict format
    level_dict = {str(level.multiplier): float(level.price) for level in levels}
    
    return ActiveSwing(
        swing_id="bear-M-002",
        scale="M",
        high_price=high_price,
        low_price=low_price,
        high_timestamp=1500,
        low_timestamp=1000,
        is_bull=False,
        state="active",
        levels=level_dict
    )


class TestLevelCrossing:
    """Test level crossing detection logic."""
    
    def test_level_cross_up(self, detector, sample_bull_swing):
        """Bar opens below level, closes above = LEVEL_CROSS_UP"""
        # Level at 0.618 should be around 130.9
        level_0618 = sample_bull_swing.levels["0.618"]
        
        previous_bar = Bar(timestamp=1600, open=125.0, high=127.0, low=124.0, close=126.0, index=0)
        current_bar = Bar(timestamp=1700, open=129.0, high=135.0, low=128.0, close=133.0, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        # Should detect upward crossing of 0.618 level
        crossing_events = [e for e in events if e.event_type == EventType.LEVEL_CROSS_UP]
        assert len(crossing_events) >= 1
        
        level_event = next(e for e in crossing_events if e.level_name == "0.618")
        assert level_event.event_type == EventType.LEVEL_CROSS_UP
        assert level_event.severity == EventSeverity.MINOR
        assert level_event.swing_id == "bull-M-001"
        assert "upward" in level_event.description
    
    def test_level_cross_down(self, detector, sample_bull_swing):
        """Bar opens above level, closes below = LEVEL_CROSS_DOWN"""
        level_0618 = sample_bull_swing.levels["0.618"]
        
        previous_bar = Bar(timestamp=1600, open=135.0, high=137.0, low=134.0, close=136.0, index=0)
        current_bar = Bar(timestamp=1700, open=133.0, high=134.0, low=128.0, close=129.0, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        # Should detect downward crossing of 0.618 level
        crossing_events = [e for e in events if e.event_type == EventType.LEVEL_CROSS_DOWN]
        assert len(crossing_events) >= 1
        
        level_event = next(e for e in crossing_events if e.level_name == "0.618")
        assert level_event.event_type == EventType.LEVEL_CROSS_DOWN
        assert level_event.severity == EventSeverity.MINOR
        assert "downward" in level_event.description
    
    def test_wick_only_no_crossing(self, detector, sample_bull_swing):
        """Bar wicks through level but closes on same side as open = no event"""
        level_0618 = sample_bull_swing.levels["0.618"]
        
        previous_bar = Bar(timestamp=1600, open=125.0, high=127.0, low=124.0, close=126.0, index=0)
        # Wick above 0.618 but close below
        current_bar = Bar(timestamp=1700, open=128.0, high=135.0, low=127.0, close=129.0, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        # Should not detect crossing since both open and close are below level
        crossing_events = [e for e in events if e.level_name == "0.618"]
        assert len(crossing_events) == 0
    
    def test_multiple_level_crossings(self, detector, sample_bull_swing):
        """Gap through multiple levels logs one event per level"""
        previous_bar = Bar(timestamp=1600, open=120.0, high=122.0, low=119.0, close=121.0, index=0)
        # Gap up through multiple levels: 0.5 (125), 0.618 (131), 0.9 (145)
        current_bar = Bar(timestamp=1700, open=123.0, high=147.0, low=122.0, close=146.0, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        # Should detect multiple upward crossings
        crossing_up_events = [e for e in events if e.event_type == EventType.LEVEL_CROSS_UP]
        assert len(crossing_up_events) >= 2  # Should cross multiple levels
        
        # Verify we get the expected levels
        crossed_levels = [e.level_name for e in crossing_up_events]
        assert "0.5" in crossed_levels
        assert "0.618" in crossed_levels


class TestCompletion:
    """Test completion detection at 2x extension."""
    
    def test_bull_completion_at_2x(self, detector, sample_bull_swing):
        """Bull swing completes when close >= 2.0 level"""
        level_2x = sample_bull_swing.levels["2"]
        
        previous_bar = Bar(timestamp=1600, open=level_2x-5, high=level_2x-2, low=level_2x-7, close=level_2x-3, index=0)
        # Close at or above 2x level
        current_bar = Bar(timestamp=1700, open=level_2x-2, high=level_2x+5, low=level_2x-3, close=level_2x+1, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1
        
        completion = completion_events[0]
        assert completion.severity == EventSeverity.MAJOR
        assert completion.level_name == "2"
        assert completion.swing_id == "bull-M-001"
        assert "COMPLETED" in completion.description
    
    def test_bull_completion_exact(self, detector, sample_bull_swing):
        """Completion at exactly the 2.0 level"""
        level_2x = sample_bull_swing.levels["2"]
        
        previous_bar = Bar(timestamp=1600, open=level_2x-5, high=level_2x-2, low=level_2x-7, close=level_2x-3, index=0)
        # Close exactly at 2x level
        current_bar = Bar(timestamp=1700, open=level_2x-2, high=level_2x+2, low=level_2x-3, close=level_2x, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1
    
    def test_near_miss_no_completion(self, detector, sample_bull_swing):
        """Close just below 2.0 does not trigger completion"""
        level_2x = sample_bull_swing.levels["2"]
        
        previous_bar = Bar(timestamp=1600, open=level_2x-5, high=level_2x-2, low=level_2x-7, close=level_2x-3, index=0)
        # Close just below 2x level (outside tolerance)
        current_bar = Bar(timestamp=1700, open=level_2x-2, high=level_2x+2, low=level_2x-3, close=level_2x-1, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 0
    
    def test_bear_completion(self, detector, sample_bear_swing):
        """Bear swing completes when close <= 2.0 level (downward)"""
        level_2x = sample_bear_swing.levels["2"]
        
        previous_bar = Bar(timestamp=1600, open=level_2x+5, high=level_2x+7, low=level_2x+2, close=level_2x+3, index=0)
        # Close at or below 2x level for bear swing
        current_bar = Bar(timestamp=1700, open=level_2x+2, high=level_2x+3, low=level_2x-5, close=level_2x-1, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bear_swing],
            previous_bar=previous_bar
        )
        
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1
        
        completion = completion_events[0]
        assert completion.event_type == EventType.COMPLETION
        assert completion.swing_id == "bear-M-002"


class TestInvalidation:
    """Test invalidation detection - now scale-aware per Issue #13.

    Note: Original tests used M scale with -0.1/-0.15 thresholds.
    After Issue #13, M scale uses S/M strict rules (no trade below L).
    The L/XL threshold rules are now tested in TestLXLScaleInvalidation.
    These tests are updated to verify M scale now uses S/M rules.
    """

    def test_invalidation_m_scale_trade_below_l(self, detector, sample_bull_swing):
        """M scale bull swing invalidates when price trades below L (Issue #13)"""
        # M scale now uses S/M strict rules - any trade below L invalidates
        # sample_bull_swing has scale="M", L=100, so trading below 100 triggers invalidation

        previous_bar = Bar(timestamp=1600, open=102.0, high=105.0, low=101.0, close=102.0, index=0)
        # Trade below L (100)
        current_bar = Bar(timestamp=1700, open=101.0, high=102.0, low=98.0, close=99.0, index=1)

        # Set lowest_since_low to reflect the bar's low (simulating state tracking)
        sample_bull_swing.lowest_since_low = 98.0

        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1

        invalidation = invalidation_events[0]
        assert invalidation.severity == EventSeverity.MAJOR
        assert "INVALIDATED" in invalidation.description
        assert "S/M strict rule" in invalidation.description

    def test_invalidation_m_scale_valid_above_l(self, detector, sample_bull_swing):
        """M scale bull swing valid when price stays above L (Issue #13)"""
        previous_bar = Bar(timestamp=1600, open=102.0, high=105.0, low=101.0, close=102.0, index=0)
        # Price stays above L (100)
        current_bar = Bar(timestamp=1700, open=102.0, high=108.0, low=101.0, close=106.0, index=1)

        # Set lowest_since_low above L
        sample_bull_swing.lowest_since_low = 101.0

        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0

    def test_m_scale_no_longer_uses_minus_0_15_wick_threshold(self, detector, sample_bull_swing):
        """M scale no longer uses -0.15 wick threshold - uses S/M strict rules (Issue #13)"""
        # Under old rules, wick to -0.15 would trigger invalidation
        # Under new S/M rules, ANY trade below L triggers invalidation
        # So a wick slightly below L already invalidates, not waiting for -0.15

        previous_bar = Bar(timestamp=1600, open=102.0, high=105.0, low=101.0, close=102.0, index=0)
        # Wick just slightly below L (100), which didn't trigger old -0.15 rule
        # but DOES trigger new S/M strict rule
        current_bar = Bar(timestamp=1700, open=101.0, high=103.0, low=99.0, close=102.0, index=1)

        sample_bull_swing.lowest_since_low = 99.0

        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )

        # Should invalidate under new S/M rules even though wick is only to -0.02 (99 vs L=100)
        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "S/M strict rule" in invalidation_events[0].description
    
    def test_bear_invalidation_m_scale(self, detector, sample_bear_swing):
        """M scale bear swing invalidates when price trades above H (Issue #13)"""
        # M scale now uses S/M strict rules - any trade above H invalidates
        # sample_bear_swing has scale="M", H=200

        previous_bar = Bar(timestamp=1600, open=195.0, high=198.0, low=193.0, close=196.0, index=0)
        # Trade above H (200)
        current_bar = Bar(timestamp=1700, open=198.0, high=202.0, low=197.0, close=199.0, index=1)

        # Set highest_since_high to reflect the bar's high
        sample_bear_swing.highest_since_high = 202.0

        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bear_swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1

        invalidation = invalidation_events[0]
        assert invalidation.swing_id == "bear-M-002"
        assert "S/M strict rule" in invalidation.description


class TestEventPriority:
    """Test event priority handling."""
    
    def test_invalidation_prevents_completion(self, detector, sample_bull_swing):
        """If both completion and invalidation conditions met, only invalidation logged"""
        level_2x = sample_bull_swing.levels["2"]
        stop_level = sample_bull_swing.levels["-0.1"]
        
        previous_bar = Bar(timestamp=1600, open=(level_2x + stop_level) / 2, high=level_2x-5, low=stop_level+2, close=level_2x-7, index=0)
        # Bar that both completes and invalidates (close above 2x but wick below -0.15)
        swing_size = sample_bull_swing.high_price - sample_bull_swing.low_price
        wick_threshold = sample_bull_swing.low_price + (swing_size * detector.invalidation_wick_threshold)
        
        current_bar = Bar(timestamp=1700, open=level_2x-5, high=level_2x+2, low=wick_threshold-1, close=level_2x+1, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        # Should only have invalidation event, no completion
        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        
        assert len(invalidation_events) == 1
        assert len(completion_events) == 0
    
    def test_completion_absorbs_2x_crossing(self, detector, sample_bull_swing):
        """Completion event replaces LEVEL_CROSS at 2.0"""
        level_2x = sample_bull_swing.levels["2"]
        
        previous_bar = Bar(timestamp=1600, open=level_2x-5, high=level_2x-2, low=level_2x-7, close=level_2x-3, index=0)
        # Cross through 2.0 level and complete
        current_bar = Bar(timestamp=1700, open=level_2x-2, high=level_2x+5, low=level_2x-3, close=level_2x+1, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        level_cross_2x_events = [e for e in events if e.level_name == "2" and e.event_type == EventType.LEVEL_CROSS_UP]
        
        assert len(completion_events) == 1
        assert len(level_cross_2x_events) == 0  # Should be absorbed by completion


class TestMultiSwingDetection:
    """Test events across multiple swings."""
    
    def test_events_across_multiple_swings(self, detector, sample_bull_swing, sample_bear_swing):
        """Same bar can trigger events on different active swings"""
        # Position bar to trigger events on both swings
        bar = Bar(timestamp=1700, open=140.0, high=155.0, low=135.0, close=152.0, index=1)
        previous_bar = Bar(timestamp=1600, open=135.0, high=137.0, low=134.0, close=136.0, index=0)
        
        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing, sample_bear_swing],
            previous_bar=previous_bar
        )
        
        # Should have events from both swings
        bull_events = [e for e in events if e.swing_id == "bull-M-001"]
        bear_events = [e for e in events if e.swing_id == "bear-M-002"]
        
        assert len(bull_events) >= 1
        assert len(bear_events) >= 1
    
    def test_different_scales_independent(self, detector):
        """S-scale and L-scale swings trigger events independently"""
        # Create swings at different scales but overlapping price ranges
        s_swing = ActiveSwing(
            swing_id="bull-S-001",
            scale="S",
            high_price=130.0,
            low_price=120.0,
            high_timestamp=1000,
            low_timestamp=800,
            is_bull=True,
            state="active",
            levels={"0.618": 126.18, "1": 130.0, "2": 140.0, "-0.1": 119.0}
        )
        
        l_swing = ActiveSwing(
            swing_id="bull-L-001",
            scale="L",
            high_price=140.0,
            low_price=100.0,
            high_timestamp=2000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 124.72, "1": 140.0, "2": 180.0, "-0.1": 96.0}
        )
        
        bar = Bar(timestamp=1700, open=122.0, high=127.0, low=121.0, close=126.5, index=1)
        previous_bar = Bar(timestamp=1600, open=120.0, high=122.0, low=119.0, close=121.0, index=0)
        
        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[s_swing, l_swing],
            previous_bar=previous_bar
        )
        
        # Events should be detected for both scales
        s_events = [e for e in events if e.scale == "S"]
        l_events = [e for e in events if e.scale == "L"]
        
        # Both scales should generate independent events
        assert len(s_events) >= 0
        assert len(l_events) >= 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_no_previous_bar(self, detector, sample_bull_swing):
        """First bar in series - crossing detection handles None previous_bar"""
        current_bar = Bar(timestamp=1700, open=120.0, high=125.0, low=118.0, close=123.0, index=0)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=0,
            active_swings=[sample_bull_swing],
            previous_bar=None
        )
        
        # Should not crash and should only check completion/invalidation
        crossing_events = [e for e in events if e.event_type in [EventType.LEVEL_CROSS_UP, EventType.LEVEL_CROSS_DOWN]]
        assert len(crossing_events) == 0  # No crossings without previous bar
    
    def test_inactive_swing_ignored(self, detector, sample_bull_swing):
        """Swings with state != 'active' don't generate events"""
        sample_bull_swing.state = "invalidated"
        
        bar = Bar(timestamp=1700, open=120.0, high=145.0, low=118.0, close=142.0, index=1)
        previous_bar = Bar(timestamp=1600, open=115.0, high=117.0, low=114.0, close=116.0, index=0)
        
        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        assert len(events) == 0
    
    def test_empty_swing_list(self, detector):
        """Empty active_swings list returns empty event list"""
        bar = Bar(timestamp=1700, open=120.0, high=125.0, low=118.0, close=123.0, index=1)
        previous_bar = Bar(timestamp=1600, open=115.0, high=117.0, low=114.0, close=116.0, index=0)
        
        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[],
            previous_bar=previous_bar
        )
        
        assert len(events) == 0


class TestLevelCalculatorIntegration:
    """Integration test with actual LevelCalculator output."""
    
    def test_with_level_calculator(self, detector):
        """Integration test using actual LevelCalculator output"""
        # Create a swing and compute levels using LevelCalculator
        levels = calculate_levels(
            high=Decimal("175.0"),
            low=Decimal("125.0"), 
            direction="bullish",
            quantization=Decimal("0.25")
        )
        
        # Convert to swing format
        level_dict = {str(level.multiplier): float(level.price) for level in levels}
        
        swing = ActiveSwing(
            swing_id="bull-integration-001",
            scale="M",
            high_price=175.0,
            low_price=125.0,
            high_timestamp=2000,
            low_timestamp=1000,
            is_bull=True,
            state="active",
            levels=level_dict
        )
        
        # Test completion at 2x level
        level_2x = level_dict["2"]
        bar = Bar(timestamp=2100, open=level_2x-5, high=level_2x+5, low=level_2x-7, close=level_2x+2, index=1)
        previous_bar = Bar(timestamp=2000, open=level_2x-10, high=level_2x-5, low=level_2x-12, close=level_2x-8, index=0)
        
        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )
        
        # Should detect completion
        completion_events = [e for e in events if e.event_type == EventType.COMPLETION]
        assert len(completion_events) == 1
        
        completion = completion_events[0]
        assert completion.level_price == level_2x
        assert completion.swing_id == "bull-integration-001"
        assert "COMPLETED" in completion.description


class TestSMScaleInvalidation:
    """Test S/M scale invalidation rules (Issue #13)."""

    def test_sm_bull_valid_above_low(self, detector):
        """S/M bull swing remains valid when price stays above L."""
        swing = ActiveSwing(
            swing_id="bull-S-001",
            scale="S",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=105.0,  # Stayed above L
            highest_since_high=None
        )

        # Price stays above L
        bar = Bar(timestamp=1700, open=110.0, high=120.0, low=105.0, close=115.0, index=1)
        previous_bar = Bar(timestamp=1600, open=105.0, high=112.0, low=104.0, close=110.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0

    def test_sm_bull_invalid_below_low(self, detector):
        """S/M bull swing invalidates when price trades below L."""
        swing = ActiveSwing(
            swing_id="bull-S-002",
            scale="S",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=98.0,  # Traded below L
            highest_since_high=None
        )

        bar = Bar(timestamp=1700, open=102.0, high=105.0, low=98.0, close=101.0, index=1)
        previous_bar = Bar(timestamp=1600, open=105.0, high=107.0, low=104.0, close=102.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "S/M strict rule" in invalidation_events[0].description

    def test_sm_bear_valid_below_high(self, detector):
        """S/M bear swing remains valid when price stays below H."""
        swing = ActiveSwing(
            swing_id="bear-S-001",
            scale="S",
            high_price=200.0,
            low_price=150.0,
            high_timestamp=500,
            low_timestamp=1000,
            is_bull=False,
            state="active",
            levels={"0.618": 169.1, "1": 150.0, "2": 100.0, "-0.1": 205.0},
            encroachment_achieved=True,
            lowest_since_low=None,
            highest_since_high=195.0  # Stayed below H
        )

        bar = Bar(timestamp=1700, open=175.0, high=195.0, low=170.0, close=180.0, index=1)
        previous_bar = Bar(timestamp=1600, open=180.0, high=190.0, low=178.0, close=175.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0

    def test_sm_bear_invalid_above_high(self, detector):
        """S/M bear swing invalidates when price trades above H."""
        swing = ActiveSwing(
            swing_id="bear-S-002",
            scale="S",
            high_price=200.0,
            low_price=150.0,
            high_timestamp=500,
            low_timestamp=1000,
            is_bull=False,
            state="active",
            levels={"0.618": 169.1, "1": 150.0, "2": 100.0, "-0.1": 205.0},
            encroachment_achieved=True,
            lowest_since_low=None,
            highest_since_high=202.0  # Traded above H
        )

        bar = Bar(timestamp=1700, open=198.0, high=202.0, low=196.0, close=199.0, index=1)
        previous_bar = Bar(timestamp=1600, open=195.0, high=198.0, low=194.0, close=198.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "S/M strict rule" in invalidation_events[0].description

    def test_m_scale_uses_sm_rules(self, detector):
        """M scale uses S/M rules (not L/XL)."""
        swing = ActiveSwing(
            swing_id="bull-M-001",
            scale="M",  # M scale
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=98.0,  # Below L, should invalidate under S/M rules
            highest_since_high=None
        )

        bar = Bar(timestamp=1700, open=102.0, high=105.0, low=98.0, close=101.0, index=1)
        previous_bar = Bar(timestamp=1600, open=105.0, high=107.0, low=104.0, close=102.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "S/M strict rule" in invalidation_events[0].description


class TestLXLScaleInvalidation:
    """Test L/XL scale invalidation rules (Issue #13)."""

    def test_lxl_bull_valid_above_deep_threshold(self, detector):
        """L/XL bull swing valid when price above L - 0.15*delta."""
        # swing_size = 50, so L - 0.15*delta = 100 - 7.5 = 92.5
        swing = ActiveSwing(
            swing_id="bull-L-001",
            scale="L",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=95.0,  # Between L and L-0.15*delta, valid for L/XL
            highest_since_high=None
        )

        # Close above L - 0.10*delta (95.0)
        bar = Bar(timestamp=1700, open=98.0, high=102.0, low=95.0, close=100.0, index=1)
        previous_bar = Bar(timestamp=1600, open=100.0, high=103.0, low=99.0, close=98.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0

    def test_lxl_bull_invalid_deep_trade_through(self, detector):
        """L/XL bull swing invalid when price trades below L - 0.15*delta."""
        # swing_size = 50, so L - 0.15*delta = 100 - 7.5 = 92.5
        swing = ActiveSwing(
            swing_id="bull-L-002",
            scale="L",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=91.0,  # Below L - 0.15*delta (92.5)
            highest_since_high=None
        )

        bar = Bar(timestamp=1700, open=95.0, high=98.0, low=91.0, close=96.0, index=1)
        previous_bar = Bar(timestamp=1600, open=98.0, high=100.0, low=97.0, close=95.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "L/XL deep threshold" in invalidation_events[0].description

    def test_lxl_bull_invalid_close_below_soft(self, detector):
        """L/XL bull swing invalid when close below L - 0.10*delta (even if no deep trade)."""
        # swing_size = 50, L - 0.10*delta = 100 - 5 = 95
        swing = ActiveSwing(
            swing_id="bull-L-003",
            scale="L",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=96.0,  # Above deep threshold (92.5)
            highest_since_high=None
        )

        # Close below soft threshold (95)
        bar = Bar(timestamp=1700, open=98.0, high=100.0, low=93.0, close=94.0, index=1)
        previous_bar = Bar(timestamp=1600, open=100.0, high=102.0, low=99.0, close=98.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "L/XL soft threshold" in invalidation_events[0].description

    def test_lxl_bull_valid_wick_below_soft_close_above(self, detector):
        """L/XL bull swing valid when wick below soft threshold but close above."""
        swing = ActiveSwing(
            swing_id="bull-L-004",
            scale="L",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=93.0,  # Above deep threshold, wick reached soft area
            highest_since_high=None
        )

        # Wick below soft threshold (95) but close above
        bar = Bar(timestamp=1700, open=98.0, high=100.0, low=93.0, close=97.0, index=1)
        previous_bar = Bar(timestamp=1600, open=100.0, high=102.0, low=99.0, close=98.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0

    def test_xl_scale_uses_lxl_rules(self, detector):
        """XL scale uses L/XL rules (not S/M)."""
        # swing_size = 50, L - 0.10*delta = 95
        swing = ActiveSwing(
            swing_id="bull-XL-001",
            scale="XL",  # XL scale
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0, "-0.1": 95.0},
            encroachment_achieved=True,
            lowest_since_low=97.0,  # Below L (100), but above L-0.15*delta (92.5)
            highest_since_high=None
        )

        # Under S/M rules this would invalidate, but L/XL allows it
        bar = Bar(timestamp=1700, open=98.0, high=102.0, low=97.0, close=100.0, index=1)
        previous_bar = Bar(timestamp=1600, open=100.0, high=103.0, low=99.0, close=98.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0

    def test_lxl_bear_invalid_deep_trade_through(self, detector):
        """L/XL bear swing invalid when price trades above H + 0.15*delta."""
        # swing_size = 50, H + 0.15*delta = 200 + 7.5 = 207.5
        swing = ActiveSwing(
            swing_id="bear-L-001",
            scale="L",
            high_price=200.0,
            low_price=150.0,
            high_timestamp=500,
            low_timestamp=1000,
            is_bull=False,
            state="active",
            levels={"0.618": 169.1, "1": 150.0, "2": 100.0, "-0.1": 205.0},
            encroachment_achieved=True,
            lowest_since_low=None,
            highest_since_high=209.0  # Above H + 0.15*delta
        )

        bar = Bar(timestamp=1700, open=205.0, high=209.0, low=203.0, close=206.0, index=1)
        previous_bar = Bar(timestamp=1600, open=202.0, high=205.0, low=201.0, close=205.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "L/XL deep threshold" in invalidation_events[0].description

    def test_lxl_bear_invalid_close_above_soft(self, detector):
        """L/XL bear swing invalid when close above H + 0.10*delta."""
        # swing_size = 50, H + 0.10*delta = 200 + 5 = 205
        swing = ActiveSwing(
            swing_id="bear-L-002",
            scale="L",
            high_price=200.0,
            low_price=150.0,
            high_timestamp=500,
            low_timestamp=1000,
            is_bull=False,
            state="active",
            levels={"0.618": 169.1, "1": 150.0, "2": 100.0, "-0.1": 205.0},
            encroachment_achieved=True,
            lowest_since_low=None,
            highest_since_high=204.0  # Below deep threshold
        )

        # Close above soft threshold (205)
        bar = Bar(timestamp=1700, open=203.0, high=207.0, low=202.0, close=206.0, index=1)
        previous_bar = Bar(timestamp=1600, open=200.0, high=203.0, low=199.0, close=203.0, index=0)

        events = detector.detect_events(
            bar=bar,
            source_bar_idx=1,
            active_swings=[swing],
            previous_bar=previous_bar
        )

        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        assert "L/XL soft threshold" in invalidation_events[0].description


class TestEncroachmentTracking:
    """Test encroachment state tracking (Issue #13)."""

    def test_encroachment_not_achieved_initially(self, detector):
        """New swing starts with encroachment_achieved=False."""
        swing = ActiveSwing(
            swing_id="bull-S-001",
            scale="S",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0},
            encroachment_achieved=False,  # Not yet achieved
            lowest_since_low=100.0,
            highest_since_high=None
        )

        assert swing.encroachment_achieved == False

    def test_encroachment_level_calculation(self, detector):
        """Encroachment level is L + 0.382*delta for bull swings."""
        # For swing H=150, L=100: delta=50, encroachment = 100 + 0.382*50 = 119.1
        swing = ActiveSwing(
            swing_id="bull-S-002",
            scale="S",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"0.618": 130.9, "1": 150.0, "2": 200.0},
            encroachment_achieved=False,
            lowest_since_low=100.0,
            highest_since_high=None
        )

        delta = swing.high_price - swing.low_price
        expected_encroachment = swing.low_price + 0.382 * delta
        assert abs(expected_encroachment - 119.1) < 0.1


class TestScaleDispatch:
    """Test that invalidation correctly dispatches by scale."""

    def test_s_scale_dispatches_to_sm(self, detector):
        """S scale swing uses S/M invalidation rules."""
        # Price below L would invalidate under S/M but not L/XL
        swing = ActiveSwing(
            swing_id="bull-S-001",
            scale="S",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={},
            encroachment_achieved=True,
            lowest_since_low=98.0,  # Below L
            highest_since_high=None
        )

        bar = Bar(timestamp=1700, open=102.0, high=105.0, low=98.0, close=101.0, index=1)

        event = detector.check_invalidation(bar, 1, swing)
        assert event is not None
        assert "S/M strict rule" in event.description

    def test_l_scale_dispatches_to_lxl(self, detector):
        """L scale swing uses L/XL invalidation rules."""
        # Price below L but above L-0.15*delta is valid under L/XL
        swing = ActiveSwing(
            swing_id="bull-L-001",
            scale="L",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={},
            encroachment_achieved=True,
            lowest_since_low=95.0,  # Below L but above L-0.15*delta (92.5)
            highest_since_high=None
        )

        # Close above soft threshold
        bar = Bar(timestamp=1700, open=98.0, high=102.0, low=95.0, close=97.0, index=1)

        event = detector.check_invalidation(bar, 1, swing)
        assert event is None  # No invalidation under L/XL rules


if __name__ == "__main__":
    pytest.main([__file__])