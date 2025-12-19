# Pending Review

**Unreviewed Change Count:** 9

**Last Review:** 2025-12-18

---

## Pending Changes

- **#142** — SwingConfig dataclass: centralized configuration for all swing detection parameters
- **#143** — SwingNode dataclass: hierarchical swing structure with DAG parent/child linking
- **#144** — SwingEvent types: formed/invalidated/completed/level_cross for hierarchical detector
- **#145** — ReferenceFrame tolerance checks: is_violated, is_formed, is_completed, get_fib_price
- **#146** — Ground truth annotator removal: archived and deleted per swing detection rewrite spec
- **#147** — HierarchicalDetector: core incremental swing detection with process_bar() entry point
- **#148** — Calibration as loop: calibrate(), calibrate_from_dataframe(), dataframe_to_bars() helpers
- **#149** — ReferenceSwing compatibility adapter: swing_node_to_reference_swing, detect_swings_compat
- **#150** — Replay router update: uses HierarchicalDetector, adds hierarchy info (depth, parent_ids)

---

## Review History

| Date | Issue/Changes | Outcome |
|------|---------------|---------|
| Dec 18 | Swing Detection Rewrite Spec | Approved; all clarifications resolved — ready for implementation |
| Dec 18 | #138, #140 (Phase 1) — Endpoint optimization fix, symmetric pre-formation protection | All Accepted; #139 closed as resolved |
| Dec 18 | #130/regression, #131 (+ 3 fixes), #133, #134, #136 — Navigation, stats toggle, XL separation, API modularization, endpoint selection | All Accepted |
| Dec 17 | #122, #123, #126, #127, #128 — Trigger explanations, always-on feedback, level band fix, offset storage, deduplication | All Accepted |
| Dec 17 | #116, #118, #119, #120, #121 — Feedback capture, collision fix, lazy sessions, incremental detection, stale filtering | All Accepted |
| Dec 17 | #112, #113, #114, #115, #117 — Replay View v2 architecture fix + usability | All Accepted |
| Dec 17 | #101, #102, #104, #105, #111 — Calibration, forward playback, event nav, scale toggles, swing markers | All Accepted, Epic #99 closed |
| Dec 17 | #100, #103, #107, #108, #109 — Zero swings fix, speed control, swing overlay, multi-swing nav | All Accepted |
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
