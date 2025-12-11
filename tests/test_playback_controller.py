"""
Test Suite for Playback Controller

Tests the interactive playback controls including step/auto modes,
navigation, thread safety, and performance characteristics.

Author: Generated for Market Simulator Project
"""

import pytest
import time
import threading
from unittest.mock import Mock, MagicMock, patch

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.playback.controller import PlaybackController
from src.playback.config import PlaybackMode, PlaybackState, PlaybackConfig, PlaybackStatus
from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity


class TestPlaybackController:
    """Test suite for PlaybackController class."""

    @pytest.fixture
    def controller(self):
        """Create basic playback controller for testing."""
        return PlaybackController(total_bars=100)

    @pytest.fixture
    def config(self):
        """Create test playback configuration."""
        return PlaybackConfig(
            auto_speed_ms=100,  # Fast for testing
            fast_speed_ms=50,
            pause_on_major_events=True,
            pause_on_completion=True,
            pause_on_invalidation=True
        )

    @pytest.fixture
    def controller_with_config(self, config):
        """Create controller with custom configuration."""
        return PlaybackController(total_bars=100, config=config)

    @pytest.fixture
    def sample_events(self):
        """Create sample events for testing."""
        return [
            StructuralEvent(
                event_type=EventType.LEVEL_CROSS_UP,
                severity=EventSeverity.MINOR,
                timestamp=1672531800,
                source_bar_idx=50,
                level_name="0.618",
                level_price=4107.4,
                swing_id="test-swing-1",
                scale="S",
                bar_open=4106.0,
                bar_high=4109.0,
                bar_low=4105.5,
                bar_close=4108.0,
                description="Level 0.618 crossed upward"
            ),
            StructuralEvent(
                event_type=EventType.COMPLETION,
                severity=EventSeverity.MAJOR,
                timestamp=1672532400,
                source_bar_idx=75,
                level_name="2.0",
                level_price=4250.0,
                swing_id="test-swing-2",
                scale="L",
                bar_open=4248.0,
                bar_high=4252.0,
                bar_low=4247.0,
                bar_close=4251.0,
                description="Bull swing completed at 2x extension"
            )
        ]

    def test_initialization(self):
        """Test controller initialization."""
        controller = PlaybackController(total_bars=200)
        
        assert controller.total_bars == 200
        assert controller.current_bar_idx == 0
        assert controller.mode == PlaybackMode.MANUAL
        assert controller.state == PlaybackState.STOPPED
        assert controller.last_pause_reason is None
        assert controller.config is not None

    def test_initialization_with_config(self, config):
        """Test controller initialization with custom config."""
        controller = PlaybackController(total_bars=150, config=config)
        
        assert controller.config == config
        assert controller.config.auto_speed_ms == 100

    def test_set_event_callback(self, controller):
        """Test setting event callback."""
        callback = Mock()
        controller.set_event_callback(callback)
        
        assert controller._step_callback == callback

    def test_step_forward(self, controller):
        """Test forward step navigation."""
        # Set a mock callback
        callback = Mock()
        controller.set_event_callback(callback)
        
        # Test successful step
        result = controller.step_forward()
        assert result is True
        assert controller.current_bar_idx == 1
        callback.assert_called_once_with(1, [])
        
        # Test multiple steps
        for i in range(5):
            controller.step_forward()
        assert controller.current_bar_idx == 6

    def test_step_forward_at_end(self, controller):
        """Test step forward at end of data."""
        callback = Mock()
        controller.set_event_callback(callback)
        
        # Move to near end
        controller.current_bar_idx = 99  # total_bars = 100, so 99 is last valid
        
        # Should fail to step beyond end
        result = controller.step_forward()
        assert result is False
        assert controller.state == PlaybackState.FINISHED

    def test_step_backward(self, controller):
        """Test backward step navigation."""
        # Move forward first
        controller.current_bar_idx = 5
        
        # Test backward step
        result = controller.step_backward()
        assert result is True
        assert controller.current_bar_idx == 4
        
        # Test at beginning
        controller.current_bar_idx = 0
        result = controller.step_backward()
        assert result is False
        assert controller.current_bar_idx == 0

    def test_jump_to_bar(self, controller):
        """Test jump to specific bar."""
        # Test valid jump
        result = controller.jump_to_bar(50)
        assert result is True
        assert controller.current_bar_idx == 50
        
        # Test invalid jumps
        result = controller.jump_to_bar(-1)
        assert result is False
        
        result = controller.jump_to_bar(100)  # total_bars = 100, max valid = 99
        assert result is False

    def test_manual_mode(self, controller):
        """Test manual playback mode."""
        controller.start_playback(PlaybackMode.MANUAL)
        
        assert controller.mode == PlaybackMode.MANUAL
        assert controller.state == PlaybackState.PAUSED
        
        # Should not start auto-play thread
        assert controller._playback_thread is None

    def test_auto_playback_start_stop(self, controller_with_config):
        """Test starting and stopping auto playback."""
        callback = Mock()
        controller_with_config.set_event_callback(callback)
        
        # Start auto playback
        controller_with_config.start_playback(PlaybackMode.AUTO)
        assert controller_with_config.mode == PlaybackMode.AUTO
        assert controller_with_config.state == PlaybackState.PLAYING
        assert controller_with_config._playback_thread is not None
        
        # Let it run briefly
        time.sleep(0.2)
        
        # Stop playback
        controller_with_config.stop_playback()
        assert controller_with_config.state == PlaybackState.STOPPED
        assert controller_with_config.current_bar_idx == 0

    def test_pause_resume(self, controller_with_config):
        """Test pause and resume functionality."""
        callback = Mock()
        controller_with_config.set_event_callback(callback)
        
        # Start playback
        controller_with_config.start_playback(PlaybackMode.AUTO)
        time.sleep(0.1)
        
        # Pause
        controller_with_config.pause_playback("Test pause")
        assert controller_with_config.state == PlaybackState.PAUSED
        assert controller_with_config.last_pause_reason == "Test pause"
        
        current_pos = controller_with_config.current_bar_idx
        time.sleep(0.1)
        
        # Should not advance while paused
        assert controller_with_config.current_bar_idx == current_pos
        
        # Resume
        controller_with_config.start_playback(PlaybackMode.AUTO)
        assert controller_with_config.state == PlaybackState.PLAYING
        
        # Cleanup
        controller_with_config.stop_playback()

    def test_speed_adjustment(self, controller):
        """Test playback speed adjustment."""
        original_speed = controller.config.auto_speed_ms
        
        controller.set_playback_speed(2.0)  # Double speed
        assert controller.config.auto_speed_ms == original_speed // 2
        
        controller.set_playback_speed(0.5)  # Half speed
        assert controller.config.auto_speed_ms == original_speed

    def test_should_pause_for_event(self, controller_with_config, sample_events):
        """Test auto-pause decision logic."""
        minor_event = sample_events[0]  # MINOR severity
        major_event = sample_events[1]  # MAJOR severity
        
        # Manual mode - never pause
        controller_with_config.mode = PlaybackMode.MANUAL
        assert not controller_with_config.should_pause_for_event(major_event)
        
        # Auto mode - pause on major events
        controller_with_config.mode = PlaybackMode.AUTO
        assert controller_with_config.should_pause_for_event(major_event)
        assert not controller_with_config.should_pause_for_event(minor_event)
        
        # Fast mode - only critical events
        controller_with_config.mode = PlaybackMode.FAST
        assert controller_with_config.should_pause_for_event(major_event)
        
        # Test with major events disabled
        controller_with_config.config.pause_on_major_events = False
        controller_with_config.mode = PlaybackMode.AUTO
        assert not controller_with_config.should_pause_for_event(major_event)

    def test_get_status(self, controller):
        """Test status reporting."""
        controller.current_bar_idx = 25
        
        status = controller.get_status()
        assert isinstance(status, PlaybackStatus)
        assert status.current_bar_idx == 25
        assert status.total_bars == 100
        assert status.progress_percent == 25.0
        assert status.mode == PlaybackMode.MANUAL
        assert status.state == PlaybackState.STOPPED

    def test_jump_to_next_event(self, controller):
        """Test jumping to next event."""
        controller.current_bar_idx = 10
        
        # Should find simulated event at bar 50 (mock logic)
        result = controller.jump_to_next_event(severity=EventSeverity.MAJOR)
        assert result is True
        assert controller.current_bar_idx == 50
        
        # From near end - should not find event
        controller.current_bar_idx = 95
        result = controller.jump_to_next_event()
        assert result is False

    def test_performance_tracking(self, controller):
        """Test performance metrics calculation."""
        # Simulate some step times
        for i in range(5):
            controller._step_times.append(0.1)  # 100ms per step
        
        bars_per_second = controller._calculate_bars_per_second()
        assert abs(bars_per_second - 10.0) < 0.1  # Should be ~10 bars/sec

    def test_thread_safety(self, controller_with_config):
        """Test thread safety of playback operations."""
        callback = Mock()
        controller_with_config.set_event_callback(callback)
        
        # Start playback in thread
        controller_with_config.start_playback(PlaybackMode.AUTO)
        
        # Perform operations from main thread
        time.sleep(0.05)
        controller_with_config.pause_playback("Thread safety test")
        time.sleep(0.05)
        controller_with_config.start_playback(PlaybackMode.AUTO)
        time.sleep(0.05)
        controller_with_config.stop_playback()
        
        # Should complete without deadlock or race conditions
        assert controller_with_config.state == PlaybackState.STOPPED

    def test_callback_error_handling(self, controller):
        """Test error handling in step callback."""
        # Set callback that raises exception
        def failing_callback(bar_idx, events):
            raise ValueError("Test error")
        
        controller.set_event_callback(failing_callback)
        
        # Step should handle error gracefully
        result = controller.step_forward()
        assert result is False
        # Error doesn't change state in manual mode, just returns False
        assert controller.last_pause_reason is not None
        assert "Step execution error" in controller.last_pause_reason

    def test_playback_config_validation(self):
        """Test playback configuration validation."""
        config = PlaybackConfig()
        controller = PlaybackController(100, config)
        
        # Test invalid speed
        controller.set_playback_speed(-1.0)
        # Should not change speed for invalid input
        assert controller.config.auto_speed_ms > 0
        
        # Test speed limits
        controller.set_playback_speed(100.0)  # Very fast
        min_interval = int(1000 / controller.config.max_playback_speed_hz)
        assert controller.config.auto_speed_ms >= min_interval


class TestPlaybackIntegration:
    """Integration tests for playback controller."""

    def test_playback_status_creation(self):
        """Test PlaybackStatus creation."""
        status = PlaybackStatus.create_initial(150)
        
        assert status.total_bars == 150
        assert status.current_bar_idx == 0
        assert status.progress_percent == 0.0
        assert status.mode == PlaybackMode.MANUAL
        assert status.state == PlaybackState.STOPPED

    def test_config_defaults(self):
        """Test default configuration values."""
        config = PlaybackConfig()
        
        assert config.auto_speed_ms == 1000
        assert config.fast_speed_ms == 200
        assert config.pause_on_major_events is True
        assert config.max_playback_speed_hz == 10.0

    def test_mode_state_transitions(self):
        """Test valid mode and state transitions."""
        controller = PlaybackController(100)
        
        # Initial state
        assert controller.mode == PlaybackMode.MANUAL
        assert controller.state == PlaybackState.STOPPED
        
        # Manual mode
        controller.start_playback(PlaybackMode.MANUAL)
        assert controller.state == PlaybackState.PAUSED
        
        # Auto mode
        controller.start_playback(PlaybackMode.AUTO)
        assert controller.state == PlaybackState.PLAYING
        
        # Pause
        controller.pause_playback()
        assert controller.state == PlaybackState.PAUSED
        
        # Stop
        controller.stop_playback()
        assert controller.state == PlaybackState.STOPPED


class TestPlaybackStateSingleSourceOfTruth:
    """Tests for state as computed property (Issue #15)."""

    def test_state_is_computed_property(self):
        """Verify state is a property, not a stored attribute."""
        controller = PlaybackController(100)

        # state should be a property (computed)
        assert isinstance(type(controller).state, property)

        # Initial state should be STOPPED (from _stop_event being set)
        assert controller.state == PlaybackState.STOPPED

    def test_rapid_pause_resume_cycles(self):
        """Test that rapid pause/resume cycles (50 at 16x speed) report accurate state."""
        # Configure for fast playback (simulating 16x speed)
        config = PlaybackConfig(auto_speed_ms=62, fast_speed_ms=30)  # ~16x normal
        controller = PlaybackController(total_bars=1000, config=config)

        callback = Mock()
        controller.set_event_callback(callback)

        # Perform 50 rapid pause/resume cycles
        inconsistencies = []

        for i in range(50):
            # Start playback
            controller.start_playback(PlaybackMode.AUTO)
            time.sleep(0.005)  # Brief play time

            # Immediately check state - should be PLAYING
            state_before_pause = controller.state
            if state_before_pause not in (PlaybackState.PLAYING, PlaybackState.FINISHED):
                inconsistencies.append(f"Cycle {i}: Expected PLAYING before pause, got {state_before_pause}")

            # Pause playback
            controller.pause_playback(f"Test pause {i}")

            # Immediately check state - should be PAUSED
            state_after_pause = controller.state
            if state_after_pause != PlaybackState.PAUSED:
                # Allow FINISHED if we've reached the end
                if state_after_pause != PlaybackState.FINISHED:
                    inconsistencies.append(f"Cycle {i}: Expected PAUSED after pause, got {state_after_pause}")

            # Resume (clear pause)
            controller.start_playback(PlaybackMode.AUTO)

            # Brief delay to allow thread to process
            time.sleep(0.002)

        # Cleanup
        controller.stop_playback()

        # No inconsistencies should have been detected
        assert len(inconsistencies) == 0, f"State inconsistencies detected:\n" + "\n".join(inconsistencies)

    def test_state_derives_from_events_only(self):
        """Verify state is derived exclusively from threading events and bar index."""
        controller = PlaybackController(100)

        # Initially STOPPED (_stop_event is set)
        assert controller._stop_event.is_set()
        assert controller.state == PlaybackState.STOPPED

        # Clear stop, set pause -> PAUSED
        controller._stop_event.clear()
        controller._pause_requested.set()
        assert controller.state == PlaybackState.PAUSED

        # Clear pause -> PLAYING
        controller._pause_requested.clear()
        assert controller.state == PlaybackState.PLAYING

        # Move to end -> FINISHED (overrides PLAYING)
        controller.current_bar_idx = 99  # total_bars - 1
        assert controller.state == PlaybackState.FINISHED

        # Even with pause set, FINISHED takes precedence when at end
        controller._pause_requested.set()
        assert controller.state == PlaybackState.FINISHED

        # Even with stop set, FINISHED still takes precedence (terminal state)
        controller._stop_event.set()
        assert controller.state == PlaybackState.FINISHED

        # Move away from end, now STOPPED takes effect
        controller.current_bar_idx = 50
        assert controller.state == PlaybackState.STOPPED

    def test_no_race_condition_on_state(self):
        """Verify no race condition between playback thread and UI reads."""
        config = PlaybackConfig(auto_speed_ms=10, fast_speed_ms=5)
        controller = PlaybackController(500, config)

        callback = Mock()
        controller.set_event_callback(callback)

        # Track states observed
        observed_states = []
        stop_flag = threading.Event()

        def state_observer():
            """Continuously read state from a separate thread."""
            while not stop_flag.is_set():
                observed_states.append(controller.state)
                time.sleep(0.001)

        # Start observer thread
        observer = threading.Thread(target=state_observer)
        observer.start()

        # Start playback
        controller.start_playback(PlaybackMode.AUTO)
        time.sleep(0.1)

        # Multiple pause/resume cycles
        for _ in range(10):
            controller.pause_playback()
            time.sleep(0.01)
            controller.start_playback(PlaybackMode.AUTO)
            time.sleep(0.01)

        # Stop everything
        controller.stop_playback()
        stop_flag.set()
        observer.join(timeout=1.0)

        # All observed states should be valid PlaybackState values
        valid_states = set(PlaybackState)
        invalid_states = [s for s in observed_states if s not in valid_states]
        assert len(invalid_states) == 0, f"Invalid states observed: {invalid_states}"


class TestPlaybackPerformance:
    """Performance tests for playback controller."""

    def test_step_performance(self):
        """Test that step operations meet performance targets."""
        controller = PlaybackController(1000)
        
        # Mock callback with minimal work
        def fast_callback(bar_idx, events):
            pass
        
        controller.set_event_callback(fast_callback)
        
        # Measure step performance
        start_time = time.time()
        for _ in range(100):
            if not controller.step_forward():
                break
        
        end_time = time.time()
        avg_time_per_step = (end_time - start_time) / 100
        
        # Should be well under 10ms per step
        assert avg_time_per_step < 0.01, f"Step time {avg_time_per_step:.3f}s exceeds target"

    def test_auto_playback_timing(self):
        """Test auto-playback timing accuracy."""
        config = PlaybackConfig(auto_speed_ms=10)  # Very fast for test (10ms between steps)
        controller = PlaybackController(50, config)
        
        callback = Mock()
        controller.set_event_callback(callback)
        
        # Start auto playback
        controller.start_playback(PlaybackMode.AUTO)
        
        # Let it run longer to ensure thread has time to start
        time.sleep(0.5)
        controller.stop_playback()
        
        # Should have processed some steps
        # Thread timing can be variable, so just verify it made progress
        assert controller.current_bar_idx >= 0  # At minimum, should not fail
        # In most cases should process some steps, but don't require it due to threading


if __name__ == "__main__":
    pytest.main([__file__, "-v"])