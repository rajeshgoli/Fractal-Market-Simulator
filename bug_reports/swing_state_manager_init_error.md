# Bug Report: SwingStateManager Initialization Error

**Date:** 2025-12-10  
**Reporter:** Claude Code  
**Severity:** High - Validation commands failing  
**Status:** Open  

## Summary

After fixing the chronological order issue (#2), validation commands now fail during SwingStateManager initialization with an unexpected keyword argument error.

## Error Details

```
src.cli.harness - ERROR - Failed to initialize harness: SwingStateManager.__init__() got an unexpected keyword argument 'bar_aggregator'
```

## Steps to Reproduce

1. Run validation command:
   ```bash
   python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2023-01-01 --end 2023-01-31 --verbose
   ```

2. The harness successfully:
   - Loads and deduplicates OHLC data
   - Initializes BarAggregator 
   - Calibrates structural scales

3. Error occurs during `_initialize_analysis_components()` when creating SwingStateManager

## Expected Behavior

SwingStateManager should initialize successfully with the provided parameters.

## Actual Behavior

SwingStateManager.__init__() rejects the `bar_aggregator` keyword argument, causing harness initialization to fail.

## Environment

- Python version: 3.12
- Command: `python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2023-01-01 --end 2023-01-31 --verbose`
- Session ID: validation_9923b72d

## Code Location

**File:** `src/cli/harness.py:146-150`

```python
# Swing state manager
self.swing_state_manager = SwingStateManager(
    scale_config=self.scale_config,
    bar_aggregator=self.bar_aggregator,  # ← This parameter is rejected
    event_detector=self.event_detector
)
```

## Investigation Notes

1. The error suggests SwingStateManager.__init__() doesn't accept `bar_aggregator` as a parameter
2. This could be due to:
   - API change in SwingStateManager constructor
   - Incorrect parameter name
   - Missing import or class definition mismatch

## Immediate Impact

- All validation commands fail at harness initialization
- Unable to run market data validation workflows
- Blocks testing of the chronological order fix

## Priority

**High** - This blocks all validation functionality and prevents proper testing of recent fixes.

## Next Steps

1. Examine SwingStateManager.__init__() signature in `src/analysis/swing_state_manager.py`
2. Compare with harness initialization parameters
3. Update harness to match correct SwingStateManager API
4. Test validation command end-to-end