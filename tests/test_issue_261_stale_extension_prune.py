"""
Tests for issue #261: Stale extension pruning only applies to child legs.

Root legs (no parent) are preserved to maintain the anchor that began the move.
Child legs are pruned at 3x extension beyond origin when invalidated.
"""

import pytest
from decimal import Decimal

from src.swing_analysis.dag import HierarchicalDetector, Leg
from src.swing_analysis.swing_config import SwingConfig

from conftest import make_bar


class TestStaleExtensionPruneOnlyChildren:
    """
    Tests for #261: Invalidated root legs are preserved, child legs are pruned.
    """

    def test_config_default_is_3x(self):
        """Default stale_extension_threshold should be 3.0."""
        config = SwingConfig.default()
        assert config.stale_extension_threshold == 3.0

    def test_root_leg_not_pruned_at_3x_extension(self):
        """
        Invalidated root leg (no parent) is NOT pruned at 3x extension.

        Root legs are preserved as historical anchors.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create initial bars
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 98.0, 108.0)
        detector.process_bar(bar1)

        # Manually add a breached root bull leg (no parent)
        # Origin=100, Pivot=110, Range=10
        # Use max_origin_breach to indicate leg has been breached
        root_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=1,
            pivot_price=Decimal("110"),
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
            max_origin_breach=Decimal("1"),  # Indicates origin was breached
            parent_leg_id=None,  # ROOT leg - no parent
        )
        detector.state.active_legs.append(root_leg)

        # Bar that extends 3x+ beyond origin (100 - 3*10 = 70)
        # Price at 65 is well beyond 3x extension
        bar2 = make_bar(2, 100.0, 102.0, 65.0, 68.0)
        events = detector.process_bar(bar2)

        # Root leg should NOT be pruned
        assert root_leg in detector.state.active_legs, \
            "Root leg should NOT be pruned even at 3x+ extension"

        # No extension prune events for root leg
        prune_events = [e for e in events if hasattr(e, 'reason') and e.reason == 'extension_prune']
        assert len(prune_events) == 0, "No extension_prune events for root leg"

    def test_child_leg_pruned_at_3x_extension(self):
        """
        Invalidated child leg (has parent) IS pruned at 3x extension.

        Child legs are cleaned up as price moves away.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create initial bars
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 98.0, 108.0)
        detector.process_bar(bar1)

        # Manually add a breached child bull leg (has parent)
        # Origin=100, Pivot=110, Range=10
        # Use max_origin_breach to indicate leg has been breached
        child_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=1,
            pivot_price=Decimal("110"),
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
            max_origin_breach=Decimal("1"),  # Indicates origin was breached
            parent_leg_id="some-parent-id",  # CHILD leg - has parent
        )
        detector.state.active_legs.append(child_leg)

        # Bar that extends 3x+ beyond origin (100 - 3*10 = 70)
        # Price at 65 is well beyond 3x extension
        bar2 = make_bar(2, 100.0, 102.0, 65.0, 68.0)
        events = detector.process_bar(bar2)

        # Child leg SHOULD be pruned
        assert child_leg not in detector.state.active_legs, \
            "Child leg should be pruned at 3x+ extension"

        # Extension prune event for child leg
        prune_events = [e for e in events if hasattr(e, 'reason') and e.reason == 'extension_prune']
        assert len(prune_events) == 1, "Should have extension_prune event for child leg"

    def test_bear_root_leg_not_pruned_at_3x_extension(self):
        """
        Invalidated root bear leg (no parent) is NOT pruned at 3x extension.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create initial bars
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 90.0, 95.0)
        detector.process_bar(bar1)

        # Manually add a breached root bear leg (no parent)
        # Origin=110, Pivot=90, Range=20
        # Use max_origin_breach to indicate leg has been breached
        root_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=1,
            pivot_price=Decimal("90"),
            pivot_index=1,
            price_at_creation=Decimal("95"),
            last_modified_bar=1,
            max_origin_breach=Decimal("1"),  # Indicates origin was breached
            parent_leg_id=None,  # ROOT leg - no parent
        )
        detector.state.active_legs.append(root_leg)

        # Bar that extends 3x+ beyond origin (110 + 3*20 = 170)
        # Price at 175 is well beyond 3x extension
        bar2 = make_bar(2, 100.0, 175.0, 95.0, 170.0)
        events = detector.process_bar(bar2)

        # Root leg should NOT be pruned
        assert root_leg in detector.state.active_legs, \
            "Root bear leg should NOT be pruned even at 3x+ extension"

    def test_bear_child_leg_pruned_at_3x_extension(self):
        """
        Invalidated child bear leg (has parent) IS pruned at 3x extension.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create initial bars
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 90.0, 95.0)
        detector.process_bar(bar1)

        # Manually add a breached child bear leg (has parent)
        # Origin=110, Pivot=90, Range=20
        # Use max_origin_breach to indicate leg has been breached
        child_leg = Leg(
            direction='bear',
            origin_price=Decimal("110"),
            origin_index=1,
            pivot_price=Decimal("90"),
            pivot_index=1,
            price_at_creation=Decimal("95"),
            last_modified_bar=1,
            max_origin_breach=Decimal("1"),  # Indicates origin was breached
            parent_leg_id="some-parent-id",  # CHILD leg - has parent
        )
        detector.state.active_legs.append(child_leg)

        # Bar that extends 3x+ beyond origin (110 + 3*20 = 170)
        # Price at 175 is well beyond 3x extension
        bar2 = make_bar(2, 100.0, 175.0, 95.0, 170.0)
        events = detector.process_bar(bar2)

        # Child leg SHOULD be pruned
        assert child_leg not in detector.state.active_legs, \
            "Child bear leg should be pruned at 3x+ extension"

    def test_child_leg_not_pruned_before_3x(self):
        """
        Invalidated child leg is NOT pruned before reaching 3x extension.
        """
        config = SwingConfig.default()
        detector = HierarchicalDetector(config)

        # Create initial bars
        bar0 = make_bar(0, 100.0, 105.0, 95.0, 100.0)
        detector.process_bar(bar0)

        bar1 = make_bar(1, 100.0, 110.0, 98.0, 108.0)
        detector.process_bar(bar1)

        # Add breached child bull leg
        # Origin=100, Pivot=110, Range=10
        # 3x extension = 100 - 30 = 70
        # Use max_origin_breach to indicate leg has been breached
        child_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=1,
            pivot_price=Decimal("110"),
            pivot_index=1,
            price_at_creation=Decimal("108"),
            last_modified_bar=1,
            max_origin_breach=Decimal("1"),  # Indicates origin was breached
            parent_leg_id="some-parent-id",
        )
        detector.state.active_legs.append(child_leg)

        # Bar at 2x extension (not yet 3x)
        # Price at 80 is only 2x extension
        bar2 = make_bar(2, 100.0, 102.0, 80.0, 82.0)
        events = detector.process_bar(bar2)

        # Child leg should NOT be pruned yet
        assert child_leg in detector.state.active_legs, \
            "Child leg should NOT be pruned before 3x extension"
