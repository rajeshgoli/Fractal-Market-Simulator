# Reference Layer Exploration

**Status:** Approved
**Created:** January 1, 2026
**Last Updated:** January 1, 2026

---

## Purpose

Reference Layer is the exploration ground for salience formulas — same pattern as DAG layer with pruning algorithms. Wire up multiple approaches, tune empirically, see what works.

**Goal:** Find the salience formula that surfaces levels with highest predictive power (bounce rate, breakout behavior).

**Validation approach:** Visual only for now. Outcome Layer required for quantitative validation.

**Epic:** #422 (Levels at Play Sidebar + Reference Exploration)

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

## Salience Components

### 1. Base Components (Existing)

| Component | Formula | Notes |
|-----------|---------|-------|
| **Range** | `normalize(leg.range)` | Size percentile |
| **Impulse** | `leg.impulsiveness / 100` | From DAG |
| **Recency** | `1 / (1 + age / 1000)` | Decay function |

### 2. Structural Importance (NEW)

**Formula:** `origin_counter_trend_range × leg.range`

Captures "how hard the market fought at this level":
- `leg.range` = size of the move that created the reference
- `origin_counter_trend_range` = size of the counter-move that defended it (already exists on Leg)

**Integration modes:** (user-selectable via dropdown)

| Mode | Formula | Use Case |
|------|---------|----------|
| Multiplier | `SI × base_salience` | Amplify defended levels |
| Additive | `w1×range + w2×impulse + w3×recency + w4×SI` | SI as 4th component |
| Replace Range | `w1×SI + w2×impulse + w3×recency` | SI subsumes range |

**UI:** Dropdown for mode + slider for weight/strength

### 3. Depth Score (NEW)

**Formula:** `1 / (1 + depth)` (linear inverse)

| Depth | Score |
|-------|-------|
| 0 (root) | 1.0 |
| 1 | 0.5 |
| 2 | 0.33 |
| 3 | 0.25 |

Root legs (major structure) score higher than nested children.

### 4. Time-at-Level (NEW)

**Definition:** Count of bars where price stayed within X% of pivot before moving away.

**Configurable:** Tolerance percentage (default TBD, exposed as slider)

**Implementation:** Track during leg formation in Reference Layer.

### 5. Touch Count (NEW)

**Definition:** Number of times price crossed any of the 9 fib levels for this reference.

**Levels tracked:** 0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0

**Implementation:** Increment counter on each level cross event.

### 6. Confluence Bonus (NEW)

**Definition:** Additive score boost when reference's levels participate in confluence zones.

**Formula:** Weighted component added to salience sum.

**Integration:** Uses existing `get_confluence_zones()` from P3.

---

## Reference Config UI

### Placement

Levels at Play view, parallel to Detection Config in Structural Legs view.

### Layout: Progressive Disclosure

```
┌─────────────────────────────────────────────┐
│ REFERENCE CONFIG                    [Apply] │
├─────────────────────────────────────────────┤
│ Base Weights (L/XL)                         │
│   Range     [====○=====] 0.5                │
│   Impulse   [===○======] 0.4                │
│   Recency   [○=========] 0.1                │
│                                             │
│ Base Weights (S/M)                          │
│   Range     [=○========] 0.2                │
│   Impulse   [==○=======] 0.3                │
│   Recency   [====○=====] 0.5                │
│                                             │
│ ▶ Advanced                                  │
└─────────────────────────────────────────────┘

Expanded:
┌─────────────────────────────────────────────┐
│ ▼ Advanced                                  │
├─────────────────────────────────────────────┤
│ Structural Importance                       │
│   Mode      [Additive ▼]                    │
│   Weight    [===○======] 0.3                │
│                                             │
│ Depth                                       │
│   Weight    [=○========] 0.2                │
│                                             │
│ Time-at-Level                               │
│   Tolerance [===○======] 1.0%               │
│   Weight    [=○========] 0.2                │
│                                             │
│ Touch Count                                 │
│   Weight    [○=========] 0.1                │
│                                             │
│ Confluence Bonus                            │
│   Weight    [=○========] 0.2                │
│                                             │
│ Formation                                   │
│   Threshold [===○======] 0.382              │
└─────────────────────────────────────────────┘
```

### Interaction

- **Apply button:** Changes batch until user clicks Apply
- **No presets:** Just manual sliders for exploration phase
- **Persist:** Save to localStorage like Detection Config

### Parameters

| Parameter | Type | Range | Default | Section |
|-----------|------|-------|---------|---------|
| big_range_weight | slider | 0-1 | 0.5 | Base (L/XL) |
| big_impulse_weight | slider | 0-1 | 0.4 | Base (L/XL) |
| big_recency_weight | slider | 0-1 | 0.1 | Base (L/XL) |
| small_range_weight | slider | 0-1 | 0.2 | Base (S/M) |
| small_impulse_weight | slider | 0-1 | 0.3 | Base (S/M) |
| small_recency_weight | slider | 0-1 | 0.5 | Base (S/M) |
| si_mode | dropdown | multiplier/additive/replace | additive | Advanced |
| si_weight | slider | 0-1 | 0.0 | Advanced |
| depth_weight | slider | 0-1 | 0.0 | Advanced |
| time_at_level_tolerance | slider | 0.1-5.0% | 1.0 | Advanced |
| time_at_level_weight | slider | 0-1 | 0.0 | Advanced |
| touch_count_weight | slider | 0-1 | 0.0 | Advanced |
| confluence_weight | slider | 0-1 | 0.0 | Advanced |
| formation_threshold | slider | 0.2-0.5 | 0.382 | Advanced |

---

## Implementation Plan

### Phase 1: Config UI + Base Weights

1. Create ReferenceConfigPanel component (mirrors DetectionConfigPanel)
2. Expose existing 6 base weights
3. Wire Apply button to API
4. Persist to localStorage

### Phase 2: Structural Importance

1. Add `si_mode` and `si_weight` to ReferenceConfig
2. Implement 3 integration modes in `_compute_salience()`
3. Add UI controls (dropdown + slider)

### Phase 3: Additional Components

1. Add depth_weight with linear inverse formula
2. Track time-at-level during formation
3. Track touch count on level cross events
4. Add confluence bonus using existing zone detection

### Phase 4: Iteration

1. Visual validation with different weight combinations
2. A/B comparison on same data window
3. Prepare for Outcome Layer integration

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Counter-leg definition | `origin_counter_trend_range` exists on Leg |
| Weight normalization | Existing weights stay as-is; SI mode-dependent |
| SI integration | Configurable via dropdown: multiplier/additive/replace |
| UI placement | Levels at Play view, parallel to Detection Config |
| Validation approach | Visual only until Outcome Layer exists |
| Depth formula | Linear inverse: `1/(1+depth)` |
| Time-at-level metric | Bars within configurable % of pivot |
| Touch definition | Any fib level crossed |
| Confluence bonus | Additive component |
| UI feedback | Apply button (batch changes) |
| Presets | None for exploration phase |

---

## Interview Notes (January 1, 2026)

Polymath interview with user to clarify spec. Key findings:

1. `origin_counter_trend_range` already exists on Leg — no new data needed for SI
2. User wants ALL salience candidates wired up for maximum exploration surface
3. SI should be configurable across all three modes (multiplier/additive/replace)
4. Progressive disclosure UI: basic weights visible, advanced expands
5. Apply button preferred over instant feedback
6. No presets needed yet — pure exploration mode
7. This work should follow #419 completion

---

## Interaction Model: Cross-Window Calibration

**Goal:** Find salience weights that surface "known-good" levels across multiple historical windows.

```
┌─────────────────────────────────────────────────────────┐
│              CROSS-WINDOW CALIBRATION                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Window 1 (e.g., 2024 ES rally)                         │
│  ├─ Load data                                           │
│  ├─ "I know the 6150 and 5800 levels mattered here"     │
│  ├─ Tune weights until those rank high                  │
│  └─ Note weight settings                                │
│                                                          │
│  Window 2 (e.g., 2023 consolidation)                    │
│  ├─ Load data                                           │
│  ├─ "Different regime — 4500-4600 range was key"        │
│  ├─ Check: do those levels rank high with same weights? │
│  └─ Adjust if needed                                    │
│                                                          │
│  Window 3 (e.g., 2022 selloff)                          │
│  └─ Repeat...                                           │
│                                                          │
│  ✓ Weights generalize → trust on new data               │
│  ✗ Weights don't generalize → regime-specific formulas? │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Validation signal:** User's domain expertise. They know which levels "should" be important from prior TradingView analysis or trading memory.

**Learning outcome:** If weights don't generalize across regimes, that's valuable information — may need regime-specific formulas, which informs Outcome Layer design.

---

## Success Criteria

- [ ] Reference Config panel in Levels at Play view
- [ ] All 6 base weights adjustable
- [ ] SI mode dropdown + weight slider working
- [ ] Depth/time-at-level/touch-count/confluence components wired
- [ ] Apply button batches changes
- [ ] Settings persist to localStorage
- [ ] Visual inspection shows different rankings with different weights
