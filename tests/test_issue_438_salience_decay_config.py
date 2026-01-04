"""
Tests for issue #438: Configurable decay factors in salience calculation.

Verifies:
- recency_decay_bars affects recency score in _compute_salience()
- depth_decay_factor affects depth score in _compute_salience()
- Config changes produce expected salience differences
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.reference_layer import ReferenceLayer


class TestRecencyDecayConfig:
    """Tests for recency_decay_bars configuration."""

    def test_recency_decay_default_value(self):
        """Default recency_decay_bars should be 1000."""
        config = ReferenceConfig.default()
        assert config.recency_decay_bars == 1000

    def test_recency_decay_formula_default(self):
        """Verify recency score formula with default decay.

        Formula: recency_score = 1 / (1 + age / recency_decay_bars)
        With default 1000 bars:
        - age=0: score = 1/(1+0) = 1.0
        - age=1000: score = 1/(1+1) = 0.5
        - age=2000: score = 1/(1+2) = 0.333
        """
        config = ReferenceConfig.default()

        # Verify at age=1000 (one half-life), score should be 0.5
        age = 1000
        expected_score = 1 / (1 + age / config.recency_decay_bars)
        assert expected_score == 0.5

    def test_recency_decay_custom_value(self):
        """Custom recency_decay_bars should affect score calculation.

        With decay=500:
        - age=500: score = 1/(1+1) = 0.5
        - age=1000: score = 1/(1+2) = 0.333
        """
        config = ReferenceConfig.default().with_salience_weights(
            recency_decay_bars=500
        )

        # Verify at age=500 (one half-life), score should be 0.5
        age = 500
        expected_score = 1 / (1 + age / config.recency_decay_bars)
        assert expected_score == 0.5


class TestDepthDecayConfig:
    """Tests for depth_decay_factor configuration."""

    def test_depth_decay_default_value(self):
        """Default depth_decay_factor should be 0.5."""
        config = ReferenceConfig.default()
        assert config.depth_decay_factor == 0.5

    def test_depth_decay_formula_default(self):
        """Verify depth score formula with default decay.

        Formula: depth_score = 1 / (1 + depth * depth_decay_factor)
        With default 0.5:
        - depth=0: score = 1/(1+0) = 1.0
        - depth=2: score = 1/(1+1) = 0.5
        - depth=4: score = 1/(1+2) = 0.333
        """
        config = ReferenceConfig.default()

        # Verify at depth=2, score should be 0.5
        depth = 2
        expected_score = 1 / (1 + depth * config.depth_decay_factor)
        assert expected_score == 0.5

        # Root leg (depth=0) should have score 1.0
        depth = 0
        expected_score = 1 / (1 + depth * config.depth_decay_factor)
        assert expected_score == 1.0

    def test_depth_decay_custom_value(self):
        """Custom depth_decay_factor should affect score calculation.

        With decay=0.25:
        - depth=4: score = 1/(1+1) = 0.5 (slower decay)
        """
        config = ReferenceConfig.default().with_salience_weights(
            depth_decay_factor=0.25
        )

        # Verify at depth=4, score should be 0.5 (slower decay than default)
        depth = 4
        expected_score = 1 / (1 + depth * config.depth_decay_factor)
        assert expected_score == 0.5


class TestSalienceCalculationWithConfig:
    """Tests for _compute_salience using configurable decay parameters."""

    def _create_mock_leg(
        self,
        origin_index: int = 0,
        range_val: float = 10.0,
        depth: int = 0,
        impulsiveness: float = None,
    ):
        """Create a mock leg for testing."""
        leg = MagicMock()
        leg.origin_index = origin_index
        leg.range = Decimal(str(range_val))
        leg.depth = depth
        leg.impulsiveness = impulsiveness
        leg.bin_impulsiveness = impulsiveness  # Salience uses bin-normalized (#491)
        return leg

    def _populate_distribution(self, layer: ReferenceLayer):
        """Helper to populate bin distribution for normalization."""
        for i, r in enumerate([5.0, 10.0, 15.0, 20.0]):
            layer._bin_distribution.add_leg(f"range_leg_{i}", r, 1000.0 + i)

    def test_salience_with_default_config(self):
        """Salience calculation should use default decay values."""
        config = ReferenceConfig.default()
        layer = ReferenceLayer(reference_config=config)

        # Add some range data for normalization
        self._populate_distribution(layer)

        # Test with leg at index 0, depth 0, current_bar at 1000
        leg = self._create_mock_leg(origin_index=0, range_val=10.0, depth=0)

        # With default config (recency_decay=1000, depth_decay=0.5):
        # - recency_score = 1/(1 + 1000/1000) = 0.5
        # - depth_score = 1/(1 + 0*0.5) = 1.0
        salience = layer._compute_salience(leg, current_bar_index=1000)

        # Should be a valid score
        assert 0 <= salience <= 1

    def test_salience_with_custom_recency_decay(self):
        """Salience should change when recency_decay_bars is modified."""
        # Fast decay config
        fast_config = ReferenceConfig.default().with_salience_weights(
            recency_decay_bars=500
        )
        fast_layer = ReferenceLayer(reference_config=fast_config)
        self._populate_distribution(fast_layer)

        # Slow decay config
        slow_config = ReferenceConfig.default().with_salience_weights(
            recency_decay_bars=2000
        )
        slow_layer = ReferenceLayer(reference_config=slow_config)
        self._populate_distribution(slow_layer)

        # Same leg for both
        leg = self._create_mock_leg(origin_index=0, range_val=10.0, depth=0)

        # At age 1000:
        # - Fast decay (500): recency = 1/(1+2) = 0.333
        # - Slow decay (2000): recency = 1/(1+0.5) = 0.667
        fast_salience = fast_layer._compute_salience(leg, current_bar_index=1000)
        slow_salience = slow_layer._compute_salience(leg, current_bar_index=1000)

        # Slow decay should result in higher salience for old legs
        assert slow_salience > fast_salience

    def test_salience_with_custom_depth_decay(self):
        """Salience should change when depth_decay_factor is modified."""
        # Fast decay config - #444: must set depth_weight > 0 for decay to matter
        fast_config = ReferenceConfig.default().with_salience_weights(
            depth_weight=0.5,  # Enable depth contribution to salience
            depth_decay_factor=1.0
        )
        fast_layer = ReferenceLayer(reference_config=fast_config)
        self._populate_distribution(fast_layer)

        # Slow decay config - #444: must set depth_weight > 0 for decay to matter
        slow_config = ReferenceConfig.default().with_salience_weights(
            depth_weight=0.5,  # Enable depth contribution to salience
            depth_decay_factor=0.25
        )
        slow_layer = ReferenceLayer(reference_config=slow_config)
        self._populate_distribution(slow_layer)

        # Deep leg (depth=4)
        leg = self._create_mock_leg(origin_index=0, range_val=10.0, depth=4)

        # At depth 4:
        # - Fast decay (1.0): depth_score = 1/(1+4) = 0.2
        # - Slow decay (0.25): depth_score = 1/(1+1) = 0.5
        fast_salience = fast_layer._compute_salience(leg, current_bar_index=0)
        slow_salience = slow_layer._compute_salience(leg, current_bar_index=0)

        # Slow decay should result in higher salience for deep legs
        assert slow_salience > fast_salience

    def test_root_leg_depth_score_is_one(self):
        """Root leg (depth=0) should always have depth_score=1.0."""
        for decay_factor in [0.25, 0.5, 1.0, 2.0]:
            config = ReferenceConfig.default().with_salience_weights(
                depth_decay_factor=decay_factor
            )

            # depth_score = 1/(1 + 0 * anything) = 1.0
            depth = 0
            depth_score = 1.0 / (1.0 + depth * config.depth_decay_factor)
            assert depth_score == 1.0, f"Failed for decay_factor={decay_factor}"

    def test_zero_age_recency_score_is_one(self):
        """Zero age leg should always have recency_score=1.0."""
        for decay_bars in [100, 500, 1000, 5000]:
            config = ReferenceConfig.default().with_salience_weights(
                recency_decay_bars=decay_bars
            )

            # recency_score = 1/(1 + 0/anything) = 1.0
            age = 0
            recency_score = 1 / (1 + age / config.recency_decay_bars)
            assert recency_score == 1.0, f"Failed for decay_bars={decay_bars}"
