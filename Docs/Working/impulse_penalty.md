# Impulse Penalty on Engulfment

**Status:** Design Spec
**Date:** December 23, 2025
**Author:** Architect (with Product input)

---

## Part 1: Product Perspective

### The Problem

The current impulse calculation is **diluted by extension**. When a leg's pivot extends through counter-trend bars, the impulse (range/bars) decreases because bar count increases. This loses the signal that mattered: *how impulsive was the move when it first formed?*

Consider the 5917→5972→5959→5845 scenario:

```
Price path:
5917 → impulse to 5972 → chop → 5959 → hard drop to 5845

What we want to know:
- The drop from 5959 was MORE impulsive than from 5972
- 5959 was a more important level despite being geometrically "inside" the larger structure
```

The current system captures geometric structure correctly, but **loses the market-generated signal about conviction**. The speed and intensity of moves tells you which levels mattered to participants.

### The Insight

From profiling es-1m.csv (126K legs):

| Mechanism | % of Pruning |
|-----------|--------------|
| **Engulfed** | **67.67%** |
| Extension | 26.10% |
| Inner structure | 5.61% |
| Domination | 1.18% |

**Engulfment is the dominant lifecycle event.** Two-thirds of all legs end by being overwhelmed — price breaches both their origin and their pivot. This is where the impulse story should be told.

### What We Want

When a child leg is engulfed:
- **The counter-move won.** The market reversed through the child's entire structure.
- **The parent gave up progress.** Whatever the child represented is now negated.
- **Parent's impulsiveness should decrease** to reflect this.

The impulse score should answer: *"How much of this leg's move was sustained vs. given back?"*

### The Model: Two Impulse Scores

The key insight is that a parent leg's segment (before child takes over) has **two distinct moves**:

```
Parent origin (A) ────→ Deepest point (D) ←──── Child origin (C)
                   impulse_to_deepest      impulse_back
```

**Two scores needed:**

1. **`impulse_to_deepest`**: How impulsively did price move from parent origin (A) to the deepest level achieved (D)?

2. **`impulse_back`**: How impulsively did price move back from deepest (D) to child origin (C)?

**Net segment impulse = impulse_to_deepest - impulse_back**

- **Typically reduces:** Counter-move gives back some of the impulsive move
- **Can increase:** If the down-move was very fast but the up-move was a slow grind

**On child formation:**
- Calculate and store both impulse scores for the parent's segment
- Parent's effective impulse is the difference

**On new child at higher origin:**
- A new child forming at higher origin means deeper counter-move
- Check if parent's pivot has extended deeper than stored `segment_deepest`
  - If yes: recalculate BOTH `impulse_to_deepest` AND `impulse_back` (deepest changed)
  - If no: only update `impulse_back`
- Net impulse direction is indeterminate — depends on relative impulsiveness of new moves

**Example:** `1000 → 900 → 950 → 500 → 960`
- Phase 1: D=900, child at 950. impulse_to=1000→900, impulse_back=900→950
- Phase 2: D=500 (deeper!), new child at 960. BOTH recalculated: impulse_to=1000→500, impulse_back=500→960
- Net impulse could INCREASE if 1000→500 was sharper than 1000→900

**Key principle:** The market's own behavior determines the score — no magic thresholds required.

---

## Part 2: Architecture Perspective

### Current State

**Impulse calculation** (leg_detector.py:58-76):
```python
def _calculate_impulse(range_value, origin_index, pivot_index):
    bar_count = abs(pivot_index - origin_index)
    return float(range_value) / bar_count if bar_count > 0 else 0.0
```

**Problem:** Recalculated on every pivot extension. Counter-trend bars dilute the score.

**Parent-child relationship:**
- `parent_leg_id` assigned at leg creation based on time-price ordering
- `reparent_children()` called when legs are pruned
- Hierarchy maintained without gaps

**Engulfment detection** (leg_pruner.py:238-420):
- Triggered when `max_origin_breach is not None AND max_pivot_breach is not None`
- Child is deleted, children reparented to grandparent
- Currently: no impulse transfer or penalty

### Design: Two-Impulse Segment Tracking

Based on user feedback, the recommended approach is **segment-based impulse tracking** with two components:

#### Data Model

Add to Leg:
```python
# Segment impulse tracking (parent.origin → child.origin)
segment_deepest_price: Optional[Decimal] = None  # Deepest point reached before child
segment_deepest_index: Optional[int] = None      # Bar index of deepest point
impulse_to_deepest: Optional[float] = None       # Impulse: origin → deepest
impulse_back: Optional[float] = None             # Impulse: deepest → child.origin
```

#### Calculation

**On child formation** (when parent hands off to child):
```python
def calculate_segment_impulse(parent: Leg, child_origin_price: Decimal, child_origin_index: int):
    # The deepest point is the current pivot (before child takes over)
    deepest_price = parent.pivot_price
    deepest_index = parent.pivot_index

    # Impulse TO deepest (the primary move)
    range_to_deepest = abs(parent.origin_price - deepest_price)
    bars_to_deepest = abs(deepest_index - parent.origin_index)
    impulse_to_deepest = float(range_to_deepest) / bars_to_deepest if bars_to_deepest > 0 else 0.0

    # Impulse BACK to child origin (the counter-move)
    range_back = abs(deepest_price - child_origin_price)
    bars_back = abs(child_origin_index - deepest_index)
    impulse_back = float(range_back) / bars_back if bars_back > 0 else 0.0

    # Store on parent
    parent.segment_deepest_price = deepest_price
    parent.segment_deepest_index = deepest_index
    parent.impulse_to_deepest = impulse_to_deepest
    parent.impulse_back = impulse_back

@property
def net_segment_impulse(self) -> Optional[float]:
    """Net impulse = forward move - counter move."""
    if self.impulse_to_deepest is None or self.impulse_back is None:
        return None
    return self.impulse_to_deepest - self.impulse_back
```

#### Update on New Child at Higher Origin

When a new child forms at a higher origin (deeper counter-move):
```python
def update_segment_impulse_for_new_child(
    parent: Leg,
    new_child_origin_price: Decimal,
    new_child_origin_index: int
):
    """
    Update segment impulse when new child forms at higher origin.

    Two cases:
    1. Parent's pivot extended deeper than stored deepest → recalculate BOTH
    2. Parent's pivot same as stored deepest → only update impulse_back
    """
    if parent.segment_deepest_price is None:
        return  # No segment established yet

    current_pivot = parent.pivot_price
    current_pivot_index = parent.pivot_index

    # Check if pivot extended deeper
    pivot_extended_deeper = (
        (parent.direction == 'bear' and current_pivot < parent.segment_deepest_price) or
        (parent.direction == 'bull' and current_pivot > parent.segment_deepest_price)
    )

    if pivot_extended_deeper:
        # Deepest changed! Recalculate BOTH impulse components
        parent.segment_deepest_price = current_pivot
        parent.segment_deepest_index = current_pivot_index

        # Recalculate impulse_to_deepest
        range_to_deepest = abs(parent.origin_price - current_pivot)
        bars_to_deepest = abs(current_pivot_index - parent.origin_index)
        parent.impulse_to_deepest = float(range_to_deepest) / bars_to_deepest if bars_to_deepest > 0 else 0.0

    # Always recalculate impulse_back with new child origin
    range_back = abs(parent.segment_deepest_price - new_child_origin_price)
    bars_back = abs(new_child_origin_index - parent.segment_deepest_index)
    parent.impulse_back = float(range_back) / bars_back if bars_back > 0 else 0.0
```

#### Interpretation

| Scenario | impulse_to_deepest | impulse_back | net_segment_impulse | Meaning |
|----------|-------------------|--------------|---------------------|---------|
| Sharp move, weak counter | High | Low | **High positive** | Strong conviction, sustained |
| Sharp move, sharp counter | High | High | **Near zero** | Contested, no clear winner |
| Weak move, sharp counter | Low | High | **Negative** | Counter-move won |
| Grind both ways | Low | Low | **Near zero** | Low conviction overall |

### Recommendation

**Implement the two-impulse segment tracking directly.**

The earlier "Option A then B" approach was superseded by user feedback. The two-impulse model:
- Captures both the primary move AND the counter-move
- Updates dynamically when new children form
- Provides net impulse as a single comparable metric
- Is conceptually clean: difference of two impulses

**Implementation sequence:**

1. Add segment tracking fields to Leg dataclass
2. Calculate on child formation (in `_find_parent_for_leg` or leg creation)
3. Update when new child forms at higher origin
4. Expose `net_segment_impulse` in API for ranking/filtering

### Technical Considerations

**Where segment impulse is calculated:**

The calculation happens when a child leg is created and assigned a parent:

```python
# In _find_parent_for_leg or leg creation:
if parent_leg_id:
    parent = find_leg_by_id(state, parent_leg_id)
    if parent:
        calculate_segment_impulse(parent, new_leg.origin_price, new_leg.origin_index)
```

**Where segment impulse is updated:**

When a new child forms at a higher origin (deeper counter-move), the parent's `impulse_back` is updated:

```python
# In _find_parent_for_leg when parent already has segment data:
if parent.segment_deepest_price is not None:
    # Check if new child origin is "higher" (deeper counter-move)
    if is_deeper_counter_move(parent, new_leg.origin_price):
        update_segment_impulse_for_new_child(parent, new_leg.origin_price, new_leg.origin_index)
```

**What is "deepest point"?**

At the moment a child forms, the parent's current pivot IS the deepest point. The segment is:
- `parent.origin` → `parent.pivot` (deepest) → `child.origin`

**What about engulfment?**

Engulfment doesn't require a separate penalty mechanism with the two-impulse model. When a child is engulfed and a new child forms at higher origin:
- The parent's `impulse_back` gets updated to reflect the deeper counter-move
- The `net_segment_impulse` automatically decreases
- The market's behavior is captured without explicit penalties

### Edge Cases

1. **Root legs have no parent:** No segment impulse to calculate — root legs track their own impulse via existing mechanism.

2. **First child of parent:** This is when segment impulse is first calculated. Before any child, parent has no segment data.

3. **Multiple children in sequence:** Each child formation can update the segment if it represents a deeper counter-move.

4. **Child at same or shallower origin:** Don't update `impulse_back` — only deeper counter-moves warrant update.

5. **Parent pruned before child forms:** No segment to calculate — parent's segment data was already finalized or never existed.

### Calibration Requirement

**Critical note for algo consumption:**

Raw impulse scores require **calibration against historical context** before they can be meaningfully compared or used for weighting.

**The problem:** If the first sample starts in a high-volatility domain, all legs might seem "normal" until a lower-volatility domain returns. A leg with impulse=10 in a high-vol period is different from impulse=10 in a low-vol period.

**Implication:** The existing `impulsiveness` percentile ranking (against all formed legs) partially addresses this, but may not be sufficient if the volatility regime is persistent.

**Possible approaches:**
- Rolling window for percentile calculation
- Volatility-adjusted normalization
- Regime detection and separate percentile pools

**This doesn't change implementation** of the two-impulse tracking, but needs to be noted for downstream consumers. The algo cannot blindly compare raw impulse scores across different market regimes.

### Migration Path

**Phase 1: Add segment tracking fields**
- New fields on Leg: `segment_deepest_price`, `segment_deepest_index`, `impulse_to_deepest`, `impulse_back`
- Backward compatible (defaults to None)
- No behavior change yet

**Phase 2: Calculate on child formation**
- Hook into leg creation when parent is assigned
- Calculate segment impulse for parent

**Phase 3: Update on new child at higher origin**
- Detect when new child has deeper counter-move
- Update parent's `impulse_back`

**Phase 4: Expose in API**
- Add `net_segment_impulse` property
- Include in leg/swing API responses
- Enable filtering/ranking experiments

---

## Part 3: Appendix — Conversation Context

### User Observations on Inner Structure Pruning

> "On the one hand it does detect and remove a lot of swings that are really 'inner' in the sense that all action happens within a larger swing and we don't care once that swing is removed. But on the other hand, it actually misses significant action."

> "Consider 5917→ impulse to 5972 → chop for some time → 5959 → impulse drop to 5845. It is true that the 5959 high is inside the larger 5917→5972 and the 'real' move was 5917→5845 in that sense. But if you look at the speed of action 5959 was a more important level than 5972. It dropped much more and much harder."

### User on Current Impulse Calculation

> "Our impulse calculation is very lossy. It uses the entire length of the leg, but by the time you do a pivot extension, you have many counter trend bars. Same holds for spiky, so we actually don't have this signal right now."

### User on Design Philosophy

> "Ideally I want the market structure and market generated data telling me which swings are important, not hard coded magic numbers that I put in :)"

> "At the bottom, I might choose the inner drop as my 'meter' because that's the one to overcome, as we get closer to 0.9, I may switch over to the next biggest one and see if it's levels are becoming more important now. For an algo this is potentially easier. It can attach weights based on impulse / range etc., and for each leg calculate the probability of move in a certain direction, then aggregate all to get a score and act on it."

### User on Impulse Granularity

**Product asked:** "What granularity for 'most impulsive move'?"

**User response:** "That depends on where you're looking from — long past action with large ranges or very recent action with constrained range?"

**Product:** "What question should we answer?"

**User:** "Hmm, perhaps start with this question: What was the most impulsive move in this range?"

### User on Child Formation and Merge

> "When a child is formed — you know, you attach a parent to it. This is where you 'fix' the parent's impulse score. This is where it's handed off to a child. Now you know max incursion below child's origin, and you can calculate impulse score to it."

> "When a child gets pruned, you know because you reparent its children to its parent. At this time you 'merge' its impulse score back to parent. This should be simple linear algebra if we define it in somewhat similar way as we do now."

### User on Engulfment Semantics

**Architect asked:** "Does the engulfment 'penalty' model match your intuition?"

**User:** "Yea, that's my thinking right now."

### User on Stale Extension

**Architect asked:** "For stale extension, is it additive or replacement?"

**User:** "Stale extension means the origin breached, it's long time since impulse updates as no child can form one tick above origin. That pruning method is no-op."

### User on Two-Impulse Model (Final Refinement)

> "My sense is that you need two impulse scores. Impulse to deepest level the parent achieved before child's origin. Impulse back to child's origin. This needs to be updated if a new child at higher origin forms. The impulse score is a difference of the two."

> "It might increase if it made even deeper inroads very fast but was a grind up, but typically we expect it to reduce."

> "This gives you segment-wide impulse score."

### User on Calibration Requirement

> "Also this needs to be calibrated at appropriate level before it can be considered useful (this doesn't change implementation, but needs to be noted in docs). For example if first sample starts in high volatility domain, then all legs might seem 'normal' until lower volatility domain comes back."

> "This probably also addresses open questions 2 and 4. 3 is orthogonal. We could later add another pruning method empirically."

### Profiling Results (es-1m.csv)

```
BASE PRUNING RESULTS (proximity disabled)

| Mechanism             |   Count | % of Created |
|-----------------------|---------|--------------|
| Legs would-be-created | 128,090 |            — |
| Legs actually created | 126,574 |            — |
| Domination rejected   |   1,516 |        1.18% |
| Engulfed              |  85,652 |       67.67% |
| Inner structure       |   7,100 |        5.61% |
| Extension             |  33,030 |       26.10% |
| Staleness             |       0 |        0.00% |
| Total pruned          | 125,782 |       99.37% |
```

### Architecture Analysis of Pruning Types

| Prune Type | Action | Impulse Effect |
|------------|--------|----------------|
| **Engulfment** | Delete child, new child with deeper origin | Parent impulse **decreases** (gave up progress) |
| **Pivot breach** | Replace child (not prune) | N/A — extension, not merge |
| **Inner structure** | Delete child | No merge — redundant noise |
| **Stale extension** | Delete child | No-op — dead leg (origin breached) |
| **Origin-proximity** | Delete loser | No merge — duplicate detection |
| **Turn/Domination** | Prevent formation | No merge — prevented at creation |

**Key insight:** Only engulfment (67% of pruning) represents a real structural change that should affect parent's impulse. The others are deduplication or cleanup.

---

## Part 4: Open Questions

1. ~~**Penalty formula tuning:**~~ **RESOLVED** — The two-impulse model replaces explicit penalties. Net segment impulse automatically reflects market behavior.

2. ~~**Counter-trend magnitude:**~~ **RESOLVED** — The `impulse_back` field directly captures counter-trend intensity. Net segment impulse = impulse_to_deepest - impulse_back.

3. **Disabling inner structure pruning:** (ORTHOGONAL) User has decided to disable by default (#303). This preserves more levels but increases algo's feature space. Could later add a new pruning method empirically based on segment impulse data.

4. ~~**Algo consumption:**~~ **RESOLVED** — The `net_segment_impulse` provides a single comparable metric per leg segment. Algo can weight legs by this score, adjusted for proximity to fib levels. Calibration section addresses regime-awareness requirement.

---

## Summary

| Phase | Deliverable | Complexity |
|-------|-------------|------------|
| 1 | Segment tracking fields on Leg | Low |
| 2 | Calculate on child formation | Medium |
| 3 | Update on new child at higher origin | Medium |
| 4 | API exposure (`net_segment_impulse`) | Low |

**Recommendation:** Implement phases 1-4 as a single coherent feature. The two-impulse model is self-contained and provides the counter-trend magnitude signal directly.

**Related issues:**
- #303 — Default inner structure pruning to OFF (orthogonal, already filed)
- #304 — Proximity O(N²) performance (orthogonal)
- #305 — Pivot breach investigation (orthogonal)
