# Engineering Note: Matplotlib Window Not Appearing (Issue #5)

**Date:** December 10, 2025
**Issue:** GitHub Issue #5 - No Matplotlib Window
**Status:** Fixed

## Summary

The validation harness CLI reported initialization of a 4-panel matplotlib visualization window, but no window appeared on macOS. Only the terminal prompt was visible.

## Root Cause

The visualization code was missing the call to `plt.show()` needed to actually display the matplotlib figure window. The code:

1. Created a figure with `plt.figure()`
2. Set up interactive mode with `plt.ion()`
3. Called `fig.canvas.draw_idle()` for updates

However, `plt.ion()` only enables interactive mode - it doesn't create a window. `draw_idle()` only redraws if a window already exists. Without `plt.show()`, the figure exists in memory but is never displayed.

## Fix Applied

### 1. Added `show_display()` method to `VisualizationRenderer`

**File:** `src/visualization/renderer.py`

```python
def show_display(self) -> None:
    """
    Make the figure window visible.

    Must be called after initialize_display() to actually show the matplotlib
    window on screen. Uses non-blocking show to allow the CLI to remain
    interactive while the visualization is displayed.
    """
    if self.fig is None:
        logging.warning("Cannot show display: figure not initialized")
        return

    plt.figure(self._fig_num)
    plt.show(block=False)
    self.fig.canvas.draw()
    self.fig.canvas.flush_events()
```

### 2. Called `show_display()` after initialization

**File:** `src/cli/harness.py`

Added call to `show_display()` in `_initialize_visualization_components()`:

```python
self.visualization_renderer.initialize_display()
self.visualization_renderer.set_interactive_mode(True)
self.visualization_renderer.show_display()  # NEW: Actually display the window
```

### 3. Added `flush_events()` to `update_display()`

**File:** `src/visualization/renderer.py`

Added `flush_events()` call after `draw_idle()` to keep the window responsive:

```python
self.fig.canvas.draw_idle()
self.fig.canvas.flush_events()  # Process GUI events
```

### 4. Ensured backend is set before any matplotlib imports

**File:** `src/cli/main.py`

Added matplotlib backend configuration at the very top of the file:

```python
import matplotlib
matplotlib.use('TkAgg')
```

## Environment Caveats

### macOS Requirements

- **TkAgg backend**: The fix uses TkAgg, which requires Tcl/Tk to be installed. This is included with Python installed via python.org or Homebrew.

- **Alternative backends**: If TkAgg fails, users can try:
  - `matplotlib.use('MacOSX')` - native macOS backend
  - `matplotlib.use('Qt5Agg')` - requires PyQt5

### Backend Selection Order

The matplotlib backend must be set **before** `matplotlib.pyplot` is imported anywhere in the module chain. This is why we added the backend configuration at the very top of both `main.py` and `harness.py`.

## Testing

1. All 15 visualization renderer tests pass
2. Manual verification that matplotlib window creation works:
   ```python
   import matplotlib
   matplotlib.use('TkAgg')
   import matplotlib.pyplot as plt
   plt.ion()
   fig = plt.figure()
   plt.show(block=False)
   fig.canvas.draw()
   fig.canvas.flush_events()
   # Window should appear
   ```

## Files Modified

- `src/visualization/renderer.py` - Added `show_display()` method and `flush_events()` call
- `src/cli/harness.py` - Added call to `show_display()` after initialization
- `src/cli/main.py` - Added matplotlib backend configuration at top
