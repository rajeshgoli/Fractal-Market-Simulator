"""
Picture-in-Picture Inset Module

Renders a small inset showing the full reference swing when
its body is scrolled out of the main view window.

Implements Issue #12 Enhancement: Reference Swing Out of View Shows Only Lines

Author: Generated for Market Simulator Project
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import logging
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes


@dataclass
class PiPConfig:
    """Configuration for PiP insets."""
    width_percent: float = 20.0    # Width as % of parent panel
    height_percent: float = 25.0   # Height as % of parent panel
    corner: str = "upper left"     # Position: "upper left", "upper right", "lower left", "lower right"
    border_color: str = "#FFD700"  # Gold border for visibility
    border_width: float = 2.0
    background_alpha: float = 0.9
    background_color: str = "#1E1E1E"


class PiPInsetManager:
    """
    Manages Picture-in-Picture insets for each panel.

    Shows a simplified representation of the reference swing when its
    body (start-to-end price range) has scrolled out of the visible area,
    so the user can still understand what swing is generating the current levels.
    """

    CORNER_ANCHORS = {
        "upper left": (0.02, 0.98, 'upper left'),
        "upper right": (0.98, 0.98, 'upper right'),
        "lower left": (0.02, 0.02, 'lower left'),
        "lower right": (0.98, 0.02, 'lower right'),
    }

    def __init__(self, config: Optional[PiPConfig] = None):
        """
        Initialize the PiP inset manager.

        Args:
            config: PiP appearance configuration
        """
        self.config = config or PiPConfig()
        self._insets: Dict[int, Axes] = {}  # panel_idx -> inset axes
        self._inset_visible: Dict[int, bool] = {}

    def update_pip(self,
                   parent_ax: Axes,
                   panel_idx: int,
                   swing,  # ActiveSwing
                   view_window,  # ViewWindow
                   aggregated_bars: List,
                   timeframe: int = 1) -> Optional[Axes]:
        """
        Update or create PiP inset if swing body is out of view.

        Args:
            parent_ax: The main panel axes
            panel_idx: Index of the panel (0-3)
            swing: The reference swing to potentially show in PiP
            view_window: Current view window of the parent (in aggregated bar space)
            aggregated_bars: All bars for this timeframe
            timeframe: Aggregation timeframe in minutes

        Returns:
            The inset axes if created/updated, None if PiP not needed
        """
        # Check if swing body is out of view
        if not self._swing_needs_pip(swing, view_window, aggregated_bars):
            self._hide_pip(panel_idx)
            return None

        # Create or get inset
        inset_ax = self._get_or_create_inset(parent_ax, panel_idx)

        # Render swing in inset
        self._render_swing_in_pip(inset_ax, swing)

        self._inset_visible[panel_idx] = True
        return inset_ax

    def _swing_needs_pip(self,
                         swing,
                         view_window,
                         bars: List) -> bool:
        """
        Check if swing body is scrolled out of view.

        The swing body is defined by its high and low timestamps.
        If both are before the view window start, the swing needs PiP.

        Args:
            swing: ActiveSwing with high_timestamp and low_timestamp
            view_window: ViewWindow with start_idx and end_idx
            bars: Aggregated bars for timestamp lookup

        Returns:
            True if PiP should be shown
        """
        if not bars:
            return False

        # Find bar indices for swing high and low timestamps
        high_idx = self._find_bar_index_by_timestamp(bars, swing.high_timestamp)
        low_idx = self._find_bar_index_by_timestamp(bars, swing.low_timestamp)

        if high_idx is None and low_idx is None:
            # Can't find swing bars in current data - might be outside data range
            return True

        # Get the end of the swing body (the later of high/low)
        swing_indices = [i for i in [high_idx, low_idx] if i is not None]
        if not swing_indices:
            return True

        swing_end = max(swing_indices)

        # Swing needs PiP if its body ended before the visible range
        return swing_end < view_window.start_idx

    def _find_bar_index_by_timestamp(self, bars: List, timestamp: int) -> Optional[int]:
        """
        Find bar index by timestamp.

        Args:
            bars: List of bars with timestamp attribute
            timestamp: Unix timestamp to find

        Returns:
            Index of bar with matching timestamp, or None
        """
        for i, bar in enumerate(bars):
            if bar.timestamp == timestamp:
                return i
        return None

    def _get_or_create_inset(self, parent_ax: Axes, panel_idx: int) -> Axes:
        """
        Get existing inset or create new one.

        Args:
            parent_ax: Parent axes to host the inset
            panel_idx: Panel index for tracking

        Returns:
            Inset Axes object
        """
        if panel_idx in self._insets:
            inset = self._insets[panel_idx]
            try:
                inset.set_visible(True)
                return inset
            except Exception:
                # Inset was removed, need to recreate
                pass

        # Create new inset using inset_axes
        x, y, loc = self.CORNER_ANCHORS.get(
            self.config.corner,
            self.CORNER_ANCHORS["upper left"]
        )

        inset = inset_axes(
            parent_ax,
            width=f"{self.config.width_percent}%",
            height=f"{self.config.height_percent}%",
            loc=loc,
        )

        # Style the inset
        inset.patch.set_facecolor(self.config.background_color)
        inset.patch.set_alpha(self.config.background_alpha)
        for spine in inset.spines.values():
            spine.set_edgecolor(self.config.border_color)
            spine.set_linewidth(self.config.border_width)

        self._insets[panel_idx] = inset
        return inset

    def _hide_pip(self, panel_idx: int) -> None:
        """
        Hide PiP for specified panel.

        Args:
            panel_idx: Panel index
        """
        if panel_idx in self._insets:
            try:
                self._insets[panel_idx].set_visible(False)
            except Exception:
                pass
            self._inset_visible[panel_idx] = False

    def _render_swing_in_pip(self, inset_ax: Axes, swing) -> None:
        """
        Render the swing body and key levels in the PiP inset.

        Shows a schematic representation using NORMALIZED coordinates (0-1):
        - Vertical rectangle showing the swing body (fixed proportions)
        - Key Fibonacci levels as horizontal lines at their relative positions
        - Color indicates bull/bear direction
        - Price labels on the right edge

        This is NOT a mini-chart - it's a conceptual diagram showing swing structure.

        Args:
            inset_ax: The inset axes to draw on
            swing: ActiveSwing with levels, high_price, low_price, is_bull
        """
        inset_ax.clear()

        # Colors
        swing_color = "#26A69A" if swing.is_bull else "#EF5350"
        text_color = "#FFFFFF"

        # Use FULLY NORMALIZED coordinates (0-1 for both axes)
        # The swing body spans from y=0.1 to y=0.9 (leaving room for labels)
        body_bottom = 0.1
        body_top = 0.9
        body_height = body_top - body_bottom

        # Draw swing body as a centered vertical rectangle
        body_width = 0.3
        body_x = 0.35  # Center it

        rect = Rectangle(
            (body_x, body_bottom),
            body_width, body_height,
            facecolor=swing_color,
            edgecolor='white',
            alpha=0.7,
            linewidth=1.5
        )
        inset_ax.add_patch(rect)

        # Calculate price range for level positioning
        price_range = swing.high_price - swing.low_price
        if price_range <= 0:
            price_range = 1  # Prevent division by zero

        # Helper to convert price to normalized Y coordinate
        def price_to_y(price):
            # Map price from [low, high] to [body_bottom, body_top]
            if price_range > 0:
                normalized = (price - swing.low_price) / price_range
                return body_bottom + normalized * body_height
            return 0.5

        # Draw key Fibonacci levels as horizontal lines
        # Show levels 0 (origin), 0.5 (mid), 1.0 (par), 1.618, 2.0 (exhaustion)
        key_levels = ["0", "0.5", "1.0", "1.618", "2.0"]
        level_colors = {
            "0": "#FFFFFF",    # White - swing origin
            "0.5": "#AAAAAA",  # Gray - midpoint
            "1.0": "#00FF00",  # Green - par (100% retracement)
            "1.618": "#FFD700", # Gold - golden ratio
            "2.0": "#FF6600",  # Orange - exhaustion
        }
        level_styles = {
            "0": "-",      # Solid for origin
            "0.5": ":",    # Dotted for mid
            "1.0": "-",    # Solid for par
            "1.618": "--", # Dashed for golden
            "2.0": "-",    # Solid for exhaustion
        }

        for level_name in key_levels:
            if level_name in swing.levels:
                price = swing.levels[level_name]
                y_pos = price_to_y(price)

                # Only draw if within visible range (0-1)
                if 0 <= y_pos <= 1:
                    color = level_colors.get(level_name, text_color)
                    style = level_styles.get(level_name, "--")

                    # Draw line from left edge to right edge
                    inset_ax.axhline(
                        y=y_pos,
                        xmin=0.1, xmax=0.9,
                        color=color,
                        linestyle=style,
                        linewidth=1.0,
                        alpha=0.8
                    )

                    # Level label on right
                    inset_ax.text(
                        0.95, y_pos, level_name,
                        fontsize=6,
                        color=color,
                        va='center',
                        ha='right',
                        alpha=0.9
                    )

        # Add price annotations at top and bottom
        inset_ax.text(
            0.05, body_top + 0.02, f"H:{swing.high_price:.1f}",
            fontsize=5, color='#AAAAAA', va='bottom', ha='left'
        )
        inset_ax.text(
            0.05, body_bottom - 0.02, f"L:{swing.low_price:.1f}",
            fontsize=5, color='#AAAAAA', va='top', ha='left'
        )

        # Set fixed limits (normalized 0-1 space)
        inset_ax.set_xlim(0, 1)
        inset_ax.set_ylim(0, 1)

        # Hide all axes (this is a schematic, not a chart)
        inset_ax.set_xticks([])
        inset_ax.set_yticks([])
        for spine in inset_ax.spines.values():
            spine.set_visible(False)

        # Add "Ref" label with direction indicator
        direction = "Bull" if swing.is_bull else "Bear"
        inset_ax.set_title(
            f"Ref ({direction})",
            fontsize=7,
            color=self.config.border_color,
            pad=2
        )

        # Style the inset background
        inset_ax.set_facecolor(self.config.background_color)

    def clear_pip(self, panel_idx: int) -> None:
        """
        Remove PiP for a specific panel.

        Args:
            panel_idx: Panel index
        """
        if panel_idx in self._insets:
            try:
                self._insets[panel_idx].remove()
            except Exception:
                pass
            del self._insets[panel_idx]
            self._inset_visible.pop(panel_idx, None)

    def clear_all(self) -> None:
        """Remove all insets."""
        for panel_idx in list(self._insets.keys()):
            self.clear_pip(panel_idx)

    def is_pip_visible(self, panel_idx: int) -> bool:
        """
        Check if PiP is currently visible for a panel.

        Args:
            panel_idx: Panel index

        Returns:
            True if PiP is visible
        """
        return self._inset_visible.get(panel_idx, False)


# Need to import plt for MaxNLocator
import matplotlib.pyplot as plt
