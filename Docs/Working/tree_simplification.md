# Tree Simplification: Refactoring DAG to Pivot-Tree Model

**Status:** Planning
**Revert Point:** Commit `4ad6622` (Issue #284)
**Created:** December 22, 2025

---

## Problem Statement

The current DAG implementation has accumulated special cases that interact in subtle ways, causing bugs:
- Legs that should be there but are missing
- Legs that don't quite seem right
- Each bug fix risks introducing new edge cases

Root cause: **We're working at the wrong level of abstraction.**

The current model treats legs as independent entities with special-case rules for their interactions:
- Pivot extension (mutating legs)
- Turn pruning
- Domination pruning
- Proximity pruning
- Pivot breach pruning
- Engulfed pruning
- Inner structure pruning
- 3x stale extension pruning

## Proposed Model: Pivot-Centric Tree

Instead of legs as independent entities, model **pivots as nodes** that connect in a tree:

```
Current (leg-centric):
  Bull Leg: origin=3900 → pivot=3950
  Bear Leg: origin=3950 → pivot=3920
  (Separate entities with special-case interaction rules)

Proposed (pivot-centric):
  [3900] ══bull══► [3950] ══bear══► [3920]
  (Pivots are nodes, legs are branches connecting them)
```

Key insight: **Legs that share a pivot are swing partners.** They should be explicitly linked.

### Core Rules

1. **Branching is greedy**: Create a branch when next bar breaks the inner pivot
2. **Flattening is greedy**: If branch reverses and continues original direction, flatten internals
3. **3x distance rule**: Flatten dead branches when opposite direction moved 3x away

### What This Eliminates

All special cases should reduce to:
- **Branching** (greedy, on break of inner pivot)
- **Flatten** (recursive, when no projection beyond parent extrema)

---

## Implementation Steps

**Workflow for each step:**
1. Write code
2. Message user to start manual testing in DAG view
3. Run tests in parallel (`python -m pytest tests/ -v`)
4. Update this doc with findings
5. Commit if tests pass and behavior matches

---

### Step 1: Remove Bar Type Classification (#285)

**Current:** Classify bars as Type 1 (inside), Type 2-Bull (HH+HL), Type 2-Bear (LH+LL), Type 3 (outside), then route to different logic paths.

**Proposed:** Compare bar.high/low directly to pivots and inner pivots. No classification needed.

Bar types exist for temporal ordering, but temporal ordering can be derived from "did bar break inner pivot?" instead.

```python
# Current
bar_type = self._classify_bar_type(bar, prev_bar)
if bar_type == BarType.TYPE_2_BULL:
    events.extend(self._process_type2_bull(...))
elif bar_type == BarType.TYPE_2_BEAR:
    events.extend(self._process_type2_bear(...))
# ... etc

# Proposed
# Just compare bar.high/low to tracked pivots
if bar.high > inner_pivot_bear:
    # Bear can branch from this pivot
if bar.low < inner_pivot_bull:
    # Bull can branch from this pivot
```

**Success criteria:** Tests pass, same legs created, simpler code.

### Step 2: Stop Extending Pivots (#286)

**Current:** When price makes new high, existing bull leg's pivot mutates from H1 to H2.

**Proposed:** Don't mutate. Create new branch. Let flatten consolidate later.

```
Current (mutation):
  L1 → H1 becomes L1 → H2 when H2 > H1

Proposed (branching + flatten):
  L1 → H1 → L2 → H2 (full tree)
  After flatten: L1 → H2 (if H1→L2 has no projection)
```

This separates concerns:
- Tree layer: just tracks structure (no mutation)
- Flatten: consolidates when structure is redundant

**Success criteria:** Tests pass, extrema match, tree retains detail until flattened.

### Step 3: Experiment with Flattening Rules (#287)

**Current:** 7+ pruning rules with different triggers.

**Proposed:** One recursive flatten rule that subsumes all:

```python
def should_flatten(branch, parent_extrema):
    """
    Flatten if:
    1. Branch is dead (origin breached)
    2. Branch extrema don't project beyond parent extrema
    3. OR opposite direction moved 3x away from branch range
    """
    if branch.is_dead:
        if branch.extrema within parent_extrema:
            return True
        if distance_to_current > 3 * branch.range:
            return True
    return False
```

**Success criteria:** Same final structure as current pruning, but one rule instead of seven.

---

## Approach

Work directly on main with incremental commits. Each step is independently testable and revertible.

If experiments fail badly, revert to commit `4ad6622` (Issue #284).

---

## Appendix: Key Conversation Excerpts

### On the core insight (pivot-centric model)

> "What we're missing is bear legs whose pivots are the same as bull legs are related to each other as swing partners. Multiple bull legs and bear legs can meet at a pivot, these should all be linked. Now if the pivot is respected in either direction, we're growing a tree. Once the tree breaks the range of the leg is when we extend the legs. The containment rule is subtree flattening and so on. We apply these rules recursively. We're working at the wrong level of abstraction and hence we're having to create a lot of special cases."

### On pivot extension as tree compression

> "1/ pivot extension: consider sequence L1 -> H1 -> L2 -> H2 such that L1 < L2 < H1 < H2. Now we're replacing the leg L1 -> H1 with L1 -> H2. This is simply saying the tree will now be compressed because H1 -> L2 is contained within the extremas. We're still retaining H1 -> L2 bear leg because it can be a good reference until 3x extension. We can possibly do some tree operation that retains this detail until H1 -> L2 is no longer useful and then flattens the tree."

### On engulfment as subtree flattening

> "2/ Engulfment: consider sequence: H3 -> L3 -> H4 -> L4 -> H5 such that L3 < L4 < H4 < H3 < H5. Now we're saying delete the leg from L4 -> H5 since we have L3 -> H5 available. Equivalent tree operation could be flatten any tree branch that has no projection beyond extremas."

### On alive vs dead branches

> "Only legs whose origin hasn't been breached can grow. Translated to tree speak, only pivots that are respected (0 breach below) can continue growing in the opposite direction. The minute a breach occurs it's a dead branch that will remain until it's flattened at some point. Once a branch stops growing it's a simple object with extremas (insides can be ignored unless we need it for something)."

### On moving formation to reference layer

> "Formation can be moved to reference layer. This makes turn tracking simple also, we don't care about the 3 types of candles. Only tree's pivots and current bars high and low."

### On bar type skepticism

> "I'm kind of skeptical if we need the bar types. They're good for mental model as a trader, but do they serve a good purpose in code? There are many ways to turn and we only track 2-2 reversal I think?"

### On the unified rule

> "If it's actually right, then there should be a simple rule that when enforced will do engulfment and flattening as a consequence of some recursive tree pruning logic."

### On inner pivot concept

> "Inner pivot is latest candle's low or high in this picture -- it's the distance to break before we start drawing a branch, but we're also pretty greedy in flattening if we are wrong."

---

## Next Steps

1. Start with Step 1: Remove bar type classification
2. Run tests after each change
3. If tests fail, understand why before proceeding
4. Document findings in this file
