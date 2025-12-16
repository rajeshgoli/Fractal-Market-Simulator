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

import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple


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


class BearReferenceDetector:
    """
    Detects bear reference swings from OHLC data.

    This is a thin wrapper around DirectionalReferenceDetector for backward compatibility.

    Usage:
        detector = BearReferenceDetector(config)
        bars = detector.load_csv("data.csv")
        swings = detector.detect(bars, current_price)
    """

    def __init__(self, config: Optional[DetectorConfig] = None):
        from .reference_detector import DirectionalReferenceDetector
        self._impl = DirectionalReferenceDetector("bear", config)
        self.config = self._impl.config

    def load_csv(self, filepath: str, last_n_bars: Optional[int] = None) -> List[Bar]:
        """Load OHLC data from CSV file."""
        return self._impl.load_csv(filepath, last_n_bars)

    def detect(self, bars: List[Bar], current_price: Optional[float] = None) -> List[BearReferenceSwing]:
        """Detect all valid bear reference swings."""
        return self._impl.detect(bars, current_price)

    def print_analysis(self, swings: List[BearReferenceSwing], current_price: float) -> None:
        """Print a formatted analysis of detected bear swings."""
        self._impl.print_analysis(swings, current_price)


class BullReferenceDetector:
    """
    Detects bull reference swings from OHLC data.

    This is a thin wrapper around DirectionalReferenceDetector for backward compatibility.

    Usage:
        detector = BullReferenceDetector(config)
        bars = detector.load_csv("data.csv")
        swings = detector.detect(bars, current_price)
    """

    def __init__(self, config: Optional[DetectorConfig] = None):
        from .reference_detector import DirectionalReferenceDetector
        self._impl = DirectionalReferenceDetector("bull", config)
        self.config = self._impl.config

    def load_csv(self, filepath: str, last_n_bars: Optional[int] = None) -> List[Bar]:
        """Load OHLC data from CSV file."""
        return self._impl.load_csv(filepath, last_n_bars)

    def detect(self, bars: List[Bar], current_price: Optional[float] = None) -> List[BullReferenceSwing]:
        """Detect all valid bull reference swings."""
        return self._impl.detect(bars, current_price)

    def print_analysis(self, swings: List[BullReferenceSwing], current_price: float) -> None:
        """Print a formatted analysis of detected swings."""
        self._impl.print_analysis(swings, current_price)


class ReferenceSwingDetector:
    """
    Unified interface for detecting both bull and bear reference swings.
    
    Usage:
        detector = ReferenceSwingDetector(config)
        bars = detector.load_csv("data.csv")
        bull_swings, bear_swings = detector.detect_all(bars, current_price)
    """
    
    def __init__(self, config: Optional[DetectorConfig] = None):
        self.config = config or DetectorConfig()
        self.bull_detector = BullReferenceDetector(self.config)
        self.bear_detector = BearReferenceDetector(self.config)
    
    def load_csv(self, filepath: str, last_n_bars: Optional[int] = None) -> List[Bar]:
        """Load OHLC data from CSV file"""
        return self.bull_detector.load_csv(filepath, last_n_bars)
    
    def detect_all(self, bars: List[Bar], current_price: Optional[float] = None) -> Tuple[List[BullReferenceSwing], List[BearReferenceSwing]]:
        """
        Detect both bull and bear reference swings.
        
        Returns:
            Tuple of (bull_swings, bear_swings)
        """
        bull_swings = self.bull_detector.detect(bars, current_price)
        bear_swings = self.bear_detector.detect(bars, current_price)
        return bull_swings, bear_swings
    
    def detect_bull(self, bars: List[Bar], current_price: Optional[float] = None) -> List[BullReferenceSwing]:
        """Detect only bull reference swings"""
        return self.bull_detector.detect(bars, current_price)
    
    def detect_bear(self, bars: List[Bar], current_price: Optional[float] = None) -> List[BearReferenceSwing]:
        """Detect only bear reference swings"""
        return self.bear_detector.detect(bars, current_price)
    
    def print_analysis(self, bull_swings: List[BullReferenceSwing], bear_swings: List[BearReferenceSwing], current_price: float) -> None:
        """Print comprehensive analysis of both bull and bear swings"""
        self.bull_detector.print_analysis(bull_swings, current_price)
        print()
        self.bear_detector.print_analysis(bear_swings, current_price)


def main():
    """Example usage demonstrating both bull and bear detection"""
    # Configuration
    config = DetectorConfig(
        swing_lookback=1,  # Use 1 for daily data, higher for 1-min
        min_swing_range=20.0,  # Minimum 20 points
        explosive_speed_threshold=100.0,
    )
    
    # Initialize unified detector
    detector = ReferenceSwingDetector(config)
    
    # Load data - update path as needed
    bars = detector.load_csv('test.csv', last_n_bars=150)
    
    if not bars:
        print("No data loaded")
        return
    
    current_price = bars[-1].close
    
    print(f"Loaded {len(bars)} bars")
    print(f"Date range: {bars[0].date.date()} to {bars[-1].date.date()}")
    print(f"Current price: {current_price:.2f}")
    print()
    
    # Detect both bull and bear swings
    bull_swings, bear_swings = detector.detect_all(bars, current_price)
    
    # Print analysis for both
    detector.print_analysis(bull_swings, bear_swings, current_price)
    
    # Print combined level clustering analysis
    print("\n" + "=" * 80)
    print("COMBINED LEVEL CLUSTERING ANALYSIS")
    print("=" * 80)
    
    # Collect all key levels from both bull and bear swings
    all_levels = []
    for swing in bull_swings:
        for level_name in ['1', '1.382', '1.5', '1.618', '2']:
            all_levels.append({
                'price': swing.levels[level_name],
                'level': level_name,
                'swing_range': swing.range,
                'swing_type': 'bull'
            })
    
    for swing in bear_swings:
        for level_name in ['1', '1.382', '1.5', '1.618', '2']:
            all_levels.append({
                'price': swing.levels[level_name],
                'level': level_name,
                'swing_range': swing.range,
                'swing_type': 'bear'
            })
    
    # Sort by price
    all_levels.sort(key=lambda x: x['price'])
    
    # Find clusters (levels within 20 points of each other)
    print("\nKey levels (sorted by price):")
    for level in all_levels:
        print(f"  {level['price']:.2f} ({level['level']} of {level['swing_range']:.0f}pt {level['swing_type']} swing)")


if __name__ == "__main__":
    main()
