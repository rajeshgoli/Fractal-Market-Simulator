# Analysis: Removing `formed` and `SwingNode` from DAG Layer

**Status:** Approved — epic filed as #394
**Started:** 2025-12-31
**Origin:** Feedback observation `27680162-15ed-4bbb-8d4b-9c074ebb32ef`
**Architect Review:** Dec 31, 2025 — Approved with expanded scope (includes Reference Layer API consolidation)
**Implementation:** [#394](https://github.com/rajeshgoli/Fractal-Market-Simulator/issues/394)

**Cross-references:**
- `reference_layer_spec.md` Rev 6 — DAG Contract section documents target state
- `architect_notes.md` — DAG Cleanup Epic section has implementation breakdown

---

## Executive Summary

Investigation revealed that both `formed` and `SwingNode` are architectural mistakes in the DAG layer:

1. **`formed`** — A trading concept (38.2% threshold) that leaked into DAG
2. **`SwingNode`** — Redundant wrapper around Leg geometry (1:1 mapping)
3. **`swing_id`** — Single-leg identifier masquerading as "linkage" concept

**Decision:** Remove all three from DAG. Formation logic belongs in Reference Layer (which already implements it via `_formed_refs`).

---

## The Zombie Leg Bug (Original Trigger)

### Observation Details
- **Leg:** `leg_bull_3995.5_179577`
- **Origin:** 3995.5 @ bar 179577
- **Pivot:** 4030.5 @ bar 179578
- **Range:** 35.0 points

### What Happened
At playback bar 19999:
- `formed: False` — leg NEVER formed
- `max_origin_breach: 493.5` — origin was breached (price went to 3502.0)
- `max_pivot_breach: None` — pivot breach was NEVER tracked

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

If origin is breached BEFORE formation:
1. Leg can never form (formation check requires `max_origin_breach is None`)
2. Pivot breach is never tracked (requires `formed`)
3. Engulfed pruning never fires (requires both breaches)
4. Result: immortal zombie leg

---

## Why This Is An Architectural Problem

### DAG Primitives Should Be Pure Geometry

**What DAG should track:**
- Legs with origin/pivot/range
- Breach state (max_origin_breach, max_pivot_breach)
- Structural validity (origin defended, pivot not violated)

**What doesn't belong in DAG:**
- 38.2% retracement threshold (trading concept)
- "Formation" status (reference layer concept)
- SwingNode (redundant wrapper)

### SwingNode Is Just a Leg Copy

Current SwingNode:
```python
swing_id: str
high_bar_index: int
high_price: Decimal
low_bar_index: int
low_price: Decimal
direction: Literal["bull", "bear"]
status: Literal["forming", "active", "invalidated", "completed"]
formed_at_bar: int
```

This is **identical** to Leg geometry. SwingNode doesn't represent "legs linked at pivots" — it's just a promoted Leg with a different prefix.

### swing_id Is Single-Leg Identity

```python
# leg.py:136
def make_swing_id(direction, origin_price, origin_index) -> str:
    return f"swing_{direction}_{origin_price}_{origin_index}"
```

swing_id is derived from ONE leg's properties. It doesn't represent structural linkage between legs.

---

## What Gets Removed

| Component | Location | Action |
|-----------|----------|--------|
| `SwingNode` class | `swing_node.py` | Delete file |
| `formed` field | `Leg` dataclass | Remove |
| `swing_id` field | `Leg` dataclass | Remove |
| `active_swings` list | `DetectorState` | Remove |
| `formed_at_bar` concept | `SwingNode` | Remove (Reference Layer owns) |
| `fib_levels_crossed` dict | `DetectorState` | Move to Reference Layer |
| `formed_leg_impulses` list | `DetectorState` | Rename to `leg_impulses` (all legs) |

---

## Events Impact

| Event | Current | After Removal |
|-------|---------|---------------|
| `SwingFormedEvent` | Emitted at 38.2% threshold | Move to Reference Layer |
| `SwingInvalidatedEvent` | Origin breached on formed leg | Remove (use `LegInvalidatedEvent`) |
| `SwingCompletedEvent` | 2.0 target reached | Move to Reference Layer |
| `LevelCrossEvent` | Fib level crossed | Move to Reference Layer |
| `LegCreatedEvent` | Keep | No change |
| `LegPrunedEvent` | Keep | Remove `swing_id` field |
| `LegInvalidatedEvent` | Keep | No change |
| `OriginBreachedEvent` | Keep | Remove `swing_id` field |
| `PivotBreachedEvent` | Keep | Remove `swing_id` field |

---

## Fixes for Zombie Bug

With `formed` removed, the gates change:

| Usage | Current Gate | New Gate |
|-------|-------------|----------|
| Pivot breach tracking | `leg.formed` | `leg.max_origin_breach is not None` |
| Engulfed pruning | `not leg.formed` | Remove check entirely |
| Formation check skip | `leg.formed` | Remove (no formation in DAG) |
| CTR ratio check | `leg.formed` | Remove (Reference Layer concern) |

**Result:** Zombie legs will now be properly pruned when engulfed.

---

## What Stays in DAG

Pure geometry and structural validity:
- `Leg` with origin/pivot/range
- `leg_id` for identity
- Breach tracking (`max_origin_breach`, `max_pivot_breach`)
- `LegCreatedEvent`, `LegPrunedEvent`, `LegInvalidatedEvent`
- `OriginBreachedEvent`, `PivotBreachedEvent`

---

## What Moves to Reference Layer

Trading-relevant concepts (Reference Layer already implements most of this):
- Formation threshold (38.2%) — already in `_formed_refs`
- Fib level tracking — already in spec as opt-in
- "Formed" state for references — already in `_is_formed_for_reference`
- Completion (2.0 target) — spec describes this
- Scale-dependent behavior — spec describes this

---

## Files to Modify

### DAG Layer (Core Changes)

1. `src/swing_analysis/swing_node.py` — Delete entirely
2. `src/swing_analysis/dag/leg.py` — Remove `formed`, `swing_id`, `make_swing_id()`
3. `src/swing_analysis/dag/leg_detector.py` — Remove all formation logic, SwingNode creation, `get_active_swings()`
4. `src/swing_analysis/dag/leg_pruner.py` — Remove `formed` gates, fix engulfed pruning
5. `src/swing_analysis/dag/state.py` — Remove `active_swings`, `fib_levels_crossed`
6. `src/swing_analysis/events.py` — Remove swing events, update leg events

### Reference Layer Consolidation (Expanded Scope)

**Architect review revealed:** Reference Layer has TWO parallel APIs:
- New: `update(List[Leg])` → `ReferenceState` (Phase 1)
- Old: `get_reference_swings(List[SwingNode])` → `ReferenceSwingInfo` (legacy)

The old API is still actively called in `replay.py` (10 sites) and `calibrate.py` (2 sites).

7. `src/swing_analysis/reference_layer.py` — Delete legacy methods:
   - `ReferenceSwingInfo` dataclass
   - `get_reference_swings()`
   - `check_invalidation()`
   - `check_completion()`
   - `get_big_swings()`
   - `update_invalidation_on_bar()`
   - `update_completion_on_bar()`
   - `get_swing_info()`
   - `_compute_big_swing_threshold()`
   - `_is_big_swing()`
   - `_compute_tolerances()`

### API Layer

8. `src/ground_truth_annotator/schemas.py` — Remove `formed` from `LegInfo`
9. `src/ground_truth_annotator/routers/replay.py` — Migrate to `update()` API, remove SwingNode usage
10. `src/swing_analysis/dag/calibrate.py` — Migrate to `update()` API

### Frontend

11. `frontend/src/types.ts` — Remove `formed` from leg types
12. `frontend/src/utils/legStatsUtils.ts` — Remove formed counting
13. `frontend/src/components/MarketStructurePanel.tsx` — Remove formed display

### Tests

14. Update all tests that reference `formed`, `swing_id`, or `SwingNode`

---

## Implementation Order

1. **Fix zombie bug first** — Change pivot breach gate from `formed` to `max_origin_breach is not None`
2. **Remove SwingNode** — Delete class, remove from state
3. **Remove swing_id** — From Leg and events
4. **Remove formed** — From Leg and all gates
5. **Clean up events** — Remove swing events, update leg events
6. **Update API/Frontend** — Remove formed from schemas and UI
7. **Update tests** — Fix all broken assertions

---

## Appendix: Investigation Q&A

### Q: SwingFormedEvent is tied to `formed` field?

**A:** No. They're set at the same time, but the event doesn't depend on the field:

```python
# leg_detector.py:1188-1190
if retracement >= formation_threshold:
    leg.formed = True  # Would be removed
    event = self._form_swing_from_leg(leg, bar, timestamp)  # Still emits event
```

The emission is triggered by the threshold check, not by reading `leg.formed`. The event name "SwingFormed" describes the action ("a swing was just formed"), not the field.

---

### Q: If SwingNode creation depends on formation threshold, isn't the threshold still used?

**A:** Yes — that's the architectural problem. The proposal removes `formed` field but keeps threshold-gated SwingNode creation. This is just renaming `formed` to `swing_id is not None`.

The correct model:
- DAG: Pure geometry (legs with origin/pivot)
- Reference Layer: Formation threshold (38.2%) determines trading relevance

---

### Q: What does SwingNode actually represent?

**A:** A single leg's geometry (1:1 with Leg). It's NOT a linkage between two legs:

```python
# swing_node.py
swing_id: str           # Single leg identifier
high_bar_index: int     # From leg
high_price: Decimal     # From leg
low_bar_index: int      # From leg
low_price: Decimal      # From leg
```

swing_id is derived from ONE leg: `swing_{direction}_{origin_price}_{origin_index}`

---

### Q: What would break if every leg had swing_id from creation?

**A:** Several things:
1. Event semantics — LegCreatedEvent has `swing_id=""` as signal "not a swing yet"
2. Serialization — Can't distinguish formed vs unformed legs
3. Frontend linger logic — Uses swing_id presence to identify swing events

But this is the wrong question. The right question is: why does DAG need swing_id at all?

---

### Q: Why remove swing_id entirely instead of assigning at creation?

**A:** swing_id serves two purposes in current code:
1. **Identity** — Links Leg ↔ SwingNode
2. **Formation marker** — `swing_id is not None` = "formed"

If we remove SwingNode, purpose #1 disappears. Purpose #2 should be Reference Layer's concern. Therefore swing_id has no purpose in DAG.

---

### Q: What about the frontend — it uses `formed` for display?

**A:** Clean deletion across all layers:
- Backend: Remove `formed` from Leg
- API: Remove `formed` from LegInfo schema
- Frontend: Remove `formed` from types and display

No compatibility shim. The concept doesn't belong anywhere — Reference Layer has its own `_formed_refs` that tracks formation for trading purposes.

---

### Q: Should we keep SwingFormedEvent name?

**A:** The event moves to Reference Layer. Could rename to `ReferenceFormedEvent` for clarity, but "SwingFormed" as a verb ("a swing was just formed") is still accurate.

---

### Q: How can origin breach (100%) happen BEFORE 38.2% formation?

**A:** Valid market behavior. Traced the zombie leg:

```
Bar 4473: L=3995.5 (becomes origin)
Bar 4474: O=4017.75 H=4030.5 L=3997.0 C=4001.75
  → Bull leg created: origin=3995.5, pivot=4030.5, range=35
  → Formation uses CLOSE: (4001.75 - 3995.5) / 35 = 17.86%
  → Threshold = 23.6% → NOT FORMED
Bar 4475: L=3970.0 (below origin!)
  → ORIGIN BREACHED (only 1 bar after creation!)
```

The bar's HIGH reached the pivot (100%), but CLOSED at only 17.86%. Formation uses close (conservative). The next bar dropped below origin.

---

### Q: What is the point of `range == 0` checks?

**A:** Defensive guard against edge case where origin_price == pivot_price:

```
Bar 1: Low=100, High=110 → pending bull origin = 100
Bar 2: Low=95, High=100  → bull leg: origin=100, pivot=100 → range=0
```

Prevents division by zero in retracement/ratio calculations. Keep these checks.
