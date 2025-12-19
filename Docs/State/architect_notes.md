# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Hierarchical swing model (SwingNode DAG) — replaces S/M/L/XL buckets
- Single incremental algorithm (HierarchicalDetector.process_bar())
- Fibonacci-based structural analysis (not arbitrary thresholds)
- Resolution-agnostic (1m to 1mo)
- SwingConfig centralizes all detection parameters
- Compatibility layer (adapters.py) for gradual migration
- Discretization: structural events, not per-bar tokens
- Calibration-first playback for causal evaluation
- Backend-controlled data boundary for replay (single source of truth)

**Known debt:**
- **HierarchicalDetector performance (#154)** — O(lookback²) per bar. Sub-issues #155 (quick wins) and #156 (algorithmic) created with prescriptive implementation.
- **Legacy detectors still present** — `swing_detector.py`, `incremental_detector.py` to be deleted after migration complete
- `detect_swings()` function (~400 LOC) — monolithic; will be replaced by HierarchicalDetector

**Cleanup tasks (after performance fix):**
- Delete `swing_detector.py` batch detection (keep ReferenceSwing for adapters)
- Delete `incremental_detector.py`
- Delete `scale_calibrator.py`

---

## Current Phase: Performance Optimization

### Active Issue

**#154 — HierarchicalDetector Performance**
- **Status:** Blocked on implementation
- **Sub-issues:** #155 (Quick wins), #156 (Algorithmic)
- **Document:** `Docs/Working/swing_detection_rewrite_performance_plan.md`

### Problem

| Dataset | Target | Actual | Gap |
|---------|--------|--------|-----|
| 1K bars | <1s | 8.2s | ~10x |
| 6M bars | <60s | N/A | ~1000x |

Root cause: O(lookback²) per bar with expensive inner operations.

### Solution Plan

**Phase 1 (#155):** Quick wins — caching, inlining, lazy checks
- Expected improvement: ~40%

**Phase 2 (#156):** Algorithmic — dominant extrema tracking
- Expected improvement: ~95% from baseline

---

## Recently Reviewed (Dec 18)

### Swing Detection Rewrite — ALL ACCEPTED

| Issue | Feature | Verdict |
|-------|---------|---------|
| #142 | SwingConfig dataclass | Accepted |
| #143 | SwingNode dataclass | Accepted |
| #144 | SwingEvent types | Accepted |
| #145 | ReferenceFrame tolerance checks | Accepted |
| #146 | Ground truth annotator removal | Accepted |
| #147 | HierarchicalDetector core | Accepted |
| #148 | Calibration helpers | Accepted |
| #149 | ReferenceSwing compatibility adapter | Accepted |
| #150 | Replay router update | Accepted |
| #151 | Discretizer SwingNode support | Accepted |

**Assessment:**

✅ **Architecture:** Implementation follows spec. ReferenceFrame is now central. SwingConfig centralizes parameters. Hierarchical model correctly replaces S/M/L/XL.

✅ **Code Quality:** Proper docstrings, type hints, examples throughout. Clean separation of concerns.

✅ **Tests:** 691 tests pass. Coverage includes unit tests for all new components.

✅ **Compatibility:** Adapter layer allows gradual migration. Legacy detect_swings_compat() works.

⚠️ **Performance:** Algorithm is correct but O(lookback²) per bar. Issue #154 with prescriptive sub-issues created.

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| HierarchicalDetector | Active (performance issue) | #155, #156 pending |
| SwingConfig | Complete | Centralizes all parameters |
| SwingNode | Complete | DAG hierarchy model |
| ReferenceFrame | Complete | Central coordinate abstraction |
| Compatibility Adapter | Complete | SwingNode ↔ ReferenceSwing |
| Replay View | Complete | Uses HierarchicalDetector |
| Discretization | Complete | Accepts SwingNode via adapter |
| Legacy Detectors | Deprecated | To be deleted after cleanup |
| Test Suite | Healthy | 691 tests passing |
| Documentation | Current | Both guides updated |

---

## Next Steps

**Parallel Execution:** No (sequential required)

1. As Engineer, implement #155 (quick wins) — prescriptive tasks in issue
2. Benchmark and verify ~40% improvement
3. As Engineer, implement #156 (algorithmic) — prescriptive tasks in issue
4. Benchmark and verify target met (1K bars < 1s)
5. After performance target met, proceed with legacy cleanup

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `developer_guide.md` | Current | Hierarchy model documented |
| `user_guide.md` | Current | Replay View uses HierarchicalDetector |
| `CLAUDE.md` | Current | - |
| `swing_detection_rewrite_performance_plan.md` | Current | Pushed to GitHub |

---

## Architecture Principles

- **Hierarchical model:** Swings form a DAG, not discrete buckets
- **Single algorithm:** process_bar() for both calibration and playback
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance target:** <60s for 6M bars (currently blocked)
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)
- **Backend-controlled boundaries:** Backend owns data visibility

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
| Dec 18 | #142-#151 — Swing Detection Rewrite (10 issues) | All Accepted; #154 performance issue identified |
| Dec 18 | Swing Detection Rewrite Spec | Approved; implementation plan created |
| Dec 18 | #138, #140 (Phase 1) — Endpoint optimization, pre-formation protection | All Accepted |
| Dec 18 | #130-#136 — Navigation, stats, API modularization | All Accepted |
| Dec 17 | #116-#128 — Feedback, incremental detection, usability | All Accepted |
| Dec 17 | #99-#111 — Replay View completion | All Accepted, Epic #99 closed |
| Dec 16 | #78-#89 — Discretization, Replay View | All Accepted |
| Dec 16 | #68-#77 — Phase 3 + Architecture Overhaul | All Accepted |
