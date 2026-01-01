# DAG Updates

Collect DAG layer changes before proceeding to Reference Layer Phase 2.

---

## 1. Engulfed Prune Threshold

**Status:** Profiled, ready for implementation

**Problem:** Currently engulfed legs (both origin and pivot breached) are pruned immediately. Reference Layer may want to use recently-engulfed legs as references since it has looser tolerance for origin breach.

**Solution:** Add configurable threshold — only prune engulfed legs when at least one side exceeds threshold × range.

**Profiling Results (206K bars, es-30m):**

| Threshold | Retention Rate | Peak Overhead |
|-----------|---------------|---------------|
| 0.236 | 12.1% | +7.2% (13 legs) |
| 0.382 | 23.7% | +10.6% (19 legs) |

**Recommendation:** 0.236 threshold (first fib level)

**Implementation:**
1. Add `engulfed_prune_threshold: float = 0.236` to `DetectionConfig`
2. Modify `prune_engulfed_legs()`:
   ```python
   if leg.max_pivot_breach is not None and leg.max_origin_breach is not None:
       threshold = self.config.engulfed_prune_threshold
       if threshold == 0:
           # Immediate prune (legacy behavior)
           legs_to_prune.append(leg)
       else:
           threshold_amount = threshold * float(leg.range)
           if (float(leg.max_origin_breach) > threshold_amount or
               float(leg.max_pivot_breach) > threshold_amount):
               legs_to_prune.append(leg)
   ```

**Files:** `detection_config.py`, `leg_pruner.py`

**Resolves:** Known debt #240 (empirically determine engulfed retention threshold)

---

## 2. Engulfed Threshold UI

**Status:** Ready for implementation

**Problem:** Frontend has an engulfed on/off toggle that will effectively always be "on" going forward. Replace with a threshold slider that gives finer control.

**Changes:**

### Backend
- Keep `enable_engulfed_prune` in `DetectionConfig` but file GitHub issue as TODO to remove it later (code comments get forgotten)
- Add `engulfed_prune_threshold` field (from item #1)

### Frontend
- Remove engulfed toggle from Detection Config panel
- Add engulfed threshold slider with fib values: **0, 0.236, 0.382, 0.5, 0.618, 1**
  - 0 = immediate prune (legacy behavior)
  - 0.236 = recommended default
  - 1 = very permissive (retain until 100% breach)
- Follow existing slider patterns (turn ratio, branch ratio, etc.)

**Files:**
- BE: `detection_config.py` (add field)
- FE: Detection config panel component (remove toggle, add slider)
- API: Config endpoint (expose new field)

---

## 3. Simplify Turn Ratio Pruning

**Status:** Ready for implementation

**Problem:** Three turn ratio pruning modes exist, but two are suboptimal:

| Mode | Config | Behavior | Issue |
|------|--------|----------|-------|
| Threshold | `min_turn_ratio > 0` | Prune if ratio < threshold | Favors high-ratio **small** legs over medium-ratio **big** legs |
| Top-K by ratio | `max_turns_per_pivot > 0` | Keep K highest-ratio legs | Same issue — ratio favors small legs |
| **Raw counter-heft** | `max_turns_per_pivot_raw > 0` | Keep K highest `_max_counter_leg_range` | **Correct** — favors legs born from significant moves |

**Decision:** Keep only mode 3, remove modes 1 and 2, and rename for clarity.

### Naming Changes

**Concept rename:** "raw counter-heft" → **"counter-trend range"**

| Location | Before | After |
|----------|--------|-------|
| Config field | `max_turns_per_pivot_raw` | `max_legs_per_pivot` |
| Leg field | `_max_counter_leg_range` | `counter_trend_range` (remove underscore, it's not private) |
| UI label | "Max Turns (Raw)" | "Max Legs per Pivot" |
| Tooltip/help | (unclear) | "Keep top N legs at each pivot, ranked by counter-trend range" |

Since only one mode remains, "by counter-trend range" becomes implicit — no need for verbose names.

### Code Removal
- `detection_config.py`: Remove `min_turn_ratio`, `max_turns_per_pivot` fields and `with_*` methods
- `leg_pruner.py`: Remove threshold mode and top-k mode branches in `prune_by_turn_ratio()`
- Frontend: Remove corresponding UI controls
- API: Remove from config endpoint schema

### Code Rename
- `detection_config.py`: `max_turns_per_pivot_raw` → `max_legs_per_pivot`
- `leg.py`: `_max_counter_leg_range` → `counter_trend_range`
- `leg_pruner.py`: Update all references
- `leg_detector.py`: Update all references
- Frontend: Update label and field names

### Documentation
- Add section to `Docs/Reference/DAG.md`: **"Pruning Methods Tried and Discarded"**
- Document thoroughly:
  1. **Rationale:** Why we tried ratio-based modes (seemed intuitive that legs shouldn't "outgrow their context")
  2. **Finding:** Ratio-based pruning favors small legs. A leg with 10pt counter-trend extending to 20pt (ratio=0.5) survives, while a leg with 50pt counter-trend extending to 150pt (ratio=0.33) gets pruned — but the latter is structurally more significant.
  3. **Restoration path:** List all code changes with enough detail that an engineer agent can reverse them if needed.

**Files:**
- `detection_config.py`
- `leg.py`
- `leg_pruner.py`
- `leg_detector.py`
- Frontend config panel
- `Docs/Reference/DAG.md`

---

## 4. Remove Branch Ratio Domination

**Status:** Ready for implementation

**Problem:** Branch ratio is redundant with max_legs_per_pivot.

**What it does:**
- Creation-time filter comparing counter-trend at child's origin vs parent's origin
- Block if `child_counter_trend < min_branch_ratio × parent_counter_trend`

**Why retire:**
1. **Too soft on grandchildren** — by design, each level only needs 10% of parent's counter-trend, so deep descendants pass easily
2. **Redundant with max_legs_per_pivot** — for direct children, anything branch ratio would catch is already caught by the horizontal sibling filter

**Implementation:**

### Code Removal
- `detection_config.py`: Remove `min_branch_ratio` field and `with_min_branch_ratio()` method
- `leg_detector.py`: Remove `_is_origin_dominated_by_branch_ratio()` method and all call sites
- Frontend: Remove UI control
- API: Remove from config endpoint schema

### Documentation
- Add to `Docs/Reference/DAG.md` "Pruning Methods Tried and Discarded" section:
  1. **Rationale:** Vertical parent→child filter to prevent insignificant nested legs
  2. **Finding:** Redundant — max_legs_per_pivot catches the same cases horizontally, and branch ratio is too permissive for deep hierarchies (10% compounds: grandchild only needs 1% of grandparent)
  3. **Restoration path:** Code changes listed for reversal

**Files:**
- `detection_config.py`
- `leg_detector.py`
- Frontend config panel
- `Docs/Reference/DAG.md`

---

## 5. Clean Up Market Structure Stats Panel

**Status:** Ready for implementation

**Problem:** Stats panel shows broken/deprecated metrics and lacks tooltips.

### Current State

| Label | Meaning | Status |
|-------|---------|--------|
| Active | Active leg count | ✅ Keep |
| Engulfed | Engulfed prune count | ✅ Keep |
| Proximity | Proximity prune count | ✅ Keep |
| CTR | Counter-trend ratio prune | ❌ **Dead code** — `apply_min_counter_trend_prune()` never called, config doesn't exist |
| Turn | Turn ratio prune count | ⚠️ Rename to match new naming |
| Formed | Formed leg count | ❌ **Deprecated** — formation moved to Reference Layer |

### Changes

**Remove:**
- **CTR row** — delete from UI (dead code in backend too)
- **Formed row** — deprecated, no longer meaningful

**Rename:**
- **Turn → Max Legs** — to match `max_legs_per_pivot` naming from item #3

**Backend cleanup:**
- Delete `apply_min_counter_trend_prune()` method from `leg_pruner.py`
- Delete `minCtr` from frontend stats utils

**Verify Turn/Max Legs works:**
- Check if `turn_ratio_raw` events reach frontend
- If not, trace the API path and fix

### Add Tooltips

Add tooltips to all remaining stats explaining what each measures:

| Stat | Tooltip |
|------|---------|
| Active | "Currently tracked legs" |
| Engulfed | "Legs pruned after both origin and pivot breached" |
| Proximity | "Legs pruned due to similar origin (time + range)" |
| Max Legs | "Legs pruned to keep top N at each pivot by counter-trend range" |

**Files:**
- `frontend/src/components/MarketStructurePanel.tsx`
- `frontend/src/utils/legStatsUtils.ts`
- `src/swing_analysis/dag/leg_pruner.py` (delete dead method)

---

## 6. Reorganize Detection Config Panel

**Status:** Ready for implementation

**Problem:** Current organization (Global / Turn Ratio Pruning / Pruning Algorithms) doesn't reflect actual semantics after cleanup.

### New Layout

```
┌─ Pruning Thresholds ─────────────────────┐
│  Engulfed              ●───────── 0.236  │
│  Max Legs/Pivot        ────────●    10   │
│                                          │
│  Origin Proximity                        │
│    Range %             ───●────────  2%  │
│    Time %              ───●────────  2%  │
│                                          │
│  Stale Extension       ────────●   3.0   │
└──────────────────────────────────────────┘
```

### Tooltips

Every label gets a tooltip explaining its purpose:

| Label | Tooltip |
|-------|---------|
| **Pruning Thresholds** | "Controls which legs are pruned to reduce noise and keep significant structure" |
| Engulfed | "Retain engulfed legs until breach exceeds this fraction of range. 0 = immediate prune." |
| Max Legs/Pivot | "Keep top N legs at each pivot, ranked by counter-trend range. 0 = no limit." |
| **Origin Proximity** | "Consolidate legs with similar origins. Both Range AND Time must be within threshold." |
| Range % | "Legs within this range difference are candidates. Works with Time % — both must match." |
| Time % | "Legs formed within this time window are candidates. Works with Range % — both must match." |
| Stale Extension | "Prune invalidated child legs after price moves this multiple of their range beyond origin" |

### Fib Values for Engulfed Slider

Discrete stops: **0, 0.236, 0.382, 0.5, 0.618, 1**

**Files:**
- `frontend/src/components/DetectionConfigPanel.tsx`

---

## 7. Dynamic Bottom Panel Layout

**Status:** Ready for implementation

**Problem:** Followed Legs panel sits empty most of the time, wasting screen real estate.

### Current Layout (4 columns, fixed)

```
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│   BULL LEGS     │   BEAR LEGS     │  FOLLOWED LEGS  │  RECENT EVENTS  │
│                 │                 │  (often empty)  │                 │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

### New Layout (dynamic)

**When NOT following any legs:**
```
┌─────────────────┬─────────────────┬───────────────────────────────────┐
│   BULL LEGS     │   BEAR LEGS     │          RECENT EVENTS            │
│                 │                 │        (expanded, 2 cols)         │
└─────────────────┴─────────────────┴───────────────────────────────────┘
```

**When following legs:**
```
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│   BULL LEGS     │   BEAR LEGS     │  RECENT EVENTS  │  FOLLOWED LEGS  │
│                 │                 │                 │                 │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

### Changes

1. **Move Followed Legs to last position** — only appears when populated
2. **Recent Events expands** when Followed Legs is empty (conditional `col-span-2`)
3. **Followed Legs panel hidden** when `followedLegs.length === 0`

**Files:**
- `frontend/src/pages/DAGView.tsx` (or wherever bottom panel layout lives)
- `frontend/src/components/FollowedLegsPanel.tsx`

---

## Implementation Order

**Phase 1: Backend cleanup** (no UI changes, can verify with tests)
1. **Item #1** — Engulfed prune threshold logic
2. **Item #3** — Remove turn ratio threshold & top-k modes, rename to counter-trend range
3. **Item #4** — Remove branch ratio domination

**Phase 2: Config wiring** (BE + FE config sync)
4. **Item #2** — Engulfed threshold slider (replaces toggle)

**Phase 3: UI cleanup** (FE only)
5. **Item #5** — Clean up stats panel (remove CTR, Formed; rename Turn)
6. **Item #6** — Reorganize detection config panel + tooltips
7. **Item #7** — Dynamic bottom panel layout

**Notes:**
- Each phase can be a separate PR
- Phase 1 items can be parallelized
- Run full test suite after Phase 1

---

## Notes

- **Break compatibility intentionally** — remove old fields/methods completely, don't leave stubs
- If something breaks, surface it loudly (crash > silent failure)
- Run full test suite — fix any failures from renamed/removed fields
- Profile each change individually before combining
