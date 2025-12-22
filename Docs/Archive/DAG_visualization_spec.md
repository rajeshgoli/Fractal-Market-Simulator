# DAG Visualization Mode Spec

**Status:** FEASIBLE — Architect assessment complete. 3.5-5.5 days MVP estimate.
**Date:** Dec 19, 2025
**Owner:** Product

---

## Purpose

Temporary validation tool for the DAG-based swing detection algorithm. Watch the algorithm "think" in real-time to:

1. Validate that we're finding all structurally significant points
2. Identify if detection is too aggressive or too soft
3. Surface subtle bugs that aren't obvious from final output

**Lifecycle:** Use until DAG is rock solid, then remove. Not a permanent feature.

**Core insight:** "Easier to iterate visually than abstractly." — User

---

## Requirements

### Visual Layout

| Component | Content |
|-----------|---------|
| **Chart 1 (Macro)** | Larger zoom level — see overall structure building |
| **Chart 2 (Micro)** | Tighter zoom — see detail of current action |
| **State Panel** | DAG internals: orphaned 1s, active legs, candidate pools |

Two charts at different zoom levels allow seeing both the forest and the trees simultaneously.

### Playback Behavior

**Reuse existing Replay View infrastructure:**
- Same play/pause controls
- Same speed controls
- Same bar-by-bar progression

**New: Linger Toggle**
- **ON:** Pause on linger events (like current Replay behavior)
- **OFF:** Continuous playback without pausing

**Linger Events** (parallel to existing swing events):
| Event | Description |
|-------|-------------|
| Leg Created | New candidate leg formed |
| Leg Pruned | Leg removed (staleness, dominance, etc.) |
| Leg Invalidated | Leg fell below 0.382 threshold |

### On-Chart Visualization

- Legs **appear** when created (drawn on chart)
- Legs **visually change** when pruned or invalidated (different color, fade, removal)
- Watch the structure build in real-time as bars load

### State Panel Content

Display DAG internals that aren't visible on the chart:
- Orphaned 1s being tracked (for sibling detection)
- Active leg count per direction
- Candidate pool status
- Recent events log

---

## User's Core Question

> "Are we finding all structurally significant points at each stage, or being too aggressive/soft? Are there subtle bugs that are non-obvious?"

This tool answers that question through direct observation rather than inference from final output.

---

## Entry Point (CX Decision - Dec 19)

**Access via CLI flag:**

```bash
# Calibration mode (default, current behavior)
python -m src.ground_truth_annotator.main --data ES.csv --window 50000

# DAG Build mode (new)
python -m src.ground_truth_annotator.main --data ES.csv --window 50000 --mode dag
```

No hamburger menu. Lightweight approach — mode selected at startup. Frontend conditionally renders `<DAGView />` vs `<Replay />` based on server config.

**Rationale:** Temporary tool, minimal UI investment. CLI flag matches existing pattern.

---

## Context

Current state:
- DAG-based detection (#158) — Complete, 4.06s for 10K bars
- Reference layer (#159) — Complete, 580 tests passing
- Sibling swing detection (#163) — Complete

Visual validation enables confidence in algorithm behavior before further iteration.

---

## Architect Assessment (Dec 19, 2025)

### Answers to Open Questions

1. **DAG hooks:** No — HierarchicalDetector emits swing-level events only (SwingFormedEvent, etc.). Legs are tracked internally without events. Need to add `LegCreatedEvent`, `LegPrunedEvent`, `LegInvalidatedEvent`. **~0.5 days.**

2. **Replay reuse:** **95% reusable.** PlaybackControls, useForwardPlayback, linger logic all work. Need only to add a "linger toggle" (ON=pause-on-event, OFF=continuous). **~0.5 days.**

3. **Two-chart layout:** **Already exists!** `Replay.tsx` has dual charts with different aggregations. "Macro" and "Micro" map directly to existing `chart1` and `chart2`. **0 days.**

4. **State panel:** Structure reusable, content needs adaptation. Create `DAGStatePanel` showing orphaned origins, active legs, pending pivots. Data already available via `detector.state`. **~1 day.**

5. **Complexity estimate:** **3.5-5.5 days** for MVP:
   - Leg events instrumentation: 0.5 days
   - Linger toggle: 0.5 days
   - Two-chart layout: 0 days (exists)
   - State panel content: 1 day
   - On-chart leg visualization: 1-2 days
   - Backend API: 0.5 days
   - CLI entry point + routing: 0.5 days

### Recommendation

**PROCEED** — Contained change, high reuse potential. Suggested implementation order:
1. Add leg events (backend)
2. Add linger toggle (frontend)
3. Create DAG state panel (frontend)
4. Add leg visualization + CLI entry point (frontend + backend)

---

## Original Questions (Answered Above)

---

## Success Criteria

| Criterion | Description |
|-----------|-------------|
| See leg lifecycle | Watch legs appear, change state, disappear |
| Understand why | State panel shows reason for each transition |
| Control speed | Same playback controls as Replay View |
| Linger control | Toggle between pause-on-event and continuous |
| Two zoom levels | See macro and micro structure simultaneously |

---

## Non-Goals (Temporary Tool)

- Polish or production-quality UI
- Persistence of visualization state
- Export or sharing capabilities
- Mobile responsiveness

This is a developer tool for algorithm validation. Minimal viable implementation is fine.
