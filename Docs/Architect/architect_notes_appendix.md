# Architecture Notes Appendix

## Historical Context

This appendix contains historical decisions, completed work records, and obsolete context that informed the current architecture but are no longer relevant for forward progress.

## Completed Implementation Work

### Historical Data Validation Harness (Dec 10, 2025)
**Status:** Complete  
**Engineer:** Claude Code  

**Implementation Details:**
- Enhanced DataLoader with date range filtering and multi-resolution support
- Extended CLI with `validate` command supporting symbol, resolution, and date range parameters  
- Created ValidationSession management for expert review tracking and progress persistence
- Implemented IssueCatalog system for structured problem documentation and analysis
- Comprehensive test suite covering all validation components
- Performance validation confirmed responsive experience during historical replay

**Technical Approach:**
- Composition-based integration with existing VisualizationHarness to preserve functionality
- Temporary file creation for harness compatibility (identified as technical debt)
- Session state persistence through JSON files in validation_sessions directory
- Issue classification system with severity levels and market context preservation

**Architectural Patterns Established:**
- Command Pattern Extension for CLI subcommand architecture
- Session State Management pattern for long-running analysis workflows  
- Composition Over Inheritance for ValidationHarness integration
- Historical Data Pipeline with date-range-aware loading

**Identified Technical Debt:**
- Temporary file creation for harness integration requires refactoring
- Bar Object dependency on legacy module should be resolved
- Memory usage patterns need validation for large dataset scenarios
- Session directory management lacks automatic cleanup

## Historical Product Requirements

### Initial Product Direction (Pre-Dec 10)
The original product direction focused on immediate progression to Market Data Generator implementation, treating the Swing Visualization Harness as complete foundation for generation work.

### Product Direction Shift (Dec 10)
Product direction shifted to prioritize historical data validation using existing datasets to validate swing detection logic before proceeding to generation. This represented a critical risk mitigation strategy to avoid building on unvalidated foundations.

## Obsolete Architecture Assumptions

### Direct Generator Development Path
Initial architecture assumed readiness to proceed directly from completed harness to Market Data Generator implementation without intermediate validation phase.

### Single-User Analysis Model  
Original harness design assumed single expert analysis sessions; validation requirements introduced potential multi-user collaboration needs.

### Memory Model Assumptions
Initial performance optimization focused on real-time generation scenarios; historical validation introduces different memory usage patterns requiring separate optimization.

## Deprecated Technical Decisions

### Immediate Generation Architecture
The following generator architecture was planned but deferred pending validation completion:

```
MarketRules → SwingSimulator → PriceGenerator → OHLC Output
      ↓             ↓               ↓             ↓
 FibonacciRules  SwingEvents   TickData    MinuteCandles
```

This architecture remains viable but is not the immediate priority.

### Performance Targets
Original 18x performance margin targets were established for real-time generation scenarios; validation phase requires different performance characteristics focused on interactive historical replay.

---

## Issue #10-14 Implementation Details (Dec 10-11, 2025)

**Status:** Complete (functionality verified)
**Architect Review:** 2025-12-11

### Issue #10: Reference Period Hang Fix

**Problem:** Initialization hung indefinitely with large reference periods (86K+ bars).

**Root Cause:** S-scale override from 60m to 1m was applied globally, causing SwingStateManager to process 86K individual bars instead of 1.4K aggregated bars.

**Solution:** Separated analysis configuration from display configuration:
- `scale_config` (original calibrated) used by SwingStateManager
- `display_aggregations` (deep copy with S override) used by VisualizationRenderer

**Performance Result:** 92s total initialization (vs infinite hang)

### Issue #11: Playback Controls

**Implementation:**
- KeyboardHandler class with matplotlib mpl_connect
- Shortcuts: SPACE (pause/resume), RIGHT (step), UP/DOWN (speed), R (reset), H (help)
- ProgressLogger for verbose CLI feedback (periodic reports, major event notifications)
- Status overlay in figure corner

### Issue #12: Visualization Usability

**New Components:**
- `LayoutManager`: QUAD (2x2) and EXPANDED (90% primary) modes with 10x10 GridSpec
- `PiPInsetManager`: Picture-in-Picture when swing body scrolls off-screen
- `SwingVisibilityController`: ALL/SINGLE/RECENT_EVENT modes with opacity control

**Bug Fixes Applied:**
- Keyboard shortcuts required renderer parameter passing to handler
- PiP initially rendered as giant candle (fixed with normalized coordinates)
- Swing body added to main panel (was missing, only Fib levels shown)
- Layout transitions now cache state for re-render
- Removed constrained_layout (conflicts with dynamic GridSpec)

**Frame Skipping:** 60ms minimum interval (~16 FPS max) prevents UI starvation at high playback speeds.

### Issue #13: Scale-Differentiated Validation

**Rules Implemented:**
- S/M scales: Strict rules (any trade-through swing boundary invalidates)
- L/XL scales: Soft rules (deep threshold: 0.15*delta, soft threshold: 0.10*delta)

**State Tracking Added:**
- `lowest_since_low` / `highest_since_high` for extreme price tracking
- `encroachment_achieved` when price retraces to 0.382 level

**Test Coverage:** 36 tests in test_event_detector.py covering all scenarios.

### CLI Data Discovery

**New Commands:**
- `list-data` (aliases: `describe`, `inspect`)
- Shows available resolutions, date ranges, file counts, bar totals
- `--verbose` provides per-file details

**Enhanced Error Messages:** Validation failures now show available date ranges and suggest discovery commands.

### 1m CSV Duplicate Timestamp Fix

**Problem:** `get_loc()` returns slice for duplicate timestamps, causing arithmetic error.

**Fix:** Check for slice type, use `.start` for first occurrence index.

**Impact:** 12M+ bars of 1m ES data now loads successfully.

---

## Test Suite Maintenance (Dec 11, 2025)

**Status:** Complete
**Engineer:** Claude Code
**Architect Review:** Accepted

### Summary

12 failing tests fixed through fixture updates. No production code modified.

### Root Causes

| Test File | Failures | Issue |
|-----------|----------|-------|
| test_cli_harness.py | 6 | CSV fixtures used wrong header (`timestamp` vs `time`), missing `volume` |
| test_validation.py | 5 | Naive datetimes, missing `index` param on Bar, bad date range |
| test_ohlc_loader.py | 1 | Duplicate timestamps collapsed rows |

### Fixes Applied

1. **CLI Harness Tests:** Updated CSV header to `time,open,high,low,close,volume`, fixed mock targets for Path.exists()
2. **Validation Tests:** Added timezone.utc to all datetimes, added index param to Bar(), fixed date ranges
3. **OHLC Loader Tests:** Generate unique timestamps per row

### Test Results

- **Before:** 184 passing, 12 failing
- **After:** 196 passing, 2 skipped

### Architectural Note

Test modification to `test_interactive_commands` tests `_handle_command()` directly instead of `run_interactive()` because select-based input loop cannot be easily mocked. This tests the same command logic but skips input loop mechanism.