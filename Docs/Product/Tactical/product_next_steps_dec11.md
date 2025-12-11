# Product Next Steps - Validation Mode Overhaul

**Date:** December 11, 2025
**Owner:** Product
**Status:** Ready for Architect Review
**Handoff To:** Architect (feasibility + performance review)

---

## Context

User has spent a day validating swing detection using the current harness. Core finding: **detection logic is working**, but the **tool is unusable for efficient validation**.

Current state feels like "intern project"—functional but not production-ready. The gap isn't missing features; it's coherent product design for the actual use case.

### User Quotes

- "Detection accuracy is pretty good... the challenge is it's too noisy at some scales"
- "To play out a month of data it takes me more than an hour"
- "It feels glitchy and buggy... not quite production ready when I look at latency and polish"
- "I'm in 'there are issues but they're fixable' phase"

---

## Core User Need

**Validate swing detection across months of historical data in minutes, not hours.**

The tool was designed for real-time playback visualization. The user needs rapid historical validation. These are different products.

---

## Requirements

### 1. Dynamic Bar Aggregation (Critical)

**Problem:** XL-scale shows 1m bars. User is drowning in noise when trying to see structure.

**Requirement:** Scale-appropriate candle density.

| View Mode | Target Candles |
|-----------|----------------|
| Quadrant (4-panel) | 40-60 |
| Zoomed (single panel) | ≤100 |

**Logic:** `aggregation = time_window / target_candle_count`, snapped to nearest standard resolution (1m, 5m, 15m, 1h, 4h, 1d).

| Scale | Typical Aggregation |
|-------|---------------------|
| S | 1m-5m |
| M | 5m-15m |
| L | 1h-4h |
| XL | 4h-1d |

Aggregation must be dynamic based on visible time window, not hardcoded per scale.

### 2. Event-Skip Mode (Critical)

**Problem:** Playing through history bar-by-bar is too slow. Hour+ for a month.

**Requirement:** Jump directly to next structural event.

- New keyboard shortcut: skip to next event (completion, invalidation, level crossing)
- Render only at event moments, not every bar
- Process intermediate bars for state accuracy, but don't render them
- Target: traverse a month in minutes

### 3. S-Scale Swing Cap (High)

**Problem:** S-scale shows 33 active swings. Unmanageable visual noise.

**Requirement:** Intelligent filtering.

- Default: show top 3-5 swings by (recency × size)
- Toggle to show all for detailed inspection
- Most recent event swing always visible

### 4. Stability Audit (High)

**Problem:** Bugs surface on zoom, pause/resume, layout transitions. Feels unreliable.

**Requirement:** One systematic pass through state management.

- Audit state preservation across all transitions
- Fix the class of bugs, not individual symptoms
- Goal: predictable behavior in all states

---

## Performance Constraints

**Scale:** 16 million bars (full ES dataset)

**Requirement:** All algorithms must be O(N) or better.

- Any O(N²) or worse patterns need explicit review and justification
- Profile "next event" implementation specifically
- Identify where time is actually spent before optimizing

### Architect Review Checklist

- [ ] Review current algorithm complexity for bar aggregation
- [ ] Review event detection loop complexity
- [ ] Profile current implementation with realistic data size
- [ ] Identify top 3 performance bottlenecks
- [ ] Assess feasibility of event-skip mode without full re-architecture
- [ ] Flag any requirements that conflict with current architecture

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Time to traverse 1 month | >1 hour | <10 minutes |
| S-scale visible swings | 33 | 3-5 (default) |
| Candles per panel | 1000s | 40-100 |
| State transition bugs | Multiple | Zero |

---

## What This Is NOT

- Not adding new detection logic
- Not changing swing rules or Fibonacci calculations
- Not building new product features (triggers, predictions, backtesting)
- Not premature optimization—profile first, then fix

---

## Handoff

**To Architect:**

1. Review feasibility of each requirement against current architecture
2. Profile current implementation to identify actual bottlenecks
3. Flag any O(N²) or worse patterns
4. Return with implementation approach or concerns

**Gating:** Do not begin implementation until architect confirms approach is sound.
