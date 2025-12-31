# Order of Operations Audit

**Status:** Audit needed
**Created:** 2025-12-31
**Related:** `Docs/Working/formed_analysis.md`

## Problem Statement

We discovered an order-of-operation bug where a leg that would correctly form over multiple candles fails when the same price action occurs in a single candle. This suggests there may be other similar bugs where the single-bar case behaves differently than the multi-bar case.

## The Bug We Found

### Multi-candle scenario (works correctly):
```
Bar 1: Leg created with origin=100, pivot=110
Bar 2: Price rises, close=105 (50% retracement) → LEG FORMS (swing_id set)
Bar 3: Price rises more
Bar 4: Price drops
Bar 5: Price drops below origin (95) → ORIGIN BREACHED
Result: Leg formed before breach, pivot breach can be tracked, engulfed pruning works
```

### Single-candle scenario (bug):
```
Bar 1: Leg created with origin=100, pivot=110, close=102 (20% < 23.6% threshold)
       → NOT FORMED (close didn't reach threshold, even though high did)
Bar 2: Price drops below origin (95) → ORIGIN BREACHED before formation
Result: Leg never forms, pivot breach never tracked, becomes zombie
```

### Root Cause

In `_update_dag_state`, the order of operations is:

```python
# leg_detector.py _update_dag_state():

1. prune_engulfed_legs()      # Uses breach values from PREVIOUS bar
2. _extend_leg_pivots()        # Extends pivots for live legs
3. _update_breach_tracking()   # ← BREACH TRACKING HERE
4. _process_type2_bull/etc()   # ← FORMATION CHECKS HERE (inside bar processors)
5. bar_count increment
6. _check_extension_prune()
```

Breach tracking (step 3) happens BEFORE formation checks (step 4). If origin is breached on the current bar, the leg is marked as breached before it has a chance to form.

### Why This Matters

The principle violated: **A leg should behave the same whether price action takes 1 bar or 5 bars.**

If a leg would form given the same price range over multiple bars, it should also form when that range occurs in a single bar. The order of operations within a bar should not create different outcomes than the natural multi-bar sequence.

---

## Current Order of Operations

### In `_update_dag_state` (leg_detector.py:550):

| Step | Operation | Reads | Writes |
|------|-----------|-------|--------|
| 1 | `prune_engulfed_legs` | max_origin_breach, max_pivot_breach, formed | status, active_legs |
| 2 | `_extend_leg_pivots` | max_origin_breach (gate) | pivot_price, pivot_index, range, impulse |
| 3 | `_update_breach_tracking` | origin_price, pivot_price, formed | max_origin_breach, max_pivot_breach |
| 4 | `_process_type2_*` | pending_origins, various | Creates legs, formed, swing_id |
| 5 | bar_count increment | max_origin_breach (gate) | bar_count |
| 6 | `_check_extension_prune` | max_origin_breach, parent_leg_id | status, active_legs |

### In `process_bar` (leg_detector.py:1402):

| Step | Operation | Notes |
|------|-----------|-------|
| 1 | `_check_level_crosses` | Fib level tracking |
| 2 | `_update_dag_state` | All the above |
| 3 | `_update_leg_moments_and_spikiness` | Statistics |
| 4 | `_update_live_leg_impulsiveness` | Percentile ranking |

---

## Audit Methodology

### Key Principle

For any state change, ask: **"If this took 5 bars instead of 1, would the outcome be different?"**

### How to Find These Bugs

1. **Identify state dependencies**: Which operations read state that other operations write?

2. **Trace single-bar edge cases**: For each pair of dependent operations:
   - What if both happen on the same bar?
   - Does the order within the bar match the natural multi-bar sequence?

3. **Look for gates that can be "missed"**:
   - Operation A sets a flag
   - Operation B checks that flag as a gate
   - If B runs before A, the gate check fails even though it would pass in multi-bar

4. **Check for stale data usage**:
   - Operation uses values from previous bar
   - But those values change on current bar
   - 1-bar delay in effect

### Specific Patterns to Look For

#### Pattern 1: Gate Before Set
```
if some_condition:  # Gate check
    do_something()
# ... later ...
some_condition = True  # Condition is set AFTER the check
```
Bug: The gate is checked before it's set on the same bar.

#### Pattern 2: Prune Before Update
```
prune_based_on(field_value)  # Uses old value
# ... later ...
field_value = new_value  # Updated after prune decision
```
Bug: Prune decision uses stale data, 1-bar delay.

#### Pattern 3: Invalidate Before Opportunity
```
mark_as_invalid()  # Marks leg as compromised
# ... later ...
check_for_valid_action()  # Skips because already invalid
```
Bug: Leg is invalidated before it has a chance to do something valid.

---

## Known Issues to Investigate

### Issue 1: Breach Before Formation (CONFIRMED BUG)
- **Location**: `_update_breach_tracking` before `_process_type2_*`
- **Effect**: Origin breach tracked before formation check
- **Single-bar case**: Leg breached before it can form
- **Multi-bar case**: Leg forms on bar N, breached on bar N+M
- **Status**: Documented in `formed_analysis.md`, fix proposed

### Issue 2: Engulfed Prune Uses Stale Data (NEEDS INVESTIGATION)
- **Location**: `prune_engulfed_legs` at step 1, before `_update_breach_tracking` at step 3
- **Effect**: Engulfed check uses breach values from PREVIOUS bar
- **Single-bar case**: Leg becomes engulfed, not pruned until next bar
- **Multi-bar case**: Same 1-bar delay
- **Question**: Is this intentional? Does the 1-bar delay cause problems?

### Issue 3: Pivot Extension Before Breach Check (PROBABLY OK)
- **Location**: `_extend_leg_pivots` before `_update_breach_tracking`
- **Effect**: Pivot extends, then breach is checked on new pivot
- **Analysis**: This seems correct - extend first, then check if extended pivot was breached
- **Status**: Likely OK, but verify

### Issue 4: Formation Check Price (RELATED)
- **Location**: `_check_leg_formations` uses close price
- **Effect**: Bar's HIGH may exceed threshold, but close doesn't
- **Single-bar case**: High reaches 100%, close at 20%, leg doesn't form
- **Multi-bar case**: Would form when close eventually reaches threshold
- **Question**: Should formation use intra-bar high for bull legs? Or is close-based conservative approach intentional?

---

## Audit Checklist

For each operation pair where A reads what B writes:

- [ ] What happens if A and B both occur on the same bar?
- [ ] Does current order (A before B, or B before A) match multi-bar behavior?
- [ ] If order is wrong, what's the fix?
- [ ] Are there tests covering the single-bar edge case?

### Specific Pairs to Audit

| Operation A (reads) | Operation B (writes) | Current Order | Needs Audit |
|---------------------|---------------------|---------------|-------------|
| prune_engulfed | _update_breach_tracking | A before B | Yes - stale data |
| _update_breach_tracking | _process_type2_* (formation) | A before B | Yes - KNOWN BUG |
| _extend_leg_pivots | _update_breach_tracking | A before B | Maybe OK |
| _check_extension_prune | _update_breach_tracking | A after B | Probably OK |
| bar_count increment | _update_breach_tracking | A after B | Probably OK |

---

## Testing Strategy

### Write Tests for Single-Bar Edge Cases

For each scenario, create two tests:
1. Multi-bar version (control) - spread action over 5 bars
2. Single-bar version (test) - same price range in 1 bar

Both should produce equivalent results (same legs formed, same pruning).

### Example Test Structure

```python
def test_formation_before_breach_multi_bar():
    """Leg forms over multiple bars, then breached - should work."""
    detector = HierarchicalDetector()
    # Bar 1: Create leg
    # Bar 2-3: Price rises, leg forms
    # Bar 4-5: Price drops, origin breached
    # Assert: leg has swing_id, max_pivot_breach tracked

def test_formation_before_breach_single_bar():
    """Same price action in fewer bars - should also work."""
    detector = HierarchicalDetector()
    # Bar 1: Create leg, high reaches formation, low breaches origin
    # Assert: SAME outcome as multi-bar case
```

---

## Files to Review

1. `src/swing_analysis/dag/leg_detector.py`
   - `_update_dag_state` - main order of operations
   - `_update_breach_tracking` - breach logic
   - `_check_leg_formations` - formation logic
   - `_extend_leg_pivots` - pivot extension logic

2. `src/swing_analysis/dag/leg_pruner.py`
   - `prune_engulfed_legs` - engulfed pruning
   - `apply_origin_proximity_prune` - proximity pruning

3. `tests/` - look for single-bar edge case coverage

---

## Next Steps

1. Audit Issue 2 (engulfed prune stale data) - is 1-bar delay a problem?
2. Audit Issue 4 (formation price) - should we use high instead of close?
3. Write single-bar edge case tests for each operation pair
4. Consider reordering operations if bugs are confirmed
5. Document intended order with rationale in code comments
