# Swing Detection Rewrite Implementation Plan

**Author:** Architect
**Date:** 2025-12-18
**Status:** Ready for Engineering

## Overview

This plan decomposes the swing detection rewrite into minimal, testable issues. The goal is to:
1. Enable parallel work where possible
2. Ensure each change is independently testable
3. Minimize blast radius of any single change
4. Maintain a working system throughout migration

## Current State Analysis

### Files to Replace

| File | Lines | Purpose | Consumers |
|------|-------|---------|-----------|
| `swing_detector.py` | 1549 | Batch detection, ReferenceSwing | 7 modules |
| `incremental_detector.py` | 725 | Bar-by-bar detection | replay.py only |
| `scale_calibrator.py` | ~300 | S/M/L/XL quartile calculation | 2 modules |

### Files to Keep/Extend

| File | Lines | Purpose | Changes Needed |
|------|-------|---------|----------------|
| `reference_frame.py` | 125 | 0/1/2 coordinate system | Add tolerance checks |
| `types.py` | ~50 | Bar dataclass | None |
| `bar_aggregator.py` | ~200 | Multi-timeframe OHLC | None |

### Key Integration Points

```
routers/replay.py ─────┬──> detect_swings() ──> ReferenceSwing
                       └──> IncrementalDetector ──> ActiveSwing, Events

routers/discretization.py ──> detect_swings() ──> ReferenceSwing

discretizer.py ──> ReferenceSwing (type only)

scale_calibrator.py ──> detect_swings()

swing_state_manager.py ──> detect_swings()
```

### Test Files Affected

- `test_swing_detector.py` - Full rewrite
- `test_swing_detector_unit.py` - Full rewrite
- `test_incremental_detector.py` - Full rewrite
- `test_reference_frame.py` - Extend
- `test_swing_state_manager.py` - Update
- `test_discretizer.py` - Minor updates

## Architecture Layers

The rewrite follows a layered approach where each layer depends only on layers below it:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: Cleanup (remove old code)                     │
├─────────────────────────────────────────────────────────┤
│  Layer 4: Integration (routers, API schemas)            │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Compatibility (adapter for old consumers)     │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Algorithm (process_bar, invalidation)         │
├─────────────────────────────────────────────────────────┤
│  Layer 1: Data Structures (SwingConfig, SwingNode)      │
└─────────────────────────────────────────────────────────┘
```

## Implementation Issues

### Layer 1: Data Structures (Parallel)

These have no dependencies and can be implemented simultaneously.

---

#### Issue #A: SwingConfig Dataclass

**File:** `src/swing_analysis/swing_config.py` (new)

**Scope:** Extract all configurable parameters into a single dataclass.

```python
@dataclass
class DirectionConfig:
    """Parameters for one direction (bull or bear)."""
    formation_fib: float = 0.287          # Fib extension to confirm swing
    self_separation: float = 0.10         # Min separation between candidate 1s
    big_swing_threshold: float = 0.10     # Top 10% = "big" swings
    big_swing_price_tolerance: float = 0.15
    big_swing_close_tolerance: float = 0.10
    child_swing_tolerance: float = 0.10

@dataclass
class SwingConfig:
    """All configurable parameters."""
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)

    # Detection parameters
    lookback_bars: int = 50

    @classmethod
    def default(cls) -> "SwingConfig":
        return cls()
```

**Tests:**
- Serialization to/from JSON
- Default values match current magic numbers
- Immutability

**Parallel:** Yes - no dependencies

---

#### Issue #B: SwingNode Dataclass

**File:** `src/swing_analysis/swing_node.py` (new)

**Scope:** Define the hierarchical swing data structure.

```python
@dataclass
class SwingNode:
    """A swing in the hierarchical model."""
    swing_id: str
    high_bar_index: int
    high_price: Decimal
    low_bar_index: int
    low_price: Decimal
    direction: Literal["bull", "bear"]
    status: Literal["forming", "active", "invalidated", "completed"]
    formed_at_bar: int

    # Hierarchy (multiple parents for DAG)
    parents: List["SwingNode"] = field(default_factory=list)
    children: List["SwingNode"] = field(default_factory=list)

    # Computed properties
    @property
    def defended_pivot(self) -> Decimal:
        return self.low_price if self.direction == "bull" else self.high_price

    @property
    def origin(self) -> Decimal:
        return self.high_price if self.direction == "bull" else self.low_price

    @property
    def range(self) -> Decimal:
        return abs(self.high_price - self.low_price)
```

**Tests:**
- Property calculations correct for bull/bear
- Parent/child linking
- Status transitions

**Parallel:** Yes - no dependencies

---

#### Issue #C: Event Types

**File:** `src/swing_analysis/events.py` (new)

**Scope:** Define event types emitted by the detector.

```python
@dataclass
class SwingEvent:
    """Base event from swing detector."""
    event_type: Literal["SWING_FORMED", "SWING_INVALIDATED", "SWING_COMPLETED", "LEVEL_CROSS"]
    bar_index: int
    timestamp: datetime
    swing_id: str

@dataclass
class SwingFormedEvent(SwingEvent):
    event_type: Literal["SWING_FORMED"] = "SWING_FORMED"
    swing: SwingNode
    parent_ids: List[str] = field(default_factory=list)

@dataclass
class SwingInvalidatedEvent(SwingEvent):
    event_type: Literal["SWING_INVALIDATED"] = "SWING_INVALIDATED"
    violation_price: Decimal
    excess_amount: Decimal

@dataclass
class LevelCrossEvent(SwingEvent):
    event_type: Literal["LEVEL_CROSS"] = "LEVEL_CROSS"
    level: float
    previous_level: float
    price: Decimal
```

**Tests:**
- Event serialization
- Event type discrimination

**Parallel:** Yes - no dependencies

---

### Layer 2: Algorithm (Sequential after Layer 1)

These depend on Layer 1 data structures.

---

#### Issue #D: ReferenceFrame Enhancement

**File:** `src/swing_analysis/reference_frame.py` (modify existing)

**Scope:** Add tolerance-based violation checking.

```python
# Add to existing ReferenceFrame class:

def is_violated(self, price: Decimal, tolerance: float = 0) -> bool:
    """Check if defended pivot (0) is violated within tolerance."""
    ratio = self.ratio(price)
    return ratio < -tolerance

def is_formed(self, price: Decimal, formation_fib: float = 0.287) -> bool:
    """Check if price has breached formation threshold."""
    ratio = self.ratio(price)
    return ratio >= formation_fib

def is_completed(self, price: Decimal) -> bool:
    """Check if swing has reached 2.0 target."""
    ratio = self.ratio(price)
    return ratio >= 2.0
```

**Tests:**
- Violation checks for bull/bear
- Formation threshold checks
- Completion checks
- Tolerance edge cases

**Parallel:** Yes - only depends on existing ReferenceFrame

**Sequence:** Can start immediately, needed by Issue #E

---

#### Issue #E: Core Incremental Algorithm

**File:** `src/swing_analysis/hierarchical_detector.py` (new)

**Scope:** Single `process_bar()` algorithm with no lookahead.

This is the heart of the rewrite. Key design:

```python
@dataclass
class DetectorState:
    """Serializable state for pause/resume."""
    active_swings: List[SwingNode]
    candidate_highs: List[Tuple[int, Decimal]]  # (bar_index, price)
    candidate_lows: List[Tuple[int, Decimal]]
    last_bar_index: int

class HierarchicalDetector:
    def __init__(self, config: SwingConfig):
        self.config = config
        self.state = DetectorState(...)

    def process_bar(self, bar: Bar) -> List[SwingEvent]:
        """Process a single bar. Returns events generated."""
        events = []

        # 1. Check invalidations (independent per swing)
        events.extend(self._check_invalidations(bar))

        # 2. Check completions
        events.extend(self._check_completions(bar))

        # 3. Check level crosses
        events.extend(self._check_level_crosses(bar))

        # 4. Update candidate extrema
        self._update_candidates(bar)

        # 5. Try to form new swings
        events.extend(self._try_form_swings(bar))

        return events

    def get_state(self) -> DetectorState:
        """Get serializable state for persistence."""
        return self.state

    @classmethod
    def from_state(cls, state: DetectorState, config: SwingConfig) -> "HierarchicalDetector":
        """Restore from serialized state."""
        detector = cls(config)
        detector.state = state
        return detector
```

**Algorithm details:**

1. **Invalidation check:** For each active swing, check if `bar.low` (bull) or `bar.high` (bear) violates the defended pivot. Use tolerance from config based on distance to big swing.

2. **Candidate tracking:** Maintain sliding window of candidate highs/lows (last N bars where N = lookback).

3. **Swing formation:** When a new candidate extremum appears AND price has breached formation_fib from a previous opposite extremum, form a swing.

4. **Parent assignment:** When forming a swing, find all active swings where this swing's defended pivot is within their 0-2 range. These are parents.

**Tests:**
- Single bar processing
- Multi-bar sequence with known outcomes
- Invalidation triggers correctly
- Formation triggers correctly
- Parent assignment correct
- State serialization round-trip

**Parallel:** No - depends on Issues #A, #B, #C, #D

**Estimate:** This is the largest issue (~400-500 LOC)

---

#### Issue #F: Calibration as Loop

**File:** `src/swing_analysis/hierarchical_detector.py` (extend)

**Scope:** Add calibration helper that runs process_bar in a loop.

```python
def calibrate(
    bars: List[Bar],
    config: SwingConfig = None
) -> Tuple[HierarchicalDetector, List[SwingEvent]]:
    """
    Run detection on historical bars.

    This is just process_bar() in a loop - no special logic.
    Guarantees identical behavior to incremental playback.
    """
    config = config or SwingConfig.default()
    detector = HierarchicalDetector(config)
    all_events = []

    for bar in bars:
        events = detector.process_bar(bar)
        all_events.extend(events)

    return detector, all_events
```

**Tests:**
- Calibration produces same results as bar-by-bar
- Large dataset performance (<60s for 6M bars target)

**Parallel:** No - depends on Issue #E

---

### Layer 3: Compatibility (Sequential after Layer 2)

---

#### Issue #G: ReferenceSwing Adapter

**File:** `src/swing_analysis/adapters.py` (new)

**Scope:** Convert new SwingNode to old ReferenceSwing format for consumers not yet updated.

```python
def swing_node_to_reference_swing(node: SwingNode) -> ReferenceSwing:
    """
    Convert hierarchical SwingNode to legacy ReferenceSwing.

    This allows gradual migration of consumers.
    """
    return ReferenceSwing(
        high_price=float(node.high_price),
        high_bar_index=node.high_bar_index,
        low_price=float(node.low_price),
        low_bar_index=node.low_bar_index,
        size=float(node.range),
        direction=node.direction,
        # Legacy fields - computed for compatibility
        level_0382=...,
        level_2x=...,
        rank=0,  # No longer meaningful
        impulse=0.0,
    )

def detect_swings_compat(
    df: pd.DataFrame,
    **kwargs
) -> Dict[str, List[ReferenceSwing]]:
    """
    Compatibility wrapper matching old detect_swings() signature.

    Returns dict with scale keys for backward compatibility,
    but internally uses hierarchical detection.
    """
    # Convert DataFrame to Bar list
    bars = dataframe_to_bars(df)

    # Run new detector
    detector, events = calibrate(bars)

    # Convert to legacy format
    swings = detector.get_active_swings()
    legacy_swings = [swing_node_to_reference_swing(s) for s in swings]

    # Group by "scale" based on size quartiles (legacy behavior)
    # This is a compatibility shim - will be removed later
    return _group_by_legacy_scale(legacy_swings)
```

**Tests:**
- Round-trip conversion preserves essential data
- Compatibility function produces similar output shape

**Parallel:** No - depends on Issue #E, #F

---

### Layer 4: Integration (Sequential after Layer 3)

---

#### Issue #H: Replay Router Update

**File:** `src/ground_truth_annotator/routers/replay.py` (modify)

**Scope:** Update replay router to use new HierarchicalDetector.

**Changes:**
1. Replace `IncrementalSwingState` with `HierarchicalDetector`
2. Replace `advance_bar_incremental` with `detector.process_bar()`
3. Update calibration endpoint to use `calibrate()`
4. Remove scale-specific logic (S/M/L/XL dropdown becomes hierarchy depth filter)
5. Update event response format for parent/child info

**Key insight:** The replay router is the ONLY consumer of IncrementalDetector, so this is a contained change.

**Tests:**
- API contract tests for /api/replay/calibrate
- API contract tests for /api/replay/advance
- Event format matches schema

**Parallel:** No - depends on Issue #G

---

#### Issue #I: Discretization Update

**File:** `src/discretization/discretizer.py` (modify)

**Scope:** Update discretizer to consume new swing format.

**Changes:**
1. Import SwingNode instead of ReferenceSwing (or use adapter)
2. Update Fib level calculations to use ReferenceFrame
3. Remove scale assumptions if any

**Tests:**
- Discretization produces valid output with new swing format

**Parallel:** Yes - can run parallel with Issue #H (different files)

---

#### Issue #J: API Schema Updates

**File:** `src/ground_truth_annotator/schemas.py` (modify)

**Scope:** Add new response schemas for hierarchical swings.

```python
class HierarchicalSwingResponse(BaseModel):
    swing_id: str
    high_bar_index: int
    high_price: float
    low_bar_index: int
    low_price: float
    direction: str
    status: str
    parent_ids: List[str]
    child_ids: List[str]
    depth: int  # Hierarchy depth (0 = root)
```

**Tests:**
- Schema validation
- Serialization round-trip

**Parallel:** Yes - can run parallel with Issues #H, #I

---

### Layer 5: Cleanup (Sequential after Layer 4)

---

#### Issue #K: Remove Old Detection Code

**Files:** Multiple

**Scope:** Delete deprecated code now that new system is working.

**Deletions:**
1. `src/swing_analysis/swing_detector.py` - batch detection functions (keep ReferenceSwing temporarily for any remaining consumers)
2. `src/swing_analysis/incremental_detector.py` - entire file
3. `src/swing_analysis/scale_calibrator.py` - entire file (S/M/L/XL obsolete)
4. Related test files

**Updates:**
1. `src/swing_analysis/__init__.py` - update exports
2. Any remaining imports

**Tests:**
- Full test suite passes
- No import errors

**Parallel:** No - must be last

---

#### Issue #L: Ground Truth Annotator Removal

**Files:** `src/ground_truth_annotator/` directory

**Scope:** Archive and delete ground truth annotator per Product decision.

**Steps:**
1. Ensure git history is preserved (commit message noting archival)
2. Delete `src/ground_truth_annotator/` directory
3. Delete `ground_truth/` directory contents
4. Update any imports that reference removed code
5. Remove related test files

**Tests:**
- No import errors
- Remaining test suite passes

**Parallel:** Yes - independent of Issues #H-K

---

## Execution Sequence

```
Week 1: Foundation (Parallel)
├── Issue #A: SwingConfig ──────────────┐
├── Issue #B: SwingNode ────────────────┼── Can all run in parallel
├── Issue #C: Event Types ──────────────┤
├── Issue #D: ReferenceFrame Enhancement┘
└── Issue #L: Ground Truth Removal ───────── Independent, can run anytime

Week 2: Core Algorithm (Sequential)
└── Issue #E: Core Incremental Algorithm ──── Blocked by #A, #B, #C, #D
    └── Issue #F: Calibration as Loop ─────── Blocked by #E

Week 3: Integration (Mixed)
├── Issue #G: ReferenceSwing Adapter ──────── Blocked by #E, #F
│   └── Issue #H: Replay Router Update ────── Blocked by #G
├── Issue #I: Discretization Update ───────── Can parallel with #H
└── Issue #J: API Schema Updates ──────────── Can parallel with #H, #I

Week 4: Cleanup (Sequential)
└── Issue #K: Remove Old Detection Code ───── Blocked by #H, #I, #J
```

## Parallelism Summary

| Phase | Issues | Parallelism |
|-------|--------|-------------|
| Foundation | #A, #B, #C, #D, #L | **All parallel** (5 agents) |
| Algorithm | #E, #F | **Sequential** (1 agent) |
| Integration | #G → #H, #I, #J | **#H sequential, #I/#J parallel** (2-3 agents) |
| Cleanup | #K | **Sequential** (1 agent) |

**Maximum parallel agents:** 5 (during Foundation phase)
**Critical path:** #A/#B/#C/#D → #E → #F → #G → #H → #K

## Testing Strategy

### Per-Issue Testing
Each issue includes unit tests that can run independently.

### Integration Testing
After Layer 3 (Issue #G):
- Run existing test suite with compatibility adapter
- Verify no regressions in output shape

### User Acceptance Testing
After Layer 4 (Issues #H, #I, #J):
- User testing via Replay Mode
- Validate swing quality with domain expertise

### Final Validation
After Layer 5 (Issue #K):
- Full test suite (865 tests) passes
- Performance benchmark (<60s for 6M bars)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Algorithm bugs | Extensive unit tests in Issue #E |
| Integration breakage | Compatibility adapter (#G) allows gradual migration |
| Performance regression | Benchmark in Issue #F before integration |
| Scope creep | Strict issue boundaries, no "while we're here" changes |

## Definition of Done

Each issue is complete when:
1. Code implemented and passes lint
2. Unit tests written and passing
3. No regressions in existing tests
4. Code reviewed (self-review for parallel agents)
5. Committed with descriptive message

## Issue Summary for GitHub

| # | Title | Layer | Parallel | Blocked By |
|---|-------|-------|----------|------------|
| A | SwingConfig dataclass | 1 | Yes | - |
| B | SwingNode dataclass | 1 | Yes | - |
| C | Event types | 1 | Yes | - |
| D | ReferenceFrame tolerance checks | 1 | Yes | - |
| E | Core incremental algorithm | 2 | No | A, B, C, D |
| F | Calibration as loop | 2 | No | E |
| G | ReferenceSwing compatibility adapter | 3 | No | E, F |
| H | Replay router update | 4 | No | G |
| I | Discretization update | 4 | Yes | G |
| J | API schema updates | 4 | Yes | G |
| K | Remove old detection code | 5 | No | H, I, J |
| L | Ground truth annotator removal | - | Yes | - |

**Total: 12 issues**
**Parallel phases: 3 (Foundation, Integration-partial, Cleanup-partial)**
**Critical path length: 7 issues (A→E→F→G→H→K)**
