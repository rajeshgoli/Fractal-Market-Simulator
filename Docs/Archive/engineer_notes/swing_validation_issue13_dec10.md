# Scale-Differentiated Swing Validation Logic (Issue #13)

**Engineer:** Claude Code
**Date:** 2025-12-10
**Type:** Feature Implementation
**Status:** Complete
**Commit:** `e467fcf`

## Context

GitHub Issue #13 requested updated swing validation logic with scale-aware invalidation rules. The previous implementation used a single set of invalidation thresholds (-0.1 close, -0.15 wick) for all scales, but the domain expert specified that different scales should use different rules:

- **S/M scales**: Strict validation - any trade through L (bull) or H (bear) invalidates
- **L/XL scales**: Softer validation with threshold-based rules

Additionally, the issue requested tracking of "encroachment" - whether price has retraced to the 0.382 level before further progress.

## Change Summary

### Modified Files

**`src/analysis/event_detector.py`**

Added validation state fields to `ActiveSwing` dataclass:
```python
@dataclass
class ActiveSwing:
    # ... existing fields ...
    encroachment_achieved: bool = False
    lowest_since_low: Optional[float] = None
    highest_since_high: Optional[float] = None
```

Replaced `check_invalidation()` with scale-dispatching logic:
```python
def check_invalidation(self, bar, source_bar_idx, swing):
    if swing.scale in ['S', 'M']:
        return self._check_invalidation_sm(bar, source_bar_idx, swing)
    else:  # L, XL
        return self._check_invalidation_lxl(bar, source_bar_idx, swing)
```

Added `_check_invalidation_sm()` for S/M strict rules.
Added `_check_invalidation_lxl()` for L/XL threshold rules.

**`src/analysis/swing_state_manager.py`**

Added `_update_swing_validation_state()` method to track:
- Lowest price since L (for bull swings)
- Highest price since H (for bear swings)
- Encroachment achievement (0.382 retracement)

Integrated state tracking into `_process_scale()` before event detection.

Updated `_create_active_swing()` to initialize new fields.

**`tests/test_event_detector.py`**

Added 4 new test classes:
- `TestSMScaleInvalidation` - 5 tests for S/M strict rules
- `TestLXLScaleInvalidation` - 7 tests for L/XL threshold rules
- `TestEncroachmentTracking` - 2 tests for 0.382 retracement
- `TestScaleDispatch` - 2 tests for scale-based dispatch

Updated `TestInvalidation` class - 4 tests updated for new S/M behavior.

## Validation Rules

### S/M Scales (Strict Rules)

| Swing Type | Invalidation Condition |
|------------|------------------------|
| Bull | Price ever trades below L (swing low) |
| Bear | Price ever trades above H (swing high) |

These are "hard" rules - any violation immediately invalidates the swing.

### L/XL Scales (Soft Rules)

| Swing Type | Deep Threshold | Soft Threshold |
|------------|----------------|----------------|
| Bull | Trade below L - 0.15*delta | Close below L - 0.10*delta |
| Bear | Trade above H + 0.15*delta | Close above H + 0.10*delta |

Where `delta = abs(H - L)` (swing size).

The deep threshold catches violent trade-throughs even if price recovers. The soft threshold uses the close price, which is less susceptible to wicks/noise.

### Encroachment Tracking

A swing is considered to have "achieved encroachment" when price retraces to the 0.382 Fibonacci level:
- **Bull swing**: `bar.high >= L + 0.382 * delta`
- **Bear swing**: `bar.low <= H - 0.382 * delta`

This tracks whether price has pulled back before continuing in the swing direction.

## State Tracking Design

The `SwingStateManager` updates validation state before calling `EventDetector`:

```python
def _update_swing_validation_state(self, bar: Bar, scale: str) -> None:
    for swing in self.active_swings[scale]:
        if swing.state != "active":
            continue
        delta = abs(swing.high_price - swing.low_price)

        if swing.is_bull:
            # Track lowest price since L
            if swing.lowest_since_low is None or bar.low < swing.lowest_since_low:
                swing.lowest_since_low = bar.low
            # Check encroachment
            encroachment_level = swing.low_price + (0.382 * delta)
            if not swing.encroachment_achieved and bar.high >= encroachment_level:
                swing.encroachment_achieved = True
        else:
            # Symmetric for bear swings
            ...
```

This ensures the `EventDetector` has accurate extreme price tracking when checking invalidation rules.

## Technical Notes

- **Aggregation-level handling**: The architecture already passes aggregated bars (1H for L, 4H for XL) to the detector, so no changes were needed for aggregation-level close checking
- **Tolerance**: All comparisons use a 0.1% tolerance (0.001 * swing_size) to handle floating-point precision
- **State initialization**: New fields have defaults, maintaining backward compatibility with existing `ActiveSwing` instances
- **Tracked extremes vs bar extremes**: The detector prefers `lowest_since_low`/`highest_since_high` when available, falling back to current bar values

## Test Results

- **36 tests** pass in `test_event_detector.py`
- **115 tests** pass across all core analysis modules (no regressions)
- New tests cover:
  - S/M strict invalidation (bull and bear)
  - L/XL threshold invalidation (deep and soft)
  - Encroachment tracking
  - Scale-based dispatch

## Usage

The validation rules apply automatically during harness playback:

```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01 --verbose
```

Invalidation events will now show scale-appropriate descriptions:
- S/M: `"INVALIDATED - trade below swing low L (S/M strict rule)"`
- L/XL: `"INVALIDATED - close below L - 0.10*delta (4157.25) (L/XL soft threshold)"`

## Scope

This change modifies swing invalidation logic only. It does not affect:
- Swing detection algorithms
- Level crossing detection
- Completion detection
- Visualization rendering
- Data loading or CLI interface

## File Locations

| Type | Path |
|------|------|
| Event Detector | `src/analysis/event_detector.py` |
| Swing State Manager | `src/analysis/swing_state_manager.py` |
| Tests | `tests/test_event_detector.py` |
