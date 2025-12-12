"""
Random interval sampling for swing validation.

Samples random time windows from historical data and detects swings
within each window for human validation.
"""

import logging
import random
import uuid
from datetime import datetime
from typing import List, Optional, Set

import pandas as pd

from ..data.ohlc_loader import load_ohlc
from ..swing_analysis.bull_reference_detector import Bar, BullReferenceDetector, BearReferenceDetector
from ..swing_analysis.scale_calibrator import ScaleCalibrator, ScaleConfig
from .models import (
    OHLCBar,
    Scale,
    SamplerConfig,
    SwingCandidate,
    ValidationSample,
)

logger = logging.getLogger(__name__)


class IntervalSampler:
    """
    Samples random intervals from market data and detects swings for validation.

    Provides deterministic sampling when seeded, ensuring reproducible validation sessions.
    """

    def __init__(self, config: SamplerConfig, seed: Optional[int] = None):
        """
        Initialize the sampler with configuration.

        Args:
            config: Sampler configuration
            seed: Optional random seed for reproducibility
        """
        self.config = config
        self.rng = random.Random(seed)

        # Load data
        self.df, self.gaps = load_ohlc(config.data_file)
        self.bars = self._df_to_bars()

        # Calibrate scales
        calibrator = ScaleCalibrator()
        self.scale_config = calibrator.calibrate(self.bars, config.instrument)

        # Track sampled intervals to avoid repeats
        self._sampled_intervals: Set[tuple] = set()

        logger.info(
            f"Initialized sampler with {len(self.bars)} bars, "
            f"scale config: {self.scale_config.boundaries}"
        )

    def _df_to_bars(self) -> List[Bar]:
        """Convert DataFrame to list of Bar objects."""
        bars = []
        for idx, (timestamp, row) in enumerate(self.df.iterrows()):
            bar = Bar(
                index=idx,
                timestamp=int(timestamp.timestamp()),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close'])
            )
            bars.append(bar)
        return bars

    def sample(self, scale: Optional[Scale] = None) -> ValidationSample:
        """
        Sample a random interval and detect swings.

        Args:
            scale: Specific scale to sample for, or None for random scale

        Returns:
            ValidationSample with interval data and swing candidates
        """
        # Select scale
        if scale is None:
            scale = self.rng.choice(list(Scale))

        # Determine interval size based on scale
        interval_size = self._get_interval_size(scale)

        # Sample random start position (ensuring enough room for context + interval)
        min_start = self.config.context_before
        max_start = len(self.bars) - interval_size - self.config.context_after

        if max_start <= min_start:
            raise ValueError(
                f"Not enough data for interval. Need {interval_size + self.config.context_before + self.config.context_after} bars, "
                f"have {len(self.bars)}"
            )

        # Try to find a unique interval
        attempts = 0
        max_attempts = 100
        while attempts < max_attempts:
            start_idx = self.rng.randint(min_start, max_start)
            end_idx = start_idx + interval_size
            interval_key = (scale.value, start_idx, end_idx)

            if interval_key not in self._sampled_intervals:
                self._sampled_intervals.add(interval_key)
                break
            attempts += 1

        if attempts >= max_attempts:
            logger.warning("Could not find unique interval, reusing existing")

        # Extract bars for interval (including context)
        context_start = start_idx - self.config.context_before
        context_end = end_idx + self.config.context_after
        interval_bars = self.bars[context_start:context_end]

        # Detect swings in the interval
        candidates = self._detect_swings(
            self.bars[start_idx:end_idx],
            scale,
            start_idx
        )

        # Convert bars to OHLCBar models
        ohlc_bars = [
            OHLCBar(
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close
            )
            for bar in interval_bars
        ]

        return ValidationSample(
            sample_id=str(uuid.uuid4()),
            scale=scale,
            interval_start=self.bars[start_idx].timestamp,
            interval_end=self.bars[end_idx - 1].timestamp,
            bars=ohlc_bars,
            candidates=candidates[:self.config.top_k_swings],
            context_bars_before=self.config.context_before,
            context_bars_after=self.config.context_after,
        )

    def _get_interval_size(self, scale: Scale) -> int:
        """Get appropriate interval size for a scale."""
        # Use median duration from calibration, or defaults
        durations = self.scale_config.median_durations
        base_duration = durations.get(scale.value, 100)

        # Scale the interval to show 1-3 complete swings
        # Add some randomness
        min_size = max(self.config.min_interval_bars, int(base_duration * 0.8))
        max_size = min(self.config.max_interval_bars, int(base_duration * 2.5))

        # Ensure valid range
        if max_size < min_size:
            max_size = min_size

        return self.rng.randint(min_size, max_size)

    def _detect_swings(
        self,
        interval_bars: List[Bar],
        scale: Scale,
        global_offset: int
    ) -> List[SwingCandidate]:
        """
        Detect swings in the interval and rank them.

        Args:
            interval_bars: Bars within the interval
            scale: Scale for filtering swings
            global_offset: Index offset for global timestamp calculation

        Returns:
            List of SwingCandidate sorted by rank (best first)
        """
        if len(interval_bars) < 20:
            return []

        candidates = []
        current_price = interval_bars[-1].close

        # Detect bull swings
        bull_detector = BullReferenceDetector()
        bull_swings = bull_detector.detect(interval_bars, current_price)

        for swing in bull_swings:
            if self._is_in_scale(swing.range, scale):
                candidates.append(self._swing_to_candidate(
                    swing, scale, is_bull=True, rank=0
                ))

        # Detect bear swings
        try:
            bear_detector = BearReferenceDetector()
            bear_swings = bear_detector.detect(interval_bars, current_price)

            for swing in bear_swings:
                if self._is_in_scale(swing.range, scale):
                    candidates.append(self._swing_to_candidate(
                        swing, scale, is_bull=False, rank=0
                    ))
        except Exception as e:
            logger.debug(f"Bear detection failed: {e}")

        # Rank candidates by size (larger swings are more significant)
        candidates.sort(key=lambda c: c.size, reverse=True)

        # Assign ranks
        for i, candidate in enumerate(candidates):
            candidate.rank = i + 1

        return candidates

    def _is_in_scale(self, swing_size: float, scale: Scale) -> bool:
        """Check if swing size falls within the given scale boundaries."""
        boundaries = self.scale_config.boundaries[scale.value]
        return boundaries[0] <= swing_size < boundaries[1]

    def _swing_to_candidate(
        self,
        swing,
        scale: Scale,
        is_bull: bool,
        rank: int
    ) -> SwingCandidate:
        """Convert a detected swing to a SwingCandidate model."""
        return SwingCandidate(
            swing_id=str(uuid.uuid4()),
            scale=scale,
            is_bull=is_bull,
            high_price=swing.high_price,
            low_price=swing.low_price,
            high_timestamp=int(swing.high_date.timestamp()) if hasattr(swing, 'high_date') else 0,
            low_timestamp=int(swing.low_date.timestamp()) if hasattr(swing, 'low_date') else 0,
            size=swing.range,
            duration_bars=swing.duration,
            levels=swing.levels,
            rank=rank
        )

    def get_scale_config(self) -> ScaleConfig:
        """Get the calibrated scale configuration."""
        return self.scale_config

    def get_data_summary(self) -> dict:
        """Get summary of loaded data."""
        # Convert infinity to None for JSON serialization
        def sanitize_boundary(boundary):
            return [
                None if v == float('inf') else v
                for v in boundary
            ]

        return {
            "total_bars": len(self.bars),
            "start_time": datetime.fromtimestamp(self.bars[0].timestamp).isoformat() if self.bars else None,
            "end_time": datetime.fromtimestamp(self.bars[-1].timestamp).isoformat() if self.bars else None,
            "gaps": len(self.gaps),
            "scale_boundaries": {k: sanitize_boundary(v) for k, v in self.scale_config.boundaries.items()},
            "samples_generated": len(self._sampled_intervals),
        }
