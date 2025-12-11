# Product Direction

**Last Updated:** December 11, 2025
**Owner:** Product

---

## Current Objective

**Complete Phase 2 stability fixes, then run user validation sessions.**

The visualization harness is functionally complete. Detection logic is validated as correct. Remaining work is stability polish before expert validation.

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Init time (150K bars) | <10s | Achieved |
| Algorithm complexity | O(N log N) | Achieved |
| Event skip latency | TBD | <100ms |
| Traversal speed | TBD | Month in <10 min |

---

## Usability Criteria

The tool should be:
- **Fast:** Traverse a month's events in <10 minutes
- **Clear:** 40-60 candles per quadrant, structure visible
- **Reliable:** No state bugs on zoom, pause, layout transitions
- **Responsive:** Skip to next event feels instant (<100ms)

---

## Implementation Sequence

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0: Algorithm rewrite | Complete | O(N log N) achieved |
| Phase 1: Visualization | Complete | Swing cap, dynamic aggregation |
| **Phase 2: Stability** | In Progress | Thread safety done, needs review |
| Phase 3: Validation | Pending | After stability complete |

---

## Checkpoint Trigger

**When to invoke Product:**
- After Phase 2 complete
- Before user validation sessions
- After first complete session with historical data

---

## Assumptions and Risks

### Assumptions
1. Thread safety fixes resolve observed state bugs
2. Event-skip mode is straightforward with pre-computed swings
3. User will validate after stability fixes

### Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| More stability issues surface | Medium | Thorough testing |
| Event-skip harder than expected | Low | Architecture supports it |

---

## Future: Generator Phase

After validation establishes confidence in detection foundations:
- Reverse analytical process to generate realistic price data
- Simulate swing formation according to validated rules
- Algorithm rewrite already complete, ready for runtime detection
