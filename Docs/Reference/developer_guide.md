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
│   └── bar_aggregator.py           # Multi-timeframe OHLC aggregation

frontend/                           # React + Vite DAG View
├── src/
│   ├── pages/
│   │   └── DAGView.tsx             # Main DAG visualization page
│   ├── components/
│   │   ├── ChartArea.tsx           # Dual lightweight-charts
│   │   ├── LegOverlay.tsx          # Leg visualization
│   │   ├── DAGStatePanel.tsx       # DAG internal state display
│   │   └── PlaybackControls.tsx    # Transport controls
│   └── hooks/
│       └── useForwardPlayback.ts   # Forward-only playback
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
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                                     │
│                                                                              │
│   frontend/src/                                                             │
│   └── DAGView.tsx ◄── ChartArea, LegOverlay, PlaybackControls              │
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

3. Analyze
   swings = detector.get_active_swings()  # Filter, aggregate, visualize
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

**Segment impulse tracking (#307):**

When a child leg forms within a parent leg, segment impulse fields capture the two-phase movement pattern:

| Field | Type | Description |
|-------|------|-------------|
| `segment_deepest_price` | `Decimal | None` | Parent's pivot price when first child formed |
| `segment_deepest_index` | `int | None` | Bar index of the deepest point |
| `impulse_to_deepest` | `float | None` | Impulse from parent origin to deepest point |
| `impulse_back` | `float | None` | Impulse from deepest back to child origin (counter-move) |
| `net_segment_impulse` | `float | None` | Property: `impulse_to_deepest - impulse_back` |
| `counter_trend_ratio` | `float | None` | Deprecated in #337; see branch ratio domination |
| `origin_counter_trend_range` | `float | None` | Range of counter-trend at origin when leg was created |

- **Impulse to deepest** measures the primary move intensity (parent origin → segment extreme)
- **Impulse back** measures the counter-move intensity (segment extreme → child origin)
- **Net segment impulse** captures sustained conviction:
  - High positive: Sharp primary move, weak counter-move (sustained trend)
  - Near zero: Both moves similar (contested)
  - Negative: Counter-move was more impulsive (gave back progress)

These fields are set on the **child leg** when it is created, capturing the parent's segment state at that moment. The deepest point may extend after child creation if the parent's pivot extends.

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

# Update config and reset state (Issue #288)
new_config = SwingConfig.default().with_bull(formation_fib=0.5)
detector.update_config(new_config)  # Resets internal state, re-run calibration
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
| Event | API Type | When emitted |
|-------|----------|--------------|
| `SwingFormedEvent` | `SWING_FORMED` | Price breaches formation threshold from candidate pair |
| `SwingInvalidatedEvent` | `SWING_INVALIDATED` | Defended pivot violated beyond tolerance |
| `SwingCompletedEvent` | `SWING_COMPLETED` | Price reaches 2.0 extension target |
| `LevelCrossEvent` | `LEVEL_CROSS` | Price crosses Fib level boundary |
| `LegCreatedEvent` | `LEG_CREATED` | New candidate leg is created (pre-formation) |
| `LegPrunedEvent` | `LEG_PRUNED` | Leg is removed (reasons: `turn_prune`, `origin_proximity_prune`, `breach_prune`, `extension_prune`) |
| `LegInvalidatedEvent` | `LEG_INVALIDATED` | Leg breaches invalidation threshold (configurable, default 0.382) |

All event types are serialized with their API type string (second column) in API responses. Leg events include their specific metadata: `LegPrunedEvent` includes `reason` and `explanation` fields in the `trigger_explanation`.

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

**Origin-proximity consolidation (#294, #298, #319)**

After turn pruning, legs close together in origin (time, range) space are consolidated within pivot groups.

**Two strategies available** (configured via `SwingConfig.proximity_prune_strategy`):

| Strategy | Description | Complexity |
|----------|-------------|------------|
| `'oldest'` | Keep oldest leg in each cluster (default, purely geometric) | O(N log N) |
| `'counter_trend'` | Keep leg with highest counter-trend range (market-structure aware) | O(N²) |

**Counter-trend scoring (#319):** Uses `parent.segment_deepest_price` to compute how far price traveled against the trend to reach each origin. Higher counter-trend range = more significant structural level (price worked harder to establish it). Fallback to leg's own range when parent data unavailable.

Algorithm (both strategies):
1. **Group by pivot** `(pivot_price, pivot_index)` — legs with different pivots are independent
2. **Build proximity clusters** — legs within time/range thresholds using union-find
3. **Apply strategy** to select winner per cluster:
   - `'oldest'`: Keep oldest leg (O(N log N) via binary search)
   - `'counter_trend'`: Keep highest counter-trend scorer (tie-breaker: oldest)
4. Prune non-winners
5. Emit `LegPrunedEvent` with `reason="origin_proximity_prune"` for discarded legs

Configuration:
- `SwingConfig.origin_range_prune_threshold` (default: 0.0 = disabled)
- `SwingConfig.origin_time_prune_threshold` (default: 0.0 = disabled)
- `SwingConfig.proximity_prune_strategy` (default: `'oldest'`)

**Branch ratio origin domination (#337):**

Prevents insignificant child legs at creation time by requiring the counter-trend at a new leg's origin to be at least a minimum ratio of the counter-trend at its parent's origin:

```
R0 = counter-trend at new leg's origin
R1 = counter-trend at parent's origin
Create leg if: R0 >= min_branch_ratio * R1
```

This scales naturally through the hierarchy:
- Root level: Large counter-trend (e.g., 100 pts)
- Child needs: >= 10% of 100 = 10 pts
- Grandchild needs: >= 10% of 10 = 1 pt

**Why this works:** At a strong pivot (countering a large rally/drop), child legs need significant counter-trend to be considered valid. At a weak pivot, smaller counter-trends are acceptable. This captures the fractal nature of market structure.

Configuration: `SwingConfig.min_branch_ratio` (default: 0.0 = disabled)

**Turn ratio pruning (#341, #342, #344, #357):**

Filters sibling legs horizontally at shared pivots based on turn ratio:
```
turn_ratio = counter_leg._max_counter_leg_range / counter_leg.range
```

Turn ratio measures how far a leg extended relative to the counter-trend that created its origin. Low turn ratio means the leg extended far beyond what the structure justified ("punched above its weight class").

**Bootstrap tracking (#357):** `_max_counter_leg_range` can be:
- `None` (exempt): Leg created before any opposite-direction leg existed (truly unknown counter-trend)
- `0.0` (most prunable): Leg created after opposite direction bootstrapped, but no counter-leg at that pivot
- `> 0.0` (normal): Actual counter-trend range captured at leg creation

The distinction is tracked via `DetectorState._has_created_bull_leg` and `_has_created_bear_leg` flags. When creating a bull leg, if no bear leg with pivot at that origin exists:
- Before any bear leg ever created → `_max_counter_leg_range = None` (exempt)
- After bear legs exist → `_max_counter_leg_range = 0.0` (turn_ratio = 0, most prunable)

Two mutually exclusive modes:
1. **Threshold mode** (`min_turn_ratio > 0`): Prune legs with `turn_ratio < min_turn_ratio`
2. **Top-k mode** (`min_turn_ratio == 0` and `max_turns_per_pivot > 0`): Keep only the k highest-ratio legs at each pivot

```
Threshold mode:
  If turn_ratio < min_turn_ratio → prune the leg

Top-k mode:
  Sort all counter-legs at pivot by turn_ratio (descending)
  Keep top k, prune the rest
```

**Largest leg exemption (#344):** The largest leg (by range) at each shared pivot is always exempt from turn-ratio pruning. Since the biggest leg has the lowest ratio (range is in the denominator), it would otherwise be pruned first — but it represents primary structure and should be preserved.

When a new leg forms at origin O, counter-legs with pivot == O are checked.

Configuration:
- `SwingConfig.min_turn_ratio` (default: 0.0 = disabled)
- `SwingConfig.max_turns_per_pivot` (default: 0 = disabled, max: 20)

If both are 0, turn ratio pruning is disabled. If `min_turn_ratio > 0`, threshold mode is used (ignoring `max_turns_per_pivot`).

**Frontend controls (#347):** Two mutually exclusive sliders in the Detection Config panel:
- **Min Ratio %** (0-50%): Setting > 0 auto-zeros Max Turns
- **Max Turns** (0-20): Setting > 0 auto-zeros Min Ratio

Both at 0 = disabled. No explicit Off button needed.

**Why pivot grouping is required:** Legs with different pivots can validly have newer legs with larger ranges (e.g., a leg that found a better origin AND a later pivot). Cross-pivot comparisons would incorrectly flag this as invalid.

Example with 10% time threshold and 20% range threshold at bar 100:
| Origin Index | Range | Time Ratio | Range Ratio | Action |
|--------------|-------|------------|-------------|--------|
| 0 | 10.0 | — | — | Keep (oldest) |
| 5 | 9.5 | 0.05 < 0.10 | 0.05 < 0.20 | Prune |
| 50 | 8.0 | 0.50 > 0.10 | — | Keep (time far apart) |

**Active swing immunity:**
Legs that have formed into active swings are never pruned. If an origin has any active swings, the entire origin is immune from pruning.

**Extended visibility for breached legs (#203, #345):**

Breached legs (where origin has been touched) remain visible in the DAG until pruned:
- `active` → legs with origin not yet breached, shown with solid lines
- `stale` → legs inactive for extended periods, shown with dashed lines
- Breached legs (`max_origin_breach is not None`) shown with dotted lines
- **Engulfed prune:** If both origin AND pivot are breached, legs are deleted immediately (no replacement)
- **Extension prune:** At N× extension beyond origin, breached child legs are pruned via `_check_extension_prune()`

Configuration:
- `SwingConfig.stale_extension_threshold`: Multiplier for extension prune (default: 3.0)
- `SwingConfig.emit_level_crosses`: Enable/disable LevelCrossEvent emission (default: False for performance)
- `SwingConfig.enable_engulfed_prune`: Toggle engulfed pruning algorithm

**Note (#345):** The `invalidation_threshold` config has been removed. Origin breach is now detected at 0% (any touch). Use `max_origin_breach is not None` to check if a leg's origin has been breached.

**Benefits:**
- Multi-origin preservation: Keeps the best leg from each structural level
- Fractal compression: Detailed near active zone, sparse further back
- Self-regulating: Tree size stays bounded as older noise is pruned
- Counter-trend references: Invalidated legs remain visible for reference until 3× extension

---

### Reference Layer

**File:** `src/swing_analysis/reference_layer.py`

Post-processes DAG output to produce trading references. Applies semantic filtering rules from `Docs/Reference/valid_swings.md`.

**Big vs Small (range-based definition):**
- **Big swing** = top 10% by range (historically called XL)
- **Small swing** = all other swings

This is determined by range percentile, computed via `ReferenceLayer._compute_big_swing_threshold()`.

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

# Get only big swings (top 10% by range)
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
| `get_big_swings(swings)` | Get only big swings (top 10% by range) |
| `update_invalidation_on_bar(swings, bar)` | Batch invalidation check |
| `update_completion_on_bar(swings, bar)` | Batch completion check |

*Note: Separation filtering (Rules 4.1, 4.2) has been removed (#164). The DAG handles separation at formation time via origin-proximity and breach pruning.*

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
| `is_formed(price, formation_fib=0.236)` | Check if formation threshold breached |
| `is_completed(price)` | Check if swing reached 2.0 target |
| `get_fib_price(level)` | Get absolute price for a Fib level |

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
| `DAGView.tsx` | Main DAG visualization page |
| `ChartArea.tsx` | Two stacked lightweight-charts |
| `LegOverlay.tsx` | Leg visualization (includes tree icon hover) |
| `HierarchyModeOverlay.tsx` | Hierarchy exploration mode (exit button, connection lines, status) |
| `PlaybackControls.tsx` | Play/pause/step transport |
| `DAGStatePanel.tsx` | DAG internal state display (legs, origins, pivots, expandable lists, attachments) |
| `Sidebar.tsx` | Event filters, feedback input, attachment display |
| `useForwardPlayback.ts` | Forward-only playback (step back via backend API) |
| `useHierarchyMode.ts` | Hierarchy exploration state management (#250) |
| `useChartPreferences.ts` | Settings persistence to localStorage |
| `useDAGViewState.ts` | DAG view consolidated state management |

**Frontend Architecture Notes:**
- DAGView is the sole view (ViewMode infrastructure removed in #349)
- `useForwardPlayback` has two bar advance mechanisms:
  - `renderNextBar`: Buffer-based for smooth continuous playback
  - `advanceBar`: Direct API call for manual stepping (step forward, jump to event)

**Settings Persistence (#347):**

`useChartPreferences` persists user settings to localStorage, including:
- Chart aggregation scales, zoom levels, maximized state
- Speed multiplier and aggregation
- Linger enabled/event states
- Detection config (full `DetectionConfig` object)

Schema evolution is handled via `mergeDetectionConfig()`, which deep-merges saved config with `DEFAULT_DETECTION_CONFIG` to ensure new fields (like `min_turn_ratio`, `max_turns_per_pivot`) have defaults when loading older saved configs.

**Backward Navigation:**

The `useForwardPlayback` hook supports stepping backward via backend API:

```typescript
// Hook return values
canStepBack: boolean;  // true when currentPosition > 0
```

**Implementation details:**
- `stepBack()` calls `POST /api/replay/reverse` to replay from bar 0 to current-1
- Backend resets detector and replays all bars to the target position
- Response includes full DAG state, swing state, and aggregated bars
- ~0.25s latency for 1k bars (acceptable for single-step backward)

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

# Reverse: POST /api/replay/reverse
# {current_bar_index, include_aggregated_bars?, include_dag_state?}
# Resets detector and replays from bar 0 to current_bar_index - 1
# Returns same response format as /advance (ReplayAdvanceResponse)
# Used for backward navigation in playback

# DAG State: GET /api/dag/state
# Returns internal leg-level state for DAG visualization:
# - active_legs: currently tracked legs (pre-formation candidates)
#   - includes parent_leg_id and swing_id for hierarchy (#250)
# - pending_origins: potential origins awaiting confirmation for each direction
# - leg_counts: count by direction (bull/bear)

# Leg Lineage: GET /api/dag/lineage/{leg_id}
# Returns full hierarchy for a leg (used by hierarchy exploration mode #250):
# - leg_id: The queried leg
# - ancestors: Chain from this leg to root (parent, grandparent, ...)
# - descendants: All legs whose ancestry includes this leg
# - depth: How deep this leg is (0 = root)

# Detection Config: GET /api/replay/config
# Returns current detection configuration:
# - bull/bear: Per-direction thresholds (formation_fib, engulfed_breach_threshold)
# - stale_extension_threshold: Extension multiplier for stale pruning
# - origin_range_threshold: Range similarity threshold for origin-proximity pruning (#294)
# - origin_time_threshold: Time proximity threshold for origin-proximity pruning (#294)

# Detection Config Update: PUT /api/replay/config
# Updates detection config and re-calibrates from bar 0:
# Request body (all fields optional):
# {
#   "bull": {"formation_fib": 0.382, "engulfed_breach_threshold": 0.0},
#   "bear": {"formation_fib": 0.382, "engulfed_breach_threshold": 0.0},
#   "stale_extension_threshold": 3.0,
#   "origin_range_threshold": 0.05,
#   "origin_time_threshold": 0.10
# }
# Returns updated configuration after re-calibration
# Note (#345): invalidation_threshold removed; origin breach detected at 0%
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
- `FeedbackDetectionConfig` - Detection config captured at observation time (#320)
- `FeedbackAttachment` - Attached leg/origin/pivot reference (max 5 per observation)
- `submitPlaybackFeedback()` - Submit observation with optional screenshot

**Snapshot fields:**
```typescript
interface PlaybackFeedbackSnapshot {
  state: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
  csv_index: number;           // Authoritative CSV row index
  bars_since_calibration: number;
  current_bar_index: number;
  swings_found: { XL, L, M, S };
  event_context?: {...};       // If during linger event
  mode?: 'replay' | 'dag';
  replay_context?: {...};      // Replay-specific
  dag_context?: {...};         // DAG-specific
  attachments?: FeedbackAttachment[];
  detection_config?: FeedbackDetectionConfig;  // Config at observation time (#320)
}
```

**Detection config in feedback (#320):**
The `detection_config` field captures the full detection configuration at observation time, enabling reproducibility:
- Bull/bear formation and invalidation thresholds
- Stale extension threshold
- Origin range/time proximity thresholds
- Pruning algorithm toggles (engulfed)

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
