# Product Direction

**Last Updated:** December 19, 2025
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

The system is blocked on performance — current algorithm takes >80s for 10K bars, making 100K window datasets unusable in the frontend. A fundamental algorithm rewrite is in progress.

---

## P0: DAG-Based Swing Detection (#158)

**Status:** Spec approved. Ready for engineering.

### Problem

Current `HierarchicalDetector` is O(n × k³):
- >80s for 10K bars
- 100K window doesn't load in frontend
- 6M bar datasets unworkable

### Solution

Replace with DAG-based streaming algorithm:
- O(n log k) complexity
- Rules enforced by construction (temporal ordering from bar relationships)
- Target: <5s for 10K bars

### Key Design Elements

| Element | Approach |
|---------|----------|
| Bar classification | Type 1 (inside), Type 2-Bull/Bear, Type 3 (outside) |
| Temporal ordering | By construction from bar relationships |
| Formation | 38.2% retracement threshold |
| Invalidation | 0.382 × range beyond defended pivot |
| Staleness | 2x range movement without change |
| Parent-child | By pivot derivation, not range containment |

### Spec

- `Docs/Working/DAG_spec.md`
- `Docs/Working/Performance_question.md`

---

## P1: Reference Layer (#159)

**Status:** Issue filed. Depends on #158.

### Problem

DAG tracks ALL structural extremas with uniform 0.382 invalidation. But valid trading references require:
- Separation filtering (not every extrema is useful)
- Differentiated invalidation (big swings get tolerance, small swings don't)

### Rules to Implement

From `Docs/Reference/valid_swings.md`:

**Separation (Rule 4):**
- Self-separation: Origin only valid if no better candidate within 0.1 × range
- Parent-child: Child's extrema must be 0.1 × parent range from parent/sibling extrema

**Invalidation (Rule 2.2):**

| Swing Size | Touch | Close |
|------------|-------|-------|
| Big (top 10% by range) | 0.15 × range | 0.10 × range |
| Small | 0 tolerance | 0 tolerance |

---

## Valid Swings That Must Be Detected

From `Docs/Reference/valid_swings.md` — ES as of Dec 18, 2025:

| Label | Structure | Description |
|-------|-----------|-------------|
| **L1** | 6166 → 4832 | Monthly/yearly swing (Jan-Apr 2025) |
| **L2** | 5837 → 4832 | Nested impulsive swing (April) |
| **L3** | 6955 → 6524 | Oct-Nov swing from ATH |
| **L4** | 6896 → 6524 | Mid-Nov high, same defended pivot as L5 |
| **L5** | 6790 → 6524 | Nov 17/20 high, sibling of L4 |
| **L6** | 6929 → 6771 | Current weekly swing (Dec) |
| **L7** | 6882 → 6770 | Daily swing |
| **Bear ref** | 6815 → 6828 | Active bear reference |

**Validation:** After #158 and #159, run detection on ES data and verify all these swings appear with correct parent-child relationships.

---

## Why This Is Highest Leverage

Performance blocks everything:
- Can't validate detection quality if frontend won't load
- Can't iterate on Reference layer rules without seeing results
- Can't use Replay View for observation sessions

Once #158 ships:
- Frontend loads 100K windows
- Detection output visible for validation
- #159 can refine filtering/invalidation semantics

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Pending #158 |
| 100K window loads in frontend | Pending #158 |
| Valid swings (L1-L7) detected | Pending #158 |
| Separation filtering applied | Pending #159 |
| Invalidation rules per swing size | Pending #159 |
| Parent-child relationships correct | Pending #158 |

---

## Checkpoint Trigger

**Invoke Product when:**
- #158 complete — validate detection output against valid_swings.md
- Performance targets met or blocked
- #159 ready for validation — verify separation/invalidation behavior
- Unexpected detection behavior observed in Replay View

---

## Previous Phase (Archived)

Ground truth annotator workflow and annotation sessions (Dec 15-17) superseded by hierarchical swing detection rewrite. Legacy swing detector code deleted (#153).

Historical context preserved in:
- `Docs/Archive/` — Previous product direction versions
- `Docs/Reference/interview_notes.md` — User feedback from annotation sessions
