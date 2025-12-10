# User Interview Notes: Swing Visualization Harness

**Date:** December 9, 2025
**Interviewer:** Product Team
**Interviewee:** Rajesh (Domain Expert / Primary User)
**Project:** Fractal Market Simulator

---

## Context

Rajesh is building a fractal market simulator that generates realistic 1-minute OHLC price data by modeling actual market structure. The system uses Fibonacci-based extension and retracement rules where large price moves are composed of smaller moves following identical patterns across different scales.

Three foundational modules are complete and validated: swing detector, swing level calculator, and OHLC data loader. The next step is determining what to build.

---

## Primary Need Identified

Rajesh's immediate concern is ensuring the swing detection logic is genuinely robust before building behavioral models on top of it. Unit tests and sanity checks have passed, but he lacks confidence that the detection will behave correctly as new data arrives over time.

The fastest path to confidence is visualization. He wants to watch the system interpret market structure step by step, verifying that detected swings remain consistent, sane, and defensible as time progresses.

---

## Key Requirements Captured

### Input Structure

The system accepts a reference window of historical data (six months to one year of one-minute bars). This window establishes initial structure and calibrates scale boundaries. Playback begins at the end of the reference window and advances forward. Configuration requires only start and end bar indices.

### Multi-Scale Visualization

Four synchronized views displaying the same underlying price data at different structural scales: S (small), M (medium), L (large), XL (extra large). Any swing smaller than S is filtered out rather than tracked.

Scale boundaries are derived from the swing size distribution in the reference window using percentiles or deciles. This adaptive approach handles different instruments without manual calibration.

Each view uses an aggregation level appropriate to its scale. The aggregation should be chosen so that typical swings at that scale resolve across roughly 10 to 30 bars. This means the S view might show 1-minute bars while the XL view shows 4-hour bars.

### Swing Selection Logic

Each view shows only one swing at a time to avoid visual clutter. Selection priority:

1. If a swing experienced an event during the most recent step, show that swing with an annotation describing the event.
2. Otherwise, show the most prominent swing: the biggest one, unless an explosive swing exists within 80% of the biggest swing's size, in which case show the explosive one.

Rajesh explicitly chose single-swing display over showing all active references. Clarity of structure is the priority.

### Event Classification

Minor events: price crosses any Fibonacci level of an active reference swing. Initially track all standard levels (0.382, 0.5, 0.618, 1.0, 1.1, 1.382, 1.5, 1.618, 2.0). Refinement to make this configurable can come later.

Major events: structural changes only.
- Completion: price reaches the 2x extension of a reference swing.
- Invalidation: price closes below -0.1 level OR encroaches below -0.15 level.

### Swing Lifecycle

Critical clarification from Rajesh: completed and invalidated swings should not be deleted. Their Fibonacci levels remain valid because price may retrace to 1.5 or 1.382 after completion. A swing is only replaced when a new swing of approximately the same size forms.

This means swings have state (active, completed, invalidated) independent of existence. Invalidated swings remain visible with a distinct indicator until replaced.

### Cross-Scale Independence

Completion or invalidation at one scale does not cascade to other scales. Each scale maintains its own reference swings independently. The hierarchical constraint described in the spec governs generation, not detection/display.

### Playback Mechanics

Two modes discussed:

1. Manual mode: user clicks to advance by a configurable number of minutes. Default step size is one underlying data bar (one minute).
2. Automatic mode: continuous advancement at configurable speed, pausing on major events.

All four views remain synchronized in wall-clock time. When advancing one step, all views advance by the same elapsed time. Higher-timeframe views show incomplete bars that update as underlying bars close.

### Time Synchronization Detail

Rajesh confirmed the four views must stay time-synchronized. This means the M candle updates but does not take final shape until multiple S-level steps complete. The XL candle may take many steps before closing.

Incomplete bars should be visually distinct and should not affect Fibonacci level calculations. Only closed bars influence structural analysis.

---

## Explicit Non-Goals

Rajesh was clear about what this module should not do:

1. No trigger modeling or stochastic event generation. The goal is observing raw swing detection behavior in isolation.
2. No prediction or backtesting. This is a debugging and validation tool.
3. No learning or rule extraction. That comes later once swing detection is validated.
4. No persistence between sessions. State exists only during a playback run.

---

## Success Criteria

The module succeeds when Rajesh can:

1. Load a dataset and observe four-scale visualization updating as time advances.
2. See clear annotations when minor or major events occur.
3. Identify edge cases or inconsistencies in swing detection that were not apparent from raw data or unit tests.
4. Build confidence that the detection logic is stable enough to support behavioral modeling.

---

## Technical Preferences

Rajesh did not specify rendering technology but accepted matplotlib as a starting point with the understanding that performance may require optimization.

Aggregation should snap to standard timeframes (1, 5, 15, 30, 60, 240 minutes) rather than arbitrary intervals.

Sub-second responsiveness is desired for manual stepping. If matplotlib cannot achieve this, alternatives are acceptable.

---

## Open Questions Resolved During Interview

**Q: Should scale boundaries be fixed point ranges or percentile-based?**
A: Percentile-based, derived from the reference window. This adapts to different instruments.

**Q: How many swings per scale view?**
A: One. Show the swing with an event if one occurred; otherwise show the most prominent. Clarity over completeness.

**Q: What triggers invalidation?**
A: Close below -0.1 or any encroachment below -0.15. Not close below 0 (the swing low), except optionally for S-scale where noise is higher. Uniform rules preferred for simplicity.

**Q: Does completion at one scale affect other scales?**
A: No cascade. Swings at each scale are managed independently. Completed swings retain their levels until replaced by a new swing of similar size.

**Q: Step size for playback?**
A: Configurable, but default to one underlying bar. The four views need different aggregations, but they advance by the same wall-clock time.

---

## Deferred Features

The following were discussed but explicitly deferred to a second pass:

1. Automatic playback mode (manual stepping is sufficient for initial validation).
2. Manual override to pin a specific swing in a view.
3. Configurable level crossing events (initially track all levels).
4. Replaying arbitrary points within the reference window (start from end only).

---

## Downstream Implications

Once the harness validates swing detection, the next modules in sequence are:

1. State machine for single swing lifecycle (B1 in tech design).
2. Multi-timeframe swing container enforcing top-down constraint (B2).
3. Trigger-structure interaction rules (C3).

The harness output (event stream with timestamps and swing identifiers) may incidentally support manual rule inspection, but this is not the primary purpose.

---

## Quotes and Key Phrases

"I want to be able to watch the system think, step by step."

"The emphasis here is clarity of structure over predictive sophistication."

"My immediate concern is ensuring that the swing detection logic is genuinely robust."

"At 2x, it may begin retracement back to 1.5 or 1.382 level, so you're still not going to delete it until you have the next reference ready."

---

## Recommendations for Implementation

1. Verify existing modules against spec examples before building harness. The harness amplifies bugs; it does not diagnose them.

2. Start with manual stepping only. Automatic mode is a convenience feature that can follow.

3. Precompute aggregated bars for all scales during initial load to meet latency targets.

4. Track swing state (active/completed/invalidated) as first-class concept from the start.

5. Keep the event log cumulative across playback runs within a session for comparison.