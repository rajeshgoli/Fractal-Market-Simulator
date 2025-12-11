# Product Next Steps - Validation Mode Overhaul (Updated)

**Date:** December 11, 2025
**Owner:** Product
**Status:** Approved - Ready for Engineering
**Input:** Architect analysis (`architect_notes_dec11_performance.md`)
**Handoff To:** Engineer

---

## Context Update

Architect completed performance profiling and algorithm audit. **Critical finding:** swing detection has O(N²) complexity, making 16M bar scale infeasible without algorithm rewrite.

This doesn't change the goal—it clarifies the execution path.

---

## Immediate Objective

**Pre-compute swings for ES 1m dataset to enable validation at scale.**

The validation harness operates on a known, fixed dataset. Instead of rewriting the O(N²) algorithm now, we can:
1. Run swing detection once (accept the long runtime)
2. Save computed swings to disk
3. Load pre-computed swings at visualization startup

Algorithm rewrite deferred until generator phase requires runtime detection.

---

## Why This Is Highest Leverage

Pre-computation approach:
- Unblocks validation work immediately (no algorithm rewrite needed)
- Event-Skip Mode becomes feasible (swings already computed → event index is fast)
- 16M bar scale works (load from disk, not compute)
- Simple solution for a known dataset

Algorithm rewrite deferred because:
- Generator is future work
- Validation harness has fixed input data
- Don't over-engineer—solve immediate problem first

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| 150K bar init time | 190s | <10s |
| Algorithm complexity | O(N²) | O(N log N) |
| Event skip latency | N/A | <100ms |
| Events per second (traversal) | N/A | >50 |

---

## Usability Criteria

After this phase, the tool should be:

- **Fast:** Traverse a month's events in <10 minutes (not hours)
- **Clear:** Structure visible at every scale (40-100 candles, not thousands)
- **Reliable:** No state bugs on zoom, pause, layout transitions
- **Responsive:** Skip to next event feels instant (<100ms)

---

## Checkpoint Trigger

**When to invoke Product for fit-for-purpose review:**

After completing Phase 0 + Phase 1 (performance fix + quick wins), schedule user validation session to confirm:
1. Algorithm is fast enough for full dataset
2. Event-Skip feels instant
3. Visual clarity achieved at all scales

---

## Implementation Sequence (Revised)

### Phase 0: Pre-Compute Swing Cache

**Scope:** One-time batch computation for ES 1m dataset

1. Run swing detection on full ES 1m dataset (accept long runtime—run overnight if needed)
2. Serialize computed swings to disk (JSON or pickle)
3. Add loader to SwingStateManager that loads from cache instead of computing

**Gate:** Harness starts in <30 seconds with pre-computed data

### Phase 1: Visualization Improvements (Parallel)

1. **S-Scale Swing Cap** - Show top 5 swings (configurable), toggle for all
2. **Dynamic Bar Aggregation** - 40-60 candles per quadrant
3. **Stability Audit** - State transition review

### Phase 2: Event-Skip Mode

With swings pre-computed, this becomes straightforward:

1. Build EventIndex from loaded swings at startup
2. Binary search jump to next event
3. State fast-forward for intermediate bars (no re-detection needed)

### Phase 3: Integration & Validation

1. Complete stability audit
2. User validation sessions with full ES dataset
3. Document any detection issues found

### Future (Generator Phase)

Algorithm rewrite (O(N²) → O(N log N)) happens here, only when needed:
- Generator requires runtime swing detection
- Pre-computation won't work for dynamic data

---

## Revised Performance Constraints

**Original:** "All algorithms must be O(N)"
**Revised:** "All algorithms must be O(N log N) or better. No O(N²) patterns in hot paths."

Rationale: O(N log N) is acceptable at scale. The goal is "no quadratic," not "strictly linear."

---

## Assumptions and Risks

### Assumptions

1. O(N²) → O(N log N) rewrite is achievable without changing detection semantics
2. Existing test suite will catch regressions
3. 30-60s startup cost for event index is acceptable to user

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Regression in swing detection | Medium | High | Run full test suite, compare outputs |
| Performance target not met | Medium | Medium | Profile iteratively, adjust targets |
| Algorithm rewrite harder than expected | Low | Medium | Fix path is clear per Architect |

---

## Open Questions for Architect

None. Architect's analysis was complete. Ready for Engineer handoff.

---

## Handoff to Engineer

**Scope:** Phase 0 (Pre-Compute Swing Cache) + Phase 1 (Visualization Improvements)

**Phase 0 Deliverables:**
1. Script to run swing detection on full ES 1m dataset and serialize to disk
2. Loader in SwingStateManager to load from cache
3. Pre-computed cache files for ES dataset

**Phase 1 Deliverables:**
1. S-Scale swing cap (top 5 default, configurable)
2. Dynamic bar aggregation (40-60 candles per quadrant)
3. Stability audit findings

**Acceptance Criteria:**
- Harness starts in <30 seconds with pre-computed data
- Visual clarity at all scales
- Existing tests pass

**Then:** Phase 2 (Event-Skip Mode) and user validation session.

---

## What This Is NOT

- Not changing swing detection rules or Fibonacci calculations
- Not adding new features beyond validation tooling
- **Not rewriting the O(N²) algorithm yet**—pre-computation sidesteps this for now
- Algorithm rewrite deferred to generator phase when runtime detection is actually needed
