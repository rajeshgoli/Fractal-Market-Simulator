"""
Tests for Issue #458: Buffer auto-tracked legs and crossing events during playback.

Verifies that:
1. RefStateSnapshot includes auto_tracked_leg_id and crossing_events fields
2. Auto-tracked leg is computed (top reference if no manual pin)
3. Crossing events are detected for the auto-tracked leg
4. Manual pin overrides auto-tracking
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.reference_layer import ReferenceLayer, ReferenceSwing, ReferenceState
from src.swing_analysis.types import Bar
from src.replay_server.schemas import RefStateSnapshot, LevelCrossEventResponse
from src.replay_server.routers.helpers.builders import build_ref_state_snapshot


class TestAutoTrackedLegInSnapshot:
    """Test auto_tracked_leg_id field in RefStateSnapshot."""

    def _create_leg(self, direction='bull', origin_price=100, pivot_price=120,
                    origin_index=0, pivot_index=10, leg_id=None):
        """Helper to create a leg for testing."""
        leg = Leg(
            direction=direction,
            origin_price=Decimal(str(origin_price)),
            origin_index=origin_index,
            pivot_price=Decimal(str(pivot_price)),
            pivot_index=pivot_index,
        )
        if leg_id:
            leg.leg_id = leg_id
        return leg

    def _create_bar(self, index=0, close=100.0, low=99.0, high=101.0):
        """Helper to create a bar for testing."""
        return Bar(
            index=index,
            timestamp=datetime.now().timestamp(),
            open=close,
            high=high,
            low=low,
            close=close,
        )

    def test_snapshot_includes_auto_tracked_leg_id_field(self):
        """RefStateSnapshot should have auto_tracked_leg_id field."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=[],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=True,
            warmup_progress=[0, 50],
            median=0.0,
        )

        assert hasattr(snapshot, 'auto_tracked_leg_id')
        assert snapshot.auto_tracked_leg_id is None

    def test_snapshot_includes_crossing_events_field(self):
        """RefStateSnapshot should have crossing_events field."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=[],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=True,
            warmup_progress=[0, 50],
            median=0.0,
        )

        assert hasattr(snapshot, 'crossing_events')
        assert snapshot.crossing_events == []

    def test_auto_tracked_leg_is_top_reference(self):
        """Auto-tracked leg should be the top reference when no manual pin."""
        ref_layer = ReferenceLayer()
        leg = self._create_leg(direction='bull', origin_price=100, pivot_price=120)
        ref_swing = ReferenceSwing(
            leg=leg,
            bin=8,
            depth=0,
            location=0.5,
            salience_score=0.9,
        )
        ref_state = ReferenceState(
            active_filtered=[],
            references=[ref_swing],  # Top reference
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
            active_legs=[leg],
        )

        assert snapshot.auto_tracked_leg_id == leg.leg_id

    def test_no_auto_tracked_leg_when_no_references(self):
        """Auto-tracked leg should be None when no references exist."""
        ref_layer = ReferenceLayer()
        ref_state = ReferenceState(
            active_filtered=[],
            references=[],  # No references
            by_bin={},
            significant=[],
            by_depth={},
            by_direction={'bull': [], 'bear': []},
            direction_imbalance=None,
            is_warming_up=True,
            warmup_progress=(10, 50),
        )
        bar = self._create_bar(index=100, close=110.0)

        snapshot = build_ref_state_snapshot(
            bar_index=100,
            ref_layer=ref_layer,
            ref_state=ref_state,
            bar=bar,
            active_legs=[],
        )

        assert snapshot.auto_tracked_leg_id is None
        assert snapshot.crossing_events == []

    def test_manual_pin_overrides_auto_tracking(self):
        """When user has pinned a leg, use that instead of top reference."""
        ref_layer = ReferenceLayer()

        # Create two legs - pin the second one
        leg1 = self._create_leg(leg_id='top_leg', direction='bull', origin_price=100, pivot_price=120)
        leg2 = self._create_leg(leg_id='pinned_leg', direction='bear', origin_price=150, pivot_price=130)

        ref_swing1 = ReferenceSwing(leg=leg1, bin=8, depth=0, location=0.5, salience_score=0.9)
        ref_swing2 = ReferenceSwing(leg=leg2, bin=7, depth=0, location=0.6, salience_score=0.7)

        ref_state = ReferenceState(
            active_filtered=[],
            references=[ref_swing1, ref_swing2],  # leg1 is top
            by_bin={8: [ref_swing1], 7: [ref_swing2]},
            significant=[ref_swing1],
            by_depth={0: [ref_swing1, ref_swing2]},
            by_direction={'bull': [ref_swing1], 'bear': [ref_swing2]},
            direction_imbalance='bull',
            is_warming_up=False,
            warmup_progress=(50, 50),
        )

        # User pins leg2
        ref_layer.add_crossing_tracking('pinned_leg')

        bar = self._create_bar(index=100, close=140.0)

        snapshot = build_ref_state_snapshot(
            bar_index=100,
            ref_layer=ref_layer,
            ref_state=ref_state,
            bar=bar,
            active_legs=[leg1, leg2],
        )

        # Should use pinned leg, not top reference
        assert snapshot.auto_tracked_leg_id == 'pinned_leg'


class TestCrossingEventsInSnapshot:
    """Test crossing_events field in RefStateSnapshot."""

    def _create_leg(self, direction='bull', origin_price=100, pivot_price=120,
                    origin_index=0, pivot_index=10, leg_id=None, formed=True):
        """Helper to create a leg for testing."""
        leg = Leg(
            direction=direction,
            origin_price=Decimal(str(origin_price)),
            origin_index=origin_index,
            pivot_price=Decimal(str(pivot_price)),
            pivot_index=pivot_index,
        )
        leg.formed = formed
        if leg_id:
            leg.leg_id = leg_id
        return leg

    def _create_bar(self, index=0, close=100.0, low=99.0, high=101.0):
        """Helper to create a bar for testing."""
        return Bar(
            index=index,
            timestamp=datetime.now().timestamp(),
            open=close,
            high=high,
            low=low,
            close=close,
        )

    def test_crossing_events_empty_for_first_bar(self):
        """First bar of tracking should not produce crossing events."""
        ref_layer = ReferenceLayer()
        leg = self._create_leg(direction='bull', origin_price=100, pivot_price=120)
        ref_swing = ReferenceSwing(leg=leg, bin=8, depth=0, location=0.5, salience_score=0.9)
        ref_state = ReferenceState(
            active_filtered=[],
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
            active_legs=[leg],
        )

        # First bar shouldn't have crossings (no previous level to compare)
        assert snapshot.crossing_events == []

    def test_crossing_event_structure(self):
        """LevelCrossEventResponse should have correct structure."""
        event = LevelCrossEventResponse(
            leg_id='test_leg',
            direction='bull',
            level_crossed=0.382,
            cross_direction='up',
            bar_index=100,
            timestamp='2024-01-01T12:00:00',
        )

        assert event.leg_id == 'test_leg'
        assert event.direction == 'bull'
        assert event.level_crossed == 0.382
        assert event.cross_direction == 'up'
        assert event.bar_index == 100


class TestSnapshotSerialization:
    """Test that new fields serialize correctly."""

    def test_serializes_with_auto_tracked_leg_id(self):
        """Snapshot should serialize auto_tracked_leg_id correctly."""
        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=['leg_1'],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
            auto_tracked_leg_id='leg_1',
            crossing_events=[],
        )

        data = snapshot.model_dump()
        assert data['auto_tracked_leg_id'] == 'leg_1'
        assert data['crossing_events'] == []

    def test_serializes_with_crossing_events(self):
        """Snapshot should serialize crossing_events correctly."""
        events = [
            LevelCrossEventResponse(
                leg_id='leg_1',
                direction='bull',
                level_crossed=0.5,
                cross_direction='up',
                bar_index=100,
                timestamp='2024-01-01T12:00:00',
            )
        ]

        snapshot = RefStateSnapshot(
            bar_index=100,
            formed_leg_ids=['leg_1'],
            references=[],
            filtered_legs=[],
            current_price=100.0,
            is_warming_up=False,
            warmup_progress=[50, 50],
            median=10.0,
            auto_tracked_leg_id='leg_1',
            crossing_events=events,
        )

        data = snapshot.model_dump()
        assert len(data['crossing_events']) == 1
        assert data['crossing_events'][0]['level_crossed'] == 0.5
        assert data['crossing_events'][0]['cross_direction'] == 'up'
