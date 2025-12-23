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
- **Structure-driven pruning:** Origin-proximity consolidation (time+range), pivot breach (10%), engulfed (strict) (#203, #208, #294)
- **Impulse scoring:** Range/duration metric + impulsiveness/spikiness percentiles (#236, #241)
- **Inner structure pruning:** Counter-direction legs from contained pivots pruned regardless of swing status (#264, #266)
- **Leg hierarchy:** Parent-child relationships with reparenting on prune (#281)
- **Runtime config:** Detection parameters adjustable via UI without restart (#288)

**Known debt:**
- #282 — Inner structure pruning should check active/larger bear legs at same pivot (follow-up from #264)
- #262 — Prune orphaned inner structure legs at 3x completion
- #240 — TODO: Empirically determine engulfed retention threshold based on impulse
- #176 — `get_windowed_swings` missing Reference layer during calibration (fix after validation)
- #177 — Minor: missing `invalidated_at_bar` field, AppState/cache duplication

---

## Current Phase: L1-L7 Validation

### Recent Changes — Dec 23 Review

All 9 pending changes accepted. Summary:

| Issue(s) | Summary | Outcome |
|----------|---------|---------|
| #294 | Origin-proximity pruning | Accepted — Clean redesign replacing pivot-based proximity with origin (time, range) consolidation |
| #288 (#289-#292) | Detection Config UI Panel | Accepted — Runtime threshold adjustment with pruning toggles |
| #261 | Child-only stale extension pruning | Accepted — Re-enabled at 3.0× for child legs, roots preserved |
| #281 | Leg hierarchy (parent-child) | Accepted — Fundamental improvement with reparenting on prune |
| #279 | Sequential invalidation fix | Accepted — Inner structure now checks previously invalidated legs |
| #278 | Backward navigation | Accepted — Backend reverse replay API |
| #283 | Batch DAG states | Accepted — Performance: per-bar states in batch response |
| #267 (#268-#276) | Follow Leg Feature | Accepted — Complete lifecycle tracking with visual markers |
| Aggregation | Standard timeframe options | Accepted — 1m-1W with dynamic filtering |

**Architectural observations:**

1. **Origin-proximity pruning (#294)**: Major improvement over pivot-based proximity. The (time, range) space consolidation is conceptually cleaner — legs that started at similar times with similar ranges are genuinely redundant, whereas pivot grouping was too aggressive. Defensive check for invariant violations is good practice.

2. **Detection Config Panel (#288)**: Proper separation — UI adjusts config, backend re-calibrates. The pruning toggles are valuable for understanding individual algorithm contributions. Config update preserves immutability via `with_*` methods.

3. **Leg hierarchy (#281)**: The `parent_leg_id` field with `reparent_children()` on prune is architecturally sound. Maintains hierarchy chain without gaps. Critical for understanding nested structure.

4. **Follow Leg (#267)**: Well-scoped feature. 5-leg limit prevents UI clutter. Color palette handles bull/bear distinction. Event markers (F/P/E/X/O!/P!) provide clear visual feedback. Implementation reuses existing LegDetector/LegPruner events.

5. **#282 requires follow-up**: Inner structure pruning has a gap — should check active/larger bear legs at same pivot before pruning bull leg from that pivot. This is a correctness issue, not a blocker, but should be addressed soon.

### Pivot/Origin Semantics — FIXED

**#188-#197 resolved:** The terminology cascade has been fixed. All code now correctly enforces:

| Leg Type | Origin | Pivot | Temporal Order |
|----------|--------|-------|----------------|
| Bull | LOW (move started) | HIGH (defended extreme) | origin_index < pivot_index |
| Bear | HIGH (move started) | LOW (defended extreme) | origin_index < pivot_index |

**#198 architectural audit completed:** Type classification, symmetric frames, and semantic enforcement reviewed. Conclusion: current design is sound. See `Docs/Working/arch_audit.md`.

### Pending: #282 Inner Structure Refinement

Issue #282 identifies a gap in inner structure pruning logic. Before pruning a bull leg from a bear's pivot, should verify:
1. No active bear legs share that pivot
2. No larger invalidated bear legs share that pivot

**Recommendation:** File as engineering task, priority normal.

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
| LegPruner (dag/) | **Complete** | Handles all pruning: domination, origin-proximity, breach, engulfed, inner structure |
| Leg Hierarchy | **Complete** | Parent-child with reparenting (#281) |
| Origin-Proximity Pruning | **Complete** | Time+range consolidation replaces pivot-based (#294) |
| Temporal Causality | **Fixed** | Strict inter-bar ordering (#189) |
| Leg Origin Updates | **Fixed** | Origins update on price extensions (#188) |
| SwingConfig | Complete | Centralizes all parameters including pruning toggles (#288) |
| SwingNode | Complete | DAG hierarchy model |
| ReferenceFrame | Complete | Central coordinate abstraction |
| ReferenceLayer | Complete | Tolerance/completion rules |
| Turn Pruning | Complete | Within-origin pruning + active swing immunity |
| Pivot Breach Pruning | Complete | 10% threshold with replacement leg (#208) |
| Engulfed Detection | Complete | Strict (0.0 threshold) deletes leg (#208, #236) |
| Inner Structure Pruning | **Needs refinement** | Same-pivot check gap (#282) |
| Impulse Metrics | **Complete** | Impulsiveness (percentile) + spikiness (sigmoid) (#241) |
| Replay View | Complete | Tree-based UI, forward playback |
| DAG Visualization | Complete | Leg/origin visualization, hover highlighting, chart interaction |
| Hierarchy Exploration | **Complete** | Tree icon, lineage API, focus/ancestor/descendant display (#250) |
| Chart Controls | **Complete** | Maximize/minimize per chart (#263) |
| Detection Config Panel | **Complete** | Runtime threshold adjustment (#288) |
| Backward Navigation | **Complete** | Backend reverse replay API (#278) |
| Follow Leg Feature | **Complete** | Lifecycle tracking, event markers (#267) |
| Batch DAG States | **Complete** | Per-bar states in response (#283) |
| Discretization | Complete | Works directly with SwingNode (no adapter) |
| V2 API Schemas | Complete | HierarchicalSwingResponse, depth-based grouping |
| Legacy Code | **Deleted** | All pre-DAG modules removed (#210, #219, #228) |
| Test Suite | Healthy | 628 tests passing |
| Documentation | **Current** | user_guide.md and developer_guide.md updated |

---

## Documentation Status

| Document | Status | Notes |
|----------|--------|-------|
| `developer_guide.md` | Current | Includes origin-proximity pruning, leg hierarchy, detection config |
| `user_guide.md` | Current | Includes detection config panel, follow leg, backward navigation |
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
- **Runtime configurability:** Detection parameters adjustable without restart (#288)

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
