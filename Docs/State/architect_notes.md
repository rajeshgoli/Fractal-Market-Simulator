# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Hierarchical swing model (Leg DAG) — replaces S/M/L/XL buckets
- Single incremental algorithm (LegDetector.process_bar())
- Fibonacci-based structural analysis (0.382 formation/invalidation)
- Resolution-agnostic (1m to 1mo)
- DetectionConfig centralizes all detection parameters
- Calibration-first playback for causal evaluation
- Backend-controlled data boundary for replay (single source of truth)
- **DAG/Reference separation:** Structural tracking vs semantic filtering
- **Rules by construction:** Temporal ordering from bar relationships (Type 1/2/3)
- **Strict inter-bar causality:** Legs only form when pivots are from different bars (#189)
- **Modular DAG layer:** dag/ subdirectory with LegDetector, LegPruner, state, calibrate, leg modules (#206)
- **Structure-driven pruning:** Origin-proximity consolidation (time+range), pivot breach (10%), engulfed (strict) (#203, #208, #294)
- **Counter-trend scoring:** Proximity pruning selects survivor by counter-trend range (#319)
- **Two-impulse model:** Segment tracking with impulse_to_deepest, impulse_back, net_segment_impulse (#307)
- **Leg hierarchy:** Parent-child relationships with reparenting on prune (#281)
- **Runtime config:** Detection parameters adjustable via UI without restart (#288)
- **Deterministic IDs:** `leg_id` based on (direction, origin_price, origin_index) survives BE reset (#299)
- **Session persistence:** UI preferences (charts, speed, config) persist via localStorage (#321)
- **Origin breach as single gate:** No 'invalidated' status — use `max_origin_breach is not None` (#345)
- **Branch ratio domination:** Creation-time filter prevents insignificant child legs (#337)
- **Turn ratio pruning:** Horizontal sibling filter at shared pivots (threshold or top-k) (#341, #342, #344)
- **Tiered Reference Layer updates:** Per-bar `track_formation()` for stateful ops only; full `update()` on-demand for display. Salience is stable (ranking rarely changes bar-to-bar), so per-bar recomputation is wasteful. See `Docs/Archive/reference_update_perf.md`.

**Known debt:**
- #240 — TODO: Empirically determine engulfed retention threshold based on impulse
- #176 — `get_windowed_swings` missing Reference layer during calibration (fix after validation)
- #399 — TODO: Salience optimization if needed (periodic refresh, event-driven, or lazy with TTL)
- Scaling test `test_scaling_is_not_quadratic` marginally fails (64 vs 60 threshold) — flaky boundary, low priority

**Completed architectural cleanup (#394, #396, #398, #403, #404, #408, #410, #412):**
- ✅ SwingNode, `swing_id`, `formed` removed from DAG; old Reference Layer API removed (#394)
- ✅ Renamed `ground_truth_annotator/` → `replay_server/` (#396)
- ✅ Removed refactoring vestiges: `swing_id` on events, `emit_level_crosses` config (#396)
- ✅ Connected `depth` to `leg.depth`, replaced `parent_ids` with `parent_leg_id` (#396)
- ✅ Unified `CalibrationSwingResponse` and `DagLegResponse` into `LegResponse` (#398)
- ✅ Created domain routers (dag, reference, feedback) with helpers (#398)
- ✅ Renamed `largest_swing_id` → `largest_leg_id` (#398)
- ✅ `swing_config.py` → `detection_config.py`, `SwingConfig` → `DetectionConfig`
- ✅ Migrated replay.py to use helpers/, removed tombstone comments (#403)
- ✅ Deleted replay.py, consolidated into dag.py (841 lines) (#410)
- ✅ Cache consolidation: single dict in cache.py, removed parallel caches (#410)
- ✅ API namespace restructure: /api/dag/*, /api/reference/*, /api/feedback/* (#410)
- ✅ Dead code cleanup: removed SWING_* events, 'formed' field vestiges (#408)
- ✅ Lazy DAG init: removed CalibrationPhase, added _ensure_initialized() (#412)
- ✅ Simplified config: removed enable_engulfed_prune, min_branch_ratio, turn_ratio_mode (#404)

**Future naming cleanup (low priority):**
- `SwingEvent` → `DetectionEvent` (deferred)
- Keep `src/swing_analysis/` — valid domain term for users

---

## Current Phase: Reference Layer Implementation

### Phase 1: COMPLETE — Dec 31, 2025

**Spec:** `Docs/Working/reference_layer_spec.md` (Revision 6 — Approved)

Phase 1 is fully complete (backend + frontend, 27 issues #361-#387):

| Component | Status | Issue |
|-----------|--------|-------|
| **Leg.depth** | ✅ Complete | #361 — O(1) lookup at creation |
| **ReferenceConfig** | ✅ Complete | #362, #383 — North star tolerances correct |
| **ReferenceSwing** | ✅ Complete | #363 — Wraps Leg with scale/depth/location/salience |
| **ReferenceState** | ✅ Complete | #364 — Grouped output with direction imbalance |
| **Scale classification** | ✅ Complete | #365 — Percentile-based S/M/L/XL |
| **Location computation** | ✅ Complete | #366 — ReferenceFrame.ratio() |
| **Formation** | ✅ Complete | #367 — Price-based, once formed stays formed |
| **Fatal breach** | ✅ Complete | #368 — Scale-dependent tolerances |
| **Salience** | ✅ Complete | #369 — Scale-dependent weights |
| **update() entry point** | ✅ Complete | #370 — Main API for processing legs |

### Design Decisions (Implemented)

1. **Leg.depth** — Computed at leg creation, stored as field (O(1) lookup)
2. **ReferenceConfig** — Separate from DetectionConfig; different lifecycle
3. **Formation tracking** — Reference Layer maintains `_formed_refs: Set[str]` (once formed, stays formed until fatally breached)
4. **Cold start** — Exclude refs until 50+ formed legs
5. **Range distribution** — All-time; DAG pruning handles recency

---

## Reference Layer Epic Decomposition

Four phases from spec, decomposed into implementable issues. Each epic is independently testable and shippable.

### Phase 1: Core Backend + Levels at Play UI (Foundation)

**Epic #P1: Reference Layer Core** — Backend implementation — ✅ COMPLETE

| # | Issue | Description | Status |
|---|-------|-------------|--------|
| P1.1 | #361 Add depth field to Leg | O(1) lookup at creation | ✅ |
| P1.2 | #362 Create ReferenceConfig | All Reference Layer params | ✅ |
| P1.3 | #363 Create ReferenceSwing dataclass | Wraps Leg with scale/depth/location/salience | ✅ |
| P1.4 | #364 Create ReferenceState dataclass | Grouped output with direction_imbalance | ✅ |
| P1.5 | #365 Implement scale classification | Percentile-based S/M/L/XL | ✅ |
| P1.6 | #366 Implement location computation | ReferenceFrame.ratio() | ✅ |
| P1.7 | #367 Implement price-based formation | 38.2% threshold, once formed stays formed | ✅ |
| P1.8 | #368 Implement fatal breach detection | Scale-dependent tolerance per north star | ✅ |
| P1.9 | #369 Implement salience computation | Scale-dependent weights | ✅ |
| P1.10 | #370 Implement ReferenceLayer.update() | Main entry point | ✅ |
| P1.11 | (in #370) Cold start handling | Empty state until 50+ legs | ✅ |
| P1.12 | (in #370) Range distribution tracking | Sorted list with bisect | ✅ |
| P1.13 | (in issues) Test suite | Comprehensive coverage | ✅ |
| — | #383 Fix ReferenceConfig tolerances | North star alignment | ✅ |

**Epic #P1-UI: Levels at Play View** — ✅ COMPLETE

| # | Issue | Description | Status |
|---|-------|-------------|--------|
| P1-UI.1 | #374 Add "Levels at Play" route | Hamburger menu entry | ✅ |
| P1-UI.2 | #375 Create Reference API endpoint | `/api/reference-state` | ✅ |
| P1-UI.3 | #376 Filter display to valid references | Location 0-2 + formed | ✅ |
| P1-UI.4 | #377 Add scale labels | S/M/L/XL badge | ✅ |
| P1-UI.5 | #378 Add direction colors | Bull (green) / Bear (red) | ✅ |
| P1-UI.6 | #379 Add location indicator | 0-2 position | ✅ |
| P1-UI.7 | #380 Hide detection config | DAG panel hidden | ✅ |
| P1-UI.8 | #381 Implement fade-out transition | Opacity animation | ✅ |
| P1-UI.9 | #382 Add telemetry panel | Reference counts, imbalance | ✅ |
| — | #386 Fix view switching | State preservation | ✅ |
| — | #387 Fix overlay rendering | SVG positioning | ✅ |

### Phase 2: Fib Level Interaction — ✅ COMPLETE

**Epic #P2: Fib Level Display** — #388 (5 sub-issues: #389-#393)

| # | Issue | Description | Status |
|---|-------|-------------|--------|
| P2.1 | #389 Implement get_active_levels() | Return fib levels with source reference info | ✅ |
| P2.2 | #390 Add hover preview | Show all 9 fib levels as horizontal lines on hover | ✅ |
| P2.3 | #391 Implement click-to-stick | Click makes fib levels persist; click again un-sticks | ✅ |
| P2.4 | #392 Color-code by source | Distinguish fib levels from different references | ✅ |
| P2.5 | #393 Track sticky state in Reference Layer | `_tracked_for_crossing` set persisted | ✅ |

### Phase 3: Structure Panel + Confluence

**Epic #P3: Level Analysis**

| # | Issue | Description | Depends On |
|---|-------|-------------|------------|
| P3.1 | Implement get_confluence_zones() | Cluster levels within percentage tolerance | P2.1 |
| P3.2 | Create structure panel UI | Three sections: touched/active/current | P1-UI.2 |
| P3.3 | Track levels touched this session | Historical record of which levels were hit | P3.2 |
| P3.4 | Show currently active levels | Levels within striking distance of current price | P3.2 |
| P3.5 | Show current bar touches | Levels touched on most recent bar | P3.2 |
| P3.6 | ~~Display confluence zones~~ | Removed — visual clutter (#421) | P3.1 |

**Note:** Confluence zone UI was implemented then removed due to visual clutter (labels stacking). Backend API (`/api/reference/confluence`) remains available.

### Phase 4: Opt-in Level Crossing — #416

**Epic #416: Level Crossing Tracking** (2 sub-issues)

| # | Issue | Description | Status |
|---|-------|-------------|--------|
| P4.1 | #417 Backend: Level crossing detection + events | Track legs, detect crosses, emit LevelCrossEvent | Pending |
| P4.2 | #418 Frontend: Track button + crossing event display | UI for tracking, display events in Structure Panel | Pending |

### Parallel Exploration Task

| # | Issue | Description | Depends On |
|---|-------|-------------|------------|
| EXP.1 | Analyze depth vs scale correlation | Compute correlation, identify disagreement cases | P1.1, P1.5 |

### DAG Cleanup Epic (Pre-P2) — #394 ✅ COMPLETE

**Status:** Completed Dec 31, 2025. Core cleanup done, but vestiges remain (see `Docs/Working/architect_fixes.md`).

**What was done:**
- SwingNode class deleted
- `swing_id` and `formed` removed from Leg
- Formation moved to Reference Layer (runtime computation)
- Old Reference Layer API removed
- Zombie leg bug fixed

**What remains (tracked in architect_fixes.md):**
- `swing_id` vestiges on DetectionEvent base class (always "")
- `emit_level_crosses` dead config
- Tombstone comments throughout router
- Schema unification needed

---

## Implementation Order

**Status:**
- ✅ P1 (Core Backend) — COMPLETE (13 issues)
- ✅ P1-UI (Levels at Play UI) — COMPLETE (11 issues including bugfixes)
- ✅ DAG Cleanup (#394, #403, #404, #408, #410, #412) — COMPLETE (all vestiges removed)
- ✅ P2 (Fib Level Interaction) — COMPLETE (5 issues: #388-#393)
- ✅ Reference Observation (#400) — COMPLETE (2 issues: #401, #402 + #414 UX inversion)
- ✅ P3 (Structure Panel + Confluence) — COMPLETE (#415)
- ⏳ **P4 (Level Crossing Tracking)** — NEXT (#416: 2 sub-issues #417, #418)

**Next step:** Phase 4 (Opt-in Level Crossing) — selective level tracking, crossing events

**Spec:** `Docs/Working/reference_layer_spec.md` (lines 806-826)

---

### L1-L7 Validation — COMPLETE (Dec 25, 2025)

All 7 reference swings detected correctly with config: `origin_time_threshold=0.02`, `origin_range_threshold=0.02`, `max_turns_per_pivot_raw=10`

| Label | Expected | Found | Status |
|-------|----------|-------|--------|
| **L1** | origin=6166, pivot=4832 | origin=6166.50, pivot=4832.00 | BREACHED |
| **L2** | origin=5837, pivot=4832 | origin=5837.25, pivot=4832.00 | BREACHED |
| **L3** | origin=6955, pivot=6524 | origin=6953.75, pivot=6525.00 | intact |
| **L4** | origin=6896, pivot=6524 | origin=6909.50, pivot=6525.00 | BREACHED |
| **L5** | origin=6790, pivot=6524 | origin=6801.50, pivot=6525.00 | BREACHED |
| **L6** | origin=6929, pivot=6771 | origin=6928.75, pivot=6771.50 | BREACHED |
| **L7** | origin=6882, pivot=6770 | origin=6892.00, pivot=6771.50 | BREACHED |

**Key insight:** Reference swings (bull references) are **bear legs** in DAG terminology (origin=HIGH, pivot=LOW). Multiple siblings exist at shared pivots.

### Recent Changes — Dec 25 Review #2 (3 issues)

All 3 pending changes accepted. Summary:

| Issue | Summary | Outcome |
|-------|---------|---------|
| #347 | Turn ratio pruning frontend UX improvements | Accepted — Dual-slider mutual exclusion, deep merge for settings persistence |
| #348 | Remove inner structure pruning | Accepted — Strong approval. Dead feature correctly deleted |
| #349 | Frontend dead code removal epic | Accepted — ~142 lines removed, ViewMode infrastructure deleted |

### Pivot/Origin Semantics — FIXED

**#188-#197 resolved:** The terminology cascade has been fixed. All code now correctly enforces:

| Leg Type | Origin | Pivot | Temporal Order |
|----------|--------|-------|----------------|
| Bull | LOW (move started) | HIGH (defended extreme) | origin_index < pivot_index |
| Bear | HIGH (move started) | LOW (defended extreme) | origin_index < pivot_index |

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| LegDetector (dag/) | **Complete** | O(n log k), modularized into 5 modules |
| LegPruner (dag/) | **Complete** | Handles: origin-proximity, breach, engulfed, turn ratio |
| Leg Hierarchy | **Complete** | Parent-child with reparenting (#281) |
| Origin-Proximity Pruning | **Complete** | Counter-trend scoring default (#319) |
| Branch Ratio Domination | **Complete** | Creation-time filter (#337) |
| Turn Ratio Pruning | **Complete** | Threshold + top-k modes, largest leg exempt (#341, #342, #344) |
| Segment Impulse | **Complete** | Two-impulse model: impulse_to_deepest, impulse_back (#307) |
| Deterministic IDs | **Complete** | Leg/swing IDs survive BE reset (#299) |
| Temporal Causality | **Fixed** | Strict inter-bar ordering (#189) |
| Leg Origin Updates | **Fixed** | Origins update on price extensions (#188) |
| Origin Breach | **Simplified** | No 'invalidated' status, breach at 0% (#345) |
| DetectionConfig | Complete | Centralizes all parameters including pruning toggles (#288) |
| SwingNode | **Removed** | Deleted in #394; formation now in Reference Layer |
| ReferenceFrame | Complete | Central coordinate abstraction |
| ReferenceLayer | **Phase 3 Complete** | Core + UI + Observation + Structure Panel (#361-#387, #400, #414, #415) |
| Pivot Breach Pruning | Complete | 10% threshold with replacement leg (#208) |
| Engulfed Detection | Complete | Strict (0.0 threshold) deletes leg (#208, #236) |
| Inner Structure Pruning | **Removed** | Deleted in #348 — disabled by default, worst-performing method |
| Replay View | **Removed** | Consolidated into DAG View (#408, #410) |
| DAG Visualization | Complete | Now called "Structural Legs" (#411), lazy init (#412) |
| Hierarchy Exploration | **Complete** | Tree icon, lineage API, focus/ancestor/descendant display (#250) |
| Chart Controls | **Complete** | Maximize/minimize per chart (#263) |
| Detection Config Panel | **Complete** | Runtime threshold adjustment, Fib dropdowns (#288, #318, #343) |
| Session Persistence | **Complete** | localStorage for charts, speed, config, linger (#321) |
| Resizable Panels | **Complete** | Draggable explanation panel height (#321) |
| Backward Navigation | **Complete** | Backend reverse replay API (#278) |
| Follow Leg Feature | **Complete** | Lifecycle tracking, event markers (#267) |
| Batch DAG States | **Complete** | Per-bar states in response (#283) |
| V2 API Schemas | Complete | HierarchicalSwingResponse, depth-based grouping |
| Frontend Refactor | **Complete** | Utility extraction, component decomposition (#333, #334) |
| Discretization | **Removed** | Will return with reference layer implementation |
| Swing Hierarchy | **Removed** | O(n²) dead code; leg hierarchy used instead (#301) |
| Turn/Domination Pruning | **Removed** | Redundant; creation-time check handles all cases (#296) |
| Legacy Code | **Deleted** | All pre-DAG modules removed (#210, #219, #228) |
| Test Suite | Healthy | 524 tests passing, 1 skipped (marginal scaling test failure noted in debt) |
| Documentation | Current | All docs updated (Jan 1) |

---

## Documentation Status

| Document | Status | Notes |
|----------|--------|-------|
| `developer_guide.md` | Current | API restructure documented; Reference Observation API added |
| `user_guide.md` | Current | O! marker, follow leg, Structural Legs naming updated |
| `DAG.md` | Current | Updated Dec 31 |
| `CLAUDE.md` | Current | No changes needed |

---

## Architecture Principles

- **Hierarchical model:** Swings form a DAG, not discrete buckets
- **Single algorithm:** process_bar() for both calibration and playback
- **Fibonacci levels:** Extended grid (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance target:** <5s for 10K bars (achieved: 4.06s)
- **Lean codebase:** 3 modules (data, swing_analysis, replay_server)
- **Backend-controlled boundaries:** Backend owns data visibility
- **DAG/Reference separation:** DAG tracks structural extremas; Reference layer defines "good reference" semantics
- **Rules by construction:** Temporal ordering enforced by bar relationships, not post-hoc filtering
- **Strict inter-bar causality:** Legs require pivots from different bars (#189)
- **Fractal compression:** Recursive pruning creates detail near active zone, sparse further back
- **Modular design:** dag/ subdirectory with clear separation of concerns (#206)
- **Configurable thresholds:** All pruning/breach thresholds centralized in DetectionConfig
- **Strong deletion bias:** Actively remove unused code to maintain codebase clarity
- **Runtime configurability:** Detection parameters adjustable without restart (#288)
- **Data-driven simplification:** Remove code when profiling shows it's unnecessary (#296)
- **Deterministic state:** IDs derived from immutable properties for reproducibility (#299)
- **Counter-trend significance:** Proximity pruning prioritizes structural levels with strong counter-moves (#319)
- **Creation-time filtering:** Prefer blocking leg creation over post-hoc pruning (#337)
- **Single structural gate:** Origin breach is the only gate; no redundant 'invalidated' status (#345)

---

## Review Checklist

### Must Check (Every Review)

1. **Symmetric Code Paths**
   - If `if direction == 'bull':` exists, verify both branches do symmetric operations
   - Red flag: bull checks `highs` but bear checks `lows` (or vice versa)

2. **Abstraction Adoption**
   - Does new code use existing abstractions (e.g., `ReferenceFrame`) or reinvent them?

3. **Performance Implications**
   - Does new code add O(n²) operations?
   - Are there repeated sorts or scans that could be cached?

4. **Direction-Specific Logic** (swing_analysis only)
   - Any new `if swing.is_bull` or `if direction ==`?
   - Can it use coordinate-based logic instead?

### Also Check

5. **Duplicated Logic** — >50 lines of parallel code should be unified
6. **Magic Numbers** — New thresholds need: what it represents, why this value
7. **Core Decisions** — Aligned with list above?
8. **Known Debt** — Add new debt, remove resolved debt
9. **No Tombstones** — Flag "# Removed in #XXX" comments, hardcoded stub values, dead config options

### Outcomes

- **Accept** — All checks pass
- **Accept with Notes** — Minor issues tracked in Known debt
- **Requires Follow-up** — Create GitHub issue before accepting
- **Blocked** — Critical issue, must fix first

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Jan 1 | #400, #403, #404, #408, #409, #410, #411, #412, #414 — Reference Observation, router cleanup, DAG cleanup, cache consolidation, lazy init, view fixes (9 issues) | All Accepted; Phase 2 complete, P3 ready |
| Dec 31 | #398 — Schema unification, router split, naming cleanup | Accepted with notes; #403 filed for incomplete split (duplication, tombstones) |
| Dec 31 | #395, #396, #397 — Pivot fix, arch cleanup (Phases 1-2d), warmup preservation | All Accepted; #398 filed for remaining work |
| Dec 31 | #394 — DAG cleanup review + architectural investigation | Accepted with notes; vestiges identified in `architect_fixes.md`; epic filed |
| Dec 31 | #371-#387 — Reference Layer Phase 1 UI + bugfixes (17 issues) | All Accepted; Phase 1 complete; spec updated to Rev 6 |
| Dec 31 | #355-#358, #361-#370, #383, #384 — Turn ratio modes, Reference Layer Phase 1 backend (11 changes) | All Accepted; Ref Layer P1 backend complete; developer_guide.md update needed |
| Dec 25 | #347-#349 — Turn ratio UX, inner structure removal, frontend cleanup (3 changes) | All Accepted; dead feature deleted, docs current |
| Dec 25 | #333-#346 — Frontend refactor, branch ratio, turn ratio, origin breach simplification (10 changes) | All Accepted; docs current |
| Dec 24 | #322-#335 — Min CTR filter, dead code cleanup, in-app settings, regression fixes (11 changes) | All Accepted; docs current |
| Dec 24 | #318-#321 — Counter-trend scoring, session persistence, UX (4 changes) | All Accepted; docs updated |
| Dec 24 | #305, #309-#316 — UX improvements, API serialization, pruning fix (9 changes) | All Accepted; docs debt updated |
| Dec 23 | #296-#303, #306, #307 — Performance, cleanup, segment impulse (10 changes) | All Accepted; docs debt noted |
| Dec 23 | #294, #288, #261, #281, #279, #278, #283, #267, aggregation (9 changes) | All Accepted; #282 follow-up noted |
| Dec 22 | #241, #248-#250, #260-#266, bugfixes — Impulse metrics, hierarchy exploration, inner structure pruning (10 changes) | All Accepted |
| Dec 21 | #210, #219, #228, #236 — Cleanup epics + impulse score (4 epics, 25 subissues) | All Accepted; minor doc fixes #248, #249 |
| Dec 21 | #199-#208, #211 — Modularization, pruning redesign, UX enhancements (10 issues) | All Accepted |
| Dec 20 | #190-#197, #198 — Pivot/origin semantics fixes + architectural audit | All Accepted |
| Dec 19 | #187-#189, #183, UX fixes (10 changes) — Temporal causality fix, sidebar unification | All Accepted |
| Dec 19 | #125, #180-#182, #185, #186 — DAG refinements + UX fixes (6 issues) | All Accepted |
| Dec 19 | #168-#172, #179 — DAG Visualization Mode (6 issues) | All Accepted |
| Dec 19 | #158-#175 — DAG algorithm rewrite + Reference layer (9 issues) | All Accepted |
| Dec 19 | #152, #153, #155, #157 — Performance optimization + cleanup | All Accepted |
| Dec 18 | #142-#151 — Swing Detection Rewrite (10 issues) | All Accepted |
| Dec 18 | Swing Detection Rewrite Spec | Approved; implementation plan created |
| Dec 18 | #138, #140 (Phase 1) — Endpoint optimization, pre-formation protection | All Accepted |
| Dec 18 | #130-#136 — Navigation, stats, API modularization | All Accepted |
| Dec 17 | #116-#128 — Feedback, incremental detection, usability | All Accepted |
| Dec 17 | #99-#111 — Replay View completion | All Accepted, Epic #99 closed |
| Dec 16 | #78-#89 — Discretization, Replay View | All Accepted |
| Dec 16 | #68-#77 — Phase 3 + Architecture Overhaul | All Accepted |
