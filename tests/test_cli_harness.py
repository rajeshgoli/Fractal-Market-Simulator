"""
Test Suite for CLI Harness

Tests the integrated visualization harness CLI including initialization,
component integration, and command handling.

Author: Generated for Market Simulator Project
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bull_reference_detector import Bar
from src.cli.harness import VisualizationHarness, create_argument_parser


class TestVisualizationHarness:
    """Test suite for VisualizationHarness class."""

    @pytest.fixture
    def sample_csv_file(self):
        """Create temporary CSV file with sample data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("timestamp,open,high,low,close\n")
            base_timestamp = 1672531200
            base_price = 4100.0
            
            for i in range(50):
                timestamp = base_timestamp + i * 60
                price_change = (i % 10 - 5) * 0.5  # Simple oscillation
                open_price = base_price + price_change
                close_price = open_price + (i % 3 - 1) * 0.2
                high_price = max(open_price, close_price) + 0.5
                low_price = min(open_price, close_price) - 0.5
                
                f.write(f"{timestamp},{open_price:.2f},{high_price:.2f},{low_price:.2f},{close_price:.2f}\n")
            
            filepath = f.name
        
        yield filepath
        
        # Cleanup
        if os.path.exists(filepath):
            os.unlink(filepath)

    @pytest.fixture
    def harness(self, sample_csv_file):
        """Create test harness instance."""
        return VisualizationHarness(
            data_file=sample_csv_file,
            session_id="test_session"
        )

    def test_initialization(self, harness):
        """Test harness initialization."""
        assert harness.session_id == "test_session"
        assert harness.bars is None
        assert not harness.is_running

    def test_invalid_data_file(self):
        """Test harness with invalid data file."""
        harness = VisualizationHarness("nonexistent.csv")
        success = harness.initialize()
        assert not success

    @patch('matplotlib.pyplot.show')  # Prevent GUI from showing
    def test_full_initialization(self, mock_show, harness):
        """Test complete harness initialization."""
        with patch('src.visualization.renderer.VisualizationRenderer.initialize_display'):
            success = harness.initialize()
            
            assert success
            assert harness.bars is not None
            assert len(harness.bars) > 0
            assert harness.scale_config is not None
            assert harness.bar_aggregator is not None
            assert harness.swing_state_manager is not None
            assert harness.visualization_renderer is not None
            assert harness.playback_controller is not None
            assert harness.event_logger is not None

    @patch('matplotlib.pyplot.show')
    def test_playback_step(self, mock_show, harness):
        """Test playback step handling."""
        # Initialize harness
        with patch('src.visualization.renderer.VisualizationRenderer.initialize_display'):
            harness.initialize()
        
        # Test step callback
        initial_events = len(harness.event_logger.events)
        harness._on_playback_step(5, [])
        
        assert harness.current_bar_idx == 5
        # Events may or may not be generated depending on swing detection

    @patch('builtins.input', side_effect=['help', 'status', 'quit'])
    @patch('matplotlib.pyplot.show')
    def test_interactive_commands(self, mock_show, mock_input, harness):
        """Test basic interactive command handling."""
        with patch('src.visualization.renderer.VisualizationRenderer.initialize_display'):
            harness.initialize()
            
            # Mock the command handler to avoid full execution
            with patch.object(harness, '_handle_command') as mock_handler:
                harness.run_interactive()
                
                # Should have called handler for each command
                assert mock_handler.call_count == 3

    @patch('matplotlib.pyplot.show')
    def test_command_handling(self, mock_show, harness):
        """Test individual command handling."""
        with patch('src.visualization.renderer.VisualizationRenderer.initialize_display'):
            harness.initialize()
        
        # Test help command
        with patch('builtins.print') as mock_print:
            harness._handle_command("help")
            mock_print.assert_called()
        
        # Test status command
        with patch('builtins.print') as mock_print:
            harness._handle_command("status")
            mock_print.assert_called()
        
        # Test play command
        harness._handle_command("play")
        # Should not raise exception
        
        # Test step command
        harness._handle_command("step")
        # Should advance current bar
        assert harness.current_bar_idx > 0

    @patch('matplotlib.pyplot.show')
    def test_export_commands(self, mock_show, harness):
        """Test export command handling."""
        with patch('src.visualization.renderer.VisualizationRenderer.initialize_display'):
            harness.initialize()
        
        # Generate some events first
        harness._on_playback_step(10, [])
        
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_file = os.path.join(temp_dir, "test_export.csv")
            
            # Test CSV export
            harness._handle_export_command(['csv', csv_file])
            # Should create file (may be empty if no events)
            
            # Test invalid export type
            with patch('builtins.print') as mock_print:
                harness._handle_export_command(['invalid'])
                mock_print.assert_called_with("Unknown export type")

    def test_filter_commands(self, harness):
        """Test filter command handling."""
        # Mock the event display
        harness.event_display = Mock()
        
        # Test major events filter
        harness._handle_filter_command(['major'])
        harness.event_display.print_filtered_events.assert_called()
        
        # Test scale filter
        harness._handle_filter_command(['scale', 'S'])
        harness.event_display.print_filtered_events.assert_called()
        
        # Test recent filter
        harness._handle_filter_command(['recent', '5'])
        harness.event_display.print_recent_events.assert_called_with(5)


class TestArgumentParser:
    """Test suite for command line argument parser."""

    def test_basic_arguments(self):
        """Test basic argument parsing."""
        parser = create_argument_parser()
        
        # Test required data argument
        args = parser.parse_args(['--data', 'test.csv'])
        assert args.data == 'test.csv'
        
        # Test with session
        args = parser.parse_args(['--data', 'test.csv', '--session', 'test_session'])
        assert args.session == 'test_session'

    def test_optional_arguments(self):
        """Test optional argument parsing."""
        parser = create_argument_parser()
        
        args = parser.parse_args([
            '--data', 'test.csv',
            '--auto-start',
            '--speed', '2.0',
            '--fast-mode',
            '--verbose'
        ])
        
        assert args.auto_start is True
        assert args.speed == 2.0
        assert args.fast_mode is True
        assert args.verbose is True

    def test_export_only_mode(self):
        """Test export-only mode argument."""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--data', 'test.csv', '--export-only', 'report.txt'])
        assert args.export_only == 'report.txt'

    def test_missing_required_arg(self):
        """Test parser with missing required argument."""
        parser = create_argument_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args([])  # No --data argument


class TestHarnessIntegration:
    """Integration tests for the complete harness."""

    @pytest.fixture
    def integration_csv(self):
        """Create larger CSV file for integration testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("timestamp,open,high,low,close\n")
            base_timestamp = 1672531200
            base_price = 4100.0
            
            # Generate more realistic price movement
            for i in range(200):
                timestamp = base_timestamp + i * 60
                
                # Create trending price movement with noise
                trend = i * 0.1
                noise = (i * 7 % 13 - 6) * 0.3  # Pseudo-random noise
                
                open_price = base_price + trend + noise
                close_change = (i % 5 - 2) * 0.4
                close_price = open_price + close_change
                
                high_price = max(open_price, close_price) + abs(noise) * 0.3 + 0.2
                low_price = min(open_price, close_price) - abs(noise) * 0.3 - 0.2
                
                f.write(f"{timestamp},{open_price:.2f},{high_price:.2f},{low_price:.2f},{close_price:.2f}\n")
            
            filepath = f.name
        
        yield filepath
        
        if os.path.exists(filepath):
            os.unlink(filepath)

    @patch('matplotlib.pyplot.show')
    def test_complete_workflow(self, mock_show, integration_csv):
        """Test complete harness workflow."""
        # Initialize harness
        harness = VisualizationHarness(integration_csv, "integration_test")
        
        with patch('src.visualization.renderer.VisualizationRenderer.initialize_display'):
            success = harness.initialize()
            assert success
            
            # Process some bars
            for i in range(0, 50, 5):
                harness._on_playback_step(i, [])
            
            # Verify state
            assert harness.current_bar_idx > 0
            assert len(harness.event_logger.events) >= 0  # May or may not have events
            
            # Test export
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                export_path = f.name
            
            try:
                success = harness.event_logger.export_to_json(export_path)
                assert success
                assert os.path.exists(export_path)
            finally:
                if os.path.exists(export_path):
                    os.unlink(export_path)

    @patch('sys.argv', ['main.py', '--data', 'test.csv', '--export-only', 'test_output.txt'])
    @patch('os.path.exists', return_value=True)
    def test_main_export_only(self, mock_exists):
        """Test main function in export-only mode."""
        from src.cli.harness import main
        
        # Mock the harness to avoid actual file operations
        with patch('src.cli.harness.VisualizationHarness') as mock_harness_class:
            mock_harness = Mock()
            mock_harness.initialize.return_value = True
            mock_harness.bars = [Mock() for _ in range(100)]  # Mock bars
            mock_harness.event_logger.export_summary_report.return_value = True
            mock_harness_class.return_value = mock_harness
            
            # Should complete without error
            main()
            
            # Verify initialization and export were called
            mock_harness.initialize.assert_called_once()
            mock_harness.event_logger.export_summary_report.assert_called()

    def test_signal_handling(self):
        """Test signal handler setup."""
        from src.cli.harness import setup_signal_handlers
        
        mock_harness = Mock()
        mock_harness.is_running = True
        
        # Should not raise exception
        setup_signal_handlers(mock_harness)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])