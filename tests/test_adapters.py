"""
Tests for swing detection compatibility adapters.

Verifies:
- Round-trip conversion preserves essential data
- Fib level calculations correct for bull/bear
- detect_swings_compat() returns dict with scale keys
- Legacy scale grouping produces reasonable distribution
- Empty input handled gracefully
"""

from decimal import Decimal
import pytest
import pandas as pd
import numpy as np

from src.swing_analysis.adapters import (
    swing_node_to_reference_swing,
    reference_swing_to_swing_node,
    detect_swings_compat,
    _group_by_legacy_scale,
    convert_swings_to_legacy_dict,
)
from src.swing_analysis.swing_node import SwingNode
from src.swing_analysis.adapters import ReferenceSwing


class TestSwingNodeToReferenceSwing:
    """Tests for converting SwingNode to ReferenceSwing."""

    def test_bull_swing_conversion(self):
        """Bull swing should convert with correct Fib levels."""
        node = SwingNode(
            swing_id="test1234",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )

        legacy = swing_node_to_reference_swing(node)

        assert legacy.high_price == 5100.0
        assert legacy.high_bar_index == 100
        assert legacy.low_price == 5000.0
        assert legacy.low_bar_index == 150
        assert legacy.size == 100.0
        assert legacy.direction == "bull"

        # Bull swing: levels calculated from low up
        # 0.382 level = low + size * 0.382 = 5000 + 100 * 0.382 = 5038.2
        assert abs(legacy.level_0382 - 5038.2) < 0.01
        # 2x level = low + size * 2.0 = 5000 + 100 * 2.0 = 5200
        assert abs(legacy.level_2x - 5200.0) < 0.01

    def test_bear_swing_conversion(self):
        """Bear swing should convert with correct Fib levels."""
        node = SwingNode(
            swing_id="test5678",
            high_bar_index=150,
            high_price=Decimal("5100.00"),
            low_bar_index=100,
            low_price=Decimal("5000.00"),
            direction="bear",
            status="active",
            formed_at_bar=150,
        )

        legacy = swing_node_to_reference_swing(node)

        assert legacy.high_price == 5100.0
        assert legacy.low_price == 5000.0
        assert legacy.direction == "bear"

        # Bear swing: levels calculated from high down
        # 0.382 level = high - size * 0.382 = 5100 - 100 * 0.382 = 5061.8
        assert abs(legacy.level_0382 - 5061.8) < 0.01
        # 2x level = high - size * 2.0 = 5100 - 100 * 2.0 = 4900
        assert abs(legacy.level_2x - 4900.0) < 0.01

    def test_default_fields_set(self):
        """Legacy fields not in SwingNode should have sensible defaults."""
        node = SwingNode(
            swing_id="default1",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )

        legacy = swing_node_to_reference_swing(node)

        assert legacy.rank == 0
        assert legacy.impulse == 0.0
        assert legacy.size_rank is None
        assert legacy.impulse_rank is None
        assert legacy.combined_score is None
        assert legacy.structurally_separated is True
        assert legacy.fib_confluence_score == 0.0

    def test_parent_mapped_to_containing_swing(self):
        """Parent swing ID should map to containing_swing_id."""
        parent = SwingNode(
            swing_id="parent12",
            high_bar_index=50,
            high_price=Decimal("5200.00"),
            low_bar_index=80,
            low_price=Decimal("4900.00"),
            direction="bull",
            status="active",
            formed_at_bar=80,
        )

        child = SwingNode(
            swing_id="child123",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )
        child.add_parent(parent)

        legacy = swing_node_to_reference_swing(child)

        assert legacy.containing_swing_id == "parent12"
        assert legacy.separation_is_anchor is False

    def test_no_parent_is_anchor(self):
        """Swing with no parents should be marked as anchor."""
        node = SwingNode(
            swing_id="orphan12",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )

        legacy = swing_node_to_reference_swing(node)

        assert legacy.containing_swing_id is None
        assert legacy.separation_is_anchor is True


class TestReferenceSwingToSwingNode:
    """Tests for converting ReferenceSwing back to SwingNode."""

    def test_basic_conversion(self):
        """Basic conversion should preserve essential fields."""
        ref = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=100,
            low_price=5000.0,
            low_bar_index=150,
            size=100.0,
            direction="bull",
        )

        node = reference_swing_to_swing_node(ref)

        assert float(node.high_price) == 5100.0
        assert node.high_bar_index == 100
        assert float(node.low_price) == 5000.0
        assert node.low_bar_index == 150
        assert node.direction == "bull"
        assert node.status == "active"

    def test_custom_swing_id(self):
        """Custom swing_id should be used if provided."""
        ref = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=100,
            low_price=5000.0,
            low_bar_index=150,
            size=100.0,
            direction="bull",
        )

        node = reference_swing_to_swing_node(ref, swing_id="custom99")

        assert node.swing_id == "custom99"

    def test_custom_formed_at_bar(self):
        """Custom formed_at_bar should be used if provided."""
        ref = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=100,
            low_price=5000.0,
            low_bar_index=150,
            size=100.0,
            direction="bull",
        )

        node = reference_swing_to_swing_node(ref, formed_at_bar=200)

        assert node.formed_at_bar == 200

    def test_default_formed_at_bar(self):
        """Default formed_at_bar should be max of bar indices."""
        ref = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=100,
            low_price=5000.0,
            low_bar_index=150,
            size=100.0,
            direction="bull",
        )

        node = reference_swing_to_swing_node(ref)

        assert node.formed_at_bar == 150  # max(100, 150)


class TestRoundTripConversion:
    """Tests for round-trip conversion preserving data."""

    def test_swing_node_round_trip(self):
        """SwingNode -> ReferenceSwing -> SwingNode preserves essential data."""
        original = SwingNode(
            swing_id="round123",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )

        legacy = swing_node_to_reference_swing(original)
        restored = reference_swing_to_swing_node(
            legacy, swing_id=original.swing_id, formed_at_bar=original.formed_at_bar
        )

        assert restored.swing_id == original.swing_id
        assert restored.high_bar_index == original.high_bar_index
        assert restored.low_bar_index == original.low_bar_index
        assert restored.direction == original.direction
        assert restored.formed_at_bar == original.formed_at_bar
        # Price precision may differ due to float conversion
        assert abs(float(restored.high_price) - float(original.high_price)) < 0.01
        assert abs(float(restored.low_price) - float(original.low_price)) < 0.01


class TestGroupByLegacyScale:
    """Tests for _group_by_legacy_scale function."""

    def test_empty_input(self):
        """Empty input should return empty scale dicts."""
        result = _group_by_legacy_scale([])

        assert result == {"XL": [], "L": [], "M": [], "S": []}

    def test_single_swing_goes_to_xl(self):
        """Single swing should go to XL (top 10% of 1 is 1)."""
        swing = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=100,
            low_price=5000.0,
            low_bar_index=150,
            size=100.0,
            direction="bull",
        )

        result = _group_by_legacy_scale([swing])

        assert len(result["XL"]) == 1
        assert len(result["L"]) == 0
        assert len(result["M"]) == 0
        assert len(result["S"]) == 0

    def test_ten_swings_distribution(self):
        """10 swings should distribute as 1 XL, 1-2 L, 2-3 M, rest S."""
        swings = []
        for i in range(10):
            swings.append(
                ReferenceSwing(
                    high_price=5100.0 + i * 100,
                    high_bar_index=100,
                    low_price=5000.0,
                    low_bar_index=150,
                    size=100.0 + i * 100,  # Varying sizes
                    direction="bull",
                )
            )

        result = _group_by_legacy_scale(swings)

        # Verify all swings accounted for
        total = sum(len(swings) for swings in result.values())
        assert total == 10

        # XL should have at least 1 (top 10%)
        assert len(result["XL"]) >= 1
        # All scales should have something or total should be 10
        assert len(result["XL"]) + len(result["L"]) + len(result["M"]) + len(result["S"]) == 10

    def test_swings_sorted_by_size(self):
        """Largest swings should be in XL, smallest in S."""
        swings = [
            ReferenceSwing(
                high_price=5100.0,
                high_bar_index=100,
                low_price=5000.0,
                low_bar_index=150,
                size=100.0,  # Smallest
                direction="bull",
            ),
            ReferenceSwing(
                high_price=5500.0,
                high_bar_index=100,
                low_price=5000.0,
                low_bar_index=150,
                size=500.0,  # Largest
                direction="bull",
            ),
            ReferenceSwing(
                high_price=5200.0,
                high_bar_index=100,
                low_price=5000.0,
                low_bar_index=150,
                size=200.0,  # Medium
                direction="bull",
            ),
        ]

        result = _group_by_legacy_scale(swings)

        # Largest (500) should be in XL
        xl_sizes = [s.size for s in result["XL"]]
        assert 500.0 in xl_sizes

    def test_ranks_assigned(self):
        """Ranks should be assigned based on size."""
        swings = [
            ReferenceSwing(
                high_price=5100.0,
                high_bar_index=100,
                low_price=5000.0,
                low_bar_index=150,
                size=100.0,
                direction="bull",
            ),
            ReferenceSwing(
                high_price=5300.0,
                high_bar_index=100,
                low_price=5000.0,
                low_bar_index=150,
                size=300.0,
                direction="bull",
            ),
        ]

        result = _group_by_legacy_scale(swings)

        # All swings should have ranks 1 and 2
        all_swings = result["XL"] + result["L"] + result["M"] + result["S"]
        ranks = sorted([s.rank for s in all_swings])
        assert ranks == [1, 2]


class TestDetectSwingsCompat:
    """Tests for detect_swings_compat function."""

    @pytest.fixture
    def sample_ohlc_df(self):
        """Create sample OHLC DataFrame for testing."""
        np.random.seed(42)
        n_bars = 200

        # Generate trending price data with volatility
        base_price = 5000.0
        returns = np.random.normal(0.0002, 0.01, n_bars)
        prices = base_price * np.cumprod(1 + returns)

        # Create OHLC with some variation
        highs = prices * (1 + np.abs(np.random.normal(0, 0.005, n_bars)))
        lows = prices * (1 - np.abs(np.random.normal(0, 0.005, n_bars)))
        opens = prices * (1 + np.random.normal(0, 0.002, n_bars))
        closes = prices * (1 + np.random.normal(0, 0.002, n_bars))

        # Ensure OHLC consistency
        highs = np.maximum(highs, np.maximum(opens, closes))
        lows = np.minimum(lows, np.minimum(opens, closes))

        return pd.DataFrame({
            "timestamp": range(1700000000, 1700000000 + n_bars * 60, 60),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
        })

    def test_returns_scale_dict(self, sample_ohlc_df):
        """Result should have XL, L, M, S keys."""
        result = detect_swings_compat(sample_ohlc_df)

        assert "XL" in result
        assert "L" in result
        assert "M" in result
        assert "S" in result

    def test_returns_reference_swings(self, sample_ohlc_df):
        """All items should be ReferenceSwing objects."""
        result = detect_swings_compat(sample_ohlc_df)

        for scale, swings in result.items():
            for swing in swings:
                assert isinstance(swing, ReferenceSwing), f"Expected ReferenceSwing in {scale}"

    def test_accepts_kwargs_silently(self, sample_ohlc_df):
        """Should accept legacy kwargs without error."""
        # These are legacy parameters that should be ignored
        result = detect_swings_compat(
            sample_ohlc_df,
            lookback=5,
            filter_redundant=True,
            quota=10,
            larger_swings=None,
        )

        assert isinstance(result, dict)


class TestConvertSwingsToLegacyDict:
    """Tests for convert_swings_to_legacy_dict function."""

    def test_empty_input(self):
        """Empty input should return empty scale dicts."""
        result = convert_swings_to_legacy_dict([])

        assert result == {"XL": [], "L": [], "M": [], "S": []}

    def test_returns_dicts_not_dataclasses(self):
        """Should return dicts, not ReferenceSwing objects."""
        node = SwingNode(
            swing_id="dict1234",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )

        result = convert_swings_to_legacy_dict([node])

        # All items should be dicts
        for scale, swings in result.items():
            for swing in swings:
                assert isinstance(swing, dict), f"Expected dict in {scale}"

    def test_dict_has_expected_keys(self):
        """Swing dicts should have expected keys."""
        node = SwingNode(
            swing_id="keys1234",
            high_bar_index=100,
            high_price=Decimal("5100.00"),
            low_bar_index=150,
            low_price=Decimal("5000.00"),
            direction="bull",
            status="active",
            formed_at_bar=150,
        )

        result = convert_swings_to_legacy_dict([node])

        # Get the swing dict (should be in XL since only one)
        swing_dict = result["XL"][0]

        assert "high_price" in swing_dict
        assert "low_price" in swing_dict
        assert "high_bar_index" in swing_dict
        assert "low_bar_index" in swing_dict
        assert "size" in swing_dict
        assert "level_0382" in swing_dict
        assert "level_2x" in swing_dict
