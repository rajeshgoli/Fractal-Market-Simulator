# Architect Fixes

Accumulated architectural issues to address together.

## Execution Order

| Phase | Items | Description |
|-------|-------|-------------|
| 1 | #1 | Rename `ground_truth_annotator` → `replay_server` (unblocks everything) |
| 2 | #4 + #5 | Schema cleanup + unification (do together) |
| 3 | #3 | Split routers (optional, Phase 2) |
| 4 | #2 | Inline models.py (low priority, optional) |

**Dependencies:**
- #5 (unify schemas) resolves parts of #4 (dead fields)
- #3 (split routers) is easier after #1 (rename)

---

## 1. Rename `ground_truth_annotator` → `replay_server`

**Status:** Identified
**Severity:** Medium (misleading name, no functional impact)

### Problem

The `src/ground_truth_annotator/` module name is obsolete and misleading:
- **Actual purpose**: FastAPI backend for replay visualization, DAG inspection, reference layer queries
- **Name implies**: ML labeling/annotation tool for ground truth collection

The original annotation functionality was removed, but the folder name was never updated.

### Current Structure

```
ground_truth_annotator/
├── api.py          (647 lines) - Main FastAPI app, session mgmt
├── main.py         (313 lines) - CLI entry point
├── models.py       (110 lines) - Feedback storage models (see #2)
├── schemas.py      (700+ lines) - Pydantic request/response models
├── storage.py      (150 lines) - Feedback storage
└── routers/
    └── replay.py   (2094 lines) - All replay/DAG/reference endpoints
```

### Secondary Issues

1. **Bloat**: `replay.py` is 2000+ lines mixing 6+ endpoint domains (see #3)
2. **Feedback storage**: Only vestige of original "ground truth" functionality (see #2)

### Recommended Fix

Rename to `replay_server/` and consider splitting routers:

```
replay_server/
├── app.py               # FastAPI app setup
├── main.py              # CLI entry point
├── schemas.py           # Pydantic models
├── routers/
│   ├── session.py       # /api/session, /api/files, /api/config
│   ├── bars.py          # /api/bars
│   ├── replay.py        # /api/replay/* (calibrate, advance, reverse)
│   ├── dag.py           # /api/dag/*
│   └── reference.py     # /api/reference-state, /api/reference/levels
└── storage/
    └── feedback.py      # Playback feedback (if keeping)
```

### Files to Update

- [ ] Rename `src/ground_truth_annotator/` → `src/replay_server/`
- [ ] Update all imports referencing the old path
- [ ] Update `CLAUDE.md` module table
- [ ] Update any documentation references
- [ ] Consider splitting `routers/replay.py` (optional, can defer)

---

## 2. `models.py` - Keep but inline into storage

**Status:** Investigated
**Severity:** Low (minor organizational issue)

### Findings

Deep investigation reveals `models.py` is **not dead code** - it's actively used:

**Dependency chain:**
```
models.py (PlaybackObservation, PlaybackSession)
    ↓
storage.py (PlaybackFeedbackStorage) - only consumer
    ↓
api.py (init_app creates storage)
    ↓
routers/replay.py (/api/playback/feedback endpoint)
    ↓
frontend/FeedbackForm.tsx (user-facing observation capture)
```

**Evidence of active use:**
- `ground_truth/playback_feedback.json` has 90KB of stored observations
- `ground_truth/screenshots/` has captured screenshots
- Frontend has full `FeedbackForm.tsx` component (374 lines)

### Decision

**Keep the functionality**, but consider:
1. Inline `models.py` into `storage.py` since it's the only consumer (2 small dataclasses)
2. This is low priority - the separation doesn't hurt anything

### Files affected
- `models.py` (109 lines) - 2 dataclasses: `PlaybackObservation`, `PlaybackSession`
- `storage.py` (157 lines) - `PlaybackFeedbackStorage` class

---

## 3. `routers/replay.py` - Split into domain routers

**Status:** Investigated
**Severity:** Medium (maintainability concern)

### Problem

Single 2094-line file mixing 6+ endpoint domains:

| Domain | Lines (est.) | Endpoints |
|--------|-------------|-----------|
| Replay calibration/advance | ~400 | `/api/replay/calibrate`, `/advance`, `/reverse` |
| DAG state | ~200 | `/api/dag/state`, `/api/dag/lineage/{leg_id}` |
| Follow Leg | ~100 | `/api/followed-legs/events` |
| Detection Config | ~200 | `/api/replay/config` (GET/PUT) |
| Reference State | ~300 | `/api/reference-state`, `/api/reference/levels`, `/api/reference/track` |
| Playback Feedback | ~100 | `/api/playback/feedback` |
| Helper functions | ~700 | Conversion, building, threshold calculation |

### Recommended Split

```
routers/
├── __init__.py          # Re-export all routers
├── replay.py            # /api/replay/* (calibrate, advance, reverse)
├── dag.py               # /api/dag/* (state, lineage)
├── reference.py         # /api/reference-state, /api/reference/*
├── config.py            # /api/replay/config (GET/PUT)
├── feedback.py          # /api/playback/feedback
└── helpers/
    ├── __init__.py
    ├── conversions.py   # _leg_to_calibration_response, _event_to_response, etc.
    └── builders.py      # _build_swing_state, _build_dag_state, etc.
```

### Shared State Issue

The file uses a global `_replay_cache` dict that all endpoints access. Options:
1. Keep as module-level singleton in a `cache.py` file
2. Move to app state (cleaner but more refactoring)
3. Keep in replay.py and import from other routers (acceptable short-term)

### Priority

This is a **Phase 2** cleanup - can be done after the rename. The current structure works, it's just harder to navigate.

---

## 4. Refactoring Debt - Dead Code & Confusing Comments

**Status:** Identified
**Severity:** Medium (maintainability hazard, confuses new readers)
**Related:** Issues #301, #345, #394

### Pattern

Multiple refactoring issues left vestiges in the codebase:
- Removed features still have schema fields, config options, and hardcoded values
- Comments explain what was removed instead of deleting the code
- New readers see code that does nothing and comments about things that don't exist

### Specific Issues

#### 4a. `swing_id` vestiges (#394)

**Should remove:**
- `SwingEvent.swing_id` field in `events.py` (always `""`)
- 15+ `swing_id=""` args in `leg_detector.py` and `leg_pruner.py`
- `ReplayEventResponse.swing_id`, `DagLegResponse.swing_id` in schemas

#### 4b. `LevelCrossEvent` vestiges (#394)

**Should remove:**
- `emit_level_crosses: bool = False` in `swing_config.py` (never used)
- `with_level_crosses()` method in `swing_config.py`
- `level`, `previous_level` fields in `ReplayEventResponse` ("For LEVEL_CROSS")
- `LEVEL_CROSS` in event type comments
- Comments like `# LevelCrossEvent removed (#394)`

#### 4c. `recently_invalidated` dead field

**Should remove:**
```python
# schemas.py:353
recently_invalidated: int  # Swings invalidated in last N bars

# replay.py:580-581 - Always returns 0!
# Note: Legs don't track invalidated_at_bar anymore, so this returns 0
recently_invalidated = 0
```

This field serves no purpose - delete from schema and all code.

#### 4d. Hierarchy fields disconnected from Leg hierarchy

**The leg hierarchy is alive and well:**
```python
# leg.py:96-99 - Leg HAS depth
depth: int = 0  # 0 = root, 1 = first-level child, etc.

# leg.py:47 - Leg HAS parent_leg_id
parent_leg_id: Optional[str] = None

# reference_layer.py:788 - Reference Layer USES leg.depth
depth=leg.depth,
```

**But the router hardcodes zeros with wrong comments:**
```python
# replay.py:194-195 - WRONG: leg hierarchy exists!
depth=0,  # Swing hierarchy removed (#301)
parent_ids=[],  # Swing hierarchy removed (#301)
```

**Recommended fix (Option 2 - Simplify):**

1. **`depth`** - populate from `leg.depth` (O(1), already stored)
2. **`parent_ids: List[str]`** - DELETE this field, replace with `parent_leg_id: Optional[str]`
   - Leg has single parent, not ancestor list
   - `DagLegResponse` already has `parent_leg_id` - use that pattern
   - If frontend needs full ancestry, traverse `parent_leg_id` links or use `/api/dag/lineage/{leg_id}`

**Why not Option 1 (traverse to build parent_ids)?**
- Requires O(depth) traversal on every response
- `parent_ids` implies multiple parents, but it's really just ancestors
- Derived data belongs in dedicated endpoint, not every response

**Schema simplification (lower priority):**
- `SwingsByDepth` / `ReplaySwingState` with `depth_1`/`depth_2`/`depth_3`/`deeper` is overcomplicated
- Could simplify to `Dict[int, List[...]]` keyed by actual depth
- Defer until schema unification (item #5)

#### 4e. Confusing "removed in #XXX" comments

These comments don't help - they confuse new readers:
```python
depth = 0  # Swing hierarchy removed (#301)
parent_ids: List[str] = []  # Swing hierarchy removed (#301)
swing_id=None,  # Swing ID removed (#394)
# LevelCrossEvent removed (#394)
# #345: invalidation_threshold removed
```

**Rule:** If something is removed, delete the code. Don't leave tombstones.

### Recommended Approach

1. **Remove dead code entirely** - no "backwards compatibility" for unused features
2. **Delete tombstone comments** - Git history preserves what was removed
3. **Simplify schemas** - if a field is always null/0/empty, remove it
4. **Frontend sync** - verify frontend doesn't use these fields before removal

### Files Most Affected

| File | Issues |
|------|--------|
| `routers/replay.py` | 20+ tombstone comments, hardcoded hierarchy values |
| `schemas.py` | Dead: `swing_id`, `parent_ids`, `recently_invalidated`, `level`. Disconnected: `depth` (see #4d) |
| `events.py` | `swing_id` on base class |
| `swing_config.py` | `emit_level_crosses` config that does nothing |

---

## 5. Unify `CalibrationSwingResponse` and `DagLegResponse`

**Status:** Identified
**Severity:** Medium (API confusion, dual schemas for same data)

### Problem

Two schemas represent the same underlying Leg:

| Field | CalibrationSwingResponse | DagLegResponse |
|-------|-------------------------|----------------|
| ID | `id` | `leg_id` |
| Direction | `direction` | `direction` |
| Prices | `high_price`, `low_price` (abstraction) | `origin_price`, `pivot_price` (direct) |
| Indices | `high_bar_index`, `low_bar_index` | `origin_index`, `pivot_index` |
| Hierarchy | `depth=0`, `parent_ids=[]` (dead) | `parent_leg_id` (correct) |
| Fibs | `fib_0`, `fib_0382`, `fib_1`, `fib_2` | ❌ none |
| Scale | `scale` (S/M/L/XL) | ❌ none |
| Metrics | `size`, `rank`, `is_active` | `retracement_pct`, `impulsiveness`, `spikiness`, etc. |

### Issues

1. **Two schemas for one entity** - confusing, they've diverged
2. **Wrong terminology** - `high`/`low` hides origin/pivot semantics
3. **Wrong name** - "CalibrationSwingResponse" is not a Swing, and not just for Calibration
4. **Dead fields** - `depth=0`, `parent_ids=[]` hardcoded

### Recommendation

**Unify to one schema based on `DagLegResponse`:**

```python
class LegResponse(BaseModel):
    """A leg in the DAG."""
    leg_id: str
    direction: str  # "bull" or "bear"
    origin_price: float
    origin_index: int
    pivot_price: float
    pivot_index: int
    depth: int  # From leg.depth
    parent_leg_id: Optional[str] = None
    status: str  # "active" or "stale"
    # Metrics
    range: float  # |origin - pivot|
    retracement_pct: float
    impulsiveness: Optional[float] = None
    spikiness: Optional[float] = None
    # Convenience (computed on request)
    fib_levels: Optional[Dict[str, float]] = None
```

**Move scale/rank to Reference Layer response** - S/M/L/XL binning is a Reference Layer concept, not a DAG concept.

### Migration

1. Create unified `LegResponse` schema
2. Update frontend to use `origin`/`pivot` terminology
3. Delete `CalibrationSwingResponse`
4. Move scale binning to Reference Layer endpoints

### Impact

Breaking API change - requires frontend coordination.

### Relationship to #4

This unification resolves several #4 issues:
- Eliminates `parent_ids` (replaced by `parent_leg_id`)
- Connects `depth` to `leg.depth`
- Removes `swing_id` from the unified schema
- Deletes the problematic `CalibrationSwingResponse` entirely

**Recommendation:** Do #4 and #5 together in Phase 2.

