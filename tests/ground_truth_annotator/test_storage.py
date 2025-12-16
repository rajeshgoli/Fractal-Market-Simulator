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
from src.ground_truth_annotator.models import REVIEW_SCHEMA_VERSION


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
    """Test versioned filename generation with schema version."""

    def test_uses_schema_version(self):
        """Test that filename uses REVIEW_SCHEMA_VERSION."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt)

        # Should contain schema version (currently ver2)
        assert f"-ver{REVIEW_SCHEMA_VERSION}.json" in filename
        assert filename.startswith("2025-dec-")

    def test_collision_number_adds_try_suffix(self):
        """Test collision handling adds -try<N> suffix."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, collision_number=2)

        assert f"-ver{REVIEW_SCHEMA_VERSION}-try2.json" in filename

    def test_with_label(self):
        """Test filename with label uses schema version."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, label="test_session")

        assert f"-ver{REVIEW_SCHEMA_VERSION}-test_session.json" in filename

    def test_with_label_and_collision(self):
        """Test filename with label and collision handling."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, label="trending", collision_number=3)

        assert f"-ver{REVIEW_SCHEMA_VERSION}-trending-try3.json" in filename

    def test_no_collision_no_try_suffix(self):
        """Test that collision_number=0 produces no -try suffix."""
        dt = datetime(2025, 12, 15, 16, 30)
        filename = generate_final_filename(dt, collision_number=0)

        assert "-try" not in filename
        assert f"-ver{REVIEW_SCHEMA_VERSION}.json" in filename


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


class TestAnnotationStorageCollision:
    """Test collision detection for schema-versioned filenames."""

    def setup_method(self):
        """Create temp directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = AnnotationStorage(
            storage_dir=self.temp_dir,
            ground_truth_dir=self.temp_dir
        )

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_collision_returns_zero(self):
        """Test returns 0 when no existing file with schema version."""
        collision = self.storage._find_collision_number("2025-dec-15-0830")
        assert collision == 0

    def test_collision_returns_try_number(self):
        """Test returns try number when base file exists."""
        # Create existing file with schema version
        base_file = f"2025-dec-15-0830-ver{REVIEW_SCHEMA_VERSION}.json"
        (Path(self.temp_dir) / base_file).write_text("{}")

        collision = self.storage._find_collision_number("2025-dec-15-0830")
        assert collision == 2  # First try after base

    def test_finds_max_try_number(self):
        """Test finds highest try number and increments."""
        # Create base file and some try files
        base_file = f"2025-dec-15-0830-ver{REVIEW_SCHEMA_VERSION}.json"
        try2_file = f"2025-dec-15-0830-ver{REVIEW_SCHEMA_VERSION}-try2.json"
        try4_file = f"2025-dec-15-0830-ver{REVIEW_SCHEMA_VERSION}-try4.json"
        (Path(self.temp_dir) / base_file).write_text("{}")
        (Path(self.temp_dir) / try2_file).write_text("{}")
        (Path(self.temp_dir) / try4_file).write_text("{}")

        collision = self.storage._find_collision_number("2025-dec-15-0830")
        assert collision == 5  # Next after try4

    def test_collision_with_label(self):
        """Test collision detection with label."""
        # Create base file with label
        base_file = f"2025-dec-15-0830-ver{REVIEW_SCHEMA_VERSION}-test.json"
        (Path(self.temp_dir) / base_file).write_text("{}")

        collision = self.storage._find_collision_number("2025-dec-15-0830", "test")
        assert collision == 2

    def test_label_collision_independent(self):
        """Test that collision is tracked independently per label."""
        # Create file without label
        no_label_file = f"2025-dec-15-0830-ver{REVIEW_SCHEMA_VERSION}.json"
        (Path(self.temp_dir) / no_label_file).write_text("{}")

        # File with label should have no collision
        collision = self.storage._find_collision_number("2025-dec-15-0830", "test")
        assert collision == 0  # No collision for labeled file

    def test_finalize_appends_to_ground_truth(self):
        """Test that finalization appends session to ground_truth.json."""
        session = self.storage.create_session(
            data_file="test.csv",
            resolution="5m",
            window_size=1000
        )

        filename, path_id = self.storage.finalize_session(
            session_id=session.session_id,
            status="keep"
        )

        # Verify filename format
        assert f"-ver{REVIEW_SCHEMA_VERSION}.json" in filename
        assert f"-ver{REVIEW_SCHEMA_VERSION}" in path_id
        assert "-try" not in filename  # No collision

        # Verify working file is deleted
        working_files = list(Path(self.temp_dir).glob("inprogress-*.json"))
        assert len(working_files) == 0

        # Verify data is appended to ground_truth.json
        ground_truth_file = Path(self.temp_dir) / "ground_truth.json"
        assert ground_truth_file.exists()

        import json
        with open(ground_truth_file, 'r') as f:
            ground_truth = json.load(f)

        assert "sessions" in ground_truth
        assert len(ground_truth["sessions"]) == 1
        assert ground_truth["sessions"][0]["original_filename"] == path_id
        assert ground_truth["sessions"][0]["session"]["session_id"] == session.session_id
