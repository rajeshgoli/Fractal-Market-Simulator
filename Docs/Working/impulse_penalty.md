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

### The Model

**On child formation:**
- Parent's impulse gets "fixed" at that moment
- We know the segment being handed off: parent.origin → child.origin

**On child engulfment:**
- Child's entire range was overwhelmed
- A new child forms with deeper origin (further back)
- Parent absorbs a **penalty** proportional to how much progress was given back

**Key principle:** The market's own behavior (engulfment depth) determines the penalty — no magic thresholds required.

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

### Design Options

#### Option A: Impulse-at-Formation (Minimal)

Add a separate `impulse_at_formation` field:
- Captured once at leg creation, never recalculated
- Provides stable signal for ranking/filtering
- **Does not address** the engulfment penalty question

**Pros:** Simple, low-risk, immediately useful
**Cons:** Doesn't capture the parent-child impulse transfer model

#### Option B: Parent Impulse Penalty on Engulfment

When child is engulfed:
1. Calculate how much progress was given back (engulfment depth)
2. Apply penalty to parent's impulsiveness score
3. Penalty is market-derived, not threshold-based

**Formula approach:**
```
engulfment_depth = |child.origin - new_child.origin|
child_contribution = child.range  # What the child represented
penalty_ratio = engulfment_depth / child_contribution
parent.impulsiveness *= (1 - penalty_ratio)  # Reduce by what was given back
```

**Pros:** Captures the semantic meaning of engulfment
**Cons:** More complex, needs careful handling of edge cases

#### Option C: Segment-Based Impulse Tracking

Track impulse per segment:
- When child forms: record `segment_impulse` for parent.origin → child.origin
- When child engulfed: record the reversal segment's impulse
- Parent's effective impulse = weighted combination

**Pros:** Most accurate model of what happened
**Cons:** Significant complexity, storage overhead, merge logic

### Recommendation

**Implement Option A first, then Option B.**

**Rationale:**

1. **Option A is immediately useful** — `impulse_at_formation` gives you a stable signal today without waiting for the full penalty model.

2. **Option B depends on A** — you need stable formation impulse to know what's being penalized.

3. **Option C is over-engineering** — the 67% engulfment dominance suggests the penalty model captures most of the story. Per-segment tracking adds complexity without proportional value.

**Implementation sequence:**

1. Add `impulse_at_formation` field to Leg (set at creation, never modified)
2. Expose in API for ranking/filtering experiments
3. Implement engulfment penalty using formation impulse as baseline
4. Iterate on penalty formula based on empirical results

### Technical Considerations

**Where penalty is applied:**

The engulfment detection happens in `prune_breach_legs()` (leg_pruner.py:238-420). The penalty should be applied *before* reparenting:

```python
# In prune_breach_legs, when engulfment detected:
if leg.max_origin_breach is not None and leg.max_pivot_breach is not None:
    # Apply penalty to parent before pruning
    if leg.parent_leg_id:
        parent = find_leg_by_id(state, leg.parent_leg_id)
        if parent:
            apply_engulfment_penalty(parent, leg, new_child_origin)

    # Then prune as normal
    legs_to_prune.append(leg)
```

**What is "new_child_origin"?**

The engulfment happens because price reversed through the child's origin. The new child that forms will have an origin further back. The difference between `child.origin` and `new_child.origin` is the engulfment depth.

**Challenge:** At the moment of engulfment, the new child may not exist yet. Options:
1. Use the current bar's extreme as proxy for new_child_origin
2. Defer penalty calculation until new child forms
3. Use `max_origin_breach` directly (it tracks how far price went past origin)

**Recommendation:** Use `max_origin_breach` — it's already tracked and represents exactly what we need (how far the reversal went).

**Penalty formula (proposed):**
```python
def apply_engulfment_penalty(parent: Leg, engulfed_child: Leg) -> None:
    """
    Reduce parent's impulsiveness when child is engulfed.

    The penalty is proportional to how much of the child's range
    was "given back" (origin breach depth).
    """
    if parent.impulsiveness is None:
        return

    child_range = float(engulfed_child.range)
    if child_range == 0:
        return

    # How much was given back beyond child's origin?
    breach_depth = float(engulfed_child.max_origin_breach or 0)

    # Penalty ratio: breach_depth relative to child's range
    # Clamped to [0, 1] to prevent over-penalization
    penalty_ratio = min(breach_depth / child_range, 1.0)

    # Apply penalty
    parent.impulsiveness *= (1 - penalty_ratio * 0.5)  # 50% max penalty per child
```

**Why 50% max per child?**

A parent may have multiple children engulfed sequentially. Each should reduce impulsiveness, but no single child should devastate the score. The 0.5 factor is conservative — can be tuned empirically.

**Alternatively:** Make penalty multiplicative without cap, but apply diminishing returns:
```python
parent.impulsiveness *= (1 - penalty_ratio) ** 0.5  # Square root for diminishing returns
```

### Edge Cases

1. **Root legs have no parent:** Engulfment penalty only applies when `parent_leg_id` exists.

2. **Parent already pruned:** If parent was pruned before child engulfment, no penalty to apply. Penalty targets grandparent via reparenting.

3. **Multiple children engulfed in same bar:** Apply penalties sequentially. Order may matter — consider sorting by engulfment depth.

4. **Child never formed (stayed pre-formation):** Still apply penalty — the structure existed even if it didn't reach swing status.

5. **Impulsiveness is None:** If parent's impulsiveness hasn't been calculated yet (too few bars), skip penalty.

### Migration Path

**Phase 1: Add impulse_at_formation**
- New field on Leg, set at creation
- Backward compatible (existing legs get current impulse as default)
- No behavior change yet

**Phase 2: Expose in API**
- Add to leg/swing API responses
- Enable filtering/ranking experiments in UI

**Phase 3: Implement penalty**
- Add `apply_engulfment_penalty()` to LegPruner
- Call in `prune_breach_legs()` before pruning
- Monitor impact on impulsiveness distribution

**Phase 4: Tune and validate**
- Empirically adjust penalty formula
- Compare to human judgment on significant levels
- Document findings

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

1. **Penalty formula tuning:** The 0.5 max penalty per child is arbitrary. Should be tuned empirically against cases where human judgment identifies "important" inner levels.

2. **Counter-trend magnitude:** The user also identified lack of "counter-trend depth" signal. This spec focuses on engulfment penalty, but counter-trend magnitude may be a separate metric worth capturing.

3. **Disabling inner structure pruning:** User has decided to disable by default (#303). This preserves more levels but increases algo's feature space. Need to validate that impulse-based ranking can separate signal from noise.

4. **Algo consumption:** The ultimate consumer is an algo, not a trader. The impulse scores become feature weights. How these get combined into directional probability is outside this spec's scope.

---

## Summary

| Phase | Deliverable | Complexity |
|-------|-------------|------------|
| 1 | `impulse_at_formation` field | Low |
| 2 | API exposure for experiments | Low |
| 3 | Engulfment penalty implementation | Medium |
| 4 | Empirical tuning | Ongoing |

**Recommendation:** Proceed with Phase 1-2 as immediate work. Phase 3 can follow once inner structure is disabled and we observe the larger feature space.
