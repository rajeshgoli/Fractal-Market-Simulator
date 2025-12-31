# Proximity Pruning Redesign: Counter-Trend Scoring

## Problem Statement

Current proximity pruning keeps the **oldest** leg in a cluster and prunes newer legs within proximity. This is purely geometric and ignores market structure.

**Example from Jan 2022:**
| Origin | Counter-trend Range | Current Result |
|--------|---------------------|----------------|
| 4699.50 | 24.25 pts | KEPT (oldest) |
| **4671.75** | **65.75 pts** | PRUNED |
| 4636.00 | 10.75 pts | KEPT (far enough) |

The 4671.75 level had the strongest bull rally into it (65.75 pts) — it's the most significant resistance. But it was pruned because it wasn't the oldest.

## Proposed Solution

Replace "oldest wins" with "highest counter-trend range wins":

1. **Build proximity clusters** — group legs by origin proximity
2. **Score each leg** by counter-trend range (how far price traveled to reach this origin)
3. **Keep the highest-scoring leg** in each cluster
4. Prune the rest

## Data Available

Counter-trend data is already captured via segment impulse (#307):

```python
# On the PARENT leg:
parent.segment_deepest_price  # Deepest point before counter-move started
parent.segment_deepest_index  # Bar index of deepest point

# Counter-trend range for a leg:
counter_trend_range = abs(leg.origin_price - parent.segment_deepest_price)
```

For a **bear leg** with origin at HIGH:
- Parent is another bear leg (the bigger move this is part of)
- `segment_deepest_price` is the LOW before the rally
- Counter-trend range = how far bulls rallied to create this high

---

## Implementation Plan

### Phase 1: Add Counter-Trend Range to Leg

**File:** `src/swing_analysis/dag/leg.py`

Add a computed property to expose counter-trend range:

```python
@property
def counter_trend_range(self) -> Optional[Decimal]:
    """
    Range of the counter-move that created this leg's origin.

    For a bear leg: how far did bulls rally to create this high?
    For a bull leg: how far did bears drop to create this low?

    This is computed from parent's segment data. Returns None if:
    - No parent leg
    - Parent's segment_deepest_price not set

    Higher values = more significant structural level.
    """
    # This will be set during pruning when we have access to parent
    return self._counter_trend_range if hasattr(self, '_counter_trend_range') else None
```

**Decision:** Should we store this on the leg permanently, or compute it on-demand during pruning?

Recommendation: **Compute on-demand** during pruning, since we need to look up the parent anyway. Don't add a new field.

---

### Phase 2: Modify Proximity Pruning Algorithm

**File:** `src/swing_analysis/dag/leg_pruner.py`

**Function:** `apply_origin_proximity_prune()`

#### Current Algorithm (O(N log N)):
```
1. Group legs by pivot (pivot_price, pivot_index)
2. For each pivot group, sort by origin_index (oldest first)
3. For each leg:
   a. Check if any older survivor is within proximity
   b. If yes, prune this leg (newer)
   c. If no, add to survivors
```

#### New Algorithm:

```
1. Group legs by pivot (pivot_price, pivot_index)  # unchanged

2. For each pivot group:
   a. Build origin-proximity clusters
   b. Score each leg by counter-trend range
   c. Keep highest-scoring leg per cluster
   d. Prune the rest
```

#### Detailed Implementation:

```python
def apply_origin_proximity_prune(
    self,
    state: DetectorState,
    direction: str,
    bar: Bar,
    timestamp: datetime,
) -> List[LegPrunedEvent]:
    """
    Apply origin-proximity pruning using counter-trend scoring (#XXX).

    Instead of keeping oldest leg, keep the leg with highest counter-trend
    range (the level where the opposing side fought hardest to reach).
    """
    events: List[LegPrunedEvent] = []
    range_threshold = Decimal(str(self.config.origin_range_prune_threshold))
    time_threshold = Decimal(str(self.config.origin_time_prune_threshold))

    if range_threshold == 0 or time_threshold == 0:
        return events

    # Get active legs
    legs = [
        leg for leg in state.active_legs
        if leg.direction == direction and leg.status == 'active'
    ]

    if len(legs) <= 1:
        return events

    current_bar = bar.index
    pruned_leg_ids: Set[str] = set()

    # Step 1: Group by pivot
    pivot_groups: Dict[Tuple[Decimal, int], List[Leg]] = defaultdict(list)
    for leg in legs:
        key = (leg.pivot_price, leg.pivot_index)
        pivot_groups[key].append(leg)

    # Step 2: Process each pivot group
    for pivot_key, group_legs in pivot_groups.items():
        if len(group_legs) <= 1:
            continue

        # Step 2a: Build proximity clusters
        clusters = self._build_proximity_clusters(
            group_legs, range_threshold, time_threshold, current_bar
        )

        # Step 2b: For each cluster, keep highest counter-trend scorer
        for cluster in clusters:
            if len(cluster) <= 1:
                continue

            # Score each leg
            scored = self._score_legs_by_counter_trend(cluster, state)

            # Sort by score descending (highest first)
            scored.sort(key=lambda x: x[1], reverse=True)

            # Keep the best, prune the rest
            best_leg, best_score = scored[0]

            for leg, score in scored[1:]:
                leg.status = 'pruned'
                pruned_leg_ids.add(leg.leg_id)
                events.append(LegPrunedEvent(
                    bar_index=bar.index,
                    timestamp=timestamp,
                    swing_id=leg.swing_id or "",
                    leg_id=leg.leg_id,
                    reason="origin_proximity_prune",
                    explanation=(
                        f"Cluster winner: {best_leg.leg_id} "
                        f"(counter_trend={best_score:.2f} vs {score:.2f})"
                    ),
                ))

    # Remove pruned legs from state
    state.active_legs = [l for l in state.active_legs if l.leg_id not in pruned_leg_ids]

    return events
```

---

### Phase 3: Helper Functions

#### `_build_proximity_clusters()`

```python
def _build_proximity_clusters(
    self,
    legs: List[Leg],
    range_threshold: Decimal,
    time_threshold: Decimal,
    current_bar: int,
) -> List[List[Leg]]:
    """
    Group legs into proximity clusters.

    Two legs are in the same cluster if:
    - time_ratio < time_threshold (formed around same time)
    - range_ratio < range_threshold (similar ranges)

    Uses union-find for efficient clustering.
    """
    n = len(legs)
    if n <= 1:
        return [legs] if legs else []

    # Sort by origin_index for consistent processing
    legs = sorted(legs, key=lambda l: l.origin_index)

    # Union-find structure
    parent = list(range(n))

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Check all pairs for proximity
    for i in range(n):
        for j in range(i + 1, n):
            leg_i, leg_j = legs[i], legs[j]

            # Time ratio
            bars_since_i = current_bar - leg_i.origin_index
            bars_since_j = current_bar - leg_j.origin_index
            if bars_since_i <= 0:
                continue
            time_ratio = Decimal(abs(bars_since_i - bars_since_j)) / Decimal(bars_since_i)

            # Range ratio
            max_range = max(leg_i.range, leg_j.range)
            if max_range == 0:
                continue
            range_ratio = abs(leg_i.range - leg_j.range) / max_range

            # If both conditions met, same cluster
            if time_ratio < time_threshold and range_ratio < range_threshold:
                union(i, j)

    # Build clusters
    clusters_dict: Dict[int, List[Leg]] = defaultdict(list)
    for i, leg in enumerate(legs):
        clusters_dict[find(i)].append(leg)

    return list(clusters_dict.values())
```

#### `_score_legs_by_counter_trend()`

```python
def _score_legs_by_counter_trend(
    self,
    cluster: List[Leg],
    state: DetectorState,
) -> List[Tuple[Leg, float]]:
    """
    Score each leg by counter-trend range.

    Counter-trend range = distance from parent's segment_deepest_price
    to this leg's origin. Higher = more significant level.

    Fallback scoring for legs without parent data:
    - Use the leg's own range (bigger legs are more significant)
    """
    scored = []

    # Build parent lookup
    leg_by_id = {l.leg_id: l for l in state.active_legs}

    for leg in cluster:
        score = 0.0

        if leg.parent_leg_id and leg.parent_leg_id in leg_by_id:
            parent = leg_by_id[leg.parent_leg_id]

            if parent.segment_deepest_price is not None:
                # Counter-trend range: how far price moved to reach this origin
                counter_range = abs(float(leg.origin_price) - float(parent.segment_deepest_price))
                score = counter_range
            else:
                # Parent exists but no segment data - use leg's own range
                score = float(leg.range)
        else:
            # No parent (root leg) - use leg's own range as fallback
            score = float(leg.range)

        scored.append((leg, score))

    return scored
```

---

### Phase 4: Edge Cases

1. **Root legs (no parent):**
   - Fallback to using the leg's own range
   - Rationale: bigger legs are generally more significant

2. **Parent exists but `segment_deepest_price` is None:**
   - This happens if no child leg has formed yet
   - Fallback to leg's own range

3. **All legs in cluster have same score:**
   - Tie-breaker: keep the oldest (original behavior)
   - Or keep the one with highest impulse

4. **Single-leg clusters:**
   - No pruning needed, skip

5. **Legs with active swings:**
   - Currently protected from pruning - keep this behavior

---

### Phase 5: Testing

#### Unit Tests

1. **Cluster building:**
   - Test that legs within proximity are grouped together
   - Test that legs far apart are in separate clusters

2. **Counter-trend scoring:**
   - Test with known parent segment data
   - Test fallback when parent missing
   - Test fallback when segment_deepest_price is None

3. **Pruning decision:**
   - Test that highest scorer survives
   - Test tie-breaker behavior

#### Integration Test

Using the Jan 2022 example:
```python
def test_counter_trend_keeps_significant_level():
    """
    4671.75 should survive (counter_trend=65.75)
    instead of 4699.50 (counter_trend=24.25).
    """
    # Set up legs at 4699.50, 4671.75, 4636.00
    # Run proximity pruning
    # Assert 4671.75 survives, 4699.50 is pruned
```

---

### Phase 6: Configuration

Add a config option to choose pruning strategy:

```python
@dataclass(frozen=True)
class SwingConfig:
    # ... existing fields ...

    # Proximity pruning strategy: 'oldest' or 'counter_trend'
    proximity_prune_strategy: str = 'counter_trend'
```

This allows:
- Backward compatibility with `'oldest'`
- New behavior with `'counter_trend'` (new default)

---

## Summary

| Step | File | Change |
|------|------|--------|
| 1 | `leg.py` | (Optional) Add `counter_trend_range` property |
| 2 | `leg_pruner.py` | Rewrite `apply_origin_proximity_prune()` |
| 3 | `leg_pruner.py` | Add `_build_proximity_clusters()` |
| 4 | `leg_pruner.py` | Add `_score_legs_by_counter_trend()` |
| 5 | `swing_config.py` | Add `proximity_prune_strategy` config |
| 6 | Tests | Add unit and integration tests |

## Complexity

- Current: O(N log N) via binary search
- New: O(N^2) for cluster building (can optimize later if needed)
- N is typically small (legs in same pivot group), so O(N^2) is acceptable

## Open Questions

1. **Should we also consider impulse?**
   - User said range matters more than impulse
   - But `counter_trend_range * impulse_back` could weight both

2. **What about legs where counter-trend is unknown?**
   - Current plan: fallback to own range
   - Alternative: exclude from clustering entirely?

3. **Should we record counter_trend_range on the leg for debugging?**
   - Useful for visualization and debugging
   - Adds storage overhead
