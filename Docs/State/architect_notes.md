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
- Discretization: structural events, not per-bar tokens
- Calibration-first playback for causal evaluation
- Backend-controlled data boundary for replay (single source of truth)
- **DAG/Reference separation:** Structural tracking vs semantic filtering
- **Rules by construction:** Temporal ordering from bar relationships (Type 1/2/3)
- **Strict inter-bar causality:** Legs only form when pivots are from different bars (#189)
- **Turn pruning:** Within-origin (keep largest) + active swing immunity
- **Modular DAG layer:** dag/ subdirectory with LegDetector, LegPruner, state, calibrate, leg modules (#206)
- **Structure-driven pruning:** Proximity consolidation (5%), pivot breach (10%), engulfed (strict) (#203, #208)
- **Impulse scoring:** Range/duration metric + impulsiveness/spikiness percentiles (#236, #241)
- **Inner structure pruning:** Counter-direction legs from contained pivots pruned regardless of swing status (#264, #266)

**Known debt:**
- #176 — `get_windowed_swings` missing Reference layer during calibration (fix after validation)
- #177 — Minor: missing `invalidated_at_bar` field, AppState/cache duplication

---

## Current Phase: L1-L7 Validation

### Recent Changes — Dec 22 Review

All 10 pending changes accepted. Summary:

| Issue(s) | Summary | Outcome |
|----------|---------|---------|
| #241 (#242-#247) | Impulsiveness & spikiness scores | Accepted — Well-documented metrics with O(log n) percentile and O(1) moments |
| #248, #249 | Documentation fixes | Accepted — Debt cleared |
| #250 (#251-#258) | Hierarchy Exploration Mode | Accepted — Tree icon, lineage API, focus/ancestor/descendant highlighting |
| #260 | Feedback endpoint crash fix | Accepted — Removed stale FeedbackAttachmentOrphanedOrigin reference |
| #261 | Disable 3x invalidated leg cleanup | Accepted — stale_extension_threshold=999.0 |
| #263 | Chart maximize/minimize controls | Accepted — UX enhancement |
| #264 | Inner structure leg pruning | Accepted — Counter-direction pruning on nested invalidation |
| #265 | Test refactoring | Accepted — Split test_hierarchical_detector.py into 5 logical modules |
| #266 | Remove swing immunity for inner structure | Accepted — Policy change, inner legs pruned regardless of swing |
| Bugfix | Engulfed pruning for invalidated legs | Accepted — Pivot breach now tracked for invalidated legs |

**Architectural observations:**
1. **Impulse metrics (#241)**: Clean implementation using bisect for O(log n) percentile lookup and running moments for O(1) spikiness updates. Metrics frozen when origin is breached — prevents stale updates.

2. **Hierarchy exploration (#250)**: Appropriate use of existing dag/ abstractions. Lineage API returns ancestors/descendants efficiently. Frontend uses new useHierarchyMode.ts hook.

3. **Inner structure pruning (#264, #266)**: Significant policy change — removing swing immunity means formed swings can be pruned if structurally contained. This is correct: inner structure is redundant when outer-origin legs exist with same pivot.

4. **Stale cleanup disabled (#261)**: Setting stale_extension_threshold=999.0 effectively disables the feature. Other pruning mechanisms (proximity, breach, engulfed) handle cleanup adequately.

### Pivot/Origin Semantics — FIXED

**#188-#197 resolved:** The terminology cascade has been fixed. All code now correctly enforces:

| Leg Type | Origin | Pivot | Temporal Order |
|----------|--------|-------|----------------|
| Bull | LOW (move started) | HIGH (defended extreme) | origin_index < pivot_index |
| Bear | HIGH (move started) | LOW (defended extreme) | origin_index < pivot_index |

**#198 architectural audit completed:** Type classification, symmetric frames, and semantic enforcement reviewed. Conclusion: current design is sound. See `Docs/Working/arch_audit.md`.

### Pending Spec: Follow Leg (#267)

Product has submitted a spec for Follow Leg feature (`Docs/Working/follow_leg.md`). **Architectural assessment:**

1. **Event tracking** — Reuses existing LegDetector/LegPruner events. No new backend logic needed for events themselves.
2. **API endpoint** — New polling endpoint for followed legs. Low complexity.
3. **CSV index mapping** — Useful improvement for all attachments. Should be included in implementation.
4. **5-leg limit** — Reasonable constraint to prevent UI clutter and performance issues.
5. **No retroactive events** — Correct design decision, simplifies implementation.

**Assessment:** Spec is sound. Ready for engineering breakdown into sub-issues.

### Next: Validate L1-L7 Detection

With semantics enforced and codebase clean, L1-L7 validation can proceed:

| Label | Structure | Expected Status |
|-------|-----------|-----------------|
| **L1** | 1=6166, 0=4832 | Should detect |
| **L2** | 1=5837, 0=4832 | Should detect (sibling of L1) |
| **L3** | 1=6955, 0=6524 | Should detect |
| **L4** | 1=6896, 0=6524 | Should detect (sibling of L3) |
| **L5** | 1=6790, 0=6524 | Should detect (sibling of L3) |
| **L6** | 1=6929, 0=6771 | Should detect |
| **L7** | 1=6882, 0=6770 | Should detect |

**Validation method:** Use DAG Build Mode to observe leg/swing formation at key price levels. Hierarchy exploration mode now available to visualize parent-child relationships.

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| LegDetector (dag/) | **Complete** | O(n log k), modularized into 5 modules |
| LegPruner (dag/) | **Complete** | Handles all pruning: domination, proximity, breach, engulfed, inner structure |
| Temporal Causality | **Fixed** | Strict inter-bar ordering (#189) |
| Leg Origin Updates | **Fixed** | Origins update on price extensions (#188) |
| SwingConfig | Complete | Centralizes all parameters including thresholds |
| SwingNode | Complete | DAG hierarchy model |
| ReferenceFrame | Complete | Central coordinate abstraction |
| ReferenceLayer | Complete | Tolerance/completion rules |
| Turn Pruning | Complete | Within-origin pruning + active swing immunity |
| Pivot Breach Pruning | Complete | 10% threshold with replacement leg (#208) |
| Engulfed Detection | Complete | Strict (0.0 threshold) deletes leg (#208, #236) |
| Proximity Consolidation | Complete | 5% relative difference consolidation (#203) |
| Inner Structure Pruning | **Complete** | Counter-direction pruning, no swing immunity (#264, #266) |
| Impulse Metrics | **Complete** | Impulsiveness (percentile) + spikiness (sigmoid) (#241) |
| Replay View | Complete | Tree-based UI, forward playback |
| DAG Visualization | Complete | Leg/origin visualization, hover highlighting, chart interaction |
| Hierarchy Exploration | **Complete** | Tree icon, lineage API, focus/ancestor/descendant display (#250) |
| Chart Controls | **Complete** | Maximize/minimize per chart (#263) |
| Discretization | Complete | Works directly with SwingNode (no adapter) |
| V2 API Schemas | Complete | HierarchicalSwingResponse, depth-based grouping |
| Legacy Code | **Deleted** | All pre-DAG modules removed (#210, #219, #228) |
| Test Suite | Healthy | 600+ tests passing, refactored into logical modules (#265) |
| Documentation | **Current** | user_guide.md and developer_guide.md updated |

---

## Documentation Status

| Document | Status | Notes |
|----------|--------|-------|
| `developer_guide.md` | Current | Includes impulse metrics, inner structure pruning, hierarchy exploration |
| `user_guide.md` | Current | Includes chart controls, hierarchy exploration mode, leg metrics |
| `CLAUDE.md` | Current | — |

---

## Architecture Principles

- **Hierarchical model:** Swings form a DAG, not discrete buckets
- **Single algorithm:** process_bar() for both calibration and playback
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance target:** <5s for 10K bars (achieved: 4.06s)
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)
- **Backend-controlled boundaries:** Backend owns data visibility
- **DAG/Reference separation:** DAG tracks structural extremas; Reference layer defines "good reference" semantics
- **Rules by construction:** Temporal ordering enforced by bar relationships, not post-hoc filtering
- **Strict inter-bar causality:** Legs require pivots from different bars (#189)
- **Fractal compression:** Recursive pruning creates detail near active zone, sparse further back
- **Modular design:** dag/ subdirectory with clear separation of concerns (#206)
- **Configurable thresholds:** All pruning/breach thresholds centralized in SwingConfig
- **Strong deletion bias:** Actively remove unused code to maintain codebase clarity
- **No swing immunity for structure:** Inner structure legs pruned regardless of formation status (#266)

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
