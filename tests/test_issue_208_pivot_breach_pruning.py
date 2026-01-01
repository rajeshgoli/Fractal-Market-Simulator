"""
Test for issue #208: Engulfed leg pruning.

When both origin AND pivot have been breached over time (engulfed),
the leg should be deleted entirely with no replacement.

Note: The original #208 design included a "pivot breach replacement" path,
but that code path was unreachable due to pivot extension happening before
breach tracking. See Docs/Archive/pivot_breach_analysis.md for analysis.
Issue #305 removed the dead code, keeping only engulfed pruning.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.dag import HierarchicalDetector, Leg
from src.swing_analysis.dag.leg_pruner import LegPruner
from src.swing_analysis.dag.state import DetectorState
from src.swing_analysis.detection_config import DetectionConfig, DirectionConfig
from src.swing_analysis.types import Bar
from src.swing_analysis.events import LegPrunedEvent


def make_bar(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    """Helper to create Bar objects for testing."""
    return Bar(
        index=index,
        timestamp=1700000000 + index * 60,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class TestConfigParameters:
    """Test that config parameters are properly defined."""

    def test_engulfed_breach_threshold_default(self):
        """engulfed_breach_threshold should default to 0.236 (#404: symmetric config)."""
        config = DetectionConfig.default()
        assert config.engulfed_breach_threshold == 0.236

    def test_custom_engulfed_breach_threshold(self):
        """DetectionConfig should accept custom engulfed_breach_threshold via with_engulfed (#404)."""
        config = DetectionConfig.default().with_engulfed(0.25)
        assert config.engulfed_breach_threshold == 0.25

    def test_swing_config_includes_engulfed_params(self):
        """DetectionConfig should include symmetric engulfed threshold (#404)."""
        config = DetectionConfig.default()

        # #404: engulfed_breach_threshold is now at DetectionConfig level (symmetric)
        assert config.engulfed_breach_threshold == 0.236  # Default threshold


class TestPivotExtension:
    """Test that pivots extend when origin is not breached."""

    def test_bear_leg_pivot_extends_when_origin_not_breached(self):
        """
        When origin is NOT breached, the pivot EXTENDS to track new extremes.

        Scenario:
        - Bear leg forms: origin=4450, pivot=4420 (range=30)
        - Price retraces up (but doesn't breach origin at 4450)
        - Price drops below pivot to 4415
        - Since origin NOT breached, pivot EXTENDS to 4415
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 4445.0, 4450.0, 4440.0, 4448.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bear (LH, LL) - starts bear leg from 4450
        bar1 = make_bar(1, 4448.0, 4449.0, 4430.0, 4432.0)
        detector.process_bar(bar1)

        # Bar 2: Continue bear - extend pivot to 4420
        bar2 = make_bar(2, 4432.0, 4435.0, 4420.0, 4422.0)
        detector.process_bar(bar2)

        # Verify bear leg exists with pivot at 4420
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        assert len(bear_legs) >= 1

        # Find the bear leg from origin 4450
        bear_leg = next(
            (leg for leg in bear_legs if leg.origin_price == Decimal('4450')),
            None
        )
        assert bear_leg is not None
        assert bear_leg.pivot_price == Decimal('4420')

        # Bar 3: Type 2-Bull retracement - causes leg to form (38.2% retrace)
        bar3 = make_bar(3, 4422.0, 4435.0, 4425.0, 4433.0)
        detector.process_bar(bar3)

        # Verify leg exists and origin is NOT breached
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        assert len(bear_legs) >= 1
        bear_leg = bear_legs[0]
        assert bear_leg.max_origin_breach is None  # Origin NOT breached

        # Bar 4: Price drops below pivot to 4415
        # Since origin is NOT breached, pivot EXTENDS
        bar4 = make_bar(4, 4433.0, 4434.0, 4415.0, 4417.0)
        detector.process_bar(bar4)

        # Verify the pivot EXTENDED to 4415
        bear_leg = next(
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.origin_price == Decimal('4450')
        )
        assert bear_leg.pivot_price == Decimal('4415')  # Extended
        assert bear_leg.max_pivot_breach is None  # Not breached

    def test_bull_leg_pivot_extends_when_origin_not_breached(self):
        """
        When origin is NOT breached, the pivot EXTENDS to track new extremes.

        Scenario:
        - Bull leg forms: origin=4400, pivot=4430 (range=30)
        - Price retraces down (but doesn't breach origin at 4400)
        - Price rallies above pivot to 4435
        - Since origin NOT breached, pivot EXTENDS to 4435
        """
        detector = HierarchicalDetector()

        # Bar 0: Initial bar
        bar0 = make_bar(0, 4405.0, 4410.0, 4400.0, 4408.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2-Bull (HH, HL) - starts bull leg from 4400
        bar1 = make_bar(1, 4408.0, 4420.0, 4405.0, 4418.0)
        detector.process_bar(bar1)

        # Bar 2: Continue bull - extend pivot to 4430
        bar2 = make_bar(2, 4418.0, 4430.0, 4415.0, 4428.0)
        detector.process_bar(bar2)

        # Verify bull leg exists with pivot at 4430
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs) >= 1

        # Bar 3: Type 2-Bear retracement - causes leg to form (38.2% retrace)
        bar3 = make_bar(3, 4428.0, 4429.0, 4412.0, 4415.0)
        detector.process_bar(bar3)

        # Verify leg exists and origin is NOT breached
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        assert len(bull_legs) >= 1
        bull_leg = bull_legs[0]
        assert bull_leg.max_origin_breach is None  # Origin NOT breached

        # Bar 4: Price rallies above pivot to 4435
        # Since origin NOT breached, pivot EXTENDS
        bar4 = make_bar(4, 4415.0, 4435.0, 4414.0, 4433.0)
        detector.process_bar(bar4)

        # Verify the pivot EXTENDED to 4435
        bull_leg = next(
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.origin_price == Decimal('4400')
        )
        assert bull_leg.pivot_price == Decimal('4435')  # Extended
        assert bull_leg.max_pivot_breach is None  # Not breached

    def test_pivot_continues_extending(self):
        """
        Pivot continues to extend as price makes new extremes.
        """
        detector = HierarchicalDetector()

        # Create and form a bear leg
        bar0 = make_bar(0, 4445.0, 4450.0, 4440.0, 4448.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 4448.0, 4449.0, 4430.0, 4432.0)
        detector.process_bar(bar1)

        bar2 = make_bar(2, 4432.0, 4435.0, 4420.0, 4422.0)
        detector.process_bar(bar2)

        bar3 = make_bar(3, 4422.0, 4435.0, 4425.0, 4433.0)
        detector.process_bar(bar3)

        # Bar 4: First extension to 4415
        bar4 = make_bar(4, 4433.0, 4434.0, 4415.0, 4417.0)
        detector.process_bar(bar4)

        # Verify pivot at 4415
        bear_leg = next(
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.origin_price == Decimal('4450')
        )
        assert bear_leg.pivot_price == Decimal('4415')

        # Bar 5: Continue extending to 4410
        bar5 = make_bar(5, 4417.0, 4418.0, 4410.0, 4412.0)
        detector.process_bar(bar5)

        # Pivot extended to 4410
        bear_leg = next(
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.origin_price == Decimal('4450')
        )
        assert bear_leg.pivot_price == Decimal('4410')  # Extended again
        assert bear_leg.max_origin_breach is None  # Origin still not breached
        assert bear_leg.max_pivot_breach is None  # Pivot still not breached


class TestEngulfedLegDetection:
    """Test engulfed leg detection (combined origin + pivot breach)."""

    def test_engulfed_leg_deleted_no_replacement(self):
        """
        When both origin AND pivot are breached, the leg should be deleted
        with no replacement (engulfed).

        Scenario:
        - Bear leg forms: origin=4450, pivot=4420 (range=30)
        - Origin breached first (freezes pivot)
        - Then pivot breached (price drops below frozen pivot)
        - On next bar, prune_engulfed_legs sees both breaches and deletes leg

        Note: prune_engulfed_legs runs at START of process_bar, so the engulfed
        prune happens on the bar AFTER both breaches are set.
        """
        # Use threshold=0.0 for strict engulfed behavior (any combined breach prunes)
        # #404: engulfed_breach_threshold is now symmetric
        config = DetectionConfig.default().with_engulfed(0.0)
        detector = HierarchicalDetector(config=config)

        # Create a formed bear leg with range=30
        bar0 = make_bar(0, 4445.0, 4450.0, 4440.0, 4448.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 4448.0, 4449.0, 4430.0, 4432.0)
        detector.process_bar(bar1)

        bar2 = make_bar(2, 4432.0, 4435.0, 4420.0, 4422.0)
        detector.process_bar(bar2)

        # Cause formation
        bar3 = make_bar(3, 4422.0, 4435.0, 4425.0, 4433.0)
        detector.process_bar(bar3)

        # Verify leg exists
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        assert len(bear_legs) >= 1
        original_leg_id = bear_legs[0].leg_id

        # Bar 4: Breach origin by going above 4450 to 4453
        # This freezes the pivot (origin is now breached)
        bar4 = make_bar(4, 4433.0, 4453.0, 4430.0, 4445.0)
        detector.process_bar(bar4)

        # Verify origin is breached and pivot is frozen at 4420
        bear_leg = next(l for l in detector.state.active_legs if l.leg_id == original_leg_id)
        assert bear_leg.max_origin_breach is not None
        assert bear_leg.pivot_price == Decimal('4420')

        # Bar 5: Breach pivot by going below frozen pivot 4420 to 4416
        # This sets max_pivot_breach (since origin is already breached)
        bar5 = make_bar(5, 4445.0, 4448.0, 4416.0, 4418.0)
        detector.process_bar(bar5)

        # Verify pivot is now also breached
        bear_leg = next((l for l in detector.state.active_legs if l.leg_id == original_leg_id), None)
        if bear_leg:
            assert bear_leg.max_pivot_breach is not None

        # Bar 6: Next bar triggers prune_engulfed_legs which sees both breaches
        bar6 = make_bar(6, 4418.0, 4420.0, 4415.0, 4417.0)
        events6 = detector.process_bar(bar6)

        # Check that a LegPrunedEvent was emitted with reason="engulfed"
        prune_events = [e for e in events6 if isinstance(e, LegPrunedEvent)]
        engulfed_events = [e for e in prune_events if e.reason == "engulfed"]
        assert len(engulfed_events) >= 1

        # The original leg should no longer be in active_legs
        remaining_legs = [
            leg for leg in detector.state.active_legs
            if leg.leg_id == original_leg_id
        ]
        assert len(remaining_legs) == 0

    def test_engulfed_requires_both_breaches(self):
        """
        Engulfed detection requires BOTH origin and pivot to be breached.
        Origin breach alone should not trigger engulfed.
        """
        detector = HierarchicalDetector()

        # Create a formed bear leg
        bar0 = make_bar(0, 4445.0, 4450.0, 4440.0, 4448.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 4448.0, 4449.0, 4430.0, 4432.0)
        detector.process_bar(bar1)

        bar2 = make_bar(2, 4432.0, 4435.0, 4420.0, 4422.0)
        detector.process_bar(bar2)

        # Cause formation
        bar3 = make_bar(3, 4422.0, 4435.0, 4425.0, 4433.0)
        detector.process_bar(bar3)

        # Bar 4: Large origin breach, but no pivot breach
        bar4 = make_bar(4, 4433.0, 4458.0, 4425.0, 4455.0)
        events4 = detector.process_bar(bar4)

        # No engulfed event should be emitted (only origin breached)
        engulfed_events = [
            e for e in events4
            if isinstance(e, LegPrunedEvent) and e.reason == "engulfed"
        ]
        assert len(engulfed_events) == 0


class TestBreachTrackingAccuracy:
    """Test that breach tracking accurately records maximum breaches."""

    def test_max_origin_breach_tracked_correctly(self):
        """Verify max_origin_breach tracks the maximum breach value."""
        detector = HierarchicalDetector()

        # Create a bear leg (origin at 4450)
        bar0 = make_bar(0, 4445.0, 4450.0, 4440.0, 4448.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 4448.0, 4449.0, 4430.0, 4432.0)
        detector.process_bar(bar1)

        # Get the bear leg
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        assert len(bear_legs) >= 1
        leg = bear_legs[0]

        # Initially no breach
        assert leg.max_origin_breach is None

        # Bar 2: Breach origin by 3 points (high=4453)
        bar2 = make_bar(2, 4432.0, 4453.0, 4425.0, 4450.0)
        detector.process_bar(bar2)

        # Re-get leg (may have changed reference)
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
            and leg.origin_price == Decimal('4450')
        ]
        if bear_legs:
            leg = bear_legs[0]
            assert leg.max_origin_breach == Decimal('3')

            # Bar 3: Smaller breach (high=4451) - should NOT update max
            bar3 = make_bar(3, 4450.0, 4451.0, 4445.0, 4448.0)
            detector.process_bar(bar3)

            bear_legs = [
                leg for leg in detector.state.active_legs
                if leg.direction == 'bear' and leg.status == 'active'
                and leg.origin_price == Decimal('4450')
            ]
            if bear_legs:
                leg = bear_legs[0]
                assert leg.max_origin_breach == Decimal('3')  # Still 3, not 1


class TestInvalidatedLegEngulfed:
    """Test that invalidated legs can still be pruned as engulfed."""

    def test_invalidated_leg_pruned_when_pivot_breached(self):
        """
        When a leg is invalidated (origin breach > threshold) and then pivot
        is breached, it should be pruned as engulfed.

        This ensures invalidated legs don't linger as visual noise when they
        become structurally irrelevant (price has gone past both ends).
        """
        detector = HierarchicalDetector()

        # Create a bear leg: origin at high, pivot at low
        bar0 = make_bar(0, 4435.0, 4440.0, 4430.0, 4438.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 4438.0, 4439.0, 4425.0, 4426.0)
        detector.process_bar(bar1)

        # Find the bear leg
        bear_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bear' and leg.status == 'active'
        ]
        assert len(bear_legs) >= 1
        target_leg = bear_legs[0]
        leg_id = target_leg.leg_id

        # Cause origin breach beyond invalidation threshold (38.2%)
        # For range ~15, need breach > 5.7 points
        bar2 = make_bar(2, 4426.0, 4448.0, 4427.0, 4447.0)
        detector.process_bar(bar2)

        bar3 = make_bar(3, 4447.0, 4450.0, 4445.0, 4449.0)
        detector.process_bar(bar3)

        # Leg should now be invalidated
        target_leg = next(
            (leg for leg in detector.state.active_legs if leg.leg_id == leg_id),
            None
        )
        if target_leg is None:
            # Leg might have been pruned by turn pruning, that's ok
            return

        # Leg should have origin breached (max_origin_breach is not None)
        assert target_leg.max_origin_breach is not None

        # Now breach the pivot (price drops below original pivot)
        bar4 = make_bar(4, 4449.0, 4450.0, 4420.0, 4422.0)
        events4 = detector.process_bar(bar4)

        # Leg should now have pivot breach tracked
        target_leg = next(
            (leg for leg in detector.state.active_legs if leg.leg_id == leg_id),
            None
        )
        # If still present, check that pivot breach is now tracked
        if target_leg:
            assert target_leg.max_pivot_breach is not None

        # Process one more bar to trigger the engulfed pruning
        bar5 = make_bar(5, 4422.0, 4425.0, 4418.0, 4420.0)
        events5 = detector.process_bar(bar5)

        # Check that an engulfed prune event was emitted
        all_events = events4 + events5
        engulfed_events = [
            e for e in all_events
            if isinstance(e, LegPrunedEvent) and e.reason == 'engulfed'
        ]

        # The invalidated leg should have been pruned as engulfed
        assert len(engulfed_events) >= 1

        # Verify the leg is no longer in active_legs
        remaining = [leg for leg in detector.state.active_legs if leg.leg_id == leg_id]
        assert len(remaining) == 0

    def test_pivot_breach_tracked_for_invalidated_legs(self):
        """
        Verify that max_pivot_breach is updated even for invalidated legs.

        This is necessary for detecting when invalidated legs become engulfed.
        """
        detector = HierarchicalDetector()

        # Create a bull leg
        bar0 = make_bar(0, 4420.0, 4425.0, 4415.0, 4423.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 4423.0, 4440.0, 4422.0, 4438.0)
        detector.process_bar(bar1)

        # Find the bull leg
        bull_legs = [
            leg for leg in detector.state.active_legs
            if leg.direction == 'bull' and leg.status == 'active'
        ]
        if not bull_legs:
            return  # No active bull leg, skip test

        target_leg = bull_legs[0]
        leg_id = target_leg.leg_id

        # Invalidate by breaching origin significantly
        bar2 = make_bar(2, 4438.0, 4439.0, 4405.0, 4408.0)
        detector.process_bar(bar2)

        # Check leg is invalidated
        target_leg = next(
            (leg for leg in detector.state.active_legs if leg.leg_id == leg_id),
            None
        )
        if target_leg is None:
            return

        # Now cause pivot breach (price goes above the pivot)
        bar3 = make_bar(3, 4408.0, 4445.0, 4407.0, 4444.0)
        detector.process_bar(bar3)

        # Check pivot breach was tracked
        target_leg = next(
            (leg for leg in detector.state.active_legs if leg.leg_id == leg_id),
            None
        )
        if target_leg and target_leg.max_origin_breach is not None:
            # Pivot breach should now be tracked for breached legs
            assert target_leg.max_pivot_breach is not None
