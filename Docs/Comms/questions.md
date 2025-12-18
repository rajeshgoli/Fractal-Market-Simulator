# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-17-1: Replay View Feedback Capture Schema Design

**From:** Product
**To:** Architect
**Date:** December 17, 2025

### Context

User wants to capture free-form feedback during Replay View playback linger events. When observing swing detection behavior, they want to type observations and have them saved with full event context for later analysis.

### Current State

`ground_truth.json` is structured for annotation sessions:
- Metadata (schema_version, timestamps)
- Sessions array with:
  - AnnotationSession (scales, swings, window info)
  - ReviewSession (match/FP/FN feedback with verdicts and categories)

This is designed for the two-click annotation workflow, not real-time playback observations.

### What User Wants

During Replay View playback:
1. Text box appears during linger events
2. User types free-form observation (e.g., "Swing detected but price already hit 2x target")
3. On submit, saves feedback with event context
4. Typing pauses auto-advance timer

### Design Questions

1. **Schema location:** Should this be a new top-level structure in ground_truth.json, a new section within sessions, or a separate file entirely?

2. **Context to capture:** What event context should be saved with each feedback entry?
   - Swing H/L prices and bar indices
   - Detection bar index
   - Event type (SWING_FORMED, SWING_COMPLETED, etc.)
   - Scale (S/M/L/XL)
   - Timestamp
   - Playback bar counter
   - Anything else?

3. **Relationship to existing data:** How does this relate to annotation sessions? Is it independent, or should it link to a session ID?

4. **Retrieval use case:** User said "you (Claude) can read and debug my intent if I say when I gave the feedback." What structure makes this easy to query and contextualize?

### References

- Interview notes: `Docs/Reference/interview_notes.md` (Dec 17 PM)
- Detection observations to capture: Cascading detection, false positive after target achieved
- GitHub issue #115 (deferred item)

---
