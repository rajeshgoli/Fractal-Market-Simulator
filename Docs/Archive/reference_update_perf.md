# Reference Layer Per-Bar Update Performance

**Status:** Investigation complete, optimization needed
**Created:** 2025-12-31
**Issue:** #397 (related)

## Problem Statement

The Reference Layer's `update()` method should be called per-bar during DAG advances to maintain accurate semantic state. Currently, we use a lightweight `track_formation()` that only tracks formation status, deferring full updates to when the user views Levels at Play.

This creates a gap: semantic computations (scale, location, breach detection) don't happen until display time, potentially missing state changes that occurred during playback.

### Why Per-Bar Update Matters

All Reference Layer computations have semantic meaning beyond display:

| Computation | Current Cost | Semantic Purpose |
|-------------|--------------|------------------|
| Formation check | 0.05 ms | Populates range distribution for scale percentiles |
| Scale classification | 0.03 ms | Determines breach tolerance (L/XL get 15%/10%, S/M get 0%) |
| Location computation | 0.09 ms | Detects breach/completion, affects trading decisions |
| Breach detection | included above | Removes invalidated refs from `_formed_refs` (stateful) |
| Salience computation | 0.24 ms | Trading relevance ranking - downstream consumers need this |
| Grouping/sorting | ~0.02 ms | API organization |

**Key insight:** Even salience will have downstream consumers (e.g., "which swings should I trade?"). Premature optimization that skips semantic work is wrong. We need to make `update()` fast enough for per-bar use.

### Current Performance

Profiled on M-series Mac with 100 active legs:

```
track_formation():  0.05 ms/bar  →  1.5s for 30k bars
update():           0.31 ms/bar  →  9.3s for 30k bars
```

The 6x difference is dominated by **salience computation** (0.24 ms of 0.31 ms total).

## Current Implementation

### File Locations

- **ReferenceLayer class:** `src/swing_analysis/reference_layer.py`
- **Per-bar tracking:** `track_formation()` method (lines 283-302)
- **Full update:** `update()` method (lines 738-834)
- **Salience computation:** `_compute_salience()` method (lines 527-590)
- **Scale classification:** `_classify_scale()` method (lines 348-383)
- **Location computation:** `_compute_location()` method (lines 402-435)

### Call Sites (where per-bar tracking happens)

All in `src/replay_server/routers/replay.py`:

1. **advance_replay main loop** (line 934): Normal bar-by-bar playback
2. **advance_replay resync loop** (line 858): Replaying bars after index mismatch
3. **reverse_replay loop** (line 1104): Replaying bars when stepping backward

### Data Structures

```python
class ReferenceLayer:
    # Range distribution for scale percentile calculation
    _range_distribution: List[Decimal]  # Sorted, O(log n) insert via bisect

    # Formed leg tracking
    _formed_refs: Set[str]      # Leg IDs that have formed (price hit 38.2%)
    _seen_leg_ids: Set[str]     # Deduplication for range distribution

    # Level crossing tracking (for fib level interactions)
    _tracked_for_crossing: Set[str]
```

## Bottleneck Analysis

### Salience Computation (0.24 ms for 100 legs)

The `_compute_salience()` method is the primary bottleneck:

```python
def _compute_salience(self, leg: Leg, scale: str, current_bar_index: int) -> float:
    # 1. Scale weight lookup - O(1), fast
    scale_weight = {'XL': 1.0, 'L': 0.75, 'M': 0.5, 'S': 0.25}[scale]

    # 2. Recency score - O(1), involves division
    bars_since_pivot = max(1, current_bar_index - leg.pivot_index)
    half_life = self.reference_config.salience_half_life  # 200
    recency = math.exp(-0.693 * bars_since_pivot / half_life)

    # 3. Depth weight - O(1), fast
    depth_weight = 1.0 / (1.0 + leg.depth * 0.2)

    # 4. Range percentile - O(log n) bisect lookup
    percentile = self._compute_percentile(leg.range)
    range_score = percentile / 100.0

    # Weighted combination
    return (scale_weight * 0.3 + recency * 0.3 +
            depth_weight * 0.2 + range_score * 0.2)
```

**Hotspots:**
1. `math.exp()` call - transcendental function, relatively expensive
2. `_compute_percentile()` - bisect lookup into sorted list
3. Called for EVERY leg, EVERY bar

### Scale Classification (0.03 ms for 100 legs)

```python
def _classify_scale(self, leg_range: Decimal) -> str:
    percentile = self._compute_percentile(leg_range)  # O(log n)
    if percentile >= 90: return 'XL'
    if percentile >= 70: return 'L'
    if percentile >= 40: return 'M'
    return 'S'
```

**Hotspot:** `_compute_percentile()` called again (same as salience)

### Location Computation (0.09 ms for 100 legs)

```python
def _compute_location(self, leg: Leg, current_price: Decimal) -> float:
    frame = ReferenceFrame(
        anchor0=leg.pivot_price,
        anchor1=leg.origin_price,
        direction="BULL" if leg.direction == 'bear' else "BEAR"
    )
    return float(frame.ratio(current_price))
```

**Hotspot:** `ReferenceFrame` instantiation and `ratio()` computation per leg

## Optimization Strategies

### Strategy 1: Cache Percentile Lookups

The `_compute_percentile()` method is called twice per leg (scale + salience). Cache the result:

```python
def update(self, legs: List[Leg], bar: Bar) -> ReferenceState:
    # Pre-compute percentiles once per leg
    percentile_cache = {leg.leg_id: self._compute_percentile(leg.range) for leg in legs}

    # Use cache in _classify_scale and _compute_salience
    ...
```

**Expected savings:** ~0.03 ms (eliminates duplicate bisect lookups)

### Strategy 2: Batch Percentile Computation

Instead of individual bisect lookups, sort all leg ranges and compute percentiles in one pass:

```python
def _compute_percentiles_batch(self, legs: List[Leg]) -> Dict[str, float]:
    if not self._range_distribution:
        return {leg.leg_id: 50.0 for leg in legs}

    # Sort legs by range
    sorted_legs = sorted(legs, key=lambda l: l.range)

    # Single pass through distribution
    result = {}
    dist_idx = 0
    for leg in sorted_legs:
        while dist_idx < len(self._range_distribution) and self._range_distribution[dist_idx] < leg.range:
            dist_idx += 1
        result[leg.leg_id] = (dist_idx / len(self._range_distribution)) * 100

    return result
```

**Expected savings:** O(n log n) sort + O(n + m) merge vs O(n log m) individual lookups. Better for large n.

### Strategy 3: Approximate Recency with Integer Math

Replace `math.exp()` with a lookup table or integer approximation:

```python
# Pre-computed decay table (indexed by bars_since_pivot // 10)
RECENCY_TABLE = [math.exp(-0.693 * i * 10 / 200) for i in range(100)]

def _fast_recency(self, bars_since_pivot: int) -> float:
    idx = min(bars_since_pivot // 10, 99)
    return RECENCY_TABLE[idx]
```

**Expected savings:** ~0.05 ms (eliminates math.exp calls)

### Strategy 4: Incremental Salience Updates

Instead of recomputing salience from scratch, track delta changes:

```python
# Only recency changes per bar (scale, depth, range_score are stable)
# Store (stable_component, last_bar) and update incrementally
```

**Complexity:** High - requires tracking per-leg state

### Strategy 5: Lazy Location Computation

Only compute location for legs that might be breached:

```python
def update(self, legs: List[Leg], bar: Bar) -> ReferenceState:
    bar_range = Decimal(str(bar.high - bar.low))

    for leg in legs:
        # Skip location check if bar is entirely within safe zone
        if self._bar_entirely_safe(leg, bar):
            continue

        location = self._compute_location(leg, current_price)
        # ... breach check
```

**Expected savings:** Variable - depends on market conditions

### Strategy 6: ReferenceFrame Reuse

Pool or reuse ReferenceFrame objects instead of creating new ones:

```python
def _compute_location(self, leg: Leg, current_price: Decimal) -> float:
    # Reuse cached frame if leg unchanged
    if leg.leg_id in self._frame_cache:
        frame = self._frame_cache[leg.leg_id]
    else:
        frame = ReferenceFrame(...)
        self._frame_cache[leg.leg_id] = frame

    return float(frame.ratio(current_price))
```

**Expected savings:** ~0.02 ms (eliminates object creation overhead)

## Recommended Approach

Based on the profiling data, pursue optimizations in this order:

1. **Cache percentile lookups** (Strategy 1) - Easy win, immediate ~10% improvement
2. **Approximate recency** (Strategy 3) - Moderate effort, ~15% improvement
3. **Batch percentile computation** (Strategy 2) - More complex, good for many legs
4. **ReferenceFrame reuse** (Strategy 6) - Easy, small improvement

**Target:** Reduce `update()` from 0.31 ms to ~0.15 ms (2x improvement), making 30k bars take ~4.5s instead of 9.3s.

## Test Plan

1. Create benchmark test in `tests/test_reference_layer_performance.py`
2. Measure baseline with 50, 100, 200, 500 legs
3. Apply optimizations incrementally, measure each
4. Verify semantic correctness with existing tests
5. Profile in realistic scenario (30k bar advance)

## Migration Path

Once `update()` is fast enough:

1. Replace `track_formation()` calls with `update()` calls in replay.py
2. Remove `track_formation()` method (or keep as alias)
3. Update tests
4. Verify Levels at Play shows correct data immediately after DAG advances

## Open Questions

1. **Acceptable latency target?** Is 4.5s for 30k bars acceptable, or do we need sub-second?
2. **Streaming updates?** Should we emit reference state changes as events during playback?
3. **Caching strategy?** How much memory is acceptable for caches (frame cache, percentile cache)?

## References

- Issue #397: Warmup state preservation (exposed this gap)
- Commit 762374a: Original removal of per-bar update() for performance
- Commit abe3d70: Added track_formation() as lightweight alternative
- `src/swing_analysis/reference_frame.py`: ReferenceFrame implementation
- `src/swing_analysis/reference_config.py`: Configuration (salience_half_life, etc.)
