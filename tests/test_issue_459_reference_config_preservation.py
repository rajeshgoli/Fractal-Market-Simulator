"""
Tests for issue #459: ReferenceConfig lost on playback resync.

ReferenceConfig (user's display preferences like top_n, salience weights)
should be preserved whenever ReferenceLayer is recreated during playback
resync. DetectionConfig is correctly extracted from the old detector;
ReferenceConfig should follow the same pattern.

The fix preserves ReferenceConfig at all 6 locations in dag.py where
ReferenceLayer is recreated:
- _ensure_initialized()
- init_dag()
- reset_dag()
- advance_dag() resync path
- reverse_dag()
- update_detection_config()
"""

from decimal import Decimal

import pytest

from src.swing_analysis.reference_layer import ReferenceLayer
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.detection_config import DetectionConfig


class TestReferenceConfigPreservation:
    """Tests for ReferenceConfig preservation during ReferenceLayer recreation."""

    def test_reference_config_passed_to_constructor(self):
        """ReferenceConfig passed to constructor should be used."""
        custom_config = ReferenceConfig(
            top_n=3,  # Non-default value
            range_weight=0.5,  # Non-default value
            recency_weight=0.8,  # Non-default value
        )

        ref_layer = ReferenceLayer(reference_config=custom_config)

        assert ref_layer.reference_config.top_n == 3
        assert ref_layer.reference_config.range_weight == 0.5
        assert ref_layer.reference_config.recency_weight == 0.8

    def test_reference_config_defaults_when_not_provided(self):
        """ReferenceConfig should default when not provided."""
        ref_layer = ReferenceLayer()

        # Check defaults from ReferenceConfig
        assert ref_layer.reference_config.top_n == 5
        assert ref_layer.reference_config.range_weight == 0.8
        assert ref_layer.reference_config.recency_weight == 0.4

    def test_reference_config_preserved_on_recreation(self):
        """ReferenceConfig should be preserved when creating new ReferenceLayer."""
        # Simulate the pattern used in dag.py
        old_ref_config = ReferenceConfig(
            top_n=3,
            range_weight=0.6,
            min_swings_for_classification=30,
        )
        old_layer = ReferenceLayer(reference_config=old_ref_config)

        # Verify old layer has custom config
        assert old_layer.reference_config.top_n == 3
        assert old_layer.reference_config.range_weight == 0.6
        assert old_layer.reference_config.min_swings_for_classification == 30

        # Simulate resync: extract config and pass to new layer
        preserved_config = old_layer.reference_config
        detection_config = DetectionConfig.default()  # New detection config
        new_layer = ReferenceLayer(detection_config, reference_config=preserved_config)

        # ReferenceConfig should be preserved
        assert new_layer.reference_config.top_n == 3
        assert new_layer.reference_config.range_weight == 0.6
        assert new_layer.reference_config.min_swings_for_classification == 30

    def test_reference_config_with_none_uses_default(self):
        """Passing None for reference_config should use default."""
        detection_config = DetectionConfig.default()
        ref_layer = ReferenceLayer(detection_config, reference_config=None)

        # Should use default ReferenceConfig values
        default_config = ReferenceConfig.default()
        assert ref_layer.reference_config.top_n == default_config.top_n
        assert ref_layer.reference_config.range_weight == default_config.range_weight

    def test_reference_config_all_fields_preserved(self):
        """All ReferenceConfig fields should be preserved on recreation."""
        # Create config with all non-default values
        custom_config = ReferenceConfig(
            significant_bin_threshold=9,
            min_swings_for_classification=40,
            formation_fib_threshold=0.3,
            pivot_breach_tolerance=0.05,
            significant_trade_breach_tolerance=0.2,
            significant_close_breach_tolerance=0.15,
            completion_threshold=2.5,
            range_weight=0.7,
            impulse_weight=0.1,
            recency_weight=0.5,
            depth_weight=0.05,
            counter_weight=0.1,
            range_counter_weight=0.05,
            recency_decay_bars=500,
            depth_decay_factor=0.3,
            top_n=7,
            confluence_tolerance_pct=0.002,
            active_level_distance_pct=0.01,
            bin_window_duration_days=60,
            bin_recompute_interval=50,
        )

        old_layer = ReferenceLayer(reference_config=custom_config)

        # Simulate preservation pattern from dag.py
        preserved_config = old_layer.reference_config
        new_layer = ReferenceLayer(reference_config=preserved_config)

        # All fields should be preserved
        assert new_layer.reference_config.significant_bin_threshold == 9
        assert new_layer.reference_config.min_swings_for_classification == 40
        assert new_layer.reference_config.formation_fib_threshold == 0.3
        assert new_layer.reference_config.pivot_breach_tolerance == 0.05
        assert new_layer.reference_config.significant_trade_breach_tolerance == 0.2
        assert new_layer.reference_config.significant_close_breach_tolerance == 0.15
        assert new_layer.reference_config.completion_threshold == 2.5
        assert new_layer.reference_config.range_weight == 0.7
        assert new_layer.reference_config.impulse_weight == 0.1
        assert new_layer.reference_config.recency_weight == 0.5
        assert new_layer.reference_config.depth_weight == 0.05
        assert new_layer.reference_config.counter_weight == 0.1
        assert new_layer.reference_config.range_counter_weight == 0.05
        assert new_layer.reference_config.recency_decay_bars == 500
        assert new_layer.reference_config.depth_decay_factor == 0.3
        assert new_layer.reference_config.top_n == 7
        assert new_layer.reference_config.confluence_tolerance_pct == 0.002
        assert new_layer.reference_config.active_level_distance_pct == 0.01
        assert new_layer.reference_config.bin_window_duration_days == 60
        assert new_layer.reference_config.bin_recompute_interval == 50


class TestPreservationPattern:
    """Tests for the preservation pattern used in dag.py endpoints."""

    def test_preservation_pattern_with_existing_layer(self):
        """Pattern: old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None"""
        # Simulate cache with existing reference layer
        cache = {
            "reference_layer": ReferenceLayer(
                reference_config=ReferenceConfig(top_n=3)
            )
        }

        # Apply preservation pattern from dag.py
        old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

        # Should have preserved config
        assert old_ref_config is not None
        assert old_ref_config.top_n == 3

        # Create new layer with preserved config
        new_layer = ReferenceLayer(reference_config=old_ref_config)
        assert new_layer.reference_config.top_n == 3

    def test_preservation_pattern_with_no_existing_layer(self):
        """Pattern should handle missing reference layer gracefully."""
        # Simulate cache without reference layer
        cache = {}

        # Apply preservation pattern from dag.py
        old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

        # Should be None
        assert old_ref_config is None

        # Create new layer with None config (uses default)
        new_layer = ReferenceLayer(reference_config=old_ref_config)
        assert new_layer.reference_config.top_n == 5  # default

    def test_preservation_pattern_with_none_value(self):
        """Pattern should handle cache["reference_layer"] = None."""
        # Simulate cache with None reference layer
        cache = {"reference_layer": None}

        # Apply preservation pattern from dag.py
        old_ref_config = cache.get("reference_layer").reference_config if cache.get("reference_layer") else None

        # Should be None
        assert old_ref_config is None


class TestReferenceConfigImmutability:
    """Tests to ensure ReferenceConfig is properly preserved as frozen dataclass."""

    def test_reference_config_is_frozen(self):
        """ReferenceConfig should be a frozen dataclass (immutable)."""
        config = ReferenceConfig(top_n=3)

        with pytest.raises(Exception):  # FrozenInstanceError
            config.top_n = 5

    def test_preserved_config_is_same_object(self):
        """Preserved config should be the same object (frozen, no copy needed)."""
        original_config = ReferenceConfig(top_n=3)
        old_layer = ReferenceLayer(reference_config=original_config)

        # The reference_config in the layer should be the same object
        preserved_config = old_layer.reference_config
        assert preserved_config is original_config

        # When passed to new layer, it's still the same object
        new_layer = ReferenceLayer(reference_config=preserved_config)
        assert new_layer.reference_config is original_config


class TestBinDistributionInitialization:
    """Tests that bin distribution is initialized correctly with preserved config."""

    def test_bin_distribution_uses_preserved_config_params(self):
        """Bin distribution should be initialized with preserved config parameters."""
        custom_config = ReferenceConfig(
            bin_window_duration_days=45,  # Non-default
            bin_recompute_interval=75,    # Non-default
        )

        ref_layer = ReferenceLayer(reference_config=custom_config)

        # Bin distribution should have been initialized with custom params
        assert ref_layer._bin_distribution.window_duration_days == 45
        assert ref_layer._bin_distribution.recompute_interval_legs == 75

    def test_preservation_maintains_bin_params(self):
        """Preserving ReferenceConfig should maintain bin distribution params."""
        custom_config = ReferenceConfig(
            bin_window_duration_days=45,
            bin_recompute_interval=75,
        )

        old_layer = ReferenceLayer(reference_config=custom_config)

        # Simulate preservation and recreation
        preserved_config = old_layer.reference_config
        new_layer = ReferenceLayer(reference_config=preserved_config)

        # New layer should have same bin params
        assert new_layer._bin_distribution.window_duration_days == 45
        assert new_layer._bin_distribution.recompute_interval_legs == 75
