# Outcome Layer Spec

**Status:** Draft (needs refinement)
**Created:** January 1, 2026

---

## Purpose

New layer for rule discovery, downstream of Reference Layer. Answers: "What happens when price touches this level?"

**Goal:** Build conditional probability model P(outcome | features) for reference levels.

---

## Architecture Position

```
DAG Layer (structure detection)
    ↓ legs with depth, range, counter-range
Reference Layer (level selection)
    ↓ active references with fib levels + metadata
Outcome Layer (rule discovery)  ← NEW
    ↓ P(outcome | features)
[Future: Tuning Loop]
```

---

## Core Concepts

### Touch Detection

**Definition:** When did price interact with a reference level?

**Open questions:**
- Wick vs close? (wick touches level vs bar closes at level)
- Tolerance band? (within X% of level counts as touch)
- Multiple touches per bar? (high and low both touch different levels)

### Outcome Labeling

**Definition:** What happened after the touch?

**Candidate labels:**
- **Bounce** — Price reversed direction after touch
- **Breakout** — Price continued through the level
- **Continuation** — Price paused then continued original direction
- **Rejection** — Strong reversal (bounce with magnitude)

**Open questions:**
- What magnitude defines a "bounce"? (X% reversal? N bars of reversal?)
- Lookforward window? (outcome within 5 bars? 20 bars?)
- How to handle multiple outcomes? (touched, bounced, then broke through later)

### Feature Extraction

Features available for each touch:
- **From Reference Layer:** scale, location, salience, formation status
- **From DAG:** leg_range, counter_leg_range, depth, impulsiveness
- **Derived:** structural_importance (range × counter), confluence (in zone?)
- **Context:** trend direction, volatility regime, time of day

---

## Statistical Model

### Simple approach: Contingency tables

```
P(bounce | scale=XL, location<0.5) = count(bounce) / count(touches)
```

### Advanced approach: Logistic regression or decision tree

```
P(bounce) = f(scale, location, structural_importance, confluence, ...)
```

---

## Data Pipeline

1. **Collect touches:** Replay through historical data, detect level touches
2. **Label outcomes:** For each touch, look forward and assign label
3. **Extract features:** Pull reference metadata at time of touch
4. **Compute statistics:** Aggregate by feature combinations
5. **Validate:** Out-of-sample testing

---

## Open Questions (Need User Input)

### Touch Definition
- [ ] Wick or close?
- [ ] Tolerance band size?
- [ ] Level types to track? (origin, pivot, fib levels, confluence zones)

### Outcome Definition
- [ ] What constitutes a bounce? (magnitude, duration)
- [ ] Lookforward window?
- [ ] Binary (bounce/not) or multi-class (bounce/breakout/continuation)?

### Feature Prioritization
- [ ] Which features to start with?
- [ ] Scale-dependent models or unified?

### Validation
- [ ] Train/test split approach?
- [ ] Minimum sample size per bucket?

---

## Relationship to Reference Layer

Reference Layer exploration and Outcome Layer are coupled:

- **Reference Layer** decides which levels to surface
- **Outcome Layer** measures whether those levels have predictive power
- **Feedback loop (future):** Outcome Layer results inform Reference Layer tuning

Can be developed in parallel:
- Reference Layer tuning enables visual exploration
- Outcome Layer provides quantitative validation
- Iterate between them

---

## Next Steps

1. Define touch detection rules (interview)
2. Define outcome labels (interview)
3. Implement touch detection on historical data
4. Build basic contingency tables
5. Iterate based on findings
