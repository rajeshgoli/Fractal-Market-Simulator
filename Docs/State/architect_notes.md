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
| Review Mode | Healthy | 3-phase feedback with preset FN explanations |
| Session Management | Healthy | Keep/discard quality control, instant window loading |
| Comparison Analyzer | Healthy | FP/FN detection with matching |
| Bar Aggregator | Healthy | Multi-scale aggregation |
| Scale Calibrator | Healthy | Quartile-based S/M/L/XL boundaries |

---

## Recent Improvements (Accepted Dec 12)

| Issue | Feature | Impact |
|-------|---------|--------|
| #50 | DataFrame caching | 30-40s → <3s on next window load |
| #49 | Session quality control | Keep/discard sessions for analysis filtering |
| #48 | Save confirmation + export | Toast feedback, in-annotation JSON export |
| #47 | FN preset buttons | 1-5 keyboard shortcuts for common explanations |
| #46 | Fibonacci level fix | Correct 0 at swing end, extensions beyond start |

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `Docs/Reference/user_guide.md` | Current | Updated Dec 12 |
| `Docs/Reference/developer_guide.md` | Current | Minor: mention cached_dataframe in AppState |
| `CLAUDE.md` | Current | No changes needed |
| `Docs/State/architect_notes.md` | Current | This file |

**Documentation Priority:** Low. All features work correctly; docs up to date.

---

## Annotation Workflow (Ready for Use)

```bash
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random
```

1. Cascade through XL → L → M → S scales
2. Auto-redirect to Review Mode after S completes
3. Review matches, FP sample, FN feedback (1-5 presets available)
4. Mark session as "Keep" or "Discard"
5. Export feedback JSON
6. Load next window (instant, <3s)

---

## Codebase Summary

```
src/
├── swing_analysis/            # Core detection algorithms (6 files)
├── ground_truth_annotator/    # Web-based annotation tool (8 files)
├── data/                      # OHLC loading (2 files)
└── examples/                  # Demo scripts

tests/                         # 396 tests (1 flaky, pre-existing)
```

**Key Metrics:**
- Test count: 395 passed, 2 skipped, 1 flaky (pre-existing)
- Flaky test: `test_scaling_factor` - passes in isolation, fails occasionally in suite

---

## Pending Decisions (Product)

| Question | Context |
|----------|---------|
| Annotation targets | How many sessions needed for statistically significant ground truth? |
| Rule iteration | How to translate Review Mode feedback into detector improvements? |

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
| Dec 12 | #46-#50 - P1 UX fixes from annotation session | All Accepted |
| Dec 12 | #44 - Deprecated module removal | Accepted |
| Dec 12 | Review Mode epic (#38) - 5 issues | All accepted |
| Dec 12 | #32, #33, #34, #35, #37 - UX polish batch | All accepted |
| Dec 12 | #27-#30 - Ground truth annotation tool MVP | All accepted |
