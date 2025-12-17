# Pending Review

**Unreviewed Change Count:** 4

**Last Review:** 2025-12-17

---

## Pending Changes

### 2025-12-17 - Highlight specific swing during explanation pause
- **Issue:** #108
- **Type:** Bug Fix
- **Files:** `frontend/src/hooks/usePlayback.ts`, `frontend/src/components/SwingOverlay.tsx`, `frontend/src/pages/Replay.tsx`

### 2025-12-17 - Swing markers and Fib levels on Replay View chart
- **Issue:** #107
- **Type:** Feature
- **Files:** `src/ground_truth_annotator/api.py`, `frontend/src/components/SwingOverlay.tsx`, `frontend/src/lib/api.ts`, `frontend/src/pages/Replay.tsx`, `frontend/src/types.ts`, `tests/test_ground_truth_annotator_api.py`

### 2025-12-17 - Replay View speed control relative to aggregation
- **Issue:** #103
- **Type:** Enhancement
- **Files:** `frontend/src/components/PlaybackControls.tsx`, `frontend/src/constants.ts`, `frontend/src/hooks/usePlayback.ts`, `frontend/src/lib/api.ts`, `frontend/src/pages/Replay.tsx`, `frontend/src/types.ts`

### 2025-12-17 - Zero swings bug fix
- **Issue:** #100
- **Type:** Bug Fix
- **Files:** `src/swing_analysis/swing_detector.py`, `tests/test_swing_detector.py`

---

## Review History

| Date | Issue/Changes | Outcome |
|------|---------------|---------|
| Dec 17 | Q-2025-12-17-1 — Zero swing bug diagnosis + forward-only playback design | Designed → Ready for engineering |
| Dec 17 | #91, #96, #97, #98 — React adoption, chart fixes, dead code removal, flaky test | All Accepted |
| Dec 16 | #84, #85, #86, #87, #89 — Replay View: split view, playback, linger, explanation, bug fixes | All Accepted |
| Dec 16 | #78, #79, #81, #82, #83 — Discretization overlay, validation, ground truth consolidation, explanation data, windowed API | All Accepted |
| Dec 16 | Replay View Spec (`Docs/Working/replay_view_spec.md`) | Feasible → Issues #82-#87 created |
| Dec 16 | #73, #74, #75, #76, #77 — Discretization core implementation | All Accepted |
| Dec 16 | #68, #69, #70, #71 — Phase 3 + Architecture Overhaul | All Accepted |
| Dec 15 | Q-2025-12-15-2: FIB structural separation feasibility | Feasible → Merged into Phase 3 |
| Dec 15 | Q-2025-12-15-2: Endpoint selection design | Designed → Ready for implementation |
| Dec 15 | #64: FP category refinements, filter tightening, --start-date parameter | Accepted |
| Dec 15 | #59, #60, #61, #62, #63 — Annotation UX + Too Small + Prominence filters | All Accepted |
| Dec 15 | Q-2025-12-15-6: Too small + subsumed filter design | Designed → #62, #63 created |
| Dec 15 | #54, #55, #56, #57, #58 - Protection validation, data collection, detection quality, UX batches | All Accepted |
| Dec 15 | Protection validation design (Q-2025-12-15-2) | Approved → #54 created |
| Dec 15 | Counter-trend FP category | Accepted |
| Dec 15 | #31, #51, #52, #53 - Test stability, FP quick-select, session filenames | All Accepted |
| Dec 12 | #46-#50 - P1 UX fixes (Fib labels, presets, toast, keep/discard, caching) | All Accepted |
| Dec 12 | #44 - Deprecated module removal | Accepted |
| Dec 12 | Review Mode epic (#38) - #39, #40, #41, #42, #43 | All Accepted, epic closed |
| Dec 12 | #32, #33, #34, #35, #37 - UX polish batch | All Accepted |
| Dec 12 | #27, #28, #29, #30 - Ground truth annotation tool MVP | All Accepted |
| Dec 12 | Ground truth annotation design question | Approved - ready for engineering |
| Dec 12 | #22, #24 - Full dataset loading, resolution-agnostic | Accepted |
| Dec 12 | #16, #17, #19, #20, #21 - Lightweight validator, O(N log N) detector, progressive loading, performance optimization, test fixes | All Accepted |
| Dec 11 | Dogfood Feedback - Harness Assessment | Resolved - Product chose Path B |
| Dec 11 | Issue #15 - PlaybackController state refactor | Accepted |
| Dec 11 | Thread Safety (renderer, keyboard_handler) | Accepted |
| Dec 11 | Phase 1 Visualization | Accepted |
| Dec 11 | Algorithm Rewrite | Accepted |
| Dec 11 | Test Maintenance | Accepted |
