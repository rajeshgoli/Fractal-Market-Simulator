# Reference Layer Exploration

**Status:** Draft
**Created:** January 1, 2026

---

## Purpose

Reference Layer is the exploration ground for salience formulas — same pattern as DAG layer with pruning algorithms. Wire up multiple approaches, tune empirically, see what works.

**Goal:** Find the salience formula that surfaces levels with highest predictive power (bounce rate, breakout behavior).

---

## Current State

### Existing Salience Formula

Located in `reference_layer.py:_compute_salience()`:

```python
# Components
range_score = normalize(leg.range)           # Size vs distribution
impulse_score = leg.impulsiveness / 100      # From DAG
recency_score = 1 / (1 + age / 1000)         # Decay

# Scale-dependent weights
L/XL: range=0.5, impulse=0.4, recency=0.1
S/M:  range=0.2, impulse=0.3, recency=0.5
```

### What's Missing

No UI for ReferenceConfig. All parameters are hardcoded or config-only (no runtime adjustment).

---

## Exploration Areas

### 1. Salience Weight Tuning

Expose existing weights in UI:
- `big_range_weight`, `big_impulse_weight`, `big_recency_weight`
- `small_range_weight`, `small_impulse_weight`, `small_recency_weight`

### 2. Formation Thresholds

- Formation threshold (currently 38.2%)
- Breach tolerances per scale

### 3. Structural Importance (NEW)

**Proposed formula:** `counter_leg_range × leg_range`

Captures "how hard the market fought at this level":
- `leg_range` = size of the move that created the reference
- `counter_leg_range` = size of the counter-move that defended it

**Implementation options:**
- Add as new salience component (alongside range/impulse/recency)
- Replace range_score with structural_importance
- Use as multiplicative factor

### 4. Other Candidates (TBD)

- Depth-weighted salience
- Time-at-level (how long price consolidated near pivot)
- Touch count (how many times level was tested)
- Confluence bonus (levels in zones get boosted)

---

## Enabler: Reference Layer Tuning UI

### Requirements

1. Expose ReferenceConfig in frontend (like DetectionConfig panel)
2. Real-time updates (slider changes → immediate re-render)
3. Persist settings in localStorage
4. Reset to defaults button

### Parameters to Expose

| Parameter | Type | Range | Default |
|-----------|------|-------|---------|
| big_range_weight | slider | 0-1 | 0.5 |
| big_impulse_weight | slider | 0-1 | 0.4 |
| big_recency_weight | slider | 0-1 | 0.1 |
| small_range_weight | slider | 0-1 | 0.2 |
| small_impulse_weight | slider | 0-1 | 0.3 |
| small_recency_weight | slider | 0-1 | 0.5 |
| formation_threshold | slider | 0.2-0.5 | 0.382 |
| structural_importance_weight | slider | 0-1 | 0 (new) |

---

## Validation Approach

1. **Visual inspection** — Do the "right" levels appear with different weight combinations?
2. **Outcome correlation** — Track bounce/breakout rates per salience tier (requires Outcome Layer)
3. **A/B comparison** — Compare formula variants on same data window

---

## Open Questions

1. Should weights auto-normalize (sum to 1) or allow arbitrary scaling?
2. How to compute `counter_leg_range` — is this available on Leg today?
3. Should structural importance be scale-dependent like other weights?

---

## Next Steps

1. Add Reference Layer config panel to frontend
2. Wire existing salience weights
3. Add `counter_leg_range` to Leg if not present
4. Implement structural importance formula
5. Iterate based on empirical observation
