# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-15-2: FIB-Based Structural Separation for Extrema Selection

**From:** Product
**To:** Architect
**Date:** December 15, 2025

### Context

Ver4 annotation sessions show 42% of FPs are extrema selection problems (better_high/low/both). The algo finds swings in the right general area but anchors to sub-optimal endpoints that aren't "structurally significant."

User observation: The algo picks "a random lower high in a series of lower highs" with no qualifying low between it and the highest high. Or it picks a low that's not the structural low — one where a stop would be "casually violated."

### Proposed Solution

Use FIB levels from **larger-scale swings** (already established, no lookahead) to enforce structural separation:

```
Given: High A exists at scale S
To register High B at scale S:
  1. There must be a Low L between A and B
  2. L must be ≥1 FIB level away from High A (measured on scale M+ grid)
  3. High B and L must be ≥1 FIB level apart (on any larger scale grid)

For XL swings (no larger reference):
  → Fall back to N bars or X% move (volatility-adjusted)
```

### Why This Should Work

- **No lookahead** — Larger swings are historical
- **Market-structure-aware** — Separation measured in FIB units, not arbitrary thresholds
- **Scale-coherent** — Small swings must register on larger FIB grids
- **Self-consistent** — Uses existing multi-scale architecture

### Questions for Architect

1. **Feasibility:** Is this implementable given current SwingDetector and ScaleCalibrator architecture?
2. **Ordering:** Does detection need to run XL→L→M→S sequentially, or can scales still be processed in parallel with post-filtering?
3. **Which FIB levels?** User said "at least one FIB level" — should this be any standard level (0.382, 0.5, 0.618, 1.0) or a minimum threshold like 0.382?
4. **Edge cases:** What happens at window boundaries where larger swings may be incomplete?
5. **Performance:** Any concerns with referencing larger-scale FIB grids during small-scale detection?

### Reference

Full interview notes: `Docs/Reference/interview_notes.md` (December 15, 2025 - FIB-Based Structural Separation)

---
