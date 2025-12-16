# Interview Notes

Consolidated user interview notes. Most recent first.

---

## December 15, 2025 - FIB-Based Structural Separation for Extrema Selection

**Context:** User completed 5 ver4 sessions (94 FP reviews). Reviewing patterns in FP data.

### Ver4 Session Analysis

| Category | Count | % |
|----------|-------|---|
| valid_missed | 36 | 38% |
| better_high | 27 | 29% |
| too_small | 18 | 19% |
| better_low | 8 | 9% |
| better_both | 5 | 5% |

**Key finding:** 42% of FPs are extrema selection problems (better_high/low/both). The algo finds swings in the right area but anchors to sub-optimal endpoints.

### User Observations

**1. "Too small" is hard to evaluate visually:**
> "If you give me a one or two candle swing, I can't quite say whether the high was before the low always. And I can't say if an important FIB level is near it."

User suggests these may be better evaluated by **FIB reaction testing** — do later price movements react at the swing's projected FIB levels (1.618, 2.0)?

**2. Extrema selection lacks structural significance:**

The algo picks extrema that satisfy lookback rules but aren't "structurally defended":

> "It picks a random lower high in a series of lower highs — why that one? There's no low differentiating it from the highest high."

> "For lows, it picks something that's not the lowest. Mechanically the 0.1 hasn't been violated, but imagine placing a stop below it — it would be casually violated because it's not breaking the structural low."

**The stop placement heuristic:** A valid swing low is one you'd defend with a stop. If price casually violates it on the way to the real low, it wasn't structural.

### Circularity Problem with FIB Reaction Eval

User initially proposed using FIB reactions to validate swings, then recognized the trap:

> "If we use FIB reactions — then it may become circular reasoning (we get the FIB reactions because we picked the swings that got the FIB reactions)."

**Constraint:** Must fix extrema selection using only information available *at the time of the swing*, not future price behavior.

### Proposed Solution: FIB-Based Structural Separation

Use FIB levels from **larger swings** (already established, no lookahead) to define "meaningful separation":

```
Given: High A exists at scale S
To register High B at scale S:
  1. There must be a Low L between A and B
  2. L must be ≥1 FIB level away from High A (measured on scale M+ grid)
  3. High B and L must be ≥1 FIB level apart (on any larger scale grid)

For XL swings (no larger reference):
  → Fall back to N bars or X% move (volatility-adjusted)
```

**Why this works:**
- **No lookahead** — Larger swings are historical (already confirmed)
- **Market-structure-aware** — "Meaningful separation" = FIB unit, not arbitrary price/bars
- **Scale-coherent** — Small swings must register on larger FIB grids to matter
- **Self-consistent** — Uses existing multi-scale architecture (S→M→L→XL)

**Key insight:** Separation measured in *FIB units* is structurally meaningful. A 10-point move is noise or signal depending on where it sits on the larger swing's grid.

### Handoff

Question added to `Docs/Comms/questions.md` for Architect: Is this implementable given current SwingDetector and ScaleCalibrator architecture?

---

## December 15, 2025 - FP Category Feedback (Batch Collection)

**Context:** User testing new version with too_small and prominence filters. Collecting additional FP category feedback for batch implementation.

**Status:** Collecting - will implement in one batch

### Ver3 Session Results (6 sessions, 119 FP samples)

| Category | Count | % | Notes |
|----------|-------|---|-------|
| subsumed | 37 | 48% | Now dominant issue |
| too_small | 32 | 42% | Improved from 65% but still present |
| counter_trend | 6 | 8% | |
| too_distant | 2 | 3% | |

**Valid-missed:** 42 (35% of samples)

### Feedback on Current Filters

**Too Small:** Still seeing 1-2 candle swings that aren't prominent. Filters need tightening.

**Subsumed:** Needs subcategories to collect clean signal. Three distinct varieties:
- "I see a better high" (low is fine, high is wrong)
- "I see a better low" (high is fine, low is wrong)
- "I see both better high and low" (entire swing misplaced)

### New FP Categories Requested

| Key | Label | Description |
|-----|-------|-------------|
| `not_prominent` | "Not prominent enough" | Swing is technically correct but either the high or the low are not prominent enough - seems random |
| `better_high` | "Better high" | Subsumed variant: I see a better high for this swing |
| `better_low` | "Better low" | Subsumed variant: I see a better low for this swing |
| `better_both` | "Better high and low" | Subsumed variant: I see both a better high and low |

**Engineer note:** Bump JSON version when adding new categories.

### CLI Enhancement

**`--start-date` parameter requested**

Current: `python3 -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random`

Problem: Random offset biases towards older data (more of it in dataset).

Request: `--start-date 2020-Jan-01 --window 10000` to test more recent data with potentially different market regimes.

### Goal

Close FPs as fast as possible to rise the signal on FNs (the gold).

*(More feedback may be added as testing continues)*

---

## December 15, 2025 - Too Small and Subsumed FPs Dominate

**Context:** User completed 5 ver2 sessions (post-Phase 1 max_rank fix). Data shows max_rank helped but two categories still dominate noise.

### Quantitative Analysis (5 ver2 sessions)

| Metric | Count |
|--------|-------|
| Total FPs reviewed | 97 |
| True FPs (noise) | 60 |
| valid_missed | 37 |

**FP Category Breakdown:**

| Category | Count | % of True FPs |
|----------|-------|---------------|
| too_small | 39 | **65%** |
| subsumed | 17 | **28%** |
| too_distant | 2 | 3% |
| counter_trend | 1 | 2% |

**93% of remaining FPs are too_small or subsumed.** Max_rank filter reduced volume but didn't address root cause.

### User-Proposed Heuristics

**1. Too Small Filter**

User observation: "We should address too small swings before continuing as that's the cause of max noise."

Proposed heuristics:
- **Bar count threshold:** If swing spans < 5% of the analysis range bars, discard
- **Volatility threshold:** If swing magnitude < 3x median candle size in the range, discard

"Obviously I'm making this up — use data to come up with heuristics on filtering."

**2. Subsumed / "Stands Out" Detection**

User observation: "Subsumed category is not picking good highs or lows in the range. You can pick something that 'stands out' from the other highs rather than highs in noise. This is what you'll see in my annotations."

Pattern from `better_reference` data:
- User consistently selects extrema that are **significantly higher/lower** than surrounding points
- Detector finds points *near* important levels but not *the* important swing
- The "stand out" high is the one that's distinctly higher than adjacent highs, not just locally highest

### Priority

**P0 — Too Small filtering is blocking.** 65% of FP noise. Must address before continuing annotation.

**P1 — Subsumed "stands out" heuristic.** 28% of FP noise. Harder to specify but clear in visual review.

### Action

Hand off to Architect:
1. Analyze existing annotation data to derive too_small thresholds empirically
2. Propose "stands out" heuristic based on better_reference coordinates
3. Implement filters and validate with new sessions

---

## December 15, 2025 - Reference Swing Validation Broken

**Context:** User observation during annotation session. Reference swings shown that violate basic definition.

### Problem

Bull reference displayed: 1496→1369 (downswing)
But price subsequently traded to 1261, violating the swing low by 108 points.

**This violates the fundamental definition of a reference swing:** the swing point (low for bull refs, high for bear refs) must remain protected. Once violated, the swing is invalidated.

### Root Cause

`swing_detector.py` (used by annotator) validates:
1. Geometric validity (size > 0)
2. Current price in 0.382-2x retracement zone
3. Swing point is extreme *during* formation

**Missing:** Post-completion protection check. No validation that the swing point hasn't been violated by subsequent price action.

Note: `bull_reference_detector.py` has this check (`_check_low_protection`, lines 841-854), but the annotator doesn't use it.

### User Direction

"The point is to show me what you think are the right references. If the current implementation fails basic definition then no point continuing to use it."

### Required Fix

Add swing point protection validation to reference detection. Either:
1. Integrate `bull_reference_detector.py` logic into annotator flow, OR
2. Add post-completion violation check to `swing_detector.py`

### Priority

**P0 - Blocking.** Without this, reference swing detection is fundamentally broken.

---

## December 15, 2025 - Directional Mismatch in Reference Detection

**Context:** User feedback during annotation sessions. Consistent FP pattern observed.

### Problem

Detector emits reference ranges in the wrong direction relative to the prevailing trend:
- **In downtrending markets:** Detects bull references ✓ but also bear references (counter-trend rallies) that are noise
- **In uptrending markets:** Detects bear references ✓ but also bull references (counter-trend pullbacks) that are noise

**Especially important at XL and L scales** where trend direction is the dominant signal.

### Root Cause

Current `swing_detector.py` logic (lines 325-433) finds reference ranges based on:
1. Geometric validity (High→Low or Low→High)
2. Price proximity (current price within 0.382-2x)
3. Size (ranked by magnitude)

**Missing:** Trend context. The detector treats bull and bear references equally regardless of whether the market is trending up or down.

### Impact

- False positives at XL/L scale for counter-trend swings
- User wastes time reviewing geometrically valid but contextually irrelevant detections
- 250x over-detection partially explained by this directional blindness

### User Question

"Did you get the direction right?"

**Answer:** No. The detector doesn't consider trend direction at all.

### Potential Solutions (for Architect to evaluate)

1. **Trend filter:** Calculate prevailing trend at each scale, suppress counter-trend references
2. **Directional weighting:** Downweight (not eliminate) counter-trend swings in ranking
3. **User-specified bias:** Let user indicate "bullish" or "bearish" context per session
4. **Adaptive:** Use larger-scale trend to filter smaller-scale detections

### Priority

**P1 for rule iteration.** This explains a significant portion of the FP noise, especially at larger scales.

---

## December 15, 2025 - Session Labeling Request

**Context:** Pre-testing feedback. User has accumulated multiple UUID-named session files and finds them impossible to reason about.

### Problem

Session files use UUIDs (e.g., `914b36db-893f-40aa-82e3-76d5de91c8cb.json`). With multiple sessions accumulated, user can't tell which is which without opening each file.

### Request

1. **Label at end of session** — After completing annotation/review, prompt for a human-readable label
2. **Use label for filename** — Rename session file from UUID to user-provided label (e.g., `es-trending-dec15.json`)

### Rationale

"Hard for me to reason about them with their alphanumeric names."

### Action

- Cleared all existing sessions (test data, not production annotations)
- Created issue #53 for session labeling feature

---

## December 15, 2025 - FP Quick-Select Buttons Not Working

**Context:** User testing the FP quick-select buttons from issue #51. Buttons exist but don't function as expected.

### Bug: Buttons Don't Dismiss

User report: "When I click on those buttons, nothing happens. I still need to click on Dismiss."

The quick-select buttons (Too small, Too distant, Something bigger) are supposed to dismiss in one click and advance to next. Currently they appear to do nothing.

**Root cause hypothesis:** JavaScript conflict - `addEventListener` on `.preset-btn` (lines 1607-1611) may interfere with `onclick` handlers on FP buttons.

### UX Simplification Request

Current UI has too many elements:
- 3 quick-select buttons
- Dropdown for "Other reason..."
- "Dismiss (Other)" button
- "Actually Valid" button

**User request:** Replace with 5 direct-action buttons:

| Button | Action |
|--------|--------|
| Too small | Dismiss + advance |
| Too distant | Dismiss + advance |
| Something bigger | Dismiss + advance |
| Dismiss (Other) | Dismiss with "other" category + advance |
| Accept | Mark valid + advance |

Each button should complete the action in one click and immediately advance to next swing. No dropdown needed.

### Key Quote

"Why not give me 5 buttons (3 of too distant, etc., plus dismiss (other reasons), and accept) and when I click on any one the screen moves to next?"

---

## December 12, 2025 - First Full Annotation Session UX Feedback

**Context:** User completed first real annotation session using the ground truth annotator. This is actionable UX feedback from actual usage.

### Bug: Reference Range Level Indicators Inverted

Bull reference shows levels incorrectly:
- Currently: 0 at top, 1 at bottom → level 2 appears *below* the low
- Should be: 0 at bottom, 2 at top → level 2 at `L + 2*(H-L)`, above the high

This makes it hard to assess whether current price is below/above the 2 level. Same issue inverted for bear reference.

**Impact:** User can't quickly validate if they noted the reference range correctly.

### Friction: FN Explanation is Too Slow

Current workflow requires explaining every FN. With multiple FNs per session, this creates significant friction.

**User request:** Make explanation optional, or provide pre-set options:
- "Biggest swing I see"
- "Most impulsive I see"
- Other common categories

### UX Gap: Unclear CTA

User asked: "What's my CTA? Should I export JSON or is this stored by backend by default?"

Need to clarify:
1. Is data auto-saved to backend?
2. If export is required, make button prominent
3. If auto-saved, show confirmation

### Feature Request: Session Quality Control

No way to distinguish:
- "This was a good session, keep this feedback"
- "I was just playing with the tool, delete this"

**Request:** Add button at end of session to mark quality (keep/discard).

### Positive Feedback

> "Overall this is awesome tool, I like it!! Much better than visualization harness. Gives me so many ideas for next steps."

### Planning Question

> "How many feedback sessions do we need before we can look at how to improve our swing detection logic? What's the plan there?"

**Action:** Clarify data collection plan and iteration roadmap.

---

## December 12, 2025 - First Complete Annotation Session

**Context:** User completed first full annotation session after UX polish (snap-to-extrema, fib preview, non-blocking confirm). Attempting to review comparison results and continue annotating.

### UX Polish Assessment

Snap-to-extrema and fib preview are complete and "look good." Snap is "delightful" when it works. Edge cases:
- Finicky when swing is at chart edge (all the way to the right)
- Finicky at S-scale — would need zoom (horizontal time, vertical price) and pan to annotate accurately

### Comparison Results (First Session)

```
User annotations:     9
System detections:    2,216
Matches:              5
False negatives:      4  (user found, system missed)
False positives:      2,211  (system found, user didn't mark)
Match rate:           0.2%
```

**Key insight:** System detects ~250x more swings than human expert considers meaningful. Even accounting for incomplete S-scale annotation, user estimates they'd mark 10-15, not 2,500. Detector is miscalibrated.

### Workflow Pivot Decision

User posed the question: What's more useful?
- **Option A:** Fewer annotations with rich metadata on FPs/FNs (review and explain why)
- **Option B:** More annotations without metadata (current workflow, repeat across windows)

**Decision: Option A (Rich metadata)**

Reasoning from user: "My sense is the former may be more useful to refine rules and iterate with the newer swing detection rules."

With 2,500 FPs, you can't annotate them all. But sampling with qualitative feedback explains *why* the system is wrong — actionable signal for rule refinement.

### Agreed Workflow (Review Mode)

```
1. ANNOTATE
   Mark swings (current 2-click workflow)

2. REVIEW MATCHES (light touch)
   Quick scroll through agreements
   Skip button if obvious

3. REVIEW FP SAMPLE (10-20 from system's detections)
   - "Noise" (default)
   - "Actually valid — I missed this"
   - Optional: why it's noise

4. REVIEW ALL FNs (the gold)
   - Required: "What caught my eye" (free text)
   - Optional: category

5. SESSION SUMMARY
   Stats + export for rule iteration
```

### Gaps Discovered

**1. No comparison UI**

User completed annotations and wanted to see what they caught vs what detector found. Comparison exists via API (`/api/compare`, `/api/compare/report`) but no UI button to trigger or view it. User has to use curl or browser directly to API endpoints.

**2. Session completion is a dead end**

After completing cascade (XL→L→M→S), CTA button fades to "Session Complete!" and disables. No option to load a new window. User expected `--window 50000` to offer continuous annotation of different 50k samples.

**3. Window selection is deterministic**

`--window 50000` always loads the *first* 50k bars (`df.head()`). Running the tool multiple times shows the same window. No randomization, no offset parameter.

### Impact

User can't:
- See their work vs detector output without API knowledge
- Continue annotating beyond one cascade
- Sample different parts of the dataset

### Mismatch with Stated Design

Product direction (line 85) states "Window complete → next random window" — this flow **does not exist** in implementation.

### Key Quote

"Shouldn't it reset to a fresh 50k sample if I started with --window 50000?"

---

## December 12, 2025 - Ground Truth Annotator Dogfood Feedback

**Context:** First dogfood of annotation tool MVP. User tested cascade workflow.

### Overall Assessment

"The UX is beautiful." Tool is working well — feedback is polish, not fundamentals.

### UX Refinements Requested

**1. Snap-to-extrema (both clicks)**

When clicking to mark a swing point, auto-select the candle with the best extrema (highest high or lowest low) within a tolerance radius. Intent is clear — user is marking structure, not pixel-hunting.

Scale-aware tolerance:
| Scale | Snap Radius |
|-------|-------------|
| XL | 4-5 bars |
| L | 5-10 bars |
| M | ~20 bars |
| S | ~30 bars |

Only prompt for re-click if truly ambiguous.

**2. Fibonacci preview before confirm**

Before confirming annotation, show horizontal lines at key levels (0, 0.382, 1, 2) so user can visually verify current price relationship to the swing range. Currently eyeballing reference ranges.

**3. XL reference panel aspect ratio**

When XL panel shrinks to reference size, it stretches horizontally. Should maintain aspect ratio so price levels visually anchor correctly.

**4. Non-blocking confirmation**

Current confirmation modal blocks entire screen and fades background charts. User loses visual context.

Better: Show confirmation in side panel (right side has space). Add hotkeys for quick accept/reject/next so user can stay in flow without mouse.

### Notes

- First annotation session data is incorrect (user learning the tool). Can be deleted.

### Key Quote

"Other than these it appears to be a great tool!!"

---

## December 12, 2025 - Ground Truth Annotation Workflow

**Context:** UX feedback after P0 blockers resolved (#22 full dataset loading, #24 resolution-agnostic design). Validator working on large datasets.

### Core Insight

Current validation paradigm (system shows swings → user validates) has a fundamental limitation: **can't catch false negatives**. User can only react to what system shows, not surface what system missed.

### Proposed Paradigm Shift

**Invert control:** User marks swings blind → compare against system output → systematic analysis.

This captures:
- False negatives (user marked, system missed) — *previously invisible*
- False positives (system detected, user didn't mark)
- Ranking gaps (both found it, different priority)

### Annotation Workflow

**Two-click swing marking:**
1. Click candle A, click candle B
2. System infers direction from price relationship:
   - First high > second high → bull reference (downswing) → green line
   - First low < second low → bear reference (upswing) → red line
3. Visual feedback: colored line connecting the points
4. Confirm or click elsewhere to start new annotation
5. "Next" advances to next scale/window

**Cascading scale progression:**
```
XL (full window) → mark all XL swings
    ↓
XL (reference) + L (main) → mark all L swings
    ↓
L (reference) + M (main) → mark all M swings
    ↓
M (reference) + S (main) → mark all S swings
    ↓
Window complete → next random window
```

Each completed scale becomes a reference panel while marking the next smaller scale.

### Window Parameter Clarification

`--window 50000` should show all 50K bars at XL level (aggregated), then cascade down through scales. Window defines data scope; XL shows full scope.

### Decision: Replace, Not Supplement

Ground truth annotation replaces current thumbs-up/down validator. The annotation approach is strictly more signal per interaction. Current validator is subset of what we learn from ground truth comparison. Git history preserves old approach if needed.

### Web UX Validation

User confirms web-based validator is "much more responsive and clean looking" than matplotlib harness. Pivot to HTML validated.

### Looking Ahead

User optimistic about trajectory: fix remaining swing detection issues → gather clean swing data → move to heuristics and rule learning phase.

### Key Quote

"Right now it's hard for me to give you full feedback. There are many scenarios — I see a swing but you didn't identify it, you show me a swing but I don't think it's real, you show me a swing that's good but not the best. How do we differentiate between them?"

---

## December 12, 2025 - Lightweight Validator First Test

**Context:** First dogfood of new lightweight HTML validator on small dataset, attempted large dataset (es-1m.csv, 6M bars)

### What Worked

- UX looks polished and professional
- Snappy and easy to test on small datasets
- Voting workflow functional
- 6 samples validated in session (5 approved, 2 marked "found_right_swings: false" with comments)

### Blockers

1. **Load time on large datasets:** 6M bar file took 7+ minutes before user interrupted. Traced to `scale_calibrator.py` still using legacy O(N²) `BullReferenceDetector` instead of new O(N log N) `swing_detector.py`.

2. **Integration gap:** The O(N log N) rewrite (signed off Dec 11) was never wired into the scale calibrator path.

### Feature Requests (pending performance fix)

- **P0:** "No reference swings in this range" option - sometimes detected swings are technically correct but don't feel right. Need to capture these for heuristic refinement.
- **P1:** Progressive loading with diverse windows - load 100k, start UX, rotate through different time windows for regime diversity.
- **P1:** Scale ordering XL→L→M→S - larger scale context helps evaluate smaller scale swings.
- **TBD:** Additional features pending large dataset testing.

### User Direction

Stage the work: fix performance first, then separate interview for features once large datasets are testable.

### Key Quote

"The O(N² issue is something we should fix anyway because wouldn't generator depend on it as well? The north star of the project would be in jeopardy if we didn't fix that."

---

## December 11, 2025 - Comprehensive Dogfooding Results

**Context:** Systematic dogfooding of visualization harness using test plan (docs/product/dog_food_wishlist.md)

### Coverage

| Category | Status | Notes |
|----------|--------|-------|
| 1. Startup & Init | Partial Pass | Auto-start broken, speed flag ignored |
| 2. CLI Playback | Blocked | CLI loses focus to Matplotlib |
| 3. Keyboard Shortcuts | Partial | Logged but no visible effect |
| 4. Panel Layout | Pass | Expansion/collapse works |
| 5. Swing Visibility | Partial | Cycling works, brackets don't update view |
| 6. Visualization Quality | Issues | Clutter, overlap, poor scale differentiation |
| 7-11 | Not Tested | Blocked by playback issues |

### Critical Blockers

1. **Playback appears frozen.** Auto-pause fires constantly (S-level events), no visible progress even at 32x speed.
2. **Timestamp errors.** Console shows: `new bar timestamp must be greater than last bar timestamp`
3. **Scale calibration clusters.** S/M close together, L/XL close together. Not four distinct regimes.
4. **Visual clutter.** 50+ lines when showing all swings. Overlapping labels.

### What Works

- Basic startup and help
- Panel expansion/collapse (1-4, 0, ESC)
- Candlestick rendering
- Fibonacci level positions
- Window resizing

### User's Pivot Proposal

User suggests considering a **lightweight HTML-based validation tool** instead of fixing the Matplotlib harness:

- Random sample time intervals at each scale
- Present top 3 candidate swings one at a time
- Thumbs-up/thumbs-down voting per swing
- "Did we find the right top 3?" final question
- Build structured validation dataset

**Rationale:** "The visualization is a means to validate and refine the detection logic, not the end product."

**Framing:** "Strong opinion, weakly held. Explicitly for product/architect to think through."

### Key Quote

"The harness demonstrates that the swing detection logic is doing 'something non-trivial.' However, the current Matplotlib-based visualization harness has a large number of usability, performance, and visual clarity issues."

---

## December 11, 2025 - Validation Experience Feedback

**Context:** Post-usage feedback after ~1 day of hands-on validation testing

### Key Findings

**Detection Logic:** Working. "Detection accuracy is pretty good in the tests I did."

**Primary Blockers:**
1. Too noisy at small scales (33 active swings on S-scale)
2. Too slow for validation (month takes >1 hour)
3. Visual noise from bar density (XL showing 1m bars)
4. Glitchy/buggy feel ("feels like an intern project")

**User Confidence:** "There are issues but they're fixable"

### Agreed Direction
1. Dynamic bar aggregation (40-60 candles per quadrant)
2. Event-skip mode (jump to next structural event)
3. S-scale swing cap (top 3-5 swings)
4. Stability audit (fix state transition bugs)

**Target:** Traverse a month in minutes, not hours.

---

## December 10, 2025 - Product Direction Sync

**Context:** Following architect proposal to start Market Data Generator

### Key Clarifications

**User Position:** Primary objective is validation of swing detection on historical data, NOT generation.

**Core Concern:** "The hard problem is correctness and robustness of the structural logic."

**Risk:** Layering complexity before core validation creates more risk than value.

### Outcome
- Generator development explicitly deferred
- Progress gated by correctness, not calendar
- Visual validation through expert review

---

## December 9, 2025 - Initial Swing Visualization Harness

**Context:** Determining what to build after foundational modules complete

### Primary Need

Visualization to watch system interpret market structure step by step. Build confidence that detection logic is stable enough for behavioral modeling.

### Key Requirements

1. **Multi-scale visualization:** Four synchronized views (S, M, L, XL)
2. **Swing selection:** One swing per view, prioritize events
3. **Event classification:** Minor (level crosses), Major (completion/invalidation)
4. **Swing lifecycle:** Completed/invalidated swings remain until replaced
5. **Cross-scale independence:** No cascade between scales
6. **Playback:** Manual stepping and auto mode with pause on events

### Success Criteria
- Load dataset and observe four-scale visualization
- See clear annotations on events
- Identify edge cases in swing detection
- Build confidence for behavioral modeling

### Key Quote
"I want to be able to watch the system think, step by step."
