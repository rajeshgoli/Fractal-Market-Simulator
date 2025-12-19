# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## To Architect: DAG Visualization Mode Feasibility

**From:** Product
**Date:** Dec 19, 2025
**Priority:** High — blocks confidence in algorithm
**Spec:** `Docs/Working/DAG_visualization_spec.md`

### Summary

User wants to watch the DAG build in real-time during calibration. Visual iteration is faster than abstract debugging. Temporary tool — remove once algorithm is validated.

See full spec for requirements (two-chart layout, linger events, state panel).

### Questions

1. **DAG hooks:** Does HierarchicalDetector currently emit creation/pruning events, or do we need to add instrumentation?
2. **Replay reuse:** How much of existing Replay View infrastructure applies here?
3. **Two-chart layout:** New component or extension of current chart?
4. **State panel:** Reuse explanation panel or new rendering?
5. **Complexity estimate:** Is this a day, a week, or bigger?

### User's Core Question

"Are we finding all structurally significant points at each stage, or being too aggressive/soft? Are there subtle bugs?"

---
