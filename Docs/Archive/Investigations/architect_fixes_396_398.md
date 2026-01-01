# Architect Fixes

Status of architectural cleanup work.

## Completed (#396 Phases 1-2d)

| Item | Description | Status |
|------|-------------|--------|
| #1 | Rename `ground_truth_annotator` → `replay_server` | ✅ Complete |
| #4a | Remove `swing_id` vestiges | ✅ Complete |
| #4b | Remove `LevelCrossEvent` vestiges | ✅ Complete |
| #4c | Remove `recently_invalidated` dead field | ✅ Complete |
| #4d | Connect `depth` to `leg.depth`, replace `parent_ids` with `parent_leg_id` | ✅ Complete |

---

## Remaining (Tracked in #398)

### Phase 1: Schema Unification

**Problem:** Two schemas (`CalibrationSwingResponse` and `DagLegResponse`) represent the same Leg.

| Field | CalibrationSwingResponse | DagLegResponse |
|-------|-------------------------|----------------|
| ID | `id` | `leg_id` |
| Prices | `high_price`, `low_price` | `origin_price`, `pivot_price` |
| Hierarchy | `parent_leg_id` (now correct) | `parent_leg_id` |
| Fibs | `fib_0`, `fib_0382`, etc. | ❌ none |
| Scale | `scale` (S/M/L/XL) | ❌ none |

**Tasks:**
- [ ] Create unified `LegResponse` schema using origin/pivot terminology
- [ ] Update frontend to use `origin`/`pivot` instead of `high`/`low`
- [ ] Delete `CalibrationSwingResponse`
- [ ] Move scale/rank to Reference Layer endpoints

### Phase 2: Router Split

**Problem:** `routers/replay.py` is 2074 lines mixing 6+ endpoint domains.

**Tasks:**
- [ ] Extract `_replay_cache` to `cache.py` module
- [ ] Create `routers/dag.py`, `reference.py`, `config.py`, `feedback.py`
- [ ] Extract helper functions to `helpers/` subdirectory

### Phase 3: Remaining Cleanup

- [ ] Remove tombstone comments (`# Swing hierarchy removed (#301)`)
- [ ] Rename `largest_swing_id` → `largest_leg_id` in TreeStatistics
- [ ] Fix docstring in leg_detector.py (references removed `swing_id`)

---

## Low Priority (Deferred)

### Naming Cleanup

- `DetectionConfig` rename already done ✅
- `SwingEvent` → `DetectionEvent` (deferred)
- Keep `src/swing_analysis/` — valid domain term

### Inline models.py

- Can inline `models.py` into `storage.py` (2 small dataclasses)
- Low priority — separation doesn't hurt anything
