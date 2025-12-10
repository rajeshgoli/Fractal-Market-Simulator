# Bug Fix: Initialization Hang with Large Reference Periods

**Date:** December 10, 2024
**Issue:** GitHub Issue #10 - Harness hangs when using `--playback-start` with large reference periods
**Status:** Fixed

## Problem Summary

When running the validation harness with a 3-month reference period (Jan-Apr 2020), the system would hang indefinitely after logging "Using reference period: bars 0-86053 for calibration".

### Reproduction Command
```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01 \
  --step-timeframe 60 --verbose
```

### Expected Behavior
- Initialize in reasonable time (~90s for 114K bars)
- Display matplotlib window
- Begin playback from April 1st

### Actual Behavior (Before Fix)
- Hangs indefinitely at SwingStateManager initialization
- No matplotlib window appears
- Process appears frozen

## Root Cause Analysis

### Investigation Process

1. **Initial hypothesis:** BarAggregator or SwingStateManager bottleneck
2. **Isolated tests:** Each component was fast individually (~0.5-1s)
3. **Full trace:** Added timing between every step

### Discovery

The trace revealed:
```
22.12s Starting scale calibration...
93.03s Scale calibration done
93.03s Overriding S-scale from 60m to 1m  <-- HERE IS THE PROBLEM
93.61s Creating BarAggregator...
93.61s Initializing SwingStateManager with bars 0-86053...
[INFINITE HANG]
```

### Root Cause

The previous fix (commit c80e674) for Issue #10's visual update problem introduced a regression:

```python
# BAD: Global override affects BOTH analysis AND visualization
if self.scale_config.aggregations.get('S', 1) > 1:
    self.scale_config.aggregations['S'] = 1  # Breaks SwingStateManager!
```

**Problem Chain:**
1. `scale_config` is shared by `SwingStateManager` AND `VisualizationRenderer`
2. Override sets S-scale from 60m to 1m globally
3. `SwingStateManager.initialize_with_bars()` uses S-scale for aggregation
4. With S-scale=1m, it processes 86,053 individual 1-minute bars
5. `detect_swings()` on 86K bars takes effectively forever

**Why It Worked Before:**
- With calibrated S-scale=60m, only ~1,434 bars are processed (86053/60)
- Swing detection on 1.4K bars takes < 1 second

## Solution

### Architectural Fix

Create separate configuration paths for analysis vs display:

```python
# Keep original calibrated config for analysis
self.scale_config = calibrator.calibrate(self.bars)

# Create separate display aggregations for visualization
self.display_aggregations = dict(self.scale_config.aggregations)
if self.display_aggregations.get('S', 1) > 1:
    self.display_aggregations['S'] = 1  # Only affects display!

# SwingStateManager gets original config
self.swing_state_manager = SwingStateManager(scale_config=self.scale_config)

# VisualizationRenderer gets display-specific config
display_scale_config = deepcopy(self.scale_config)
display_scale_config.aggregations = self.display_aggregations
self.visualization_renderer = VisualizationRenderer(scale_config=display_scale_config, ...)
```

### Key Changes

1. **No global S-scale override** - Original calibrated values preserved
2. **Separate `display_aggregations` dict** - Only used for visualization
3. **VisualizationRenderer gets deepcopy** - Isolated from analysis config
4. **Clear logging** - Shows both analysis and display timeframes

## Performance Results

### Before Fix (c80e674)
| Component | Time |
|-----------|------|
| Data loading | ~22s |
| Scale calibration | ~68s |
| SwingStateManager init | **INFINITE HANG** |
| **Total** | **Never completes** |

### After Fix (2b3e244)
| Component | Time |
|-----------|------|
| Data loading | ~22s |
| Scale calibration | ~68s |
| SwingStateManager init | **0.7s** |
| Visualization + rest | <1s |
| **Total** | **~92s** |

## Verification

### Test Command
```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01 \
  --step-timeframe 60 --verbose
```

### Expected Log Output
```
Analysis timeframes (for swing detection):
  S: 60m
  M: 240m
  L: 240m
  XL: 240m
Display S-panel: overriding from 60m to 1m for per-bar visibility
Display timeframes (for visualization):
  S: 1m
  M: 240m
  L: 240m
  XL: 240m
```

### Unit Tests
All 46 relevant tests pass:
- `test_playback_controller.py` - 23 passed
- `test_scale_calibrator.py` - 8 passed
- `test_visualization_renderer.py` - 15 passed

## Lessons Learned

1. **Shared Configuration Danger:** When multiple components share a config object, modifying it affects all consumers unexpectedly

2. **Override Strategy:** For display-only modifications, create a separate config copy rather than modifying the shared one

3. **Performance Testing:** Always test with realistic data volumes. The bug only manifested with 86K+ bars.

4. **Trace Full Flow:** Isolated component tests all passed. The bug was only visible when tracing the complete initialization sequence.

5. **Log Intermediate States:** Adding logging between steps immediately revealed where the hang occurred

## Files Modified

- `src/cli/harness.py` - Separated analysis config from display config
  - Lines 134-154: Create separate `display_aggregations`
  - Lines 208-218: Pass display-specific config to VisualizationRenderer

## Related Issues

- **Issue #10:** Historical Harness Playback Behavior (this fix)
- **Commit c80e674:** Previous fix that introduced the regression
- **Commit 2b3e244:** This fix

---

**Commit:** 2b3e244 - "Fix initialization hang with large reference periods (fixes #10)"
