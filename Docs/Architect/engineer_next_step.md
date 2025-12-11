# Engineer Next Step: Phase 1 - Visualization Improvements

**Priority:** HIGH
**Status:** Ready for implementation
**Owner:** Engineering
**Date:** December 11, 2025

---

## Objective

Implement three visualization improvements to reduce visual clutter and improve usability:

1. **S-Scale Swing Cap** (Priority 1)
2. **Dynamic Bar Aggregation** (Priority 2)
3. **Stability Audit** (Priority 3 - parallel track)

---

## 1. S-Scale Swing Cap

### Problem

S-scale panels often display 20-30+ swings, making the visualization unreadable. Users need to see only the most relevant swings.

### Specification

**Default behavior:** Show top 5 swings per scale, scored by `recency × size`

**Scoring formula:**
```python
score = recency_weight * recency_factor + size_weight * normalized_size
# where:
#   recency_factor = 1.0 - (bars_since_swing / max_bars)
#   normalized_size = swing_size / max_swing_size
#   recency_weight = 0.6, size_weight = 0.4
```

**Special rule:** The swing associated with the most recent event is ALWAYS visible, regardless of cap.

**Configuration:**
- Default cap: 5 swings
- Configurable via `RenderConfig.max_swings_per_scale`
- Toggle: keyboard shortcut to show/hide all swings (temporarily bypass cap)

### Implementation Location

**File:** `src/visualization/renderer.py`

**Method to modify:** `_group_swings_by_scale()` (line 903-911)

**Current:**
```python
def _group_swings_by_scale(self, swings: List[ActiveSwing]) -> Dict[str, List[ActiveSwing]]:
    """Group swings by their scale."""
    groups = {}
    for swing in swings:
        scale = swing.scale
        if scale not in groups:
            groups[scale] = []
        groups[scale].append(swing)
    return groups
```

**Target:**
```python
def _group_swings_by_scale(self, swings: List[ActiveSwing],
                           current_bar_idx: int = None,
                           recent_event_swing_id: str = None) -> Dict[str, List[ActiveSwing]]:
    """Group swings by scale, applying swing cap filtering."""
    groups = {}
    for swing in swings:
        scale = swing.scale
        if scale not in groups:
            groups[scale] = []
        groups[scale].append(swing)

    # Apply cap if enabled
    if self.config.max_swings_per_scale > 0:
        for scale, scale_swings in groups.items():
            groups[scale] = self._apply_swing_cap(
                scale_swings,
                current_bar_idx,
                recent_event_swing_id
            )

    return groups
```

**New helper method:**
```python
def _apply_swing_cap(self,
                     swings: List[ActiveSwing],
                     current_bar_idx: int,
                     recent_event_swing_id: str = None) -> List[ActiveSwing]:
    """Filter swings to top N by recency × size score."""
    if len(swings) <= self.config.max_swings_per_scale:
        return swings

    max_bar = current_bar_idx or 1
    max_size = max(s.size for s in swings) if swings else 1

    def score(swing):
        recency = 1.0 - (max_bar - swing.low_bar_idx) / max(max_bar, 1)
        size_norm = swing.size / max_size
        return 0.6 * recency + 0.4 * size_norm

    # Sort by score descending
    scored = sorted(swings, key=score, reverse=True)
    top_swings = scored[:self.config.max_swings_per_scale]

    # Ensure recent event swing is included
    if recent_event_swing_id:
        for swing in swings:
            if swing.swing_id == recent_event_swing_id and swing not in top_swings:
                top_swings.append(swing)
                break

    return top_swings
```

**Config update:** Add to `RenderConfig` in `config.py`:
```python
max_swings_per_scale: int = 5  # 0 = show all
show_all_swings: bool = False  # Toggle state for bypass
```

### Testing

- Test with 30+ swings: verify only 5 shown by default
- Test scoring: larger recent swings should rank higher than smaller old ones
- Test event swing inclusion: swing from latest event always visible
- Test toggle: verify all swings show when toggled

---

## 2. Dynamic Bar Aggregation

### Problem

When viewing long time periods, too many candles crowd the display. When zoomed in, candles are too sparse. The display should auto-adjust timeframe aggregation.

### Specification

**Target:** 40-60 candles visible per quadrant

**Algorithm:**
1. Calculate visible time range from `view_window`
2. Calculate source bar count in that range
3. Select aggregation timeframe that yields 40-60 aggregated bars
4. Available timeframes: 1, 5, 15, 30, 60, 240 minutes

**Hierarchy constraint:** Never show higher aggregation for S-scale than M-scale, etc.

### Implementation Location

**File:** `src/visualization/renderer.py`

**Method to modify:** `calculate_view_window()` (line 745) and `render_panel()` (line 370)

**New helper method:**
```python
def _calculate_optimal_timeframe(self,
                                  scale: str,
                                  source_bar_count: int) -> int:
    """
    Select timeframe to achieve 40-60 visible candles.

    Args:
        scale: Current scale (S, M, L, XL)
        source_bar_count: Number of 1-minute bars in visible range

    Returns:
        Optimal aggregation timeframe in minutes
    """
    AVAILABLE_TIMEFRAMES = [1, 5, 15, 30, 60, 240]
    TARGET_CANDLES_MIN = 40
    TARGET_CANDLES_MAX = 60
    TARGET_CANDLES = 50  # Ideal target

    # Base timeframe from scale config (never go below this)
    base_timeframe = self.scale_config.aggregations.get(scale, 1)

    # Find optimal timeframe
    best_tf = base_timeframe
    best_diff = float('inf')

    for tf in AVAILABLE_TIMEFRAMES:
        if tf < base_timeframe:
            continue  # Respect scale hierarchy

        candle_count = source_bar_count / tf

        if TARGET_CANDLES_MIN <= candle_count <= TARGET_CANDLES_MAX:
            # Within target range - prefer lower timeframe for more detail
            if tf < best_tf or abs(candle_count - TARGET_CANDLES) < best_diff:
                best_tf = tf
                best_diff = abs(candle_count - TARGET_CANDLES)
        elif candle_count < TARGET_CANDLES_MIN and tf < best_tf:
            # Too few candles - use lower timeframe
            best_tf = tf

    return best_tf
```

**Modify `render_panel()`:**
```python
# Replace fixed timeframe lookup with dynamic calculation
# OLD: timeframe = self.scale_config.aggregations.get(scale, 1)
# NEW:
source_bar_span = view_window.end_idx - view_window.start_idx
timeframe = self._calculate_optimal_timeframe(scale, source_bar_span)
```

### Testing

- Verify 40-60 candles visible across different time ranges
- Verify scale hierarchy maintained (S never coarser than M, etc.)
- Verify smooth transitions when time range changes

---

## 3. Stability Audit (Parallel Track)

### Problem

Layout transitions and state management have known issues. Document and catalog them.

### Scope

**Document these areas:**
1. Layout transition state loss (expand/collapse, quad mode)
2. Pause/resume state inconsistencies
3. Frame skipping edge cases
4. Keyboard handler state synchronization

### Deliverable

Create `Docs/engineer_notes/stability_audit_dec11.md` with:

1. **Issue Catalog:** List each issue with:
   - Description
   - Steps to reproduce
   - Severity (Critical/High/Medium/Low)
   - Affected files

2. **Recommendations:** Suggested fixes for each issue

3. **Priority Order:** Rank fixes by impact

### Investigation Areas

**File locations to examine:**
- `src/visualization/renderer.py` - layout transition handling
- `src/visualization/keyboard_handler.py` - state synchronization
- `src/cli/harness.py` - playback state management
- `src/playback/controller.py` - pause/resume logic

**Known symptoms to investigate:**
- Swings disappear after layout toggle
- Events not rendering after pause/resume
- Frame skipping causing missed updates
- Expand mode not preserving swing visibility

---

## Implementation Checklist

### Phase 1.1: S-Scale Swing Cap
- [ ] Add `max_swings_per_scale` to `RenderConfig`
- [ ] Add `show_all_swings` toggle to `RenderConfig`
- [ ] Implement `_apply_swing_cap()` method
- [ ] Modify `_group_swings_by_scale()` to apply cap
- [ ] Add keyboard shortcut for toggle (suggest: `A` for "all swings")
- [ ] Write tests for swing cap logic
- [ ] Update user guide with new feature

### Phase 1.2: Dynamic Bar Aggregation
- [ ] Implement `_calculate_optimal_timeframe()` method
- [ ] Integrate into `render_panel()`
- [ ] Ensure scale hierarchy constraint
- [ ] Test across various time ranges
- [ ] Document behavior in user guide

### Phase 1.3: Stability Audit
- [ ] Review layout transition code
- [ ] Review state management code
- [ ] Document findings in audit report
- [ ] Prioritize fixes

---

## Success Criteria

| Feature | Metric |
|---------|--------|
| Swing Cap | Default shows ≤5 swings; toggle works; event swing always visible |
| Dynamic Agg | 40-60 candles visible; scale hierarchy preserved |
| Stability Audit | Complete catalog with severity ratings |

---

## Testing Requirements

Run existing tests after each change:
```bash
source venv/bin/activate && python -m pytest tests/ -v
```

Manual testing:
1. Load data with 30+ S-scale swings
2. Verify only 5 shown by default
3. Toggle visibility and verify all show
4. Zoom in/out and verify candle count adjusts
5. Test layout transitions for state preservation

---

## Handoff Protocol

When complete:
1. Run full test suite
2. Create engineer note: `Docs/engineer_notes/phase1_visualization_dec11.md`
3. Return to Architect: "Ready for architect review"

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/visualization/config.py` | Add swing cap config |
| `src/visualization/renderer.py` | Swing cap + dynamic agg logic |
| `src/visualization/keyboard_handler.py` | Toggle shortcut |
| `Docs/Product/user_guide.md` | Document new features |
| `Docs/engineer_notes/stability_audit_dec11.md` | Audit findings |
