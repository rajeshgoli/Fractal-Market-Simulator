# Product Response to Architect Performance Assessment

**Date:** December 11, 2025
**From:** Product
**To:** Architect (and Engineer)
**Re:** `architect_notes_dec11_performance.md`

---

## Summary

Architect's analysis is accepted in full. The O(N²) blocker is real and must be addressed before Event-Skip Mode can be implemented. The recommended phased approach is approved.

---

## Answers to Open Questions

### 1. Is 30-60 second pre-compute for event index acceptable?

**Yes.**

User's stated goal is "traverse a month in minutes, not hours." A one-time startup cost of 30-60 seconds is acceptable if it enables instant event jumping thereafter.

Consider:
- Current state: >1 hour to traverse a month
- With pre-compute: 60s startup + 10 minutes traversal = ~11 minutes total
- This is an order of magnitude improvement

### 2. Should swing cap be configurable or fixed 3-5?

**Configurable with 5 as default.**

- Default: 5 swings (per Architect recommendation)
- Power user toggle: show all
- Most recent event swing always visible regardless of cap

### 3. Priority trade-off: If only 2 of (Event-Skip, Dynamic Agg, Swing Cap)?

**Event-Skip + S-Scale Swing Cap.**

Rationale:
- Event-Skip directly addresses "hour+ to traverse month" problem
- Swing Cap directly addresses "33 swings is unmanageable" problem
- Dynamic Aggregation is important but user can mentally adjust for bar density

If we must choose, solve speed and noise first. Clarity can follow.

---

## Accepted Revisions

### Performance Constraint

**Original:** "All algorithms must be O(N)"
**Revised:** "All algorithms must be O(N log N) or better. No O(N²) patterns in hot paths."

This is correct. The goal is no quadratic patterns, not strictly linear.

### Event-Skip Metric

**Original:** "Traverse a month in minutes"
**Revised:** ">50 events/second" or "<100ms skip latency"

Both are acceptable. Suggest using the more intuitive user-facing metric ("traverse month in <10 minutes") externally while using the technical metric (">50 events/second") for engineering gates.

---

## Approved Implementation Sequence (REVISED)

**User input:** Pre-compute swings for known ES 1m dataset instead of rewriting algorithm.

| Phase | Scope | Gate |
|-------|-------|------|
| Phase 0 | Pre-Compute Swing Cache | Harness starts in <30s |
| Phase 1 | Visualization Improvements | Swing cap, dynamic agg, stability audit |
| Phase 2 | Event-Skip Mode | Event index + binary jump |
| Phase 3 | Integration | User validation sessions |
| Future | Algorithm Rewrite | Deferred to generator phase |

**Rationale:** Validation harness has a fixed dataset (ES 1m). Pre-computing once and loading from cache sidesteps O(N²) entirely for this use case. Algorithm rewrite deferred until generator requires runtime detection.

---

## Handoff

- **Updated product spec:** `product_next_steps_dec11_v2.md`
- **Next owner:** Engineer (for Phase 0 + Phase 1)
- **Checkpoint:** After Phase 0 + Phase 1, return to Product for user validation session

The simpler approach unblocks validation work immediately. Proceed with pre-computation.
