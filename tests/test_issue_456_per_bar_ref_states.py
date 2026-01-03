"""
Tests for per-bar reference state buffering (#456).

Issue #456: Performance optimization for Levels at Play view.
During high-speed playback, instead of per-bar API fetches for reference state,
the frontend uses buffered ref_states from the advance response.

Key changes tested:
1. RefStateSnapshot schema includes full reference state (references, filtered_legs, etc.)
2. build_ref_state_snapshot helper builds snapshots from ReferenceState
3. Advance endpoint includes per-bar ref states when requested
"""

import pytest
from decimal import Decimal

from src.swing_analysis.reference_layer import ReferenceLayer, ReferenceState, ReferenceSwing
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.types import Bar
from src.replay_server.routers.helpers.builders import build_ref_state_snapshot
from src.replay_server.schemas import RefStateSnapshot, ReferenceSwingResponse


class TestRefStateSnapshotSchema:
    """Tests for the expanded RefStateSnapshot schema (#456)."""

    def test_snapshot_has_references_field(self):
        """RefStateSnapshot should include references field."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=["leg_1"],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
        )
        assert hasattr(snapshot, 'references')
        assert isinstance(snapshot.references, list)

    def test_snapshot_has_filtered_legs_field(self):
        """RefStateSnapshot should include filtered_legs field."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=["leg_1"],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
        )
        assert hasattr(snapshot, 'filtered_legs')
        assert isinstance(snapshot.filtered_legs, list)

    def test_snapshot_has_warmup_fields(self):
        """RefStateSnapshot should include warmup state fields."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=[],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=True,
            warmup_progress=[10, 50],
            median=5.0,
        )
        assert snapshot.is_warming_up is True
        assert snapshot.warmup_progress == [10, 50]
        assert snapshot.median == 5.0

    def test_snapshot_serializes_to_dict(self):
        """RefStateSnapshot should serialize properly for API response."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=["leg_1", "leg_2"],
            references=[],
            filtered_legs=[],
            current_price=105.5,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
        )
        data = snapshot.model_dump()
        assert data['bar_index'] == 100
        assert data['formed_leg_ids'] == ["leg_1", "leg_2"]
        assert data['current_price'] == 105.5
        assert data['is_warming_up'] is False


class TestBuildRefStateSnapshot:
    """Tests for the build_ref_state_snapshot helper function (#456)."""

    def _create_leg(self, direction='bull', origin_price=100, pivot_price=110, origin_index=0, pivot_index=5):
        """Helper to create a test Leg."""
        return Leg(
            direction=direction,
            origin_price=Decimal(str(origin_price)),
            origin_index=origin_index,
            pivot_price=Decimal(str(pivot_price)),
            pivot_index=pivot_index,
        )

    def _create_bar(self, index=100, close=105.0):
        """Helper to create a test Bar."""
        return Bar(
            index=index,
            timestamp=1640000000 + index * 60,
            open=100.0,
            high=110.0,
            low=98.0,
            close=close,
        )

    def test_builds_snapshot_with_empty_refs(self):
        """build_ref_state_snapshot should work with empty references."""
        ref_layer = ReferenceLayer()
        ref_state = ReferenceState(active_filtered=[],
            references=[],
            by_bin={},
            significant=[],
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=(10, 50),
        )
        bar = self._create_bar(index=100, close=105.0)

        snapshot = build_ref_state_snapshot(
            bar_index=100,
            ref_layer=ref_layer,
            ref_state=ref_state,
            bar=bar,
            active_legs=[],  # #458: required for crossing detection
        )

        assert snapshot.bar_index == 100
        assert snapshot.references == []
        assert snapshot.current_price == 105.0
        assert snapshot.is_warming_up is True

    def test_builds_snapshot_with_references(self):
        """build_ref_state_snapshot should include reference data."""
        ref_layer = ReferenceLayer()
        leg = self._create_leg(direction='bull', origin_price=100, pivot_price=120)
        ref_swing = ReferenceSwing(
            leg=leg,
            bin=8,
            depth=0,
            location=0.5,
            salience_score=0.8,
        )
        ref_state = ReferenceState(active_filtered=[],
            references=[ref_swing],
            by_bin={8: [ref_swing]},
            significant=[ref_swing],
            by_depth={0: [ref_swing]},
            by_direction={'bull': [ref_swing], 'bear': []},
            direction_imbalance='bull',
            is_warming_up=False,
            warmup_progress=(50, 50),
        )
        bar = self._create_bar(index=100, close=110.0)

        snapshot = build_ref_state_snapshot(
            bar_index=100,
            ref_layer=ref_layer,
            ref_state=ref_state,
            bar=bar,
            active_legs=[leg],  # #458: required for crossing detection
        )

        assert snapshot.bar_index == 100
        assert len(snapshot.references) == 1
        assert snapshot.references[0].leg_id == leg.leg_id
        assert snapshot.references[0].bin == 8
        assert snapshot.references[0].direction == 'bull'
        assert snapshot.references[0].salience_score == 0.8
        assert snapshot.current_price == 110.0
        assert snapshot.is_warming_up is False

    def test_snapshot_includes_warmup_state(self):
        """build_ref_state_snapshot should capture warmup state correctly."""
        ref_layer = ReferenceLayer()
        ref_state = ReferenceState(active_filtered=[],
            references=[],
            by_bin={},
            significant=[],
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=(25, 50),
        )
        bar = self._create_bar(index=50, close=100.0)

        snapshot = build_ref_state_snapshot(
            bar_index=50,
            ref_layer=ref_layer,
            ref_state=ref_state,
            bar=bar,
            active_legs=[],  # #458: required for crossing detection
        )

        assert snapshot.is_warming_up is True
        assert snapshot.warmup_progress == [25, 50]

    def test_snapshot_reference_response_has_all_fields(self):
        """ReferenceSwingResponse in snapshot should have all required fields."""
        ref_layer = ReferenceLayer()
        leg = self._create_leg(
            direction='bear',
            origin_price=150,
            pivot_price=130,
            origin_index=10,
            pivot_index=20,
        )
        # Note: depth comes from leg.depth (default 0), not ref_swing.depth
        # impulsiveness comes from leg.impulsiveness (default None)
        ref_swing = ReferenceSwing(
            leg=leg,
            bin=9,
            depth=1,  # ReferenceSwing.depth is separate from leg.depth
            location=0.618,
            salience_score=0.9,
        )
        ref_state = ReferenceState(active_filtered=[],
            references=[ref_swing],
            by_bin={9: [ref_swing]},
            significant=[ref_swing],
            by_depth={1: [ref_swing]},
            by_direction={'bull': [], 'bear': [ref_swing]},
            direction_imbalance='bear',
            is_warming_up=False,
            warmup_progress=(50, 50),
        )
        bar = self._create_bar(index=100, close=140.0)

        snapshot = build_ref_state_snapshot(
            bar_index=100,
            ref_layer=ref_layer,
            ref_state=ref_state,
            bar=bar,
            active_legs=[leg],  # #458: required for crossing detection
        )

        ref_response = snapshot.references[0]
        assert ref_response.leg_id == leg.leg_id
        assert ref_response.bin == 9
        # depth in response comes from leg.depth, which defaults to 0
        assert ref_response.depth == leg.depth  # 0 by default
        assert ref_response.location == 0.618
        assert ref_response.salience_score == 0.9
        assert ref_response.direction == 'bear'
        assert ref_response.origin_price == 150.0
        assert ref_response.origin_index == 10
        assert ref_response.pivot_price == 130.0
        assert ref_response.pivot_index == 20
        # impulsiveness comes from leg.impulsiveness, which defaults to None
        assert ref_response.impulsiveness == leg.impulsiveness


class TestRefStateSnapshotIntegration:
    """Integration tests for per-bar ref state buffering (#456)."""

    def test_snapshot_compatible_with_frontend_format(self):
        """Snapshot fields should match what frontend expects from ReferenceStateResponse."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=["leg_1"],
            references=[
                ReferenceSwingResponse(
                    leg_id="leg_1",
                    bin=8,
                    median_multiple=5.5,
                    depth=0,
                    location=0.5,
                    salience_score=0.8,
                    direction='bull',
                    origin_price=100.0,
                    origin_index=0,
                    pivot_price=110.0,
                    pivot_index=5,
                    impulsiveness=0.6,
                )
            ],
            filtered_legs=[],
            current_price=105.0,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
        )

        # Verify all fields frontend needs are present
        data = snapshot.model_dump()
        assert 'references' in data
        assert 'filtered_legs' in data
        assert 'is_warming_up' in data
        assert 'warmup_progress' in data
        assert 'median' in data

        # Verify reference structure
        ref = data['references'][0]
        assert ref['leg_id'] == 'leg_1'
        assert ref['bin'] == 8
        assert ref['direction'] == 'bull'
        assert ref['salience_score'] == 0.8
        assert ref['origin_price'] == 100.0
        assert ref['pivot_price'] == 110.0

    def test_multiple_references_in_snapshot(self):
        """Snapshot should handle multiple references correctly."""
        refs = [
            ReferenceSwingResponse(
                leg_id=f"leg_{i}",
                bin=8 + (i % 3),
                median_multiple=5.0 + i,
                depth=0,
                location=0.5,
                salience_score=0.9 - (i * 0.1),
                direction='bull' if i % 2 == 0 else 'bear',
                origin_price=100.0 + i,
                origin_index=i * 10,
                pivot_price=110.0 + i,
                pivot_index=i * 10 + 5,
                impulsiveness=0.5,
            )
            for i in range(5)
        ]

        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=[r.leg_id for r in refs],
            references=refs,
            filtered_legs=[],
            current_price=105.0,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
        )

        assert len(snapshot.references) == 5
        assert len(snapshot.formed_leg_ids) == 5
        # References should maintain order (sorted by salience on backend)
        for i, ref in enumerate(snapshot.references):
            assert ref.leg_id == f"leg_{i}"
