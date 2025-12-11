# Architect Assessment: Pre-Compute vs Algorithm Rewrite

**Date:** December 11, 2025
**From:** Architect
**To:** Product
**Re:** `product_question_for_architect_dec11.md`
**Status:** Complete

---

## Executive Summary

**Recommendation: Option B (Algorithm Rewrite)**

The pre-compute approach has a fatal flaw for the validation use case: **cache invalidation during active development**. Since validation exists specifically to find and fix issues with swing detection, the algorithm will change during validation. Each change invalidates the cache, requiring another multi-day computation cycle.

---

## Data Reality Check

| Dataset | Bars | Current Init Time (O(N²)) |
|---------|------|--------------------------|
| test.csv | 6,794 | ~30 seconds |
| 5min.csv | 25,950 | ~8 minutes (est.) |
| **es-1m.csv** | **6,033,777** | **~84 hours** (extrapolated) |

The ES 1m dataset is 6M bars, not 16M. Still, at O(N²) scaling, pre-computing once takes approximately **3.5 days**.

---

## Option A Analysis: Pre-Compute and Cache

### Costs

| Factor | Estimate | Notes |
|--------|----------|-------|
| Initial compute | ~84 hours | One-time cost (assuming no changes) |
| Serialized size | ~460MB | 2.3M swings × 200 bytes JSON |
| Deserialization | 2-5 seconds | Fast enough |
| Implementation | 4-8 hours | Serialize/deserialize code, cache format |
| Memory overhead | Same | Swings loaded either way |

### Hidden Cost: Cache Invalidation

The validation harness exists to answer: "Is our swing detection correct?"

When validation reveals issues (expected!), the detection algorithm must change. **Each algorithm change invalidates the cache entirely.**

| Scenario | Cache Re-compute Time |
|----------|----------------------|
| 1 algorithm fix | +84 hours |
| 2 algorithm fixes | +168 hours |
| 3 algorithm fixes | +252 hours |

**Practical reality:** If validation is useful, we will find issues. If we find issues, we must fix them. If we fix them, the cache is worthless.

### When Pre-Compute Makes Sense

Pre-compute is the right choice when:
- The algorithm is **stable and validated** (not our case)
- The data is **fixed and won't change** (partially true)
- Startup time is critical for **production use** (validation is development)

None of these conditions hold for the current validation phase.

---

## Option B Analysis: Algorithm Rewrite

### Costs

| Factor | Estimate | Notes |
|--------|----------|-------|
| Engineering effort | 16-32 hours | 2-4 days focused work |
| Regression testing | 4-8 hours | Test suite exists, 158+ tests |
| Post-fix startup time | <30 seconds | O(N log N) for 6M bars |
| Maintenance burden | None | Algorithm just works |
| Reusability | Full | Required for generator phase |

### Technical Path (Confirmed Feasible)

The O(N²) bottleneck is at `src/legacy/swing_detector.py:219-304`:

```python
# Current: O(H × L × L) where H=highs, L=lows
for high_swing in swing_highs:        # O(H)
    for low_swing in swing_lows:      # O(L)
        for intermediate_low in swing_lows:  # O(L) validation
```

**Fix approach:**
1. Sort swing_highs and swing_lows by bar_index (already the case)
2. Use binary search (`bisect`) to find valid pairing candidates
3. Use sorted array for interval validation (no inner loop)

This reduces to O(N log N) with clear implementation path.

---

## Comparative Analysis

| Factor | Option A (Cache) | Option B (Rewrite) |
|--------|------------------|-------------------|
| Implementation effort | Low (4-8 hrs) | High (16-32 hrs) |
| First startup | Fast (5s) | Fast (<30s) |
| **Algorithm change cost** | **+84 hours each** | **0 (re-run in 30s)** |
| Total cost if 0 fixes | ~88 hours | ~32 hours |
| Total cost if 1 fix | ~172 hours | ~32 hours |
| Total cost if 3 fixes | ~340 hours | ~32 hours |
| Reusability | None | Full |

**Break-even point:** If we expect ANY algorithm changes during validation, Option B is cheaper.

---

## Assessment of Product's Decision Criteria

Product specified:
> - If cache approach is significantly simpler AND fast enough → Option A
> - If cache approach has hidden costs that approach rewrite effort → Option B
> - If close call → Option B (investment carries forward to generator)

**Finding:** Cache approach has hidden costs that **exceed** rewrite effort as soon as any algorithm changes occur. This is not a close call.

---

## Recommendation

**Proceed with Option B: Algorithm Rewrite**

Rationale:
1. **Lower total cost** given expected algorithm iterations during validation
2. **Zero friction** when detection issues are found and fixed
3. **Investment carries forward** to generator phase
4. **No throwaway infrastructure** (cache format, invalidation logic)

### Revised Implementation Sequence

| Phase | Scope | Gate |
|-------|-------|------|
| Phase 0 | **Algorithm rewrite: O(N²) → O(N log N)** | <30s init for 6M bars |
| Phase 1 | Visualization improvements | Swing cap, dynamic agg |
| Phase 2 | Event-Skip Mode | Event index + binary jump |
| Phase 3 | User validation sessions | Feedback loop active |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Regression in swing detection | 158+ existing tests, add specific regression tests |
| Longer than estimated | Algorithm is well-understood, fix path is clear |
| Validation blocked during rewrite | Use test.csv (6.7K bars) for initial validation - works today |

---

## Handoff

**Status:** Assessment complete
**Recommendation:** Option B (Algorithm Rewrite)
**Next Owner:** Product (to confirm direction)
**Artifact Updated:** This document

**Instruction to Product:** Confirm Option B direction. If approved, return to Architect to update `engineer_next_step.md` with rewrite specification.

---

## Review Summary

**Status:** Accepted with recommendation
**Next Step:** Product confirmation of Option B direction
**Owner:** Product
**Updated:** `architect_assessment_precompute_dec11.md`

**Instruction:** Review this assessment and confirm direction. The pre-compute approach has hidden costs that make it more expensive than the algorithm rewrite for the validation use case.
