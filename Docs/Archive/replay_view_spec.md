# Replay View Specification

**Status:** Ready for architect review
**Author:** Product
**Date:** 2025-12-16

---

## Context

The discretization pipeline is complete (#73-77) and we have a working overlay view (#78). However, static views don't build trust or intuition. Users need to **watch the system think** - see swings form, understand why they're detected, and compare system logic against their own mental model.

This is a debugging and trust-building tool, not just visualization.

## User Goals

1. **Understand detection logic**: "Why did you think this was a swing? Which high and low? What separated them?"
2. **Build intuition**: Watch structure unfold temporally at natural chart zoom levels
3. **Debug FP/FN**: Compare system decisions against implicit human judgment
4. **Top-down validation**: Start at XL to validate big picture before drilling into smaller scales

## Core Requirements

### 1. Split View with Independent Aggregation

Users should view charts at their natural zoom levels, not the system's default. Split view allows seeing the same time range at two different aggregation levels simultaneously.

**Layout:** Top/bottom stacked charts, each with its own aggregation selector.

**Required aggregations:** 5m, 15m, 1H, 4H, 1D

**Sync behavior:** Both charts stay time-synced during playback. Current bar position advances together.

The chart should re-aggregate bars when selection changes (we already have `BarAggregator` for this).

### 2. Playback Controls

| Control | Behavior |
|---------|----------|
| **Play** | Advance bars continuously at selected speed |
| **Pause** | Stop advancement; also triggered by events |
| **Step Forward** | Advance one bar |
| **Step Back** | Go back one bar |
| **Speed selector** | 1x, 2x, 5x, 10x (where 1x = 1 bar per second at source resolution) |

### 3. Event-Driven Linger

When a significant event occurs (SWING_FORMED, COMPLETION, INVALIDATION), playback should:

1. **Auto-pause** at the event bar
2. **Highlight** the relevant swing on the chart
3. **Show explanation** in the panel
4. **Display timer** - 15 second countdown before auto-resume

**Timer UX (refined):**
- Pause button has a circular progress wheel around it showing countdown
- Wheel completes over 30 seconds
- Clicking Pause pauses the timer until user clicks on play again
- Clicking Play skips ahead immediately
- Pause button is visually highlighted as the "primary action" during linger

### 4. Swing Detection Explanation

The core value prop. When SWING_FORMED fires, show:

**Visual on chart:**
- Current swing: highlighted with markers at high/low
- Previous swing (separation reference): shown dimmed with connecting line/label
- Both displayed on both charts in split view

```
SWING FORMED: XL BULL

Endpoints:
  High: 5862.50 at bar 1234 (2024-03-15 14:30)
  Low:  5750.00 at bar 1200 (2024-03-14 09:15)
  Size: 112.50 pts (1.92%)

Why this scale (XL):
  Size 112.50 pts >= XL threshold 100 pts

Separation from previous:
  Distance: 0.42 FIB levels from previous XL swing
  Minimum required: 0.236 FIB levels
  Reference grid: XL parent swing (id: abc123)

  [Visual: Previous swing highlighted on chart in dimmed color with label]

[For largest swing only]
  "Largest swing in calibration window - anchor point"
```

### 5. Event Filtering

User should control which events trigger linger:

| Event Type | Default | User Configurable |
|------------|---------|-------------------|
| SWING_FORMED | ON | Yes |
| COMPLETION | ON | Yes |
| INVALIDATION | ON | Yes |
| LEVEL_CROSS | OFF | Yes |
| SWING_TERMINATED | OFF | Yes |

---

## Data Requirements (Backend)

### SWING_FORMED Event Extension

Current `data` field:
```python
data: {
    "swing_id": str,
    "scale": str,
    "direction": str
}
```

**Required extension:**
```python
data: {
    "swing_id": str,
    "scale": str,
    "direction": str,
    "explanation": {
        "high_bar": int,
        "high_price": float,
        "high_timestamp": str,  # ISO 8601
        "low_bar": int,
        "low_price": float,
        "low_timestamp": str,   # ISO 8601
        "size_pts": float,
        "size_pct": float,
        "scale_reason": str,    # Human-readable: "Size 112.5 >= XL threshold 100"
        "is_anchor": bool,      # True if largest swing (no comparison)
        "separation": {         # null if is_anchor=True
            "from_swing_id": str,
            "distance_fib": float,
            "minimum_fib": float,
            "containing_swing_id": str | null
        }
    }
}
```

### API Endpoints

Existing endpoints should suffice:
- `GET /api/bars?scale={scale}` - Aggregated bars
- `GET /api/discretization/events` - All events with explanation data
- `GET /api/discretization/swings` - Swing registry

May need:
- `GET /api/discretization/events?bar_start={n}&bar_end={m}` - Windowed events for playback

---

## UX Wireframe

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Replay View                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ [1H ▼]                                              TOP CHART     │  │
│  │                                                                   │  │
│  │         ↓ H: 5862.50 (current swing)                              │  │
│  │          \                                                        │  │
│  │   ~~~~~~~ \___                                                    │  │
│  │   prev swing  ↑ L: 5750.00                                        │  │
│  │   (dimmed)                                                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ [5m ▼]                                            BOTTOM CHART    │  │
│  │                                                                   │  │
│  │    (same time range, different aggregation for detail)            │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ Bar: 1234 / 50000    2024-03-15 14:30                              ││
│  │                                                                     ││
│  │   [|◄] [◄] [ ▶ ] [(⏸)] [►|]     Speed: [1x ▼]                      ││
│  │              ↑                                                      ││
│  │         timer wheel                                                 ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ SWING FORMED: XL BULL                                              ││
│  │─────────────────────────────────────────────────────────────────────││
│  │ High: 5862.50 at bar 1234 (2024-03-15 14:30)                       ││
│  │ Low:  5750.00 at bar 1200 (2024-03-14 09:15)                       ││
│  │ Size: 112.50 pts (1.92%)                                           ││
│  │                                                                     ││
│  │ Scale: XL                                                           ││
│  │   → Size 112.50 >= threshold 100                                   ││
│  │                                                                     ││
│  │ Separation: PASSED                                                  ││
│  │   → 0.42 FIB from previous (min: 0.236)                            ││
│  │   → Previous swing shown dimmed on chart ↑                         ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  Event Filters: [x] Swing Formed [x] Completion [x] Invalidation       │
│                 [ ] Level Cross  [ ] Terminated                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Split View Behavior:**
- Top and bottom charts show same time range, synced during playback
- Each chart has independent aggregation selector (5m, 15m, 1H, 4H, 1D)
- Current swing highlighted on both charts
- Previous swing (for separation context) shown dimmed with label

---

## Acceptance Criteria

- [ ] Split view with top/bottom charts, each with independent aggregation selector
- [ ] User can select bar aggregation (5m, 15m, 1H, 4H, 1D) per chart
- [ ] Charts stay time-synced during playback
- [ ] Playback controls work (play, pause, step, speed)
- [ ] SWING_FORMED events pause playback and show explanation
- [ ] Explanation shows: which high, which low, size, scale reason, separation
- [ ] Previous swing (separation reference) shown dimmed on chart with label
- [ ] Pause button has timer wheel showing 30s countdown
- [ ] Clicking Pause freezes timer, clicking Play resumes/skips
- [ ] User can configure which events trigger linger

---

## Open Questions

1. **Scale thresholds**: Where are XL/L/M/S thresholds defined? Need to surface these in explanations.
2. **Largest swing**: Should we explain absolute size for the anchor swing, or just say "anchor point"?
3. **Multiple events at same bar**: How to handle? Queue them? Show all at once?

---

## Handoff Notes for Architect

1. **Backend first**: The `explanation` field in SWING_FORMED is the foundation. Without it, the UI has nothing meaningful to show.

2. **Detection logic is in `swing_detector.py`**: The thresholds and separation logic exist but aren't captured as human-readable strings. Need to add explanation generation during detection.

3. **Existing infrastructure**: `/discretization` view has most of the chart infrastructure. `/replay` can borrow heavily from it.

4. **Timer wheel**: CSS animation with `conic-gradient` or SVG arc - straightforward frontend work.
