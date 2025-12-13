# Product Direction

**Last Updated:** December 12, 2025
**Owner:** Product

---

## Current Objective

**Collect ground truth data.**

P1 UX blockers are resolved. The annotation tool is ready for quality data collection sessions.

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

**Where we are:** P1 UX blockers resolved. Annotation tool is production-ready.

**What's next:**
1. Run 5-10 quality annotation sessions across different market regimes
2. Analyze feedback patterns (FP categories, FN clusters)
3. Iterate detection rules based on patterns

**Key insight:** Tool friction eliminated. Ready to collect data at scale.
