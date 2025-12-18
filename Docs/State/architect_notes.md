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
- Self-referential separation at XL scale (no larger_swings available)
- Candidate swings: pending 0.236 validation before promotion to reference

**Known debt:**
- `detect_swings()` function (~400 LOC) — monolithic; filter pipeline not extracted

**Cleanup tasks (deferred):**
- Delete `Docs/Archive/Proposals/Discretization/` once discretization pipeline is complete and documented in user_guide + developer_guide

---

## Current Phase: User Testing — Active

### Status

**Replay View v2 is feature-complete.** Detection quality improvements deployed:
- Self-referential separation for XL swings (17 → 5 in test case)
- Recursive endpoint optimization for best "1" selection
- Candidate swing tracking for pending 0.236 validation
- Protection tolerance restricted to established anchors
- API modularized into 7 domain-specific routers

**Current milestone:** User testing to validate detection quality improvements.

---

## Recently Completed (Dec 18 — Review 3)

| Issue | Feature | Verdict |
|-------|---------|---------|
| #130 (+ regression) | Navigation decoupled from display count | Accepted |
| #131 (+ 3 follow-ups) | Stats panel toggle, swing H/L markers | Accepted |
| #133 | Self-referential separation for XL scale | Accepted |
| #134 | API modularization (3,514 → 550 lines in api.py) | Accepted |
| #136 | Endpoint optimization, candidate swings, protection tolerance | Accepted |

**Key improvements:**

1. **Self-Referential Separation (#133):**
   - XL swings now require both endpoints to be > 0.1 FIB from existing swings
   - 17 redundant swings → 5 distinct swings in test case
   - Same rally to ATH no longer generates 12+ nearly-identical references

2. **Endpoint Selection (#136):**
   - Recursive `_optimize_defended_pivot()` finds best "1" endpoint
   - Stops when either well-separated (≥ 0.1 FIB) OR at absolute best extremum
   - Candidate swings (`is_candidate=True`) track pending 0.236 validation
   - Protection tolerance (0.1) only applies when larger_swings context exists

3. **API Modularization (#134):**
   - 7 routers: annotations, session, cascade, comparison, review, discretization, replay
   - schemas.py with all Pydantic models
   - api.py reduced to app factory and core routes

4. **UX Fixes (#130, #131):**
   - Navigation cycles through ALL swings (e.g., 1/17 to 17/17)
   - Display count (dropdown) controls chart density, not navigation
   - "Show Stats" toggle brings calibration panel back during playback
   - Swing H/L markers visible during both calibration and playback

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | **Healthy** | Self-referential separation + endpoint optimization |
| Incremental Detector | Healthy | Deduplication + frozen calibration stats |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode |
| Discretization Pipeline | Healthy | Core complete, visual overlay done |
| Replay View | **Complete** | Full observation workflow with feedback capture |
| API Layer | **Refactored** | 7 routers, clean separation |
| Test Suite | Healthy | 865 tests passing |
| Documentation | **Current** | Both guides updated Dec 18 |

---

## Next Steps

### 1. User Testing (Active)

With detection improvements deployed, user can validate:
- XL swing quality (fewer redundant swings)
- Endpoint selection (best "1" found, not just any valid one)
- Candidate swing behavior (pending 0.236 validation)
- Protection tolerance behavior (strict at XL, tolerant with context)

**Observations to collect:**
- Do the 5 XL swings (vs 17) feel right for the test window?
- Are candidate swings being promoted at the right time?
- Any remaining endpoint selection issues?

### 2. Candidate Swing Promotion (Pending Data)

The `is_candidate=True` swings need downstream handling:
- Incremental detector should emit LEVEL_CROSS at 0.236 for promotion
- Discretization module should track candidate → reference transitions
- This can be implemented once user testing validates the candidate concept

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `Docs/Reference/developer_guide.md` | **Current** | Updated Dec 18 with filter pipeline, routers |
| `Docs/Reference/user_guide.md` | **Current** | Updated Dec 18 with Show Stats toggle |
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
- **Self-referential separation:** XL scale uses itself for FIB-based deduplication

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
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
