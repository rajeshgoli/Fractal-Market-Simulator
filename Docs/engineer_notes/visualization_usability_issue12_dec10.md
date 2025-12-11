# Visualization Usability & Performance (Issue #12)

**Engineer:** Claude Code
**Date:** 2025-12-10
**Type:** Feature Implementation + Bug Fixes
**Status:** Complete
**Commits:** `532e7f1`, `e48438a`

## Context

GitHub Issue #12 requested four visualization enhancements to improve the validation workflow:
1. **Playback speed above 32x** - Rendering bottleneck prevented meaningful high-speed playback
2. **Expandable quadrants** - 4-panel layout was cramped, no way to focus on single scale
3. **PiP for off-screen swings** - Reference swing context lost when body scrolls out of view
4. **Swing visibility toggle** - Overlapping swings/levels hard to read with multiple active swings

The core problem was that the visualization became difficult to use during extended validation sessions, especially when analyzing specific scales or tracking swings over long time periods.

## Change Summary

### New Files

**`src/visualization/layout_manager.py`**
- `LayoutMode` enum: QUAD (2x2 equal) and EXPANDED (one panel ~90%)
- `PanelGeometry` dataclass: row/col positions with `is_primary` and `is_mini` flags
- `LayoutManager` class with `toggle_expand()`, `transition_to()`, and `create_gridspec()`
- Uses 10x10 GridSpec for fine layout control in EXPANDED mode

**`src/visualization/pip_inset.py`**
- `PiPConfig` dataclass: width/height percent, corner position, border styling
- `PiPInsetManager` class that creates matplotlib inset axes when swing body scrolls off-screen
- Shows simplified swing representation: vertical body rectangle + key levels (0, 1.0, 2.0)
- Uses `mpl_toolkits.axes_grid1.inset_locator.inset_axes()` for positioning

**`src/visualization/swing_visibility.py`**
- `VisibilityMode` enum: ALL, SINGLE, RECENT_EVENT
- `SwingVisibilityState` dataclass: per-scale mode and selection tracking
- `SwingVisibilityController` class with mode cycling, swing selection, opacity calculation
- Tracks recent events per swing for RECENT_EVENT mode highlighting

### Modified Files

**`src/visualization/config.py`**
- Added `enable_frame_skipping: bool = True` to RenderConfig
- Added `min_render_interval_ms: int = 60` (~16 FPS max)

**`src/playback/config.py`**
- Added render performance fields to `PlaybackStatus`:
  - `effective_speed: float = 1.0` - Actual achieved speed multiplier
  - `frames_skipped: int = 0` - Count for diagnostics
  - `render_limited: bool = False` - True if speed capped by rendering

**`src/visualization/renderer.py`**
- Added imports for new modules: `PiPInsetManager`, `SwingVisibilityController`, `LayoutManager`
- Added instance variables: `pip_manager`, `swing_visibility`, `layout_manager`
- Added frame skipping in `update_display()`: tracks `_last_render_time`, `_pending_update`, `_frames_skipped`
- Added `_apply_layout()` method for GridSpec management
- Added `expand_panel()`, `restore_quad_layout()`, `toggle_panel_expand()` methods
- Modified `render_panel()` to integrate visibility filtering and PiP updates
- Modified `draw_fibonacci_levels()` to accept `opacity` parameter
- Added `_get_primary_swing()` helper for PiP
- Added `get_render_stats()` method for diagnostics
- Added visibility control methods: `cycle_visibility_mode()`, `cycle_next_swing()`, etc.

**`src/visualization/keyboard_handler.py`**
- Updated docstring with new keyboard shortcuts
- Added key handlers: `1-4` (expand panels), `0/ESC` (restore quad), `V` (cycle visibility), `[/]` (cycle swings)
- Added click handler for panel toggle via `button_press_event`
- Added visibility control methods: `_cycle_visibility_mode()`, `_cycle_next_swing()`, `_cycle_previous_swing()`
- Updated `_show_help()` with swing visibility section

## Keyboard Shortcuts

| Key | Action | Notes |
|-----|--------|-------|
| `1-4` | Expand panel 1/2/3/4 | Panel takes ~90% of space |
| `0` or `ESC` | Return to quad layout | Standard 2x2 view |
| Click panel | Toggle expand/collapse | Same as pressing panel number |
| `V` | Cycle visibility mode | All -> Single -> Recent Event -> All |
| `[` | Previous swing | In Single mode only |
| `]` | Next swing | In Single mode only |

## Frame Skipping Design

The rendering bottleneck was `render_panel()` clearing and recreating 1500+ matplotlib artists per panel every frame. Frame skipping addresses this without modifying the rendering architecture:

- **Config**: `min_render_interval_ms = 60` (~16 FPS max)
- **Logic**: If time since last render < interval, store update as `_pending_update` and return
- **Latest state**: When interval allows, use `_pending_update` to render latest state
- **Diagnostics**: `get_render_stats()` returns skip rate for monitoring

This allows high playback speeds (32x, 64x, 128x) without the display becoming a slideshow.

## Layout Manager Design

EXPANDED mode uses a 10x10 GridSpec for precise control:
- **Primary panel**: rows 0-7, cols 0-8 (72% of figure area)
- **Mini panels**: stacked vertically in col 9, ~2-3 rows each
- Mini panels show scale label only, simplified rendering

Transition between modes:
1. Clear all existing axes via `ax.remove()`
2. Create new GridSpec for target mode
3. Add subplots with geometry from `PanelGeometry`
4. Configure appearance based on `is_mini` flag

## PiP Inset Design

PiP visibility logic:
1. Find bar indices for swing high/low timestamps in aggregated bar space
2. Get the later of high_idx/low_idx (swing body end)
3. If swing body end < view_window.start_idx, show PiP

PiP rendering (simplified for quick recognition):
- Vertical rectangle: swing body (high-low range) with bull/bear color
- Horizontal dashes: key levels (0, 1.0, 2.0) only
- Gold border, dark background, "Ref (Bull/Bear)" title
- Fixed position: upper-left corner of panel

## Swing Visibility Design

Three modes with different opacity behaviors:

| Mode | Selected | Others | Use Case |
|------|----------|--------|----------|
| ALL | 1.0 | 1.0 | Default view, all swings visible |
| SINGLE | 1.0 | 0.0 | Focus on one swing, cycle with [/] |
| RECENT_EVENT | 1.0 | 0.3 | Highlight swing with recent activity |

Event tracking:
- `record_event()` updates `_swing_event_times` with current timestamp
- RECENT_EVENT mode queries most recent swing per scale
- State persists until mode change or reset

## Usage

```bash
# Run validation with new features enabled automatically
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01 --step-timeframe 60

# In visualization window:
# - Press 1 to expand S-scale panel
# - Press V to cycle to Single mode
# - Press ] to cycle through swings
# - Press 0 to return to quad layout
```

## Technical Notes

- All matplotlib operations remain on main thread (no threading changes)
- Layout transitions use `figure.clear()` pattern to avoid artist conflicts
- PiP uses `inset_axes()` which handles coordinate transforms automatically
- Visibility filtering applied before rendering, not via artist alpha (cleaner)
- Frame skipping stores latest state, never loses user's position

## Test Results

- All 15 `test_visualization_renderer.py` tests pass
- All 23 `test_playback_controller.py` tests pass
- Functional tests for new components pass
- Import verification passes for all new modules

## Scope

This change adds UI improvements. It does not modify:
- Core analysis algorithms (swing detection, event detection)
- Data loading or processing
- Existing CLI command interface
- Playback controller logic (only status fields added)

## File Locations

| Type | Path |
|------|------|
| New: Layout Manager | `src/visualization/layout_manager.py` |
| New: PiP Insets | `src/visualization/pip_inset.py` |
| New: Visibility | `src/visualization/swing_visibility.py` |
| Modified: Renderer | `src/visualization/renderer.py` |
| Modified: Keyboard | `src/visualization/keyboard_handler.py` |
| Modified: Config | `src/visualization/config.py` |
| Modified: Status | `src/playback/config.py` |
| Modified: Harness | `src/cli/harness.py` |

---

## Bug Fixes (Post-Implementation)

After initial implementation, user testing revealed three blocking issues that were fixed in subsequent commits.

### Bug Fix 1: Keyboard Shortcuts Not Working (`532e7f1`)

**Problem:** Pressing `1-4`, `V`, `[`, `]` keys produced runtime errors instead of expected behavior.

**Root Cause:** `_initialize_keyboard_handler()` in `harness.py` was not passing `visualization_renderer` to the `KeyboardHandler` constructor, leaving it as `None`.

**Fix:** Added `visualization_renderer=self.visualization_renderer` to the `KeyboardHandler` constructor call in `harness.py` line 245.

### Bug Fix 2: PiP Renders as Giant Candle (`532e7f1`)

**Problem:** PiP inset showed a single oversized candle instead of a schematic swing representation.

**Root Cause:** `_render_swing_in_pip()` used actual price coordinates for Y-axis (e.g., 4000-4100) but fixed coordinates for X (0-1), creating an extremely tall, thin shape that looked like a candle.

**Fix:** Complete rewrite of `_render_swing_in_pip()` to use fully normalized coordinates (0-1 for both axes):
- Swing body: centered rectangle from y=0.1 to y=0.9, x=0.35 with width=0.3
- Added `price_to_y()` helper: maps price from [low, high] to [0.1, 0.9]
- Fib levels (0, 0.5, 1.0, 1.618, 2.0) drawn at relative Y positions
- Level colors: 0=white, 0.5=gray, 1.0=green, 1.618=gold, 2.0=orange
- Price annotations "H:{high}" and "L:{low}" at top/bottom
- All axes/spines hidden (schematic diagram, not chart)

### Bug Fix 3: Main Panel Swing Body Missing (`e48438a`)

**Problem:** Reference swing in main panels appeared as "giant candle" - user expected an abstract geometric object.

**Root Cause:** Main panel only drew Fibonacci levels via `ax.axhline()` (infinite horizontal lines). There was no bounded swing body representation like in PiP.

**Fix:** Added `draw_swing_body()` method to renderer:
- Position: x = -2.5, width = 2 (in reserved left margin)
- Height: spans swing high to swing low prices
- Color: green (#26A69A) for bull, red (#EF5350) for bear
- Labels: "H" at high, "L" at low
- Level markers: solid white lines at 0 and 1 on body
- Extended panel xlim from -0.5 to -4.0 to show swing body area

### Bug Fix 4: Swing Disappears on Layout Transitions (`e48438a`)

**Problem:** Reference swing disappeared when pausing/resuming playback or switching between quad/expanded layouts.

**Root Cause:** `_apply_layout()` cleared all axes and recreated them, but the new axes had no swing data. The renderer didn't cache state for re-rendering.

**Fix:** Implemented state caching and re-render:
- Added cache variables: `_cached_active_swings`, `_cached_recent_events`, `_cached_highlighted_events`
- Extracted rendering logic into `_do_render()` method (can bypass frame skipping)
- Added `_rerender_cached_state()` method
- `expand_panel()` and `restore_quad_layout()` now call `_rerender_cached_state()` after `_apply_layout()`

### Bug Fix 5: constrained_layout Warnings (`e48438a`)

**Problem:** Repeated warnings: "UserWarning: constrained_layout not applied because axes sizes collapsed to zero."

**Root Cause:** `layout='constrained'` was set during figure creation, but dynamic GridSpec manipulation during layout transitions conflicts with constrained_layout.

**Fix:** Removed `layout='constrained'` from `plt.figure()` call. Layout is now fully controlled by manual GridSpec management in `_apply_layout()`.

---

## Lessons Learned

1. **Unit tests don't guarantee integration success** - All component tests passed, but runtime failed because harness.py wasn't passing required parameters.

2. **PiP fix != main panel fix** - User's "giant candle" complaint could refer to PiP OR main panel. The initial fix addressed PiP; user clarification revealed main panel also needed swing body rendering.

3. **Layout transitions destroy matplotlib state** - Artists are tied to specific axes instances. When axes are removed/recreated, artists must be recreated from cached state.

4. **constrained_layout conflicts with dynamic layouts** - Matplotlib's automatic layout managers don't work well with manual GridSpec manipulation during runtime.
