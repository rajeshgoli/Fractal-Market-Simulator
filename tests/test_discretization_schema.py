"""
Unit tests for discretization schema.

Tests serialization round-trips, validation, and edge cases.
"""

import pytest
from datetime import datetime, timezone

from src.discretization.schema import (
    DiscretizationConfig,
    DiscretizationMeta,
    EffortAnnotation,
    ShockAnnotation,
    ParentContext,
    SwingEntry,
    DiscretizationEvent,
    DiscretizationLog,
    EventType,
    validate_log,
    SCHEMA_VERSION,
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
def sample_effort():
    """Create a sample EffortAnnotation."""
    return EffortAnnotation(
        dwell_bars=15,
        test_count=3,
        max_probe_r=0.395,
    )


@pytest.fixture
def sample_shock():
    """Create a sample ShockAnnotation."""
    return ShockAnnotation(
        levels_jumped=3,
        range_multiple=2.5,
        gap_multiple=1.8,
        is_gap=True,
    )


@pytest.fixture
def sample_parent_context():
    """Create a sample ParentContext."""
    return ParentContext(
        scale="XL",
        swing_id="swing-xl-001",
        band="1.382-1.5",
        direction="BULL",
        ratio=1.42,
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
        terminated_at_bar=None,
        termination_reason=None,
    )


@pytest.fixture
def sample_event(sample_effort, sample_shock, sample_parent_context):
    """Create a sample DiscretizationEvent with all side-channels."""
    return DiscretizationEvent(
        bar=120,
        timestamp="2024-01-15T14:30:00Z",
        swing_id="swing-l-001",
        event_type=EventType.LEVEL_CROSS,
        data={
            "from_ratio": 0.382,
            "to_ratio": 0.5,
            "level_crossed": 0.5,
            "direction": "UP",
        },
        effort=sample_effort,
        shock=sample_shock,
        parent_context=sample_parent_context,
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
# DiscretizationConfig Tests
# =============================================================================


class TestDiscretizationConfig:
    """Tests for DiscretizationConfig."""

    def test_to_dict(self, sample_config):
        """Test serialization to dict."""
        d = sample_config.to_dict()

        assert d["level_set"] == sample_config.level_set
        assert d["level_set_version"] == "v1.0"
        assert d["crossing_semantics"] == "close_cross"
        assert d["crossing_tolerance_pct"] == 0.001
        assert d["invalidation_thresholds"]["XL"] == -0.15
        assert d["swing_detector_version"] == "v2.3"
        assert d["discretizer_version"] == "1.0"

    def test_from_dict(self, sample_config):
        """Test deserialization from dict."""
        d = sample_config.to_dict()
        restored = DiscretizationConfig.from_dict(d)

        assert restored.level_set == sample_config.level_set
        assert restored.level_set_version == sample_config.level_set_version
        assert restored.crossing_semantics == sample_config.crossing_semantics
        assert restored.crossing_tolerance_pct == sample_config.crossing_tolerance_pct
        assert restored.invalidation_thresholds == sample_config.invalidation_thresholds
        assert restored.swing_detector_version == sample_config.swing_detector_version
        assert restored.discretizer_version == sample_config.discretizer_version

    def test_round_trip(self, sample_config):
        """Test serialization round-trip."""
        d = sample_config.to_dict()
        restored = DiscretizationConfig.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2


# =============================================================================
# DiscretizationMeta Tests
# =============================================================================


class TestDiscretizationMeta:
    """Tests for DiscretizationMeta."""

    def test_to_dict(self, sample_meta):
        """Test serialization to dict."""
        d = sample_meta.to_dict()

        assert d["instrument"] == "ES"
        assert d["source_resolution"] == "1m"
        assert d["date_range_start"] == "2024-01-01T00:00:00Z"
        assert d["date_range_end"] == "2024-01-31T23:59:59Z"
        assert d["created_at"] == "2024-02-01T12:00:00Z"
        assert "config" in d
        assert d["config"]["level_set_version"] == "v1.0"

    def test_from_dict(self, sample_meta):
        """Test deserialization from dict."""
        d = sample_meta.to_dict()
        restored = DiscretizationMeta.from_dict(d)

        assert restored.instrument == sample_meta.instrument
        assert restored.source_resolution == sample_meta.source_resolution
        assert restored.date_range_start == sample_meta.date_range_start
        assert restored.date_range_end == sample_meta.date_range_end
        assert restored.config.level_set_version == sample_meta.config.level_set_version

    def test_round_trip(self, sample_meta):
        """Test serialization round-trip."""
        d = sample_meta.to_dict()
        restored = DiscretizationMeta.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2


# =============================================================================
# EffortAnnotation Tests
# =============================================================================


class TestEffortAnnotation:
    """Tests for EffortAnnotation."""

    def test_to_dict(self, sample_effort):
        """Test serialization to dict."""
        d = sample_effort.to_dict()

        assert d["dwell_bars"] == 15
        assert d["test_count"] == 3
        assert d["max_probe_r"] == 0.395

    def test_from_dict(self, sample_effort):
        """Test deserialization from dict."""
        d = sample_effort.to_dict()
        restored = EffortAnnotation.from_dict(d)

        assert restored.dwell_bars == sample_effort.dwell_bars
        assert restored.test_count == sample_effort.test_count
        assert restored.max_probe_r == sample_effort.max_probe_r

    def test_round_trip(self, sample_effort):
        """Test serialization round-trip."""
        d = sample_effort.to_dict()
        restored = EffortAnnotation.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2

    def test_optional_max_probe_r(self):
        """Test with None max_probe_r."""
        effort = EffortAnnotation(dwell_bars=10, test_count=2, max_probe_r=None)
        d = effort.to_dict()
        restored = EffortAnnotation.from_dict(d)

        assert restored.max_probe_r is None


# =============================================================================
# ShockAnnotation Tests
# =============================================================================


class TestShockAnnotation:
    """Tests for ShockAnnotation."""

    def test_to_dict(self, sample_shock):
        """Test serialization to dict."""
        d = sample_shock.to_dict()

        assert d["levels_jumped"] == 3
        assert d["range_multiple"] == 2.5
        assert d["gap_multiple"] == 1.8
        assert d["is_gap"] is True

    def test_from_dict(self, sample_shock):
        """Test deserialization from dict."""
        d = sample_shock.to_dict()
        restored = ShockAnnotation.from_dict(d)

        assert restored.levels_jumped == sample_shock.levels_jumped
        assert restored.range_multiple == sample_shock.range_multiple
        assert restored.gap_multiple == sample_shock.gap_multiple
        assert restored.is_gap == sample_shock.is_gap

    def test_round_trip(self, sample_shock):
        """Test serialization round-trip."""
        d = sample_shock.to_dict()
        restored = ShockAnnotation.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2

    def test_optional_gap_fields(self):
        """Test with None gap fields."""
        shock = ShockAnnotation(levels_jumped=1, range_multiple=1.2)
        d = shock.to_dict()
        restored = ShockAnnotation.from_dict(d)

        assert restored.gap_multiple is None
        assert restored.is_gap is False


# =============================================================================
# ParentContext Tests
# =============================================================================


class TestParentContext:
    """Tests for ParentContext."""

    def test_to_dict(self, sample_parent_context):
        """Test serialization to dict."""
        d = sample_parent_context.to_dict()

        assert d["scale"] == "XL"
        assert d["swing_id"] == "swing-xl-001"
        assert d["band"] == "1.382-1.5"
        assert d["direction"] == "BULL"
        assert d["ratio"] == 1.42

    def test_from_dict(self, sample_parent_context):
        """Test deserialization from dict."""
        d = sample_parent_context.to_dict()
        restored = ParentContext.from_dict(d)

        assert restored.scale == sample_parent_context.scale
        assert restored.swing_id == sample_parent_context.swing_id
        assert restored.band == sample_parent_context.band
        assert restored.direction == sample_parent_context.direction
        assert restored.ratio == sample_parent_context.ratio

    def test_round_trip(self, sample_parent_context):
        """Test serialization round-trip."""
        d = sample_parent_context.to_dict()
        restored = ParentContext.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2


# =============================================================================
# SwingEntry Tests
# =============================================================================


class TestSwingEntry:
    """Tests for SwingEntry."""

    def test_to_dict(self, sample_swing_entry):
        """Test serialization to dict."""
        d = sample_swing_entry.to_dict()

        assert d["swing_id"] == "swing-l-001"
        assert d["scale"] == "L"
        assert d["direction"] == "BULL"
        assert d["anchor0"] == 5000.0
        assert d["anchor1"] == 5100.0
        assert d["anchor0_bar"] == 100
        assert d["anchor1_bar"] == 50
        assert d["formed_at_bar"] == 110
        assert d["status"] == "active"
        assert d["terminated_at_bar"] is None
        assert d["termination_reason"] is None

    def test_from_dict(self, sample_swing_entry):
        """Test deserialization from dict."""
        d = sample_swing_entry.to_dict()
        restored = SwingEntry.from_dict(d)

        assert restored.swing_id == sample_swing_entry.swing_id
        assert restored.scale == sample_swing_entry.scale
        assert restored.direction == sample_swing_entry.direction
        assert restored.anchor0 == sample_swing_entry.anchor0
        assert restored.anchor1 == sample_swing_entry.anchor1
        assert restored.status == sample_swing_entry.status

    def test_round_trip(self, sample_swing_entry):
        """Test serialization round-trip."""
        d = sample_swing_entry.to_dict()
        restored = SwingEntry.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2

    def test_terminated_swing(self):
        """Test swing with termination data."""
        swing = SwingEntry(
            swing_id="swing-m-002",
            scale="M",
            direction="BEAR",
            anchor0=5200.0,
            anchor1=5100.0,
            anchor0_bar=200,
            anchor1_bar=180,
            formed_at_bar=210,
            status="completed",
            terminated_at_bar=250,
            termination_reason="COMPLETION",
        )
        d = swing.to_dict()
        restored = SwingEntry.from_dict(d)

        assert restored.status == "completed"
        assert restored.terminated_at_bar == 250
        assert restored.termination_reason == "COMPLETION"


# =============================================================================
# DiscretizationEvent Tests
# =============================================================================


class TestDiscretizationEvent:
    """Tests for DiscretizationEvent."""

    def test_to_dict_full(self, sample_event):
        """Test serialization with all side-channels."""
        d = sample_event.to_dict()

        assert d["bar"] == 120
        assert d["timestamp"] == "2024-01-15T14:30:00Z"
        assert d["swing_id"] == "swing-l-001"
        assert d["event_type"] == "LEVEL_CROSS"
        assert d["data"]["from_ratio"] == 0.382
        assert "effort" in d
        assert d["effort"]["dwell_bars"] == 15
        assert "shock" in d
        assert d["shock"]["levels_jumped"] == 3
        assert "parent_context" in d
        assert d["parent_context"]["scale"] == "XL"

    def test_from_dict_full(self, sample_event):
        """Test deserialization with all side-channels."""
        d = sample_event.to_dict()
        restored = DiscretizationEvent.from_dict(d)

        assert restored.bar == sample_event.bar
        assert restored.timestamp == sample_event.timestamp
        assert restored.swing_id == sample_event.swing_id
        assert restored.event_type == EventType.LEVEL_CROSS
        assert restored.data == sample_event.data
        assert restored.effort is not None
        assert restored.effort.dwell_bars == 15
        assert restored.shock is not None
        assert restored.shock.levels_jumped == 3
        assert restored.parent_context is not None
        assert restored.parent_context.scale == "XL"

    def test_round_trip(self, sample_event):
        """Test serialization round-trip."""
        d = sample_event.to_dict()
        restored = DiscretizationEvent.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2

    def test_minimal_event(self):
        """Test event without optional side-channels."""
        event = DiscretizationEvent(
            bar=50,
            timestamp="2024-01-10T10:00:00Z",
            swing_id="swing-s-001",
            event_type=EventType.SWING_FORMED,
            data={"swing_id": "swing-s-001", "scale": "S", "direction": "BULL"},
        )
        d = event.to_dict()

        assert "effort" not in d
        assert "shock" not in d
        assert "parent_context" not in d

        restored = DiscretizationEvent.from_dict(d)
        assert restored.effort is None
        assert restored.shock is None
        assert restored.parent_context is None

    def test_all_event_types(self):
        """Test serialization of all event types."""
        for event_type in EventType:
            event = DiscretizationEvent(
                bar=100,
                timestamp="2024-01-20T12:00:00Z",
                swing_id="swing-test",
                event_type=event_type,
                data={"test": True},
            )
            d = event.to_dict()
            restored = DiscretizationEvent.from_dict(d)

            assert restored.event_type == event_type


# =============================================================================
# DiscretizationLog Tests
# =============================================================================


class TestDiscretizationLog:
    """Tests for DiscretizationLog."""

    def test_to_dict(self, sample_log):
        """Test serialization to dict."""
        d = sample_log.to_dict()

        assert d["schema_version"] == SCHEMA_VERSION
        assert "meta" in d
        assert d["meta"]["instrument"] == "ES"
        assert len(d["swings"]) == 1
        assert d["swings"][0]["swing_id"] == "swing-l-001"
        assert len(d["events"]) == 1
        assert d["events"][0]["bar"] == 120

    def test_from_dict(self, sample_log):
        """Test deserialization from dict."""
        d = sample_log.to_dict()
        restored = DiscretizationLog.from_dict(d)

        assert restored.meta.instrument == sample_log.meta.instrument
        assert len(restored.swings) == len(sample_log.swings)
        assert len(restored.events) == len(sample_log.events)

    def test_round_trip(self, sample_log):
        """Test serialization round-trip."""
        d = sample_log.to_dict()
        restored = DiscretizationLog.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2

    def test_empty_log(self, sample_meta):
        """Test log with no swings or events."""
        log = DiscretizationLog(meta=sample_meta, swings=[], events=[])
        d = log.to_dict()
        restored = DiscretizationLog.from_dict(d)

        assert len(restored.swings) == 0
        assert len(restored.events) == 0


# =============================================================================
# Validation Tests
# =============================================================================


class TestValidation:
    """Tests for validate_log function."""

    def test_valid_log(self, sample_log):
        """Test validation of a valid log."""
        errors = validate_log(sample_log)
        assert len(errors) == 0

    def test_missing_swing_reference(self, sample_meta):
        """Test validation catches missing swing reference."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="active",
        )
        event = DiscretizationEvent(
            bar=120,
            timestamp="2024-01-15T14:30:00Z",
            swing_id="nonexistent-swing",  # Bad reference
            event_type=EventType.LEVEL_CROSS,
            data={
                "from_ratio": 0.382,
                "to_ratio": 0.5,
                "level_crossed": 0.5,
                "direction": "UP",
            },
        )
        log = DiscretizationLog(meta=sample_meta, swings=[swing], events=[event])

        errors = validate_log(log)
        assert len(errors) == 1
        assert "unknown swing_id" in errors[0]

    def test_unordered_events(self, sample_meta):
        """Test validation catches unordered events."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="active",
        )
        event1 = DiscretizationEvent(
            bar=120,
            timestamp="2024-01-15T14:30:00Z",
            swing_id="swing-001",
            event_type=EventType.LEVEL_CROSS,
            data={"from_ratio": 0.382, "to_ratio": 0.5, "level_crossed": 0.5, "direction": "UP"},
        )
        event2 = DiscretizationEvent(
            bar=100,  # Earlier bar than event1
            timestamp="2024-01-15T14:00:00Z",
            swing_id="swing-001",
            event_type=EventType.LEVEL_CROSS,
            data={"from_ratio": 0.0, "to_ratio": 0.382, "level_crossed": 0.382, "direction": "UP"},
        )
        log = DiscretizationLog(
            meta=sample_meta,
            swings=[swing],
            events=[event1, event2],  # Out of order
        )

        errors = validate_log(log)
        assert len(errors) == 1
        assert "not ordered" in errors[0]

    def test_empty_level_set(self, sample_meta):
        """Test validation catches empty level_set."""
        sample_meta.config.level_set = []
        log = DiscretizationLog(meta=sample_meta, swings=[], events=[])

        errors = validate_log(log)
        assert any("level_set is empty" in e for e in errors)

    def test_level_cross_missing_fields(self, sample_meta):
        """Test validation catches missing LEVEL_CROSS fields."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="active",
        )
        event = DiscretizationEvent(
            bar=120,
            timestamp="2024-01-15T14:30:00Z",
            swing_id="swing-001",
            event_type=EventType.LEVEL_CROSS,
            data={"from_ratio": 0.382},  # Missing to_ratio, level_crossed, direction
        )
        log = DiscretizationLog(meta=sample_meta, swings=[swing], events=[event])

        errors = validate_log(log)
        assert len(errors) >= 1
        assert any("to_ratio" in e for e in errors)

    def test_completion_missing_ratio(self, sample_meta):
        """Test validation catches missing COMPLETION ratio."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="active",
        )
        event = DiscretizationEvent(
            bar=200,
            timestamp="2024-01-16T10:00:00Z",
            swing_id="swing-001",
            event_type=EventType.COMPLETION,
            data={},  # Missing completion_ratio
        )
        log = DiscretizationLog(meta=sample_meta, swings=[swing], events=[event])

        errors = validate_log(log)
        assert any("completion_ratio" in e for e in errors)

    def test_invalidation_missing_fields(self, sample_meta):
        """Test validation catches missing INVALIDATION fields."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="active",
        )
        event = DiscretizationEvent(
            bar=150,
            timestamp="2024-01-15T16:00:00Z",
            swing_id="swing-001",
            event_type=EventType.INVALIDATION,
            data={"invalidation_ratio": -0.12},  # Missing threshold
        )
        log = DiscretizationLog(meta=sample_meta, swings=[swing], events=[event])

        errors = validate_log(log)
        assert any("threshold" in e for e in errors)

    def test_swing_terminated_invalid_type(self, sample_meta):
        """Test validation catches invalid termination_type."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="completed",
        )
        event = DiscretizationEvent(
            bar=200,
            timestamp="2024-01-16T10:00:00Z",
            swing_id="swing-001",
            event_type=EventType.SWING_TERMINATED,
            data={"termination_type": "INVALID_TYPE"},  # Bad value
        )
        log = DiscretizationLog(meta=sample_meta, swings=[swing], events=[event])

        errors = validate_log(log)
        assert any("termination_type" in e for e in errors)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and corner cases."""

    def test_multiple_swings_same_scale(self, sample_meta):
        """Test log with multiple swings of same scale."""
        swings = [
            SwingEntry(
                swing_id=f"swing-{i}",
                scale="L",
                direction="BULL" if i % 2 == 0 else "BEAR",
                anchor0=5000.0 + i * 50,
                anchor1=5100.0 + i * 50,
                anchor0_bar=100 + i * 10,
                anchor1_bar=50 + i * 10,
                formed_at_bar=110 + i * 10,
                status="active",
            )
            for i in range(5)
        ]
        log = DiscretizationLog(meta=sample_meta, swings=swings, events=[])
        d = log.to_dict()
        restored = DiscretizationLog.from_dict(d)

        assert len(restored.swings) == 5

    def test_event_with_all_side_channels(
        self, sample_meta, sample_effort, sample_shock, sample_parent_context
    ):
        """Test event with all three side-channels populated."""
        swing = SwingEntry(
            swing_id="swing-001",
            scale="L",
            direction="BULL",
            anchor0=5000.0,
            anchor1=5100.0,
            anchor0_bar=100,
            anchor1_bar=50,
            formed_at_bar=110,
            status="active",
        )
        event = DiscretizationEvent(
            bar=120,
            timestamp="2024-01-15T14:30:00Z",
            swing_id="swing-001",
            event_type=EventType.LEVEL_CROSS,
            data={
                "from_ratio": 0.382,
                "to_ratio": 0.5,
                "level_crossed": 0.5,
                "direction": "UP",
            },
            effort=sample_effort,
            shock=sample_shock,
            parent_context=sample_parent_context,
        )
        log = DiscretizationLog(meta=sample_meta, swings=[swing], events=[event])

        d = log.to_dict()
        restored = DiscretizationLog.from_dict(d)

        assert restored.events[0].effort is not None
        assert restored.events[0].shock is not None
        assert restored.events[0].parent_context is not None

    def test_large_log(self, sample_meta):
        """Test log with many events."""
        swings = [
            SwingEntry(
                swing_id="swing-001",
                scale="L",
                direction="BULL",
                anchor0=5000.0,
                anchor1=5100.0,
                anchor0_bar=100,
                anchor1_bar=50,
                formed_at_bar=110,
                status="active",
            )
        ]
        events = [
            DiscretizationEvent(
                bar=110 + i,
                timestamp=f"2024-01-15T14:{i:02d}:00Z",
                swing_id="swing-001",
                event_type=EventType.LEVEL_CROSS,
                data={
                    "from_ratio": 0.382,
                    "to_ratio": 0.5,
                    "level_crossed": 0.5,
                    "direction": "UP",
                },
            )
            for i in range(100)
        ]
        log = DiscretizationLog(meta=sample_meta, swings=swings, events=events)

        d = log.to_dict()
        restored = DiscretizationLog.from_dict(d)

        assert len(restored.events) == 100
        errors = validate_log(restored)
        assert len(errors) == 0

    def test_negative_invalidation_thresholds(self, sample_config):
        """Test config with various negative thresholds."""
        sample_config.invalidation_thresholds = {
            "S": -0.05,
            "M": -0.10,
            "L": -0.15,
            "XL": -0.20,
        }
        d = sample_config.to_dict()
        restored = DiscretizationConfig.from_dict(d)

        assert restored.invalidation_thresholds["S"] == -0.05
        assert restored.invalidation_thresholds["XL"] == -0.20
