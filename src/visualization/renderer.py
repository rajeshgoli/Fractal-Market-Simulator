"""
Visualization Renderer Module

Implements a 4-panel synchronized matplotlib display system that renders OHLC charts
with structural overlays across all four scales (S, M, L, XL).

Key Features:
- Four synchronized panels with scale-specific aggregations
- Real-time OHLC candlestick rendering with current bar highlighting
- Fibonacci level overlays from active swings
- Event marker placement for structural events
- Sliding window display for performance
- Interactive updates during playback

Author: Generated for Market Simulator Project
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
from datetime import datetime

# Import project modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.legacy.bull_reference_detector import Bar
from src.analysis.swing_state_manager import ActiveSwing
from src.analysis.event_detector import StructuralEvent, EventType, EventSeverity
from src.analysis.bar_aggregator import BarAggregator
from src.analysis.scale_calibrator import ScaleConfig
from src.visualization.config import (
    RenderConfig, ViewWindow, PANEL_SCALE_MAPPING, LEVEL_LINE_STYLES,
    EVENT_MARKERS, get_scale_colors
)
from src.visualization.layout_manager import LayoutManager, LayoutMode, PanelGeometry
from src.visualization.pip_inset import PiPInsetManager, PiPConfig
from src.visualization.swing_visibility import SwingVisibilityController, VisibilityMode


class VisualizationRenderer:
    """Multi-panel synchronized OHLC visualization with structural overlays."""
    
    def __init__(self, 
                 scale_config: ScaleConfig,
                 bar_aggregator: BarAggregator,
                 render_config: Optional[RenderConfig] = None):
        """
        Initialize the visualization renderer.
        
        Args:
            scale_config: Scale boundaries and aggregation settings
            bar_aggregator: Source for aggregated bar data
            render_config: Appearance configuration (uses defaults if None)
        """
        self.scale_config = scale_config
        self.bar_aggregator = bar_aggregator
        self.config = render_config or RenderConfig()
        
        # Matplotlib state
        self.fig = None
        self.axes = {}  # panel_idx -> axis object
        self.artists = {}  # panel_idx -> dict of artist collections
        
        # Current display state
        self.current_bar_idx = 0
        self.view_windows = {}  # scale -> ViewWindow
        self.last_events = []

        # Performance tracking
        self.update_count = 0
        self._updates_requested = 0  # Total update requests (including skipped)
        self._frames_skipped = 0     # Count of skipped frames

        # Frame skipping state
        self._last_render_time = 0.0
        self._pending_update: Optional[Tuple[int, List[Any], List[Any], Optional[List[Any]]]] = None

        # Status overlay text artist
        self._status_text = None

        # Layout manager for dynamic panel layouts (Issue #12)
        self.layout_manager: Optional[LayoutManager] = None
        self._panel_geometries: Dict[int, PanelGeometry] = {}

        # PiP inset manager for off-screen reference swings (Issue #12)
        self.pip_manager: PiPInsetManager = PiPInsetManager()

        # Swing visibility controller for overlapping swings (Issue #12)
        self.swing_visibility: SwingVisibilityController = SwingVisibilityController()

        logging.info(f"VisualizationRenderer initialized with {len(self.scale_config.boundaries)} scales")
    
    def initialize_display(self) -> None:
        """Setup matplotlib figure and subplots for 4-panel display."""
        # Create figure with dark background
        # Use layout='constrained' instead of tight_layout() to avoid warnings
        # about incompatible axes configurations
        self.fig = plt.figure(figsize=self.config.figure_size, layout='constrained')
        self.fig.patch.set_facecolor(self.config.background_color)

        # Store figure number for later reference
        self._fig_num = self.fig.number

        # Initialize layout manager
        self.layout_manager = LayoutManager(self.fig)

        # Apply initial QUAD layout
        self._apply_layout(LayoutMode.QUAD)

        logging.info("Display initialized with 4 panels")

    def _apply_layout(self, mode: LayoutMode, expanded_panel: Optional[int] = None) -> None:
        """
        Apply a new layout, recreating axes as needed.

        Args:
            mode: QUAD or EXPANDED
            expanded_panel: Panel to expand (for EXPANDED mode)
        """
        # Clear existing axes if any
        for panel_idx in list(self.axes.keys()):
            self.axes[panel_idx].remove()
        self.axes.clear()
        self.artists.clear()

        # Get new geometries from layout manager
        geometries = self.layout_manager.transition_to(mode, expanded_panel)
        gs = self.layout_manager.create_gridspec(mode)

        # Create new axes based on geometries
        for panel_idx in range(4):
            geom = geometries[panel_idx]
            scale = PANEL_SCALE_MAPPING[panel_idx]

            if mode == LayoutMode.QUAD:
                # Standard 2x2 layout
                row = panel_idx // 2
                col = panel_idx % 2
                ax = self.fig.add_subplot(gs[row, col])
            else:
                # EXPANDED mode: use geometry slices
                ax = self.fig.add_subplot(
                    gs[geom.row_start:geom.row_start + geom.row_span,
                       geom.col_start:geom.col_start + geom.col_span]
                )

            self.axes[panel_idx] = ax
            self._panel_geometries[panel_idx] = geom

            # Configure appearance based on whether it's a mini panel
            self._configure_panel_appearance(ax, panel_idx, geom.is_mini)

            # Initialize artist collections
            self.artists[panel_idx] = {
                'candlesticks': [],
                'levels': [],
                'events': [],
                'current_bar': None
            }

        # Force redraw
        self.fig.canvas.draw_idle()

    def _configure_panel_appearance(self, ax, panel_idx: int, is_mini: bool) -> None:
        """
        Configure axis appearance based on whether it's a mini panel.

        Args:
            ax: Matplotlib axis
            panel_idx: Panel index (0-3)
            is_mini: True if this is a mini summary panel
        """
        scale = PANEL_SCALE_MAPPING[panel_idx]
        ax.set_facecolor(self.config.background_color)

        if is_mini:
            # Simplified view for mini panels
            ax.set_title(f"{scale}", color=self.config.text_color, fontsize=8)
            ax.tick_params(labelsize=6, colors=self.config.text_color)
            ax.grid(False)  # No grid on mini panels for cleaner look
        else:
            # Full view
            ax.grid(True, color=self.config.grid_color, alpha=0.3)
            ax.tick_params(colors=self.config.text_color)

            # Set title with scale, resolution, and boundaries
            scale_range = self.scale_config.boundaries.get(scale, (0, "inf"))
            aggregation = self.scale_config.aggregations.get(scale, 1)
            resolution_label = self._format_resolution(aggregation)
            ax.set_title(
                f"{scale} Scale | {resolution_label} | {scale_range[0]:.1f}-{scale_range[1]} pts",
                color=self.config.text_color,
                fontsize=11,
                fontweight='bold'
            )

    def expand_panel(self, panel_idx: int) -> None:
        """
        Expand specified panel to ~90% view.

        Args:
            panel_idx: Panel index (0-3) to expand
        """
        if self.layout_manager is None:
            return
        self._apply_layout(LayoutMode.EXPANDED, panel_idx)
        logging.info(f"Expanded panel {panel_idx} ({PANEL_SCALE_MAPPING[panel_idx]} scale)")

    def restore_quad_layout(self) -> None:
        """Return to standard 2x2 layout."""
        if self.layout_manager is None:
            return
        self._apply_layout(LayoutMode.QUAD)
        logging.info("Restored QUAD layout")

    def toggle_panel_expand(self, panel_idx: int) -> None:
        """
        Toggle expansion of a panel.

        If already expanded, returns to QUAD. Otherwise expands the panel.

        Args:
            panel_idx: Panel index (0-3) to toggle
        """
        if self.layout_manager is None:
            return

        current_mode = self.layout_manager.get_current_mode()
        expanded = self.layout_manager.get_expanded_panel()

        if current_mode == LayoutMode.EXPANDED and expanded == panel_idx:
            self.restore_quad_layout()
        else:
            self.expand_panel(panel_idx)
    
    def update_display(self,
                      current_bar_idx: int,
                      active_swings: List[ActiveSwing],
                      recent_events: List[StructuralEvent],
                      highlighted_events: Optional[List[StructuralEvent]] = None) -> None:
        """
        Update all panels with current market state.

        Implements frame skipping for high-speed playback: if updates are requested
        faster than min_render_interval_ms, intermediate frames are skipped and only
        the latest state is rendered when the interval allows.

        Args:
            current_bar_idx: Current position in source bar timeline
            active_swings: All active swings across scales from SwingStateManager
            recent_events: Recent structural events for highlighting
            highlighted_events: Specific events to emphasize (e.g., major events)
        """
        if self.fig is None:
            self.initialize_display()

        self._updates_requested += 1
        current_time = time.time()

        # Frame skipping logic
        if self.config.enable_frame_skipping:
            time_since_last_ms = (current_time - self._last_render_time) * 1000
            if time_since_last_ms < self.config.min_render_interval_ms:
                # Too soon to render - store pending update for later
                self._pending_update = (current_bar_idx, active_swings, recent_events, highlighted_events)
                self._frames_skipped += 1
                return

        # Use pending update if available (ensures we render latest state after skip)
        if self._pending_update is not None:
            current_bar_idx, active_swings, recent_events, highlighted_events = self._pending_update
            self._pending_update = None

        self._last_render_time = current_time
        self.current_bar_idx = current_bar_idx
        self.last_events = recent_events

        # Group swings by scale
        swings_by_scale = self._group_swings_by_scale(active_swings)
        events_by_scale = self._group_events_by_scale(recent_events)
        
        # Update each panel
        for panel_idx in range(4):
            scale = PANEL_SCALE_MAPPING[panel_idx]
            scale_swings = swings_by_scale.get(scale, [])
            scale_events = events_by_scale.get(scale, [])
            
            # Calculate view window for this scale
            view_window = self.calculate_view_window(scale, current_bar_idx, scale_swings)
            self.view_windows[scale] = view_window
            
            # Render the panel
            self.render_panel(panel_idx, scale, view_window, scale_swings, scale_events)
        
        # Update panel annotations
        for panel_idx in range(4):
            scale = PANEL_SCALE_MAPPING[panel_idx]
            swing_count = len(swings_by_scale.get(scale, []))
            latest_event = None
            
            scale_events = events_by_scale.get(scale, [])
            if scale_events:
                latest_event = max(scale_events, key=lambda e: e.source_bar_idx)
            
            self.update_panel_annotations(panel_idx, scale, swing_count, latest_event)
        
        # Refresh display
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()  # Process GUI events to keep window responsive
        self.update_count += 1

        if self.update_count % 100 == 0:
            logging.debug(f"Display updated {self.update_count} times")
    
    def render_panel(self,
                    panel_idx: int,
                    scale: str,
                    view_window: ViewWindow,
                    scale_swings: List[ActiveSwing],
                    scale_events: List[StructuralEvent]) -> None:
        """
        Render a single scale panel with OHLC bars and structural overlays.

        Args:
            panel_idx: Subplot index (0-3)
            scale: Scale identifier (S, M, L, XL)
            view_window: Time/price range to display
            scale_swings: Active swings for this scale
            scale_events: Recent events for this scale
        """
        ax = self.axes[panel_idx]

        # Clear previous artists
        self._clear_panel_artists(panel_idx)

        # Get aggregated bars for this scale
        timeframe = self.scale_config.aggregations.get(scale, 1)
        try:
            aggregated_bars = self.bar_aggregator.get_bars(timeframe)
        except Exception as e:
            logging.warning(f"Could not get bars for {scale} scale timeframe {timeframe}: {e}")
            return

        # Filter bars to view window
        visible_bars = self._get_visible_bars(aggregated_bars, view_window)
        if not visible_bars:
            return

        # Draw OHLC bars (drawn at local indices 0 to N-1)
        self.draw_price_bars(panel_idx, visible_bars, self.current_bar_idx)

        # Apply swing visibility filtering (Issue #12)
        visible_swings = self.swing_visibility.get_visible_swings(panel_idx, scale_swings)

        # Draw Fibonacci levels for each visible swing with opacity
        # Pass num_visible for label positioning in local coordinates
        for swing in visible_swings:
            opacity = self.swing_visibility.get_swing_opacity(swing, panel_idx)
            if opacity > 0:
                self.draw_fibonacci_levels(
                    panel_idx, swing, view_window,
                    num_visible=len(visible_bars),
                    opacity=opacity
                )

        # Update PiP inset if primary swing is out of view (Issue #12)
        primary_swing = self._get_primary_swing(scale_swings)
        if primary_swing:
            self.pip_manager.update_pip(
                parent_ax=ax,
                panel_idx=panel_idx,
                swing=primary_swing,
                view_window=view_window,
                aggregated_bars=aggregated_bars,
                timeframe=timeframe
            )

        # Draw event markers - pass timeframe for source-to-aggregated translation
        if scale_events:
            self.draw_event_markers(panel_idx, scale_events, view_window, timeframe)

        # Set axis limits - use local drawing coordinates (0 to N)
        # Bars are drawn at positions 0, 1, 2, ..., N-1
        num_visible = len(visible_bars)
        ax.set_xlim(-0.5, num_visible - 0.5)  # Add margin for bar width
        ax.set_ylim(view_window.price_min, view_window.price_max)

        # Configure time-based X-axis labels
        self._configure_time_axis(ax, visible_bars, view_window, timeframe)
    
    def draw_price_bars(self,
                       panel_idx: int,
                       bars: List[Bar],
                       current_bar_idx: int) -> None:
        """Draw OHLC candlestick bars with current bar highlighted."""
        if not bars:
            return
            
        ax = self.axes[panel_idx]
        scale = PANEL_SCALE_MAPPING[panel_idx]
        colors = get_scale_colors(self.config, scale)
        
        candlesticks = []
        
        for i, bar in enumerate(bars):
            # Determine bar color
            if bar.close >= bar.open:
                color = colors["bullish"]
                edge_color = colors["bullish"]
            else:
                color = colors["bearish"]
                edge_color = colors["bearish"]
            
            # Highlight current bar with thicker border
            line_width = 2.0 if i == len(bars) - 1 else 1.0
            
            # Draw candlestick body
            body_height = abs(bar.close - bar.open)
            body_bottom = min(bar.open, bar.close)
            
            # Create body rectangle
            body = Rectangle(
                (i - 0.3, body_bottom),
                0.6, body_height,
                facecolor=color,
                edgecolor=edge_color,
                linewidth=line_width,
                alpha=0.8
            )
            ax.add_patch(body)
            candlesticks.append(body)
            
            # Draw wicks
            # Upper wick
            if bar.high > max(bar.open, bar.close):
                upper_wick = ax.plot([i, i], [max(bar.open, bar.close), bar.high], 
                                   color=edge_color, linewidth=line_width)[0]
                candlesticks.append(upper_wick)
            
            # Lower wick
            if bar.low < min(bar.open, bar.close):
                lower_wick = ax.plot([i, i], [bar.low, min(bar.open, bar.close)], 
                                   color=edge_color, linewidth=line_width)[0]
                candlesticks.append(lower_wick)
        
        self.artists[panel_idx]['candlesticks'] = candlesticks
    
    def draw_fibonacci_levels(self,
                             panel_idx: int,
                             swing: ActiveSwing,
                             view_window: ViewWindow,
                             num_visible: int = 100,
                             opacity: float = 1.0) -> None:
        """
        Draw horizontal lines for all Fibonacci levels of a swing.

        Level styling:
        - Solid lines: Key levels (0, 1, 2)
        - Dashed lines: Retracement levels (0.382, 0.5, 0.618)
        - Dotted lines: Extension levels (1.382, 1.5, 1.618)
        - Bold lines: Critical levels (-0.1, 2)

        Args:
            panel_idx: Panel index to draw on
            swing: Active swing with Fibonacci levels
            view_window: View window for price range filtering
            num_visible: Number of visible bars (for local X coordinate positioning)
            opacity: Opacity multiplier for visibility control (0.0 to 1.0)
        """
        if not swing.levels:
            return

        ax = self.axes[panel_idx]
        scale = PANEL_SCALE_MAPPING[panel_idx]
        colors = get_scale_colors(self.config, scale)

        level_lines = []

        # Calculate effective alpha (base alpha * opacity)
        effective_alpha = self.config.level_alpha * opacity

        for level_name, level_price in swing.levels.items():
            # Skip levels outside view window
            if level_price < view_window.price_min or level_price > view_window.price_max:
                continue

            # Get color and line style
            color = colors["levels"].get(level_name, self.config.text_color)
            line_style = LEVEL_LINE_STYLES.get(level_name, "-")

            # Adjust line width for critical levels
            line_width = self.config.level_line_width
            if level_name in ["-0.1", "2.0"]:
                line_width *= 2.0

            # Draw horizontal line across view window
            line = ax.axhline(
                y=level_price,
                color=color,
                linestyle=line_style,
                linewidth=line_width,
                alpha=effective_alpha,
                label=f"{swing.swing_id[:8]}-{level_name}"
            )
            level_lines.append(line)

            # Add level label on right side (use local coordinates)
            # Bars are drawn at 0 to num_visible-1, place label near right edge
            label_x = num_visible - 1 - num_visible * 0.02
            ax.text(
                label_x, level_price,
                level_name,
                color=color,
                fontsize=8,
                ha='right',
                va='center',
                alpha=effective_alpha
            )

        self.artists[panel_idx]['levels'].extend(level_lines)
    
    def draw_event_markers(self,
                          panel_idx: int,
                          events: List[StructuralEvent],
                          view_window: ViewWindow,
                          timeframe: int = 1) -> None:
        """
        Draw event markers on the chart.

        Marker types:
        - Triangle up: Level cross up
        - Triangle down: Level cross down
        - Star: Completion
        - X: Invalidation

        Args:
            panel_idx: Panel index to draw on
            events: List of structural events to mark
            view_window: Current view window (in aggregated bar space)
            timeframe: Timeframe in minutes for this scale (for index translation)
        """
        if not events:
            return

        ax = self.axes[panel_idx]
        event_artists = []

        for event in events:
            # Translate event's source bar index to aggregated bar index
            agg_bar = self.bar_aggregator.get_bar_at_source_time(timeframe, event.source_bar_idx)
            if agg_bar is None:
                continue

            event_agg_idx = agg_bar.index

            # Skip events outside view window (in aggregated space)
            if (event_agg_idx < view_window.start_idx or
                event_agg_idx > view_window.end_idx):
                continue

            # Get marker style
            marker = EVENT_MARKERS.get(event.event_type.value, "o")

            # Get color based on severity
            if event.severity == EventSeverity.MAJOR:
                color = self.config.major_event_color
                size = self.config.event_marker_size * 1.5
            else:
                color = self.config.minor_event_color
                size = self.config.event_marker_size

            # Calculate position in local drawing coordinates
            # Bars are drawn at positions 0, 1, 2, ... so translate agg_idx to local
            x_pos = event_agg_idx - view_window.start_idx
            y_pos = event.level_price

            # Draw marker
            marker_artist = ax.scatter(
                x_pos, y_pos,
                marker=marker,
                c=color,
                s=size,
                alpha=0.8,
                zorder=10  # Ensure markers appear on top
            )
            event_artists.append(marker_artist)

        self.artists[panel_idx]['events'].extend(event_artists)
    
    def calculate_view_window(self,
                             scale: str,
                             source_bar_idx: int,
                             active_swings: List[ActiveSwing]) -> ViewWindow:
        """
        Calculate optimal view window for a scale panel.

        Logic:
        - Time range: Show last max_visible_bars in AGGREGATED space
        - Price range: Include all active swing extremes + 5% margin
        - Auto-scaling: Adjust for current price action

        IMPORTANT: source_bar_idx is in source (1-minute) bar space.
        We must translate it to aggregated bar space for each timeframe.
        """
        # Get timeframe for this scale
        timeframe = self.scale_config.aggregations.get(scale, 1)

        # CRITICAL FIX: Translate source bar index to aggregated bar index
        # This ensures all panels are synchronized to the same wall-clock time
        agg_bar = self.bar_aggregator.get_bar_at_source_time(timeframe, source_bar_idx)
        if agg_bar is not None:
            # Use the aggregated bar's index for view window calculation
            current_agg_idx = agg_bar.index
        else:
            # Fallback: if no mapping exists yet, use 0
            current_agg_idx = 0

        # Calculate time window in AGGREGATED bar space
        start_idx = max(0, current_agg_idx - self.config.max_visible_bars)
        end_idx = current_agg_idx + 10  # Small lookahead for clarity

        try:
            # Get bars for price range calculation
            aggregated_bars = self.bar_aggregator.get_bars(timeframe)
            visible_bars = [
                bar for i, bar in enumerate(aggregated_bars)
                if start_idx <= i <= end_idx
            ]
            
            if not visible_bars:
                # Fallback to default range
                return ViewWindow(
                    start_idx=start_idx,
                    end_idx=end_idx,
                    price_min=4000.0,
                    price_max=4200.0,
                    scale=scale
                )
            
            # Calculate price range from bars
            bar_lows = [bar.low for bar in visible_bars]
            bar_highs = [bar.high for bar in visible_bars]
            
            price_min = min(bar_lows)
            price_max = max(bar_highs)
            
            # Expand range to include swing extremes
            for swing in active_swings:
                if swing.scale == scale:
                    price_min = min(price_min, swing.low_price)
                    price_max = max(price_max, swing.high_price)
                    
                    # Include all level prices
                    if swing.levels:
                        level_prices = list(swing.levels.values())
                        price_min = min(price_min, min(level_prices))
                        price_max = max(price_max, max(level_prices))
            
            # Add 5% margin
            price_range = price_max - price_min
            margin = price_range * 0.05
            price_min -= margin
            price_max += margin
            
        except Exception as e:
            logging.warning(f"Error calculating view window for {scale}: {e}")
            # Fallback values
            price_min = 4000.0
            price_max = 4200.0
        
        return ViewWindow(
            start_idx=start_idx,
            end_idx=end_idx,
            price_min=price_min,
            price_max=price_max,
            scale=scale
        )
    
    def update_panel_annotations(self,
                                panel_idx: int,
                                scale: str,
                                swing_count: int,
                                latest_event: Optional[StructuralEvent]) -> None:
        """Update panel title and status annotations."""
        ax = self.axes[panel_idx]

        # Get resolution info
        aggregation = self.scale_config.aggregations.get(scale, 1)
        resolution_label = self._format_resolution(aggregation)

        # Build status line
        swing_status = f"{swing_count} swing{'s' if swing_count != 1 else ''}" if swing_count > 0 else "No active swings"

        status_parts = [swing_status]
        if latest_event:
            status_parts.append(f"Last: {latest_event.event_type.value}")

        status_text = " | ".join(status_parts)

        # Update title with scale, resolution, boundaries, and status
        scale_range = self.scale_config.boundaries.get(scale, (0, "inf"))
        title = f"{scale} Scale | {resolution_label} | {scale_range[0]:.1f}-{scale_range[1]} pts\n{status_text}"

        ax.set_title(
            title,
            color=self.config.text_color,
            fontsize=10,
            fontweight='bold'
        )
    
    def set_interactive_mode(self, enabled: bool) -> None:
        """Enable/disable matplotlib interactive features for performance."""
        if enabled:
            plt.ion()  # Interactive mode on
        else:
            plt.ioff()  # Interactive mode off

    def show_display(self) -> None:
        """
        Make the figure window visible.

        Must be called after initialize_display() to actually show the matplotlib
        window on screen. Uses non-blocking show to allow the CLI to remain
        interactive while the visualization is displayed.

        On macOS, this requires a GUI backend (TkAgg, MacOSX, Qt5Agg) to be
        configured before any matplotlib figures are created.
        """
        if self.fig is None:
            logging.warning("Cannot show display: figure not initialized")
            return

        # Ensure the figure is the current figure
        plt.figure(self._fig_num)

        # Show the figure in non-blocking mode
        # This creates the window and starts the GUI event loop in the background
        plt.show(block=False)

        # Force an initial draw to ensure the window appears
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

        logging.info("Visualization window displayed")
    
    # Helper methods
    
    def _group_swings_by_scale(self, swings: List[ActiveSwing]) -> Dict[str, List[ActiveSwing]]:
        """Group swings by their scale."""
        groups = {}
        for swing in swings:
            scale = swing.scale
            if scale not in groups:
                groups[scale] = []
            groups[scale].append(swing)
        return groups
    
    def _group_events_by_scale(self, events: List[StructuralEvent]) -> Dict[str, List[StructuralEvent]]:
        """Group events by their scale."""
        groups = {}
        for event in events:
            scale = event.scale
            if scale not in groups:
                groups[scale] = []
            groups[scale].append(event)
        return groups
    
    def _get_visible_bars(self, bars: List[Bar], view_window: ViewWindow) -> List[Bar]:
        """Filter bars to view window time range."""
        return bars[view_window.start_idx:view_window.end_idx + 1]
    
    def _clear_panel_artists(self, panel_idx: int) -> None:
        """Clear all artists from a panel for redraw."""
        artists = self.artists[panel_idx]

        def safe_remove(artist):
            """Safely remove an artist, handling cases where it's already removed."""
            try:
                if hasattr(artist, 'remove'):
                    # Check if artist is still in an axes before removing
                    # This prevents "list.remove(x): x not in list" errors
                    if hasattr(artist, 'axes') and artist.axes is not None:
                        artist.remove()
                    elif hasattr(artist, 'figure') and artist.figure is not None:
                        artist.remove()
            except (ValueError, AttributeError):
                # Artist was already removed or not properly attached
                pass

        # Remove candlesticks
        for artist in artists['candlesticks']:
            safe_remove(artist)
        artists['candlesticks'].clear()

        # Remove level lines
        for line in artists['levels']:
            safe_remove(line)
        artists['levels'].clear()

        # Remove event markers
        for marker in artists['events']:
            safe_remove(marker)
        artists['events'].clear()
    
    def get_scale_colors(self, scale: str) -> Dict[str, str]:
        """Get color scheme for a specific scale (darker colors for larger scales)."""
        return get_scale_colors(self.config, scale)

    def _format_resolution(self, minutes: int) -> str:
        """Format aggregation minutes into human-readable resolution label."""
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours}h"
        else:
            days = minutes // 1440
            return f"{days}d"

    def _configure_time_axis(self, ax, visible_bars: List[Bar], view_window: ViewWindow, timeframe: int) -> None:
        """
        Configure X-axis to show time-based labels instead of bar indices.

        Args:
            ax: Matplotlib axis
            visible_bars: List of visible Bar objects with timestamps
            view_window: Current view window
            timeframe: Aggregation timeframe in minutes
        """
        if not visible_bars:
            return

        # Get timestamps from visible bars
        num_bars = len(visible_bars)

        # Select appropriate tick positions (aim for 4-6 ticks)
        if num_bars <= 6:
            tick_step = 1
        elif num_bars <= 20:
            tick_step = max(1, num_bars // 5)
        else:
            tick_step = max(1, num_bars // 5)

        tick_positions = list(range(0, num_bars, tick_step))
        # Ensure last bar is included
        if tick_positions[-1] != num_bars - 1:
            tick_positions.append(num_bars - 1)

        # Build tick labels from timestamps
        tick_labels = []
        for pos in tick_positions:
            if pos < len(visible_bars):
                bar = visible_bars[pos]
                ts = datetime.fromtimestamp(bar.timestamp)
                # Format based on timeframe
                if timeframe < 60:
                    # For minute data: show HH:MM
                    label = ts.strftime("%H:%M")
                elif timeframe < 1440:
                    # For hourly data: show MM-DD HH:MM
                    label = ts.strftime("%m-%d %H:%M")
                else:
                    # For daily data: show YYYY-MM-DD
                    label = ts.strftime("%Y-%m-%d")
                tick_labels.append(label)
            else:
                tick_labels.append("")

        # Set the ticks and labels
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=8)

        # Add time range info to the axis
        if visible_bars:
            first_ts = datetime.fromtimestamp(visible_bars[0].timestamp)
            last_ts = datetime.fromtimestamp(visible_bars[-1].timestamp)
            ax.set_xlabel(
                f"{first_ts.strftime('%Y-%m-%d %H:%M')} to {last_ts.strftime('%Y-%m-%d %H:%M')}",
                color=self.config.text_color,
                fontsize=8
            )

    def get_figure(self) -> Optional['Figure']:
        """
        Return the matplotlib Figure for external event binding.

        Returns:
            The matplotlib Figure object, or None if not initialized
        """
        return self.fig

    def get_render_stats(self) -> Dict[str, Any]:
        """
        Return rendering performance statistics.

        Returns:
            Dictionary with:
            - updates_requested: Total update_display() calls
            - updates_rendered: Actual renders performed
            - frames_skipped: Frames skipped due to throttling
            - skip_rate: Percentage of frames skipped (0-100)
        """
        skip_rate = 0.0
        if self._updates_requested > 0:
            skip_rate = (self._frames_skipped / self._updates_requested) * 100

        return {
            'updates_requested': self._updates_requested,
            'updates_rendered': self.update_count,
            'frames_skipped': self._frames_skipped,
            'skip_rate': skip_rate,
        }

    def update_status_overlay(self, status_text: str) -> None:
        """
        Update the status text overlay in the figure corner.

        Displays playback state, current bar, and speed information.

        Args:
            status_text: Text to display (e.g., "[PLAYING 2x] Bar 1234/5000")
        """
        if self.fig is None:
            return

        if self._status_text is None:
            # Create status text in top-left corner
            self._status_text = self.fig.text(
                0.02, 0.98, status_text,
                transform=self.fig.transFigure,
                fontsize=10,
                verticalalignment='top',
                horizontalalignment='left',
                color='#FFD700',  # Gold color for visibility
                fontweight='bold',
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor='#1E1E1E',
                    edgecolor='#FFD700',
                    alpha=0.9
                )
            )
        else:
            # Update existing text
            self._status_text.set_text(status_text)

        # Redraw the status area
        self.fig.canvas.draw_idle()

    def _get_primary_swing(self, swings: List[ActiveSwing]) -> Optional[ActiveSwing]:
        """
        Get the primary (most recent) swing for PiP display.

        The primary swing is typically the one with the most recent timestamp,
        which represents the currently active reference swing.

        Args:
            swings: List of ActiveSwing objects for a scale

        Returns:
            The primary swing, or None if no swings exist
        """
        if not swings:
            return None

        # Return swing with most recent high or low timestamp
        def get_max_timestamp(swing: ActiveSwing) -> int:
            return max(swing.high_timestamp, swing.low_timestamp)

        return max(swings, key=get_max_timestamp)

    # Swing visibility control methods (Issue #12)

    def cycle_visibility_mode(self) -> VisibilityMode:
        """
        Cycle visibility mode for all scales.

        Returns:
            New visibility mode
        """
        return self.swing_visibility.cycle_mode_all_scales()

    def cycle_next_swing(self, panel_idx: int, swings: List[ActiveSwing]) -> Optional[str]:
        """
        Select the next swing in SINGLE mode for a panel.

        Args:
            panel_idx: Panel index (0-3)
            swings: List of swings for this panel

        Returns:
            ID of newly selected swing
        """
        return self.swing_visibility.cycle_next(panel_idx, swings)

    def cycle_previous_swing(self, panel_idx: int, swings: List[ActiveSwing]) -> Optional[str]:
        """
        Select the previous swing in SINGLE mode for a panel.

        Args:
            panel_idx: Panel index (0-3)
            swings: List of swings for this panel

        Returns:
            ID of newly selected swing
        """
        return self.swing_visibility.cycle_previous(panel_idx, swings)

    def get_visibility_status(self, panel_idx: int, swings: List[ActiveSwing]) -> str:
        """
        Get visibility status summary for a panel.

        Args:
            panel_idx: Panel index (0-3)
            swings: List of swings for this panel

        Returns:
            Status string describing current visibility mode and selection
        """
        return self.swing_visibility.get_status_summary(panel_idx, swings)

    def record_swing_event(self, event: Any, scale: int) -> None:
        """
        Record an event for visibility highlighting.

        Args:
            event: Structural event
            scale: Scale index (0-3)
        """
        self.swing_visibility.record_event(event, scale)