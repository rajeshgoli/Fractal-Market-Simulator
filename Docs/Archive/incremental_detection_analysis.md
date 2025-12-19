# Incremental Swing Detection: Feasibility Analysis

**Date:** 2025-12-17
**Status:** Analysis Complete
**Author:** Architect Review

## Problem Statement

The current replay implementation runs full O(N log N) swing detection on every source bar advance. For the user scenario:

- **Data:** es-5m.csv, 10K bars calibration
- **UI:** Two screens at 1H and 4H
- **Speed:** 10x on 1H (12 source bars per 100ms tick)

This results in 12 × O(10K log 10K) ≈ 1.6M operations per tick—far too slow for smooth playback.

**Question:** Can incremental detection produce equivalent results while achieving O(active_swings) per bar?

---

## Executive Summary

**Yes, incremental detection works**, with these caveats:

| Aspect | Equivalent to Full Detection? |
|--------|------------------------------|
| Swing formation | ✅ YES |
| Swing invalidation | ✅ YES |
| Fib level crosses | ✅ YES |
| Completion events | ✅ YES |
| Statistics-based filtering | ⚠️ DIFFERS (freeze at calibration) |
| Redundancy/quota promotion | ❌ DIFFERS (no retroactive promotion) |

The differences **simulate live trading behavior**, which is arguably the correct semantics for a replay tool.

**Performance improvement:** ~2400x (from 1.6M ops to ~660 ops per tick)

---

## Algorithm Analysis

### Current Algorithm Dependencies

| Phase | Component | Global Dependency | Can Be Incremental? |
|-------|-----------|-------------------|---------------------|
| 1 | Swing point detection | ALL bars (vectorized) | NO - but only need trailing edge |
| 2 | Suffix arrays | ALL bars | NO - but replaced by per-bar check |
| 3 | Pairing | Sorted swing points | YES - binary search O(log N) |
| 4 | Protection (pre-formation) | Range [high_idx, low_idx] | YES - local range query |
| 5 | Protection (post-formation) | suffix_min/max | YES - check vs new bar price |
| 6 | Size filter | median_candle, price_range | PARTIAL - freeze at calibration |
| 7 | Prominence | ±lookback window | YES - local check |
| 8 | Structural separation | Previous accepted swings | YES - sequential processing |
| 9 | Redundancy filter | All swings by size | NO - but accept difference |
| 10 | Quota | All swings ranked | NO - but accept difference |

---

## Edge Case Analysis

### Case 1: Swing Point Confirmation Timing

**Scenario:** Bar at index `i` is a swing low, confirmed when bars `i+1` through `i+lookback` all have higher lows.

**Full detection:** Detects at any point after `i+lookback` bars exist.

**Incremental:** Check bar `N-lookback` when bar `N` arrives.

```
New bar at N → Check if bar N-lookback is now confirmed as swing point
```

**Verdict:** ✅ EQUIVALENT

---

### Case 2: Post-Formation Invalidation

**Scenario:** Bull swing formed at bar 100 (high=80, low=100). At bar 500, price drops below pivot.

**Full detection:** Uses `suffix_min_lows[101]` to check if low was violated.

**Incremental:** For each new bar, check all active swings:

```python
for swing in active_swings:
    if swing.direction == 'bull' and new_bar.low < swing.low - tolerance:
        emit(SWING_INVALIDATED, swing)
        remove(swing)
```

**Verdict:** ✅ EQUIVALENT - O(active_swings) per bar produces same result.

---

### Case 3: New Swing Pairing (The O(log N) Step)

**Scenario:** New swing low confirmed at bar N. Need to pair with previous highs.

**Steps:**
1. Binary search `swing_highs` for candidates in `[N - max_pair_distance, N]` → O(log N)
2. For each candidate high at bar M:
   - Size check: `high_price - low_price > 0` → O(1)
   - Price validity: `0.382 < current_price < 2.0` → O(1)
   - Structure: `min(lows[M:N]) == low_price` → O(N-M) or O(1) with range tree
   - Pre-formation protection: `max(highs[M+1:N]) < high_price` → O(N-M) or O(1)

**Total:** O(log N + k × range_query) where k = candidates in window

With `max_pair_distance` bounding k, this is O(log N + k) amortized over many bars.

**Verdict:** ✅ EQUIVALENT

---

### Case 4: Statistics Drift

**Scenario:**
- Bar 1000: median_candle=10, swing size=15 passes filter
- Bar 5000: median_candle=20, same swing would fail

**Full detection:** Recomputes statistics each bar. Swing existence depends on current statistics.

**Incremental:** Freeze statistics at calibration. Swings that form stay formed.

**Key insight:** Current implementation also exhibits statistics drift—swings can "appear" or "disappear" as window expands. This is arguably WRONG for live simulation.

**Verdict:** ⚠️ DIFFERS - But incremental behavior is more realistic for live trading.

**Resolution:** Freeze `median_candle` and `price_range` at calibration end.

---

### Case 5: Redundancy Promotion

**Scenario:**
- Swing A (size=100) and Swing B (size=95) share same Fib bands
- A kept, B filtered as redundant
- A invalidated later
- Should B be "promoted"?

**Full detection:** YES - Re-running would now keep B.

**Incremental:** NO - B was never tracked.

**Verdict:** ❌ DIFFERS

**Severity:** LOW - Requires same-band swings of similar size, then invalidation of larger. Rare in practice.

**Resolution:** Accept difference. Live trading wouldn't retroactively promote either.

---

### Case 6: Quota Promotion

**Scenario:**
- Quota=5, swings #1-6 exist
- #6 filtered by quota
- #3 invalidated
- Should #6 become #5?

**Full detection:** YES

**Incremental:** NO - #6 never tracked

**Verdict:** ❌ DIFFERS (same as Case 5)

---

### Case 7: Extrema Re-adjustment

**Scenario:**
- Swing detected with high at bar 50
- `adjust_extrema=True` moves to bar 48
- Later, bar 52 has even higher high
- Should endpoint shift?

**Full detection:** Would find bar 52 if in ±lookback window.

**Incremental:** Swing identity fixed at formation time.

**Verdict:** ⚠️ DIFFERS - But this is correct for live behavior. Once formed, identity is fixed.

---

### Case 8: Structural Separation Context Change

**Scenario:**
- XL swing provides fib grid for L swing separation
- XL swing invalidated
- Should L swings be re-evaluated?

**Full detection:** YES - Would use new XL (or fallback).

**Incremental:** NO - L swings formed with original context.

**Verdict:** ⚠️ DIFFERS - Matches live behavior.

---

## UI Configuration Edge Cases

### Scale Selection (XL/L/M/S toggles)

User enables/disables scales for event filtering.

**Impact:** None - filtering happens at event emission, after detection.

### Speed/Aggregation Settings

10x at 1H = 12 source bars per 100ms tick.

**Edge case:** Aggregation change mid-playback?

**Answer:** Detection always operates on source bars. Aggregation is visual only.

### Two-Screen Configuration (1H + 4H)

**Edge case:** Are swings detected per-screen aggregation?

**Answer:** No. Detection uses source bars. Mapping to aggregated bars is display-time.

A swing at source bar 500 → 1H bar 41 → 4H bar 10. Same swing, different visual mappings.

---

## Proposed Incremental State

```python
@dataclass
class IncrementalSwingState:
    # Frozen at calibration
    median_candle: float
    price_range: float
    scale_thresholds: Dict[str, float]  # XL/L/M/S -> size threshold

    # Sorted swing points (for O(log N) lookup)
    swing_highs: SortedList[SwingPoint]  # by bar_index
    swing_lows: SortedList[SwingPoint]   # by bar_index

    # Active swings by scale
    active_swings: Dict[str, Dict[str, Swing]]  # scale -> swing_id -> swing

    # Fib level tracking
    fib_levels: Dict[str, float]  # swing_id -> current level (0.0 to 2.0+)

    # For structural separation (XL→L→M→S cascade)
    larger_swings: Dict[str, List[Swing]]  # 'L' -> XL swings, 'M' -> L swings, etc.
    accepted_by_direction: Dict[str, List[Swing]]  # 'bull'/'bear' -> accepted list

    # Source bar data (for range queries)
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
```

---

## Per-Bar Algorithm

```python
def advance_bar_incremental(new_bar: Bar, state: IncrementalSwingState) -> List[Event]:
    events = []

    # Append new bar data
    state.highs = np.append(state.highs, new_bar.high)
    state.lows = np.append(state.lows, new_bar.low)
    state.closes = np.append(state.closes, new_bar.close)

    # 1. Check for swing point confirmation at N-lookback
    check_idx = new_bar.index - LOOKBACK
    if check_idx >= LOOKBACK:  # Need full window on both sides
        if is_swing_high(check_idx, state.highs, LOOKBACK):
            point = SwingPoint('high', check_idx, state.highs[check_idx])
            state.swing_highs.add(point)
            events.extend(pair_high_with_lows(point, state))

        if is_swing_low(check_idx, state.lows, LOOKBACK):
            point = SwingPoint('low', check_idx, state.lows[check_idx])
            state.swing_lows.add(point)
            events.extend(pair_low_with_highs(point, state))

    # 2. Check invalidations
    for scale in ['XL', 'L', 'M', 'S']:
        for swing_id, swing in list(state.active_swings[scale].items()):
            if is_pivot_violated(swing, new_bar, PROTECTION_TOLERANCE):
                del state.active_swings[scale][swing_id]
                events.append(Event('SWING_INVALIDATED', swing))

    # 3. Check fib level crosses
    for scale in ['XL', 'L', 'M', 'S']:
        for swing_id, swing in state.active_swings[scale].items():
            old_level = state.fib_levels.get(swing_id, 0.0)
            new_level = get_fib_level(new_bar.close, swing)
            state.fib_levels[swing_id] = new_level

            if old_level < 2.0 <= new_level:
                events.append(Event('SWING_COMPLETED', swing, level=2.0))
            elif new_level > old_level:
                for sig_level in [0.382, 0.5, 0.618, 1.0, 1.382, 1.618]:
                    if old_level < sig_level <= new_level:
                        events.append(Event('LEVEL_CROSS', swing, level=sig_level))
                        break

    return events
```

---

## Complexity Analysis

| Operation | Frequency | Cost | Notes |
|-----------|-----------|------|-------|
| Append bar | Every bar | O(1) | Amortized array append |
| Swing point check | Every bar | O(lookback) | Check ±5 bars |
| Insert swing point | ~1 per 30 bars | O(log N) | SortedList insert |
| Binary search for pairs | ~1 per 30 bars | O(log N) | Find candidates |
| Filter candidates | ~1 per 30 bars | O(k) | k bounded by max_pair_distance |
| Invalidation scan | Every bar | O(active) | active << N |
| Fib level scan | Every bar | O(active) | active << N |

**Per-bar typical:** O(active + lookback) ≈ O(55) for 50 active swings, lookback=5

**Per-bar when swing forms:** O(log N + k + active) ≈ O(70) for N=10K, k=10

**Amortized:** O(active) ≈ O(50)

### Comparison

| Approach | Ops per 100ms tick (12 bars) |
|----------|------------------------------|
| Current (full detection) | 12 × O(N log N) ≈ 1,600,000 |
| Incremental | 12 × O(50) + 0.4 × O(70) ≈ 630 |
| **Improvement** | **~2,500x** |

---

## Summary: What's Equivalent, What Differs

### Equivalent (Same Result)

| Aspect | Why |
|--------|-----|
| Swing point detection | Same logic, just deferred to confirmation time |
| Swing pairing | Same binary search + validation |
| Pre-formation protection | Same range check |
| Post-formation invalidation | Check per bar = same as suffix array result |
| Fib level tracking | Same calculation |
| Event emission | Same triggers |

### Differs (Intentionally)

| Aspect | Full Detection | Incremental | Resolution |
|--------|----------------|-------------|------------|
| Statistics | Recomputed per bar | Frozen at calibration | More realistic for live |
| Redundancy promotion | Retroactive | No promotion | Matches live behavior |
| Quota promotion | Retroactive | No promotion | Matches live behavior |
| Extrema re-adjustment | Per detection | Fixed at formation | Matches live behavior |

**Key insight:** All differences favor "live simulation" over "omniscient replay". For a replay tool meant to simulate real-time trading, incremental behavior is arguably **more correct**.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Swing point list grows unbounded | Memory | Prune points older than `max_pair_distance` |
| Active swings accumulate | Memory + scan time | Cap per scale (e.g., top 10 by size) |
| Statistics freeze is wrong | Swings form that shouldn't | Use calibration window stats (representative) |
| Range queries are slow | Pairing becomes expensive | Use segment tree for O(log N) range min/max |

---

## Conclusion

**Incremental detection is feasible and correct for the replay use case.**

1. Core events (FORMED, INVALIDATED, LEVEL_CROSS, COMPLETED) are equivalent
2. Differences simulate live trading behavior, not full hindsight
3. Performance enables smooth 10x playback at any aggregation
4. Implementation requires:
   - Sorted lists for swing points
   - Per-bar invalidation and level checks
   - Frozen calibration statistics
   - Cascade context (larger_swings) from calibration

The ~2,500x performance improvement enables the user scenario: smooth 1H bar movement at 10x speed until events fire.
