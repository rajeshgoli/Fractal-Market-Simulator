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
   - [Visualization Harness](#visualization-harness)
   - [Validation Infrastructure](#validation-infrastructure)
6. [Key Data Structures](#key-data-structures)
7. [Configuration System](#configuration-system)
8. [Extending the System](#extending-the-system)
9. [Testing](#testing)
10. [Troubleshooting](#troubleshooting)

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
# Basic visualization harness
python main.py --data test.csv

# With auto-start and custom speed
python main.py --data market_data.csv --auto-start --speed 2.0

# Show available options
python main.py --help

# Discover available historical data
python3 -m src.visualization_harness.main list-data --symbol ES --verbose

# Run historical validation
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11
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
│  │   Scale      │────▶│    Bar       │────▶│   Swing State        │    │
│  │ Calibrator   │     │ Aggregator   │     │   Manager            │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
│         │                    │                       │                  │
│         ▼                    ▼                       ▼                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ Boundaries   │     │ Multi-TF     │     │   Event Detector     │    │
│  │ (S,M,L,XL)   │     │ OHLC Cache   │     │ (cross/complete/inv) │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      VISUALIZATION HARNESS                               │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │  Renderer    │◀───▶│  Playback    │◀───▶│   Event Logger       │    │
│  │ (4-panel)    │     │ Controller   │     │  (search/export)     │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
│         │                    │                       │                  │
│         ▼                    ▼                       ▼                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ matplotlib   │     │ Thread-safe  │     │   CSV/JSON Export    │    │
│  │ Candlesticks │     │ Auto-play    │     │   Full-text Search   │    │
│  └──────────────┘     └──────────────┘     └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
fractal-market-simulator/
├── main.py                          # Application entry point
├── src/
│   ├── data/
│   │   ├── ohlc_loader.py          # CSV data loading
│   │   └── loader.py               # Historical data with date filtering
│   ├── swing_analysis/
│   │   ├── bull_reference_detector.py   # Bar dataclass, reference detection
│   │   ├── level_calculator.py          # Fibonacci level computation
│   │   ├── scale_calibrator.py          # Auto-calibrate scale boundaries
│   │   ├── bar_aggregator.py            # Multi-timeframe bar aggregation
│   │   ├── swing_state_manager.py       # Active swing tracking
│   │   ├── event_detector.py            # Structural event detection
│   │   └── swing_detector.py            # Legacy swing detection (pandas)
│   ├── visualization_harness/
│   │   ├── harness.py              # Main CLI harness
│   │   ├── main.py                 # Multi-command CLI entry
│   │   ├── renderer.py             # 4-panel matplotlib visualization
│   │   ├── render_config.py        # Styling and layout configuration
│   │   ├── controller.py           # Playback control
│   │   ├── playback_config.py      # Playback modes and states
│   │   ├── event_logger.py         # Event logging with export
│   │   ├── display.py              # Event formatting
│   │   ├── filters.py              # Event filtering
│   │   ├── layout_manager.py       # Dynamic panel layouts
│   │   ├── pip_inset.py            # Picture-in-picture insets
│   │   └── swing_visibility.py     # Swing display filtering
│   └── validation/
│       ├── session.py              # Validation session management
│       └── issue_catalog.py        # Issue tracking
├── tests/                          # Test suite (250+ tests)
├── Docs/                           # Documentation
└── data/                           # Sample data files
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
-0.1        -0.10    Stop/invalidation zone
0           0.00     Swing low (bullish) / high (bearish)
0.382       0.382    Shallow retracement
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

Validation criteria:
1. The swing must be the most extreme in its range (no intervening higher highs or lower lows)
2. Current price must be within the 0.382-2.0 "active zone"

### Structural Events

The system detects three types of structural events:

| Event Type | Description | Trigger |
|------------|-------------|---------|
| **LEVEL_CROSS** | Price crosses a Fibonacci level | Bar close above/below level |
| **COMPLETION** | Swing reaches target (2.0 extension) | Close above 2.0 level |
| **INVALIDATION** | Swing breaks structure | Close below -0.1 level |

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
       │   └─▶ Check invalidations (-0.1 break)
       │
       └─▶ Returns List[StructuralEvent]

3. Log Events
   └─▶ event_logger.log_events_batch(events, market_context)
       └─▶ Generates auto-tags
       └─▶ Updates indices for fast lookup

4. Update Visualization
   └─▶ renderer.update_display(bar_idx, active_swings, events)
       │
       ├─▶ For each panel (S, M, L, XL):
       │   └─▶ Calculate view window in aggregated space
       │   └─▶ Draw OHLC candlesticks
       │   └─▶ Draw swing bodies (left margin schematic)
       │   └─▶ Draw Fibonacci level lines
       │   └─▶ Draw event markers
       │
       └─▶ Refresh matplotlib canvas
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

#### `src/data/loader.py`

**Purpose**: Load historical data with date range filtering for validation.

**Key Functions**:

```python
from src.data.loader import load_historical_data, get_data_summary

# Load with date filtering
bars = load_historical_data(
    symbol="ES",
    resolution="1m",
    start_date=datetime(2024, 10, 10),
    end_date=datetime(2024, 10, 11)
)

# Discover available data
summary = get_data_summary(symbol="ES")
# Returns: {resolution: {files: [...], date_range: (start, end)}}
```

---

### Swing Analysis

#### `src/swing_analysis/bull_reference_detector.py`

**Purpose**: Core Bar dataclass and reference swing detection.

**Key Dataclass**: `Bar`

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

**Key Class**: `BullReferenceDetector`

Detects swing highs/lows and pairs them into valid reference swings. Uses lookback validation to ensure swings are structural (not noise).

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
| `INVALIDATION` | Bar closes below -0.1 stop | MAJOR |

#### `src/swing_analysis/swing_detector.py`

**Purpose**: Legacy swing detection using pandas. Used for batch analysis and historical swing identification.

**Key Function**: `detect_swings(df, lookback=5, filter_redundant=True)`

Uses `SparseTable` for O(1) range minimum/maximum queries to validate swing structure efficiently.

---

### Visualization Harness

#### `src/visualization_harness/renderer.py`

**Purpose**: 4-panel synchronized matplotlib display.

**Key Class**: `VisualizationRenderer`

```python
renderer = VisualizationRenderer(scale_config, bar_aggregator)
renderer.initialize_display()
renderer.show_display()

# Update with new state
renderer.update_display(
    current_bar_idx=100,
    active_swings=swings,
    recent_events=events
)
```

**Visual Elements**:
- 2x2 grid showing S/M/L/XL scales simultaneously
- OHLC candlestick rendering with bullish/bearish coloring
- Swing body schematic (left margin rectangle showing H/L)
- Fibonacci level lines with labels
- Event markers (triangles for crosses, stars for completions, X for invalidations)

**Features**:
- Frame skipping for high-speed playback
- Dynamic timeframe selection (targets 40-60 candles)
- Thread-safe state caching for layout transitions

**Layout Modes**:

```python
# Expand a single panel to ~90%
renderer.expand_panel(panel_idx=0)  # Expand S scale

# Return to standard 2x2 grid
renderer.restore_quad_layout()

# Toggle expansion
renderer.toggle_panel_expand(panel_idx=1)
```

#### `src/visualization_harness/controller.py`

**Purpose**: Interactive playback control with auto-pause intelligence.

**Key Class**: `PlaybackController`

```python
controller = PlaybackController(total_bars=5000)
controller.set_event_callback(my_step_handler)

# Start playback
controller.start_playback(mode=PlaybackMode.AUTO)

# Manual control
controller.step_forward()
controller.pause_playback(reason="Major event")
controller.jump_to_bar(1000)

# Get status
status = controller.get_status()
```

**Playback Modes**:

| Mode | Behavior |
|------|----------|
| `MANUAL` | Step-by-step, no auto-advance |
| `AUTO` | Auto-advance with configured speed |
| `FAST` | Rapid playback, minimal delays |

**Playback States**:

| State | Description |
|-------|-------------|
| `STOPPED` | Initial state or after stop |
| `PLAYING` | Active playback |
| `PAUSED` | Paused by user or event |
| `FINISHED` | Reached end of data |

**Auto-Pause Logic**: Automatically pauses on major events (completions, invalidations) when `pause_on_major_events=True`.

#### `src/visualization_harness/event_logger.py`

**Purpose**: Comprehensive event logging with search and export.

**Key Class**: `EventLogger`

```python
logger = EventLogger(session_id="session_001")

# Log events
event_id = logger.log_event(structural_event, market_context)

# Query events
events = logger.get_events(
    filter_criteria=LogFilter(scales=["M", "L"]),
    limit=50
)

# Full-text search
matches = logger.search_events("completion 0.618")

# Export
logger.export_to_csv("events.csv")
logger.export_to_json("events.json")

# Statistics
stats = logger.get_event_statistics()
```

**Auto-Tagging**: Events are automatically tagged based on:
- Severity: `severity-major`, `severity-minor`
- Type: `type-completion`, `type-level_cross`
- Scale: `scale-S`, `scale-M`, etc.
- Level category: `critical-level`, `retracement`, `decision-zone`
- Swing age: `new-swing`, `mature-swing`

#### `src/visualization_harness/harness.py`

**Purpose**: Unified CLI integrating all components.

**Interactive Commands**:

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `status` | Show current playback status |
| `play` / `pause` | Control playback |
| `step` | Step forward one bar |
| `speed <N>` | Set playback speed multiplier |
| `events <N>` | Show last N events |
| `filter <criteria>` | Filter events |
| `export csv <file>` | Export events to CSV |
| `export json <file>` | Export events to JSON |
| `quit` | Exit application |

---

### Validation Infrastructure

#### `src/validation/session.py`

**Purpose**: Manage validation sessions for systematic expert review.

**Key Class**: `ValidationSession`

```python
session = ValidationSession(
    symbol="ES",
    resolution="1m",
    start_date=datetime(2024, 10, 10),
    end_date=datetime(2024, 10, 11)
)

# Start session
session.start_session("ES", (start_date, end_date))

# Update progress
session.update_progress(current_bar=100, total_bars=5000)

# Log issues
session.log_issue(
    timestamp=datetime.now(),
    issue_type="accuracy",
    description="Missed swing low at bar 95",
    severity="major",
    suggested_fix="Adjust lookback parameter"
)

# Add expert notes
session.add_expert_note("Market was unusually volatile here")

# Save/load session
session.save_session()
session.load_session("abc123")

# Export findings
session.export_findings("validation_report.json")
```

**Issue Types**:
- `accuracy`: Incorrect swing detection
- `level`: Fibonacci calculation issues
- `event`: Missing or false event triggers
- `consistency`: Multi-scale relationship issues
- `performance`: Processing speed issues

**Session Persistence**: Sessions are saved to JSON files in `validation_sessions/` with automatic progress checkpointing.

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

---

## Configuration System

### RenderConfig

Located in `src/visualization_harness/render_config.py`:

```python
@dataclass
class RenderConfig:
    # Display
    figure_size: Tuple[int, int] = (16, 12)
    max_visible_bars: int = 100

    # Colors
    background_color: str = "#1E1E1E"
    text_color: str = "#E0E0E0"
    grid_color: str = "#404040"

    # Events
    major_event_color: str = "#FF6B6B"
    minor_event_color: str = "#4ECDC4"
    event_marker_size: int = 100

    # Levels
    level_alpha: float = 0.6
    level_line_width: float = 1.0

    # Performance
    enable_frame_skipping: bool = True
    min_render_interval_ms: int = 50

    # Swing display
    max_swings_per_scale: int = 3
    show_all_swings: bool = False
```

### PlaybackConfig

Located in `src/visualization_harness/playback_config.py`:

```python
@dataclass
class PlaybackConfig:
    auto_speed_ms: int = 500        # Interval for AUTO mode
    fast_speed_ms: int = 50         # Interval for FAST mode
    max_playback_speed_hz: int = 60  # Max updates per second

    # Auto-pause settings
    pause_on_major_events: bool = True
    pause_on_completion: bool = True
    pause_on_invalidation: bool = True
    pause_on_scale_filter: Optional[List[str]] = None
```

---

## Extending the System

### Adding a New Scale

1. Update `ScaleCalibrator.calibrate()` to compute additional boundaries
2. Add scale to `PANEL_SCALE_MAPPING` in `render_config.py`
3. Update `VisualizationRenderer` grid layout if more than 4 panels needed

### Adding a New Event Type

1. Add type to `EventType` enum in `event_detector.py`
2. Implement detection logic in `EventDetector.detect_events()`
3. Add marker style in `EVENT_MARKERS` dict in `render_config.py`
4. Update auto-tagging in `EventLogger._generate_auto_tags()`

### Adding a New Data Source

1. Add format handler in `OHLCLoader._detect_format()`
2. Implement parsing in `OHLCLoader._parse_<format>()`
3. Ensure output is `List[Bar]` with Decimal prices

### Adding a New Visualization Element

1. Add artist storage in `VisualizationRenderer.artists` dict
2. Implement drawing method `draw_<element>()`
3. Call from `render_panel()`
4. Add cleanup in `_clear_panel_artists()`

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
├── test_scale_calibrator.py      # Scale boundary calibration
├── test_bar_aggregator.py        # Multi-timeframe aggregation
├── test_swing_state_manager.py   # Swing tracking state machine
├── test_event_detector.py        # Event detection logic
├── test_visualization_renderer.py # Rendering and display
├── test_playback_controller.py   # Playback state machine
├── test_event_logger.py          # Logging and export
├── test_ohlc_loader.py           # Data loading
└── conftest.py                   # Shared fixtures
```

### Key Test Patterns

**State Machine Tests** (e.g., PlaybackController):

```python
def test_state_transitions():
    controller = PlaybackController(total_bars=100)
    assert controller.state == PlaybackState.STOPPED

    controller.start_playback(PlaybackMode.AUTO)
    assert controller.state == PlaybackState.PLAYING

    controller.pause_playback()
    assert controller.state == PlaybackState.PAUSED
```

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

#### "No data found for date range"

```bash
# Check what data is available
python3 -m src.visualization_harness.main list-data --symbol ES --verbose

# Adjust date range to match available data
```

#### matplotlib window not appearing

Ensure a GUI backend is configured:

```python
import matplotlib
matplotlib.use('TkAgg')  # or 'MacOSX' on macOS
import matplotlib.pyplot as plt
```

#### Slow playback performance

1. Enable frame skipping: `RenderConfig.enable_frame_skipping = True`
2. Increase render interval: `RenderConfig.min_render_interval_ms = 100`
3. Reduce visible bars: `RenderConfig.max_visible_bars = 50`
4. Use FAST playback mode

#### Virtual environment issues

```bash
# Remove and recreate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Debug Logging

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Key log sources:
- `SwingStateManager`: Swing additions/removals
- `EventDetector`: Event triggers
- `VisualizationRenderer`: Display updates

---

## Performance Benchmarks

| Component | Target | Achieved | Notes |
|-----------|--------|----------|-------|
| Scale calibration | <100ms | ~50ms | ~7,000 bars |
| Bar aggregation | <100ms | ~50ms | 10K bars |
| Per-bar analysis | <500ms | ~28ms | Full pipeline |
| UI update | <100ms | ~50ms | 4-panel refresh |
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
