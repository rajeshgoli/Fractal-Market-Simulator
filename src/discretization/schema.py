"""
Discretization Event Schema

Defines the canonical event schema for discretization output. The schema
is parseable, ordered, comprehensive, and includes side-channels for
effort/shock measurement and cross-scale analysis.

Design Principle: "Log everything; filter later. Don't embed assumptions
about what matters into the discretizer."
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


# Schema version for backward-compatible evolution
# v1.0: Initial schema with side-channels
SCHEMA_VERSION = "1.0"


class EventType(str, Enum):
    """Types of discretization events."""
    LEVEL_CROSS = "LEVEL_CROSS"           # Price crossed a Fib level
    LEVEL_TEST = "LEVEL_TEST"             # Price approached but didn't cross
    COMPLETION = "COMPLETION"             # Ratio crossed 2.0
    INVALIDATION = "INVALIDATION"         # Ratio crossed below threshold
    SWING_FORMED = "SWING_FORMED"         # New swing detected at scale
    SWING_TERMINATED = "SWING_TERMINATED" # Swing ended


# =============================================================================
# Configuration (for corpus comparability)
# =============================================================================


@dataclass
class DiscretizationConfig:
    """
    Configuration used to produce a discretization log.

    Recorded in metadata so different runs remain comparable.
    Enables corpus-wide analysis with known parameters.
    """
    level_set: List[float]                    # Actual levels used
    level_set_version: str                    # e.g., "v1.0"
    crossing_semantics: Literal["close_cross", "open_close_cross", "wick_touch"]
    crossing_tolerance_pct: float             # e.g., 0.001 (0.1% of swing size)
    invalidation_thresholds: Dict[str, float] # e.g., {"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15}
    swing_detector_version: str               # e.g., "v2.3" - links to detection config
    discretizer_version: str                  # e.g., "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "level_set": self.level_set,
            "level_set_version": self.level_set_version,
            "crossing_semantics": self.crossing_semantics,
            "crossing_tolerance_pct": self.crossing_tolerance_pct,
            "invalidation_thresholds": self.invalidation_thresholds,
            "swing_detector_version": self.swing_detector_version,
            "discretizer_version": self.discretizer_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscretizationConfig":
        """Deserialize from dictionary."""
        return cls(
            level_set=data["level_set"],
            level_set_version=data["level_set_version"],
            crossing_semantics=data["crossing_semantics"],
            crossing_tolerance_pct=data["crossing_tolerance_pct"],
            invalidation_thresholds=data["invalidation_thresholds"],
            swing_detector_version=data["swing_detector_version"],
            discretizer_version=data["discretizer_version"],
        )


# =============================================================================
# Metadata
# =============================================================================


@dataclass
class DiscretizationMeta:
    """
    Log metadata for provenance and reproducibility.

    Contains full configuration so logs are self-describing
    and can be compared across different runs.
    """
    instrument: str                           # e.g., "ES"
    source_resolution: str                    # e.g., "1m"
    date_range_start: str                     # ISO 8601
    date_range_end: str                       # ISO 8601
    created_at: str                           # ISO 8601
    config: DiscretizationConfig              # Full config for reproducibility

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "instrument": self.instrument,
            "source_resolution": self.source_resolution,
            "date_range_start": self.date_range_start,
            "date_range_end": self.date_range_end,
            "created_at": self.created_at,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscretizationMeta":
        """Deserialize from dictionary."""
        return cls(
            instrument=data["instrument"],
            source_resolution=data["source_resolution"],
            date_range_start=data["date_range_start"],
            date_range_end=data["date_range_end"],
            created_at=data["created_at"],
            config=DiscretizationConfig.from_dict(data["config"]),
        )


# =============================================================================
# Side-Channels
# =============================================================================


@dataclass
class EffortAnnotation:
    """
    Wyckoff-style effort measurement (attached to LEVEL_CROSS events).

    Captures "effort vs result" dynamics:
    - dwell_bars: How long price worked the previous band
    - test_count: How many approach/retreat patterns before crossing
    - max_probe_r: Deepest excursion past level before success
    """
    dwell_bars: int                           # Bars spent in previous band before transition
    test_count: int                           # Approach-retreat patterns at boundary
    max_probe_r: Optional[float] = None       # Deepest ratio excursion past level before reject

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "dwell_bars": self.dwell_bars,
            "test_count": self.test_count,
            "max_probe_r": self.max_probe_r,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EffortAnnotation":
        """Deserialize from dictionary."""
        return cls(
            dwell_bars=data["dwell_bars"],
            test_count=data["test_count"],
            max_probe_r=data.get("max_probe_r"),
        )


@dataclass
class ShockAnnotation:
    """
    Tail/impulsive behavior measurement (attached to LEVEL_CROSS events).

    Captures outlier price action:
    - levels_jumped: Count of levels crossed in one bar (multi-level jump)
    - range_multiple: Bar range relative to rolling median
    - gap_multiple: Gap size relative to rolling median
    - is_gap: Flag for session boundary gaps
    """
    levels_jumped: int                        # Fib boundaries crossed in one bar
    range_multiple: float                     # (high-low) / rolling_median_range
    gap_multiple: Optional[float] = None      # Gap size / rolling_median_range
    is_gap: bool = False                      # True if transition includes session gap

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "levels_jumped": self.levels_jumped,
            "range_multiple": self.range_multiple,
            "gap_multiple": self.gap_multiple,
            "is_gap": self.is_gap,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShockAnnotation":
        """Deserialize from dictionary."""
        return cls(
            levels_jumped=data["levels_jumped"],
            range_multiple=data["range_multiple"],
            gap_multiple=data.get("gap_multiple"),
            is_gap=data.get("is_gap", False),
        )


@dataclass
class ParentContext:
    """
    Snapshot of parent-scale state at event time.

    Enables post-hoc cross-scale analysis without encoding
    coupling rules into the discretizer. Allows queries like
    "L events when XL is in 1.382-1.5 band".
    """
    scale: str                                # Parent scale: "XL", "L", "M"
    swing_id: str
    band: str                                 # e.g., "1.382-1.5"
    direction: Literal["BULL", "BEAR"]
    ratio: float                              # Exact ratio position at event time

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "scale": self.scale,
            "swing_id": self.swing_id,
            "band": self.band,
            "direction": self.direction,
            "ratio": self.ratio,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParentContext":
        """Deserialize from dictionary."""
        return cls(
            scale=data["scale"],
            swing_id=data["swing_id"],
            band=data["band"],
            direction=data["direction"],
            ratio=data["ratio"],
        )


# =============================================================================
# Core Schema
# =============================================================================


@dataclass
class SwingEntry:
    """
    Reference swing registered in the log.

    Tracks the lifecycle of a swing from formation to termination.
    """
    swing_id: str
    scale: Literal["XL", "L", "M", "S"]
    direction: Literal["BULL", "BEAR"]
    anchor0: float                            # Defended pivot (low for bull, high for bear)
    anchor1: float                            # Origin extremum
    anchor0_bar: int
    anchor1_bar: int
    formed_at_bar: int
    status: Literal["active", "completed", "invalidated"]
    terminated_at_bar: Optional[int] = None
    termination_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "swing_id": self.swing_id,
            "scale": self.scale,
            "direction": self.direction,
            "anchor0": self.anchor0,
            "anchor1": self.anchor1,
            "anchor0_bar": self.anchor0_bar,
            "anchor1_bar": self.anchor1_bar,
            "formed_at_bar": self.formed_at_bar,
            "status": self.status,
            "terminated_at_bar": self.terminated_at_bar,
            "termination_reason": self.termination_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SwingEntry":
        """Deserialize from dictionary."""
        return cls(
            swing_id=data["swing_id"],
            scale=data["scale"],
            direction=data["direction"],
            anchor0=data["anchor0"],
            anchor1=data["anchor1"],
            anchor0_bar=data["anchor0_bar"],
            anchor1_bar=data["anchor1_bar"],
            formed_at_bar=data["formed_at_bar"],
            status=data["status"],
            terminated_at_bar=data.get("terminated_at_bar"),
            termination_reason=data.get("termination_reason"),
        )


@dataclass
class DiscretizationEvent:
    """
    A single structural event in the log.

    Events are ordered by bar index and represent discrete
    structural changes in price behavior relative to active swings.
    """
    bar: int                                  # Source bar index
    timestamp: str                            # ISO 8601
    swing_id: str                             # Reference to SwingEntry
    event_type: EventType
    data: Dict[str, Any]                      # Event-type-specific fields

    # Side-channels (optional, populated where applicable)
    effort: Optional[EffortAnnotation] = None
    shock: Optional[ShockAnnotation] = None
    parent_context: Optional[ParentContext] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        result: Dict[str, Any] = {
            "bar": self.bar,
            "timestamp": self.timestamp,
            "swing_id": self.swing_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "data": self.data,
        }
        if self.effort is not None:
            result["effort"] = self.effort.to_dict()
        if self.shock is not None:
            result["shock"] = self.shock.to_dict()
        if self.parent_context is not None:
            result["parent_context"] = self.parent_context.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscretizationEvent":
        """Deserialize from dictionary."""
        effort = None
        if data.get("effort"):
            effort = EffortAnnotation.from_dict(data["effort"])

        shock = None
        if data.get("shock"):
            shock = ShockAnnotation.from_dict(data["shock"])

        parent_context = None
        if data.get("parent_context"):
            parent_context = ParentContext.from_dict(data["parent_context"])

        return cls(
            bar=data["bar"],
            timestamp=data["timestamp"],
            swing_id=data["swing_id"],
            event_type=EventType(data["event_type"]),
            data=data["data"],
            effort=effort,
            shock=shock,
            parent_context=parent_context,
        )


@dataclass
class DiscretizationLog:
    """
    Complete discretization output for a corpus segment.

    Contains metadata, all registered swings, and all events.
    Self-describing via embedded configuration.
    """
    meta: DiscretizationMeta
    swings: List[SwingEntry] = field(default_factory=list)
    events: List[DiscretizationEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "schema_version": SCHEMA_VERSION,
            "meta": self.meta.to_dict(),
            "swings": [s.to_dict() for s in self.swings],
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscretizationLog":
        """
        Deserialize from dictionary.

        Handles schema version checking for forward compatibility.
        """
        # Check schema version (for future compatibility)
        file_version = data.get("schema_version", "1.0")
        if file_version != SCHEMA_VERSION:
            # Log warning but attempt to parse (future versions may add fields)
            pass

        return cls(
            meta=DiscretizationMeta.from_dict(data["meta"]),
            swings=[SwingEntry.from_dict(s) for s in data.get("swings", [])],
            events=[DiscretizationEvent.from_dict(e) for e in data.get("events", [])],
        )


# =============================================================================
# Validation
# =============================================================================


class ValidationError(Exception):
    """Raised when schema validation fails."""
    pass


def validate_log(log: DiscretizationLog) -> List[str]:
    """
    Validate a discretization log for structural correctness.

    Checks:
    - All event swing_ids reference existing swings
    - Events are ordered by bar index
    - Required config fields are present
    - Event data matches event_type requirements

    Args:
        log: The DiscretizationLog to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: List[str] = []

    # Build swing_id set for reference validation
    swing_ids = {s.swing_id for s in log.swings}

    # Validate event references
    for i, event in enumerate(log.events):
        if event.swing_id not in swing_ids:
            errors.append(
                f"Event {i} references unknown swing_id: {event.swing_id}"
            )

    # Validate event ordering
    for i in range(1, len(log.events)):
        if log.events[i].bar < log.events[i - 1].bar:
            errors.append(
                f"Events not ordered by bar: event {i} (bar {log.events[i].bar}) "
                f"< event {i-1} (bar {log.events[i-1].bar})"
            )

    # Validate config completeness
    config = log.meta.config
    if not config.level_set:
        errors.append("Config level_set is empty")
    if not config.level_set_version:
        errors.append("Config level_set_version is empty")
    if not config.invalidation_thresholds:
        errors.append("Config invalidation_thresholds is empty")

    # Validate event-type-specific data
    for i, event in enumerate(log.events):
        event_errors = _validate_event_data(event, i)
        errors.extend(event_errors)

    return errors


def _validate_event_data(event: DiscretizationEvent, index: int) -> List[str]:
    """
    Validate event-type-specific data fields.

    Each event type has required fields in its data dict.
    """
    errors: List[str] = []
    data = event.data
    prefix = f"Event {index} ({event.event_type.value})"

    if event.event_type == EventType.LEVEL_CROSS:
        required = ["from_ratio", "to_ratio", "level_crossed", "direction"]
        for field_name in required:
            if field_name not in data:
                errors.append(f"{prefix}: missing required field '{field_name}'")

    elif event.event_type == EventType.LEVEL_TEST:
        required = ["level", "result"]
        for field_name in required:
            if field_name not in data:
                errors.append(f"{prefix}: missing required field '{field_name}'")
        if data.get("result") not in ["REJECT", "WICK_THROUGH", None]:
            errors.append(f"{prefix}: invalid result value '{data.get('result')}'")

    elif event.event_type == EventType.COMPLETION:
        if "completion_ratio" not in data:
            errors.append(f"{prefix}: missing required field 'completion_ratio'")

    elif event.event_type == EventType.INVALIDATION:
        required = ["invalidation_ratio", "threshold"]
        for field_name in required:
            if field_name not in data:
                errors.append(f"{prefix}: missing required field '{field_name}'")

    elif event.event_type == EventType.SWING_FORMED:
        required = ["swing_id", "scale", "direction"]
        for field_name in required:
            if field_name not in data:
                errors.append(f"{prefix}: missing required field '{field_name}'")

    elif event.event_type == EventType.SWING_TERMINATED:
        if "termination_type" not in data:
            errors.append(f"{prefix}: missing required field 'termination_type'")
        if data.get("termination_type") not in ["COMPLETED", "INVALIDATED", None]:
            errors.append(f"{prefix}: invalid termination_type '{data.get('termination_type')}'")

    return errors
