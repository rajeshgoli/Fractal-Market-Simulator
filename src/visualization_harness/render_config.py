"""
Visualization Configuration Module

Provides configuration classes and constants for the visualization renderer,
including color schemes, styling options, and layout parameters.

Author: Generated for Market Simulator Project
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional


@dataclass
class ViewWindow:
    """Defines the visible time/price range for a panel."""
    start_idx: int           # Starting bar index
    end_idx: int            # Ending bar index
    price_min: float        # Minimum price to display
    price_max: float        # Maximum price to display
    scale: str              # S, M, L, XL


@dataclass
class RenderConfig:
    """Configuration for visualization appearance and behavior."""
    
    # Panel layout
    panel_rows: int = 2
    panel_cols: int = 2
    figure_size: Tuple[int, int] = (16, 12)
    
    # Color scheme
    bullish_color: str = "#26A69A"
    bearish_color: str = "#EF5350"
    background_color: str = "#1E1E1E"
    grid_color: str = "#333333"
    text_color: str = "#FFFFFF"
    
    # Level styling
    level_colors: Optional[Dict[str, str]] = None
    level_line_width: float = 1.0
    level_alpha: float = 0.7
    
    # Event highlighting
    major_event_color: str = "#FFD700"
    minor_event_color: str = "#87CEEB"
    event_marker_size: int = 8
    
    # Performance settings
    max_visible_bars: int = 500  # Sliding window size

    # Frame skipping for high-speed playback
    enable_frame_skipping: bool = True
    min_render_interval_ms: int = 60  # ~16 FPS max, skip renders faster than this

    # Swing cap settings (Issue #12 Phase 1)
    max_swings_per_scale: int = 5  # Max swings to display per scale (0 = show all)
    show_all_swings: bool = False  # Toggle state for bypassing swing cap

    def __post_init__(self):
        """Initialize default level colors if not provided."""
        if self.level_colors is None:
            self.level_colors = {
                # Critical levels
                "-0.1": "#FF4444",     # Stop level - bright red
                "2.0": "#FF6600",      # Exhaustion - orange
                
                # Key structural levels
                "0": "#FFFFFF",        # Swing extreme - white
                "1.0": "#00FF00",      # Par - green
                
                # Retracement levels
                "0.382": "#FFFF99",    # Light yellow
                "0.5": "#CCFF99",      # Light green
                "0.618": "#99FFCC",    # Light cyan
                
                # Support/resistance
                "0.1": "#99CCFF",      # Light blue
                "0.9": "#CC99FF",      # Light purple
                "1.1": "#FFCC99",      # Light orange
                
                # Decision zone
                "1.382": "#FF99CC",    # Light pink
                "1.5": "#CCCCCC",      # Light gray
                "1.618": "#FFCCFF",    # Light magenta
            }


# Color schemes for different scales (darker colors for larger scales)
SCALE_COLOR_MULTIPLIERS = {
    "S": 1.0,      # Full brightness for S scale
    "M": 0.85,     # Slightly darker for M scale
    "L": 0.7,      # Darker for L scale
    "XL": 0.55     # Darkest for XL scale
}

# Line style mappings for level types
LEVEL_LINE_STYLES = {
    # Key levels - solid lines
    "-0.1": "-",
    "0": "-",
    "1.0": "-",
    "2.0": "-",
    
    # Retracement levels - dashed lines
    "0.382": "--",
    "0.5": "--",
    "0.618": "--",
    
    # Support/resistance - dotted lines
    "0.1": ":",
    "0.9": ":",
    "1.1": ":",
    
    # Decision zone - dash-dot lines
    "1.382": "-.",
    "1.5": "-.",
    "1.618": "-.",
}

# Event marker mappings
EVENT_MARKERS = {
    "level_cross_up": "^",      # Triangle up
    "level_cross_down": "v",    # Triangle down
    "completion": "*",          # Star
    "invalidation": "x",        # X mark
}

# Panel scale mapping (for 2x2 layout)
PANEL_SCALE_MAPPING = {
    0: "S",   # Top-left
    1: "M",   # Top-right
    2: "L",   # Bottom-left
    3: "XL"   # Bottom-right
}

def get_scale_colors(config: RenderConfig, scale: str) -> Dict[str, str]:
    """
    Get color scheme for a specific scale with appropriate brightness.
    
    Args:
        config: Base render configuration
        scale: Scale identifier (S, M, L, XL)
        
    Returns:
        Dictionary of adjusted colors for the scale
    """
    multiplier = SCALE_COLOR_MULTIPLIERS.get(scale, 1.0)
    
    def adjust_color(hex_color: str, factor: float) -> str:
        """Adjust hex color brightness by factor."""
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Convert to RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Apply factor
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        
        # Clamp to valid range
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        
        return f"#{r:02x}{g:02x}{b:02x}"
    
    # Adjust level colors
    adjusted_level_colors = {}
    for level, color in config.level_colors.items():
        adjusted_level_colors[level] = adjust_color(color, multiplier)
    
    return {
        "bullish": adjust_color(config.bullish_color, multiplier),
        "bearish": adjust_color(config.bearish_color, multiplier),
        "levels": adjusted_level_colors
    }