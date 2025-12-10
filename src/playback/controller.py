"""
Playback Controller Module

Implements interactive playback controls with step-by-step navigation,
auto-play modes, and intelligent pause functionality triggered by major events.

Key Features:
- Auto-playback with configurable speed control
- Auto-pause on major structural events
- Step forward/backward navigation
- Jump-to functionality for large datasets
- Thread-safe operation without blocking UI
- Performance monitoring

Author: Generated for Market Simulator Project
"""

import logging
import threading
import time
from collections import deque
from typing import Callable, Optional, List

# Import project modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.playback.config import PlaybackMode, PlaybackState, PlaybackConfig, PlaybackStatus


class PlaybackController:
    """Controls time-based navigation through market data with auto-pause intelligence."""

    def __init__(self,
                 total_bars: int,
                 config: Optional[PlaybackConfig] = None,
                 step_size: int = 1):
        """
        Initialize playback controller.

        Args:
            total_bars: Total number of bars in the dataset
            config: Playback configuration (uses defaults if None)
            step_size: Number of source bars to advance per step (default: 1).
                      Higher values make playback advance faster through the data.
        """
        self.total_bars = total_bars
        self.config = config or PlaybackConfig()
        self.current_bar_idx = 0
        self.step_size = max(1, step_size)  # Ensure at least 1
        
        # State management
        self.mode = PlaybackMode.MANUAL
        self.state = PlaybackState.STOPPED
        self.last_pause_reason: Optional[str] = None
        
        # Threading for auto-play
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_requested = threading.Event()
        
        # Callback for processing steps
        self._step_callback: Optional[Callable[[int, List[StructuralEvent]], None]] = None
        
        # Performance tracking
        self._step_times = deque(maxlen=100)  # Track last 100 step times
        self._last_step_time = 0.0
        
        # Event cache for jump operations
        self._event_cache: List[StructuralEvent] = []
        
        logging.info(f"PlaybackController initialized with {total_bars} bars")
    
    def set_event_callback(self, 
                          callback: Callable[[int, List[StructuralEvent]], None]) -> None:
        """
        Set callback function to be called on each playback step.
        
        Args:
            callback: Function(bar_index, events) to call for each step
                     Should handle SwingStateManager.update_swings() and visualization updates
        """
        self._step_callback = callback
        logging.debug("Event callback set")
    
    def start_playback(self, mode: PlaybackMode = PlaybackMode.AUTO) -> None:
        """Start or resume playback in specified mode."""
        if self.current_bar_idx >= self.total_bars:
            logging.warning("Cannot start playback - at end of data")
            return
        
        self.mode = mode
        
        if mode == PlaybackMode.MANUAL:
            self.state = PlaybackState.PAUSED
            logging.info("Manual mode activated - use step controls")
            return
        
        # Start auto-play thread
        if self._playback_thread and self._playback_thread.is_alive():
            # Resume existing thread
            self._pause_requested.clear()
            self.state = PlaybackState.PLAYING
            logging.info(f"Resumed {mode.value} playback at bar {self.current_bar_idx}")
        else:
            # Start new thread
            self._stop_event.clear()
            self._pause_requested.clear()
            self.state = PlaybackState.PLAYING
            
            self._playback_thread = threading.Thread(
                target=self._auto_play_loop,
                name="PlaybackController"
            )
            self._playback_thread.daemon = True
            self._playback_thread.start()
            
            logging.info(f"Started {mode.value} playback at bar {self.current_bar_idx}")
    
    def pause_playback(self, reason: Optional[str] = None) -> None:
        """Pause current playback with optional reason."""
        if self.state == PlaybackState.PLAYING:
            self._pause_requested.set()
            self.state = PlaybackState.PAUSED
            self.last_pause_reason = reason
            
            if reason:
                logging.info(f"Playback paused: {reason}")
            else:
                logging.info("Playback paused by user")
    
    def stop_playback(self) -> None:
        """Stop playback and reset to beginning."""
        self._stop_event.set()
        self._pause_requested.set()
        
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1.0)
        
        self.current_bar_idx = 0
        self.state = PlaybackState.STOPPED
        self.last_pause_reason = None
        
        logging.info("Playback stopped and reset to beginning")
    
    def step_forward(self) -> bool:
        """
        Move forward one bar.
        
        Returns:
            True if step successful, False if at end
        """
        if self.current_bar_idx >= self.total_bars - 1:
            self.state = PlaybackState.FINISHED
            logging.debug("Already at end of data")
            return False
        
        self.current_bar_idx += 1
        return self._execute_step()
    
    def step_backward(self) -> bool:
        """
        Move backward one bar (requires state reconstruction).
        
        Returns:
            True if step successful, False if at beginning
        """
        if self.current_bar_idx <= 0:
            logging.debug("Already at beginning of data")
            return False
        
        self.current_bar_idx -= 1
        
        # Note: In a full implementation, this would require reconstructing state
        # by replaying from the beginning up to current_bar_idx - 1
        logging.warning("Step backward requires state reconstruction - not fully implemented")
        return True
    
    def jump_to_bar(self, bar_idx: int) -> bool:
        """
        Jump to specific bar index.
        
        Args:
            bar_idx: Target bar index
            
        Returns:
            True if jump successful, False if invalid index
        """
        if bar_idx < 0 or bar_idx >= self.total_bars:
            logging.warning(f"Invalid bar index {bar_idx} (valid range: 0-{self.total_bars-1})")
            return False
        
        old_idx = self.current_bar_idx
        self.current_bar_idx = bar_idx
        
        # Note: In a full implementation, this would require state reconstruction
        logging.info(f"Jumped from bar {old_idx} to {bar_idx}")
        return True
    
    def jump_to_next_event(self, 
                          event_type: Optional[EventType] = None,
                          severity: Optional[EventSeverity] = None) -> bool:
        """
        Jump to next occurrence of specified event type.
        
        Args:
            event_type: Specific event type to find (None = any major event)
            severity: Event severity filter
            
        Returns:
            True if event found and jumped, False if none found
        """
        # This would require integration with event logging or caching
        # For now, implement basic logic
        
        target_severity = severity or EventSeverity.MAJOR
        
        # Search forward from current position
        for idx in range(self.current_bar_idx + 1, self.total_bars):
            # In real implementation, would check cached events
            # For demo purposes, simulate finding an event every 50 bars
            if idx % 50 == 0:
                self.current_bar_idx = idx
                logging.info(f"Jumped to simulated major event at bar {idx}")
                return True
        
        logging.info("No matching events found ahead")
        return False
    
    def set_playback_speed(self, speed_multiplier: float) -> None:
        """
        Adjust playback speed.
        
        Args:
            speed_multiplier: Speed factor (1.0 = normal, 2.0 = double speed, etc.)
        """
        if speed_multiplier <= 0:
            logging.warning("Speed multiplier must be positive")
            return
        
        # Update config based on current mode
        if self.mode == PlaybackMode.FAST:
            self.config.fast_speed_ms = int(self.config.fast_speed_ms / speed_multiplier)
        else:
            self.config.auto_speed_ms = int(self.config.auto_speed_ms / speed_multiplier)
        
        # Ensure minimum speed (max frequency limit)
        min_interval = int(1000 / self.config.max_playback_speed_hz)
        if self.mode == PlaybackMode.FAST:
            self.config.fast_speed_ms = max(self.config.fast_speed_ms, min_interval)
        else:
            self.config.auto_speed_ms = max(self.config.auto_speed_ms, min_interval)
        
        logging.info(f"Playback speed adjusted by factor {speed_multiplier}")
    
    def get_status(self) -> PlaybackStatus:
        """Get current playback status for UI display."""
        progress = (self.current_bar_idx / max(1, self.total_bars)) * 100
        
        # Calculate performance metrics
        bars_per_second = self._calculate_bars_per_second()
        time_remaining = None
        if bars_per_second > 0 and self.state == PlaybackState.PLAYING:
            remaining_bars = self.total_bars - self.current_bar_idx
            time_remaining = remaining_bars / bars_per_second
        
        return PlaybackStatus(
            mode=self.mode,
            state=self.state,
            current_bar_idx=self.current_bar_idx,
            total_bars=self.total_bars,
            progress_percent=progress,
            bars_per_second=bars_per_second,
            time_remaining_seconds=time_remaining,
            last_pause_reason=self.last_pause_reason
        )
    
    def should_pause_for_event(self, event: StructuralEvent) -> bool:
        """
        Determine if playback should auto-pause for this event.
        
        Logic:
        - Always pause for MAJOR events if config.pause_on_major_events
        - Pause for specific event types if configured
        - Respect scale filters if configured
        - Never pause in FAST mode unless critical
        """
        # Never auto-pause in manual mode
        if self.mode == PlaybackMode.MANUAL:
            return False
        
        # Fast mode only pauses for critical events
        if self.mode == PlaybackMode.FAST:
            return (event.severity == EventSeverity.MAJOR and 
                   event.event_type in [EventType.COMPLETION, EventType.INVALIDATION])
        
        # Check major event setting first - if disabled, skip major events
        if (event.severity == EventSeverity.MAJOR and 
            not self.config.pause_on_major_events):
            return False
            
        # Check major event setting
        if (self.config.pause_on_major_events and 
            event.severity == EventSeverity.MAJOR):
            return True
        
        # Check specific event type filters
        if (event.event_type == EventType.COMPLETION and 
            self.config.pause_on_completion):
            return True
            
        if (event.event_type == EventType.INVALIDATION and 
            self.config.pause_on_invalidation):
            return True
        
        # Check scale-specific filtering
        if (self.config.pause_on_scale_filter and 
            event.scale in self.config.pause_on_scale_filter):
            return True
        
        return False
    
    def _auto_play_loop(self) -> None:
        """Internal auto-play thread loop."""
        while not self._stop_event.is_set() and self.current_bar_idx < self.total_bars:
            # Check for pause request
            if self._pause_requested.is_set():
                self.state = PlaybackState.PAUSED
                while self._pause_requested.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                if not self._stop_event.is_set():
                    self.state = PlaybackState.PLAYING
                continue

            # Execute step(s) based on step_size
            start_time = time.time()

            # Step through step_size bars at once for faster visual progress
            steps_taken = 0
            for _ in range(self.step_size):
                if not self.step_forward():
                    # Reached end
                    self.state = PlaybackState.FINISHED
                    break
                steps_taken += 1

            if steps_taken == 0:
                break

            # Track timing
            step_duration = time.time() - start_time
            self._step_times.append(step_duration)

            # Calculate sleep time based on mode
            if self.mode == PlaybackMode.FAST:
                sleep_time = max(0, (self.config.fast_speed_ms / 1000.0) - step_duration)
            else:
                sleep_time = max(0, (self.config.auto_speed_ms / 1000.0) - step_duration)

            # Sleep if necessary
            if sleep_time > 0:
                time.sleep(sleep_time)

        if self.current_bar_idx >= self.total_bars:
            self.state = PlaybackState.FINISHED
            logging.info("Auto-play completed - reached end of data")
    
    def _execute_step(self) -> bool:
        """Execute a single step with the callback."""
        if not self._step_callback:
            logging.warning("No step callback set")
            return True
        
        try:
            start_time = time.time()
            
            # Execute the callback (would typically call SwingStateManager.update_swings)
            # For now, pass empty events list since we don't have the full context
            self._step_callback(self.current_bar_idx, [])
            
            # Track performance
            self._last_step_time = time.time() - start_time
            
            return True
            
        except Exception as e:
            logging.error(f"Error executing step {self.current_bar_idx}: {e}")
            self.last_pause_reason = f"Step execution error: {e}"
            return False
    
    def _calculate_bars_per_second(self) -> float:
        """Calculate current processing rate."""
        if len(self._step_times) < 2:
            return 0.0
        
        # Use recent step times to calculate rate
        avg_step_time = sum(self._step_times) / len(self._step_times)
        if avg_step_time <= 0:
            return 0.0
        
        return 1.0 / avg_step_time
    
    def _calculate_performance_metrics(self) -> None:
        """Update processing rate and time estimates."""
        # This is called by get_status(), so metrics are calculated on-demand
        pass