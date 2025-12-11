# Bug Fix: ES-1m.csv Loading Failure

**Date:** December 10, 2024  
**Issue:** ES 1m CSV files failing to load with "unsupported operand type(s) for -: 'slice' and 'int'" error  
**Status:** ✅ Fixed

## Root Cause

The issue occurred in the gap detection logic of `src/data/ohlc_loader.py` when processing CSV files with duplicate timestamps. 

### Technical Details

1. **Duplicate Timestamps**: The ES-1m.csv file contained 1,380 duplicate timestamps (e.g., multiple entries for `2024-07-25 00:00:00+00:00`)

2. **pandas Index Behavior**: When `DataFrame.index.get_loc()` encounters duplicate values, it returns a `slice` object instead of an `int`
   - Normal case: `get_loc()` returns `int` (e.g., `27`)
   - Duplicate case: `get_loc()` returns `slice` (e.g., `slice(6022738, 6024119, None)`)

3. **Arithmetic Error**: The code attempted `loc - 1` where `loc` was a `slice`, causing the TypeError

### Why Only 1m Files Were Affected

- High-frequency 1m data has a much higher chance of duplicate timestamps than 5m/1d data
- The specific ES-1m.csv file had overlapping data ranges that created duplicates
- 5m and 1d files in this dataset had fewer or no duplicate timestamps

## Fix Applied

Modified the gap detection loop in `src/data/ohlc_loader.py` (lines 194-200):

```python
# Handle case where get_loc returns a slice (duplicate timestamps)
if isinstance(loc, slice):
    # Use the first occurrence of the duplicate timestamp
    loc = loc.start
    
# Ensure we don't go below index 0
if loc > 0:
    start_time = df.index[loc - 1]
    # ... rest of gap processing
```

### Key Changes

1. **Slice Detection**: Check if `get_loc()` returns a slice
2. **Slice Handling**: Use `slice.start` to get the first index of duplicate timestamps
3. **Boundary Protection**: Added check to ensure `loc > 0` before accessing `loc - 1`

## Verification

### Before Fix
```bash
$ python3 -m src.cli.main list-data
# ... errors and "Resolution: 1m Status: No data available"
```

### After Fix
```bash
$ python3 -m src.cli.main list-data
Resolution: 1m
  Status: Available
  Files: 2
  Total Bars: 12,067,554
  Date Range: 2007-04-01 17:00:00 UTC to 2024-08-05 00:00:00 UTC
```

## Regression Test

Created `test_1m_regression.py` with two tests:
1. **Synthetic Test**: CSV with known duplicate timestamps
2. **Real File Test**: Actual ES-1m.csv file loading

Both tests pass, confirming the fix works and won't regress.

## Impact

- ✅ 1m data now loads successfully
- ✅ No behavioral changes for 5m/1d data  
- ✅ Gap detection still works correctly
- ✅ Handles edge cases (duplicate timestamps, boundary conditions)

## Lessons Learned

1. **pandas Index Behavior**: `get_loc()` can return different types depending on data uniqueness
2. **High-Frequency Data Issues**: 1m data commonly has duplicate timestamps due to overlapping sources
3. **Robust Error Handling**: Always check return types when working with pandas indexing operations

---

**Files Modified:**
- `src/data/ohlc_loader.py` - Fixed gap detection logic
- `test_1m_regression.py` - Added regression test (new file)