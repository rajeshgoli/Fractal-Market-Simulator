# Pending Review

**Unreviewed Change Count:** 0

**Last Review:** 2026-01-03

---

## Pending Changes

(none)

---

## Review History

| Date | Issue/Changes | Outcome |
|------|---------------|---------|
| Jan 3 | #462, #463, #465-#467, #469-#472 — Calibration/Swing naming cleanup, sourceBars consolidation, CLI simplification, fib level fix, completed ref no-reform, pause buffering, config persistence, fromIndex fix, filter_stats in snapshots (9 issues) | All Accepted; commit 0004057 (follow-up to #471) untracked |
| Jan 2 | #454-#460, #464 — Breach filtering fix, reset button, batched ref states, per-pivot top N, auto-track buffering, config preservation, calibration deletion, test helper consolidation (8 issues) | All Accepted; calibration removed from core decisions |
| Jan 2 | #448, #449, #450, #452 — Formation pivot tracking, playback position filtering, view persistence, chart cleanup race fix (4 issues) | All Accepted; developer_guide.md discrepancy noted |
| Jan 2 | #445 — Bottom panel consolidation: LEVELS AT PLAY (column-major, paginated), FILTERS to sidebar, hover highlight, removed redundant panels | Accepted |
| Jan 2 | #444 — Reference Config Panel redesign: 4-section layout, color fill sliders, discrete Fib threshold, continuous breach tolerance (0-0.30), updated defaults | Accepted |
| Jan 2 | #442 — Unified salience formula: 6 additive weights, normalized via median×25, no standalone mode | Accepted |
| Jan 2 | #433 — Auto-select top-ranked leg on load, re-auto-select on config change, single selection model | Accepted |
| Jan 2 | #432 enhancement — Viewport-based label density limiting (grid-based, O(n)) | Accepted |
| Jan 2 | #430, #431, #432, #440 — Top N sidebar, bottom panel merge, label midpoint, rolling eviction (4 issues) | All Accepted |
| Jan 2 | #437 — Replace track_formation() with update(build_response=False) for continuous breach tracking | Accepted |
| Jan 2 | #438, #439 — Configurable decay factors, remove stale _range_distribution in favor of bin distribution | Accepted |
| Jan 2 | #415, #416, #420, #421, #423, #424, #425, #426, #427, #429, #434, #436 — Reference Layer P3/P4, Config Panel redesign, bin-based classification (10 issues) | All Accepted; Reference Layer Phase 4 complete, bin-based classification deployed |
| Jan 1 | #400, #403, #404, #408, #409, #410, #411, #412, #414 — Reference Observation, router cleanup, DAG cleanup, cache consolidation, lazy init, view fixes (9 issues) | All Accepted; Reference Phase 2 complete, P3 ready |
| Dec 31 | #398 — Schema unification, router split, naming cleanup | Accepted with notes; #403 filed for incomplete split |
| Dec 31 | #395, #396, #397 — Pivot fix, arch cleanup (Phases 1-2d), warmup preservation | All Accepted; #398 filed for remaining work |
| Dec 31 | #394 — DAG cleanup review + architectural investigation | Accepted with notes; vestiges identified in `architect_fixes.md`; epic filed |
| Dec 31 | #371-#387 — Reference Layer Phase 1 UI + bugfixes (17 issues) | All Accepted; Phase 1 complete; spec updated to Rev 6 |
| Dec 31 | #355-#358, #361-#370, #383, #384 — Turn ratio modes, Reference Layer Phase 1 backend, config defaults (11 changes) | All Accepted; Ref Layer P1 backend complete; doc update needed for developer_guide.md |
| Dec 25 | #347-#349 — Turn ratio UX, inner structure removal, frontend cleanup (3 changes) | All Accepted; dead feature deleted, docs current |
| Dec 25 | #333-#346 — Frontend refactor, branch ratio, turn ratio, origin breach simplification (10 changes) | All Accepted; docs current |
| Dec 24 | #322-#335 — Min CTR filter, dead code cleanup, in-app settings, regressions (11 changes) | All Accepted; docs current |
| Dec 24 | #318-#321 — Counter-trend scoring, session persistence, UX (4 changes) | All Accepted; docs updated |
| Dec 24 | #305, #309-#316 — UX improvements, API serialization, pruning fix (9 changes) | All Accepted; docs debt updated |
| Dec 23 | #296-#303, #306, #307 — Performance, cleanup, segment impulse (10 changes) | All Accepted; docs debt noted |
| Dec 23 | #294, #288, #261, #281, #279, #278, #283, #267, aggregation (9 changes) | All Accepted; #282 follow-up noted |
| Dec 22 | #241, #248-#250, #260-#266, bugfixes — Impulse metrics, hierarchy exploration, inner structure pruning (10 changes) | All Accepted |
| Dec 21 | #210, #219, #228, #236 — Cleanup epics + impulse score (4 epics, 25 subissues) | All Accepted; minor doc fixes #248, #249 |
| Dec 21 | #199-#208, #211 — Modularization, pruning redesign, UX enhancements (10 issues) | All Accepted |
| Dec 20 | #190-#197, #198 — Pivot/origin semantics cascade + architectural audit | All Accepted; design sound post-#197 |
| Dec 19 | #187-#189, #183, UX fixes (10 changes) — Temporal causality, sidebar unification, feedback snapshots | All Accepted |
| Dec 19 | #125, #180-#182, #185, #186 — DAG refinements + UX fixes (6 issues) | All Accepted |
| Dec 19 | #168-#172, #179 — DAG Visualization Mode (6 issues) | All Accepted |
| Dec 19 | #158-#175 — DAG algorithm rewrite + Reference layer (9 issues) | All Accepted |
| Dec 19 | #152, #153, #155, #157 — Performance optimization + cleanup (4 issues) | All Accepted |
| Dec 18 | #142-#151 — Swing Detection Rewrite (10 issues) | All Accepted; #154 performance issue identified with prescriptive sub-issues #155, #156 |
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
