"""
Scale Calibration Module

Analyzes historical OHLC data to determine size boundaries and aggregation settings
for four structural scales (S, M, L, XL) used in swing detection visualization.

The module uses quartile analysis of detected swing sizes to create adaptive
boundaries that reflect the actual market structure of the instrument and timeframe.
"""

import logging
import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime

import pandas as pd

from .bull_reference_detector import Bar
from .swing_detector import detect_swings


@dataclass
class ScaleConfig:
    """Configuration for structural scale boundaries and aggregation settings"""
    boundaries: Dict[str, Tuple[float, float]]  # {"S": (0, 15), "M": (15, 40), ...}
    aggregations: Dict[str, int]  # {"S": 1, "M": 15, "L": 60, "XL": 240} (minutes)
    swing_count: int  # Number of swings found in reference window
    used_defaults: bool  # True if instrument defaults were used
    median_durations: Dict[str, int]  # {"S": 18, "M": 45, ...} bars per swing
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'boundaries': {k: list(v) for k, v in self.boundaries.items()},
            'aggregations': self.aggregations,
            'swing_count': self.swing_count,
            'used_defaults': self.used_defaults,
            'median_durations': self.median_durations
        }


class ScaleCalibrator:
    """
    Calibrates structural scale boundaries and aggregation settings from historical data.
    
    Uses quartile analysis of swing sizes to create four scales (S, M, L, XL) with
    appropriate time aggregations for visualization.
    """
    
    # Default thresholds for known instruments
    DEFAULT_BOUNDARIES = {
        "ES": {
            "S": (0, 15),
            "M": (15, 40), 
            "L": (40, 100),
            "XL": (100, float('inf'))
        }
    }
    
    # Default aggregations (minutes)
    DEFAULT_AGGREGATIONS = {
        "S": 1,
        "M": 15,
        "L": 60,
        "XL": 240
    }
    
    # Default median durations (bars)
    DEFAULT_DURATIONS = {
        "S": 18,
        "M": 45,
        "L": 120,
        "XL": 300
    }
    
    # Allowed aggregation values (minutes)
    ALLOWED_AGGREGATIONS = [1, 5, 15, 30, 60, 240]
    
    def __init__(self, instrument_defaults: Optional[Dict] = None):
        """
        Initialize with optional custom instrument defaults.
        
        Args:
            instrument_defaults: Dict of custom defaults keyed by instrument.
                Example: {"ES": {"S": 15, "M": 40, "L": 100, "XL": float("inf")}}
        """
        self.logger = logging.getLogger(__name__)
        self.instrument_defaults = instrument_defaults or {}
        
    def calibrate(self, bars: List[Bar], instrument: str = "ES") -> ScaleConfig:
        """
        Analyze bars to determine scale boundaries and aggregation settings.
        
        Args:
            bars: List of OHLC bars for analysis
            instrument: Instrument identifier (e.g., "ES")
            
        Returns:
            ScaleConfig with boundaries and aggregations, or defaults if insufficient data
        """
        try:
            # Step 1: Detect all swings (bull and bear)
            all_swings = self._detect_all_swings(bars)
            
            # Step 2: Check minimum swing count
            if len(all_swings) < 20:
                self.logger.warning(
                    f"Insufficient swings detected ({len(all_swings)} < 20). "
                    f"Using instrument defaults for {instrument}."
                )
                return self._create_default_config(instrument, len(all_swings))
            
            # Step 3: Compute quartile boundaries
            swing_sizes = [swing['size'] for swing in all_swings]
            boundaries = self._compute_quartile_boundaries(swing_sizes, instrument)
            
            # If boundaries are degenerate, fall back to defaults
            if boundaries is None:
                self.logger.warning(
                    f"Degenerate swing distribution for {instrument}. Using defaults."
                )
                return self._create_default_config(instrument, len(all_swings))
            
            # Step 4: Compute aggregation settings
            aggregations, median_durations = self._compute_aggregations(all_swings, boundaries)
            
            # Step 5: Validate constraints
            aggregations = self._enforce_monotonicity(aggregations)
            
            return ScaleConfig(
                boundaries=boundaries,
                aggregations=aggregations,
                swing_count=len(all_swings),
                used_defaults=False,
                median_durations=median_durations
            )
            
        except Exception as e:
            self.logger.error(f"Error calibrating scales for {instrument}: {e}")
            return self._create_default_config(instrument, 0)
    
    def _detect_all_swings(self, bars: List[Bar]) -> List[Dict]:
        """
        Detect both bull and bear swings using the O(N log N) swing detector.

        Returns list of swing dictionaries with size, duration, etc.
        """
        if not bars:
            return []

        all_swings = []

        try:
            # Convert List[Bar] to DataFrame for detect_swings()
            df = pd.DataFrame({
                'open': [bar.open for bar in bars],
                'high': [bar.high for bar in bars],
                'low': [bar.low for bar in bars],
                'close': [bar.close for bar in bars]
            })

            # Use O(N log N) swing detector
            result = detect_swings(df, lookback=5, filter_redundant=True)

            # Map bull references to expected format
            for ref in result.get('bull_references', []):
                # Bull swing: high before low (downswing)
                duration = ref['low_bar_index'] - ref['high_bar_index']
                if duration > 0:
                    speed = ref['size'] / duration
                else:
                    speed = 0.0

                all_swings.append({
                    'type': 'bull',
                    'size': ref['size'],
                    'duration': duration,
                    'high': ref['high_price'],
                    'low': ref['low_price'],
                    'speed': speed
                })

            # Map bear references to expected format
            for ref in result.get('bear_references', []):
                # Bear swing: low before high (upswing)
                duration = ref['high_bar_index'] - ref['low_bar_index']
                if duration > 0:
                    speed = ref['size'] / duration
                else:
                    speed = 0.0

                all_swings.append({
                    'type': 'bear',
                    'size': ref['size'],
                    'duration': duration,
                    'high': ref['high_price'],
                    'low': ref['low_price'],
                    'speed': speed
                })

        except Exception as e:
            self.logger.error(f"Error detecting swings: {e}")

        return all_swings
    
    def _compute_quartile_boundaries(self, swing_sizes: List[float], instrument: str) -> Optional[Dict]:
        """
        Compute scale boundaries using quartile analysis.
        
        Returns None if distribution is degenerate.
        """
        if len(swing_sizes) < 4:
            return None
            
        try:
            sorted_sizes = sorted(swing_sizes)
            
            # Compute quartiles using linear interpolation
            q25 = statistics.quantiles(sorted_sizes, n=4)[0]  # 25th percentile  
            q50 = statistics.quantiles(sorted_sizes, n=4)[1]  # 50th percentile (median)
            q75 = statistics.quantiles(sorted_sizes, n=4)[2]  # 75th percentile
            
            # Round to nearest 0.25 (ES tick size)
            q25 = round(q25 * 4) / 4
            q50 = round(q50 * 4) / 4  
            q75 = round(q75 * 4) / 4
            
            # Check for degenerate ranges
            if q25 >= q50 or q50 >= q75 or q75 - q25 < 1.0:
                return None
                
            boundaries = {
                "S": (0, q25),
                "M": (q25, q50),
                "L": (q50, q75), 
                "XL": (q75, float('inf'))
            }
            
            return boundaries
            
        except Exception as e:
            self.logger.error(f"Error computing quartiles: {e}")
            return None
    
    def _compute_aggregations(self, all_swings: List[Dict], boundaries: Dict) -> Tuple[Dict, Dict]:
        """
        Compute aggregation settings for each scale based on swing durations.
        
        Returns (aggregations, median_durations)
        """
        scale_swings = {"S": [], "M": [], "L": [], "XL": []}
        
        # Categorize swings by scale
        for swing in all_swings:
            size = swing['size']
            for scale, (min_size, max_size) in boundaries.items():
                if min_size <= size < max_size or (scale == "XL" and size >= min_size):
                    scale_swings[scale].append(swing)
                    break  # Assign to first matching scale (handles ties)
        
        aggregations = {}
        median_durations = {}
        
        for scale in ["S", "M", "L", "XL"]:
            swings = scale_swings[scale]
            
            if swings:
                # Compute median duration in bars
                durations = [s['duration'] for s in swings if s['duration'] > 0]
                if durations:
                    median_duration = statistics.median(durations)
                    median_durations[scale] = int(median_duration)
                    
                    # Target aggregation: median_duration / 20 (for 10-30 bars display)
                    target_agg = median_duration / 20
                    
                    # Snap to nearest allowed value
                    aggregation = self._snap_to_allowed_aggregation(target_agg)
                    aggregations[scale] = aggregation
                else:
                    # No valid durations, use defaults
                    median_durations[scale] = self.DEFAULT_DURATIONS[scale]
                    aggregations[scale] = self.DEFAULT_AGGREGATIONS[scale]
            else:
                # No swings in this scale, use defaults
                median_durations[scale] = self.DEFAULT_DURATIONS[scale] 
                aggregations[scale] = self.DEFAULT_AGGREGATIONS[scale]
        
        return aggregations, median_durations
    
    def _snap_to_allowed_aggregation(self, target: float) -> int:
        """Snap target aggregation to nearest allowed value."""
        if target < 1:
            return 1
        if target > 240:
            return 240
            
        # Find closest allowed value
        best_agg = self.ALLOWED_AGGREGATIONS[0]
        min_diff = abs(target - best_agg)
        
        for agg in self.ALLOWED_AGGREGATIONS[1:]:
            diff = abs(target - agg)
            if diff < min_diff:
                min_diff = diff
                best_agg = agg
                
        return best_agg
    
    def _enforce_monotonicity(self, aggregations: Dict) -> Dict:
        """
        Ensure aggregations increase monotonically across scales.
        
        If a smaller scale has larger aggregation than bigger scale,
        force the smaller scale down to match.
        """
        scales = ["S", "M", "L", "XL"]
        
        for i in range(len(scales) - 1):
            current_scale = scales[i]
            next_scale = scales[i + 1]
            
            if aggregations[current_scale] > aggregations[next_scale]:
                aggregations[current_scale] = aggregations[next_scale]
        
        return aggregations
    
    def _create_default_config(self, instrument: str, swing_count: int) -> ScaleConfig:
        """Create ScaleConfig using instrument defaults."""
        # Use custom defaults if available, otherwise use built-in defaults
        if instrument in self.instrument_defaults:
            custom = self.instrument_defaults[instrument]
            boundaries = {
                scale: (0 if scale == "S" else custom[prev_scale], 
                       custom[scale] if scale != "XL" else float('inf'))
                for i, (scale, prev_scale) in enumerate(zip(["S", "M", "L", "XL"], [None, "S", "M", "L"]))
            }
        else:
            boundaries = self.DEFAULT_BOUNDARIES.get(instrument, self.DEFAULT_BOUNDARIES["ES"])
        
        return ScaleConfig(
            boundaries=boundaries,
            aggregations=self.DEFAULT_AGGREGATIONS.copy(),
            swing_count=swing_count,
            used_defaults=True,
            median_durations=self.DEFAULT_DURATIONS.copy()
        )