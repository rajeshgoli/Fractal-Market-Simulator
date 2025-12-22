# Impulsiveness & Spikiness Scores

**Epic:** #241
**Date:** December 21, 2025

---

## Motivation

Issue #236 added a raw `impulse` field to legs, calculated as `range / bars`. While mathematically correct, this value is not trader-interpretable:

> "On its own, this field doesn't feel very useful to me. 'Points by time by bars' is hard to interpret as a trader—what does that really mean?"

The raw number lacks context. Is 10 points/bar impulsive? It depends on the market—what's impulsive at 1000 points differs from 4000 points. The same applies to different instruments and volatility regimes.

---

## Two Distinct Concepts

The raw impulse conflates two separate ideas:

### 1. Impulsiveness

How impulsive is this leg compared to all other legs we've seen?

> "We can make this a forward-only update—so all active legs get this impulsiveness score, and once they become inactive, we stop updating it. It would range from zero—the dullest leg that barely moves—to a hundred, the most impulsive leg we've seen."

**Key insight:** Impulsiveness is inherently scale-dependent. It must be normalized against historical context to be meaningful.

### 2. Spikiness

Was the move driven by a single sharp event, or is it a sustained regime change?

> "Sometimes a leg is very impulsive because one single candle (or a big gap) contributes all the movement. In that case, the spikiness score would be high. If it's a sustained move spread evenly across many candles, the spikiness would be low, even if the overall impulsiveness is high."

**Key insight:** Spikiness measures distribution shape, not magnitude. It's inherently scale-independent.

---

## Use Case

> "If I had to prioritize, I'd say the impulsiveness score is more important than spikiness."

Both metrics are actionable during leg formation, not just after:

> "Formed would miss impulsive legs as they form and continue. E.g., a leg that's impulsive but not spiky is usually a good one to go with (trend continuation). Stop loss at entry works in these scenarios. If you wait for it to be formed, it is useful info in reference calculation but not trades potentially if we do this in future."

**Signal:** High impulsiveness + low spikiness = sustained trend continuation, potentially tradeable.

---

## Design Decisions

### Which Legs Get Updated?

Only **live legs**—legs that can still grow (`max_origin_breach is None`).

> "So my sense is it's updated for all legs that can grow (we need a term for this, essentially I mean any bar whose max_origin_breach is None) in process_bars(). Once a leg stops growing we don't update it retroactively. For e.g., we saw a huge impulsive move it got a score of 100, then there were 30 more of those and it looks more like a 73 in this population. This doesn't mean we go and update that old leg."

### Population for Impulsiveness Ranking

All formed legs from history. No size threshold.

> "What if we didn't [filter by size]? We'll have a long tail distribution as long as they're all correctly represented with low numbers, shouldn't hurt, right?"

Tiny legs naturally cluster at low impulsiveness values. The distribution handles itself.

### Spikiness: Why Not `(mean - median) / mean`?

The original proposal was to track per-bar contributions and compute `(mean - median) / mean * 100`.

**Problem:** Computing median requires maintaining an array of all contributions or using heaps.

> "You can have a 10000 bar leg eventually. These will likely be very few. But—I don't like the idea of a O(bars) array per leg. That could get unwieldy quickly."

A heap-based approach (two heaps for streaming median) was proposed but rejected:

> "I don't like it. We're paying O(Log bars) price for heap insert and we have to do it every bar. We reach O(Bar Log Bar) just for this spikiness metric."

### Solution: Moment-Based Skewness

Fisher's skewness can be computed from running moments—O(1) per bar, O(1) space per leg:

```python
# Maintain per leg (O(1) space):
n, sum_x, sum_x2, sum_x3

# On each bar (O(1)):
contribution = bar.close - prev_bar.high  # bull leg
n += 1
sum_x += contribution
sum_x2 += contribution ** 2
sum_x3 += contribution ** 3

# Compute skewness:
mean = sum_x / n
variance = (sum_x2 / n) - mean**2
std_dev = sqrt(variance)
third_moment = (sum_x3 / n) - 3*mean*(sum_x2/n) + 2*mean**3
skewness = third_moment / (std_dev ** 3)
```

Skewness captures the same signal: positive = right-skewed = spike-driven.

### Normalizing Spikiness

Fisher's skewness is unbounded. To match impulsiveness (0-100), sigmoid normalization was chosen:

> "Why not sigmoid? Gives you nice 0-100 like impulsiveness? Is it less interpretable?"

Sigmoid works well:
- 50 = neutral (symmetric distribution)
- 70+ = moderately spiky
- 90+ = very spiky
- 30- = moderately smooth
- 10- = very smooth

```python
spikiness = 100 / (1 + exp(-skewness))
```

---

## Final Formulas

### Impulsiveness (0-100)

```python
raw_impulse = leg.range / (pivot_bar_index - origin_bar_index)
impulsiveness = percentile_rank(raw_impulse, formed_legs_population) * 100
```

- **Complexity:** O(log n) per update (binary search for percentile)
- **Space:** Population tracking required

### Spikiness (0-100)

```python
# Per-bar contribution
contribution = bar.close - prev_bar.high  # bull
contribution = prev_bar.low - bar.close   # bear

# Running moments (O(1) space)
mean = sum_x / n
variance = (sum_x2 / n) - mean**2
std_dev = sqrt(variance)
third_moment = (sum_x3 / n) - 3*mean*(sum_x2/n) + 2*mean**3
skewness = third_moment / (std_dev ** 3)

# Sigmoid normalization
spikiness = 100 / (1 + exp(-skewness))
```

- **Complexity:** O(1) per bar
- **Space:** O(1) per leg (4 floats)

---

## Summary

| Metric | What It Measures | Scale-Dependent? | Normalization |
|--------|------------------|------------------|---------------|
| **Impulsiveness** | Magnitude relative to history | Yes | Percentile rank |
| **Spikiness** | Distribution shape | No | Sigmoid of skewness |

Both metrics:
- Updated for live legs only
- Frozen when leg stops being live
- Output 0-100 for consistent interpretation

---

## Appendix: Design Discussion

Verbatim user quotes with summarized responses from the design conversation.

---

### On the Problem with Raw Impulse

**User:**
> "I'm reflecting on the epic we just implemented—adding the 'impulse' field. It's a great start, but on its own, this field doesn't feel very useful to me. 'Points by time by bars' is hard to interpret as a trader—what does that really mean?"

> "Instead, I think this encompasses two separate ideas. One is something like an 'impulsiveness score,' which tells me how impulsive a leg is compared to all the other legs we've seen so far."

> "The second aspect is how 'spiky' the impulse is. Sometimes a leg is very impulsive because one single candle (or a big gap) contributes all the movement."

---

### On When to Calculate

**User:**
> "We can't wait till formed to start calculating. Formed would miss impulsive legs as they form and continue. E.g., a leg that's impulsive but not spiky is usually a good one to go with (trend continuation). Stop loss at entry works in these scenarios."

> "So my sense is it's updated for all legs that can grow (we need a term for this, essentially I mean any bar whose max_origin_breach is None) in process_bars()."

**Response summary:** Proposed "live legs" as terminology for legs with `max_origin_breach is None`.

---

### On Freezing Scores

**User:**
> "Once a leg stops growing we don't update it retroactively. For e.g., we saw a huge impulsive move it got a score of 100, then there were 30 more of those and it looks more like a 73 in this population. This doesn't mean we go and update that old leg."

---

### On Population and Size Thresholds

**User:**
> "What if we didn't [filter by size]? We'll have a long tail distribution as long as they're all correctly represented with low numbers, shouldn't hurt, right?"

**Response summary:** Agreed. Tiny legs naturally cluster at low impulsiveness. No threshold needed—simpler is better.

---

### On Spikiness Formula

**User:**
> "Hmm, I was thinking of something like the following—open to thoughts. Measure bar.close - prev_bar.high. This tells you how much this bar truly moved the leg. In theory it could be a bar with a HH and HL, but still have close worse than last bar's high, this means it pushed price higher but next bar has to continue the work. But if the close of this bar is very high (spikes usually are), then this bar did the heavy lifting even if price retraces afterwards (think of spike and retrace with a large number of bear candles). We calculate a running mean and median, and normalize the difference against the population of legs as before."

**Response summary:** This approach captures whether bars "held" their extension, not just touched it. Proposed `(mean - median) / mean` as the raw spikiness measure.

---

### On Scale Independence

**User:**
> "Hmm, why would (mean - median) / mean be better vs (mean - median) alone? One reason I thought this is impulsiveness is scale dependent, spikiness on the other hand isn't. Meaning if you got 50% of contribution from one bar then if the leg is 100 pts or 500 pts, the spikiness is similar. Impulsiveness on the other hand measures how much it moved per bar. That has to be contextualized."

> "If not—simply using (mean - median) introduces a scale confounding factor. Legs will start to seem spikier as volume grows even if their actual 'spikiness' is sort of the same."

**Response summary:** Correct. Dividing by mean removes scale dependence. Impulsiveness needs percentile normalization; spikiness is already normalized.

---

### On Array Storage for Median

**User:**
> "You can have a 10000 bar leg eventually. These will likely be very few. But—I don't like the idea of a O(bars) array per leg. That could get unwieldy quickly."

**Response summary:** Proposed two-heap approach for O(log n) streaming median.

---

### On Heap Complexity

**User:**
> "I don't like it. We're paying O(Log bars) price for heap insert and we have to do it every bar. We reach O(Bar Log Bar) just for this spikiness metric."

**Response summary:** Proposed moment-based skewness as alternative—O(1) per bar, O(1) space. Track running moments (sum, sum², sum³) and compute Fisher's skewness directly.

---

### On Normalization

**User:**
> "Can we normalize this as well?"

> "Why not sigmoid? Gives you nice 0-100 like impulsiveness? Is it less interpretable?"

**Response summary:** Sigmoid maps unbounded skewness to 0-100. 50 = neutral, higher = spikier, lower = smoother. Same mental model as impulsiveness.

---

### On Keeping Raw Impulse

**User:**
> "Why replace? Why not keep the existing impulse metric (you're not showing it to the user but this is the input to calculations, no?)"

**Response summary:** Correct. Raw `impulse` stays as internal input to percentile calculation—just hidden from UI.
