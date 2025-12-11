# User Interview Notes: Validation Experience Feedback

**Date:** December 11, 2025
**Interviewer:** Product Manager (Claude)
**Interviewee:** Rajesh (Project Owner / Domain Expert)
**Context:** Post-usage feedback after ~1 day of hands-on validation testing

---

## Interview Summary

User spent a full day using the swing visualization harness to validate detection logic on historical data. The session surfaced critical usability gaps that are blocking effective validation work.

---

## Key Findings

### Detection Logic: Working

**User Assessment:** "Detection accuracy is pretty good in the tests I did."

- Swings appear correct when manually inspecting
- Larger scales correctly capture big swings per rules
- Core logic is sound—this is not a detection problem

### Primary Blockers

#### 1. Too Noisy at Small Scales
- S-scale detects 33 active swings, attempts to plot all
- "Obviously unmanageable"
- Need intelligent filtering, not raw display

#### 2. Too Slow for Validation
- Playing out a month takes more than an hour
- "I'm obviously not going to sit through that"
- Current architecture optimized for real-time playback, not rapid review

#### 3. Visual Noise from Bar Density
- XL-scale showing 1m bars—structure invisible in noise
- Need 40-60 candles in quadrant view, max 100 zoomed
- Aggregation should be dynamic based on time window, not hardcoded

#### 4. Glitchy/Buggy Feel
- "Feels like an intern project"
- State issues on zoom, pause/resume, layout transitions
- Latency and polish not production-ready

### User Confidence Level

**"There are issues but they're fixable"**

- Detection logic is fundamentally working
- Would want to look deeper to gain confidence
- But visualization tool is not easy to use right now
- Can't build confidence if the tool fights back

---

## Meta-Feedback: Process Issue

User observed that bugs were filed, engineer fixed them dutifully, but the process was reactive rather than purposeful.

**User Request:** "You really should step in here and apply taste as a product manager... drive this a bit more purposefully."

**Interpretation:** The product role was absent. Engineer was responsive but had no coherent vision to build toward. Need proactive product direction, not reactive bug triage.

---

## Technical Constraints Specified

- **Scale:** Must handle 16 million bars (full ES dataset)
- **Complexity:** All algorithms should be O(N)—anything worse needs scrutiny
- **Profiling:** Before optimizing, profile to see where time is actually spent

---

## Agreed Direction

### Immediate Focus (Priority Order)

1. **Dynamic bar aggregation** — 40-60 candles per quadrant, scale-appropriate resolution
2. **Event-skip mode** — Jump to next structural event, don't render every bar
3. **S-scale swing cap** — Default to top 3-5 swings, toggle for all
4. **Stability audit** — Fix state transition bugs as a class

### Success Target

- Traverse a month in minutes, not hours
- Clear structure visibility at every scale
- Predictable behavior across all UI states

---

## Handoff

Product next steps documented in `product_next_steps_dec11.md`.

Architect to review for:
- Feasibility against current architecture
- Performance profiling before implementation
- Algorithm complexity audit (O(N) requirement)

No implementation until architect confirms approach.
