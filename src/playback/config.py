"""
Playback Configuration Module

Defines configuration classes and enums for the playback controller,
including playback modes, states, and behavior settings.

Author: Generated for Market Simulator Project
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List


class PlaybackMode(Enum):
    """Playback operation modes."""
    MANUAL = "manual"      # Step-by-step only
    AUTO = "auto"          # Continuous playback
    FAST = "fast"          # Accelerated playback (skip minor events)


class PlaybackState(Enum):
    """Current playback state."""
    STOPPED = "stopped"    # At beginning or reset
    PLAYING = "playing"    # Auto mode active
    PAUSED = "paused"      # Paused (manual intervention or auto-pause)
    FINISHED = "finished"  # Reached end of data


@dataclass
class PlaybackConfig:
    """Configuration for playback behavior."""
    
    # Auto-play settings
    auto_speed_ms: int = 1000           # Milliseconds between auto steps
    fast_speed_ms: int = 200            # Fast playback speed
    
    # Pause behavior
    pause_on_major_events: bool = True  # Auto-pause on MAJOR severity events
    pause_on_completion: bool = True    # Pause on swing completions
    pause_on_invalidation: bool = True  # Pause on swing invalidations
    pause_on_scale_filter: Optional[List[str]] = None  # Pause only for specific scales
    
    # Performance settings
    max_playback_speed_hz: float = 10.0  # Maximum update frequency


@dataclass
class PlaybackStatus:
    """Current playback state information."""
    mode: PlaybackMode
    state: PlaybackState
    current_bar_idx: int
    total_bars: int
    progress_percent: float
    bars_per_second: float              # Current processing rate
    time_remaining_seconds: Optional[float]
    last_pause_reason: Optional[str]
    
    @classmethod
    def create_initial(cls, total_bars: int) -> 'PlaybackStatus':
        """Create initial status for new playback session."""
        return cls(
            mode=PlaybackMode.MANUAL,
            state=PlaybackState.STOPPED,
            current_bar_idx=0,
            total_bars=total_bars,
            progress_percent=0.0,
            bars_per_second=0.0,
            time_remaining_seconds=None,
            last_pause_reason=None
        )