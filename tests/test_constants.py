"""Tests for swing_analysis constants."""

import pytest
from src.swing_analysis.constants import (
    DISCRETIZATION_LEVELS,
    DISCRETIZATION_LEVEL_SET_VERSION,
)


class TestDiscretizationLevels:
    """Tests for DISCRETIZATION_LEVELS constant."""

    def test_is_list(self):
        """DISCRETIZATION_LEVELS should be a list."""
        assert isinstance(DISCRETIZATION_LEVELS, list)

    def test_contains_expected_count(self):
        """DISCRETIZATION_LEVELS should have 16 levels."""
        assert len(DISCRETIZATION_LEVELS) == 16

    def test_is_sorted_ascending(self):
        """DISCRETIZATION_LEVELS should be sorted in ascending order."""
        assert DISCRETIZATION_LEVELS == sorted(DISCRETIZATION_LEVELS)

    def test_all_floats(self):
        """All levels should be numeric."""
        for level in DISCRETIZATION_LEVELS:
            assert isinstance(level, (int, float))

    def test_includes_negative_levels(self):
        """Should include negative stop-run levels."""
        negative_levels = [l for l in DISCRETIZATION_LEVELS if l < 0]
        assert len(negative_levels) == 2
        assert -0.15 in DISCRETIZATION_LEVELS
        assert -0.10 in DISCRETIZATION_LEVELS

    def test_includes_key_fib_levels(self):
        """Should include key Fibonacci levels."""
        key_levels = [0.0, 0.382, 0.5, 0.618, 1.0, 1.618, 2.0]
        for level in key_levels:
            assert level in DISCRETIZATION_LEVELS

    def test_includes_extension_levels(self):
        """Should include extension levels beyond 1.0."""
        extension_levels = [l for l in DISCRETIZATION_LEVELS if l > 1.0]
        assert len(extension_levels) == 7  # 1.236, 1.382, 1.5, 1.618, 1.786, 2.0, 2.236

    def test_no_duplicates(self):
        """Should have no duplicate levels."""
        assert len(DISCRETIZATION_LEVELS) == len(set(DISCRETIZATION_LEVELS))


class TestDiscretizationLevelSetVersion:
    """Tests for DISCRETIZATION_LEVEL_SET_VERSION constant."""

    def test_is_string(self):
        """Version should be a string."""
        assert isinstance(DISCRETIZATION_LEVEL_SET_VERSION, str)

    def test_starts_with_v(self):
        """Version should start with 'v'."""
        assert DISCRETIZATION_LEVEL_SET_VERSION.startswith("v")

    def test_current_version(self):
        """Current version should be v1.0."""
        assert DISCRETIZATION_LEVEL_SET_VERSION == "v1.0"
