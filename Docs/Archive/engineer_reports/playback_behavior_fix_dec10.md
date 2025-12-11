# Historical Harness Playback Behavior Fix

**Issue:** #10
**Date:** December 10, 2025
**Status:** Fixed

## Summary

Implemented two enhancements to the validation harness to improve usability for swing detection validation:

1. **Reference Period Support** - Separate calibration window from playback start
2. **Timeframe-Based Stepping** - Playback speed tied to displayed timeframes

## Problem Description

### Issue 1: Reference Period vs Playback Start
- Previously, `--start` and `--end` defined both the data range AND the playback start point
- Users couldn't pre-calibrate swing state before watching playback
- Made it difficult to observe mature swing behavior going forward

### Issue 2: Playback Speed Tied to 1m Input Bars
- Each step advanced by 1 source bar (1 minute) regardless of displayed timeframes
- When viewing 1h/4h panels, visible candle updates were extremely slow
- Made the harness feel unresponsive for higher-timeframe validation

## Solution

### New CLI Parameters

```bash
python3 -m src.cli.main validate \
  --symbol ES \
  --resolution 1m \
  --start 2020-01-01 \
  --end 2020-05-01 \
  --playback-start 2020-04-01 \   # NEW: Start playback from here
  --step-timeframe 60              # NEW: Step by 60-minute chunks
```

### --playback-start

- Defines when playback begins after calibration
- Data from `--start` to `--playback-start` is used as reference period for swing calibration
- Playback starts from `--playback-start` with fully mature swing state
- If not specified, backward-compatible behavior (first 200 bars for calibration)

### --step-timeframe

- Timeframe for playback stepping in minutes (choices: 1, 5, 15, 30, 60, 240)
- Each "step" command advances by this many minutes of market time
- Auto-play also advances by this many bars per tick
- Default: smallest displayed timeframe (S scale aggregation, typically 1m)

## Implementation Details

### Files Modified

1. **src/cli/main.py**
   - Added `--playback-start` and `--step-timeframe` CLI parameters
   - Updated ValidationHarness to pass parameters to core harness
   - Enhanced startup message to show reference period and step size info

2. **src/cli/harness.py**
   - Added `playback_start_idx` and `step_timeframe` constructor parameters
   - Modified `_initialize_analysis_components()` to use custom init window
   - Modified `_initialize_playback_components()` to calculate step size
   - Updated step command to advance by configured number of bars
   - Updated help text to show current step size

3. **src/playback/controller.py**
   - Added `step_size` parameter to constructor
   - Modified `_auto_play_loop()` to step by `step_size` bars per tick

### Architecture Changes

```
Before:
  --start → First 200 bars for calibration → Playback from bar 200
  step → 1 source bar (1m) per step

After:
  --start to --playback-start → All bars for calibration
  --playback-start → Playback begins here (mature swing state)
  --step-timeframe → N source bars per step/tick
```

## Usage Examples

### Pre-calibrated Playback
```bash
# Use Jan-Mar 2020 as reference period, start watching from April
python3 -m src.cli.main validate \
  --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01
```

### Faster Visual Progress for Higher Timeframes
```bash
# Step by 60 minutes (1 hour) at a time
python3 -m src.cli.main validate \
  --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31 \
  --step-timeframe 60
```

### Combined Usage
```bash
# Reference period + hourly stepping
python3 -m src.cli.main validate \
  --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-06-01 \
  --playback-start 2020-04-01 \
  --step-timeframe 60
```

## Testing

- All existing playback controller tests pass (23/23)
- Syntax validation passed for all modified files
- CLI help updated to document new parameters

## Backward Compatibility

- Default behavior unchanged when new parameters not specified
- `--playback-start` defaults to None (use first 200 bars for calibration)
- `--step-timeframe` defaults to smallest displayed timeframe (typically 1m)
