# Why We Track Pending Origins

**Document Type:** Product Explanation
**Date:** 2025-12-21

## The Core Problem

When detecting market structure (legs/swings), we need to know where a move **started** (the origin) and where it's **going** (the pivot). The challenge: we can't know if a price extreme is the origin of a new leg until we see what happens next.

**Example:** A bar prints a low at 4520.0. Is this the start of an upward leg? We can't know yet. We need to see:
1. Does the market start moving up from here? (confirms it as a bull origin)
2. Or does it keep falling? (this low gets replaced by a lower low)

This is the **temporal ordering problem**: we must wait for future bars to establish that the origin came *before* the pivot in the price sequence.

## What Pending Origins Do

A `PendingOrigin` is a **candidate starting point** for a future leg that's waiting for confirmation. The system tracks two pending origins at all times:

| Direction | Pending Origin Tracks | What It Becomes |
|-----------|----------------------|-----------------|
| Bull | LOWs (potential bull leg starts) | Origin of bull leg |
| Bear | HIGHs (potential bear leg starts) | Origin of bear leg |

**Lifecycle:**
1. **Established** — When a bar prints a new extreme (low for bull, high for bear)
2. **Updated** — If a more extreme price appears, the pending origin updates
3. **Consumed** — When temporal ordering is confirmed, a leg is created using the pending origin
4. **Cleared** — The pending origin is set to None after consumption

## Real Data Examples

Using ES 5-minute bars starting at offset 1172207:

### Example 1: Simple Two-Bar Confirmation

```
Bar #1: O=4416.0, H=4417.25, L=4414.75, C=4415.75
  → Bull pending: None → 4414.75@0  (track the low)
  → Bear pending: None → 4417.25@0  (track the high)

Bar #2: O=4415.75, H=4416.25, L=4414.25, C=4415.25
  → Bull pending: 4414.75@0 → 4414.25@1  (lower low, update)
  → Bear pending: 4417.25@0 → CONSUMED
  *** LEG CREATED: bear origin=4417.25@0 → pivot=4414.25@1
```

The bar #2 moved lower (LH, LL pattern), confirming temporal order: the HIGH at bar #0 came before the LOW at bar #1. This creates a bear leg.

### Example 2: Pending Origin Survives 13 Bars

This is the critical case that shows why pending origins are essential:

```
Bar 1282: L=4520.0 → Bull pending set to 4520.0@1282
Bar 1283-1294: Sideways consolidation (12 bars of equal bars)
  → Bull pending PRESERVED at 4520.0@1282 through all 12 bars
Bar 1295: Finally confirms upward movement
  → Bull pending CONSUMED
  *** LEG CREATED: bull origin=4520.0@1282 → pivot=4521.25@1295
```

Without pending origins, we would have no way to "remember" that bar 1282 established the low. The origin would be lost during the 12-bar consolidation.

## Statistics from 10,000 Bars

| Metric | Value |
|--------|-------|
| Total legs created | 2,229 |
| Legs using delayed origin | 2,229 (100%) |
| Average origin age | 1.8 bars |
| Maximum origin age | 13 bars |

**Origin age distribution:**

| Bars delayed | Count | Percentage |
|--------------|-------|------------|
| 0-4 bars | 2,146 | 96.3% |
| 5-9 bars | 78 | 3.5% |
| 10-14 bars | 5 | 0.2% |

**Key insight:** Every single leg creation used a pending origin. Even when the origin was established on the previous bar (age=1), the pending origin mechanism was required to track it.

## Why This Can't Be Removed

### Without Pending Origins

If we removed pending origins, we'd need an alternative approach:

**Option A: Create legs immediately on each bar**
- Problem: We don't know if the current bar's extreme is an origin until the next bar
- Result: Would create invalid legs that immediately get invalidated

**Option B: Look backwards on each bar**
- Problem: Must scan backwards to find the "best" origin candidate
- Result: O(n²) complexity instead of O(n), catastrophic performance

**Option C: Only create legs from the current bar's extreme**
- Problem: Misses the true origin entirely
- Result: Incorrect leg structure — all origins would be 1 bar old maximum

### The 13-Bar Example Failure Case

Consider the consolidation from bars 1282-1295:

| Approach | Result |
|----------|--------|
| With pending origins | Origin correctly identified at 4520.0@1282 |
| Without (Option A) | Creates/invalidates 13 false legs during consolidation |
| Without (Option B) | Must scan 13 bars backward on bar 1295 — multiplied by 2229 legs = 29,000 backward scans |
| Without (Option C) | Origin incorrectly placed at bar 1294 or 1295 — wrong by 13 bars |

## Impact Assessment: Removing Pending Origins

### What Would Break

1. **Leg Origin Accuracy**
   - 100% of legs would have incorrect origins
   - Origins would be placed at the current bar instead of where the move actually started

2. **Market Structure Integrity**
   - Fibonacci retracements calculated from wrong origin
   - Swing highs/lows misidentified
   - Parent-child relationships between swings corrupted

3. **Performance**
   - Without forward tracking (pending origins), must backward-scan
   - Would degrade from O(n) to O(n²)
   - 10,000 bars: ~100M operations instead of ~10K

4. **Consolidation Handling**
   - Inside bars and sideways movement would break detection
   - The 3.7% of legs with origin age 5+ bars would be completely wrong

### What Would Need to Replace It

To remove pending origins, you'd need to:
1. Store all candidate extremes in a rolling buffer
2. Implement backward scanning with O(n²) worst case
3. Handle the "which origin is best?" selection problem
4. Deal with memory growth from storing all candidates

This is exactly what pending origins were designed to avoid.

## Conclusion

Pending origins are **load-bearing infrastructure** for the leg detection algorithm. They solve the temporal ordering problem elegantly:

- **Track forward** (O(1) per bar) instead of scanning backward (O(n) per bar)
- **Remember** origins through consolidation periods up to 13+ bars
- **Enable** accurate leg structure for all 2,229 legs in a 10,000 bar window

Removing this concept would require a complete rewrite of the detection algorithm with worse performance characteristics and more complex code. The current design is both simpler and faster.

**Recommendation:** Pending origins should remain as a core concept. Any refactoring should preserve this mechanism.
