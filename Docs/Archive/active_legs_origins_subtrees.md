# Why We Track Active Legs and Subtrees

**Document Type:** Product Explanation
**Date:** 2025-12-21

## The Core Concept

In the swing detection system, a **leg** represents a directional price move from origin to pivot. An **active leg** is one that's still being tracked for extension, formation, and invalidation. The `status` field controls what operations apply to each leg:

| Status | Meaning | Operations Allowed |
|--------|---------|-------------------|
| `active` | Currently being monitored | Extend pivots, form swings, prune, invalidate |
| `invalidated` | Origin breached beyond threshold | Wait for 3x extension, then remove |
| `stale` | Ready for removal | Removed from active_legs list |
| `pruned` | Consolidated with another leg | Immediately removed |

**The "active" concept answers:** Which legs should we still be updating, and which are frozen reference points?

## What "Active" Controls

### 1. Pivot Extension (Active Only)

When price makes a new extreme in the direction of a leg, only active legs extend:

```
Bar 100: Bull leg created - origin=4520.0, pivot=4530.0, status=active
Bar 101: Price makes new high at 4535.0
  → Active leg extends: pivot=4535.0
Bar 102: Origin breached, status becomes 'invalidated'
Bar 103: Price makes new high at 4540.0
  → Invalidated leg does NOT extend (pivot stays 4535.0)
```

**Why it matters:** Once a leg is invalidated, its pivot is "frozen" — it represents the historical high/low of that move, not a continuously updating reference.

### 2. Swing Formation (Active Only)

Legs can only form swings (confirm their structure) while active:

```python
# From leg_detector.py lines 723-758
for leg in self.state.active_legs:
    if leg.status != 'active' or leg.formed:
        continue  # Skip non-active or already-formed legs
    # Check if leg reaches 38.2% retracement threshold...
```

**Why it matters:** We don't want invalidated legs creating new swings. The market has already proven the move was wrong.

### 3. Breach Tracking (Active Only)

The system tracks how far price breaches origins and pivots, but only for active legs:

```
Active leg: origin=4520.0, pivot=4530.0 (range=10)
  Bar 105: price dips to 4518.0 (breaches origin by 2 points)
  → Track this breach for potential pruning

Invalidated leg: same prices
  Bar 105: price dips to 4518.0
  → Don't track — this leg is already resolved
```

### 4. Pruning Rules (Active Only)

Only active legs can be pruned via turn, proximity, or domination rules:

| Pruning Type | What It Does | Applies To |
|--------------|--------------|------------|
| Turn prune | Remove shorter legs when price turns | Active only |
| Proximity prune | Consolidate legs with similar origins | Active only |
| Domination prune | Larger leg absorbs smaller | Active only |

**Exception:** Legs with formed swings are immune to these pruning operations.

## Real Data Examples

Using ES 5-minute bars, offset 1172207, window 10,000 bars:

### Example 1: Status Transition Lifecycle

```
Bar    5: Leg 6e06bce1 created (bull, active, formed=True)
          Origin: 4413.75 @ bar 4
          Pivot: 4416.00 @ bar 5

Bar    6: Price violates origin beyond 38.2% threshold
          Status: active → invalidated
          Pivot extended to: 4419.25 (before invalidation)

          The leg is now FROZEN:
          - Pivot stays at 4419.25
          - Associated swing (85a70a8b) uses these coordinates
          - Leg remains in list as structural reference
```

### Example 2: Why Invalidated Legs Stay in the List

At the end of 500 bars, the system has:

| Status | Count | Why They Remain |
|--------|-------|-----------------|
| Active | 12 | Being actively monitored |
| Invalidated | 7 | All 7 have associated swings |

**Every invalidated leg has a swing attached.** The swing needs the leg's origin/pivot coordinates to calculate Fibonacci levels. Removing the leg would orphan the swing.

### Example 3: Population Over Time

Sampling every 200 bars across 10,000 bars:

| Bar | Active | Total | Active % |
|-----|--------|-------|----------|
| 200 | 9 | 17 | 53% |
| 2,000 | 37 | 64 | 58% |
| 5,000 | 43 | 92 | 47% |
| 8,000 | 79 | 134 | 59% |
| 10,000 | 91 | 162 | 56% |

**Observation:** Approximately 40-50% of legs are in non-active states at any time. These are structural references that the algorithm keeps for swing calculations.

### Example 4: High-Volume Transitions

Over 10,000 bars:

| Metric | Count |
|--------|-------|
| Legs created | 6,658 |
| Legs removed | 6,490 |
| Status transitions (active → invalidated) | 451 |

The status system manages ~7% of all legs through the invalidation lifecycle rather than immediate removal.

## The State Machine

```
                    ┌─────────────┐
                    │   Created   │
                    │  (active)   │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
┌────────▼─────────┐       │       ┌─────────▼────────┐
│  Pruning Paths   │       │       │   Invalidation   │
│ (turn/proximity/ │       │       │  (origin breach  │
│   domination)    │       │       │  beyond 0.382)   │
└────────┬─────────┘       │       └─────────┬────────┘
         │                 │                 │
         ▼                 │                 ▼
   status='pruned'         │          status='invalidated'
   (immediate removal)     │          (remains in list)
                           │                 │
                           │      ┌──────────┘
                           │      │ Price extends 3x
                           │      │ beyond origin
                           │      ▼
                           │  status='stale'
                           │  (removed from list)
                           │
            ┌──────────────┘
            │ Breach pruning
            │ (engulfed or pivot breach)
            ▼
       status='stale'
       (removed from list)
```

## Impact Assessment: Removing the "Active" Concept

### What Would Need to Change

**Option A: Remove all status tracking — just use a single list**

Every leg would be treated equally:

| Current Behavior | Without Active Status |
|------------------|----------------------|
| Invalidated legs freeze their pivots | All legs would extend forever |
| Only active legs can form swings | Invalidated legs could create swings |
| Pruning applies to active legs only | All legs subject to all pruning |

**Problems:**
1. Swings created from invalidated legs would be meaningless
2. Pivot prices would keep updating even after the market proved the move wrong
3. No way to distinguish "still tracking" from "keeping for reference"

**Option B: Remove legs immediately on invalidation**

When a leg is invalidated, delete it from the list.

**Problems:**
1. Swings lose their anchor points — swing has swing_id but no leg with matching id
2. Must orphan-check swings on every leg removal
3. Fibonacci calculations fail — no origin/pivot reference

**Option C: Copy leg data into swing, then delete leg**

Duplicate origin/pivot data into the swing, remove the leg.

**Problems:**
1. Data duplication — same prices stored in two places
2. Memory overhead increases
3. Complex synchronization if leg state ever updates
4. Breaks the current clean ownership model (leg owns coordinates, swing references leg)

### Quantified Impact

From 10,000 bars of real data:

| Metric | With Active Status | Without (Option A) | Without (Option B) |
|--------|-------------------|--------------------|--------------------|
| Legs managed | 6,658 | 6,658 | 6,658 |
| Correct pivot freeze | 451 legs | 0 (all extend wrong) | N/A |
| Orphaned swings | 0 | 0 | ~451 (need cleanup) |
| Valid swing refs | 100% | 100% | 0% (all orphaned) |

### The Root Issue

The "active" status exists because **legs have two lifecycle phases**:

1. **Tracking phase** — The leg is actively being updated as price moves
2. **Reference phase** — The leg is done updating but still needed structurally

Without this distinction, you'd need to either:
- Delete legs and orphan their swings
- Never delete legs (memory grows unbounded)
- Duplicate data across legs and swings

The status field is the **minimal mechanism** that solves this problem cleanly.

## Why This Exists: The Product Perspective

### The User's Mental Model

When a trader looks at market structure:
- **Active swings** are "in play" — price might return to these levels
- **Invalidated swings** are "broken" — the market rejected this structure

The system mirrors this mental model:
- Active legs can extend and form new structure
- Invalidated legs are frozen references showing where structure was rejected

### Trading Application

Consider a bull swing from 4520 to 4540:

| If status=active | If status=invalidated |
|------------------|----------------------|
| Price breaks 4540? Leg extends to new high | Pivot stays frozen at 4540 |
| 38.2% retracement? May form new swing | Cannot form new structure |
| Price returns to 4530? Active level to watch | Historical reference only |

The "active" concept directly maps to **tradability**: active structures are actionable, invalidated structures are historical context.

## Conclusion

The "active" status for legs is **load-bearing infrastructure** that:

1. **Separates concerns** — tracking logic vs. reference preservation
2. **Prevents incorrect updates** — invalidated legs don't extend or form swings
3. **Preserves structural integrity** — swings always have valid leg references
4. **Mirrors trading reality** — active = in play, invalidated = broken

**Recommendation:** The active/invalidated distinction should remain. Any refactoring should preserve this two-phase lifecycle.

### If Removal Is Desired

To safely remove the "active" concept, you would need to:

1. Embed leg coordinates directly in swings (data duplication)
2. Implement orphan detection and cleanup for swings
3. Rethink pivot extension logic to exclude "zombie" legs somehow
4. Add alternative mechanism to track "should this leg still update?"

The resulting system would be more complex, not simpler. The status field is an elegant solution to a real problem.
