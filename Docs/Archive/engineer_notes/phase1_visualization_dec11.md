# Phase 1 Visualization Improvements

**Date:** December 11, 2025
**Type:** Feature Enhancement
**Status:** Complete

---

## Task Summary

Implemented three visualization improvements from `Docs/Architect/engineer_next_step.md`:

1. **S-Scale Swing Cap** - Limits visible swings per scale to reduce visual clutter
2. **Dynamic Bar Aggregation** - Auto-adjusts timeframe for optimal candle density
3. **Stability Audit** - Documented state management issues

---

## Assumptions

- Default swing cap of 5 was appropriate as specified
- Timestamp-based recency scoring was preferred over bar-index (since ActiveSwing lacks bar indices)
- The stability audit should document issues without implementing fixes in this phase

---

## Modules Implemented

### 1. Swing Cap (Priority 1)

**Files Changed:**
- `src/visualization/config.py:57-59` - Added config options
- `src/visualization/renderer.py:957-1023` - Added `_apply_swing_cap()` method
- `src/visualization/renderer.py:903-954` - Modified `_group_swings_by_scale()`
- `src/visualization/renderer.py:1309-1343` - Added `toggle_show_all_swings()`, `get_swing_cap_status()`
- `src/visualization/keyboard_handler.py:162-163` - Added 'A' key handler
- `src/visualization/keyboard_handler.py:536-560` - Added `_toggle_show_all_swings()` method

**Config Options Added:**
```python
max_swings_per_scale: int = 5  # 0 = show all
show_all_swings: bool = False  # Toggle state for bypass
```

**Scoring Formula:**
```python
score = 0.6 * recency_factor + 0.4 * size_factor
# recency_factor: based on timestamp (0=oldest, 1=newest)
# size_factor: normalized by max swing size in scale
```

**Special Rule:** Swing from most recent event is ALWAYS included.

**Keyboard Shortcut:** `A` toggles show_all_swings

### 2. Dynamic Bar Aggregation (Priority 2)

**Files Changed:**
- `src/visualization/renderer.py:103-104` - Added `_current_timeframes` tracking
- `src/visualization/renderer.py:405-412` - Modified `render_panel()` to use dynamic timeframe
- `src/visualization/renderer.py:863-865` - Modified `update_panel_annotations()` to show dynamic timeframe
- `src/visualization/renderer.py:1345-1399` - Added `_calculate_optimal_timeframe()` method

**Algorithm:**
1. Calculate visible time range from view_window
2. Select aggregation timeframe yielding 40-60 candles
3. Available timeframes: 1, 5, 15, 30, 60, 240 minutes
4. Scale hierarchy enforced (S never coarser than M, etc.)

**Target:** 40-60 visible candles per quadrant

### 3. Stability Audit (Priority 3)

**Deliverable:** `Docs/engineer_notes/stability_audit_dec11.md`

**Issues Documented:**
| Issue | Severity | Description |
|-------|----------|-------------|
| Layout Transition State Loss | HIGH | Swings disappear after layout toggle |
| Pause/Resume Inconsistencies | MEDIUM | Race conditions in state management |
| Frame Skipping Edge Cases | MEDIUM | Events lost during high-speed playback |
| Keyboard Handler State Sync | MEDIUM | Unsynchronized access to cached state |

---

## Tests and Validation

**New Test Classes:**
- `TestSwingCapFunctionality` (7 tests)
- `TestDynamicBarAggregation` (4 tests)

**Test Coverage:**
- Swing cap filtering with excess swings
- No filtering when under cap
- Recent event swing always included
- Toggle bypass functionality
- Scoring prefers recent + large swings
- Dynamic timeframe respects scale hierarchy
- Optimal timeframe targets 40-60 candles

**Full Suite Result:** 220 passed, 2 skipped

---

## Known Limitations

1. **Swing Cap:** Uses timestamp-based recency since ActiveSwing lacks bar indices
2. **Dynamic Aggregation:** May cause visual "jumps" when crossing timeframe boundaries
3. **Stability Issues:** Documented but not fixed in this phase (see audit)

---

## Questions for Architect

1. Should the swing cap be configurable per-scale (e.g., S=5, M=3, L=2, XL=1)?
2. Should dynamic aggregation have hysteresis to prevent rapid timeframe switching?
3. Which stability issues should be prioritized for Phase 2?

---

## Suggested Next Steps

1. **Thread Safety (from audit):** Add `threading.RLock` to protect cached state
2. **Event Coalescing:** Preserve events during frame skipping
3. **User Guide Update:** Document new 'A' keyboard shortcut
4. **Scale-Specific Caps:** Consider different caps for different scales

---

## Files Changed Summary

| File | Lines Changed | Description |
|------|---------------|-------------|
| `src/visualization/config.py` | +3 | Swing cap config options |
| `src/visualization/renderer.py` | +150 | Swing cap + dynamic aggregation |
| `src/visualization/keyboard_handler.py` | +27 | Toggle shortcut |
| `tests/test_visualization_renderer.py` | +190 | New test classes |
| `Docs/engineer_notes/stability_audit_dec11.md` | +180 | Audit document |
