# Discretization Proposal F1: Measurement-First Approach

**Status:** Proposal
**Date:** December 15, 2025
**Supersedes:** Draft proposals c1, c2, c3, o1, o2, g1, cl1, os1 (see `draft_discretization_proposals.md` for reference)

---

## Executive Summary

This proposal takes a **measurement-first** approach to discretization. Rather than encoding North Star rules as axioms and tuning parameters, we treat them as **hypotheses to validate** against real market data.

The key insight: we have all of ES-1m data. Expert annotations are ground truth for *swing detection*. Once swings are detected, discretization should be mechanical and rules should be *observable* if we haven't engaged in circular reasoning.

**Milestone 1 (this proposal):** Build the discretizer—an instrument that converts continuous OHLC + detected swings into a log of structural events. This enables measurement.

**Future work (requires separate planning):** Parameter estimation, generator, discriminator.

---

## Problem Statement

We need to convert continuous OHLC data into discrete "game pieces" suitable for:
1. **Measurement**: Validating whether North Star axioms hold empirically
2. **Generation** (future): Producing realistic synthetic market data

The prior draft proposals assumed limited data and treated rules as ground truth. This proposal inverts the epistemology:

| Prior Assumption | This Proposal |
|------------------|---------------|
| Expert annotations are primary data | ES-1m corpus is primary data; annotations validate swing detection |
| North Star rules are axioms to encode | North Star rules are hypotheses to test |
| Parameters are tuned from small samples | Parameters are estimated from full corpus |
| Adjacent-band transitions only | No adjacency constraint; observe what actually happens |
| 2x completion is terminal | 2x is significant but not necessarily terminal |

---

## Scope

### In Scope (Milestone 1)

- **Discretizer implementation**: Convert OHLC + detected swings → structural event log
- **Canonical log schema**: Define the format for level crossings, completions, invalidations
- **Coordinate system**: Oriented reference frame that unifies bull/bear handling
- **Visual verification workflow**: Integration with existing annotation tool for inspection
- **Success criteria**: Measurable definition of "discretizer works correctly"

### Out of Scope (Future Work)

The following require separate planning documents after Milestone 1 validates the approach:

| Future Milestone | Purpose | Prerequisite |
|------------------|---------|--------------|
| **Parameter Estimation** | Measure empirical distributions from discretized corpus | Working discretizer |
| **Generator v0** | Sample from observed distributions to produce sequences | Validated parameter estimates |
| **Discriminator** | GAN-style classifier to measure real vs generated | Working generator |
| **News Integration** | Measure CPI/FOMC impact on structural moves | Baseline parameter estimates |

---

## Design

### Coordinate System

Use an **oriented reference frame** where Fibonacci ratio always increases in the expected move direction:

```
ReferenceFrame:
  anchor0: Decimal  # Defended pivot (low for bull, high for bear)
  anchor1: Decimal  # Opposite pivot
  direction: BULL | BEAR

  range = anchor1 - anchor0  # Sign encodes direction

  ratio(price) = (price - anchor0) / range
  price(ratio) = anchor0 + ratio * range
```

Interpretation:
- `ratio = 0`: Defended pivot
- `ratio = 1`: Origin extremum
- `ratio = 2`: Completion target (2x extension)
- Negative ratios: Beyond defended pivot (stop-run territory)

This coordinate system is mathematically clean and agnostic to what we discover about behavior.

### Level Set

Start with North Star Fibonacci levels. The discretizer logs crossings at these boundaries:

```
LEVELS = [
    -0.15,   # Deep stop-run (L/XL invalidation threshold)
    -0.10,   # Stop-run (S/M invalidation threshold)
     0.00,   # Defended pivot
     0.236,  # Shallow retracement
     0.382,  # Standard retracement
     0.50,   # Half retracement
     0.618,  # Golden retracement
     0.786,  # Deep retracement
     1.00,   # Origin
     1.236,  # Shallow extension
     1.382,  # Standard extension / Decision zone start
     1.50,   # Decision zone
     1.618,  # Golden extension / Decision zone end
     1.786,  # Deep extension
     2.00,   # Completion target
     2.236,  # Extended completion
]
```

**Note:** This level set is a starting point. If measurement reveals other significant levels, we extend it.

### Canonical Log Schema

The discretizer outputs a structured log of events:

```json
{
  "meta": {
    "instrument": "ES",
    "source_resolution": "1m",
    "discretizer_version": "f1.0",
    "created_at": "2025-12-15T12:00:00Z"
  },
  "swings": [
    {
      "swing_id": "xl_001",
      "scale": "XL",
      "direction": "BULL",
      "anchor0": 4800.00,
      "anchor1": 5100.00,
      "formed_at_bar": 0,
      "status": "active"
    }
  ],
  "events": [
    {
      "bar": 42,
      "timestamp": "2025-01-15T10:42:00Z",
      "swing_id": "xl_001",
      "event_type": "LEVEL_CROSS",
      "from_ratio": 1.35,
      "to_ratio": 1.42,
      "level_crossed": 1.382,
      "direction": "UP",
      "close_price": 5214.50
    },
    {
      "bar": 89,
      "timestamp": "2025-01-15T11:29:00Z",
      "swing_id": "xl_001",
      "event_type": "LEVEL_TEST",
      "level": 1.50,
      "result": "REJECT",
      "high_ratio": 1.497,
      "close_ratio": 1.463
    },
    {
      "bar": 156,
      "timestamp": "2025-01-15T12:36:00Z",
      "swing_id": "xl_001",
      "event_type": "COMPLETION",
      "completion_ratio": 2.03,
      "close_price": 5406.75
    }
  ]
}
```

**Event Types:**

| Event | Meaning | Data |
|-------|---------|------|
| `LEVEL_CROSS` | Price crossed a Fib level | from_ratio, to_ratio, level_crossed, direction |
| `LEVEL_TEST` | Price approached but didn't cross | level, result (REJECT/WICK_THROUGH), high/low_ratio |
| `COMPLETION` | Ratio crossed 2.0 | completion_ratio |
| `INVALIDATION` | Ratio crossed below threshold | invalidation_ratio, threshold |
| `SWING_FORMED` | New swing detected at scale | swing reference |
| `SWING_TERMINATED` | Swing ended (completion or invalidation) | termination_type |

**Design Principle:** Log everything; filter later. Don't embed assumptions about what matters into the discretizer.

### No Adjacency Constraint

Unlike prior proposals, this discretizer does **not** enforce adjacent-band transitions. If price jumps from 1.0 to 1.618 in one bar, we log:
- `LEVEL_CROSS` at 1.236
- `LEVEL_CROSS` at 1.382
- `LEVEL_CROSS` at 1.50
- `LEVEL_CROSS` at 1.618

All with the same bar timestamp. This captures the reality that price can move through multiple levels.

### Multi-Scale Handling

The discretizer processes each scale independently:
- XL, L, M, S swings each get their own event streams
- Cross-scale relationships are **not assumed**—they are observable in the logs
- If XL completion correlates with L behavior, measurement will reveal it

### Integration with Existing Codebase

The discretizer builds on existing infrastructure:

```
┌─────────────────────────────────────────────────────────────────┐
│                     EXISTING PIPELINE                            │
│                                                                 │
│   OHLC Data → SwingDetector → Detected Swings (S/M/L/XL)       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     NEW: DISCRETIZER                             │
│                                                                 │
│   Detected Swings + OHLC → Level Crossing Log (per scale)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     NEW: VISUAL VERIFICATION                     │
│                                                                 │
│   Ground Truth Annotator + Discretization Overlay              │
│   (See level crossings on chart; verify correctness)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Visual Verification Workflow

The discretizer must be visually verifiable. Proposed workflow using the existing Ground Truth Annotator:

1. **Load OHLC + detected swings** (existing capability)
2. **Run discretizer** to produce level-crossing log
3. **Overlay discretized events on chart**:
   - Horizontal lines at Fib levels (from active swing's reference frame)
   - Markers at level crossings (color-coded by event type)
   - Event annotations (completion, invalidation, level test)
4. **Manual inspection**: Verify events correspond to visible price action

**Acceptance Test:** A user looking at the overlay should be able to:
- See that level crossings are logged when price actually crosses levels
- See that completions are logged when price reaches 2x
- Identify any false positives (logged event that didn't happen) or false negatives (missed event)

The architect should determine whether this is:
- A new mode in the existing annotator
- A separate visualization tool
- A CLI that outputs annotated charts

---

## Success Criteria

### Functional Correctness

| Criterion | Verification Method |
|-----------|---------------------|
| **Level crossings detected** | Visual: overlay shows markers at correct bar positions |
| **Completions detected** | Count completions in log matches manual inspection on sample windows |
| **Invalidations detected** | Scale-appropriate thresholds applied correctly |
| **Multi-level jumps handled** | Large moves log all intermediate level crossings |
| **No lookahead** | Discretizer uses only data up to current bar |

### Coverage

| Criterion | Target |
|-----------|--------|
| **Scales processed** | XL, L, M, S all produce event logs |
| **Time range** | Full ES-1m corpus can be discretized |
| **Performance** | Discretization completes in reasonable time (<1 hour for full corpus) |

### Data Quality

| Criterion | Verification Method |
|-----------|---------------------|
| **Log is parseable** | JSON schema validation passes |
| **Events are ordered** | Bar timestamps monotonically increase |
| **Swing references valid** | Every event references an existing swing |
| **No duplicate events** | Same level crossing not logged twice |

### Validation Samples

Before declaring success, manually verify on at least:
- 3 different date ranges (different market regimes)
- All 4 scales
- Both bull and bear swings
- At least one completion and one invalidation per scale

---

## Open Questions for Architect

1. **Swing detection dependency**: Does the discretizer run on pre-computed swings, or should it call SwingDetector as part of its pipeline?

2. **Incremental vs batch**: Should the discretizer support streaming (process bar-by-bar) or batch-only (process full range)?

3. **Storage format**: JSON as shown, or something more efficient for large corpus (Parquet, SQLite)?

4. **Visualization backend**: Extend Ground Truth Annotator, or separate tool?

5. **Testing strategy**: Unit tests on synthetic data, integration tests on real ES-1m samples, or both?

---

## Future Work (Requires Separate Planning)

These milestones depend on a working discretizer and will need their own proposal documents:

### Parameter Estimation

**Purpose:** Measure empirical distributions from the discretized corpus.

**Key Questions:**
- What is P(next level | current level, scale)?
- How long do transitions take (duration distributions)?
- Do frustration patterns exist? (P(reversal | N failed tests))
- Are there scale-dependent differences?
- How does CPI/FOMC affect distributions?

**Prerequisite:** Discretizer producing valid logs for full ES-1m corpus.

### Generator v0

**Purpose:** Sample from observed distributions to produce synthetic sequences.

**Key Questions:**
- What's the generation architecture (state machine, grammar, hybrid)?
- How to handle multi-scale coordination?
- What constraints are hard vs soft?

**Prerequisite:** Parameter estimation complete with validated distributions.

### Discriminator

**Purpose:** GAN-style classifier to measure realism of generated data.

**Key Questions:**
- Feature-based or raw OHLC input?
- How to prevent memorization/overfitting?
- What's the baseline distinguishability?

**Prerequisite:** Generator producing output to evaluate.

---

## Appendix: Relationship to Prior Drafts

This proposal synthesizes insights from drafts c1, c2, c3, o1, o2, g1, cl1, os1 while making a key epistemic shift:

**What we keep:**
- Oriented reference frame (from o2, os1)
- Canonical log schema (from all)
- Fib levels as coordinate system (from all)
- Interpretability requirement (from all)

**What we change:**
- Axioms → Hypotheses (treat rules as testable, not given)
- Small data → Full corpus (ES-1m is the ground truth for discretization)
- Adjacent-only → Observe freely (don't constrain what we log)
- Encode rules → Measure distributions (parameter estimation comes after discretization)

**What we defer:**
- Generator architecture decisions
- Second-order rule encoding (frustration, exhaustion)
- News modeling
- Discriminator design

See `draft_discretization_proposals.md` for the full text of prior drafts.

---

*Document version: 1.0*
