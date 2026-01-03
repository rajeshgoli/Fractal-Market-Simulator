"""
Tests for issue #397: Warmup count resets when switching views.

The bug was that switching from Levels at Play to DAG view triggered
a detection config sync, which created a new ReferenceLayer and reset
the bin distribution (warmup progress).

The fix adds:
1. copy_state_from() method to preserve state across config updates
2. track_formation() method for per-bar formation tracking during advances
"""

from decimal import Decimal
from dataclasses import dataclass, field

import pytest

from src.swing_analysis.reference_layer import ReferenceLayer
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import RefMetadata


@dataclass
class MockBar:
    """Mock bar for testing."""
    index: int
    timestamp: float
    open: float
    high: float
    low: float
    close: float


@dataclass
class MockLeg:
    """Mock leg for testing."""
    leg_id: str
    direction: str
    origin_price: Decimal
    pivot_price: Decimal
    range: Decimal
    depth: int = 0
    status: str = "active"
    ref: RefMetadata = field(default_factory=RefMetadata)


class TestCopyStateFrom:
    """Tests for ReferenceLayer.copy_state_from() method."""

    def test_copy_state_from_preserves_bin_distribution(self):
        """Bin distribution should be copied to new instance."""
        old_layer = ReferenceLayer()
        old_layer._bin_distribution.add_leg("leg_1", 10.0, 1000.0)
        old_layer._bin_distribution.add_leg("leg_2", 20.0, 1001.0)
        old_layer._bin_distribution.add_leg("leg_3", 30.0, 1002.0)

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        assert new_layer._bin_distribution.total_count == 3

    def test_copy_state_from_preserves_formed_refs(self):
        """Formed refs dict should be copied to new instance."""
        old_layer = ReferenceLayer()
        old_layer._formed_refs = {
            "leg_1": Decimal("100"),
            "leg_2": Decimal("200"),
            "leg_3": Decimal("300"),
        }

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        assert new_layer._formed_refs == {
            "leg_1": Decimal("100"),
            "leg_2": Decimal("200"),
            "leg_3": Decimal("300"),
        }

    def test_copy_state_from_preserves_tracked_for_crossing(self):
        """Tracked for crossing set should be copied to new instance."""
        old_layer = ReferenceLayer()
        old_layer._tracked_for_crossing = {"leg_a", "leg_b"}

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        assert new_layer._tracked_for_crossing == {"leg_a", "leg_b"}

    def test_copy_state_from_preserves_seen_leg_ids(self):
        """Seen leg IDs set should be copied to new instance."""
        old_layer = ReferenceLayer()
        old_layer._seen_leg_ids = {"id_1", "id_2", "id_3", "id_4"}

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        assert new_layer._seen_leg_ids == {"id_1", "id_2", "id_3", "id_4"}

    def test_copy_state_from_creates_independent_copies(self):
        """Copied state should be independent (mutations don't affect original)."""
        old_layer = ReferenceLayer()
        old_layer._bin_distribution.add_leg("leg_1", 10.0, 1000.0)
        old_layer._bin_distribution.add_leg("leg_2", 20.0, 1001.0)
        old_layer._formed_refs = {"leg_1": Decimal("100")}  # dict with pivot price
        old_layer._seen_leg_ids = {"id_1"}

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        # Mutate new layer
        new_layer._bin_distribution.add_leg("leg_3", 30.0, 1002.0)
        new_layer._formed_refs["leg_2"] = (Decimal("100"), 0)  # dummy pivot price
        new_layer._seen_leg_ids.add("id_2")

        # Original should be unchanged
        assert old_layer._bin_distribution.total_count == 2
        assert old_layer._formed_refs == {"leg_1": Decimal("100")}
        assert old_layer._seen_leg_ids == {"id_1"}

    def test_copy_state_from_preserves_cold_start_progress(self):
        """Cold start progress (warmup count) should be preserved."""
        config = ReferenceConfig.default()
        old_layer = ReferenceLayer(reference_config=config)

        # Simulate having collected 43 swings
        for i in range(43):
            old_layer._bin_distribution.add_leg(f"leg_{i}", 10.0 + i, 1000.0 + i)
            old_layer._seen_leg_ids.add(f"leg_{i}")

        assert old_layer.cold_start_progress == (43, 50)
        assert old_layer.is_cold_start is True

        # Create new layer with different config and copy state
        new_layer = ReferenceLayer(reference_config=config)
        new_layer.copy_state_from(old_layer)

        # Warmup progress should be preserved
        assert new_layer.cold_start_progress == (43, 50)
        assert new_layer.is_cold_start is True

    def test_copy_state_from_empty_layer(self):
        """Copying from empty layer should work without error."""
        old_layer = ReferenceLayer()
        new_layer = ReferenceLayer()

        # Should not raise
        new_layer.copy_state_from(old_layer)

        assert new_layer._bin_distribution.total_count == 0
        assert new_layer._formed_refs == {}  # empty dict
        assert new_layer._tracked_for_crossing == set()
        assert new_layer._seen_leg_ids == set()


class TestWarmupStatePreservation:
    """Integration tests for warmup state preservation across config updates."""

    def test_warmup_progress_preserved_after_reaching_threshold(self):
        """After passing cold start, state should still be preserved."""
        old_layer = ReferenceLayer()

        # Simulate having collected 55 swings (past the 50 threshold)
        for i in range(55):
            old_layer._bin_distribution.add_leg(f"leg_{i}", 10.0 + i, 1000.0 + i)
            old_layer._seen_leg_ids.add(f"leg_{i}")
            old_layer._formed_refs[f"leg_{i}"] = (Decimal("100"), 0)  # dummy pivot price

        assert old_layer.is_cold_start is False
        assert old_layer.cold_start_progress == (55, 50)

        # Create new layer and copy state
        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        # Should still be past cold start
        assert new_layer.is_cold_start is False
        assert new_layer.cold_start_progress == (55, 50)
        assert len(new_layer._formed_refs) == 55


class TestTrackFormation:
    """Tests for ReferenceLayer.track_formation() method."""

    def test_track_formation_adds_formed_legs_to_distribution(self):
        """track_formation should add formed legs to bin distribution."""
        ref_layer = ReferenceLayer()

        # Create a bear leg (high to low) - price at 38.2% retracement = formed
        # Origin = 110, Pivot = 100, Range = 10
        # Price at 103.82 = 38.2% from pivot toward origin = formed
        leg = MockLeg(
            leg_id="leg_1",
            direction="bear",
            origin_price=Decimal("110"),
            pivot_price=Decimal("100"),
            range=Decimal("10"),
        )

        # Bar with close at 104 (40% retracement, should form)
        bar = MockBar(
            index=0,
            timestamp=1000.0,
            open=102.0,
            high=105.0,
            low=101.0,
            close=104.0,
        )

        assert ref_layer._bin_distribution.total_count == 0
        assert "leg_1" not in ref_layer._formed_refs

        ref_layer.track_formation([leg], bar)

        # Leg should be formed and added to distribution
        assert "leg_1" in ref_layer._formed_refs
        assert ref_layer._bin_distribution.total_count == 1
        assert ref_layer._bin_distribution.leg_ranges["leg_1"] == 10.0

    def test_track_formation_ignores_unformed_legs(self):
        """track_formation should not add legs that haven't formed yet."""
        ref_layer = ReferenceLayer()

        # Create a bear leg - price NOT at 38.2% retracement yet
        leg = MockLeg(
            leg_id="leg_1",
            direction="bear",
            origin_price=Decimal("110"),
            pivot_price=Decimal("100"),
            range=Decimal("10"),
        )

        # Bar with close at 101 (10% retracement, not formed yet)
        bar = MockBar(
            index=0,
            timestamp=1000.0,
            open=100.0,
            high=102.0,
            low=100.0,
            close=101.0,
        )

        ref_layer.track_formation([leg], bar)

        # Leg should NOT be formed
        assert "leg_1" not in ref_layer._formed_refs
        assert ref_layer._bin_distribution.total_count == 0

    def test_track_formation_doesnt_duplicate_legs(self):
        """track_formation should not add same leg twice to distribution."""
        ref_layer = ReferenceLayer()

        leg = MockLeg(
            leg_id="leg_1",
            direction="bear",
            origin_price=Decimal("110"),
            pivot_price=Decimal("100"),
            range=Decimal("10"),
        )

        bar = MockBar(
            index=0,
            timestamp=1000.0,
            open=102.0,
            high=105.0,
            low=101.0,
            close=104.0,
        )

        # Track twice
        ref_layer.track_formation([leg], bar)
        ref_layer.track_formation([leg], bar)

        # Should only be added once
        assert ref_layer._bin_distribution.total_count == 1

    def test_track_formation_tracks_multiple_legs(self):
        """track_formation should track multiple legs in one call."""
        ref_layer = ReferenceLayer()

        # Bear leg: origin=110 (high), pivot=100 (low)
        # For formation, price must move from pivot toward origin by 38.2%
        # Price at 104 = 40% from pivot(100) toward origin(110) = formed
        leg1 = MockLeg(
            leg_id="leg_1",
            direction="bear",
            origin_price=Decimal("110"),
            pivot_price=Decimal("100"),
            range=Decimal("10"),
        )
        # Bull leg: origin=100 (low), pivot=110 (high)
        # For formation, price must move from pivot toward origin by 38.2%
        # Price at 104 = 60% from pivot(110) toward origin(100) = formed
        leg2 = MockLeg(
            leg_id="leg_2",
            direction="bull",
            origin_price=Decimal("100"),
            pivot_price=Decimal("110"),
            range=Decimal("10"),
        )

        # Bar at 104 - both legs should form
        bar = MockBar(
            index=0,
            timestamp=1000.0,
            open=103.0,
            high=105.0,
            low=103.0,
            close=104.0,
        )

        ref_layer.track_formation([leg1, leg2], bar)

        assert "leg_1" in ref_layer._formed_refs
        assert "leg_2" in ref_layer._formed_refs
        assert ref_layer._bin_distribution.total_count == 2
