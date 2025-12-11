# Bug Fix Report: SwingStateManager Initialization Error

**Date:** 2025-12-10
**Issue:** GitHub #3
**Commit:** 435e7a4

## Summary

The validation harness failed during initialization with `SwingStateManager.__init__() got an unexpected keyword argument 'bar_aggregator'`. This blocked all validation commands, preventing systematic testing of swing detection against historical data.

## Symptoms

Running any validation command produced:

```
src.cli.harness - ERROR - Failed to initialize harness: SwingStateManager.__init__() got an unexpected keyword argument 'bar_aggregator'
```

The failure occurred after successful data loading, bar aggregation, and scale calibration—specifically during `_initialize_analysis_components()` when instantiating SwingStateManager.

## Root Cause

`src/cli/harness.py:146-150` passed three arguments to SwingStateManager:

```python
SwingStateManager(
    scale_config=self.scale_config,
    bar_aggregator=self.bar_aggregator,
    event_detector=self.event_detector
)
```

However, `SwingStateManager.__init__()` only accepts `scale_config`. The class creates its own `EventDetector` internally (line 59 of `swing_state_manager.py`).

This was an API mismatch introduced when the harness was written, likely based on an assumed signature rather than the actual implementation.

## Fix

Updated `src/cli/harness.py` to:

1. Remove the unused `EventDetector` import
2. Call `SwingStateManager(scale_config=self.scale_config)` with only the required parameter
3. Reference the internally-created event detector via `self.event_detector = self.swing_state_manager.event_detector`

This aligns the harness with SwingStateManager's actual API while preserving access to the event detector for downstream components.

## Verification

**Command tested:**
```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2024-07-01 --end 2024-07-02 --verbose
```

**Results:**
- Harness initialized successfully
- Scale calibration completed (S: 0-23.5, M: 23.5-28.5, L: 28.5-31.25, XL: 31.25+)
- Analysis components initialized with 200 bars
- Visualization and playback components started
- Validation session completed without errors

**Other resolutions:** Not affected—the fix is specific to harness initialization, which is shared across all data resolutions.

## Scope and Risk

**What changed:** Only the SwingStateManager instantiation in `harness.py`. No changes to SwingStateManager itself, event detection logic, or any analysis algorithms.

**Risk:** Minimal. The event detector reference now comes from SwingStateManager rather than being independently created, which is the intended design. All downstream usage remains identical.

## Follow-Ups

- Consider adding type hints to harness component initialization to catch API mismatches earlier
- The duplicate timestamp warnings during data loading appear frequently; may warrant a separate cleanup pass
