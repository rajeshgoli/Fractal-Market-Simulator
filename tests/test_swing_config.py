"""
Tests for SwingConfig dataclass.

Verifies:
- Default values match documented magic numbers from valid_swings.md
- Serialization round-trip (to_json → from_json)
- Immutability (frozen=True)
- DirectionConfig can be customized per direction
"""

import json
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
        assert config.lookback_bars == 50

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
            config.lookback_bars = 100  # type: ignore

    def test_lookback_bars_default(self):
        """lookback_bars should default to 50."""
        config = SwingConfig()
        assert config.lookback_bars == 50

    def test_custom_lookback(self):
        """SwingConfig should accept custom lookback_bars."""
        config = SwingConfig(lookback_bars=100)
        assert config.lookback_bars == 100


class TestSwingConfigSerialization:
    """Tests for SwingConfig serialization."""

    def test_to_dict(self):
        """to_dict should produce correct dictionary structure."""
        config = SwingConfig.default()
        data = config.to_dict()

        assert "bull" in data
        assert "bear" in data
        assert "lookback_bars" in data

        assert data["bull"]["formation_fib"] == 0.287
        assert data["bear"]["formation_fib"] == 0.287
        assert data["lookback_bars"] == 50

    def test_from_dict(self):
        """from_dict should correctly reconstruct SwingConfig."""
        data = {
            "bull": {"formation_fib": 0.382, "self_separation": 0.15},
            "bear": {"formation_fib": 0.236},
            "lookback_bars": 75,
        }

        config = SwingConfig.from_dict(data)

        assert config.bull.formation_fib == 0.382
        assert config.bull.self_separation == 0.15
        # Other bull fields should use defaults
        assert config.bull.big_swing_threshold == 0.10

        assert config.bear.formation_fib == 0.236
        # Other bear fields should use defaults
        assert config.bear.self_separation == 0.10

        assert config.lookback_bars == 75

    def test_from_dict_empty(self):
        """from_dict with empty dict should use all defaults."""
        config = SwingConfig.from_dict({})

        assert config == SwingConfig.default()

    def test_to_json(self):
        """to_json should produce valid JSON string."""
        config = SwingConfig.default()
        json_str = config.to_json()

        # Should be valid JSON
        data = json.loads(json_str)

        assert data["bull"]["formation_fib"] == 0.287
        assert data["lookback_bars"] == 50

    def test_from_json(self):
        """from_json should correctly parse JSON string."""
        json_str = '{"bull": {"formation_fib": 0.382}, "lookback_bars": 100}'

        config = SwingConfig.from_json(json_str)

        assert config.bull.formation_fib == 0.382
        assert config.lookback_bars == 100

    def test_round_trip_default(self):
        """to_json → from_json should preserve default config."""
        original = SwingConfig.default()
        json_str = original.to_json()
        restored = SwingConfig.from_json(json_str)

        assert restored == original

    def test_round_trip_custom(self):
        """to_json → from_json should preserve custom config."""
        original = SwingConfig(
            bull=DirectionConfig(formation_fib=0.382, self_separation=0.15),
            bear=DirectionConfig(formation_fib=0.236, big_swing_threshold=0.05),
            lookback_bars=100,
        )

        json_str = original.to_json()
        restored = SwingConfig.from_json(json_str)

        assert restored == original

    def test_round_trip_through_dict(self):
        """to_dict → from_dict should preserve config."""
        original = SwingConfig.default()
        data = original.to_dict()
        restored = SwingConfig.from_dict(data)

        assert restored == original


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
        assert modified.lookback_bars == original.lookback_bars

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

    def test_with_lookback(self):
        """with_lookback should create new config with modified lookback."""
        original = SwingConfig.default()
        modified = original.with_lookback(100)

        # Original unchanged
        assert original.lookback_bars == 50

        # Modified has new value
        assert modified.lookback_bars == 100

        # Other values preserved
        assert modified.bull == original.bull
        assert modified.bear == original.bear

    def test_chained_builders(self):
        """Builder methods should be chainable."""
        config = (
            SwingConfig.default()
            .with_bull(formation_fib=0.382)
            .with_bear(formation_fib=0.236)
            .with_lookback(100)
        )

        assert config.bull.formation_fib == 0.382
        assert config.bear.formation_fib == 0.236
        assert config.lookback_bars == 100


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

    def test_unequal_lookback(self):
        """Configs with different lookback should not be equal."""
        config1 = SwingConfig.default()
        config2 = config1.with_lookback(100)

        assert config1 != config2

    def test_hashable(self):
        """SwingConfig should be hashable."""
        config = SwingConfig.default()
        # Should not raise
        hash(config)
        {config: "test"}
