# Reference Observation Spec

**Status:** Draft
**Author:** Product
**Date:** December 31, 2025

---

## Goal

Add observability to the Levels at Play view for understanding Reference Layer filtering behavior. Before building P2 (Fib Level Display), we need visibility into which legs are filtered and why.

---

## Background

The Reference Layer filters DAG legs through several conditions before they become valid trading references:

| Filter Condition | Description |
|------------------|-------------|
| **Cold Start** | System warming up (< 50 formed legs) |
| **Not Formed** | Price hasn't reached 38.2% formation threshold |
| **Pivot Breached** | Location < 0 (price past defended pivot) |
| **Completed** | Location > 2 (past 2× extension target) |
| **Origin Breached** | Scale-dependent tolerance exceeded (S/M: 0%, L/XL: 15% trade or 10% close) |

Currently, the Levels at Play view only shows valid references. There's no visibility into:
- How many legs were considered but filtered
- Why each leg was filtered
- The pass rate and filter distribution

---

## Design

### Interaction Model

Follow the existing Levels at Play UX pattern:
- **Toggle** in left nav: "Show Filtered" checkbox (default off), persisted to localStorage
- **Leg list**: When toggle on, filtered legs appear alongside valid refs
- **Styling**: Filtered legs highlighted (full opacity), valid refs muted (fade to background)
- **Filter badges**: Each filtered leg shows reason badge (e.g., "NOT FORMED", "PIVOT BREACHED")
- **Stats section**: Collapsible panel in left sidebar lower area
- **Explanation panel**: Clicking filtered leg shows filter reason with details

### Visual Hierarchy (Toggle On)

```
┌─────────────────────────────────────────────┐
│  BULL REFERENCES                            │
│  ├─ L1 (L) loc:0.42 sal:0.78               │  ← Valid (muted)
│  ├─ L3 (M) loc:0.65 sal:0.54               │  ← Valid (muted)
│  ├─ L5 (S) [NOT FORMED]                    │  ← Filtered (highlighted + badge)
│  └─ L7 (M) [ORIGIN BREACHED]               │  ← Filtered (highlighted + badge)
│                                             │
│  BEAR REFERENCES                            │
│  ├─ L2 (XL) loc:0.31 sal:0.82              │  ← Valid (muted)
│  └─ L4 (L) [PIVOT BREACHED]                │  ← Filtered (highlighted + badge)
└─────────────────────────────────────────────┘
```

### Stats Panel (Left Sidebar Lower)

```
┌─────────────────────────────────────────────┐
│  FILTER STATS                          [−]  │
│  ────────────────────────────────────────── │
│  Total legs:        24                      │
│  Valid refs:        15  (62.5%)             │
│  ────────────────────────────────────────── │
│  Not formed:         5                      │
│  Pivot breached:     2                      │
│  Origin breached:    1                      │
│  Completed:          1                      │
│  Cold start:         0                      │
└─────────────────────────────────────────────┘
```

### Explanation Panel (Filtered Leg Selected)

When a filtered leg is clicked, the explanation panel shows:
- Filter reason with human-readable description
- Current location value
- Threshold that was violated (if applicable)
- Scale classification (affects origin breach tolerance)

---

## Backend Changes

### New Types

```python
class FilterReason(Enum):
    VALID = "valid"
    COLD_START = "cold_start"
    NOT_FORMED = "not_formed"
    PIVOT_BREACHED = "pivot_breached"
    COMPLETED = "completed"
    ORIGIN_BREACHED = "origin_breached"

@dataclass
class FilteredLeg:
    leg: Leg
    reason: FilterReason
    scale: str              # S/M/L/XL
    location: float         # Current location in reference frame
    threshold: Optional[float]  # Violated threshold (for breach reasons)
```

### New ReferenceLayer Method

```python
def get_all_with_status(self, legs: List[Leg], bar: Bar) -> List[FilteredLeg]:
    """
    Returns all legs with their filter status.

    Unlike update() which returns only valid references, this method
    returns every active leg with its filter reason for observability.
    """
```

### Extended API Response

Extend `/api/reference-state` to include:

```json
{
  "references": [...],
  "filtered_legs": [
    {
      "leg_id": "bear_6166.50_1234",
      "direction": "bear",
      "origin_price": 6166.50,
      "pivot_price": 4832.00,
      "scale": "L",
      "filter_reason": "not_formed",
      "location": 0.28,
      "threshold": 0.382
    }
  ],
  "filter_stats": {
    "total_legs": 24,
    "valid_count": 15,
    "pass_rate": 0.625,
    "by_reason": {
      "not_formed": 5,
      "pivot_breached": 2,
      "origin_breached": 1,
      "completed": 1,
      "cold_start": 0
    }
  }
}
```

---

## Frontend Changes

### Left Nav Toggle

Add "Show Filtered" checkbox to Levels at Play left nav, similar to existing toggles:
- Persisted to localStorage via `useChartPreferences` or `useSessionSettings`
- Default: off (clean view for normal use)

### ReferenceTelemetryPanel Extension

Add collapsible "Filter Stats" section to existing telemetry panel:
- Shows counts by filter reason
- Shows pass rate percentage
- Collapsed by default, expands on click

### Leg List Updates

When "Show Filtered" toggle is on:
- Filtered legs appear in bull/bear sections
- Filtered legs highlighted (full opacity) with filter reason badge
- Valid refs muted (0.4 opacity) — fade to background
- Clicking filtered leg populates explanation panel with filter details

### ReferenceLegOverlay Updates

When "Show Filtered" toggle is on:
- Filtered legs render on chart at full opacity (highlighted)
- Valid refs render muted (fade to background)

---

## Issue Decomposition

Consolidate into 2-3 issues for efficient implementation:

### Issue 1: Backend — Filter Status API

- Create `FilterReason` enum in `reference_layer.py`
- Create `FilteredLeg` dataclass
- Implement `get_all_with_status()` method
- Extend `/api/reference-state` with `filtered_legs` and `filter_stats`
- Add tests for filter classification

### Issue 2: Frontend — Observation UI

- Add "Show Filtered" toggle to left nav
- Extend `ReferenceTelemetryPanel` with filter stats section
- Update leg list to show filtered legs with badges
- Update overlay to render filtered legs when toggle on
- Wire explanation panel for filter reasons
- Persist toggle state to localStorage

### Issue 3 (Optional): Documentation

- Update `developer_guide.md` with new API fields
- Update `user_guide.md` with observation mode usage

---

## Success Criteria

1. Toggle reveals all filtered legs with clear reason badges
2. Stats show accurate breakdown by filter reason
3. Clicking filtered leg explains why it was filtered
4. Toggle state persists across sessions
5. No performance regression (filter computation is O(n) on active legs)

---

## Open Questions

None — design is straightforward extension of existing patterns.
