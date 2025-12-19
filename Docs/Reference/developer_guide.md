# Developer Guide

Technical reference for engineers working on the Market Simulator codebase.

---

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
python -m pytest tests/ -v
```

---

## Directory Structure

```
src/
├── data/
│   └── ohlc_loader.py              # CSV loading (TradingView + semicolon formats)
├── swing_analysis/
│   ├── types.py                    # Bar, BullReferenceSwing, BearReferenceSwing
│   ├── swing_config.py             # SwingConfig, DirectionConfig (rewrite Phase 1)
│   ├── swing_node.py               # SwingNode hierarchical structure (rewrite Phase 1)
│   ├── events.py                   # SwingEvent types (rewrite Phase 1)
│   ├── hierarchical_detector.py    # Incremental detector with process_bar() (rewrite Phase 2)
│   ├── adapters.py                 # Legacy compatibility: SwingNode ↔ ReferenceSwing (rewrite Phase 3)
│   ├── swing_detector.py           # Main detection: detect_swings() (legacy)
│   ├── incremental_detector.py     # O(active) per-bar detection for replay (legacy)
│   ├── level_calculator.py         # Fibonacci level computation
│   ├── reference_frame.py          # Oriented coordinate system for ratios
│   ├── bar_aggregator.py           # Multi-timeframe OHLC aggregation
│   ├── scale_calibrator.py         # Auto-calibrate S/M/L/XL boundaries (legacy)
│   ├── constants.py                # Fibonacci level sets
│   ├── swing_state_manager.py      # Live swing tracking (legacy)
│   └── event_detector.py           # Live event detection (legacy)
└── discretization/
    ├── schema.py                   # DiscretizationEvent, SwingEntry, etc.
    ├── discretizer.py              # Batch OHLC → event log processor
    └── io.py                       # JSON read/write for logs

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

tests/                              # 600+ tests
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
│ 3b. DEFENDED PIVOT OPTIMIZATION (#136)                            │
│    _optimize_defended_pivot() — recursively find best "1" endpoint│
│    until no candidates within 0.1 FIB separation, then classify:  │
│    • >= 0.236 retracement: valid swing (is_candidate=False)       │
│    • 0.1-0.236 retracement: candidate swing (is_candidate=True)   │
│    • < 0.1 retracement: rejected (None)                           │
└───────────────────────────────────────────────────────────────────┘
                                 ↓
┌───────────────────────────────────────────────────────────────────┐
│ 4. PROTECTION VALIDATION (protection_tolerance)                   │
│    _apply_protection_filter() — reject violated swing points      │
│    Note: At XL scale (no larger_swings), uses 0 tolerance         │
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
- `is_candidate` (True if pending 0.236 validation, False if fully valid)
- `pending_level` (0.236 if candidate, None if valid)
- `current_retracement` (retracement ratio, only on candidates)

**Multi-scale detection pattern:**

```python
# Detect XL first, pass results to L, and so on
xl_result = detect_swings(df, lookback=10, quota=4)
xl_swings = xl_result["bull_references"] + xl_result["bear_references"]

l_result = detect_swings(df, lookback=8, quota=6, larger_swings=xl_swings)
# L swings now have structural separation context from XL
```

---

### Incremental Swing Detection

**File:** `src/swing_analysis/incremental_detector.py`

O(active_swings) per-bar detection for replay playback, replacing O(N log N) full detection.

```python
from src.swing_analysis.incremental_detector import (
    IncrementalSwingState,
    advance_bar_incremental,
    initialize_from_calibration,
)

# Initialize from calibration results
state = initialize_from_calibration(
    calibration_swings=active_swings_by_scale,  # Dict of scale -> swing list
    source_bars=source_bars,
    calibration_bar_count=10000,
    scale_thresholds={"XL": 100.0, "L": 40.0, "M": 15.0, "S": 0.0},
    current_price=current_price,
    lookback=5,
    protection_tolerance=0.1,
)

# Advance one bar incrementally
events = advance_bar_incremental(
    bar_high=bar.high,
    bar_low=bar.low,
    bar_close=bar.close,
    state=state
)

# Events are: SWING_FORMED, SWING_INVALIDATED, LEVEL_CROSS, SWING_COMPLETED
for event in events:
    print(f"{event.event_type}: {event.swing_id} at bar {event.bar_index}")
```

**Key characteristics:**
- Statistics (median_candle, price_range) frozen at calibration
- Swing point detection deferred by lookback (confirmed at N - lookback)
- No retroactive promotion of redundancy/quota-filtered swings
- Simulates live trading behavior (decisions made with available information)

**Performance:** ~2,500x improvement (from ~1.6M ops to ~630 ops per 12-bar tick)

---

### Hierarchical Swing Detection (Rewrite Phase 2)

**File:** `src/swing_analysis/hierarchical_detector.py`

Incremental swing detector with hierarchical model. Replaces both batch and incremental detectors with a single `process_bar()` entry point. Calibration is just a loop calling `process_bar()` — no special batch logic.

```python
from src.swing_analysis.hierarchical_detector import (
    HierarchicalDetector,
    DetectorState,
    calibrate,
    calibrate_from_dataframe,
    dataframe_to_bars,
)
from src.swing_analysis.swing_config import SwingConfig

# Option 1: Calibrate from DataFrame (most common)
import pandas as pd
df = pd.read_csv("market_data.csv")
detector, events = calibrate_from_dataframe(df)
active_swings = detector.get_active_swings()

# Option 2: Calibrate from Bar list
bars = [...]  # List[Bar]
detector, events = calibrate(bars)

# Option 3: Calibrate with progress callback
def on_progress(current: int, total: int):
    print(f"Processing bar {current}/{total}")

detector, events = calibrate(bars, progress_callback=on_progress)

# Option 4: Process bars incrementally
config = SwingConfig.default()
detector = HierarchicalDetector(config)
for bar in bars:
    events = detector.process_bar(bar)
    for event in events:
        print(f"{event.event_type}: {event.swing_id}")

# Convert DataFrame to Bar list manually
bars = dataframe_to_bars(df)  # Handles various column naming conventions

# Save and restore state
state = detector.get_state()
state_dict = state.to_dict()  # JSON-serializable

restored_state = DetectorState.from_dict(state_dict)
detector2 = HierarchicalDetector.from_state(restored_state, config)
```

**Calibration functions:**
| Function | Purpose |
|----------|---------|
| `calibrate(bars, config, progress_callback)` | Run detection on Bar list |
| `calibrate_from_dataframe(df, config, progress_callback)` | Convenience wrapper for DataFrame input |
| `dataframe_to_bars(df)` | Convert DataFrame with OHLC columns to Bar list |

**Key design principles:**
- **No lookahead** — Algorithm only sees current and past bars
- **Single code path** — Calibration calls `process_bar()` in a loop
- **Independent invalidation** — Each swing checks its own defended pivot (no cascade)
- **DAG hierarchy** — Swings can have multiple parents for structural context

**Event types:**
| Event | When emitted |
|-------|--------------|
| `SwingFormedEvent` | Price breaches formation threshold from candidate pair |
| `SwingInvalidatedEvent` | Defended pivot violated beyond tolerance |
| `SwingCompletedEvent` | Price reaches 2.0 extension target |
| `LevelCrossEvent` | Price crosses Fib level boundary |

**Tolerance rules (Rule 2.2):**
- Big swings (top 10% by range): full tolerance (0.15)
- Children of big swings: basic tolerance (0.10)
- Others: no tolerance (absolute)

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

# Tolerance checks (rewrite Phase 1)
frame.is_violated(Decimal("4990"))                # True: below defended pivot
frame.is_violated(Decimal("4990"), tolerance=0.15) # False: within 15% tolerance
frame.is_formed(Decimal("5030"))                  # True: above 0.287 formation threshold
frame.is_completed(Decimal("5200"))               # True: reached 2.0 extension
frame.get_fib_price(0.618)                        # Returns Decimal("5061.8")
```

**Ratio interpretation:**
| Ratio | Meaning |
|-------|---------|
| 0 | Defended pivot (stop level) |
| 0.382-0.618 | Retracement zone |
| 1 | Origin extremum |
| 2 | Completion target |
| < 0 | Invalidation territory |

**Tolerance check methods:**
| Method | Description |
|--------|-------------|
| `is_violated(price, tolerance=0)` | Check if defended pivot is violated (ratio < -tolerance) |
| `is_formed(price, formation_fib=0.287)` | Check if formation threshold breached |
| `is_completed(price)` | Check if swing reached 2.0 target |
| `get_fib_price(level)` | Get absolute price for a Fib level |

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
    swings={"XL": xl_swings, "L": l_swings, ...},  # Dict[scale, List[ReferenceSwing | SwingNode]]
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
| `test_reference_frame.py` | ReferenceFrame coordinate system |
| `test_swing_config.py` | SwingConfig dataclass |
| `test_swing_node.py` | SwingNode hierarchical structure |
| `test_swing_events.py` | Event types |
| `test_hierarchical_detector.py` | Hierarchical detector algorithm |
| `test_adapters.py` | Legacy compatibility adapters |

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

### Replay View API

The replay view backend (`src/ground_truth_annotator/`) uses HierarchicalDetector for incremental swing detection:

```python
# Calibration: GET /api/replay/calibrate?bar_count=10000
# Returns swings grouped by scale with hierarchy info (depth, parent_ids)

# Advance: POST /api/replay/advance
# {calibration_bar_count, current_bar_index, advance_by}
# Processes bars using detector.process_bar() and returns events
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
