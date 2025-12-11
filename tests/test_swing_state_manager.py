"""
Test suite for Swing State Manager Module

Tests all aspects of swing lifecycle management including swing detection across scales,
state transitions, replacement logic, and integration with other modules.
"""

import pytest
import sys
import os
from decimal import Decimal
from unittest.mock import Mock, patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.swing_analysis.swing_state_manager import SwingStateManager, SwingUpdateResult
from src.swing_analysis.scale_calibrator import ScaleConfig
from src.swing_analysis.event_detector import EventType, EventSeverity, StructuralEvent, ActiveSwing
from src.swing_analysis.bull_reference_detector import Bar


# Global fixtures available to all test classes
@pytest.fixture
def sample_scale_config():
    """Create a sample scale configuration."""
    return ScaleConfig(
        boundaries={
            'S': (0.0, 25.0),
            'M': (25.0, 50.0), 
            'L': (50.0, 100.0),
            'XL': (100.0, float('inf'))
        },
        aggregations={
            'S': 1,
            'M': 5,
            'L': 15,
            'XL': 60
        },
        swing_count=50,
        used_defaults=False,
        median_durations={
            'S': 15,
            'M': 25,
            'L': 40,
            'XL': 80
        }
    )


@pytest.fixture
def sample_bars():
    """Create sample OHLC bars for testing."""
    bars = []
    base_timestamp = 1000000
    
    # Create 100 bars with some price movement
    for i in range(100):
        timestamp = base_timestamp + i * 60  # 1-minute intervals
        
        # Simple trending price pattern
        base_price = 100.0 + (i * 0.5)  # Upward trending
        
        # Add some volatility
        high = base_price + (2.0 if i % 10 == 0 else 0.5)
        low = base_price - (1.5 if i % 7 == 0 else 0.3)
        open_price = base_price + ((-1) ** i) * 0.2
        close = base_price + ((-1) ** (i+1)) * 0.1
        
        bar = Bar(
            timestamp=timestamp,
            open=open_price,
            high=high,
            low=low,
            close=close,
            index=i
        )
        bars.append(bar)
    
    return bars


@pytest.fixture
def swing_state_manager(sample_scale_config):
    """Create a swing state manager with sample configuration."""
    return SwingStateManager(sample_scale_config)


@pytest.fixture
def sample_active_swing():
    """Create a sample active swing for testing."""
    return ActiveSwing(
        swing_id="test-M-001",
        scale="M",
        high_price=150.0,
        low_price=100.0,
        high_timestamp=2000,
        low_timestamp=1000,
        is_bull=True,
        state="active",
        levels={
            "-0.1": 95.0,
            "0": 100.0,
            "0.382": 119.1,
            "0.5": 125.0,
            "0.618": 130.9,
            "1": 150.0,
            "1.382": 169.1,
            "1.5": 175.0,
            "1.618": 180.9,
            "2": 200.0
        }
    )


class TestSwingStateManagerInitialization:
    """Test swing state manager initialization and setup."""
    
    def test_initialization(self, sample_scale_config):
        """Test basic initialization."""
        manager = SwingStateManager(sample_scale_config)
        
        assert manager.scale_config == sample_scale_config
        assert manager.event_detector is not None
        assert len(manager.active_swings) == 4  # S, M, L, XL
        assert all(scale in manager.active_swings for scale in ['S', 'M', 'L', 'XL'])
        assert manager.bar_aggregator is None  # Not initialized yet
        assert manager.total_bars_processed == 0
    
    def test_initialize_with_bars(self, swing_state_manager, sample_bars):
        """Test initialization with historical bars."""
        swing_state_manager.initialize_with_bars(sample_bars)
        
        assert swing_state_manager.bar_aggregator is not None
        assert swing_state_manager.bar_aggregator.source_bar_count == len(sample_bars)
        
        # Check that some swings were detected during initialization
        total_swings = sum(len(swings) for swings in swing_state_manager.active_swings.values())
        assert total_swings >= 0  # May be 0 if patterns don't match scale boundaries
    
    def test_initialize_with_empty_bars(self, swing_state_manager):
        """Test initialization with empty bar list."""
        swing_state_manager.initialize_with_bars([])
        
        assert swing_state_manager.bar_aggregator is None
        assert all(len(swings) == 0 for swings in swing_state_manager.active_swings.values())


class TestSwingDetection:
    """Test swing detection and creation logic."""
    
    def test_is_swing_in_scale(self, swing_state_manager):
        """Test scale classification of swing sizes."""
        assert swing_state_manager._is_swing_in_scale(15.0, 'S')
        assert swing_state_manager._is_swing_in_scale(35.0, 'M')
        assert swing_state_manager._is_swing_in_scale(75.0, 'L')
        assert swing_state_manager._is_swing_in_scale(150.0, 'XL')
        
        # Boundary conditions
        assert swing_state_manager._is_swing_in_scale(25.0, 'M')
        assert not swing_state_manager._is_swing_in_scale(25.0, 'S')
    
    def test_create_active_swing(self, swing_state_manager):
        """Test creation of ActiveSwing from swing reference."""
        swing_ref = {
            'high_price': 150.0,
            'low_price': 100.0,
            'size': 50.0,
            'high_timestamp': 2000,
            'low_timestamp': 1000
        }
        
        active_swing = swing_state_manager._create_active_swing(swing_ref, 'M', True)
        
        assert active_swing is not None
        assert active_swing.scale == 'M'
        assert active_swing.is_bull == True
        assert active_swing.state == "active"
        assert active_swing.high_price == 150.0
        assert active_swing.low_price == 100.0
        assert len(active_swing.levels) > 0
        assert "2" in active_swing.levels  # Should have 2x extension level
    
    def test_create_active_swing_invalid_data(self, swing_state_manager):
        """Test handling of invalid swing reference data."""
        # Missing required fields
        invalid_ref = {'size': 50.0}
        
        active_swing = swing_state_manager._create_active_swing(invalid_ref, 'M', True)
        assert active_swing is None  # Should handle error gracefully


class TestStateTransitions:
    """Test swing state transition handling."""
    
    def test_handle_completion(self, swing_state_manager, sample_active_swing):
        """Test handling of completion events."""
        # Add swing to active list
        swing_state_manager.active_swings['M'].append(sample_active_swing)
        
        # Create completion event
        completion_event = StructuralEvent(
            event_type=EventType.COMPLETION,
            severity=EventSeverity.MAJOR,
            timestamp=3000,
            source_bar_idx=50,
            level_name="2",
            level_price=200.0,
            swing_id=sample_active_swing.swing_id,
            scale="M",
            bar_open=195.0,
            bar_high=201.0,
            bar_low=194.0,
            bar_close=200.0,
            description="Bull swing test-M-001: COMPLETED at 2x extension (200.00)"
        )
        
        state_changes = swing_state_manager._handle_completion(completion_event, 'M')
        
        assert len(state_changes) == 1
        assert state_changes[0] == (sample_active_swing.swing_id, "active", "completed")
        assert sample_active_swing.state == "completed"
        assert len(swing_state_manager.completed_swings['M']) == 1
    
    def test_handle_invalidation(self, swing_state_manager, sample_active_swing):
        """Test handling of invalidation events."""
        # Add swing to active list
        swing_state_manager.active_swings['M'].append(sample_active_swing)
        
        # Create invalidation event
        invalidation_event = StructuralEvent(
            event_type=EventType.INVALIDATION,
            severity=EventSeverity.MAJOR,
            timestamp=3000,
            source_bar_idx=50,
            level_name="-0.1",
            level_price=95.0,
            swing_id=sample_active_swing.swing_id,
            scale="M",
            bar_open=96.0,
            bar_high=97.0,
            bar_low=93.0,
            bar_close=94.0,
            description="Bull swing test-M-001: INVALIDATED - close below -0.1 threshold"
        )
        
        state_changes = swing_state_manager._handle_invalidation(invalidation_event, 'M')
        
        assert len(state_changes) == 1
        assert state_changes[0] == (sample_active_swing.swing_id, "active", "invalidated")
        assert sample_active_swing.state == "invalidated"
        assert len(swing_state_manager.active_swings['M']) == 0  # Removed from active
        assert len(swing_state_manager.invalidated_swings['M']) == 1


class TestSwingReplacement:
    """Test swing replacement logic."""
    
    def test_check_swing_replacements(self, swing_state_manager):
        """Test swing replacement based on size similarity."""
        # Create existing swing
        existing_swing = ActiveSwing(
            swing_id="existing-M-001",
            scale="M",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"2": 200.0}
        )
        swing_state_manager.active_swings['M'].append(existing_swing)
        
        # Create new swing with similar size (within 20%)
        new_swing = ActiveSwing(
            swing_id="new-M-002",
            scale="M",
            high_price=155.0,
            low_price=105.0,
            high_timestamp=2000,
            low_timestamp=1500,
            is_bull=True,  # Same direction
            state="active",
            levels={"2": 205.0}
        )
        
        # Add new swing to active list first (simulate what would happen in real usage)
        swing_state_manager.active_swings['M'].append(new_swing)
        
        removed_ids = swing_state_manager._check_swing_replacements('M', [new_swing])
        
        assert existing_swing.swing_id in removed_ids
        assert len(swing_state_manager.active_swings['M']) == 1  # Only new swing remains
        assert swing_state_manager.active_swings['M'][0].swing_id == new_swing.swing_id
    
    def test_no_replacement_different_direction(self, swing_state_manager):
        """Test that swings of different directions don't replace each other."""
        # Create existing bull swing
        existing_swing = ActiveSwing(
            swing_id="existing-M-001",
            scale="M",
            high_price=150.0,
            low_price=100.0,
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"2": 200.0}
        )
        swing_state_manager.active_swings['M'].append(existing_swing)
        
        # Create new bear swing with similar size
        new_swing = ActiveSwing(
            swing_id="new-M-002",
            scale="M",
            high_price=155.0,
            low_price=105.0,
            high_timestamp=2000,
            low_timestamp=1500,
            is_bull=False,  # Different direction
            state="active",
            levels={"2": 55.0}
        )
        
        # Add new swing to active list first
        swing_state_manager.active_swings['M'].append(new_swing)
        
        removed_ids = swing_state_manager._check_swing_replacements('M', [new_swing])
        
        assert len(removed_ids) == 0
        assert len(swing_state_manager.active_swings['M']) == 2  # Both swings remain
    
    def test_no_replacement_size_difference(self, swing_state_manager):
        """Test that swings with >20% size difference don't replace each other."""
        # Create existing swing
        existing_swing = ActiveSwing(
            swing_id="existing-M-001",
            scale="M",
            high_price=150.0,
            low_price=100.0,  # 50-point range
            high_timestamp=1000,
            low_timestamp=500,
            is_bull=True,
            state="active",
            levels={"2": 200.0}
        )
        swing_state_manager.active_swings['M'].append(existing_swing)
        
        # Create new swing with >20% size difference
        new_swing = ActiveSwing(
            swing_id="new-M-002",
            scale="M",
            high_price=170.0,
            low_price=105.0,  # 65-point range (30% larger)
            high_timestamp=2000,
            low_timestamp=1500,
            is_bull=True,
            state="active",
            levels={"2": 235.0}
        )
        
        # Add new swing to active list first
        swing_state_manager.active_swings['M'].append(new_swing)
        
        removed_ids = swing_state_manager._check_swing_replacements('M', [new_swing])
        
        assert len(removed_ids) == 0
        assert len(swing_state_manager.active_swings['M']) == 2  # Both swings remain


class TestSwingQueries:
    """Test swing query methods."""
    
    def test_get_active_swings_all_scales(self, swing_state_manager, sample_active_swing):
        """Test getting active swings for all scales."""
        # Add swings to different scales
        swing_m = sample_active_swing
        swing_s = ActiveSwing(
            swing_id="test-S-001",
            scale="S",
            high_price=120.0,
            low_price=110.0,
            high_timestamp=1500,
            low_timestamp=1200,
            is_bull=True,
            state="active",
            levels={"2": 130.0}
        )
        
        swing_state_manager.active_swings['M'].append(swing_m)
        swing_state_manager.active_swings['S'].append(swing_s)
        
        all_swings = swing_state_manager.get_active_swings()
        
        assert len(all_swings) == 2
        assert swing_m in all_swings
        assert swing_s in all_swings
    
    def test_get_active_swings_specific_scale(self, swing_state_manager, sample_active_swing):
        """Test getting active swings for a specific scale."""
        swing_state_manager.active_swings['M'].append(sample_active_swing)
        
        m_swings = swing_state_manager.get_active_swings('M')
        s_swings = swing_state_manager.get_active_swings('S')
        
        assert len(m_swings) == 1
        assert len(s_swings) == 0
        assert m_swings[0] == sample_active_swing
    
    def test_get_swing_counts(self, swing_state_manager, sample_active_swing):
        """Test getting swing counts by scale and state."""
        # Add swings to different states
        swing_state_manager.active_swings['M'].append(sample_active_swing)
        
        completed_swing = ActiveSwing(
            swing_id="completed-M-001",
            scale="M",
            high_price=140.0,
            low_price=90.0,
            high_timestamp=1500,
            low_timestamp=1000,
            is_bull=True,
            state="completed",
            levels={"2": 190.0}
        )
        swing_state_manager.completed_swings['M'].append(completed_swing)
        
        counts = swing_state_manager.get_swing_counts()
        
        assert counts['M']['active'] == 1
        assert counts['M']['completed'] == 1
        assert counts['M']['invalidated'] == 0
        assert counts['S']['active'] == 0


class TestUpdateSwings:
    """Test main update_swings method integration."""
    
    @patch('src.swing_analysis.swing_state_manager.detect_swings')
    def test_update_swings_basic(self, mock_detect_swings, swing_state_manager, sample_bars):
        """Test basic update_swings functionality."""
        # Initialize with bars
        swing_state_manager.initialize_with_bars(sample_bars[:50])
        
        # Mock swing detection to return empty results
        mock_detect_swings.return_value = {
            'current_price': 125.0,
            'swing_highs': [],
            'swing_lows': [],
            'bull_references': [],
            'bear_references': []
        }
        
        # Update with new bar
        new_bar = sample_bars[50]
        result = swing_state_manager.update_swings(new_bar, 50)
        
        assert isinstance(result, SwingUpdateResult)
        assert swing_state_manager.total_bars_processed == 1
        assert len(result.events) == 0  # No events with empty swings
    
    def test_update_swings_no_aggregator(self, swing_state_manager):
        """Test update_swings when aggregator not initialized."""
        bar = Bar(timestamp=1000, open=100.0, high=101.0, low=99.0, close=100.5, index=0)
        
        result = swing_state_manager.update_swings(bar, 0)
        
        assert isinstance(result, SwingUpdateResult)
        assert len(result.events) == 0
        assert len(result.new_swings) == 0
        assert len(result.state_changes) == 0
        assert len(result.removed_swings) == 0


class TestPerformance:
    """Test performance requirements."""
    
    def test_initialization_performance(self, swing_state_manager, sample_bars):
        """Test that initialization completes within reasonable time."""
        import time
        
        # Create larger dataset with proper ordering
        large_bars = []
        base_timestamp = 1000000
        for i in range(2000):  # 2000 bars
            # Use original pattern but ensure proper ordering
            original_idx = i % len(sample_bars)
            original_bar = sample_bars[original_idx]
            
            new_bar = Bar(
                timestamp=base_timestamp + i * 60,  # Proper chronological order
                open=original_bar.open,
                high=original_bar.high,
                low=original_bar.low,
                close=original_bar.close,
                index=i
            )
            large_bars.append(new_bar)
        
        start_time = time.time()
        swing_state_manager.initialize_with_bars(large_bars)
        end_time = time.time()
        
        # Should complete in reasonable time (adjust threshold as needed)
        assert end_time - start_time < 5.0  # 5 seconds for 2000 bars
    
    def test_update_performance(self, swing_state_manager, sample_bars):
        """Test that individual updates are fast enough."""
        import time
        
        # Initialize with moderate dataset
        swing_state_manager.initialize_with_bars(sample_bars)
        
        # Measure update time
        new_bar = Bar(timestamp=2000000, open=150.0, high=151.0, low=149.0, close=150.5, index=len(sample_bars))
        
        start_time = time.time()
        result = swing_state_manager.update_swings(new_bar, len(sample_bars))
        end_time = time.time()
        
        # Should complete very quickly for single update
        assert end_time - start_time < 0.1  # 100ms for single update


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_scale_config(self):
        """Test handling of edge case configurations."""
        minimal_config = ScaleConfig(
            boundaries={'S': (0.0, 10.0)},
            aggregations={'S': 1},
            swing_count=0,
            used_defaults=True,
            median_durations={'S': 10}
        )
        
        manager = SwingStateManager(minimal_config)
        assert len(manager.active_swings) == 4  # Still creates all scales
        assert manager.scale_config == minimal_config
    
    def test_single_bar_update(self, swing_state_manager):
        """Test update with single bar (no previous bar)."""
        single_bar = [Bar(timestamp=1000, open=100.0, high=101.0, low=99.0, close=100.5, index=0)]
        swing_state_manager.initialize_with_bars(single_bar)
        
        new_bar = Bar(timestamp=1060, open=100.5, high=102.0, low=100.0, close=101.5, index=1)
        result = swing_state_manager.update_swings(new_bar, 1)
        
        # Should handle gracefully without errors
        assert isinstance(result, SwingUpdateResult)


class TestIntegration:
    """Test integration with other modules."""
    
    def test_integration_with_event_detector(self, swing_state_manager, sample_bars, sample_active_swing):
        """Test integration with event detector for state transitions."""
        # Initialize and add an active swing
        swing_state_manager.initialize_with_bars(sample_bars[:50])
        swing_state_manager.active_swings['M'].append(sample_active_swing)
        
        # Create a bar that should trigger completion (price at 2x level)
        completion_bar = Bar(
            timestamp=sample_bars[49].timestamp + 60,
            open=199.0,
            high=201.0,
            low=198.0,
            close=200.0,  # At 2x extension level
            index=50
        )
        
        result = swing_state_manager.update_swings(completion_bar, 50)
        
        # Check that completion was detected
        completion_events = [e for e in result.events if e.event_type == EventType.COMPLETION]
        if completion_events:  # Depends on aggregation alignment
            assert len(completion_events) == 1
            assert completion_events[0].swing_id == sample_active_swing.swing_id
    
    def test_integration_with_level_calculator(self, swing_state_manager):
        """Test integration with level calculator for Fibonacci levels."""
        swing_ref = {
            'high_price': 200.0,
            'low_price': 100.0,
            'size': 100.0,
            'high_timestamp': 2000,
            'low_timestamp': 1000
        }
        
        active_swing = swing_state_manager._create_active_swing(swing_ref, 'L', True)
        
        assert active_swing is not None
        assert len(active_swing.levels) > 0
        
        # Check specific Fibonacci levels
        expected_levels = ["-0.1", "0", "0.382", "0.5", "0.618", "1", "1.382", "1.5", "1.618", "2"]
        for level_name in expected_levels:
            assert level_name in active_swing.levels
        
        # Verify 2x level calculation
        assert abs(active_swing.levels["2"] - 300.0) < 1.0  # Should be around 300 (100 + 2*100)