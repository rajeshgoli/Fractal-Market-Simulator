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
from typing import Dict, List, Optional, Tuple
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
        
        logging.info(f"VisualizationRenderer initialized with {len(self.scale_config.boundaries)} scales")
    
    def initialize_display(self) -> None:
        """Setup matplotlib figure and subplots for 4-panel display."""
        # Create figure with dark background
        self.fig = plt.figure(figsize=self.config.figure_size)
        self.fig.patch.set_facecolor(self.config.background_color)
        
        # Create 2x2 subplot grid
        gs = self.fig.add_gridspec(
            self.config.panel_rows, 
            self.config.panel_cols,
            hspace=0.3,
            wspace=0.2
        )
        
        # Initialize each panel
        for panel_idx in range(4):
            row = panel_idx // 2
            col = panel_idx % 2
            scale = PANEL_SCALE_MAPPING[panel_idx]
            
            # Create subplot
            ax = self.fig.add_subplot(gs[row, col])
            self.axes[panel_idx] = ax
            
            # Configure appearance
            ax.set_facecolor(self.config.background_color)
            ax.grid(True, color=self.config.grid_color, alpha=0.3)
            ax.tick_params(colors=self.config.text_color)
            
            # Set title
            scale_range = self.scale_config.boundaries.get(scale, (0, "inf"))
            ax.set_title(
                f"{scale} Scale ({scale_range[0]:.1f} - {scale_range[1]} pts)",
                color=self.config.text_color,
                fontsize=12,
                fontweight='bold'
            )
            
            # Initialize artist collections
            self.artists[panel_idx] = {
                'candlesticks': [],
                'levels': [],
                'events': [],
                'current_bar': None
            }
            
        plt.tight_layout()
        logging.info("Display initialized with 4 panels")
    
    def update_display(self,
                      current_bar_idx: int,
                      active_swings: List[ActiveSwing],
                      recent_events: List[StructuralEvent],
                      highlighted_events: Optional[List[StructuralEvent]] = None) -> None:
        """
        Update all panels with current market state.
        
        Args:
            current_bar_idx: Current position in source bar timeline
            active_swings: All active swings across scales from SwingStateManager
            recent_events: Recent structural events for highlighting
            highlighted_events: Specific events to emphasize (e.g., major events)
        """
        if self.fig is None:
            self.initialize_display()
        
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
        
        # Draw OHLC bars
        self.draw_price_bars(panel_idx, visible_bars, self.current_bar_idx)
        
        # Draw Fibonacci levels for each swing
        for swing in scale_swings:
            self.draw_fibonacci_levels(panel_idx, swing, view_window)
        
        # Draw event markers
        if scale_events:
            self.draw_event_markers(panel_idx, scale_events, view_window)
        
        # Set axis limits
        ax.set_xlim(view_window.start_idx, view_window.end_idx)
        ax.set_ylim(view_window.price_min, view_window.price_max)
    
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
                             view_window: ViewWindow) -> None:
        """
        Draw horizontal lines for all Fibonacci levels of a swing.
        
        Level styling:
        - Solid lines: Key levels (0, 1, 2)
        - Dashed lines: Retracement levels (0.382, 0.5, 0.618)
        - Dotted lines: Extension levels (1.382, 1.5, 1.618)
        - Bold lines: Critical levels (-0.1, 2)
        """
        if not swing.levels:
            return
            
        ax = self.axes[panel_idx]
        scale = PANEL_SCALE_MAPPING[panel_idx]
        colors = get_scale_colors(self.config, scale)
        
        level_lines = []
        
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
                alpha=self.config.level_alpha,
                label=f"{swing.swing_id[:8]}-{level_name}"
            )
            level_lines.append(line)
            
            # Add level label on right side
            label_x = view_window.end_idx - (view_window.end_idx - view_window.start_idx) * 0.02
            ax.text(
                label_x, level_price,
                level_name,
                color=color,
                fontsize=8,
                ha='right',
                va='center',
                alpha=self.config.level_alpha
            )
        
        self.artists[panel_idx]['levels'].extend(level_lines)
    
    def draw_event_markers(self,
                          panel_idx: int,
                          events: List[StructuralEvent],
                          view_window: ViewWindow) -> None:
        """
        Draw event markers on the chart.
        
        Marker types:
        - Triangle up: Level cross up
        - Triangle down: Level cross down  
        - Star: Completion
        - X: Invalidation
        """
        if not events:
            return
            
        ax = self.axes[panel_idx]
        event_artists = []
        
        for event in events:
            # Skip events outside view window
            if (event.source_bar_idx < view_window.start_idx or 
                event.source_bar_idx > view_window.end_idx):
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
            
            # Calculate position
            x_pos = event.source_bar_idx - view_window.start_idx
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
                             current_bar_idx: int,
                             active_swings: List[ActiveSwing]) -> ViewWindow:
        """
        Calculate optimal view window for a scale panel.
        
        Logic:
        - Time range: Show last max_visible_bars
        - Price range: Include all active swing extremes + 5% margin
        - Auto-scaling: Adjust for current price action
        """
        # Calculate time window
        start_idx = max(0, current_bar_idx - self.config.max_visible_bars)
        end_idx = current_bar_idx + 10  # Small lookahead for clarity
        
        # Get timeframe for this scale
        timeframe = self.scale_config.aggregations.get(scale, 1)
        
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
        
        # Build status text
        status_parts = [f"{swing_count} swings"]
        
        if latest_event:
            event_desc = f"Last: {latest_event.event_type.value}"
            status_parts.append(event_desc)
        
        status_text = " | ".join(status_parts)
        
        # Update title to include status
        scale_range = self.scale_config.boundaries.get(scale, (0, "inf"))
        title = f"{scale} Scale ({scale_range[0]:.1f} - {scale_range[1]} pts)\n{status_text}"
        
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
        
        # Remove candlesticks
        for artist in artists['candlesticks']:
            if hasattr(artist, 'remove'):
                artist.remove()
        artists['candlesticks'].clear()
        
        # Remove level lines
        for line in artists['levels']:
            if hasattr(line, 'remove'):
                line.remove()
        artists['levels'].clear()
        
        # Remove event markers
        for marker in artists['events']:
            if hasattr(marker, 'remove'):
                marker.remove()
        artists['events'].clear()
    
    def get_scale_colors(self, scale: str) -> Dict[str, str]:
        """Get color scheme for a specific scale (darker colors for larger scales)."""
        return get_scale_colors(self.config, scale)