# Swing Validation Harness - User Guide

## Overview

The Swing Validation Harness is an interactive tool for validating swing detection logic across historical market data. It provides a 4-panel visualization showing swing activity at four structural scales (S, M, L, XL) with Fibonacci level overlays, enabling systematic expert review of detection accuracy.

## Quick Start

### Prerequisites
- Python 3.8+ with virtual environment
- Matplotlib with TkAgg backend
- Historical OHLC data in `Data/Historical/` directory

### Activate Environment
```bash
cd /path/to/Market\ generator
source venv/bin/activate
```

### Discover Available Data
```bash
# See what data is available
python3 -m src.cli.main list-data --symbol ES

# Get detailed file information
python3 -m src.cli.main list-data --symbol ES --resolution 1m --verbose
```

### Launch Validation Session
```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m \
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
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01
```

This is useful when you want to observe "mature" swing behavior without waiting through initialization.

### Timeframe-Based Stepping

Use `--step-timeframe` to advance by larger time chunks instead of 1-minute bars:

```bash
# Step by 60 minutes (1 hour) at a time
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31 \
  --step-timeframe 60
```

Options: 1, 5, 15, 30, 60, 240 minutes.

### Verbose Mode

Add `--verbose` for detailed progress logging:

```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31 --verbose
```

Shows:
- Which data files were loaded
- Periodic progress reports during playback
- Major event notifications

### Combined Example

```bash
# Full-featured validation session
python3 -m src.cli.main validate --symbol ES --resolution 1m \
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
python3 -m src.cli.main list-data --symbol ES --resolution 1m --verbose
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
$ python3 -m src.cli.main validate --symbol ES --resolution 1m \
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
