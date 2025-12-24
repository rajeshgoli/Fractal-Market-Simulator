# Pivot Breach Analysis

**Issue:** #305 - Investigate pivot breach code path (0% triggered)

**Date:** 2025-12-23

## Summary

The "pivot_breach" replacement code path in `prune_breach_legs()` is **dead code** — it can never be reached due to mutually exclusive conditions in the detection logic.

## What Is Pivot Breach?

Issue #208 introduced two breach-related pruning mechanisms:

1. **Pivot Breach (with replacement)**: When a formed leg's pivot is breached beyond a threshold AND origin was never breached → prune the original, create a replacement leg with the new pivot

2. **Engulfed (deletion)**: When both origin AND pivot have been breached over time → delete the leg entirely with no replacement

## Why 0% Trigger Rate?

The pivot_breach replacement path requires two conditions (from `leg_pruner.py:324-341`):

```python
if leg.max_pivot_breach is None:
    continue  # Condition 1: pivot must be breached

if leg.max_origin_breach is not None:
    # engulfed path...
    continue

# Condition 2: origin must NOT be breached
# ... pivot_breach replacement code
```

These conditions are **mutually exclusive** because of the order of operations in `process_bar()`:

### Order of Operations (leg_detector.py:504-515)

```python
# Step 1: Extend pivots first
self._extend_leg_pivots(bar, bar_high, bar_low)

# Step 2: Then track breaches
breach_events = self._update_breach_tracking(bar, bar_high, bar_low, timestamp)
```

### Why They're Mutually Exclusive

**For a bull leg:**

1. If origin is NOT breached:
   - `_extend_leg_pivots`: `bar_high > pivot` → pivot extends to `bar_high`
   - `_update_breach_tracking`: `bar_high > pivot` → NO (pivot IS bar_high now)
   - Result: `max_pivot_breach` stays None

2. If origin IS breached:
   - `_extend_leg_pivots`: skipped (condition `max_origin_breach is None` fails)
   - `_update_breach_tracking`: `bar_high > pivot` → YES, breach recorded
   - Result: `max_pivot_breach` is set, BUT `max_origin_breach` is also set → engulfed path

**For a bear leg:**

1. If origin is NOT breached:
   - `_extend_leg_pivots`: `bar_low < pivot` → pivot extends to `bar_low`
   - `_update_breach_tracking`: `bar_low < pivot` → NO (pivot IS bar_low now)
   - Result: `max_pivot_breach` stays None

2. If origin IS breached:
   - `_extend_leg_pivots`: skipped
   - `_update_breach_tracking`: `bar_low < pivot` → YES, breach recorded
   - Result: Both breaches set → engulfed path

### The Logical Impossibility

```
max_pivot_breach != None   →   pivot was frozen (didn't extend)
pivot was frozen           →   max_origin_breach != None
max_origin_breach != None  →   engulfed path taken (not pivot_breach)
```

Therefore, the condition `(max_pivot_breach != None AND max_origin_breach == None)` can **never** be true.

## What Does Work?

The **engulfed** path works correctly:

1. Origin gets breached first (pivot freezes)
2. Later, price goes past the frozen pivot
3. Both `max_origin_breach` and `max_pivot_breach` are set
4. `prune_breach_legs()` sees both and triggers "engulfed" pruning

## Design Intent vs Implementation

**Original Intent (Issue #208):**
> When a formed leg's pivot is breached beyond a threshold, prune and replace with a new leg at the breach price.

The scenario described:
1. Bear leg forms: origin=4450, pivot=4420
2. Price reverses up (bull leg forms)
3. Price drops to 4415 (below original pivot 4420)
4. **Expected**: Prune 4450→4420, create 4450→4415

**Actual Behavior:**
- In step 3, since origin (4450) was never breached, pivot **extends** to 4415
- No pruning occurs — the same leg just grows
- The leg becomes 4450→4415 naturally via extension

The implementation assumes that once formed, the pivot is "locked" and shouldn't extend. But the extension logic doesn't check the `formed` flag — it only checks if origin is breached.

## Recommendations

### Option A: Remove Dead Code (Recommended)

Delete the unreachable pivot_breach replacement code path:

**Pros:**
- Simplifies codebase
- Removes confusing dead code
- Engulfed pruning still works

**Cons:**
- Loses the "replacement" concept (but it was never working anyway)

**What to remove:**
- Lines 341-357 in `leg_pruner.py` (pivot_breach replacement logic)
- Lines 387-448 (legs_to_replace processing)
- `enable_pivot_breach_prune` config flag
- Related test cases that test unreachable behavior

### Option B: Fix the Logic

Make pivot breach work as intended by freezing pivots once formed:

**Change in `_extend_leg_pivots`:**
```python
# Current
if bar_high > leg.pivot_price and leg.max_origin_breach is None:

# Fixed
if bar_high > leg.pivot_price and leg.max_origin_breach is None and not leg.formed:
```

**Pros:**
- Implements original design intent
- Formed legs have stable pivots

**Cons:**
- Major behavioral change
- Legs would stop extending once formed (38.2% retracement reached)
- May break existing expected behavior
- Requires extensive testing

### Option C: Keep but Disable by Default

Set `enable_pivot_breach_prune: False` as default, acknowledge it's dead code:

**Pros:**
- No code changes needed
- Already defaults to True but has no effect

**Cons:**
- Leaves confusing dead code in place
- Wastes cycles checking unreachable conditions

## Impact Assessment

| Metric | Current | After Option A | After Option B |
|--------|---------|----------------|----------------|
| Pivot breach triggers | 0% | N/A (removed) | TBD (would trigger) |
| Engulfed triggers | Works | Works | Works |
| Code complexity | High | Lower | Same |
| Behavioral change | None | None | Significant |

## Conclusion

**Recommendation: Option A (Remove Dead Code)**

The pivot_breach replacement logic was designed with an assumption (formed pivots are frozen) that wasn't implemented in the extension logic. Rather than introducing a significant behavioral change, the cleanest approach is to:

1. Remove the dead code path
2. Keep engulfed pruning (which works)
3. Document that formed legs continue extending until origin breach

This aligns with the current actual behavior where formed legs naturally extend their pivots, which is reasonable — a leg's "best" pivot is always the deepest extreme reached.

## Files Affected

- `src/swing_analysis/dag/leg_pruner.py` — `prune_breach_legs()` method
- `src/swing_analysis/dag/leg_detector.py` — `_extend_leg_pivots()`, `_update_breach_tracking()`
- `src/swing_analysis/swing_config.py` — `enable_pivot_breach_prune` flag
- `tests/test_issue_208_pivot_breach_pruning.py` — Several tests for unreachable behavior
