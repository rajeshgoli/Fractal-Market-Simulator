# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## 2025-12-18: Swing Detection Rewrite (Product → Architect)

**This is the single biggest blocker for the project.** Clean swings are prerequisite for discretization. Without this, we cannot proceed.

**The Problem:**

1. **Rules not enforced**: Pre-formation requires absolute checks (no tolerance), but code uses tolerance. Configurable parameters are scattered as magic numbers - impossible to extract and verify.

2. **S/M/L/XL is now a liability**: Was useful for bootstrapping, now causes bugs. Swings are hierarchical (7-15 nested levels in practice), not 4 discrete buckets. No parent-child links means no cascading invalidation.

3. **Dual code paths diverge**: Batch detector (calibration) and incremental detector (playback) produce different results for same data. Lookahead bugs. Bar index mismatches.

4. **Discretization blocked**: Currently events exceed bars. Discretizing would *increase* data 2-5x. Clean swings required first.

**Proposal:**

- Single incremental algorithm (calibration = loop over same algo)
- Hierarchical tree/DAG model with cascading invalidation
- Unified reference frame (0/1/2) - eliminate bull/bear branching in core logic
- `SwingConfig` dataclass for all configurable parameters

**Spec:** `Docs/Working/swing_detection_rewrite_spec.md`

**Rules:** `Docs/Reference/valid_swings.md` (canonical source of truth)

**Questions for Architect:**
1. Performance: incremental calibration over 10K+ bars acceptable?
2. DAG complexity: multiple parents per swing - does this complicate invalidation?
3. State serialization format for detector state?
4. Migration path for existing ground truth annotations?

**Priority:** Critical - fundamental architecture issue blocking project progress.
