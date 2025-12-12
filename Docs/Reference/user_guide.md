# Swing Validation Tools - User Guide

## Overview

This project provides three tools for swing detection validation and ground truth collection:

1. **Ground Truth Annotator** - A web-based tool for expert swing annotation with two-click workflow
2. **Lightweight Swing Validator** - A web-based tool for fast validation with voting interface
3. **Swing Validation Harness** - A matplotlib-based tool for detailed 4-panel visualization

---

# Ground Truth Annotator

The Ground Truth Annotator is a web-based tool for expert annotation of swing references. It provides a two-click workflow for marking swings on aggregated OHLC charts, with automatic direction inference.

## Quick Start

### Prerequisites
- Python 3.8+ with virtual environment
- OHLC data in CSV format (test data included in `test_data/`)

### Installation

```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate and install dependencies
source venv/bin/activate
pip install -r requirements.txt
```

### Launch the Annotator

```bash
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/test.csv --scale S
```

Open http://127.0.0.1:8000 in your browser.

### Command Line Options

| Option | Description |
|--------|-------------|
| `--data FILE` | Path to OHLC CSV data file (required) |
| `--port PORT` | Server port (default: 8000) |
| `--host HOST` | Server host (default: 127.0.0.1) |
| `--storage-dir DIR` | Directory for annotation sessions |
| `--resolution RES` | Source data resolution (default: 1m) |
| `--window N` | Total bars to work with (default: 50000) |
| `--scale SCALE` | Scale to annotate: S, M, L, XL (default: S) |
| `--target-bars N` | Target bars to display in chart (default: 200) |

### Examples

```bash
# Annotate small-scale swings on 1m data
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --scale S

# Annotate medium-scale swings with more bars displayed
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --scale M --target-bars 300

# Annotate on 5m data with custom port
python -m src.ground_truth_annotator.main --data data/es-5m.csv --resolution 5m --scale L --port 8001
```

## The Two-Click Annotation Workflow

1. **Click Start**: Click near the first candle of the swing. The system **automatically snaps** to the best extrema (highest high or lowest low) within a tolerance radius. A "Start" marker appears on the snapped candle.
2. **Click End**: Click near the last candle. The system snaps to the opposite extrema (if start was a high, snaps to lowest low; if start was a low, snaps to highest high). A confirmation dialog appears.
3. **Confirm Direction**: The system infers the direction automatically:
   - If start.high > end.high → **Bull Reference** (downswing)
   - If start.low < end.low → **Bear Reference** (upswing)
4. **Save or Cancel**: Click "Confirm" to save or "Cancel" to restart.

### Snap-to-Extrema

Clicks automatically snap to the best extrema within a scale-aware tolerance radius. This means you don't need pixel-perfect clicking—the system finds the optimal candle for you.

| Scale | Snap Radius (bars) |
|-------|-------------------|
| XL | 5 |
| L | 10 |
| M | 20 |
| S | 30 |

Larger scales use tighter tolerances because fewer aggregated bars are visible.

### Direction Inference

The annotator automatically determines swing direction based on price movement:

| Price Movement | Direction | Meaning |
|---------------|-----------|---------|
| Start high > End high | Bull Reference | Downswing completed, now bullish |
| Start high ≤ End high | Bear Reference | Upswing completed, now bearish |

## User Interface

### Chart Area
- **OHLC Candlesticks**: Green (bullish) and red (bearish) candles
- **Selection Markers**: Blue arrows show selected start/end points
- **Annotation Markers**: Numbered circles show saved annotations

### Sidebar
- **Annotation List**: All saved annotations with direction and bar range
- **Delete Button**: Click × to remove an annotation
- **Keyboard Hints**: Quick reference for shortcuts

### Header
- **Scale Badge**: Shows current scale being annotated
- **Bar Count**: Number of aggregated bars displayed
- **Annotation Count**: Total annotations for this session

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Esc` | Cancel current selection |
| `Enter` | Confirm annotation (when dialog open) |
| `Delete` / `Backspace` | Delete last annotation |

## API Endpoints

The annotator exposes a REST API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve annotation UI |
| `/api/health` | GET | Health check |
| `/api/bars` | GET | Get aggregated bars for chart |
| `/api/annotations` | GET | List annotations for current scale |
| `/api/annotations` | POST | Create new annotation |
| `/api/annotations/{id}` | DELETE | Delete annotation |
| `/api/session` | GET | Get session state |

## Session Files

Annotation sessions are saved to `annotation_sessions/{session_id}.json` containing:
- Session metadata (data file, resolution, window size)
- All annotations with bar indices and prices
- Scale completion status

## Comparison Analysis

After annotating swings, compare your annotations against the system's automatic detection to identify:
- **False Negatives**: Swings you marked that the system missed
- **False Positives**: Swings the system detected that you didn't mark
- **Matches**: Swings both you and the system identified

### Running Comparison

Use the API endpoints to run comparison analysis:

```bash
# Run comparison (POST)
curl -X POST http://127.0.0.1:8000/api/compare

# Get detailed report (GET)
curl http://127.0.0.1:8000/api/compare/report

# Export as CSV (GET)
curl http://127.0.0.1:8000/api/compare/export?format=csv > report.csv
```

### Understanding the Report

The comparison report includes:

| Field | Description |
|-------|-------------|
| `overall_match_rate` | Percentage of swings that matched (0.0 to 1.0) |
| `total_false_negatives` | Swings you marked that system missed |
| `total_false_positives` | Swings system found that you didn't mark |
| `by_scale` | Per-scale breakdown (XL, L, M, S) |

### Matching Logic

A user annotation matches a system-detected swing when:
1. **Direction matches**: Both are bull or both are bear
2. **Start index within tolerance**: User's start is within 10% of swing duration from system's start
3. **End index within tolerance**: User's end is within 10% of swing duration from system's end
4. **Minimum tolerance**: At least 5 bars tolerance for short swings

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/compare` | POST | Run comparison, returns summary |
| `/api/compare/report` | GET | Get full report with FN/FP lists |
| `/api/compare/export` | GET | Export as JSON or CSV |

---

# Lightweight Swing Validator

The Lightweight Swing Validator is a web-based tool for human-in-the-loop validation of swing detection. It presents random time intervals with detected swing candidates for quick review and voting.

## Quick Start

### Prerequisites
- Python 3.8+ with virtual environment
- OHLC data in CSV format (test data included in `test_data/`)

### Installation

```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate and install dependencies
source venv/bin/activate
pip install -r requirements.txt
```

### Launch the Validator

```bash
source venv/bin/activate
python -m src.lightweight_swing_validator.main --data test_data/test.csv
```

Open http://127.0.0.1:8000 in your browser.

### Command Line Options

| Option | Description |
|--------|-------------|
| `--data FILE` | Path to OHLC CSV data file (required) |
| `--port PORT` | Server port (default: 8000) |
| `--host HOST` | Server host (default: 127.0.0.1) |
| `--storage-dir DIR` | Directory for validation results |
| `--seed N` | Random seed for reproducible sampling |
| `--resolution RES` | Source data resolution (default: 1m). Options: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo |
| `--window N` | Calibration window size in bars (default: auto) |

### Examples

```bash
# Basic usage with 1m data (default)
python -m src.lightweight_swing_validator.main --data test_data/es-1m.csv --port 8080

# Using 5m resolution data with custom calibration window
python -m src.lightweight_swing_validator.main --data data/es-5m.csv --resolution 5m --window 50000

# Daily data
python -m src.lightweight_swing_validator.main --data data/es-daily.csv --resolution 1d
```

### Resolution Parameter

The `--resolution` parameter tells the system what resolution your source data is in. This affects:

- **Available timeframes**: Only aggregations >= source resolution are available
- **Scale calibration**: Default aggregations are adjusted (e.g., S=5m for 5m data instead of S=1m)
- **Gap detection**: Thresholds scale with resolution

| Resolution | Minutes | Typical Use Case |
|------------|---------|------------------|
| 1m | 1 | Intraday micro-structure |
| 5m | 5 | Intraday with reduced noise |
| 15m | 15 | Swing trading |
| 30m | 30 | Position trading |
| 1h | 60 | Daily patterns |
| 4h | 240 | Multi-day swings |
| 1d | 1440 | Long-term trends |
| 1w | 10080 | Weekly analysis |
| 1mo | 43200 | Monthly/yearly trends |

## Progressive Loading for Large Datasets

For datasets larger than 100,000 bars (e.g., multi-year 1-minute data), the validator uses **progressive loading** to ensure fast startup:

### How It Works

1. **Quick Start (<2 seconds)**: The validator loads a random 20K-bar window immediately
2. **Background Loading**: Additional windows are loaded in the background while you work
3. **Diverse Coverage**: Windows are distributed across the dataset for market regime diversity

### User Experience

On startup with a large file, you'll see:

```
============================================================
Lightweight Swing Validator
============================================================
Data file:   data/es-1m-6years.csv
Resolution:  1m
Total bars:  6.2M
Date range:  2018-01-02 to 2024-12-01

Large dataset detected (6.2M bars)
Using progressive loading for fast startup...
(Additional time windows will load in background)

Initialization: 1.43s
Server:         http://127.0.0.1:8000
============================================================
```

### Window Switching

In the browser interface:
- **Window Selector**: A dropdown in the header shows available time windows
- **Loading Indicator**: Shows background loading progress (e.g., "Loading: 45%")
- **Next Window Button (→)**: Click to rotate through different time periods
- **Window Dates**: Each window shows its date range (e.g., "Jan 15, '24 - Feb 3, '24")

As background loading completes, more windows become available in the dropdown.

### Benefits

- **Immediate validation**: Start validating within seconds, even with 6M+ bars
- **Regime coverage**: Automatic sampling across different market conditions
- **Random start**: Each session begins at a different window for variety
- **Full access**: All windows eventually available for comprehensive validation

## The Validation Workflow

1. **View Sample**: The tool displays a random time interval with OHLC chart
2. **Review Swings**: Up to 3 detected swing candidates are shown with markers
3. **Vote**: Click Valid/Invalid/Skip for each swing
4. **Overall Assessment**: Answer "Did we find the right swings?"
5. **Submit & Next**: Move to the next random interval

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1`, `2`, `3` | Cycle vote for swing 1/2/3 |
| `Y` | Overall vote: Yes |
| `N` | Overall vote: No |
| `Enter` | Submit and get next sample |
| `Escape` | Skip current sample |

## API Endpoints

The validator exposes a REST API:

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/sample` | GET | Get random validation sample |
| `/api/sample?scale=M` | GET | Get sample for specific scale |
| `/api/vote` | POST | Submit votes for a sample |
| `/api/stats` | GET | Get session statistics |
| `/api/data-summary` | GET | Get loaded data summary |
| `/api/export/csv` | GET | Export results as CSV |
| `/api/export/json` | GET | Export results as JSON |

### Progressive Loading Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/windows` | GET | List all data windows with status |
| `/api/windows/{id}` | GET | Switch to specific window |
| `/api/windows/next` | POST | Switch to next ready window |
| `/api/loading-status` | GET | Get background loading progress |

## Session Files

Validation results are saved to `validation_results/session_{timestamp}.json` containing:
- Session metadata
- All votes and comments
- Statistics by scale

---

# Swing Validation Harness

The Swing Validation Harness is an interactive tool for validating swing detection logic across historical market data. It provides a 4-panel visualization showing swing activity at four structural scales (S, M, L, XL) with Fibonacci level overlays, enabling systematic expert review of detection accuracy.

## Quick Start

### Prerequisites
- Python 3.8+ with virtual environment
- Matplotlib with TkAgg backend
- Historical OHLC data in `Data/Historical/` directory

### Activate Environment
```bash
cd /path/to/fractal-market-simulator
source venv/bin/activate
```

### Discover Available Data
```bash
# See what data is available
python3 -m src.visualization_harness.main list-data --symbol ES

# Get detailed file information
python3 -m src.visualization_harness.main list-data --symbol ES --resolution 1m --verbose
```

### Launch Validation Session
```bash
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31
```

## What You'll See

### Terminal Output
After initialization, you'll see:
1. Data loading summary (files loaded, bar count, date range)
2. Scale calibration results (S, M, L, XL point boundaries)
3. Session startup banner with quick-start instructions
4. The `validation>` prompt for interactive commands

### Visualization Window
A matplotlib window appears with four panels in a 2x2 grid:
- **Top-left (S)**: Small-scale swings (short timeframe)
- **Top-right (M)**: Medium-scale swings
- **Bottom-left (L)**: Large-scale swings
- **Bottom-right (XL)**: Extra-large swings (long timeframe)

Each panel displays:
- OHLC candlesticks for price action
- Horizontal Fibonacci level lines from active swings
- A swing body indicator on the left margin
- Event markers for completions/invalidations

## CLI Commands

### Playback Control

| Command | Action |
|---------|--------|
| `play` | Start auto-playback (pauses on major events) |
| `play fast` | Fast playback (skips minor events) |
| `pause` | Pause playback |
| `step` | Advance one step |
| `step N` | Advance N steps |
| `jump <idx>` | Jump to bar index |
| `speed <mult>` | Set speed multiplier (e.g., 2.0) |
| `status` | Show current position and state |

### Validation Actions

| Command | Action |
|---------|--------|
| `log accuracy` | Log swing identification issue |
| `log level` | Log Fibonacci level problem |
| `log event` | Log completion/invalidation issue |
| `log consistency` | Log multi-scale relationship problem |
| `log <type> <desc>` | Log issue with inline description |

### Session Management

| Command | Action |
|---------|--------|
| `help` / `h` / `?` | Show command reference |
| `quit` / `q` | End session and save findings |

## Keyboard Shortcuts

Click on the matplotlib window to give it focus, then use:

### Playback
| Key | Action |
|-----|--------|
| SPACE | Toggle play/pause |
| RIGHT | Step forward one bar |
| F | Step forward 1 hour (60 bars) |
| G | Step forward 4 hours (240 bars) |
| D | Step forward 1 day (1440 bars) |
| UP | Double playback speed |
| DOWN | Halve playback speed |
| R | Reset to beginning |
| H | Show keyboard help in terminal |

### Layout
| Key | Action |
|-----|--------|
| 1 | Expand S-scale panel |
| 2 | Expand M-scale panel |
| 3 | Expand L-scale panel |
| 4 | Expand XL-scale panel |
| 0 or ESC | Return to quad layout |
| Click panel | Toggle expand/collapse |

### Swing Visibility
| Key | Action |
|-----|--------|
| V | Cycle visibility mode (All -> Single -> Recent -> All) |
| [ | Previous swing (in Single mode) |
| ] | Next swing (in Single mode) |
| A | Toggle show all swings (bypass 5-swing cap) |

## Advanced Usage

### Reference Period for Pre-Calibration

Use `--playback-start` to specify when playback begins. Data between `--start` and `--playback-start` is used to calibrate swing state before you start watching:

```bash
# Use Jan-Mar 2020 as reference, start playback from April
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01
```

This is useful when you want to observe "mature" swing behavior without waiting through initialization.

### Timeframe-Based Stepping

Use `--step-timeframe` to advance by larger time chunks instead of 1-minute bars:

```bash
# Step by 60 minutes (1 hour) at a time
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31 \
  --step-timeframe 60
```

Options: 1, 5, 15, 30, 60, 240 minutes.

### Verbose Mode

Add `--verbose` for detailed progress logging:

```bash
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31 --verbose
```

Shows:
- Which data files were loaded
- Periodic progress reports during playback
- Major event notifications

### Combined Example

```bash
# Full-featured validation session
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-06-01 \
  --playback-start 2020-04-01 \
  --step-timeframe 60 \
  --verbose
```

## Typical Workflows

### Manual Step-by-Step Review

Best for detailed examination of specific periods:

```
validation> jump 1000       # Go to bar 1000
validation> step            # Advance one bar
validation> step            # Watch swing updates
validation> log accuracy Swing high detected too early at bar 1002
validation> step 10         # Skip ahead 10 bars
```

### Auto-Play with Event Pauses

Best for scanning for interesting patterns:

```
validation> play            # Start auto-advance
[system pauses on major events]
validation> log level 1.618 extension looks incorrect
validation> play            # Resume
```

### Quick Scan Mode

Best for rapid overview of extended periods:

```
validation> play fast       # Fast forward
[watch visualization for obvious issues]
validation> pause           # Stop at interesting point
validation> step            # Fine-grained review
```

## Understanding the Visualization

### Panel Layout

Each panel shows one scale (S, M, L, XL) with its own timeframe aggregation:
- **S (Small)**: Fastest timeframe, shows micro-structure
- **M (Medium)**: Intermediate swings
- **L (Large)**: Major structural moves
- **XL (Extra Large)**: Macro market structure

### Swing Body Indicator

On the left margin of each panel:
- Vertical colored bar represents the swing's price range (high to low)
- Green = Bull swing (upward)
- Red = Bear swing (downward)
- "H" label at swing high, "L" label at swing low

### Fibonacci Levels

Horizontal lines show key price levels relative to the reference swing:
- **0**: Swing low (bull) or swing high (bear)
- **0.382, 0.5, 0.618**: Retracement levels
- **1.0**: Swing high (bull) or swing low (bear)
- **1.382, 1.5, 1.618**: Extension levels
- **2.0**: Completion level (swing is "done")

### Picture-in-Picture (PiP)

When the swing body scrolls off the left edge of the panel, a small inset appears in the upper-left corner showing:
- Schematic swing body with direction
- Key levels (0, 0.5, 1.0, 1.618, 2.0)
- High and low price labels

## Scale-Specific Validation Rules

The system uses different invalidation rules for different scales:

### S/M Scales (Strict)
- Bull swing: Invalid if price ever trades below swing low
- Bear swing: Invalid if price ever trades above swing high

### L/XL Scales (Soft)
- More tolerance for noise and wicks
- Deep threshold: 15% of swing size beyond the boundary
- Soft threshold: 10% on close price

This reflects market reality where larger structures can absorb more volatility.

## Session Files

Validation sessions are automatically saved to `validation_sessions/` directory:
- `{session_id}.json` contains session metadata and logged issues
- Sessions can be resumed if the application restarts

## Troubleshooting

### No matplotlib window appears
1. Ensure matplotlib is installed: `pip install matplotlib`
2. Verify TkAgg backend: Add `matplotlib.use('TkAgg')` before any pyplot imports
3. Check you're not in a headless/SSH environment

### Date range errors
```bash
# Check what dates are available
python3 -m src.visualization_harness.main list-data --symbol ES --resolution 1m --verbose
```
Adjust `--start` and `--end` to overlap with available data.

### Initialization hangs
- Large datasets (100K+ bars) take time to calibrate
- Use `--verbose` to monitor progress
- Consider smaller date ranges or using `--playback-start` for pre-calibration

### Keyboard shortcuts not working
- Click on the matplotlib window to give it focus
- The terminal must not be blocking input

## Issue Types Reference

When logging issues, use these types:

| Type | Use For |
|------|---------|
| `accuracy` | Swing highs/lows identified incorrectly |
| `level` | Fibonacci level computation errors |
| `event` | Completion/invalidation timing issues |
| `consistency` | Multi-scale relationship problems |
| `performance` | Response time or memory issues |

## Example Session

```bash
$ python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m \
    --start 2024-01-15 --end 2024-01-20 --verbose

Loading ES 1m data from 2024-01-15 to 2024-01-20...
Loaded 3,450 bars from 2 files

Scale calibration complete:
  S: 0-25 points (1m resolution)
  M: 25-45 points (5m resolution)
  L: 45-90 points (15m resolution)
  XL: 90+ points (60m resolution)

╔════════════════════════════════════════════════════════════╗
║           VALIDATION SESSION STARTED                       ║
║                                                            ║
║  Type 'help' for commands, 'quit' to exit                 ║
║  Click matplotlib window and use keyboard shortcuts        ║
╚════════════════════════════════════════════════════════════╝

validation> step 100
Stepped to bar 300

validation> play
Playing... (press SPACE in window to pause)

[Auto-paused: MAJOR event - L scale completion at bar 423]

validation> log level The 1.618 extension seems off by ~2 points

validation> play
Playing...

validation> quit
Session saved to validation_sessions/abc123.json
Logged 1 issue(s)
```

## Next Steps

After validation, review logged issues in the session JSON files. Issues are categorized by type and severity, making it easy to prioritize fixes to the swing detection logic.

The goal is to establish expert confidence in the detection foundation before proceeding to the market data generator phase.
