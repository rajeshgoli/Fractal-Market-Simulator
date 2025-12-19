# HierarchicalDetector Performance Assessment

**Author:** Architect
**Date:** 2025-12-18
**Issue:** #154
**Status:** Assessment Complete — Ready for Engineering

## Executive Summary

The HierarchicalDetector is ~1000x slower than required. Root cause: O(lookback²) per bar with expensive inner operations. The algorithm does O(n²) work to produce O(1) output (swings are sparse — 10s to 100s per year of ES data).

**Current:** 8.2s for 1K bars (122 bars/sec)
**Target:** <0.01s for 1K bars (100K+ bars/sec)
**Gap:** ~1000x

The good news: the output is correct. The algorithm follows valid_swings.md rules. The task is pure optimization without changing behavior.

**Key Solution (Phase 3):** Use pre-aggregated multi-timeframe data (1h, 4h, 1d) as candidate sources. A 1h bar's high/low is a natural "dominant extremum" — no need to compute dominance. This reduces candidate pairs from 2,500 to ~9-25 per bar (**100-280x reduction**) while maintaining strict causality (only use completed higher-TF bars).

## Profiling Results

### Benchmark Data (1K bars)

| Metric | Value |
|--------|-------|
| Total time | 8.21s |
| Active swings at end | 10 |
| Total events generated | 6907 |
| Swing ranges accumulated | 1663 |
| Bars/second | 122 |

### Scaling Behavior (O(n²) confirmed)

| Bars | Time (s) | Bars/sec | Active Swings |
|------|----------|----------|---------------|
| 100 | 0.18 | 544 | 7 |
| 500 | 2.02 | 248 | 8 |
| 1000 | 5.98 | 167 | 10 |
| 2000 | 18.03 | 111 | 10 |

Bars/sec *decreases* as data grows — classic O(n²) signature.

### Top Bottlenecks by Cumulative Time

| Function | Time (s) | Calls | Time % | Issue |
|----------|----------|-------|--------|-------|
| `_try_form_direction_swings` | 6.66 | 2000 | 81% | O(lookback²) nested loop |
| `_check_separation` | 1.80 | 166,990 | 22% | Called per candidate pair |
| `_is_big_swing` | 1.42 | 14,141 | 17% | Sorts ALL ranges every call |
| `is_formed` | 1.39 | 2,065,676 | 17% | Called per candidate pair |
| `_check_pre_formation` | 0.74 | 845,224 | 9% | Called per candidate pair |

**Note:** Percentages overlap because functions are nested.

## Root Cause Analysis

### Problem 1: O(lookback²) Candidate Pair Explosion

With `lookback_bars=50`:
- 50 candidate highs × 50 candidate lows = 2,500 pairs per direction
- 5,000 pairs total per bar
- For 1,000 bars: 5,000,000 pair evaluations

The inner loop body executes for each pair:
```python
for origin_idx, origin_price in origins:      # O(50)
    for pivot_idx, pivot_price in pivots:     # O(50)
        # 1. Check temporal order (cheap)
        # 2. Check range > 0 (cheap)
        # 3. Create ReferenceFrame (allocation)
        # 4. is_formed() check (math)
        # 5. _check_pre_formation() (O(candidates))
        # 6. _check_separation() (O(active_swings))
        # 7. _swing_exists() (O(active_swings))
```

Most pairs fail early, but the iteration overhead dominates.

### Problem 2: Repeated Sorting in `_is_big_swing`

```python
def _is_big_swing(self, swing: SwingNode, config: DirectionConfig) -> bool:
    sorted_ranges = sorted(self.state.all_swing_ranges, reverse=True)  # O(n log n)
    threshold_idx = int(len(sorted_ranges) * config.big_swing_threshold)
    threshold_range = sorted_ranges[threshold_idx]
    return swing.range >= threshold_range
```

This sorts `all_swing_ranges` (1,663 entries after 1K bars) on EVERY call. With 14,141 calls, that's 14,141 × O(1663 log 1663) = ~23 million comparison operations just for threshold calculation.

**The threshold changes only when a new swing forms** (~1663 times in 1K bars). We're recomputing it 14,141 times.

### Problem 3: ReferenceFrame Allocations

```python
frame = ReferenceFrame(
    anchor0=pivot_price,
    anchor1=origin_price,
    direction="BULL",
)
```

Created 2,103,783 times in 1K bars. Each allocation includes:
- Dataclass construction
- Decimal arithmetic in `__post_init__`
- Range calculation

These should be reusable or avoided entirely.

## The Sparseness Insight

**Key observation from valid_swings.md:**
> "Relevant swings for the whole year of 2025 on ES range in the 10s to 100s."

The algorithm does O(bars × lookback²) work to find O(100) swings in O(1,000,000) bars. This is fundamentally wrong.

| Metric | Current | Should Be |
|--------|---------|-----------|
| Work per bar | O(lookback²) = O(2500) | O(1) amortized |
| Total work | O(bars × lookback²) = O(5B) | O(bars + swings) |
| Data structure updates | Per pair evaluation | Per swing formed |

## Proposed Optimizations

### Priority 1: Cache Big Swing Threshold (Quick Win)

**Current cost:** 1.4s (17% of runtime)
**Expected savings:** ~1.3s

```python
# In DetectorState:
_cached_big_threshold: Optional[Decimal] = None
_threshold_valid: bool = False

# In _is_big_swing:
def _is_big_swing(self, swing: SwingNode, config: DirectionConfig) -> bool:
    if not self.state._threshold_valid:
        self._update_big_threshold(config)
    return swing.range >= self.state._cached_big_threshold

def _update_big_threshold(self, config: DirectionConfig):
    if not self.state.all_swing_ranges:
        self.state._cached_big_threshold = Decimal("0")
    else:
        sorted_ranges = sorted(self.state.all_swing_ranges, reverse=True)
        threshold_idx = int(len(sorted_ranges) * config.big_swing_threshold)
        threshold_idx = max(0, min(threshold_idx, len(sorted_ranges) - 1))
        self.state._cached_big_threshold = sorted_ranges[threshold_idx]
    self.state._threshold_valid = True

# Invalidate cache when swing forms:
def _on_swing_formed(self, swing: SwingNode):
    self.state.all_swing_ranges.append(swing.range)
    self.state._threshold_valid = False  # Invalidate
```

**Correctness:** SAFE. The threshold is recalculated when it changes. Between swing formations, it's constant.

**Implementation:** ~20 lines, isolated change.

### Priority 2: Dominant Extrema Tracking (High Impact, Medium Complexity)

**Current cost:** 6.6s in nested loops
**Expected savings:** ~5s (reduce pairs from 2500 to ~100)

**Concept:** Instead of tracking ALL bars in lookback window, track only "structurally significant" extrema:

1. **Local maximum**: A bar's high is a local max if no higher high exists within N bars on either side
2. **Local minimum**: A bar's low is a local min if no lower low exists within N bars on either side

With appropriate N (e.g., 5-10), this reduces candidates from 50 to ~5-10 per direction.

**Implementation sketch:**
```python
def _update_candidates(self, bar: Bar) -> None:
    # Instead of appending every bar...
    # Check if this bar creates a new dominant extremum

    bar_high = Decimal(str(bar.high))
    bar_low = Decimal(str(bar.low))

    # A high is dominant if it exceeds recent highs
    # Keep track of "pending" highs that might become dominant
    self._pending_highs.append((bar.index, bar_high))

    # After N bars, promote pending to confirmed dominant
    # Remove highs that were exceeded
    self._prune_exceeded_candidates()
```

**Correctness risk:** MEDIUM. Need to verify this doesn't miss valid swings per Rule 2.1 and Rule 4. The key invariant: **a valid origin (1) must be the true maximum between itself and the defended pivot**. If a higher high exists between them, it's not valid. Dominant extrema tracking enforces this naturally.

**Verification approach:**
1. Run both algorithms on test data
2. Compare output swings
3. Any swing found by brute-force but missed by dominant tracking indicates a bug

### Priority 3: Early Termination per Origin

**Current cost:** Included in nested loop time
**Expected savings:** ~20% of remaining loop time

Once a swing forms from a given origin, check if nearby origins are now invalid due to separation rules. Skip them.

```python
formed_origins = set()  # Origins that formed swings this bar

for origin_idx, origin_price in origins:
    if origin_idx in formed_origins:
        continue
    # ... rest of loop ...
    if swing_formed:
        # Mark nearby origins as "used"
        for oidx, _ in origins:
            if abs(oidx - origin_idx) < min_separation_bars:
                formed_origins.add(oidx)
```

**Correctness:** SAFE. Separation rules already prevent multiple swings from nearby origins.

### Priority 4: Avoid ReferenceFrame Allocations

**Current cost:** ~0.3s (allocation overhead)
**Expected savings:** ~0.2s

Instead of creating ReferenceFrame objects, use inline calculations:

```python
# Instead of:
frame = ReferenceFrame(anchor0=pivot, anchor1=origin, direction="BULL")
if frame.is_formed(price, fib):

# Do:
swing_range = abs(origin - pivot)
if swing_range == 0:
    continue
ratio = (price - pivot) / swing_range
if ratio >= fib:
    # formed
```

**Correctness:** SAFE. Same math, fewer allocations.

### Priority 5: Lazy Invalidation Checks

**Current:** Check all active swings for invalidation on every bar
**Observation:** Swings are only invalidated when price exceeds their defended pivot

For bull swings, only check invalidation if `bar.low < lowest_defended_pivot`.
For bear swings, only check invalidation if `bar.high > highest_defended_pivot`.

```python
def _check_invalidations(self, bar: Bar, timestamp: datetime):
    events = []

    # Quick check: can any bull swing be invalidated?
    bar_low = Decimal(str(bar.low))
    bull_swings = [s for s in self.state.active_swings
                   if s.status == "active" and s.is_bull]
    if bull_swings:
        lowest_pivot = min(s.defended_pivot for s in bull_swings)
        if bar_low >= lowest_pivot:
            # No bull swing can be invalidated
            bull_swings = []

    # Similar for bear...
```

**Correctness:** SAFE. Price below the lowest defended pivot can't invalidate any bull swing.

## Implementation Plan

### Phase 1: Quick Wins (1-2 hours engineering)

| Change | Expected Savings | Risk |
|--------|------------------|------|
| Cache big swing threshold | 1.3s (16%) | Low |
| Inline ReferenceFrame math | 0.2s (2%) | Low |
| Lazy invalidation checks | 0.1s (1%) | Low |

**Phase 1 target:** 6.5s → ~5s for 1K bars (~30% improvement)

### ~~Phase 2: Candidate Reduction~~ (CLOSED — #156)

**Status:** Not needed. Closed in favor of hierarchical architecture.

**Why:** Once L1-L3 swings exist (via #157), child swing detection is bounded by parent's time range:
- L4 search: ~864 bars (3 days) — brute force OK
- L5 search: ~72 bars (6 hours) — trivially fast
- L6+ search: <12 bars — instant

Dominant extrema tracking would save ~1s on L4 detection, which only runs when a new L3 forms. Not worth the complexity.

See #156 closing comment for full rationale.

### Phase 3: Multi-Timeframe Candidate Generation (Recommended)

**Key insight from additional analysis:** The algorithm is O(lookback²) regardless of timeframe. Even daily data (10K bars) takes 626s at 16.8 bars/sec. The bottleneck is candidate pair explosion, not data volume.

**Solution:** Use completed higher-timeframe bars as candidate sources instead of all source bars.

#### Available Aggregated Data

| Timeframe | Bars | Compression vs 5m |
|-----------|------|-------------------|
| 1d | 10,499 | 117x |
| 4h | 26,745 | 46x |
| 1h | 104,132 | 12x |
| 30m | 206,097 | 6x |
| 15m | 408,541 | 3x |
| 5m | 1,223,616 | 1x |

#### How It Works

Instead of tracking all 50 recent 5m bars as candidates:
1. Track extrema from COMPLETED higher-timeframe bars
2. A 1h bar's high is the maximum of 12 5m bars — a natural "dominant extremum"
3. Use BarAggregator to track when higher-TF bars complete

```python
def _update_candidates_multi_tf(self, bar: Bar) -> None:
    """Track candidates from completed higher-timeframe bars."""

    # Check if any higher timeframe bar just completed
    for tf_minutes in [60, 240, 1440]:  # 1h, 4h, 1d
        completed_bar = self.aggregator.get_closed_bar_at_source_time(tf_minutes, bar.index)
        if completed_bar and completed_bar not in self._seen_tf_bars[tf_minutes]:
            self._seen_tf_bars[tf_minutes].add(completed_bar.index)
            # Add this bar's extrema as candidates (with source bar index for temporal ordering)
            last_source_idx = self._get_last_source_idx(completed_bar, tf_minutes)
            self.state.candidate_highs.append((last_source_idx, Decimal(str(completed_bar.high))))
            self.state.candidate_lows.append((last_source_idx, Decimal(str(completed_bar.low))))

    # Prune old candidates (keep last N timeframe bars, not N source bars)
    self._prune_old_tf_candidates()
```

#### Candidate Reduction

| Approach | Candidates per Direction | Pairs per Bar | Reduction |
|----------|-------------------------|---------------|-----------|
| Current (50 5m bars) | 50 | 2,500 | 1x |
| Dominant extrema (~5-10) | 5-10 | 25-100 | 25-100x |
| Multi-TF (1h + 4h + 1d) | 3-5 | 9-25 | **100-280x** |

With multi-TF approach, over 50 source bars we accumulate:
- ~0-1 completed 1h bars (12 5m bars each)
- ~0 completed 4h bars (48 5m bars each)
- Total: 3-5 candidates vs 50

#### Causality (No Lookahead)

**Strictly causal:** Only use COMPLETED higher-TF bars.
- At 5m bar N, the 1h bar is complete only if N is at or past an hour boundary
- `BarAggregator.get_closed_bar_at_source_time()` enforces this
- A 1h bar covering 10:00-10:59 is "complete" only after the 10:55 5m bar

#### Correctness

**Claim:** Using higher-TF extrema as candidates does NOT miss valid swings.

**Proof:**
- A valid swing's origin (1) must be the true maximum between origin and pivot (Rule 2.1)
- If a 5m high is NOT a 1h high, it was exceeded within that hour
- If it was exceeded within the hour, any swing using it as origin would violate Rule 2.1
- Therefore, valid origins must be local maxima at some timeframe level
- Higher-TF bars naturally identify these local maxima

**Caveat:** Very short-term swings (intra-hour) may be missed. Per valid_swings.md, we want "10s to 100s" of swings per year — intra-hour swings are likely noise.

#### Integration with BarAggregator

The codebase already has `BarAggregator` (bar_aggregator.py) with:
- `get_closed_bar_at_source_time(tf_minutes, source_idx)` — returns completed bar at position
- `_source_to_agg_mapping` — maps source bars to aggregated bars
- Pre-computed aggregations for all standard timeframes

**Implementation:** Initialize BarAggregator with source bars, use it for candidate generation.

```python
class HierarchicalDetector:
    def __init__(self, config: SwingConfig, bars: List[Bar] = None):
        self.config = config
        self.state = DetectorState()
        if bars:
            self.aggregator = BarAggregator(bars, source_resolution_minutes=5)
            self._seen_tf_bars = {60: set(), 240: set(), 1440: set()}
```

#### Expected Performance

| Dataset | Current | After Phase 1+2 | After Phase 3 | Target |
|---------|---------|-----------------|---------------|--------|
| 1K bars | 8.2s | ~0.5s | ~0.05s | <1s |
| 10K bars | ~80s | ~5s | ~0.5s | <5s |
| 100K bars | ~800s | ~50s | ~5s | <30s |
| 1M bars | - | ~500s | ~50s | <60s |

**Rationale:** 100-280x reduction in candidate pairs × Phase 1+2 improvements = potentially 1000x+ total improvement.

## Performance Targets (Final)

| Dataset | Current | Phase 1 (#155) | Phase 3 (#157) | Target |
|---------|---------|----------------|----------------|--------|
| 1K bars | 8.2s | ~5s | ~0.05s | <1s |
| 10K bars | ~80s | ~50s | ~0.5s | <5s |
| 100K bars | ~800s | ~500s | ~5s | <30s |
| 1M bars | - | - | ~50s | <60s |
| 6M bars | - | - | ~300s | <60s |

**Phase 3 (#157) is the key enabler.** Multi-timeframe candidate generation provides 100-280x reduction in pair evaluations for L1-L3 detection. Hierarchical bounds handle L4+ naturally.

**Recommendation:** Implement #157 first, then #155 for incremental gains. #156 is closed (not needed).

## Verification Strategy

### 1. Output Equivalence Testing

Before and after each optimization:
```python
def verify_equivalence(bars, old_detector, new_detector):
    old_swings = run_old(bars)
    new_swings = run_new(bars)
    assert same_swings(old_swings, new_swings), "Output changed!"
```

### 2. Rule Compliance Testing

For each detected swing, verify:
- Rule 2.1: No pre-formation violation
- Rule 2.2: Correct tolerance applied
- Rule 3: Formation trigger correct
- Rule 4: Separation maintained

### 3. Benchmark Suite

Add performance tests with assertions:
```python
def test_performance_1k_bars():
    start = time.time()
    detector, events = calibrate(bars_1k)
    elapsed = time.time() - start
    assert elapsed < 1.0, f"1K bars took {elapsed}s, should be <1s"
```

## Appendix: Profiling Commands

```bash
# Run profiler on 1K bars
source venv/bin/activate && python -c "
import cProfile
import pstats
from src.swing_analysis.hierarchical_detector import calibrate, dataframe_to_bars
import pandas as pd

df = pd.read_csv('test_data/es-5m.csv', sep=';', header=None,
                 names=['date','time','open','high','low','close','volume'],
                 nrows=1000)
bars = dataframe_to_bars(df)

cProfile.run('calibrate(bars)', 'profile.stats')
pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(30)
"
```

## Decision: Proceed with Implementation

**Recommendation:** Proceed with Phase 1 immediately (low risk, measurable improvement). Evaluate results before Phase 2.

**Correctness:** Non-negotiable. All optimizations must preserve output equivalence. The verification strategy above ensures this.

**Parallel work:** Phase 1 changes are isolated. Multiple engineers could work on different caching/inlining changes simultaneously.

---

**Next Steps for Engineering:**
1. Create sub-issues for Phase 1 optimizations
2. Implement with output equivalence tests
3. Benchmark and report results
4. Proceed to Phase 2 if needed
