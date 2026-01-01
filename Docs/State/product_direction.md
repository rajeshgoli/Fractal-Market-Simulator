# Product Direction

**Last Updated:** December 31, 2025
**Owner:** Product

---

## Current Objective

**Add observability to Reference Layer before building Structure Panel (P3).**

---

## Current Phase: Reference Observation (#400)

Reference Layer P1 (backend + Levels at Play UI) and P2 (Fib Level Interaction) complete. Before building P3 (Structure Panel + Confluence), adding observability to understand filtering behavior.

**Epic:** #400 Reference Observation Mode
- #401 Backend: Filter Status API
- #402 Frontend: Observation UI

**Spec:** `Docs/Working/reference_observation_spec.md`

**Key features:**
- "Show Filtered" toggle in left nav (Levels at Play view)
- Filtered legs highlighted, valid refs muted when toggle on
- Filter stats panel (counts by reason, pass rate)
- Explanation panel shows why each leg was filtered

---

## Completed: Reference Layer Phase 2 (Dec 31, 2025)

**Status:** Complete. Fib Level Interaction (5 issues, #388-#393).

| Component | Status |
|-----------|--------|
| get_active_levels() backend | Complete |
| Hover preview UI | Complete |
| Click-to-stick | Complete |
| Color-coding by source | Complete |
| Sticky state persistence | Complete |

---

## Completed: Reference Layer Phase 1 (Dec 31, 2025)

**Status:** Complete. Backend + Levels at Play UI (27 issues, #361-#387).

| Component | Status |
|-----------|--------|
| ReferenceConfig | Complete |
| ReferenceSwing/ReferenceState | Complete |
| Scale classification (S/M/L/XL) | Complete |
| Location computation | Complete |
| Formation tracking | Complete |
| Fatal breach detection | Complete |
| Salience scoring | Complete |
| Levels at Play view | Complete |

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

---

## Completed: Previous Phases

- #361-#387 Reference Layer Phase 1 — Complete
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
| Valid swings (L1-L7) detected | Done (Dec 25) |
| Sibling swings with same pivot detected | Done (Dec 25) |
| Parent-child relationships correct | Done (#158) |
| Visual validation of DAG behavior | Done (#167) |
| Multi-timeframe chart view | Done (#186) |
| Reference Layer filters valid references | **Done** (#361-#387) |
| Reference Layer observability | Pending (#400) |

---

## Roadmap

1. ✅ **P2: Fib Level Interaction** — Complete (#388-#393)
2. ⏳ **Reference Observation** (#400) — Current
3. **P3: Structure Panel + Confluence** — Level analysis
4. **P4: Level Crossing Tracking** — Opt-in crossing events

---

## Checkpoint Trigger

**Invoke Product when:**
- Reference Observation epic complete
- Unexpected behavior observed during testing
- Ready to start P2 (Fib Level Display)
