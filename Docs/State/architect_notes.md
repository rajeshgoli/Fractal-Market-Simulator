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

**Known debt:**
- `MULTI_TF_LOOKBACKS` constants (12, 6, 5 bars) — documented but not derived from domain primitives. Consider making configurable via SwingConfig if tuning becomes necessary.

---

## Current Phase: DAG Algorithm Rewrite

### Performance Issue — NOT Resolved

**#154 — HierarchicalDetector Performance** — Optimizations insufficient

| Phase | Issue | Status | Result |
|-------|-------|--------|--------|
| Phase 1 | #155 — Quick wins (caching, inlining, lazy checks) | Closed | Minor improvement |
| Phase 2 | #156 — Dominant extrema tracking | Closed (not needed) | Superseded by #157 |
| Phase 3 | #157 — Multi-TF candidate generation | Closed | Candidate reduction, but core O(k³) remains |

**Actual state:** >80s for 10K bars. 100K window doesn't load in frontend. Core algorithm is O(n × k³) due to candidate pair generation and pre-formation checks. Multi-TF optimization reduced candidates but didn't address fundamental complexity.

### Active Work: DAG-Based Algorithm

**#158 — Implement DAG-based swing detection algorithm**

Replace O(n × k³) algorithm with O(n log k) DAG-based streaming approach.

**Core insight:** Instead of generating O(k²) candidate pairs and filtering by rules, build a structure where rules are enforced by construction through temporal ordering.

**Key elements:**
- Bar type classification (Type 1/2-Bull/2-Bear/3)
- Temporal ordering by construction (not H/L within single bar)
- Simultaneous bull/bear leg tracking
- 0.382 decisive invalidation + 2x staleness pruning
- Parent-child by pivot derivation (not range containment)
- DAG/Reference layer separation

**Spec:** `Docs/Working/DAG_spec.md`
**Target:** <5s for 10K bars, 100K window loads in frontend

---

## Recently Reviewed (Dec 19)

### Performance + Cleanup — ALL ACCEPTED

| Issue | Feature | Verdict |
|-------|---------|---------|
| #152 | V2 API schemas for hierarchical swings | Accepted |
| #153 | Old swing detection code removal | Accepted |
| #155 | Phase 1 performance: caching and inlining | Accepted |
| #157 | Phase 3 performance: multi-TF candidate generation | Accepted |
| #156 | Phase 2: Dominant extrema (not needed) | Closed — superseded by #157 |

**Assessment:**

✅ **Architecture:** Multi-TF approach is cleaner than dominant extrema. Reuses existing BarAggregator. Hybrid fallback ensures correctness for short datasets.

✅ **Code Quality:** Symmetric bull/bear logic. ReferenceFrame for coordinate abstraction. Caching properly invalidated.

✅ **Tests:** 551 tests pass. Performance tests verify targets (<5s for 1K bars).

✅ **Cleanup Complete:** Legacy detectors deleted. ReferenceSwing preserved in adapters.py.

⚠️ **Minor:** MULTI_TF_LOOKBACKS magic numbers documented but not configurable. Acceptable for now — tracked in Known debt.

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| HierarchicalDetector | **Blocked** | O(n×k³) — >80s for 10K bars. #158 in progress |
| SwingConfig | Complete | Centralizes all parameters |
| SwingNode | Complete | DAG hierarchy model |
| ReferenceFrame | Complete | Central coordinate abstraction |
| Compatibility Adapter | Complete | SwingNode ↔ ReferenceSwing |
| Replay View | Blocked | Can't load 100K window due to detector performance |
| Discretization | Complete | Accepts SwingNode via adapter |
| V2 API Schemas | Complete | HierarchicalSwingResponse, etc. |
| Legacy Detectors | Deleted | #153 completed cleanup |
| Test Suite | Healthy | 551 tests passing |
| Documentation | Current | Both guides updated |

---

## Next Steps

**Active: #158 — DAG-based swing detection**

1. Implement DAG algorithm as drop-in replacement for HierarchicalDetector
2. Benchmark on 10K+ bar datasets (target: <5s)
3. Validate output correctness through manual inspection
4. Refine pruning rules based on empirical results

**After #158:**
- End-to-end validation against real trading decisions
- GAN training data generation using discretization logs

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `developer_guide.md` | Current | Multi-TF optimization documented |
| `user_guide.md` | Current | Replay View using hierarchical detector |
| `CLAUDE.md` | Current | - |

---

## Architecture Principles

- **Hierarchical model:** Swings form a DAG, not discrete buckets
- **Single algorithm:** process_bar() for both calibration and playback
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance target:** <5s for 10K bars, <60s for 6M bars (NOT YET MET)
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
| Dec 19 | DAG-based algorithm spec review | Approved → #158 created |
| Dec 19 | #152, #153, #155, #157 — Performance optimization + cleanup | All Accepted (but performance still unworkable) |
| Dec 18 | #142-#151 — Swing Detection Rewrite (10 issues) | All Accepted; #154 performance issue identified |
| Dec 18 | Swing Detection Rewrite Spec | Approved; implementation plan created |
| Dec 18 | #138, #140 (Phase 1) — Endpoint optimization, pre-formation protection | All Accepted |
| Dec 18 | #130-#136 — Navigation, stats, API modularization | All Accepted |
| Dec 17 | #116-#128 — Feedback, incremental detection, usability | All Accepted |
| Dec 17 | #99-#111 — Replay View completion | All Accepted, Epic #99 closed |
| Dec 16 | #78-#89 — Discretization, Replay View | All Accepted |
| Dec 16 | #68-#77 — Phase 3 + Architecture Overhaul | All Accepted |
