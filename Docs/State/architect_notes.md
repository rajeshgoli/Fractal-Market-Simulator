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
- Discretization: structural events, not per-bar tokens

**Known debt:**
- `detect_swings()` function (~333 LOC) — monolithic; filter pipeline not extracted
- Flaky performance test (`test_performance_scaling_is_nlogn`) — passes in isolation, fails occasionally in full suite
- `_detect_level_crossings()` fallback — `open_close_cross` and `wick_touch` semantics not fully implemented (fall back to `close_cross`)

**Cleanup tasks (deferred):**
- Delete `Docs/Archive/Proposals/Discretization/` once discretization pipeline is complete and documented in user_guide + developer_guide (exploratory drafts no longer needed)

---

## Current Phase: Replay View

**Active work stream:** Replay View (#82-#87) — Temporal debugging tool for swing detection validation

### Issue Status

| Issue | Component | Status | Priority |
|-------|-----------|--------|----------|
| #82 | SWING_FORMED explanation enrichment | **Next** | P0 (blocking) |
| #83 | Windowed events API | Pending | P1 |
| #84 | Split view + aggregation | Pending | P1 |
| #85 | Playback controls | Pending | P1 |
| #86 | Event-driven linger + timer | Pending | P2 |
| #87 | Swing explanation panel | Pending | P2 |

**Critical path:** #82 → #84 → #86 → #87

### Architecture Assessment

Spec: `Docs/Working/replay_view_spec.md`
Analysis: `Docs/Working/replay_view_architecture.md`

**Key decisions:**
- Timer duration: 30 seconds (longer dwell aids comprehension)
- Multiple events at same bar: Queue, show sequentially
- Explanation generation: At discretization time, not API read time
- Split view: Two independent lightweight-charts instances with shared time sync

**Dependencies:**
- Leverages existing discretization.html (~1100 LOC reusable)
- Uses existing API endpoints (`/api/discretization/*`)
- Uses `BarAggregator` for chart aggregation

---

## Previous Phase: Discretization Pipeline

**Work stream:** Milestone 1 (#72) — Core implementation complete

| Issue | Component | Status |
|-------|-----------|--------|
| #73 | ReferenceFrame | Complete |
| #74 | Level Set Constants | Complete |
| #75 | DiscretizationEvent Schema | Complete |
| #76 | Discretizer Core | Complete |
| #77 | Event Log I/O | Complete |
| #78 | Visual Overlay | Complete |
| #79 | Validation | Pending |

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | Phase 1-3 complete |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode |
| Discretization Pipeline | Healthy | Core complete, visual overlay done |
| Test Suite | Healthy | 733 tests passing (1 flaky perf test) |
| Documentation | Current | user_guide.md and developer_guide.md updated |

---

## Architecture Highlights

### Replay View (New)

**Purpose:** Trust-building tool that shows *why* swings are detected.

**Key design decisions:**
- **Split view** — Two charts with independent aggregation for natural zoom levels
- **Event-driven linger** — Auto-pause on SWING_FORMED to explain detection
- **30s timer wheel** — Visual countdown before auto-resume
- **Explanation panel** — Shows endpoints, size, scale reason, separation details

### Discretization Pipeline

**Purpose:** Convert OHLC + swings → structural event log for hypothesis testing.

**Key design decisions:**
- **Batch-only** — No streaming complexity; corpus processing is goal
- **Per-scale independence** — No cross-scale coupling in discretizer; analysis is post-hoc
- **Config-driven** — Level set, crossing semantics, thresholds all configurable
- **Self-describing** — Each log embeds full config for corpus comparability
- **Side-channels** — EffortAnnotation, ShockAnnotation, ParentContext enable rich queries

**Event Types:**
- `LEVEL_CROSS` — Price crossed a Fibonacci level
- `LEVEL_TEST` — Price approached but didn't cross
- `COMPLETION` — Ratio reached 2.0
- `INVALIDATION` — Ratio crossed below threshold
- `SWING_FORMED` / `SWING_TERMINATED` — Lifecycle events

**Level Set (v1.0):** 16 levels from -0.15 (deep stop-run) to 2.236 (extended completion)

### ReferenceFrame Abstraction

Unified coordinate system for bull/bear swings:
- `ratio = 0`: Defended pivot (stop level)
- `ratio = 1`: Origin extremum
- `ratio = 2`: Completion target
- Negative ratios: Stop-run territory

---

## Follow-On Work

### After Replay View

**Hypothesis Baseline (#80)** — Measure baseline statistics:

| Hypothesis | What it tests |
|------------|---------------|
| H1: Completion conditional on band | P(completion \| ext_high) >> P(completion \| mid_retrace) |
| H2: Frustration rule | P(invalidation \| test_count > 3) elevated |
| H3: Void transit time | Decision corridor (1.382-1.618) traversed faster |
| H4: Downward causality | L behavior differs based on XL band |
| H5: Shock clustering | Shocks cluster in time (not uniform) |

---

## Documentation Status

| Document | Status |
|----------|--------|
| `Docs/Reference/user_guide.md` | Current |
| `Docs/Reference/developer_guide.md` | Current (discretization section added) |
| `CLAUDE.md` | Current |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S, M, L, XL)
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars detection, <1hr for discretization (target)
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 16 | Replay View spec assessment | Feasible → Issues #82-#87 created |
| Dec 16 | #73, #74, #75, #76, #77 — Discretization core implementation | All Accepted |
| Dec 16 | #68, #69, #70, #71 — Phase 3 + Architecture Overhaul | All Accepted |
| Dec 16 | Discretization proposal synthesis (5 agents) | Converged → Schema extensions |
| Dec 15 | Discretization Proposal F1: Issue decomposition | Accepted → Epic #72 |
| Dec 15 | #59-#66 — Annotation UX + Filters + Endpoint Selection | All Accepted |
| Dec 12 | Review Mode epic (#38) | All Accepted |
