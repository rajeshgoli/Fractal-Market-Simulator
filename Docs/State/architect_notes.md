# Architect Notes

## Current Phase: Phase 3 Design Complete

**Status:** Phases 1-2 implemented. Phase 3 designed, ready for implementation.
**Owner:** Engineering

---

## System State

| Component | Status | Notes |
|-----------|--------|-------|
| Swing Detector | Healthy | Phase 1 (adjust_extrema) + Phase 2 (quota) implemented |
| Ground Truth Annotator | Healthy | Two-click annotation + Review Mode + skip scales + schema v4 |
| Test Suite | Healthy | All tests passing |
| Documentation | Current | user_guide.md and developer_guide.md updated |

---

## P0 Design: Endpoint Selection (Fib Confluence + Best Extrema + Quota)

### Problem Statement

Ver3 sessions show **75% of FPs are endpoint selection issues** (better_high/low/both). Core swing detection works; need to pick better endpoints when alternatives exist.

### Architecture Decision: Three-Layer Approach

```
Layer 1: Fib Confluence Score (Primary Signal)
    ↓
Layer 2: Best Extrema Adjustment (Tie Breaker)
    ↓
Layer 3: Quota per Scale (Quantity Control)
```

---

### Layer 1: Fib Confluence Scoring

**Purpose:** Prefer swing endpoints that land near fib levels of larger swings. These are structurally significant—price respects them because participants watch them.

#### Design Decisions

| Question | Answer | Rationale |
|----------|--------|-----------|
| Which larger swing to reference? | **Immediate containing swing only** | Multiple ancestors adds complexity without clear benefit. The immediate parent is the dominant structure. |
| Score method? | **Proximity to nearest fib level** | Simpler than "confluence count." A point near one important level is better than points near nothing. |
| Tolerance for "near"? | **0.5% of swing size** | Adaptive to swing magnitude. A 100-point swing tolerates 0.5 point; a 10-point swing tolerates 0.05. |

#### Algorithm

```python
def calculate_fib_confluence_score(endpoint_price: float, containing_swing: dict) -> float:
    """
    Score how close a price is to any fib level of the containing swing.

    Returns:
        Score from 0.0 (no confluence) to 1.0 (exactly on level)
    """
    # Calculate fib levels of the containing swing
    levels = calculate_levels(containing_swing['high'], containing_swing['low'], direction)

    # Find minimum distance to any fib level
    swing_size = containing_swing['high'] - containing_swing['low']
    tolerance = 0.005 * swing_size  # 0.5% of swing size

    min_distance = float('inf')
    for level in levels:
        distance = abs(endpoint_price - level.price)
        min_distance = min(min_distance, distance)

    # Convert to score (1.0 = on level, 0.0 = beyond tolerance)
    if min_distance <= tolerance:
        return 1.0 - (min_distance / tolerance)
    else:
        return 0.0
```

#### Finding the Containing Swing

```python
def find_containing_swing(swing: dict, all_swings: list, scale_hierarchy: list) -> Optional[dict]:
    """
    Find the smallest swing at a larger scale that contains this swing.

    A containing swing has:
    - high >= swing.high
    - low <= swing.low
    - bar_index range overlaps
    - Scale is one level larger (e.g., M contains S)
    """
    larger_scale = get_next_larger_scale(swing['scale'])  # S→M, M→L, L→XL

    candidates = [s for s in all_swings
                  if s['scale'] == larger_scale
                  and s['high'] >= swing['high']
                  and s['low'] <= swing['low']]

    if not candidates:
        return None

    # Return smallest containing swing (most relevant context)
    return min(candidates, key=lambda s: s['size'])
```

#### Integration Point

After swing detection and pairing, before redundancy filtering:

```
Current Pipeline:
1. Swing detection (vectorized)
2. Pairing and validation
3. Protection validation
4. Size filter
5. Prominence filter
6. Redundancy filtering  ← FIB SCORING HERE (needs larger-scale swings)
7. Ranking
8. max_rank filter

Modified Pipeline:
1-5. (unchanged)
6. Calculate fib confluence score for each swing
7. Redundancy filtering (can use score as tiebreaker)
8. Ranking (incorporate fib score)
9. max_rank filter / quota
```

**Key insight:** Fib scoring requires knowledge of larger-scale swings. The annotator already runs detection at multiple scales. The scoring should happen at the annotation layer, not in the core detector.

---

### Layer 2: Best Extrema Adjustment

**Purpose:** When multiple candidate endpoints exist, prefer the most extreme (highest high / lowest low) in the vicinity.

#### Design Decisions

| Question | Answer | Rationale |
|----------|--------|-----------|
| How to define "vicinity"? | **lookback bars** (same as detection) | Consistent with swing detection semantics. Already parameterized. |
| Post-filter or integrated? | **Post-filter** | Cleaner separation. Run after detection, adjust endpoints without re-running detection. |

#### Algorithm

```python
def adjust_to_best_extrema(swing: dict, highs: np.ndarray, lows: np.ndarray, lookback: int) -> dict:
    """
    Adjust swing endpoints to the best extrema in vicinity.

    For swing highs: find highest high within ±lookback bars
    For swing lows: find lowest low within ±lookback bars
    """
    adjusted = swing.copy()

    # Adjust high endpoint
    high_idx = swing['high_bar_index']
    start = max(0, high_idx - lookback)
    end = min(len(highs), high_idx + lookback + 1)

    window_highs = highs[start:end]
    best_high_offset = np.argmax(window_highs)
    best_high_idx = start + best_high_offset

    adjusted['high_bar_index'] = best_high_idx
    adjusted['high_price'] = highs[best_high_idx]

    # Adjust low endpoint
    low_idx = swing['low_bar_index']
    start = max(0, low_idx - lookback)
    end = min(len(lows), low_idx + lookback + 1)

    window_lows = lows[start:end]
    best_low_offset = np.argmin(window_lows)
    best_low_idx = start + best_low_offset

    adjusted['low_bar_index'] = best_low_idx
    adjusted['low_price'] = lows[best_low_idx]

    # Recalculate size
    adjusted['size'] = adjusted['high_price'] - adjusted['low_price']

    return adjusted
```

#### Integration Point

After pairing, before any filtering:

```
1. Swing detection
2. Pairing and validation
3. **Best extrema adjustment** ← HERE
4. Protection validation (re-validate with adjusted endpoints)
5. Size filter
6. Prominence filter
7. Fib confluence scoring
8. Redundancy filtering
9. Ranking
10. Quota filter
```

---

### Layer 3: Quota per Scale

**Purpose:** Control swing quantity by scale without threshold tuning. Best swings naturally surface; scale determines how many to show.

#### Design Decisions

| Question | Answer | Rationale |
|----------|--------|-----------|
| How to rank swings? | **Combined score: 0.6×size_rank + 0.4×impulse_rank** | Size captures magnitude; impulse (size/span) captures conviction. Weighting is tunable. |
| Quota per scale? | **XL=4, L=6, M=10, S=15** | Fewer swings at larger scales (more significant). More detail at smaller scales. |

#### Algorithm

```python
def apply_quota(swings: list, scale: str, direction: str) -> list:
    """
    Rank swings by combined score and return top N per scale.
    """
    QUOTA = {'XL': 4, 'L': 6, 'M': 10, 'S': 15}
    SIZE_WEIGHT = 0.6
    IMPULSE_WEIGHT = 0.4

    # Calculate impulse for each swing
    for swing in swings:
        span = abs(swing['high_bar_index'] - swing['low_bar_index']) + 1
        swing['impulse'] = swing['size'] / span

    # Rank by size (1 = largest)
    by_size = sorted(swings, key=lambda s: s['size'], reverse=True)
    for rank, swing in enumerate(by_size, 1):
        swing['size_rank'] = rank

    # Rank by impulse (1 = most impulsive)
    by_impulse = sorted(swings, key=lambda s: s['impulse'], reverse=True)
    for rank, swing in enumerate(by_impulse, 1):
        swing['impulse_rank'] = rank

    # Combined score (lower is better)
    for swing in swings:
        swing['combined_score'] = (SIZE_WEIGHT * swing['size_rank'] +
                                   IMPULSE_WEIGHT * swing['impulse_rank'])

    # Sort by combined score and take top N
    swings.sort(key=lambda s: s['combined_score'])
    quota = QUOTA.get(scale, 10)

    return swings[:quota]
```

#### Integration Point

Replaces `max_rank` filter:

```
...
8. Redundancy filtering
9. **Quota filter** (replaces max_rank)
10. Final ranking assignment
```

---

## Implementation Phases

### Phase 1: Best Extrema Adjustment ✓ DONE (#65)

**Scope:** Add endpoint adjustment as post-processing step.

**Implemented:**
- `_adjust_to_best_extrema()` function in `swing_detector.py`
- `adjust_extrema: bool = True` parameter
- Called after pairing, before protection validation
- Protection re-validated with adjusted endpoints

**Impact:** Endpoints now snap to best high/low within lookback window.

### Phase 2: Quota per Scale ✓ DONE (#66)

**Scope:** Replace threshold-based filtering with quota.

**Implemented:**
- `_apply_quota()` function in `swing_detector.py`
- `quota: Optional[int]` parameter (replaces `max_rank`)
- New output fields: `impulse`, `size_rank`, `impulse_rank`, `combined_score`
- Scale-specific quotas: XL=4, L=6, M=10, S=15

**Impact:** Best swings surface via combined size+impulse ranking.

### Phase 3: FIB-Aware Endpoint Selection (Unified)

**Scope:** Add FIB-based structural separation gate AND confluence scoring.

This phase combines two FIB relationships:
1. **Structural Separation Gate** (new) — Swings must be ≥1 FIB level apart from previous swing
2. **Fib Confluence Scoring** (existing design) — Prefer endpoints that land on FIB levels

**3A: Structural Separation Gate**

Validates that consecutive swings are structurally distinct, measured in FIB units.

**Extended FIB Grid for Separation:**

Standard levels have asymmetric gaps that work for price projection but miss valid reversals. For separation calculation, use a denser symmetric grid:

```
Standard:  0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0
Extended:  0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0
```

The additions (0.236, 0.786, 1.236, 1.786) fill the voids where legitimate structural reversals occur.

```python
# Separation-specific FIB levels (symmetric grid)
SEPARATION_FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0]

def is_structurally_separated(swing: dict, previous_swings: list, larger_swings: list) -> bool:
    """
    Check if swing is structurally separated from previous swings.

    For High B to register after High A:
    1. There must be a Low L between A and B
    2. L must be ≥1 FIB level from High A (on larger-scale grid)
    3. High B and L must be ≥1 FIB level apart

    Uses extended FIB grid (includes 0.236, 0.786, 1.236, 1.786) for
    better coverage of structural reversals.
    """
    if not larger_swings:
        # XL or window edge: use fallback
        return _fallback_separation_check(swing, previous_swings)

    # Get FIB grid from immediate larger swing
    containing = find_containing_swing(swing, larger_swings)
    if not containing:
        return _fallback_separation_check(swing, previous_swings)

    swing_size = containing['high_price'] - containing['low_price']
    min_separation = 0.236 * swing_size  # Minimum 1 FIB level (smallest on extended grid)

    # Check separation from previous swing endpoints
    for prev in previous_swings:
        separation = abs(swing['low_price'] - prev['high_price'])
        if separation < min_separation:
            return False  # Not structurally distinct

    return True
```

**Fallback for XL/window edges:**
```python
def _fallback_separation_check(swing: dict, previous_swings: list) -> bool:
    """Use N-bar or X% move when no larger swing exists."""
    MIN_BAR_SEPARATION = 2 * lookback  # Non-overlapping detection windows
    MIN_PRICE_SEPARATION = 0.236 * median_candle * lookback  # FIB-equivalent (smallest level)

    for prev in previous_swings:
        bar_sep = abs(swing['low_bar_index'] - prev['high_bar_index'])
        price_sep = abs(swing['low_price'] - prev['high_price'])

        if bar_sep < MIN_BAR_SEPARATION and price_sep < MIN_PRICE_SEPARATION:
            return False

    return True
```

**3B: Fib Confluence Scoring**

Score endpoints by proximity to FIB levels of containing swing (unchanged from original design):

```python
def calculate_fib_confluence_score(endpoint_price: float, containing_swing: dict) -> float:
    """
    Score how close a price is to any fib level of the containing swing.
    Returns: Score from 0.0 (no confluence) to 1.0 (exactly on level)
    """
    levels = calculate_levels(containing_swing['high'], containing_swing['low'], direction)
    swing_size = containing_swing['high'] - containing_swing['low']
    tolerance = 0.005 * swing_size  # 0.5% of swing size

    min_distance = min(abs(endpoint_price - level.price) for level in levels)

    if min_distance <= tolerance:
        return 1.0 - (min_distance / tolerance)
    return 0.0
```

**Ordering Requirement: Sequential XL→L→M→S**

Structural separation requires larger-scale swings as reference. Detection must run sequentially:

```python
# Current (parallel/independent)
s_swings = detect_swings(df, scale='S', ...)

# Required (sequential with context)
xl_swings = detect_swings(df, scale='XL', ...)
l_swings = detect_swings(df, scale='L', larger_swings=xl_swings, ...)
m_swings = detect_swings(df, scale='M', larger_swings=l_swings, ...)
s_swings = detect_swings(df, scale='S', larger_swings=m_swings, ...)
```

The annotator already cascades—the change is passing larger-scale results as context.

**Changes:**
- New parameter `larger_swings: Optional[List[dict]]` to `detect_swings()`
- New function `is_structurally_separated()` in `swing_detector.py`
- New function `calculate_fib_confluence_score()` in `level_calculator.py`
- New fields: `fib_confluence_score`, `structurally_separated`, `containing_swing_id`

**Expected impact:** Addresses 42% of FPs (extrema selection: better_high/low/both)

---

## Detection Pipeline (Proposed State)

```
Sequential scale processing: XL → L → M → S

Per scale:
1. Swing detection (vectorized, O(N log N))
2. Pairing and validation
3. Best extrema adjustment ← Phase 1 (DONE)
4. Protection validation (with adjusted endpoints)
5. Size filter (min_candle_ratio, min_range_pct)
6. Prominence filter (min_prominence)
7. Structural separation gate ← Phase 3A (uses larger-scale swings)
8. Redundancy filtering
9. Fib confluence scoring ← Phase 3B
10. Quota filter ← Phase 2 (replaces max_rank)
11. Final ranking
```

---

## Recommendation

**Current status:** Phase 1 ✓ → Phase 2 ✓ → **Phase 3 ready for implementation**

Phase 1 (Best Extrema) and Phase 2 (Quota) are complete and deployed.

Phase 3 (FIB-Aware Endpoint Selection) is designed and ready:
- 3A: Structural Separation Gate — requires ≥1 FIB level separation
- 3B: Fib Confluence Scoring — prefers endpoints on FIB levels
- Uses extended symmetric grid (includes 0.236, 0.786, 1.236, 1.786)
- Requires sequential XL→L→M→S processing with `larger_swings` context

**Expected impact:** Addresses remaining 42% of FPs (extrema selection issues).

---

## Documentation Status

| Document | Status |
|----------|--------|
| `Docs/Reference/user_guide.md` | Current |
| `Docs/Reference/developer_guide.md` | Current (filters documented) |
| `CLAUDE.md` | Current |

---

## Architecture Principles

- **Multi-scale:** Four simultaneous scales (S, M, L, XL)
- **Fibonacci levels:** 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0
- **Resolution-agnostic:** 1m to 1mo source data supported
- **Performance:** <60s for 6M bars, <3s window transitions
- **Lean codebase:** Single tool (ground truth annotator) for validation workflow

---

## Review History

| Date | Changes | Outcome |
|------|---------|---------|
| Dec 15 | Q-2025-12-15-2 (FIB structural separation): Feasibility assessment | Feasible → Merged into Phase 3 |
| Dec 15 | Q-2025-12-15-2: Endpoint selection design | Designed → Ready for implementation |
| Dec 15 | #59, #60, #61, #62, #63 — Annotation UX + Too Small + Prominence filters | All Accepted |
| Dec 15 | Q-2025-12-15-6: Too small + subsumed filter design | Designed → #62, #63 |
| Dec 15 | #54-#58 batch review | All Accepted |
| Dec 12 | Review Mode epic (#38) | All Accepted |
