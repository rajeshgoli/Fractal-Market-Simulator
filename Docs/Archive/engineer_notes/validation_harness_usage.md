# Validation Harness Usage Guide

**Engineer:** Claude Code
**Date:** 2025-12-10
**Type:** Usage Documentation
**Status:** Complete

## Overview

The validation harness is an interactive tool for systematic validation of swing detection logic across historical market data. It combines data loading, swing analysis, and a 4-panel visualization into a single interactive session.

## What the Validate Command Does

When you run:
```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11 --verbose
```

The system performs these steps:

1. **Data Discovery**: Finds historical data files matching the symbol and resolution
2. **Date Filtering**: Loads only bars within the specified date range
3. **Duplicate Handling**: Removes duplicate timestamps (common with overlapping data files)
4. **Scale Calibration**: Computes S, M, L, XL swing size boundaries from the data
5. **Swing Initialization**: Initializes swing state manager with first 200 bars
6. **Visualization Launch**: Opens a matplotlib window with 4 synchronized panels
7. **Interactive REPL**: Presents a `validation>` prompt for expert review

## What You Should See

### CLI Output
After initialization, you'll see:
- Data loading summary (files loaded, bars, date range)
- Scale calibration results (S, M, L, XL point boundaries)
- A "VALIDATION SESSION STARTED" banner with quick-start instructions
- The `validation>` prompt

### Matplotlib Window
A separate window appears with:
- **4 panels** showing S, M, L, XL scales (2x2 grid)
- **OHLC candlesticks** for price action
- **Fibonacci level overlays** from active swings
- **Event markers** for completions, invalidations, and level crossings

## Interactive Commands

### Playback Commands
| Command | Description |
|---------|-------------|
| `play` | Start auto-playback (pauses on major events) |
| `play fast` | Start fast playback mode |
| `pause` | Pause playback |
| `step` | Step forward one bar |
| `step N` | Step forward N bars |
| `jump <idx>` | Jump to specific bar index |
| `speed <mult>` | Set playback speed (e.g., 2.0 for 2x) |
| `status` | Show current position and state |

### Validation Commands
| Command | Description |
|---------|-------------|
| `log <type>` | Log a validation issue at current bar |
| `log <type> <desc>` | Log issue with inline description |
| `help` / `h` / `?` | Show full help message |
| `quit` / `exit` / `q` | End validation session |

### Issue Types for `log` Command
- `accuracy` - Swing identification errors (wrong high/low detection)
- `level` - Fibonacci level computation problems
- `event` - Completion/invalidation trigger issues
- `consistency` - Multi-scale relationship problems
- `performance` - Response time or memory issues

## Typical Workflows

### Manual Step-by-Step Review
```
validation> step 50        # Jump ahead 50 bars to interesting area
validation> step           # Advance one bar at a time
validation> step           # Watch swing updates in visualization
validation> log accuracy Swing high detected too early
validation> step
```

### Auto-Play with Event Pauses
```
validation> play           # Start auto-advance
[system auto-pauses on major events like completions]
validation> log level 1.618 level looks incorrect
validation> play           # Resume playback
```

### Quick Scan
```
validation> play fast      # Fast forward through data
[watch for obvious issues in visualization]
validation> pause          # Stop at point of interest
validation> jump 1500      # Go to specific bar
validation> step           # Fine-grained review
```

## Duplicate Timestamp Handling

When loading data from multiple files with overlapping date ranges, the system:

1. Loads all bars from all matching files
2. Sorts by timestamp
3. Removes duplicates (keeps first occurrence for each timestamp)
4. Reports an aggregated summary (not individual warnings per file)

This is expected behavior when data files cover overlapping periods. The summary shows:
- How many files were loaded
- Total bars before deduplication
- Number of duplicates removed
- Final unique bar count

## Troubleshooting

### No matplotlib window appears
- Check that matplotlib is installed: `pip install matplotlib`
- Ensure you're not running in a headless environment
- Try setting `DISPLAY` environment variable if on Linux

### Date range errors
- Run `python3 -m src.cli.main list-data --symbol ES --resolution 1m --verbose` to see available dates
- Ensure start/end dates overlap with available data

### Performance issues
- Use `--verbose` to monitor loading progress
- Reduce date range for faster initialization
- Large datasets may take several seconds to calibrate

## Session Files

Validation sessions are saved to `validation_sessions/` directory:
- `{session_id}.json` - Session metadata and logged issues
- Use `--output` flag to export findings to a specific file on exit

## Related Documentation

- `CLAUDE.md` - Project overview and development commands
- `cli_enhancements_dec10.md` - Data discovery command details
- `Docs/Product/product_next_steps_dec10.md` - Validation phase objectives
