# Engineer Report: Playback Threading Fix (Issue #7)

**Date:** December 10, 2025
**Issue:** #7 - Playback Fails in Historical Visualization Harness
**Status:** Fixed (Multiple Iterations)

## Problem Summary

The validation harness experienced several threading-related crashes:

1. **`main thread is not in main loop`** - Threading violation with matplotlib
2. **`list.remove(x): x not in list`** - Visual element double-removal
3. **`Tcl_WaitForEvent: Notifier not initialized`** - Tk event loop crash (regression from initial fix)

## Root Cause Analysis

### Error 1: Threading Violation (Initial)

The `PlaybackController` runs auto-playback in a background thread which called `_on_playback_step`, directly invoking `visualization_renderer.update_display()`. Matplotlib GUI operations must execute on the main thread.

### Error 2: Double Removal

The `_clear_panel_artists()` method called `artist.remove()` without checking if artists were still attached, causing removal errors during rapid updates.

### Error 3: Tcl Notifier Crash (Regression)

The initial fix used a background thread for `input()` to enable non-blocking input. However, on macOS with TkAgg backend, running `input()` in a background thread can interfere with Tk's event loop initialization, causing:
```
Tcl_WaitForEvent: Notifier not initialized
zsh: abort
```

## Solution

### Fix 1: Thread-Safe GUI Updates

Implemented a **producer-consumer pattern** using a thread-safe queue:

1. **Background thread (producer):** `_on_playback_step` queues GUI updates instead of calling `update_display()` directly
2. **Main thread (consumer):** Processes pending GUI updates via `_process_pending_gui_updates()`

### Fix 2: Safe Artist Removal

Added `safe_remove()` helper with defensive checks before removing matplotlib artists.

### Fix 3: Select-Based Non-Blocking Input (Final Fix)

Replaced the background input thread with **`select()`-based non-blocking input on the main thread**:

```python
readable, _, _ = select.select([sys.stdin], [], [], 0.05)
if readable:
    char = sys.stdin.read(1)
    # Process character...
```

This approach:
- Keeps all I/O on the main thread (no Tk/threading conflicts)
- Uses a 50ms timeout to allow GUI event processing between input checks
- Accumulates characters into a buffer until newline is received
- Avoids the Tcl notifier initialization issues entirely

**Files modified:**
- `src/cli/harness.py`: `run_interactive()` uses select-based input
- `src/cli/main.py`: `_run_interactive_validation()` uses same pattern
- `src/visualization/renderer.py`: `safe_remove()` in `_clear_panel_artists()`

## Testing

- All 38 playback controller and visualization renderer tests pass
- Harness remains stable at prompt without issuing any commands
- `step` and `play` commands execute without crash

## Architecture Note

The final architecture keeps everything on the main thread with cooperative multitasking:

```
Main Thread Event Loop:
┌─────────────────────────────────────────────┐
│ 1. Process pending GUI updates from queue   │
│ 2. Flush matplotlib events                  │
│ 3. Check stdin with select() (50ms timeout) │
│ 4. If input available, process character    │
│ 5. Loop                                     │
└─────────────────────────────────────────────┘
```

This avoids all threading issues with Tk while maintaining responsive GUI updates during playback.
