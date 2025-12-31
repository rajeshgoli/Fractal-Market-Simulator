# Leg Analysis Report

**Date:** December 24, 2025
**Data:** ES 30m, Dec 23, 2021 - May 1, 2025 (39,535 bars)
**Cached:** `cache/leg_analysis_cache.json`

---

## Executive Summary

With origin-proximity pruning **disabled** (current default), the detector produces **severe redundancy**: 159 legs share the same pivot at 6166.5. This represents noise that would crowd out signal in any trading algorithm.

**Key finding:** The current pruning settings are too loose. Enabling moderate proximity thresholds reduces leg count from 180 to 41 (77% reduction) while preserving structurally significant levels.

**Recommendation:** Enable origin-proximity pruning with:
- `origin_range_prune_threshold = 0.05` (5%)
- `origin_time_prune_threshold = 0.10` (10%)

---

## 1. Current State (Pruning Disabled)

| Metric | Value |
|--------|-------|
| Total legs | 311 |
| Active legs | 180 |
| Formed legs | 297 |
| Bull legs (active) | 141 |
| Bear legs (active) | 39 |

### Redundancy at Pivot 6166.5

**159 bull legs** share the exact same pivot (6166.5), differing only in origin. Origins range from 3502 to 5813 — spanning 2300+ points. From an algo perspective, these all represent the **same structural level**.

Origin distribution at pivot 6166.5 (100-point bins):

| Origin Range | Leg Count |
|--------------|-----------|
| 3500-3599 | 2 |
| 3600-3899 | 27 |
| 3900-4099 | 15 |
| 4100-4499 | 26 |
| 4500-4899 | 39 |
| 4900-5199 | 16 |
| 5200-5899 | 34 |

**Conclusion:** 95%+ of these legs are redundant for trading purposes.

---

## 2. L1-L7 Reference Legs

From `Docs/Reference/valid_swings.md`, a human chart reader identifies 7 key reference swings. Only L1 and L2 are in our date range (L3-L7 involve prices above 6166).

| Label | Expected | Status |
|-------|----------|--------|
| **L1** | pivot=6166, origin=4832 | Partial match: origin=4808 found with pivot=6166 |
| **L2** | pivot=5837, origin=4832 | Found: 6 legs at pivot 5837 |
| L3-L7 | prices 6500+ | Not in date range (May 2025 cutoff) |

### Why L1 Doesn't Match Exactly

The leg from origin=4832 exists but has pivot=5649, not 6166. This is correct behavior:

- **April 6, 2025:** Price drops to 4832 (origin)
- **April 30, 2025:** Price at 5649 (current pivot at data end)
- The leg hasn't extended to 6166 because price hasn't returned there yet

There are separate legs from origin ~4808 with pivot 6166, formed earlier in the dataset. These represent the same structural level but from slightly different origins.

---

## 3. Sensitivity Analysis: Proximity Pruning

| Config | Range | Time | Active Legs | At 6166 |
|--------|-------|------|-------------|---------|
| Disabled (current) | 0% | 0% | 180 | 124 |
| Tight | 3% | 5% | 54 | 22 |
| **Moderate** | 5% | 10% | 41 | 16 |
| Aggressive | 10% | 15% | 27 | 7 |
| Very Aggressive | 15% | 20% | 22 | 5 |

### Impact on Structure

**Moderate pruning (recommended)** reduces:
- Total active legs: 180 → 41 (77% reduction)
- Legs at 6166.5: 124 → 16 (87% reduction)

Surviving origins at 6166.5 with moderate pruning:
- 3502, 3678, 3809, 3937, 4052, 4122, 4312, 4407
- 4500, 4662, 4808, 4959, 4964, 5080, 5120, 5182...

These represent distinct structural levels (roughly 100-200 point spacing).

---

## 4. Size Distribution Analysis

| Metric | Without Pruning | With Moderate |
|--------|-----------------|---------------|
| Total active | 180 | 41 |
| Range min | 8 | 8 |
| Range max | 2664 | 2664 |
| Mean range | 1516 | 1000 |
| Median range | 1487 | 948 |

**Pruning by size:**
- Small legs (range ≤ 1487): 66% pruned
- Large legs (range > 1487): 89% pruned

Large legs are pruned more because proximity is relative to the **larger** leg's range. A small leg next to a large leg may survive if it's outside the large leg's proximity window.

---

## 5. Accidental Pruning Risk

### Key Structural Levels Preserved

| Origin Level | Without Pruning | With Moderate |
|--------------|-----------------|---------------|
| ~4000 | 6 legs | 1 leg |
| ~4500 | 14 legs | 3 legs |
| ~4800 | 16 legs | 4 legs |
| ~5000 | 10 legs | 6 legs |
| ~5500 | 16 legs | 10 legs |

**The critical 4832 leg survives** moderate pruning.

### Minimum Size Hypothesis

The user hypothesized that proximity pruning might delete a small leg, then another mechanism (invalidation, engulfed) prunes the survivor, leaving a gap.

**Simulation results:**

| Min Range Threshold | Legs Surviving | 4832 Leg |
|---------------------|----------------|----------|
| 0 | 311 | Survives |
| 200 | 307 | Survives |
| 400 | 304 | Survives |
| 600 | 299 | Survives |
| 800 | 293 | Survives |
| 1000 | 290 | **Pruned** |

**Finding:** The 4832 leg (range=817) survives all reasonable thresholds. Setting a minimum size ≤800 would preserve it.

However, the user's concern is valid: **formed legs are more stable** and should be protected. Small unformed legs are ephemeral; pruning them is fine. But a formed leg with significant range represents confirmed structure.

---

## 6. Recommendations

### A. Enable Origin-Proximity Pruning

```python
config = SwingConfig.default().with_origin_prune(
    origin_range_prune_threshold=0.05,  # 5%
    origin_time_prune_threshold=0.10,   # 10%
)
```

**Rationale:** Reduces 180 legs to 41 while preserving key structural levels.

### B. Consider Minimum Size Protection

Add a minimum range threshold to proximity pruning:
- Only apply proximity pruning to legs with `range < min_range_threshold`
- Larger legs (formed, structurally significant) are exempt

Suggested threshold: **500-800 points** for ES 30m data.

**Implementation concept:**
```python
# In LegPruner.apply_origin_proximity_prune()
if leg.range >= config.min_range_for_proximity_prune:
    continue  # Don't prune large legs
```

### C. Alternative: Form-Based Protection

Only apply proximity pruning to **unformed** legs. Once a leg forms (38.2% retracement confirmed), it represents validated structure and should survive.

This aligns with the user's intuition: stability matters. Formed legs are stable.

---

## 7. Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Moderate pruning (recommended)** | 77% noise reduction, key levels preserved | May prune some valid smaller structures |
| No pruning (current) | All structure preserved | 95% noise, unusable for algo |
| Aggressive pruning | Very clean, ~20 legs | Risk of missing important levels |
| Min-size protection | Preserves large structures | Keeps more small-leg noise |

---

## 8. Next Steps

1. **Enable moderate pruning** as the new default
2. **Monitor L1-L7 detection** as more data arrives (May 2025+)
3. **Consider min-size or form-based protection** if important structures are being pruned
4. **Validate with live trading signals** once algo is integrated

---

## Appendix: Analysis Scripts

The analysis was performed using:
- `scripts/leg_analysis.py` - Main analysis script
- `cache/leg_analysis_cache.json` - Cached leg data

To reproduce:
```bash
source venv/bin/activate
python scripts/leg_analysis.py
```
