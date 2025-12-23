"""
Tests for SwingConfig dataclass.

Verifies:
- Default values match documented magic numbers from valid_swings.md
- Immutability (frozen=True)
- DirectionConfig can be customized per direction
"""

import pytest

from src.swing_analysis.swing_config import DirectionConfig, SwingConfig


class TestDirectionConfig:
    """Tests for DirectionConfig dataclass."""

    def test_default_values_match_valid_swings_md(self):
        """Default values should match documented magic numbers."""
        config = DirectionConfig()

        # Formation fib: 0.287 per valid_swings.md Rule 3
        assert config.formation_fib == 0.287

        # Self-separation: 0.10 per Rule 4.1
        assert config.self_separation == 0.10

        # Big swing threshold: top 10% per Rule 2.2
        assert config.big_swing_threshold == 0.10

        # Big swing price tolerance: 0.15 per Rule 2.2
        assert config.big_swing_price_tolerance == 0.15

        # Big swing close tolerance: 0.10 per Rule 2.2
        assert config.big_swing_close_tolerance == 0.10

        # Child swing tolerance: 0.10
        assert config.child_swing_tolerance == 0.10

    def test_custom_values(self):
        """DirectionConfig should accept custom values."""
        config = DirectionConfig(
            formation_fib=0.382,
            self_separation=0.15,
            big_swing_threshold=0.05,
            big_swing_price_tolerance=0.20,
            big_swing_close_tolerance=0.12,
            child_swing_tolerance=0.08,
        )

        assert config.formation_fib == 0.382
        assert config.self_separation == 0.15
        assert config.big_swing_threshold == 0.05
        assert config.big_swing_price_tolerance == 0.20
        assert config.big_swing_close_tolerance == 0.12
        assert config.child_swing_tolerance == 0.08

    def test_immutability(self):
        """DirectionConfig should be immutable (frozen=True)."""
        config = DirectionConfig()

        with pytest.raises(AttributeError):
            config.formation_fib = 0.5  # type: ignore

    def test_equality(self):
        """Two DirectionConfigs with same values should be equal."""
        config1 = DirectionConfig()
        config2 = DirectionConfig()

        assert config1 == config2

        config3 = DirectionConfig(formation_fib=0.5)
        assert config1 != config3

    def test_hashable(self):
        """DirectionConfig should be hashable (for use in sets/dicts)."""
        config = DirectionConfig()
        # Should not raise
        hash(config)
        {config: "test"}


class TestSwingConfig:
    """Tests for SwingConfig dataclass."""

    def test_default_factory(self):
        """SwingConfig.default() should create config with default values."""
        config = SwingConfig.default()

        assert isinstance(config.bull, DirectionConfig)
        assert isinstance(config.bear, DirectionConfig)

    def test_default_constructor(self):
        """SwingConfig() should create same as default()."""
        config1 = SwingConfig()
        config2 = SwingConfig.default()

        assert config1 == config2

    def test_bull_bear_independent(self):
        """Bull and bear configs should be independent instances."""
        config = SwingConfig()

        # They should have same values but be separate instances
        assert config.bull == config.bear
        # This is expected since both use defaults

    def test_custom_bull_bear(self):
        """SwingConfig should accept custom bull and bear configs."""
        bull_config = DirectionConfig(formation_fib=0.382)
        bear_config = DirectionConfig(formation_fib=0.236)

        config = SwingConfig(bull=bull_config, bear=bear_config)

        assert config.bull.formation_fib == 0.382
        assert config.bear.formation_fib == 0.236

    def test_immutability(self):
        """SwingConfig should be immutable (frozen=True)."""
        config = SwingConfig()

        with pytest.raises(AttributeError):
            config.origin_range_prune_threshold = 0.1  # type: ignore

    def test_origin_prune_thresholds_default(self):
        """Origin prune thresholds should default to 0.0 (disabled) (#294)."""
        config = SwingConfig()
        assert config.origin_range_prune_threshold == 0.0
        assert config.origin_time_prune_threshold == 0.0

    def test_stale_extension_threshold_default(self):
        """stale_extension_threshold should default to 3.0 (#261)."""
        config = SwingConfig()
        assert config.stale_extension_threshold == 3.0


class TestSwingConfigBuilders:
    """Tests for SwingConfig builder methods."""

    def test_with_bull(self):
        """with_bull should create new config with modified bull params."""
        original = SwingConfig.default()
        modified = original.with_bull(formation_fib=0.382)

        # Original unchanged
        assert original.bull.formation_fib == 0.287

        # Modified has new value
        assert modified.bull.formation_fib == 0.382

        # Other values preserved
        assert modified.bull.self_separation == 0.10
        assert modified.bear == original.bear

    def test_with_bear(self):
        """with_bear should create new config with modified bear params."""
        original = SwingConfig.default()
        modified = original.with_bear(big_swing_threshold=0.05)

        # Original unchanged
        assert original.bear.big_swing_threshold == 0.10

        # Modified has new value
        assert modified.bear.big_swing_threshold == 0.05

        # Other values preserved
        assert modified.bull == original.bull
        assert modified.bear.formation_fib == 0.287

    def test_with_origin_prune(self):
        """with_origin_prune should create new config with modified thresholds (#294)."""
        original = SwingConfig.default()
        modified = original.with_origin_prune(
            origin_range_prune_threshold=0.10,
            origin_time_prune_threshold=0.20,
        )

        # Original unchanged
        assert original.origin_range_prune_threshold == 0.0
        assert original.origin_time_prune_threshold == 0.0

        # Modified has new values
        assert modified.origin_range_prune_threshold == 0.10
        assert modified.origin_time_prune_threshold == 0.20

        # Other values preserved
        assert modified.bull == original.bull
        assert modified.bear == original.bear

    def test_with_stale_extension(self):
        """with_stale_extension should create new config with modified threshold."""
        original = SwingConfig.default()
        modified = original.with_stale_extension(5.0)

        # Original unchanged
        assert original.stale_extension_threshold == 3.0

        # Modified has new value
        assert modified.stale_extension_threshold == 5.0

    def test_chained_builders(self):
        """Builder methods should be chainable."""
        config = (
            SwingConfig.default()
            .with_bull(formation_fib=0.382)
            .with_bear(formation_fib=0.236)
            .with_origin_prune(origin_range_prune_threshold=0.10, origin_time_prune_threshold=0.20)
        )

        assert config.bull.formation_fib == 0.382
        assert config.bear.formation_fib == 0.236
        assert config.origin_range_prune_threshold == 0.10
        assert config.origin_time_prune_threshold == 0.20


class TestSwingConfigEquality:
    """Tests for SwingConfig equality."""

    def test_equal_configs(self):
        """Two configs with same values should be equal."""
        config1 = SwingConfig.default()
        config2 = SwingConfig.default()

        assert config1 == config2

    def test_unequal_bull(self):
        """Configs with different bull params should not be equal."""
        config1 = SwingConfig.default()
        config2 = config1.with_bull(formation_fib=0.5)

        assert config1 != config2

    def test_unequal_bear(self):
        """Configs with different bear params should not be equal."""
        config1 = SwingConfig.default()
        config2 = config1.with_bear(formation_fib=0.5)

        assert config1 != config2

    def test_unequal_origin_prune(self):
        """Configs with different origin_prune should not be equal (#294)."""
        config1 = SwingConfig.default()
        config2 = config1.with_origin_prune(origin_range_prune_threshold=0.10)

        assert config1 != config2

    def test_hashable(self):
        """SwingConfig should be hashable."""
        config = SwingConfig.default()
        # Should not raise
        hash(config)
        {config: "test"}
