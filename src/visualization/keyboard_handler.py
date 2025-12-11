"""
Keyboard Handler Module

Provides keyboard event handling for the matplotlib visualization window,
enabling pause/resume, stepping, speed control, layout management, and
swing visibility control directly from the UI.

Keyboard Shortcuts:
- SPACE: Toggle pause/resume
- RIGHT ARROW: Step forward one bar
- UP ARROW: Increase playback speed
- DOWN ARROW: Decrease playback speed
- R: Reset to beginning
- H: Show help

Time-Based Stepping (Issue #14):
- F: Step forward 1 hour (60 bars at 1m resolution)
- G: Step forward 4 hours (240 bars at 1m resolution)
- D: Step forward 1 day (1440 bars at 1m resolution, skips weekends)

Layout Controls (Issue #12):
- 1-4: Expand panel 1/2/3/4 (S/M/L/XL scale)
- 0/ESC: Return to quad layout
- Click panel: Toggle expand/collapse

Swing Visibility Controls (Issue #12):
- V: Cycle visibility mode (All -> Single -> Recent Event -> All)
- [: Previous swing in Single mode
- ]: Next swing in Single mode
- A: Toggle show all swings (bypass swing cap)

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
                 on_action_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 visualization_renderer: Optional[Any] = None):
        """
        Initialize keyboard handler.

        Args:
            playback_controller: Controller for playback state management
            on_action_callback: Optional callback(action_name, details) for status updates
            visualization_renderer: Optional renderer for layout control (Issue #12)
        """
        self.playback_controller = playback_controller
        self.on_action_callback = on_action_callback
        self.visualization_renderer = visualization_renderer
        self._cid = None  # Connection ID for matplotlib keyboard event
        self._click_cid = None  # Connection ID for matplotlib click event
        self._fig = None

        # Speed tracking - starts at 1x (doubles with UP, halves with DOWN, min 0.25x)
        self._current_speed = 1.0

        logging.info("KeyboardHandler initialized")

    def set_visualization_renderer(self, renderer: Any) -> None:
        """
        Set the visualization renderer for layout control.

        Args:
            renderer: VisualizationRenderer instance
        """
        self.visualization_renderer = renderer

    def connect(self, fig: Figure) -> None:
        """
        Connect keyboard and click event handlers to matplotlib figure.

        Args:
            fig: Matplotlib Figure to bind events to
        """
        if self._cid is not None:
            self.disconnect()

        self._fig = fig
        self._cid = fig.canvas.mpl_connect('key_press_event', self._on_key_press)
        self._click_cid = fig.canvas.mpl_connect('button_press_event', self._on_click)
        logging.info("Keyboard and click handlers connected to figure")

    def disconnect(self) -> None:
        """Disconnect keyboard and click event handlers from figure."""
        if self._fig is not None:
            if self._cid is not None:
                try:
                    self._fig.canvas.mpl_disconnect(self._cid)
                except Exception as e:
                    logging.warning(f"Error disconnecting keyboard handler: {e}")
                self._cid = None
            if self._click_cid is not None:
                try:
                    self._fig.canvas.mpl_disconnect(self._click_cid)
                except Exception as e:
                    logging.warning(f"Error disconnecting click handler: {e}")
                self._click_cid = None
        self._fig = None
        logging.debug("Keyboard and click handlers disconnected")

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
        # Time-based stepping (Issue #14)
        elif key == 'f':
            self._step_time(60)  # 1 hour
        elif key == 'g':
            self._step_time(240)  # 4 hours
        elif key == 'd':
            self._step_time(1440)  # 1 day
        # Layout controls (Issue #12)
        elif key in ['1', '2', '3', '4']:
            self._expand_panel(int(key) - 1)
        elif key in ['0', 'escape']:
            self._restore_quad_layout()
        # Swing visibility controls (Issue #12)
        elif key == 'v':
            self._cycle_visibility_mode()
        elif key == '[':
            self._cycle_previous_swing()
        elif key == ']':
            self._cycle_next_swing()
        elif key == 'a':
            self._toggle_show_all_swings()

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

    def _step_time(self, minutes: int) -> None:
        """
        Step forward by a fixed time interval.

        This assumes 1-minute source bars. The method steps forward by
        the specified number of minutes efficiently using bulk stepping.

        Args:
            minutes: Number of minutes to step forward (60=1h, 240=4h, 1440=1d)
        """
        # Ensure we're paused for manual stepping
        status = self.playback_controller.get_status()
        if status.state == PlaybackState.PLAYING:
            self.playback_controller.pause_playback("Time-based step requested")

        # Use bulk step for efficiency - this skips per-bar callbacks
        # The harness will need to catch up swing state separately
        steps_taken = self.playback_controller.step_forward_bulk(minutes, skip_callbacks=True)

        if steps_taken > 0:
            new_status = self.playback_controller.get_status()
            # Format time label
            if minutes >= 1440:
                time_label = f"{minutes // 1440} day(s)"
            elif minutes >= 60:
                time_label = f"{minutes // 60} hour(s)"
            else:
                time_label = f"{minutes} minute(s)"

            # Notify action with bulk_step flag so harness knows to catch up swing state
            self._notify_action("time_step", {
                "bar_idx": new_status.current_bar_idx,
                "total_bars": new_status.total_bars,
                "steps": steps_taken,
                "minutes": minutes,
                "bulk_step": True,  # Signal that swing state needs catch-up
                "message": f"Stepped {time_label} ({steps_taken} bars) to bar {new_status.current_bar_idx}"
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

Time-Based Stepping:
  F      - Step forward 1 hour (60 bars)
  G      - Step forward 4 hours (240 bars)
  D      - Step forward 1 day (1440 bars)

Layout Controls:
  1-4    - Expand panel 1/2/3/4 (S/M/L/XL)
  0/ESC  - Return to quad layout
  Click  - Toggle expand on clicked panel

Swing Visibility:
  V      - Cycle mode (All -> Single -> Recent -> All)
  [      - Previous swing (in Single mode)
  ]      - Next swing (in Single mode)
  A      - Toggle show all swings (bypass cap)
"""
        self._notify_action("help", {
            "message": help_text
        })

    # Layout control methods (Issue #12)

    def _expand_panel(self, panel_idx: int) -> None:
        """
        Expand a panel to ~90% view.

        Args:
            panel_idx: Panel index (0-3)
        """
        if self.visualization_renderer is None:
            self._notify_action("layout_error", {
                "message": "No renderer configured for layout control"
            })
            return

        if panel_idx < 0 or panel_idx > 3:
            return

        scale_names = {0: 'S', 1: 'M', 2: 'L', 3: 'XL'}
        self.visualization_renderer.expand_panel(panel_idx)
        self._notify_action("layout_expand", {
            "panel": panel_idx,
            "scale": scale_names[panel_idx],
            "message": f"Expanded {scale_names[panel_idx]} scale panel"
        })

    def _restore_quad_layout(self) -> None:
        """Return to standard 2x2 layout."""
        if self.visualization_renderer is None:
            self._notify_action("layout_error", {
                "message": "No renderer configured for layout control"
            })
            return

        self.visualization_renderer.restore_quad_layout()
        self._notify_action("layout_quad", {
            "message": "Restored quad layout"
        })

    def _on_click(self, event) -> None:
        """
        Handle mouse click events for panel expansion.

        Double-click or single click on a panel toggles its expansion.

        Args:
            event: Matplotlib MouseEvent
        """
        if event.inaxes is None:
            return

        if self.visualization_renderer is None:
            return

        # Find which panel was clicked
        panel_idx = self._find_clicked_panel(event.inaxes)
        if panel_idx is not None:
            self.visualization_renderer.toggle_panel_expand(panel_idx)
            scale_names = {0: 'S', 1: 'M', 2: 'L', 3: 'XL'}
            self._notify_action("layout_toggle", {
                "panel": panel_idx,
                "scale": scale_names[panel_idx],
                "message": f"Toggled {scale_names[panel_idx]} scale panel"
            })

    def _find_clicked_panel(self, clicked_ax) -> Optional[int]:
        """
        Determine which panel index corresponds to the clicked axis.

        Args:
            clicked_ax: The axis that was clicked

        Returns:
            Panel index (0-3) or None if not found
        """
        if self.visualization_renderer is None:
            return None

        for panel_idx, ax in self.visualization_renderer.axes.items():
            if ax is clicked_ax:
                return panel_idx
        return None

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

    # Swing visibility control methods (Issue #12)

    def _cycle_visibility_mode(self) -> None:
        """Cycle through swing visibility modes for all panels."""
        if self.visualization_renderer is None:
            self._notify_action("visibility_error", {
                "message": "No renderer configured for visibility control"
            })
            return

        new_mode = self.visualization_renderer.cycle_visibility_mode()
        mode_names = {
            "all": "All Swings",
            "single": "Single Swing",
            "recent": "Recent Event"
        }
        mode_name = mode_names.get(new_mode.value, new_mode.value)

        # Trigger redraw to reflect new visibility mode
        self.visualization_renderer._rerender_cached_state()

        self._notify_action("visibility_mode", {
            "mode": new_mode.value,
            "message": f"Visibility: {mode_name}"
        })

    def _cycle_next_swing(self) -> None:
        """Select next swing in Single visibility mode."""
        if self.visualization_renderer is None:
            return

        # Get cached swings from renderer, grouped by scale
        cached_swings = self.visualization_renderer._cached_active_swings
        swings_by_scale = self.visualization_renderer._group_swings_by_scale(cached_swings)

        # Cycle through swings for all panels (or use focused panel if in expanded mode)
        expanded = None
        if self.visualization_renderer.layout_manager:
            expanded = self.visualization_renderer.layout_manager.get_expanded_panel()

        if expanded is not None:
            # Only cycle for expanded panel
            panels = [expanded]
        else:
            # Cycle for all panels
            panels = list(range(4))

        scale_names = {0: 'S', 1: 'M', 2: 'L', 3: 'XL'}
        for panel_idx in panels:
            scale = scale_names[panel_idx]
            panel_swings = swings_by_scale.get(scale, [])
            self.visualization_renderer.swing_visibility.cycle_next(panel_idx, panel_swings)

        # Trigger redraw to reflect new selection
        self.visualization_renderer._rerender_cached_state()

        self._notify_action("swing_next", {
            "message": "Next swing selected"
        })

    def _cycle_previous_swing(self) -> None:
        """Select previous swing in Single visibility mode."""
        if self.visualization_renderer is None:
            return

        # Get cached swings from renderer, grouped by scale
        cached_swings = self.visualization_renderer._cached_active_swings
        swings_by_scale = self.visualization_renderer._group_swings_by_scale(cached_swings)

        # Similar to _cycle_next_swing
        expanded = None
        if self.visualization_renderer.layout_manager:
            expanded = self.visualization_renderer.layout_manager.get_expanded_panel()

        if expanded is not None:
            panels = [expanded]
        else:
            panels = list(range(4))

        scale_names = {0: 'S', 1: 'M', 2: 'L', 3: 'XL'}
        for panel_idx in panels:
            scale = scale_names[panel_idx]
            panel_swings = swings_by_scale.get(scale, [])
            self.visualization_renderer.swing_visibility.cycle_previous(panel_idx, panel_swings)

        # Trigger redraw to reflect new selection
        self.visualization_renderer._rerender_cached_state()

        self._notify_action("swing_previous", {
            "message": "Previous swing selected"
        })

    def _toggle_show_all_swings(self) -> None:
        """Toggle between showing capped swings and all swings."""
        if self.visualization_renderer is None:
            self._notify_action("swing_cap_error", {
                "message": "No renderer configured for swing cap control"
            })
            return

        show_all = self.visualization_renderer.toggle_show_all_swings()

        # Trigger redraw to reflect new visibility
        self.visualization_renderer._rerender_cached_state()

        if show_all:
            self._notify_action("swing_cap_toggle", {
                "show_all": True,
                "message": "Showing all swings (cap bypassed)"
            })
        else:
            cap = self.visualization_renderer.config.max_swings_per_scale
            self._notify_action("swing_cap_toggle", {
                "show_all": False,
                "cap": cap,
                "message": f"Showing top {cap} swings per scale"
            })
