# Engineer Report: Playback Threading Fix (Issue #7)

**Date:** December 10, 2025
**Issue:** #7 - Playback Fails in Historical Visualization Harness
**Status:** Fixed

## Problem Summary

When running the validation harness and issuing the `play` command, two critical errors occurred:

1. **`main thread is not in main loop`** - Threading violation with matplotlib
2. **`list.remove(x): x not in list`** - Visual element double-removal

These errors made playback non-functional, blocking the validation workflow.

## Root Cause Analysis

### Error 1: Threading Violation

**Location:** `src/cli/harness.py` and `src/playback/controller.py`

The `PlaybackController` runs auto-playback in a background thread (`_auto_play_loop` at line 321 in controller.py). This thread calls `_on_playback_step` which directly invoked `visualization_renderer.update_display()`.

**Problem:** Matplotlib GUI operations must execute on the main thread. When `update_display()` was called from the background playback thread, matplotlib raised:
```
main thread is not in main loop
```

### Error 2: Double Removal

**Location:** `src/visualization/renderer.py` at `_clear_panel_artists()`

The `_clear_panel_artists()` method called `artist.remove()` on matplotlib artists without checking if they were still attached to an axes. When rapid updates occurred or artists were already removed, this caused:
```
list.remove(x): x not in list
```

## Solution

### Fix 1: Thread-Safe GUI Updates

Implemented a **producer-consumer pattern** using a thread-safe queue:

1. **Background thread (producer):** `_on_playback_step` now queues GUI updates instead of calling `update_display()` directly:
   ```python
   self._update_queue.put({
       'bar_idx': bar_idx,
       'active_swings': active_swings,
       'events': update_result.events,
       ...
   })
   ```

2. **Main thread (consumer):** `run_interactive()` now uses a non-blocking input loop that:
   - Processes pending GUI updates via `_process_pending_gui_updates()`
   - Flushes matplotlib events via `fig.canvas.flush_events()`
   - Collects user input from a background thread (avoiding `input()` blocking)

**Files modified:**
- `src/cli/harness.py`: Added `_update_queue`, `_process_pending_gui_updates()`, refactored `run_interactive()`
- `src/cli/main.py`: Same pattern applied to `_run_interactive_validation()`

### Fix 2: Safe Artist Removal

Added defensive checks before removing matplotlib artists:

```python
def safe_remove(artist):
    try:
        if hasattr(artist, 'remove'):
            if hasattr(artist, 'axes') and artist.axes is not None:
                artist.remove()
            elif hasattr(artist, 'figure') and artist.figure is not None:
                artist.remove()
    except (ValueError, AttributeError):
        pass  # Already removed
```

**File modified:** `src/visualization/renderer.py` at `_clear_panel_artists()`

## Testing

- All 38 playback controller and visualization renderer tests pass
- The CLI harness test failures are pre-existing (test data issues), unrelated to this fix

## Verification

To verify the fix:

```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2023-01-01 --end 2023-01-31 --verbose
```

Then at the `validation>` prompt:
1. Type `play` - playback should start without errors
2. The matplotlib window should update as bars advance
3. Type `pause` to stop playback
4. No threading or removal errors should appear

## Architecture Note

This fix follows the standard pattern for GUI applications with background threads:

```
Background Thread          Queue              Main Thread
     |                       |                     |
     | compute data         |                     |
     |----> put(update) --->|                     |
     |                       |<---- get() <-------|
     |                       |                     | update GUI
```

The main thread maintains exclusive ownership of GUI updates, while background threads handle data processing and queue updates for safe consumption.
