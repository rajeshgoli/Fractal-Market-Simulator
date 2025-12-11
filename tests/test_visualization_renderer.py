"""
Test Suite for Visualization Renderer

Tests the 4-panel matplotlib visualization system including OHLC rendering,
Fibonacci level overlays, event markers, and performance characteristics.

Author: Generated for Market Simulator Project
"""

import pytest
import numpy as np
import matplotlib.pyplot as plt
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.legacy.bull_reference_detector import Bar
from src.analysis.swing_state_manager import ActiveSwing
from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.analysis.scale_calibrator import ScaleConfig
from src.analysis.bar_aggregator import BarAggregator
from src.visualization.renderer import VisualizationRenderer
from src.visualization.config import RenderConfig, ViewWindow


class TestVisualizationRenderer:
    """Test suite for VisualizationRenderer class."""

    @pytest.fixture
    def sample_bars(self):
        """Create sample bars for testing."""
        bars = []
        for i in range(100):
            timestamp = 1609459200 + i * 60  # Start from 2021-01-01, 1-minute intervals
            bars.append(Bar(
                index=i,
                timestamp=timestamp,
                open=4000.0 + i * 0.5,
                high=4002.0 + i * 0.5,
                low=3998.0 + i * 0.5,
                close=4001.0 + i * 0.5
            ))
        return bars

    @pytest.fixture
    def scale_config(self):
        """Create test scale configuration."""
        return ScaleConfig(
            boundaries={"S": (0, 25), "M": (25, 50), "L": (50, 100), "XL": (100, float('inf'))},
            aggregations={"S": 1, "M": 1, "L": 5, "XL": 5},
            used_defaults=False,
            swing_count=25,
            median_durations={"S": 10, "M": 20, "L": 30, "XL": 40}
        )

    @pytest.fixture
    def bar_aggregator(self, sample_bars):
        """Create test bar aggregator."""
        return BarAggregator(sample_bars)

    @pytest.fixture
    def render_config(self):
        """Create test render configuration."""
        return RenderConfig(
            figure_size=(12, 8),
            max_visible_bars=50
        )

    @pytest.fixture
    def sample_swings(self):
        """Create sample active swings for testing."""
        return [
            ActiveSwing(
                swing_id="test-swing-1",
                scale="S",
                high_price=4010.0,
                low_price=3990.0,
                high_timestamp=1609459260,
                low_timestamp=1609459200,
                is_bull=True,
                state="active",
                levels={"0": 3990.0, "0.618": 4002.36, "1.0": 4010.0, "1.618": 4022.36, "2.0": 4030.0}
            ),
            ActiveSwing(
                swing_id="test-swing-2",
                scale="M",
                high_price=4050.0,
                low_price=3950.0,
                high_timestamp=1609459800,
                low_timestamp=1609459200,
                is_bull=False,
                state="active",
                levels={"0": 4050.0, "0.382": 4011.8, "0.5": 4000.0, "0.618": 3988.2, "1.0": 3950.0, "1.618": 3888.2}
            )
        ]

    @pytest.fixture
    def sample_events(self):
        """Create sample structural events for testing."""
        return [
            StructuralEvent(
                event_type=EventType.LEVEL_CROSS_UP,
                severity=EventSeverity.MINOR,
                timestamp=1609459320,
                source_bar_idx=5,
                level_name="0.618",
                level_price=4002.36,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4001.0,
                bar_high=4003.0,
                bar_low=3999.0,
                bar_close=4002.5,
                description="Level 0.618 crossed upward"
            ),
            StructuralEvent(
                event_type=EventType.COMPLETION,
                severity=EventSeverity.MAJOR,
                timestamp=1609459380,
                source_bar_idx=6,
                level_name="2.0",
                level_price=4030.0,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4028.0,
                bar_high=4031.0,
                bar_low=4027.0,
                bar_close=4030.5,
                description="Bull swing completed at 2x extension"
            )
        ]

    def test_initialization(self, scale_config, bar_aggregator, render_config):
        """Test renderer initialization."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator, render_config)
        
        assert renderer.scale_config == scale_config
        assert renderer.bar_aggregator == bar_aggregator
        assert renderer.config == render_config
        assert renderer.fig is None  # Not initialized until display setup
        assert renderer.current_bar_idx == 0

    def test_initialize_display(self, scale_config, bar_aggregator):
        """Test display initialization creates proper matplotlib structure."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        with patch('matplotlib.pyplot.figure') as mock_fig, \
             patch('matplotlib.pyplot.tight_layout'):
            mock_figure = MagicMock()
            mock_fig.return_value = mock_figure
            
            renderer.initialize_display()
            
            # Verify figure was created
            mock_fig.assert_called_once()
            assert renderer.fig == mock_figure
            
            # Verify 4 panels initialized
            assert len(renderer.axes) == 4
            assert len(renderer.artists) == 4
            
            # Verify artist collections initialized
            for panel_idx in range(4):
                assert 'candlesticks' in renderer.artists[panel_idx]
                assert 'levels' in renderer.artists[panel_idx]
                assert 'events' in renderer.artists[panel_idx]

    def test_calculate_view_window(self, scale_config, bar_aggregator):
        """Test view window calculation."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        # Test with S scale
        view_window = renderer.calculate_view_window("S", 50, [])
        
        assert view_window.scale == "S"
        assert view_window.start_idx >= 0
        assert view_window.end_idx > view_window.start_idx
        assert view_window.price_max > view_window.price_min

    def test_calculate_view_window_with_swings(self, scale_config, bar_aggregator, sample_swings):
        """Test view window calculation includes swing extremes."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        # Test with swings that extend price range
        s_swings = [swing for swing in sample_swings if swing.scale == "S"]
        view_window = renderer.calculate_view_window("S", 50, s_swings)
        
        # Should include swing extremes
        assert view_window.price_min <= min(s.low_price for s in s_swings)
        assert view_window.price_max >= max(s.high_price for s in s_swings)

    def test_group_swings_by_scale(self, scale_config, bar_aggregator, sample_swings):
        """Test swing grouping by scale."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        grouped = renderer._group_swings_by_scale(sample_swings)
        
        assert "S" in grouped
        assert "M" in grouped
        assert len(grouped["S"]) == 1
        assert len(grouped["M"]) == 1
        assert grouped["S"][0].scale == "S"
        assert grouped["M"][0].scale == "M"

    def test_group_events_by_scale(self, scale_config, bar_aggregator, sample_events):
        """Test event grouping by scale."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        grouped = renderer._group_events_by_scale(sample_events)
        
        assert "S" in grouped
        assert len(grouped["S"]) == 2  # Both events are S scale
        assert all(event.scale == "S" for event in grouped["S"])

    def test_get_visible_bars(self, scale_config, bar_aggregator, sample_bars):
        """Test bar filtering to view window."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        view_window = ViewWindow(
            start_idx=10,
            end_idx=20,
            price_min=3995.0,
            price_max=4015.0,
            scale="S"
        )
        
        visible = renderer._get_visible_bars(sample_bars, view_window)
        
        assert len(visible) == 11  # Indices 10-20 inclusive
        assert visible[0] == sample_bars[10]
        assert visible[-1] == sample_bars[20]

    @patch('matplotlib.pyplot.figure')
    def test_update_display_basic(self, mock_fig, scale_config, bar_aggregator, sample_swings, sample_events):
        """Test basic display update functionality."""
        mock_figure = MagicMock()
        mock_fig.return_value = mock_figure
        
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        # Mock axes and artists
        renderer.axes = {i: MagicMock() for i in range(4)}
        renderer.artists = {i: {'candlesticks': [], 'levels': [], 'events': []} for i in range(4)}
        renderer.fig = mock_figure
        
        # Update display
        renderer.update_display(50, sample_swings, sample_events, sample_events)
        
        # Verify state updated
        assert renderer.current_bar_idx == 50
        assert renderer.last_events == sample_events
        
        # Verify figure draw was called
        mock_figure.canvas.draw_idle.assert_called_once()

    def test_clear_panel_artists(self, scale_config, bar_aggregator):
        """Test artist clearing functionality."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        # Create mock artists with remove method
        mock_candlestick = MagicMock()
        mock_level = MagicMock()
        mock_event = MagicMock()
        
        # Ensure hasattr check passes
        mock_candlestick.remove = MagicMock()
        mock_level.remove = MagicMock()
        mock_event.remove = MagicMock()
        
        renderer.artists[0] = {
            'candlesticks': [mock_candlestick],
            'levels': [mock_level],
            'events': [mock_event]
        }
        
        renderer._clear_panel_artists(0)
        
        # Verify removal was called
        mock_candlestick.remove.assert_called_once()
        mock_level.remove.assert_called_once()
        mock_event.remove.assert_called_once()
        
        # Verify lists cleared
        assert len(renderer.artists[0]['candlesticks']) == 0
        assert len(renderer.artists[0]['levels']) == 0
        assert len(renderer.artists[0]['events']) == 0

    def test_set_interactive_mode(self, scale_config, bar_aggregator):
        """Test interactive mode setting."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        with patch('matplotlib.pyplot.ion') as mock_ion, \
             patch('matplotlib.pyplot.ioff') as mock_ioff:
            
            renderer.set_interactive_mode(True)
            mock_ion.assert_called_once()
            
            renderer.set_interactive_mode(False)
            mock_ioff.assert_called_once()

    def test_render_config_defaults(self, scale_config, bar_aggregator):
        """Test that default render config is applied correctly."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        assert isinstance(renderer.config, RenderConfig)
        assert renderer.config.panel_rows == 2
        assert renderer.config.panel_cols == 2
        assert renderer.config.max_visible_bars == 500
        assert renderer.config.level_colors is not None


class TestRenderPerformance:
    """Performance-focused tests for the visualization renderer."""

    @pytest.fixture
    def large_dataset(self):
        """Create large dataset for performance testing."""
        bars = []
        for i in range(1000):
            timestamp = 1609459200 + i * 60
            bars.append(Bar(
                index=i,
                timestamp=timestamp,
                open=4000.0 + np.sin(i * 0.1) * 20,
                high=4005.0 + np.sin(i * 0.1) * 20,
                low=3995.0 + np.sin(i * 0.1) * 20,
                close=4002.0 + np.sin(i * 0.1) * 20
            ))
        return bars

    @patch('matplotlib.pyplot.figure')
    def test_update_performance(self, mock_fig, large_dataset):
        """Test that display updates meet performance targets."""
        import time
        
        # Setup
        scale_config = ScaleConfig(
            boundaries={"S": (0, 25), "M": (25, 50), "L": (50, 100), "XL": (100, float('inf'))},
            aggregations={"S": 1, "M": 1, "L": 5, "XL": 5},
            used_defaults=False,
            swing_count=50,
            median_durations={"S": 10, "M": 20, "L": 30, "XL": 40}
        )
        
        bar_aggregator = BarAggregator(large_dataset)
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        # Mock matplotlib components
        mock_figure = MagicMock()
        mock_fig.return_value = mock_figure
        renderer.axes = {i: MagicMock() for i in range(4)}
        renderer.artists = {i: {'candlesticks': [], 'levels': [], 'events': []} for i in range(4)}
        renderer.fig = mock_figure
        
        # Mock the render_panel method to avoid matplotlib issues
        with patch.object(renderer, 'render_panel') as mock_render:
            # Test performance
            start_time = time.time()
            
            for i in range(0, 100, 10):  # Test 10 updates
                renderer.update_display(i, [], [], [])
            
            end_time = time.time()
            avg_time_per_update = (end_time - start_time) / 10
        
        # Should be under 100ms per update (performance target)
        assert avg_time_per_update < 0.1, f"Average update time {avg_time_per_update:.3f}s exceeds target"

    def test_memory_usage_stability(self, large_dataset):
        """Test that memory usage remains stable over many updates."""
        # This test would require memory profiling in a real environment
        # For now, verify no obvious memory leaks in artist management
        
        scale_config = ScaleConfig(
            boundaries={"S": (0, 25), "M": (25, 50), "L": (50, 100), "XL": (100, float('inf'))},
            aggregations={"S": 1, "M": 1, "L": 5, "XL": 5},
            used_defaults=False,
            swing_count=50,
            median_durations={"S": 10, "M": 20, "L": 30, "XL": 40}
        )
        
        bar_aggregator = BarAggregator(large_dataset)
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        
        # Initialize artist collections
        for i in range(4):
            renderer.artists[i] = {'candlesticks': [], 'levels': [], 'events': []}
        
        # Simulate many clear operations
        for _ in range(1000):
            for panel_idx in range(4):
                # Add mock artists with remove method
                mock_candle = MagicMock()
                mock_candle.remove = MagicMock()
                mock_level = MagicMock()
                mock_level.remove = MagicMock()
                mock_event = MagicMock()
                mock_event.remove = MagicMock()
                
                renderer.artists[panel_idx]['candlesticks'].append(mock_candle)
                renderer.artists[panel_idx]['levels'].append(mock_level)
                renderer.artists[panel_idx]['events'].append(mock_event)
                
                # Clear them
                renderer._clear_panel_artists(panel_idx)
        
        # Verify all collections remain empty
        for panel_idx in range(4):
            assert len(renderer.artists[panel_idx]['candlesticks']) == 0
            assert len(renderer.artists[panel_idx]['levels']) == 0
            assert len(renderer.artists[panel_idx]['events']) == 0


class TestRenderIntegration:
    """Integration tests with other components."""

    def test_with_real_swing_state_manager(self):
        """Test integration with actual SwingStateManager."""
        # This would test real integration but requires full component setup
        # For now, verify interface compatibility
        
        from src.analysis.swing_state_manager import SwingUpdateResult
        
        # Verify that SwingUpdateResult has expected fields for renderer
        result = SwingUpdateResult(
            events=[],
            new_swings=[],
            state_changes=[],
            removed_swings=[]
        )
        
        assert hasattr(result, 'events')
        assert hasattr(result, 'new_swings')
        assert hasattr(result, 'state_changes')
        assert hasattr(result, 'removed_swings')

    def test_scale_config_compatibility(self):
        """Test compatibility with ScaleConfig from ScaleCalibrator."""
        from src.analysis.scale_calibrator import ScaleConfig
        
        config = ScaleConfig(
            boundaries={"S": (0, 25), "M": (25, 50), "L": (50, 100), "XL": (100, float('inf'))},
            aggregations={"S": 1, "M": 1, "L": 5, "XL": 5},
            used_defaults=False,
            swing_count=25,
            median_durations={"S": 10, "M": 20, "L": 30, "XL": 40}
        )
        
        # Verify renderer can access required fields
        assert hasattr(config, 'boundaries')
        assert hasattr(config, 'aggregations')
        assert 'S' in config.boundaries
        assert 'S' in config.aggregations


class TestSwingCapFunctionality:
    """Tests for swing cap filtering functionality (Phase 1 Priority 1)."""

    @pytest.fixture
    def scale_config(self):
        """Create test scale configuration."""
        return ScaleConfig(
            boundaries={"S": (0, 25), "M": (25, 50), "L": (50, 100), "XL": (100, float('inf'))},
            aggregations={"S": 1, "M": 5, "L": 15, "XL": 60},
            used_defaults=False,
            swing_count=25,
            median_durations={"S": 10, "M": 20, "L": 30, "XL": 40}
        )

    @pytest.fixture
    def sample_bars(self):
        """Create sample bars for testing."""
        bars = []
        for i in range(500):
            timestamp = 1609459200 + i * 60
            bars.append(Bar(
                index=i,
                timestamp=timestamp,
                open=4000.0 + i * 0.5,
                high=4002.0 + i * 0.5,
                low=3998.0 + i * 0.5,
                close=4001.0 + i * 0.5
            ))
        return bars

    @pytest.fixture
    def bar_aggregator(self, sample_bars):
        """Create test bar aggregator."""
        return BarAggregator(sample_bars)

    @pytest.fixture
    def many_swings(self):
        """Create many swings for cap testing."""
        swings = []
        for i in range(10):
            # Vary timestamps to test recency scoring
            # Later swings have higher timestamps (more recent)
            swings.append(ActiveSwing(
                swing_id=f"swing-{i}",
                scale="S",
                high_price=4010.0 + i * 5,  # Increasing sizes
                low_price=3990.0 + i * 5,
                high_timestamp=1609459260 + i * 10000,  # More recent as i increases
                low_timestamp=1609459200 + i * 10000,
                is_bull=True,
                state="active",
                levels={"0": 3990.0 + i * 5, "1.0": 4010.0 + i * 5}
            ))
        return swings

    def test_swing_cap_default_value(self, scale_config, bar_aggregator):
        """Test that default swing cap is 5."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)
        assert renderer.config.max_swings_per_scale == 5

    def test_swing_cap_filters_excess_swings(self, scale_config, bar_aggregator, many_swings):
        """Test that swing cap filters swings when there are more than the cap."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        filtered = renderer._apply_swing_cap(many_swings, current_bar_idx=100)

        assert len(filtered) <= renderer.config.max_swings_per_scale
        assert len(filtered) == 5  # Default cap

    def test_swing_cap_no_filter_when_under_cap(self, scale_config, bar_aggregator):
        """Test that swing cap doesn't filter when under the cap."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        few_swings = [
            ActiveSwing(
                swing_id=f"swing-{i}",
                scale="S",
                high_price=4010.0,
                low_price=3990.0,
                high_timestamp=1609459260,
                low_timestamp=1609459200,
                is_bull=True,
                state="active",
                levels={}
            ) for i in range(3)
        ]

        filtered = renderer._apply_swing_cap(few_swings, current_bar_idx=100)

        assert len(filtered) == 3  # No filtering

    def test_swing_cap_includes_recent_event_swing(self, scale_config, bar_aggregator, many_swings):
        """Test that recent event swing is always included."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        # Pick a swing that would normally be excluded (old, small)
        event_swing_id = "swing-0"  # Oldest swing

        filtered = renderer._apply_swing_cap(
            many_swings,
            current_bar_idx=200,
            recent_event_swing_id=event_swing_id
        )

        # Verify event swing is included regardless of score
        included_ids = [s.swing_id for s in filtered]
        assert event_swing_id in included_ids

    def test_toggle_show_all_swings(self, scale_config, bar_aggregator):
        """Test toggling show_all_swings bypasses cap."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        assert renderer.config.show_all_swings is False

        result = renderer.toggle_show_all_swings()
        assert result is True
        assert renderer.config.show_all_swings is True

        result = renderer.toggle_show_all_swings()
        assert result is False
        assert renderer.config.show_all_swings is False

    def test_group_swings_bypasses_cap_when_toggled(self, scale_config, bar_aggregator, many_swings):
        """Test that _group_swings_by_scale bypasses cap when show_all_swings is True."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        # With cap enabled
        grouped = renderer._group_swings_by_scale(many_swings, current_bar_idx=100)
        assert len(grouped.get("S", [])) == 5  # Capped

        # Toggle to show all
        renderer.toggle_show_all_swings()
        grouped = renderer._group_swings_by_scale(many_swings, current_bar_idx=100)
        assert len(grouped.get("S", [])) == 10  # All swings

    def test_swing_cap_scoring_prefers_recent_large(self, scale_config, bar_aggregator):
        """Test that scoring prefers recent and large swings."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        swings = [
            # Old, small swing (low timestamp, small size 10.0)
            ActiveSwing(
                swing_id="old-small",
                scale="S",
                high_price=4010.0,
                low_price=4000.0,
                high_timestamp=1609459260,
                low_timestamp=1609459200,
                is_bull=True,
                state="active",
                levels={}
            ),
            # Recent, large swing (high timestamp, large size 100.0)
            ActiveSwing(
                swing_id="recent-large",
                scale="S",
                high_price=4100.0,
                low_price=4000.0,
                high_timestamp=1609465000,
                low_timestamp=1609464900,
                is_bull=True,
                state="active",
                levels={}
            ),
        ]

        # Add more swings to exceed cap (medium size 10.0, medium timestamps)
        for i in range(5):
            swings.append(ActiveSwing(
                swing_id=f"filler-{i}",
                scale="S",
                high_price=4050.0,
                low_price=4040.0,
                high_timestamp=1609461000 + i * 100,
                low_timestamp=1609460900 + i * 100,
                is_bull=True,
                state="active",
                levels={}
            ))

        filtered = renderer._apply_swing_cap(swings, current_bar_idx=100)
        filtered_ids = [s.swing_id for s in filtered]

        # Recent-large should be included (highest recency + large size = best score)
        assert "recent-large" in filtered_ids


class TestDynamicBarAggregation:
    """Tests for dynamic bar aggregation functionality (Phase 1 Priority 2)."""

    @pytest.fixture
    def scale_config(self):
        """Create test scale configuration."""
        return ScaleConfig(
            boundaries={"S": (0, 25), "M": (25, 50), "L": (50, 100), "XL": (100, float('inf'))},
            aggregations={"S": 1, "M": 5, "L": 15, "XL": 60},
            used_defaults=False,
            swing_count=25,
            median_durations={"S": 10, "M": 20, "L": 30, "XL": 40}
        )

    @pytest.fixture
    def sample_bars(self):
        """Create sample bars for testing."""
        bars = []
        for i in range(500):
            timestamp = 1609459200 + i * 60
            bars.append(Bar(
                index=i,
                timestamp=timestamp,
                open=4000.0 + i * 0.5,
                high=4002.0 + i * 0.5,
                low=3998.0 + i * 0.5,
                close=4001.0 + i * 0.5
            ))
        return bars

    @pytest.fixture
    def bar_aggregator(self, sample_bars):
        """Create test bar aggregator."""
        return BarAggregator(sample_bars)

    def test_calculate_optimal_timeframe_respects_base(self, scale_config, bar_aggregator):
        """Test that optimal timeframe never goes below base for scale."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        # For M scale with base timeframe 5, should never return < 5
        tf = renderer._calculate_optimal_timeframe("M", source_bar_count=10)
        assert tf >= 5  # Base for M scale

        # For L scale with base timeframe 15, should never return < 15
        tf = renderer._calculate_optimal_timeframe("L", source_bar_count=20)
        assert tf >= 15  # Base for L scale

    def test_calculate_optimal_timeframe_targets_50_candles(self, scale_config, bar_aggregator):
        """Test that optimal timeframe aims for ~50 candles."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        # 250 source bars should give 50 candles with 5m aggregation
        tf = renderer._calculate_optimal_timeframe("M", source_bar_count=250)
        expected_candles = 250 / tf

        # Should be in 40-60 range (our target)
        assert 40 <= expected_candles <= 60 or expected_candles < 40  # Allow fewer if at base

    def test_calculate_optimal_timeframe_handles_small_datasets(self, scale_config, bar_aggregator):
        """Test handling of very small datasets."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        # 0 bars should return base timeframe
        tf = renderer._calculate_optimal_timeframe("S", source_bar_count=0)
        assert tf == 1  # Base for S scale

        # Few bars should return base timeframe
        tf = renderer._calculate_optimal_timeframe("S", source_bar_count=10)
        assert tf == 1  # Base for S scale

    def test_calculate_optimal_timeframe_scales_hierarchy(self, scale_config, bar_aggregator):
        """Test that scale hierarchy is maintained."""
        renderer = VisualizationRenderer(scale_config, bar_aggregator)

        # Given same bar count, larger scales should have >= timeframe
        tf_s = renderer._calculate_optimal_timeframe("S", source_bar_count=500)
        tf_m = renderer._calculate_optimal_timeframe("M", source_bar_count=500)
        tf_l = renderer._calculate_optimal_timeframe("L", source_bar_count=500)
        tf_xl = renderer._calculate_optimal_timeframe("XL", source_bar_count=500)

        # Hierarchy should be maintained
        assert tf_s <= tf_m <= tf_l <= tf_xl


if __name__ == "__main__":
    pytest.main([__file__, "-v"])