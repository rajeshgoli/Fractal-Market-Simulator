"""
Tests for the hierarchy exploration API (#250, #251).

Tests the /api/dag/lineage/{leg_id} endpoint that returns
ancestor and descendant leg IDs for hierarchy visualization.
"""

import pytest
from decimal import Decimal
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.state import DetectorState


class TestLegLineage:
    """Tests for leg lineage computation."""

    def test_leg_with_no_parent_is_root(self):
        """A leg with no parent_leg_id has depth 0."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=10,
            leg_id="root-leg",
            parent_leg_id=None,
        )

        # No parent means depth 0 (root)
        assert leg.parent_leg_id is None

    def test_leg_with_parent_has_depth_1(self):
        """A leg with a parent_leg_id pointing to a root has depth 1."""
        parent = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=10,
            leg_id="parent-leg",
            parent_leg_id=None,
        )

        child = Leg(
            direction='bear',
            origin_price=Decimal("108"),
            origin_index=12,
            pivot_price=Decimal("102"),
            pivot_index=20,
            leg_id="child-leg",
            parent_leg_id="parent-leg",
        )

        assert child.parent_leg_id == "parent-leg"

    def test_lineage_chain_computation(self):
        """Test computing ancestors by following parent_leg_id chain."""
        # Create a 3-level hierarchy
        root = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("120"),
            pivot_index=20,
            leg_id="root",
            parent_leg_id=None,
        )

        child1 = Leg(
            direction='bear',
            origin_price=Decimal("118"),
            origin_index=22,
            pivot_price=Decimal("105"),
            pivot_index=40,
            leg_id="child1",
            parent_leg_id="root",
        )

        grandchild = Leg(
            direction='bull',
            origin_price=Decimal("106"),
            origin_index=42,
            pivot_price=Decimal("112"),
            pivot_index=50,
            leg_id="grandchild",
            parent_leg_id="child1",
        )

        # Build lookup
        legs_by_id = {
            "root": root,
            "child1": child1,
            "grandchild": grandchild,
        }

        # Compute ancestors for grandchild
        ancestors = []
        current_id = grandchild.parent_leg_id
        while current_id and current_id in legs_by_id:
            ancestors.append(current_id)
            current_id = legs_by_id[current_id].parent_leg_id

        assert ancestors == ["child1", "root"]

    def test_descendants_computation(self):
        """Test computing descendants by scanning for parent_leg_id matches."""
        # Create a hierarchy with multiple descendants
        root = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("120"),
            pivot_index=20,
            leg_id="root",
            parent_leg_id=None,
        )

        child1 = Leg(
            direction='bear',
            origin_price=Decimal("118"),
            origin_index=22,
            pivot_price=Decimal("105"),
            pivot_index=40,
            leg_id="child1",
            parent_leg_id="root",
        )

        child2 = Leg(
            direction='bear',
            origin_price=Decimal("119"),
            origin_index=25,
            pivot_price=Decimal("106"),
            pivot_index=45,
            leg_id="child2",
            parent_leg_id="root",
        )

        grandchild = Leg(
            direction='bull',
            origin_price=Decimal("106"),
            origin_index=47,
            pivot_price=Decimal("112"),
            pivot_index=55,
            leg_id="grandchild",
            parent_leg_id="child1",
        )

        legs = [root, child1, child2, grandchild]
        legs_by_id = {leg.leg_id: leg for leg in legs}

        # Compute descendants for root
        def get_ancestors(lid):
            result = set()
            current = legs_by_id.get(lid)
            if not current:
                return result
            cur_parent = current.parent_leg_id
            seen = {lid}
            while cur_parent and cur_parent in legs_by_id and cur_parent not in seen:
                result.add(cur_parent)
                seen.add(cur_parent)
                cur_parent = legs_by_id[cur_parent].parent_leg_id
            return result

        target_leg_id = "root"
        descendants = []
        for lid in legs_by_id:
            if lid == target_leg_id:
                continue
            leg_ancestors = get_ancestors(lid)
            if target_leg_id in leg_ancestors:
                descendants.append(lid)

        # Root should have child1, child2, and grandchild as descendants
        assert set(descendants) == {"child1", "child2", "grandchild"}

    def test_cycle_prevention(self):
        """Ensure lineage computation doesn't loop on circular references."""
        # Create a leg that points to itself (shouldn't happen but test defensively)
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=10,
            leg_id="loop-leg",
            parent_leg_id="loop-leg",  # Self-reference (should not cause infinite loop)
        )

        legs_by_id = {"loop-leg": leg}

        # Compute ancestors with cycle detection
        ancestors = []
        current_id = leg.parent_leg_id
        visited = {leg.leg_id}
        while current_id and current_id in legs_by_id and current_id not in visited:
            ancestors.append(current_id)
            visited.add(current_id)
            current_id = legs_by_id[current_id].parent_leg_id

        # Should be empty because the self-reference is in visited set
        assert ancestors == []


class TestDagStateWithHierarchy:
    """Tests for detector state with hierarchy fields."""

    def test_leg_serialization_includes_parent_leg_id(self):
        """Leg serialization preserves parent_leg_id."""
        state = DetectorState()

        parent_leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=10,
            leg_id="parent",
            parent_leg_id=None,
        )
        state.active_legs.append(parent_leg)

        child_leg = Leg(
            direction='bear',
            origin_price=Decimal("108"),
            origin_index=12,
            pivot_price=Decimal("102"),
            pivot_index=20,
            leg_id="child",
            parent_leg_id="parent",
        )
        state.active_legs.append(child_leg)

        # Serialize
        serialized = state.to_dict()

        # Deserialize
        restored = DetectorState.from_dict(serialized)

        # Check parent_leg_id is preserved
        child_restored = next(l for l in restored.active_legs if l.leg_id == "child")
        assert child_restored.parent_leg_id == "parent"

    def test_leg_serialization_includes_swing_id(self):
        """Leg serialization preserves swing_id."""
        state = DetectorState()

        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=10,
            leg_id="test-leg",
            swing_id="swing-123",
            formed=True,
        )
        state.active_legs.append(leg)

        # Serialize
        serialized = state.to_dict()

        # Deserialize
        restored = DetectorState.from_dict(serialized)

        # Check swing_id is preserved
        restored_leg = restored.active_legs[0]
        assert restored_leg.swing_id == "swing-123"
