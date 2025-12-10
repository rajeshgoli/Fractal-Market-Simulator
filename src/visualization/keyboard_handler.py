"""
Keyboard Handler Module

Provides keyboard event handling for the matplotlib visualization window,
enabling pause/resume, stepping, and speed control directly from the UI.

Keyboard Shortcuts:
- SPACE: Toggle pause/resume
- RIGHT ARROW: Step forward one bar
- UP ARROW: Increase playback speed
- DOWN ARROW: Decrease playback speed
- R: Reset to beginning

Author: Generated for Market Simulator Project
"""

import logging
from typing import Callable, Optional, Dict, Any
from matplotlib.figure import Figure
from matplotlib.backend_bases import KeyEvent

from src.playback.controller import PlaybackController
from src.playback.config import PlaybackMode, PlaybackState


class KeyboardHandler:
    """
    Handles keyboard events from the matplotlib figure window.

    Provides UI-integrated playback controls without requiring CLI interaction.
    All keyboard events are processed on the main thread (matplotlib's event loop).
    """

    def __init__(self,
                 playback_controller: PlaybackController,
                 on_action_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        """
        Initialize keyboard handler.

        Args:
            playback_controller: Controller for playback state management
            on_action_callback: Optional callback(action_name, details) for status updates
        """
        self.playback_controller = playback_controller
        self.on_action_callback = on_action_callback
        self._cid = None  # Connection ID for matplotlib event
        self._fig = None

        # Speed tracking - starts at 1x (doubles with UP, halves with DOWN, min 0.25x)
        self._current_speed = 1.0

        logging.info("KeyboardHandler initialized")

    def connect(self, fig: Figure) -> None:
        """
        Connect keyboard event handler to matplotlib figure.

        Args:
            fig: Matplotlib Figure to bind keyboard events to
        """
        if self._cid is not None:
            self.disconnect()

        self._fig = fig
        self._cid = fig.canvas.mpl_connect('key_press_event', self._on_key_press)
        logging.info("Keyboard handler connected to figure")

    def disconnect(self) -> None:
        """Disconnect keyboard event handler from figure."""
        if self._cid is not None and self._fig is not None:
            try:
                self._fig.canvas.mpl_disconnect(self._cid)
            except Exception as e:
                logging.warning(f"Error disconnecting keyboard handler: {e}")
            self._cid = None
        self._fig = None
        logging.debug("Keyboard handler disconnected")

    def _on_key_press(self, event: KeyEvent) -> None:
        """
        Handle keyboard events from matplotlib.

        Args:
            event: Matplotlib KeyEvent containing key information
        """
        if event.key is None:
            return

        key = event.key.lower()

        # Dispatch based on key
        if key == ' ':  # Space bar
            self._toggle_pause_resume()
        elif key == 'right':
            self._step_forward()
        elif key == 'up':
            self._increase_speed()
        elif key == 'down':
            self._decrease_speed()
        elif key == 'r':
            self._reset()
        elif key == 'h':
            self._show_help()

    def _toggle_pause_resume(self) -> None:
        """Toggle between paused and playing states."""
        status = self.playback_controller.get_status()

        if status.state == PlaybackState.PLAYING:
            # Pause
            self.playback_controller.pause_playback("User pressed SPACE")
            self._notify_action("pause", {
                "bar_idx": status.current_bar_idx,
                "message": "Playback paused"
            })
        elif status.state in [PlaybackState.PAUSED, PlaybackState.STOPPED]:
            # Resume/Start
            mode = status.mode if status.mode != PlaybackMode.MANUAL else PlaybackMode.AUTO
            self.playback_controller.start_playback(mode)
            self._notify_action("resume", {
                "bar_idx": status.current_bar_idx,
                "mode": mode.value,
                "message": f"Playback resumed ({mode.value} mode)"
            })
        elif status.state == PlaybackState.FINISHED:
            # Reset and start
            self.playback_controller.stop_playback()
            self.playback_controller.start_playback(PlaybackMode.AUTO)
            self._notify_action("restart", {
                "message": "Restarted from beginning"
            })

    def _step_forward(self) -> None:
        """Advance one bar manually."""
        # Ensure we're paused for manual stepping
        status = self.playback_controller.get_status()
        if status.state == PlaybackState.PLAYING:
            self.playback_controller.pause_playback("Manual step requested")

        success = self.playback_controller.step_forward()
        if success:
            new_status = self.playback_controller.get_status()
            self._notify_action("step", {
                "bar_idx": new_status.current_bar_idx,
                "total_bars": new_status.total_bars,
                "message": f"Stepped to bar {new_status.current_bar_idx}"
            })
        else:
            self._notify_action("step_failed", {
                "message": "Cannot step - at end of data"
            })

    def _increase_speed(self) -> None:
        """Increase playback speed - doubles current speed (no maximum)."""
        # Double the current speed
        self._current_speed *= 2
        self.playback_controller.set_playback_speed(self._current_speed)

        # Format label nicely
        if self._current_speed >= 1:
            label = f"{int(self._current_speed)}x" if self._current_speed == int(self._current_speed) else f"{self._current_speed}x"
        else:
            label = f"{self._current_speed}x"

        self._notify_action("speed_change", {
            "speed": self._current_speed,
            "label": label,
            "message": f"Speed: {label}"
        })

    def _decrease_speed(self) -> None:
        """Decrease playback speed - halves current speed (minimum 0.25x)."""
        if self._current_speed > 0.25:
            # Halve the current speed
            self._current_speed /= 2
            # Don't go below 0.25x
            if self._current_speed < 0.25:
                self._current_speed = 0.25
            self.playback_controller.set_playback_speed(self._current_speed)

            # Format label nicely
            if self._current_speed >= 1:
                label = f"{int(self._current_speed)}x" if self._current_speed == int(self._current_speed) else f"{self._current_speed}x"
            else:
                label = f"{self._current_speed}x"

            self._notify_action("speed_change", {
                "speed": self._current_speed,
                "label": label,
                "message": f"Speed: {label}"
            })
        else:
            self._notify_action("speed_min", {
                "message": "Already at minimum speed (0.25x)"
            })

    def _reset(self) -> None:
        """Reset playback to beginning."""
        self.playback_controller.stop_playback()
        self._current_speed = 1.0  # Reset to 1x speed
        self.playback_controller.set_playback_speed(1.0)
        self._notify_action("reset", {
            "message": "Reset to beginning"
        })

    def _show_help(self) -> None:
        """Show keyboard shortcuts help."""
        help_text = """
Keyboard Shortcuts:
  SPACE  - Pause/Resume playback
  RIGHT  - Step forward one bar
  UP     - Increase speed
  DOWN   - Decrease speed
  R      - Reset to beginning
  H      - Show this help
"""
        self._notify_action("help", {
            "message": help_text
        })

    def _notify_action(self, action: str, details: Dict[str, Any]) -> None:
        """
        Notify callback of action taken.

        Args:
            action: Name of action performed
            details: Dictionary with action details
        """
        if self.on_action_callback:
            try:
                self.on_action_callback(action, details)
            except Exception as e:
                logging.error(f"Error in action callback: {e}")

    def get_current_speed_label(self) -> str:
        """Get the current speed label."""
        if self._current_speed >= 1:
            if self._current_speed == int(self._current_speed):
                return f"{int(self._current_speed)}x"
            return f"{self._current_speed}x"
        return f"{self._current_speed}x"
