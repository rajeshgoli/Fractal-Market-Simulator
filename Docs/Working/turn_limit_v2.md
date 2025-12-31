# Turn Limit Pruning v2

## Problem with Current Implementation

Turn limit pruning (#340) doesn't work as intended. The core issues:

### Issue 1: Formation Timing

Legs "form" when they're tiny, then extend to much larger sizes:

```
Bar 6422: Bear leg forms
  origin=1586.75, pivot=1580.50, range=6.25

Bar 20000: Same leg after extension
  origin=1586.75, pivot=739.00, range=847.75
```

Turn limit triggers at formation (range=6.25), but the leg grows 135x larger afterward.

### Issue 2: Threshold Asymmetry

The threshold check compares a newly-forming leg against already-extended counter-legs:

```python
threshold_ratio = new_leg.range / largest_counter.range
# 6.25 / 212.25 = 2.9% < 23.6% threshold → NO PRUNE
```

Counter-legs had time to extend; the new leg is checked at its smallest point.

### Issue 3: No Scale-Aware Survival

Legs that survive pruning at a large scale (e.g., 300-point turn) shouldn't compete with legs from smaller scales (e.g., 50-point turn). Currently all legs compete in the same pool.

## Proposed Solution

Three changes working together:

### Change 1: Reset `formed` on Pivot Extension

When a leg's pivot extends, reset `formed=False`. The leg must re-form at its new size.

**Why this works**: Formation requires 38.2% retracement from pivot. As the leg extends:
- Pivot moves further from origin
- Formation threshold (in price) moves with it
- Leg only "confirms" when market shows meaningful retrace at the new scale

**Example**:
```
Bull leg 100→200 (range=100)
  Formation price = 200 - 38.2% × 100 = 161.8
  Price at 160 → forms (40% retrace)

Price extends to 250 (range=150)
  formed=False (proposed change)
  New formation price = 250 - 38.2% × 150 = 192.7
  Price at 180 → does NOT form (only 20.8% retrace)
  Price at 190 → forms (40% retrace)
```

The leg only confirms when there's a meaningful retrace at its TRUE size.

### Change 2: Track `survived_at_scale`

Each leg tracks the scale (counter-move range) at which it survived a turn limit pruning.

```python
@dataclass
class Leg:
    ...
    survived_at_scale: Optional[Decimal] = None  # Range of counter-move when survived
```

### Change 3: Scale-Aware Pruning

Turn limit only prunes legs at or below the current scale. Veterans from larger-scale prunings are protected.

## Revised Algorithm

### Trigger Condition

When a leg L_new **forms** (reaches 38.2% retracement from pivot).

### Step 1: Find Candidates

Find counter-direction legs whose `pivot_price == L_new.origin_price`.

```python
candidates = [
    leg for leg in active_legs
    if leg.direction != L_new.direction
    and leg.pivot_price == L_new.origin_price
    and leg.status == 'active'
]
```

### Step 2: Filter by Scale

Partition candidates into protected vs. eligible:

```python
protected = []
eligible = []

for leg in candidates:
    if leg.survived_at_scale is not None and leg.survived_at_scale >= L_new.range:
        protected.append(leg)  # Survived at larger scale, skip
    else:
        eligible.append(leg)   # Compete for slots
```

If a leg survived a 300-point turn, it won't be pruned by a 150-point turn.

### Step 3: Check Slot Availability

```python
available_slots = max_legs_per_turn - len(protected)

if len(eligible) <= available_slots:
    # Not enough legs to require pruning
    return
```

### Step 4: Score Eligible Legs

Score = max range of counter-direction legs at this leg's origin.

This measures: "How significant was the counter-trend move that established this leg's origin?"

```python
def score_leg(leg):
    opposite = 'bear' if leg.direction == 'bull' else 'bull'
    counter_legs_at_origin = [
        l for l in active_legs
        if l.direction == opposite
        and l.pivot_price == leg.origin_price
    ]
    if not counter_legs_at_origin:
        return float('inf')  # First leg survives
    return max(l.range for l in counter_legs_at_origin)
```

### Step 5: Rank and Prune

```python
# Sort by score descending (highest = most significant)
eligible.sort(key=lambda leg: -score_leg(leg))

# Keep top N, prune rest
survivors = eligible[:available_slots]
to_prune = eligible[available_slots:]

for leg in to_prune:
    leg.status = 'pruned'
    emit LegPrunedEvent(reason="turn_limit", ...)
```

### Step 6: Update Survivors

```python
for leg in survivors:
    # Track the scale at which they survived (keep max)
    if leg.survived_at_scale is None:
        leg.survived_at_scale = L_new.range
    else:
        leg.survived_at_scale = max(leg.survived_at_scale, L_new.range)
```

## Worked Example

### Setup

Price action: 600 → 300 → 500 → 200 → 400

**Phase 1: 600→300**
- 15 bear legs form with pivots extending to 300
- Origins at: 600, 590, 580, 570, 560, 550, 540, 530, 520, 510, 500, 490, 480, 470, 460

**Phase 2: 300→500**
- Bull leg B1 forms at origin=300, range=200
- Turn limit triggers:
  - Candidates: 15 bear legs with pivot=300
  - All have survived_at_scale=None → all eligible
  - Score by counter-trend range at each origin
  - Keep top 5, prune 10
  - Survivors get survived_at_scale=200

**Phase 3: 500→200**
- 10 new bear legs form (origins 500, 490, 480, ...)
- Their pivots extend to 200
- The 5 survivors from Phase 2 also extend pivots to 200 (if origins not breached)

**Phase 4: 200→400**
- Bull leg B2 forms at origin=200, range=200
- Turn limit triggers:
  - Candidates: 5 veterans + 10 newcomers = 15 bear legs with pivot=200
  - Filter by scale:
    - Veterans: survived_at_scale=200, current range=200 → 200 >= 200 → **protected**
    - Newcomers: survived_at_scale=None → **eligible**
  - Available slots: 5 - 5 = 0 (veterans fill all slots!)
  - Newcomers all get pruned
  - Veterans survive again

**Result**: The structurally important legs from the 600→300 move survive through multiple turns.

### If Current Move is Larger

Price action: 600 → 300 → 500 → 100 → 450

**Phase 4 (revised): 100→450**
- Bull leg forms at origin=100, range=350 (larger than 200!)
- Turn limit triggers:
  - Veterans: survived_at_scale=200, current range=350 → 200 < 350 → **eligible**
  - Newcomers: also eligible
  - Everyone competes! This is a structural reset.
  - Score all 15 legs, keep top 5

**Result**: A larger move "resets" the hierarchy. All legs must prove themselves again.

## Edge Cases

### Engulfed Legs with Reset Formation

Concern: If `formed` resets on extension, will engulfed pruning still work?

**Scenario**:
1. Bull leg 100→200, forms at 160
2. Price to 201 → pivot extends, formed=False
3. Flash crash to 90 → origin breached
4. Rally to 210

**Analysis**:
- At 210, retracement = (210-100)/101 = 108% > 38.2% → leg **re-forms**
- Pivot breach detected: 210 > 201
- Both origin_breached and pivot_breached → **engulfed → pruned**

The natural re-formation handles this. No special case needed.

### Spike Bars

If a bar has high=300, close=150 on a bull leg 100→300:
- Pivot extends to 300, range=200
- Formation threshold = 300 - 76.4 = 223.6
- Close at 150 < 223.6 → doesn't form immediately
- Forms when price later rises above 223.6 or if bar.high is used for formation check

This is correct behavior - spike bars shouldn't immediately confirm structure.

### First Leg (No Counter-Trend)

A leg with no counter-leg at its origin gets score=infinity and always survives.
This preserves existing behavior.

## Implementation Tasks

### Backend

1. **Leg dataclass** (`leg.py`):
   - Add `survived_at_scale: Optional[Decimal] = None`

2. **Pivot extension** (`leg_detector.py`):
   - In `_extend_leg_pivots()`, after updating pivot:
     ```python
     leg.formed = False
     ```

3. **Turn limit pruning** (`leg_pruner.py`):
   - Rewrite `prune_turn_limit()` with:
     - Scale-based filtering
     - Slot availability check
     - Survivor scale tracking
   - Remove or adjust `min_turn_threshold` check (may no longer be needed)

4. **Serialization** (`state.py`):
   - Include `survived_at_scale` in leg serialization

### Testing

1. Test formation reset on pivot extension
2. Test scale-aware filtering (veterans protected)
3. Test structural reset (larger move makes everyone compete)
4. Test engulfed pruning still works with formation reset
5. Test spike bar handling
6. Test first leg (infinite score) survival

### Frontend

No changes needed - existing "Max Legs/Turn" slider controls the behavior.

## Open Questions

1. **Should `min_turn_threshold` be removed?** With formation reset, the threshold check may be redundant - formation already requires meaningful retrace.

2. **What about proximity pruning?** Should it also respect `survived_at_scale`?

3. **Serialization of `survived_at_scale`**: Store as string decimal for JSON compatibility?
