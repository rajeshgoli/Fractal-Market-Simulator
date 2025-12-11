# Architect Analysis: Performance Assessment & Feasibility Review

**Date:** December 11, 2025
**Owner:** Architect
**Status:** Complete - Return to Product
**Input:** `Docs/Product/Tactical/product_next_steps_dec11.md`

---

## Executive Summary

**Overall Assessment: CONCERNS IDENTIFIED - Architectural changes required before implementation**

The product requirements are achievable, but the current architecture has **critical performance bottlenecks** that must be addressed first. The swing detection algorithm exhibits O(N²) or worse complexity, making it unsuitable for the 16M bar target without significant refactoring.

| Requirement | Feasibility | Risk Level | Notes |
|-------------|-------------|------------|-------|
| Dynamic Bar Aggregation | ✅ Feasible | Low | Current aggregator supports this |
| Event-Skip Mode | ⚠️ Feasible with changes | Medium | Requires pre-computed event index |
| S-Scale Swing Cap | ✅ Feasible | Low | Simple filtering logic |
| Stability Audit | ✅ Feasible | Low | Isolated state management review |
| 16M Bar Scale | ❌ NOT feasible currently | **CRITICAL** | O(N²) swing detection blocks this |

---

## Profiling Results

### Test Configuration
- **Data:** ES 1-minute bars (150,000 bars tested)
- **Hardware:** Development machine
- **Date:** December 11, 2025

### Component Performance

| Component | Time | Rate | Complexity | Assessment |
|-----------|------|------|------------|------------|
| Data Loading (CSV) | 10,046ms | - | O(N) | Acceptable |
| DataFrame to Bars | 1,689ms | 88,816/sec | O(N) | Acceptable |
| Bar Aggregation Init | 776ms | 193,000/sec | O(N × T) | Acceptable |
| Scale Calibration | 87ms | - | O(N) | Acceptable |
| **SwingStateManager Init** | **189,836ms** | **53/sec** | **O(N²+)** | **CRITICAL BOTTLENECK** |
| Per-Bar Update | 0.01ms | 100,000/sec | O(S × L) | Excellent |
| Event Detection (isolated) | 0.02ms | 50,000/sec | O(S × L) | Excellent |

### Swing Detection Scaling Analysis

| Bar Count | Time (ms) | Rate (bars/sec) | Scaling Factor |
|-----------|-----------|-----------------|----------------|
| 100 | 10.5 | 9,527 | baseline |
| 500 | 72.1 | 6,936 | 6.9x time, 5x data |
| 1,000 | 212.8 | 4,700 | 20x time, 10x data |
| 5,000 | **25,291** | **198** | **2,400x time, 50x data** |

**Conclusion:** Swing detection is **O(N²) or worse**. At 16M bars, this would take **days** to initialize.

---

## Algorithm Complexity Audit

### ❌ CRITICAL: Swing Detector (`src/legacy/swing_detector.py`)

**Location:** Lines 219-304
**Pattern:** Nested O(N²) loops

```python
# Bull References: O(H * L * V) where H=highs, L=lows, V=validation
for high_swing in swing_highs:           # O(H) - grows with N
    for low_swing in swing_lows:         # O(L) - grows with N
        # ...
        for intermediate_low in swing_lows:  # O(L) validation
```

With 1,000 bars producing ~200 highs and ~180 lows, the pairing alone is 200 × 180 = 36,000 iterations. With validation, this becomes 36,000 × 180 = **6.5 million** iterations.

**Recommended Fix:** Pre-sort swings by timestamp and use binary search for interval queries, reducing to O(N log N).

---

### ⚠️ HIGH: SwingStateManager `_detect_new_swings()` (`src/analysis/swing_state_manager.py`)

**Location:** Lines 262-317
**Pattern:** Repeated DataFrame creation + O(N²) detector call

```python
def _detect_new_swings(self, scale: str, timeframe: int):
    # ...
    recent_bars = all_bars[-100:] if len(all_bars) > 100 else all_bars

    df_data = []
    for bar in recent_bars:  # O(100) per call
        df_data.append({...})

    df = pd.DataFrame(df_data)  # DataFrame creation overhead
    swing_result = detect_swings(df, ...)  # O(N²) call
```

**Issues:**
1. Creates new DataFrame every bar update (4 scales × every bar)
2. Calls O(N²) swing detector repeatedly
3. Pandas DataFrame overhead dominates small-N performance

**Recommended Fix:**
- Cache swing detection results
- Incremental swing detection (detect only new swings, not recompute all)
- Use numpy arrays instead of pandas for inner loops

---

### ⚠️ MEDIUM: Bar Aggregator Memory (`src/analysis/bar_aggregator.py`)

**Location:** Lines 68-82
**Pattern:** O(N × T) memory for mappings

```python
# For 1m timeframe, creates N-entry mapping dict
self._source_to_agg_mapping[1] = {i: i for i in range(len(self._source_bars))}
```

**At 16M bars:** 6 timeframes × 16M entries × ~50 bytes/entry = **~5GB memory**

**Recommended Fix:** Use sparse mappings or lazy computation for 1m timeframe (1:1 mapping doesn't need explicit storage).

---

### ✅ OK: Event Detector (`src/analysis/event_detector.py`)

**Complexity:** O(S × L) per bar where S=active swings, L=levels per swing
**Measured:** 0.02ms per bar with 10 swings × 7 levels
**Assessment:** Acceptable, scales linearly with swing count

---

### ✅ OK: Visualization Renderer (`src/visualization/renderer.py`)

**Pattern:** O(V) per frame where V=visible bars (max 100)
**Mitigation:** Frame skipping at 16 FPS, sliding window limits
**Assessment:** Acceptable with current mitigations

---

## Requirement Feasibility Assessment

### 1. Dynamic Bar Aggregation ✅ FEASIBLE

**Current State:** `BarAggregator` pre-computes all standard timeframes (1, 5, 15, 30, 60, 240 min)

**Required Changes:**
- Add dynamic timeframe selection logic to renderer
- Calculate optimal aggregation based on visible time window
- Snap to nearest standard timeframe

**Estimated Effort:** Low - mostly configuration/display logic
**Risk:** Low
**Conflicts:** None

**Recommendation:** Proceed as designed. Can be implemented without core algorithm changes.

---

### 2. Event-Skip Mode ⚠️ FEASIBLE WITH CHANGES

**Current State:** Events detected per-bar, no forward index

**Required Changes:**
1. **Pre-compute Event Index:** Build sorted list of (bar_idx, event) tuples during initialization
2. **Binary Search Jump:** Find next event using `bisect` for O(log N) lookup
3. **State Fast-Forward:** Process intermediate bars for state accuracy without rendering

**Architecture Impact:**
```
┌─────────────────────────────────────────────────────────────┐
│                    EventIndex (NEW)                          │
│  Pre-computed: [(bar_123, event1), (bar_456, event2), ...]   │
│  Lookup: O(log N) to find next event after current position │
└─────────────────────────────────────────────────────────────┘
```

**Estimated Effort:** Medium - new component + integration
**Risk:** Medium - requires careful state management during fast-forward
**Conflicts:** Depends on fixing swing detection performance first

**Recommendation:** Implement after swing detection optimization. Without it, pre-computing events for a month of data would take prohibitively long.

---

### 3. S-Scale Swing Cap ✅ FEASIBLE

**Current State:** All active swings displayed without filtering

**Required Changes:**
1. Add scoring function: `score = recency_weight * recency + size_weight * size`
2. Filter to top N in renderer's `_group_swings_by_scale()`
3. Add toggle command to show all

**Estimated Effort:** Low
**Risk:** Low
**Conflicts:** None

**Recommendation:** Proceed as designed. Straightforward filtering logic.

---

### 4. Stability Audit ✅ FEASIBLE

**Current State:** Known state management issues during transitions

**Required Changes:**
1. Audit state preservation in layout transitions
2. Review pause/resume state handling
3. Document and fix state machine gaps

**Estimated Effort:** Medium (depends on issue severity)
**Risk:** Low - isolated changes
**Conflicts:** None

**Recommendation:** Can proceed in parallel with other work.

---

### 5. 16M Bar Scale ❌ NOT FEASIBLE (Current Architecture)

**Blocker:** O(N²+) swing detection algorithm

**Analysis at 16M bars:**
- Estimated swing highs: ~3.2M (20% of bars)
- Estimated swing lows: ~3.2M
- Pairing complexity: 3.2M × 3.2M = **10 trillion** operations
- Estimated time: **Days to weeks**

**Required Changes:**
1. **Rewrite swing detection algorithm** - O(N log N) using sorted intervals
2. **Incremental detection** - Only process new bars, not full history
3. **Sparse aggregation mappings** - Lazy computation for trivial timeframes

**Estimated Effort:** High - core algorithm rewrite
**Risk:** High - regression risk, extensive testing needed
**Conflicts:** All other requirements depend on this working

---

## Critical Path Analysis

```
                    ┌──────────────────────────────────┐
                    │  Swing Detection Optimization    │
                    │  (BLOCKER - Must be first)       │
                    └────────────────┬─────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Event-Skip Mode │       │ Dynamic Agg     │       │ S-Scale Cap     │
│ (Depends on ^)  │       │ (Independent)   │       │ (Independent)   │
└─────────────────┘       └─────────────────┘       └─────────────────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │       Stability Audit            │
                    │  (Can run parallel, gate deploy) │
                    └──────────────────────────────────┘
```

---

## Recommended Implementation Sequence

### Phase 0: Performance Foundation (REQUIRED FIRST)
1. **Rewrite swing detection to O(N log N)**
   - Use timestamp-sorted arrays
   - Binary search for swing pairing
   - Pre-filter invalid candidates

2. **Implement incremental swing detection**
   - Detect new swings only as bars arrive
   - Maintain swing cache instead of recomputing

3. **Optimize aggregation mappings**
   - Remove redundant 1:1 mapping storage
   - Use lazy evaluation for trivial cases

**Gate:** Must achieve <1 second init for 100K bars

### Phase 1: Quick Wins (Parallel with Phase 0)
1. S-Scale Swing Cap
2. Dynamic Bar Aggregation
3. Stability Audit (begin)

### Phase 2: Event-Skip Mode
1. Pre-compute event index
2. Implement binary search jump
3. State fast-forward logic

### Phase 3: Integration & Polish
1. Complete stability audit
2. Integration testing at scale
3. User acceptance validation

---

## Requirements Requiring Revision

### Event-Skip Mode Target

**Original Requirement:** "Traverse a month in minutes"

**Concern:** Without knowing event density, this is hard to validate. A month with 1,000 events vs 100,000 events has very different traversal times.

**Recommended Revision:**
- Define target as "events per second" not "month in minutes"
- Suggest: ">50 events/second" as measurable target
- Alternative: "Skip to any event in <100ms"

### 16M Bar Performance Constraint

**Original Requirement:** "All algorithms must be O(N) or better"

**Concern:** Some algorithms legitimately need O(N log N), which is acceptable at scale. O(N) is too restrictive.

**Recommended Revision:**
- "All algorithms must be O(N log N) or better"
- "No O(N²) or worse patterns in hot paths"
- "Profile before deploying to full dataset"

---

## Open Questions for Product

1. **Event Pre-computation:** Is it acceptable for the harness to spend 30-60 seconds pre-computing an event index at startup for a month of data? This enables instant jumps but requires upfront cost.

2. **Swing Cap Default:** Product specifies "3-5 swings" - should this be configurable or fixed? Recommend configurable with 5 as default.

3. **Priority Trade-off:** If we can only deliver 2 of (Event-Skip, Dynamic Agg, Swing Cap) in first iteration, which are highest priority?

---

## Risk Summary

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| O(N²) algorithm not fixable | Low | Critical | Algorithm well-understood, fix path clear |
| Regression in swing detection | Medium | High | Comprehensive test suite exists |
| Performance targets not met | Medium | Medium | Profile iteratively, adjust targets |
| Scope expansion | Medium | Medium | Gate each phase with acceptance criteria |

---

## Conclusion

**Return to Product with:**

1. **CONFIRMED:** Dynamic Bar Aggregation, S-Scale Swing Cap, Stability Audit are feasible within current architecture

2. **CONFIRMED WITH CHANGES:** Event-Skip Mode is feasible but requires new EventIndex component

3. **BLOCKED:** 16M bar scale requires O(N²) → O(N log N) algorithm rewrite as prerequisite

4. **RECOMMENDED:** Proceed with Phase 0 (Performance Foundation) before implementing product requirements

**Next Action:** Product to confirm priority trade-offs and approve Phase 0 pre-work before engineering begins.

---

## Appendix: Profiling Script

The profiling script used for this analysis is available at:
```
architect_profile.py
```

To reproduce:
```bash
source venv/bin/activate
python architect_profile.py
```
