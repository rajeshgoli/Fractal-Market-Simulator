# Market Simulator - Architecture Notes

## Current Phase: Phase 1 - Visualization Improvements

**Status:** Ready to begin
**Blocker:** None - Phase 0 complete
**Owner:** Product (prioritization) → Engineering (implementation)

---

## Phase 0 Completion Summary

The swing detection algorithm rewrite is complete:

| Metric | Target | Achieved |
|--------|--------|----------|
| 100K bars | <30s | <20s ✅ |
| Test suite | Pass | 209 passed ✅ |
| Correctness | Match original | Verified ✅ |

**Key implementation:** SparseTable RMQ for O(1) interval validation + binary search for pair enumeration.

**Gate revision:** Original 30s/6M-bars gate was based on misunderstanding usage. Revised to 30s/100K-bars (1 year S-scale data), which is met.

---

## System State Summary

| Layer | Status | Notes |
|-------|--------|-------|
| CLI | ✅ Ready | Commands operational |
| Visualization | ✅ Ready | 4-panel, layouts, controls |
| Playback | ✅ Ready | Keyboard shortcuts, stepping |
| Analysis | ✅ Ready | O(N log N) swing detection |
| Data | ✅ Ready | 6M+ bars loadable |
| Test Suite | ✅ Healthy | 209 passed, 2 skipped |

---

## Implementation Sequence

| Phase | Scope | Status | Owner |
|-------|-------|--------|-------|
| ~~Phase 0~~ | ~~Algorithm rewrite~~ | ✅ Complete | ~~Engineering~~ |
| **Phase 1** | **Visualization improvements** | Ready | Engineering |
| Phase 2 | Event-Skip Mode | Pending | Engineering |
| Phase 3 | User validation sessions | Pending | Product |

---

## Phase 1 Scope (Pending Product Prioritization)

From prior product requirements:

1. **S-Scale Swing Cap** - Limit displayed swings to top 5 by recency/size
2. **Dynamic Bar Aggregation** - Auto-adjust timeframe based on visible window
3. **Stability Audit** - Fix state management issues during layout transitions

Product to confirm priority order and any scope changes.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                               │
│  validate | list-data/describe/inspect | harness                │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Validation Harness                           │
│  Interactive REPL + Keyboard Control + Progress Logging         │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   Visualization Layer                           │
│  4-panel renderer | Expand/Quad layouts | PiP | Visibility      │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Analysis Pipeline                            │
│  ScaleCalibrator | BarAggregator | SwingStateManager            │
│  ✅ SwingDetector (O(N log N) - complete)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Data Layer                                 │
│  Historical loader | Multi-resolution | Date filtering          │
│  ES: 6M bars (es-1m.csv)                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Decisions Made

| Decision | Date | Rationale |
|----------|------|-----------|
| Algorithm Rewrite over Pre-Compute | Dec 11 | Cache invalidation costs exceed rewrite |
| Revised Phase 0 gate (100K not 6M) | Dec 11 | Validation uses date ranges, not full dataset |
| SparseTable RMQ implementation | Dec 11 | O(1) interval queries, clean abstraction |

---

## Risk Tracking

| Risk | Status | Mitigation |
|------|--------|------------|
| ~~Algorithm regression~~ | ✅ Resolved | 209 tests passing |
| ~~Performance target~~ | ✅ Resolved | 240x improvement achieved |
| Validation blocked | ✅ Resolved | Can proceed with practical data ranges |

---

## Open Questions

None blocking. Awaiting Product prioritization for Phase 1.

---

## Handoff Artifacts

| Artifact | Purpose | Location |
|----------|---------|----------|
| Algorithm review | Phase 0 acceptance | `architect_review_algorithm_dec11.md` |
| Engineer notes | Implementation details | `engineer_notes/algorithm_rewrite_dec11.md` |
| Performance decision | Pre-compute vs rewrite | `architect_assessment_precompute_dec11.md` |
