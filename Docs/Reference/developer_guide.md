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
│   ├── detection_config.py             # DetectionConfig, DirectionConfig
│   ├── swing_node.py               # SwingNode hierarchical structure
│   ├── events.py                   # DetectionEvent types
│   ├── dag/                        # DAG-based leg detection (modularized)
│   │   ├── __init__.py             # Re-exports: LegDetector, Leg, DetectorState, etc.
│   │   ├── leg_detector.py         # LegDetector (main class, formerly HierarchicalDetector)
│   │   ├── leg.py                  # Leg, PendingOrigin dataclasses
│   │   ├── state.py                # BarType, DetectorState
│   │   └── leg_pruner.py           # LegPruner (pruning algorithms)
│   ├── reference_frame.py          # Oriented coordinate system for ratios
│   └── bar_aggregator.py           # Multi-timeframe OHLC aggregation

frontend/                           # React + Vite DAG View
├── src/
│   ├── pages/
│   │   ├── DAGView.tsx             # Main DAG visualization page
│   │   └── LevelsAtPlayView.tsx    # Reference Layer visualization (#374)
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
│   └── LegDetector.process_bar() ───────────► SwingNode + DetectionEvent │   │
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

2. Process bars incrementally (hierarchical DAG detection)
   detector = LegDetector()
   for bar in bars:
       events = detector.process_bar(bar)
   detector.state.active_legs → List[Leg]  # Active legs

3. Analyze
   legs = detector.state.active_legs  # Filter, aggregate, visualize
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

Modular DAG-based leg detection with incremental swing formation. The main entry point is `LegDetector.process_bar()` for incremental detection.

**Module structure:**
| Module | Purpose |
|--------|---------|
| `leg_detector.py` | LegDetector class (main entry point) |
| `leg.py` | Leg, PendingOrigin dataclasses |
| `state.py` | BarType enum, DetectorState for persistence |
| `leg_pruner.py` | LegPruner with pruning algorithms |

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
    Leg,
    PendingOrigin,
    LegPruner,
)
from src.swing_analysis.detection_config import DetectionConfig

# Process bars incrementally
config = DetectionConfig.default()
detector = LegDetector(config)
for bar in bars:
    events = detector.process_bar(bar)
    for event in events:
        print(f"{event.event_type}: {event.swing_id}")

# Process with Reference layer for tolerance-based invalidation
from src.swing_analysis.reference_layer import ReferenceLayer
config = DetectionConfig.default()
ref_layer = ReferenceLayer(config)
detector = LegDetector(config)
for bar in bars:
    events = detector.process_bar(bar)
    ref_result = ref_layer.update(bar, detector.state.active_legs)
    # ref_result contains Reference layer invalidation/completion events

# Save and restore state
state = detector.get_state()
state_dict = state.to_dict()  # JSON-serializable

restored_state = DetectorState.from_dict(state_dict)
detector2 = LegDetector.from_state(restored_state, config)

# Update config and reset state (Issue #288)
new_config = DetectionConfig.default().with_bull(formation_fib=0.5)
detector.update_config(new_config)  # Resets internal state
```

**Pipeline integration:**

When processing bars with a `ReferenceLayer`, tolerance-based invalidation and completion are applied during processing, not just at response time. This ensures accurate swing counts throughout the replay.

The pipeline order per bar:
1. `detector.process_bar(bar)` — DAG events (formation, structural invalidation, level cross)
2. `ref_layer.update_invalidation_on_bar(swings, bar)` — Tolerance-based invalidation
3. `ref_layer.update_completion_on_bar(swings, bar)` — Completion (2× for small swings)

**Key design principles:**
- **No lookahead** — Algorithm only sees current and past bars
- **Single code path** — All detection uses `process_bar()` in a loop
- **Independent invalidation** — Each swing checks its own defended pivot (no cascade)
- **DAG hierarchy** — Swings can have multiple parents for structural context
- **Multi-TF optimization** — Uses higher-timeframe bars (1h, 4h, 1d) as candidates for O(1) candidate pairs vs O(lookback²)
- **Directional leg creation** — Bull legs are only created in TYPE_2_BULL (HH, HL) and bear legs only in TYPE_2_BEAR (LH, LL). This ensures correct temporal order: origin_index < pivot_index for all legs (#195, #197)
- **Leg terminology** — Origin is where the move started (fixed), Pivot is the defended extreme (extends). Bull leg: origin=LOW, pivot=HIGH. Bear leg: origin=HIGH, pivot=LOW (#197)

**Event types (#408: SWING_* events removed):**
| Event | API Type | When emitted |
|-------|----------|--------------|
| `LegCreatedEvent` | `LEG_CREATED` | New candidate leg is created |
| `LegPrunedEvent` | `LEG_PRUNED` | Leg is removed (reasons: `turn_prune`, `origin_proximity_prune`, `breach_prune`, `extension_prune`) |
| `LegInvalidatedEvent` | `LEG_INVALIDATED` | Leg breaches invalidation threshold (configurable, default 0.382) |

All event types are serialized with their API type string (second column) in API responses. `LegPrunedEvent` includes `reason` and `explanation` fields in the `trigger_explanation`.

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

**Two strategies available** (configured via `DetectionConfig.proximity_prune_strategy`):

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
- `DetectionConfig.origin_range_prune_threshold` (default: 0.0 = disabled)
- `DetectionConfig.origin_time_prune_threshold` (default: 0.0 = disabled)
- `DetectionConfig.proximity_prune_strategy` (default: `'oldest'`)

**Turn pruning (#404):**

Limits the number of sibling legs at each shared pivot. When a new leg forms at origin O, counter-legs with pivot == O are evaluated.

```
max_turns = 10 (default)
At each pivot, keep only the top k legs ranked by counter-trend range.
```

**Counter-trend range scoring:** Each leg tracks `_max_counter_leg_range` — the largest opposite-direction leg that existed at their origin when created. Higher counter-trend range = more structurally significant origin.

**Largest leg exemption:** The largest leg (by range) at each shared pivot is always exempt from pruning. It represents primary structure.

Configuration: `DetectionConfig.max_turns` (default: 10, 0 = disabled)

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
- `DetectionConfig.stale_extension_threshold`: Multiplier for extension prune (default: 3.0)
- `DetectionConfig.engulfed_breach_threshold`: Breach ratio for engulfed deletion (default: 0.236, 1.0 = disabled)

**Note (#345):** Origin breach is detected at 0% (any touch). Use `max_origin_breach is not None` to check if a leg's origin has been breached.

**Benefits:**
- Multi-origin preservation: Keeps the best leg from each structural level
- Fractal compression: Detailed near active zone, sparse further back
- Self-regulating: Tree size stays bounded as older noise is pruned
- Counter-trend references: Invalidated legs remain visible for reference until 3× extension

---

### Reference Layer

**Files:**
- `src/swing_analysis/reference_layer.py` — Core logic
- `src/swing_analysis/reference_config.py` — Configuration

The Reference Layer is a thin filter over DAG's active legs that determines which legs qualify as valid trading references. It applies semantic rules (formation, breach, salience) to structural output from the DAG.

**Design:** DAG tracks structural extremas; Reference Layer applies semantic filtering. Clean separation keeps DAG simple.

#### Primary API: update()

The main entry point processes legs each bar and returns grouped references:

```python
from src.swing_analysis.reference_layer import ReferenceLayer, ReferenceState, ReferenceSwing
from src.swing_analysis.reference_config import ReferenceConfig
from src.swing_analysis.dag.leg_detector import LegDetector

# Initialize with configuration
config = ReferenceConfig.default()
ref_layer = ReferenceLayer(reference_config=config)
detector = LegDetector(...)

# Process each bar
for bar in bars:
    detector.process_bar(bar)
    legs = detector.get_active_legs()

    # Get valid trading references
    state: ReferenceState = ref_layer.update(legs, bar)

    # Access references sorted by salience (highest first)
    for ref in state.references:
        print(f"Bin {ref.bin} {ref.leg.direction} at {ref.location:.2f}")

    # Access groupings (#436: bin-based)
    significant_refs = state.significant  # Bin >= 8 (5× median or larger)
    bin_8_refs = state.by_bin.get(8, [])
    root_refs = state.by_depth.get(0, [])
    bull_refs = state.by_direction['bull']

    # Check market bias
    if state.direction_imbalance == 'bull':
        print("Bull-dominated environment")
```

#### ReferenceConfig

Separate from DetectionConfig — different lifecycle, UI-tunable independently.

```python
from src.swing_analysis.reference_config import ReferenceConfig

# Default configuration
config = ReferenceConfig.default()

# Customize with builder methods (#436: unified weights)
config = ReferenceConfig.default().with_breach_tolerance(
    pivot_breach_tolerance=0.0,             # Bins < 8: 0% (default per north star)
    significant_trade_breach_tolerance=0.15, # Bins >= 8: 15% trade breach
    significant_close_breach_tolerance=0.10, # Bins >= 8: 10% close breach
).with_salience_weights(
    range_weight=0.8,                       # Unified across all bins (#444)
    impulse_weight=0.0,
    recency_weight=0.4,
    depth_weight=0.0,
)
```

**Key ReferenceConfig fields (#436: bin-based):**

| Field | Default | Description |
|-------|---------|-------------|
| `significant_bin_threshold` | 8 | Bins >= this are "significant" (5× median) |
| `min_swings_for_classification` | 50 | Cold start threshold |
| `formation_fib_threshold` | 0.236 | Price-based formation level |
| `pivot_breach_tolerance` | 0.0 | Small bins: pivot breach tolerance (#454) |
| `significant_trade_breach_tolerance` | 0.15 | Significant bins: trade breach (15%) |
| `significant_close_breach_tolerance` | 0.10 | Significant bins: close breach (10%) |
| `completion_threshold` | 2.0 | Location threshold for COMPLETED status (#454) |
| `range_weight` | 0.8 | Unified salience: range weight (#444) |
| `impulse_weight` | 0.0 | Unified salience: impulse weight (#444) |
| `recency_weight` | 0.4 | Unified salience: recency weight (#444) |
| `depth_weight` | 0.0 | Unified salience: depth weight (#444) |
| `recency_decay_bars` | 1000 | Recency half-life: `1/(1 + age/decay)` |
| `depth_decay_factor` | 0.5 | Depth decay: `1/(1 + depth*factor)` |
| `range_counter_weight` | 0.0 | Standalone mode: when > 0, uses range × counter |
| `confluence_tolerance_pct` | 0.001 | Confluence zone clustering tolerance (0.1%) |

#### Output Dataclasses

**ReferenceState** — Complete output for a bar (#436: bin-based, #457: per-pivot top N):
| Field | Type | Description |
|-------|------|-------------|
| `references` | `List[ReferenceSwing]` | Top N per pivot, sorted by salience |
| `active_filtered` | `List[ReferenceSwing]` | Valid refs that didn't make per-pivot top N (#457) |
| `by_bin` | `Dict[int, List]` | Grouped by bin index (0-10) |
| `significant` | `List[ReferenceSwing]` | Bin >= 8 (5× median or larger) |
| `by_depth` | `Dict[int, List]` | Grouped by hierarchy depth |
| `by_direction` | `Dict[str, List]` | Grouped by bull/bear |
| `direction_imbalance` | `Optional[str]` | 'bull'/'bear' if >2× imbalance |

**ReferenceSwing** — A qualified trading reference (#436: bin-based):
| Field | Type | Description |
|-------|------|-------------|
| `leg` | `Leg` | The underlying DAG Leg |
| `bin` | `int` | 0-10 median-normalized bin index |
| `depth` | `int` | Hierarchy depth (0 = root) |
| `location` | `float` | Price position 0-2 (capped) |
| `salience_score` | `float` | Relevance ranking |

#### Bin Classification (#436)

Based on median-normalized range using `RollingBinDistribution`:

| Bin | Median Multiple | Description |
|-----|-----------------|-------------|
| 0-3 | < 1× | Below median range |
| 4-7 | 1-5× | Above median, below significant |
| 8 | 5-10× | Significant (threshold default) |
| 9 | 10-25× | Large |
| 10 | 25×+ | Exceptional |

The frontend displays median multiples (e.g., "2.5×") instead of bin numbers for user clarity.

#### Formation and Breach

**Formation:** Price-based, not age-based. A leg becomes a valid reference when price retraces to the formation threshold (default 23.6%). Formation is tracked per pivot level — if the pivot extends past the price at which formation occurred, formation is nullified and must be re-achieved at the new level (#448).

**Fatal breach conditions:**
1. **Pivot breach**: location < 0 (price past defended pivot)
2. **Completion**: location > 2 (past 2× target)
3. **Origin breach**: Bin-dependent (#436):

| Bin | Trade Breach | Close Breach |
|-----|--------------|--------------|
| < 8 (small) | 0% (default) | 0% |
| ≥ 8 (significant) | 15% | 10% |

#### Reference Observation Mode (#400)

For debugging why legs are filtered, use `get_all_with_status()`:

```python
from src.swing_analysis.reference_layer import (
    ReferenceLayer, FilterReason, FilteredLeg
)

# Get ALL legs with their filter status
statuses: List[FilteredLeg] = ref_layer.get_all_with_status(legs, bar)

for status in statuses:
    if status.reason != FilterReason.VALID:
        print(f"{status.leg.leg_id}: {status.reason.value}")
        print(f"  Bin: {status.bin}, Location: {status.location:.2f}")
        if status.threshold:
            print(f"  Violated threshold: {status.threshold:.2f}")
```

**FilterReason enum values:**
| Value | Meaning |
|-------|---------|
| `VALID` | Passed all filters |
| `COLD_START` | Not enough swings for bin classification |
| `NOT_FORMED` | Price hasn't reached 23.6% formation |
| `PIVOT_BREACHED` | Location < 0 (past defended pivot with tolerance) |
| `COMPLETED` | Location > completion_threshold (default 2×) |
| `ACTIVE_NOT_SALIENT` | Valid ref, but didn't make per-pivot top N (#457) |

**FilteredLeg fields (#436: bin-based):**
| Field | Type | Description |
|-------|------|-------------|
| `leg` | `Leg` | The underlying DAG Leg |
| `reason` | `FilterReason` | Why filtered (or VALID) |
| `bin` | `int` | 0-10 median-normalized bin index |
| `location` | `float` | Price position 0-2 (capped) |
| `threshold` | `Optional[float]` | Violated threshold value |

**API extension:** `/api/reference-state` includes:
- `filtered_legs`: Array of non-valid legs with reasons
- `filter_stats`: `{total_legs, valid_count, pass_rate, by_reason}`

#### Salience Computation (#436)

Ranks references by relevance. Unified weights across all bins:

| Component | Weight |
|-----------|--------|
| Range | 0.4 |
| Impulse | 0.4 |
| Recency | 0.1 |
| Depth | 0.1 |

**Philosophy:** Salience is now unified — all references use the same weight formula. Range×Counter standalone mode available via `range_counter_weight`.

#### Cold Start

Returns empty ReferenceState until `min_swings_for_classification` legs (default 50) have been seen. This ensures meaningful median-based bin classification.

#### Legacy SwingNode API

For backward compatibility, the older SwingNode-based API remains:

```python
from src.swing_analysis.reference_layer import (
    ReferenceLayer,
    ReferenceSwingInfo,
    InvalidationResult,
    CompletionResult,
)
from src.swing_analysis.dag import LegDetector

# Process bars to get legs
detector = LegDetector(config)
for bar in bars:
    detector.process_bar(bar)
legs = detector.state.active_legs

# Apply reference layer filters
ref_layer = ReferenceLayer(config)
reference_swings = ref_layer.get_reference_swings(legs)

# Check invalidation/completion
for info in reference_swings:
    result = ref_layer.check_invalidation(info.swing, bar)
    if result.is_invalidated:
        print(f"{info.swing.swing_id} invalidated: {result.reason}")
```

**ReferenceSwingInfo fields:**
- `swing`: The underlying SwingNode
- `touch_tolerance`: Tolerance for wick violations
- `close_tolerance`: Tolerance for close violations
- `is_reference`: Whether swing passes all filters
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

## Playback Architecture

### Batched Advance

The frontend fetches bars in batches (`FETCH_BATCH_SIZE = 100`) for performance. This creates a temporal gap:

```
Server position: bar 600 (after processing batch)
Render position: bar 515 (frontend iterating through batch)
```

**Invariant:** Any state layer consumed during playback rendering must capture per-bar snapshots.

### Per-Bar State Snapshots

The `per_bar_dag_states` pattern (established in #283) solves this:

```python
# In advance endpoint - capture state AFTER each bar
for idx in range(start_idx, end_idx):
    bar = s.source_bars[idx]
    events = detector.process_bar(bar)

    if request.include_per_bar_dag_states:
        per_bar_dag_states.append(build_dag_state(detector, s.window_offset))
```

Frontend applies the correct snapshot during render:

```typescript
// renderNextBar() - use snapshot matching render position
const dagState = dagStatesBuffer[renderPosition - bufferStartIndex];
setDagState(dagState);
```

### Adding a New State Layer

When adding a state layer that's consumed during playback:

1. **Add request parameter:** `include_per_bar_<layer>_states: bool`
2. **Capture per-bar:** Snapshot state after each `process_bar()`
3. **Return array:** Add `<layer>_states: List[StateSnapshot]` to response
4. **Frontend buffer:** Apply correct snapshot in `renderNextBar()`

**Anti-pattern:** Calling a state endpoint (e.g., `/api/reference/state`) during render and getting current accumulated state rather than historical state. This causes temporal inconsistency where rendered data shows future state.

### Formation Bar Tracking (#451)

Reference Layer tracks when each leg formed (not just that it formed):

```python
# _formed_refs stores (pivot_price, formation_bar_index)
self._formed_refs: Dict[str, Tuple[Decimal, int]] = {}

# Query formation state at a specific bar
def is_formed_at_bar(self, leg_id: str, bar_index: int) -> bool:
    if leg_id not in self._formed_refs:
        return False
    _, formation_bar = self._formed_refs[leg_id]
    return bar_index >= formation_bar
```

This enables correct per-bar formation state during buffered playback, where the server may be at bar 600 but frontend is rendering bar 515.

### View Position Synchronization (#451)

When switching between views (DAG View ↔ Levels at Play), the render position is preserved via `playbackPosition` in session settings:

```typescript
// useSessionSettings.ts
interface SessionSettings {
  dataFile: string | null;
  startDate: string | null;
  playbackPosition: number | null;  // Frontend render position
}

// Each view saves position during playback
updateSessionSettings({ playbackPosition: renderPosition });

// On mount, use saved position instead of server position
const targetPosition = sessionSettings.playbackPosition ?? session.current_bar_index;
```

This prevents jarring jumps where switching views would snap to the server's buffered position rather than the user's viewing position.

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
| `LevelsAtPlayView.tsx` | Reference Layer visualization page (#374, #426) |
| `ChartArea.tsx` | Two stacked lightweight-charts |
| `LegOverlay.tsx` | Leg visualization (includes tree icon hover) |
| `ReferenceLegOverlay.tsx` | Reference visualization with labels, viewport density limiting, hover fade effect (#377-#379, #432, #445) |
| `HierarchyModeOverlay.tsx` | Hierarchy exploration mode (exit button, connection lines, status) |
| `PlaybackControls.tsx` | Play/pause/step transport |
| `DAGStatePanel.tsx` | DAG internal state display (legs, origins, pivots, expandable lists, attachments) |
| `ReferenceSidebar.tsx` | Collapsible sidebar with Config/Filters/Stats panels for Levels at Play view (#424, #426, #445) |
| `LevelsAtPlayBottomPanel.tsx` | Column-major grid of all references in bottom panel with pagination (#445) |
| `ReferenceTelemetryPanel.tsx` | Bottom panel with LEVELS AT PLAY + EVENTS columns (#445) |
| `ReferenceConfigPanel.tsx` | Salience weight sliders + Apply button (#425) |
| `Sidebar.tsx` | Event filters, feedback input, attachment display |
| `useForwardPlayback.ts` | Forward-only playback (step back via backend API) |
| `useHierarchyMode.ts` | Hierarchy exploration state management (#250) |
| `useReferenceState.ts` | Reference Layer state with fade-out transitions (#381) |
| `useChartPreferences.ts` | Settings persistence to localStorage (incl. sidebar state #426) |
| `useDAGViewState.ts` | DAG view consolidated state management |

**Frontend Architecture Notes:**
- Two view modes available via Header dropdown (#374):
  - **DAG View**: Full DAG exploration with leg overlays, hierarchy mode, detection config
  - **Levels at Play View**: Reference Layer visualization with scale labels, direction colors, location indicators
- App.tsx routes between views using `ViewMode` state
- `useForwardPlayback` has two bar advance mechanisms:
  - `renderNextBar`: Buffer-based for smooth continuous playback
  - `advanceBar`: Direct API call for manual stepping (step forward, jump to event)
- **Overlay Position Filtering (#449)**: Both `LegOverlay` and `ReferenceLegOverlay` filter legs by `pivot_index <= currentPosition` to prevent rendering legs before their candles exist during playback

**Settings Persistence (#347, #358, #425, #426):**

`useChartPreferences` persists user settings to localStorage, including:
- Chart aggregation scales, zoom levels, maximized state
- Speed multiplier and aggregation
- Linger enabled/event states
- Detection config (full `DetectionConfig` object)
- Reference config (salience weights + formation threshold) (#425)
- Levels at Play sidebar open/closed state (#426)

Schema evolution is handled via `mergeDetectionConfig()` and `mergeReferenceConfig()`, which deep-merge saved config with defaults to ensure new fields have defaults when loading older saved configs.

**Server sync on startup (#358):**

When the app loads with saved detection config in localStorage, it's automatically pushed to the server via `updateDetectionConfig()`. This ensures:
- User preferences override server defaults from the first bar
- No manual "Apply" needed after page refresh
- Server and client state stay synchronized

Implementation in `DAGView.tsx`:
- `setDetectionConfig()` — Updates state AND saves to localStorage (used after Apply)
- `setDetectionConfigFromServer()` — Updates state only (used during server fetch to avoid overwriting saved preferences)

**Backward Navigation:**

The `useForwardPlayback` hook supports stepping backward via backend API:

```typescript
// Hook return values
canStepBack: boolean;  // true when currentPosition > 0
```

**Implementation details:**
- `stepBack()` calls `POST /api/dag/reverse` to replay from bar 0 to current-1
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
python -m pytest tests/test_detector_state.py -v

# Single test class
python -m pytest tests/test_detector_state.py::TestStateRestore -v

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
| `test_discretizer.py` | Event generation, side-channels |
| `test_reference_frame.py` | ReferenceFrame coordinate system |
| `test_detection_config.py` | DetectionConfig dataclass |
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
python -m src.replay_server.main --data test.csv --port 8001
```

### Replay View API

The replay view backend (`src/replay_server/`) uses LegDetector for incremental swing detection with Reference layer filtering:

```python
# Lazy Initialization (#412)
# Most endpoints auto-initialize detector if not present.
# Frontend no longer needs to call /init explicitly.

# Init: POST /api/dag/init (#410)
# Explicitly initializes detector with empty state.
# Returns empty response (no bars processed).
# Note: Usually not needed - /advance, /state, /reverse auto-init.

# Reset: POST /api/dag/reset (#412)
# Clears all state and creates a fresh detector.
# Use when you want to restart detection from bar 0.
# Returns empty response.

# Advance: POST /api/dag/advance
# {current_bar_index, advance_by}
# Processes bars using detector.process_bar() and returns events
# Auto-initializes detector if not present (#412)

# Reverse: POST /api/dag/reverse
# {current_bar_index, include_aggregated_bars?, include_dag_state?}
# Resets detector and replays from bar 0 to current_bar_index - 1
# Returns same response format as /advance (ReplayAdvanceResponse)
# Used for backward navigation in playback
# Auto-initializes detector if not present (#412)

# DAG State: GET /api/dag/state
# Returns internal leg-level state for DAG visualization.
# Auto-initializes detector if not present (#412).
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

# Lifecycle Events: GET /api/dag/events (#409)
# Returns all cached lifecycle events from the current session.
# Used to restore frontend state when switching views (DAG View -> Reference View -> back).
# - events: Array of LifecycleEvent objects with leg_id, direction, event_type,
#   bar_index, csv_index, timestamp, explanation

# Detection Config: GET /api/dag/config (#410)
# Returns current detection configuration:
# - stale_extension_threshold: Extension multiplier for stale pruning
# - origin_range_threshold: Range similarity threshold for origin-proximity pruning (#294)
# - origin_time_threshold: Time proximity threshold for origin-proximity pruning (#294)
# - max_turns: Maximum turns per pivot (#404)
# - engulfed_breach_threshold: Symmetric engulfed threshold (#404)

# Detection Config Update: PUT /api/dag/config (#410)
# Updates detection config (applies to future bars only):
# Request body (all fields optional):
# {
#   "stale_extension_threshold": 3.0,
#   "origin_range_threshold": 0.05,
#   "origin_time_threshold": 0.10,
#   "max_turns": 3,
#   "engulfed_breach_threshold": 0.20
# }
# Returns updated configuration

# Reference State: GET /api/reference/state?bar_index=NNN (#410, #436)
# Returns Reference Layer output for Levels at Play view (#374-#382):
# - references: All valid ReferenceSwings, sorted by salience (highest first)
#   - leg_id, bin (0-10), median_multiple (e.g. 2.5), depth, location (0-2), salience_score
#   - direction, origin_price, origin_index, pivot_price, pivot_index
# - by_bin: References grouped by bin index {0: [], 1: [], ..., 10: []}
# - significant: References with bin >= 8 (5× median or larger)
# - by_depth: References grouped by hierarchy depth {0: [], 1: [], ...}
# - by_direction: References grouped by direction {bull: [], bear: []}
# - direction_imbalance: 'bull' | 'bear' | null (>2x ratio)
# - is_warming_up: True if in cold start (insufficient swings for bin classification)
# - warmup_progress: [current_count, required_count] (e.g., [35, 50])
# - median: Current rolling median for context
# - tracked_leg_ids: List of leg IDs tracked for level crossing (sticky legs)
# - crossing_events: Level crossings detected this bar (Issue #416)
#   LevelCrossEvent: {leg_id, direction, level_crossed, cross_direction, bar_index, timestamp}

# Fib Levels: GET /api/reference/levels?bar_index=NNN (#388, #436)
# Returns all fib levels from valid references for hover preview and sticky display:
# - levels_by_ratio: Dict keyed by ratio string ("0", "0.382", "0.5", etc.)
#   - Each ratio maps to list of FibLevel: {price, ratio, leg_id, bin, direction}
# Used for computing horizontal level lines on chart

# Track Leg: POST /api/reference/track/{leg_id} (#388, #416)
# Add a leg to level crossing tracking (makes its fib levels "sticky")
# Max 10 legs can be tracked at once for performance reasons
# Returns: {success: bool, leg_id: string, tracked_count: int, error: string|null}

# Untrack Leg: DELETE /api/reference/track/{leg_id} (#388, #416)
# Remove a leg from level crossing tracking
# Returns: {success: bool, leg_id: string, tracked_count: int, error: null}

# Get Crossing Events: GET /api/reference/crossings (#416)
# Get pending level crossing events (cleared after retrieval)
# Returns: {events: LevelCrossEvent[], tracked_count: int}
# LevelCrossEvent: {leg_id, direction, level_crossed, cross_direction, bar_index, timestamp}

# Get Reference Config: GET /api/reference/config (#423, #436, #454)
# Returns current salience weights and formation threshold
# Returns: {range_weight, impulse_weight, recency_weight, depth_weight,
#           range_counter_weight, top_n, formation_fib_threshold,
#           pivot_breach_tolerance, completion_threshold, significant_bin_threshold}

# Update Reference Config: POST /api/reference/config (#423, #436)
# Accepts partial updates, returns full updated config
# Request: any subset of config fields (e.g., {range_weight: 0.6})
# Response: full ReferenceConfig with all values
```

**Reference Layer Integration:**

The API pipeline applies Reference layer filtering to DAG output before returning swings:

```
┌─────────────────────────────────────────────────────────────────┐
│                     API Request Flow                             │
│                                                                  │
│  1. init() ─────────────► LegDetector                           │
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
- `src/replay_server/routers/` - API endpoints (modularized #398, consolidated #410)
  - `dag.py` - Init, advance, reverse, state, lineage, config, followed-legs endpoints
  - `reference.py` - Reference Layer state and levels
  - `feedback.py` - Playback feedback endpoint
  - `cache.py` - Shared replay cache state
  - `helpers/` - Conversion and builder functions
- `src/swing_analysis/reference_layer.py` - Filtering logic
- `src/swing_analysis/dag/` - DAG algorithm (modularized)
  - `leg_detector.py` - LegDetector main class
  - `leg_pruner.py` - Pruning algorithms

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
  state: 'playing' | 'paused';
  csv_index: number;           // Authoritative CSV row index
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

**Backend storage** (`src/replay_server/storage.py`):
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
| Bar aggregation | <100ms | 10K bars |
| File metrics | <100ms | Any file size |
