# Visualization Usability & Performance (Issue #12)

**Engineer:** Claude Code
**Date:** 2025-12-10
**Type:** Feature Implementation
**Status:** Complete

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
