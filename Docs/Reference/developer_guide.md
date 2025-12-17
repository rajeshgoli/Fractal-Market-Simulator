# Developer Guide

A comprehensive reference for developers working on the Fractal Market Simulator codebase.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Core Concepts](#core-concepts)
4. [Data Flow](#data-flow)
5. [Module Reference](#module-reference)
   - [Data Layer](#data-layer)
   - [Swing Analysis](#swing-analysis)
   - [Ground Truth Annotator](#ground-truth-annotator)
6. [Key Data Structures](#key-data-structures)
7. [Extending the System](#extending-the-system)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Environment Setup

```bash
# Clone and enter the repository
cd fractal-market-simulator

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m pytest tests/ -v
```

### Running the Application

```bash
# Ground Truth Annotator (two-click swing annotation)
python -m src.ground_truth_annotator.main --data test_data/test.csv --scale S

# Cascade mode (XL → L → M → S workflow)
python -m src.ground_truth_annotator.main --data test_data/test.csv --cascade

# Random window selection
python -m src.ground_truth_annotator.main --data test_data/test.csv --cascade --offset random
```

### Git Conventions

**Do NOT commit:**
- `venv/` - Virtual environment
- `__pycache__/` - Python bytecode
- `.DS_Store` - macOS metadata
- Large data files

---

## Architecture Overview

The system follows a pipeline architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                     │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ OHLC Loader  │────▶│ Bar Objects  │────▶│ Historical Loader    │    │
│  │ (CSV/custom) │     │  (Decimal)   │     │ (date range filter)  │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        SWING ANALYSIS                                    │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │   Scale      │────▶│    Bar       │────▶│   Swing Detector     │    │
│  │ Calibrator   │     │ Aggregator   │     │   (O(N log N))       │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
│         │                    │                       │                  │
│         ▼                    ▼                       ▼                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ Boundaries   │     │ Multi-TF     │     │ Comparison Analyzer  │    │
│  │ (S,M,L,XL)   │     │ OHLC Cache   │     │   (FN/FP detection)  │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    GROUND TRUTH ANNOTATOR                                │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │  FastAPI     │◀───▶│  Cascade     │◀───▶│   Review Controller  │    │
│  │  (REST API)  │     │ Controller   │     │  (feedback phases)   │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
│         │                    │                       │                  │
│         ▼                    ▼                       ▼                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ Web-based UI │     │ XL→L→M→S     │     │   JSON/CSV Export    │    │
│  │ (Two-click)  │     │ Workflow     │     │   Feedback Storage   │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
fractal-market-simulator/
├── src/
│   ├── data/
│   │   └── ohlc_loader.py          # CSV data loading
│   ├── swing_analysis/
│   │   ├── bull_reference_detector.py   # Bar, BullReferenceSwing, BearReferenceSwing dataclasses
│   │   ├── level_calculator.py          # Fibonacci level computation
│   │   ├── scale_calibrator.py          # Auto-calibrate scale boundaries
│   │   ├── bar_aggregator.py            # Multi-timeframe bar aggregation
│   │   ├── swing_state_manager.py       # Active swing tracking
│   │   ├── event_detector.py            # Structural event detection
│   │   └── swing_detector.py            # O(N log N) vectorized swing detection
│   ├── discretization/
│   │   ├── schema.py               # Event schema and validation
│   │   └── __init__.py
│   └── ground_truth_annotator/
│       ├── main.py                 # CLI entry point
│       ├── api.py                  # FastAPI endpoints
│       ├── models.py               # SwingAnnotation, AnnotationSession
│       ├── storage.py              # JSON-backed persistence
│       ├── csv_utils.py            # CSV field escaping utilities
│       ├── comparison_analyzer.py  # Compare annotations vs system detection
│       ├── cascade_controller.py   # XL→L→M→S scale progression
│       ├── review_controller.py    # Review Mode workflow
│       └── static/index.html       # Two-click annotation UI
├── scripts/                        # Development utilities
│   ├── validate_discretizer.py    # Discretizer validation on sample data
│   └── compare_discretizers.py    # Sanity comparison vs old event_detector
├── tests/                          # Test suite (550+ tests)
├── Docs/                           # Documentation
└── test_data/                      # Sample data files
    └── discretization_validation/ # Validation output logs
```

---

## Core Concepts

### Multi-Scale Analysis

The system operates simultaneously across four scales representing different swing magnitudes:

| Scale | Description | Typical Size Range | Base Aggregation |
|-------|-------------|-------------------|------------------|
| **S** (Small) | Minor retracements | 0-10 points | 1-minute |
| **M** (Medium) | Intermediate swings | 10-25 points | 5-minute |
| **L** (Large) | Major structural moves | 25-50 points | 15-minute |
| **XL** (Extra Large) | Primary trend swings | 50+ points | 60-minute |

Scale boundaries are **auto-calibrated** from historical data using quartile analysis in `ScaleCalibrator`.

### Fibonacci Levels

All structural analysis uses Fibonacci ratios applied to reference swings:

```
Level       Ratio    Meaning
──────────────────────────────────────────
0           0.00     Swing low (bullish) / high (bearish)
0.382       0.382    Shallow retracement / minimum encroachment
0.5         0.500    50% retracement
0.618       0.618    Deep retracement
1.0         1.000    Swing high (bullish) / low (bearish)
1.382       1.382    First extension
1.5         1.500    Mid extension
1.618       1.618    Golden extension
2.0         2.000    Full extension (completion zone)
```

### Reference Swings

A **reference swing** is a validated high-low pair used to calculate Fibonacci levels:

- **Bull Reference**: High BEFORE Low (downswing completed, now bullish)
- **Bear Reference**: Low BEFORE High (upswing completed, now bearish)

### Swing Validation Rules (Scale-Dependent)

Validation operates at the **swing's aggregation level** (not raw input bars). For a bull swing with `H` (high), `L` (low), and `Δ = H - L`:

#### S/M Scales (Strict)

A bull swing remains valid if ALL conditions hold:
1. **Structure**: Price made H then L
2. **Location**: Current price is between H and L
3. **Minimum encroachment**: After L, price retraced to at least `L + 0.382 × Δ`
4. **No violation**: Price never trades below L

#### L/XL Scales (Soft)

A bull swing remains valid if ALL conditions hold:
1. **Structure**: Price made H then L
2. **Location**: Current price is between H and L
3. **Minimum encroachment**: After L, price retraced to at least `L + 0.382 × Δ`
4. **No deep trade-through**: Price never trades below `L - 0.15 × Δ`
5. **No close below soft threshold**: No CLOSE below `L - 0.10 × Δ` (at aggregated timeframe)

Bear swings use symmetric rules (L then H, inequalities flipped).

### Structural Events

The system detects three types of structural events:

| Event Type | Description | Trigger |
|------------|-------------|---------|
| **LEVEL_CROSS** | Price crosses a Fibonacci level | Bar close above/below level |
| **COMPLETION** | Swing reaches target (2.0 extension) | Close above 2.0 level |
| **INVALIDATION** | Swing breaks structure | Scale-dependent (see validation rules above) |

Events have severity: **MAJOR** (completions, invalidations) or **MINOR** (level crosses).

---

## Data Flow

### Initialization Flow

```
1. Load OHLC Data
   └─▶ OHLCLoader.load_data(filepath)
       └─▶ Returns List[Bar] with Decimal prices

2. Calibrate Scales
   └─▶ ScaleCalibrator.calibrate(bars, instrument)
       └─▶ Detects all swings in historical data
       └─▶ Computes quartile boundaries
       └─▶ Returns ScaleConfig with boundaries + aggregations

3. Pre-compute Aggregations
   └─▶ BarAggregator(source_bars, scale_config)
       └─▶ Builds OHLC for all timeframes: 1m, 5m, 15m, 30m, 60m, 240m
       └─▶ Natural boundary alignment (5m bars start at :00, :05, :10...)

4. Initialize State Manager
   └─▶ SwingStateManager(scale_config, bar_aggregator)
       └─▶ Creates empty state for each scale
```

### Per-Bar Processing Flow

```
For each new bar at index N:

1. Update Swing State
   └─▶ swing_state_manager.update_swings(bar_idx)
       │
       ├─▶ For each scale (S, M, L, XL):
       │   └─▶ Get aggregated bar at this source time
       │   └─▶ Detect new reference swings
       │   └─▶ Update active swing list
       │   └─▶ Classify by size into correct scale
       │
       └─▶ Returns List[ActiveSwing]

2. Detect Events
   └─▶ event_detector.detect_events(bar, active_swings)
       │
       ├─▶ For each active swing:
       │   └─▶ Check level crossings
       │   └─▶ Check completions (2.0 break)
       │   └─▶ Check invalidations (scale-dependent thresholds)
       │
       └─▶ Returns List[StructuralEvent]

3. Compare Against Ground Truth
   └─▶ comparison_analyzer.compare_session(session, bars, scales)
       └─▶ Identifies false negatives (user marked, system missed)
       └─▶ Identifies false positives (system found, user didn't mark)
       └─▶ Calculates match rate
```

---

## Module Reference

### Data Layer

#### `src/data/ohlc_loader.py`

**Purpose**: Load OHLC data from CSV files with multiple format support.

**Key Class**: `OHLCLoader`

```python
from src.data.ohlc_loader import OHLCLoader

# Load data (auto-detects format)
loader = OHLCLoader()
bars = loader.load_data("market_data.csv")

# Returns List[Bar] - each Bar has:
# - index: int
# - timestamp: int (Unix)
# - open, high, low, close: Decimal
```

**Supported Formats**:
- TradingView CSV: `time,open,high,low,close,volume`
- Custom semicolon: `date;time;open;high;low;close`

**Features**:
- Auto-format detection via header inspection
- Gap detection between bars
- Data validation (OHLC consistency)

---

### Swing Analysis

#### `src/swing_analysis/bull_reference_detector.py`

**Purpose**: Core dataclass definitions for bars and reference swings.

**Key Dataclasses**: `Bar`, `BullReferenceSwing`, `BearReferenceSwing`, `DetectorConfig`

```python
@dataclass
class Bar:
    index: int
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
```

The `BullReferenceSwing` and `BearReferenceSwing` dataclasses include computed Fibonacci levels and methods for retracement calculations.

#### `src/swing_analysis/level_calculator.py`

**Purpose**: Compute Fibonacci levels from swing high/low.

```python
from src.swing_analysis.level_calculator import calculate_levels

levels = calculate_levels(
    high=Decimal("5100.00"),
    low=Decimal("5000.00"),
    direction="bullish",
    quantization=Decimal("0.25")  # ES tick size
)
# Returns List[Level] with price at each Fibonacci ratio
```

**Quantization**: Prices are rounded to market-appropriate tick sizes (e.g., 0.25 for ES futures).

#### `src/swing_analysis/scale_calibrator.py`

**Purpose**: Auto-calibrate scale boundaries from historical data.

**Key Class**: `ScaleCalibrator`

```python
calibrator = ScaleCalibrator()
scale_config = calibrator.calibrate(bars, instrument="ES")

# scale_config contains:
# - boundaries: {'S': (0, 10.5), 'M': (10.5, 25.0), ...}
# - aggregations: {'S': 1, 'M': 5, 'L': 15, 'XL': 60}
```

**Algorithm**:
1. Detect all swings in historical data
2. Calculate size distribution (quartiles)
3. Map quartile boundaries to S/M/L/XL scales
4. Assign aggregation timeframes based on scale

**Performance**: <50ms for ~7,000 bars

#### `src/swing_analysis/bar_aggregator.py`

**Purpose**: Pre-compute aggregated OHLC bars for all timeframes.

**Key Class**: `BarAggregator`

```python
aggregator = BarAggregator(source_bars, scale_config)

# Get 5-minute aggregated bars
bars_5m = aggregator.get_bars(timeframe=5)

# Get aggregated bar at specific source time
bar = aggregator.get_bar_at_source_time(timeframe=5, source_bar_idx=100)
```

**Features**:
- Natural boundary alignment (5m bars start at :00, :05, :10...)
- O(1) bar retrieval after O(N) pre-computation
- Source-to-aggregated index mapping

**Supported Timeframes**: 1, 5, 15, 30, 60, 240 minutes

#### `src/swing_analysis/swing_state_manager.py`

**Purpose**: Track active swings across all scales with event-driven state transitions.

**Key Class**: `SwingStateManager`

```python
manager = SwingStateManager(scale_config, bar_aggregator)

# Process each bar
active_swings = manager.update_swings(bar_idx)

# Returns List[ActiveSwing] with:
# - swing_id: str (unique identifier)
# - scale: str (S/M/L/XL)
# - is_bull: bool
# - high_price, low_price: float
# - levels: Dict[str, float] (Fibonacci levels)
```

**State Transitions**:
- New swing detected -> Added to active list
- Swing invalidated -> Removed from active list
- Swing completed -> May be replaced by new swing

**Performance**: ~28ms per bar (target: <500ms)

#### `src/swing_analysis/event_detector.py`

**Purpose**: Detect structural events from price action.

**Key Class**: `EventDetector`

```python
detector = EventDetector()
events = detector.detect_events(current_bar, active_swings)

# Returns List[StructuralEvent] with:
# - event_type: EventType (LEVEL_CROSS, COMPLETION, INVALIDATION)
# - severity: EventSeverity (MAJOR, MINOR)
# - level_name: str (e.g., "0.618")
# - level_price: float
# - swing_id, scale: str
```

**Event Types**:

| Type | Trigger | Severity |
|------|---------|----------|
| `LEVEL_CROSS` | Bar closes above/below a level | MINOR |
| `COMPLETION` | Bar closes above 2.0 extension | MAJOR |
| `INVALIDATION` | Scale-dependent threshold breach (see Core Concepts) | MAJOR |

#### `src/swing_analysis/swing_detector.py`

**Purpose**: Legacy swing detection using pandas. Used for batch analysis and historical swing identification.

**Key Function**: `detect_swings(df, lookback=5, filter_redundant=True, protection_tolerance=0.1, min_candle_ratio=None, min_range_pct=None, min_prominence=None, adjust_extrema=True, quota=None)`

Uses `SparseTable` for O(1) range minimum/maximum queries to validate swing structure efficiently.

**Best Extrema Adjustment** (added #65): Adjusts swing endpoints to the best extrema in vicinity:
- `adjust_extrema`: When True (default), adjusts both high and low endpoints to the best values within ±lookback bars
- For swing highs: finds highest high within the search window
- For swing lows: finds lowest low within the search window
- Recalculates size and level references after adjustment
- Runs protection validation on adjusted endpoints
- Set `adjust_extrema=False` to preserve original endpoint detection behavior

**Protection Validation** (added #54): Filters references where swing points are violated:
- **Pre-formation**: High violated before low forms (bull) / Low violated before high forms (bear)
- **Post-formation**: Swing point violated beyond tolerance threshold after formation
- Set `protection_tolerance=None` to disable

**Size Filter** (added #62): Filters swings that are too small relative to context:
- `min_candle_ratio`: Minimum swing size as multiple of median candle height (e.g., 5.0 = 5x median)
- `min_range_pct`: Minimum swing size as percentage of window price range (e.g., 2.0 = 2%)
- **OR logic**: Swing kept if it passes **either** threshold
- **High volatility exception**: 1-2 bar swings kept if ≥3x median candle (prevents filtering significant short-duration moves)
- Set both to `None` (default) to disable

**Prominence Filter** (added #63): Filters swings that don't "stand out" from surrounding points:
- `min_prominence`: Minimum prominence as multiple of median candle height (e.g., 1.0 = 1x median)
- **Prominence definition**: Gap between the extremum and second-best value within the lookback window
- For bull references: checks swing low prominence (how much lower than nearest competing low)
- For bear references: checks swing high prominence (how much higher than nearest competing high)
- Addresses "subsumed" false positives where detector finds locally-optimal extrema that blend with neighbors
- Set to `None` (default) to disable

**Quota Filter** (added #66): Ranks swings by combined score and limits output:
- `quota`: Maximum number of swings to return per direction (bull/bear)
- **Combined score formula**: `0.6 × size_rank + 0.4 × impulse_rank` (lower is better)
- **Impulse calculation**: `size / span` - measures how quickly the swing formed
- **Output fields added**: `impulse`, `size_rank`, `impulse_rank`, `combined_score`
- **Scale-specific quotas**: Recommended values - XL=4, L=6, M=10, S=15
- Set to `None` (default) to disable

#### Filter Pipeline Reference

The `detect_swings()` function applies filters in a specific order. Understanding this pipeline is essential for adding new filters or debugging detection behavior.

**Pipeline Steps:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. SWING DETECTION                                                   │
│    _detect_swing_points_vectorized()                                │
│    - O(N) vectorized detection using rolling windows                │
│    - Identifies swing highs (local maxima) and lows (local minima)  │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. PAIRING & STRUCTURAL VALIDATION                                   │
│    - Match swing highs with swing lows to form reference candidates │
│    - Bull: High BEFORE Low (downswing)                              │
│    - Bear: Low BEFORE High (upswing)                                │
│    - Uses SparseTable for O(1) range min/max queries                │
│    - Validates: geometric validity, price range, structure          │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. BEST EXTREMA ADJUSTMENT (adjust_extrema)                          │
│    _adjust_to_best_extrema()                                        │
│    - Adjusts swing endpoints to best extrema within ±lookback       │
│    - Finds highest high / lowest low in search window               │
│    - Recalculates size and level references                         │
│    - Set adjust_extrema=False to disable                            │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. PROTECTION VALIDATION (protection_tolerance)                      │
│    _apply_protection_filter()                                       │
│    - Pre-formation: Was swing point violated before pair formed?    │
│    - Post-formation: Was swing point violated after formation?      │
│    - Runs on adjusted endpoints when adjust_extrema=True            │
│    - Set protection_tolerance=None to disable                       │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. SIZE FILTER (min_candle_ratio, min_range_pct)                    │
│    _apply_size_filter()                                             │
│    - Filters swings too small relative to context                   │
│    - OR logic: passes if either threshold met                       │
│    - High volatility exception for 1-2 bar swings                   │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. PROMINENCE FILTER (min_prominence)          ← INSERT NEW FILTERS │
│    _apply_prominence_filter()                                       │
│    - Filters swings that don't "stand out" from neighbors           │
│    - Checks gap between extremum and second-best in window          │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 7. REDUNDANCY FILTER (filter_redundant)                             │
│    filter_swings()                                                  │
│    - Removes structurally redundant swings using Fibonacci bands    │
│    - Keeps largest swing when multiple occupy same bands            │
│    - Tiered processing: anchor → filter → next tier                 │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 8. QUOTA FILTER (quota)                                             │
│    _apply_quota()                                                   │
│    - Ranks swings by combined score (0.6×size + 0.4×impulse)        │
│    - Returns top N swings by combined score                         │
│    - Adds impulse, size_rank, impulse_rank, combined_score fields   │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 9. RANKING                                                          │
│    - Sort by combined_score (if quota) or size descending           │
│    - Assign rank 1, 2, 3... to each reference                       │
└─────────────────────────────────────────────────────────────────────┘
```

**Adding a New Filter:**

1. **Create helper function** following naming convention:
   ```python
   def _apply_<name>_filter(references: List[Dict[str, Any]], ...) -> List[Dict[str, Any]]:
       """Filter description."""
       if <parameter> is None:
           return references  # Disabled by default

       filtered = []
       for ref in references:
           if <condition>:
               filtered.append(ref)
       return filtered
   ```

2. **Add parameter** to `detect_swings()` signature with `None` default:
   ```python
   def detect_swings(df, ..., new_filter_param: Optional[float] = None) -> Dict[str, Any]:
   ```

3. **Insert filter call** between steps 4-6 (after size, before redundancy):
   ```python
   # 5. Apply New Filter (after size, before redundancy)
   if new_filter_param is not None:
       bull_references = _apply_new_filter(bull_references, ..., new_filter_param)
       bear_references = _apply_new_filter(bear_references, ..., new_filter_param)
   ```

4. **Add tests** following `TestProminenceFilter` or `TestSizeFilter` patterns in `tests/test_swing_detector.py`

**Key Internal Functions:**

| Function | Purpose |
|----------|---------|
| `_build_suffix_min()` / `_build_suffix_max()` | O(1) suffix min/max queries for protection validation |
| `_range_min()` / `_range_max()` | Range min/max queries using numpy slicing |
| `filter_swings()` | Fibonacci band redundancy filtering |
| `get_level_band()` | Determine which Fib band a price falls into |

**ReferenceSwing Dataclass:**

A typed dataclass for representing detected reference swings:

```python
@dataclass
class ReferenceSwing:
    # Required fields
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    direction: Literal["bull", "bear"]

    # Level calculations
    level_0382: float = 0.0
    level_2x: float = 0.0

    # Ranking (computed during filtering)
    rank: int = 0
    impulse: float = 0.0
    size_rank: Optional[int] = None
    impulse_rank: Optional[int] = None
    combined_score: Optional[float] = None

    # Structural properties
    structurally_separated: bool = False
    containing_swing_id: Optional[str] = None
    fib_confluence_score: float = 0.0

    @property
    def span(self) -> int:
        """Number of bars in the swing."""
        return abs(self.high_bar_index - self.low_bar_index) + 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
```

Note: Currently `detect_swings()` returns dictionaries. The dataclass is available for future migration to typed swing objects.

#### `src/swing_analysis/reference_frame.py`

**Purpose**: Oriented coordinate system for bull/bear swings, providing unified ratio calculations.

**Key Class**: `ReferenceFrame`

```python
from src.swing_analysis.reference_frame import ReferenceFrame
from decimal import Decimal

# Create directly
bull_frame = ReferenceFrame(
    anchor0=Decimal("5000"),  # Defended pivot (low for bull)
    anchor1=Decimal("5100"),  # Origin extremum (high for bull)
    direction="BULL"
)

# Or create from a ReferenceSwing
frame = ReferenceFrame.from_swing(swing)

# Convert price to ratio
ratio = frame.ratio(Decimal("5050"))  # Returns 0.5

# Convert ratio to price
price = frame.price(Decimal("0.618"))  # Returns 5061.8
```

**Ratio Interpretation**:

| Ratio | Meaning |
|-------|---------|
| 0 | Defended pivot (stop level) |
| 0.382 | Shallow retracement |
| 0.5 | Mid retracement |
| 0.618 | Golden retracement |
| 1 | Origin extremum |
| 2 | Completion target (2x extension) |
| < 0 | Stop-run territory (invalidation) |

**Key Properties**:

- `range`: Signed swing range (positive for bull, negative for bear)
- `ratio(price)`: Convert absolute price to ratio
- `price(ratio)`: Convert ratio to absolute price
- `from_swing(swing)`: Factory method to create from `ReferenceSwing`

**Design Note**: The frame normalizes direction-specific logic so that ratio 0 is always the defended pivot and ratio 1 is always the origin, regardless of bull/bear direction.

---

### Discretization

#### `src/discretization/schema.py`

**Purpose**: Defines the canonical event schema for discretization output - converting continuous OHLC + detected swings into a log of structural events.

**Design Principle**: "Log everything; filter later. Don't embed assumptions about what matters into the discretizer."

**Key Dataclasses**:

```python
# Configuration (for corpus comparability)
@dataclass
class DiscretizationConfig:
    level_set: List[float]                    # Fib levels to track
    level_set_version: str                    # e.g., "v1.0"
    crossing_semantics: Literal["close_cross", "open_close_cross", "wick_touch"]
    crossing_tolerance_pct: float             # Tolerance for level crossing
    invalidation_thresholds: Dict[str, float] # Per-scale thresholds
    swing_detector_version: str
    discretizer_version: str

# Core event
@dataclass
class DiscretizationEvent:
    bar: int                                  # Source bar index
    timestamp: str                            # ISO 8601
    swing_id: str                             # Reference to SwingEntry
    event_type: EventType                     # LEVEL_CROSS, COMPLETION, etc.
    data: Dict[str, Any]                      # Event-specific fields
    effort: Optional[EffortAnnotation]        # Wyckoff-style effort
    shock: Optional[ShockAnnotation]          # Tail/impulsive behavior
    parent_context: Optional[ParentContext]   # Cross-scale state

# Complete log
@dataclass
class DiscretizationLog:
    meta: DiscretizationMeta                  # Provenance + config
    swings: List[SwingEntry]                  # Registered swings
    events: List[DiscretizationEvent]         # Ordered event list
```

**Event Types**:

| Event | Meaning | Required Data Fields |
|-------|---------|---------------------|
| `LEVEL_CROSS` | Price crossed a Fib level | from_ratio, to_ratio, level_crossed, direction |
| `LEVEL_TEST` | Price approached but didn't cross | level, result (REJECT/WICK_THROUGH) |
| `COMPLETION` | Ratio crossed 2.0 | completion_ratio |
| `INVALIDATION` | Ratio crossed below threshold | invalidation_ratio, threshold |
| `SWING_FORMED` | New swing detected | swing_id, scale, direction |
| `SWING_TERMINATED` | Swing ended | termination_type (COMPLETED/INVALIDATED) |

**Side-Channels**:

| Annotation | Purpose | Fields |
|------------|---------|--------|
| `EffortAnnotation` | Wyckoff effort vs result | dwell_bars, test_count, max_probe_r |
| `ShockAnnotation` | Tail/impulsive behavior | levels_jumped, range_multiple, gap_multiple, is_gap |
| `ParentContext` | Cross-scale state snapshot | scale, swing_id, band, direction, ratio |

**Validation**:

```python
from src.discretization import validate_log, DiscretizationLog

log = DiscretizationLog.from_dict(data)
errors = validate_log(log)
if errors:
    print(f"Validation failed: {errors}")
```

The `validate_log()` function checks:
- All event swing_ids reference existing swings
- Events are ordered by bar index
- Required config fields are present
- Event data matches event_type requirements

#### `src/discretization/discretizer.py`

**Purpose**: Batch processor that converts OHLC + detected swings into structural event log.

**Design Principles**:
- Batch-only (no streaming state between calls)
- Per-scale independence (no cross-scale coupling in core logic)
- Config-driven levels and semantics (corpus comparability)
- No lookahead (uses only data up to current bar)

**Key Classes**:

```python
from src.discretization import Discretizer, DiscretizerConfig

# Create with default config
discretizer = Discretizer()

# Or with custom config
config = DiscretizerConfig(
    level_set=[0.0, 0.382, 0.5, 0.618, 1.0, 2.0],
    crossing_semantics="close_cross",
    crossing_tolerance_pct=0.001,
    invalidation_thresholds={"S": -0.10, "M": -0.10, "L": -0.15, "XL": -0.15},
    rolling_window_sizes={"S": 20, "M": 50, "L": 100, "XL": 200},
)
discretizer = Discretizer(config)

# Process OHLC and swings
log = discretizer.discretize(
    ohlc=ohlc_df,                    # DataFrame with timestamp, open, high, low, close
    swings={"XL": [...], "M": [...]}, # Dict[scale, List[ReferenceSwing]]
    instrument="ES",
    source_resolution="1m",
)

# Access results
for event in log.events:
    print(f"Bar {event.bar}: {event.event_type.value}")
```

**DiscretizerConfig Parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `level_set` | `DISCRETIZATION_LEVELS` | Fibonacci levels to track |
| `level_set_version` | `"v1.0"` | Version identifier for corpus comparability |
| `crossing_semantics` | `"close_cross"` | How crossings are detected |
| `crossing_tolerance_pct` | `0.001` | Tolerance as fraction of swing size |
| `invalidation_thresholds` | `{"S": -0.10, ...}` | Per-scale invalidation ratios |
| `rolling_window_sizes` | `{"S": 20, ...}` | Per-scale windows for range_multiple |
| `gap_threshold_pct` | `0.005` | Gap detection threshold (fraction of price) |

**Crossing Semantics**:

| Mode | Description |
|------|-------------|
| `close_cross` | Level crossed when bar close moves past level (default) |
| `open_close_cross` | Level crossed when bar opens on one side, closes on other |
| `wick_touch` | Level crossed if wick touches it |

**Multi-Level Jump Handling**: If price jumps from 0.3 to 1.5 in one bar, the discretizer logs `LEVEL_CROSS` events for all intermediate levels (0.382, 0.5, 0.618, 1.0) with the same bar timestamp. All events share the same `ShockAnnotation` with `levels_jumped` set to the count.

**Example Output**:

```python
# Log structure
log.meta          # DiscretizationMeta with config, instrument, date range
log.swings        # List[SwingEntry] - all registered swings
log.events        # List[DiscretizationEvent] - ordered event stream

# Event with side-channels
event = log.events[0]
event.bar         # Source bar index
event.event_type  # EventType.LEVEL_CROSS, COMPLETION, etc.
event.data        # Event-specific data
event.shock       # ShockAnnotation (levels_jumped, range_multiple, is_gap)
event.effort      # EffortAnnotation (dwell_bars, test_count)
event.parent_context  # ParentContext (larger scale swing state)
```

#### `src/discretization/io.py`

**Purpose**: Persistence layer for reading and writing discretization logs. JSON format for development; Parquet can be added later if needed.

**Key Functions**:

```python
from src.discretization import write_log, read_log, compare_configs, config_compatible

# Write log to JSON file
write_log(log, Path("output/events.json"))

# Read log from JSON file (validates by default)
log = read_log(Path("output/events.json"))

# Read without validation
log = read_log(path, validate=False, warn_config_diff=False)

# Compare configs between two logs
diffs = compare_configs(log1, log2)
# Returns: ["level_set_version differs: v1.0 vs v1.1", ...]

# Check if log is compatible with expected config
from src.discretization import get_default_config
if config_compatible(log, get_default_config()):
    print("Log uses current config")
```

**File Format**:

```json
{
  "schema_version": "1.0",
  "meta": {
    "instrument": "ES",
    "source_resolution": "1m",
    "date_range_start": "2024-01-01T00:00:00Z",
    "date_range_end": "2024-01-31T23:59:00Z",
    "created_at": "2025-12-15T12:00:00Z",
    "config": { ... }
  },
  "swings": [...],
  "events": [...]
}
```

**Config Compatibility**: When reading logs, the `warn_config_diff` parameter (default `True`) logs a warning if the log was produced with a different configuration than current defaults. Use `config_compatible()` to programmatically check compatibility based on `level_set` and `level_set_version`.

---

### Ground Truth Annotator

#### `src/ground_truth_annotator/models.py`

**Purpose**: Data models for expert swing annotations.

**Key Dataclasses**:

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
    start_price: Decimal
    end_price: Decimal
    created_at: datetime
    window_id: str              # Session identifier

@dataclass
class AnnotationSession:
    session_id: str
    data_file: str              # Path to source data
    resolution: str             # "1m", "5m", etc.
    window_size: int            # Number of bars
    created_at: datetime
    annotations: List[SwingAnnotation]
    completed_scales: List[str]
    skipped_scales: List[str]   # Scales explicitly skipped without review
    version: int                # Schema version (REVIEW_SCHEMA_VERSION)

@dataclass
class SwingFeedback:
    """Feedback on a single swing (match, FP, or FN) in Review Mode."""
    feedback_id: str              # UUID
    swing_type: str               # "match" | "false_positive" | "false_negative"
    swing_reference: Dict[str, Any]  # annotation_id or DetectedSwing data
    verdict: str                  # "correct" | "incorrect" | "noise" | "valid_missed" | "explained"
    comment: Optional[str]        # Free text explanation
    category: Optional[str]       # FP: "too_small" | "too_distant" | "not_prominent" | "counter_trend" | "better_high" | "better_low" | "better_both" | "other"
    created_at: datetime

@dataclass
class ReviewSession:
    """Review feedback for a single annotation session."""
    review_id: str                        # UUID
    session_id: str                       # Links to AnnotationSession
    phase: str                            # "matches" | "fp_sample" | "fn_feedback" | "complete"
    match_feedback: List[SwingFeedback]
    fp_feedback: List[SwingFeedback]
    fn_feedback: List[SwingFeedback]
    fp_sample_indices: List[int]          # Which FPs were sampled
    started_at: datetime
    completed_at: Optional[datetime]
```

**Schema Versioning**:

Both `AnnotationSession` and `ReviewSession` use `REVIEW_SCHEMA_VERSION` for backward compatibility:

| Version | Changes |
|---------|---------|
| v1 | Initial ReviewSession schema |
| v2 | Added difficulty, regime, session_comments |
| v3 | Replaced subsumed with not_prominent, better_high, better_low, better_both |
| v4 | Added version and skipped_scales to AnnotationSession |

- Files without version field default to v3 (AnnotationSession) or v1 (ReviewSession)
- Files without skipped_scales treated as empty list
- `skipped_scales` tracks scales explicitly skipped without review (for "Skip to FP Review" workflow)

#### `src/ground_truth_annotator/storage.py`

**Purpose**: JSON-backed persistence for annotation sessions.

**Directory Structure**:

```
ground_truth/
├── ground_truth.json              # All completed sessions (version-controlled)
└── sessions/                      # In-progress only (ephemeral, gitignored)
    └── inprogress-{timestamp}.json
```

**Session Lifecycle**:

1. **Session start** → Create `ground_truth/sessions/inprogress-{timestamp}.json`
2. **During session** → Update working file as normal
3. **Finalize "keep"** → Append session+review to `ground_truth.json`, delete working files
4. **Finalize "discard"** → Delete working files

**Ground Truth Schema**:

```json
{
  "metadata": {
    "schema_version": 1,
    "created_at": "...",
    "last_updated": "..."
  },
  "sessions": [
    {
      "finalized_at": "...",
      "original_filename": "2025-dec-15-1225-ver1",
      "session": { ... AnnotationSession dict ... },
      "review": { ... ReviewSession dict ... }
    }
  ]
}
```

**Single-User Assumption**:

This storage layer is designed for single-user operation. Concurrent users would cause:
- Race conditions on `ground_truth.json` appends
- Potential data loss from concurrent writes

If multi-user becomes a requirement, the storage layer would need:
- File locking on writes, or
- SQLite/database backend, or
- Per-user ground truth files with merge strategy

**Key Class**: `AnnotationStorage`

```python
storage = AnnotationStorage()  # Uses ground_truth/sessions/ by default

# Create session
session = storage.create_session(
    data_file="test.csv",
    resolution="1m",
    window_size=50000
)

# Save annotation
storage.save_annotation(session.session_id, annotation)

# Query annotations
annotations = storage.get_annotations(session.session_id, scale="S")

# Delete annotation
storage.delete_annotation(session.session_id, annotation_id)

# Finalize session (appends to ground_truth.json, deletes working files)
session_filename, path_id = storage.finalize_session(session.session_id, status="keep")

# Clean up stale sessions (older than 3 hours)
deleted_count = storage.cleanup_stale_sessions()
```

**Key Class**: `ReviewStorage`

```python
review_storage = ReviewStorage()  # Uses ground_truth/sessions/ by default

# Create review session for an annotation session
review = review_storage.create_review(session_id="abc123")

# Add feedback
feedback = SwingFeedback.create(
    swing_type="match",
    swing_reference={"annotation_id": "xyz"},
    verdict="correct"
)
review.add_feedback(feedback)
review_storage.save_review(review)

# Advance through phases
review.advance_phase()  # matches -> fp_sample -> fn_feedback -> complete

# Get review
loaded = review_storage.get_review(session_id="abc123")

# Finalize review (deletes working file; data already in ground_truth.json)
review_storage.finalize_review(session_id, status="keep", new_path_id=path_id)
```

#### `src/ground_truth_annotator/api.py`

**Purpose**: FastAPI backend for the annotation UI.

**Key Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve annotation UI |
| `/api/health` | GET | Health check |
| `/api/bars` | GET | Get aggregated bars for chart display |
| `/api/annotations` | GET | List annotations for current scale |
| `/api/annotations` | POST | Create annotation with direction inference |
| `/api/annotations/{id}` | DELETE | Delete annotation |
| `/api/session` | GET | Get session state |

**Direction Inference Logic**:

```python
# In POST /api/annotations
if start_bar.high > end_bar.high:
    # Price went down: bull reference (downswing)
    direction = "bull"
    start_price = start_bar.high
    end_price = end_bar.low
else:
    # Price went up: bear reference (upswing)
    direction = "bear"
    start_price = start_bar.low
    end_price = end_bar.high
```

**Snap-to-Extrema (Frontend)**:

The UI automatically snaps clicks to the best extrema within a scale-aware tolerance radius. This is implemented in `static/index.html`:

```javascript
const SNAP_TOLERANCE = { XL: 5, L: 10, M: 20, S: 30 };

// State for click intent tracking
let startClickedHigh = null;  // true if user clicked near high
let endClickedHigh = null;

function findBestExtrema(clickedIndex, tolerance, lookingForHigh, targetPrice) {
    // Searches bars[clickedIndex - tolerance] to bars[clickedIndex + tolerance]
    // Returns index of bar with extremum closest to targetPrice
}
```

- **Click intent**: Determined by click position relative to candle midpoint (above = HIGH, below = LOW)
- **Snap validation**: After snapping, checks if start and end resolve to same bar; shows error toast if so
- **Direction inference**: Uses stored click intents (`startClickedHigh`, `endClickedHigh`) instead of comparing bar highs
- **Shift key**: Disables snap-to-extrema, uses exact clicked bar

#### `src/ground_truth_annotator/main.py`

**Purpose**: CLI entry point for the annotator.

```bash
python -m src.ground_truth_annotator.main --data test.csv --scale S --target-bars 200
```

**CLI Options**:

| Option | Default | Description |
|--------|---------|-------------|
| `--data` | (required) | OHLC CSV file path |
| `--resolution` | 1m | Source data resolution |
| `--window` | 50000 | Total bars to load |
| `--scale` | S | Scale to annotate (S/M/L/XL) |
| `--target-bars` | 200 | Bars to display in chart |
| `--port` | 8000 | Server port |
| `--offset` | 0 | Start offset in bars (use 'random' for random position) |
| `--start-date` | None | Filter to start at date (e.g., `2020-Jan-01`). Overrides --offset. |

#### `src/ground_truth_annotator/comparison_analyzer.py`

**Purpose**: Compare user annotations against system-detected swings to identify false negatives and false positives.

**Key Classes**:

```python
@dataclass
class DetectedSwing:
    """System-detected swing in normalized format."""
    direction: str          # "bull" or "bear"
    start_index: int        # Bar index where swing starts
    end_index: int          # Bar index where swing ends
    high_price: float
    low_price: float
    size: float
    rank: int

@dataclass
class ComparisonResult:
    """Result of comparing annotations against detection for one scale."""
    scale: str
    false_negatives: List[SwingAnnotation]  # User marked, system missed
    false_positives: List[DetectedSwing]    # System found, user didn't mark
    matches: List[Tuple[SwingAnnotation, DetectedSwing]]

    @property
    def match_rate(self) -> float:
        """matches / (matches + FN + FP)"""
```

**Key Class**: `ComparisonAnalyzer`

```python
analyzer = ComparisonAnalyzer(tolerance_pct=0.1)  # 10% tolerance

# Compare single scale
result = analyzer.compare_scale(user_annotations, system_swings, scale="M")

# Compare entire session (runs system detection automatically)
results = analyzer.compare_session(session, bars, scales=["XL", "L", "M", "S"])

# Generate report
report = analyzer.generate_report(results)
# Returns: {summary: {...}, by_scale: {...}, false_negatives: [...], false_positives: [...]}
```

**Matching Logic**:

A user annotation matches a system-detected swing when:
1. Direction matches (both bull or both bear)
2. Start indices within tolerance: `abs(user.start - system.start) <= tolerance_bars`
3. End indices within tolerance: `abs(user.end - system.end) <= tolerance_bars`

Tolerance is calculated as: `max(5, int(duration * tolerance_pct))`

**API Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/compare` | POST | Run comparison, returns summary |
| `/api/compare/report` | GET | Get full report with FN/FP lists |
| `/api/compare/export` | GET | Export as JSON or CSV |

#### Review Mode API (`/api/review/*`)

**Purpose**: Structured feedback collection on comparison results through a phased workflow.

**Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/review/start` | POST | Initialize review, run comparison if needed, sample FPs |
| `/api/review/state` | GET | Get current phase and progress |
| `/api/review/matches` | GET | Get matched swings for Phase 1 review |
| `/api/review/fp-sample` | GET | Get stratified FP sample for Phase 2 |
| `/api/review/fn-list` | GET | Get all false negatives for Phase 3 |
| `/api/review/feedback` | POST | Submit feedback on a swing |
| `/api/review/advance` | POST | Advance to next review phase |
| `/api/review/summary` | GET | Get review statistics |
| `/api/review/export` | GET | Export feedback as JSON or CSV |

#### Discretization API (`/api/discretization/*`)

**Purpose**: Run discretization on the current window and retrieve structural events for visualization.

**Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/discretization/state` | GET | Check if discretization has been run |
| `/api/discretization/run` | POST | Run discretization on current window |
| `/api/discretization/events` | GET | Get all events (with optional filters) |
| `/api/discretization/swings` | GET | Get all detected swings |
| `/api/discretization/levels` | GET | Get Fib levels for a specific swing |

**Query Parameters for `/api/discretization/events`**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `scale` | string | Filter by swing scale (XL, L, M, S) |
| `event_type` | string | Filter by event type (LEVEL_CROSS, COMPLETION, etc.) |
| `shock_threshold` | float | Minimum `range_multiple` for shock filter |
| `levels_jumped_min` | int | Minimum `levels_jumped` for shock filter |
| `is_gap` | bool | Filter for gap events only |
| `bar_start` | int | Filter events from bar index |
| `bar_end` | int | Filter events up to bar index |

**Response Models**:

```python
class DiscretizationEventResponse(BaseModel):
    bar: int
    timestamp: str
    swing_id: str
    event_type: str
    data: dict
    effort: Optional[dict]
    shock: Optional[dict]
    parent_context: Optional[dict]

class DiscretizationSwingResponse(BaseModel):
    swing_id: str
    scale: str
    direction: str
    anchor0: float
    anchor1: float
    anchor0_bar: int
    anchor1_bar: int
    status: str
    formed_at_bar: int
    terminated_at_bar: Optional[int]
    termination_reason: Optional[str]
```

#### Replay View (`/replay`)

**Purpose**: Split-chart interface for temporal debugging with independent aggregation per chart.

**Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/replay` | GET | Serve React Replay View UI |

**Features**:
- React + Tailwind frontend (built with Vite)
- Two stacked charts with aggregation selectors (5m/15m/1H/4H labels)
- Time synchronization via shared source bar index
- Playback controls with SVG timer wheel for linger countdown
- Event filter toggles in collapsible sidebar
- 3-column explanation panel for swing details

**React Frontend (`frontend/`)**:

```
frontend/
├── src/
│   ├── components/
│   │   ├── Header.tsx          # Navigation menu, timestamp
│   │   ├── Sidebar.tsx         # Event filter toggles
│   │   ├── ChartArea.tsx       # Dual lightweight-charts
│   │   ├── PlaybackControls.tsx # Transport + timer wheel
│   │   ├── ExplanationPanel.tsx # 3-column swing details
│   │   └── ui/                 # Toggle, Badge primitives
│   ├── hooks/
│   │   └── usePlayback.ts      # Playback state machine
│   ├── lib/
│   │   └── api.ts              # API client functions
│   ├── pages/
│   │   └── Replay.tsx          # Main page component
│   ├── types.ts                # TypeScript types
│   └── constants.ts            # Filter defaults, speeds
├── tailwind.config.js          # Designer color palette
└── vite.config.ts              # Dev proxy to :8000
```

**Development Workflow**:

```bash
# Hot-reload development (proxies API to Python server)
cd frontend && npm run dev  # Starts on :3000

# Production build (served by Python server)
cd frontend && npm run build  # Outputs to frontend/dist/
```

**Implementation Notes**:
- Uses lightweight-charts v5 API (`chart.addSeries(CandlestickSeries, options)`)
- `usePlayback` hook manages play/pause/step/linger state machine
- Sidebar filters stored in React state, control which events trigger linger
- Charts sync via `onPositionChange` callback from usePlayback

**Request/Response Models** (defined in `api.py`):

```python
class ReviewStateResponse(BaseModel):
    review_id: str
    session_id: str
    phase: str  # "matches" | "fp_sample" | "fn_feedback" | "complete"
    progress: dict  # {"completed": int, "total": int}
    is_complete: bool

class FeedbackSubmit(BaseModel):
    swing_type: str  # "match" | "false_positive" | "false_negative"
    swing_reference: dict  # {"annotation_id": str} or {"sample_index": int}
    verdict: str  # "correct" | "incorrect" | "noise" | "valid_missed" | "explained"
    comment: Optional[str] = None  # Required for false_negative
    category: Optional[str] = None
```

**Phase Progression**:
- `matches` → `fp_sample` → `fn_feedback` → `complete`
- FN phase requires all false negatives to have feedback with comments before advancing

#### `src/ground_truth_annotator/review_controller.py`

**Purpose**: Manage Review Mode workflow phases (matches → FP sample → FN feedback → complete).

**Key Class**: `ReviewController`

```python
from src.ground_truth_annotator.review_controller import ReviewController

controller = ReviewController(
    session_id="abc123",
    annotation_storage=annotation_storage,
    review_storage=review_storage,
    comparison_results=comparison_results  # From ComparisonAnalyzer
)

# Get or create review session (samples FPs on first call)
review = controller.get_or_create_review()

# Phase 1: Review matches
matches = controller.get_matches()
for match in matches:
    controller.submit_feedback(
        swing_type="match",
        swing_reference={"annotation_id": match["annotation"]["annotation_id"]},
        verdict="correct"
    )
controller.advance_phase()

# Phase 2: Review sampled FPs
fp_sample = controller.get_fp_sample()
for fp in fp_sample:
    controller.submit_feedback(
        swing_type="false_positive",
        swing_reference={"sample_index": fp["sample_index"]},
        verdict="noise",
        category="too_small"
    )
controller.advance_phase()

# Phase 3: Review FNs (comment required)
fn_list = controller.get_false_negatives()
for fn in fn_list:
    controller.submit_feedback(
        swing_type="false_negative",
        swing_reference={"annotation_id": fn["annotation"]["annotation_id"]},
        verdict="valid_missed",
        comment="Pattern needs tuning"  # Required for FN
    )
controller.advance_phase()

# Complete
assert controller.is_complete()
summary = controller.get_summary()
```

**Key Methods**:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_or_create_review()` | `ReviewSession` | Get existing or create new review, samples FPs |
| `get_current_phase()` | `str` | Current phase name |
| `get_phase_progress()` | `(int, int)` | (completed, total) for current phase |
| `get_matches()` | `List[dict]` | Matched swings for Phase 1 |
| `get_fp_sample()` | `List[dict]` | Sampled FPs for Phase 2 |
| `get_false_negatives()` | `List[dict]` | All FNs for Phase 3 |
| `submit_feedback()` | `SwingFeedback` | Submit verdict on a swing |
| `advance_phase()` | `bool` | Move to next phase |
| `is_complete()` | `bool` | True if all phases done |
| `get_summary()` | `dict` | Review statistics |

**FP Sampling Algorithm**:

```python
# Static method for stratified sampling
sampled, indices = ReviewController.sample_false_positives(
    fps_by_scale={"XL": [...], "L": [...], "M": [...], "S": [...]},
    target=20
)
```

1. If total FPs ≤ target, return all
2. Otherwise, allocate proportionally with minimum 2 per scale
3. Random sample within each scale's allocation
4. Cap at target (default 20)

**Verdict Types**:

| Swing Type | Valid Verdicts |
|------------|----------------|
| `match` | `correct`, `incorrect` |
| `false_positive` | `noise`, `valid` |
| `false_negative` | `valid_missed`, `explained` |

---

## Key Data Structures

### Bar

```python
@dataclass
class Bar:
    index: int           # Position in dataset
    timestamp: int       # Unix timestamp
    open: Decimal       # Opening price
    high: Decimal       # High price
    low: Decimal        # Low price
    close: Decimal      # Closing price
```

### ActiveSwing

```python
@dataclass
class ActiveSwing:
    swing_id: str              # Unique identifier
    scale: str                 # S, M, L, or XL
    is_bull: bool             # True = bullish reference
    high_price: float
    low_price: float
    high_timestamp: int
    low_timestamp: int
    levels: Dict[str, float]  # {"0.382": 5050.25, "0.618": 5062.50, ...}
```

### StructuralEvent

```python
@dataclass
class StructuralEvent:
    event_type: EventType        # LEVEL_CROSS, COMPLETION, INVALIDATION
    severity: EventSeverity      # MAJOR, MINOR
    timestamp: int
    source_bar_idx: int
    level_name: str              # "0.618", "2.0", etc.
    level_price: float
    swing_id: str
    scale: str
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    description: str
```

### ScaleConfig

```python
@dataclass
class ScaleConfig:
    boundaries: Dict[str, Tuple[float, float]]  # {'S': (0, 10.5), ...}
    aggregations: Dict[str, int]                 # {'S': 1, 'M': 5, ...}
```

### SwingAnnotation

```python
@dataclass
class SwingAnnotation:
    annotation_id: str          # UUID
    scale: str                  # S, M, L, XL
    direction: str              # "bull" or "bear"
    start_bar_index: int        # Index in aggregated view
    end_bar_index: int          # Index in aggregated view
    start_source_index: int     # Index in source data
    end_source_index: int       # Index in source data
    start_price: Decimal
    end_price: Decimal
    created_at: datetime
    window_id: str              # Session identifier
```

---

## Extending the System

### Adding a New Scale

1. Update `ScaleCalibrator.calibrate()` to compute additional boundaries
2. Add scale handling in `BarAggregator` for new timeframe if needed
3. Update ground truth annotator UI to support the new scale

### Adding a New Event Type

1. Add type to `EventType` enum in `event_detector.py`
2. Implement detection logic in `EventDetector.detect_events()`

### Adding a New Data Source

1. Add format handler in `OHLCLoader._detect_format()`
2. Implement parsing in `OHLCLoader._parse_<format>()`
3. Ensure output is `List[Bar]` with Decimal prices

---

## Testing

### Running Tests

```bash
# All tests with verbose output
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_scale_calibrator.py -v

# Single test function
python -m pytest tests/test_scale_calibrator.py::test_calibrate_boundaries -v

# With coverage report
python -m pytest tests/ --cov=src --cov-report=html
```

### Test Organization

```
tests/
├── test_scale_calibrator.py           # Scale boundary calibration
├── test_bar_aggregator.py             # Multi-timeframe aggregation
├── test_swing_state_manager.py        # Swing tracking state machine
├── test_event_detector.py             # Event detection logic
├── test_ohlc_loader.py                # Data loading
├── test_swing_detector.py             # Swing detection logic
├── test_swing_detector_unit.py        # Swing detection unit tests
├── test_ground_truth_foundation.py    # Annotation models and storage (68 tests)
├── test_ground_truth_annotator_api.py # Annotator API endpoints (71 tests)
├── test_comparison_analyzer.py        # Comparison logic (23 tests)
├── test_cascade_controller.py         # Cascade workflow (29 tests)
├── ground_truth_annotator/
│   └── test_review_controller.py      # Review Mode controller (28 tests)
└── conftest.py                        # Shared fixtures
```

### Key Test Patterns

**Event Detection Tests**:

```python
def test_completion_detection():
    detector = EventDetector()
    swing = create_test_swing(low=5000, high=5100)
    bar = create_bar(close=5200)  # Above 2.0 extension

    events = detector.detect_events(bar, [swing])

    completions = [e for e in events if e.event_type == EventType.COMPLETION]
    assert len(completions) == 1
```

---

## Troubleshooting

### Common Issues

#### Virtual environment issues

```bash
# Remove and recreate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Port already in use

If the annotator fails to start with a port conflict:

```bash
# Use a different port
python -m src.ground_truth_annotator.main --data test_data/test.csv --port 8001
```

### Debug Logging

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Key log sources:
- `SwingDetector`: Swing detection
- `ComparisonAnalyzer`: FN/FP comparison
- `ReviewController`: Review Mode phases

---

## Performance Benchmarks

| Component | Target | Achieved | Notes |
|-----------|--------|----------|-------|
| Scale calibration | <100ms | ~50ms | ~7,000 bars |
| Bar aggregation | <100ms | ~50ms | 10K bars |
| Swing detection | <60s | ~30s | 6M bars |
| Event detection | <10ms | <1ms | Per bar |

---

## Code Standards

- Type hints on all public functions
- Docstrings for classes and non-trivial functions
- Tests for new functionality
- Follow existing patterns in the codebase
- Use `Decimal` for price calculations

---

## Further Reading

- `CLAUDE.md` - Project overview and development guidelines
- `Docs/Reference/user_guide.md` - End-user documentation
- `Docs/State/architect_notes.md` - Architecture decisions
- `Docs/State/product_direction.md` - Product roadmap
