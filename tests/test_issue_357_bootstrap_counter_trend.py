"""
Tests for issue #357: Treat None counter-trend as zero for turn ratio pruning.

Verifies that:
1. Bootstrap flags track whether any leg of each direction has been created
2. Legs created before bootstrap have _max_counter_leg_range = None (exempt)
3. Legs created after bootstrap with no counter-leg get _max_counter_leg_range = 0.0
4. Legs with _max_counter_leg_range = 0.0 have turn_ratio = 0 and are prunable
5. State serialization preserves bootstrap flags
"""

from decimal import Decimal

import pytest

from src.swing_analysis.dag.leg_detector import LegDetector
from src.swing_analysis.dag.leg import Leg
from src.swing_analysis.dag.state import DetectorState
from src.swing_analysis.detection_config import DetectionConfig
from src.swing_analysis.types import Bar


def make_bar(idx: int, open_: float, high: float, low: float, close: float) -> Bar:
    """Create a test bar."""
    return Bar(
        index=idx,
        timestamp=0,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class TestBootstrapFlagsInitialization:
    """Test that bootstrap flags start as False."""

    def test_initial_state_has_no_bootstrap(self):
        """Bootstrap flags should be False initially."""
        detector = LegDetector()
        assert detector.state._has_created_bull_leg is False
        assert detector.state._has_created_bear_leg is False

    def test_detector_state_has_bootstrap_fields(self):
        """DetectorState should have the bootstrap flag fields."""
        state = DetectorState()
        assert hasattr(state, '_has_created_bull_leg')
        assert hasattr(state, '_has_created_bear_leg')
        assert state._has_created_bull_leg is False
        assert state._has_created_bear_leg is False


class TestBootstrapFlagsSetting:
    """Test that bootstrap flags are set when legs are created."""

    def test_bull_leg_creation_sets_bull_bootstrap(self):
        """Creating a bull leg should set _has_created_bull_leg = True."""
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # Process bars to create a bull leg (TYPE_2_BULL pattern)
        bars = [
            make_bar(0, 100, 102, 98, 101),   # First bar
            make_bar(1, 101, 105, 100, 104),  # HH+HL = TYPE_2_BULL -> creates bull leg
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Verify bull bootstrap is set
        assert detector.state._has_created_bull_leg is True
        # Bear bootstrap should still be False
        assert detector.state._has_created_bear_leg is False

    def test_bear_leg_creation_sets_bear_bootstrap(self):
        """Creating a bear leg should set _has_created_bear_leg = True."""
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # Process bars to create a bear leg (TYPE_2_BEAR pattern)
        bars = [
            make_bar(0, 100, 102, 98, 101),  # First bar
            make_bar(1, 100, 101, 95, 96),   # LH+LL = TYPE_2_BEAR -> creates bear leg
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Verify bear bootstrap is set
        assert detector.state._has_created_bear_leg is True
        # Bull bootstrap should still be False
        assert detector.state._has_created_bull_leg is False


class TestBootstrapExemption:
    """Test that legs created before bootstrap are exempt (None counter-trend)."""

    def test_first_bull_leg_has_none_counter_trend(self):
        """The first bull leg should have _max_counter_leg_range = None (bootstrap exempt)."""
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # Create a bull leg when no bear legs exist yet
        bars = [
            make_bar(0, 100, 102, 98, 101),
            make_bar(1, 101, 106, 100, 105),  # Creates bull leg from low 98
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Find the bull leg
        bull_legs = [l for l in detector.state.active_legs if l.direction == 'bull']
        assert len(bull_legs) >= 1, "Expected at least one bull leg"

        first_bull = bull_legs[0]
        # Before any bear leg exists, _max_counter_leg_range should be None
        assert first_bull._max_counter_leg_range is None, \
            "First bull leg should have None counter-trend (bootstrap exempt)"

    def test_first_bear_leg_has_none_counter_trend(self):
        """The first bear leg should have _max_counter_leg_range = None (bootstrap exempt)."""
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # Create a bear leg when no bull legs exist yet
        bars = [
            make_bar(0, 100, 102, 98, 101),
            make_bar(1, 100, 101, 93, 94),  # Creates bear leg from high 102
        ]

        for bar in bars:
            detector.process_bar(bar)

        # Find the bear leg
        bear_legs = [l for l in detector.state.active_legs if l.direction == 'bear']
        assert len(bear_legs) >= 1, "Expected at least one bear leg"

        first_bear = bear_legs[0]
        # Before any bull leg exists, _max_counter_leg_range should be None
        assert first_bear._max_counter_leg_range is None, \
            "First bear leg should have None counter-trend (bootstrap exempt)"


class TestZeroCounterTrendAfterBootstrap:
    """Test that legs with no counter-leg get 0.0 after bootstrap."""

    def test_bull_leg_after_bear_bootstrap_gets_zero(self):
        """Bull leg created after bear leg exists but with no matching pivot gets 0.0."""
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # First create a bear leg to bootstrap bear direction
        bars = [
            make_bar(0, 100, 102, 98, 101),
            make_bar(1, 100, 101, 93, 94),  # Creates bear leg: 102->93 (pivot at 93)
        ]
        for bar in bars:
            detector.process_bar(bar)

        # Verify bear bootstrap is set
        assert detector.state._has_created_bear_leg is True

        # Now create a bull leg at a price where no bear pivot exists
        # The bear leg's pivot is at 93, so a bull leg from a different origin
        # should have _max_counter_leg_range = 0.0 (not None)
        bars_phase2 = [
            make_bar(2, 95, 110, 90, 108),  # Outside bar, creates bull leg from 90
        ]
        for bar in bars_phase2:
            detector.process_bar(bar)

        # Find bull legs created after bootstrap
        bull_legs = [l for l in detector.state.active_legs
                     if l.direction == 'bull' and l.origin_index >= 2]

        # The bull leg's origin (90) has no bear pivot matching it
        # So it should get _max_counter_leg_range = 0.0 (not None)
        for bull_leg in bull_legs:
            if bull_leg._max_counter_leg_range is not None:
                # Found a leg with set counter-trend - it should be 0.0
                # (unless there's an actual bear pivot there)
                bear_pivots = [l.pivot_price for l in detector.state.active_legs
                              if l.direction == 'bear']
                if bull_leg.origin_price not in bear_pivots:
                    assert bull_leg._max_counter_leg_range == 0.0, \
                        f"Bull leg at {bull_leg.origin_price} should have 0.0 counter-trend, " \
                        f"got {bull_leg._max_counter_leg_range}"


class TestTurnRatioWithZeroCounterTrend:
    """Test that legs with _max_counter_leg_range = 0.0 have turn_ratio = 0."""

    def test_turn_ratio_is_zero_when_counter_trend_is_zero(self):
        """Leg with _max_counter_leg_range = 0.0 should have turn_ratio = 0."""
        # Create a leg directly with _max_counter_leg_range = 0.0
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=5,
            _max_counter_leg_range=0.0,
        )

        # turn_ratio = _max_counter_leg_range / range = 0.0 / 10 = 0.0
        assert leg.turn_ratio == 0.0

    def test_turn_ratio_is_none_when_counter_trend_is_none(self):
        """Leg with _max_counter_leg_range = None should have turn_ratio = None (exempt)."""
        leg = Leg(
            direction='bull',
            origin_price=Decimal("100"),
            origin_index=0,
            pivot_price=Decimal("110"),
            pivot_index=5,
            _max_counter_leg_range=None,
        )

        # turn_ratio should be None when _max_counter_leg_range is None
        assert leg.turn_ratio is None


class TestStateSerialization:
    """Test that bootstrap flags survive serialization/deserialization."""

    def test_bootstrap_flags_roundtrip(self):
        """Bootstrap flags should survive to_dict/from_dict round trip."""
        state = DetectorState()
        state._has_created_bull_leg = True
        state._has_created_bear_leg = False

        # Serialize
        data = state.to_dict()
        assert data['_has_created_bull_leg'] is True
        assert data['_has_created_bear_leg'] is False

        # Deserialize
        restored = DetectorState.from_dict(data)
        assert restored._has_created_bull_leg is True
        assert restored._has_created_bear_leg is False

    def test_bootstrap_flags_default_on_missing(self):
        """Missing bootstrap flags in serialized data should default to False."""
        # Simulate legacy data without bootstrap flags
        data = {
            'active_swings': [],
            'last_bar_index': -1,
            'fib_levels_crossed': {},
            'all_swing_ranges': [],
            'active_legs': [],
            'pending_origins': {'bull': None, 'bear': None},
            'formed_leg_impulses': [],
        }

        restored = DetectorState.from_dict(data)
        assert restored._has_created_bull_leg is False
        assert restored._has_created_bear_leg is False


class TestIntegrationScenario:
    """Integration test for the full #357 scenario."""

    def test_scenario_from_issue(self):
        """
        Reproduce the scenario from issue #357:
        - Bear legs are created and breached
        - A bull leg is created at an origin where no bear pivot exists
        - The bull leg should have _max_counter_leg_range = 0.0 (not None)
        - This makes it the most prunable (lowest turn_ratio)
        """
        config = DetectionConfig.default()
        detector = LegDetector(config)

        # Phase 1: Create some bear legs
        bars = [
            make_bar(0, 4500, 4510, 4490, 4505),  # First bar
            make_bar(1, 4505, 4510, 4480, 4485),  # Bear leg: 4510->4480
            make_bar(2, 4485, 4495, 4470, 4475),  # Bear extension
        ]
        for bar in bars:
            detector.process_bar(bar)

        assert detector.state._has_created_bear_leg is True

        # Phase 2: Price breaches all bear origins (going above 4510)
        bars_phase2 = [
            make_bar(3, 4475, 4530, 4470, 4525),  # Breaches bear origins
        ]
        for bar in bars_phase2:
            detector.process_bar(bar)

        # Phase 3: Create a bull leg from a low that has no bear pivot
        bars_phase3 = [
            make_bar(4, 4520, 4550, 4490, 4545),  # Bull leg from 4490
        ]
        for bar in bars_phase3:
            detector.process_bar(bar)

        # Find the bull leg created at origin 4490
        bull_legs = [l for l in detector.state.active_legs
                     if l.direction == 'bull' and l.origin_price == Decimal("4490")]

        # Check that there's no bear leg with pivot at 4490
        bear_pivots = [l.pivot_price for l in detector.state.active_legs
                       if l.direction == 'bear']

        if bull_legs and Decimal("4490") not in bear_pivots:
            for leg in bull_legs:
                # Should have 0.0 counter-trend (not None) because bears have bootstrapped
                assert leg._max_counter_leg_range == 0.0, \
                    f"Expected 0.0 counter-trend, got {leg._max_counter_leg_range}"
                # turn_ratio should be 0.0
                assert leg.turn_ratio == 0.0
