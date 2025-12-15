# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-15-2: Endpoint Selection Design

**From:** Product
**To:** Architect
**Date:** December 15, 2025

### Context

Ver3 sessions show 75% of FPs are endpoint selection issues (better_high/low/both). Core swing detection works; need to pick better endpoints.

### Questions

1. **Fib Confluence Implementation:**
   - Which larger swing(s) to reference? Immediate parent only, or all ancestors?
   - Should we score by "fib confluence count" (how many fib levels from different swings converge)?
   - What tolerance for "near a fib level"? (e.g., within 0.5% of price?)

2. **Best Extrema in Vicinity:**
   - How to define "vicinity"? Bar count? % of swing range?
   - Should this be a post-filter or integrated into initial detection?

3. **Quota per Scale:**
   - How to rank swings for the quota? Size + impulse weighting?
   - Is "2 biggest + 2 highest impulse" a reasonable starting point for XL?

### User Preferences

- Fib confluence = primary importance signal
- Best extrema = tie breaker
- Quota controls quantity, no threshold tuning needed

Please design implementation approach and add to architect_notes.md when ready.
