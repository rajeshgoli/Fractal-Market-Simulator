# PlaybackController State Refactor (Issue #15)

**Date:** 2025-12-11
**Type:** Refactor / Bug Fix
**Status:** Complete

## Context

The PlaybackController had a race condition where pause/resume state management was inconsistent between the playback thread and UI thread. The `PlaybackState` enum was being directly assigned in multiple locations:

1. `pause_playback()` directly assigned `self.state = PlaybackState.PAUSED`
2. `_auto_play_loop()` also assigned the same state when detecting pause events

This dual-source approach allowed the playback thread to queue GUI updates displaying PLAYING status while the actual state was PAUSED.

## Root Cause

State was stored as a mutable attribute (`self.state`) that could be modified from any thread at any time. This created a classic TOCTOU (time-of-check-time-of-use) race condition where:
- UI thread reads state → PLAYING
- Playback thread sets state → PAUSED
- UI displays stale PLAYING status

## Solution

Converted `state` from a stored attribute to a computed property that derives its value exclusively from thread-safe events:

```python
@property
def state(self) -> PlaybackState:
    # FINISHED: at end of data (terminal state)
    if self.current_bar_idx >= self.total_bars - 1:
        return PlaybackState.FINISHED
    # STOPPED: stop event is set (initial state or after stop_playback)
    if self._stop_event.is_set():
        return PlaybackState.STOPPED
    # PAUSED: pause requested
    if self._pause_requested.is_set():
        return PlaybackState.PAUSED
    # PLAYING: default state when running
    return PlaybackState.PLAYING
```

Key changes:
1. Removed `self.state` as a stored attribute
2. Added `@property def state()` that computes state from threading events
3. Initialize `_stop_event.set()` in `__init__` to indicate initial STOPPED state
4. Removed all 13 direct `self.state =` assignments throughout the codebase
5. State transitions now happen by manipulating `_stop_event` and `_pause_requested` events

### State Priority Order

1. **FINISHED** - Terminal state when at or past last bar (data exhausted)
2. **STOPPED** - When `_stop_event` is set (initial or after stop)
3. **PAUSED** - When `_pause_requested` is set
4. **PLAYING** - Default when none of the above

FINISHED takes highest priority because reaching end of data is terminal regardless of other flags.

## Files Changed

| File | Changes |
|------|---------|
| `src/playback/controller.py` | Added `state` property, removed stored attribute, removed 13 direct assignments |
| `tests/test_playback_controller.py` | Added `TestPlaybackStateSingleSourceOfTruth` test class with 4 new tests |

## Testing

### New Tests Added (4)
1. `test_state_is_computed_property` - Verifies state is a property, not stored attribute
2. `test_rapid_pause_resume_cycles` - 50 iterations at 16x speed verify accurate state
3. `test_state_derives_from_events_only` - Verifies state derivation priority order
4. `test_no_race_condition_on_state` - Concurrent observer thread verifies thread safety

### Test Results
- All 231 tests pass
- All 27 playback controller tests pass
- Rapid pause/resume test verified no state inconsistencies in 50 cycles

## Notes for Future Engineers

1. **Never assign to `state` directly** - The property is read-only by design
2. **State changes happen via events** - Use `_stop_event.set()/clear()` and `_pause_requested.set()/clear()`
3. **Threading events are atomic** - Python `threading.Event` operations are thread-safe
4. **Priority order matters** - FINISHED must be checked first to handle edge case where data is exhausted while other flags are set
