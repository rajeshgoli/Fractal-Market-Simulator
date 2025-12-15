# Resolved Questions

---

## Q-2025-12-15-1: Trend-Aware Reference Detection

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 15, 2025

**Context:** User feedback identifies consistent FP pattern — detector emits reference ranges against the prevailing trend direction. At XL and L scales, counter-trend swings are technically valid but contextually noise.

**Questions Asked:**
1. What's the best approach to add trend awareness to the swing detector?
2. Options considered: Trend filter, directional weighting, user-specified bias, scale cascade

**Resolution (Architect):**

**Recommended Approach: Hybrid (Options 1 + 3)**

Add `trend_context` parameter to `detect_swings()`:
```python
def detect_swings(..., trend_context: Literal["auto", "bullish", "bearish", "neutral"] = "neutral"):
```

| Mode | Behavior |
|------|----------|
| `"neutral"` | Current behavior (default), no filtering |
| `"bullish"` | Suppress bear_references |
| `"bearish"` | Suppress bull_references |
| `"auto"` | Calculate trend from price data, apply appropriate filter |

**Trend Calculation (for auto mode):**
- Simple linear regression slope over the window
- Alternative: Compare first-third vs last-third price averages
- O(N) computation, doesn't affect O(N log N) overall

**Implementation Strategy:**
- Apply as post-filter after standard detection
- Don't modify core swing detection or Fibonacci logic
- Optional enhancement: demote rather than remove (multiply size by 0.3)

**Why This Approach:**
1. Minimal invasion: Core algorithm unchanged, filter is additive
2. User control: `neutral` preserves current behavior; users can override
3. Simple trend math: Linear regression is O(N) and statistically robust
4. Testable: New parameter = easy to test both modes
5. Reversible: If trend awareness causes issues, just use `neutral`

**What NOT to Do:**
- Don't add ML-based trend detection (too heavy, hard to debug)
- Don't modify swing point detection logic (risk regression)
- Don't implement scale cascade yet (adds cross-scale coupling; defer)

**Files Affected:**
| File | Change |
|------|--------|
| `src/swing_analysis/swing_detector.py` | Add `trend_context` param, trend calc, post-filter |
| `tests/test_swing_detector.py` | Add trend context tests |

**Alternative Considered:** Directional weighting (counter-trend refs get `size *= 0.3`) - more nuanced but adds complexity. Recommend starting with suppression, can add weighting later if needed.

**Next Step:** Product to confirm approach. If approved, Engineering creates GitHub issue.

---

## Q-2025-12-12-4: P1 UX Fixes for Ground Truth Annotator

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 12, 2025

**Context:** First real annotation session surfaced 4 UX issues blocking quality data collection.

**Questions Asked:**
1. Reference level labels inverted (bull reference shows 0 at top, should be at bottom)
2. FN explanation too slow (requires typing for every FN)
3. Unclear export/save workflow (no feedback on save)
4. Session quality control (no way to mark session as keep vs discard)

**Resolution (Architect):**

All 4 issues scoped and GitHub issues created:

| Issue | Title | Scope | Files |
|-------|-------|-------|-------|
| #46 | Fix inverted Fibonacci reference level labels | Frontend only | `index.html` |
| #47 | Add preset options for FN explanations in Review Mode | Frontend only | `review.html` |
| #48 | Add save confirmation and export button to Annotation UI | Frontend only | `index.html` |
| #49 | Add session quality control (keep/discard) at session end | Backend + Frontend | `models.py`, `api.py`, `review.html` |
| #50 | Preload next annotation window to eliminate 30-40s wait | Backend | `api.py` |

**Complexity Assessment:**
- #46, #48: Small (~20 lines each)
- #47: Small-Medium (~40 lines)
- #49: Medium (~50 lines across 3 files)
- #50: Medium (caching + optional preload threading)

**Root Cause of #50:** `init_app()` re-reads entire CSV on every "Load Next Window" call. Fix: cache DataFrame in memory, optionally preload next window in background thread when user enters Review Mode.

**Parallelism:** Issues #46, #47, #48 can run in parallel (all frontend-only). Issues #49 and #50 require backend changes.

**Next Step:** Engineering to implement #46-#48 in parallel, then #49 and #50.

---

## Q-2025-12-12-3: Review Mode Implementation

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 12, 2025

**Context:** First annotation session showed 2,216 system detections vs 9 user annotations. Pivoting from "volume annotation" to "rule feedback" approach.

**Questions Asked:**
1. Implementation approach: New screen vs extending existing UI?
2. FP sampling strategy: Random 10-20 or stratified by scale/confidence?
3. Feedback schema: How to extend annotation storage for comments/categories?
4. Export format: JSON? CSV? What structure is most useful?

**Resolution (Architect):**

**Q1: Implementation approach**
**Answer:** Separate `review.html` page.
- `index.html` is already 1,279 lines with complex state management
- Review Mode has distinct workflow (linear progression, not free-form annotation)
- Easier to test and maintain independently
- Navigation: `/review?session_id=X` after cascade completes

**Q2: FP sampling strategy**
**Answer:** Stratified by scale, 2-5 samples per scale, capped at 20 total.
- Ensures coverage across all scales where miscalibration may differ
- Prevents S-scale domination of sample (where most FPs live)
- Still manageable review time (~5 min)

**Q3: Feedback schema**
**Answer:** New `SwingFeedback` and `ReviewSession` dataclasses.
- Stored in separate `{session_id}_review.json` files
- Keeps annotation data clean (no schema changes to existing models)
- Enables re-review without affecting annotations

**Q4: Export format**
**Answer:** JSON primary with nested structure. CSV optional for spreadsheet analysis.
- JSON preserves relationships for programmatic analysis
- Includes summary stats + per-swing detail
- CSV export available for quick viewing

**Full design:** See `Docs/State/architect_notes.md` for complete design including:
- 3-phase workflow (matches → FP sample → FN feedback)
- Data model extensions
- API endpoints
- Implementation order
- P1 session flow improvements (random windows, continuation)

**Next Step:** Engineering to create GitHub issues and implement per the design.

---

## Q-2025-12-12-2: Ground Truth Annotator UX Polish

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 12, 2025

**Context:** MVP delivered and validated. "UX is beautiful" per dogfood. Four refinements identified before heavy annotation sessions.

**Questions Asked:**
1. Snap-to-extrema - Both clicks auto-select best high/low within scale-aware tolerance
2. Fib preview - Show 0, 0.382, 1, 2 horizontal lines on pending annotation
3. XL aspect ratio - Maintain aspect ratio when reference panel shrinks
4. Non-blocking confirmation - Move modal to side panel, add hotkeys, keep charts visible

**Resolution (Architect):**

**Architecture Decision:** All four refinements are **frontend-only** changes. No backend API modifications required.

**Rationale:**
- Scale information already available via `/api/cascade/state`
- Bar data already available via `/api/bars`
- All calculations (snapping, fib levels) are simple client-side arithmetic
- No new data persistence requirements

**Module Design:**

| Issue | Purpose | Complexity | File |
|-------|---------|------------|------|
| #32 | Snap-to-extrema | Medium | index.html |
| #33 | Fib preview lines | Small | index.html |
| #34 | XL aspect ratio | Small | index.html |
| #35 | Non-blocking confirmation | Medium | index.html |
| #36 | Housekeeping (clear data) | Trivial | CLI |

All 4 implementation issues can be worked **in parallel** by separate engineer agents.

**Next Step:** Engineering to implement #32-#35 in parallel. Then housekeeping (#36), then heavy annotation.

---

## Q-2025-12-12-1: Ground Truth Annotation Tool Design

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 12, 2025

**Context:** User feedback identified fundamental limitation in current validation approach: can't catch false negatives (swings user sees that system missed). New paradigm: user marks swings blind, then compare against system output.

**Questions Asked:**
1. Cascading scale implementation: How should the XL → L → M → S progression work technically?
2. Annotation data model: What should be stored per annotation? How to match user vs system swings?
3. Integration approach: Replace `lightweight_swing_validator` in place, or build parallel and swap?
4. Window parameter behavior: Does current bar_aggregator support showing 50K bars aggregated at XL?
5. Any feasibility concerns?

**Resolution (Architect):**

**1. Cascading Scales:**
- XL: aggregate to ~50 bars (window / 50)
- L: aggregate to ~200 bars (window / 200)
- M: aggregate to ~800 bars (window / 800)
- S: source resolution (no aggregation)
- Panel layout: 25% reference (larger scale), 75% main (active annotation)

**2. Annotation Data Model:**
```python
SwingAnnotation:
    annotation_id, scale, direction, start_bar_index, end_bar_index,
    start_source_index, end_source_index, start_price, end_price,
    created_at, window_id
```
Matching: direction + scale + positional overlap (start/end within 10% tolerance)

**3. Integration Approach:**
Build parallel, then swap. Current validator may still be useful for quick checks. Reuse: ProgressiveLoader, BarAggregator, ScaleCalibrator, swing_detector. New: AnnotationStorage, ComparisonAnalyzer, CascadeController, Canvas UI.

**4. Window Parameter:**
Current bar_aggregator does NOT support arbitrary aggregation. Need new `aggregate_to_target_bars()` method. Straightforward extension of existing logic.

**5. Feasibility:**
No blockers. Medium risk on canvas UX at scale (mitigated by fixed aggregation per scale) and matching tolerance calibration (start at 10%, expose as parameter).

**Next Step:** Engineering to create GitHub issue for MVP implementation.

---

## Q-2025-12-11-3: Harness vs Lightweight Validation Tool

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 11, 2025

**Context:** Dogfooding revealed visualization harness cannot support validation - playback frozen, timestamp errors, auto-pause spam. User proposed pivoting to lightweight HTML-based swing validation tool.

**Questions Asked:**
1. Root cause of playback freeze?
2. Effort to fix harness?
3. Effort to build lightweight tool?
4. What's salvageable from harness?

**Resolution (Architect):**

**Root cause:** Multiple interacting failures:
- Timestamp ordering violations in BarAggregator (deep architectural issue - aggregator assumes forward-only stream but harness allows jumps/resets)
- Aggressive auto-pause on S-scale events (fires constantly, masks all other issues)
- Visualization update queue stalls when constantly paused

**Effort assessment:**

| Path | Effort | Risk |
|------|--------|------|
| Fix harness (minimum viable) | 2-3 weeks | Medium - state synchronization issues |
| Fix harness (full polish) | 4-6 weeks | Medium |
| Lightweight validator | 10-14 days | Low - clean implementation |

**Salvageable from harness:** ~70% of codebase
- Fully reusable: All of `src/swing_analysis/*`, `src/data/*`, `src/validation/*`
- Not reusable: `src/visualization_harness/renderer.py`, `controller.py`, `harness.py`

**Recommendation:** Path B (lightweight tool) - faster time to value, lower risk, directly serves validation objective.

**Next step:** Awaiting Product decision on path. Full technical assessment in `Docs/State/architect_notes.md`.

---

## Q1: Stale CLI Path References Need Cleanup

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** 2024-12-11

**Question:** Stale `src.cli.main` references in CLAUDE.md, src/data/loader.py, and Docs/State/architect_notes.md need cleanup. Should these be updated to `src.visualization_harness.main`, or is there a planned CLI restructuring?

**Resolution (Architect):** **Updated all stale references.** No CLI restructuring is planned.

Investigation confirmed:
- `src/cli/` directory does not exist and never existed
- All CLI functionality lives in `src/visualization_harness/` (main.py, harness.py)
- References to `src.cli.main` were incorrect documentation artifacts

**Files updated:**
| File | Change |
|------|--------|
| `src/data/loader.py:404,434` | Updated error message CLI commands |
| `src/visualization_harness/harness.py:8-10` | Updated docstring usage examples |
| `CLAUDE.md:116-193` | Restructured Core Components to match actual directory layout |
| `Docs/State/architect_notes.md:56-57` | Updated validation commands |

**Additional cleanup:**
- Consolidated 6 fake directories (`src/analysis/`, `src/visualization/`, `src/playback/`, `src/logging/`, `src/cli/`, `src/legacy/`) into actual structure (`src/swing_analysis/`, `src/visualization_harness/`, `src/data/`)
- CLAUDE.md architecture section now accurately reflects codebase

---

## Q-2025-12-11-2

**From:** Architect
**To:** Product
**Status:** Resolved
**Date:** December 11, 2025

**Question:** UX decisions for validation refinement - per-scale swing caps and hysteresis

**Resolution (Product):** **Collect during validation, not before.**

These are tuning parameters that should be informed by actual usage:
- Per-scale swing caps (S=5, M=3, L=2, XL=1 vs uniform 5) - Current uniform default is a reasonable starting point
- Hysteresis for dynamic aggregation - Unclear if this is a problem until user experiences rapid switching

**Rationale:** We don't have enough signal to make these decisions ahead of time. Current defaults work. If they cause friction during validation, user will tell us. That's the highest-signal way to tune.

**Action:** No engineering work. Observe during validation sessions and adjust if feedback indicates need.

---

## Q-2025-12-11-1

**From:** Director
**To:** Product
**Status:** Resolved
**Date:** December 11, 2025

**Question:** Should Product have direct tool access via MCP server?

**Resolution (Product):** **Defer.** Wrong timing, wrong problem.

**Reasoning:**

1. **Timing is wrong.** Phase 2 stability nearly complete. Validation sessions imminent. Building MCP infrastructure now would delay the path to the actual goal (generator).

2. **Problem is wrong.** The core validation question is: "Does swing detection match expert market structure intuition?" This requires domain expertise, not automation. Product seeing screenshots cannot substitute for 12 years of market structure experience.

3. **Scope is non-trivial.** CLI execution + screenshot capture + keyboard simulation + output parsing = significant engineering that doesn't advance the generator.

4. **North star alignment.** User stated: "I don't care about visualization other than for debugging." The goal is generating realistic OHLC data, not more harness tooling.

5. **Current workflow works.** User validates → Product interprets feedback → direction updated. The "expensive oracle" model is appropriate here because the oracle has the expertise we actually need.

**If revisited later:** Consider only if validation reveals a pattern where Product needs to triage before User engagement. Even then, a simpler approach (CLI output parsing only, no screenshot/keyboard sim) would likely suffice.

---

## Q-2025-12-11-A

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 11, 2025

**Question:** Pre-compute swing cache vs algorithm rewrite - which is cheaper?

**Resolution:** Architect recommended algorithm rewrite. O(N log N) rewrite was achievable and carries forward to generator phase. Caching would be throwaway work. Algorithm rewrite completed Dec 11.

---

## Q-2025-12-10-A

**From:** Architect
**To:** Product
**Status:** Resolved
**Date:** December 10, 2025

**Question:** Ready to proceed to Market Data Generator phase?

**Resolution:** No. User clarified in interview that validation on historical data must complete first. Generator phase explicitly deferred.
