# Architectural Audit: Type Classification, Symmetric Frames, and Semantic Enforcement

**Date:** 2025-12-20
**Issue:** #198
**Triggered by:** Bug cascade in #188-197
**Scope:** HierarchicalDetector leg/swing semantics

---

## Executive Summary

The audit examined three Product questions following a bug cascade (#188-197) that traced to terminology confusion (pivot/origin inversion).

**Findings:**
1. **Type classification is useful** — The 4-branch structure reflects market reality, not unnecessary complexity
2. **Symmetric frames are not recommended for legs** — Current explicit direction + semantic fields is clearer after #197 fixes
3. **Semantic consistency is now correct** — All audited locations follow the invariants

**Recommendation:** Keep current design. The #197 fix corrected the root cause (terminology inversion), and the codebase now enforces correct semantics throughout.

---

## Audit 1: Type Classification Utility

### Question
> Is the TYPE_1, TYPE_2_BULL, TYPE_2_BEAR, TYPE_3 classification helping or hurting the logic?

### Assessment

The `BarType` enum classifies the relationship between consecutive bars:

| Type | Pattern | What It Tells Us |
|------|---------|------------------|
| TYPE_1 | LH, HL (inside) | Both temporal orderings known |
| TYPE_2_BULL | HH, HL | prev.L before bar.H (uptrend) |
| TYPE_2_BEAR | LH, LL | prev.H before bar.L (downtrend) |
| TYPE_3 | HH, LL (outside) | Ambiguous — use close conservatively |

**Why 4 branches exist:**

The branches are not arbitrary — they encode **known temporal ordering** for intra-bar extremes:
- Within a single bar, we cannot know if H or L occurred first
- Between bars, the type classification tells us which extremes are temporally ordered
- This temporal ordering is essential for determining origin vs pivot

**The classification is useful because:**

1. **Temporal ordering by construction** — Rather than post-hoc filtering, temporal ordering is established at bar classification time
2. **Prevents incorrect leg creation** — TYPE_2_BEAR correctly avoids creating bull legs (see #195 fix)
3. **Conservative handling of ambiguity** — TYPE_3 uses close price because H/L order is unknown

**The classification is NOT problematic because:**

1. The 4 branches correspond to 4 distinct market conditions
2. Asymmetric code paths reflect asymmetric market movement (bull ≠ bear)
3. The bugs in #188-197 were due to **incorrect field assignment**, not the classification itself

### Verdict

**Keep current design.** The type classification correctly encodes temporal ordering and prevents the algorithm from creating legs with invalid structure.

---

## Audit 2: Symmetric Reference Frame for Legs

### Question
> Would a symmetric reference frame (0, 0.382, 1, 2) for legs reduce bug surface?

### Current Implementation

```python
@dataclass
class Leg:
    direction: Literal['bull', 'bear']
    origin_price: Decimal    # Where move started (fixed)
    origin_index: int
    pivot_price: Decimal     # Defended extreme (extends)
    pivot_index: int
```

Semantics:
- Bull: origin=LOW, pivot=HIGH
- Bear: origin=HIGH, pivot=LOW

### Alternative: Symmetric Leg

```python
@dataclass
class SymmetricLeg:
    anchor_0_price: Decimal   # defended pivot (0 in frame)
    anchor_0_index: int
    anchor_1_price: Decimal   # origin (1 in frame)
    anchor_1_index: int
    # Direction derived: anchor_1 > anchor_0 → bear, else bull
```

### Trade-off Analysis

| Aspect | Current (Explicit) | Symmetric |
|--------|-------------------|-----------|
| Field clarity | `origin_price` is obvious | `anchor_1_price` requires lookup |
| Bug surface | Swap origin/pivot → wrong behavior | Swap anchor_0/1 → wrong behavior |
| Code readability | `leg.origin_price` | `leg.anchor_1_price` (what's 1?) |
| Direction checks | Still needed for creation | Still needed for creation |
| Extension logic | `_extend_leg_pivots` with direction | `_extend_anchor_0` — simpler |
| Formation logic | `(close - origin) / range` | Same formula for both |

**Assessment:**

The symmetric approach has theoretical appeal but limited practical benefit:

1. **Root cause was terminology confusion, not asymmetry** — The #188-197 bugs occurred because code used "pivot" where it meant "origin" and vice versa. A symmetric frame would have different field names, but the same confusion could occur (`anchor_0` vs `anchor_1`).

2. **ReferenceFrame already provides symmetric abstraction** — The existing `ReferenceFrame` class (used for swings) provides the symmetric 0-1-2 coordinate system. Legs feed into this abstraction at swing formation time.

3. **Explicit direction improves debugging** — When investigating issues, seeing `direction='bear', origin_price=4416.25` is immediately understandable. Seeing `anchor_1_price=4416.25` requires deriving the direction.

4. **Post-#197, semantics are correct** — The fix enforced correct terminology throughout. Now that origin/pivot are correctly assigned, the explicit naming aids comprehension.

### Verdict

**Keep current design.** The symmetric frame is a good abstraction for the ReferenceFrame class (which already exists). For legs, explicit direction + semantic field names provide better debuggability now that terminology is correct.

---

## Audit 3: Semantic Consistency Post-#197

### Question
> Are the semantics correctly enforced throughout the code after the last spate of fixes?

### Invariants to Verify

| Leg Type | Origin | Pivot | Temporal Order |
|----------|--------|-------|----------------|
| Bull | LOW (move started) | HIGH (defended extreme) | origin_index < pivot_index |
| Bear | HIGH (move started) | LOW (defended extreme) | origin_index < pivot_index |

### Audit Results

#### `_process_type2_bull` (lines 681-694)
```python
new_leg = Leg(
    direction='bull',
    origin_price=pending.price,  # LOW - where upward move started
    origin_index=pending.bar_index,
    pivot_price=bar_high,  # HIGH - current defended extreme
    pivot_index=bar.index,
```
**Result:** ✅ Correct — Bull leg has origin=LOW, pivot=HIGH

#### `_process_type2_bear` (lines 769-778)
```python
new_bear_leg = Leg(
    direction='bear',
    origin_price=pending.price,  # HIGH - where downward move started
    origin_index=pending.bar_index,
    pivot_price=bar_low,  # LOW - current defended extreme
    pivot_index=bar.index,
```
**Result:** ✅ Correct — Bear leg has origin=HIGH, pivot=LOW

#### `_process_type1` (lines 846-857, 883-897)

Bear leg creation:
```python
origin_price=pending_bear.price,  # HIGH
pivot_price=pending_bull.price,   # LOW
```
Temporal check: `pending_bear.bar_index < pending_bull.bar_index`

Bull leg creation:
```python
origin_price=pending_bull.price,  # LOW
pivot_price=pending_bear.price,   # HIGH
```
Temporal check: `pending_bull.bar_index < pending_bear.bar_index`

**Result:** ✅ Correct — Both directions properly checked and assigned

#### `_form_swing_from_leg` (lines 1090-1111)
```python
if leg.direction == 'bull':
    swing = SwingNode(
        low_bar_index=leg.origin_index,   # origin at LOW
        low_price=leg.origin_price,
        high_bar_index=leg.pivot_index,   # pivot at HIGH
        high_price=leg.pivot_price,
else:
    swing = SwingNode(
        high_bar_index=leg.origin_index,  # origin at HIGH
        high_price=leg.origin_price,
        low_bar_index=leg.pivot_index,    # pivot at LOW
        low_price=leg.pivot_price,
```
**Result:** ✅ Correct — Swing fields mapped correctly from leg semantics

#### `_form_sibling_swings_from_orphaned_origins` (lines 1226-1247)

Same mapping as `_form_swing_from_leg`:
- Bull: low_bar=origin_index, high_bar=pivot_index
- Bear: high_bar=origin_index, low_bar=pivot_index

Ratio calculation (lines 1193-1196):
```python
if leg.direction == 'bull':
    ratio = (close_price - origin_price) / swing_range
else:
    ratio = (origin_price - close_price) / swing_range
```
**Result:** ✅ Correct — Bull origin=LOW, Bear origin=HIGH

#### `_check_leg_invalidations` (lines 1316-1327)
```python
if leg.direction == 'bull':
    invalidation_price = leg.origin_price - threshold_amount
    if bar_low < invalidation_price:
else:  # bear
    invalidation_price = leg.origin_price + threshold_amount
    if bar_high > invalidation_price:
```
**Result:** ✅ Correct — Bull invalidates on price dropping below LOW origin, Bear invalidates on price rising above HIGH origin

#### Orphaned origin storage (line 1332)
```python
origin_tuple = (leg.origin_price, leg.origin_index)
```
After #197 fix:
- Bull legs store LOW as orphaned origin (where upward moves started)
- Bear legs store HIGH as orphaned origin (where downward moves started)

**Result:** ✅ Correct — Orphaned origins now at correct price levels

### Test Coverage

The following tests verify the invariants:
- `tests/test_issue_195_inverted_temporal_order.py` — Temporal ordering
- `tests/test_issue_192_bar_index_mismatch.py` — Pivot extension
- `tests/test_issue_193_pivot_mismatch.py` — Pending pivot handling
- `tests/test_issue_194_dominated_leg_skip.py` — Dominated leg pruning
- `tests/test_issue_192_real_data.py` — Real data validation

### Verdict

**All semantics correctly enforced.** Every audited location follows the correct invariants. The test suite covers the key scenarios.

---

## Recommendations

### Keep Current Design

1. **Type classification** — Essential for temporal ordering, correctly implemented
2. **Explicit direction + semantic fields** — Better debuggability than symmetric alternatives
3. **Semantic consistency** — Now correct after #197

### No Refactoring Needed

The bug cascade was caused by **terminology confusion in implementation**, not architectural flaws. The #197 fix addressed the root cause. Further abstraction would:
- Add complexity without reducing bug surface
- Make debugging harder
- Risk introducing new bugs during migration

### Risk Analysis

If symmetric refactoring were pursued:
- **Migration risk:** High — Every leg creation/read site needs updating
- **Benefit:** Marginal — Same bugs could occur with different field names
- **Cost:** ~2-3 days of engineering + regression testing

**Recommendation:** Do not refactor. The current design with corrected semantics is sound.

---

## Action Items

- [x] Write audit findings to `Docs/Working/arch_audit.md`
- [ ] Close #198 with summary
- [ ] Update `Docs/State/pending_review.md` — reset count

No new GitHub issues warranted. The design is correct.

---

## Appendix: Review Checklist Results

Per `architect_notes.md` Review Checklist:

1. **Symmetric Code Paths** — ✅ Bull/Bear branches perform symmetric operations
2. **Abstraction Adoption** — ✅ Uses ReferenceFrame for coordinate abstraction
3. **Performance Implications** — ✅ O(n log k) maintained, no new O(n²) operations
4. **Direction-Specific Logic** — ✅ Necessary for market semantics, not premature abstraction
5. **Duplicated Logic** — ✅ No excessive duplication
6. **Magic Numbers** — ✅ 0.382 formation/invalidation threshold is documented in config
7. **Core Decisions** — ✅ Aligned with architect_notes.md principles
8. **Known Debt** — No new debt identified

**Overall:** Accepted. Design is sound post-#197.
