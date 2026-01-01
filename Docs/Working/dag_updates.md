# DAG Updates

Collect DAG layer changes before proceeding to Reference Layer Phase 2.

---

## 1. Engulfed Prune Threshold

**Status:** Profiled, ready for implementation

**Problem:** Currently engulfed legs (both origin and pivot breached) are pruned immediately. Reference Layer may want to use recently-engulfed legs as references since it has looser tolerance for origin breach.

**Solution:** Add configurable threshold — only prune engulfed legs when at least one side exceeds threshold × range.

**Profiling Results (206K bars, es-30m):**

| Threshold | Retention Rate | Peak Overhead |
|-----------|---------------|---------------|
| 0.236 | 12.1% | +7.2% (13 legs) |
| 0.382 | 23.7% | +10.6% (19 legs) |

**Recommendation:** 0.236 threshold (first fib level)

**Implementation:**
1. Add `engulfed_prune_threshold: float = 0.236` to `DetectionConfig`
2. Modify `prune_engulfed_legs()`:
   ```python
   if leg.max_pivot_breach is not None and leg.max_origin_breach is not None:
       threshold = self.config.engulfed_prune_threshold
       if threshold == 0:
           # Immediate prune (legacy behavior)
           legs_to_prune.append(leg)
       else:
           threshold_amount = threshold * float(leg.range)
           if (float(leg.max_origin_breach) > threshold_amount or
               float(leg.max_pivot_breach) > threshold_amount):
               legs_to_prune.append(leg)
   ```

**Files:** `detection_config.py`, `leg_pruner.py`

**Resolves:** Known debt #240 (empirically determine engulfed retention threshold)

---

## 2. (Add next item here)

---

## Implementation Order

(To be determined after all items collected)

---

## Notes

- All changes should maintain backward compatibility via config defaults
- Profile each change individually before combining
- Run full test suite after implementation
