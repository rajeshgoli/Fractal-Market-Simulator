# Product Direction

**Last Updated:** December 20, 2025 (PM4)
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

Validation session Dec 19-20 uncovered a structural bug in pivot tracking. Now focused on **fixing #193** before further validation.

---

## P0: Pivot Mismatch Bug

| Issue | Problem | Priority |
|-------|---------|----------|
| #193 | Bear leg pivot doesn't match bull leg origin at swing extrema | **P0** |

### #193: Pending Pivot Overwrite Bug

**Problem:** When a bull leg terminates at a swing high (e.g., 4436.75), the subsequent bear leg should start from that same extrema. Currently, the pending pivot is unconditionally overwritten by each bar's high, so bear legs start from a later, lower high (e.g., 4435.25).

**Root cause:** In `hierarchical_detector.py`, pending pivots are overwritten on every bar type:
```python
self.state.pending_pivots['bear'] = PendingPivot(
    price=bar_high, bar_index=bar.index, ...
)
```

**Fix direction:** Only update pending pivot if new extrema is more extreme (higher high for bear pivot, lower low for bull pivot).

---

## Completed: DAG Visualization Mode (#167)

**Status:** Complete. Validation session Dec 19-20 confirmed it works.

| Issue | Feature | Status |
|-------|---------|--------|
| #185 | Recursive 10% pruning | Done |
| #186 | Per-chart timeframe aggregation | Done |
| #168-#172 | DAG state API, panel, visualization | Done |
| #179-#182 | Incremental playback, pruning, orphans | Done |

---

## Completed: Previous Phases

- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete (4.06s for 10K bars)
- #159 Reference layer — Complete

---

## Valid Swings Detection Status

From `Docs/Reference/valid_swings.md` — ES as of Dec 18, 2025:

| Label | Structure | Status |
|-------|-----------|--------|
| **L1** | 1=6166, 0=4832 | Detected |
| **L2** | 1=5837, 0=4832 | Pending validation |
| **L3** | 1=6955, 0=6524 | Detected |
| **L4** | 1=6896, 0=6524 | Pending validation |
| **L5** | 1=6790, 0=6524 | Pending validation |
| **L6** | 1=6929, 0=6771 | Detected |
| **L7** | 1=6882, 0=6770 | Pending validation |

Full validation blocked by #193 — pivot mismatch affects all swing structure.

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | Blocked by #193 |
| Sibling swings with same 0 detected | Blocked by #193 |
| Parent-child relationships correct | Done (#158) |
| Visual validation of DAG behavior | Done (#167) |
| Multi-timeframe chart view | Done (#186) |

---

## Checkpoint Trigger

**Invoke Product when:**
- #193 fixed — pivot mismatch resolved
- L1-L7 validation complete
- Unexpected detection behavior observed

---

## Previous Phase (Archived)

- #185, #186 DAG refinements — Complete
- #167 DAG visualization epic — Complete
