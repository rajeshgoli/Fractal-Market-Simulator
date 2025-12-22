"""
Test that inner structure legs are pruned even with active swings.

Issue context: If an inner bear leg is contained in an outer bear leg, and both
are invalidated, the bull leg from the inner pivot should be pruned because
there's a bull leg from the outer pivot with the same current pivot.

The inner bull leg is structurally redundant regardless of whether it has formed
a swing - there's always a better outer structure leg.
"""

import pytest
from decimal import Decimal

from src.swing_analysis.dag import HierarchicalDetector
from src.swing_analysis.swing_config import SwingConfig
from src.swing_analysis.events import LegPrunedEvent

from conftest import make_bar


def test_inner_structure_pruned_despite_swing():
    """
    Inner structure bull leg should be pruned even if it has an active swing.

    Structure:
    - Outer bear: origin=4436.75, pivot=4422.25
    - Inner bear: origin=4433.5, pivot=4426.75 (contained in outer)
    - Bull from outer pivot: origin=4422.25
    - Bull from inner pivot: origin=4426.75 (has active swing)

    When both bears are invalidated, the inner bull should be pruned.
    """
    config = SwingConfig.default()
    detector = HierarchicalDetector(config)

    bars = [
        make_bar(0, 4407.25, 4410.0, 4407.25, 4409.0),
        make_bar(1, 4409.0, 4419.25, 4408.0, 4418.0),
        # Bar 2: outer bear origin at 4436.75
        make_bar(2, 4431.25, 4436.75, 4430.75, 4433.75),
        make_bar(3, 4433.75, 4434.5, 4432.25, 4432.75),
        make_bar(4, 4433.0, 4435.25, 4432.5, 4433.25),
        make_bar(5, 4431.5, 4432.5, 4426.5, 4429.25),
        make_bar(6, 4428.75, 4428.75, 4425.0, 4426.5),
        make_bar(7, 4427.0, 4427.25, 4424.5, 4424.5),
        # Bar 8: outer pivot at 4422.25
        make_bar(8, 4424.75, 4425.0, 4422.25, 4423.25),
        make_bar(9, 4423.25, 4428.0, 4423.0, 4427.75),
        make_bar(10, 4427.75, 4431.5, 4426.5, 4431.0),
        # Bar 11: inner bear origin at 4433.5
        make_bar(11, 4431.25, 4433.5, 4431.25, 4432.5),
        make_bar(12, 4432.25, 4433.5, 4429.75, 4429.75),
        make_bar(13, 4430.0, 4430.75, 4428.0, 4428.75),
        # Bar 14: inner pivot at 4426.75
        make_bar(14, 4428.5, 4430.0, 4426.75, 4429.25),
        make_bar(15, 4429.0, 4431.0, 4427.5, 4429.75),
        make_bar(16, 4429.75, 4432.0, 4428.5, 4431.5),
        make_bar(17, 4431.5, 4434.5, 4431.0, 4434.0),
        make_bar(18, 4434.0, 4435.5, 4433.5, 4435.0),
    ]

    for bar in bars:
        detector.process_bar(bar)

    # Find the inner bull leg (origin at inner bear's pivot)
    inner_bull = next((leg for leg in detector.state.active_legs
                      if leg.direction == 'bull' and leg.origin_price == Decimal("4426.75")), None)

    assert inner_bull is not None, "Inner bull leg should exist before invalidation"
    assert inner_bull.swing_id is not None, "Inner bull leg should have formed a swing"

    # Verify the swing is active
    swing = next((s for s in detector.state.active_swings
                 if s.swing_id == inner_bull.swing_id), None)
    assert swing is not None and swing.status == 'active', "Swing should be active"

    inner_bull_id = inner_bull.leg_id

    # Bar 19: high=4443.0 invalidates BOTH bear legs
    bar19 = make_bar(19, 4435.0, 4443.0, 4434.75, 4442.0)
    events19 = detector.process_bar(bar19)

    # Check that inner structure prune occurred
    prune_events = [e for e in events19 if isinstance(e, LegPrunedEvent)]
    inner_structure_prunes = [e for e in prune_events if e.reason == "inner_structure"]

    assert len(inner_structure_prunes) > 0, "Inner structure prune should have occurred"

    # Verify the inner bull leg was pruned
    inner_bull_pruned = any(e.leg_id == inner_bull_id for e in inner_structure_prunes)
    assert inner_bull_pruned, f"Inner bull leg {inner_bull_id[:8]} should have been pruned"

    # Verify the outer bull leg still exists
    outer_bull = next((leg for leg in detector.state.active_legs
                      if leg.direction == 'bull'
                      and leg.origin_price == Decimal("4422.25")
                      and leg.status == 'active'), None)
    assert outer_bull is not None, "Outer bull leg should still be active"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
