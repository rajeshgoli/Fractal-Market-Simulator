# Reference Layer Specification

**Status:** Draft (Revised)
**Author:** Product
**Date:** December 25, 2025
**Revision:** 2 — Correcting premature decisions

---

## Revision 2 Summary

**Corrections from user feedback on Rev 1:**

1. **0-2 validity for ALL scales** — Rev 1 incorrectly invalidated nested legs at origin (location=1). This would miss the entire extension zone (1-2) where ES typically completes at 2x. All scales now valid in 0-2 range.

2. **Origin breach ≠ instant invalidation** — Rev 1 was too aggressive. Invalidating at first origin touch leaves you with no references at the edges—exactly when you have the best edge. Especially for larger swings, tolerance is needed.

3. **S/M/L/XL kept as open question** — Rev 1 prematurely replaced scale classification with hierarchy depth. User feedback: "Can you still do north star vision without them? Maybe, maybe not." This requires exploration before deciding.

4. **Formation in Reference Layer** — Still valid from Rev 1.

5. **All-time range distribution** — Still valid from Rev 1.

---

## Purpose

The Reference Layer is a thin filter over the DAG's active legs. It answers:

> "Which of the current DAG legs qualify as valid trading references, and what is their salience?"

It does NOT:
- Freeze or capture historical state
- Modify DAG state
- Store its own legs/swings

It DOES:
- Apply its own formation rules (independent of DAG formation)
- Filter legs by validity using the 0-1-2 coordinate system
- Rank legs by salience (for reference selection)
- Provide location context (where is price relative to each reference)

---

## Inputs

From DAG (per bar):
- `active_legs`: List of Leg objects with:
  - `direction`: 'bull' | 'bear'
  - `origin_price`, `origin_index`
  - `pivot_price`, `pivot_index`
  - `range`: |pivot - origin|
  - `impulse`: float (points per bar)
  - `impulsiveness`: Optional[float] (percentile 0-100)
  - `parent_id`: Optional[str]
  - `depth`: int (hierarchy depth — 0 = root)

From caller:
- `current_bar`: Bar with OHLC
- `all_ranges`: Historical range distribution (all-time, from formed legs)

---

## Outputs

```python
@dataclass
class ReferenceSwing:
    """A DAG leg that qualifies as a valid trading reference."""
    leg: Leg                      # The underlying DAG leg
    scale: str                    # 'S' | 'M' | 'L' | 'XL' (see exploration section)
    location: float               # Current price in reference frame (0-2 range)
    salience_score: float         # Higher = more relevant reference
    origin_stress: float          # How close to origin breach (0 = safe, 1 = at origin)

@dataclass
class ReferenceState:
    """Complete reference layer output for current bar."""
    references: List[ReferenceSwing]  # All valid references, ranked by salience
    by_scale: Dict[str, List[ReferenceSwing]]  # Grouped by S/M/L/XL
    by_direction: Dict[str, List[ReferenceSwing]]  # Grouped by bull/bear
```

**Design notes:**
- `scale` retained pending exploration (see "Scale vs Hierarchy" section)
- `origin_stress` tracks proximity to origin breach without instant invalidation
- Invalid legs (location outside 0-2) are excluded from output

---

## Validity Rules

A DAG leg is a valid reference if ALL conditions are met:

### 1. Reference Layer Formation

Formation is a Reference Layer concept — DAG tracks structural candidates, Reference Layer decides which qualify as valid references.

Formation criteria (applied by Reference Layer):

```python
def is_formed_for_reference(leg, current_bar_index, config):
    """
    Reference Layer's own formation check.
    May differ from DAG's structural formation.
    """
    age = current_bar_index - leg.origin_index

    # Scale-dependent formation threshold
    # Larger swings need more confirmation
    if leg.scale in ('L', 'XL'):
        min_age = config.big_formation_bars  # e.g., 5
    else:
        min_age = config.small_formation_bars  # e.g., 2

    return age >= min_age
```

**Rationale:** Large swings are major structural references; they need time to prove valid. Small swings are refinements that can be used sooner.

### 2. Location Within Valid Range (ALL SCALES)

```
In reference frame terms: 0 <= location <= 2
```

**This applies to ALL scales.** The extension zone (1-2) is where the trade plays out — ES typically completes at 2x.

| Location | Meaning | Valid Reference? |
|----------|---------|------------------|
| < 0 | Pivot breached | No (with tolerance, see below) |
| 0–1 | In swing range | Yes |
| 1–2 | Extending toward target | **Yes (all scales)** |
| > 2 | Past completion | No |

### 3. Origin Breach Handling (NOT Instant Invalidation)

**Problem with instant invalidation:** If you delete a reference the moment origin is touched, you're left with no references at the edges — exactly when you have the best trading edge.

**Solution: Track stress, don't instantly invalidate.**

```python
def compute_origin_stress(leg, current_price):
    """
    Returns 0-1 indicating how stressed the reference is.
    0 = price far from origin (safe)
    1 = price at or past origin (maximum stress)
    """
    location = compute_location(leg, current_price)

    if location <= 0.5:
        return 0  # In defended zone, no stress
    elif location < 1.0:
        # Approaching origin — increasing stress
        return (location - 0.5) / 0.5  # Linear 0→1 as location goes 0.5→1
    else:
        return 1.0  # At or past origin

def is_fatally_breached(leg, bar, scale):
    """
    Scale-dependent fatal breach threshold.
    Larger swings tolerate more breach before invalidation.
    """
    location = compute_location(leg, bar.close)

    if scale in ('S', 'M'):
        # Small swings: invalidate when clearly past origin
        return location > 1.05  # 5% tolerance past origin
    else:  # L, XL
        # Large swings: more tolerance — these are structural
        return location > 1.15  # 15% tolerance past origin
```

**Key insight:** A reference in "stress" (location approaching 1) is still valuable — it tells you the swing is being tested. Only when clearly breached does it invalidate.

---

## Scale Classification (S/M/L/XL)

### Current Approach: Range Percentile Buckets

Scale is determined by range percentile within historical population:

| Scale | Percentile Range |
|-------|------------------|
| XL    | Top 10% (≥ P90)  |
| L     | 60-90% (P60-P90) |
| M     | 30-60% (P30-P60) |
| S     | Bottom 30% (<P30)|

```python
def classify_scale(leg_range, range_distribution):
    percentile = compute_percentile(leg_range, range_distribution)
    if percentile >= 90:
        return 'XL'
    elif percentile >= 60:
        return 'L'
    elif percentile >= 30:
        return 'M'
    else:
        return 'S'
```

**Note:** Range distribution is all-time; DAG pruning naturally handles recency.

### What Scale Classification Provides

Scale is used for:
1. **Tolerance rules** — L/XL get more tolerance before invalidation
2. **Formation thresholds** — L/XL need more bars to confirm
3. **Salience weighting** — Different weight profiles for big vs small
4. **Completion behavior** — Small swings "complete" at 2x; big swings never do

---

## Exploration Needed: Scale vs Hierarchy

**Open question:** Can DAG's hierarchy depth replace S/M/L/XL scale classification?

### What Hierarchy Depth Could Provide

| Depth | Meaning | Analogous to |
|-------|---------|--------------|
| 0 | Root legs — major market structure | XL/L |
| 1 | First-level children — intermediate swings | L/M |
| 2+ | Nested children — minor refinements | M/S |

**Potential advantages:**
1. **Structural meaning**: Depth = where leg sits in structure, not just size
2. **Stable**: Depth never changes (no hysteresis at percentile boundaries)
3. **Richer info**: Parent-child relationships enable rules like "prefer root's child"
4. **Already computed**: DAG provides this; no range distribution needed

### Questions Before Deciding

1. **Does depth correlate with scale?** If depth=0 legs are always L/XL by range, hierarchy might suffice. If not, we may need both.

2. **What north star rules depend on scale specifically?**
   - "Big swings never complete" — is this about range or structural importance?
   - Tolerance rules — should a small root leg get big-swing tolerance?

3. **Can tolerance rules use depth instead of scale?** E.g., depth=0 gets more tolerance regardless of range.

4. **What's the interaction?** A leg could be:
   - Depth=0, Range=Small (root but small range)
   - Depth=2, Range=Large (nested but large range)
   Which attribute matters for which rule?

### Exploration Task

Before deciding, analyze existing data:
1. Compute correlation between depth and range percentile
2. Identify cases where they disagree (small roots, large nested)
3. For each north star rule, determine which attribute matters

**Status:** Open — requires exploration before decision. 

---

## Salience Ranking

North star defines ideal reference as: **big, impulsive, and early** (for large swings) vs **recent** (for small swings).

### Salience Formula

```python
def compute_salience(leg, scale, current_bar_index, range_distribution):
    # Base: range (bigger = more salient)
    range_score = normalize(leg.range, range_distribution)  # 0-1

    # Impulse: faster moves are more salient
    impulse_score = (leg.impulsiveness or 50) / 100  # 0-1

    # Recency: bars since origin
    age = current_bar_index - leg.origin_index
    recency_score = 1 / (1 + age / 1000)  # Decay function

    # Scale-dependent weighting
    if scale in ('L', 'XL'):
        # Big swings: prefer early (low recency weight)
        weights = {'range': 0.5, 'impulse': 0.4, 'recency': 0.1}
    else:
        # Small swings: prefer recent
        weights = {'range': 0.2, 'impulse': 0.3, 'recency': 0.5}

    return (weights['range'] * range_score +
            weights['impulse'] * impulse_score +
            weights['recency'] * recency_score)
```

### Selection Within Scale

Per north star: "Practically there can be 3-4 reference swings per stage of hierarchy"

For each scale, keep top N by salience (configurable, default N=4):
- Biggest
- Most impulsive
- Most recent
- (Others by combined score)

---

## Location Computation

Location tells us where current price sits within the reference frame:

```python
def compute_location(leg, current_price):
    """
    Returns position in reference frame:
    - 0 = at defended pivot (origin for bull, will extend for bear)
    - 1 = at origin (start of move)
    - 2 = at completion target

    For bull: location = (current - pivot) / range + 0
              when current = pivot: location = 0
              when current = origin: location = 1
              when current = origin + range: location = 2

    Wait, let me reconsider based on valid_swings.md terminology:
    - Origin (1): where move started
    - Defended pivot (0): the extreme that must hold
    - Target (2): completion level

    For bull swing (high before low, bearish setup):
    - Origin = HIGH (where move started going down)
    - Defended pivot = LOW (must hold)
    - 0 = defended pivot (low)
    - 1 = origin (high)
    - 2 = low - range (target below)

    For bear swing (low before high, bullish setup):
    - Origin = LOW (where move started going up)
    - Defended pivot = HIGH (must hold)
    - 0 = defended pivot (high)
    - 1 = origin (low)
    - 2 = high + range (target above)
    """
    # Use ReferenceFrame class for this
    frame = ReferenceFrame(
        anchor0=leg.pivot_price,  # defended pivot = 0
        anchor1=leg.origin_price,  # origin = 1
        direction="BULL" if leg.direction == 'bull' else "BEAR"
    )
    return frame.to_ratio(current_price)
```

**Key insight:** Location tells downstream rules where we are:
- `0 < location < 1`: Between pivot and origin (in the swing range)
- `1 < location < 2`: Extended past origin toward target
- `location >= 2`: Completed (for small swings)
- `location < 0`: Pivot violated (check tolerance)

---

## API Design

```python
class ReferenceLayer:
    """Thin filter over DAG legs to identify valid trading references."""

    def __init__(self, config: ReferenceConfig = None):
        self.config = config or ReferenceConfig.default()
        self._range_distribution = []  # All-time, updated incrementally

    def update(self, legs: List[Leg], bar: Bar) -> ReferenceState:
        """
        Main entry point. Called each bar after DAG processes.

        Args:
            legs: Active legs from DAG (formation check done here)
            bar: Current bar (for location checks)

        Returns:
            ReferenceState with valid references ranked by salience
        """
        # Update range distribution (all-time)
        self._update_range_distribution(legs)

        references = []
        for leg in legs:
            scale = self._classify_scale(leg.range)

            # Reference Layer formation check
            if not self._is_formed_for_reference(leg, scale, bar.index):
                continue

            location = self._compute_location(leg, bar.close)

            # Validity = location in valid range (with scale-dependent tolerance)
            if self._is_fatally_breached(leg, scale, location):
                continue

            # Compute stress and salience
            stress = self._compute_origin_stress(location)
            salience = self._compute_salience(leg, scale, bar.index)

            references.append(ReferenceSwing(
                leg=leg,
                scale=scale,
                location=location,
                salience_score=salience,
                origin_stress=stress
            ))

        # Sort by salience
        references.sort(key=lambda r: r.salience_score, reverse=True)

        return ReferenceState(
            references=references,
            by_scale=self._group_by_scale(references),
            by_direction=self._group_by_direction(references)
        )

    def _is_fatally_breached(self, leg, scale: str, location: float) -> bool:
        """
        Check if leg is fatally breached (scale-dependent tolerance).
        """
        if location < 0 or location > 2:
            return True

        # Scale-dependent origin breach tolerance
        if scale in ('S', 'M'):
            return location > 1.05  # 5% past origin
        else:  # L, XL
            return location > 1.15  # 15% past origin

    def get_reference_at_scale(self, state: ReferenceState, scale: str) -> Optional[ReferenceSwing]:
        """Get the most salient reference at a given scale."""
        refs = state.by_scale.get(scale, [])
        return refs[0] if refs else None

    def get_active_levels(self, state: ReferenceState) -> Dict[str, List[float]]:
        """
        Get key price levels from all valid references.

        Returns dict with fib levels: {
            '0': [...],      # Defended pivots
            '0.382': [...],  # Key support/resistance
            '0.5': [...],
            '0.618': [...],
            '1': [...],      # Origins
            '1.382': [...],
            '1.5': [...],
            '1.618': [...],
            '2': [...],      # Completion targets
        }
        """
        pass  # Implementation aggregates levels from all references
```

---

## Configuration

```python
@dataclass
class ReferenceConfig:
    # Scale thresholds (percentiles)
    xl_threshold: float = 0.90  # Top 10%
    l_threshold: float = 0.60   # Top 40%
    m_threshold: float = 0.30   # Top 70%

    # Formation thresholds (bars since origin)
    big_formation_bars: int = 5       # L/XL need more confirmation
    small_formation_bars: int = 2     # S/M form faster

    # Origin breach tolerance (location past 1.0)
    small_origin_tolerance: float = 0.05  # 5% for S/M
    big_origin_tolerance: float = 0.15    # 15% for L/XL

    # Salience weights (big swings: L/XL)
    big_range_weight: float = 0.5
    big_impulse_weight: float = 0.4
    big_recency_weight: float = 0.1

    # Salience weights (small swings: S/M)
    small_range_weight: float = 0.2
    small_impulse_weight: float = 0.3
    small_recency_weight: float = 0.5

    # Selection
    max_references_per_scale: int = 4
```

---

## Integration Points

### With DAG

```python
# In main processing loop
for bar in bars:
    # DAG processes bar first
    events = detector.process_bar(bar)

    # Reference layer filters current state
    # Note: Pass ALL legs; Reference Layer does its own formation check
    legs = detector.get_state().active_legs
    ref_state = reference_layer.update(legs, bar)

    # Downstream rules use ref_state
    for ref in ref_state.references:
        # Apply trading rules...
```

### With Trading Rules (Future)

The Reference Layer output feeds into:

1. **Move Completion Detection**
   ```python
   # Small swings reaching 2x = completion event
   for ref in ref_state.by_scale.get('S', []) + ref_state.by_scale.get('M', []):
       if ref.location >= 2.0:
           emit_completion_event(ref)
   # Big swings never "complete" per north star
   ```

2. **Frustration Rule**
   ```python
   # If near 1.5 but repeatedly rejected...
   if 1.45 < ref.location < 1.55 and rejection_count > N:
       expect_retracement_to(0.5)
   ```

3. **Stacked Targets Detection**
   ```python
   targets_2x = [ref.leg.get_level(2.0) for ref in refs]
   if targets_cluster(targets_2x, tolerance=0.01):
       emit_stacked_targets_warning()
   ```

4. **Multi-Scale Interaction**
   ```python
   # Find where levels from different scales align
   aligned = find_level_alignments(ref_state)
   ```

5. **Origin Stress Monitoring**
   ```python
   # Track references under stress (approaching origin)
   stressed = [r for r in ref_state.references if r.origin_stress > 0.5]
   # These references are being tested — high edge potential
   ```

---

## What This Spec Explicitly Defers

1. **Impulse-based filtering** — DAG provides impulse metrics, but filtering on "impulsiveness" as a validity criterion is deferred. Currently used only for salience ranking.

2. **Sibling preference rules** — North star mentions preferring certain siblings. Current spec ranks by salience but doesn't have explicit sibling logic.

3. **Cross-timeframe aggregation** — This spec assumes single-timeframe operation. Multi-timeframe reference selection is a separate concern.

4. **Trading signal generation** — Reference Layer identifies references; it doesn't generate trading signals. That's a downstream consumer.

---

## Open Questions

### Resolved

1. **Range distribution scope** — **RESOLVED: All-time.**
   DAG naturally prunes older legs, so all-time distribution reflects the relevant population.

2. **0-2 validity range** — **RESOLVED: All scales use 0-2.**
   Extension zone (1-2) is where ES typically completes. All scales valid in 0-2 range.

3. **Origin breach handling** — **RESOLVED: Tolerance, not instant invalidation.**
   Track `origin_stress` as location approaches 1. Scale-dependent tolerance before fatal breach (S/M: 5%, L/XL: 15%).

### Still Open

1. **Scale vs hierarchy depth** — Can hierarchy depth replace S/M/L/XL? Requires exploration. See "Exploration Needed" section.

2. **Scale boundary hysteresis** — If we keep percentile-based scale, a leg near a boundary might flip scales bar-to-bar. Options:
   - Hysteresis band (e.g., 5% buffer around thresholds)
   - Lock scale at formation time
   - Accept the flip-flopping (may not matter in practice)

3. **Pivot breach tolerance** — Current spec focuses on origin breach. What about pivot breach (location < 0)? Should large swings get tolerance there too?

4. **Parent preference in salience** — Should a child of the most salient large swing be preferred over children of less salient swings?

---

## Success Criteria

Reference Layer is working when:

1. L1-L7 from valid_swings.md are identified as valid references at appropriate points in time
2. Scale classification matches intuition (L1 is XL, L7 is S/M)
3. Salience ranking puts the "right" references at the top within each scale
4. Location computation enables downstream rules to work (0-2 range for all scales)
5. Origin stress tracking identifies references being tested without premature invalidation
6. Formation rules correctly filter out structural candidates that aren't mature enough
7. Performance: <1ms per bar for filtering

---

## Feedback History

### Initial Feedback (Dec 25, 2025) — Addressed in Rev 1

| # | Feedback | Resolution |
|---|----------|------------|
| 1 | Formation belongs in Reference Layer | ✅ Added scale-dependent formation check |
| 2 | Completion is DAG concern | ✅ Removed `is_completed` from Reference Layer |
| 3 | Scale classification still needed? | ⏳ Kept as open question (see Rev 2) |
| 4 | Range distribution — all-time | ✅ Documented as all-time |
| 5 | Invalidation = simple 1x retrace | ⚠️ Revised in Rev 2 (see below) |
| 6 | Hierarchy could replace scale | ⏳ Added exploration section (see Rev 2) |
| 7 | Scale boundary hysteresis | ⏳ Added as open question (see Rev 2) |

### Correction Feedback (Dec 25, 2025) — Addressed in Rev 2

| # | Feedback | Resolution |
|---|----------|------------|
| 1 | 0-2 validity for ALL scales | ✅ All scales valid in 0-2; extension zone (1-2) needed for ES completion at 2x |
| 2 | Origin breach ≠ instant invalidation | ✅ Added `origin_stress` tracking; scale-dependent tolerance before fatal breach |
| 3 | S/M/L/XL removal was premature | ✅ Restored scale; added exploration section for scale vs hierarchy decision |

---

## Next Steps

1. ~~Address initial feedback~~ ✅ Done in Rev 1
2. ~~Address correction feedback~~ ✅ Done in Rev 2
3. Get user sign-off on revised spec
4. **Exploration:** Analyze depth vs scale correlation before deciding on replacement
5. Delete existing `reference_layer.py`
6. Implement new Reference Layer per approved spec
7. Wire into replay backend
