# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-17-1: Replay View Architecture Redesign

**From:** Product
**To:** Architect
**Date:** 2025-12-17

### Context

User tested Replay View. UI is polished but replay model is fundamentally wrong for the intended purpose (causal evaluation of swing detection).

### Issues to Address

1. **No swings detected** — 10K 5m bars yields zero swings. Bug or missing scale/salience input?

2. **Look-ahead bias** — Current preload-and-scrub model shows entire future upfront. Need calibration-first, forward-only playback:
   - Calibration window establishes active swings
   - Play advances *beyond* window with new bars appearing
   - Events surface in real-time
   - Keep loading data until CSV exhausted

3. **Speed reference** — Currently tied to source resolution (5m). Should be relative to chart aggregation.

4. **Navigation** — `<<` / `>>` should jump to previous/next event, not bar.

### New UI Elements

- Scale toggles: XL, L, M, S
- Active swings dropdown: 1-5 (default 2)
- Calibration report in report area

### Questions

1. What's causing zero swing detection? Is there a calibration threshold issue or bug?
2. How should we architect the forward-only playback with progressive data loading?
3. Any concerns with the calibration → playback model from a technical standpoint?

### Reference

- User feedback: `Docs/Reference/interview_notes.md` (Dec 17 entry)
- Updated requirements: `Docs/State/product_direction.md` (P0 section)
- Original spec: `Docs/Working/replay_view_spec.md`

---
