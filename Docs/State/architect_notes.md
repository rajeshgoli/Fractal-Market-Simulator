# Architect Notes

## Current Phase: Ground Truth Collection - UX Fixes

**Status:** 4 P1 UX issues scoped from first annotation session
**Owner:** Engineering (implement #46-#49)
**Blocker:** None - issues ready for implementation

---

## Immediate Next Steps

| Issue | Title | Owner | Parallelism |
|-------|-------|-------|-------------|
| #46 | Fix inverted Fibonacci reference level labels | Engineering | Can parallelize |
| #47 | Add preset options for FN explanations | Engineering | Can parallelize |
| #48 | Add save confirmation and export button | Engineering | Can parallelize |
| #49 | Add session quality control (keep/discard) | Engineering | Sequential (has backend) |
| #50 | Preload next annotation window | Engineering | Sequential (has backend) |

**Recommendation:** Implement #46, #47, #48 in parallel (all frontend-only), then #49 and #50 (both have backend changes).

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | O(N log N), vectorized, production-ready |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode complete |
| Review Mode | Healthy | 3-phase feedback workflow operational |
| Comparison Analyzer | Healthy | FP/FN detection with matching |
| Bar Aggregator | Healthy | Multi-scale aggregation |
| Scale Calibrator | Healthy | Quartile-based S/M/L/XL boundaries |

**Removed Components (Issue #44):**
- `lightweight_swing_validator/` - superseded by ground truth annotator
- `visualization_harness/` - replaced by web-based annotation tool
- ~14,500 lines of deprecated code removed

---

## Codebase Summary

```
src/
├── swing_analysis/            # Core detection algorithms (6 files)
├── ground_truth_annotator/    # Web-based annotation tool (8 files)
├── data/                      # OHLC loading (2 files)
└── examples/                  # Demo scripts

tests/                         # 388 tests
```

**Key Metrics:**
- Test count: 388 passed, 2 skipped
- Ground truth annotator tests: 180
- Lines removed in cleanup: ~14,500

---

## Annotation Workflow (Ready for Use)

```bash
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random
```

1. Cascade through XL → L → M → S scales
2. Auto-redirect to Review Mode after S completes
3. Review matches, FP sample, FN feedback
4. Export feedback JSON
5. Load next window (random offset) to continue

---

## Pending Decisions (Product)

| Question | Context |
|----------|---------|
| Annotation targets | How many sessions needed for statistically significant ground truth? |
| Rule iteration | How to translate Review Mode feedback into detector improvements? |

---

## Documentation Status

| Document | Status |
|----------|--------|
| `Docs/Reference/user_guide.md` | Current (deprecated sections removed) |
| `Docs/Reference/developer_guide.md` | Current (updated for cleanup) |
| `CLAUDE.md` | Current (deprecated references removed) |
| `Docs/State/architect_notes.md` | Current (this file) |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S, M, L, XL)
- **Fibonacci levels:** 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars
- **Lean codebase:** Single tool (ground truth annotator) for validation workflow

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 12 | #46-#50 - P1 UX fixes from annotation session | Scoped |
| Dec 12 | #44 - Deprecated module removal | Accepted |
| Dec 12 | Review Mode epic (#38) - 5 issues | All accepted |
| Dec 12 | #32, #33, #34, #35, #37 - UX polish batch | All accepted |
| Dec 12 | #27-#30 - Ground truth annotation tool MVP | All accepted |
