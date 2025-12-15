# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## From Product → Architect: Trend-Aware Reference Detection

**Date:** December 15, 2025

**Context:** User feedback identifies consistent FP pattern — detector emits reference ranges against the prevailing trend direction.

### The Problem

At XL and L scales, the detector finds geometrically valid swings regardless of trend context:
- Downtrending market → still emits bear references (counter-trend rallies)
- Uptrending market → still emits bull references (counter-trend pullbacks)

These are technically valid but contextually noise. User reports this as a major source of false positives.

### Question

**What's the best approach to add trend awareness to the swing detector?**

Options identified:
1. **Trend filter:** Calculate prevailing trend, suppress counter-trend references
2. **Directional weighting:** Downweight counter-trend swings in ranking (don't eliminate)
3. **User-specified bias:** Let user indicate market context per session
4. **Scale cascade:** Use XL trend to filter L, L trend to filter M, etc.

### Constraints

- Should not require major architectural changes
- Must preserve O(N log N) performance
- Trend calculation should be simple/robust (not ML-heavy)

### Requested Output

Feasibility assessment and recommended approach for implementation.

---
