"""Unit tests for ReferenceFrame coordinate system."""

import pytest
from decimal import Decimal

from src.swing_analysis.reference_frame import ReferenceFrame
from src.swing_analysis.swing_detector import ReferenceSwing


class TestReferenceFrameBasics:
    """Test ReferenceFrame basic construction and properties."""

    def test_bull_frame_construction(self):
        """Bull frame: anchor0 is low, anchor1 is high."""
        frame = ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )
        assert frame.anchor0 == Decimal("5000")
        assert frame.anchor1 == Decimal("5100")
        assert frame.direction == "BULL"

    def test_bear_frame_construction(self):
        """Bear frame: anchor0 is high, anchor1 is low."""
        frame = ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )
        assert frame.anchor0 == Decimal("5100")
        assert frame.anchor1 == Decimal("5000")
        assert frame.direction == "BEAR"

    def test_range_positive_for_bull(self):
        """Bull frame has positive range (high - low > 0)."""
        frame = ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )
        assert frame.range == Decimal("100")
        assert frame.range > 0

    def test_range_negative_for_bear(self):
        """Bear frame has negative range (low - high < 0)."""
        frame = ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )
        assert frame.range == Decimal("-100")
        assert frame.range < 0

    def test_zero_range_raises_error(self):
        """Cannot create frame with zero range."""
        with pytest.raises(ValueError, match="zero range"):
            ReferenceFrame(
                anchor0=Decimal("5000"),
                anchor1=Decimal("5000"),
                direction="BULL",
            )

    def test_immutable(self):
        """Frame is immutable (frozen dataclass)."""
        frame = ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            frame.anchor0 = Decimal("4900")


class TestBullFrameRatios:
    """Test ratio calculations for bull frames."""

    @pytest.fixture
    def bull_frame(self):
        """Bull frame: low=5000, high=5100, range=100."""
        return ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )

    def test_ratio_at_anchor0_is_zero(self, bull_frame):
        """ratio(anchor0) == 0 (defended pivot)."""
        assert bull_frame.ratio(Decimal("5000")) == Decimal("0")

    def test_ratio_at_anchor1_is_one(self, bull_frame):
        """ratio(anchor1) == 1 (origin extremum)."""
        assert bull_frame.ratio(Decimal("5100")) == Decimal("1")

    def test_ratio_at_completion_is_two(self, bull_frame):
        """ratio at 2x extension == 2."""
        # 2x extension = 5000 + 2 * 100 = 5200
        assert bull_frame.ratio(Decimal("5200")) == Decimal("2")

    def test_ratio_at_fib_382(self, bull_frame):
        """Test 0.382 retracement level."""
        # 0.382 = 5000 + 0.382 * 100 = 5038.2
        price = Decimal("5038.2")
        assert bull_frame.ratio(price) == Decimal("0.382")

    def test_ratio_at_fib_618(self, bull_frame):
        """Test 0.618 retracement level."""
        price = Decimal("5061.8")
        assert bull_frame.ratio(price) == Decimal("0.618")

    def test_ratio_below_defended_is_negative(self, bull_frame):
        """Price below defended pivot (stop-run) has negative ratio."""
        # 4990 is 10 points below 5000 = -0.1 ratio
        assert bull_frame.ratio(Decimal("4990")) == Decimal("-0.1")

    def test_ratio_at_deep_stop_run(self, bull_frame):
        """Test -0.15 (deep invalidation threshold)."""
        # -0.15 * 100 = -15 points below 5000 = 4985
        assert bull_frame.ratio(Decimal("4985")) == Decimal("-0.15")


class TestBearFrameRatios:
    """Test ratio calculations for bear frames."""

    @pytest.fixture
    def bear_frame(self):
        """Bear frame: high=5100 (defended), low=5000 (origin), range=-100."""
        return ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )

    def test_ratio_at_anchor0_is_zero(self, bear_frame):
        """ratio(anchor0) == 0 (defended pivot = high for bear)."""
        assert bear_frame.ratio(Decimal("5100")) == Decimal("0")

    def test_ratio_at_anchor1_is_one(self, bear_frame):
        """ratio(anchor1) == 1 (origin = low for bear)."""
        assert bear_frame.ratio(Decimal("5000")) == Decimal("1")

    def test_ratio_at_completion_is_two(self, bear_frame):
        """ratio at 2x extension == 2."""
        # For bear: 5100 + 2 * (-100) = 4900
        assert bear_frame.ratio(Decimal("4900")) == Decimal("2")

    def test_ratio_at_fib_382(self, bear_frame):
        """Test 0.382 retracement level."""
        # 0.382 for bear = 5100 + 0.382 * (-100) = 5061.8
        price = Decimal("5061.8")
        assert bear_frame.ratio(price) == Decimal("0.382")

    def test_ratio_above_defended_is_negative(self, bear_frame):
        """Price above defended pivot (stop-run) has negative ratio."""
        # 5110 is 10 points above 5100 = -0.1 ratio (with range -100)
        assert bear_frame.ratio(Decimal("5110")) == Decimal("-0.1")


class TestPriceConversion:
    """Test price() conversion method."""

    @pytest.fixture
    def bull_frame(self):
        """Bull frame: low=5000, high=5100."""
        return ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )

    @pytest.fixture
    def bear_frame(self):
        """Bear frame: high=5100, low=5000."""
        return ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )

    def test_price_at_zero_is_anchor0_bull(self, bull_frame):
        """price(0) == anchor0 for bull."""
        assert bull_frame.price(Decimal("0")) == Decimal("5000")

    def test_price_at_one_is_anchor1_bull(self, bull_frame):
        """price(1) == anchor1 for bull."""
        assert bull_frame.price(Decimal("1")) == Decimal("5100")

    def test_price_at_two_is_completion_bull(self, bull_frame):
        """price(2) == completion target for bull."""
        assert bull_frame.price(Decimal("2")) == Decimal("5200")

    def test_price_at_zero_is_anchor0_bear(self, bear_frame):
        """price(0) == anchor0 for bear."""
        assert bear_frame.price(Decimal("0")) == Decimal("5100")

    def test_price_at_one_is_anchor1_bear(self, bear_frame):
        """price(1) == anchor1 for bear."""
        assert bear_frame.price(Decimal("1")) == Decimal("5000")

    def test_price_at_two_is_completion_bear(self, bear_frame):
        """price(2) == completion target for bear."""
        assert bear_frame.price(Decimal("2")) == Decimal("4900")


class TestRoundTrip:
    """Test that price(ratio(x)) == x."""

    @pytest.fixture
    def bull_frame(self):
        return ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )

    @pytest.fixture
    def bear_frame(self):
        return ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )

    @pytest.mark.parametrize("price", [
        Decimal("4950"),   # Below defended
        Decimal("5000"),   # Defended pivot
        Decimal("5038.2"), # 0.382
        Decimal("5050"),   # 0.5
        Decimal("5061.8"), # 0.618
        Decimal("5100"),   # Origin
        Decimal("5150"),   # 1.5 extension
        Decimal("5200"),   # 2x completion
    ])
    def test_round_trip_bull(self, bull_frame, price):
        """price(ratio(x)) == x for bull frame."""
        ratio = bull_frame.ratio(price)
        recovered = bull_frame.price(ratio)
        assert recovered == price

    @pytest.mark.parametrize("price", [
        Decimal("5150"),   # Above defended (stop-run)
        Decimal("5100"),   # Defended pivot
        Decimal("5061.8"), # 0.382
        Decimal("5050"),   # 0.5
        Decimal("5038.2"), # 0.618
        Decimal("5000"),   # Origin
        Decimal("4950"),   # 1.5 extension
        Decimal("4900"),   # 2x completion
    ])
    def test_round_trip_bear(self, bear_frame, price):
        """price(ratio(x)) == x for bear frame."""
        ratio = bear_frame.ratio(price)
        recovered = bear_frame.price(ratio)
        assert recovered == price


class TestFromSwing:
    """Test ReferenceFrame.from_swing() factory method."""

    def test_from_bull_swing(self):
        """Create frame from bull swing (high before low)."""
        swing = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=10,
            low_price=5000.0,
            low_bar_index=20,
            size=100.0,
            direction="bull",
        )
        frame = ReferenceFrame.from_swing(swing)

        assert frame.direction == "BULL"
        assert frame.anchor0 == Decimal("5000")  # Low = defended
        assert frame.anchor1 == Decimal("5100")  # High = origin
        assert frame.range == Decimal("100")

    def test_from_bear_swing(self):
        """Create frame from bear swing (low before high)."""
        swing = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=20,
            low_price=5000.0,
            low_bar_index=10,
            size=100.0,
            direction="bear",
        )
        frame = ReferenceFrame.from_swing(swing)

        assert frame.direction == "BEAR"
        assert frame.anchor0 == Decimal("5100")  # High = defended
        assert frame.anchor1 == Decimal("5000")  # Low = origin
        assert frame.range == Decimal("-100")

    def test_preserves_ratio_semantics_bull(self):
        """Bull frame from swing: defended pivot ratio == 0."""
        swing = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=10,
            low_price=5000.0,
            low_bar_index=20,
            size=100.0,
            direction="bull",
        )
        frame = ReferenceFrame.from_swing(swing)

        # Defended pivot (low) should be ratio 0
        assert frame.ratio(Decimal("5000")) == Decimal("0")
        # Origin (high) should be ratio 1
        assert frame.ratio(Decimal("5100")) == Decimal("1")

    def test_preserves_ratio_semantics_bear(self):
        """Bear frame from swing: defended pivot ratio == 0."""
        swing = ReferenceSwing(
            high_price=5100.0,
            high_bar_index=20,
            low_price=5000.0,
            low_bar_index=10,
            size=100.0,
            direction="bear",
        )
        frame = ReferenceFrame.from_swing(swing)

        # Defended pivot (high) should be ratio 0
        assert frame.ratio(Decimal("5100")) == Decimal("0")
        # Origin (low) should be ratio 1
        assert frame.ratio(Decimal("5000")) == Decimal("1")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_range(self):
        """Frame with small range (0.25 tick)."""
        frame = ReferenceFrame(
            anchor0=Decimal("5000.00"),
            anchor1=Decimal("5000.25"),
            direction="BULL",
        )
        assert frame.range == Decimal("0.25")
        assert frame.ratio(Decimal("5000.125")) == Decimal("0.5")

    def test_very_large_range(self):
        """Frame with large range (1000 points)."""
        frame = ReferenceFrame(
            anchor0=Decimal("4500"),
            anchor1=Decimal("5500"),
            direction="BULL",
        )
        assert frame.range == Decimal("1000")
        assert frame.ratio(Decimal("5000")) == Decimal("0.5")

    def test_negative_prices(self):
        """Frame works with negative prices (futures can be negative)."""
        frame = ReferenceFrame(
            anchor0=Decimal("-50"),
            anchor1=Decimal("-40"),
            direction="BULL",
        )
        assert frame.range == Decimal("10")
        assert frame.ratio(Decimal("-45")) == Decimal("0.5")

    def test_repr(self):
        """Test human-readable representation."""
        frame = ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )
        repr_str = repr(frame)
        assert "BULL" in repr_str
        assert "5000" in repr_str
        assert "5100" in repr_str
        assert "100" in repr_str  # range

    def test_ratio_precision(self):
        """Test that ratio maintains Decimal precision."""
        frame = ReferenceFrame(
            anchor0=Decimal("5000.00"),
            anchor1=Decimal("5100.00"),
            direction="BULL",
        )
        # 0.618 ratio should preserve precision
        price = frame.price(Decimal("0.618"))
        assert price == Decimal("5061.80")


class TestSymmetry:
    """Test that bull and bear frames are symmetric in their semantics."""

    def test_completion_semantics(self):
        """Both frames reach completion at ratio 2."""
        bull_frame = ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )
        bear_frame = ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )

        # Bull completion: above high
        bull_completion = bull_frame.price(Decimal("2"))
        assert bull_completion == Decimal("5200")

        # Bear completion: below low
        bear_completion = bear_frame.price(Decimal("2"))
        assert bear_completion == Decimal("4900")

    def test_invalidation_semantics(self):
        """Both frames have consistent invalidation at negative ratios."""
        bull_frame = ReferenceFrame(
            anchor0=Decimal("5000"),
            anchor1=Decimal("5100"),
            direction="BULL",
        )
        bear_frame = ReferenceFrame(
            anchor0=Decimal("5100"),
            anchor1=Decimal("5000"),
            direction="BEAR",
        )

        # Bull invalidation: below low
        bull_invalid = bull_frame.price(Decimal("-0.15"))
        assert bull_invalid == Decimal("4985")

        # Bear invalidation: above high
        bear_invalid = bear_frame.price(Decimal("-0.15"))
        assert bear_invalid == Decimal("5115")
