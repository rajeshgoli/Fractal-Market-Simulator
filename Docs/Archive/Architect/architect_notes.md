# Market Simulator - Architecture Notes

## Current Phase: Phase 2 - Stability (Continued)

**Status:** In progress - Priority 1 complete, Priority 2 ready
**Blocker:** None
**Owner:** Engineering

---

## System State Summary

| Layer | Status | Notes |
|-------|--------|-------|
| CLI | Ready | Commands operational |
| Visualization | Ready | Thread-safe cached state, swing cap, dynamic aggregation |
| Playback | Ready | Keyboard shortcuts, stepping |
| Analysis | Ready | O(N log N) swing detection |
| Data | Ready | 6M+ bars loadable |
| Test Suite | Healthy | 227 passed, 2 skipped |

---

## Implementation Sequence

| Phase | Scope | Status | Owner |
|-------|-------|--------|-------|
| ~~Phase 0~~ | ~~Algorithm rewrite~~ | Complete | ~~Engineering~~ |
| ~~Phase 1~~ | ~~Visualization improvements~~ | Complete | ~~Engineering~~ |
| **Phase 2** | **Stability fixes** | In Progress | Engineering |
| Phase 3 | User validation sessions | Pending | Product |

---

## Phase 2 Progress

### ✅ Priority 1: Thread Safety (Complete)

Implemented thread-safe cached state access:
- Added `threading.RLock` to protect `_cached_active_swings`
- All cache writes/reads wrapped in lock context
- Public `get_cached_swings_copy()` accessor for external callers
- 7 new tests including concurrent access validation

**Issues Resolved:**
- Layout Transition State Loss (HIGH) ✅
- Keyboard Handler State Sync (MEDIUM) ✅

### 🎯 Priority 2: Pause/Resume Consistency (Next)

**Issue:** Race conditions between UI thread and playback thread cause incorrect state display.

**Implementation Approach:**
- Derive state from threading events (single source of truth)
- Remove redundant state enum assignments in `PlaybackController`
- State property should inspect `_pause_requested` and `_stop_event` directly

### Priority 3: Event Coalescing (Deferred)

**Issue:** Events lost during high-speed frame skipping.

Lower priority - can proceed to validation without this fix.

---

## Recent Decisions

| Decision | Date | Rationale |
|----------|------|-----------|
| RLock over Lock | Dec 11 | Supports potential recursive acquisition |
| Shallow copy sufficient | Dec 11 | Swings are immutable after creation |
| Public accessor pattern | Dec 11 | Clean API for external thread access |

---

## Architecture Diagram

```
                         CLI Layer
  validate | list-data/describe/inspect | harness

                    Validation Harness
  Interactive REPL + Keyboard Control + Progress Logging

                   Visualization Layer
  4-panel renderer | Expand/Quad layouts | PiP | Visibility
  Swing Cap (5/scale) | Dynamic Aggregation (40-60 candles)
  [NEW] Thread-safe cached state (RLock)

                    Analysis Pipeline
  ScaleCalibrator | BarAggregator | SwingStateManager
  SwingDetector (O(N log N) - complete)

                      Data Layer
  Historical loader | Multi-resolution | Date filtering
  ES: 6M bars (es-1m.csv)
```

---

## Risk Tracking

| Risk | Status | Mitigation |
|------|--------|------------|
| ~~Thread safety issues~~ | ✅ Resolved | RLock + accessor pattern |
| Pause/resume race conditions | Active | Phase 2 Priority 2 |
| Visual artifacts at high speed | Monitored | Phase 2 Priority 3 (deferred) |

---

## Gate for Validation Sessions

Before proceeding to Phase 3 (user validation):

| Requirement | Status |
|-------------|--------|
| Thread safety | ✅ Complete |
| Pause/resume consistency | 🎯 Next |
| No crashes during layout toggle | ✅ Resolved |

Pause/resume consistency is recommended but not strictly required for validation. Engineering may proceed to validation after Priority 2 or defer if timeline is tight.

---

## Handoff Artifacts

| Artifact | Purpose | Location |
|----------|---------|----------|
| Thread safety review | Phase 2.1 acceptance | `architect_notes_appendix.md` |
| Engineer next step | Priority 2 instruction | `engineer_next_step.md` |
| Stability audit | Original roadmap | `engineer_notes/stability_audit_dec11.md` |
