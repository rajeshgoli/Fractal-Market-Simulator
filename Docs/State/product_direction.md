# Product Direction

**Last Updated:** December 13, 2025
**Owner:** Product

---

## Current Objective

**Complete Review Mode UI, then run first validation session with historical data.**

The ground truth annotation tool backend is complete. Review Mode (3-phase feedback workflow) is implemented but has no frontend. Once UI is complete, we can conduct the first real validation session.

---

## Why This Is Highest Leverage

The swing detection algorithm is the foundation of everything that follows (behavioral modeling, data generation). Validation must be rigorous:

1. **Annotation** captures expert ground truth (what swings *should* be detected)
2. **Comparison** measures algorithm accuracy (matches, false positives, false negatives)
3. **Review Mode** collects structured feedback (why misses happen, patterns in errors)

Without Review Mode UI, we can annotate but can't complete the feedback loop. The algorithm improvement cycle is broken.

---

## Success Criteria

| Metric | Target | Current |
|--------|--------|---------|
| Annotation workflow | Functional | Achieved |
| Comparison analysis | Functional | Achieved |
| Review Mode workflow | All 3 phases usable | Backend complete, no UI |
| First validation session | Complete with feedback | Pending |

---

## P2: Annotation UX (Deferred)

### Zoom/Pan for S-Scale

**Problem:** Snap is finicky at S-scale. May need horizontal (time) and vertical (price) zoom plus pan.

| Phase | Status | Notes |
|-------|--------|-------|
| Ground Truth MVP | Complete | Two-click annotation, cascading scales |
| UX Polish | Complete | Snap-to-extrema, keybindings, export |
| Review Mode Backend | Complete | Models, storage, controller, API endpoints |
| **Review Mode UI** | In Progress | Frontend for 3-phase workflow |
| First Validation Session | Pending | After UI complete |
| Algorithm Iteration | Pending | Based on validation feedback |

---

## Usability Criteria

The annotation + review tool should be:
- **Efficient:** Annotate a window in <5 minutes
- **Accurate:** Two-click annotation snaps to extrema precisely
- **Complete:** Full loop from annotation through structured feedback
- **Exportable:** Raw data and analysis available for algorithm tuning

---

## Delivered (This Cycle)

**Invoke Product when:**
- Review Mode UI is complete
- First validation session is ready to begin
- Validation reveals significant algorithm issues requiring direction change

---

## Deferred

### Assumptions
1. Review Mode UI is straightforward (standard web forms, no complex interactions)
2. Comparison matching tolerance (10%) is reasonable starting point
3. User available for validation once tooling is complete

### Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Algorithm needs significant rework | Medium | Validation will reveal patterns |
| UI takes longer than expected | Low | Backend API is clean |
| Review workflow too tedious | Low | Can skip phases if not useful |

---

## Session Context (for next conversation)

**Where we are:** Tooling complete. Ground truth annotator with Review Mode and session flow is production-ready. Codebase cleaned up (~14,500 lines removed).

**What's next:**
1. Run annotation sessions to collect ground truth data
2. Analyze Review Mode feedback for patterns
3. Use patterns to refine detection rules
4. Iterate: better rules → cleaner detections → validate at scale

After validation establishes confidence in detection foundations:
- Reverse analytical process to generate realistic price data
- Simulate swing formation according to validated rules
- Validated detection = trusted generator inputs
