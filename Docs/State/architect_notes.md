# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Hierarchical swing model (SwingNode DAG) — replaces S/M/L/XL buckets
- Single incremental algorithm (HierarchicalDetector.process_bar())
- Fibonacci-based structural analysis (0.382 formation/invalidation)
- Resolution-agnostic (1m to 1mo)
- SwingConfig centralizes all detection parameters
- Compatibility layer (adapters.py) for gradual migration
- Discretization: structural events, not per-bar tokens
- Calibration-first playback for causal evaluation
- Backend-controlled data boundary for replay (single source of truth)
- **DAG/Reference separation:** Structural tracking vs semantic filtering
- **Rules by construction:** Temporal ordering from bar relationships (Type 1/2/3)
- **Sibling detection:** Orphaned origins with 10% pruning

**Known debt:**
- `MULTI_TF_LOOKBACKS` constants (12, 6, 5 bars) — documented but not derived from domain primitives
- #176 — `get_windowed_swings` missing Reference layer during calibration (fix after validation)
- #177 — Minor: missing `invalidated_at_bar` field, AppState/cache duplication

---

## Current Phase: DAG Visualization + Validation

### DAG Algorithm — COMPLETE

**Performance target achieved:** 4.06s for 10K bars (target was <5s)

| Issue | Feature | Status |
|-------|---------|--------|
| #158 | DAG-based swing detection (O(n log k)) | ✅ Complete |
| #159 | Reference layer for filtering/invalidation | ✅ Complete |
| #160 | Wire ReferenceLayer into API pipeline | ✅ Complete |
| #163 | Sibling swing detection (orphaned origins) | ✅ Complete |
| #164 | Remove legacy candidate lists | ✅ Complete |
| #165 | Simplify Reference Layer | ✅ Complete |
| #166 | Redesign calibration UI (tree navigation) | ✅ Complete |
| #174 | Leg→swing invalidation propagation | ✅ Complete |
| #175 | Wire Reference layer into calibrate()/advance() | ✅ Complete |

### Next: DAG Visualization Mode

**Epic #167 — Visual validation tool for DAG algorithm**

Watch the algorithm "think" in real-time to validate detection behavior before proceeding with further development.

| Issue | Feature | Status |
|-------|---------|--------|
| #168 | Add leg lifecycle events to HierarchicalDetector | Open |
| #169 | Add DAG state API endpoint | Open |
| #170 | Add linger toggle to playback controls | Open |
| #171 | Create DAG state panel | Open |
| #172 | Add leg visualization on charts | Open |

**Spec:** `Docs/Working/DAG_visualization_spec.md`
**Estimate:** 3-5 days MVP

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| HierarchicalDetector | **Complete** | O(n log k), 4.06s for 10K bars |
| SwingConfig | Complete | Centralizes all parameters |
| SwingNode | Complete | DAG hierarchy model |
| ReferenceFrame | Complete | Central coordinate abstraction |
| ReferenceLayer | Complete | Tolerance/completion rules |
| Sibling Detection | Complete | Orphaned origins + 10% pruning |
| Compatibility Adapter | Complete | SwingNode ↔ ReferenceSwing |
| Replay View | Complete | Tree-based UI, forward playback |
| Discretization | Complete | Accepts SwingNode via adapter |
| V2 API Schemas | Complete | HierarchicalSwingResponse, etc. |
| Legacy Detectors | Deleted | #153 completed cleanup |
| Test Suite | Healthy | 587 tests passing |
| Documentation | Current | Both guides updated |

---

## Pending Validation

Before proceeding with new features:

1. **Manual validation** — Use Replay View on real data to verify swing detection quality
2. **Compare L1-L7** — Validate against `Docs/Reference/valid_swings.md` examples
3. **Fix #176** — After validation, wire Reference layer into `get_windowed_swings`

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `developer_guide.md` | Current | Reference layer, sibling detection documented |
| `user_guide.md` | Current | Tree-based UI, calibration report documented |
| `CLAUDE.md` | Current | - |

---

## Architecture Principles

- **Hierarchical model:** Swings form a DAG, not discrete buckets
- **Single algorithm:** process_bar() for both calibration and playback
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance target:** <5s for 10K bars ✅ ACHIEVED (4.06s)
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)
- **Backend-controlled boundaries:** Backend owns data visibility
- **DAG/Reference separation:** DAG tracks structural extremas; Reference layer defines "good reference" semantics
- **Rules by construction:** Temporal ordering enforced by bar relationships, not post-hoc filtering

---

## Review Checklist

### Must Check (Every Review)

1. **Symmetric Code Paths**
   - If `if direction == 'bull':` exists, verify both branches do symmetric operations
   - Red flag: bull checks `highs` but bear checks `lows` (or vice versa)

2. **Abstraction Adoption**
   - Does new code use existing abstractions (e.g., `ReferenceFrame`) or reinvent them?

3. **Performance Implications**
   - Does new code add O(n²) operations?
   - Are there repeated sorts or scans that could be cached?

4. **Direction-Specific Logic** (swing_analysis only)
   - Any new `if swing.is_bull` or `if direction ==`?
   - Can it use coordinate-based logic instead?

### Also Check

5. **Duplicated Logic** — >50 lines of parallel code should be unified
6. **Magic Numbers** — New thresholds need: what it represents, why this value
7. **Core Decisions** — Aligned with list above?
8. **Known Debt** — Add new debt, remove resolved debt

### Outcomes

- **Accept** — All checks pass
- **Accept with Notes** — Minor issues tracked in Known debt
- **Requires Follow-up** — Create GitHub issue before accepting
- **Blocked** — Critical issue, must fix first

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 19 | #158-#175 — DAG algorithm rewrite + Reference layer (9 issues) | All Accepted |
| Dec 19 | #152, #153, #155, #157 — Performance optimization + cleanup | All Accepted |
| Dec 18 | #142-#151 — Swing Detection Rewrite (10 issues) | All Accepted; #154 performance issue identified |
| Dec 18 | Swing Detection Rewrite Spec | Approved; implementation plan created |
| Dec 18 | #138, #140 (Phase 1) — Endpoint optimization, pre-formation protection | All Accepted |
| Dec 18 | #130-#136 — Navigation, stats, API modularization | All Accepted |
| Dec 17 | #116-#128 — Feedback, incremental detection, usability | All Accepted |
| Dec 17 | #99-#111 — Replay View completion | All Accepted, Epic #99 closed |
| Dec 16 | #78-#89 — Discretization, Replay View | All Accepted |
| Dec 16 | #68-#77 — Phase 3 + Architecture Overhaul | All Accepted |
