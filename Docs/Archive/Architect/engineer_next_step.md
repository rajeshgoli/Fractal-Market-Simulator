# Engineer Next Step

**Phase:** 2 - Stability Fixes
**Priority:** 2 (Pause/Resume Consistency)
**Date:** 2025-12-11

---

## Instruction

Refactor `PlaybackController` to derive state from threading events rather than maintaining a separate state enum.

### Context

The stability audit (`Docs/engineer_notes/stability_audit_dec11.md`) identified MEDIUM severity issues where rapid pause/resume toggling causes the UI to show incorrect state. The root cause is that state is updated in two places:
1. `pause_playback()` sets `self.state = PlaybackState.PAUSED` immediately
2. `_auto_play_loop()` also sets `self.state = PlaybackState.PAUSED` when it sees the pause event

This creates a race condition where the playback thread may queue a GUI update showing PLAYING while the actual state is PAUSED.

### Required Changes

#### 1. Convert State to Property (`src/playback/controller.py`)

Replace the state attribute with a computed property:

```python
@property
def state(self) -> PlaybackState:
    """Derive state from threading events (single source of truth)."""
    if self._stop_event.is_set():
        return PlaybackState.STOPPED
    if self._pause_requested.is_set():
        return PlaybackState.PAUSED
    if self.current_bar_idx >= self.total_bars - 1:
        return PlaybackState.FINISHED
    return PlaybackState.PLAYING
```

#### 2. Remove Direct State Assignments

Remove or comment out all lines like:
```python
self.state = PlaybackState.PAUSED  # Remove these
self.state = PlaybackState.PLAYING  # Remove these
```

Keep only the threading event manipulation:
```python
self._pause_requested.set()  # Keep these
self._pause_requested.clear()  # Keep these
```

#### 3. Update Any State Comparisons

If any code compares state directly, ensure it still works with the property.

### Testing Requirements

1. Add test for rapid pause/resume toggling (50x at high speed)
2. Verify state property returns correct value in all scenarios
3. Run `python -m pytest tests/test_playback_controller.py -v`
4. Manual test: Toggle pause rapidly at 16x speed, verify status overlay is accurate

### Deliverables

1. Refactored `PlaybackController` with state property
2. Tests for state derivation
3. Engineer note documenting the change
4. Update `PENDING_REVIEW.md` with change count

### Scope Boundary

Do NOT implement in this step:
- Event coalescing (Priority 3)
- Any other stability fixes

Focus only on pause/resume state consistency.

### Note on Priority

This fix is **recommended but not blocking** for validation sessions. If timeline is tight, Engineering may defer this and proceed to Phase 3 (validation) after discussion with Architect.

---

## Reference Documents

- Stability Audit: `Docs/engineer_notes/stability_audit_dec11.md` (Issue 2)
- Architect Notes: `Docs/Architect/architect_notes.md`
