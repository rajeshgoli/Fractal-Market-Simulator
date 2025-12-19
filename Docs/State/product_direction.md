# Product Direction

**Last Updated:** December 19, 2025
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

Performance target achieved (#158). Reference layer complete (#159). Now blocked on **sibling swing detection** — swings with same 0 but different 1s are not being captured.

---

## P0: DAG Visualization Mode (NEW)

**Status:** Requirements captured. Awaiting Architect feasibility assessment.

### Why This First

User insight: "Easier to iterate visually than abstractly." Before implementing #163 (sibling detection), we need confidence that the current DAG behavior is correct. Watching it build in real-time surfaces subtle bugs and validates structural decisions faster than inferring from final output.

### Scope

Temporary validation tool — remove once algorithm is rock solid.

- Two charts (macro + micro zoom)
- State panel showing DAG internals (orphaned 1s, active legs)
- Linger events: Leg created, Leg pruned, Leg invalidated
- Reuse existing Replay View infrastructure

### Next Step

Architect answers feasibility questions in `Docs/Comms/questions.md`, then Engineering implements.

---

## P1: Sibling Swing Detection (#163)

**Status:** Spec approved. Ready for engineering after DAG visualization enables validation.

### Problem

The DAG algorithm prunes legs when invalidated, losing their 1 as a candidate for larger swings. This prevents detection of sibling swings that share a defended 0.

**Example (L1/L2):**
- Bull leg forms: 0=5525, 1=5837
- Price drops below 5525 - 0.382×312 ≈ 5406
- Leg is **invalidated and pruned** — 1=5837 is lost
- Price continues to 4832, reverses
- L2 (1=5837, 0=4832) **cannot form** because 5837 isn't tracked

**Swings affected:**
- L2 (1=5837, 0=4832) — shares 0 with L1
- L4, L5 (1=6896/6790, 0=6524) — share 0 with L3
- L7 (1=6882, 0=6770) — 0 is 1 point from L6's 0

### Solution

Preserve invalidated 1s as orphaned candidates. Prune aggressively at each bar using **10% rule**:

1. On each bar, current low is working 0
2. For all invalidated 1s: if two are within 10% of the larger range, prune the smaller
3. As 0 extends, threshold grows, naturally eliminating noise
4. Only scale-appropriate structure survives

**Trace through L2:**

| Working 0 | Range (from 5837) | 10% threshold | 5763 survives? |
|-----------|-------------------|---------------|----------------|
| 5500 | 337 | 33.7 | Yes (74 > 33.7) |
| 5000 | 837 | 83.7 | No (74 < 83.7) — pruned |
| 4832 | 1005 | — | Only 5837 remains |

**Recursive property:** Small bull legs can preserve their noise (10% of small range is small). When invalidated, their nested 1s join the larger pool and get pruned by the larger threshold. Fractal structure emerges naturally.

### Key Design Elements

| Element | Approach |
|---------|----------|
| Orphaned origins | Flat list per direction, not hierarchical |
| Pruning trigger | Every bar, relative to current working 0 |
| Threshold | 10% of range from 1 to working 0 |
| Separation at formation | **None** — DAG pruning already ensures 10% separation |
| Complexity | O(invalidated origins) per bar, stays sparse |

---

## Completed: DAG-Based Swing Detection (#158)

**Status:** Complete. 4.06s for 10K bars.

Replaced O(n × k³) algorithm with O(n log k) DAG-based streaming approach. Performance target met.

---

## Completed: Reference Layer (#159)

**Status:** Complete. 580 tests passing.

Implemented separation filtering and size-differentiated invalidation thresholds per Rule 2.2.

**Issue discovered during validation:** Current separation check applies to BOTH 0 and 1, but Rule 4.1 only requires 1 separation. Further refinement: separation check can be removed entirely since DAG pruning already ensures 10% separation. See #163.

---

## Valid Swings That Must Be Detected

From `Docs/Reference/valid_swings.md` — ES as of Dec 18, 2025:

| Label | Structure | Current Status | After #163 |
|-------|-----------|----------------|------------|
| **L1** | 1=6166, 0=4832 | Detected | Detected |
| **L2** | 1=5837, 0=4832 | **Missing** (1 pruned) | Detected |
| **L3** | 1=6955, 0=6524 | Detected | Detected |
| **L4** | 1=6896, 0=6524 | **Missing** (0 separation) | Detected |
| **L5** | 1=6790, 0=6524 | **Missing** (0 separation) | Detected |
| **L6** | 1=6929, 0=6771 | Detected | Detected |
| **L7** | 1=6882, 0=6770 | **Missing** (0 separation) | Detected |

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | **Done** (#158) |
| 100K window loads in frontend | **Done** (#158) |
| Valid swings (L1-L7) detected | Pending #163 |
| Sibling swings with same 0 detected | Pending #163 |
| Separation check removed (DAG prunes) | Pending #163 |
| Parent-child relationships correct | **Done** (#158) |

---

## Checkpoint Trigger

**Invoke Product when:**
- DAG Visualization complete — ready to validate algorithm behavior
- #163 complete — validate L1-L7 all detected
- Unexpected detection behavior observed during visual validation

---

## Previous Phase (Archived)

- #158 DAG-based swing detection — Complete
- #159 Reference layer — Complete
- Ground truth annotator workflow (Dec 15-17) — Superseded
