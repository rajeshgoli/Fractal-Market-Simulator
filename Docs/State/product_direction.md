# Product Direction

**Last Updated:** December 19, 2025 (PM2)
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

Performance target achieved (#158). Reference layer complete (#159). Sibling swing detection complete (#163). Now focused on **DAG visualization** to validate algorithm behavior visually before further iteration.

---

## P0: DAG Visualization Mode

**Status:** BLOCKED — Implementation doesn't match spec. Rework required (#179).
**Epic:** #167
**Rework Issue:** #179

### Problem (Dec 19)

User tested DAG mode. It doesn't work as specified:

| Spec Requirement | Current State |
|------------------|---------------|
| Start from bar 0, build incrementally | Pre-calibrates full window |
| Bar-by-bar progression via playback | Buttons do nothing |
| Legs drawn as lines (origin→pivot) | Horizontal pivot price lines |
| Linger toggle | Not visible (tied to broken playback) |

The tool is not usable. Core value prop — watching the algorithm "think" — is missing.

### What's Needed

1. **Playback from bar 0** — Start empty, step forward, watch DAG construct
2. **Leg visualization as lines** — Connect origin to pivot, not horizontal price lines
3. **Working linger toggle** — Pause on leg lifecycle events

### Next Step

Engineering fixes #179 to match spec in `Docs/Working/DAG_visualization_spec.md`.

### Original Implementation Issues (Complete but Broken)

- [x] #168 — Leg lifecycle events (implemented)
- [x] #169 — DAG state API endpoint (implemented)
- [x] #170 — Linger toggle (implemented but not visible)
- [x] #171 — DAG state panel (implemented)
- [x] #172 — Leg visualization (implemented incorrectly)

---

## Completed: Sibling Swing Detection (#163)

**Status:** Implementation complete. Validation pending.

Implemented orphaned origin tracking with 10% pruning rule. User validation via DAG visualization (#167) will confirm sibling swings (same 0, different 1s) are detected correctly.

---

## Completed: DAG-Based Swing Detection (#158)

**Status:** Complete. 4.06s for 10K bars.

Replaced O(n × k³) algorithm with O(n log k) DAG-based streaming approach. Performance target met.

---

## Completed: Reference Layer (#159)

**Status:** Complete. 580 tests passing.

Implemented separation filtering and size-differentiated invalidation thresholds per Rule 2.2.

**Issue discovered during validation:** Current separation check applies to BOTH 0 and 1, but Rule 4.1 only requires 1 separation. Further refinement: separation check can be removed entirely since DAG pruning already ensures 10% separation. See #163.

---

## Valid Swings Detection Status

From `Docs/Reference/valid_swings.md` — ES as of Dec 18, 2025:

| Label | Structure | Status |
|-------|-----------|--------|
| **L1** | 1=6166, 0=4832 | ✅ Detected |
| **L2** | 1=5837, 0=4832 | 🔄 Pending validation (#163) |
| **L3** | 1=6955, 0=6524 | ✅ Detected |
| **L4** | 1=6896, 0=6524 | 🔄 Pending validation (#163) |
| **L5** | 1=6790, 0=6524 | 🔄 Pending validation (#163) |
| **L6** | 1=6929, 0=6771 | ✅ Detected |
| **L7** | 1=6882, 0=6770 | 🔄 Pending validation (#163) |

#163 implementation complete. Validation pending — DAG visualization (#167) will enable visual confirmation.

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | **Done** (#158) |
| 100K window loads in frontend | **Done** (#158) |
| Valid swings (L1-L7) detected | Implemented (#163) — validation pending |
| Sibling swings with same 0 detected | Implemented (#163) — validation pending |
| Separation check removed (DAG prunes) | Implemented (#163) — validation pending |
| Parent-child relationships correct | **Done** (#158) |
| Visual validation of DAG behavior | Pending #167 |

---

## Checkpoint Trigger

**Invoke Product when:**
- #179 fixed — DAG visualization actually works per spec
- Validation complete — confirm L1-L7 detection status via working DAG tool
- Unexpected detection behavior observed during visual validation

---

## Previous Phase (Archived)

- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete
- #159 Reference layer — Complete
- Ground truth annotator workflow (Dec 15-17) — Superseded
