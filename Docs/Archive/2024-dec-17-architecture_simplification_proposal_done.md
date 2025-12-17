# Architecture Simplification Proposal

**Date:** December 17, 2025
**Status:** Draft
**Author:** Architecture Review

---

## Problem Statement

This codebase serves a singular mission: build a trusted swing detection and market simulation system to support a trading edge. The quality bar is absolute—one edge case mishandled and the edge disappears.

After reviewing the repository, I observe:

1. **Duplicate implementations**: Two reference detector modules (`bull_reference_detector.py` at 407 LOC and `reference_detector.py` at 575 LOC) coexist. The latter was designed to unify both, but the former is still actively imported.

2. **Monolithic functions**: `detect_swings()` is 333 lines of sequential filtering logic without a clear pipeline abstraction. This makes it hard to reason about filter ordering, test individual stages, or extend with new filters.

3. **Large API surface**: `api.py` at 2044 lines handles annotation, review, comparison, discretization, replay, and static file serving—all in one file.

4. **Accumulated archives**: ~1.3MB of historical proposals, drafts, and role-based artifacts spread across `.archive/` and `Docs/Archive/`. These served their purpose during development but now add cognitive load during navigation.

5. **Completed work still in "Working"**: `Docs/Working/replay_view_spec.md` and `replay_view_architecture.md` describe implemented features. They should move to Archive.

6. **Test-to-code ratio is healthy** (30K tests / 11K source ≈ 2.7x) but the test structure mirrors source structure rather than behavioral contracts, making refactors expensive.

**The core tension:** The codebase has evolved through rapid iteration (as it should during exploration), but now needs consolidation before the next phase (Hypothesis Baseline testing). Technical debt compounds faster than you'd expect when validating a trading system—any uncertainty about what the code actually does erodes trust.

---

## Key Questions

Before proposing changes, I need to answer:

| # | Question | Why It Matters |
|---|----------|----------------|
| Q1 | What is the minimum viable surface area for hypothesis testing? | Deletions should preserve only what's needed for the next milestone |
| Q2 | Are `bull_reference_detector.py` and `reference_detector.py` both still needed? | Eliminating duplication reduces maintenance burden |
| Q3 | Can `detect_swings()` be decomposed without changing behavior? | Testability and extensibility depend on this |
| Q4 | What in the archive directories is still referenced? | Safe deletion requires knowing dependencies |
| Q5 | Is the frontend architecture (React Replay View) complete, or evolving? | Determines whether to invest in frontend simplification |
| Q6 | How coupled is the test suite to internal implementations? | Affects refactoring risk |

---

## Panel of Advisors

I consult a panel of thinkers well-suited to these questions:

### Fred Brooks (Software Engineering)
*Assigned to: Q1, Q3*

> "The hardest single part of building a software system is deciding precisely what to build. No other part of the conceptual work is as difficult as establishing the detailed technical requirements."

**Advice for this repo:**
- Your North Star is swing detection quality, not feature breadth. Every module should answer: "Does this directly improve detection accuracy or my confidence in it?"
- The 333-line `detect_swings()` function is what Brooks calls "conceptual integrity violated through accretion." Each filter was added to solve a specific problem, but the function no longer expresses a coherent concept.
- **Prescription:** Extract a `FilterPipeline` pattern where each stage is named, testable, and orderable. The function becomes documentation of the algorithm.

### Rich Hickey (Simplicity)
*Assigned to: Q2, Q4*

> "Simplicity is a prerequisite for reliability. Complecting things together leads to software that you can't reason about."

**Advice for this repo:**
- Two reference detectors is complected. You have `bull_reference_detector.py` defining `Bar`, `BullReferenceSwing`, `BearReferenceSwing`, and `DetectorConfig`—then `reference_detector.py` imports those and wraps them in `DirectionalReferenceDetector`. But `api.py` imports from `bull_reference_detector` directly. Pick one.
- Archives are "incidental complexity"—they don't serve the running system. If something isn't imported, it doesn't exist to the code. Move it out of the repo entirely, or delete it.
- **Prescription:** `reference_detector.py` should own the abstraction. Move the data classes there. Delete the original file or reduce it to a backward-compatibility shim that re-exports.

### Kent Beck (Testing Philosophy)
*Assigned to: Q6*

> "I get paid for code that works, not for tests. Test until fear is transformed into boredom."

**Advice for this repo:**
- 30K lines of tests for 11K of source is impressive coverage, but are you testing behavior or implementation? If refactoring `detect_swings()` requires changing 50 tests, the tests are coupled to structure.
- **Prescription:** Identify the "contract tests"—tests that specify external behavior—and label them. During refactors, those must pass unchanged. Implementation tests can be rewritten with the implementation.

### Edward Tufte (Information Design)
*Assigned to: Q5*

> "Clutter and confusion are failures of design, not attributes of information."

**Advice for this repo:**
- The React frontend (1800 LOC) is compact and focused. `Replay.tsx` at 307 lines handles state, layout, and interaction—but it's comprehensible.
- The API serving it (`api.py`) is not. 2044 lines mixing REST endpoints, business logic, and HTML template responses is "chartjunk" in code form.
- **Prescription:** Split API into routers by concern: `annotation_routes.py`, `review_routes.py`, `discretization_routes.py`, `replay_routes.py`. Each under 500 lines.

### Nassim Taleb (Antifragility)
*Assigned to: Q1 (risk perspective)*

> "Antifragility is beyond resilience or robustness. The resilient resists shocks and stays the same; the antifragile gets better."

**Advice for this repo:**
- Your system needs to be antifragile to market regime changes. That means the core algorithm (swing detection) must be easily adjustable without cascading breakage.
- Monolithic functions are fragile—change one thing, break five others.
- Archives are ballast. They add weight without adding strength.
- **Prescription:** Prune aggressively. What survives should be load-bearing.

---

## Implications for This Repository

Translating the panel's advice:

| Observation | Action | Rationale |
|-------------|--------|-----------|
| Duplicate detectors | **Merge into `reference_detector.py`**, re-export from `bull_reference_detector.py` for backward compatibility | Hickey: decomplect |
| Monolithic `detect_swings()` | **Extract `FilterPipeline` class** with named stages | Brooks: conceptual integrity |
| Large `api.py` | **Split into 4-5 router modules** | Tufte: reduce clutter |
| `.archive/` (464KB) | **Delete entirely** | Not imported, not needed |
| `Docs/Archive/Proposals/Discretization/` (19 files, 848KB) | **Delete** | Discretization is implemented |
| `Docs/Working/replay_view_*.md` | **Move to `Docs/Archive/Replay/`** | Work is complete |
| Test coupling | **Identify and label contract tests** | Beck: refactor safely |

---

## Strategy Options

### Option A: Aggressive — Consolidate to React, Remove Legacy Views

**Philosophy:** One frontend framework. The React Replay view works; extend it rather than maintaining parallel HTML files.

**Deletions:**

| File | Lines | Reason |
|------|-------|--------|
| `static/discretization.html` | 1,161 | Replay view shows same events |
| `static/replay.html` | 1,780 | React version exists at `/replay` |
| `static/index.html` | 1,478 | Port to React (see below) |
| `static/review.html` | 2,369 | Port to React (see below) |
| `.archive/` directory | 464KB | Not imported anywhere |
| `Docs/Archive/Proposals/` | 848KB | All implemented |
| `tmp/` directory | - | Junk files |
| `/discretization` route | ~15 | Serves deleted HTML |
| `/replay-legacy` route | ~15 | Serves deleted HTML |

**New React Development:**

Port Ground Truth Annotator + Review Mode to React:
- `frontend/src/pages/Annotate.tsx` — two-click annotation workflow
- `frontend/src/pages/Review.tsx` — FP/FN review workflow
- Shared components: chart, sidebar, keyboard handlers

**Resulting Structure:**
```
src/
├── data/                          # unchanged
├── swing_analysis/                # unchanged
├── discretization/                # unchanged (KEEP backend)
├── ground_truth_annotator/
│   ├── main.py
│   ├── api.py                     # Remove HTML-serving routes only
│   ├── models.py
│   ├── storage.py
│   ├── cascade_controller.py
│   ├── review_controller.py
│   └── comparison_analyzer.py
│   └── static/                    # DELETED (empty or removed)
└── frontend/
    └── src/
        ├── pages/
        │   ├── Replay.tsx         # existing
        │   ├── Annotate.tsx       # NEW (port from index.html)
        │   └── Review.tsx         # NEW (port from review.html)
        └── components/            # shared chart components
```

**Metrics:**
- HTML deleted: 6,788 LOC (4 files)
- Docs/archive deleted: ~1.3MB
- React added: ~2,000-2,500 LOC (estimate for port)
- Net frontend: single framework, ~30% fewer lines

**Risks:**
- React port is real work (~4-8 hours)
- Annotation workflow is more complex than Replay
- Could introduce bugs in working annotation tool

**Risk Controls:**
- Port one page at a time (Annotate first, then Review)
- Keep HTML files until React version is validated
- Feature-flag new routes (`/annotate-v2`) during transition

---

### Option B: Moderate — Remove Redundant Views, Keep Annotator HTML

**Philosophy:** Delete what's clearly redundant. Don't touch working annotation UI.

**Deletions:**

| File | Lines | Reason |
|------|-------|--------|
| `static/discretization.html` | 1,161 | Replay view shows same events |
| `static/replay.html` | 1,780 | React version exists |
| `.archive/` directory | 464KB | Not imported |
| `Docs/Archive/Proposals/` | 848KB | Implemented |
| `tmp/` directory | - | Junk |
| `/discretization` route | ~15 | Serves deleted HTML |
| `/replay-legacy` route | ~15 | Serves deleted HTML |

**Keep:**
- `static/index.html` (1,478 LOC) — working annotator
- `static/review.html` (2,369 LOC) — working review mode
- All backend code unchanged

**Metrics:**
- HTML deleted: 2,941 LOC
- Docs/archive deleted: ~1.3MB
- API routes removed: ~30 lines
- Zero risk to annotation workflow

**Risks:**
- Near-zero — only removing genuinely unused code
- Annotation UI stays as-is (tech debt remains but doesn't block)

**Risk Controls:**
- Run test suite
- Verify `/replay` still works after removing legacy

---

### Option C: Conservative — Archives Only

**Philosophy:** Just clean up documentation cruft.

**Deletions:**

| Target | Size |
|--------|------|
| `.archive/` directory | 464KB |
| `Docs/Archive/Proposals/` | 848KB |
| `tmp/` directory | - |

**Keep:**
- All HTML files
- All source code
- All routes

**Metrics:**
- Source deleted: 0 LOC
- Docs deleted: ~1.3MB

**Risks:**
- None

---

## Trade-off Analysis

*In the voice of Daniel Kahneman (decision-making rigor):*

> "A reliable way to make people believe in falsehoods is frequent repetition, because familiarity is not easily distinguished from truth."

| Criterion | Option A (React Port) | Option B (Remove Redundant) | Option C (Archives Only) |
|-----------|----------------------|----------------------------|------------------------|
| **Frontend maintenance** | One framework | Two frameworks (React + vanilla) | Two frameworks |
| **Lines deleted** | ~6,800 HTML + 1.3MB docs | ~2,900 HTML + 1.3MB docs | 1.3MB docs only |
| **Time investment** | 4-8 hours | 30-60 minutes | 15 minutes |
| **Risk to annotation** | Medium (port could have bugs) | Zero | Zero |
| **Future velocity** | Best (shared components) | OK | Unchanged |
| **Reversibility** | Git history | Easy | Perfect |

**Key insight:** The annotation workflow (`index.html` + `review.html`) is battle-tested through 15+ annotation sessions. Porting it to React has value (single framework, shared components with Replay), but introduces risk to a working tool during an active data collection phase.

**The question is timing:** React port is the right long-term move, but is now the right time? The Hypothesis Baseline milestone doesn't require annotation UI changes.

---

## Recommendation

**Implement Option B now. Option A is a separate project for after Hypothesis Baseline.**

### Rationale:

1. **Remove clear cruft immediately:** `discretization.html`, `replay.html` (legacy), archives, `tmp/` — all clearly redundant. Zero risk.

2. **Don't touch working annotation UI:** The HTML annotator works. It's not elegant, but it's validated. Rewriting it before Hypothesis Baseline adds risk without enabling the milestone.

3. **React port as dedicated project:** After Hypothesis Baseline, create a focused project to port annotation UI. This gets proper attention rather than being rushed as cleanup.

### Sequencing Plan:

| Phase | Action | Done Criteria |
|-------|--------|---------------|
| **Phase 1 (Now)** | Delete `.archive/` | Directory gone |
| **Phase 1 (Now)** | Delete `Docs/Archive/Proposals/` | All proposal subdirs gone |
| **Phase 1 (Now)** | Delete `tmp/` | Directory gone |
| **Phase 1 (Now)** | Delete `static/discretization.html` | File gone |
| **Phase 1 (Now)** | Delete `static/replay.html` | File gone |
| **Phase 1 (Now)** | Remove `/discretization` route from api.py | Route removed |
| **Phase 1 (Now)** | Remove `/replay-legacy` route from api.py | Route removed |
| **Phase 1 (Now)** | Archive `Docs/Working/replay_view_*.md` | Moved to Archive |
| **Phase 2 (After H-Baseline)** | Port `index.html` to React `Annotate.tsx` | Feature parity |
| **Phase 2 (After H-Baseline)** | Port `review.html` to React `Review.tsx` | Feature parity |
| **Phase 3 (Future)** | Delete remaining HTML files | Single frontend |

### "Done" Criteria for Phase 1:

- [ ] `.archive/` deleted
- [ ] `Docs/Archive/Proposals/` deleted
- [ ] `tmp/` deleted
- [ ] `static/discretization.html` deleted
- [ ] `static/replay.html` deleted
- [ ] `/discretization` and `/replay-legacy` routes removed from `api.py`
- [ ] `Docs/Working/replay_view_*.md` moved to `Docs/Archive/Replay/`
- [ ] Tests pass: `python -m pytest tests/ -v`
- [ ] `/replay` (React) still works
- [ ] `/` (annotator) still works
- [ ] `/review` still works

---

## Appendix: File Inventory

### Files to Delete (Phase 1)

**Directories:**
```
.archive/                              # 464KB - historical role-based artifacts
Docs/Archive/Proposals/                # 848KB - all implemented proposals
tmp/                                   # Junk files
```

**HTML Views (redundant):**
```
src/ground_truth_annotator/static/discretization.html  # 1,161 LOC - Replay subsumes
src/ground_truth_annotator/static/replay.html          # 1,780 LOC - React version exists
```

**API Routes to Remove (in api.py):**
```python
# Lines ~1827-1840: /discretization route
@app.get("/discretization", response_class=HTMLResponse)
async def discretization_page(): ...

# Lines ~1868-1880: /replay-legacy route
@app.get("/replay-legacy", response_class=HTMLResponse)
async def replay_legacy_page(): ...
```

### Files to Archive (Phase 1)

```
Docs/Working/replay_view_spec.md           → Docs/Archive/Replay/
Docs/Working/replay_view_architecture.md   → Docs/Archive/Replay/
```

### Files to Keep (explicitly)

```
src/discretization/                    # Backend module - KEEP
tests/test_discretiz*.py               # Backend tests - KEEP
/api/discretization/* endpoints        # API for Replay view - KEEP
src/ground_truth_annotator/static/index.html   # Working annotator - KEEP (for now)
src/ground_truth_annotator/static/review.html  # Working review - KEEP (for now)
```

### Future Work (Phase 2-3)

```
# React port of annotation UI
frontend/src/pages/Annotate.tsx        # Port from index.html
frontend/src/pages/Review.tsx          # Port from review.html

# Then delete:
src/ground_truth_annotator/static/index.html
src/ground_truth_annotator/static/review.html
```

---

## Ready to Execute?

Phase 1 is purely deletions of unused files and routes. No behavioral changes to working features.

If approved, I'll execute the deletions and verify tests pass.
