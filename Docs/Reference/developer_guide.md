# Developer Guide

Technical reference for engineers working on the Market Simulator codebase.

---

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
python -m pytest tests/ -v

# Start annotator
python -m src.ground_truth_annotator.main --data test_data/test.csv --scale S
```

---

## Directory Structure

```
src/
├── data/
│   └── ohlc_loader.py              # CSV loading (TradingView + semicolon formats)
├── swing_analysis/
│   ├── types.py                    # Bar, BullReferenceSwing, BearReferenceSwing
│   ├── swing_detector.py           # Main detection: detect_swings()
│   ├── level_calculator.py         # Fibonacci level computation
│   ├── reference_frame.py          # Oriented coordinate system for ratios
│   ├── bar_aggregator.py           # Multi-timeframe OHLC aggregation
│   ├── scale_calibrator.py         # Auto-calibrate S/M/L/XL boundaries
│   ├── constants.py                # Fibonacci level sets
│   ├── swing_state_manager.py      # Live swing tracking (legacy)
│   └── event_detector.py           # Live event detection (legacy)
├── discretization/
│   ├── schema.py                   # DiscretizationEvent, SwingEntry, etc.
│   ├── discretizer.py              # Batch OHLC → event log processor
│   └── io.py                       # JSON read/write for logs
└── ground_truth_annotator/
    ├── main.py                     # CLI entry point
    ├── api.py                      # FastAPI REST endpoints
    ├── models.py                   # SwingAnnotation, AnnotationSession, ReviewSession
    ├── storage.py                  # JSON persistence
    ├── comparison_analyzer.py      # FN/FP detection vs annotations
    ├── cascade_controller.py       # XL→L→M→S workflow
    └── review_controller.py        # Match/FP/FN review phases

frontend/                           # React + Vite Replay View
├── src/
│   ├── pages/Replay.tsx            # Main replay page
│   ├── components/
│   │   ├── ChartArea.tsx           # Dual lightweight-charts
│   │   ├── SwingOverlay.tsx        # Fib level rendering
│   │   ├── PlaybackControls.tsx    # Transport controls
│   │   └── ExplanationPanel.tsx    # Swing detail display
│   └── hooks/
│       ├── usePlayback.ts          # Legacy playback (calibration scrubbing)
│       └── useForwardPlayback.ts   # Forward-only playback (after calibration)
└── package.json

tests/                              # 780 tests
scripts/                            # Dev utilities
```

---

## Architecture

### Module Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│                                                                              │
│   src/data/ohlc_loader.py                                                   │
│   ├── load_ohlc() ──────────────────► DataFrame + gaps                      │
│   ├── load_ohlc_window() ───────────► DataFrame + gaps (windowed)           │
│   └── get_file_metrics() ───────────► FileMetrics (fast inspection)         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SWING ANALYSIS                                     │
│                                                                              │
│   swing_detector.py ◄─────────────────────────────────────────────────────┐ │
│   └── detect_swings() ──► {swing_highs, swing_lows, bull_refs, bear_refs} │ │
│            │                                                               │ │
│            │ uses                                                          │ │
│            ▼                                                               │ │
│   level_calculator.py ──► Fibonacci levels                                 │ │
│   reference_frame.py ───► Price ↔ ratio conversion                         │ │
│   bar_aggregator.py ────► Multi-timeframe OHLC                             │ │
│   constants.py ─────────► DISCRETIZATION_LEVELS (16 Fib ratios)            │ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DISCRETIZATION                                     │
│                                                                              │
│   discretizer.py                                                            │
│   └── Discretizer.discretize(ohlc, swings) ──► DiscretizationLog            │
│            │                                                                 │
│            │ produces                                                        │
│            ▼                                                                 │
│   schema.py ────► DiscretizationEvent, SwingEntry, side-channels            │
│   io.py ────────► read_log(), write_log()                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GROUND TRUTH ANNOTATOR                                 │
│                                                                              │
│   api.py ◄───────────────────────────────────────────────────────────────┐  │
│   └── FastAPI endpoints                                                  │  │
│            │                                                             │  │
│            │ uses                                                        │  │
│            ▼                                                             │  │
│   models.py ────────────► SwingAnnotation, AnnotationSession, ReviewSession │
│   storage.py ───────────► JSON persistence (ground_truth.json)           │  │
│   comparison_analyzer.py ► FN/FP detection                               │  │
│   cascade_controller.py ─► XL→L→M→S workflow                             │  │
│   review_controller.py ──► Match/FP/FN review phases                     │  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                                     │
│                                                                              │
│   frontend/src/                                                             │
│   └── Replay.tsx ◄── ChartArea, SwingOverlay, PlaybackControls             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

**Batch analysis (typical):**

```
1. Load OHLC
   load_ohlc("data.csv") → DataFrame

2. Detect swings (sequential by scale)
   detect_swings(df, quota=4) → XL swings
   detect_swings(df, quota=6, larger_swings=XL) → L swings
   detect_swings(df, quota=10, larger_swings=L) → M swings
   detect_swings(df, quota=15, larger_swings=M) → S swings

3. Discretize
   Discretizer().discretize(df, {"XL": xl, "L": l, "M": m, "S": s}) → DiscretizationLog

4. Analyze
   log.events → filter, aggregate, visualize
```

**Ground truth annotation:**

```
1. CLI starts server
   main.py --data file.csv --scale S

2. Server loads data
   load_ohlc() → source_bars
   BarAggregator(source_bars) → aggregated_bars for UI

3. User annotates
   POST /api/annotations → SwingAnnotation stored in session

4. Comparison
   POST /api/compare → detect_swings() vs annotations → FN/FP lists

5. Review
   /api/review/* → phased feedback collection

6. Finalize
   POST /api/session/finalize → append to ground_truth.json
```

### Filter Pipeline (detect_swings)

The detection pipeline applies filters in order. Understanding this is essential for adding new filters.

```
┌───────────────────────────────────────────────────────────────────┐
│ 1. SWING POINT DETECTION                                          │
│    _detect_swing_points_vectorized()                              │
│    → swing_highs[], swing_lows[] (local maxima/minima)            │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 2. PAIRING & STRUCTURAL VALIDATION                                │
│    Match swing highs with swing lows:                             │
│    • Bull: High BEFORE Low (downswing)                            │
│    • Bear: Low BEFORE High (upswing)                              │
│    → bull_references[], bear_references[]                         │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 3. BEST EXTREMA ADJUSTMENT (adjust_extrema=True)                  │
│    _adjust_to_best_extrema() — snap to best H/L within ±lookback  │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 4. PROTECTION VALIDATION (protection_tolerance)                   │
│    _apply_protection_filter() — reject violated swing points      │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 5. SIZE FILTER (min_candle_ratio, min_range_pct)                  │
│    _apply_size_filter() — reject swings too small for context     │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 6. PROMINENCE FILTER (min_prominence)                             │
│    _apply_prominence_filter() — reject swings that don't stand out│
│    ← INSERT NEW FILTERS HERE                                      │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 7. STRUCTURAL SEPARATION (larger_swings)                          │
│    _apply_structural_separation_filter() — require 0.236 FIB gap  │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 8. REDUNDANCY FILTER (filter_redundant=True)                      │
│    filter_swings() — remove swings in same Fib bands              │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 9. QUOTA FILTER (quota)                                           │
│    _apply_quota() — rank by size+impulse, keep top N              │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 10. RANKING                                                       │
│     Sort by combined_score (if quota) or size, assign rank        │
└───────────────────────────────────────────────────────────────────┘
```

---

## Core Modules

### Data Loading

**File:** `src/data/ohlc_loader.py`

```python
from src.data.ohlc_loader import load_ohlc, load_ohlc_window, get_file_metrics

# Load entire file
df, gaps = load_ohlc("data.csv")
# Returns: DataFrame[timestamp, open, high, low, close, volume], List[gaps]

# Load window (for large files)
df, gaps = load_ohlc_window("data.csv", start_row=10000, num_rows=5000)

# Quick file inspection
metrics = get_file_metrics("data.csv")
# Returns: FileMetrics(total_bars, file_size_bytes, format, first_timestamp, last_timestamp)
```

**Supported formats:**
- TradingView: `time,open,high,low,close,volume` (comma-separated, Unix timestamp)
- Historical: `DD/MM/YYYY;HH:MM:SS;open;high;low;close;volume` (semicolon-separated)

---

### Swing Detection

**File:** `src/swing_analysis/swing_detector.py`

The primary detection interface. Returns swing points and reference swings.

```python
from src.swing_analysis.swing_detector import detect_swings
import pandas as pd

df = pd.DataFrame({...})  # columns: open, high, low, close

result = detect_swings(
    df,
    lookback=5,                     # Bars before/after for swing point detection
    filter_redundant=True,          # Apply Fib-band redundancy filter
    protection_tolerance=0.1,       # 10% violation tolerance
    min_candle_ratio=None,          # Size filter: multiple of median candle
    min_range_pct=None,             # Size filter: % of window range
    min_prominence=None,            # Prominence filter: multiple of median candle
    adjust_extrema=True,            # Snap endpoints to best extrema
    quota=None,                     # Max swings per direction
    larger_swings=None,             # Context from larger scale (for separation gate)
    current_bar_index=None,         # Price reference bar (None = last bar)
)

# Returns:
# {
#     "current_price": float,
#     "swing_highs": [{"price": float, "bar_index": int}, ...],
#     "swing_lows": [{"price": float, "bar_index": int}, ...],
#     "bull_references": [dict, ...],  # High BEFORE Low (downswing)
#     "bear_references": [dict, ...],  # Low BEFORE High (upswing)
# }
```

**Reference swing dict fields:**
- `high_price`, `low_price`, `high_bar_index`, `low_bar_index`
- `size` (high - low)
- `level_0382`, `level_2x` (Fib levels)
- `rank` (by size or combined score)
- `impulse`, `size_rank`, `impulse_rank`, `combined_score` (if quota set)
- `structurally_separated`, `containing_swing_id` (if larger_swings provided)

**Multi-scale detection pattern:**

```python
# Detect XL first, pass results to L, and so on
xl_result = detect_swings(df, lookback=10, quota=4)
xl_swings = xl_result["bull_references"] + xl_result["bear_references"]

l_result = detect_swings(df, lookback=8, quota=6, larger_swings=xl_swings)
# L swings now have structural separation context from XL
```

---

### Reference Frame

**File:** `src/swing_analysis/reference_frame.py`

Converts absolute prices to swing-relative ratios. Handles bull/bear orientation.

```python
from src.swing_analysis.reference_frame import ReferenceFrame
from decimal import Decimal

# Bull swing: defended pivot is low, origin is high
frame = ReferenceFrame(
    anchor0=Decimal("5000"),   # Defended pivot (stop level)
    anchor1=Decimal("5100"),   # Origin extremum
    direction="BULL"
)

# Price → ratio
ratio = frame.ratio(Decimal("5050"))  # Returns 0.5

# Ratio → price
price = frame.price(Decimal("0.618"))  # Returns 5061.8

# Properties
frame.range  # Signed: positive for bull, negative for bear
```

**Ratio interpretation:**
| Ratio | Meaning |
|-------|---------|
| 0 | Defended pivot (stop level) |
| 0.382-0.618 | Retracement zone |
| 1 | Origin extremum |
| 2 | Completion target |
| < 0 | Invalidation territory |

---

### Discretization

**File:** `src/discretization/discretizer.py`

Batch processor: OHLC + detected swings → structural event log.

```python
from src.discretization import Discretizer, DiscretizerConfig

config = DiscretizerConfig(
    level_set=[0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0, 2.618, 3.0, 4.0],
    crossing_semantics="close_cross",
    invalidation_thresholds={"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15},
)

discretizer = Discretizer(config)

log = discretizer.discretize(
    ohlc=df,                              # DataFrame with timestamp, open, high, low, close
    swings={"XL": xl_swings, "L": l_swings, ...},  # Dict[scale, List[ReferenceSwing]]
    instrument="ES",
    source_resolution="1m",
)

# log.events: List[DiscretizationEvent]
# log.swings: List[SwingEntry]
# log.meta: DiscretizationMeta (config, date range, etc.)
```

**Event types:**
| Event | Meaning |
|-------|---------|
| `SWING_FORMED` | New swing registered |
| `LEVEL_CROSS` | Price crossed Fib level |
| `COMPLETION` | Ratio crossed 2.0 |
| `INVALIDATION` | Ratio crossed below threshold |
| `SWING_TERMINATED` | Swing ended (completed/invalidated) |

**Side-channels on events:**
- `effort`: `EffortAnnotation(dwell_bars, test_count, max_probe_r)`
- `shock`: `ShockAnnotation(levels_jumped, range_multiple, gap_multiple, is_gap)`
- `parent_context`: `ParentContext(scale, swing_id, band, direction, ratio)`

---

### Bar Aggregation

**File:** `src/swing_analysis/bar_aggregator.py`

```python
from src.swing_analysis.bar_aggregator import BarAggregator
from src.swing_analysis.types import Bar

source_bars: List[Bar] = [...]
aggregator = BarAggregator(source_bars)

# Aggregate to specific timeframe (minutes)
bars_5m = aggregator.get_bars(timeframe=5)

# Aggregate to target bar count
bars_200 = aggregator.aggregate_to_target_bars(200)

# Source-to-aggregated mapping
agg_bar = aggregator.get_bar_at_source_time(timeframe=5, source_bar_idx=100)
```

---

## Ground Truth Annotator

### CLI

```bash
python -m src.ground_truth_annotator.main \
    --data test_data/test.csv \
    --scale S \
    --resolution 1m \
    --window 50000 \
    --target-bars 200 \
    --offset 0           # or 'random'
    --start-date 2020-Jan-01  # overrides --offset
    --port 8000
```

### REST API

**Core endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Annotation UI |
| `/replay` | GET | Replay View UI |
| `/api/bars` | GET | Aggregated bars for chart |
| `/api/annotations` | GET/POST/DELETE | CRUD annotations |
| `/api/session` | GET | Session state |
| `/api/cascade/state` | GET | Cascade workflow state |
| `/api/cascade/advance` | POST | Advance to next scale |
| `/api/compare` | POST | Run comparison |
| `/api/review/*` | * | Review mode endpoints |
| `/api/discretization/*` | * | Discretization endpoints |

**Discretization API:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/discretization/state` | GET | Check if discretization exists |
| `/api/discretization/run` | POST | Run discretization on window |
| `/api/discretization/events` | GET | Get events (with filters) |
| `/api/discretization/swings` | GET | Get swing entries |

**Event filters (query params):**
- `scale`: XL, L, M, S
- `event_type`: LEVEL_CROSS, COMPLETION, etc.
- `shock_threshold`: minimum range_multiple
- `levels_jumped_min`: minimum levels jumped
- `is_gap`: true/false
- `bar_start`, `bar_end`: bar range

**Replay Calibration API:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/replay/calibrate` | GET | Run calibration on first N bars |
| `/api/replay/advance` | POST | Advance playback beyond calibration window |

**GET /api/replay/calibrate:**

Query params:
- `bar_count`: Number of bars for calibration window (default: 10000)

Returns:
- `calibration_bar_count`: Actual bars used
- `current_price`: Price at end of calibration window
- `swings_by_scale`: Dict of scale → list of swings
- `active_swings_by_scale`: Dict of scale → list of active swings
- `scale_thresholds`: Dict of scale → size threshold
- `stats_by_scale`: Dict of scale → {total_swings, active_swings}

**POST /api/replay/advance:**

Request body:
```json
{
  "calibration_bar_count": 10000,
  "current_bar_index": 9999,
  "advance_by": 1
}
```

Returns:
- `new_bars`: List of new OHLC bars to append
- `events`: List of events that occurred (SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED, LEVEL_CROSS)
- `swing_state`: Current swing state by scale (XL, L, M, S)
- `current_bar_index`: New position after advance
- `current_price`: Price at new position
- `end_of_data`: Boolean indicating if end of data reached

Event diffing logic compares previous vs new swing state to detect:
- New swings appearing (SWING_FORMED)
- Swings disappearing due to pivot violation (SWING_INVALIDATED)
- Swings reaching 2.0 extension (SWING_COMPLETED)
- Price crossing significant Fib levels (LEVEL_CROSS)

---

## Data Models

### SwingAnnotation

```python
@dataclass
class SwingAnnotation:
    annotation_id: str          # UUID
    scale: str                  # S, M, L, XL
    direction: str              # "bull" or "bear"
    start_bar_index: int        # Aggregated view index
    end_bar_index: int
    start_source_index: int     # Source data index
    end_source_index: int
    start_price: Decimal
    end_price: Decimal
    created_at: datetime
    window_id: str
```

### AnnotationSession

```python
@dataclass
class AnnotationSession:
    session_id: str
    data_file: str
    resolution: str             # "1m", "5m", etc.
    window_size: int
    window_offset: int
    created_at: datetime
    annotations: List[SwingAnnotation]
    completed_scales: List[str]
    skipped_scales: List[str]
    status: str                 # "in_progress" | "keep" | "discard"
    version: int                # Schema version (4)
```

### ReviewSession

```python
@dataclass
class ReviewSession:
    review_id: str
    session_id: str
    phase: str                  # "matches" | "fp_sample" | "fn_feedback" | "complete"
    match_feedback: List[SwingFeedback]
    fp_feedback: List[SwingFeedback]
    fn_feedback: List[SwingFeedback]
    fp_sample_indices: List[int]
    started_at: datetime
    completed_at: Optional[datetime]
    difficulty: Optional[int]   # 1-5
    regime: Optional[str]       # "bull" | "bear" | "chop"
```

---

## Storage

**Directory structure:**

```
ground_truth/
├── ground_truth.json              # All finalized sessions (version-controlled)
└── sessions/                      # In-progress only (gitignored)
    └── inprogress-{timestamp}.json
```

**Session lifecycle:**
1. Start → create `sessions/inprogress-{timestamp}.json`
2. Work → update working file
3. Finalize "keep" → append to `ground_truth.json`, delete working files
4. Finalize "discard" → delete working files

**Single-user assumption:** No file locking. Concurrent use would cause data loss.

---

## Frontend (Replay View)

```bash
# Development (hot reload, proxies API to :8000)
cd frontend && npm run dev  # Starts on :3000

# Production build
cd frontend && npm run build  # Output: frontend/dist/
```

**Key components:**

| Component | Purpose |
|-----------|---------|
| `Replay.tsx` | Main page, state coordination |
| `ChartArea.tsx` | Two stacked lightweight-charts |
| `SwingOverlay.tsx` | Fib level rendering on charts |
| `PlaybackControls.tsx` | Play/pause/step transport |
| `ExplanationPanel.tsx` | Calibration report and swing details |
| `usePlayback.ts` | Legacy playback (calibration scrubbing) |
| `useForwardPlayback.ts` | Forward-only playback after calibration |
| `useSwingDisplay.ts` | Scale filtering and swing ranking |

**Stack:** React 19, lightweight-charts v5, Tailwind CSS 4, Vite 7

---

## Extending the System

### Adding a New Filter to detect_swings()

1. Create helper function:
   ```python
   def _apply_new_filter(references: List[Dict], param: float) -> List[Dict]:
       if param is None:
           return references
       return [r for r in references if <condition>]
   ```

2. Add parameter to `detect_swings()` signature with `None` default

3. Insert call in pipeline (after size filter, before redundancy filter):
   ```python
   if new_param is not None:
       bull_references = _apply_new_filter(bull_references, new_param)
       bear_references = _apply_new_filter(bear_references, new_param)
   ```

4. Add tests following `TestProminenceFilter` pattern

### Adding a New Event Type

1. Add to `EventType` enum in `src/discretization/schema.py`
2. Implement detection logic in `Discretizer.discretize()` loop
3. Update validation in `validate_log()`

### Adding a New Data Format

1. Add format detection in `detect_format()`
2. Add parsing branch in `load_ohlc()` and `load_ohlc_window()`
3. Ensure output is standard DataFrame with `timestamp, open, high, low, close, volume`

---

## Testing

```bash
# All tests
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_swing_detector.py -v

# Single test
python -m pytest tests/test_swing_detector.py::TestQuotaFilter -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
```

**Test organization:**

| File | Tests |
|------|-------|
| `test_swing_detector.py` | Detection, filters, ranking |
| `test_discretizer.py` | Event generation, side-channels |
| `test_ground_truth_annotator_api.py` | REST API endpoints |
| `test_ground_truth_foundation.py` | Models, storage |
| `test_comparison_analyzer.py` | FN/FP detection |
| `test_review_controller.py` | Review workflow |

---

## Troubleshooting

### Virtual environment issues
```bash
rm -rf venv && python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Port conflict
```bash
python -m src.ground_truth_annotator.main --data test.csv --port 8001
```

### Debug logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Performance

| Operation | Target | Notes |
|-----------|--------|-------|
| Swing detection | <60s for 6M bars | With `max_pair_distance=2000` |
| Scale calibration | <100ms | ~7K bars |
| Bar aggregation | <100ms | 10K bars |
| File metrics | <100ms | Any file size |
