# Turn Limit Pruning

## Problem

During extended moves, multiple legs accumulate with pivots extending to the same extreme. For example, during a bull run from 100 to 150, several bull legs may form at different origins (100, 110, 115, 120) but all extend their pivots to 150. When price finally turns, we have too many legs at this shared pivot.

This happens because pivot extension preserves all legs whose origins haven't been breached. Without pruning, leg count grows unbounded at significant turning points.

## Solution: Turn Limit Pruning

Limit the number of counter-direction legs at each significant turn to a configurable maximum (default: 5). Legs are ranked by structural significance and only the top N survive.

### Trigger Condition

When a new leg L_new forms at origin O_new **and** reaches a minimum size threshold relative to the largest counter-leg at that pivot:

```
L_new.range >= min_turn_threshold * max(counter_legs with pivot=O_new).range
```

This ensures we only prune at significant turns, not at small pivots that may give way.

### Algorithm

**Step 1: Find candidate legs**
- Find all counter-direction legs whose pivot = O_new
- These legs all "converged" to turn at O_new

**Step 2: Score each candidate**
- For each leg L_i with origin O_i:
  - Find counter-direction legs (to L_i) whose pivot = O_i
  - Score = max(range) of those legs
  - This measures: "How significant was the counter-trend move that established L_i's origin?"

**Step 3: Rank and prune**
- Sort candidates by score descending
- Keep top N (configurable via `max_legs_per_turn`)
- Prune the rest
- Reparent children of pruned legs
- Emit `LegPrunedEvent` with reason `"turn_limit"`

### Edge Case: First Leg

If a leg's origin has no counter-leg pointing at it (start of data), treat its score as infinite. This ensures the first leg always survives.

## Worked Example

**Price action:**
```
0. 130 → 100: Bear R0 (origin=130, pivot=100, range=30)
1. 100 → 120: Bull B1 (origin=100, pivot=120)
2. 120 → 110: Bear R1 (origin=120, pivot=110, range=10)
3. 110 → 130: B1→130, B2 forms (origin=110, pivot=130)
4. 130 → 115: Bear R2 (origin=130, pivot=115, range=15)
5. 115 → 140: B1→140, B2→140, B3 forms (origin=115, pivot=140)
6. 140 → 120: Bear R3 (origin=140, pivot=120, range=20)
7. 120 → 150: B1→150, B2→150, B3→150, B4 forms (origin=120, pivot=150)
8. 150 → 125: New bear leg forms at origin=150
```

**At step 8:** Bear leg forms at origin=150. Once it reaches threshold size, trigger turn pruning.

Find bull legs with pivot=150: B1, B2, B3, B4

**Scoring:**
| Leg | Origin | Counter-leg at origin | Score |
|-----|--------|----------------------|-------|
| B1 | 100 | R0 (range=30) | 30 |
| B2 | 110 | R1 (range=10) | 10 |
| B3 | 115 | R2 (range=15) | 15 |
| B4 | 120 | R3 (range=20) | 20 |

**With max_legs_per_turn=3:** Keep B1(30), B4(20), B3(15). Prune B2(10).

B1 survives because the pullback that established its origin (R0) was the largest. The leg that started the whole move is backed by the biggest counter-trend.

## Why This Is Fractal

The scoring depends on counter-legs, which are themselves subject to the same pruning rule. Only structurally significant levels survive at each scale, creating a self-similar hierarchy.

## Configuration

### Backend

```python
@dataclass
class SwingConfig:
    # Maximum counter-direction legs per turn. 0 = disabled.
    max_legs_per_turn: int = 0

    # Minimum size of new leg (as fraction of largest counter-leg)
    # to trigger turn pruning. Prevents pruning at small pivots.
    min_turn_threshold: float = 0.236
```

### Frontend

Add slider to `DetectionConfigPanel` in **Global** section (after Branch Ratio):
- **Label:** "Max Legs/Turn"
- **Type:** Slider (match existing style)
- **Range:** 0-10 (0 = disabled)
- **Display:** Integer value
- **Persistence:** Save to session settings

## Integration Points

### Where to Check

In `LegDetector._check_leg_formations()` or similar, after a leg forms:
1. Check if leg has reached threshold relative to largest counter-leg
2. If so, call `LegPruner.prune_turn_limit()`

### LegPruner Method

```python
def prune_turn_limit(
    self,
    state: DetectorState,
    new_leg: Leg,
    bar: Bar,
    timestamp: datetime,
) -> List[LegPrunedEvent]:
    """
    Prune counter-direction legs at a turn when too many share the same pivot.

    Triggered when new_leg reaches min_turn_threshold of the largest counter-leg.
    Keeps top max_legs_per_turn by score, prunes the rest.
    """
```

### Events

Emit `LegPrunedEvent` with:
- `reason="turn_limit"`
- `explanation="Scored {score} vs threshold; kept top {N}"`
