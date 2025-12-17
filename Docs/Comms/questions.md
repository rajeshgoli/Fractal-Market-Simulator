# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## 2024-12-17: Replay View Playback Architecture (Issue #112)

**From:** Engineer
**To:** Architect
**Issue:** #112

### Context

The Replay View playback is not working as expected. Currently:
1. All source bars are loaded at startup via `fetchBars('S')`
2. Calibration analyzes the first N bars
3. During playback, the frontend filters pre-loaded bars based on position
4. The `/api/replay/advance` endpoint is called but new bars come from the same pre-loaded dataset

### Problem

The algorithm has already "seen" all bars at startup, including those meant for playback. This defeats the purpose of incremental playback - there's no true streaming of unseen data. The filtering approach just hides bars that were already processed.

### User's Expected Behavior

1. Calibrate on full 10k bars using the complete calibration window
2. During playback, load 1 bar at a time BEYOND calibration from the backend
3. Re-run detection incrementally as each new bar arrives
4. **No look-ahead** - the algorithm must not have seen playback bars during calibration

### Question for Architect

This appears to require architectural changes:

1. **Data loading:** Should the frontend only load calibration bars initially? Or should the backend limit what it returns based on a "playback window"?

2. **Incremental detection:** The `/api/replay/advance` endpoint already re-runs detection per bar. Is this the right approach, or should detection state be maintained and updated incrementally?

3. **Chart data:** Currently `chart1Bars` and `chart2Bars` (aggregated bars) are loaded once at startup. How should these be handled during playback - fetched incrementally or computed from new source bars?

4. **State management:** Where should the "current playback position" boundary be enforced - frontend filtering, backend API, or both?

Please provide architectural guidance on how to restructure this for true incremental playback without look-ahead.

---
