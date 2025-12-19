# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Multi-scale (S/M/L/XL) with independent processing → **Under Review** (see Swing Detection Rewrite)
- Fibonacci-based structural analysis (not arbitrary thresholds)
- Resolution-agnostic (1m to 1mo)
- Ground truth annotation as validation mechanism
- Sequential XL→L→M→S detection with `larger_swings` context passing → **Under Review**
- Discretization: structural events, not per-bar tokens
- Calibration-first playback for causal evaluation
- Backend-controlled data boundary for replay (single source of truth)
- Incremental detection for playback (O(active) vs O(N log N))
- Self-referential separation at XL scale (no larger_swings available)
- Candidate swings: pending 0.236 validation before promotion to reference

**Known debt:**
- `detect_swings()` function (~400 LOC) — monolithic; filter pipeline not extracted
- **Bull/bear asymmetric branching (#140 Phases 2-4)** — 38+ instances of `if direction == 'bull'` that should use symmetric ReferenceFrame coordinates. Critical bug fixed (Phase 1), but refactoring to use ReferenceFrame abstraction deferred.

**Cleanup tasks (deferred):**
- Delete `Docs/Archive/Proposals/Discretization/` once discretization pipeline is complete and documented in user_guide + developer_guide

---

## Current Phase: Swing Detection Rewrite — Ready for Implementation

### Proposal

**Document:** `Docs/Working/swing_detection_rewrite_spec.md`
**Status:** Approved — All clarifications resolved

### Feasibility Assessment

#### Problem Analysis: Valid

The spec correctly identifies real issues:

| Problem | Evidence | Severity |
|---------|----------|----------|
| Dual code paths | 2,274 LOC across two detectors; #139, #140 bugs | High |
| Bull/bear asymmetry | 26+ direction-specific branches in swing_analysis | High |
| S/M/L/XL mismatch | `valid_swings.md` describes 10-15 hierarchy levels | Medium |
| Magic numbers | Formation fib scattered, tolerances inconsistent | Medium |
| Events > Bars | Discretization produces more data than source | Blocking |

The dual-path divergence bugs (#139, #140) are symptomatic of a structural problem. Fixing them individually accumulates debt; a unified algorithm eliminates the class of bugs.

#### Solution Architecture: Sound

**Strengths:**

1. **Single incremental algorithm** — Eliminates lookahead bugs entirely. Calibration as `for bar in bars: process_bar(bar)` guarantees identical behavior to playback.

2. **Leverages existing ReferenceFrame** — The 125-line `reference_frame.py` already implements symmetric 0/1/2 coordinates. It's underutilized; the rewrite would make it central.

3. **SwingConfig centralizes parameters** — All magic numbers in one place. Testable. Auditable. Can be tuned without code changes.

4. **Hierarchical model matches reality** — `valid_swings.md` explicitly states hierarchy can be 10-15 levels deep. S/M/L/XL buckets were always a simplification; now they're a liability.

5. **Phased migration** — Not a big-bang rewrite. New core → Calibration loop → Integration → Cleanup.

#### Clarifications Resolved (Dec 18)

| Question | Resolution |
|----------|------------|
| **DAG vs Tree** | DAG confirmed. Multiple parents for structural context and tolerance calculation. NO automatic cascade — each swing invalidated only when its own 0 is violated. Children typically have higher defended pivots, so they invalidate before parents. |
| **Invalidation semantics** | Independent per-swing. Cascade only when swings share same defended pivot (simultaneous invalidation, not propagation). |
| **Golden dataset** | Not needed. Current detection has known bugs; user testing via replay mode validates new implementation. |
| **Ground truth** | Archive in git, delete locally. Can recreate via 5-10 replay sessions. |

#### Risk Assessment

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope creep | Medium | Strict Phase 1 boundaries |
| Regressions | Low | User testing via replay mode |
| Performance miss | Low | Incremental is O(active), should be fast |
| Extended timeline | Medium | User testing blocked until Phase 3 |

#### Verdict

**Approved for Implementation**

All blocking questions resolved. Engineering can proceed with Phase 1.

---

## Recently Completed (Dec 18 — Review 4)

| Issue | Feature | Verdict |
|-------|---------|---------|
| #138 | Endpoint optimization: bull swings find highest HIGH, bear swings find lowest LOW | Accepted |
| #140 (Phase 1) | Symmetric pre-formation protection in both detectors | Accepted |
| #139 | Pre-violated lows bug | Closed as resolved by #140 |

### Previous Review (Dec 18 — Review 3)

| Issue | Feature | Verdict |
|-------|---------|---------|
| #130 (+ regression) | Navigation decoupled from display count | Accepted |
| #131 (+ 3 follow-ups) | Stats panel toggle, swing H/L markers | Accepted |
| #133 | Self-referential separation for XL scale | Accepted |
| #134 | API modularization (3,514 → 550 lines in api.py) | Accepted |
| #136 | Endpoint optimization, candidate swings, protection tolerance | Accepted |

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | **Under Review** | Rewrite proposed |
| Incremental Detector | **Under Review** | Will be unified with batch |
| Ground Truth Annotator | Healthy | May be archived post-rewrite |
| Discretization Pipeline | Healthy | Core complete, visual overlay done |
| Replay View | Complete | Full observation workflow with feedback capture |
| API Layer | Refactored | 7 routers, clean separation |
| Test Suite | Healthy | 865 tests passing |
| Documentation | Current | Both guides updated Dec 18 |

---

## Next Steps

**Implementation Plan:** `Docs/Working/swing_detection_implementation_plan.md`

### Phase 1: Foundation (Parallel — 5 agents)

| Issue | Scope | Files |
|-------|-------|-------|
| #A | SwingConfig dataclass | `swing_config.py` (new) |
| #B | SwingNode dataclass | `swing_node.py` (new) |
| #C | Event types | `events.py` (new) |
| #D | ReferenceFrame tolerance checks | `reference_frame.py` |
| #L | Ground truth removal | `ground_truth_annotator/` |

### Phase 2: Algorithm (Sequential — 1 agent)

| Issue | Scope | Blocked By |
|-------|-------|------------|
| #E | Core incremental algorithm | #A, #B, #C, #D |
| #F | Calibration as loop | #E |

### Phase 3: Integration (Mixed — 2-3 agents)

| Issue | Scope | Blocked By | Parallel |
|-------|-------|------------|----------|
| #G | ReferenceSwing adapter | #E, #F | No |
| #H | Replay router update | #G | No |
| #I | Discretization update | #G | Yes (with #J) |
| #J | API schema updates | #G | Yes (with #I) |

### Phase 4: Cleanup (Sequential)

| Issue | Scope | Blocked By |
|-------|-------|------------|
| #K | Remove old detection code | #H, #I, #J |

### User Testing

After Phase 3:
- User tests new detection via Replay Mode
- Quality judged by domain expertise
- Feedback drives iteration

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `Docs/Reference/developer_guide.md` | Current | Will need update after rewrite |
| `Docs/Reference/user_guide.md` | Current | Hierarchy model needs documenting |
| `CLAUDE.md` | Current | - |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S/M/L/XL) → **Transitioning to hierarchy**
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars detection; O(active) per-bar for replay
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)
- **Backend-controlled boundaries:** Backend owns data visibility; frontend visualizes
- **Event filtering:** Stale events suppressed at API layer, not detection layer
- **Self-referential separation:** XL scale uses itself for FIB-based deduplication

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 18 | Swing Detection Rewrite Spec | Approved; all clarifications resolved — ready for implementation |
| Dec 18 | #138, #140 (Phase 1) — Endpoint optimization fix, symmetric pre-formation protection | All Accepted; #139 closed as resolved |
| Dec 18 | #130/regression, #131 (+ 3 fixes), #133, #134, #136 — Navigation, stats toggle, XL separation, API modularization, endpoint selection | All Accepted |
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

---

## Review Checklist

**Why this exists:** Bull/bear asymmetry (#140) went undetected through 40+ reviews. 38 instances accumulated.

### Must Check (Every Review)

1. **Symmetric Code Paths**
   - If `if direction == 'bull':` exists, verify both branches do symmetric operations
   - Red flag: bull checks `highs` but bear checks `lows` (or vice versa)

2. **Abstraction Adoption**
   - Does new code use existing abstractions (e.g., `ReferenceFrame`) or reinvent them?
   - If bypassed, is there a documented reason?

3. **Pattern Proliferation**
   - How many instances of this pattern exist now?
   - Threshold: >5 instances should trigger abstraction discussion

4. **Direction-Specific Logic** (swing_analysis only)
   - Any new `if swing.is_bull` or `if direction ==`?
   - Can it use coordinate-based logic instead? (ratio < 0 vs checking prices)

### Also Check

5. **Duplicated Logic** — >50 lines of parallel code should be unified
6. **Magic Numbers** — New thresholds need: what it represents, why this value, single source
7. **Core Decisions** — Aligned with list above?
8. **Known Debt** — Add new debt, remove resolved debt

### Outcomes

- **Accept** — All checks pass
- **Accept with Notes** — Minor issues tracked in Known debt or follow-up issue
- **Requires Follow-up** — Create GitHub issue before accepting
- **Blocked** — Critical issue, must fix first
