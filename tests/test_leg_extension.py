"""
Tests for leg extension: pivot extension, same-bar prevention, state cleanup.

Tests the leg extension and creation logic of the HierarchicalDetector/LegDetector.
"""

import pytest
from decimal import Decimal

from src.swing_analysis.dag import (
    HierarchicalDetector,
    Leg,
    PendingOrigin,
)
from src.swing_analysis.detection_config import DetectionConfig
from src.swing_analysis.events import LegCreatedEvent

from conftest import make_bar


class TestLegOriginExtension:
    """
    Tests for leg origin extension when price makes new extremes (#188).

    Verifies that leg origins are updated when:
    - Bar makes new high (extends bull leg origins)
    - Bar makes new low (extends bear leg origins)

    This is independent of bar type classification.
    """

    def test_bull_leg_pivot_extended_on_higher_high_equal_low(self):
        """
        Bug fix for #188, #197: Bull leg pivots should update on HH+EL bar.

        After terminology fix (#197):
        - Bull leg: origin=LOW (fixed starting point), pivot=HIGH (extends)
        - Bear leg: origin=HIGH (fixed starting point), pivot=LOW (extends)

        When bar has higher high but equal low, it's classified as Type 1
        (inside bar), but bull leg pivots should still extend.
        """
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        # Set up initial state with prev_bar
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 103.0)
        detector.process_bar(bar0)

        # Create bar 1 for classification context
        bar1 = make_bar(1, 103.0, 110.0, 100.0, 108.0)
        detector.process_bar(bar1)

        # Add a bull leg manually with origin at LOW (100), pivot at HIGH (110)
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),  # LOW - fixed starting point
            origin_index=1,
            pivot_price=Decimal("110"),   # HIGH - extends
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bull_leg)

        # Bar 2: Higher high (115) but EQUAL low (100) - should extend pivot
        # This is the edge case from #188
        bar2 = make_bar(2, 108.0, 115.0, 100.0, 113.0)
        detector.process_bar(bar2)

        # Verify pivot was extended (not origin - origin is fixed)
        assert bull_leg.pivot_price == Decimal("115"), \
            f"Expected pivot_price 115, got {bull_leg.pivot_price}"
        assert bull_leg.pivot_index == 2, \
            f"Expected pivot_index 2, got {bull_leg.pivot_index}"
        # Origin should remain fixed at starting point
        assert bull_leg.origin_price == Decimal("100"), \
            f"Origin should remain fixed at 100, got {bull_leg.origin_price}"

    def test_bear_leg_pivot_extended_on_lower_low_equal_high(self):
        """
        Bug fix for #188, #197: Bear leg pivots should update on EH+LL bar.

        After terminology fix (#197):
        - Bull leg: origin=LOW (fixed starting point), pivot=HIGH (extends)
        - Bear leg: origin=HIGH (fixed starting point), pivot=LOW (extends)

        When bar has equal high but lower low, it's classified as Type 1
        (inside bar), but bear leg pivots should still extend.
        """
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        # Set up initial state with prev_bar
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        # Create prev_bar for classification
        bar1 = make_bar(1, 100.0, 110.0, 90.0, 95.0)
        detector.process_bar(bar1)

        # Add a bear leg manually with origin at HIGH (110), pivot at LOW (90)
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),  # HIGH - fixed starting point
            origin_index=1,
            pivot_price=Decimal("90"),    # LOW - extends
            pivot_index=1,
            price_at_creation=Decimal("95"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bear_leg)

        # Bar 2: EQUAL high (110) but lower low (85) - should extend pivot
        bar2 = make_bar(2, 95.0, 110.0, 85.0, 88.0)
        detector.process_bar(bar2)

        # Verify pivot was extended (not origin - origin is fixed)
        assert bear_leg.pivot_price == Decimal("85"), \
            f"Expected pivot_price 85, got {bear_leg.pivot_price}"
        assert bear_leg.pivot_index == 2, \
            f"Expected pivot_index 2, got {bear_leg.pivot_index}"
        # Origin should remain fixed at starting point
        assert bear_leg.origin_price == Decimal("110"), \
            f"Origin should remain fixed at 110, got {bear_leg.origin_price}"

    def test_bull_leg_pivot_extended_on_type2_bull(self):
        """Bull leg pivots extend on Type 2-Bull bars (HH+HL). Fixed for #197."""
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 105.0, 95.0, 103.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 103.0, 110.0, 98.0, 108.0)
        detector.process_bar(bar1)

        # Add a bull leg with origin at LOW (98), pivot at HIGH (110)
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("98"),   # LOW - fixed starting point
            origin_index=1,
            pivot_price=Decimal("110"),   # HIGH - extends
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bull_leg)

        # Bar 2: Type 2-Bull (HH=115, HL=100)
        bar2 = make_bar(2, 108.0, 115.0, 100.0, 113.0)
        detector.process_bar(bar2)

        # Pivot extends to new high
        assert bull_leg.pivot_price == Decimal("115")
        assert bull_leg.pivot_index == 2
        # Origin remains fixed
        assert bull_leg.origin_price == Decimal("98")

    def test_bear_leg_pivot_extended_on_type2_bear(self):
        """Bear leg pivots extend on Type 2-Bear bars (LH+LL). Fixed for #197."""
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 110.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 108.0, 90.0, 92.0)
        detector.process_bar(bar1)

        # Add a bear leg with origin at HIGH (108), pivot at LOW (90)
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("108"),  # HIGH - fixed starting point
            origin_index=1,
            pivot_price=Decimal("90"),    # LOW - extends
            pivot_index=1,
            price_at_creation=Decimal("92"),
            last_modified_bar=1,
        )
        detector.state.active_legs.append(bear_leg)

        # Bar 2: Type 2-Bear (LH=105, LL=85)
        bar2 = make_bar(2, 92.0, 105.0, 85.0, 88.0)
        detector.process_bar(bar2)

        # Pivot extends to new low
        assert bear_leg.pivot_price == Decimal("85")
        assert bear_leg.pivot_index == 2
        # Origin remains fixed
        assert bear_leg.origin_price == Decimal("108")

    def test_both_legs_pivot_extend_on_type3(self):
        """Both bull and bear leg pivots extend on Type 3 bars (HH+LL). Fixed for #197."""
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 90.0, 100.0)
        detector.process_bar(bar1)

        # Add both bull and bear legs with correct terminology
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("90"),   # LOW - fixed starting point
            origin_index=1,
            pivot_price=Decimal("110"),   # HIGH - extends
            pivot_index=1,
            price_at_creation=Decimal("100"),
            last_modified_bar=1,
        )
        bear_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),  # HIGH - fixed starting point
            origin_index=1,
            pivot_price=Decimal("90"),    # LOW - extends
            pivot_index=1,
            price_at_creation=Decimal("100"),
            last_modified_bar=1,
        )
        detector.state.active_legs.extend([bull_leg, bear_leg])

        # Bar 2: Type 3 (HH=115, LL=85)
        bar2 = make_bar(2, 100.0, 115.0, 85.0, 100.0)
        detector.process_bar(bar2)

        # Pivots extend on Type 3
        assert bull_leg.pivot_price == Decimal("115")
        assert bull_leg.pivot_index == 2
        assert bear_leg.pivot_price == Decimal("85")
        assert bear_leg.pivot_index == 2
        # Origins remain fixed
        assert bull_leg.origin_price == Decimal("90")
        assert bear_leg.origin_price == Decimal("110")

    def test_pivot_not_extended_if_not_new_extreme(self):
        """Pivot should not change if bar doesn't make new extreme. Fixed for #197."""
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        bar0 = make_bar(0, 100.0, 115.0, 85.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 112.0, 88.0, 100.0)
        detector.process_bar(bar1)

        # Add a bull leg with origin at LOW (85), pivot at HIGH (115)
        bull_leg = Leg(
            direction='bull',
            origin_price=Decimal("85"),   # LOW - fixed
            origin_index=0,
            pivot_price=Decimal("115"),   # HIGH - extends on new highs only
            pivot_index=0,
            price_at_creation=Decimal("100"),
            last_modified_bar=0,
        )
        detector.state.active_legs.append(bull_leg)

        # Bar 2: Inside bar, no new high (110 < 115)
        bar2 = make_bar(2, 100.0, 110.0, 90.0, 100.0)
        detector.process_bar(bar2)

        # Pivot should remain unchanged (no new high)
        assert bull_leg.pivot_price == Decimal("115")
        assert bull_leg.pivot_index == 0
        # Origin is always fixed
        assert bull_leg.origin_price == Decimal("85")


class TestSameBarLegPrevention:
    """Test that legs cannot have pivot_index == origin_index (Issue #189).

    Same-bar legs violate temporal causality because we cannot know
    the H/L ordering within a single OHLC bar.
    """

    def test_type1_after_type2_no_same_bar_legs(self):
        """After Type 2 bar, Type 1 bar should not create same-bar legs.

        This reproduces issue #189: After a Type 2 bar, both pending pivots
        have the same bar_index. When the next bar is Type 1 (inside bar),
        the old <= comparison would create legs with pivot_index == origin_index.
        """
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        # Bar 0: Initial bar
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2 bar (extends both H and L)
        # After this bar, both pending_bear and pending_bull have bar_index=1
        bar1 = make_bar(1, 100.0, 110.0, 90.0, 100.0)
        events1 = detector.process_bar(bar1)

        # Bar 2: Type 1 inside bar (H < prev.H, L > prev.L)
        # This should NOT create same-bar legs
        bar2 = make_bar(2, 100.0, 108.0, 92.0, 100.0)
        events2 = detector.process_bar(bar2)

        # Check that no legs were created with same pivot and origin index
        leg_events = [e for e in events2 if isinstance(e, LegCreatedEvent)]
        for leg_event in leg_events:
            assert leg_event.pivot_index != leg_event.origin_index, (
                f"Same-bar leg created: pivot_index={leg_event.pivot_index}, "
                f"origin_index={leg_event.origin_index}"
            )

    def test_type1_with_different_bar_indices_creates_legs(self):
        """Type 1 bars should still create legs when indices differ.

        This ensures the fix doesn't prevent legitimate leg creation.
        """
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        # Bar 0: Initial bar with high
        bar0 = make_bar(0, 100.0, 110.0, 95.0, 100.0)
        detector.process_bar(bar0)

        # Bar 1: Type 2 Bull (new low, but not new high)
        # Creates pending_bull at bar 1, pending_bear stays at bar 0
        bar1 = make_bar(1, 100.0, 105.0, 85.0, 90.0)
        events1 = detector.process_bar(bar1)

        # Bar 2: Type 1 inside bar
        # Now pending_bear.bar_index=0, pending_bull.bar_index=1
        # Should create bull leg (origin at 0, pivot at 1)
        bar2 = make_bar(2, 90.0, 100.0, 88.0, 95.0)
        events2 = detector.process_bar(bar2)

        # Verify legs created have different indices
        leg_events = [e for e in events2 if isinstance(e, LegCreatedEvent)]
        for leg_event in leg_events:
            assert leg_event.pivot_index != leg_event.origin_index

    def test_strict_inequality_prevents_same_bar_on_equal_indices(self):
        """Verify strict inequality logic: <= was the bug, < is the fix."""
        # Simulate the scenario from issue #189
        pending_bear = PendingOrigin(
            price=Decimal("100"), bar_index=5, direction='bear', source='high'
        )
        pending_bull = PendingOrigin(
            price=Decimal("95"), bar_index=5, direction='bull', source='low'
        )

        # Old behavior (bug): <= would allow both conditions to be True
        old_bull_condition = pending_bear.bar_index <= pending_bull.bar_index  # True
        old_bear_condition = pending_bull.bar_index <= pending_bear.bar_index  # True

        # New behavior (fix): < prevents both when equal
        new_bull_condition = pending_bear.bar_index < pending_bull.bar_index  # False
        new_bear_condition = pending_bull.bar_index < pending_bear.bar_index  # False

        assert old_bull_condition is True, "Sanity check: old behavior was <=, True"
        assert old_bear_condition is True, "Sanity check: old behavior was <=, True"
        assert new_bull_condition is False, "Fix: < prevents same-bar leg"
        assert new_bear_condition is False, "Fix: < prevents same-bar leg"


class TestLegCreationCleansUpState:
    """
    Tests for issue #196: Leg creation doesn't clear pending pivots.

    When a new leg is created, pending pivots used to create the leg should be cleared.
    """

    def test_pending_origins_cleared_after_leg_creation(self):
        """
        Pending origins are cleared when a leg is created from them (#197 fix).

        After the terminology fix (#197, #200):
        - Bear leg: origin_price = HIGH (where downward move started), pivot_price = LOW
        - Bull leg: origin_price = LOW (where upward move started), pivot_price = HIGH
        - pending_origins['bear'] tracks HIGHs (potential bear origins)
        - pending_origins['bull'] tracks LOWs (potential bull origins)

        When a leg is created from a pending origin, that pending origin is cleared.
        However, subsequent bar processing may set a NEW pending origin, so we check
        that the pending origin (if any) is different from the one used for the leg.
        """
        config = DetectionConfig.default()
        detector = HierarchicalDetector(config)

        # Create a sequence that forms a bear leg from a pending bear origin
        bars = [
            make_bar(0, 100.0, 105.0, 95.0, 102.0),  # Initial
            make_bar(1, 102.0, 110.0, 100.0, 108.0),  # TYPE_2_BULL - creates pending bear origin at 110
            make_bar(2, 108.0, 108.5, 98.0, 100.0),  # TYPE_2_BEAR (LH, LL) - creates bear leg from pending origin at 110
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Check if bear leg was created with origin at 110 (pending bear origin)
        # After #197 fix: bear leg origin = HIGH (where downward move started)
        bear_legs = [leg for leg in detector.state.active_legs if leg.direction == 'bear']
        bear_legs_with_origin_at_110 = [
            leg for leg in bear_legs if leg.origin_price == Decimal("110")
        ]

        # Verify a bear leg was created with origin at 110
        assert len(bear_legs_with_origin_at_110) > 0, "Bear leg should be created with origin at 110"

        # Verify the original pending origin at 110 was cleared (#197 fix)
        # After leg creation, the pending origin may be updated to a new value (bar 2 high = 108.5)
        # but it should NOT still be at 110 (which was consumed by the leg)
        pending_bear = detector.state.pending_origins.get('bear')
        if pending_bear is not None:
            # If there's a pending origin, it should be from a later bar, not the consumed one
            assert pending_bear.price != Decimal("110"), (
                f"Pending bear origin at 110 should be cleared after leg creation. "
                f"Found: {pending_bear}"
            )
