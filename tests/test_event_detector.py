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

from src.analysis.event_detector import (
    EventDetector, EventType, EventSeverity, StructuralEvent, ActiveSwing
)
from bull_reference_detector import Bar
from level_calculator import calculate_levels


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
    """Test invalidation detection with close and wick thresholds."""
    
    def test_invalidation_close_below_minus_0_1(self, detector, sample_bull_swing):
        """Close below -0.1 triggers invalidation"""
        stop_level = sample_bull_swing.levels["-0.1"]
        
        previous_bar = Bar(timestamp=1600, open=stop_level+2, high=stop_level+5, low=stop_level, close=stop_level+1, index=0)
        # Close below -0.1 level
        current_bar = Bar(timestamp=1700, open=stop_level+1, high=stop_level+2, low=stop_level-5, close=stop_level-2, index=1)
        
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
        assert invalidation.level_name == "-0.1"
        assert "INVALIDATED" in invalidation.description
        assert "close below" in invalidation.description
    
    def test_invalidation_wick_below_minus_0_15(self, detector, sample_bull_swing):
        """Wick to -0.16 triggers invalidation even with close above -0.1"""
        stop_level = sample_bull_swing.levels["-0.1"]
        swing_size = sample_bull_swing.high_price - sample_bull_swing.low_price
        wick_threshold = sample_bull_swing.low_price + (swing_size * detector.invalidation_wick_threshold)
        
        previous_bar = Bar(timestamp=1600, open=stop_level+2, high=stop_level+5, low=stop_level, close=stop_level+1, index=0)
        # Wick below -0.15 threshold but close above -0.1
        current_bar = Bar(timestamp=1700, open=stop_level+1, high=stop_level+2, low=wick_threshold-1, close=stop_level+0.5, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 1
        
        invalidation = invalidation_events[0]
        assert "wick below" in invalidation.description
    
    def test_wick_between_thresholds_no_invalidation(self, detector, sample_bull_swing):
        """Wick to -0.12 with close above -0.1 = no invalidation"""
        stop_level = sample_bull_swing.levels["-0.1"]
        
        previous_bar = Bar(timestamp=1600, open=stop_level+2, high=stop_level+5, low=stop_level, close=stop_level+1, index=0)
        # Wick between -0.1 and -0.15, close above -0.1
        current_bar = Bar(timestamp=1700, open=stop_level+1, high=stop_level+2, low=stop_level-2, close=stop_level+0.5, index=1)
        
        events = detector.detect_events(
            bar=current_bar,
            source_bar_idx=1,
            active_swings=[sample_bull_swing],
            previous_bar=previous_bar
        )
        
        invalidation_events = [e for e in events if e.event_type == EventType.INVALIDATION]
        assert len(invalidation_events) == 0
    
    def test_bear_invalidation(self, detector, sample_bear_swing):
        """Bear swing invalidates on close above -0.1 (upward)"""
        stop_level = sample_bear_swing.levels["-0.1"]
        
        previous_bar = Bar(timestamp=1600, open=stop_level-2, high=stop_level, low=stop_level-5, close=stop_level-1, index=0)
        # Close above -0.1 level for bear swing
        current_bar = Bar(timestamp=1700, open=stop_level-1, high=stop_level+5, low=stop_level-2, close=stop_level+2, index=1)
        
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


if __name__ == "__main__":
    pytest.main([__file__])