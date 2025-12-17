# Replay View Architecture Assessment

**Status:** Feasible - Ready for Engineering
**Author:** Architect
**Date:** 2025-12-16

---

## Feasibility Assessment

**Verdict:** Feasible with strong existing infrastructure. Backend explanation enrichment is the critical path.

### Strengths (Leverage Points)

1. **Discretization View exists** - `discretization.html` provides:
   - Lightweight-charts integration with candlestick rendering
   - Swing selection with Fib level lines
   - Event markers with tooltips
   - Scale filtering and aggregation
   - ~1100 LOC of reusable frontend code

2. **API endpoints exist** - `/api/discretization/*` provides:
   - Events, swings, levels endpoints
   - Scale and event type filtering
   - Bar aggregation via `BarAggregator`

3. **Separation logic exists** - `is_structurally_separated()` in `swing_detector.py`:
   - Uses 0.236 FIB minimum separation
   - Tracks `containing_swing_id`
   - Just needs explanation string generation

4. **Scale thresholds defined** - `ScaleCalibrator.DEFAULT_BOUNDARIES`:
   - ES: S(0-15), M(15-40), L(40-100), XL(100+) points
   - Ready to surface in explanations

### Gaps to Fill

1. **SWING_FORMED event data is minimal** - Currently only:
   ```python
   data: {"swing_id", "scale", "direction", "anchor0", "anchor1"}
   ```
   Needs enrichment with explanation fields.

2. **No windowed events API** - Need `bar_start`/`bar_end` params for playback efficiency.

3. **No replay page** - New `replay.html` needed (but can borrow heavily from `discretization.html`).

---

## Design Decisions

### D1: Timer Duration
Spec mentions both 15s and 30s. **Use 30s** - longer dwell time aids comprehension for debugging.

### D2: Multiple Events at Same Bar
Events occasionally cluster (e.g., swing formed + level cross). **Queue them** - show one at a time with implicit "next event" on timer expiry or manual skip.

### D3: Explanation Data Location
Generate explanation strings **at discretization time** (in `discretizer.py`), not at API read time. Rationale: explanation depends on detection context (thresholds, containing swings) that's harder to reconstruct later.

### D4: Split View Implementation
Two independent `LightweightCharts` instances sharing a time sync mechanism. Each chart manages its own aggregation but subscribes to a shared "current bar" state.

### D5: Scale Thresholds in Explanation
Embed actual threshold values from `ScaleCalibrator` in the explanation:
```
"Scale: XL (size 112.5 >= threshold 100)"
```
This surfaces the calibration for trust-building.

---

## Issue Decomposition

Six issues in three phases:

### Phase 1: Backend Foundation (Blocking)

**#82: Enrich SWING_FORMED events with explanation data**
- Add to `data` field: endpoints with timestamps, size metrics, scale_reason, is_anchor, separation details
- Source: `swing_detector.py` has the data; `discretizer.py` needs to capture it
- This is **P0** - all frontend work depends on it

**#83: Add windowed events API endpoint**
- Add `bar_start`, `bar_end` query params to `/api/discretization/events`
- Enables efficient playback (fetch events for visible window only)
- **P1** - can proceed with full event load initially

### Phase 2: Frontend Structure (Parallel)

**#84: Replay View - Split chart with independent aggregation**
- New `/replay` route serving `replay.html`
- Two stacked charts with aggregation selectors (5m, 15m, 1H, 4H, 1D)
- Time sync: both charts track same "current bar index"
- Borrow layout/styling from `discretization.html`

**#85: Playback controls**
- Play, pause, step forward, step back, speed selector (1x, 2x, 5x, 10x)
- Speed = bars per second at source resolution
- State machine: STOPPED | PLAYING | PAUSED (event linger)

### Phase 3: Event Experience (Sequential after Phase 2)

**#86: Event-driven linger with timer wheel**
- Auto-pause on SWING_FORMED, COMPLETION, INVALIDATION
- 30s countdown timer rendered as circular progress on Pause button
- Pause freezes timer, Play skips ahead
- Event filtering checkboxes for which events trigger linger

**#87: Swing explanation panel**
- Render enriched SWING_FORMED data in formatted panel
- Highlight current swing (bright) + previous swing (dimmed) on chart
- Show: endpoints, size, scale reason, separation distance

---

## Dependency Graph

```
#82 (Backend: explanation data)
 │
 └─► #84 (Split view) ──► #86 (Timer wheel)
 │                           │
 │                           └─► #87 (Explanation panel)
 │
 └─► #85 (Playback controls) ─┘

#83 (Windowed API) ── independent, can merge anytime
```

**Critical path:** #82 → #84 → #86 → #87

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Where are scale thresholds? | `ScaleCalibrator.DEFAULT_BOUNDARIES` |
| Largest swing explanation? | Show "anchor point" + absolute size |
| Multiple events same bar? | Queue, show sequentially |
| Timer 15s or 30s? | 30s for comprehension |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Backend explanation work larger than expected | Separation logic already exists; this is data plumbing not new algorithms |
| Dual chart performance | Lightweight-charts is designed for this; discretization view already performant |
| Timer wheel CSS complexity | Standard technique with `conic-gradient`; many examples available |

---

## Handoff

**Phase:** Ready for Engineering

**Owner:** Engineering (issue implementation)

**Parallel Execution:** Partial
- #82 and #83 can run in parallel (both backend)
- #84 and #85 can run in parallel (both frontend structure)
- #86 and #87 are sequential (both depend on #84/#85)

**First step:** Implement #82 (explanation enrichment) - this unblocks frontend work.
