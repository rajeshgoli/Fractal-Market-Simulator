# Stability Audit: Visualization State Management

**Date:** December 11, 2025
**Phase:** 1.3
**Status:** Complete

---

## Executive Summary

This audit documents stability issues related to layout transitions, pause/resume operations, frame skipping, and keyboard handler state synchronization in the visualization harness. Four categories of issues were identified, ranging from Medium to High severity.

---

## Issue Catalog

### Issue 1: Layout Transition State Loss

**Description:**
When toggling between QUAD and EXPANDED layouts, swing and event data can fail to render properly. The layout transition clears all axes and artists, then attempts to restore from cached state.

**Steps to Reproduce:**
1. Start visualization with multiple active swings
2. Press `1` to expand S-scale panel
3. Observe swings may not render in expanded view
4. Press `0` to return to quad layout
5. Swings may appear/disappear inconsistently

**Severity:** HIGH

**Affected Files:**
- `src/visualization/renderer.py:124-174` (`_apply_layout`)
- `src/visualization/renderer.py:230-244` (`_rerender_cached_state`)
- `src/visualization/layout_manager.py`

**Root Cause Analysis:**
```python
# In _apply_layout(), all axes are cleared:
for panel_idx in list(self.axes.keys()):
    self.axes[panel_idx].remove()
self.axes.clear()
self.artists.clear()

# Then _rerender_cached_state() is called, but it relies on cached data
# that may be incomplete or stale during playback
```

The problem is twofold:
1. `_cached_active_swings` only stores the last frame's swings, not complete history
2. During rapid playback, the cache can be updated by the playback thread while `_rerender_cached_state()` is executing

**Recommendations:**
1. Add thread lock around cached state access
2. Deep copy cached state before re-rendering to avoid race conditions
3. Consider storing view window state per panel to restore scroll position

---

### Issue 2: Pause/Resume State Inconsistencies

**Description:**
The playback controller's pause/resume mechanism uses threading events that can lead to race conditions between the UI thread and playback thread.

**Steps to Reproduce:**
1. Start auto-playback at high speed (e.g., 8x)
2. Rapidly press SPACE to toggle pause/resume
3. Status overlay may show incorrect state
4. Events may be missed or duplicated

**Severity:** MEDIUM

**Affected Files:**
- `src/playback/controller.py:122-146` (pause/resume methods)
- `src/cli/harness.py:409-464` (`_on_playback_step`)

**Root Cause Analysis:**
```python
# In controller.py, pause is set via threading event:
def pause_playback(self, reason: Optional[str] = None):
    if self.state == PlaybackState.PLAYING:
        self._pause_requested.set()
        self.state = PlaybackState.PAUSED  # State updated immediately

# But in _auto_play_loop(), the check happens later:
if self._pause_requested.is_set():
    self.state = PlaybackState.PAUSED  # Redundant state set
    while self._pause_requested.is_set() and not self._stop_event.is_set():
        time.sleep(0.1)
```

The race condition occurs because:
1. `pause_playback()` sets state to PAUSED immediately
2. The playback thread may be mid-step and queue another GUI update
3. This update shows PLAYING state while actual state is PAUSED

**Recommendations:**
1. Use a single source of truth for state (the threading event, not the enum)
2. Add state change callback to notify UI immediately when state changes
3. Use thread-safe state transitions with locks

---

### Issue 3: Frame Skipping Edge Cases

**Description:**
The frame skipping mechanism stores only the latest pending update. During high-speed playback, intermediate states are lost, causing visual discontinuities.

**Steps to Reproduce:**
1. Start playback at 32x speed
2. Observe that swings appear to "jump" rather than animate smoothly
3. Events may not trigger visual markers if they occur in skipped frames
4. Press `D` (step 1 day) during playback

**Severity:** MEDIUM

**Affected Files:**
- `src/visualization/renderer.py:266-314` (`update_display` with frame skipping)
- `src/cli/harness.py:466-496` (`_process_pending_gui_updates`)

**Root Cause Analysis:**
```python
# In renderer.py, only the latest update is kept:
if time_since_last_ms < self.config.min_render_interval_ms:
    self._pending_update = (current_bar_idx, active_swings, recent_events, highlighted_events)
    self._frames_skipped += 1
    return  # Skipped!

# In harness.py, the queue can grow faster than it's processed:
while not self._update_queue.empty():
    update = self._update_queue.get_nowait()
    self.visualization_renderer.update_display(...)
```

The issues:
1. Renderer's `_pending_update` overwrites previous pending updates
2. Harness queues updates faster than they can be processed at high speeds
3. Events in skipped frames may never trigger event markers

**Recommendations:**
1. Accumulate events across skipped frames instead of overwriting
2. Add event coalescing to preserve significant events during frame skip
3. Limit queue growth and drop oldest updates rather than blocking

---

### Issue 4: Keyboard Handler State Synchronization

**Description:**
The keyboard handler directly manipulates renderer state without coordination with the playback thread, leading to potential data races.

**Steps to Reproduce:**
1. Start auto-playback
2. Press `V` to cycle visibility mode while playback is running
3. Press `[` or `]` to cycle swings during rapid playback
4. Observe inconsistent visibility state

**Severity:** MEDIUM

**Affected Files:**
- `src/visualization/keyboard_handler.py:443-534`
- `src/visualization/renderer.py` (cached state access)

**Root Cause Analysis:**
```python
# In keyboard_handler.py, cached state is accessed directly:
def _cycle_next_swing(self):
    cached_swings = self.visualization_renderer._cached_active_swings
    swings_by_scale = self.visualization_renderer._group_swings_by_scale(cached_swings)

# Meanwhile, in harness.py's _on_playback_step(), the cache is updated:
self._cached_active_swings = active_swings  # No synchronization!
```

The keyboard handler and playback thread both access `_cached_active_swings` without synchronization, leading to:
1. Stale data being used for visibility calculations
2. Inconsistent swing selection after visibility mode change
3. Potential crashes if list is modified during iteration

**Recommendations:**
1. Add `threading.Lock` for cached state access
2. Use immutable data structures (tuples/frozensets) for cached state
3. Copy cached state before operations to avoid iteration issues

---

## Priority Order for Fixes

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| 1 | Layout Transition State Loss | Medium | HIGH - Users lose visibility of critical swings |
| 2 | Keyboard Handler State Sync | Low | MEDIUM - Data races during interaction |
| 3 | Pause/Resume Inconsistencies | Medium | MEDIUM - Confusing state display |
| 4 | Frame Skipping Edge Cases | High | MEDIUM - Visual artifacts at high speed |

---

## Recommended Implementation Plan

### Phase A: Thread Safety (Priority 1 & 2)

Add a `threading.RLock` to protect cached state:

```python
# In renderer.py __init__:
self._state_lock = threading.RLock()

# Wrap all cached state access:
with self._state_lock:
    self._cached_active_swings = active_swings.copy()
```

Estimated complexity: Low

### Phase B: State Synchronization (Priority 3)

Refactor pause/resume to use single source of truth:

```python
@property
def state(self):
    if self._stop_event.is_set():
        return PlaybackState.STOPPED
    if self._pause_requested.is_set():
        return PlaybackState.PAUSED
    if self.current_bar_idx >= self.total_bars - 1:
        return PlaybackState.FINISHED
    return PlaybackState.PLAYING
```

Estimated complexity: Medium

### Phase C: Event Coalescing (Priority 4)

Modify frame skipping to preserve events:

```python
if time_since_last_ms < self.config.min_render_interval_ms:
    # Accumulate events instead of replacing
    if self._pending_update:
        old_events = self._pending_update[2]
        combined_events = old_events + recent_events
        recent_events = combined_events[-50:]  # Keep last 50
    self._pending_update = (current_bar_idx, active_swings, recent_events, highlighted_events)
```

Estimated complexity: Medium

---

## Testing Strategy

After implementing fixes:

1. **Layout Transition Test:** Toggle expand/collapse 20 times during playback, verify swing count consistency
2. **Rapid Pause/Resume Test:** Toggle pause 50 times at 16x speed, verify no state mismatches
3. **High-Speed Playback Test:** Run at 64x speed for 5000 bars, verify event markers present
4. **Concurrent Interaction Test:** Cycle visibility while stepping, verify no crashes

---

## Notes for Future Engineers

- The visualization uses a mixed threading model: matplotlib runs on main thread, playback runs on background thread
- All matplotlib calls MUST happen on main thread (hence the update queue in harness.py)
- The `_rerender_cached_state()` method is the primary source of layout transition issues
- Frame skipping was added for performance but trades visual fidelity for speed
