# Reference Layer Specification

**Status:** Draft (Revised)
**Author:** Product
**Date:** December 31, 2025
**Revision:** 5 — Origin breach tolerance correction (aligned with north star)

---

## Revision 5 Summary (Dec 31, 2025)

**Origin breach tolerance correction:**

Spec had drifted from north star. Fixed to match `product_north_star.md` lines 122-128:

| Scale | Previous (Wrong) | Correct (North Star) |
|-------|------------------|----------------------|
| S/M | 5% tolerance | **0% (instant invalidation)** |
| L/XL | 15% single threshold | **15% trade + 10% close (two thresholds)** |

ReferenceConfig fields updated:
- `small_origin_tolerance: float = 0.0` — S/M default to zero tolerance per north star (configurable for tuning)
- Removed: `big_origin_tolerance` (single threshold)
- Added: `big_trade_breach_tolerance` (0.15), `big_close_breach_tolerance` (0.10)

---

## Revision 4 Summary (Dec 31, 2025)

**Major corrections from polymath interview:**

1. **Formation is PRICE-BASED, not age-based** — Rev 3 incorrectly used "bars since origin" for formation. Correct: a swing becomes a valid reference when price retraces to a fib threshold (default 38.2%). Example: bear leg becomes bull reference when subsequent bull leg reaches 38.2% retracement.

2. **Removed origin_stress concept** — Was never in north star; superfluous. Just use fatal breach detection with scale-dependent tolerance.

3. **Clarified terminology** — Bull reference = bear swing (and vice versa). The "origin breach" that invalidates a reference is when the confirming leg's origin is breached.

4. **XL completion just works via DAG** — When price exits 2x, retraces to ~1x, DAG spawns a new swing. New swing becomes reference; old one naturally falls outside 0-2 range. No special Reference Layer handling needed.

5. **Salience is context-dependent** — Weights should be UI tunable (like detection config). Different presets for scalping vs swing trading.

6. **No internal reference limit** — Keep all valid references; UI can limit display (max_references_per_scale removed from core).

7. **Add by_depth grouping** — For A/B testing scale vs hierarchy depth. Toggle between classification schemes in settings.

8. **UI: "Levels at Play"** — Menu item renamed from "Reference View" to "Levels at Play".

9. **Phase 1 scope expanded** — Add scale labels, direction color, location indicator from the start.

10. **Telemetry panel** — Full telemetry like DAG's market structure panel (not minimal logging).

---

## Previous Revision Summaries

<details>
<summary>Revision 3 (Dec 31, 2025)</summary>

**UI visualization approach:**
- Separate view accessible from hamburger menu
- Purpose: eyeball validation → rule discovery → algo input (not live trading)
- Same skeleton as DAG View, different lens
- Fib levels via hover/click, opt-in level crossing
</details>

<details>
<summary>Revision 2 (Dec 25, 2025)</summary>

- 0-2 validity for ALL scales (extension zone needed for ES completion at 2x)
- Origin breach ≠ instant invalidation (tolerance needed)
- S/M/L/XL kept as open question pending exploration
</details>

---

## Purpose

The Reference Layer is a thin filter over the DAG's active legs. It answers:

> "Which of the current DAG legs qualify as valid trading references, and what is their salience?"

It does NOT:
- Freeze or capture historical state
- Modify DAG state
- Store its own legs/swings
- Detect patterns like "frustration" (downstream consumer concern)
- Generate trading signals (downstream consumer concern)

It DOES:
- Apply its own formation rules (price-based, independent of DAG formation)
- Filter legs by validity using the 0-1-2 coordinate system
- Rank legs by salience (for reference selection)
- Provide location context (where is price relative to each reference)
- Track which legs are monitored for level crossings (opt-in)
- Emit telemetry for monitoring panel

---

## Key Terminology

| Term | Meaning |
|------|---------|
| **Bull reference** | A bear leg (high→low) that can be used for bullish trades |
| **Bear reference** | A bull leg (low→high) that can be used for bearish trades |
| **Origin** | Where the leg's move started (high for bear leg, low for bull leg) |
| **Pivot** | The extreme that must hold (low for bear leg, high for bull leg) |
| **Formation** | When a confirming move reaches the fib threshold (price-based) |
| **Invalidation** | When the confirming leg's origin is breached beyond tolerance |

---

## Inputs

From DAG (per bar):
- `active_legs`: List of Leg objects with:
  - `direction`: 'bull' | 'bear'
  - `origin_price`, `origin_index`
  - `pivot_price`, `pivot_index`
  - `range`: |pivot - origin|
  - `impulse`: float (points per bar)
  - `impulsiveness`: Optional[float] (percentile 0-100, provided by DAG)
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
    scale: str                    # 'S' | 'M' | 'L' | 'XL' (percentile-based)
    depth: int                    # Hierarchy depth from DAG (for A/B testing)
    location: float               # Current price in reference frame (0-2 range, capped)
    salience_score: float         # Higher = more relevant reference

@dataclass
class LevelInfo:
    """A fib level with its source reference."""
    price: float                  # The price level
    ratio: float                  # The fib ratio (0, 0.382, 0.5, etc.)
    reference: ReferenceSwing     # Source reference

@dataclass
class ReferenceState:
    """Complete reference layer output for current bar."""
    references: List[ReferenceSwing]  # All valid references (no limit), ranked by salience
    by_scale: Dict[str, List[ReferenceSwing]]  # Grouped by S/M/L/XL
    by_depth: Dict[int, List[ReferenceSwing]]  # Grouped by hierarchy depth (for A/B)
    by_direction: Dict[str, List[ReferenceSwing]]  # Grouped by bull/bear
    direction_imbalance: Optional[str]  # 'bull' | 'bear' | None if balanced
```

**Design notes:**
- No internal limit on references (UI can limit display)
- `location` capped at 2.0 (suffices for 99.999% of swings)
- `depth` included for A/B testing scale vs hierarchy
- `direction_imbalance` highlights when one direction dominates

---

## Validity Rules

A DAG leg is a valid reference if ALL conditions are met:

### 1. Reference Layer Formation (PRICE-BASED)

**Critical correction from Rev 3:** Formation is NOT about age (bars since origin). Formation is about price action.

A leg becomes a valid reference when the subsequent confirming move reaches the formation threshold:

```python
def is_formed_for_reference(leg, current_price, config):
    """
    Reference Layer's formation check.

    A bear leg becomes a bull reference when price retraces UP
    to reach the formation threshold (e.g., 38.2% of the leg's range).

    A bull leg becomes a bear reference when price retraces DOWN
    to reach the formation threshold.
    """
    # Compute current location in reference frame
    location = compute_location(leg, current_price)

    # Formation threshold (default 0.382)
    threshold = config.formation_fib_threshold

    # For a valid reference, price must have reached the threshold
    # Location 0 = pivot, Location 1 = origin
    # For bull reference (bear leg): price must have risen to threshold
    # For bear reference (bull leg): price must have fallen to threshold

    # If current location is between 0 and threshold, swing is formed
    # (price has moved away from origin toward pivot by at least threshold)
    return location <= (1.0 - threshold)  # e.g., location <= 0.618 for 38.2% threshold
```

**Example:** Bear leg from $110 (origin) to $100 (pivot), range = $10.
- Formation threshold = 0.382 (38.2%)
- Price must rise to $103.82 (38.2% retracement from pivot toward origin)
- At that point, location = 0.382, which is <= 0.618, so formed = True
- Once formed, stays formed until fatally breached (see below)

### 2. Location Within Valid Range (ALL SCALES)

```
In reference frame terms: 0 <= location <= 2
```

**This applies to ALL scales.** The extension zone (1-2) is where the trade plays out — ES typically completes at 2x.

| Location | Meaning | Valid Reference? |
|----------|---------|------------------|
| < 0 | Pivot breached | No |
| 0–1 | In swing range | Yes |
| 1–2 | Extending toward target | **Yes (all scales)** |
| > 2 | Past completion | No |

**Note:** Location is capped at 2.0 in output (actual value computed internally for breach detection).

### 3. Origin Breach Handling (Scale-Dependent Tolerance)

**Invalidation = origin of confirming leg breached beyond tolerance.**

For a bull reference (which is a bear leg), the confirming bull leg's origin is the bear leg's pivot. If this is breached (price drops below pivot beyond tolerance), the reference is invalidated.

**Per north star (product_north_star.md lines 122-128):**

| Scale | Condition | Threshold |
|-------|-----------|-----------|
| S, M | Price **trades** beyond extreme | **0%** (instant invalidation) |
| L, XL | Price **trades** beyond extreme | **15%** (0.15 × range) |
| L, XL | Price **closes** beyond extreme | **10%** (0.10 × range) |

```python
def is_fatally_breached(leg, scale: str, location: float, bar_close_location: float, config) -> bool:
    """
    Scale-dependent fatal breach threshold.

    S/M swings have zero tolerance — any trade beyond extreme invalidates.
    L/XL swings have TWO thresholds: trade breach (15%) and close breach (10%).

    Args:
        leg: The leg being checked
        scale: Scale classification ('S', 'M', 'L', 'XL')
        location: Current price location (from bar high/low depending on direction)
        bar_close_location: Location of bar close (for L/XL close breach check)
        config: ReferenceConfig with tolerance values
    """
    if location < 0:
        return True  # Pivot breached

    if location > 2:
        return True  # Past completion

    # Scale-dependent origin breach tolerance (location past 1.0)
    if scale in ('S', 'M'):
        # S/M: Default zero tolerance (configurable)
        return location > (1.0 + config.small_origin_tolerance)  # default 0.0
    else:  # L, XL
        # L/XL: Two thresholds
        # Trade breach: invalidates if price TRADES beyond 15%
        if location > (1.0 + config.big_trade_breach_tolerance):  # 0.15
            return True
        # Close breach: invalidates if price CLOSES beyond 10%
        if bar_close_location > (1.0 + config.big_close_breach_tolerance):  # 0.10
            return True
        return False
```

**Note:** All tolerance values are UI tunable (like detection config). S/M defaults to 0% per north star but can be adjusted for tuning.

---

## Scale Classification (S/M/L/XL)

### Approach: Range Percentile Buckets

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

**Notes:**
- Range distribution is all-time; DAG pruning naturally handles recency
- Fixed decay for recency is intentional (DAG handles regime shifts)

### Cold Start Handling

Until 50+ swings have accumulated, scale classification is unreliable. During cold start:
- **Exclude all references** from output (no scale classification possible)
- UI can show "Warming up: N/50 swings collected"

### What Scale Classification Provides

Scale is used for:
1. **Tolerance rules** — L/XL get more tolerance before invalidation
2. **Salience weighting** — Different weight profiles for big vs small
3. **Completion behavior** — Small swings "complete" at 2x; big swings stay valid until DAG creates replacement

---

## Scale vs Hierarchy Depth (A/B Testing)

**Decision: Implement both, A/B test.**

### Toggle in Settings

User can switch between:
- **Percentile scale mode** — S/M/L/XL based on range percentile
- **Hierarchy depth mode** — Classification based on DAG depth

### What Hierarchy Depth Provides

| Depth | Meaning | Analogous to |
|-------|---------|--------------|
| 0 | Root legs — major market structure | XL/L |
| 1 | First-level children — intermediate swings | L/M |
| 2+ | Nested children — minor refinements | M/S |

**Advantages of depth:**
1. Structural meaning (where leg sits in hierarchy, not just size)
2. Stable (no hysteresis at percentile boundaries)
3. Already computed by DAG

### Exploration Task

Before deciding which approach to keep:
1. Compute correlation between depth and range percentile
2. Identify disagreement cases (small roots, large nested)
3. Determine which attribute matters for which rule

---

## Salience Ranking

North star defines ideal reference as: **big, impulsive, and early** (for large swings) vs **recent** (for small swings).

### Salience Formula

```python
def compute_salience(leg, scale, current_bar_index, range_distribution, config):
    # Base: range (bigger = more salient)
    range_score = normalize(leg.range, range_distribution)  # 0-1

    # Impulse: faster moves are more salient
    # If impulsiveness is missing, skip this component
    if leg.impulsiveness is not None:
        impulse_score = leg.impulsiveness / 100  # 0-1
        use_impulse = True
    else:
        impulse_score = 0
        use_impulse = False

    # Recency: bars since origin (fixed decay — DAG handles regime shifts)
    age = current_bar_index - leg.origin_index
    recency_score = 1 / (1 + age / 1000)  # Decay function

    # Scale-dependent weighting (UI tunable)
    if scale in ('L', 'XL'):
        weights = {
            'range': config.big_range_weight,      # e.g., 0.5
            'impulse': config.big_impulse_weight,  # e.g., 0.4
            'recency': config.big_recency_weight   # e.g., 0.1
        }
    else:
        weights = {
            'range': config.small_range_weight,      # e.g., 0.2
            'impulse': config.small_impulse_weight,  # e.g., 0.3
            'recency': config.small_recency_weight   # e.g., 0.5
        }

    # Normalize weights if impulse is missing
    if not use_impulse:
        total = weights['range'] + weights['recency']
        weights['range'] /= total
        weights['recency'] /= total
        weights['impulse'] = 0

    return (weights['range'] * range_score +
            weights['impulse'] * impulse_score +
            weights['recency'] * recency_score)
```

**Note:** Salience weights should be UI tunable with presets for different trading objectives (scalping vs swing).

---

## Location Computation

Location tells us where current price sits within the reference frame:

```python
def compute_location(leg, current_price):
    """
    Returns position in reference frame:
    - 0 = at defended pivot
    - 1 = at origin
    - 2 = at completion target (origin + range in direction of move)

    For bull reference (bear leg, high→low):
    - Origin = HIGH (where bear move started)
    - Defended pivot = LOW (must hold for bullish setup)
    - 0 = pivot (low), 1 = origin (high), 2 = target below pivot

    For bear reference (bull leg, low→high):
    - Origin = LOW (where bull move started)
    - Defended pivot = HIGH (must hold for bearish setup)
    - 0 = pivot (high), 1 = origin (low), 2 = target above pivot
    """
    frame = ReferenceFrame(
        anchor0=leg.pivot_price,  # defended pivot = 0
        anchor1=leg.origin_price,  # origin = 1
        direction="BULL" if leg.direction == 'bull' else "BEAR"
    )
    return frame.to_ratio(current_price)
```

---

## API Design

```python
class ReferenceLayer:
    """Thin filter over DAG legs to identify valid trading references."""

    def __init__(self, config: ReferenceConfig = None):
        self.config = config or ReferenceConfig.default()
        self._range_distribution = []  # All-time, updated incrementally
        self._tracked_for_crossing: Set[str] = set()  # Leg IDs being monitored

    def update(self, legs: List[Leg], bar: Bar) -> ReferenceState:
        """
        Main entry point. Called each bar after DAG processes.

        One bar at a time. No look-ahead. Always assume real-time flow.
        """
        # Update range distribution (all-time)
        self._update_range_distribution(legs)

        # Cold start check
        if len(self._range_distribution) < self.config.min_swings_for_scale:
            return ReferenceState(
                references=[],
                by_scale={},
                by_depth={},
                by_direction={},
                direction_imbalance=None
            )

        references = []
        for leg in legs:
            scale = self._classify_scale(leg.range)
            location = self._compute_location(leg, bar.close)

            # Formation check (price-based)
            if not self._is_formed_for_reference(leg, bar.close):
                continue

            # Validity check (location + tolerance)
            if self._is_fatally_breached(leg, scale, location):
                continue

            salience = self._compute_salience(leg, scale, bar.index)

            references.append(ReferenceSwing(
                leg=leg,
                scale=scale,
                depth=leg.depth,
                location=min(location, 2.0),  # Cap at 2.0
                salience_score=salience
            ))

        # Sort by salience
        references.sort(key=lambda r: r.salience_score, reverse=True)

        # Compute direction imbalance
        by_direction = self._group_by_direction(references)
        bull_count = len(by_direction.get('bull', []))
        bear_count = len(by_direction.get('bear', []))
        if bull_count > bear_count * 2:
            imbalance = 'bull'
        elif bear_count > bull_count * 2:
            imbalance = 'bear'
        else:
            imbalance = None

        return ReferenceState(
            references=references,
            by_scale=self._group_by_scale(references),
            by_depth=self._group_by_depth(references),
            by_direction=by_direction,
            direction_imbalance=imbalance
        )

    def get_active_levels(self, state: ReferenceState) -> Dict[float, List[LevelInfo]]:
        """
        Get key price levels from all valid references.

        Returns dict keyed by fib ratio with LevelInfo including source reference.
        """
        levels = {}
        ratios = [0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2]

        for ref in state.references:
            frame = ReferenceFrame(
                anchor0=ref.leg.pivot_price,
                anchor1=ref.leg.origin_price,
                direction="BULL" if ref.leg.direction == 'bull' else "BEAR"
            )
            for ratio in ratios:
                price = frame.to_price(ratio)
                if ratio not in levels:
                    levels[ratio] = []
                levels[ratio].append(LevelInfo(
                    price=price,
                    ratio=ratio,
                    reference=ref
                ))

        return levels

    def get_confluence_zones(self, state: ReferenceState,
                             tolerance_pct: float = 0.001) -> List[Dict]:
        """
        Find where levels from different references cluster.

        Args:
            tolerance_pct: Percentage tolerance for clustering (e.g., 0.001 = 0.1%)

        Returns:
            List of confluence zones with participating levels
        """
        pass  # Implementation clusters levels within tolerance

    # Level crossing tracking
    def add_crossing_tracking(self, leg_id: str):
        """Add a leg to level crossing monitoring."""
        self._tracked_for_crossing.add(leg_id)

    def remove_crossing_tracking(self, leg_id: str):
        """Remove a leg from level crossing monitoring."""
        self._tracked_for_crossing.discard(leg_id)
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

    # Cold start
    min_swings_for_scale: int = 50  # Exclude refs until this many swings

    # Formation threshold (fib level)
    formation_fib_threshold: float = 0.382  # 38.2% retracement

    # Origin breach tolerance — per north star (product_north_star.md lines 122-128)
    # S/M: Zero tolerance by default (configurable for tuning)
    small_origin_tolerance: float = 0.0  # Default 0% per north star
    # L/XL: Two thresholds — UI TUNABLE
    big_trade_breach_tolerance: float = 0.15  # Invalidates if TRADES beyond 15%
    big_close_breach_tolerance: float = 0.10  # Invalidates if CLOSES beyond 10%

    # Salience weights (big swings: L/XL) — UI TUNABLE
    big_range_weight: float = 0.5
    big_impulse_weight: float = 0.4
    big_recency_weight: float = 0.1

    # Salience weights (small swings: S/M) — UI TUNABLE
    small_range_weight: float = 0.2
    small_impulse_weight: float = 0.3
    small_recency_weight: float = 0.5

    # Classification mode (for A/B testing)
    use_depth_instead_of_scale: bool = False

    # Confluence detection
    confluence_tolerance_pct: float = 0.001  # 0.1% — percentage-based
```

---

## Persistence

### State Saving

Reference Layer state can be persisted for faster startup:
- `ReferenceConfig` (all tunable parameters)
- `_range_distribution` (all-time range data)
- `_tracked_for_crossing` (which legs are monitored)

### Version Mismatch Handling

When loading saved state, if DAG or Reference Layer algorithm has changed:
- **Show generic warning:** "State may be outdated. Rebuild recommended."
- User can dismiss and continue with stale state, or trigger rebuild

---

## UI: Levels at Play

### Overview

**Menu name: "Levels at Play"** (not "Reference View")

Accessible from hamburger menu. Provides a focused lens for analyzing valid trading references without DAG debugging controls.

**Purpose:**
1. Eyeball validation (do the references look right?)
2. Rule discovery (assign probabilities, find patterns)
3. Algo input (feed into forward-testing system)

NOT for live trading execution.

### What Changes vs DAG View

| Element | DAG View | Levels at Play |
|---------|----------|----------------|
| **Legs shown** | All active legs | Only valid references |
| **Filtered legs** | N/A | Fade out, then hidden |
| **Detection config** | Visible, adjustable | Hidden |
| **Fib levels** | Not shown | Hover = preview, Click = sticky |
| **Structure panel** | Leg stats | Levels at play, telemetry |
| **Level crossings** | Disabled | Opt-in per leg |

### Visual Indicators (Phase 1)

Each visible leg shows:
- **Scale label** — S/M/L/XL badge
- **Direction color** — Bull (green) vs Bear (red)
- **Location indicator** — Current position in 0-2 range

### Leg Disappearance

When a reference becomes invalid:
1. **Fade out transition** (brief visual cue)
2. Then hidden completely

Not grayed out or de-emphasized — just fades and disappears.

### Fib Levels Interaction

1. **Hover** — Temporarily display all 9 fib levels as horizontal lines
2. **Click** — Make fib levels sticky (persist)
3. **Click again** — Un-stick

Multiple legs can have sticky levels. Color-code to distinguish sources.

### Confluence Zones

When levels from different references cluster (within percentage tolerance):
- Merge into **confluence zone** (thicker band)
- Label shows participating references

### Structure Panel: Levels at Play

Three sections:

1. **Touched this session** — Historical record of which levels were hit
2. **Currently active** — Levels within striking distance of current price
3. **Current bar** — Levels touched on most recent bar

**Level "testing" = touch/cross (not proximity).** A level is tested when price actually trades at or through it.

### Telemetry Panel

Like DAG's market structure panel. Shows:
- Reference counts by scale: "XL: 2, L: 5, M: 12, S: 23"
- Direction imbalance: "Bull-heavy (3:1)"
- Formation/invalidation events: "Ref #123 formed", "Ref #456 invalidated"
- Biggest and most impulsive active references

### Opt-in Level Crossing

Level crossing is expensive (N refs × M levels × bars). Use selective tracking:
1. User clicks "track" on a leg
2. Only tracked legs generate crossing events
3. Events appear in structure panel
4. State lives in Reference Layer (`_tracked_for_crossing`)

### Implementation Path

**Phase 1:** (expanded scope)
- Add "Levels at Play" menu item
- Show filtered legs (location 0-2 + formed)
- Scale labels, direction colors, location indicators
- Hide detection config
- Fade out transition for invalidated legs

**Phase 2:**
- Fib level hover/click-to-stick

**Phase 3:**
- Structure panel with three sections (touched/active/current)
- Telemetry panel
- Confluence zones

**Phase 4:**
- Opt-in level crossing per leg

Each phase independently testable and shippable.

---

## Integration Points

### With DAG

```python
# In main processing loop
for bar in bars:
    # DAG processes bar first
    events = detector.process_bar(bar)

    # Reference layer filters current state
    legs = detector.get_state().active_legs
    ref_state = reference_layer.update(legs, bar)

    # Downstream consumers use ref_state
    # (frustration detection, signal generation, etc.)
```

### With Downstream Consumers

Reference Layer provides data. Pattern detection is downstream:

| Pattern | Owner |
|---------|-------|
| Move completion | Downstream consumer |
| Frustration rule | Downstream consumer |
| Stacked targets | Downstream consumer |
| Trading signals | Downstream consumer |

---

## What This Spec Explicitly Defers

1. **Sibling preference rules** — Not important for v1
2. **Cross-timeframe aggregation** — Single-timeframe for now
3. **Trading signal generation** — Downstream concern
4. **Outcome tracking** — Separate future work

---

## Open Questions

### Resolved

1. **Range distribution scope** — **RESOLVED: All-time.** DAG pruning handles recency.

2. **0-2 validity range** — **RESOLVED: All scales use 0-2.**

3. **Origin breach handling** — **RESOLVED: Per north star.** S/M: default zero tolerance (configurable). L/XL: two thresholds (15% trade, 10% close). All tolerances UI tunable.

4. **Formation basis** — **RESOLVED: Price-based (fib threshold), not age-based.**

5. **Origin stress concept** — **RESOLVED: Removed.** Was never in north star; superfluous.

6. **Scale vs depth** — **RESOLVED: Implement both, A/B test.** Toggle in settings.

7. **Reference limit** — **RESOLVED: No internal limit.** UI can limit display.

8. **Persistence versioning** — **RESOLVED: Generic warning on mismatch.** User decides whether to rebuild.

### Still Open

1. **Scale boundary hysteresis** — If percentile-based scale, leg near boundary might flip. Options:
   - Hysteresis band
   - Lock scale at formation
   - Accept flip-flopping

2. **Parent preference in salience** — Should child of most salient large swing be preferred?

---

## Success Criteria

Reference Layer is working when:

1. References identified match north star expectations (L1-L7 from valid_swings.md)
2. Scale classification matches intuition (L1 is XL, L7 is S/M)
3. Formation correctly triggers on fib threshold (38.2% default)
4. Location computation works for 0-2 range (capped at 2.0)
5. Invalidation respects scale-dependent tolerance
6. Cold start excludes refs until 50+ swings
7. A/B testing possible (scale vs depth toggle)
8. Performance: aspirational <1ms per bar (not strict target)

---

## Feedback History

### Initial Feedback (Dec 25, 2025) — Addressed in Rev 1-2

| # | Feedback | Resolution |
|---|----------|------------|
| 1 | Formation belongs in Reference Layer | ✅ Price-based formation (Rev 4) |
| 2 | 0-2 validity for ALL scales | ✅ Confirmed |
| 3 | Origin breach ≠ instant invalidation | ✅ Scale-dependent tolerance |
| 4 | Range distribution — all-time | ✅ Confirmed |

### UI Direction Feedback (Dec 31, 2025) — Addressed in Rev 3-4

| # | Feedback | Resolution |
|---|----------|------------|
| 1 | Separate view, not toggle | ✅ Hamburger menu |
| 2 | Level crossing performance | ✅ Opt-in per leg |
| 3 | Incremental phases | ✅ 4-phase plan |

### In-Depth Interview (Dec 31, 2025) — Addressed in Rev 4

| # | Finding | Resolution |
|---|---------|------------|
| 1 | Formation is PRICE-BASED | ✅ Corrected from age-based |
| 2 | origin_stress is superfluous | ✅ Removed |
| 3 | Bull reference = bear swing | ✅ Clarified terminology |
| 4 | XL completion via DAG | ✅ Documented |
| 5 | Salience context-dependent | ✅ UI tunable weights |
| 6 | No internal reference limit | ✅ Removed max_references_per_scale |
| 7 | A/B test scale vs depth | ✅ Added by_depth, toggle |
| 8 | Menu: "Levels at Play" | ✅ Renamed |
| 9 | Phase 1 scope expansion | ✅ Scale/direction/location labels |
| 10 | Telemetry panel | ✅ Added like DAG market structure |
| 11 | Fade out transition | ✅ For invalidated legs |
| 12 | Confluence zones | ✅ Percentage-based clustering |
| 13 | Direction imbalance | ✅ Highlight in output |
| 14 | Cold start: 50+ swings | ✅ Exclude until threshold |
| 15 | Level testing = touch/cross | ✅ Clarified (not proximity) |
| 16 | Include reference in levels | ✅ LevelInfo with source |
| 17 | Missing impulse: skip component | ✅ Normalize remaining weights |
| 18 | Crossing state in Reference Layer | ✅ _tracked_for_crossing |
| 19 | Version warning: generic | ✅ User decides on rebuild |
| 20 | Frustration rule downstream | ✅ Documented as consumer concern |
| 21 | Sibling rules not v1 | ✅ Deferred |
| 22 | Performance: aspirational | ✅ Not strict target |

---

## Next Steps

1. ~~Address initial feedback~~ ✅ Done in Rev 1-2
2. ~~Add UI visualization~~ ✅ Done in Rev 3
3. ~~In-depth interview corrections~~ ✅ Done in Rev 4
4. **Get user sign-off on Rev 4**
5. **Implementation Phase 1:** Levels at Play route + filtered legs + labels + telemetry
6. **Implementation Phase 2:** Fib level hover/click-to-stick
7. **Implementation Phase 3:** Structure panel + confluence zones
8. **Implementation Phase 4:** Opt-in level crossing
9. **Exploration (parallel):** Analyze depth vs scale correlation

---

## Appendix: Interview Transcript (Dec 31, 2025)

In-depth polymath interview (product + architect) to clarify spec details. Questions and answers preserved for future reference.

### Recency Decay

**Q:** The salience formula uses a fixed decay function (1/(1+age/1000)) for recency. But market regimes change - a 1000-bar-old swing from a volatility spike might be more relevant than a 100-bar-old swing from chop. Have you considered regime-aware recency, or is the simplicity of a fixed decay intentional because the DAG pruning already handles regime shifts?

**A:** Fixed decay is intentional. DAG pruning handles regime shifts; simplicity is preferred.

---

### XL Completion Behavior

**Q:** The spec mentions 'big swings never complete' but doesn't define what completion means for the Reference Layer. If an XL swing reaches location=2, what happens? Does it stay valid forever? Does it transform somehow? Or does 'never complete' mean the 2x target is just informational?

**A:** It stays valid until price exits 2x for good. For example, this is a common XL pattern: A pull back starts from >2x but below <2.1x. It continues until 0.9-1.1 zone. Then there's a sharp reversal. Then it continues normally until 2x is exited. But notice how this would have created a fresh XL swing (2x->1x is as big as the original reference by definition). The new swing then becomes the reference leaving the old one out as price re-exists 2x (1x of the new swing created).

**Follow-up Q:** This implies the DAG spawns the new swing. Does the Reference Layer need any special handling for this, or does it 'just work' because DAG creates the new leg and the old one falls outside 0-2?

**A:** Just works via DAG.

---

### Origin Stress Concept

**Q:** The spec treats price at location 0.3 (defensive zone) as 'safe' but 0.7 as 'stressed.' Is this stress concept even useful to you? Or is it over-engineering, since what matters is whether the reference is fatally breached (past tolerance)?

**A:** I never defined the stress concept. It's not there in north star. Seems superfluous to me.

---

### Range Distribution Scope

**Q:** The spec uses all-time range distribution for scale classification. But if a market transitions from low-vol regime to high-vol regime, all new swings would be classified as L/XL until enough high-vol swings accumulate. Is this desirable (market 'remembers' low-vol), or should there be a rolling window?

**A:** All-time is correct.

---

### Salience Priority

**Q:** The salience formula has hardcoded weights. The spec says 'recent wins for small swings.' Is that the right intuition? Or should the most impulsive small swing win regardless of age? Or does it even matter if we're keeping top 4 per scale anyway?

**A:** Salience depends on trading objective. For fib levels that matter large / most impulsive swings win. For 1 minute chart level quick trades of scalps, recent legs matter.

---

### Fib Level Count

**Q:** The UI spec says fib levels appear on hover/click. How many levels should be shown? The spec lists 9 levels. That's a lot of horizontal lines. Should all be shown, or should users choose which fibs matter to them?

**A:** Good question. I tend to show all on my TradingView but I configure 4 different panels and select the right reference frames for each time-frame (1-minute timeframe may have a small reference leg and a bigger one, 1D timeframe may have only the largest 2, etc.).

---

### Multi-Panel Support

**Q:** You mentioned 4 panels per timeframe with different reference frames. Should the UI support multiple 'workspaces' or 'panels' where users can configure different reference selections?

**A:** Current DAG view shows 2 views already. Start with that (simple). We can add if needed. Remember the objective is not to trade with this the way I use TradingView, the objective is to compute conditional probabilities (rules) and build an automated trading bot that uses the reference layer.

---

### Salience Mode Switch

**Q:** If salience depends on trading objective (scalping vs swing), should there be a mode switch in the UI, or should the Reference Layer always output both rankings?

**A:** Perhaps these should be tunable the way DAG allows to tune the detection config. There can be stored settings for different modes -- could be useful.

---

### Outcome Tracking

**Q:** For rule discovery, you'll need to compute stats like 'when price is at location 1.5 of an XL swing, what % of the time does it reach 2x?' Should the Reference Layer track outcomes, or is that a separate component?

**A:** My current thinking is that reference layer is for me to eyeball that we're indeed finding the correct reference swings. Outcome tracking needs separate work. That would be the next step in the project.

---

### Bot Consumption Mode

**Q:** For the automated bot: does it need real-time updates (every bar), or batch analysis?

**A:** Real-time per bar.

---

### Level Crossing Cost

**Q:** The spec mentions 'level crossing events are expensive to compute.' Can you help me understand why?

**A:** N refs × M levels × bars (combinatorial explosion).

---

### Persistence

**Q:** If I close the app and reopen, does the Reference Layer need to rebuild from scratch, or should state be persisted?

**A:** Save current state and load would be extremely useful. Only challenge I perceive is it might get "outdated" if we update DAG or reference. So perhaps it needs to know what "version" of each it used?

**Follow-up Q:** For version mismatch: invalidate on mismatch, cache but rebuild available, or just warn?

**A:** Just warn.

---

### Scale vs Depth Decision

**Q:** The scale vs hierarchy depth exploration is flagged as open. Before implementing Reference Layer, do you want this resolved? Or can we ship with percentile-based scale and explore depth correlation in parallel?

**A:** Implement both, A/B test.

---

### Leg Disappearance UX

**Q:** The spec says filtered legs are 'hidden completely' in Reference View. But if a leg was valid 5 bars ago and just became invalid, hiding it suddenly might be disorienting. Should there be a transition?

**A:** Fade out transition.

---

### Cluster Tolerance

**Q:** What's the clustering tolerance for level confluence? If XL's 1.5 level is at $4150 and M's 0.5 level is at $4152 (2 points apart on ES), is that a cluster?

**A:** Percentage-based.

---

### Formation Basis

**Q:** The formation rule uses age (bars since origin). But some legs might have origin far in the past but just got their pivot confirmed recently. Should formation be based on age-since-origin or age-since-pivot-confirmation?

**A:** Not sure I follow. Here's my understanding of formation -- a bull reference is a bear leg and a bear reference is a bull leg. In the above example you have a bear leg. This bear leg can be a bull reference if there's a certain threshold that's been reached in the bull leg whose origin is the pivot of the bear leg. Let's say if this is set to 0.384, then it means that this swing has formed and the bear leg is a bull reference if price reaches 0.384. In the above case at 103.84. Even if price subsequently drops after, but holds above the pivot of 100, the swing is still formed. If the price drops below the pivot (using the invalidation threshold used in the spec), then it becomes invalid.

**Follow-up Q:** To confirm: formation threshold is 38.2% default, configurable?

**A:** 38.2% default, configurable.

**Follow-up Q:** What happens if price reaches the formation threshold but then immediately retraces back below pivot?

**A:** It becomes formed when the fib level configured is hit. Then it can become invalidated through invalidation rules (origin breach for most scales). If it becomes invalid, it's removed from being a reference anyway!

---

### Reference Limit

**Q:** The spec shows 'max_references_per_scale: int = 4'. But if there are 15 valid S-scale references, you lose 11. For rule discovery, wouldn't you want all valid references available?

**A:** No limit internally.

---

### Missing Impulsiveness

**Q:** If DAG produces a leg with no impulsiveness value (None), should Reference Layer skip the impulse component in salience, use a default, or exclude that reference entirely?

**A:** Skip impulse component.

---

### Crossing State Location

**Q:** For the 'opt-in level crossing' feature, someone needs to track which legs are being monitored. Should that tracking state live in Reference Layer, in a separate component, or in the UI layer?

**A:** In Reference Layer.

---

### Invalidation Events

**Q:** When a reference becomes invalid, should there be an explicit event emitted, or is it sufficient that it simply disappears from the next ReferenceState?

**A:** Isn't origin_breach already emitted by DAG? Does that not suffice? If not, then reference layer should own it. If it does, then the question is no op.

---

### Bulk Processing

**Q:** For backtesting/replay: should Reference Layer support processing bars in bulk, or always one-bar-at-a-time?

**A:** One bar at a time. Always assume no look-ahead.

---

### Panel Selection Criteria

**Q:** When you assign references to TradingView panels, what's your selection criteria?

**A:** In TradingView, I select manually. For a bot, I assume it should be provided (if you're doing this, then use these levels sort of thing).

---

### Sibling Rules

**Q:** The north star mentions 'sibling preference rules' but the spec defers them. Can you briefly describe what sibling preference means?

**A:** Not important for v1.

---

### A/B Display Mode

**Q:** During A/B testing of scale vs depth, would you want both classification schemes available simultaneously, or toggle between them?

**A:** Toggle in settings.

---

### Level Testing Definition

**Q:** For the 'levels at play' structure panel: when a level is 'being tested', what constitutes that?

**A:** Should strictly cross or touch the level in the direction expected. For example, you have a bull reference swing (bear leg with bull leg formed). You're looking to go long, price is above a fib level for that reference frame. Unless it trades at or below that level, then any trade you placed will not be filled (buy limit order at that price). Reverse the logic for bear reference swing. No level touch/cross -- no trade.

---

### Levels Display Sections

**Q:** For display purposes in 'Levels at Play', should the panel show: levels touched this session, levels within proximity, or only levels touched on current bar?

**A:** All of the above.

---

### Phase 1 Essentials

**Q:** Is there anything that should be added to phase 1 besides filtered legs + hide detection config?

**A:** All of the above (scale labels, direction color, location indicator).

---

### Frustration Rule Ownership

**Q:** The spec mentions 'frustration rule'. Is this something Reference Layer should detect, or is it downstream?

**A:** Downstream consumer.

---

### Warning Detail

**Q:** When saving/loading with version mismatch: generic warning or include specifics?

**A:** Generic warning.

---

### Level Attribution

**Q:** The get_active_levels() returns fib levels grouped by ratio. Should it also return which reference each level belongs to?

**A:** Include reference info.

---

### Cold Start Threshold

**Q:** For minimum N swings needed before scale classification works: what should N be?

**A:** 50+ swings.

---

### Logging/Telemetry

**Q:** Should the Reference Layer have logging/telemetry for debugging?

**A:** Full telemetry and shown to the user like "market structure" panel on DAG view. Currently it shows legs by: active, formed, pruned by: engulfed, turn, counter trend, proximity. Also shows biggest and most impulsive legs.

---

### Confluence Display

**Q:** When multiple references have fib levels that cluster, should the UI show them as a single 'confluence zone' or as separate lines?

**A:** Confluence zone.

---

### Direction Balance

**Q:** In a trending market with imbalanced bull/bear references, should the UI balance the display or show raw counts?

**A:** Highlight imbalance.

---

### Tolerance Configuration

**Q:** Should tolerance values be UI tunable or hardcoded initially?

**A:** UI tunable.

---

### Menu Naming

**Q:** For the hamburger menu entry: 'Reference View', 'Trading References', 'Levels at Play', or different?

**A:** Levels at Play.

---

### Location Cap

**Q:** Should location output cap at 2.0 or show actual value beyond 2x?

**A:** For most of the time (~99.999% of all swings) capping at 2x suffices. Only for the largest swings 2.1x may be needed.

---

### Gaps Check

**Q:** Is there anything about the Reference Layer concept that still feels unclear or underspecified?

**A:** No major gaps.
