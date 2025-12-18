# Architect Notes

## Onboarding

Read in order:
1. **`.claude/why.md`** — North Star
2. **This document** — Current state and active designs
3. **`Docs/Reference/developer_guide.md`** — Implementation details as needed

**Core architectural decisions:**
- Multi-scale (S/M/L/XL) with independent processing
- Fibonacci-based structural analysis (not arbitrary thresholds)
- Resolution-agnostic (1m to 1mo)
- Ground truth annotation as validation mechanism
- Sequential XL→L→M→S detection with `larger_swings` context passing
- Discretization: structural events, not per-bar tokens
- Calibration-first playback for causal evaluation

**Known debt:**
- `detect_swings()` function (~333 LOC) — monolithic; filter pipeline not extracted

**Cleanup tasks (deferred):**
- Delete `Docs/Archive/Proposals/Discretization/` once discretization pipeline is complete and documented in user_guide + developer_guide

---

## Current Phase: Replay View Playback Redesign + Feedback Capture Design

### Feedback Capture Schema Design (Q-2025-12-17-1)

**Decision:** Separate file (`playback_feedback.json`) — not part of `ground_truth.json`.

**Rationale:**
1. **Different workflow** — Playback observation ≠ annotation. Annotation sessions are deliberate two-click workflows; playback feedback is opportunistic observation capture.
2. **Different lifecycle** — Annotation sessions have phases (XL→L→M→S cascade). Playback observations are append-only stream.
3. **File size** — `ground_truth.json` is already 600KB+ with annotation data. Mixing workflows creates bloat and complicates querying.
4. **Query patterns** — User wants to ask "what did I observe on Dec 17?" not "what feedback relates to annotation session X?"

**Schema:**

```json
{
  "schema_version": 1,
  "playback_sessions": [
    {
      "session_id": "uuid",
      "data_file": "es-5m.csv",
      "started_at": "2025-12-17T14:30:00Z",
      "observations": [
        {
          "observation_id": "uuid",
          "created_at": "2025-12-17T14:35:22Z",
          "playback_bar": 1234,
          "event_context": {
            "event_type": "SWING_FORMED",
            "scale": "M",
            "swing": {
              "high_bar_index": 100,
              "low_bar_index": 150,
              "high_price": "4500.00",
              "low_price": "4400.00",
              "direction": "bull"
            },
            "detection_bar_index": 160
          },
          "text": "Swing detected but price already hit 2x target"
        }
      ]
    }
  ]
}
```

**Context Fields Captured:**

| Field | Purpose |
|-------|---------|
| `playback_bar` | Playback position — "where was I when I typed this?" |
| `event_type` | What triggered the linger (SWING_FORMED, SWING_COMPLETED, LEVEL_CROSS, etc.) |
| `scale` | S/M/L/XL — allows filtering observations by scale |
| `swing.*` | Full swing geometry — H/L prices and bar indices |
| `detection_bar_index` | When swing was detected — for debugging timing issues |
| `text` | Free-form observation — the actual user insight |

**Not Captured:**

- `playback_speed` — Not useful for debugging intent
- `active_filters` — UI state, not observation context
- Link to `annotation_session_id` — Different workflow

**Retrieval Examples:**

```python
# "Show me all observations about M-scale swings"
[o for s in data['playback_sessions']
   for o in s['observations']
   if o['event_context']['scale'] == 'M']

# "What did I observe on Dec 17?"
[o for s in data['playback_sessions']
   for o in s['observations']
   if o['created_at'].startswith('2025-12-17')]

# "Find observations about false positives after target achieved"
[o for s in data['playback_sessions']
   for o in s['observations']
   if 'target' in o['text'].lower()]
```

**Implementation Notes:**

1. File location: `ground_truth/playback_feedback.json` (alongside `ground_truth.json`)
2. Backend creates playback session on first `/api/replay/advance` call
3. New endpoint: `POST /api/playback/feedback` with body `{text: string, event_context: ...}`
4. Frontend sends event context from current linger state
5. Auto-pause timer on text input focus (already in product requirements)

---

### Playback Redesign (#112)

**Status:** Architecture guidance provided. Implementation required.

#### Problem Identified

User testing revealed a fundamental architecture flaw: the current implementation pre-loads ALL source bars at startup, meaning the algorithm has "seen" all data including bars meant for playback. The frontend filtering approach is cosmetic — it hides bars that were already processed during calibration. This defeats the purpose of incremental playback.

#### Architectural Decision

**Backend-controlled data boundary** — the backend should be the single source of truth for what bars are "visible" at any point in time.

**Rationale:**
1. Single responsibility — backend owns data loading; frontend owns visualization
2. No trust issue — frontend cannot accidentally receive future data
3. Simpler frontend — no complex filtering logic with potential bugs
4. Testable — backend behavior can be unit tested in isolation

#### Implementation Required

| Task | Scope | Status |
|------|-------|--------|
| Modify `init_app()` to only load calibration window | Backend | Pending |
| Add `playback_index` tracking to `AppState` | Backend | Pending |
| `/api/replay/advance` loads from disk/cache | Backend | Pending |
| `/api/bars` respects `playback_index` | Backend | Pending |
| Remove client-side filtering logic | Frontend | Pending |
| Re-fetch aggregated bars after advance | Frontend | Pending |

**Key Design:**

1. **Phase 1 - Calibration:** `init_app()` only loads calibration window into `source_bars`. Store `total_bars_available` and file reference for later loading.

2. **Phase 2 - Playback:** `/api/replay/advance` loads bars from disk/cache (not pre-loaded array), extends `source_bars`, runs detection on visible window.

3. **Detection Strategy:** Re-run detection per bar (current approach) is correct. O(N log N) detection takes <10ms for 10K bars.

---

## Recently Completed

**Epic #99 — Replay View v2:**

| Issue | Feature | Status |
|-------|---------|--------|
| #100 | Zero swings bug fix — `current_bar_index` param | Complete |
| #101 | Calibration phase — load window, detect swings, show report | Complete |
| #102 | Forward-only playback — incremental detection, event diffing | Complete |
| #103 | Speed control — aggregation-relative ("Nx per 1H") | Complete |
| #104 | Event navigation — ◀◀/▶▶ jump by event, not bar | Complete |
| #105 | Scale toggles — XL/L/M/S filters, active swing count dropdown | Complete |
| #111 | Swing markers — H/L labels, Fib levels on chart | Complete |

**Key implementation details:**

1. **CalibrationPhase state machine:** NOT_STARTED → CALIBRATING → CALIBRATED → PLAYING
   - CALIBRATED: User can cycle through active swings with `[`/`]` keys
   - PLAYING: Forward-only playback with real-time event detection

2. **useSwingDisplay hook:** Filters swings by enabled scales, ranks by size, limits to top N per scale

3. **useForwardPlayback hook:** POST /api/replay/advance fetches bars incrementally, diffs swing state for events

4. **Event diffing logic:** Compares previous vs new swing state to detect SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED, LEVEL_CROSS

---

## Next Steps

### 1. Playback Redesign Implementation

Create GitHub issues for the implementation tasks above. Backend changes first, then frontend cleanup.

### 2. User Testing (After Redesign)

Once playback is truly incremental:

1. **User testing** — Gather feedback on:
   - Calibration UX (is 10K bars appropriate default?)
   - Event navigation (are event types well-chosen?)
   - Scale filtering (is S-off default appropriate?)
   - Speed control (is aggregation-relative intuitive?)

2. **Performance profiling** — Monitor for:
   - Detection latency during forward playback
   - Memory usage during long sessions
   - Chart rendering performance with many swings

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | `current_bar_index` param for replay context |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode |
| Discretization Pipeline | Healthy | Core complete, visual overlay done |
| Replay View | **Needs Redesign** | Look-ahead bug in playback (#112) |
| Test Suite | Healthy | 780 tests (778 passing, 2 skipped) |
| Documentation | **Current** | Both guides updated Dec 17 |

---

## Documentation Status

| Document | Status | Action Needed |
|----------|--------|---------------|
| `Docs/Reference/developer_guide.md` | **Current** | Updated Dec 17 |
| `Docs/Reference/user_guide.md` | **Current** | Updated Dec 17 |
| `CLAUDE.md` | Current | - |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S, M, L, XL)
- **Fibonacci levels:** Extended grid for discretization (16 levels)
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars detection, <1hr for discretization (target)
- **Lean codebase:** 4 modules (data, swing_analysis, discretization, ground_truth_annotator)

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 17 | Q-2025-12-17-1 — Feedback capture schema design (#115) | Separate file, playback_feedback.json |
| Dec 17 | Q-2025-12-17-2 — Playback redesign architecture (#112) | Backend-controlled data boundary |
| Dec 17 | #101, #102, #104, #105, #111 — Calibration, forward playback, event nav, scale toggles | All Accepted, Epic #99 closed |
| Dec 17 | #100, #103, #107, #108, #109 — Zero swings fix, speed control, swing overlay, multi-swing nav | All Accepted |
| Dec 17 | Q-2025-12-17-1 — Zero swing bug diagnosis + forward-only playback design | Designed → Ready for engineering |
| Dec 16 | #84, #85, #86, #87, #89 — Replay View complete | All Accepted |
| Dec 16 | #78, #79, #81, #82, #83 — Discretization overlay, validation | All Accepted |
| Dec 16 | Replay View spec assessment | Feasible → Issues #82-#87 created |
| Dec 16 | #73, #74, #75, #76, #77 — Discretization core | All Accepted |
| Dec 16 | #68, #69, #70, #71 — Phase 3 + Architecture Overhaul | All Accepted |
