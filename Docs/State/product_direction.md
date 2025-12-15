# Product Direction

**Last Updated:** December 15, 2025
**Owner:** Product

---

## Current Objective

**Fix "too small" and "subsumed" FP noise before continuing annotation.**

Ver2 sessions (5 completed) show max_rank filter helped but **93% of remaining FPs are too_small (65%) or subsumed (28%)**. Must address before collecting more data — annotation velocity is blocked by dismissing noise.

---

## P0: Too Small Filter (Blocking)

**Problem:** 65% of FPs are swings that are too small to be meaningful at the scale being analyzed.

**User-Proposed Heuristics:**
1. **Bar count threshold:** Discard if swing spans < 5% of range bars
2. **Volatility threshold:** Discard if swing magnitude < 3x median candle size

**Action:** Architect to analyze annotation data empirically, derive thresholds, implement filter.

---

## P1: Subsumed / "Stands Out" Heuristic

**Problem:** 28% of FPs are swings with endpoints *near* but not *at* the important extrema. User consistently picks highs/lows that "stand out" from surrounding noise.

**Pattern from better_reference data:**
- Detector finds local extrema that happen to be near important levels
- User picks the extrema that is **distinctly higher/lower** than adjacent points
- The difference: "highest point in noisy region" vs "point that stands out from surrounding highs"

**Potential heuristics (for Architect to evaluate):**
- Distance from nearest higher high (for tops) / lower low (for bottoms)
- Percentile rank within local window
- Price delta from surrounding extrema

**Action:** Architect to analyze better_reference coordinates, propose heuristic, implement.

---

## Why This Is Highest Leverage

The detector is miscalibrated (250x more detections than human expert). We have:
- Two-click annotation workflow
- Cascading scale progression (XL → L → M → S)
- Review Mode with FP/FN feedback collection
- Random window selection for dataset diversity
- Structured export for rule iteration
- Session quality control (keep/discard)

**The tool is production-ready. The bottleneck is now data collection.** Multiple annotation sessions across different market regimes will reveal patterns in detection errors.

---

## Immediate Next Steps

### 1. Run Annotation Sessions

```bash
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random
```

**Target:** 5-10 quality sessions (XL → S + Review Mode) to build initial ground truth corpus.

### 2. Review Feedback Patterns

After sessions, analyze exported JSON for:
- Common FP categories (noise patterns)
- FN explanations (what the system misses)
- Match confirmation rate

### 3. Iterate Detection Rules

Use feedback to refine `swing_detector.py` parameters or logic.

---

## Data Collection Plan

**Question:** "How many sessions before we can iterate on detection logic?"

### Short Answer

**5-10 quality sessions** should reveal actionable patterns. You don't need comprehensive coverage — you need enough diversity to see which error categories repeat.

### Criteria for "Enough Data"

You're ready to iterate when:
1. **FP categories stabilize** — Same noise patterns appear across sessions
2. **FN patterns emerge** — "Biggest swing" or "most impulsive" clusters form
3. **At least 3 different market regimes** — Trending, ranging, volatile windows

### Iteration Cycle

```
Annotate 5-10 sessions
    ↓
Export JSON, analyze patterns
    ↓
Identify top 2-3 error categories
    ↓
Propose rule adjustments
    ↓
Implement changes to swing_detector.py
    ↓
Re-run on same data to validate improvement
    ↓
New sessions to check for regressions
    ↓
Repeat
```

### What "Improvement" Looks Like

- FP rate drops (fewer noise detections)
- FN rate drops (fewer missed swings user marked)
- Match rate increases (user agrees with more system detections)

### Risk Mitigation

- Don't over-fit to one session — wait for pattern repetition
- Keep practice sessions separate from real data (session quality control)
- Version control rule changes so you can revert

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| Two-click annotation workflow | Complete |
| Cascading scale progression (XL → L → M → S) | Complete |
| Annotations comparable against system output | Complete |
| Snap-to-extrema removes pixel-hunting friction | Complete |
| Fibonacci preview for visual validation | Complete |
| Non-blocking confirmation with hotkeys | Complete |
| Review Mode (matches, FP sample, FN feedback) | Complete |
| Structured export for rule iteration | Complete |
| Session continuation with random windows | Complete |
| Reference level label orientation | Complete |
| FN explanation with preset categories | Complete |
| Clear export/save workflow | Complete |
| Session quality control (keep/discard) | Complete |

**All success criteria met. Tool is production-ready.**

---

## Completed Issues

| Issue | Description | Status |
|-------|-------------|--------|
| #44 | Remove deprecated modules | Done |
| #43 | Session flow (random offset, next window) | Done |
| #42 | Review Mode frontend | Done |
| #41 | Review Mode API endpoints | Done |
| #40 | Review controller | Done |
| #39 | Review Mode data models | Done |
| #37 | Snap-to-extrema price proximity | Done |
| #35 | Non-blocking confirmation | Done |
| #33 | Fibonacci preview lines | Done |
| #32 | Snap-to-extrema | Done |

---

## P1: Trend-Aware Detection

**Status:** Approach confirmed. Implementation deferred until pattern validated.

**Problem:** Detector emits reference ranges against the prevailing trend direction:
- Downtrending market → finds bear references (counter-trend rallies) as FPs
- Uptrending market → finds bull references (counter-trend pullbacks) as FPs

**Impact:** May explain significant portion of 250x over-detection at XL/L scales.

**Confirmed Approach (Dec 15):**
Add `trend_context` parameter to `detect_swings()`:
- `"neutral"` — Current behavior (default)
- `"bullish"` — Suppress bear_references
- `"bearish"` — Suppress bull_references
- `"auto"` — Calculate trend from price data, apply appropriate filter

Implementation as post-filter; core algorithm unchanged. See `Docs/Comms/archive.md` Q-2025-12-15-1.

**Data Collection (Dec 15):**
Added "Counter trend" (`4`) to FP quick-select buttons. Track prevalence in annotation sessions before implementing full trend-aware detection.

**Implementation Trigger:**
- 3+ sessions show counter-trend in top-3 FP categories
- Pattern appears across different market regimes

---

## P1 (Complete): FP Quick-Select Buttons (#52)

**Status:** Complete.

Five direct-action buttons now work for FP review:
- Too small (`1`) - Dismiss + advance
- Too distant (`2`) - Dismiss + advance
- Something bigger (`3`) - Dismiss + advance
- Dismiss (Other) (`N`) - Dismiss + advance
- Accept (`V`) - Accept + advance

---

## P1.5 (Complete): Session Labeling (#53)

**Status:** Complete.

Timestamp-based session filenames with keep/discard workflow implemented. Sessions now saved as `session_YYYYMMDD_HHMMSS.json` instead of UUIDs.

---

## P2: Annotation UX (#57)

**Status:** Issue filed. See GitHub issue #57.

| Item | Problem | Status |
|------|---------|--------|
| FN Auto-Advance | FP auto-advances, FN requires extra click. Inconsistent. | Ready |
| Session Metadata | Difficulty (1-5) + market regime + comments at session end | Ready |
| Inline Better Reference | Modal flow with no verification. Should be inline with Fib preview. | Ready |
| Fib Preview on Alternate | No Fib lines when selecting alternate swing in FP dismissal | Ready |
| ESC to Cancel Selection | ESC should clear pending alternate selection for re-pick | Ready |
| Remove Redundant Screen | "Move to next section" after FPs → go straight to review | Ready |
| Add -0.1 Fib Level | Add stop level -0.1 to existing Fib preview | Ready |
| Precompute System Swings | Compute detector swings in background while user annotates | Ready |
| Review Screen Show XL | Show XL scale on review screen for big picture context | Ready |
| Versioned Filenames | Format: `yyyy-mmm-dd-HHmm-ver<version>.json` for easy parsing | Ready |
| PST/PDT Timestamps | Use local timezone for HHmm instead of UTC | Ready |
| Zoom/Pan for S-Scale | Snap finicky at small scale | Deferred |
| Snap at Chart Edges | Snap radius may extend beyond visible data | Deferred |

---

## Deferred

- Generator work — pending validated swing detection and ground truth data
- Zoom/pan UX — deferred until blocking in practice
- Edge snap fixes — deferred until blocking in practice

---

## Checkpoint Trigger

**Invoke Product when:**
- After 5+ annotation sessions reveal feedback patterns
- When ready to translate feedback into detection rule changes
- If P2 UX issues prove blocking during annotation

---

## Session Observations (Dec 15, Updated)

### Ver2 Sessions (Post-max_rank fix)

**Sessions completed:** 5 (ver2)

| Metric | Count |
|--------|-------|
| Total FPs reviewed | 97 |
| True FPs (noise) | 60 |
| valid_missed | 37 |
| Matches | 3 |
| FNs | 2 |

**FP Category Distribution (ver2):**

| Category | Count | % of True FPs |
|----------|-------|---------------|
| too_small | 39 | **65%** |
| subsumed | 17 | **28%** |
| too_distant | 2 | 3% |
| counter_trend | 1 | 2% |

**93% of remaining FPs are too_small or subsumed.** Max_rank filter reduced volume but root cause persists.

### Pre-Ver2 Sessions (10 sessions)

| Metric | Total |
|--------|-------|
| Matches confirmed | 37 |
| FPs reviewed | 185 |
| True FPs | 129 |
| Valid missed | 56 |
| FNs | 33 |

**FP Category Distribution (pre-ver2):**

| Category | Count | % of True FPs |
|----------|-------|---------------|
| too_small | 68 | 53% |
| subsumed | 54 | 42% |
| too_distant | 5 | 4% |
| other | 2 | 2% |

**Pattern is stable across all sessions** — too_small and subsumed dominate.

### FN Analysis

| Type | Count | Description |
|------|-------|-------------|
| Matching issues | 9 | Detector found swing, comparison too strict |
| True misses | 16 | Detector doesn't output the swing |

### FN Themes (33 total)

| Theme | Count |
|-------|-------|
| "Biggest swing at this scale" | 19 |
| "Fits timeframe/nearest" | 4 |
| "Most impulsive move" | 4 |
| "Inner/nested structure" | 3 |
| Other | 3 |

---

## P0: Detection Quality — Reactions vs Primary Structures (#56)

**Status:** Root cause identified. Implementation ready. See GitHub issue #56.

### Key Finding

**The detector DOES find primary structures correctly and ranks them #1.**

The problem is OUTPUT VOLUME — detector also emits many secondary structures (rank 2, 3, 4...) which users dismiss as "too small" or "subsumed".

**Evidence from session 1838:**
- Detector output: 71 swings across all scales
- User annotations: 9 swings
- If rank=1 only: 8 swings (close match!)
- If rank≤2: 12 swings

### Two Distinct Problems

| Problem | Count | Root Cause | Fix |
|---------|-------|------------|-----|
| **FPs** | 129 | Too many secondary structures | Add `max_rank` filter |
| **FN (matching)** | 9 | Comparison tolerance too strict | Relax threshold |
| **FN (true miss)** | 16 | Protection/Fib zone filters | Needs investigation |

### Recommended Implementation

**Phase 1 (Quick wins):**
1. Add `max_rank` parameter to `detect_swings()` — filter to top N per direction
2. Relax comparison matching tolerance to 20% of span

**Phase 2 (Investigation):**
- Instrument detection to track why swings are filtered
- Categorize 16 true misses by filter reason
- Determine if protection checks are too aggressive

### User's Characterization (still valid)

**"Subsumed":** Detector catches swings with endpoints *near* important levels but not *the* important swing. These are rank 2+ swings that should be filtered.

**"Too small":** Low-rank, small swings. Filtered by rank threshold.

---

## P1.5: Data Collection Improvements (Blocking)

**Status:** Ready for Engineer. Blocks P0 fix design.

### 1. Optional "Better Reference" for FP Dismissals

When dismissing an FP, optionally mark what you would have chosen instead. Gives "detector found X, should have found Y" data.

- Strictly optional (overwhelming otherwise)
- Two-click selection like annotation mode
- Stored in review feedback

### 2. Feedback JSON Versioning

Add `"version": 1` field before schema changes. Allows backward-compatible interpretation.

### 3. Snap Toggle Hotkey

Hold modifier (Shift?) to temporarily disable snap-to-extrema. Useful when snap doesn't find the right point and user wants manual selection.

---

## Session Context

**Where we are:** 15 sessions complete (10 ver1 + 5 ver2). Max_rank filter (#56) implemented. Two root causes remain.

**What's next:**
1. **P0: Too Small Filter** — Derive thresholds from data (bar count %, volatility multiple), implement filter
2. **P1: Subsumed "Stands Out" Heuristic** — Analyze better_reference data, propose heuristic for selecting truly prominent extrema
3. **Validate** — Run 3-5 sessions post-fix to confirm FP reduction

**Key insight:** Max_rank reduced volume but didn't address root cause. 93% of remaining FPs are too_small (65%) or subsumed (28%). Need swing-level filtering based on:
- **Too small:** Bar count and volatility thresholds
- **Subsumed:** "Stands out" heuristic to select prominent extrema over locally-optimal-but-noisy points
