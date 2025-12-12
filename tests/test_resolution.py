"""
Tests for the resolution module.

Verifies resolution-agnostic configuration works correctly across different
source data resolutions.
"""

import pytest

from src.swing_analysis.resolution import (
    RESOLUTION_MINUTES,
    SUPPORTED_RESOLUTIONS,
    parse_resolution,
    get_available_timeframes,
    get_default_aggregations,
    get_allowed_aggregations,
    create_resolution_config,
    get_gap_threshold_minutes,
    format_minutes,
)


class TestParseResolution:
    """Tests for parse_resolution function."""

    def test_parse_1m(self):
        assert parse_resolution("1m") == 1

    def test_parse_5m(self):
        assert parse_resolution("5m") == 5

    def test_parse_15m(self):
        assert parse_resolution("15m") == 15

    def test_parse_30m(self):
        assert parse_resolution("30m") == 30

    def test_parse_1h(self):
        assert parse_resolution("1h") == 60

    def test_parse_4h(self):
        assert parse_resolution("4h") == 240

    def test_parse_1d(self):
        assert parse_resolution("1d") == 1440

    def test_parse_1w(self):
        assert parse_resolution("1w") == 10080

    def test_parse_1mo(self):
        assert parse_resolution("1mo") == 43200

    def test_parse_case_insensitive(self):
        assert parse_resolution("1M") == 1
        assert parse_resolution("1H") == 60

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_resolution("2m")
        with pytest.raises(ValueError):
            parse_resolution("invalid")


class TestGetAvailableTimeframes:
    """Tests for get_available_timeframes function."""

    def test_1m_source(self):
        tfs = get_available_timeframes(1)
        assert 1 in tfs
        assert 5 in tfs
        assert 15 in tfs
        assert 60 in tfs
        assert 240 in tfs

    def test_5m_source(self):
        tfs = get_available_timeframes(5)
        assert 1 not in tfs
        assert 5 in tfs
        assert 15 in tfs
        assert 60 in tfs

    def test_1h_source(self):
        tfs = get_available_timeframes(60)
        assert 1 not in tfs
        assert 5 not in tfs
        assert 15 not in tfs
        assert 60 in tfs
        assert 240 in tfs

    def test_1d_source(self):
        tfs = get_available_timeframes(1440)
        assert 60 not in tfs
        assert 240 not in tfs
        assert 1440 in tfs


class TestGetDefaultAggregations:
    """Tests for get_default_aggregations function."""

    def test_1m_defaults(self):
        aggs = get_default_aggregations(1)
        assert aggs["S"] == 1
        assert aggs["M"] >= aggs["S"]
        assert aggs["L"] >= aggs["M"]
        assert aggs["XL"] >= aggs["L"]

    def test_5m_defaults(self):
        aggs = get_default_aggregations(5)
        assert aggs["S"] == 5  # Source resolution
        assert aggs["M"] >= aggs["S"]
        assert aggs["L"] >= aggs["M"]
        assert aggs["XL"] >= aggs["L"]

    def test_monotonicity(self):
        """Aggregations should increase monotonically S -> M -> L -> XL."""
        for res in [1, 5, 15, 30, 60, 240]:
            aggs = get_default_aggregations(res)
            assert aggs["S"] <= aggs["M"]
            assert aggs["M"] <= aggs["L"]
            assert aggs["L"] <= aggs["XL"]


class TestGetAllowedAggregations:
    """Tests for get_allowed_aggregations function."""

    def test_1m_allowed(self):
        allowed = get_allowed_aggregations(1)
        assert 1 in allowed
        assert 5 in allowed

    def test_5m_allowed(self):
        allowed = get_allowed_aggregations(5)
        assert 1 not in allowed  # Can't aggregate to smaller than source
        assert 5 in allowed

    def test_1h_allowed(self):
        allowed = get_allowed_aggregations(60)
        assert 5 not in allowed
        assert 15 not in allowed
        assert 60 in allowed


class TestCreateResolutionConfig:
    """Tests for create_resolution_config function."""

    def test_5m_config(self):
        config = create_resolution_config("5m")
        assert config.source_resolution == "5m"
        assert config.source_minutes == 5
        assert 5 in config.available_timeframes
        assert 1 not in config.available_timeframes
        assert config.default_aggregations["S"] == 5

    def test_1h_config(self):
        config = create_resolution_config("1h")
        assert config.source_minutes == 60
        assert 60 in config.available_timeframes
        assert 15 not in config.available_timeframes


class TestGapThreshold:
    """Tests for get_gap_threshold_minutes function."""

    def test_1m_gap_threshold(self):
        threshold = get_gap_threshold_minutes(1)
        assert threshold == 1.5  # 1.5x source resolution

    def test_5m_gap_threshold(self):
        threshold = get_gap_threshold_minutes(5)
        assert threshold == 7.5  # 1.5x source resolution

    def test_custom_tolerance(self):
        threshold = get_gap_threshold_minutes(5, tolerance_factor=2.0)
        assert threshold == 10.0


class TestFormatMinutes:
    """Tests for format_minutes function."""

    def test_format_minutes(self):
        assert format_minutes(5) == "5m"
        assert format_minutes(30) == "30m"

    def test_format_hours(self):
        assert format_minutes(60) == "1h"
        assert format_minutes(240) == "4h"

    def test_format_days(self):
        assert format_minutes(1440) == "1d"
        assert format_minutes(2880) == "2d"
