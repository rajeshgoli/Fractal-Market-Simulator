"""
Swing Visibility Controller Module

Manages swing visibility modes for the visualization harness, allowing users
to cycle through overlapping swings and highlight recent events.

Implements Issue #12 Enhancement: Overlapping Swings/Levels Hard to Read

Author: Generated for Market Simulator Project
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging
import time


class VisibilityMode(Enum):
    """Swing visibility modes."""
    ALL = "all"             # Show all swings (default)
    SINGLE = "single"       # One swing at a time, cycle with [/]
    RECENT_EVENT = "recent" # Highlight swing with most recent event, dim others


@dataclass
class SwingVisibilityState:
    """Visibility state for a single scale."""
    mode: VisibilityMode = VisibilityMode.ALL
    selected_swing_id: Optional[str] = None  # For SINGLE mode
    highlighted_swing_id: Optional[str] = None  # For RECENT_EVENT mode
    last_event_time: float = 0.0


class SwingVisibilityController:
    """
    Controls swing visibility across scales.

    Supports three visibility modes:
    - ALL: Show all swings with full opacity
    - SINGLE: Show one swing at a time, user can cycle through
    - RECENT_EVENT: Highlight the swing with most recent event, dim others

    Usage:
        controller = SwingVisibilityController()
        controller.set_mode(scale=0, mode=VisibilityMode.SINGLE)
        visible_swings = controller.get_visible_swings(scale=0, all_swings=swings)
        opacity = controller.get_swing_opacity(swing_id, scale=0)
    """

    # Opacity values for different visibility states
    OPACITY_FULL = 1.0
    OPACITY_DIMMED = 0.3
    OPACITY_HIDDEN = 0.0

    def __init__(self):
        """Initialize the visibility controller."""
        # Per-scale visibility state (0-3 for S/M/L/XL)
        self._scale_states: Dict[int, SwingVisibilityState] = {
            i: SwingVisibilityState() for i in range(4)
        }
        # Track recent events per swing for RECENT_EVENT mode
        self._swing_event_times: Dict[str, float] = {}
        logging.info("SwingVisibilityController initialized")

    def get_mode(self, scale: int) -> VisibilityMode:
        """
        Get current visibility mode for a scale.

        Args:
            scale: Scale index (0-3)

        Returns:
            Current VisibilityMode
        """
        return self._scale_states[scale].mode

    def set_mode(self, scale: int, mode: VisibilityMode) -> None:
        """
        Set visibility mode for a scale.

        Args:
            scale: Scale index (0-3)
            mode: New visibility mode
        """
        if scale not in self._scale_states:
            logging.warning(f"Invalid scale index: {scale}")
            return

        old_mode = self._scale_states[scale].mode
        self._scale_states[scale].mode = mode
        logging.debug(f"Scale {scale} visibility mode: {old_mode.value} -> {mode.value}")

    def cycle_mode(self, scale: int) -> VisibilityMode:
        """
        Cycle to the next visibility mode for a scale.

        Order: ALL -> SINGLE -> RECENT_EVENT -> ALL

        Args:
            scale: Scale index (0-3)

        Returns:
            New visibility mode
        """
        current = self._scale_states[scale].mode
        mode_order = [VisibilityMode.ALL, VisibilityMode.SINGLE, VisibilityMode.RECENT_EVENT]
        current_idx = mode_order.index(current)
        next_idx = (current_idx + 1) % len(mode_order)
        new_mode = mode_order[next_idx]
        self.set_mode(scale, new_mode)
        return new_mode

    def cycle_mode_all_scales(self) -> VisibilityMode:
        """
        Cycle visibility mode for all scales simultaneously.

        Returns:
            New visibility mode (same for all scales)
        """
        # Use scale 0's mode as reference
        new_mode = self.cycle_mode(0)
        for scale in range(1, 4):
            self.set_mode(scale, new_mode)
        return new_mode

    def cycle_next(self, scale: int, swings: List[Any]) -> Optional[str]:
        """
        Select the next swing in SINGLE mode.

        Args:
            scale: Scale index (0-3)
            swings: List of ActiveSwing objects

        Returns:
            ID of newly selected swing, or None if no swings
        """
        if not swings:
            return None

        state = self._scale_states[scale]
        swing_ids = [self._get_swing_id(s) for s in swings]

        if state.selected_swing_id is None or state.selected_swing_id not in swing_ids:
            # Select first swing
            state.selected_swing_id = swing_ids[0]
        else:
            # Select next swing
            current_idx = swing_ids.index(state.selected_swing_id)
            next_idx = (current_idx + 1) % len(swing_ids)
            state.selected_swing_id = swing_ids[next_idx]

        logging.debug(f"Scale {scale}: selected swing {state.selected_swing_id}")
        return state.selected_swing_id

    def cycle_previous(self, scale: int, swings: List[Any]) -> Optional[str]:
        """
        Select the previous swing in SINGLE mode.

        Args:
            scale: Scale index (0-3)
            swings: List of ActiveSwing objects

        Returns:
            ID of newly selected swing, or None if no swings
        """
        if not swings:
            return None

        state = self._scale_states[scale]
        swing_ids = [self._get_swing_id(s) for s in swings]

        if state.selected_swing_id is None or state.selected_swing_id not in swing_ids:
            # Select last swing
            state.selected_swing_id = swing_ids[-1]
        else:
            # Select previous swing
            current_idx = swing_ids.index(state.selected_swing_id)
            prev_idx = (current_idx - 1) % len(swing_ids)
            state.selected_swing_id = swing_ids[prev_idx]

        logging.debug(f"Scale {scale}: selected swing {state.selected_swing_id}")
        return state.selected_swing_id

    def get_visible_swings(self, scale: int, all_swings: List[Any]) -> List[Any]:
        """
        Get list of swings that should be visible for a scale.

        Args:
            scale: Scale index (0-3)
            all_swings: All ActiveSwing objects for this scale

        Returns:
            List of swings to render (may be filtered in SINGLE mode)
        """
        state = self._scale_states[scale]

        if state.mode == VisibilityMode.ALL:
            return all_swings
        elif state.mode == VisibilityMode.SINGLE:
            if state.selected_swing_id is None and all_swings:
                # Auto-select first swing
                state.selected_swing_id = self._get_swing_id(all_swings[0])
            # Return only the selected swing
            return [s for s in all_swings
                    if self._get_swing_id(s) == state.selected_swing_id]
        elif state.mode == VisibilityMode.RECENT_EVENT:
            # In RECENT_EVENT mode, return all swings (opacity handles dimming)
            return all_swings

        return all_swings

    def get_swing_opacity(self, swing: Any, scale: int) -> float:
        """
        Get opacity for a swing based on current visibility mode.

        Args:
            swing: ActiveSwing object
            scale: Scale index (0-3)

        Returns:
            Opacity value (0.0 to 1.0)
        """
        state = self._scale_states[scale]
        swing_id = self._get_swing_id(swing)

        if state.mode == VisibilityMode.ALL:
            return self.OPACITY_FULL

        elif state.mode == VisibilityMode.SINGLE:
            if swing_id == state.selected_swing_id:
                return self.OPACITY_FULL
            return self.OPACITY_HIDDEN

        elif state.mode == VisibilityMode.RECENT_EVENT:
            # Highlight swing with most recent event
            highlighted = self._get_most_recent_swing(scale)
            if highlighted and swing_id == highlighted:
                return self.OPACITY_FULL
            return self.OPACITY_DIMMED

        return self.OPACITY_FULL

    def record_event(self, event: Any, scale: int) -> None:
        """
        Record an event for a swing (updates "most recent" tracking).

        Args:
            event: Event object with swing_id attribute
            scale: Scale index (0-3)
        """
        swing_id = self._get_event_swing_id(event)
        if swing_id:
            event_time = time.time()
            self._swing_event_times[swing_id] = event_time
            self._scale_states[scale].highlighted_swing_id = swing_id
            self._scale_states[scale].last_event_time = event_time
            logging.debug(f"Recorded event for swing {swing_id} at scale {scale}")

    def get_selected_swing_id(self, scale: int) -> Optional[str]:
        """
        Get the currently selected swing ID for SINGLE mode.

        Args:
            scale: Scale index (0-3)

        Returns:
            Selected swing ID or None
        """
        return self._scale_states[scale].selected_swing_id

    def get_highlighted_swing_id(self, scale: int) -> Optional[str]:
        """
        Get the highlighted swing ID for RECENT_EVENT mode.

        Args:
            scale: Scale index (0-3)

        Returns:
            Highlighted swing ID or None
        """
        return self._scale_states[scale].highlighted_swing_id

    def clear_selection(self, scale: int) -> None:
        """
        Clear swing selection for a scale.

        Args:
            scale: Scale index (0-3)
        """
        self._scale_states[scale].selected_swing_id = None
        self._scale_states[scale].highlighted_swing_id = None

    def clear_all_selections(self) -> None:
        """Clear swing selection for all scales."""
        for scale in range(4):
            self.clear_selection(scale)

    def reset(self) -> None:
        """Reset all visibility state to defaults."""
        for scale in range(4):
            self._scale_states[scale] = SwingVisibilityState()
        self._swing_event_times.clear()
        logging.info("SwingVisibilityController reset")

    def _get_swing_id(self, swing: Any) -> str:
        """
        Get unique identifier for a swing.

        Args:
            swing: ActiveSwing object

        Returns:
            String identifier
        """
        # Try various attribute patterns for swing ID
        if hasattr(swing, 'swing_id'):
            return str(swing.swing_id)
        elif hasattr(swing, 'id'):
            return str(swing.id)
        elif hasattr(swing, 'high_timestamp') and hasattr(swing, 'low_timestamp'):
            # Create ID from timestamps
            return f"{swing.high_timestamp}_{swing.low_timestamp}"
        else:
            # Fallback to object id
            return str(id(swing))

    def _get_event_swing_id(self, event: Any) -> Optional[str]:
        """
        Extract swing ID from an event.

        Args:
            event: Event object

        Returns:
            Swing ID or None
        """
        if hasattr(event, 'swing_id'):
            return str(event.swing_id)
        elif hasattr(event, 'swing') and event.swing:
            return self._get_swing_id(event.swing)
        elif hasattr(event, 'context') and isinstance(event.context, dict):
            if 'swing_id' in event.context:
                return str(event.context['swing_id'])
        return None

    def _get_most_recent_swing(self, scale: int) -> Optional[str]:
        """
        Get the swing with most recent event for a scale.

        Args:
            scale: Scale index (0-3)

        Returns:
            Swing ID with most recent event, or None
        """
        # First check scale-specific highlighted swing
        state = self._scale_states[scale]
        if state.highlighted_swing_id:
            return state.highlighted_swing_id

        # Fallback to global most recent
        if self._swing_event_times:
            return max(self._swing_event_times, key=self._swing_event_times.get)

        return None

    def get_mode_display_name(self, scale: int) -> str:
        """
        Get human-readable name for current mode.

        Args:
            scale: Scale index (0-3)

        Returns:
            Display name string
        """
        mode = self._scale_states[scale].mode
        names = {
            VisibilityMode.ALL: "All Swings",
            VisibilityMode.SINGLE: "Single Swing",
            VisibilityMode.RECENT_EVENT: "Recent Event"
        }
        return names.get(mode, mode.value)

    def get_status_summary(self, scale: int, swings: List[Any]) -> str:
        """
        Get status summary for display.

        Args:
            scale: Scale index (0-3)
            swings: Available swings

        Returns:
            Status string
        """
        state = self._scale_states[scale]
        mode_name = self.get_mode_display_name(scale)

        if state.mode == VisibilityMode.ALL:
            return f"{mode_name} ({len(swings)} swings)"
        elif state.mode == VisibilityMode.SINGLE:
            if swings:
                swing_ids = [self._get_swing_id(s) for s in swings]
                if state.selected_swing_id in swing_ids:
                    idx = swing_ids.index(state.selected_swing_id) + 1
                    return f"{mode_name} ({idx}/{len(swings)})"
            return f"{mode_name} (no selection)"
        elif state.mode == VisibilityMode.RECENT_EVENT:
            if state.highlighted_swing_id:
                return f"{mode_name} (active)"
            return f"{mode_name} (no events)"

        return mode_name
