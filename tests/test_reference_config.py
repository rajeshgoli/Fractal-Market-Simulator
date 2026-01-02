"""
Tests for ReferenceConfig dataclass (#436 bin-based migration).

Verifies:
- Default values match current spec
- Immutability (frozen=True)
- Serialization to/from dict
- Builder methods for modification
"""

import pytest

from src.swing_analysis.reference_config import ReferenceConfig


class TestReferenceConfigDefaults:
    """Tests for ReferenceConfig default values."""

    def test_default_bin_threshold(self):
        """Significant bin threshold should be 8 (5× median)."""
        config = ReferenceConfig.default()
        assert config.significant_bin_threshold == 8

    def test_default_cold_start(self):
        """Cold start threshold should be 50 swings."""
        config = ReferenceConfig.default()
        assert config.min_swings_for_classification == 50

    def test_default_formation_threshold(self):
        """Formation threshold should be 38.2%."""
        config = ReferenceConfig.default()
        assert config.formation_fib_threshold == 0.382

    def test_default_origin_tolerances(self):
        """Origin breach tolerances should match spec."""
        config = ReferenceConfig.default()
        # Small bins (< 8): zero tolerance per north star
        assert config.origin_breach_tolerance == 0.0
        # Significant bins (>= 8): two thresholds
        assert config.significant_trade_breach_tolerance == 0.15  # 15% trade breach
        assert config.significant_close_breach_tolerance == 0.10  # 10% close breach

    def test_default_unified_salience_weights(self):
        """Unified salience weights should match spec (#436)."""
        config = ReferenceConfig.default()
        assert config.range_weight == 0.4
        assert config.impulse_weight == 0.4
        assert config.recency_weight == 0.1
        assert config.depth_weight == 0.1

    def test_default_range_counter_weight(self):
        """Range×Counter standalone mode should be disabled by default."""
        config = ReferenceConfig.default()
        assert config.range_counter_weight == 0.0

    def test_default_confluence_tolerance(self):
        """Confluence tolerance should be 0.1%."""
        config = ReferenceConfig.default()
        assert config.confluence_tolerance_pct == 0.001


class TestReferenceConfigImmutability:
    """Tests for ReferenceConfig immutability."""

    def test_immutable(self):
        """ReferenceConfig should be immutable (frozen=True)."""
        config = ReferenceConfig.default()

        with pytest.raises(AttributeError):
            config.significant_bin_threshold = 9  # type: ignore

    def test_hashable(self):
        """ReferenceConfig should be hashable."""
        config = ReferenceConfig.default()
        # Should not raise
        hash(config)
        {config: "test"}


class TestReferenceConfigEquality:
    """Tests for ReferenceConfig equality."""

    def test_equal_configs(self):
        """Two configs with same values should be equal."""
        config1 = ReferenceConfig.default()
        config2 = ReferenceConfig.default()
        assert config1 == config2

    def test_unequal_configs(self):
        """Configs with different values should not be equal."""
        config1 = ReferenceConfig.default()
        config2 = config1.with_formation_threshold(0.5)
        assert config1 != config2


class TestReferenceConfigSerialization:
    """Tests for ReferenceConfig serialization."""

    def test_to_dict(self):
        """to_dict should include all fields."""
        config = ReferenceConfig.default()
        data = config.to_dict()

        assert data["significant_bin_threshold"] == 8
        assert data["min_swings_for_classification"] == 50
        assert data["formation_fib_threshold"] == 0.382
        assert data["origin_breach_tolerance"] == 0.0
        assert data["significant_trade_breach_tolerance"] == 0.15
        assert data["significant_close_breach_tolerance"] == 0.10
        assert data["range_weight"] == 0.4
        assert data["impulse_weight"] == 0.4
        assert data["recency_weight"] == 0.1
        assert data["depth_weight"] == 0.1
        assert data["range_counter_weight"] == 0.0
        assert data["confluence_tolerance_pct"] == 0.001

    def test_from_dict(self):
        """from_dict should restore all fields."""
        data = {
            "significant_bin_threshold": 9,
            "min_swings_for_classification": 100,
            "formation_fib_threshold": 0.5,
            "origin_breach_tolerance": 0.05,
            "significant_trade_breach_tolerance": 0.20,
            "significant_close_breach_tolerance": 0.15,
            "range_weight": 0.3,
            "impulse_weight": 0.5,
            "recency_weight": 0.1,
            "depth_weight": 0.1,
            "range_counter_weight": 0.5,
            "confluence_tolerance_pct": 0.002,
        }

        config = ReferenceConfig.from_dict(data)

        assert config.significant_bin_threshold == 9
        assert config.min_swings_for_classification == 100
        assert config.formation_fib_threshold == 0.5
        assert config.origin_breach_tolerance == 0.05
        assert config.significant_trade_breach_tolerance == 0.20
        assert config.significant_close_breach_tolerance == 0.15
        assert config.range_weight == 0.3
        assert config.impulse_weight == 0.5
        assert config.recency_weight == 0.1
        assert config.depth_weight == 0.1
        assert config.range_counter_weight == 0.5
        assert config.confluence_tolerance_pct == 0.002

    def test_from_dict_missing_fields_use_defaults(self):
        """from_dict should use defaults for missing fields."""
        data = {}  # Empty dict
        config = ReferenceConfig.from_dict(data)

        # Should have all defaults
        assert config.significant_bin_threshold == 8
        assert config.formation_fib_threshold == 0.382
        assert config.range_weight == 0.4

    def test_round_trip_serialization(self):
        """to_dict -> from_dict should preserve all values."""
        original = ReferenceConfig(
            significant_bin_threshold=9,
            min_swings_for_classification=75,
            formation_fib_threshold=0.45,
            origin_breach_tolerance=0.08,
            significant_trade_breach_tolerance=0.18,
            significant_close_breach_tolerance=0.12,
            range_weight=0.35,
            impulse_weight=0.45,
            recency_weight=0.10,
            depth_weight=0.10,
            range_counter_weight=0.5,
            confluence_tolerance_pct=0.0015,
        )

        data = original.to_dict()
        restored = ReferenceConfig.from_dict(data)

        assert original == restored


class TestReferenceConfigBuilders:
    """Tests for ReferenceConfig builder methods."""

    def test_with_formation_threshold(self):
        """with_formation_threshold should modify formation threshold."""
        original = ReferenceConfig.default()
        modified = original.with_formation_threshold(0.5)

        assert original.formation_fib_threshold == 0.382
        assert modified.formation_fib_threshold == 0.5

    def test_with_breach_tolerance(self):
        """with_breach_tolerance should modify origin tolerances."""
        original = ReferenceConfig.default()
        modified = original.with_breach_tolerance(
            origin_breach_tolerance=0.10,
            significant_trade_breach_tolerance=0.25,
            significant_close_breach_tolerance=0.18,
        )

        assert original.origin_breach_tolerance == 0.0
        assert original.significant_trade_breach_tolerance == 0.15
        assert original.significant_close_breach_tolerance == 0.10
        assert modified.origin_breach_tolerance == 0.10
        assert modified.significant_trade_breach_tolerance == 0.25
        assert modified.significant_close_breach_tolerance == 0.18

    def test_with_salience_weights(self):
        """with_salience_weights should modify salience weights."""
        original = ReferenceConfig.default()
        modified = original.with_salience_weights(
            range_weight=0.6,
            recency_weight=0.2,
        )

        # Original unchanged
        assert original.range_weight == 0.4
        assert original.recency_weight == 0.1

        # Modified has new values
        assert modified.range_weight == 0.6
        assert modified.recency_weight == 0.2
        # Unspecified values preserved
        assert modified.impulse_weight == 0.4
        assert modified.depth_weight == 0.1

    def test_with_confluence_tolerance(self):
        """with_confluence_tolerance should modify confluence tolerance."""
        original = ReferenceConfig.default()
        modified = original.with_confluence_tolerance(0.005)

        assert original.confluence_tolerance_pct == 0.001
        assert modified.confluence_tolerance_pct == 0.005

    def test_chained_builders(self):
        """Builder methods should be chainable."""
        config = (
            ReferenceConfig.default()
            .with_formation_threshold(0.5)
            .with_breach_tolerance(origin_breach_tolerance=0.08)
        )

        assert config.formation_fib_threshold == 0.5
        assert config.origin_breach_tolerance == 0.08
        # Other values should be defaults
        assert config.significant_bin_threshold == 8


class TestReferenceConfigUsage:
    """Tests for typical usage patterns."""

    def test_recency_focused_config(self):
        """Create a recency-focused config (recent swings prioritized)."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.1,
            impulse_weight=0.2,
            recency_weight=0.6,
            depth_weight=0.1,
        )

        assert config.recency_weight == 0.6

    def test_range_focused_config(self):
        """Create a range-focused config (big swings prioritized)."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.6,
            impulse_weight=0.3,
            recency_weight=0.05,
            depth_weight=0.05,
        )

        assert config.range_weight == 0.6

    def test_strict_formation(self):
        """Create config with stricter formation threshold."""
        config = ReferenceConfig.default().with_formation_threshold(0.5)

        assert config.formation_fib_threshold == 0.5

    def test_loose_tolerance(self):
        """Create config with looser breach tolerance."""
        config = ReferenceConfig.default().with_breach_tolerance(
            origin_breach_tolerance=0.15,
            significant_trade_breach_tolerance=0.25,
            significant_close_breach_tolerance=0.20,
        )

        assert config.origin_breach_tolerance == 0.15
        assert config.significant_trade_breach_tolerance == 0.25
        assert config.significant_close_breach_tolerance == 0.20

    def test_range_counter_standalone_mode(self):
        """Create config using Range×Counter standalone salience mode."""
        config = ReferenceConfig.default().with_salience_weights(
            range_counter_weight=1.0,  # Enable standalone mode
        )

        assert config.range_counter_weight == 1.0
