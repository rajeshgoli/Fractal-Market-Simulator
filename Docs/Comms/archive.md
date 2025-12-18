# Resolved Questions

---

## Q-2025-12-17-2: Replay View Playback Redesign (Issue #112)

**From:** Engineer
**To:** Architect
**Date:** December 17, 2025
**Status:** Resolved

### Context

Replay View playback not working as expected. The current architecture pre-loads ALL source bars at startup via `fetchBars('S')`, meaning the algorithm has "seen" all data including bars meant for playback. The frontend filtering approach is cosmetic - it hides bars that were already processed during calibration.

### Questions Asked

1. **Data loading:** Should the frontend only load calibration bars initially? Or should the backend limit what it returns based on a "playback window"?
2. **Incremental detection:** Is re-running detection per bar correct, or should detection state be maintained incrementally?
3. **Chart data:** How should aggregated bars be handled during playback - fetched incrementally or computed from new source bars?
4. **State management:** Where should the "current playback position" boundary be enforced - frontend, backend, or both?

### Resolution (Architect)

**Recommendation: Backend-controlled data boundary**

The backend should be the single source of truth for what bars are "visible" at any point in time.

**Rationale:**
1. Single responsibility - backend owns data loading; frontend owns visualization
2. No trust issue - frontend cannot accidentally receive future data
3. Simpler frontend - no complex filtering logic with potential bugs
4. Testable - backend behavior can be unit tested in isolation

**Architecture Changes:**

#### 1. Data Loading (Two-phase)

**Phase 1 - Calibration:**
- `init_app()` only loads calibration window into `source_bars`
- Store `total_bars_available` and file reference for later loading
- Track `playback_index` in `AppState`

**Phase 2 - Playback:**
- `/api/replay/advance` loads bars from disk/cache (not pre-loaded array)
- Extend `source_bars` with newly loaded bars
- Run detection on entire visible window (now includes new bar)

#### 2. API Changes

- Modify `/api/bars` to respect `playback_index` when returning bars
- Modify `/api/replay/advance` to load from disk instead of slicing `source_bars`

#### 3. Frontend Changes

- Remove `filteredChart1Bars` / `filteredChart2Bars` memos
- Trust backend returns only what's visible
- Re-fetch aggregated bars after advance (or batch every N bars)

#### 4. Detection Strategy

**Answer:** Re-run detection per bar (current approach) is correct.
- Detection is O(N log N) where N is visible bars
- At bar 10,001, this is ~130K comparisons = <10ms
- Incremental detection would add complexity for minimal gain

**Implementation Checklist:**

1. Backend: Modify `init_app()` to only load calibration window
2. Backend: Add `playback_index` tracking to `AppState`
3. Backend: `/api/replay/advance` loads from disk/cache
4. Backend: `/api/bars` respects `playback_index`
5. Frontend: Remove client-side filtering logic
6. Frontend: Re-fetch aggregated bars after advance

**Alternative Rejected:** Client-side filtering cannot work because detection runs on the full dataset server-side. Even if frontend filters bars, swing detection results are contaminated by look-ahead.

---

## Q-2025-12-17-1: Replay View Architecture Redesign

**From:** Product
**To:** Architect
**Date:** December 17, 2025
**Status:** Resolved

### Context

User tested Replay View. UI is polished but replay model is fundamentally wrong for the intended purpose (causal evaluation of swing detection).

### Issues Identified

1. **No swings detected** — 10K 5m bars yields zero swings
2. **Look-ahead bias** — Current preload-and-scrub model shows entire future upfront
3. **Speed reference** — Currently tied to source resolution (5m), should be relative to chart aggregation
4. **Navigation** — `<<` / `>>` navigate by bar, should navigate by event

### Resolution (Architect)

**Bug Diagnosis: Zero Swings Detected**

**Root cause:** The `current_price` filter in `detect_swings()` (lines 1020-1024, 1091-1095 in `swing_detector.py`) is designed for **live detection** but breaks on **historical replay**.

When Replay View loads 10K bars:
1. `current_price` is set to the close of bar 9999 (the final bar)
2. A swing formed at bar 2000 must have its 0.382-2.0 zone bracket the price at bar 9999
3. Over 10K 5m bars (~35 hours), price moves substantially
4. Most swings fail this check because they were formed in a different price regime

**Why Ground Truth Annotator works:** Uses windowed data (e.g., 5K bar windows). Within a small window, the final price is more likely to bracket swings formed in that window.

**Fix required:** Add `current_bar_index` parameter to `detect_swings()`. When provided, use that bar's close as the reference price instead of the dataset end.

**Architecture Design: Calibration-First, Forward-Only Playback**

| Phase | Behavior |
|-------|----------|
| **Calibration** | Load window, detect active swings, show calibration report |
| **Pre-playback** | Allow cycling through active swings |
| **Forward-only playback** | Advance beyond window, new bars appear, events surface in real-time |

Key components:
- **Backend:** New `POST /api/replay/advance` endpoint for incremental bar loading and detection
- **Frontend:** State machine with phases (calibrating, pre-playback, playing, paused)
- **Speed control:** Relative to chart aggregation, not source resolution
- **Navigation:** Event-based (`<<`/`>>` jump to previous/next event)

**Technical Concerns Addressed:**

| Concern | Resolution |
|---------|------------|
| Incremental detection efficient? | Yes — O(N log N) detection takes <100ms for 10K bars |
| Multiple events at same bar? | Queue them, show sequentially |
| Memory with large datasets? | Stream bars on demand, calibration window is max footprint |

**Issue Decomposition:**

| Issue | Scope |
|-------|-------|
| #99 | Zero swings bug fix (add `current_bar_index` param) |
| #100 | Calibration phase |
| #101 | Forward-only playback |
| #102 | Speed control redesign |
| #103 | Event navigation |
| #104 | Active swing display (toggles, colors, markers) |

**Full design:** See `Docs/State/architect_notes.md`

---

## Q-2025-12-15-2: FIB-Based Structural Separation for Extrema Selection

**From:** Product
**To:** Architect
**Date:** December 15, 2025
**Status:** Resolved

### Context

Ver4 annotation sessions show 42% of FPs are extrema selection problems (better_high/low/both). The algo finds swings in the right general area but anchors to sub-optimal endpoints that aren't "structurally significant."

User observation: The algo picks "a random lower high in a series of lower highs" with no qualifying low between it and the highest high. Or it picks a low that's not the structural low — one where a stop would be "casually violated."

### Questions Asked

1. **Feasibility:** Is this implementable given current SwingDetector and ScaleCalibrator architecture?
2. **Ordering:** Does detection need to run XL→L→M→S sequentially, or can scales still be processed in parallel with post-filtering?
3. **Which FIB levels?** User said "at least one FIB level" — should this be any standard level (0.382, 0.5, 0.618, 1.0) or a minimum threshold like 0.382?
4. **Edge cases:** What happens at window boundaries where larger swings may be incomplete?
5. **Performance:** Any concerns with referencing larger-scale FIB grids during small-scale detection?

### Resolution (Architect)

**Status: FEASIBLE** — Merged into Phase 3 of endpoint selection design.

| Question | Decision | Rationale |
|----------|----------|-----------|
| Feasibility | Yes | Current architecture has all components: multi-scale detection, FIB calculation, scale cascade |
| Ordering | Sequential XL→L→M→S required | Smaller-scale validation needs larger-scale swings as reference |
| FIB grid | Extended symmetric grid | Add 0.236, 0.786, 1.236, 1.786 to fill voids where reversals occur |
| FIB threshold | 0.236 minimum | Smallest level on extended grid (captures shallow retracements) |
| Edge cases | N-bar + X% fallback | For XL and window boundaries, use volatility-adjusted heuristic |
| Performance | No concerns | O(N × quota) additional work, negligible vs O(N log N) detection |

**Integration Decision:** Merged with existing Fib Confluence design to create unified Phase 3:
- **3A: Structural Separation Gate** — Require ≥1 FIB level separation (0.236 minimum on extended grid)
- **3B: Fib Confluence Scoring** — Prefer endpoints that land on FIB levels of containing swing

**Extended FIB Grid:** `0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0`
Standard grid has gaps where valid reversals occur; extended grid provides symmetric coverage.

Both are FIB-based relationships; separation is a gate, confluence is a score.

**Key Change:** Detection must pass `larger_swings` context between scales:
```python
xl_swings = detect_swings(df, scale='XL', ...)
l_swings = detect_swings(df, scale='L', larger_swings=xl_swings, ...)
m_swings = detect_swings(df, scale='M', larger_swings=l_swings, ...)
s_swings = detect_swings(df, scale='S', larger_swings=m_swings, ...)
```

**Full design:** See `Docs/State/architect_notes.md` Phase 3 section.

---

## Q-2025-12-15-2: Endpoint Selection Design

**From:** Product
**To:** Architect
**Date:** December 15, 2025
**Status:** Resolved

### Context

Ver3 sessions show 75% of FPs are endpoint selection issues (better_high/low/both). Core swing detection works; need to pick better endpoints.

### Questions Asked

1. **Fib Confluence Implementation:**
   - Which larger swing(s) to reference? Immediate parent only, or all ancestors?
   - Should we score by "fib confluence count"?
   - What tolerance for "near a fib level"?

2. **Best Extrema in Vicinity:**
   - How to define "vicinity"?
   - Post-filter or integrated?

3. **Quota per Scale:**
   - How to rank swings for quota?
   - Is "2 biggest + 2 highest impulse" reasonable?

### Resolution (Architect)

**Designed three-layer approach:**

#### Layer 1: Fib Confluence Scoring (Primary Signal)

| Decision | Answer | Rationale |
|----------|--------|-----------|
| Which swing to reference? | Immediate containing swing only | Multiple ancestors adds complexity without clear benefit |
| Score method? | Proximity to nearest fib level | Simpler than "confluence count" |
| Tolerance? | 0.5% of swing size | Adaptive to swing magnitude |

#### Layer 2: Best Extrema Adjustment (Tie Breaker)

| Decision | Answer | Rationale |
|----------|--------|-----------|
| Vicinity definition? | lookback bars (same as detection) | Consistent with detection semantics |
| Integration? | Post-filter | Cleaner separation of concerns |

#### Layer 3: Quota per Scale (Quantity Control)

| Decision | Answer | Rationale |
|----------|--------|-----------|
| Ranking method? | 0.6×size_rank + 0.4×impulse_rank | Size captures magnitude; impulse captures conviction |
| Quota per scale? | XL=4, L=6, M=10, S=15 | Fewer swings at larger scales |

### Implementation Phases

1. **Phase 1: Best Extrema** - Quick win, ~50% FP reduction expected
2. **Phase 2: Quota per Scale** - Replaces max_rank, removes threshold tuning
3. **Phase 3: Fib Confluence** - Most complex, adds structural justification

**Full design:** See `Docs/State/architect_notes.md`

---

## Q-2025-12-15-6: Too Small and Subsumed Filters

**From:** Product
**To:** Architect
**Date:** December 15, 2025
**Status:** Resolved

### Context

15 annotation sessions complete (10 ver1 + 5 ver2). Max_rank filter (#56) implemented but didn't address root cause.

**Ver2 Session Data (post-max_rank):**

| Category | Count | % of True FPs |
|----------|-------|---------------|
| too_small | 39 | **65%** |
| subsumed | 17 | **28%** |
| too_distant | 2 | 3% |
| counter_trend | 1 | 2% |

**93% of remaining FPs are too_small or subsumed.**

### Resolution (Architect)

**Designed two filters based on empirical data analysis.**

#### Filter 1: Too Small (P0) — Issue #62

Two parameters added to `detect_swings()`:
- `min_candle_ratio=5.0` — Swing must be at least 5x median candle size
- `min_range_pct=2.0` — Swing must be at least 2% of window price range

**Logic:** Filter if BOTH thresholds fail (kept if either passes). This handles cases where small absolute size is significant in low-volatility windows.

**Empirical basis:** Ver2 "too_small" FPs show p50=5.85% range, p25=3.15%. Threshold of 2% captures bottom quartile.

#### Filter 2: Prominence (P1) — Issue #63

One parameter added to `detect_swings()`:
- `min_prominence=1.0` — Swing high/low must stand out by at least 1x median candle from nearest competing extremum

**Logic:** Calculate gap between swing high/low and second-best in local window. If gap < threshold, filter out.

**Empirical basis:** 74 better_reference entries show users consistently pick points that are distinctly higher/lower than adjacent extrema.

### Integration Point

After protection validation, before redundancy filtering:
```
1. Swing detection → 2. Pairing → 3. Protection → 4. Size filter → 5. Prominence filter → 6. Redundancy → 7. Ranking → 8. max_rank
```

### Validation Plan

After implementation:
1. Run 3-5 annotation sessions
2. Target: FP rate reduced by >70%
3. Check for regressions (new FNs from over-filtering)

**Full design:** See `Docs/State/architect_notes.md`

---

## Q-2025-12-15-5: Phase 2 FN Investigation Priority

**From:** Engineer
**To:** Product
**Date:** December 15, 2025
**Status:** Resolved

### Context

Issue #56 Phase 1 complete:
- `max_rank` parameter reduces FP noise (~95% of FPs addressable)
- Relaxed matching tolerance converts ~9 FNs to matches

**Remaining:** 16 true FN misses (detector genuinely doesn't output the swing)

### Phase 2 Scope

Investigation to understand WHY these swings aren't detected:
1. Add debug instrumentation to track filter reasons
2. Re-run analysis on 10 annotation sessions with debug output
3. Categorize misses by filter type (protection check, Fibonacci zone, pairing logic)
4. Propose fixes based on findings

### Question

Is Phase 2 worth pursuing now?

### Resolution (Product)

**Decision: Defer — Low priority, not blocking current goals.**

**Reasoning:**

1. **Phase 1 is sufficient for annotation goals.** The `max_rank` filter addresses ~95% of FPs. Users can annotate with far less noise. The immediate bottleneck is removed.

2. **"Better Reference" data is higher leverage.** Q-2025-12-15-4 (broader detection quality) is blocked waiting for "detector found X, should have found Y" data. That data will inform both FP and FN fixes more comprehensively than Phase 2 alone.

3. **16 FNs may be acceptable edge cases.** That's ~1.6/session across 10 sessions. If these are genuinely hard cases, algorithm changes may not be warranted.

4. **Avoid premature optimization.** Without "better reference" data, we don't know if the 16 FNs are filter bugs (fixable), edge cases (acceptable), or symptoms of a deeper design issue (requires rethinking).

**Recommended Priority Order:**

1. P1.5: "Better Reference" data collection — Ship inline better-reference UX (#57)
2. Collect 3-5 more sessions with new tooling
3. Revisit Phase 2 IF FN data suggests filter fixes are warranted

**Reactivation Trigger:** If Architect requests FN filter categorization during detection quality redesign, reactivate Phase 2 at that point.

---

## Q-2025-12-15-2: Reference Swing Protection Validation

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 15, 2025

**Context:** User identified that `swing_detector.py` shows reference swings where the swing point has been violated by subsequent price action. Example: Bull ref 1496→1369 shown, but price traded to 1261 afterward (low violated by 108 pts).

**Questions Asked:**
1. What's the cleanest path to fix this?
2. Option 1: Add protection check to `swing_detector.py`
3. Option 2: Switch annotator to use `bull_reference_detector.py`

**Resolution (Architect):**

**Recommended Approach: Option 1 - Extend swing_detector.py**

| Aspect | Option 1 | Option 2 |
|--------|----------|----------|
| API Change | None | Breaking (dataclass vs dict) |
| Refactoring | ~20 lines | ~100+ lines in comparison_analyzer.py |
| Complexity | O(N log N) maintained | O(N²) post-formation scan |
| Risk | Low | Medium-high |

**Implementation Design:**

1. **Build additional sparse tables on ALL bar lows/highs** (not just swing points):
   ```python
   all_lows_min_table = SparseTable(lows, mode='min')
   all_highs_max_table = SparseTable(highs, mode='max')
   ```

2. **Add protection check after structural validation:**
   - Bull reference: After validating structure, check `all_lows_min_table.query(low_bar_index+1, len(bars))` to ensure no subsequent bar violated the swing low
   - Bear reference: Check `all_highs_max_table.query(high_bar_index+1, len(bars))` to ensure no subsequent bar violated the swing high

3. **Tolerance parameter** (matching `bull_reference_detector.py`):
   ```python
   def detect_swings(..., protection_tolerance: float = 0.1):
   ```
   - Default 10% of swing range
   - Violation threshold: `low_price - (protection_tolerance * size)`

**Complexity Analysis:**
- Additional preprocessing: O(N log N) for two sparse tables on full bars
- Query per candidate: O(1)
- Total: O(N log N) maintained

**Why NOT Option 2:**
- `bull_reference_detector.py` uses different API (dataclass vs dict)
- Would require refactoring `comparison_analyzer.py` (~100+ lines)
- Has features we don't need (explosive classification, multiple subsumption passes)
- Higher regression risk

**Files Affected:**
| File | Change |
|------|--------|
| `src/swing_analysis/swing_detector.py` | Add protection_tolerance param, build full-bar sparse tables, add post-formation check |
| `tests/test_swing_detector.py` | Add protection validation tests |

**Next Step:** Engineering to create GitHub issue and implement.

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
