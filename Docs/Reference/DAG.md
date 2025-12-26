# Market Structure Detection: How the DAG Layer Works

**A Trader's Guide to the Algorithm**

*Last Updated: December 24, 2025*

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Core Idea: What Are We Detecting?](#the-core-idea)
3. [Fundamental Concepts](#fundamental-concepts)
4. [How Swings Are Born: The Leg Lifecycle](#leg-lifecycle)
5. [Bar Classification: Establishing Temporal Order](#bar-classification)
6. [Formation: When a Leg Becomes a Swing](#formation)
7. [Invalidation: When Structure Breaks](#invalidation)
8. [Pruning: Keeping the Structure Clean](#pruning)
9. [Hierarchy: Parent-Child Relationships](#hierarchy)
10. [Impulse Metrics: Quantifying Move Quality](#impulse-metrics)
11. [Configuration Parameters](#configuration)
12. [Complete Example: Walking Through Real Data](#complete-example)
13. [QA Section: Expert Trader Questions](#qa-section)
14. [Simplification Opportunities](#simplification)

---

## Terminology Note

**Important:** The code uses terminology that may differ from traditional swing trading:

| Code Term | Code Meaning | Traditional Meaning |
|-----------|--------------|---------------------|
| **Bull leg** | Upward move (LOW → HIGH) | Often refers to bearish setup |
| **Bear leg** | Downward move (HIGH → LOW) | Often refers to bullish setup |
| **Origin** | Where move started (defended level) | — |
| **Pivot** | Current extreme (extends as move continues) | — |
| **Formation** | Move has progressed 28.7% from origin | — |

This document describes **what the code does**, using the code's terminology.

---

## Executive Summary <a name="executive-summary"></a>

This document reverse-engineers the DAG (Directed Acyclic Graph) layer that detects market structure in ES futures. The algorithm identifies **swings** — defended price extremes that form the backbone of market structure.

**What the algorithm does:**
- Tracks directional price movements ("legs") from origin to pivot
- Confirms structure when price retraces 28.7% toward origin
- Invalidates structure when origin is breached by 38.2% of range
- Builds hierarchical relationships between swings
- Prunes redundant structure to maintain clarity

**Key insight for traders:** The algorithm thinks in terms of *defended levels*. A swing high is a high that price pulled back from. A swing low is a low that price bounced from. The algorithm only confirms structure after price demonstrates the level matters.

---

## The Core Idea: What Are We Detecting? <a name="the-core-idea"></a>

Market structure = defended extremes connected by directional moves.

```
                     Swing High (Defended)
                         ▲
                        /|\
                       / | \
                      /  |  \  ← Retracement confirms
                     /   |   \    the high matters
                    /    |    \
                   /     |     \
    Swing Low ────       │
   (Defended)            │
                         │
                    Origin of move
```

**A swing is not just a high or low.** It's a high or low that:
1. Price moved away from (establishing it as an extreme)
2. Price partially returned toward (confirming it's defended)

Without the retracement, we don't know if the extreme matters. The algorithm waits for confirmation.

---

## Fundamental Concepts <a name="fundamental-concepts"></a>

### Legs vs. Swings

| Concept | Definition | Trader Analogy |
|---------|------------|----------------|
| **Leg** | Directional move from origin to pivot, before confirmation | "Price is pushing up from here" |
| **Swing** | Confirmed leg that reached 28.7% retracement | "That was a real swing low" |

A leg is a *candidate* swing. It becomes a swing when the market confirms the extreme matters by retracing toward it.

### Origin and Pivot

```
BULL LEG:
    Pivot (HIGH) ────────────────────►  Extends on new highs
         ▲
         │
         │  Range = |Pivot - Origin|
         │
    Origin (LOW) ────────────────────►  FIXED (never moves)

BEAR LEG:
    Origin (HIGH) ───────────────────►  FIXED (never moves)
         │
         │  Range = |Origin - Pivot|
         │
         ▼
    Pivot (LOW) ─────────────────────►  Extends on new lows
```

**Key insight:** Origins are fixed; pivots extend. The origin is where the move started — it's the level being defended. The pivot is where the move reached — it extends as price pushes further.

### The 28.7% Formation Threshold

Why 28.7%? It's between the 23.6% and 38.2% Fibonacci levels — enough progress to confirm the move is real, not just noise.

**Important:** Formation is about the move's *progress*, not a pullback. The leg forms when price has moved at least 28.7% of the way from origin toward pivot.

```
Example: Bull leg from 3900 (origin) to 3950 (pivot)
Range = 50 points

Formation happens when: (current - origin) / range >= 0.287
                       (current - 3900) / 50 >= 0.287
                       current >= 3900 + 14.35 = 3914.35

When current price >= 3914.35, the swing is FORMED.
This can happen immediately on the same bar the leg is created,
if price has already moved far enough.
```

### Origin Breach Detection (#345)

When price touches or crosses the origin, the leg's structure is compromised. This is tracked via `max_origin_breach`:

```
Example: Bull leg from 3900 (origin) to 3950 (pivot)

If price drops to 3899 (below origin of 3900):
  - max_origin_breach = 1 point
  - Leg is now "breached" (origin_breached = True)
  - Pivot stops extending
  - Swing is invalidated

The 3950 high remains as a historical reference but is no longer
actively defended.
```

**Key behavior after origin breach:**
- Pivot freezes (no longer extends to new extremes)
- Leg remains in active_legs for context
- Can be pruned by engulfed or stale extension mechanisms
- Cannot form new swings or be a parent for child legs

---

## How Swings Are Born: The Leg Lifecycle <a name="leg-lifecycle"></a>

### Phase 1: Pending Origin

Before a leg can exist, we need to know where the move started. A **pending origin** is a candidate starting point awaiting temporal confirmation.

```
ES 5-minute: January 3, 2023

Bar 0: O=3976.50 H=3978.50 L=3976.25 C=3977.50
       Creates pending origins:
       - Bull origin at 3976.25 (LOW)
       - Bear origin at 3978.50 (HIGH)

These are CANDIDATES. We don't know temporal order yet.
```

### Phase 2: Temporal Confirmation

The next bar establishes which extreme came first. This is critical — we need to know the origin existed *before* the pivot.

```
Bar 0: H=3978.50 L=3976.25
Bar 1: H=3979.50 L=3977.75  (Higher High, Higher Low = Type 2-Bull)

Type 2-Bull bar tells us:
- Bar 0's LOW (3976.25) came BEFORE Bar 1's HIGH (3979.50)
- Temporal order established: LOW → HIGH
- Bull leg created: Origin=3976.25, Pivot=3979.50
```

### Phase 3: Active Tracking

Once created, the leg is actively tracked:
- **Pivot extends** on new highs (for bull) or new lows (for bear)
- **Pending origin updates** when pivot extends (#338): Bull pivot extension → pending bear origin updated to that price; Bear pivot extension → pending bull origin updated. This ensures counter-trend legs form at leg pivots where the branch ratio check (#337) can find matching counter-trend ranges.
- **Retracement calculated** as price moves toward/away from origin
- **Breach tracked** if price violates origin

```
Bar 2: H=3979.50 L=3978.25  (pivot unchanged, H not exceeded)
Bar 3: H=3980.00 L=3978.25  (pivot EXTENDS to 3980.00)
Bar 4: H=3981.00 L=3979.00  (pivot EXTENDS to 3981.00)
...

Bull leg now: Origin=3976.25, Pivot=3981.00, Range=4.75 points
```

### Phase 4: Formation

When progress through the move reaches 28.7%, the leg becomes a swing.

```
Bull leg: Origin=3976.25, Pivot=3983.25 (extended), Range=7.00 points
Formation threshold = 0.287 (28.7% progress from origin to pivot)

Progress = (current - origin) / range

Bar N: Close=3978.00 → Progress = (3978 - 3976.25) / 7.00 = 25% (not yet)
Bar N+1: Close=3979.00 → Progress = (3979 - 3976.25) / 7.00 = 39% ✓ FORMED!

The 3983.25 high is now a confirmed SWING HIGH.

Note: Formation can happen immediately on leg creation if the
close is already 28.7%+ of the way from origin to pivot.
```

### Phase 5: Invalidation

If price breaches origin by 38.2% of range, the structure breaks.

```
Bull leg: Origin=3976.25, Pivot=3983.25, Range=7.00 points
Invalidation threshold = 3976.25 - (0.382 × 7.00) = 3973.58

Bar M: Low=3974.00 → Still valid (above 3973.58)
Bar M+1: Low=3973.50 → INVALIDATED! (below 3973.58)

The swing is invalidated but NOT deleted.
It remains as a historical reference until cleaned up.
```

### Phase 6: Removal (Pruning)

Invalidated or redundant legs are eventually removed through various pruning mechanisms (detailed in [Pruning](#pruning)).

---

## Bar Classification: Establishing Temporal Order <a name="bar-classification"></a>

The algorithm classifies each bar by its relationship to the previous bar. This determines which price came first within the two-bar window.

### The Four Bar Types

```
TYPE 1: INSIDE BAR (LH + HL)
────────────────────────────
Previous: H=100, L=95
Current:  H=99,  L=96  (Lower High AND Higher Low)

     100 ────┐
             │ Prev
      95 ────┘
        99 ──┐
             │ Curr (contained)
        96 ──┘

Meaning: Current bar is contained within previous.
         No directional information. Both extremes tracked.


TYPE 2-BULL: UPTREND (HH + HL)
──────────────────────────────
Previous: H=100, L=95
Current:  H=102, L=97  (Higher High AND Higher Low)

                  102 ──┐
     100 ────┐          │ Curr
             │ Prev     │
      95 ────┘     97 ──┘

Meaning: Trending up. Previous LOW came before current HIGH.
         Creates/extends bull leg from prev.LOW to curr.HIGH.


TYPE 2-BEAR: DOWNTREND (LH + LL)
────────────────────────────────
Previous: H=100, L=95
Current:  H=98,  L=93  (Lower High AND Lower Low)

     100 ────┐
             │ Prev
      95 ────┘
        98 ──┐
             │ Curr
        93 ──┘

Meaning: Trending down. Previous HIGH came before current LOW.
         Creates/extends bear leg from prev.HIGH to curr.LOW.


TYPE 3: OUTSIDE BAR (HH + LL)
─────────────────────────────
Previous: H=100, L=95
Current:  H=102, L=93  (Higher High AND Lower Low)

                  102 ──┐
     100 ────┐          │
             │ Prev     │ Curr (engulfing)
      95 ────┘          │
                   93 ──┘

Meaning: Engulfing/outside bar. High volatility, ambiguous order.
         Both extremes updated. No legs created (ambiguous).
```

### Real ES Example: Bar Classification

```
ES 5-minute: January 3, 2023, 00:00-00:30

Bar 0: O=3976.50 H=3978.50 L=3976.25 C=3977.50
Bar 1: O=3977.75 H=3977.75 L=3977.00 C=3977.50
       Compare to Bar 0: H 3977.75 < 3978.50 (LH)
                         L 3977.00 > 3976.25 (HL)
       → TYPE 1 (Inside Bar)

Bar 2: O=3977.75 H=3979.50 L=3977.75 C=3979.00
       Compare to Bar 1: H 3979.50 > 3977.75 (HH)
                         L 3977.75 > 3977.00 (HL)
       → TYPE 2-BULL

Bar 3: O=3979.25 H=3979.50 L=3978.25 C=3978.25
       Compare to Bar 2: H 3979.50 = 3979.50 (not HH)
                         L 3978.25 > 3977.75 (HL)
       → TYPE 1 (equal high treated as inside)

Bar 4: O=3978.50 H=3980.00 L=3978.25 C=3979.25
       Compare to Bar 3: H 3980.00 > 3979.50 (HH)
                         L 3978.25 = 3978.25 (not HL)
       → TYPE 1 (equal low treated as inside)

Bar 5: O=3979.00 H=3981.00 L=3979.00 C=3980.75
       Compare to Bar 4: H 3981.00 > 3980.00 (HH)
                         L 3979.00 > 3978.25 (HL)
       → TYPE 2-BULL
```

---

## Formation: When a Leg Becomes a Swing <a name="formation"></a>

### The Formation Rule

A leg FORMS (becomes a swing) when price has moved at least 28.7% from origin toward pivot.

**Key insight:** Formation measures *progress through the move*, not a pullback. A leg can form on the same bar it's created if the move is already substantial.

```
BULL LEG FORMATION:
───────────────────
            Pivot ────►  3983.25
               ▲
               │ Range = 7.00
               │
           Origin ────►  3976.25

Formation Check: (current - origin) / range >= 0.287
                 (current - 3976.25) / 7.00 >= 0.287
                 current >= 3978.26

When bar.close >= 3978.26, the swing is FORMED.
(Note: Uses bar.high for inside bars where temporal order is known)


BEAR LEG FORMATION:
───────────────────
           Origin ────►  4523.50
               │
               │ Range = 5.25
               ▼
            Pivot ────►  4518.25

Formation Check: (origin - current) / range >= 0.287
                 (4523.50 - current) / 5.25 >= 0.287
                 current <= 4522.00

When bar.close <= 4522.00, the swing is FORMED.
```

### Why Have a Formation Threshold?

Formation ensures the move is substantial:

```
ES 5-minute: Very small move

Bar 0: Price at 3900
Bar 1: Type 2-Bull, price at 3901 (only 1 point move)

Without formation requirement:
  - This tiny move creates a "swing"
  - Not meaningful structure

With formation requirement:
  - 1 point move with any reasonable pivot won't meet 28.7%
  - Filters out noise, keeps only substantial moves
```

**What formation really means:** The move from origin to pivot is big enough to matter. It's not just random fluctuation.

### Real ES Example: Formation

```
ES 5-minute: March 9, 2023 (Pre-SVB period)

Session shows price trending up from 4517.50 to 4524.00

Bull Leg Created:
  Origin: 4517.50 (LOW at 17:15)

As price extends:
  Bar +5: Pivot extends to 4520.25
  Bar +10: Pivot extends to 4522.25
  Bar +15: Pivot extends to 4523.50
  Bar +20: Pivot extends to 4524.00

Range = 4524.00 - 4517.50 = 6.50 points
Formation threshold = 4517.50 + (0.287 × 6.50) = 4519.37

Looking for close ≥ 4519.37:
  Bar at 19:15: Close = 4520.25 → 43% retracement ✓ FORMED!

The 4524.00 high is now a confirmed swing high.
```

---

## Invalidation: When Structure Breaks <a name="invalidation"></a>

### The Invalidation Rule

A leg (or swing) is INVALIDATED when price breaches the origin by 38.2% of the range.

```
BULL LEG INVALIDATION:
──────────────────────
            Pivot ────►  3983.25
               ▲
               │ Range = 7.00
               │
           Origin ────►  3976.25
               │
               │ 38.2% of Range = 2.67
               ▼
    Invalidation ────►  3973.58

When bar.low ≤ 3973.58, the leg is INVALIDATED.
The pivot is no longer a valid swing reference.


BEAR LEG INVALIDATION:
──────────────────────
    Invalidation ────►  4525.51
               ▲
               │ 38.2% of Range = 2.01
               │
           Origin ────►  4523.50
               │
               │ Range = 5.25
               ▼
            Pivot ────►  4518.25

When bar.high ≥ 4525.51, the leg's origin is BREACHED.
The pivot is no longer a valid swing reference.
```

### What Happens After Origin Breach? (#345)

**Breached legs are NOT immediately deleted.** They remain as counter-trend references:

1. Pivot is frozen (stops extending)
2. `max_origin_breach` is set (tracks breach amount)
3. Leg remains visible for context
4. Eventually cleaned up by pruning mechanisms (engulfed, stale extension)

### Real ES Example: Origin Breach

```
ES 5-minute: January 3, 2023, 07:00-08:00

Strong selloff during early session:

Bull Leg before breach:
  Origin: 3985.50 (LOW at 06:30)
  Pivot: 3989.75 (HIGH at 03:00)
  Range: 4.25 points

Bar at 07:20: Low = 3976.50 ← Below origin of 3985.50!

Origin breach amount = 3985.50 - 3976.50 = 9 points
The leg's origin is BREACHED (max_origin_breach = 9).
The 3989.75 swing high is no longer valid structure.
Price has broken the pattern — the low was not defended.

What happened next:
  Bar at 07:30: Low = 3968.50 (aggressive selloff continues)
  Bar at 07:40: Low = 3964.75
  Bar at 08:05: Low = 3960.00

The invalidation correctly signaled structure breakdown.
```

---

## Pruning: Keeping the Structure Clean <a name="pruning"></a>

Multiple legs can exist simultaneously. Pruning removes redundant or dominated legs.

### 1. Origin-Proximity Pruning (#294, #319)

**Rule:** Legs close together in origin (time, range) space are consolidated. Legs are grouped into clusters where BOTH conditions are true:
- **Time ratio** < threshold: Legs formed around the same time
- **Range ratio** < threshold: Legs have similar ranges

```
Formula:
  time_ratio = (bars_since_older_origin - bars_since_newer_origin) / bars_since_older_origin
  range_ratio = |older_range - newer_range| / max(older_range, newer_range)

  Legs are in proximity if: time_ratio < time_threshold AND range_ratio < range_threshold

Example at bar 100:
  Leg A: origin_index=0, range=10 (older, larger)
  Leg B: origin_index=5, range=9  (newer, smaller)

  time_ratio = (100-0 - 100-5) / (100-0) = 5/100 = 0.05
  range_ratio = |10-9| / max(10,9) = 0.10

  With thresholds: time=0.10, range=0.20
  0.05 < 0.10 ✓ AND 0.10 < 0.20 ✓ → Legs A and B are in same cluster
```

**Survivor Selection Strategy (#319):**

Two strategies determine which leg survives from each cluster:

| Strategy | Survivor Rule | Use Case |
|----------|---------------|----------|
| `oldest` (default) | Oldest leg (by origin_index) wins | Simple, deterministic, O(N log N) |
| `counter_trend` | Highest counter-trend range wins | Prioritizes structural significance |

**Counter-Trend Scoring:**
When `counter_trend` strategy is active, each leg is scored by how far price traveled against the trend to reach its origin:

```
For a leg with parent:
  counter_range = |leg.origin_price - parent.segment_deepest_price|

For a leg without parent (root leg):
  score = leg.range (fallback to simple range)

Tie-breaker: If scores are equal, oldest leg wins.
```

**Rationale:**
- Legs formed close together in time = redundant structure (noise)
- Legs formed far apart in time = distinct structures (keep both)
- Counter-trend scoring favors legs that required significant market reversal to form
- These are more likely to represent meaningful structural levels

**Defensive Check:** If a newer leg is longer than an older leg, an exception is raised. This should be impossible per design (breach/engulfing mechanics prevent it). If it happens, there's a bug upstream.

### 2. Pivot Breach Pruning

**Rule:** A formed leg whose pivot is breached (but origin defended) gets replaced.

```
Scenario: Bull swing formed at pivot 4000, origin 3980
          Price rallies to 4015 (10%+ breach of pivot)
          BUT origin (3980) was never breached

Action:
1. Original leg (origin=3980, pivot=4000) is PRUNED
2. Replacement leg created: origin=3980, pivot=4015
3. Replacement must re-form (not automatically formed)

Rationale: The defended level (origin) is intact.
           The pivot just extended — structure continues.
```

### 3. Engulfed Pruning

**Rule:** A leg breached on BOTH origin AND pivot is deleted immediately.

```
Scenario: Bull swing with origin=3980, pivot=4000
          First, price drops below 3980 (origin breach)
          Then, price rallies above 4000 (pivot breach)

Both endpoints violated = structure is meaningless.
Leg is deleted immediately. No replacement.
```

### 4. Min Counter-Trend Ratio Pruning

**Rule:** Child legs require sufficient counter-trend at their origin relative to their parent's counter-trend.

This is an **origin selection filter** that operates at leg creation time (#337). It prevents insignificant child legs from being created by requiring the counter-trend at the child's origin to be at least a minimum ratio of the counter-trend at the parent's origin.

```
Formula:
  R0 = range of largest counter-direction leg at new leg's origin
  R1 = range of largest counter-direction leg at parent's origin

  Create leg if: R0 >= min_branch_ratio * R1

For root legs (no parent):
  Always create (root legs have no parent to compare against)

For legs where parent has no counter-trend (R1 is None):
  Always create (parent is root-like, no comparison possible)

Example:
  Bear B1: 200 → 100 (range 100) - creates counter-trend at 100
  Bull L1: 100 → 190 (root) - uses B1 as counter-trend at origin
  Bear B2: 111 → 110 (range 1) - creates counter-trend at 110
  Bull L2: 110 → 190 (parent = L1)
    R0 = 1 (B2's range at L2's origin)
    R1 = 100 (B1's range at L1's origin)
    Check: 1 >= 0.1 * 100 = 10 → FAILS → L2 blocked

  With min_branch_ratio = 0.1 (10%): L2 blocked because 1 < 10
```

**Recursive scaling:**
The threshold scales naturally through the hierarchy:
- Root level: Large counter-trend (e.g., 100 pts)
- Child needs: >= 10% of 100 = 10 pts
- Grandchild needs: >= 10% of 10 = 1 pt

**Why this works:**
- At strong pivots (large counter-trend), child origins need significant counter-trend
- At weak pivots (small counter-trend), smaller counter-trends are acceptable
- This captures the fractal nature of market structure
- Operates at creation time, not as post-hoc pruning

### Real ES Example: Pruning in Action

```
ES 5-minute: August 1, 2023, 17:00-19:30

Price oscillates between 3918 and 3927

Active legs at one point:
1. Bull: O=3918.00 → P=3925.00 (from session low)
2. Bull: O=3919.25 → P=3925.00 (from higher low)

With origin-proximity pruning enabled:
  time_ratio = (bars_since_leg1 - bars_since_leg2) / bars_since_leg1
             = small (legs formed close together)
  range_ratio = |7.00 - 5.75| / 7.00 = 0.18 (similar ranges)

  Both ratios below threshold → Leg 2 is PRUNED

After pruning:
1. Bull: O=3918.00 → P=3925.00 (SURVIVES - older, larger)

Clean structure: dominant swing low at 3918.
```

---

## Hierarchy: Parent-Child Relationships <a name="hierarchy"></a>

Legs form hierarchical **trees by direction** — bull legs have a separate hierarchy from bear legs. Multiple disconnected hierarchies can exist within the same direction.

### The Leg Hierarchy Rule

Parent-child relationships are established when a new leg is created, based on **same-direction, time-price ordering**:

> "For any two legs L1 and L2 in the same direction such that L1.origin.time is before L2.origin.time and L1.origin.price < L2.origin.price, and no L3 exists such that L1.origin.time < L3.origin.time < L2.origin.time and L1.origin.price < L3.origin.price < L2.origin.price, then L2 is a child of L1."

**In plain terms:**
- Bull legs: A leg with a higher-low origin is a child of the nearest leg with a lower-low origin
- Bear legs: A leg with a lower-high origin is a child of the nearest leg with a higher-high origin
- "Nearest" means no intermediate leg exists between them in both time AND price dimensions

### Eligibility Constraint: Origin Breach

> "Only legs whose origin has not been breached can have new children."

When searching for a parent, legs with breached origins are filtered out. This ensures broken structure doesn't propagate into new hierarchy.

```
BULL HIERARCHY EXAMPLE:
═══════════════════════

L1: origin=(100, t1), non-breached     ← Root leg (lowest origin)
 └── L2: origin=(110, t2)              ← Child of L1 (higher low)
      └── L3: origin=(120, t3)         ← Child of L2 (higher low)

Each leg's origin is higher than its parent's.
This tracks the progression of "higher lows" in an uptrend.


BEAR HIERARCHY EXAMPLE:
═══════════════════════

B1: origin=(120, t1), non-breached     ← Root leg (highest origin)
 └── B2: origin=(115, t3)              ← Child of B1 (lower high)
      └── B3: origin=(110, t5)         ← Child of B2 (lower high)

Each leg's origin is lower than its parent's.
This tracks the progression of "lower highs" in a downtrend.
```

### Finding the Immediate Parent

The "no L3 between" clause naturally selects the **immediate predecessor**. Implementation simplifies to:

```
BULL: parent = max(origin.price) among eligible legs
      (eligible = same direction, non-breached, earlier time, lower price)

BEAR: parent = min(origin.price) among eligible legs
      (eligible = same direction, non-breached, earlier time, higher price)

TIEBREAKER: If multiple legs have the same origin price, select the one
            with the latest origin time (most recent confirmation of that level).
```

### Siblings and Distant Cousins

> "You can also have 'siblings' such that S1.origin.time < S2.origin.time but S1.origin.price = S2.origin.price although this should be rare. They are 'siblings' if S1's origin was never breached, then by definition S2 must have the same parent as S1. If S1's origin was breached, S2 will have a different parent. They're in unrelated branches and can be distant 'cousins' even."

Two legs at the same price level but different times:

**Case 1 — Siblings (S1 non-breached):**
- S1 and S2 have the same `origin_price`
- S1's origin was never breached
- When S2 forms, S1 is still eligible as a potential parent for others
- S2's parent search finds the same parent that S1 has
- Result: S1 and S2 are **siblings** (same parent)

**Case 2 — Distant Cousins (S1 breached):**
- S1 and S2 have the same `origin_price`
- S1's origin was breached before S2 formed
- S1 is filtered out of the eligible parent search
- S2's parent search finds a different (possibly much older or newer depending on price action) leg
- Result: S1 and S2 are in **completely different branches** — distant cousins or unrelated

### Reparenting on Prune

> "If legs L4, L5, and L6 exist, such that L6.parent = L5 and L5.parent = L4, then if L5 is pruned for whatever reason and L6 is not pruned then, L6.parent will be set to L4."

When a leg is pruned, its children are reparented to the grandparent:

```
BEFORE PRUNE:           AFTER L5 PRUNED:
L4 (root)               L4 (root)
 └── L5                  └── L6 (reparented)
      └── L6

If the root is pruned, children become roots.
```

### Multiple Disconnected Hierarchies

Bull and bear legs maintain **completely separate hierarchies**. Additionally, within the same direction, multiple disconnected trees can form:

```
EXAMPLE: Two separate bull hierarchies

Price action: L1 → H1 → L2 → H2 → L3 → H3
              (where L1 < L2 < H2 < L3 < H3)

Bull hierarchy: L1 → H3 forms one large bull leg
                (single tree tracking the major uptrend)

Bear hierarchies:
  Tree 1: H2 → L2 (not growing, inner structure)
  Tree 2: H3 → L3 (possibly still growing)

The bear legs from H2 and H3 are in separate hierarchies
because H3 > H2 (H3 cannot be a child of H2).
```

### Why Leg Hierarchy Matters

Leg hierarchy tracks **structural progression** within a directional move:

```
TRADING INTERPRETATION:
═══════════════════════

Bull leg hierarchy with depth 4:
  L1 (origin=3900) → L2 (3920) → L3 (3950) → L4 (3980)

This represents FOUR confirmed "higher lows" in succession.
- Strong trending structure
- Each child validates the parent's defended level
- Invalidation of L1 cascades implications to all descendants

Contrast with a single bull leg (depth 0):
- Just one defended low
- Less structural confirmation
- More vulnerable to invalidation
```

### Hierarchy vs. Swing Parents

**Leg hierarchy** (this section) tracks same-direction structural progression based on origin relationships.

**Swing hierarchy** uses Fibonacci containment: a swing is a parent of another if the child's defended pivot falls within the parent's 0-2 range. This enables cross-direction nesting (a bull swing inside a bear swing's range).

Both hierarchies coexist and serve different analytical purposes.

---

## Impulse Metrics: Quantifying Move Quality <a name="impulse-metrics"></a>

### Impulse (Raw Intensity)

**Formula:** `Impulse = Range / Bar Count`

```
Example:
  Bull leg from 3900 to 3950 over 10 bars
  Impulse = 50 / 10 = 5.0 points per bar

Compare:
  Bull leg from 3900 to 3950 over 50 bars
  Impulse = 50 / 50 = 1.0 point per bar

Higher impulse = faster, more aggressive move.
```

### Impulsiveness (Percentile Rank)

**Formula:** `Impulsiveness = Percentile Rank vs All Formed Legs`

```
If a leg's impulse is higher than 70% of all historical legs:
  Impulsiveness = 70

Range: 0-100
  0-30: Slow, grinding moves
  30-70: Normal intensity
  70-100: Sharp, aggressive moves
```

### Spikiness (Move Distribution)

**Formula:** Sigmoid normalization of Fisher's skewness

```
Spikiness measures HOW the move happened:
  - Low (10-40): Smooth, evenly distributed
  - Neutral (40-60): Balanced
  - High (60-90): Spike-driven, concentrated in few bars

Example interpretation:
  Impulse = 5.0, Spikiness = 80
  → Fast move that happened mostly in one or two bars

  Impulse = 5.0, Spikiness = 30
  → Same total move but spread evenly across bars
```

### Trader Application

```
                    High Impulsiveness
                          │
           ┌──────────────┼──────────────┐
           │              │              │
           │   Impulsive  │  Impulsive   │
           │   + Smooth   │  + Spiky     │
           │              │              │
           │   Trend      │  Breakout    │
Low ───────┼──────────────┼──────────────┼─────── High
Spikiness  │              │              │  Spikiness
           │              │              │
           │   Grinding   │  Choppy      │
           │   + Smooth   │  + Spiky     │
           │              │              │
           └──────────────┼──────────────┘
                          │
                   Low Impulsiveness

Trading signals:
  - High impulsiveness + Low spikiness = Strong trend continuation
  - High impulsiveness + High spikiness = Possible exhaustion
  - Low impulsiveness + High spikiness = Choppy, avoid
```

---

## Configuration Parameters <a name="configuration"></a>

All thresholds are configurable. Defaults shown:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `formation_fib` | 0.236 | Retracement % to confirm swing |
| `engulfed_breach_threshold` | 0.0 | Combined breach % for engulfed deletion (#236) |
| `origin_range_prune_threshold` | 0.0 | Range similarity % for origin-proximity consolidation (#294) |
| `origin_time_prune_threshold` | 0.0 | Time proximity % for origin-proximity consolidation (#294) |
| `proximity_prune_strategy` | 'oldest' | Strategy for selecting survivor: 'oldest' or 'counter_trend' (#319) |
| `min_branch_ratio` | 0.0 | Branch ratio for origin domination - prevents insignificant child legs (#337) |
| `min_turn_ratio` | 0.0 | Turn ratio threshold for sibling pruning (threshold mode) (#341, #344) |
| `max_turns_per_pivot` | 0 | Top-k turn ratio pruning - keep only k highest-ratio legs per pivot (#342, #344) |
| `stale_extension_threshold` | 3.0 | Prune breached child legs at 3x range (root legs preserved) |

**Note (#345):** Origin breach is detected at 0% (any touch of origin). The old `invalidation_threshold` parameter has been removed. Leg status is now only `'active'` or `'stale'`, with `max_origin_breach` tracking structural invalidation.

Bull and bear can have different configs for asymmetric markets.

### Dynamic Configuration (Issue #288)

The detector supports **runtime configuration updates** via `LegDetector.update_config()`:

```python
from src.swing_analysis.dag import LegDetector
from src.swing_analysis.swing_config import SwingConfig

# Create detector with defaults
detector = LegDetector()

# Later, update config (resets state)
new_config = SwingConfig.default().with_bull(formation_fib=0.5)
detector.update_config(new_config)

# Must re-calibrate after config change
for bar in bars:
    detector.process_bar(bar)
```

**Key behaviors:**
- `update_config()` resets internal state (clears legs, pending origins, etc.)
- Caller must re-run calibration from bar 0 to apply new thresholds
- Useful for experimenting with different thresholds during analysis

**Frontend integration:**
The Detection Config Panel in the sidebar provides sliders for adjusting thresholds:
- Bull/Bear Formation threshold (0.1-1.0)
- Bull/Bear Invalidation threshold (0.1-1.0)
- Stale Extension threshold (1.0-5.0)
- Origin Range % threshold (0.0-0.5) — Range similarity for origin-proximity pruning (#294)
- Origin Time % threshold (0.0-0.5) — Time proximity for origin-proximity pruning (#294)
- Min Branch Ratio % threshold (0.0-0.2) — Branch ratio for origin domination (#337)
- Turn Ratio Pruning mode toggle (#342, #344):
  - Off: Disabled
  - %: Threshold mode with min_turn_ratio slider
  - Top-k: Top-k mode with max_turns_per_pivot slider
  - Note: The largest leg at each pivot is always exempt from turn-ratio pruning (#344)

Changes trigger automatic re-calibration via `PUT /api/replay/config`.

---

## Complete Example: Walking Through Real Data <a name="complete-example"></a>

Let's walk through a complete sequence using ES 5-minute data.

### Session: January 3, 2023, 00:00-03:00 UTC

```
BAR-BY-BAR WALKTHROUGH
══════════════════════

Bar 0 (00:00): O=3976.50 H=3978.50 L=3976.25 C=3977.50
──────────────────────────────────────────────────────
First bar. Initialize:
  Pending Bull Origin: 3976.25 (LOW)
  Pending Bear Origin: 3978.50 (HIGH)
  Active Legs: []


Bar 1 (00:05): O=3977.75 H=3977.75 L=3977.00 C=3977.50
──────────────────────────────────────────────────────
Compare to Bar 0:
  H: 3977.75 < 3978.50 (Lower High)
  L: 3977.00 > 3976.25 (Higher Low)
  → TYPE 1 (Inside Bar)

No leg created (no temporal order established).
Pending origins unchanged.


Bar 2 (00:10): O=3977.75 H=3979.50 L=3977.75 C=3979.00
──────────────────────────────────────────────────────
Compare to Bar 1:
  H: 3979.50 > 3977.75 (Higher High)
  L: 3977.75 > 3977.00 (Higher Low)
  → TYPE 2-BULL

Temporal order: Bar 0's LOW (3976.25) came before Bar 2's HIGH (3979.50)

CREATE BULL LEG:
  Origin: 3976.25
  Pivot: 3979.50
  Range: 3.25 points

Active Legs: [Bull: 3976.25 → 3979.50]


Bar 5 (00:25): O=3979.00 H=3981.00 L=3979.00 C=3980.75
──────────────────────────────────────────────────────
Compare: HH=3981.00 > 3980.00, HL=3979.00 > 3978.25
→ TYPE 2-BULL

EXTEND BULL LEG PIVOT:
  Origin: 3976.25 (unchanged)
  Pivot: 3981.00 (extended from 3979.50)
  Range: 4.75 points


Bar 6 (00:30): O=3980.75 H=3983.25 L=3980.25 C=3982.25
──────────────────────────────────────────────────────
Compare: HH, HL → TYPE 2-BULL

EXTEND BULL LEG PIVOT:
  Origin: 3976.25
  Pivot: 3983.25 (extended)
  Range: 7.00 points

CHECK FORMATION:
  Formation threshold = 3976.25 + (0.287 × 7.00) = 3978.26
  Current close = 3982.25
  Retracement = (3982.25 - 3976.25) / 7.00 = 85.7%

  Wait... that's above the pivot. Not yet retracing.


Bar 7 (00:35): O=3982.25 H=3982.75 L=3979.25 C=3980.00
──────────────────────────────────────────────────────
Compare: LH=3982.75 < 3983.25, HL=3979.25 < 3980.25
→ TYPE 2-BEAR (direction change!)

CREATE BEAR LEG:
  Origin: 3983.25 (previous bar's HIGH)
  Pivot: 3979.25 (current LOW)
  Range: 4.00 points

Active Legs: [Bull: 3976.25 → 3983.25, Bear: 3983.25 → 3979.25]

CHECK BULL LEG FORMATION:
  Formation threshold = 3976.25 + (0.287 × 7.00) = 3978.26
  Current close = 3980.00
  Retracement toward origin = (3983.25 - 3980.00) / 7.00 = 46.4%

  Has price pulled back to 3978.26?
  Close is 3980.00, which is above 3978.26.
  So retracement is: (3980.00 - 3976.25) / 7.00 = 53.6% of range above origin.

  Formation check: Is price at or below formation level? No.
  Formation threshold interpreted as: price must retrace TO this level.
  3980.00 > 3978.26, so still above formation level.

  WAIT: Let me reconsider. For a BULL leg:
    - Origin is at LOW (3976.25)
    - Pivot is at HIGH (3983.25)
    - Formation means price retraces TOWARD origin (goes down)
    - Formation price = 3976.25 + 0.287 × 7.00 = 3978.26
    - Price must drop TO 3978.26 or below to form.

  Current close = 3980.00 (above 3978.26)
  NOT YET FORMED.


Bar 8-10: Price continues lower...

Bar 11 (00:55): O=3979.50 H=3980.00 L=3979.00 C=3979.75
───────────────────────────────────────────────────────
Close = 3979.75 (still above 3978.26 formation level)

Bull leg still forming...


Bar 25 (02:00): O=3982.75 H=3984.00 L=3978.25 C=3981.00
───────────────────────────────────────────────────────
Low = 3978.25 (touched formation zone!)

CHECK BULL LEG FORMATION:
  Formation threshold = 3978.26
  Low = 3978.25 ← BELOW threshold!

  Using close for formation check: Close = 3981.00 (above threshold)

  Actually, the algorithm uses close for TYPE_2 bars.
  Close = 3981.00 > 3978.26, so NOT formed on this bar.


Bar 31 (02:30): O=3981.50 H=3981.50 L=3978.75 C=3980.50
───────────────────────────────────────────────────────
TYPE 1 (inside bar)
For TYPE 1, formation uses bar.high for bull check.

High = 3981.50 > 3978.26 → Still above formation zone.

Hmm, the bull leg keeps extending but hasn't formed yet because
price hasn't retraced enough. Let me check if the pivot extended more.

Actually, checking the data: Bar at 03:00 shows H=3989.50
So the pivot extended further, increasing the range.

New range after extension:
  Origin: 3976.25
  Pivot: 3989.50
  Range: 13.25 points
  Formation threshold = 3976.25 + (0.287 × 13.25) = 3980.05

Now price needs to drop to 3980.05 or below to form.


Bar at 03:05 (close=3986.75): Above 3980.05 → NOT FORMED
Bar at 03:15 (close=3983.50): Above 3980.05 → NOT FORMED
Bar at 03:20 (close=3983.50): Above 3980.05 → NOT FORMED
Bar at 03:25 (close=3983.00): Above 3980.05 → NOT FORMED
...

Eventually when price drops below 3980.05, the swing FORMS.
```

This walkthrough illustrates:
1. Bar classification determining temporal order
2. Leg creation from pending origins
3. Pivot extension on new extremes
4. Turn detection and pruning
5. Formation threshold calculation and waiting

---

## QA Section: Expert Trader Questions <a name="qa-section"></a>

### Q1: Why 28.7% for formation instead of 38.2%?

**A:** The 28.7% threshold sits between 23.6% and 38.2% Fibonacci levels. It's a balance:
- **Too low (23.6%):** Too many small moves qualify as "swings."
- **Too high (38.2%):** Misses moves that are substantial but haven't extended far enough.

28.7% is empirically chosen to filter noise while capturing real structure. The move must be at least 28.7% of the range to be considered a swing.

*Verification:* The configuration allows this to be changed. You could set `formation_fib=0.382` for more conservative detection (only larger moves form swings).

### Q2: Why use origin breach for invalidation instead of just "price below origin"?

**A:** A simple breach (1 tick below) would be too sensitive. Markets probe levels before reversing. The 38.2% threshold:
- Gives the structure room to breathe
- Aligns with Fibonacci significance
- Filters out false breakdowns

Example: If origin is 3900 with range 50, invalidation is at 3880.9. This means:
- 3899.75 breach? Structure intact.
- 3880.00 breach? Structure broken.

### Q3: Why not just track the most recent swing? Why multiple legs?

**A:** Markets are fractal. Multiple structures coexist at different scales:

```
Daily trader sees: 3800 → 4000 → 3900 (big swing)
Intraday trader sees: 3920 → 3950 → 3935 (small swing within)

Both are valid. The algorithm tracks all concurrent structures
so traders at different timeframes get relevant levels.
```

### Q4: What happens when a swing is invalidated? Does it disappear immediately?

**A:** No. Invalidated swings remain as **historical references** for context. They're eventually pruned when:
- Another structure supersedes them (domination)
- They become engulfed (both ends breached)
- The market moves far beyond them (optional 3x cleanup, currently disabled)

Traders can still see where old structure was, even if it's no longer valid.

### Q5: How do I know if a swing is "big" vs "small"?

**A:** The algorithm tracks a population of all formed leg ranges. A swing is "big" if its range is in the top 10% of all historical swings (configurable via `big_swing_threshold`).

Big swings get different invalidation tolerances — they're more significant levels.

### Q6: The algorithm tracks "impulse" and "spikiness" — how should I interpret these together?

**A:**

| Impulse | Spikiness | Interpretation |
|---------|-----------|----------------|
| High | Low | Strong sustained trend — high conviction |
| High | High | Explosive move — possibly exhaustion |
| Low | Low | Grinding consolidation — range-bound |
| Low | High | Choppy noise — low signal quality |

The combination tells you both *how fast* and *how* the move happened.

### Q7: What's the difference between pivot extension and engulfed?

**A:** They represent different scenarios:

**Pivot extension (origin NOT breached):**
- Origin is still defended
- Price moves beyond the current pivot in the leg's direction
- Structure is intact and growing
- Action: Pivot extends to the new extreme

**Engulfed (BOTH origin AND pivot breached over time):**
- Origin was breached at some point (leg invalidated)
- Later, price also went past the frozen pivot
- Structure is completely violated — price hit both ends
- Action: Delete the leg entirely (#208, #305)

### Q8: Can a swing have multiple parents? What does that mean?

**A:** Yes. A swing can be a child of multiple larger structures:

```
Parent A: Daily swing 3800 → 4100
Parent B: 4H swing 3900 → 4050

Child: 1H swing 3950 → 4020

Child's defended pivot (3950) is within both parents' ranges.
Child is nested inside BOTH larger structures.
```

This means invalidating Parent A would cascade implications to the child, and similarly for Parent B.

### Q9: The algorithm seems complex. Is there a simpler mental model?

**A:** Yes. Think of it as tracking "defended levels":

1. **A level becomes defended** when price bounces from it (leg created)
2. **Defense is confirmed** when price retraces 28.7% toward it (swing formed)
3. **Defense is broken** when price breaches 38.2% beyond it (invalidated)

Everything else (pruning, hierarchy, metrics) is bookkeeping to keep the structure clean and hierarchical.

---

## Simplification Opportunities <a name="simplification"></a>

After reverse-engineering all rules, here are potential simplifications:

### 1. Unifying Theme: "Defended Levels"

All rules reduce to one concept: **Is this level still being defended?**

- Formation = confirmation of defense
- Invalidation = defense broken
- Pruning = removing redundant defenders

**Opportunity:** Rename "leg" to "defended level" in documentation. More intuitive for traders.

### 2. Formation vs. Invalidation Thresholds

Current:
- Formation: 28.7% retracement
- Invalidation: 38.2% breach

These could be unified as **one "structure threshold"** with different directions:
- Positive direction (toward pivot): Formation
- Negative direction (away from origin): Invalidation

**Opportunity:** Single `structure_threshold = 0.382` that governs both.

### 3. Pruning Rules Consolidation

Three pruning rules could reduce to two:
1. **Dominance:** Keep the best origin for each direction
2. **Breach:** Remove when endpoints are violated

The proximity pruning is a variation of dominance.

**Opportunity:** Document as "dominance-based cleanup" rather than separate rules.

### 4. Impulse Metrics

Three metrics (impulse, impulsiveness, spikiness) may be overkill. Consider:
- **Keep:** Impulse (raw) — simple, intuitive
- **Optional:** Impulsiveness (percentile) — useful for comparison
- **Question:** Spikiness — adds complexity for marginal utility

**Opportunity:** Make spikiness opt-in or remove entirely.

### 5. Configuration Asymmetry

Bull/bear can have different configs, but is this used?

Current defaults are symmetric. If asymmetric behavior isn't needed, simplify to single config.

**Opportunity:** Merge `bull` and `bear` configs unless asymmetry is actively used.

---

## Appendix A: All Thresholds Summary

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Formation Fibonacci | 0.287 | Retracement to confirm swing |
| Invalidation Threshold | 0.382 | Origin breach to invalidate |
| Pivot Breach Threshold | 0.10 | Pivot extension to replace |
| Origin Range Prune | 0.0 | Range similarity for origin-proximity pruning (#294) |
| Origin Time Prune | 0.0 | Time proximity for origin-proximity pruning (#294) |
| Big Swing Threshold | 0.10 | Top 10% by range = "big" |
| Big Swing Price Tolerance | 0.15 | Touch tolerance for big swings |
| Big Swing Close Tolerance | 0.10 | Close tolerance for big swings |
| Child Swing Tolerance | 0.10 | Tolerance for children of big swings |
| Stale Extension | 3.0 | Prune invalidated child legs at 3x range |

---

## Appendix B: Event Types

The algorithm emits events for state changes:

| Event | Trigger |
|-------|---------|
| `LegCreatedEvent` | New leg from pending origin |
| `LegPrunedEvent` | Leg removed by pruning |
| `LegInvalidatedEvent` | Origin breach beyond threshold |
| `SwingFormedEvent` | Leg reached formation threshold |
| `SwingInvalidatedEvent` | Formed swing's origin breached |
| `LevelCrossEvent` | Price crossed Fibonacci level |

---

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| **Leg** | Directional move from origin to pivot, before confirmation |
| **Swing** | Confirmed leg (reached 28.7% retracement) |
| **Origin** | Where the move started (fixed, defended level) |
| **Pivot** | Current extreme of the move (extends on new extremes) |
| **Range** | Distance from origin to pivot |
| **Formation** | Confirmation of swing via retracement |
| **Invalidation** | Structure broken via origin breach |
| **Pruning** | Removing redundant or dominated legs |
| **DAG** | Directed Acyclic Graph (hierarchical structure) |
| **Impulse** | Points per bar (move intensity) |
| **Impulsiveness** | Percentile rank of impulse |
| **Spikiness** | Skewness of bar contributions |

---

*End of Document*
