"""
Tests for Ground Truth Annotator main.py functions.

Tests the CLI helper functions including date parsing and offset calculation.
"""

import pytest
from datetime import datetime

from src.ground_truth_annotator.main import parse_start_date, parse_offset


class TestParseStartDate:
    """Tests for parse_start_date function."""

    def test_parse_iso_format(self):
        """Test parsing ISO date format: 2020-01-15."""
        result = parse_start_date("2020-01-15")
        assert result == datetime(2020, 1, 15)

    def test_parse_month_abbrev_format(self):
        """Test parsing month abbreviation format: 2020-Jan-01."""
        result = parse_start_date("2020-Jan-01")
        assert result == datetime(2020, 1, 1)

    def test_parse_month_abbrev_lowercase(self):
        """Test parsing lowercase month abbreviation: 2020-jan-15."""
        result = parse_start_date("2020-jan-15")
        assert result == datetime(2020, 1, 15)

    def test_parse_day_first_format(self):
        """Test parsing day-first format: 15-Jan-2020."""
        result = parse_start_date("15-Jan-2020")
        assert result == datetime(2020, 1, 15)

    def test_parse_month_first_format(self):
        """Test parsing month-first format: Jan-15-2020."""
        result = parse_start_date("Jan-15-2020")
        assert result == datetime(2020, 1, 15)

    def test_parse_slash_iso_format(self):
        """Test parsing slash-separated ISO format: 2020/01/15."""
        result = parse_start_date("2020/01/15")
        assert result == datetime(2020, 1, 15)

    def test_parse_slash_us_format(self):
        """Test parsing slash-separated US format: 01/15/2020."""
        result = parse_start_date("01/15/2020")
        assert result == datetime(2020, 1, 15)

    def test_invalid_format_raises_error(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            parse_start_date("not-a-date")
        assert "Could not parse date" in str(excinfo.value)

    def test_error_message_suggests_formats(self):
        """Test that error message suggests valid formats."""
        with pytest.raises(ValueError) as excinfo:
            parse_start_date("invalid")
        assert "2020-Jan-01" in str(excinfo.value)
        assert "2020-01-01" in str(excinfo.value)


class TestParseOffset:
    """Tests for parse_offset function."""

    def test_parse_numeric_offset(self):
        """Test parsing numeric offset string."""
        result = parse_offset("1000", total_bars=50000, window_size=10000)
        assert result == 1000

    def test_parse_zero_offset(self):
        """Test parsing zero offset."""
        result = parse_offset("0", total_bars=50000, window_size=10000)
        assert result == 0

    def test_parse_random_offset(self):
        """Test parsing 'random' offset."""
        result = parse_offset("random", total_bars=50000, window_size=10000)
        # Random offset should be within valid range
        max_offset = 50000 - 10000
        assert 0 <= result <= max_offset

    def test_parse_random_offset_case_insensitive(self):
        """Test parsing 'RANDOM' is case-insensitive."""
        result = parse_offset("RANDOM", total_bars=50000, window_size=10000)
        max_offset = 50000 - 10000
        assert 0 <= result <= max_offset

    def test_random_offset_at_boundary(self):
        """Test random offset when window fills data."""
        result = parse_offset("random", total_bars=10000, window_size=10000)
        # Max offset is 0 when window equals data size
        assert result == 0

    def test_random_offset_window_larger_than_data(self):
        """Test random offset when window is larger than data."""
        result = parse_offset("random", total_bars=5000, window_size=10000)
        # Max offset is 0 when window exceeds data size
        assert result == 0
