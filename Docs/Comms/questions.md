# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-15-4: Detection Quality — Reactions vs Primary Structures

**From:** Product
**To:** Architect
**Date:** December 15, 2025

### Context

6 annotation sessions complete. Clear pattern emerged:
- 95% of true FPs are "too small" (54%) or "subsumed" (41%)
- FNs are consistently "biggest swing" or "most impulsive"
- Match rate: 50%

### The Problem

Detector finds **secondary reactions** instead of **primary structures**.

**User's characterization:**

- **"Subsumed":** Catches swings with endpoints *near* important levels but not *the* important swing. Example: catches a bounce after a selloff, misses the original meltdown. Finds echoes, not signals.

- **"Too small":** Almost always 1-2 candle ranges. Noise unless huge impulse (>5 candles of volume in 1-2 bars).

### Key Insight

**Significance is relative to context, not absolute:**

- 100pt in 2 candles: significant if surrounding candles are 10pt, noise if they're 60pt
- 50pt in 20 candles: noise if peers are 200pt, meaningful if it's the most recent unviolated swing providing tactical targets

Simple thresholds (min bar span, min size) won't work. Need relative significance scoring.

### Open Questions

1. Why are primary swings not detected? Are they:
   - Failing protection checks?
   - Outside Fibonacci zone?
   - Detected but ranked lower?

2. How should relative significance be scored? Factors:
   - Size relative to local volatility
   - Duration relative to scale
   - Recency (most recent unviolated)
   - Tactical value (provides actionable targets)

3. Should we collect "what I would have chosen instead" data for FP dismissals to understand detector-vs-human divergence?

### Related: Structural Validation Bug (Edge Case)

2-candle ranges can have invalid geometry. `swing_detector.py:363-375` checks intervening swing lows, not all bar lows. Becomes irrelevant if short-span ranges are filtered/de-prioritized.

### Deliverable

Design approach for detection quality improvement. Consider whether this is a filtering fix, ranking fix, or fundamental detection change.

### Status

**Blocked on data collection.** Before Architect can design a fix, we need:
1. Engineer to implement "better reference" field for FP dismissals
2. User to annotate with new tooling
3. Concrete "detector found X, should have found Y" data to analyze

This question will be ready for Architect after data collection phase.
