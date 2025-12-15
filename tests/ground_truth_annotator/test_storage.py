"""
Tests for annotation storage layer.

Tests versioned filenames, local timezone conversion, and session management.
"""

import tempfile
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.ground_truth_annotator.storage import (
    get_local_time,
    generate_timestamp_base,
    generate_final_filename,
    generate_inprogress_filename,
    sanitize_label,
    AnnotationStorage,
)


class TestLocalTimezone:
    """Test local timezone conversion."""

    def test_converts_utc_to_local(self):
        """Test that UTC datetime is converted to local time."""
        utc_dt = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        local_dt = get_local_time(utc_dt)

        # Verify it's different from UTC (unless we're in UTC timezone)
        # The local time should match what time.localtime gives us
        expected = time.localtime(utc_dt.timestamp())
        assert local_dt.hour == expected.tm_hour
        assert local_dt.minute == expected.tm_min

    def test_naive_datetime_treated_as_utc(self):
        """Test that naive datetime is treated as UTC."""
        naive_dt = datetime(2025, 1, 15, 12, 0)
        local_dt = get_local_time(naive_dt)

        # Should be same as converting UTC
        utc_dt = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        expected = get_local_time(utc_dt)
        assert local_dt == expected

    def test_preserves_minutes(self):
        """Test that minutes are preserved correctly."""
        utc_dt = datetime(2025, 6, 15, 12, 45, tzinfo=timezone.utc)
        local_dt = get_local_time(utc_dt)

        assert local_dt.minute == 45


class TestTimestampBase:
    """Test timestamp base generation."""

    def test_format_pattern(self):
        """Test timestamp base format matches expected pattern."""
        dt = datetime(2025, 12, 15, 16, 30)
        base = generate_timestamp_base(dt, use_local=False)

        # Should be yyyy-mmm-dd-HHmm format
        assert base == "2025-dec-15-1630"

    def test_zero_padded(self):
        """Test that single-digit values are zero-padded."""
        dt = datetime(2025, 1, 5, 8, 5)
        base = generate_timestamp_base(dt, use_local=False)

        assert base == "2025-jan-05-0805"

    def test_use_local_false(self):
        """Test timestamp without local conversion."""
        dt = datetime(2025, 12, 15, 16, 30)
        base = generate_timestamp_base(dt, use_local=False)

        assert base == "2025-dec-15-1630"

    def test_use_local_true_converts(self):
        """Test that use_local=True converts to local time."""
        utc_dt = datetime(2025, 12, 15, 12, 0, tzinfo=timezone.utc)
        base = generate_timestamp_base(utc_dt, use_local=True)

        # Verify the local conversion was applied
        local_dt = get_local_time(utc_dt)
        expected_base = f"{local_dt.year}-dec-{local_dt.day:02d}-{local_dt.hour:02d}{local_dt.minute:02d}"
        assert base == expected_base


class TestVersionedFilenames:
    """Test versioned filename generation."""

    def test_default_version(self):
        """Test default version 1 in filename."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt)

        # Should contain -ver1.json
        assert "-ver1.json" in filename
        assert filename.startswith("2025-dec-")

    def test_custom_version(self):
        """Test custom version number."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, version=3)

        assert "-ver3.json" in filename

    def test_with_label(self):
        """Test filename with label."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, label="test_session")

        assert "-ver1-test_session.json" in filename

    def test_with_label_and_version(self):
        """Test filename with both label and version."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, label="trending", version=2)

        assert "-ver2-trending.json" in filename


class TestInProgressFilename:
    """Test in-progress filename generation."""

    def test_format(self):
        """Test in-progress filename format."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_inprogress_filename(dt)

        # Should start with inprogress- and end with .json
        assert filename.startswith("inprogress-2025-dec-")
        assert filename.endswith(".json")


class TestSanitizeLabel:
    """Test label sanitization."""

    def test_spaces_replaced(self):
        """Test that spaces are replaced with underscores."""
        assert sanitize_label("my test") == "my_test"

    def test_lowercase(self):
        """Test that label is lowercased."""
        assert sanitize_label("MyTest") == "mytest"

    def test_special_chars_removed(self):
        """Test that special characters are removed."""
        assert sanitize_label("test@#$%") == "test"

    def test_hyphens_allowed(self):
        """Test that hyphens are preserved."""
        assert sanitize_label("my-test") == "my-test"

    def test_truncation(self):
        """Test that label is truncated to 50 chars."""
        long_label = "a" * 100
        assert len(sanitize_label(long_label)) == 50


class TestAnnotationStorageVersioning:
    """Test version auto-increment in storage."""

    def setup_method(self):
        """Create temp directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = AnnotationStorage(self.temp_dir)

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_next_version_empty(self):
        """Test version is 1 when no existing files."""
        version = self.storage._find_next_version("2025-dec-15-0830")
        assert version == 1

    def test_find_next_version_increment(self):
        """Test version increments when files exist."""
        # Create existing versioned file
        (Path(self.temp_dir) / "2025-dec-15-0830-ver1.json").write_text("{}")

        version = self.storage._find_next_version("2025-dec-15-0830")
        assert version == 2

    def test_find_next_version_gap(self):
        """Test version finds max and increments."""
        # Create files with gap
        (Path(self.temp_dir) / "2025-dec-15-0830-ver1.json").write_text("{}")
        (Path(self.temp_dir) / "2025-dec-15-0830-ver3.json").write_text("{}")

        version = self.storage._find_next_version("2025-dec-15-0830")
        assert version == 4

    def test_find_next_version_with_label(self):
        """Test version tracking with label."""
        # Create file without label
        (Path(self.temp_dir) / "2025-dec-15-0830-ver1.json").write_text("{}")
        # Create file with label
        (Path(self.temp_dir) / "2025-dec-15-0830-ver1-test.json").write_text("{}")

        # Without label should find ver1
        version_no_label = self.storage._find_next_version("2025-dec-15-0830")
        assert version_no_label == 2

        # With label should find ver1 (independent)
        version_with_label = self.storage._find_next_version("2025-dec-15-0830", "test")
        assert version_with_label == 2

    def test_finalize_creates_versioned_file(self):
        """Test that finalization creates properly versioned filename."""
        session = self.storage.create_session(
            data_file="test.csv",
            resolution="5m",
            window_size=1000
        )

        filename, path_id = self.storage.finalize_session(
            session_id=session.session_id,
            status="keep"
        )

        assert "-ver1.json" in filename
        assert "-ver1" in path_id
        assert (Path(self.temp_dir) / filename).exists()
