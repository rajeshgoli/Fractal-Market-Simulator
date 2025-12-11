# Thread Safety for Cached State Access

## Task Summary

Implemented thread safety for cached state access in the visualization renderer, addressing HIGH severity race conditions identified in the stability audit (`Docs/engineer_notes/stability_audit_dec11.md`).

## Assumptions

- The playback thread updates cached state (`_cached_active_swings`, etc.) while the UI thread reads from it
- Using `threading.RLock` is appropriate as it allows recursive acquisition within the same thread (needed for nested calls)
- Making copies of the cached lists is sufficient protection; deep copies of individual swing objects are not required since swing objects are not mutated after creation

## Modules Implemented

### `src/visualization/renderer.py`

**Changes:**

1. **Added `threading.RLock`** (`_state_lock`) to protect cached state access
   - Location: `__init__` method, line 101
   - RLock chosen over Lock to support potential recursive acquisition

2. **Protected cache writes** in `update_display`
   - Location: lines 316-319
   - All three cached lists are now copied under lock
   - Pattern: `with self._state_lock: self._cached_active_swings = list(active_swings) if active_swings else []`

3. **Protected cache reads** in `_rerender_cached_state`
   - Location: lines 245-249
   - Copies are made under lock, then rendering happens outside lock
   - This minimizes lock hold time while ensuring data consistency

4. **Added `get_cached_swings_copy()` public method**
   - Location: lines 1312-1324
   - Thread-safe accessor for external callers (keyboard handler)
   - Returns a copy of the cached swings list

### `src/visualization/keyboard_handler.py`

**Changes:**

1. **Updated `_cycle_next_swing`** (line 477)
   - Now uses `get_cached_swings_copy()` instead of direct attribute access
   - Pattern: `cached_swings = self.visualization_renderer.get_cached_swings_copy()`

2. **Updated `_cycle_previous_swing`** (line 511)
   - Same change as above for consistency

## Tests and Validation

Added 7 new tests in `tests/test_visualization_renderer.py` under `TestThreadSafety` class:

| Test | Purpose |
|------|---------|
| `test_state_lock_exists` | Verify lock is initialized |
| `test_get_cached_swings_copy_returns_list` | Returns proper list type |
| `test_get_cached_swings_copy_returns_copy_not_reference` | Returns copy, not reference |
| `test_get_cached_swings_copy_empty_state` | Handles empty state |
| `test_get_cached_swings_copy_none_state` | Handles None state |
| `test_concurrent_cache_access` | Concurrent read/write from threads |
| `test_rerender_cached_state_uses_lock` | Verify _rerender copies under lock |

**Test Results:** 227 passed, 2 skipped (7 new tests, no regressions)

### Manual Testing Recommended

Per the stability audit:
1. Toggle expand/collapse 20 times during playback
2. Verify swing count consistency across transitions
3. Cycle visibility modes while playback is running

## Known Limitations

1. **Lock granularity**: The lock protects the entire cached state; a more fine-grained approach could use separate locks per cache variable, but this adds complexity without clear benefit for current use patterns

2. **Not protecting all state**: Only `_cached_active_swings`, `_cached_recent_events`, and `_cached_highlighted_events` are protected. Other renderer state (like `current_bar_idx`, `last_events`) is not locked because they are only written from the main thread

3. **Shallow copy**: We copy the list but not the swing objects themselves. This is safe because swings are treated as immutable after creation, but would need review if swing mutation is introduced

## Questions for Architect

No questions for architect. Implementation follows the specification in `engineer_next_step.md` exactly.

## Suggested Next Steps

Per the stability audit priority order:

1. **Priority 2: Pause/Resume Consistency** - Refactor `PlaybackController` to use single source of truth for state (derive state from threading events, not maintain separate enum)

2. **Priority 3: Frame Skipping Edge Cases** - Modify frame skipping to accumulate events across skipped frames instead of overwriting

3. **Priority 4: Event Coalescing** - Implement event preservation during high-speed playback
