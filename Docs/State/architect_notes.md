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
- Calibration-first playback for causal evaluation
- Backend-controlled data boundary for replay (single source of truth)
- Incremental detection for playback (O(active) vs O(N log N))

**Known debt:**
- `detect_swings()` function (~333 LOC) — monolithic; filter pipeline not extracted

**Cleanup tasks (deferred):**
- Delete `Docs/Archive/Proposals/Discretization/` once discretization pipeline is complete and documented in user_guide + developer_guide

---

## Current Phase: User Testing — Active

### Status

**Replay View v2 is feature-complete.** All observation capture infrastructure is operational:
- Always-on feedback capture with rich context snapshots
- Trigger explanations for all event types (SWING_FORMED, INVALIDATED, COMPLETED, LEVEL_CROSS)
- Critical bug fix: `get_level_band()` now correctly identifies Fib bands (was causing all swings to filter as "redundant")
- Incremental detector deduplicates swings using same pivot

**Current milestone:** User testing to collect detection quality observations.

---

## Recently Completed (Dec 17, PM — Review 2)

| Issue | Feature | Verdict |
|-------|---------|---------|
| #122 | Trigger explanation for replay events | Accepted |
| #123 | Always-on feedback capture with rich context | Accepted |
| #126 | **Critical:** Fix `get_level_band()` bug causing valid swings to be filtered | Accepted |
| #127 | Store offset in playback_feedback.json | Accepted |
| #128 | Deduplicate swings using same pivot in incremental detector | Accepted |

**Key fixes:**

1. **get_level_band() Bug (#126):**
   - Root cause: Code assumed `levels[0]` was lowest price, but levels are ordered by **multiplier** (-0.1, 0, 0.1, ..., 1), not price
   - Impact: ALL swings returned band `-999`, making them all "redundant" with anchor
   - Result: Only largest swing survived filtering — explains "calibration found only 1 XL swing"
   - Fix: Check against actual lowest price in levels list

2. **Incremental Detector Deduplication (#128):**
   - Problem: New lows were paired with ALL valid highs, creating duplicate swings
   - Fix: Check if swing with same pivot already exists before creating new one
   - Result: Only optimal pairing kept; suboptimal duplicates prevented

3. **Trigger Explanations (#122):**
   - Human-readable explanations for why events fired
   - Examples: "Price entered zone below 0.382", "Pivot exceeded — swing invalidated"
   - Replaces "No separation data available" with meaningful content

4. **Always-On Feedback (#123):**
   - Feedback box visible at all times (not just during linger)
   - Auto-pause on focus
   - Rich context: state, offset, bars since calibration, swing counts, event context

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | **Healthy** | `get_level_band()` fix deployed |
| Incremental Detector | **Healthy** | Deduplication added |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode |
| Discretization Pipeline | Healthy | Core complete, visual overlay done |
| Replay View | **Complete** | Full observation workflow with feedback capture |
| Test Suite | Healthy | 834 tests passing |
| Documentation | **Current** | Both guides updated Dec 17 |

---

## Next Steps

### 1. User Testing (Active)

With observation workflow complete and critical bugs fixed, user can:
- Run forward playback with true incremental detection
- See meaningful trigger explanations for all events
- Capture observations at any time via always-on feedback
- Verify that calibration now finds expected swing counts

**Observations to collect:**
- Cascading swing detection noise patterns
- False positives after target achieved
- Detection timing issues
- Any remaining missing swing issues

### 2. Detection Algorithm Improvements (Pending Data)

Per `product_direction.md`, two observations pending investigation:
- **Observation A:** Cascading swing detection (smaller swings fire before larger)
- **Observation B:** False positives after target achieved (2x extension)

Wait for concrete examples via feedback capture before designing fixes.

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `Docs/Reference/developer_guide.md` | **Current** | Updated Dec 17 |
| `Docs/Reference/user_guide.md` | **Current** | Updated Dec 17 |
| `CLAUDE.md` | Current | - |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S/M/L/XL)
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars detection; O(active) per-bar for replay
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)
- **Backend-controlled boundaries:** Backend owns data visibility; frontend visualizes
- **Event filtering:** Stale events suppressed at API layer, not detection layer

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 17 | #122, #123, #126, #127, #128 — Trigger explanations, always-on feedback, level band fix, offset storage, deduplication | All Accepted |
| Dec 17 | #116, #118, #119, #120, #121 — Feedback capture, collision fix, lazy sessions, incremental detection, stale filtering | All Accepted |
| Dec 17 | #112, #113, #114, #115, #117 — Replay View v2 architecture fix + usability | All Accepted |
| Dec 17 | Q-2025-12-17-1 — Feedback capture schema design | Separate file, playback_feedback.json |
| Dec 17 | Q-2025-12-17-2 — Playback redesign architecture | Backend-controlled data boundary |
| Dec 17 | #101, #102, #104, #105, #111 — Calibration, forward playback, event nav, scale toggles | All Accepted, Epic #99 closed |
| Dec 17 | #100, #103, #107, #108, #109 — Zero swings fix, speed control, swing overlay, multi-swing nav | All Accepted |
| Dec 16 | #84, #85, #86, #87, #89 — Replay View complete | All Accepted |
| Dec 16 | #78, #79, #81, #82, #83 — Discretization overlay, validation | All Accepted |
| Dec 16 | #73, #74, #75, #76, #77 — Discretization core | All Accepted |
| Dec 16 | #68, #69, #70, #71 — Phase 3 + Architecture Overhaul | All Accepted |
