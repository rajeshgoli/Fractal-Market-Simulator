# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Product → Architect: Reference Swing Protection Validation

**Date:** December 15, 2025

### Context

User identified that `swing_detector.py` shows reference swings where the swing point has been violated by subsequent price action. This breaks the fundamental definition of a reference swing.

Example: Bull ref 1496→1369 shown, but price traded to 1261 afterward (low violated by 108 pts).

### Question

What's the cleanest path to fix this?

Options identified:
1. **Add protection check to `swing_detector.py`** - Extend existing detection with post-formation violation scan
2. **Switch annotator to use `bull_reference_detector.py`** - Already has `_check_low_protection`, but needs integration work

### Considerations

- `swing_detector.py` is O(N log N) optimized with RMQ structures
- `bull_reference_detector.py` has richer validation but different API
- This is P0 - annotation results are unreliable without this fix

