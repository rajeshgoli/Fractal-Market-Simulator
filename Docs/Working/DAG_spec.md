# DAG-Based Swing Detection Specification

## Overview

This document specifies a streaming DAG-based algorithm for swing detection that achieves O(n log k) complexity instead of O(n k³), where n = number of bars and k = lookback window size.

**Core insight:** Instead of generating O(k²) candidate pairs and filtering by rules, build a structure where only valid swings exist by construction. Rules are enforced through temporal ordering, not post-hoc filtering.

---

## Definitions

### Leg

A **leg** is a directional price movement with known temporal ordering:

```
Bull leg: L (defended pivot) → H (origin)
  - Price moved from low L to high H
  - L occurred before H (temporal ordering established)

Bear leg: H (defended pivot) → L (origin)
  - Price moved from high H to low L
  - H occurred before L (temporal ordering established)
```

### Swing (Formed Leg)

A **swing** is a leg that has retraced at least 38.2% from origin toward pivot:

```
Bull swing formed when: (origin - close) / (origin - pivot) >= 0.382
Bear swing formed when: (close - origin) / (pivot - origin) >= 0.382
```

### DAG

The **DAG** (Directed Acyclic Graph) contains:
- Active legs being tracked
- Formed swings with parent-child relationships
- Pruning state (active, stale, invalidated)

---

## Bar Type Classification

Given two consecutive bars, classify the relationship:

| Type | Condition | Meaning |
|------|-----------|---------|
| Type 2-Bull | HH and HL | Trending up; establishes temporal order |
| Type 2-Bear | LH and LL | Trending down; establishes temporal order |
| Type 1 | LH and HL (inside) | Contained; no new information |
| Type 3 | HH and LL (outside) | Engulfing; high volatility decision point |

Where:
- HH = Higher High (bar2.high > bar1.high)
- HL = Higher Low (bar2.low > bar1.low)
- LH = Lower High (bar2.high < bar1.high)
- LL = Lower Low (bar2.low < bar1.low)

---

## Temporal Ordering Rules

Within a single bar, we do NOT know if high or low occurred first.

Temporal ordering is established by bar relationships:

| Sequence | Establishes |
|----------|-------------|
| Type 2-Bull | bar1.high occurred BEFORE bar2.low (bull leg possible) |
| Type 2-Bear | bar1.low occurred BEFORE bar2.high (bear leg possible) |
| Type 1 | No new ordering (wait for resolution) |
| Type 3 | Both orderings possible (decision point) |

---

## State Machine

### Active State

At any point, the DAG tracks:

```python
@dataclass
class Leg:
    direction: Literal['bull', 'bear']
    pivot_price: float      # Defended pivot
    pivot_index: int        # Bar index of pivot
    origin_price: float     # Current origin (extends as leg grows)
    origin_index: int       # Bar index of origin
    retracement_pct: float  # Current retracement percentage
    formed: bool            # Has 38.2% been reached?
    parent: Optional[Leg]   # Parent leg (if child)
    status: Literal['active', 'stale', 'invalidated']
    bar_count: int          # Bars since leg started (impulsiveness signal)
    gap_count: int = 0      # Number of gap bars in this leg
```

### Simultaneous Tracking

Both bull and bear legs can be active simultaneously. This represents market indecision ("chop"). One will eventually be invalidated.

Example after 5 bars:
```
Bull leg: 95 → 112 (active, formed)
Bear leg: 112 → 97 (active, formed, child of bull)
```

Neither 95 nor 112 invalidated yet. DAG holds both until decisive resolution.

---

## State Transitions

### Type 2-Bull Bar

```python
def process_type2_bull(bar, state):
    # Bull leg extends
    if state.bull_leg:
        state.bull_leg.origin_price = bar.high
        state.bull_leg.origin_index = bar.index
        state.bull_leg.retracement_pct = calc_retracement(state.bull_leg, bar.close)
        if state.bull_leg.retracement_pct >= 0.382:
            state.bull_leg.formed = True
    else:
        # Start new bull leg from previous low
        state.bull_leg = Leg(direction='bull', pivot=prev_low, origin=bar.high, ...)

    # Bear leg: check for violation
    if state.bear_leg and bar.high > state.bear_leg.pivot_price:
        # Origin exceeded - violation but NOT immediate prune
        # Keep tracking, may resolve via 2x staleness rule
        pass

    # Potential new bear leg from this high
    state.pending_bear_pivot = bar.high
```

### Type 2-Bear Bar

Symmetric to Type 2-Bull.

### Type 1 Bar (Inside)

```python
def process_type1(bar, state):
    # No new temporal information
    # Update retracement based on close
    for leg in state.active_legs:
        leg.retracement_pct = calc_retracement(leg, bar.close)
        if leg.retracement_pct >= 0.382:
            leg.formed = True
```

### Type 3 Bar (Outside)

```python
def process_type3(bar, state):
    # High volatility decision point
    # Both directions extended - keep both branches until resolution

    if state.bull_leg:
        state.bull_leg.origin_price = bar.high  # Origin extends
        # But also deeper retracement to bar.low

    if state.bear_leg:
        state.bear_leg.origin_price = bar.low   # Origin extends
        # But also retracement toward bar.high

    # Don't prune either - wait for decisive resolution
    # Either bar.high or bar.low will be violated eventually
```

---

## Formation Rules

A leg becomes a **formed swing** when:

```python
def check_formation(leg, close_price):
    if leg.direction == 'bull':
        retracement = (leg.origin_price - close_price) / (leg.origin_price - leg.pivot_price)
    else:  # bear
        retracement = (close_price - leg.origin_price) / (leg.pivot_price - leg.origin_price)

    if retracement >= 0.382:
        leg.formed = True
        add_to_dag(leg)
```

Formation triggers immediate DAG addition. No "settling period."

---

## Pruning Rules

### Rule 1: Decisive Invalidation (0.382 Rule)

A swing is **decisively invalidated** when price moves 38.2% of the swing's range beyond the defended pivot:

```python
def check_decisive_invalidation(swing, current_price):
    range_size = abs(swing.origin_price - swing.pivot_price)
    threshold = 0.382 * range_size

    if swing.direction == 'bull':
        invalidation_price = swing.pivot_price - threshold
        if current_price < invalidation_price:
            prune(swing)
            # Track the invalidating bear leg
            new_bear = Leg(
                direction='bear',
                pivot=swing.origin_price,
                origin=current_price,
                ...
            )
    else:  # bear
        invalidation_price = swing.pivot_price + threshold
        if current_price > invalidation_price:
            prune(swing)
            # Track the invalidating bull leg
```

### Rule 2: Staleness (2x Rule)

A swing is **stale** when price has moved 2x the swing's range without the swing changing:

```python
def check_staleness(swing, price_movement_since_last_change):
    range_size = abs(swing.origin_price - swing.pivot_price)
    if price_movement_since_last_change > 2 * range_size:
        if swing.last_modified == swing.created:  # Hasn't changed
            prune(swing)
```

This handles cases where neither branch is "decisively" invalidated but one became irrelevant.

### Pruning Cascades

When a swing is pruned, check its children:
- Children whose pivot derived from the pruned swing may also need pruning
- Children whose pivot is decisively violated by the same move are pruned

```python
def prune(swing):
    swing.status = 'invalidated'
    for child in swing.children:
        if child.pivot_derived_from(swing):
            # Check if child's pivot is also invalidated
            if is_invalidated(child, current_price):
                prune(child)
```

---

## Parent-Child Relationships

Parent-child is about **pivot derivation**, not range containment. A child can grow larger than its parent.

**Example:**
```
1. Bear leg: 130 → 100 (origin=130, pivot=100 defended)
2. Bull leg forms: 100 → 140 (child, pivot derived from bear's defended pivot)
3. Drops to 120, rallies to 150
4. Bull leg now: 100 → 150 (range [100,150] exceeds bear's [100,130])
5. Still a child! Pivot 100 derived from parent structure.
6. If 100 violated: BOTH parent and child invalidated.
```

A swing B is a **child** of swing A if:
1. B's defended pivot originated from within A's structure (typically A's defended pivot or a retracement point)
2. A's defended pivot remains unviolated

```python
def establish_parent(new_swing, dag):
    # Find the swing whose structure gave rise to new_swing's pivot
    for candidate_parent in dag.active_swings:
        if pivot_derived_from(new_swing, candidate_parent):
            new_swing.parent = candidate_parent
            candidate_parent.children.append(new_swing)
            break

def pivot_derived_from(child, parent):
    # Child's pivot came from parent's defended pivot or retracement
    # This is tracked during formation, not computed geometrically
    return child.pivot_source == parent.id or child.pivot_source == parent.pivot_id
```

**Key insight:** The hierarchy tracks pivot dependencies, not geometric containment. A child that "outgrows" its parent is still invalidated if the shared pivot breaks.

---

## Complexity Analysis

| Operation | Current Algorithm | DAG Algorithm |
|-----------|-------------------|---------------|
| Per bar: candidate generation | O(k²) | O(1) - direct tracking |
| Per bar: pre-formation check | O(k) per pair | O(1) - by construction |
| Per bar: separation check | O(s) per pair | O(log s) - tree traversal |
| **Total per bar** | O(k² × (k + s)) | O(log s) |
| **Total for n bars** | O(n × k³) | O(n × log s) |

Where:
- n = number of bars (10,000)
- k = lookback window (~50)
- s = number of active swings (~log n due to pruning)

**Expected improvement:** From O(n × k³) ≈ 10B operations to O(n × log n) ≈ 130K operations.

---

## Edge Cases

### Case 1: First Bar

Open → Close ordering is known. Initialize with O → C leg:

```python
if bar.close > bar.open:
    # Bull leg: O → C
    state.active_leg = Leg(
        direction='bull',
        pivot_price=bar.open,
        origin_price=bar.close,
        ...
    )
elif bar.close < bar.open:
    # Bear leg: O → C
    state.active_leg = Leg(
        direction='bear',
        pivot_price=bar.open,
        origin_price=bar.close,
        ...
    )
```

H and L cannot be used yet—their temporal ordering within the bar is unknown. Wait for subsequent bars to establish whether H or L can extend the leg.

### Case 2: Type 1 Bars (Inside Bars)

Type 1 bars are NOT "no information" — they can:

1. **Inform retracement using H/L directly**: Since the inside bar's extremes are from a DIFFERENT bar than the leg's origin, temporal ordering is known. Use H/L, not just close.

2. **Establish two legs (if second bar)**: When bar2 is inside bar1, we gain temporal ordering for BOTH directions:
   - bar1.H occurred before bar2.L → bear leg: H1 → L2, retracement uses L2
   - bar1.L occurred before bar2.H → bull leg: L1 → H2, retracement uses H2

```python
def process_type1(bar, state):
    # Type 1 means: bar.H < prev.H and bar.L > prev.L
    # Extremes are from different bars → temporal order known

    if state.bear_leg:
        # Can use bar.L directly (prev.H was before bar.L)
        state.bear_leg.update_retracement(bar.low)

    if state.bull_leg:
        # Can use bar.H directly (prev.L was before bar.H)
        state.bull_leg.update_retracement(bar.high)
```

**Contrast with Type 2**: For Type 2-Bull (HH, HL), the new high is from the CURRENT bar. We don't know if current bar's L was before or after its H, so we must use Close for retracement.

### Case 3: Consecutive Type 3 Bars

High volatility. Each bar potentially creates new branches. Apply 2x staleness rule aggressively to prevent unbounded growth.

### Case 4: Gap Up/Down

Gaps are structurally just large Type 2 bars. Nothing special:

- **Gap up** (bar.low > prev.high): Type 2-Bull with clear temporal ordering
- **Gap down** (bar.high < prev.low): Type 2-Bear with clear temporal ordering

May immediately invalidate opposite legs due to the large move. The `gap_count` field on Leg tracks how many gap bars occurred within a leg (useful signal for impulsiveness).

### Case 5: Multiple Swings from Same Pivot

The DAG tracks ALL swings from the same pivot as siblings. No separation filtering at DAG level — that belongs in the Reference layer. The DAG's job is structural tracking; semantic filtering (0.15/0.1 separation thresholds) happens downstream.

---

## Data Structures

### PendingPivot

A pending pivot is a potential defended pivot that hasn't yet been confirmed by temporal ordering.

```python
@dataclass
class PendingPivot:
    price: float
    bar_index: int
    direction: Literal['bull', 'bear']  # What leg type this could start
    source: Literal['high', 'low', 'open', 'close']
```

**Semantics:**
- `pending_pivots['bull']` — Lowest unviolated low; could become a bull leg's defended pivot
- `pending_pivots['bear']` — Highest unviolated high; could become a bear leg's defended pivot

**Lifecycle:**
1. **Created** when a bar establishes a new extreme (for the opposite direction)
2. **Confirmed** when subsequent bar establishes temporal ordering → becomes active leg
3. **Superseded** when a more extreme candidate appears in same direction
4. **Invalidated** when price violates it before confirmation

**Example:**
```
Bar 1: H=105, L=100, C=102
  → pending_pivots['bear'] = PendingPivot(105, 1, 'bear', 'high')
  → pending_pivots['bull'] = PendingPivot(100, 1, 'bull', 'low')

Bar 2: H=103, L=95, C=97  (Type 2-Bear)
  → Temporal order established: bar1.H before bar2.L
  → pending_pivots['bear'] confirmed → active bear leg: 105 → 95
  → pending_pivots['bull'] superseded by 95 (lower low)
  → pending_pivots['bull'] = PendingPivot(95, 2, 'bull', 'low')
```

### SwingDAG

```python
@dataclass
class SwingDAG:
    active_legs: List[Leg]          # Currently being tracked
    formed_swings: List[Swing]      # In DAG with parent-child links
    pending_pivots: Dict[Literal['bull', 'bear'], Optional[PendingPivot]]

    def process_bar(self, bar: Bar) -> List[Swing]:
        bar_type = classify_bar(bar, self.prev_bar)

        if bar_type == Type2Bull:
            self._process_type2_bull(bar)
        elif bar_type == Type2Bear:
            self._process_type2_bear(bar)
        elif bar_type == Type1:
            self._process_type1(bar)
        elif bar_type == Type3:
            self._process_type3(bar)

        self._check_formations(bar.close)
        self._check_invalidations(bar)
        self._check_staleness()

        self.prev_bar = bar
        return self.get_active_swings()
```

---

## Lookup Operations

| Query | Complexity | Method |
|-------|------------|--------|
| Is swing X invalidated? | O(1) | Direct price comparison |
| Active swings at price P | O(log s) | Tree traversal |
| Parent of swing X | O(1) | Stored in node |
| Children of swing X | O(1) | Stored in node |

---

## Design Decision: Separation of Concerns

**DAG and Reference calculation are separate layers.**

| Layer | Responsibility | Rules |
|-------|----------------|-------|
| **DAG** | Track extremas efficiently | 0.382 invalidation, 2x staleness |
| **Reference** | Define "good reference" for trading | 0.15/0.1 separation thresholds |

The DAG answers: "What pivots exist?" (structural tracking)
Reference answers: "Which swings are useful?" (semantic/trading logic)

**Why separate:**
- DAG stays simple and O(n log k)
- Reference logic can evolve without touching DAG
- No business rules baked into the data structure
- Easy to experiment with different reference definitions

**Implementation:** DAG produces all valid extremas. Reference layer filters/selects from DAG output using separation and other criteria.

---

## Open Questions

1. **Staleness threshold:** 2x is the initial value (also a Fibonacci extension). Make configurable via SwingConfig — empirically derived, will validate in practice.

---

## Next Steps

**Status:** Spec approved by Architecture (Dec 19). Ready for implementation.

1. Implement DAG-based algorithm as drop-in replacement for HierarchicalDetector
2. Benchmark performance on 10K+ bar datasets (target: <5s for 10K)
3. Validate output correctness through manual inspection (no trusted baseline)
4. Refine pruning rules (2x staleness) based on empirical results
