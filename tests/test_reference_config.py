"""
Tests for ReferenceConfig dataclass.

Verifies:
- Default values match reference_layer_spec.md
- Immutability (frozen=True)
- Serialization to/from dict
- Builder methods for modification
"""

import pytest

from src.swing_analysis.reference_config import ReferenceConfig


class TestReferenceConfigDefaults:
    """Tests for ReferenceConfig default values."""

    def test_default_scale_thresholds(self):
        """Scale thresholds should match spec defaults."""
        config = ReferenceConfig.default()

        assert config.xl_threshold == 0.90  # Top 10%
        assert config.l_threshold == 0.60   # Top 40%
        assert config.m_threshold == 0.30   # Top 70%

    def test_default_cold_start(self):
        """Cold start threshold should be 50 swings."""
        config = ReferenceConfig.default()
        assert config.min_swings_for_scale == 50

    def test_default_formation_threshold(self):
        """Formation threshold should be 38.2%."""
        config = ReferenceConfig.default()
        assert config.formation_fib_threshold == 0.382

    def test_default_origin_tolerances(self):
        """Origin breach tolerances should match north star spec."""
        config = ReferenceConfig.default()
        # S/M: default zero tolerance per north star
        assert config.small_origin_tolerance == 0.0   # 0% for S/M per north star
        # L/XL: two thresholds per north star
        assert config.big_trade_breach_tolerance == 0.15  # 15% trade breach
        assert config.big_close_breach_tolerance == 0.10  # 10% close breach

    def test_default_big_salience_weights(self):
        """Big swing (L/XL) salience weights should match spec."""
        config = ReferenceConfig.default()
        assert config.big_range_weight == 0.5
        assert config.big_impulse_weight == 0.4
        assert config.big_recency_weight == 0.1

    def test_default_small_salience_weights(self):
        """Small swing (S/M) salience weights should match spec."""
        config = ReferenceConfig.default()
        assert config.small_range_weight == 0.2
        assert config.small_impulse_weight == 0.3
        assert config.small_recency_weight == 0.5

    def test_default_classification_mode(self):
        """Default should use scale, not depth."""
        config = ReferenceConfig.default()
        assert config.use_depth_instead_of_scale is False

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
            config.xl_threshold = 0.80  # type: ignore

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

        assert data["xl_threshold"] == 0.90
        assert data["l_threshold"] == 0.60
        assert data["m_threshold"] == 0.30
        assert data["min_swings_for_scale"] == 50
        assert data["formation_fib_threshold"] == 0.382
        assert data["small_origin_tolerance"] == 0.0
        assert data["big_trade_breach_tolerance"] == 0.15
        assert data["big_close_breach_tolerance"] == 0.10
        assert data["big_range_weight"] == 0.5
        assert data["big_impulse_weight"] == 0.4
        assert data["big_recency_weight"] == 0.1
        assert data["small_range_weight"] == 0.2
        assert data["small_impulse_weight"] == 0.3
        assert data["small_recency_weight"] == 0.5
        assert data["use_depth_instead_of_scale"] is False
        assert data["confluence_tolerance_pct"] == 0.001

    def test_from_dict(self):
        """from_dict should restore all fields."""
        data = {
            "xl_threshold": 0.85,
            "l_threshold": 0.55,
            "m_threshold": 0.25,
            "min_swings_for_scale": 100,
            "formation_fib_threshold": 0.5,
            "small_origin_tolerance": 0.10,
            "big_trade_breach_tolerance": 0.20,
            "big_close_breach_tolerance": 0.15,
            "big_range_weight": 0.4,
            "big_impulse_weight": 0.5,
            "big_recency_weight": 0.1,
            "small_range_weight": 0.3,
            "small_impulse_weight": 0.4,
            "small_recency_weight": 0.3,
            "use_depth_instead_of_scale": True,
            "confluence_tolerance_pct": 0.002,
        }

        config = ReferenceConfig.from_dict(data)

        assert config.xl_threshold == 0.85
        assert config.l_threshold == 0.55
        assert config.m_threshold == 0.25
        assert config.min_swings_for_scale == 100
        assert config.formation_fib_threshold == 0.5
        assert config.small_origin_tolerance == 0.10
        assert config.big_trade_breach_tolerance == 0.20
        assert config.big_close_breach_tolerance == 0.15
        assert config.big_range_weight == 0.4
        assert config.big_impulse_weight == 0.5
        assert config.big_recency_weight == 0.1
        assert config.small_range_weight == 0.3
        assert config.small_impulse_weight == 0.4
        assert config.small_recency_weight == 0.3
        assert config.use_depth_instead_of_scale is True
        assert config.confluence_tolerance_pct == 0.002

    def test_from_dict_missing_fields_use_defaults(self):
        """from_dict should use defaults for missing fields."""
        data = {}  # Empty dict
        config = ReferenceConfig.from_dict(data)

        # Should have all defaults
        assert config.xl_threshold == 0.90
        assert config.formation_fib_threshold == 0.382
        assert config.use_depth_instead_of_scale is False

    def test_round_trip_serialization(self):
        """to_dict -> from_dict should preserve all values."""
        original = ReferenceConfig(
            xl_threshold=0.88,
            l_threshold=0.66,
            m_threshold=0.33,
            min_swings_for_scale=75,
            formation_fib_threshold=0.45,
            small_origin_tolerance=0.08,
            big_trade_breach_tolerance=0.18,
            big_close_breach_tolerance=0.12,
            big_range_weight=0.45,
            big_impulse_weight=0.45,
            big_recency_weight=0.10,
            small_range_weight=0.25,
            small_impulse_weight=0.35,
            small_recency_weight=0.40,
            use_depth_instead_of_scale=True,
            confluence_tolerance_pct=0.0015,
        )

        data = original.to_dict()
        restored = ReferenceConfig.from_dict(data)

        assert original == restored


class TestReferenceConfigBuilders:
    """Tests for ReferenceConfig builder methods."""

    def test_with_scale_thresholds(self):
        """with_scale_thresholds should modify scale thresholds."""
        original = ReferenceConfig.default()
        modified = original.with_scale_thresholds(
            xl_threshold=0.95,
            l_threshold=0.70,
        )

        # Original unchanged
        assert original.xl_threshold == 0.90
        assert original.l_threshold == 0.60

        # Modified has new values
        assert modified.xl_threshold == 0.95
        assert modified.l_threshold == 0.70
        # Unspecified value preserved
        assert modified.m_threshold == 0.30

    def test_with_formation_threshold(self):
        """with_formation_threshold should modify formation threshold."""
        original = ReferenceConfig.default()
        modified = original.with_formation_threshold(0.5)

        assert original.formation_fib_threshold == 0.382
        assert modified.formation_fib_threshold == 0.5

    def test_with_tolerance(self):
        """with_tolerance should modify origin tolerances."""
        original = ReferenceConfig.default()
        modified = original.with_tolerance(
            small_origin_tolerance=0.10,
            big_trade_breach_tolerance=0.25,
            big_close_breach_tolerance=0.18,
        )

        assert original.small_origin_tolerance == 0.0
        assert original.big_trade_breach_tolerance == 0.15
        assert original.big_close_breach_tolerance == 0.10
        assert modified.small_origin_tolerance == 0.10
        assert modified.big_trade_breach_tolerance == 0.25
        assert modified.big_close_breach_tolerance == 0.18

    def test_with_salience_weights(self):
        """with_salience_weights should modify salience weights."""
        original = ReferenceConfig.default()
        modified = original.with_salience_weights(
            big_range_weight=0.6,
            small_recency_weight=0.6,
        )

        # Original unchanged
        assert original.big_range_weight == 0.5
        assert original.small_recency_weight == 0.5

        # Modified has new values
        assert modified.big_range_weight == 0.6
        assert modified.small_recency_weight == 0.6
        # Unspecified values preserved
        assert modified.big_impulse_weight == 0.4
        assert modified.small_impulse_weight == 0.3

    def test_with_depth_mode(self):
        """with_depth_mode should toggle classification mode."""
        original = ReferenceConfig.default()
        modified = original.with_depth_mode(True)

        assert original.use_depth_instead_of_scale is False
        assert modified.use_depth_instead_of_scale is True

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
            .with_tolerance(small_origin_tolerance=0.08)
            .with_depth_mode(True)
        )

        assert config.formation_fib_threshold == 0.5
        assert config.small_origin_tolerance == 0.08
        assert config.use_depth_instead_of_scale is True
        # Other values should be defaults
        assert config.xl_threshold == 0.90


class TestReferenceConfigUsage:
    """Tests for typical usage patterns."""

    def test_scalping_preset(self):
        """Create a scalping-focused config (recency-heavy)."""
        config = ReferenceConfig.default().with_salience_weights(
            small_range_weight=0.1,
            small_impulse_weight=0.2,
            small_recency_weight=0.7,  # Favor recent swings
        )

        assert config.small_recency_weight == 0.7

    def test_swing_trading_preset(self):
        """Create a swing-trading config (size-heavy)."""
        config = ReferenceConfig.default().with_salience_weights(
            big_range_weight=0.6,
            big_impulse_weight=0.3,
            big_recency_weight=0.1,  # Favor big swings
        )

        assert config.big_range_weight == 0.6

    def test_strict_formation(self):
        """Create config with stricter formation threshold."""
        config = ReferenceConfig.default().with_formation_threshold(0.5)

        assert config.formation_fib_threshold == 0.5

    def test_loose_tolerance(self):
        """Create config with looser breach tolerance."""
        config = ReferenceConfig.default().with_tolerance(
            small_origin_tolerance=0.15,
            big_trade_breach_tolerance=0.25,
            big_close_breach_tolerance=0.20,
        )

        assert config.small_origin_tolerance == 0.15
        assert config.big_trade_breach_tolerance == 0.25
        assert config.big_close_breach_tolerance == 0.20
