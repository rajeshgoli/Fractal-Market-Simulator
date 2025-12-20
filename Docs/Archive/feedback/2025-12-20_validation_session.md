# Validation Session Feedback Archive

**Date:** December 19-20, 2025
**Data:** test_data/es-5m.csv (offset 1172207)

## Filed as Issues

| Observation | Issue |
|-------------|-------|
| "Why isn't the bear leg using the same extrema that bull leg terminated in?" (bar 45) | #193 |

## Archived Observations

These observations were noted during validation but not filed as separate issues. They may be symptoms of #193 or require further investigation after that fix.

### 1. Missing legs in consolidation (bar 169)
> "Can you now answer why there are no legs in the chop in between?"

### 2. Origin not extending to current bar (bar 219)
> "Why are all the bull legs going up to the high of the last -1 bar when the last bar has a higher high?"

Likely related to #193 — pending pivot overwrite may affect origin extension.

### 3. Same-bar leg violation (bar 22)
> "In this state, why is there a bear leg from a single candle's high to low. This can never happen because H->L temporal order is not known, no?"

Possible temporal ordering bug — legs should not have pivot and origin on same bar unless confirmed by subsequent bar.

### 4. Unexpected pruning (bar 62)
> "Why is this bear leg and its sibling pruned here: BEAR active Pivot: 4433.50 Origin: 4422.25 Retr: 44.4% Bars: 23"

### 5. Orphan deduplication (bar 174)
> "If we have multiple orphaned origins on the same leg, we should keep the best one, just the same way we do with legs."

Feature request — currently multiple orphaned origins accumulate; should prune to best.

### 6. Turn pruning incomplete (bar 211)
> "Why aren't the 2 bear legs from before the turn at 4427 pruned down to 1?"

Turn pruning may not be reducing sibling legs as expected.

---

**Next steps:** Re-validate after #193 fix to see which issues persist.
