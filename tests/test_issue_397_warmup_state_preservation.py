"""
Tests for issue #397: Warmup count resets when switching views.

The bug was that switching from Levels at Play to DAG view triggered
a detection config sync, which created a new ReferenceLayer and reset
the _range_distribution (warmup progress).

The fix adds copy_state_from() method to ReferenceLayer and uses it
in the config update endpoint to preserve accumulated state.
"""

from decimal import Decimal

import pytest

from src.swing_analysis.reference_layer import ReferenceLayer
from src.swing_analysis.reference_config import ReferenceConfig


class TestCopyStateFrom:
    """Tests for ReferenceLayer.copy_state_from() method."""

    def test_copy_state_from_preserves_range_distribution(self):
        """Range distribution should be copied to new instance."""
        old_layer = ReferenceLayer()
        old_layer._range_distribution = [Decimal("10"), Decimal("20"), Decimal("30")]

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        assert new_layer._range_distribution == [Decimal("10"), Decimal("20"), Decimal("30")]

    def test_copy_state_from_preserves_formed_refs(self):
        """Formed refs set should be copied to new instance."""
        old_layer = ReferenceLayer()
        old_layer._formed_refs = {"leg_1", "leg_2", "leg_3"}

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        assert new_layer._formed_refs == {"leg_1", "leg_2", "leg_3"}

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
        old_layer._range_distribution = [Decimal("10"), Decimal("20")]
        old_layer._formed_refs = {"leg_1"}
        old_layer._seen_leg_ids = {"id_1"}

        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        # Mutate new layer
        new_layer._range_distribution.append(Decimal("30"))
        new_layer._formed_refs.add("leg_2")
        new_layer._seen_leg_ids.add("id_2")

        # Original should be unchanged
        assert old_layer._range_distribution == [Decimal("10"), Decimal("20")]
        assert old_layer._formed_refs == {"leg_1"}
        assert old_layer._seen_leg_ids == {"id_1"}

    def test_copy_state_from_preserves_cold_start_progress(self):
        """Cold start progress (warmup count) should be preserved."""
        config = ReferenceConfig.default()
        old_layer = ReferenceLayer(reference_config=config)

        # Simulate having collected 43 swings
        for i in range(43):
            old_layer._range_distribution.append(Decimal(str(10 + i)))
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

        assert new_layer._range_distribution == []
        assert new_layer._formed_refs == set()
        assert new_layer._tracked_for_crossing == set()
        assert new_layer._seen_leg_ids == set()


class TestWarmupStatePreservation:
    """Integration tests for warmup state preservation across config updates."""

    def test_warmup_progress_preserved_after_reaching_threshold(self):
        """After passing cold start, state should still be preserved."""
        old_layer = ReferenceLayer()

        # Simulate having collected 55 swings (past the 50 threshold)
        for i in range(55):
            old_layer._range_distribution.append(Decimal(str(10 + i)))
            old_layer._seen_leg_ids.add(f"leg_{i}")
            old_layer._formed_refs.add(f"leg_{i}")

        assert old_layer.is_cold_start is False
        assert old_layer.cold_start_progress == (55, 50)

        # Create new layer and copy state
        new_layer = ReferenceLayer()
        new_layer.copy_state_from(old_layer)

        # Should still be past cold start
        assert new_layer.is_cold_start is False
        assert new_layer.cold_start_progress == (55, 50)
        assert len(new_layer._formed_refs) == 55
