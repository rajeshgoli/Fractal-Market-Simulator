# Product Question for Architect: Pre-Compute vs Algorithm Rewrite

**Date:** December 11, 2025
**From:** Product
**To:** Architect
**Status:** Awaiting Assessment

---

## Context

User proposed an alternative to the O(N²) algorithm rewrite: pre-compute swings for the known ES 1m dataset once, serialize to disk, and load at visualization startup.

Rationale: Validation harness operates on fixed data. Why rewrite the algorithm now when we can sidestep the problem entirely?

---

## Question

**Which approach is actually cheaper for the validation use case?**

### Option A: Pre-Compute and Cache

1. Run swing detection once on full ES 1m dataset (accept long runtime)
2. Serialize computed swings to disk
3. Load from cache at startup

**Unknowns:**
- What's the serialized size for 16M bars worth of swings?
- Deserialization time for that data volume?
- Memory footprint when loaded?
- Cache invalidation complexity if detection logic changes?

### Option B: Algorithm Rewrite Now

1. Rewrite O(N²) → O(N log N) swing detection
2. Run detection at startup (fast enough with fixed algorithm)
3. No caching layer needed

**Knowns from your prior analysis:**
- Fix path is clear (sorted arrays + binary search)
- Test suite exists for regression detection
- Estimated effort: "High" but achievable

---

## Assessment Requested

| Factor | Option A (Cache) | Option B (Rewrite) |
|--------|------------------|-------------------|
| Implementation effort | ? | High |
| Startup time | ? (deserialize) | ? (O(N log N) compute) |
| Memory overhead | ? | Current |
| Maintenance burden | Cache invalidation | None |
| Reusability for generator | None | Full |

Please assess and recommend. If Option B is comparable or cheaper in total cost, we should just do it now rather than building throwaway caching infrastructure.

---

## Decision Criteria

- If cache approach is significantly simpler AND fast enough → Option A
- If cache approach has hidden costs that approach rewrite effort → Option B
- If close call → Option B (investment carries forward to generator)
