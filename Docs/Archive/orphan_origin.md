# Orphaned Origins: Analysis and Conclusion

**Status:** DEPRECATED - To be removed in #210

---

## What Are Orphaned Origins?

When a leg is invalidated, its origin is preserved as an "orphaned origin." The intent was to later pair this origin with a new pivot to form "sibling swings."

---

## The Problem

The implementation is structurally broken. Traced example:

```
Bar 1: H1 = 100
Bar 2: L1 = 90   → Bear leg: origin=H1 (100), pivot=L1 (90)
Bar 3: H2 = 98   → Bear leg defended. Bull leg: origin=L1 (90), pivot=H2 (98)
Bar 4: L2 = 85   → Bull leg invalidated (85 < 86.9)
                 → Orphaned origin preserved: L1 = 90
Bar 5: H3 = 95   → New bull leg: origin=L2 (85), pivot=H3 (95)
                 → Sibling formed: L1 (90) → H3 (95)
```

**What sibling formation produces:**
- Primary swing: L2 (85) → H3 (95), range = 10
- Sibling swing: L1 (90) → H3 (95), range = 5

**Why this is wrong:**
1. L1 (90) was already **broken** - price went through it to L2 (85)
2. The primary swing L2→H3 already captures the correct structure
3. The sibling L1→H3 is strictly **smaller** and structurally meaningless
4. There's no leg from L1 to H3 - the actual leg is L2→H3

---

## Data Validation

Using `test_data/es-5m.csv` (bars 1,172,207 to 1,182,207):

| Metric | Value |
|--------|-------|
| Total swings | 6,894 |
| Sibling swings | 318 (4.6%) |
| Siblings smaller than primary | 99.9% |

Almost all siblings are smaller - confirming they represent broken levels, not meaningful structure.

---

## Spec vs Implementation Mismatch

The original spec (#163) intended to preserve the **"1"** (the extreme) to pair with a new **"0"** (defended level). This would create a **larger** swing.

But the implementation preserves `leg.origin_price`:
- For bull leg: origin = LOW (the defended level, not the extreme)
- This pairs with new HIGH to create a **smaller** swing

The spec's intent and the implementation diverged.

---

## R3 (Pivot Breach) Is Sufficient

Issue #208 implemented R3: when a leg's pivot is breached, create a replacement leg with the same origin but extended pivot.

This correctly handles structure extension without needing orphaned origins:
- Bear leg 100→90 extends to 100→85 via R3
- New bull leg 85→95 captures the reversal
- No need for orphaned L1=90

---

## Conclusion

**Delete orphaned origins entirely.** Added to #210.

The concept was intended to detect nested/fractal structure but:
1. The implementation produces structurally meaningless smaller swings
2. R3 replacement legs handle the valid use case (structure extension)
3. The code adds complexity with no value

---

## Files to Remove (tracked in #210)

- `DetectorState.orphaned_origins` (state.py)
- `_form_sibling_swings_from_orphaned_origins()` (leg_detector.py)
- `_prune_orphaned_origins()` (leg_detector.py)
- `_clean_up_after_leg_creation()` orphan logic (leg_detector.py)
- Orphan creation on invalidation (leg_detector.py)
- Serialization/deserialization (state.py)
- ground_truth_annotator schema/endpoint references
- Related tests
