# Architect Notes

## Current Phase: Ground Truth Annotation Tool

**Status:** Design approved, ready for engineering
**Owner:** Engineering
**Blocker:** None

---

## System State

The lightweight swing validator is production-ready. Product has requested a paradigm shift from thumbs-up/down validation to ground truth annotation.

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | O(N log N), vectorized, production-ready |
| Bar Aggregator | Healthy | Resolution-agnostic, all standard timeframes |
| Progressive Loader | Healthy | <2s startup for 6M+ datasets |
| Scale Calibrator | Healthy | Resolution-aware quartile boundaries |
| Current Validator | Deprecated | Being replaced by annotation tool |

---

## Ground Truth Annotation Tool - Technical Design

### 1. Cascading Scale Implementation

**Aggregation Levels per Scale:**

Given a `--window N` parameter (bars in source resolution):

| Scale | Purpose | Aggregation Calculation |
|-------|---------|-------------------------|
| XL | Full window overview | `target_bars = 50`, aggregation = N / 50 |
| L | Medium-term context | aggregation = N / 200 |
| M | Short-term structure | aggregation = N / 800 |
| S | Fine-grained detail | source resolution (no aggregation) |

**Panel Layout (vertical split):**
- Reference panel: 25% height (shows completed larger-scale annotations)
- Main panel: 75% height (active annotation area)
- Both panels share horizontal time axis (main zooms into subset)

**Dynamic Aggregation:**
Extend `BarAggregator` with a new method:

```python
def aggregate_to_target_bars(self, source_bars: List[Bar], target_count: int) -> List[Bar]:
    """Aggregate source bars to approximately target_count output bars."""
    if len(source_bars) <= target_count:
        return source_bars

    bars_per_candle = len(source_bars) // target_count
    # Group and aggregate using existing _create_aggregated_bar logic
```

This is a straightforward extension of existing aggregation logic.

### 2. Annotation Data Model

**Annotation Record:**
```python
@dataclass
class SwingAnnotation:
    annotation_id: str          # UUID
    scale: str                  # "S", "M", "L", "XL"
    direction: str              # "bull" or "bear"
    start_bar_index: int        # Index in aggregated view
    end_bar_index: int          # Index in aggregated view
    start_source_index: int     # Index in source data
    end_source_index: int       # Index in source data
    start_price: Decimal        # High/low at start
    end_price: Decimal          # High/low at end
    created_at: datetime        # For audit trail
    window_id: str              # Links to data window
```

**Matching for Comparison:**

System swings and user annotations match when:
1. **Direction matches** (bull/bear)
2. **Scale matches** (same scale level)
3. **Position overlaps** within tolerance:
   - Overlap threshold: annotations covering ≥50% same bars = match
   - Alternative: start/end within ±5% of swing duration

```python
def swings_match(user_ann: SwingAnnotation, system_swing: DetectedSwing, tolerance_pct: float = 0.1) -> bool:
    """Check if user annotation matches system-detected swing."""
    if user_ann.direction != system_swing.direction:
        return False

    duration = abs(user_ann.end_source_index - user_ann.start_source_index)
    tolerance_bars = max(5, int(duration * tolerance_pct))

    start_match = abs(user_ann.start_source_index - system_swing.start_index) <= tolerance_bars
    end_match = abs(user_ann.end_source_index - system_swing.end_index) <= tolerance_bars

    return start_match and end_match
```

### 3. Integration Approach

**Recommendation: Build parallel, then swap.**

Rationale:
- Current validator is functional and may be useful for quick checks
- Ground truth tool is a different paradigm, not incremental enhancement
- Git history preserves both approaches
- Clean separation reduces risk

**Reusable Components:**
| Component | Reuse Strategy |
|-----------|----------------|
| `ProgressiveLoader` | Reuse directly - handles large datasets |
| `BarAggregator` | Extend with dynamic aggregation method |
| `ScaleCalibrator` | Reuse for system swing detection |
| `swing_detector.py` | Reuse for comparison baseline |
| FastAPI structure | Copy and modify endpoints |
| Static file serving | Reuse pattern |

**New Components Needed:**
| Component | Purpose |
|-----------|---------|
| `AnnotationStorage` | SQLite-backed annotation persistence |
| `ComparisonAnalyzer` | Match user vs system, generate reports |
| `CascadeController` | Manage XL→L→M→S workflow state |
| New HTML/JS UI | Canvas-based two-click annotation |

### 4. Window Parameter Behavior

**Current State:**
- `--window` sets calibration window size (bars for scale calibration)
- `BarAggregator` pre-computes standard timeframes (1, 5, 15, 30, 60, 240, 1440 minutes)
- Does NOT support arbitrary aggregation levels

**Required Enhancement:**
User expectation: `--window 50000` shows all 50K bars at XL, aggregated to ~50 candles.

**Implementation:**
1. Interpret `--window` as "total bars to work with" for annotation
2. Add `aggregate_to_target_bars()` method to `BarAggregator`
3. XL scale: aggregate to ~50 bars (each candle = 1000 source bars for 50K window)
4. Cascading scales use progressively less aggregation

**No changes needed to existing BarAggregator API** - add new method alongside existing timeframe-based methods.

### 5. Feasibility Assessment

**Low Risk:**
- Dynamic aggregation: straightforward extension
- Two-click annotation: standard UI pattern
- Data storage: simple JSON/SQLite
- Comparison analysis: data transformation

**Medium Risk:**
- Canvas annotation UX at scale (zooming/panning while annotating)
  - Mitigation: fixed aggregation per scale, no zoom during annotation
- Matching tolerance calibration may need iteration
  - Mitigation: start with 10% tolerance, expose as parameter

**No Blockers Identified.**

---

## Architecture Reference

```
                    ┌─────────────────────────────────────┐
                    │         CLI Entry Point             │
                    │   --window --resolution             │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │    Ground Truth Annotation Tool     │
                    │ - FastAPI + Canvas UI               │
                    │ - Cascading scale workflow          │
                    │ - Two-click annotation              │
                    └────────────────┬────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
   ┌──────────▼──────────┐ ┌────────▼────────┐ ┌──────────▼──────────┐
   │  CascadeController  │ │AnnotationStorage│ │ ComparisonAnalyzer  │
   │ - Scale progression │ │ - SQLite/JSON   │ │ - Match logic       │
   │ - Window management │ │ - Export        │ │ - Report generation │
   └──────────┬──────────┘ └────────┬────────┘ └──────────┬──────────┘
              │                      │                      │
              └──────────────────────┼──────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │        Analysis Pipeline            │
                    │ - BarAggregator (extended)         │
                    │ - SwingDetector (for comparison)    │
                    │ - ProgressiveLoader (reused)        │
                    └─────────────────────────────────────┘
```

---

## Next Step

**Engineering to create GitHub issue for Ground Truth Annotation Tool MVP.**

Issue should include:
1. New module: `src/ground_truth_annotator/`
2. Extend `BarAggregator` with `aggregate_to_target_bars()`
3. Implement `CascadeController`, `AnnotationStorage`, `ComparisonAnalyzer`
4. Canvas-based two-click annotation UI
5. Comparison report endpoint

Success criteria from Product:
- [ ] User can mark swings via two-click annotation
- [ ] Cascading scale workflow operational (XL → L → M → S)
- [ ] Annotations stored and comparable against system output
- [ ] Analysis report surfaces false negatives, false positives, ranking gaps

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 12 | Ground truth annotation design review | Approved - ready for engineering |
| Dec 12 | #22, #24 - Full dataset loading, resolution-agnostic | Accepted |
| Dec 12 | #16, #17, #19, #20, #21 | All accepted - P0 performance gate cleared |
