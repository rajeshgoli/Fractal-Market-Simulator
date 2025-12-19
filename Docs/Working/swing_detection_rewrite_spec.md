# Swing Detection Rewrite Specification

**Author:** Product
**Date:** 2025-12-18
**Status:** Approved - Ready for Implementation (Dec 18)

## Why This Matters

**This is the single biggest blocker for the project.** Clean swing detection is the prerequisite for discretization. Without reliable swings, we cannot proceed to the next phase.

## Problem Statement

### What is a Valid Swing?

A reference swing is a price range (high to low) used to predict future price action. Using a symmetric reference frame:
- **0** = Defended pivot (low for bull, high for bear) - must never be violated
- **1** = Origin (high for bull, low for bear) - the starting extremum
- **2** = Target (completion level)

A valid reference swing exists when:
1. Price is between 0 and 2, with correct temporal ordering
2. 0 was never violated after swing was created
3. Price breached a configurable fib extension (0.287) from the defended pivot
4. 1 is structurally differentiated from other candidate 1s

### Swings are Hierarchical

Swings form a tree/DAG structure, not discrete buckets. From the ES example (Dec 2025):

```
L1: 6166→4832 (yearly)
├── L2: 5837→4832 (impulsive April drop)
│   └── L3: 6955→6524 (Oct-Nov)
│       ├── L4: 6896→6524 (mid-Nov high)
│       ├── L5: 6790→6524 (Nov 17/20 high)
│       │   └── L6: 6929→6771 (Dec weekly)
│       │       └── L7: 6882→6770 (daily)
```

This is 7+ nested levels. In practice there can be 10-15 levels of hierarchy. **When a parent's defended pivot is violated, all children must be invalidated** (prune the subtree).

### The S/M/L/XL Model is Now a Liability

The S/M/L/XL scale classification (based on quartiles) was useful for bootstrapping:
- Made calibration tractable early on
- Provided a simple mental model

But it is now a source of bugs:
- **Obscures hierarchy**: Swings don't naturally fall into 4 buckets
- **No parent-child links**: Can't cascade invalidation
- **Arbitrary boundaries**: Quartiles don't map to structural significance
- **Duplicated logic**: Each scale has separate processing, leading to divergent behavior

### Rules are Not Consistently Enforced

The swing detection rules (see `Docs/Reference/valid_swings.md`) require:

| Rule | Requirement | Current State |
|------|-------------|---------------|
| **2.1 Pre-formation** | Absolute - NO tolerance | Code uses tolerance (bug) |
| **2.2 Post-formation** | Tolerance only for big swings | Applied inconsistently |
| **3 Formation trigger** | Configurable fib extension | Magic numbers scattered |
| **4 Extrema separation** | 0.1× range self-separation | Not consistently checked |

**Configurable parameters are scattered as magic numbers** throughout the codebase. If the formation fib is different for bull vs bear, that should be a config in the unified reference frame, not buried in conditionals. Currently it's impossible to extract and verify these parameters.

### Dual Code Paths Cause Divergent Behavior

Two separate implementations exist:
- **Batch detector** (`swing_detector.py`) - calibration, sees entire dataset
- **Incremental detector** (`incremental_detector.py`) - playback, bar-by-bar

This causes:
- **Lookahead bugs**: Batch can use future data that incremental can't
- **Divergent results**: Same data, different swings depending on path
- **Double maintenance**: Bug fixed in one path may not be fixed in other (#139, #140)
- **Bar index mismatches**: Batch reports indices that don't match actual price locations

### Discretization is Blocked

The goal of swing detection is to enable discretization - converting continuous price data into discrete structural events. But:

**Currently, events exceed bars.** If we discretized today, we would *increase* data size by 2-5x, not reduce it. This makes discretization futile - why not just use source bars at that point?

Clean swings (fewer, structurally significant) are required before discretization is viable.

## Proposed Architecture

### Single Incremental Algorithm

One algorithm that processes bars incrementally. Calibration = same algorithm in a loop.

```
┌─────────────────────────────────────┐
│     SwingDetector (incremental)     │
├─────────────────────────────────────┤
│ process_bar(bar) → List[Event]      │
│ get_active_swings() → SwingTree     │
│ get_state() → SerializableState     │
└─────────────────────────────────────┘

Calibration:
    detector = SwingDetector(config)
    for bar in historical_bars:
        events = detector.process_bar(bar)
    state = detector.get_state()

Playback:
    detector = SwingDetector.from_state(state)
    for bar in new_bars:
        events = detector.process_bar(bar)  # Identical code path
```

**No lookahead possible** - algorithm only sees current and past bars.

### Unified Reference Frame

All swing logic operates in symmetric 0/1/2 coordinates:

```python
@dataclass
class DirectionConfig:
    """Parameters for one direction (bull or bear)."""
    formation_fib: float = 0.287          # Fib extension to confirm swing
    self_separation: float = 0.10         # Min separation between candidate 1s
    parent_child_separation: float = 0.10 # Min separation from parent extrema
    big_swing_threshold: float = 0.10     # Top 10% = "big" swings
    big_swing_price_tolerance: float = 0.15   # Level 0: full tolerance
    big_swing_close_tolerance: float = 0.10   # Level 0: close-based tolerance
    child_swing_tolerance: float = 0.10       # Level 1-2: basic tolerance

@dataclass
class SwingConfig:
    """All configurable parameters - separate configs for bull and bear."""
    bull: DirectionConfig = field(default_factory=DirectionConfig)
    bear: DirectionConfig = field(default_factory=DirectionConfig)

class ReferenceFrame:
    """Symmetric coordinates - direction-agnostic logic."""
    anchor0: Decimal  # Defended pivot
    anchor1: Decimal  # Origin

    def price_to_ratio(self, price: Decimal) -> Decimal:
        """Convert price to 0/1/2 coordinate system."""
        return (price - self.anchor0) / self.range

    def is_violated(self, price: Decimal, tolerance: float = 0) -> bool:
        """Check if defended pivot (0) is violated."""
        return self.price_to_ratio(price) < -tolerance
```

All bull/bear branching is eliminated from core logic. Direction only matters for:
- Choosing which price series to check (highs vs lows)
- Display/labeling

### Hierarchical Swing Model

Replace S/M/L/XL with tree/DAG:

```python
@dataclass
class SwingNode:
    high_bar_index: int
    high_price: Decimal
    low_bar_index: int
    low_price: Decimal
    direction: Literal["bull", "bear"]
    status: Literal["forming", "active", "invalidated", "completed"]
    parents: List[SwingNode]   # Can have multiple parents
    children: List[SwingNode]

class SwingTree:
    roots: List[SwingNode]

    def check_invalidations(self, price: Decimal) -> List[SwingNode]:
        """Check all swings for invalidation. Returns newly invalidated nodes."""
        invalidated = []
        for swing in self.all_active_swings():
            if swing.reference_frame.is_violated(price, swing.tolerance):
                swing.status = "invalidated"
                invalidated.append(swing)
        return invalidated
```

**Independent invalidation**: Each swing is invalidated only when its own defended pivot (0) is violated. No automatic cascade — children typically have higher defended pivots than parents, so they invalidate first. The only "cascade" is when multiple swings share the same defended pivot (e.g., L1 and L2 both defend 4832), which is simultaneous invalidation, not propagation.

## Rules Implementation

All rules from `Docs/Reference/valid_swings.md`:

### Rule 2.1: Pre-Formation (Absolute)

```python
def check_pre_formation(frame: ReferenceFrame, bars: List[Bar]) -> bool:
    """NO tolerance - any violation rejects candidate."""
    for bar in bars_between_origin_and_pivot:
        if frame.is_violated(bar.low, tolerance=0):  # Absolute
            return False
        if frame.price_to_ratio(bar.high) > 1:  # Origin exceeded
            return False
    return True
```

### Rule 2.2: Post-Formation Invalidation

```python
def is_big_swing(swing: SwingNode, all_swings: List[SwingNode], config: DirectionConfig) -> bool:
    """Big swing = range in top percentile of all active swings.

    From valid_swings.md: "Big swings are defined as those whose range is
    within 10% of all the reference swings" - meaning top 10% by range.
    These are typically monthly/yearly swings.
    """
    ranges = sorted([s.range for s in all_swings], reverse=True)
    threshold_idx = int(len(ranges) * config.big_swing_threshold)  # e.g., top 10%
    threshold_range = ranges[threshold_idx] if threshold_idx < len(ranges) else 0
    return swing.range >= threshold_range

def distance_to_big_swing(swing: SwingNode, all_swings: List[SwingNode], config: DirectionConfig) -> int:
    """Return hierarchy distance to nearest big swing ancestor.

    Returns:
        0 if swing itself is big
        1 if parent is big (daily/weekly child of monthly/yearly)
        2 if grandparent is big
        999 if no big swing ancestor within 2 levels
    """
    if is_big_swing(swing, all_swings, config):
        return 0
    for parent in swing.parents:
        if is_big_swing(parent, all_swings, config):
            return 1
        for grandparent in parent.parents:
            if is_big_swing(grandparent, all_swings, config):
                return 2
    return 999  # No big swing ancestor

def check_invalidation(swing: SwingNode, bar: Bar, all_swings: List[SwingNode], config: DirectionConfig) -> bool:
    """Graduated tolerance based on distance from big swings.

    - Level 0 (big swing itself): full tolerance (0.15 price, 0.10 close)
    - Level 1-2 (child/grandchild): basic tolerance (0.10 price)
    - Level 3+: absolute (no tolerance)
    """
    frame = swing.reference_frame
    distance = distance_to_big_swing(swing, all_swings, config)

    if distance == 0:  # Big swing itself
        # Full tolerance: 0.15 price OR 0.10 close
        return frame.is_violated(bar.low, config.big_swing_price_tolerance)
    elif distance <= 2:  # Child or grandchild of big swing
        # Basic tolerance: 0.10 price
        return frame.is_violated(bar.low, config.child_swing_tolerance)  # 0.10
    else:
        return frame.is_violated(bar.low, tolerance=0)  # Absolute
```

### Rule 3: Formation Trigger

```python
def check_formation(frame: ReferenceFrame, price: Decimal, config: SwingConfig) -> bool:
    """Swing forms when price breaches formation fib."""
    ratio = frame.price_to_ratio(price)
    return ratio >= config.formation_fib
```

### Rule 4: Extrema Separation

```python
def check_separation(candidate: SwingNode, existing: List[SwingNode], config: SwingConfig) -> bool:
    """4.1 Self-separation and 4.2 Parent-child separation."""
    for other in existing:
        distance = abs(candidate.origin_price - other.origin_price)
        if distance < config.self_separation * candidate.range:
            return False  # Too close to another candidate
    # Similar check for parent-child separation
    ...
```

## Migration Path

### Phase 1: New Core
- Implement `SwingDetector` with hierarchical model
- Single `process_bar()` entry point
- `SwingConfig` for all parameters
- `ReferenceFrame` for direction-agnostic logic

### Phase 2: Calibration as Loop
- Calibration calls `process_bar()` in loop
- State serialization for pause/resume
- Verify identical results vs current batch (modulo bug fixes)

### Phase 3: Integration
- Update playback to use new detector
- Update event system for tree-based events
- Migrate ground truth annotations

### Phase 4: Cleanup
- Remove `swing_detector.py` batch logic
- Remove `incremental_detector.py`
- Remove S/M/L/XL scale classification entirely

## Success Criteria

1. **No lookahead**: Algorithm only accesses current and past bars
2. **Single code path**: Calibration and playback are identical
3. **Independent invalidation**: Each swing invalidated only when its own 0 is violated (no automatic cascade)
4. **Rule compliance**: All `valid_swings.md` rules correctly enforced
5. **Configurable parameters**: All magic numbers extracted to `SwingConfig`
6. **Events < Bars**: Discretization reduces data, not increases it
7. **Unified reference frame**: No bull/bear branching in core logic

## Frontend Implications

### Ground Truth Annotator
**Status: Can be archived.**

The annotator (`src/ground_truth_annotator/`) was built for capturing false negatives in swing detection. With the rewrite:
- Existing annotations may not map cleanly to new hierarchical model
- The S/M/L/XL scale selector becomes obsolete
- If needed later, can rebuild with hierarchy-aware UI

### Replay Mode
**Status: Must work.**

Replay is the primary user-facing feature. Required changes:

| Component | Current | After Rewrite |
|-----------|---------|---------------|
| Scale selector | S/M/L/XL dropdown | Remove or replace with hierarchy depth filter |
| Swing display | Colored by scale bucket | Colored by hierarchy level or tree depth |
| Event feed | `SWING_FORMED` with scale | `SWING_FORMED` with parent references |
| Invalidation | Per-scale independent | Cascading (shows children invalidated too) |

**Minimal changes for replay to work:**
1. Event structure adds `parents: List[SwingId]` and `children: List[SwingId]`
2. Remove scale from events (or derive from hierarchy depth for display)
3. Invalidation events include cascade info (which children also invalidated)
4. Visualization can initially ignore hierarchy and just show swings flat

**Enhanced visualization (later):**
- Tree view of active swings
- Expand/collapse hierarchy levels
- Filter by depth (show only top N levels)

### Event Structure Changes

```python
# Current
SwingEvent(scale="M", high_bar=100, low_bar=150, ...)

# After rewrite
SwingEvent(
    swing_id: str,
    high_bar: int,
    low_bar: int,
    parents: List[str],      # Parent swing IDs
    children: List[str],     # Child swing IDs (if any)
    depth: int,              # Hierarchy depth (0 = root)
    ...
)

# Invalidation includes cascade
InvalidationEvent(
    swing_id: str,
    cascade: List[str],      # Child swings also invalidated
    ...
)
```

## Resolved Questions (Dec 18)

| Question | Resolution |
|----------|------------|
| **Performance** | Acceptable. Incremental is O(active swings) per bar, not O(N). Should be faster than batch's O(N log N). |
| **DAG complexity** | DAG confirmed. Multiple parents for context/tolerance. NO automatic cascade — each swing checks its own 0. Children invalidate before parents (higher defended pivots). |
| **State format** | JSON recommended. Simple, portable, versionable. |
| **Ground truth** | Archive in git, delete locally. Can recreate via replay sessions. |

## References

- `Docs/Reference/valid_swings.md` - Canonical swing rules (source of truth)
- `src/swing_analysis/reference_frame.py` - Existing ReferenceFrame (underutilized)
- `src/swing_analysis/swing_detector.py` - Current batch detector
- `src/swing_analysis/incremental_detector.py` - Current incremental detector
- Issues #139, #140 - Examples of dual-path divergence bugs
