"""
Unit tests for discretization I/O module.

Tests file read/write, config comparison, and compatibility checks.
"""

import json
import pytest
from pathlib import Path

from src.discretization import (
    DiscretizationConfig,
    DiscretizationMeta,
    SwingEntry,
    DiscretizationEvent,
    DiscretizationLog,
    EventType,
    EffortAnnotation,
    ShockAnnotation,
    ParentContext,
)
from src.discretization.io import (
    write_log,
    read_log,
    compare_configs,
    compare_configs_detail,
    config_compatible,
    get_default_config,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_config():
    """Create a sample DiscretizationConfig."""
    return DiscretizationConfig(
        level_set=[-0.15, -0.10, 0.0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.618, 2.0],
        level_set_version="v1.0",
        crossing_semantics="close_cross",
        crossing_tolerance_pct=0.001,
        invalidation_thresholds={"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15},
        swing_detector_version="v2.3",
        discretizer_version="1.0",
    )


@pytest.fixture
def sample_meta(sample_config):
    """Create a sample DiscretizationMeta."""
    return DiscretizationMeta(
        instrument="ES",
        source_resolution="1m",
        date_range_start="2024-01-01T00:00:00Z",
        date_range_end="2024-01-31T23:59:59Z",
        created_at="2024-02-01T12:00:00Z",
        config=sample_config,
    )


@pytest.fixture
def sample_swing_entry():
    """Create a sample SwingEntry."""
    return SwingEntry(
        swing_id="swing-l-001",
        scale="L",
        direction="BULL",
        anchor0=5000.0,
        anchor1=5100.0,
        anchor0_bar=100,
        anchor1_bar=50,
        formed_at_bar=110,
        status="active",
    )


@pytest.fixture
def sample_event():
    """Create a sample DiscretizationEvent."""
    return DiscretizationEvent(
        bar=120,
        timestamp="2024-01-15T14:30:00Z",
        swing_id="swing-l-001",
        event_type=EventType.LEVEL_CROSS,
        data={
            "from_ratio": 0.382,
            "to_ratio": 0.5,
            "level_crossed": 0.5,
            "direction": "up",
        },
        effort=EffortAnnotation(dwell_bars=15, test_count=3, max_probe_r=0.395),
        shock=ShockAnnotation(levels_jumped=1, range_multiple=1.2),
        parent_context=ParentContext(
            scale="XL",
            swing_id="swing-xl-001",
            band="1.382-1.5",
            direction="BULL",
            ratio=1.42,
        ),
    )


@pytest.fixture
def sample_log(sample_meta, sample_swing_entry, sample_event):
    """Create a sample DiscretizationLog."""
    return DiscretizationLog(
        meta=sample_meta,
        swings=[sample_swing_entry],
        events=[sample_event],
    )


# =============================================================================
# write_log Tests
# =============================================================================


class TestWriteLog:
    """Tests for write_log function."""

    def test_write_creates_file(self, sample_log, tmp_path):
        """Test that write_log creates a file."""
        path = tmp_path / "test_log.json"
        write_log(sample_log, path)

        assert path.exists()
        assert path.stat().st_size > 0

    def test_write_creates_parent_directories(self, sample_log, tmp_path):
        """Test that write_log creates parent directories if needed."""
        path = tmp_path / "nested" / "dirs" / "test_log.json"
        write_log(sample_log, path)

        assert path.exists()

    def test_write_produces_valid_json(self, sample_log, tmp_path):
        """Test that written file is valid JSON."""
        path = tmp_path / "test_log.json"
        write_log(sample_log, path)

        with open(path) as f:
            data = json.load(f)

        assert "meta" in data
        assert "swings" in data
        assert "events" in data
        assert "schema_version" in data

    def test_write_pretty_printed(self, sample_log, tmp_path):
        """Test that output is pretty-printed (indented)."""
        path = tmp_path / "test_log.json"
        write_log(sample_log, path)

        content = path.read_text()
        # Pretty-printed JSON has newlines
        assert "\n" in content
        # And indentation
        assert "  " in content


# =============================================================================
# read_log Tests
# =============================================================================


class TestReadLog:
    """Tests for read_log function."""

    def test_read_round_trip(self, sample_log, tmp_path):
        """Test write then read produces identical log."""
        path = tmp_path / "test_log.json"
        write_log(sample_log, path)
        restored = read_log(path)

        assert restored.meta.instrument == sample_log.meta.instrument
        assert restored.meta.source_resolution == sample_log.meta.source_resolution
        assert len(restored.swings) == len(sample_log.swings)
        assert len(restored.events) == len(sample_log.events)
        assert restored.swings[0].swing_id == sample_log.swings[0].swing_id
        assert restored.events[0].bar == sample_log.events[0].bar

    def test_read_preserves_config(self, sample_log, tmp_path):
        """Test that config is preserved through round-trip."""
        path = tmp_path / "test_log.json"
        write_log(sample_log, path)
        restored = read_log(path)

        assert restored.meta.config.level_set == sample_log.meta.config.level_set
        assert restored.meta.config.level_set_version == sample_log.meta.config.level_set_version
        assert restored.meta.config.crossing_semantics == sample_log.meta.config.crossing_semantics

    def test_read_preserves_side_channels(self, sample_log, tmp_path):
        """Test that side-channels are preserved through round-trip."""
        path = tmp_path / "test_log.json"
        write_log(sample_log, path)
        restored = read_log(path)

        event = restored.events[0]
        assert event.effort is not None
        assert event.effort.dwell_bars == 15
        assert event.shock is not None
        assert event.shock.levels_jumped == 1
        assert event.parent_context is not None
        assert event.parent_context.scale == "XL"

    def test_read_file_not_found(self, tmp_path):
        """Test read_log raises for nonexistent file."""
        path = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            read_log(path)

    def test_read_invalid_json(self, tmp_path):
        """Test read_log raises for invalid JSON."""
        path = tmp_path / "invalid.json"
        path.write_text("not valid json {{{")

        with pytest.raises(json.JSONDecodeError):
            read_log(path)

    def test_read_with_validation_error(self, sample_log, tmp_path):
        """Test read_log raises ValueError on validation failure."""
        # Create a log with invalid event reference
        sample_log.events[0] = DiscretizationEvent(
            bar=120,
            timestamp="2024-01-15T14:30:00Z",
            swing_id="nonexistent-swing",  # Invalid reference
            event_type=EventType.LEVEL_CROSS,
            data={"from_ratio": 0.382, "to_ratio": 0.5, "level_crossed": 0.5, "direction": "up"},
        )

        path = tmp_path / "invalid_log.json"
        write_log(sample_log, path)

        with pytest.raises(ValueError) as exc_info:
            read_log(path, validate=True)

        assert "Validation failed" in str(exc_info.value)

    def test_read_skip_validation(self, sample_log, tmp_path):
        """Test read_log can skip validation."""
        # Create a log with invalid event reference
        sample_log.events[0] = DiscretizationEvent(
            bar=120,
            timestamp="2024-01-15T14:30:00Z",
            swing_id="nonexistent-swing",
            event_type=EventType.LEVEL_CROSS,
            data={"from_ratio": 0.382, "to_ratio": 0.5, "level_crossed": 0.5, "direction": "up"},
        )

        path = tmp_path / "invalid_log.json"
        write_log(sample_log, path)

        # Should not raise when validation is skipped
        restored = read_log(path, validate=False, warn_config_diff=False)
        assert restored is not None


# =============================================================================
# compare_configs Tests
# =============================================================================


class TestCompareConfigs:
    """Tests for compare_configs function."""

    def test_identical_configs(self, sample_log):
        """Test comparison of identical configs returns empty list."""
        log2 = DiscretizationLog(
            meta=sample_log.meta,
            swings=[],
            events=[],
        )

        diffs = compare_configs(sample_log, log2)
        assert diffs == []

    def test_different_level_set_version(self, sample_log, sample_config):
        """Test detection of different level_set_version."""
        config2 = DiscretizationConfig(
            level_set=sample_config.level_set,
            level_set_version="v1.1",  # Different version
            crossing_semantics=sample_config.crossing_semantics,
            crossing_tolerance_pct=sample_config.crossing_tolerance_pct,
            invalidation_thresholds=sample_config.invalidation_thresholds,
            swing_detector_version=sample_config.swing_detector_version,
            discretizer_version=sample_config.discretizer_version,
        )
        meta2 = DiscretizationMeta(
            instrument="ES",
            source_resolution="1m",
            date_range_start="2024-01-01T00:00:00Z",
            date_range_end="2024-01-31T23:59:59Z",
            created_at="2024-02-01T12:00:00Z",
            config=config2,
        )
        log2 = DiscretizationLog(meta=meta2, swings=[], events=[])

        diffs = compare_configs(sample_log, log2)
        assert len(diffs) == 1
        assert "level_set_version" in diffs[0]
        assert "v1.0 vs v1.1" in diffs[0]

    def test_different_crossing_semantics(self, sample_log, sample_config):
        """Test detection of different crossing_semantics."""
        config2 = DiscretizationConfig(
            level_set=sample_config.level_set,
            level_set_version=sample_config.level_set_version,
            crossing_semantics="wick_touch",  # Different
            crossing_tolerance_pct=sample_config.crossing_tolerance_pct,
            invalidation_thresholds=sample_config.invalidation_thresholds,
            swing_detector_version=sample_config.swing_detector_version,
            discretizer_version=sample_config.discretizer_version,
        )
        meta2 = DiscretizationMeta(
            instrument="ES",
            source_resolution="1m",
            date_range_start="2024-01-01T00:00:00Z",
            date_range_end="2024-01-31T23:59:59Z",
            created_at="2024-02-01T12:00:00Z",
            config=config2,
        )
        log2 = DiscretizationLog(meta=meta2, swings=[], events=[])

        diffs = compare_configs(sample_log, log2)
        assert len(diffs) == 1
        assert "crossing_semantics" in diffs[0]

    def test_different_level_set_contents(self, sample_log, sample_config):
        """Test detection of different level_set contents."""
        config2 = DiscretizationConfig(
            level_set=[0.0, 0.5, 1.0, 2.0],  # Different levels
            level_set_version=sample_config.level_set_version,
            crossing_semantics=sample_config.crossing_semantics,
            crossing_tolerance_pct=sample_config.crossing_tolerance_pct,
            invalidation_thresholds=sample_config.invalidation_thresholds,
            swing_detector_version=sample_config.swing_detector_version,
            discretizer_version=sample_config.discretizer_version,
        )
        meta2 = DiscretizationMeta(
            instrument="ES",
            source_resolution="1m",
            date_range_start="2024-01-01T00:00:00Z",
            date_range_end="2024-01-31T23:59:59Z",
            created_at="2024-02-01T12:00:00Z",
            config=config2,
        )
        log2 = DiscretizationLog(meta=meta2, swings=[], events=[])

        diffs = compare_configs(sample_log, log2)
        assert len(diffs) == 1
        assert "level_set differs" in diffs[0]

    def test_multiple_differences(self, sample_log, sample_config):
        """Test detection of multiple differences."""
        config2 = DiscretizationConfig(
            level_set=[0.0, 1.0, 2.0],  # Different
            level_set_version="v2.0",  # Different
            crossing_semantics="wick_touch",  # Different
            crossing_tolerance_pct=0.005,  # Different
            invalidation_thresholds={"S": -0.20, "M": -0.20, "L": -0.25, "XL": -0.25},  # Different
            swing_detector_version="v3.0",  # Different
            discretizer_version="2.0",  # Different
        )
        meta2 = DiscretizationMeta(
            instrument="ES",
            source_resolution="1m",
            date_range_start="2024-01-01T00:00:00Z",
            date_range_end="2024-01-31T23:59:59Z",
            created_at="2024-02-01T12:00:00Z",
            config=config2,
        )
        log2 = DiscretizationLog(meta=meta2, swings=[], events=[])

        diffs = compare_configs(sample_log, log2)
        # Should find all 7 differences
        assert len(diffs) == 7


class TestCompareConfigsDetail:
    """Tests for compare_configs_detail function."""

    def test_identical_configs(self, sample_config):
        """Test comparison of identical configs."""
        config2 = DiscretizationConfig(
            level_set=sample_config.level_set,
            level_set_version=sample_config.level_set_version,
            crossing_semantics=sample_config.crossing_semantics,
            crossing_tolerance_pct=sample_config.crossing_tolerance_pct,
            invalidation_thresholds=sample_config.invalidation_thresholds,
            swing_detector_version=sample_config.swing_detector_version,
            discretizer_version=sample_config.discretizer_version,
        )

        diffs = compare_configs_detail(sample_config, config2)
        assert diffs == []


# =============================================================================
# config_compatible Tests
# =============================================================================


class TestConfigCompatible:
    """Tests for config_compatible function."""

    def test_compatible_config(self, sample_log, sample_config):
        """Test config_compatible returns True for matching configs."""
        result = config_compatible(sample_log, sample_config)
        assert result is True

    def test_incompatible_version(self, sample_log, sample_config):
        """Test config_compatible returns False for different version."""
        expected = DiscretizationConfig(
            level_set=sample_config.level_set,
            level_set_version="v2.0",  # Different version
            crossing_semantics=sample_config.crossing_semantics,
            crossing_tolerance_pct=sample_config.crossing_tolerance_pct,
            invalidation_thresholds=sample_config.invalidation_thresholds,
            swing_detector_version=sample_config.swing_detector_version,
            discretizer_version=sample_config.discretizer_version,
        )

        result = config_compatible(sample_log, expected)
        assert result is False

    def test_incompatible_level_set(self, sample_log, sample_config):
        """Test config_compatible returns False for different level_set."""
        expected = DiscretizationConfig(
            level_set=[0.0, 0.5, 1.0, 2.0],  # Different levels
            level_set_version=sample_config.level_set_version,
            crossing_semantics=sample_config.crossing_semantics,
            crossing_tolerance_pct=sample_config.crossing_tolerance_pct,
            invalidation_thresholds=sample_config.invalidation_thresholds,
            swing_detector_version=sample_config.swing_detector_version,
            discretizer_version=sample_config.discretizer_version,
        )

        result = config_compatible(sample_log, expected)
        assert result is False

    def test_compatible_ignores_other_fields(self, sample_log, sample_config):
        """Test config_compatible ignores non-critical differences."""
        expected = DiscretizationConfig(
            level_set=sample_config.level_set,
            level_set_version=sample_config.level_set_version,
            crossing_semantics="wick_touch",  # Different but not checked
            crossing_tolerance_pct=0.999,  # Different but not checked
            invalidation_thresholds={"S": -1.0},  # Different but not checked
            swing_detector_version="v99",  # Different but not checked
            discretizer_version="99",  # Different but not checked
        )

        result = config_compatible(sample_log, expected)
        assert result is True  # Compatible because level_set and version match


# =============================================================================
# get_default_config Tests
# =============================================================================


class TestGetDefaultConfig:
    """Tests for get_default_config function."""

    def test_returns_config(self):
        """Test get_default_config returns a DiscretizationConfig."""
        config = get_default_config()
        assert isinstance(config, DiscretizationConfig)

    def test_has_level_set(self):
        """Test default config has level_set."""
        config = get_default_config()
        assert config.level_set is not None
        assert len(config.level_set) > 0

    def test_has_version(self):
        """Test default config has level_set_version."""
        config = get_default_config()
        assert config.level_set_version is not None
        assert config.level_set_version.startswith("v")

    def test_consistent_calls(self):
        """Test multiple calls return equivalent configs."""
        config1 = get_default_config()
        config2 = get_default_config()

        diffs = compare_configs_detail(config1, config2)
        assert diffs == []


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for I/O workflow."""

    def test_full_workflow(self, sample_log, tmp_path):
        """Test complete write-read-compare workflow."""
        # Write log
        path = tmp_path / "full_test.json"
        write_log(sample_log, path)

        # Read it back
        restored = read_log(path, warn_config_diff=False)

        # Verify round-trip
        original_dict = sample_log.to_dict()
        restored_dict = restored.to_dict()
        assert original_dict == restored_dict

    def test_multiple_logs_comparison(self, sample_log, tmp_path):
        """Test comparing multiple saved logs."""
        # Write first log
        path1 = tmp_path / "log1.json"
        write_log(sample_log, path1)

        # Create and write second log with different config
        config2 = DiscretizationConfig(
            level_set=sample_log.meta.config.level_set,
            level_set_version="v1.1",  # Different
            crossing_semantics=sample_log.meta.config.crossing_semantics,
            crossing_tolerance_pct=sample_log.meta.config.crossing_tolerance_pct,
            invalidation_thresholds=sample_log.meta.config.invalidation_thresholds,
            swing_detector_version=sample_log.meta.config.swing_detector_version,
            discretizer_version=sample_log.meta.config.discretizer_version,
        )
        meta2 = DiscretizationMeta(
            instrument="ES",
            source_resolution="1m",
            date_range_start="2024-02-01T00:00:00Z",
            date_range_end="2024-02-28T23:59:59Z",
            created_at="2024-03-01T12:00:00Z",
            config=config2,
        )
        log2 = DiscretizationLog(meta=meta2, swings=[], events=[])
        path2 = tmp_path / "log2.json"
        write_log(log2, path2)

        # Read both and compare
        loaded1 = read_log(path1, warn_config_diff=False)
        loaded2 = read_log(path2, warn_config_diff=False)

        diffs = compare_configs(loaded1, loaded2)
        assert len(diffs) == 1
        assert "level_set_version" in diffs[0]

    def test_empty_log_round_trip(self, sample_meta, tmp_path):
        """Test round-trip of empty log."""
        log = DiscretizationLog(meta=sample_meta, swings=[], events=[])

        path = tmp_path / "empty.json"
        write_log(log, path)
        restored = read_log(path, warn_config_diff=False)

        assert len(restored.swings) == 0
        assert len(restored.events) == 0
        assert restored.meta.instrument == "ES"
