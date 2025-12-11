"""
Layout Manager Module

Manages dynamic panel layouts for the visualization harness, supporting
expanded single-panel views with mini-summaries for other scales.

Implements Issue #12 Enhancement: Quadrants Cramped and Not Zoomable

Author: Generated for Market Simulator Project
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.figure import Figure


class LayoutMode(Enum):
    """Panel layout modes."""
    QUAD = "quad"           # 2x2 equal panels
    EXPANDED = "expanded"   # One panel at ~90%, others as mini-summaries


@dataclass
class PanelGeometry:
    """Geometry specification for a panel in the grid."""
    row_start: int
    row_span: int
    col_start: int
    col_span: int
    is_primary: bool = False  # True if this is the expanded panel
    is_mini: bool = False     # True if this is a mini summary panel


class LayoutManager:
    """
    Manages dynamic panel layout transitions.

    Supports two modes:
    - QUAD: Standard 2x2 equal-size panels
    - EXPANDED: One panel takes ~90% of space, others become mini-summaries

    Usage:
        layout_manager = LayoutManager(fig)
        geometries = layout_manager.toggle_expand(panel_idx=0)
        # Apply geometries to recreate axes...
    """

    # Grid dimensions for expanded mode (10x10 for fine control)
    EXPANDED_GRID_SIZE = 10

    def __init__(self, figure: Figure):
        """
        Initialize the layout manager.

        Args:
            figure: The matplotlib Figure to manage
        """
        self.figure = figure
        self.current_mode = LayoutMode.QUAD
        self.expanded_panel: Optional[int] = None  # Which panel is expanded (0-3)
        self._gridspec: Optional[GridSpec] = None

    def get_layout(self, mode: LayoutMode, expanded_panel: Optional[int] = None) -> Dict[int, PanelGeometry]:
        """
        Get panel geometries for the specified layout mode.

        Args:
            mode: QUAD or EXPANDED
            expanded_panel: Panel index to expand (required for EXPANDED mode)

        Returns:
            Dict mapping panel_idx (0-3) -> PanelGeometry
        """
        if mode == LayoutMode.QUAD:
            return self._quad_layout()
        else:
            if expanded_panel is None:
                raise ValueError("expanded_panel required for EXPANDED mode")
            return self._expanded_layout(expanded_panel)

    def _quad_layout(self) -> Dict[int, PanelGeometry]:
        """
        Standard 2x2 layout.

        Panel positions:
            0: Top-left (S scale)
            1: Top-right (M scale)
            2: Bottom-left (L scale)
            3: Bottom-right (XL scale)
        """
        return {
            0: PanelGeometry(row_start=0, row_span=1, col_start=0, col_span=1),
            1: PanelGeometry(row_start=0, row_span=1, col_start=1, col_span=1),
            2: PanelGeometry(row_start=1, row_span=1, col_start=0, col_span=1),
            3: PanelGeometry(row_start=1, row_span=1, col_start=1, col_span=1),
        }

    def _expanded_layout(self, primary: int) -> Dict[int, PanelGeometry]:
        """
        Expanded layout: primary panel takes ~90% (8x9 of 10x10),
        other panels become mini-summaries stacked in rightmost columns.

        Layout (10x10 grid):
        - Primary panel: rows 0-7, cols 0-8 (8 rows, 9 cols = 72% of area)
        - Mini panels: stacked in rows 0-7, cols 9 (rightmost column)
          Each mini panel gets 2-3 rows

        Args:
            primary: Panel index (0-3) to expand

        Returns:
            Dict mapping panel_idx -> PanelGeometry
        """
        geometries = {}

        # Primary panel: 8 rows, 9 columns
        geometries[primary] = PanelGeometry(
            row_start=0, row_span=8,
            col_start=0, col_span=9,
            is_primary=True,
            is_mini=False
        )

        # Mini panels: stacked vertically in rightmost column
        # Each gets roughly equal vertical space
        mini_panels = [i for i in range(4) if i != primary]
        mini_row_span = 8 // 3  # ~2-3 rows each

        for i, panel_idx in enumerate(mini_panels):
            row_start = i * mini_row_span
            # Last mini panel gets any remaining rows
            if i == len(mini_panels) - 1:
                row_span = 8 - row_start
            else:
                row_span = mini_row_span

            geometries[panel_idx] = PanelGeometry(
                row_start=row_start, row_span=row_span,
                col_start=9, col_span=1,
                is_primary=False,
                is_mini=True
            )

        return geometries

    def transition_to(self, mode: LayoutMode, expanded_panel: Optional[int] = None) -> Dict[int, PanelGeometry]:
        """
        Transition to a new layout mode.

        Args:
            mode: Target layout mode
            expanded_panel: Panel to expand (for EXPANDED mode)

        Returns:
            New panel geometries for the renderer to apply
        """
        self.current_mode = mode
        self.expanded_panel = expanded_panel
        return self.get_layout(mode, expanded_panel)

    def toggle_expand(self, panel_idx: int) -> Dict[int, PanelGeometry]:
        """
        Toggle expansion of a panel.

        If already expanded on this panel, return to QUAD.
        If in QUAD mode or expanded on different panel, expand the requested panel.

        Args:
            panel_idx: Panel index (0-3) to expand or collapse

        Returns:
            New panel geometries
        """
        if self.current_mode == LayoutMode.EXPANDED and self.expanded_panel == panel_idx:
            # Already expanded on this panel - return to quad
            return self.transition_to(LayoutMode.QUAD)
        else:
            # Expand the requested panel
            return self.transition_to(LayoutMode.EXPANDED, panel_idx)

    def create_gridspec(self, mode: LayoutMode) -> GridSpec:
        """
        Create appropriate GridSpec for the layout mode.

        Args:
            mode: QUAD or EXPANDED

        Returns:
            GridSpec configured for the mode
        """
        if mode == LayoutMode.QUAD:
            self._gridspec = GridSpec(
                2, 2,
                figure=self.figure,
                hspace=0.3,
                wspace=0.2
            )
        else:
            self._gridspec = GridSpec(
                self.EXPANDED_GRID_SIZE, self.EXPANDED_GRID_SIZE,
                figure=self.figure,
                hspace=0.1,
                wspace=0.1
            )
        return self._gridspec

    def get_current_mode(self) -> LayoutMode:
        """Get the current layout mode."""
        return self.current_mode

    def get_expanded_panel(self) -> Optional[int]:
        """Get the currently expanded panel index, or None if in QUAD mode."""
        return self.expanded_panel if self.current_mode == LayoutMode.EXPANDED else None

    def is_mini_panel(self, panel_idx: int) -> bool:
        """
        Check if a panel is currently in mini mode.

        Args:
            panel_idx: Panel index (0-3)

        Returns:
            True if panel is a mini summary, False otherwise
        """
        if self.current_mode == LayoutMode.QUAD:
            return False
        return panel_idx != self.expanded_panel
