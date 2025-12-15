# Architect Notes

## Current Phase: Ground Truth Collection - Active Use

**Status:** Tooling complete. Ready for sustained annotation sessions.
**Owner:** User (annotation), Product (analysis strategy)
**Blocker:** None

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | O(N log N), vectorized, production-ready |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode complete |
| Review Mode | Healthy | 3-phase feedback with preset FN explanations, FP quick-select |
| Session Management | Healthy | Timestamp filenames, keep/discard workflow, instant window loading |
| Comparison Analyzer | Healthy | FP/FN detection with matching |
| Bar Aggregator | Healthy | Multi-scale aggregation |
| Scale Calibrator | Healthy | Quartile-based S/M/L/XL boundaries |
| Test Suite | Healthy | 402 tests passing, scaling tests stabilized |

---

## Recent Improvements (Accepted Dec 15)

| Issue | Feature | Impact |
|-------|---------|--------|
| #53 | Timestamp-based session filenames | Human-readable names, chronological sorting |
| #52 | FP quick-select fix + 5-button UI | One-click dismiss with keyboard shortcuts |
| #51 | FP quick-select buttons | Quick dismiss for common FP categories |
| #31 | Flaky test fix | Scaling tests now stable (multiple runs, min selection) |

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `Docs/Reference/user_guide.md` | Current | Updated Dec 15 with session filenames |
| `Docs/Reference/developer_guide.md` | Current | No changes needed |
| `CLAUDE.md` | Current | No changes needed |
| `Docs/State/architect_notes.md` | Current | This file |

**Documentation Priority:** Low. All features documented.

---

## Annotation Workflow (Ready for Use)

```bash
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random
```

1. Cascade through XL → L → M → S scales
2. Auto-redirect to Review Mode after S completes
3. Review matches, FP sample (quick-select buttons: 1-3, N, V), FN feedback (1-5 presets)
4. Optionally add session label
5. Keep or Discard session
6. Load next window (instant, <3s)

**Session files:** Timestamp-based names (`2025-dec-15-0830.json`) for easy organization.

---

## Codebase Summary

```
src/
├── swing_analysis/            # Core detection algorithms (6 files)
├── ground_truth_annotator/    # Web-based annotation tool (8 files)
├── data/                      # OHLC loading (2 files)
└── examples/                  # Demo scripts

tests/                         # 402 tests passing
```

**Key Metrics:**
- Test count: 402 passed, 2 skipped
- All scaling tests now stable

---

## Pending Decisions (Product)

| Question | Context |
|----------|---------|
| Annotation targets | How many sessions needed for statistically significant ground truth? |
| Rule iteration | How to translate Review Mode feedback into detector improvements? |
| **Trend-aware detection** | Recommend hybrid approach: `trend_context` param with auto/bullish/bearish/neutral modes. See `Docs/Comms/archive.md` Q-2025-12-15-1. Awaiting Product confirmation. |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S, M, L, XL)
- **Fibonacci levels:** 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars, <3s window transitions
- **Lean codebase:** Single tool (ground truth annotator) for validation workflow

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 15 | #31, #51, #52, #53 - Test stability, FP quick-select, session filenames | All Accepted |
| Dec 12 | #46-#50 - P1 UX fixes from annotation session | All Accepted |
| Dec 12 | #44 - Deprecated module removal | Accepted |
| Dec 12 | Review Mode epic (#38) - 5 issues | All accepted |
| Dec 12 | #32, #33, #34, #35, #37 - UX polish batch | All accepted |
| Dec 12 | #27-#30 - Ground truth annotation tool MVP | All accepted |
