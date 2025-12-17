"""
Reference Swing Detector

Detects valid bull and bear reference swings from OHLC price data.

Bull Reference Swing: A completed bear leg (high followed by low) that the 
current market is actively countering from below.

Bear Reference Swing: A completed bull leg (low followed by high) that the 
current market is actively countering from above.

Bull Algorithm:
1. Finds swing lows (local minima) using configurable lookback window
2. For each swing low, scans backward to find all bear legs feeding into it
3. Filters by retracement validity (current price between 0.382 and 2x)
4. Filters by low protection (swing low not violated beyond tolerance)
5. Applies subsumption to remove redundant swings

Bear Algorithm (symmetric):
1. Finds swing highs (local maxima) using configurable lookback window
2. For each swing high, scans backward to find all bull legs feeding into it
3. Filters by retracement validity (current price between -0.382 and -2x of swing)
4. Filters by high protection (swing high not violated beyond tolerance)
5. Applies subsumption to remove redundant swings

Both preserve:
- Largest swing per anchor point
- Most explosive swings (high speed)
- Swings whose termination is also a swing point
- Most recent swing for immediate context

Author: Generated for Market Simulator Project
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class Bar:
    """Single OHLC bar"""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    
    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class BearReferenceSwing:
    """A valid bear reference swing (completed bull leg being countered)"""
    low_index: int
    low_price: float
    low_date: datetime
    high_index: int
    high_price: float
    high_date: datetime
    range: float
    duration: int  # bars from low to high
    speed: float  # points per bar
    is_explosive: bool
    is_swing_low: bool  # low is also a swing low (downswing termination)
    
    # Computed Fibonacci levels
    levels: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        """Compute Fibonacci levels after initialization"""
        self._compute_levels()
    
    def _compute_levels(self):
        """Compute all structural levels for this swing (measured from high downward)"""
        high = self.high_price
        r = self.range
        
        self.levels = {
            '-0.1': high + 0.1 * r,  # above high (stop level)
            '0': high,  # swing high
            '0.1': high - 0.1 * r,
            '0.382': high - 0.382 * r,
            '0.5': high - 0.5 * r,
            '0.618': high - 0.618 * r,
            '0.9': high - 0.9 * r,
            '1': high - r,  # swing low
            '1.1': high - 1.1 * r,
            '1.382': high - 1.382 * r,
            '1.5': high - 1.5 * r,
            '1.618': high - 1.618 * r,
            '2': high - 2.0 * r,  # 2x extension (bear move completion)
        }
    
    def get_retracement(self, current_price: float) -> float:
        """Get current price as retracement level (0 = high, 1 = low, 2 = 2x down)"""
        return (self.high_price - current_price) / self.range
    
    def get_zone(self, current_price: float) -> str:
        """Get descriptive zone for current price position"""
        ret = self.get_retracement(current_price)
        
        if ret < 0:
            return "ABOVE_HIGH"
        elif ret < 0.382:
            return "INVALID_RETRACEMENT"
        elif ret < 1.0:
            return "ABOVE_LOW"
        elif ret < 1.382:
            return "BUILDING_1_TO_1382"
        elif ret < 1.618:
            return "DECISION_ZONE"
        elif ret < 2.0:
            return "LIQUIDITY_VOID"
        else:
            return "EXHAUSTION"
    
    def __repr__(self):
        markers = []
        if self.is_explosive:
            markers.append("EXPLOSIVE")
        if self.is_swing_low:
            markers.append("SWING-LOW")
        marker_str = f" [{', '.join(markers)}]" if markers else ""
        
        return (f"BearRef({self.low_price:.2f} -> {self.high_price:.2f}, "
                f"range={self.range:.2f}, speed={self.speed:.1f}{marker_str})")


@dataclass
class BullReferenceSwing:
    """A valid bull reference swing (completed bear leg being countered)"""
    high_index: int
    high_price: float
    high_date: datetime
    low_index: int
    low_price: float
    low_date: datetime
    range: float
    duration: int  # bars from high to low
    speed: float  # points per bar
    is_explosive: bool
    is_swing_high: bool  # high is also a swing high (upswing termination)
    
    # Computed Fibonacci levels
    levels: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        """Compute Fibonacci levels after initialization"""
        self._compute_levels()
    
    def _compute_levels(self):
        """Compute all structural levels for this swing"""
        low = self.low_price
        r = self.range
        
        self.levels = {
            '-0.1': low - 0.1 * r,
            '0': low,
            '0.1': low + 0.1 * r,
            '0.382': low + 0.382 * r,
            '0.5': low + 0.5 * r,
            '0.618': low + 0.618 * r,
            '0.9': low + 0.9 * r,
            '1': low + r,  # swing high
            '1.1': low + 1.1 * r,
            '1.382': low + 1.382 * r,
            '1.5': low + 1.5 * r,
            '1.618': low + 1.618 * r,
            '2': low + 2.0 * r,  # 2x extension (bull move completion)
        }
    
    def get_retracement(self, current_price: float) -> float:
        """Get current price as retracement level (0 = low, 1 = high, 2 = 2x)"""
        return (current_price - self.low_price) / self.range
    
    def get_zone(self, current_price: float) -> str:
        """Get descriptive zone for current price position"""
        ret = self.get_retracement(current_price)
        
        if ret < 0:
            return "BELOW_LOW"
        elif ret < 0.382:
            return "INVALID_RETRACEMENT"
        elif ret < 1.0:
            return "BELOW_HIGH"
        elif ret < 1.382:
            return "BUILDING_1_TO_1382"
        elif ret < 1.618:
            return "DECISION_ZONE"
        elif ret < 2.0:
            return "LIQUIDITY_VOID"
        else:
            return "EXHAUSTION"
    
    def __repr__(self):
        markers = []
        if self.is_explosive:
            markers.append("EXPLOSIVE")
        if self.is_swing_high:
            markers.append("SWING-HIGH")
        marker_str = f" [{', '.join(markers)}]" if markers else ""
        
        return (f"BullRef({self.high_price:.2f} -> {self.low_price:.2f}, "
                f"range={self.range:.2f}, speed={self.speed:.1f}{marker_str})")


@dataclass
class DetectorConfig:
    """Configuration for the swing detector"""
    # Swing detection
    swing_lookback: int = 1  # bars to look back/forward for swing detection
    min_swing_range: float = 20.0  # minimum range in points to consider

    # Retracement validity
    min_retracement: float = 0.382  # minimum retracement for valid reference
    max_retracement: float = 2.0  # maximum (2x extension)

    # Protection levels
    low_violation_tolerance: float = 0.1  # as fraction of range (for bull swings)
    high_violation_tolerance: float = 0.1  # as fraction of range (for bear swings)

    # Explosive classification
    explosive_speed_threshold: float = 100.0  # points per bar
    explosive_speed_multiplier: float = 2.0  # relative to group average

    # Subsumption
    recent_duration_threshold: int = 3  # bars - keep if within this of low
