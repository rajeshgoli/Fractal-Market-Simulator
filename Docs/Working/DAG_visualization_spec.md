# DAG Visualization Mode Spec

**Status:** Requirements captured. Awaiting Architect feasibility assessment.
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

## Context: Why This Before #163

Current state:
- DAG-based detection (#158) — Complete, 4.06s for 10K bars
- Reference layer (#159) — Complete, 580 tests passing
- Sibling swing detection (#163) — Spec approved, ready for engineering

Before implementing sibling detection, we need confidence that the current DAG behavior is correct. Visual validation is faster than abstract debugging. Once validated, #163 implementation can proceed with confidence.

---

## Open Questions for Architect

1. **DAG hooks:** Does HierarchicalDetector currently emit creation/pruning/invalidation events, or do we need to add instrumentation?

2. **Replay reuse:** How much of existing Replay View infrastructure (playback controls, linger logic, event handling) can we reuse directly?

3. **Two-chart layout:** Is this a new component, or can we extend current chart to support split view?

4. **State panel:** Can we reuse the existing explanation panel, or does DAG state need different rendering?

5. **Complexity estimate:** Is this a day, a week, or bigger?

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
