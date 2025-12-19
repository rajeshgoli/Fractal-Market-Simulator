# Swing Detection Performance Problem

## Problem Statement

### What is a Swing?

A **swing** is a price movement pattern in financial data:
- **Bull swing**: Price rises from a LOW point (defended pivot) to a HIGH point (origin), then retraces
- **Bear swing**: Price falls from a HIGH point (origin) to a LOW point (defended pivot), then retraces

```
Bull Swing Example:
        HIGH (origin)
       /    \
      /      \  ← retracement
     /        \
   LOW --------+--- close must be above 38.2% of range
(defended pivot)
```

### Formation Rules

A valid swing must satisfy:

1. **Temporal order**: Origin bar comes before pivot bar
2. **Formation threshold**: Price has retraced at least 38.2% of the swing range
3. **Pre-formation protection**: Between origin and pivot bars, no price exceeded the origin or violated the pivot
4. **Separation**: New swing must be sufficiently separated from existing swings (not a duplicate)

### Current Algorithm

```python
for each bar:
    for each candidate_high in lookback_window:      # ~50 candidates
        for each candidate_low in lookback_window:   # ~50 candidates

            if high_bar_index >= low_bar_index: continue
            if not meets_formation_threshold(): continue

            # O(n) check: iterate ALL candidates to verify no violations
            if not check_pre_formation(): continue

            # O(n) check: iterate ALL existing swings
            if not check_separation(): continue

            form_swing()
```

### Performance Problem

| Component | Complexity | Count |
|-----------|------------|-------|
| Bars to process | O(n) | 10,000 |
| Candidate pairs per bar | O(k²) | 50 × 50 = 2,500 |
| Pre-formation check per pair | O(k) | ~50 iterations |
| Separation check per pair | O(s) | ~200 swings |

**Total**: O(n × k² × (k + s)) ≈ **O(n × k³)** where n=10,000, k=50

This results in billions of operations → **80 seconds** for 10k bars.

### Target

- Current: 80s for 10k bars
- Target: <5s for 10k bars (16x improvement)

---

## Proposed Solution: DAG-Based Approach

### Core Insight

Instead of generating all candidates and filtering by rules, build a structure where **rules are enforced by construction**. The DAG tracks only valid extremas by maintaining strict temporal ordering as bars arrive.

**Complexity reduction**: O(n × k³) → O(n × log(DAG nodes))

### Bar Relationship Types

Given two consecutive bars, classify their relationship:

| Type | Condition | Temporal Information |
|------|-----------|---------------------|
| Type 1 | Higher low, lower high (inside) | Both directions have known ordering |
| Type 2-Bull | Higher high, higher low | bar1.L occurred before bar2.H |
| Type 2-Bear | Lower high, lower low | bar1.H occurred before bar2.L |
| Type 3 | Higher high, lower low (outside) | Decision point, high volatility |

### Streaming Construction

The DAG is built incrementally as each bar arrives:

1. **First bar**: Initialize with O → C leg (known temporal ordering). H and L cannot be used yet.

2. **Type 2 bars**: Extend the leg in that direction. Use Close for retracement (H/L ordering within bar unknown).

3. **Type 1 bars**: Can use H/L directly for retracement (extremes from different bars → ordering known). If second bar, establishes TWO legs simultaneously.

4. **Type 3 bars**: Keep both branches until decisive resolution. Either the high or low will eventually be violated.

### Simultaneous Leg Tracking

Both bull and bear legs can be active simultaneously. This represents market indecision ("chop"):

```
Example after 5 bars:
Bull leg: 95 → 112 (pivot=95, origin=112)
Bear leg: 112 → 97 (retracement of bull, tracking separately)

Neither invalidated yet. DAG holds both until decisive resolution.
```

### Formation

A leg becomes a **formed swing** when retracement reaches 38.2%:

```python
if retracement_pct >= 0.382:
    leg.formed = True
    add_to_dag(leg)  # Immediate addition, no settling period
```

### Pruning Rules

**Rule 1: Decisive Invalidation (0.382 Rule)**

A swing is pruned when price moves 0.382 × range beyond the defended pivot:

```
Bull swing: pivot=100, origin=150, range=50
Invalidation at: 100 - (0.382 × 50) = 80.9
At invalidation: prune bull, track new bear leg 150 → 80.9
```

**Rule 2: Staleness (2x Rule)**

If a branch hasn't changed and price moved 2x its range, prune as stale. This handles Type 3 resolution where neither branch is decisively invalidated but one became irrelevant.

*Note: 2x is configurable. Strong opinion weakly held—will validate in practice.*

### Parent-Child Relationships

Parent-child is about **pivot derivation**, not range containment. A child can grow larger than its parent:

```
1. Bear leg: 130 → 100 (origin=130, pivot=100 defended)
2. Bull leg forms: 100 → 140 (pivot derived from bear's defended point)
3. Drops to 120, rallies to 150
4. Bull leg now: 100 → 150 (range exceeds bear's [100,130])
5. Still a child! Pivot 100 derived from parent structure.
6. If 100 violated: BOTH parent and child invalidated.
```

### Retracement Price Selection

Which price to use for retracement calculation depends on known temporal ordering:

| Bar Type | Use H/L? | Why |
|----------|----------|-----|
| Type 1 | Yes | Extremes from different bars → ordering known |
| Type 2 | No, use Close | New extreme from current bar → unknown H/L ordering within bar |
| Type 3 | Context-dependent | May have both scenarios |

---

## Architecture: Separation of Concerns

**DAG and Reference calculation are separate layers.**

| Layer | Responsibility | Rules |
|-------|----------------|-------|
| **DAG** | Track extremas efficiently | 0.382 invalidation, 2x staleness |
| **Reference** | Define "good reference" for trading | 0.15/0.1 separation thresholds |

The DAG answers: "What pivots exist?" (structural)
Reference answers: "Which swings are useful?" (semantic)

**Benefits:**
- DAG stays simple and O(n log k)
- Reference logic can evolve without touching DAG
- No business rules baked into the data structure
- Easy to experiment with different reference definitions

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

**Expected improvement:** From ~10B operations to ~130K operations.

---

## Why This Works

### Rules by Construction, Not Filtering

The current algorithm says: "Generate all candidates, form all pairs, then filter by rules."

The DAG approach says: "Build the structure such that only valid swings can exist."

### Temporal Ordering is Implicit

When you see a Type 2-Bull (higher high, higher low), you've established `bar1.L → bar2.H` ordering. You don't need to check if the origin came before the pivot—the bar sequence proves it.

### Pre-Formation Protection is Automatic

When bar 3 exceeds bar 2's high, you get `bar1.L → bar2.H → bar3.H`. You abandon bar2.H as the origin. You never form a swing with bar2.H as origin because bar3.H exceeded it. The rule isn't checked—it's enforced by construction.

### Pruning = Invalidation

When a retracement drops below the defended pivot (decisively), you prune. This is exactly the invalidation rule, but instead of tracking invalidated swings in a list, they simply don't exist in the DAG.

---

## Current State

- **Location**: `src/swing_analysis/hierarchical_detector.py`
- **Hot path**: `_try_form_direction_swings()` (lines ~700-800)
- **Bottleneck**: `_check_pre_formation()` called 1M+ times for 1k bars

---

## Next Steps

See `Docs/Working/DAG_spec.md` for the full specification.

1. Validate spec against current test suite expectations
2. Implement prototype and compare outputs with current HierarchicalDetector
3. Benchmark performance on 10K bar dataset
4. Refine pruning rules based on empirical results

---

## Appendix A: Design Clarifications

This appendix summarizes key clarifications that shaped the design. See Appendix B for full transcript.

### A1: Simultaneous Bull and Bear Tracking

**Question**: Can both bull and bear legs be active simultaneously?

**Resolution**: Yes. Both legs in the DAG represent market indecision ("chop"). At some point one will be invalidated decisively; prune it and continue tracking the survivor.

### A2: Type 3 Bar Handling

**Question**: When a formed swing is violated by a Type 3 bar, do we immediately prune?

**Resolution**: No. Type 3 bars represent high volatility at decision points. Keep both branches until decisive resolution. Either the bar's H or L will be violated eventually:
- If H violated (new HH): New bull branch from L active, old branch stale → prune via 2x rule
- If L decisively violated: Old branch pruned, any branch from L also pruned

### A3: First Bar Initialization

**Question**: How do we initialize with the first bar?

**Resolution**: Use O → C (known temporal ordering):
- If C > O: bull leg (O is pivot, C is origin)
- If C < O: bear leg (O is pivot, C is origin)

H and L cannot be used yet—wait for subsequent bars to establish their temporal ordering.

### A4: Type 1 (Inside Bar) Information

**Question**: Do inside bars provide information?

**Resolution**: Yes, they are NOT "no information":
1. Can use H/L directly for retracement (extremes from different bars → ordering known)
2. If second bar, establish TWO legs with known temporal ordering: bar1.H → bar2.L (bear) and bar1.L → bar2.H (bull)

### A5: Parent-Child Definition

**Question**: Is parent-child based on range containment?

**Resolution**: No. Parent-child is about **pivot derivation**. A child's pivot originated from within the parent's structure. A child can grow larger than its parent—if the shared pivot breaks, both are invalidated.

### A6: Separation of DAG and Reference

**Question**: Should the DAG use 0.15/0.1 separation thresholds?

**Resolution**: No. Keep DAG and Reference as separate concerns:
- DAG: Track extremas efficiently (0.382 invalidation only)
- Reference: Define "good reference" (0.15/0.1 thresholds)

This allows reference logic to evolve without touching the DAG structure.

---

## Appendix B: Full Q&A Transcript (Dec 19)

This appendix preserves the verbatim conversation that led to the design decisions above.

---

### Q1: Simultaneous Bull and Bear Tracking

**Claude:** Consider this sequence:

```
Bar 1: H=105, L=95, C=102
Bar 2: H=110, L=100, C=108
Bar 3: H=112, L=105, C=106
Bar 4: H=107, L=98, C=99
Bar 5: H=104, L=97, C=103
```

At the end of Bar 5, I see two potentially valid swings:

```
Bull swing: 95 → 112
  - Pivot=95, Origin=112
  - Retracement to 97 (close=103)
  - (112-103)/(112-95) = 53% > 38.2% ✓ FORMED
  - Pivot 95 not violated (97 > 95)

Bear swing: 112 → 97
  - Pivot=112, Origin=97
  - Retracement to 103 (close=103)
  - (103-97)/(112-97) = 40% > 38.2% ✓ FORMED
  - Pivot 112 not violated (104 < 112)
```

**Question**: Are both of these in the DAG simultaneously? Or does the bear swing 112→97 exist as a "child" within the bull swing 95→112, meaning we only track one "active branch"?

**Rajesh:** Bull leg is correct. Bear leg is a retracement for that bull leg. Neither 95 nor 112 have been invalidated. The DAG is exactly tracking these two legs. One leg starts at 95 and all the way to 112. Another leg tracks retracement from 112 to 97. This is actually not atypical at all. It looks like what a trader would call chop (decision zone). However at some point one of these will be invalidated decisively and you can prune that leg and continue tracking the bigger surviving leg.

---

### Q2: Formation vs Commitment to DAG (First Attempt - Malformed)

**Claude:** [Original example with Bar 1: H=105, L=95, C=97]

**Rajesh:** Q2 is malformed at Bar 1. I don't know temporal order between H and L so I can't really say 105 -> 95 was a retracement. High could have occurred before Low or the other way around. I only know Open happened before Close and Open is not provided, so Bar 1 I don't know anything about retracement. Can you provide a better example?

---

### Q2 Reformulated: Establishing Temporal Order

**Claude:** Let me try again with bar relationships to establish temporal order:

```
Bar 1: H=105, L=100, C=102
Bar 2: H=103, L=95, C=97   (Type 2-Bear: LH, LL)
```

After Bar 2, I know:
- Bar 2 made a lower high (103 < 105) and lower low (95 < 100)
- This establishes: Bar 1's high (105) occurred BEFORE Bar 2's low (95)
- So we have a bear leg: 105 → 95, with close at 97
- Retracement = (97 - 95) / (105 - 95) = 20%

```
Bar 3: H=98, L=88, C=90   (Type 2-Bear continues)
```

- Bear leg extends: 105 → 88
- Retracement = (90 - 88) / (105 - 88) = 12%

```
Bar 4: H=96, L=85, C=93   (Type 2-Bear continues)
```

- Bear leg extends: 105 → 85
- Retracement = (93 - 85) / (105 - 85) = 40% > 38.2% ✓ FORMED

```
Bar 5: H=110, L=84, C=108  (Type 3: HH, LL)
```

- New high 110 > 105 (bear origin violated)
- New low 84 < 85 (bear pivot extended momentarily, but then violated by the high)

**Question**: The bear swing 105→85 formed at Bar 4. At Bar 5, it's violated (110 > 105). Does the swing get added to DAG at Bar 4 and then pruned at Bar 5? Or is there a "settling" period before commitment?

**Rajesh:** That's an excellent question and this is not atypical at pivots (you get higher volatility as decision is being made which results in Type 3). Just keeping the old branch until resolution is not expensive in my opinion. Consider what can happen for a reason why. Either the final 3 bars H or L needs to be violated at some point. If H gets violated then you have a new active branch that starts at 3L and the older one you had from before can be pruned once that branch no longer grows (this maybe where you need 2x prune rule, if price reaches 2x and this branch hasn't changed, get rid of it). If L gets decisively violated, then you have an easier solution, the old branch must go and potentially any new branch that was created from 3L also.

---

### Q3: True Invalidation Threshold

**Claude:** Consider a formed bull swing:

```
Bull swing: Pivot=100, Origin=150, Range=50
Formed and in DAG.
```

Now price drops:

```
Scenario A: Price drops to 99 (1 point below pivot)
Scenario B: Price drops to 95 (5 points below pivot, 10% of range)
Scenario C: Price drops to 81 (19 points below pivot, 38% of range)
Scenario D: Price drops to 75 (25 points below pivot, 50% of range)
```

**Question**: At which scenario (A, B, C, or D) do we prune this swing from the DAG as "truly invalidated"?

**Rajesh:** As worded it sounds like we started dropping from 150 and now dropped to 100, so there isn't an active swing? Or did we start at 100 go to 150 and then drop back to 100? If it's the latter question, then you have a 50 point leg. The true invalidation is when you drop 0.382 * 50 below 100. At this point you can simply track the bigger leg 150 to 100 - 0.382 * 50. The old bull leg was decisively invalidated by bears.

---

### Q4: Parent-Child Definition

**Claude:** [In initial DAG spec] A swing becomes a child of another when its entire range is contained within the parent's range.

**Rajesh:** This isn't right. Consider: you have a bear leg from 130 to 100 (30 pt range). 100 is defended and never trades below. It then makes a bull leg to 140. Then price drops to 120 (in the first bear leg's range but without violating the low), then it jumps to 150. Now price is no longer contained in either of the first legs. Isn't it still a child though?

---

### Q5: First Bar Handling

**Claude:** [In initial DAG spec] "No temporal ordering known. Initialize pending pivots."

**Rajesh:** This isn't right either. You do have open and close so you have a leg bull or bear. It's just that you can't use the first candle's high or low yet.

---

### Q6: Type 1 (Inside Bar) Handling

**Claude:** [In initial DAG spec] "Multiple inside bars in sequence. No new ordering established. Continue tracking existing legs, update retracement based on closes."

**Rajesh:** This isn't right either, a Type 1 can still inform retracement if it's better than available information. It can also establish 2 legs if this is a second candle from the start.

**Claude:** [Follow-up] So we can use H/L for retracement in Type 1?

**Rajesh:** Actually you can use the high or low for retracement as you know the temporal order, you only need to use the close if it's a 2 type bar because then you have a higher high and therefore can't quite say if the low was before the high or after. In the case of 1, the high is from your existing bar, which occurred before the L of the 1 bar.

---

### Q7: Separation Tolerance in DAG

**Claude:** [In DAG spec open questions] "Separation tolerance: Current algorithm uses 0.15 (normal) and 0.1 (large). Should DAG use same thresholds for sibling detection?"

**Rajesh:** My current bias and I'm open to your thoughts here is that we should keep the reference calculation (whether a swing is a valid bull reference) separate from the DAG. For DAG you invalidate at 0.382 below. This is simply so we can track the extremas we care about without getting O(k³) complexity. Once we have all the extremas we need we can change around how we define what constitutes a good reference easily. Separate these two concerns.
