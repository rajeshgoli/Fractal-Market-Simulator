# Product Direction

**Last Updated:** December 25, 2025
**Owner:** Product

---

## Current Objective

**Wire up Reference Layer to filter DAG output into valid trading references per north star rules.**

---

## Current Phase: Reference Layer Design

DAG validation complete. L1-L7 detected correctly. Now designing the Reference Layer — a thin filter over DAG output that identifies valid trading references.

**Status:** Spec drafted at `Docs/Working/reference_layer_spec.md`. Under review.

**Key insight from validation:** Reference swings are **bear legs** in DAG terminology (HIGH before LOW = bullish reference). The DAG correctly tracks these with origin breach status.

---

## Completed: L1-L7 Validation (Dec 25, 2025)

**Status:** Complete. All 7 reference swings detected correctly.

Config used: `origin_time_threshold=0.02`, `origin_range_threshold=0.02`, `max_turns_per_pivot_raw=10`

| Label | Expected | Found | Status |
|-------|----------|-------|--------|
| **L1** | origin=6166, pivot=4832 | origin=6166.50, pivot=4832.00 | BREACHED |
| **L2** | origin=5837, pivot=4832 | origin=5837.25, pivot=4832.00 | BREACHED |
| **L3** | origin=6955, pivot=6524 | origin=6953.75, pivot=6525.00 | **intact** |
| **L4** | origin=6896, pivot=6524 | origin=6909.50, pivot=6525.00 | BREACHED |
| **L5** | origin=6790, pivot=6524 | origin=6801.50, pivot=6525.00 | BREACHED |
| **L6** | origin=6929, pivot=6771 | origin=6928.75, pivot=6771.50 | BREACHED |
| **L7** | origin=6882, pivot=6770 | origin=6892.00, pivot=6771.50 | BREACHED |

**Key findings:**
- All references are bear legs (origin=HIGH, pivot=LOW)
- Multiple siblings exist at shared pivots (e.g., L1/L2 share pivot 4832)
- Breach status correctly reflects price action (L3 intact since price < 6953)
- DAG structural detection is solid

---

## Completed: Self-Contained Playback Setup (#324)

**Status:** Complete. All 7 sub-issues (#325-#331) implemented.

| Feature | Status |
|---------|--------|
| **File selection** | Done — Dropdown picks CSV from `test_data/` |
| **Start date** | Done — Date picker instead of CLI offset |
| **Session persistence** | Done — App loads last session automatically |
| **Process Till** | Done — Fast-forward to specific CSV index with progress |

**Usage:** `python -m src.replay_server.main` (no args needed)

---

## Completed: Previous Phases

- #347-#349 Turn ratio UX, inner structure removal, frontend cleanup — Complete
- #324 Self-contained playback — Complete
- #250 Hierarchy exploration mode — Complete
- #241 Impulsiveness & spikiness scores — Complete
- #167 DAG visualization mode — Complete
- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete (4.06s for 10K bars)

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | **Done** (Dec 25) |
| Sibling swings with same pivot detected | **Done** (Dec 25) |
| Parent-child relationships correct | Done (#158) |
| Visual validation of DAG behavior | Done (#167) |
| Multi-timeframe chart view | Done (#186) |
| Reference Layer filters valid references | Pending |

---

## Next: Reference Layer

**Purpose:** Filter DAG legs to identify valid trading references per north star rules.

**Key capabilities needed:**
1. Location check (price between 0 and 2 in reference frame)
2. Scale classification (S/M/L/XL by range percentile)
3. Scale-dependent invalidation tolerance (small: 0%, big: 15%/10%)
4. Salience ranking (big/impulsive/early vs recent)

**Spec:** `Docs/Working/reference_layer_spec.md`

---

## Checkpoint Trigger

**Invoke Product when:**
- Reference Layer spec approved
- Reference Layer implementation complete
- Unexpected behavior observed during testing
