# Interview Notes

Consolidated user interview notes. Most recent first.

---

## December 11, 2025 - Validation Experience Feedback

**Context:** Post-usage feedback after ~1 day of hands-on validation testing

### Key Findings

**Detection Logic:** Working. "Detection accuracy is pretty good in the tests I did."

**Primary Blockers:**
1. Too noisy at small scales (33 active swings on S-scale)
2. Too slow for validation (month takes >1 hour)
3. Visual noise from bar density (XL showing 1m bars)
4. Glitchy/buggy feel ("feels like an intern project")

**User Confidence:** "There are issues but they're fixable"

### Agreed Direction
1. Dynamic bar aggregation (40-60 candles per quadrant)
2. Event-skip mode (jump to next structural event)
3. S-scale swing cap (top 3-5 swings)
4. Stability audit (fix state transition bugs)

**Target:** Traverse a month in minutes, not hours.

---

## December 10, 2025 - Product Direction Sync

**Context:** Following architect proposal to start Market Data Generator

### Key Clarifications

**User Position:** Primary objective is validation of swing detection on historical data, NOT generation.

**Core Concern:** "The hard problem is correctness and robustness of the structural logic."

**Risk:** Layering complexity before core validation creates more risk than value.

### Outcome
- Generator development explicitly deferred
- Progress gated by correctness, not calendar
- Visual validation through expert review

---

## December 9, 2025 - Initial Swing Visualization Harness

**Context:** Determining what to build after foundational modules complete

### Primary Need

Visualization to watch system interpret market structure step by step. Build confidence that detection logic is stable enough for behavioral modeling.

### Key Requirements

1. **Multi-scale visualization:** Four synchronized views (S, M, L, XL)
2. **Swing selection:** One swing per view, prioritize events
3. **Event classification:** Minor (level crosses), Major (completion/invalidation)
4. **Swing lifecycle:** Completed/invalidated swings remain until replaced
5. **Cross-scale independence:** No cascade between scales
6. **Playback:** Manual stepping and auto mode with pause on events

### Success Criteria
- Load dataset and observe four-scale visualization
- See clear annotations on events
- Identify edge cases in swing detection
- Build confidence for behavioral modeling

### Key Quote
"I want to be able to watch the system think, step by step."
