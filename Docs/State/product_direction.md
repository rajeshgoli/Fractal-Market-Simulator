# Product Direction

**Last Updated:** December 20, 2025 (PM4)
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

DAG visualization complete (#167, #185, #186 all done). Validation session Dec 19-20 uncovered a **fundamental causality bug** in leg creation that must be fixed before L1-L7 validation can proceed.

---

## P0: Data Integrity Bugs

| Issue | Problem | Priority |
|-------|---------|----------|
| #189 | Same-bar legs violate temporal causality | **Blocking** |
| #192 | Leg bar indices don't match actual price locations | **Blocking** |

### #189: Same-Bar Leg Creation

**Problem:** `_process_type1()` creates legs where both `pivot_index` and `origin_index` are the same bar. This claims to know H→L or L→H ordering within a single candle — which is unknowable from OHLC data.

**Root cause:** After any Type 2 bar, both pending pivots have the same `bar_index`. When the next bar is Type 1 (inside bar), both leg-creation conditions pass, creating same-bar legs.

**Fix:** Use strict inequality in `_process_type1()` — only create legs when pending pivots are from different bars.

### #192: Bar Index Mismatch

**Problem:** Leg objects show correct prices but wrong bar indices. Example at bar 45:
- `pivot_price: 4426.50` at `pivot_index: 37` — but bar 37's low is 4432.00
- `origin_price: 4434.00` at `origin_index: 36` — but bar 36's high is 4435.25

The prices 4426.50 and 4434.00 exist in the data, just not at those bar indices.

**Root cause:** Running extremas are tracked correctly as prices, but bar indices aren't updated when extrema values change.

**Fix:** Ensure pivot_index and origin_index always point to the bar where the current price actually occurred.

---

## Completed: Pruning & Chart Fixes

| Issue | Problem | Status |
|-------|---------|--------|
| #185 | Recursive 10% pruning | ✅ Done |
| #186 | Per-chart timeframe aggregation | ✅ Done |

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

Full validation blocked by #189 and #192 — must fix data integrity bugs before trusting leg/swing detection.

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | Blocked by #189, #192 |
| Sibling swings with same 0 detected | Blocked by #189, #192 |
| Parent-child relationships correct | Done (#158) |
| Visual validation of DAG behavior | Done (#167) |
| Multi-timeframe chart view | Done (#186) |
| Temporal causality enforced | Blocked by #189 |
| Bar indices match prices | Blocked by #192 |

---

## Checkpoint Trigger

**Invoke Product when:**
- #189 and #192 fixed — data integrity restored
- L1-L7 validation complete
- Unexpected detection behavior observed

---

## Previous Phase (Archived)

- #179-#182 DAG visualization refinements — Complete
- #167 DAG visualization epic — Complete
- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete
- #159 Reference layer — Complete
