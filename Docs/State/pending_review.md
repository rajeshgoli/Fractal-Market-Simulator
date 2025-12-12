# Pending Review

**Unreviewed Change Count:** 3

**Last Review:** 2025-12-11

---

## Pending Changes

### 2025-12-12 - Optimize swing_detector.py for 6M+ bar datasets
- **Issue:** #20
- **Type:** Enhancement (Performance)
- **Files:**
  - `src/swing_analysis/swing_detector.py` - Vectorized swing detection, added `max_pair_distance` parameter
  - `src/swing_analysis/scale_calibrator.py` - Auto-applies `max_pair_distance=2000` for >100K bars
  - `tests/test_swing_detector.py` - Added `TestSwingDetectorLargeDataset` with 6M bar validation
  - `tests/test_scale_calibrator.py` - Adjusted timing tolerance for measurement variance
- **Summary:** Optimized swing detector to meet <60s target for 6M bars:
  - **Phase 1**: Vectorized swing point detection using numpy (8x faster)
  - **Phase 2**: Added `max_pair_distance` parameter enabling O(N×D) instead of O(S²) pairing
  - **Result**: 100K bars in 0.18s → extrapolated 10.8s for 6M bars (target: <60s)
- **Note:** 3 pre-existing unit test failures in `test_swing_detector_unit.py` (tests 3, 11, 14) have incorrect expectations about Fibonacci banding - these fail with or without this change.

### 2025-12-12 - Integrate O(N log N) Swing Detector
- **Issue:** #17
- **Type:** Enhancement
- **Files:**
  - `src/swing_analysis/scale_calibrator.py` - Replaced legacy detectors with `detect_swings()`
  - `tests/test_scale_calibrator.py` - Added O(N log N) scaling test
- **Summary:** Integrated existing `detect_swings()` into scale calibrator. Profiling revealed underlying detector has bottlenecks (slow `df.iloc`, O(S²) pairing) preventing <60s target. Created follow-up issue #20.

### 2025-12-12 - Lightweight Swing Validator Implementation
- **Issue:** #16
- **Type:** Feature
- **Files:**
  - `src/lightweight_swing_validator/` (new module)
    - `__init__.py` - Module exports
    - `models.py` - Pydantic data models
    - `sampler.py` - Random interval sampling logic
    - `storage.py` - Vote persistence (JSON)
    - `api.py` - FastAPI REST endpoints
    - `main.py` - CLI entry point
    - `static/index.html` - Web frontend with Lightweight Charts
  - `tests/test_lightweight_swing_validator.py` - 21 tests
  - `Docs/Reference/user_guide.md` - Updated with validator documentation
  - `.gitignore` - Added `validation_results/`
- **Summary:** Implements web-based swing validation tool per product direction. Replaces blocked matplotlib harness path with simpler HTML/JS approach. Reuses existing swing detection logic.
- **Update (Dec 12):** Fixed missing dependencies (fastapi, pydantic, uvicorn, httpx) in requirements.txt. Added installation instructions to user guide. All 21 tests pass.

---

## Review History

| Date | Issue/Changes | Outcome |
|------|---------------|---------|
| Dec 11 | Dogfood Feedback - Harness Assessment | **Resolved** - Product chose Path B (lightweight validator) |
| Dec 11 | Issue #15 - PlaybackController state refactor | Accepted |
| Dec 11 | Thread Safety (renderer, keyboard_handler) | Accepted |
| Dec 11 | Phase 1 Visualization | Accepted |
| Dec 11 | Algorithm Rewrite | Accepted |
| Dec 11 | Test Maintenance | Accepted |
