# Analysis: Removing `formed` from DAG Layer

**Status:** Investigation in progress
**Started:** 2025-12-31
**Origin:** Feedback observation `27680162-15ed-4bbb-8d4b-9c074ebb32ef`

## Problem Statement

User observed a "zombie leg" (`leg_bull_3995.5_179577`) that should have been pruned as engulfed but wasn't. Investigation revealed this is a symptom of a larger architectural issue with the `formed` field in the DAG layer.

## The Zombie Leg Bug

### Observation Details
- **Leg:** `leg_bull_3995.5_179577`
- **Origin:** 3995.5 @ bar 179577
- **Pivot:** 4030.5 @ bar 179578
- **Range:** 35.0 points

### What Happened
At playback bar 19999:
- `formed: False` - the leg NEVER formed
- `max_origin_breach: 493.5` - origin was breached (price went to 3502.0)
- `max_pivot_breach: None` - pivot breach was NEVER tracked

### Price Movement Proof
- Price went **604 points above** pivot (4030.5 → 4634.5)
- Price went **493.5 points below** origin (3995.5 → 3502.0)
- The leg was clearly "engulfed" but never pruned

### Root Cause
Pivot breach tracking is gated by `formed`:
```python
# leg_detector.py:512
if leg.formed and leg.range > 0:
    # Track pivot breach
```

But `formed` is set when leg reaches 38.2% retracement. If origin is breached BEFORE formation:
1. Leg can never form (formation check requires `max_origin_breach is None`)
2. Pivot breach is never tracked (requires `formed`)
3. Engulfed pruning never fires (requires both breaches)
4. Result: immortal zombie leg

---

## Audit of `formed` Usage in DAG Layer

### Usage Locations

| File | Line | Code | Purpose |
|------|------|------|---------|
| `leg.py` | 48 | `formed: bool = False` | Field definition |
| `leg_detector.py` | 512 | `if leg.formed and leg.range > 0:` | Gate pivot breach tracking |
| `leg_detector.py` | 1173 | `leg.formed or leg.max_origin_breach` | Skip already-formed in formation check |
| `leg_detector.py` | 1190 | `leg.formed = True` | Set when threshold reached |
| `leg_detector.py` | 1208 | `leg.formed or leg.max_origin_breach` | Skip already-formed (extremes variant) |
| `leg_detector.py` | 1226 | `leg.formed = True` | Set when threshold reached (extremes) |
| `leg_detector.py` | 1279 | `bisect.insort(formed_leg_impulses...)` | Track impulse distribution |
| `leg_pruner.py` | 524 | `if not leg.formed or leg.range == 0:` | Gate engulfed pruning |
| `leg_pruner.py` | 617 | `leg.formed` | Gate counter-trend ratio pruning |
| `state.py` | 109, 230 | Serialization | Persist/restore state |

---

## Detailed Analysis by Usage

### Usage 1: Formation Check Gates (lines 1173, 1208)

**Current logic:**
```python
if leg.status != 'active' or leg.formed or leg.max_origin_breach is not None:
    continue  # Skip
```

**Purpose:** Prevent re-processing legs that already formed.

**Analysis:** Can use `leg.swing_id is not None` as equivalent gate:
- When a leg forms → it gets a swing_id via `_form_swing_from_leg`
- When a leg inherits via proximity prune → it gets a swing_id
- Either way, no need to re-form

**Proposed change:**
```python
if leg.status != 'active' or leg.swing_id is not None or leg.max_origin_breach is not None:
    continue
```

**Note:** When survivor inherits swing_id, its impulse wasn't added to `formed_leg_impulses`. Minor issue - original leg's impulse is already there.

---

### Usage 2: Pivot Breach Tracking Gate (line 512)

**Current logic:**
```python
if leg.formed and leg.range > 0:
    # Track pivot breach
```

**Comment says:** "Once formed, the pivot is frozen... for unformed legs, it would just extend"

**But that's not accurate!** Pivot extension is gated by `max_origin_breach`, NOT by `formed`:

```python
# _extend_leg_pivots (line 347):
if leg.direction == 'bull' and leg.max_origin_breach is None:
    if bar_high > leg.pivot_price:
        leg.update_pivot(bar_high, bar.index)  # Pivot extends
```

**What actually freezes a pivot:**
1. Origin breached → pivot stops extending
2. `formed` → has NO effect on extension!

**The zombie leg matrix:**

| Leg State | Pivot Extends? | Pivot Breach Tracked? | Result |
|-----------|---------------|----------------------|--------|
| Unformed, origin OK | Yes | No | OK - still growing |
| Unformed, origin breached | No (frozen!) | No | **BUG - zombie** |
| Formed, origin OK | Yes | Yes | OK |
| Formed, origin breached | No | Yes | OK - can be engulfed |

**Proposed change:**
```python
# Track pivot breach when pivot is frozen (origin breached stops extension)
if leg.max_origin_breach is not None and leg.range > 0:
    # Track pivot breach
```

This makes structural sense: if the pivot can't extend anymore, price going past it IS a breach.

---

### Usage 3: Engulfed Pruning Gate (line 524)

**Current logic:**
```python
if not leg.formed or leg.range == 0:
    continue
# Then check if both origin and pivot are breached
```

**Analysis:** "Engulfed" means price went past BOTH ends of the leg. This is a pure geometric property - the leg's range is now inside a larger price move. Whether the leg reached 38.2% retracement is irrelevant.

**Proposed change:**
```python
if leg.range == 0:
    continue
if leg.max_pivot_breach is not None and leg.max_origin_breach is not None:
    # Engulfed - prune
```

**Result:** Zombie legs will now be pruned when engulfed.

---

### Usage 4: Counter-Trend Ratio Gate (line 617)

**Current logic:**
```python
legs_to_check = [
    leg for leg in state.active_legs
    if leg.direction == direction and leg.max_origin_breach is None and leg.formed
]
```

**Purpose:** Prune legs with insufficient counter-trend pressure at their origin.

**Analysis:** CTR ratio is `origin_counter_trend_range / leg.range`. Since formed legs can still extend (if origin not breached), their range grows and CTR ratio decreases over time.

**Should we remove `formed`?** No - unformed legs have unstable CTR ratios. A leg just starting has tiny range, so artificially high CTR. We want to let legs form before deciding if they're significant.

**Proposed change:** Use `swing_id is not None` instead (semantically equivalent):
```python
legs_to_check = [
    leg for leg in state.active_legs
    if leg.direction == direction and leg.max_origin_breach is None and leg.swing_id is not None
]
```

---

### Usage 5: SwingNode Creation (lines 1190, 1226)

**Current logic:**
```python
if retracement >= formation_threshold:
    leg.formed = True  # Mark as formed
    event = self._form_swing_from_leg(leg, bar, timestamp)
```

**What `_form_swing_from_leg` does:**
1. Creates SwingNode
2. Sets `leg.swing_id = swing.swing_id` (line 1276)
3. Adds to `active_swings`
4. Returns SwingFormedEvent

**Analysis:** The `swing_id` serves as the "formed" marker. If we remove `leg.formed = True`, the gate at line 1173 can use `swing_id is not None` instead.

**Proposed change:** Remove `leg.formed = True`. The `swing_id` assignment serves the same purpose.

---

### Usage 6: formed_leg_impulses Tracking (line 1279)

**Current logic:**
```python
# In _form_swing_from_leg:
bisect.insort(self.state.formed_leg_impulses, leg.impulse)
```

**Purpose:** Track impulses of formed legs for percentile ranking (impulsiveness calculation).

**Analysis:** No change needed. The list is populated by `_form_swing_from_leg`, which is still called when threshold is reached. Could rename to `swing_leg_impulses` for clarity.

---

### Usage 7: State Serialization (state.py lines 109, 230)

Just serialization/deserialization. If we remove `formed` from `Leg`, we'd remove it from state serialization too. Uses `leg_data.get("formed", False)` for backward compatibility.

---

## Reference Layer Already Has Its Own Formation Logic

From `reference_layer.py`:
```python
# Track which legs have formed as references (price reached formation threshold)
# Once formed, stays formed until fatally breached
self._formed_refs: Set[str] = set()

def _is_formed_for_reference(self, leg: Leg, current_price: Decimal) -> bool:
    # Once formed, always formed (until fatal breach removes it)
    if leg.leg_id in self._formed_refs:
        return True
    # ... price-based calculation using location >= 0.382
```

The reference layer:
1. Maintains its own `_formed_refs` set
2. Calculates formation based on current price (location >= 0.382)
3. Tracks formation lifecycle independently of DAG

---

## Proposed Changes Summary

| Usage | Current Gate | New Gate | Notes |
|-------|-------------|----------|-------|
| **1. Formation check** (1173, 1208) | `leg.formed` | `leg.swing_id is not None` | Works |
| **2. Pivot breach tracking** (512) | `leg.formed` | `leg.max_origin_breach is not None` | Fixes zombie bug |
| **3. Engulfed pruning** (524) | `leg.formed` | Remove check entirely | Fixes zombie bug |
| **4. Counter-trend ratio** (617) | `leg.formed` | `leg.swing_id is not None` | Equivalent |
| **5. Set formed flag** (1190, 1226) | `leg.formed = True` | Remove | swing_id serves same purpose |
| **6. Impulse population** (1279) | N/A | No change | Still works |
| **7. Serialization** (state.py) | Serialize `formed` | Remove from serialization | Clean up |

---

## Key Architectural Insight

The DAG layer should track pure geometry and breaches:
- Leg geometry (origin, pivot, range)
- Breach state (max_origin_breach, max_pivot_breach)
- Structural relationships (parent_leg_id)

The "formation" concept (38.2% retracement threshold) should live in the reference layer, which already implements this via `_formed_refs`.

---

## Open Questions / Further Investigation Needed

1. **Swing inheritance edge cases:** When a leg inherits `swing_id` via proximity prune, should we update the SwingNode's prices to match the new leg's origin?

2. **Backward compatibility:** Old saved states have `formed` field. Need migration strategy.

3. **Test coverage:** Which tests rely on `formed` behavior? Need to update them.

4. **Reference layer impact:** Does reference layer use `leg.formed` anywhere, or only its own `_formed_refs`?

5. **Event emission:** Currently `SwingFormedEvent` is emitted when leg forms. If we remove `formed`, do we emit based on `swing_id` being set?

---

## Files to Modify

1. `src/swing_analysis/dag/leg.py` - Remove `formed` field
2. `src/swing_analysis/dag/leg_detector.py` - Update all usages
3. `src/swing_analysis/dag/leg_pruner.py` - Update all usages
4. `src/swing_analysis/dag/state.py` - Remove from serialization
5. Tests - Update as needed

---

## Next Steps

1. Answer open questions above
2. Check reference layer usage of `leg.formed`
3. Identify affected tests
4. Create implementation plan
5. File GitHub issue
