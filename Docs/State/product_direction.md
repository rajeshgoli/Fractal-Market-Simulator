# Product Direction

**Last Updated:** December 12, 2025
**Owner:** Product

---

## Current Objective

**Collect ground truth data through annotation sessions.**

The tooling is complete. Review Mode, session flow, and codebase cleanup are done. Now it's time to use the tool to build a ground truth dataset and collect qualitative feedback on detection quality.

---

## Why This Is Highest Leverage

The detector is miscalibrated (250x more detections than human expert). We have:
- Two-click annotation workflow
- Cascading scale progression (XL → L → M → S)
- Review Mode with FP/FN feedback collection
- Random window selection for dataset diversity
- Structured export for rule iteration

**The tool is ready. The bottleneck is now data collection.** Multiple annotation sessions across different market regimes will reveal patterns in detection errors that inform rule refinement.

---

## Immediate Next Steps

### 1. Run Annotation Sessions

```bash
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random
```

**Target:** 5-10 complete sessions (XL → S + Review Mode) to build initial ground truth corpus.

### 2. Review Feedback Patterns

After sessions, analyze exported JSON for:
- Common FP categories (noise patterns)
- FN explanations (what the system misses)
- Match confirmation rate

### 3. Iterate Detection Rules

Use feedback to refine `swing_detector.py` parameters or logic.

---

## P2: Annotation UX (Deferred)

### Zoom/Pan for S-Scale

**Problem:** Snap is finicky at S-scale. May need horizontal (time) and vertical (price) zoom plus pan.

**Status:** Deferred until annotation sessions reveal if this is blocking.

### Snap at Chart Edges

**Problem:** Snap finicky when swing is at chart edge. Snap radius may extend beyond visible data.

**Status:** Deferred until annotation sessions reveal if this is blocking.

---

## Delivered (This Cycle)

### Ground Truth Annotation Tool (Complete)

- Two-click swing marking with direction inference
- Cascading scale progression (XL → L → M → S)
- Snap-to-extrema with price proximity
- Fibonacci preview lines
- Non-blocking inline confirmation with hotkeys
- Comparison analysis (FP/FN detection)

### Review Mode (Complete)

- Phase 1: Match review with correct/incorrect feedback
- Phase 2: Stratified FP sample with noise/valid labels
- Phase 3: FN feedback with required explanations
- Session summary with statistics
- JSON/CSV export for rule iteration

### Session Flow (Complete)

- Random window selection (`--offset random`)
- "Load Next Window" for continuous sessions
- Auto-redirect to Review Mode after cascade

### Codebase Cleanup (Complete)

- Removed deprecated `lightweight_swing_validator/` (~8 files)
- Removed deprecated `visualization_harness/` (~15 files)
- ~14,500 lines of dead code eliminated
- Single focused tool: ground truth annotator

---

## Completed Issues

| Issue | Description | Result |
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
| #24 | Resolution-agnostic design | Done |
| #22 | Full dataset loading | Done |

---

## Success Criteria (This Phase)

1. ~~User can mark swings via two-click annotation~~ ✓
2. ~~Cascading scale workflow operational (XL → L → M → S)~~ ✓
3. ~~Annotations stored and comparable against system output~~ ✓
4. ~~Analysis report surfaces false negatives, false positives~~ ✓
5. ~~Snap-to-extrema removes pixel-hunting friction~~ ✓
6. ~~Fib preview enables visual validation before confirm~~ ✓
7. ~~Non-blocking confirmation with hotkeys for flow~~ ✓
8. ~~Review Mode: matches, FP sample, FN review with feedback~~ ✓
9. ~~Structured export for rule iteration~~ ✓
10. ~~Session continuation with random windows~~ ✓

**All success criteria met. Tool is production-ready for annotation sessions.**

---

## Deferred

- Generator work — pending validated swing detection and ground truth data
- Zoom/pan UX — deferred until blocking in practice
- Edge snap fixes — deferred until blocking in practice

---

## Checkpoint Trigger

**When to invoke Product:**
- After 5+ annotation sessions reveal feedback patterns
- When ready to translate feedback into detection rule changes
- If P2 UX issues prove blocking during annotation

---

## Session Context (for next conversation)

**Where we are:** Tooling complete. Ground truth annotator with Review Mode and session flow is production-ready. Codebase cleaned up (~14,500 lines removed).

**What's next:**
1. Run annotation sessions to collect ground truth data
2. Analyze Review Mode feedback for patterns
3. Use patterns to refine detection rules
4. Iterate: better rules → cleaner detections → validate at scale

**Key insight:** The tool-building phase is done. Now entering the data collection phase.
