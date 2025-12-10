# Playback Controls and Observability (Issue #11)

**Engineer:** Claude Code
**Date:** 2025-12-10
**Type:** Feature Implementation
**Status:** Complete

## Context

GitHub Issue #11 requested three enhancements to the visualization harness:
1. UI-integrated pause/resume control (keyboard shortcuts in matplotlib window)
2. UI-integrated speed and step control (manual stepping, speed adjustment)
3. Improved CLI verbose feedback (periodic progress logging, major event notifications)

The core problem was that the CLI blocks during matplotlib's event loop, making it impossible to issue commands while playback is running. Users needed a way to control playback directly from the visualization window.

## Change Summary

### New Files

**`src/visualization/keyboard_handler.py`**
- `KeyboardHandler` class that connects to matplotlib figure via `mpl_connect('key_press_event', ...)`
- Handles keyboard shortcuts: SPACE (pause/resume), RIGHT (step), UP/DOWN (speed), R (reset), H (help)
- Provides callback mechanism for status updates to harness

**`src/logging/progress_logger.py`**
- `ProgressLogger` class for verbose CLI feedback during playback
- Emits periodic progress reports every N bars (default: 100)
- Logs major events (completions, invalidations) immediately
- Tracks event counts by type for progress summaries

### Modified Files

**`src/visualization/renderer.py`**
- Added `_status_text` field for overlay management
- Added `get_figure()` method to expose figure for external event binding
- Added `update_status_overlay(text)` to display playback state in figure corner

**`src/playback/config.py`**
- Added `SPEED_PRESETS` constant (note: subsequently removed when speed control was changed to unbounded)

**`src/cli/harness.py`**
- Added `verbose` parameter to `__init__`
- Added `keyboard_handler` and `progress_logger` fields
- Added `_initialize_keyboard_handler()` method
- Added `_on_keyboard_action()` callback for status updates
- Integrated progress logger in `_on_playback_step()`
- Updated `_print_help()` with keyboard shortcuts section
- Updated `_cleanup()` to disconnect keyboard handler
- Updated `main()` to pass `verbose=args.verbose` to harness

## Keyboard Shortcuts

| Key | Action | Notes |
|-----|--------|-------|
| SPACE | Toggle pause/resume | Works in AUTO or FAST mode |
| RIGHT | Step forward one bar | Pauses first if playing |
| UP | Double playback speed | No maximum limit |
| DOWN | Halve playback speed | Minimum 0.25x |
| R | Reset to beginning | Resets speed to 1x |
| H | Show keyboard help | Prints shortcuts to console |

## Speed Control Design

Speed adjustment uses exponential scaling (doubling/halving) rather than fixed presets:
- **UP arrow**: Multiplies current speed by 2 (1x → 2x → 4x → 8x → 16x → ...)
- **DOWN arrow**: Divides current speed by 2 (1x → 0.5x → 0.25x minimum)
- **Reset**: Returns to 1x

This allows unlimited speed increase for fast-forwarding through large datasets.

## Verbose Logging Format

**Periodic progress (every 100 bars):**
```
INFO - Progress: bar 500/5000 (10.0%) | timestamp: 2024-10-10 09:35 | events: level_cross_up:12
```

**Major event (immediate):**
```
INFO - MAJOR EVENT [M]: completion at bar 523 - crossed 2.0 on swing a3b4c5d6 @ 4157.50
```

## Usage

```bash
# Run with keyboard controls enabled (automatic)
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-01-15

# Enable verbose progress logging
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-01-15 --verbose
```

**Important:** Click on the matplotlib window to give it keyboard focus before using shortcuts.

## Technical Notes

- Keyboard events fire on matplotlib's main thread (no threading issues)
- Status overlay uses `fig.text()` with bbox for visibility against any background
- Progress logger checks interval on every step call, emits report when threshold reached
- Event subscription uses `on_event()` direct notification rather than polling

## Scope

This change adds UI controls and verbose feedback. It does not modify:
- Core analysis algorithms
- Swing detection logic
- Data loading or processing
- Existing CLI command interface

## Verification

- All imports verified working
- Keyboard handler connects to figure successfully
- Speed control tested: doubling/halving works correctly, no maximum
- Progress logger emits reports at configured interval
- Status overlay displays in figure corner
