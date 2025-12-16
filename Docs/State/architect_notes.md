# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Multi-scale (S/M/L/XL) with independent processing
- Fibonacci-based structural analysis (not arbitrary thresholds)
- Resolution-agnostic (1m to 1mo)
- Ground truth annotation as validation mechanism
- Sequential XL→L→M→S detection with `larger_swings` context passing

**Known debt:**
- `detect_swings()` function (~333 LOC) — monolithic; filter pipeline not extracted
- No other significant debt after architecture overhaul

**Cleanup tasks (deferred):**
- Delete `Docs/Archive/Proposals/Discretization/` once discretization pipeline is complete and documented in user_guide + developer_guide (exploratory drafts no longer needed)

---

## Current Phase: Discretization Pipeline

**Active work stream:**

**Discretization Pipeline Milestone 1** (#72)
- Build discretizer to convert OHLC + swings → structural event log
- Enables measurement of North Star rules as hypotheses
- Owner: Engineering

**Implementation order:**
```
#73, #74, #75 (parallel) → #76 (depends on all) → #77, #78 (parallel) → #79
```

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | Phase 1 (adjust_extrema) + Phase 2 (quota) + Phase 3 (FIB confluence/separation) complete |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode + skip scales + schema v4 |
| Test Suite | Healthy | 561 tests passing |
| Documentation | Current | user_guide.md and developer_guide.md updated |

---

## Recent Completions

### Architecture Overhaul (Dec 15)

**#69 - Dead Code Elimination:**
- Deleted `src/validation/` (923 LOC)
- Deleted `src/data/loader.py` (437 LOC)
- Deleted `src/examples/` (71 LOC)
- Removed deprecated SwingType enum, max_rank parameter
- Centralized FIB constants in `constants.py`

**#70 - Consolidate Duplication:**
- Created `DirectionalReferenceDetector` base class (`reference_detector.py`: 575 LOC)
- Reduced `bull_reference_detector.py` from 1,244 to 407 LOC
- Created `csv_utils.py` for CSV field escaping

**#71 - Standard Library Migration:**
- Removed custom `SparseTable` class (uses suffix arrays)
- Added `ReferenceSwing` dataclass with typed properties
- (Filter pipeline extraction deferred — acceptable debt)

### Phase 3 Endpoint Selection (#68)

**Structural Separation Gate:**
- `is_structurally_separated()` validates consecutive swings ≥1 FIB level apart
- Uses extended symmetric grid: 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0
- Fallback for XL/window edges (N-bar + price separation)

**FIB Confluence Scoring:**
- `score_swing_fib_confluence()` scores endpoints by proximity to FIB levels
- New `ReferenceSwing` dataclass with `fib_confluence_score`, `structurally_separated`, `containing_swing_id`

**Architecture Change:**
- Detection now sequential: XL → L → M → S
- `larger_swings` parameter passes context to subsequent scales

---

## Discretization Pipeline Design (Milestone 1)

**Epic:** #72

### Purpose

Convert continuous OHLC + detected swings → log of structural events. This enables:
- **Measurement:** Validate North Star rules empirically (treat as hypotheses, not axioms)
- **Future generation:** Foundation for synthetic market data (deferred milestones)

### Design Synthesis (Dec 2025)

Five independent proposals were generated and synthesized. All converged on:
- Reject per-bar tokenization (too noisy, invites overfitting)
- Embrace structural events (~50K-100K events from 6M bars)
- Use oriented Fibonacci coordinates (reference frames per swing)
- Preserve hierarchy (XL→L→M→S) without encoding coupling rules
- Separate structure from path (discrete events vs. continuous rendering)
- Measurement before generation (falsification is a feature)

Key insight: **Discretize commitments, not pixels.**

### Architecture Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Swing detection dependency | Pre-computed swings | Separation of concerns |
| Incremental vs batch | **Batch-only** | Streaming adds complexity; corpus processing is goal |
| Cross-scale coupling | **None in discretizer** | Per-scale logs independent |
| Level set | **Config-driven** | Accept `level_set` parameter; version tracked |
| Crossing semantics | **Config-driven** | Default `close_cross`; configurable |
| Storage format | JSON primary | Inspectable during development |
| Visualization | Extend Ground Truth Annotator | Already loads OHLC + swings |
| Testing | Unit + Integration + Sanity | Synthetic + ES-1m + comparison |

### Schema Extensions

| Component | Purpose | Fields |
|-----------|---------|--------|
| `DiscretizationConfig` | Corpus comparability | level_set, level_set_version, crossing_semantics, invalidation_thresholds, discretizer_version |
| `EffortAnnotation` | Wyckoff-style effort | dwell_bars, test_count, max_probe_r |
| `ShockAnnotation` | Tail/impulsive behavior | levels_jumped, range_multiple, gap_multiple, is_gap |
| `ParentContext` | Cross-scale context | parent scale, swing_id, band, direction, ratio |

### Key Components

1. **ReferenceFrame** (#73) — Oriented coordinate system with ratio()/price()
2. **Level Set** (#74) — Extended Fib levels including negative (stop-run territory)
3. **Event Schema** (#75) — LEVEL_CROSS, COMPLETION, INVALIDATION + side-channels
4. **Discretizer** (#76) — Batch processing: config-driven levels/semantics
5. **Log I/O** (#77) — JSON persistence with nested dataclass handling
6. **Visual Overlay** (#78) — Verification mode with shock visualization
7. **Validation** (#79) — Manual verification + sanity comparison

### Follow-On: Hypothesis Baseline (#80)

After M1 completes, measure baseline statistics:

| Hypothesis | What it tests |
|------------|---------------|
| H1: Completion conditional on band | P(completion \| ext_high) >> P(completion \| mid_retrace) |
| H2: Frustration rule | P(invalidation \| test_count > 3) elevated |
| H3: Void transit time | Decision corridor (1.382-1.618) traversed faster |
| H4: Downward causality | L behavior differs based on XL band |
| H5: Shock clustering | Shocks cluster in time (not uniform) |

---

## Detection Pipeline (Current State)

```
Sequential scale processing: XL → L → M → S

Per scale:
1. Swing detection (vectorized, O(N log N))
2. Pairing and validation
3. Best extrema adjustment ← Phase 1 (DONE)
4. Protection validation (with adjusted endpoints)
5. Size filter (min_candle_ratio, min_range_pct)
6. Prominence filter (min_prominence)
7. Structural separation gate ← Phase 3 (DONE)
8. Redundancy filtering
9. Fib confluence scoring ← Phase 3 (DONE)
10. Quota filter ← Phase 2 (DONE)
11. Final ranking
```

---

## Documentation Status

| Document | Status |
|----------|--------|
| `Docs/Reference/user_guide.md` | Current |
| `Docs/Reference/developer_guide.md` | Current |
| `CLAUDE.md` | Current |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S, M, L, XL)
- **Fibonacci levels:** 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars, <3s window transitions
- **Lean codebase:** 3 modules (data, swing_analysis, ground_truth_annotator)

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 16 | #68, #69, #70, #71 — Phase 3 + Architecture Overhaul | All Accepted |
| Dec 16 | Discretization proposal synthesis (5 agents) | Converged → Schema extensions |
| Dec 16 | Schema extensions: EffortAnnotation, ShockAnnotation, ParentContext | Added to #75 |
| Dec 15 | Discretization Proposal F1: Issue decomposition | Accepted → Epic #72 |
| Dec 15 | Q-2025-12-15-2 (FIB structural separation): Feasibility | Feasible → Phase 3 |
| Dec 15 | #59-#66 — Annotation UX + Filters + Endpoint Selection | All Accepted |
| Dec 12 | Review Mode epic (#38) | All Accepted |
