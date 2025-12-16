"""
Reference Swing Detector - Unified Base Implementation

This module provides a single parameterized class for detecting reference swings,
eliminating the duplication between BullReferenceDetector and BearReferenceDetector.

A reference swing is a completed price leg that the current market is actively countering:
- Bull reference: A completed bear leg (high→low) being countered from below
- Bear reference: A completed bull leg (low→high) being countered from above

The detector finds swing points, validates retracement levels, checks price protection,
and applies subsumption rules to return only structurally significant swings.
"""

import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple, Literal

from .bull_reference_detector import (
    Bar,
    BullReferenceSwing,
    BearReferenceSwing,
    DetectorConfig,
)


Direction = Literal["bull", "bear"]


class DirectionalReferenceDetector:
    """
    Unified reference swing detector parameterized by direction.

    This base class handles both bull and bear detection through configuration:
    - Bull: detects bear legs (high→low) feeding into swing lows
    - Bear: detects bull legs (low→high) feeding into swing highs

    Usage:
        detector = DirectionalReferenceDetector("bull", config)
        bars = detector.load_csv("data.csv")
        swings = detector.detect(bars, current_price)
    """

    def __init__(self, direction: Direction, config: Optional[DetectorConfig] = None):
        """
        Initialize detector with direction and configuration.

        Args:
            direction: "bull" for bull reference swings, "bear" for bear reference swings
            config: Detection configuration (uses defaults if None)
        """
        self.direction = direction
        self.config = config or DetectorConfig()
        self._swing_highs: Set[int] = set()
        self._swing_lows: Set[int] = set()

        # Direction-specific configuration
        if direction == "bull":
            # Bull swings: bear leg (high→low), anchor at low
            self._anchor_price = "low"
            self._anchor_index = "low_index"
            self._terminus_price = "high"
            self._terminus_index = "high_index"
            self._anchor_set_name = "_swing_lows"
            self._terminus_set_name = "_swing_highs"
            self._is_terminus_swing_field = "is_swing_high"
            self._protection_tolerance = self.config.low_violation_tolerance
        else:
            # Bear swings: bull leg (low→high), anchor at high
            self._anchor_price = "high"
            self._anchor_index = "high_index"
            self._terminus_price = "low"
            self._terminus_index = "low_index"
            self._anchor_set_name = "_swing_highs"
            self._terminus_set_name = "_swing_lows"
            self._is_terminus_swing_field = "is_swing_low"
            self._protection_tolerance = self.config.high_violation_tolerance

    def load_csv(self, filepath: str, last_n_bars: Optional[int] = None) -> List[Bar]:
        """
        Load OHLC data from CSV file.

        Supports two formats:
        - TradingView: time,open,high,low,close (comma-separated, unix timestamp)
        - Historical: date;open;high;low;close (semicolon-separated)
        """
        bars = []

        with open(filepath, 'r') as f:
            first_line = f.readline()
            f.seek(0)

            if ';' in first_line:
                # Historical format
                reader = csv.DictReader(f, delimiter=';')
                for i, row in enumerate(reader):
                    try:
                        dt = datetime.strptime(row['date'], '%d.%m.%Y %H:%M:%S')
                        timestamp = int(dt.timestamp())
                    except:
                        continue

                    bars.append(Bar(
                        index=i,
                        timestamp=timestamp,
                        open=float(row['open']),
                        high=float(row['high']),
                        low=float(row['low']),
                        close=float(row['close'])
                    ))
            else:
                # TradingView format
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    bars.append(Bar(
                        index=i,
                        timestamp=int(row['time']),
                        open=float(row['open']),
                        high=float(row['high']),
                        low=float(row['low']),
                        close=float(row['close'])
                    ))

        if last_n_bars and len(bars) > last_n_bars:
            bars = bars[-last_n_bars:]
            for i, bar in enumerate(bars):
                bar.index = i

        return bars

    def detect(self, bars: List[Bar], current_price: Optional[float] = None):
        """
        Detect all valid reference swings.

        Args:
            bars: List of OHLC bars
            current_price: Current price for retracement calculation.
                          If None, uses the close of the last bar.

        Returns:
            List of valid reference swing objects (BullReferenceSwing or BearReferenceSwing),
            sorted by range (largest first)
        """
        if not bars:
            return []

        if current_price is None:
            current_price = bars[-1].close

        # Step 1: Find all swing highs and lows
        self._find_swing_points(bars)

        # Step 2: For each anchor swing, find all feeding legs
        anchor_set = getattr(self, self._anchor_set_name)
        all_legs = []
        for anchor_idx in anchor_set:
            legs = self._find_legs(bars, anchor_idx)
            all_legs.extend(legs)

        # Step 3: Filter by retracement validity
        valid_legs = [
            leg for leg in all_legs
            if self._check_retracement_validity(leg, current_price)
        ]

        # Step 4: Filter by protection
        valid_legs = [
            leg for leg in valid_legs
            if self._check_protection(bars, leg)
        ]

        # Step 5: Filter by minimum range
        valid_legs = [
            leg for leg in valid_legs
            if leg['range'] >= self.config.min_swing_range
        ]

        # Step 6: Enrich with metadata
        terminus_set = getattr(self, self._terminus_set_name)
        for leg in valid_legs:
            leg['speed'] = leg['range'] / leg['duration'] if leg['duration'] > 0 else leg['range']
            leg[self._is_terminus_swing_field] = leg[self._terminus_index] in terminus_set
            leg['high_date'] = bars[leg['high_index']].date
            leg['low_date'] = bars[leg['low_index']].date

        # Step 7: Classify explosive swings
        self._classify_explosive(valid_legs)

        # Step 8: Apply subsumption
        final_legs = self._subsume_same_anchor(valid_legs)
        final_legs = self._subsume_nested(final_legs)

        # Step 9: Apply direction-specific deduplication (bull only has extra step)
        if self.direction == "bull":
            final_legs = self._deduplicate_structural_variations(final_legs)

        # Step 10: Convert to typed swing objects
        result = self._convert_to_swings(final_legs)

        # Sort by range (largest first)
        result.sort(key=lambda x: x.range, reverse=True)

        return result

    def _find_swing_points(self, bars: List[Bar]) -> None:
        """Find all swing highs and swing lows."""
        self._swing_highs = set()
        self._swing_lows = set()

        lookback = self.config.swing_lookback

        for i in range(lookback, len(bars) - lookback):
            # Check for swing high
            is_swing_high = True
            for j in range(1, lookback + 1):
                if bars[i].high < bars[i - j].high or bars[i].high < bars[i + j].high:
                    is_swing_high = False
                    break
            if is_swing_high:
                self._swing_highs.add(i)

            # Check for swing low
            is_swing_low = True
            for j in range(1, lookback + 1):
                if bars[i].low > bars[i - j].low or bars[i].low > bars[i + j].low:
                    is_swing_low = False
                    break
            if is_swing_low:
                self._swing_lows.add(i)

    def _find_legs(self, bars: List[Bar], anchor_index: int) -> List[Dict]:
        """
        Find all legs feeding into the anchor swing point.

        For bull: finds bear legs (high→low) feeding into a swing low
        For bear: finds bull legs (low→high) feeding into a swing high
        """
        if self.direction == "bull":
            return self._find_bear_legs(bars, anchor_index)
        else:
            return self._find_bull_legs(bars, anchor_index)

    def _find_bear_legs(self, bars: List[Bar], low_index: int) -> List[Dict]:
        """Find all bear legs (high→low) feeding into a swing low."""
        low_price = bars[low_index].low
        bear_legs = []
        best_high_so_far = low_price

        for i in range(low_index - 1, -1, -1):
            bar = bars[i]

            # Stop if this bar's low is below our swing low
            if bar.low < low_price:
                break

            # Record new higher high as a bear leg
            if bar.high > best_high_so_far:
                bear_legs.append({
                    'high_index': i,
                    'high_price': bar.high,
                    'low_index': low_index,
                    'low_price': low_price,
                    'range': bar.high - low_price,
                    'duration': low_index - i
                })
                best_high_so_far = bar.high

        return bear_legs

    def _find_bull_legs(self, bars: List[Bar], high_index: int) -> List[Dict]:
        """Find all bull legs (low→high) feeding into a swing high."""
        high_price = bars[high_index].high
        bull_legs = []
        best_low_so_far = high_price

        for i in range(high_index - 1, -1, -1):
            bar = bars[i]

            # Stop if this bar's high is above our swing high
            if bar.high > high_price:
                break

            # Record new lower low as a bull leg
            if bar.low < best_low_so_far:
                bull_legs.append({
                    'low_index': i,
                    'low_price': bar.low,
                    'high_index': high_index,
                    'high_price': high_price,
                    'range': high_price - bar.low,
                    'duration': high_index - i
                })
                best_low_so_far = bar.low

        return bull_legs

    def _check_retracement_validity(self, leg: Dict, current_price: float) -> bool:
        """Check if current price is in valid retracement zone."""
        if self.direction == "bull":
            # Bull: valid when price is above the low (retracing the bear leg)
            low = leg['low_price']
            r = leg['range']
            level_min = low + self.config.min_retracement * r
            level_max = low + self.config.max_retracement * r
            return level_min <= current_price <= level_max
        else:
            # Bear: valid when price is below the high (retracing the bull leg)
            high = leg['high_price']
            r = leg['range']
            level_max = high - self.config.min_retracement * r
            level_min = high - self.config.max_retracement * r
            return level_min <= current_price <= level_max

    def _check_protection(self, bars: List[Bar], leg: Dict) -> bool:
        """Check if the anchor price has been protected (not violated beyond tolerance)."""
        r = leg['range']
        tolerance = self._protection_tolerance * r

        if self.direction == "bull":
            # Check low protection
            low = leg['low_price']
            low_index = leg['low_index']
            violation_threshold = low - tolerance

            for i in range(low_index + 1, len(bars)):
                if bars[i].low < violation_threshold:
                    return False
        else:
            # Check high protection
            high = leg['high_price']
            high_index = leg['high_index']
            violation_threshold = high + tolerance

            for i in range(high_index + 1, len(bars)):
                if bars[i].high > violation_threshold:
                    return False

        return True

    def _classify_explosive(self, legs: List[Dict]) -> None:
        """Mark legs as explosive based on speed."""
        if not legs:
            return

        # Group by anchor index to calculate peer averages
        by_anchor = {}
        for leg in legs:
            anchor_idx = leg[self._anchor_index]
            if anchor_idx not in by_anchor:
                by_anchor[anchor_idx] = []
            by_anchor[anchor_idx].append(leg)

        for anchor_idx, group in by_anchor.items():
            avg_speed = sum(l['speed'] for l in group) / len(group)

            for leg in group:
                leg['is_explosive'] = (
                    leg['speed'] >= self.config.explosive_speed_threshold or
                    leg['speed'] >= avg_speed * self.config.explosive_speed_multiplier
                )

    def _subsume_same_anchor(self, legs: List[Dict]) -> List[Dict]:
        """
        For swings sharing the same anchor, keep only structurally significant ones:
        - The largest (HTF context)
        - The most explosive (if significantly faster than average)
        - Any whose terminus is a swing point (swing termination)
        - The most recent (if within threshold of anchor)
        """
        by_anchor = {}
        for leg in legs:
            anchor_idx = leg[self._anchor_index]
            if anchor_idx not in by_anchor:
                by_anchor[anchor_idx] = []
            by_anchor[anchor_idx].append(leg)

        survivors = []

        for anchor_idx, group in by_anchor.items():
            if len(group) == 1:
                survivors.append(group[0])
                continue

            kept_ids = set()

            # Keep largest
            largest = max(group, key=lambda x: x['range'])
            kept_ids.add(id(largest))

            # Keep most explosive
            most_explosive = max(group, key=lambda x: x['speed'])
            if most_explosive['is_explosive']:
                kept_ids.add(id(most_explosive))

            # Keep any swing-point terminations
            for leg in group:
                if leg.get(self._is_terminus_swing_field, False):
                    kept_ids.add(id(leg))

            # Keep most recent if within threshold
            most_recent = max(group, key=lambda x: x[self._terminus_index])
            if most_recent['duration'] <= self.config.recent_duration_threshold:
                kept_ids.add(id(most_recent))

            for leg in group:
                if id(leg) in kept_ids:
                    survivors.append(leg)

        return survivors

    def _subsume_nested(self, legs: List[Dict]) -> List[Dict]:
        """
        Remove swings completely contained within larger swings,
        unless they are explosive or swing-point terminations.
        """
        legs = sorted(legs, key=lambda x: x['range'], reverse=True)
        survivors = []

        for leg in legs:
            subsumed = False

            for survivor in survivors:
                # Check containment based on direction
                if self.direction == "bull":
                    time_contained = (
                        survivor['high_index'] <= leg['high_index'] and
                        survivor['low_index'] >= leg['low_index']
                    )
                    price_contained = (
                        survivor['high_price'] >= leg['high_price'] and
                        survivor['low_price'] <= leg['low_price']
                    )
                else:
                    time_contained = (
                        survivor['low_index'] <= leg['low_index'] and
                        survivor['high_index'] >= leg['high_index']
                    )
                    price_contained = (
                        survivor['low_price'] <= leg['low_price'] and
                        survivor['high_price'] >= leg['high_price']
                    )

                if time_contained and price_contained:
                    # Keep if explosive or swing-point termination
                    if not leg['is_explosive'] and not leg.get(self._is_terminus_swing_field, False):
                        subsumed = True
                        break

            if not subsumed:
                survivors.append(leg)

        return survivors

    def _deduplicate_structural_variations(self, legs: List[Dict]) -> List[Dict]:
        """
        Simple deduplication to eliminate variations of the same structural swing.

        Groups swings by high price proximity and keeps only the most significant
        variations from each high group. Only used for bull direction.
        """
        if len(legs) <= 1:
            return legs

        # Group swings by high price (within 30 points = same structural high)
        high_groups = {}
        for leg in legs:
            high_bucket = round(leg['high_price'] / 30) * 30
            if high_bucket not in high_groups:
                high_groups[high_bucket] = []
            high_groups[high_bucket].append(leg)

        survivors = []

        for high_bucket, group in high_groups.items():
            if len(group) == 1:
                survivors.extend(group)
                continue

            group = sorted(group, key=lambda x: x['range'], reverse=True)
            group_survivors = [group[0]]

            for candidate in group[1:]:
                is_distinct = True

                for survivor in group_survivors:
                    low_diff = abs(candidate['low_price'] - survivor['low_price'])
                    max_range = max(candidate['range'], survivor['range'])

                    if low_diff < 0.05 * max_range:
                        is_distinct = False
                        break

                if is_distinct:
                    group_survivors.append(candidate)
                    if len(group_survivors) >= 3:
                        break

            survivors.extend(group_survivors)

        return survivors

    def _convert_to_swings(self, legs: List[Dict]):
        """Convert leg dictionaries to typed swing objects."""
        result = []

        for leg in legs:
            if self.direction == "bull":
                swing = BullReferenceSwing(
                    high_index=leg['high_index'],
                    high_price=leg['high_price'],
                    high_date=leg['high_date'],
                    low_index=leg['low_index'],
                    low_price=leg['low_price'],
                    low_date=leg['low_date'],
                    range=leg['range'],
                    duration=leg['duration'],
                    speed=leg['speed'],
                    is_explosive=leg.get('is_explosive', False),
                    is_swing_high=leg.get('is_swing_high', False)
                )
            else:
                swing = BearReferenceSwing(
                    low_index=leg['low_index'],
                    low_price=leg['low_price'],
                    low_date=leg['low_date'],
                    high_index=leg['high_index'],
                    high_price=leg['high_price'],
                    high_date=leg['high_date'],
                    range=leg['range'],
                    duration=leg['duration'],
                    speed=leg['speed'],
                    is_explosive=leg.get('is_explosive', False),
                    is_swing_low=leg.get('is_swing_low', False)
                )
            result.append(swing)

        return result

    def print_analysis(self, swings, current_price: float) -> None:
        """Print a formatted analysis of detected swings."""
        direction_label = "BULL" if self.direction == "bull" else "BEAR"
        print("=" * 80)
        print(f"{direction_label} REFERENCE SWINGS (Current Price: {current_price:.2f})")
        print("=" * 80)

        for i, swing in enumerate(swings, 1):
            ret = swing.get_retracement(current_price)
            zone = swing.get_zone(current_price)

            markers = []
            if swing.is_explosive:
                markers.append("EXPLOSIVE")

            if self.direction == "bull" and swing.is_swing_high:
                markers.append("SWING-HIGH")
            elif self.direction == "bear" and swing.is_swing_low:
                markers.append("SWING-LOW")

            marker_str = f" [{', '.join(markers)}]" if markers else ""

            if self.direction == "bull":
                print(f"\n{i}. {swing.high_price:.2f} ({swing.high_date.date()}) -> "
                      f"{swing.low_price:.2f} ({swing.low_date.date()})")
            else:
                print(f"\n{i}. {swing.low_price:.2f} ({swing.low_date.date()}) -> "
                      f"{swing.high_price:.2f} ({swing.high_date.date()})")

            print(f"   Range: {swing.range:.2f} | Duration: {swing.duration} bars | "
                  f"Speed: {swing.speed:.1f} pts/bar{marker_str}")
            print(f"   Current: {ret:.3f} retracement -> {zone}")
            print(f"   Levels: 1.0={swing.levels['1']:.2f}, "
                  f"1.382={swing.levels['1.382']:.2f}, "
                  f"1.5={swing.levels['1.5']:.2f}, "
                  f"2x={swing.levels['2']:.2f}")
