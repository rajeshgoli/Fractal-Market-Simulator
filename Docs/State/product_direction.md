# Product Direction

**Last Updated:** December 13, 2025
**Owner:** Product

---

## Current Objective

**Collect ground truth data through annotation sessions.**

All tooling is complete: annotation workflow, Review Mode (3-phase feedback with UI), and session flow with random windows. The tool-building phase is done. Now entering data collection.

---

## Why This Is Highest Leverage

The detector is miscalibrated (250x more detections than human expert). We have:
- Two-click annotation workflow
- Cascading scale progression (XL → L → M → S)
- Review Mode with FP/FN feedback collection (UI complete)
- Random window selection for dataset diversity
- Structured export for rule iteration

**The tool is ready. The bottleneck is now data collection.** Multiple annotation sessions across different market regimes will reveal patterns in detection errors.

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

## P2: Annotation UX (Deferred)

| Item | Problem | Status |
|------|---------|--------|
| Zoom/Pan for S-Scale | Snap finicky at small scale | Deferred until blocking |
| Snap at Chart Edges | Snap radius may extend beyond visible data | Deferred until blocking |

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

## Session Context

**Where we are:** Tooling complete. Ground truth annotator with Review Mode and session flow is production-ready. Codebase cleaned up (~14,500 lines removed).

**What's next:**
1. Run annotation sessions to collect ground truth data
2. Analyze Review Mode feedback for patterns
3. Use patterns to refine detection rules
4. Iterate: better rules → cleaner detections → validate at scale

**Key insight:** The tool-building phase is done. Now entering the data collection phase.
