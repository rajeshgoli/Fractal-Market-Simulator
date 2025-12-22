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
│   ├── types.py                    # Bar dataclass
│   ├── swing_config.py             # SwingConfig, DirectionConfig
│   ├── swing_node.py               # SwingNode hierarchical structure
│   ├── events.py                   # SwingEvent types
│   ├── dag/                        # DAG-based leg detection (modularized)
│   │   ├── __init__.py             # Re-exports: LegDetector, calibrate, etc.
│   │   ├── leg_detector.py         # LegDetector (main class, formerly HierarchicalDetector)
│   │   ├── leg.py                  # Leg, PendingOrigin dataclasses
│   │   ├── state.py                # BarType, DetectorState
│   │   ├── leg_pruner.py           # LegPruner (pruning algorithms)
│   │   └── calibrate.py            # calibrate, calibrate_from_dataframe, dataframe_to_bars
│   ├── reference_frame.py          # Oriented coordinate system for ratios
│   ├── bar_aggregator.py           # Multi-timeframe OHLC aggregation
│   └── constants.py                # Fibonacci level sets
└── discretization/
    ├── schema.py                   # DiscretizationEvent, SwingEntry, etc.
    ├── discretizer.py              # Batch OHLC → event log processor
    └── io.py                       # JSON read/write for logs

frontend/                           # React + Vite Replay View
├── src/
│   ├── pages/
│   │   ├── Replay.tsx              # Main replay page (calibration mode)
│   │   └── DAGView.tsx             # DAG visualization page (dag mode)
│   ├── components/
│   │   ├── ChartArea.tsx           # Dual lightweight-charts
│   │   ├── SwingOverlay.tsx        # Fib level rendering
│   │   ├── LegOverlay.tsx          # Leg visualization (DAG mode)
│   │   ├── DAGStatePanel.tsx       # DAG internal state display
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
│   dag/leg_detector.py ──────────────────────────────────────────────────┐   │
│   └── LegDetector.process_bar() ───────────► SwingNode + SwingEvent     │   │
│   dag/calibrate.py                                                      │   │
│   └── calibrate() ─────────────────────────► (detector, events)         │   │
│            │                                                             │   │
│            │ uses                                                        │   │
│            ▼                                                             │   │
│   dag/leg_pruner.py ────► LegPruner (pruning algorithms)                │   │
│   dag/leg.py ───────────► Leg, PendingOrigin dataclasses                │   │
│   dag/state.py ─────────► BarType, DetectorState                        │   │
│   reference_frame.py ───► Price ↔ ratio conversion                       │   │
│   bar_aggregator.py ────► Multi-timeframe OHLC                           │   │
│   constants.py ─────────► DISCRETIZATION_LEVELS (16 Fib ratios)          │   │
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

2. Calibrate (hierarchical DAG detection)
   calibrate_from_dataframe(df) → (detector, events)
   detector.get_active_nodes() → List[SwingNode]  # Hierarchical tree

3. Discretize (by depth or custom grouping)
   swings_by_depth = group_swings_by_depth(detector.get_active_nodes())
   Discretizer().discretize(df, swings_by_depth) → DiscretizationLog

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

**Directory:** `src/swing_analysis/dag/`

Modular DAG-based leg detection with incremental swing formation. The main entry points are `LegDetector.process_bar()` for incremental detection and `calibrate()` for batch processing.

**Module structure:**
| Module | Purpose |
|--------|---------|
| `leg_detector.py` | LegDetector class (main entry point) |
| `leg.py` | Leg, PendingOrigin dataclasses |
| `state.py` | BarType enum, DetectorState for persistence |
| `leg_pruner.py` | LegPruner with pruning algorithms |
| `calibrate.py` | calibrate, calibrate_from_dataframe, dataframe_to_bars |

**Leg metrics (#241):**
| Field | Type | Description |
|-------|------|-------------|
| `impulse` | `float` | Raw intensity (points/bar) - internal only, not exposed in API |
| `impulsiveness` | `float | None` | Percentile rank (0-100) of impulse vs all formed legs |
| `spikiness` | `float | None` | Sigmoid-normalized skewness (0-100) of bar contributions |

- **Impulsiveness** measures how fast a move is relative to the historical population. Calculated using bisect for O(log n) percentile lookup against `DetectorState.formed_leg_impulses`.
- **Spikiness** measures whether the move was spike-driven or evenly distributed. Uses running moments (n, sum_x, sum_x2, sum_x3) for O(1) per-bar updates.
- Both are updated only for "live" legs (where `max_origin_breach is None`). Once a leg's origin is breached, values are frozen.

```python
from src.swing_analysis.dag import (
    LegDetector,
    HierarchicalDetector,  # Backward compatibility alias
    DetectorState,
    calibrate,
    calibrate_from_dataframe,
    dataframe_to_bars,
    Leg,
    PendingOrigin,
    LegPruner,
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

# Option 4: Calibrate with Reference layer for tolerance-based invalidation
from src.swing_analysis.reference_layer import ReferenceLayer
config = SwingConfig.default()
ref_layer = ReferenceLayer(config)
detector, events = calibrate(bars, config, ref_layer=ref_layer)
# Events now include Reference layer invalidation/completion events

# Option 5: Process bars incrementally
config = SwingConfig.default()
detector = LegDetector(config)
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
detector2 = LegDetector.from_state(restored_state, config)
```

**Calibration functions:**
| Function | Purpose |
|----------|---------|
| `calibrate(bars, config, progress_callback, ref_layer)` | Run detection on Bar list |
| `calibrate_from_dataframe(df, config, progress_callback, ref_layer)` | Convenience wrapper for DataFrame input |
| `dataframe_to_bars(df)` | Convert DataFrame with OHLC columns to Bar list |

**Pipeline integration (ref_layer parameter):**

When a `ReferenceLayer` is passed to `calibrate()`, tolerance-based invalidation and completion are applied during calibration, not just at response time. This ensures accurate swing counts throughout the replay.

The pipeline order per bar:
1. `detector.process_bar(bar)` — DAG events (formation, structural invalidation, level cross)
2. `ref_layer.update_invalidation_on_bar(swings, bar)` — Tolerance-based invalidation
3. `ref_layer.update_completion_on_bar(swings, bar)` — Completion (2× for small swings)

**Key design principles:**
- **No lookahead** — Algorithm only sees current and past bars
- **Single code path** — Calibration calls `process_bar()` in a loop
- **Independent invalidation** — Each swing checks its own defended pivot (no cascade)
- **DAG hierarchy** — Swings can have multiple parents for structural context
- **Multi-TF optimization** — Uses higher-timeframe bars (1h, 4h, 1d) as candidates for O(1) candidate pairs vs O(lookback²)
- **Directional leg creation** — Bull legs are only created in TYPE_2_BULL (HH, HL) and bear legs only in TYPE_2_BEAR (LH, LL). This ensures correct temporal order: origin_index < pivot_index for all legs (#195, #197)
- **Leg terminology** — Origin is where the move started (fixed), Pivot is the defended extreme (extends). Bull leg: origin=LOW, pivot=HIGH. Bear leg: origin=HIGH, pivot=LOW (#197)

**Event types:**
| Event | When emitted |
|-------|--------------|
| `SwingFormedEvent` | Price breaches formation threshold from candidate pair |
| `SwingInvalidatedEvent` | Defended pivot violated beyond tolerance |
| `SwingCompletedEvent` | Price reaches 2.0 extension target |
| `LevelCrossEvent` | Price crosses Fib level boundary |
| `LegCreatedEvent` | New candidate leg is created (pre-formation) |
| `LegPrunedEvent` | Leg is removed (reasons: `turn_prune`, `proximity_prune`, `breach_prune`, `extension_prune`, `inner_structure`) |
| `LegInvalidatedEvent` | Leg breaches invalidation threshold (configurable, default 0.382) |

**Tolerance rules (Rule 2.2):**
- Big swings (top 10% by range): full tolerance (0.15)
- Children of big swings: basic tolerance (0.10)
- Others: no tolerance (absolute)

**Turn pruning:**

During strong trends, the DAG creates many parallel legs with different origins all converging to the same pivot (the defended extreme extends with price). When a directional turn is detected (Type 2-Bear bar for bull legs, Type 2-Bull bar for bear legs), we apply turn pruning:

**Within-origin pruning (turn_prune)**
1. Group active legs by direction that share the same origin (price and index)
2. For each group: keep ONLY the leg with the largest range
3. Emit `LegPrunedEvent` with `reason="turn_prune"` for discarded legs

**Proximity-based consolidation (#203)**

After turn pruning, legs within a configurable relative difference threshold are consolidated:
1. Sort remaining legs by range (descending)
2. Keep first (largest) as survivor
3. For each remaining leg: if relative_diff(leg, nearest_survivor) < threshold, prune
4. Uses bisect for O(log N) nearest-neighbor lookup
5. Threshold controlled by `SwingConfig.proximity_prune_threshold` (default: 0.05 = 5%)
6. Emit `LegPrunedEvent` with `reason="proximity_prune"` for discarded legs

Example with 5% threshold:
| Leg Range | Nearest Survivor | Rel Diff | Action |
|-----------|------------------|----------|--------|
| 113.5 | — | — | Keep (largest) |
| 100.5 | 113.5 | 11.5% | Keep |
| 98.5 | 100.5 | 2.0% | Prune |
| 38.5 | 100.5 | 62% | Keep (distinct) |

**Active swing immunity:**
Legs that have formed into active swings are never pruned. If an origin has any active swings, the entire origin is immune from pruning.

**Extended visibility for invalidated legs (#203):**

Invalidated legs remain visible in the DAG until pruned by one of two conditions:
- `active` → legs not yet invalidated, shown with solid lines
- `invalidated` → legs past invalidation threshold, shown with dotted lines
- **Engulfed prune:** If both origin AND pivot are breached, invalidated legs are deleted immediately (no replacement)
- **Extension prune:** At N× extension beyond origin, invalidated legs are pruned via `_check_extension_prune()` (disabled by default)

Configuration:
- `DirectionConfig.invalidation_threshold`: Configurable per direction (default: 0.382)
- `SwingConfig.stale_extension_threshold`: Multiplier for extension prune (default: 999.0, effectively disabled)

**Inner structure pruning (#264):**

When multiple legs of the same direction are invalidated simultaneously, prune counter-direction legs from inner structure pivots. Inner structure legs are redundant when an outer-origin leg exists with the same current pivot.

Example (bear direction):
```
H1=6100 → L1=5900 → H2=6050 → L2=5950 → H4=6150
         (outer)              (inner)

At H4 (breaks above H1):
- Bear leg H1→L1 invalidated (outer structure)
- Bear leg H2→L2 invalidated (inner structure, contained in H1→L1)
- Bull leg L1→H4 survives (outer-origin)
- Bull leg L2→H4 PRUNED (inner-origin, reason="inner_structure")
```

Containment definition:
- Bear: B_inner contained in B_outer iff `inner.origin < outer.origin AND inner.pivot > outer.pivot`
- Bull: B_inner contained in B_outer iff `inner.origin > outer.origin AND inner.pivot < outer.pivot`

Pruning conditions:
1. Multiple legs of same direction invalidated in same bar
2. One leg strictly contained in another
3. Counter-direction legs exist from both pivots
4. Both counter-direction legs share the same current pivot

**Benefits:**
- Multi-origin preservation: Keeps the best leg from each structural level
- Fractal compression: Detailed near active zone, sparse further back
- Self-regulating: Tree size stays bounded as older noise is pruned
- Counter-trend references: Invalidated legs remain visible for reference until 3× extension

---

### Reference Layer

**File:** `src/swing_analysis/reference_layer.py`

Post-processes DAG output to produce trading references. Applies semantic filtering rules from `Docs/Reference/valid_swings.md`.

**Big vs Small (hierarchy-based definition):**
- **Big swing** = `len(swing.parents) == 0` (root level, no parents)
- **Small swing** = `len(swing.parents) > 0` (has parent)

This is determined by hierarchy, not range percentile.

```python
from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwingInfo,
    InvalidationResult,
    CompletionResult,
)
from src.swing_analysis.dag import calibrate
from src.swing_analysis.swing_config import SwingConfig

# Get swings from DAG
detector, events = calibrate(bars)
swings = detector.get_active_swings()

# Apply reference layer filters
config = SwingConfig.default()
ref_layer = ReferenceLayer(config)
reference_swings = ref_layer.get_reference_swings(swings)

# Check invalidation on new bar with touch/close thresholds
for info in reference_swings:
    result = ref_layer.check_invalidation(info.swing, bar)
    if result.is_invalidated:
        print(f"{info.swing.swing_id} invalidated: {result.reason}")

# Check completion on new bar
for info in reference_swings:
    result = ref_layer.check_completion(info.swing, bar)
    if result.is_completed:
        print(f"{info.swing.swing_id} completed")

# Get only big swings (root level, no parents)
big_swings = ref_layer.get_big_swings(swings)

# Batch invalidation check
invalidated = ref_layer.update_invalidation_on_bar(swings, bar)
for swing, result in invalidated:
    swing.invalidate()

# Batch completion check
completed = ref_layer.update_completion_on_bar(swings, bar)
for swing, result in completed:
    swing.complete()
```

**Key operations:**
| Method | Purpose |
|--------|---------|
| `get_reference_swings(swings)` | Get all swings with tolerances computed |
| `check_invalidation(swing, bar)` | Apply Rule 2.2 with touch/close thresholds |
| `check_completion(swing, bar)` | Check if swing should be marked complete |
| `get_big_swings(swings)` | Get only big swings (root level, no parents) |
| `update_invalidation_on_bar(swings, bar)` | Batch invalidation check |
| `update_completion_on_bar(swings, bar)` | Batch completion check |

*Note: Separation filtering (Rules 4.1, 4.2) has been removed (#164). The DAG handles separation at formation time via proximity and breach pruning.*

**Invalidation thresholds (Rule 2.2):**
| Swing Size | Touch Tolerance | Close Tolerance |
|------------|-----------------|-----------------|
| Big (no parent) | 0.15 × range | 0.10 × range |
| Small (has parent) | 0 (absolute) | 0 (absolute) |

**Completion rules:**
| Swing Size | Completion Rule |
|------------|-----------------|
| Big (no parent) | Never complete — keep active indefinitely |
| Small (has parent) | Complete at 2× extension |

**ReferenceSwingInfo fields:**
- `swing`: The underlying SwingNode
- `touch_tolerance`: Tolerance for wick violations
- `close_tolerance`: Tolerance for close violations
- `is_reference`: Whether swing passes all filters
- `filter_reason`: Why filtered (if not reference)
- `is_big()`: Method to check if swing is big (no parents)

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
from src.swing_analysis import calibrate_from_dataframe

# Calibrate to get SwingNode tree
detector, events = calibrate_from_dataframe(df)

# Group by depth for discretization
swings_by_depth = {}
for node in detector.get_active_nodes():
    depth = node.get_depth()
    key = f"depth_{depth}" if depth < 3 else "deeper"
    swings_by_depth.setdefault(key, []).append(node)

config = DiscretizerConfig(
    level_set=[0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0, 2.618, 3.0, 4.0],
    crossing_semantics="close_cross",
)

discretizer = Discretizer(config)

log = discretizer.discretize(
    ohlc=df,                              # DataFrame with timestamp, open, high, low, close
    swings=swings_by_depth,               # Dict[depth_key, List[SwingNode]]
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
| `Replay.tsx` | Main page for calibration mode |
| `DAGView.tsx` | Page for DAG build visualization mode |
| `ChartArea.tsx` | Two stacked lightweight-charts |
| `SwingOverlay.tsx` | Fib level rendering on charts |
| `LegOverlay.tsx` | Leg visualization for DAG mode |
| `PlaybackControls.tsx` | Play/pause/step transport |
| `ExplanationPanel.tsx` | Calibration report and swing details |
| `DAGStatePanel.tsx` | DAG internal state display (legs, origins, pivots, expandable lists, attachments) |
| `Sidebar.tsx` | Event filters, feedback input, attachment display |
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
python -m pytest tests/test_calibration.py -v

# Single test
python -m pytest tests/test_calibration.py::TestCalibrateFromDataframe -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
```

**Test organization:**

| File | Tests |
|------|-------|
| `conftest.py` | Shared fixtures (`make_bar()`) |
| `test_detector_state.py` | Initialization, serialization, state restore |
| `test_swing_lifecycle.py` | Formation, invalidation, level crossing, parent assignment |
| `test_leg_pruning.py` | Turn pruning, domination pruning |
| `test_leg_extension.py` | Pivot extension, same-bar prevention, state cleanup |
| `test_calibration.py` | Calibrate functions, DataFrame helpers, performance |
| `test_discretizer.py` | Event generation, side-channels |
| `test_reference_frame.py` | ReferenceFrame coordinate system |
| `test_swing_config.py` | SwingConfig dataclass |
| `test_swing_node.py` | SwingNode hierarchical structure |
| `test_swing_events.py` | Event types |

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

The replay view backend (`src/ground_truth_annotator/`) uses LegDetector for incremental swing detection with Reference layer filtering:

```python
# Config: GET /api/config
# Returns application configuration including visualization mode
# {mode: "calibration" | "dag"}

# Calibration: GET /api/replay/calibrate?bar_count=10000
# Returns swings grouped by depth with tree statistics

# Advance: POST /api/replay/advance
# {calibration_bar_count, current_bar_index, advance_by}
# Processes bars using detector.process_bar() and returns events

# DAG State: GET /api/dag/state
# Returns internal leg-level state for DAG visualization:
# - active_legs: currently tracked legs (pre-formation candidates)
# - pending_origins: potential origins awaiting confirmation for each direction
# - leg_counts: count by direction (bull/bear)
```

**Reference Layer Integration:**

The API pipeline applies Reference layer filtering to DAG output before returning swings:

```
┌─────────────────────────────────────────────────────────────────┐
│                     API Request Flow                             │
│                                                                  │
│  1. calibrate(bars) ─────► LegDetector                          │
│                              │                                   │
│                              ▼                                   │
│  2. detector.get_active_swings() ────► Raw DAG swings           │
│                              │                                   │
│                              ▼                                   │
│  3. ReferenceLayer.get_reference_swings() ──► Filtered swings   │
│        • classify_swings() - big/small classification           │
│                              │                                   │
│                              ▼                                   │
│  4. Return filtered reference swings to client                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key files:**
- `src/ground_truth_annotator/routers/replay.py` - API endpoints
- `src/swing_analysis/reference_layer.py` - Filtering logic
- `src/swing_analysis/dag/` - DAG algorithm (modularized)
  - `leg_detector.py` - LegDetector main class
  - `leg_pruner.py` - Pruning algorithms
  - `calibrate.py` - Batch processing

### Feedback System

The feedback system captures user observations with rich context snapshots:

**Frontend types** (`frontend/src/lib/api.ts`):
- `PlaybackFeedbackSnapshot` - Complete state at observation time
- `FeedbackAttachment` - Attached leg/origin/pivot reference (max 5 per observation)
- `submitPlaybackFeedback()` - Submit observation with optional screenshot

**Attachment types:**
```typescript
type FeedbackAttachment =
  | { type: 'leg'; leg_id: string; direction: 'bull' | 'bear'; pivot_price: number; origin_price: number; ... }
  | { type: 'pending_origin'; direction: 'bull' | 'bear'; price: number; bar_index: number; source: string };
```

**Backend storage** (`src/ground_truth_annotator/storage.py`):
- `PLAYBACK_FEEDBACK_SCHEMA_VERSION = 2` - Current schema version
- Observations persist to `ground_truth/playback_feedback.json`
- Screenshots saved to `ground_truth/screenshots/`

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
