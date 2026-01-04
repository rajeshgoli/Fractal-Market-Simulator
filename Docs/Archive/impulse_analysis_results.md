# Impulse Analysis Results

**Data:** ES 30-minute (222,641 bars)
**Total formed legs:** 43,436
**Generated:** Issue #485

---

## Experiment 1: Impulse Distribution by Bin

Raw impulse = range / bar_count (points per bar)

| Bin | Multiplier | Count | Mean | Median | Std | P90 | Min | Max |
|-----|------------|-------|------|--------|-----|-----|-----|-----|
| 0 | 0.0×-0.3× | 3,169 | 1.710 | 1.250 | 1.475 | 3.500 | 0.107 | 11.000 |
| 1 | 0.3×-0.5× | 7,453 | 2.393 | 1.750 | 2.171 | 5.000 | 0.135 | 17.250 |
| 2 | 0.5×-0.75× | 8,933 | 3.393 | 2.417 | 3.112 | 7.250 | 0.156 | 22.500 |
| 3 | 0.75×-1.0× | 6,073 | 4.533 | 3.125 | 4.191 | 9.875 | 0.292 | 31.000 |
| 4 | 1.0×-1.5× | 7,946 | 5.660 | 3.750 | 5.542 | 12.000 | 0.365 | 46.500 |
| 5 | 1.5×-2.0× | 3,819 | 6.994 | 4.583 | 7.025 | 14.750 | 0.438 | 55.000 |
| 6 | 2.0×-3.0× | 3,560 | 8.870 | 5.833 | 9.013 | 18.750 | 0.598 | 74.250 |
| 7 | 3.0×-5.0× | 1,814 | 12.010 | 7.635 | 13.111 | 25.856 | 0.295 | 121.000 |
| 8 | 5.0×-10.0× | 577 | 16.543 | 10.900 | 17.611 | 35.000 | 0.241 | 135.000 |
| 9 | 10.0×-25.0× | 89 | 34.003 | 20.250 | 51.926 | 67.958 | 0.032 | 419.500 |
| 10 | 25.0×+ | 3 | 0.198 | 0.202 | 0.019 | 0.212 | 0.178 | 0.215 |

**Observation:** Median impulse for bins 8+ is 11.875 vs 2.938 for bins 0-7. Larger legs have higher impulse (unexpected).

---

## Experiment 2: Within-Bin Impulsiveness

Compare global percentile rank vs bin-local percentile for bin 8+ legs.

**Sample:** 669 legs in bins 8-10

**Global vs Local Percentile Difference:**
- Mean absolute difference: 41.3 percentage points
- Median difference: 40.3 percentage points
- Max difference: 92.5 percentage points

**Legs with >20pp ranking change:** 498 (74.4%)

**Sample (first 20 legs):**

| Leg ID | Bin | Impulse | Global % | Local % | Diff |
|--------|-----|---------|----------|---------|------|
| 3342... | 8 | 0.347 | 38.7 | 0.5 | +38.2 |
| 4244... | 8 | 1.082 | 61.5 | 1.9 | +59.6 |
| 4575... | 8 | 1.595 | 69.4 | 2.3 | +67.2 |
| 4611... | 8 | 0.241 | 18.3 | 0.0 | +18.3 |
| 4662... | 8 | 0.256 | 20.0 | 0.2 | +19.8 |
| 4690... | 8 | 0.265 | 27.3 | 0.3 | +26.9 |
| 4855... | 8 | 0.541 | 43.3 | 0.7 | +42.6 |
| 4883... | 8 | 0.750 | 50.0 | 1.0 | +49.0 |
| 4897... | 8 | 0.898 | 56.7 | 1.6 | +55.1 |
| 4946... | 8 | 0.647 | 45.0 | 0.9 | +44.1 |
| 4957... | 8 | 0.819 | 55.0 | 1.4 | +53.6 |
| 4902... | 8 | 0.812 | 55.7 | 1.2 | +54.5 |
| 4910... | 8 | 0.972 | 56.2 | 1.7 | +54.5 |
| 4918... | 8 | 1.250 | 62.5 | 2.1 | +60.4 |
| 5630... | 8 | 12.750 | 98.2 | 57.9 | +40.3 |
| 8415... | 8 | 10.400 | 98.0 | 48.7 | +49.3 |
| 9091... | 8 | 3.033 | 91.3 | 6.9 | +84.4 |
| 9195... | 8 | 9.875 | 98.4 | 45.4 | +53.0 |
| 9557... | 8 | 6.393 | 93.5 | 24.8 | +68.7 |
| 9636... | 8 | 8.562 | 82.4 | 37.4 | +44.9 |

---

## Experiment 3: Segment Impulse for Significant Legs

For parent legs in bin 8+ that have children:
- impulse_to_deepest: Impulse of primary move (origin → deepest)
- impulse_back: Impulse of counter-move (deepest → child origin)
- net_segment_impulse: impulse_to_deepest - impulse_back

**Sample:** 5,657 parent legs with segment data

| Metric | Mean | Median | Std | Min | Max |
|--------|------|--------|-----|-----|-----|
| impulse_to_deepest | 5.822 | 2.969 | 10.674 | 0.104 | 419.500 |
| impulse_back | 9.225 | 4.438 | 13.377 | 0.000 | 182.750 |
| net_segment_impulse | -3.403 | -1.062 | 14.721 | -160.500 | 396.125 |

**Net segment impulse distribution:**
- Positive (sustained conviction): 2,184 (38.6%)
- Negative (gave back progress): 3,467 (61.3%)
- Zero: 6 (0.1%)

---

## Experiment 4: Impulse Stability Over Leg Lifetime

Track impulse at bar counts 5, 10, 20, 50, 100 for legs that reach bin 8+.

**Sample:** 5,687 legs that reached bin 8+

| Bar Count | Legs | Mean Impulse | Median | Std |
|-----------|------|--------------|--------|-----|
| 5 | 5,678 | 6.936 | 4.083 | 10.998 |
| 10 | 5,612 | 5.428 | 3.150 | 9.535 |
| 20 | 5,461 | 4.177 | 2.364 | 8.767 |
| 50 | 4,980 | 2.094 | 1.271 | 3.086 |
| 100 | 4,089 | 1.289 | 0.809 | 1.831 |

**Observation:** Impulse decays as leg ages: median 4.083 at bar 5 → 0.809 at bar 100 (80% decay).

**Early impulse vs final range correlation:**
- Correlation between impulse at bar 10 and final range: 0.198
- Weak correlation: Early impulse doesn't strongly predict final range.

---

## Experiment 5: Child Formation Count by Bin

For parent legs in each bin, count how many children form.

| Bin | Parents | Mean Children | Median | Max | Total Children |
|-----|---------|---------------|--------|-----|----------------|
| 0 | 112 | 1.1 | 1 | 2 | 120 |
| 1 | 842 | 1.2 | 1 | 4 | 971 |
| 2 | 1,951 | 1.3 | 1 | 5 | 2,470 |
| 3 | 2,209 | 1.3 | 1 | 5 | 2,965 |
| 4 | 4,411 | 1.5 | 1 | 7 | 6,682 |
| 5 | 3,281 | 1.7 | 1 | 7 | 5,707 |
| 6 | 4,373 | 2.0 | 2 | 11 | 8,715 |
| 7 | 4,418 | 2.4 | 2 | 22 | 10,451 |
| 8 | 3,529 | 2.8 | 2 | 30 | 9,869 |
| 9 | 1,672 | 4.0 | 3 | 85 | 6,633 |
| 10 | 302 | 16.6 | 4 | 455 | 5,007 |

**Bin 8+ summary:** 5,503 parents, mean 3.9 children, median 2, max 455
→ Hypothesis NOT confirmed: mean children is 3.9, not ~50.

---

## Experiment 6: Segment Velocity Curve

For parent legs in bin 8+ with 10+ children, analyze velocity patterns.

Incremental velocity = |pivot_delta| / bar_delta between consecutive child formations.

**Sample:** 264 parents with 10+ children in bin 8+

**Velocity statistics across all segments:**

| Metric | Value |
|--------|-------|
| Count | 6,982 |
| Mean | 0.159 |
| Median | 0.000 |
| Std | 0.613 |
| Min | 0.000 |
| Max | 17.667 |
| P10 | 0.000 |
| P90 | 0.398 |

**Velocity pattern distribution:**

| Pattern | Count | Percentage |
|---------|-------|------------|
| accelerating | 0 | 0.0% |
| decelerating | 0 | 0.0% |
| choppy | 5 | 1.9% |
| steady | 259 | 98.1% |

**Key finding:** Steady is the most common pattern (98%).

**Sample velocity sequences (first 5 parents):**

- `5447` (11 children, steady): [0.00, 0.00, 0.00, 0.00, ..., 0.00, 0.00, 0.00, 0.00]
- `5606` (16 children, steady): [1.19, 0.55, 0.00, 0.54, ..., 0.00, 0.00, 0.04, 0.00]
- `5856` (11 children, steady): [0.16, 0.00, 0.00, 0.00, ..., 0.06, 0.00, 0.00, 0.00]
- `6145` (24 children, steady): [0.07, 0.00, 0.00, 0.14, ..., 0.17, 0.00, 0.00, 0.00]
- `6422` (33 children, steady): [0.00, 0.00, 0.00, 0.01, ..., 0.00, 0.00, 0.00, 0.00]

---

## Summary & Unexpected Findings

1. **Bin normalization significantly changes rankings** (avg 41.3pp difference). Within-bin impulsiveness may be more useful for comparing legs of similar scale.

2. **Many segments have negative net impulse** (39% positive). Counter-moves are often more impulsive than primary moves (unexpected).

3. **Impulse decays significantly over time** (80% decay from bar 5 to 100). Early impulse is much higher than mature impulse.

4. **Child event count is lower than expected** (mean 3.9 in bin 8+, not ~50). May limit velocity curve granularity.

