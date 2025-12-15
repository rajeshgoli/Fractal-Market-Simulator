# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-15-6: Too Small and Subsumed Filters

**From:** Product
**To:** Architect
**Date:** December 15, 2025

### Context

15 annotation sessions complete (10 ver1 + 5 ver2). Max_rank filter (#56) implemented and helped but didn't address root cause.

**Ver2 Session Data (post-max_rank):**

| Category | Count | % of True FPs |
|----------|-------|---------------|
| too_small | 39 | **65%** |
| subsumed | 17 | **28%** |
| too_distant | 2 | 3% |
| counter_trend | 1 | 2% |

**93% of remaining FPs are too_small or subsumed.** Pattern stable across all sessions.

### User Direction

"We should address too small swings before continuing as that's the cause of max noise."

"Subsumed category is not picking good highs or lows. You can pick something that 'stands out' from the other highs rather than highs in noise."

### Deliverable 1: Too Small Filter (P0)

**User-proposed heuristics (starting point):**
1. Bar count threshold: Discard if swing spans < 5% of range bars
2. Volatility threshold: Discard if swing magnitude < 3x median candle size

**Request:** Analyze annotation data empirically to derive thresholds. User explicitly said "I'm making this up — use data."

### Deliverable 2: "Stands Out" Heuristic (P1)

**Pattern from better_reference data:**
- Detector finds local extrema near important levels
- User picks extrema that are **distinctly higher/lower** than adjacent points
- "Highest point in noisy region" vs "point that stands out from surrounding highs"

**Potential approaches:**
- Distance from nearest higher high (for tops) / lower low (for bottoms)
- Percentile rank within local window
- Price delta from surrounding extrema

**Request:** Analyze better_reference coordinates from annotation sessions. Quantify "stands out" pattern. Propose heuristic.

### Data Available

- 15 annotation sessions in `annotation_sessions/`
- `better_reference` coordinates captured for subsumed dismissals
- Session files have bar indices and prices for both detector's choice and user's choice

### Priority

**P0** — Too small is 65% of noise. Blocking annotation velocity.
**P1** — Subsumed is 28% of noise. Harder to specify but clear in visual review.
