# Product Direction

**Last Updated:** December 19, 2025 (PM3)
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

DAG visualization working (#179 complete). Validation session confirmed core functionality. Now focused on **pruning refinements** to achieve properly tuned DAG behavior before further iteration.

---

## P0: Pruning & Chart Fixes

Two issues from validation session:

| Issue | Problem | Priority |
|-------|---------|----------|
| #185 | Pruning too aggressive — loses intermediate structure | **High** |
| #186 | Charts ignore timeframe config — both show same data | Medium |

### #185: Recursive 10% Pruning

**Problem:** Current approach (keep one leg) quickly reduces to giant arrow between extremes.

**Solution:**
- During trend: accumulate candidates
- At confirmed pivot: prune to biggest among same-origin candidates
- After direction change: preserve legs from different origins (different structural levels)
- Recursive 10% rule: each leg prunes subtrees <10% of its size
- Result: detailed near active zone, compressed further back

### #186: Chart Timeframe Bug

Both charts show identical data despite different timeframe configs (1H vs 5m). Blocks multi-timeframe validation.

---

## Completed: DAG Visualization Mode (#167)

**Status:** Complete. Validation session Dec 19 confirmed it works.

| Issue | Feature | Status |
|-------|---------|--------|
| #168 | Leg lifecycle events | Done |
| #169 | DAG state API endpoint | Done |
| #170 | Linger toggle | Done |
| #171 | DAG state panel | Done |
| #172 | Leg visualization | Done |
| #179 | Incremental playback from bar 0 | Done |
| #181 | Prune redundant legs on turn | Done |
| #182 | Visualize orphaned origins | Done |

**Refinements identified:** #185 (pruning logic), #186 (chart timeframe)

---

## Completed: Sibling Swing Detection (#163)

**Status:** Implementation complete. Validation via DAG visualization confirmed orphaned origin tracking works.

---

## Completed: DAG-Based Swing Detection (#158)

**Status:** Complete. 4.06s for 10K bars.

---

## Completed: Reference Layer (#159)

**Status:** Complete. 580+ tests passing.

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

Full validation pending #185 fix — need properly tuned DAG to confirm sibling detection.

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | Pending #185 |
| Sibling swings with same 0 detected | Pending #185 |
| Parent-child relationships correct | Done (#158) |
| Visual validation of DAG behavior | Done (#167) |
| Multi-timeframe chart view | Pending #186 |

---

## Checkpoint Trigger

**Invoke Product when:**
- #185 fixed — DAG shows properly tuned structure with multi-level preservation
- L1-L7 validation complete with tuned DAG
- Unexpected detection behavior observed

---

## Previous Phase (Archived)

- #179-#182 DAG visualization refinements — Complete
- #167 DAG visualization epic — Complete
- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete
- #159 Reference layer — Complete
