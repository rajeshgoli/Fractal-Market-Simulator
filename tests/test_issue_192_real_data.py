"""
Test for Issue #192 using real data from the issue report.

Data file: test_data/es-5m.csv
Window offset: 1172207
Playback bar: 45
"""

import pytest
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.swing_analysis.dag import (
    HierarchicalDetector,
    calibrate,
    dataframe_to_bars,
)
from src.swing_analysis.detection_config import DetectionConfig
from src.data.ohlc_loader import load_ohlc_window


class TestIssue192RealData:
    """Reproduce issue #192 with actual data from the report."""

    @pytest.fixture
    def test_data_path(self):
        """Path to the test data file."""
        path = Path("test_data/es-5m.csv")
        if not path.exists():
            pytest.skip("Test data file not found")
        return path

    def test_reproduce_issue_192(self, test_data_path):
        """
        Reproduce the exact scenario from issue #192.

        At bar 45 with window_offset=1172207, leg `dbf2603a` shows:
        - pivot_price: 4426.5, pivot_index: 37
        - origin_price: 4434.0, origin_index: 36

        But the actual data shows:
        - Bar 37's low is 4432.00, not 4426.50
        - Bar 36's high is 4435.25, not 4434.00
        """
        # Load the data window from the issue
        window_offset = 1172207
        num_bars = 50  # Load enough bars past bar 45

        df, gaps = load_ohlc_window(str(test_data_path), window_offset, num_bars)

        if len(df) < 45:
            pytest.skip("Not enough bars in data window")

        bars = dataframe_to_bars(df)

        # Process bars up to bar 45
        config = DetectionConfig.default()
        detector, events = calibrate(bars[:46], config)

        # Check all active legs for price/index consistency
        # After #197:
        # - Bull leg: origin=LOW (where upward move started), pivot=HIGH (defended extreme)
        # - Bear leg: origin=HIGH (where downward move started), pivot=LOW (defended extreme)
        errors = []
        for leg in detector.state.active_legs:
            if leg.pivot_index >= len(bars) or leg.origin_index >= len(bars):
                continue

            pivot_bar = bars[leg.pivot_index]
            origin_bar = bars[leg.origin_index]

            if leg.direction == 'bull':
                # Bull leg: origin at LOW, pivot at HIGH
                actual_origin_price = Decimal(str(origin_bar.low))
                actual_pivot_price = Decimal(str(pivot_bar.high))

                if leg.origin_price != actual_origin_price:
                    errors.append(
                        f"Bull leg {leg.leg_id}: origin_price={leg.origin_price} "
                        f"but bar {leg.origin_index}'s low is {actual_origin_price}"
                    )
                if leg.pivot_price != actual_pivot_price:
                    errors.append(
                        f"Bull leg {leg.leg_id}: pivot_price={leg.pivot_price} "
                        f"but bar {leg.pivot_index}'s high is {actual_pivot_price}"
                    )
            else:
                # Bear leg: origin at HIGH, pivot at LOW
                actual_origin_price = Decimal(str(origin_bar.high))
                actual_pivot_price = Decimal(str(pivot_bar.low))

                if leg.origin_price != actual_origin_price:
                    errors.append(
                        f"Bear leg {leg.leg_id}: origin_price={leg.origin_price} "
                        f"but bar {leg.origin_index}'s high is {actual_origin_price}"
                    )
                if leg.pivot_price != actual_pivot_price:
                    errors.append(
                        f"Bear leg {leg.leg_id}: pivot_price={leg.pivot_price} "
                        f"but bar {leg.pivot_index}'s low is {actual_pivot_price}"
                    )

        if errors:
            # Print detailed diagnostics
            print("\n=== Leg Bar Index Mismatches ===")
            for error in errors:
                print(error)

            print("\n=== All Active Legs ===")
            for leg in detector.state.active_legs:
                print(f"  {leg.leg_id}: {leg.direction} "
                      f"pivot={{price={leg.pivot_price}, idx={leg.pivot_index}}} "
                      f"origin={{price={leg.origin_price}, idx={leg.origin_index}}}")

            print("\n=== Relevant Bars ===")
            for i in range(min(46, len(bars))):
                b = bars[i]
                print(f"  Bar {i}: H={b.high}, L={b.low}")

        assert not errors, f"Found {len(errors)} price/index mismatches:\n" + "\n".join(errors)

    def test_incremental_processing_maintains_consistency(self, test_data_path):
        """
        Process bars one at a time and check consistency after each bar.
        """
        window_offset = 1172207
        num_bars = 50

        df, gaps = load_ohlc_window(str(test_data_path), window_offset, num_bars)
        bars = dataframe_to_bars(df)

        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        for bar_idx, bar in enumerate(bars[:46]):
            detector.process_bar(bar)

            # After each bar, verify all legs are consistent
            # After #197:
            # - Bull leg: origin=LOW (where upward move started), pivot=HIGH (defended extreme)
            # - Bear leg: origin=HIGH (where downward move started), pivot=LOW (defended extreme)
            for leg in detector.state.active_legs:
                if leg.pivot_index > bar_idx or leg.origin_index > bar_idx:
                    continue  # Skip legs with future indices

                pivot_bar = bars[leg.pivot_index]
                origin_bar = bars[leg.origin_index]

                if leg.direction == 'bull':
                    # Bull leg: origin at LOW, pivot at HIGH
                    actual_origin = Decimal(str(origin_bar.low))
                    actual_pivot = Decimal(str(pivot_bar.high))

                    assert leg.origin_price == actual_origin, (
                        f"After bar {bar_idx}, bull leg {leg.leg_id}: "
                        f"origin_price={leg.origin_price} != bar[{leg.origin_index}].low={actual_origin}"
                    )
                    assert leg.pivot_price == actual_pivot, (
                        f"After bar {bar_idx}, bull leg {leg.leg_id}: "
                        f"pivot_price={leg.pivot_price} != bar[{leg.pivot_index}].high={actual_pivot}"
                    )
                else:
                    # Bear leg: origin at HIGH, pivot at LOW
                    actual_origin = Decimal(str(origin_bar.high))
                    actual_pivot = Decimal(str(pivot_bar.low))

                    assert leg.origin_price == actual_origin, (
                        f"After bar {bar_idx}, bear leg {leg.leg_id}: "
                        f"origin_price={leg.origin_price} != bar[{leg.origin_index}].high={actual_origin}"
                    )
                    assert leg.pivot_price == actual_pivot, (
                        f"After bar {bar_idx}, bear leg {leg.leg_id}: "
                        f"pivot_price={leg.pivot_price} != bar[{leg.pivot_index}].low={actual_pivot}"
                    )
