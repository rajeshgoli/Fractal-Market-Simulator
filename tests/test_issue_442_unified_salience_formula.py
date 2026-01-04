"""
Tests for issue #442: Unified salience formula.

Verifies:
- counter_weight and range_counter_weight are additive peers in salience
- Range, counter, and range×counter are normalized via median × 25
- No clamping — exceptional values can score > 1.0
- Standalone mode is removed — all weights work together
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.reference_layer import ReferenceLayer


class TestUnifiedSalienceConfig:
    """Tests for unified salience weight configuration."""

    def test_counter_weight_default_value(self):
        """Default counter_weight should be 0.0."""
        config = ReferenceConfig.default()
        assert config.counter_weight == 0.0

    def test_range_counter_weight_default_value(self):
        """Default range_counter_weight should be 0.0."""
        config = ReferenceConfig.default()
        assert config.range_counter_weight == 0.0

    def test_counter_weight_in_with_salience_weights(self):
        """counter_weight should be settable via with_salience_weights."""
        config = ReferenceConfig.default().with_salience_weights(
            counter_weight=0.5
        )
        assert config.counter_weight == 0.5

    def test_range_counter_weight_in_with_salience_weights(self):
        """range_counter_weight should be settable via with_salience_weights."""
        config = ReferenceConfig.default().with_salience_weights(
            range_counter_weight=0.3
        )
        assert config.range_counter_weight == 0.3

    def test_all_weights_can_be_non_zero(self):
        """All 6 weights should be usable simultaneously."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.2,
            counter_weight=0.2,
            range_counter_weight=0.1,
            impulse_weight=0.2,
            recency_weight=0.15,
            depth_weight=0.15,
        )
        assert config.range_weight == 0.2
        assert config.counter_weight == 0.2
        assert config.range_counter_weight == 0.1
        assert config.impulse_weight == 0.2
        assert config.recency_weight == 0.15
        assert config.depth_weight == 0.15


class TestNormalizationBehavior:
    """Tests for normalization using median × 25."""

    def _create_mock_leg(
        self,
        origin_index: int = 0,
        range_val: float = 10.0,
        counter_range: float = None,
        depth: int = 0,
        impulsiveness: float = None,
    ):
        """Create a mock leg for testing."""
        leg = MagicMock()
        leg.origin_index = origin_index
        leg.range = Decimal(str(range_val))
        leg.origin_counter_trend_range = Decimal(str(counter_range)) if counter_range else None
        leg.depth = depth
        leg.impulsiveness = impulsiveness
        leg.bin_impulsiveness = impulsiveness  # Salience uses bin-normalized (#491)
        return leg

    def _populate_distribution(self, layer: ReferenceLayer, median: float = 10.0):
        """Helper to populate bin distribution with known median."""
        # Add legs to establish a median
        for i in range(10):
            layer._bin_distribution.add_leg(f"leg_{i}", median, 1000.0 + i)

    def test_range_normalization(self):
        """Range should be normalized via median × 25."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=1.0,
            counter_weight=0.0,
            range_counter_weight=0.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # max_val = 10 × 25 = 250
        # Leg with range=250 should have range_score = 1.0
        leg = self._create_mock_leg(range_val=250.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert abs(salience - 1.0) < 0.01

        # Leg with range=125 should have range_score = 0.5
        leg = self._create_mock_leg(range_val=125.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert abs(salience - 0.5) < 0.01

    def test_counter_normalization(self):
        """Counter should be normalized via median × 25."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.0,
            counter_weight=1.0,
            range_counter_weight=0.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # max_val = 10 × 25 = 250
        # Leg with counter=250 should have counter_score = 1.0
        leg = self._create_mock_leg(range_val=10.0, counter_range=250.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert abs(salience - 1.0) < 0.01

        # Leg with counter=125 should have counter_score = 0.5
        leg = self._create_mock_leg(range_val=10.0, counter_range=125.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert abs(salience - 0.5) < 0.01

    def test_range_counter_normalization(self):
        """Range×Counter should be normalized via (median × 25)²."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.0,
            counter_weight=0.0,
            range_counter_weight=1.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # max_val = 10 × 25 = 250
        # max_val² = 250 × 250 = 62500
        # Leg with range=250, counter=250: score = (250×250)/62500 = 1.0
        leg = self._create_mock_leg(range_val=250.0, counter_range=250.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert abs(salience - 1.0) < 0.01

        # Leg with range=125, counter=250: score = (125×250)/62500 = 0.5
        leg = self._create_mock_leg(range_val=125.0, counter_range=250.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert abs(salience - 0.5) < 0.01


class TestNoClamping:
    """Tests verifying exceptional values are not clamped."""

    def _create_mock_leg(
        self,
        origin_index: int = 0,
        range_val: float = 10.0,
        counter_range: float = None,
        depth: int = 0,
        impulsiveness: float = None,
    ):
        """Create a mock leg for testing."""
        leg = MagicMock()
        leg.origin_index = origin_index
        leg.range = Decimal(str(range_val))
        leg.origin_counter_trend_range = Decimal(str(counter_range)) if counter_range else None
        leg.depth = depth
        leg.impulsiveness = impulsiveness
        leg.bin_impulsiveness = impulsiveness  # Salience uses bin-normalized (#491)
        return leg

    def _populate_distribution(self, layer: ReferenceLayer, median: float = 10.0):
        """Helper to populate bin distribution with known median."""
        for i in range(10):
            layer._bin_distribution.add_leg(f"leg_{i}", median, 1000.0 + i)

    def test_exceptional_range_scores_above_one(self):
        """Exceptional range values (>25× median) should score > 1.0."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=1.0,
            counter_weight=0.0,
            range_counter_weight=0.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # max_val = 10 × 25 = 250
        # Leg with range=500 should have score = 500/250 = 2.0
        leg = self._create_mock_leg(range_val=500.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert salience > 1.0
        assert abs(salience - 2.0) < 0.01

    def test_exceptional_counter_scores_above_one(self):
        """Exceptional counter values should score > 1.0."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.0,
            counter_weight=1.0,
            range_counter_weight=0.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # max_val = 10 × 25 = 250
        # Leg with counter=500 should have score = 500/250 = 2.0
        leg = self._create_mock_leg(range_val=10.0, counter_range=500.0)
        salience = layer._compute_salience(leg, current_bar_index=0)
        assert salience > 1.0
        assert abs(salience - 2.0) < 0.01


class TestAdditiveWeights:
    """Tests verifying all weights are additive peers."""

    def _create_mock_leg(
        self,
        origin_index: int = 0,
        range_val: float = 10.0,
        counter_range: float = None,
        depth: int = 0,
        impulsiveness: float = 50.0,
    ):
        """Create a mock leg for testing."""
        leg = MagicMock()
        leg.origin_index = origin_index
        leg.range = Decimal(str(range_val))
        leg.origin_counter_trend_range = Decimal(str(counter_range)) if counter_range else None
        leg.depth = depth
        leg.impulsiveness = impulsiveness
        leg.bin_impulsiveness = impulsiveness  # Salience uses bin-normalized (#491)
        return leg

    def _populate_distribution(self, layer: ReferenceLayer, median: float = 10.0):
        """Helper to populate bin distribution with known median."""
        for i in range(10):
            layer._bin_distribution.add_leg(f"leg_{i}", median, 1000.0 + i)

    def test_pure_range_ranking(self):
        """range=1, others=0 should rank purely by size."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=1.0,
            counter_weight=0.0,
            range_counter_weight=0.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        small_leg = self._create_mock_leg(range_val=50.0)
        large_leg = self._create_mock_leg(range_val=200.0)

        small_salience = layer._compute_salience(small_leg, current_bar_index=0)
        large_salience = layer._compute_salience(large_leg, current_bar_index=0)

        assert large_salience > small_salience

    def test_pure_counter_ranking(self):
        """counter=1, others=0 should rank purely by counter-trend defense."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.0,
            counter_weight=1.0,
            range_counter_weight=0.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        small_counter_leg = self._create_mock_leg(range_val=100.0, counter_range=50.0)
        large_counter_leg = self._create_mock_leg(range_val=50.0, counter_range=200.0)

        small_salience = layer._compute_salience(small_counter_leg, current_bar_index=0)
        large_salience = layer._compute_salience(large_counter_leg, current_bar_index=0)

        # Large counter should win even with smaller range
        assert large_salience > small_salience

    def test_pure_range_counter_ranking(self):
        """range_counter=1, others=0 should require both big AND defended."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.0,
            counter_weight=0.0,
            range_counter_weight=1.0,
            impulse_weight=0.0,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # Big range, small counter
        undefended_leg = self._create_mock_leg(range_val=200.0, counter_range=10.0)
        # Small range, big counter
        small_defended_leg = self._create_mock_leg(range_val=50.0, counter_range=200.0)
        # Medium range, medium counter
        balanced_leg = self._create_mock_leg(range_val=100.0, counter_range=100.0)

        undefended_salience = layer._compute_salience(undefended_leg, current_bar_index=0)
        small_defended_salience = layer._compute_salience(small_defended_leg, current_bar_index=0)
        balanced_salience = layer._compute_salience(balanced_leg, current_bar_index=0)

        # Balanced should beat undefended (200×10 < 100×100)
        assert balanced_salience > undefended_salience
        # Balanced should beat small_defended (50×200 = 100×100)
        assert abs(balanced_salience - small_defended_salience) < 0.01

    def test_blended_weights(self):
        """Any blend should work: range=0.3, counter=0.3, impulse=0.4."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.3,
            counter_weight=0.3,
            range_counter_weight=0.0,
            impulse_weight=0.4,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        leg = self._create_mock_leg(
            range_val=125.0,  # half of max -> 0.5 score
            counter_range=125.0,  # half of max -> 0.5 score
            impulsiveness=50.0,  # 50% -> 0.5 score
        )

        salience = layer._compute_salience(leg, current_bar_index=0)

        # Expected: 0.3×0.5 + 0.3×0.5 + 0.4×0.5 = 0.15 + 0.15 + 0.2 = 0.5
        assert abs(salience - 0.5) < 0.01


class TestNoStandaloneMode:
    """Tests verifying standalone mode is removed."""

    def _create_mock_leg(
        self,
        origin_index: int = 0,
        range_val: float = 10.0,
        counter_range: float = None,
        depth: int = 0,
        impulsiveness: float = 50.0,
    ):
        """Create a mock leg for testing."""
        leg = MagicMock()
        leg.origin_index = origin_index
        leg.range = Decimal(str(range_val))
        leg.origin_counter_trend_range = Decimal(str(counter_range)) if counter_range else None
        leg.depth = depth
        leg.impulsiveness = impulsiveness
        leg.bin_impulsiveness = impulsiveness  # Salience uses bin-normalized (#491)
        return leg

    def _populate_distribution(self, layer: ReferenceLayer, median: float = 10.0):
        """Helper to populate bin distribution with known median."""
        for i in range(10):
            layer._bin_distribution.add_leg(f"leg_{i}", median, 1000.0 + i)

    def test_range_counter_does_not_disable_others(self):
        """Setting range_counter_weight > 0 should not disable other weights."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.3,
            counter_weight=0.0,
            range_counter_weight=0.3,
            impulse_weight=0.4,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # Two legs with same range×counter product but different impulse
        low_impulse_leg = self._create_mock_leg(
            range_val=100.0, counter_range=100.0, impulsiveness=20.0
        )
        high_impulse_leg = self._create_mock_leg(
            range_val=100.0, counter_range=100.0, impulsiveness=80.0
        )

        low_salience = layer._compute_salience(low_impulse_leg, current_bar_index=0)
        high_salience = layer._compute_salience(high_impulse_leg, current_bar_index=0)

        # High impulse should win because impulse_weight=0.4 contributes
        assert high_salience > low_salience


class TestImpulseRedistribution:
    """Tests for weight redistribution when impulse is missing."""

    def _create_mock_leg(
        self,
        origin_index: int = 0,
        range_val: float = 10.0,
        counter_range: float = None,
        depth: int = 0,
        impulsiveness: float = None,
    ):
        """Create a mock leg for testing."""
        leg = MagicMock()
        leg.origin_index = origin_index
        leg.range = Decimal(str(range_val))
        leg.origin_counter_trend_range = Decimal(str(counter_range)) if counter_range else None
        leg.depth = depth
        leg.impulsiveness = impulsiveness
        leg.bin_impulsiveness = impulsiveness  # Salience uses bin-normalized (#491)
        return leg

    def _populate_distribution(self, layer: ReferenceLayer, median: float = 10.0):
        """Helper to populate bin distribution with known median."""
        for i in range(10):
            layer._bin_distribution.add_leg(f"leg_{i}", median, 1000.0 + i)

    def test_impulse_redistributed_when_missing(self):
        """Impulse weight should be redistributed to other weights when missing."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.4,
            counter_weight=0.0,
            range_counter_weight=0.0,
            impulse_weight=0.4,
            recency_weight=0.1,
            depth_weight=0.1,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # Leg without impulse
        leg = self._create_mock_leg(
            range_val=250.0,  # max_val -> score = 1.0
            impulsiveness=None,
        )

        salience = layer._compute_salience(leg, current_bar_index=0)

        # Without impulse, range_weight=0.4 should be boosted proportionally
        # Total non-impulse = 0.4 + 0.1 + 0.1 = 0.6
        # After redistribution, range contribution = 0.4 × (1 + 0.4/0.6) = 0.4 × 1.667 = 0.667
        # With range_score = 1.0, recency_score ~1.0, depth_score = 1.0
        # Total should be close to 1.0
        assert salience > 0.9

    def test_counter_weight_included_in_redistribution(self):
        """Counter weight should also receive redistributed impulse."""
        config = ReferenceConfig.default().with_salience_weights(
            range_weight=0.3,
            counter_weight=0.3,
            range_counter_weight=0.0,
            impulse_weight=0.4,
            recency_weight=0.0,
            depth_weight=0.0,
        )
        layer = ReferenceLayer(reference_config=config)
        self._populate_distribution(layer, median=10.0)

        # Leg without impulse but with counter
        leg = self._create_mock_leg(
            range_val=250.0,  # max_val -> score = 1.0
            counter_range=250.0,  # max_val -> score = 1.0
            impulsiveness=None,
        )

        salience = layer._compute_salience(leg, current_bar_index=0)

        # After redistribution: range and counter each get boosted
        # Total non-impulse = 0.3 + 0.3 = 0.6
        # Each gets factor = 1 + 0.4/0.6 = 1.667
        # Final: 0.3×1.667×1.0 + 0.3×1.667×1.0 = 0.5 + 0.5 = 1.0
        assert abs(salience - 1.0) < 0.01
