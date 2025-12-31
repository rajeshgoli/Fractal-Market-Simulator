# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Hierarchical swing model (SwingNode DAG) — replaces S/M/L/XL buckets
- Single incremental algorithm (LegDetector.process_bar())
- Fibonacci-based structural analysis (0.382 formation/invalidation)
- Resolution-agnostic (1m to 1mo)
- SwingConfig centralizes all detection parameters
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
- **Deterministic IDs:** Leg/swing IDs based on (direction, origin_price, origin_index) survive BE reset (#299)
- **Session persistence:** UI preferences (charts, speed, config) persist via localStorage (#321)
- **Origin breach as single gate:** No 'invalidated' status — use `max_origin_breach is not None` (#345)
- **Branch ratio domination:** Creation-time filter prevents insignificant child legs (#337)
- **Turn ratio pruning:** Horizontal sibling filter at shared pivots (threshold or top-k) (#341, #342, #344)

**Known debt:**
- #240 — TODO: Empirically determine engulfed retention threshold based on impulse
- #176 — `get_windowed_swings` missing Reference layer during calibration (fix after validation)

---

## Current Phase: Reference Layer Design

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

### Next: Reference Layer

**Purpose:** Thin filter over DAG output to identify valid trading references per north star rules.

**Spec:** `Docs/Working/reference_layer_spec.md`

**Key capabilities:**
1. Location check (price between 0 and 2 in reference frame)
2. Scale classification (S/M/L/XL by range percentile)
3. Scale-dependent invalidation tolerance (small: 0%, big: 15%/10%)
4. Salience ranking (big/impulsive/early vs recent)

**Design decision:** Reference Layer is a filter, not a capture mechanism. It answers "which current DAG legs qualify as valid trading references?" — doesn't freeze or store historical state.

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
| SwingConfig | Complete | Centralizes all parameters including pruning toggles (#288) |
| SwingNode | Complete | DAG hierarchy model |
| ReferenceFrame | Complete | Central coordinate abstraction |
| ReferenceLayer | Complete | Tolerance/completion rules |
| Pivot Breach Pruning | Complete | 10% threshold with replacement leg (#208) |
| Engulfed Detection | Complete | Strict (0.0 threshold) deletes leg (#208, #236) |
| Inner Structure Pruning | **Removed** | Deleted in #348 — disabled by default, worst-performing method |
| Replay View | Complete | Tree-based UI, forward playback |
| DAG Visualization | Complete | Leg/origin visualization, hover highlighting, chart interaction |
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
| Test Suite | Healthy | 502 tests passing |
| Documentation | Current | All docs updated |

---

## Documentation Status

| Document | Status | Notes |
|----------|--------|-------|
| `developer_guide.md` | Current | Turn ratio, branch ratio, #345 documented |
| `user_guide.md` | Current | O! marker, follow leg updated |
| `DAG.md` | Current | Updated Dec 24 |
| `CLAUDE.md` | Current | No changes needed |

---

## Architecture Principles

- **Hierarchical model:** Swings form a DAG, not discrete buckets
- **Single algorithm:** process_bar() for both calibration and playback
- **Fibonacci levels:** Extended grid (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance target:** <5s for 10K bars (achieved: 4.06s)
- **Lean codebase:** 3 modules (data, swing_analysis, ground_truth_annotator)
- **Backend-controlled boundaries:** Backend owns data visibility
- **DAG/Reference separation:** DAG tracks structural extremas; Reference layer defines "good reference" semantics
- **Rules by construction:** Temporal ordering enforced by bar relationships, not post-hoc filtering
- **Strict inter-bar causality:** Legs require pivots from different bars (#189)
- **Fractal compression:** Recursive pruning creates detail near active zone, sparse further back
- **Modular design:** dag/ subdirectory with clear separation of concerns (#206)
- **Configurable thresholds:** All pruning/breach thresholds centralized in SwingConfig
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

### Outcomes

- **Accept** — All checks pass
- **Accept with Notes** — Minor issues tracked in Known debt
- **Requires Follow-up** — Create GitHub issue before accepting
- **Blocked** — Critical issue, must fix first

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
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
