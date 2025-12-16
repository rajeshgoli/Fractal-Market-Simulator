# Discretizing Continuous OHLC into Recursive Swing “Game Pieces”

*Fractal Market Simulator — proposal draft*

## Problem statement (grounded in this repo’s North Star)

This codebase already knows how to *read* markets: it detects multi-scale reference swings (S/M/L/XL), computes Fibonacci levels, and flags structural events (level crosses, completions, invalidations) for expert review via the Ground Truth Annotator. The Product North Star, however, is not just to interpret history—it is to **generate 1-minute OHLC that is indistinguishable from real markets** while obeying the same structural laws across scales.

The missing link is a **discrete, swing-level representation**—“game pieces”—that a recursive generator can manipulate. Continuous OHLC is too high-dimensional and too easy to overfit; we need a representation that:

- Preserves the North Star invariants: Fibonacci attractors, completion at 2×, scale-aware invalidation tolerance, decision zones/liquidity voids, and **top-down causality** (“big moves drive smaller moves”).
- Is **interpretable** enough that any generated bar can be traced back to a small number of explicit structural decisions (not latent vectors).
- Supports **fractal recursion**: the same move grammar applies at XL, L, M, S; smaller scales are allowed to be “more extreme” without changing the core rules.
- Allows stochasticity (news/trigger stream later) to **tilt** outcomes without violating structural constraints.
- Can be tuned with small data (expert swing annotations + statistics extracted from real OHLC) and can be extended indefinitely without losing fidelity.

This document proposes approaches for discretizing continuous OHLC into game pieces suitable for a recursive, swing-based market model.

---

## The questions that determine success

Question quality is a deliverable here: these are the pressure points where discretization either becomes a clean generative system or degenerates into ad-hoc rules.

| # | Question | Why it matters |
|---|----------|----------------|
| Q1 | What is the **canonical coordinate system** for “position”? | Everything becomes simpler if bull/bear swings share one oriented definition of “0 → 2×” and “STOP”. |
| Q2 | What is the **atomic game piece**: a level-to-level step, a target-seeking intent, or a macro-motif? | The atomic unit determines tractability, recursion, and what the generator can explain. |
| Q3 | What is the **minimal sufficient state** for next-move prediction (semi-Markov, not necessarily Markov)? | If state is too small, outcomes depend on hidden history; too large, it becomes unlearnable and un-debuggable. |
| Q4 | How do we enforce **top-down causality** without making lower scales rigid? | Parent swings must constrain children, but children must still have room to “play” (chop/overshoot) without constantly forcing parent changes. |
| Q5 | How do we represent **time** at swing granularity (durations, dwell, impatience) while keeping structure primary? | Decision zones are mostly a *time* phenomenon (dwell/failed attempts), but structure must remain the core state. |
| Q6 | How do we encode **decision zones** and **liquidity voids** so they emerge in generation (chop vs snap)? | These are signature market behaviors in the North Star rules and must be reproduced statistically and visually. |
| Q7 | How do we model **frustration**, **measured-move**, and **exhaustion** as explicit, auditable mechanisms? | These rules are second-order; if they are “baked into noise,” debugging becomes impossible. |
| Q8 | What is the **canonical game record** (log schema) that guarantees replay and audit? | If we can’t replay deterministically, we can’t trust or refine the generator. |
| Q9 | Which parameters are **learned from data** vs fixed as priors from the North Star? | With limited data, we must learn only what is stable and observable. |
| Q10 | What does “**indistinguishable**” mean operationally (metrics + visual tests + invariants)? | Without hard “done” criteria, iteration collapses into taste and endless tweaking. |

---

## Guiding tenets (explicit tiebreakers)

These tenets are designed to create productive tension. Each has a plausible opposite; disagreements become focal points.

1. **Interpretability over compression.**  
   Opposite: “Compress state aggressively; we’ll explain later.”  
   Tiebreaker: choose the representation that yields a clean English explanation for every state transition.

2. **Hierarchy is causal, not correlational.**  
   Opposite: “Let higher scales emerge from aggregated lower-scale behavior.”  
   Tiebreaker: if a choice allows S/M noise to directly steer XL/L (without a defined structural event), reject it.

3. **Structure first; time is a modifier.**  
   Opposite: “Time is a first-class state dimension.”  
   Tiebreaker: encode time effects via dwell/attempt counters and semi-Markov timing, not via arbitrary clocks.

4. **Discrete decisions, continuous rendering.**  
   Opposite: “Keep the generator continuous; discretize only for analysis.”  
   Tiebreaker: if a variable is only needed for OHLC realism, it belongs in the renderer, not in the game state.

5. **Hard invariants, soft preferences.**  
   Opposite: “Everything is probabilistic; violations are just low probability.”  
   Tiebreaker: completion/invalidation/allowed transitions must be enforced as hard constraints; everything else is a weighting.

6. **Learn parameters, not representations.**  
   Opposite: “Learn the representation end-to-end (embeddings, latent states).”  
   Tiebreaker: if success requires large datasets to tune, it fails the project’s current reality.

7. **The log is the product.**  
   Opposite: “Only the OHLC matters; internals can be messy.”  
   Tiebreaker: if we can’t replay and audit a sequence from a compact decision log, we don’t truly understand it.

---

## Virtual consultation panel

This is not roleplay; it is a method for extracting high-quality principles by asking what these thinkers would insist on, then translating to actionable implications for *this* codebase.

| Focus | Consultant | Why they fit |
|-------|------------|--------------|
| Representation level | **David Marr** | Separates “what/why” from “how,” preventing us from mixing state with rendering artifacts. |
| Minimal state + logging | **Claude Shannon** | Forces a rate–distortion view: what must be kept to predict and replay? |
| Stochasticity under constraints | **E.T. Jaynes** | Maximum-entropy reasoning: don’t invent structure you can’t justify; encode constraints explicitly. |
| Fractals + tails | **Benoit Mandelbrot** | Self-similarity and heavy tails are axioms here, not optional features. |
| Causality | **Judea Pearl** | Makes “big moves drive small moves” a formal causal constraint, not a narrative. |
| Volatility dynamics | **Robert Engle** | Gives a principled way to encode volatility clustering and asymmetry without black boxes. |
| Game-piece design | **Sid Meier** | “A game is a series of interesting choices”: helps define what the generator should be choosing. |

### Marr: keep three levels separate

Marr would demand we separate:

- **Computational goal**: generate OHLC that obeys swing/level rules and looks real.  
- **Algorithmic level**: discrete game pieces and transition logic across scales.  
- **Implementation level**: how we render bars (bridges, wicks, motifs).

Actionable implication: **do not smuggle rendering detail into the state**. If we need wick shape for realism, it belongs in a renderer module driven by the discrete log—not in the structural decision process.

### Shannon: minimal sufficient state + replayable bits

Shannon’s instinct is to ask: *how many bits do we need to encode the future?* For us, the “future” is the next structural decision and its timing. The sufficient state is whatever removes uncertainty about:

- which reference frames are active,
- where price is relative to those frames (discrete band),
- which constraints are currently binding (exhaustion, frustration, stacked targets),
- and a small set of volatility/duration variables.

Actionable implication: the canonical record should store **decisions + random seeds**, not raw OHLC. OHLC is a deterministic rendering of the log (given seeds).

### Jaynes: maximum entropy subject to North Star constraints

Jaynes would treat the North Star rules as **constraints** (hard invariants and soft preferences). Where we lack data, he would select the **maximum entropy** distribution consistent with those constraints—meaning:

- don’t invent complex conditional tables unless the rules/data force them,
- prefer a small number of interpretable multipliers (zone type, trend alignment, news bias, volatility regime),
- and make every “preference” a parameter you can surface and tune.

Actionable implication: start with sparse transition sets (adjacent levels) and layer only the smallest set of modifiers required to reproduce decision-zone vs void behavior.

### Mandelbrot: self-similarity with scale-dependent extremity

Mandelbrot would insist that:

- the *rules* repeat across scales (self-similarity),
- but the **tail heaviness** and “extremity allowance” can be scale-dependent (smaller scales can do crazier things).

Actionable implication: implement a two-channel stochastic mechanism: (1) ordinary transitions constrained to adjacent levels, (2) a rare tail channel that allows unusual behavior—but with explicit logs so it remains inspectable.

### Pearl: top-down causality as a model constraint

Pearl would ask us to model the hierarchy as a causal graph:

- parent state → child transition probabilities (and child allowed space),
- child events → parent updates only through explicit structural events (completion/invalidation) or declared tail overrides.

Actionable implication: encode cross-scale coupling as **directed control inputs** (context vectors / gating weights), not as emergent aggregation.

### Engle: volatility clustering and asymmetry without black boxes

Engle would push for an explicit volatility state that evolves over time:

- a simple regime variable (low/med/high) or a continuous EMA of “impulse,”
- asymmetric response (down moves can spike volatility more than up moves),
- durations drawn from distributions conditioned on regime and zone type.

Actionable implication: volatility should live in the semi-Markov timing and in the renderer noise budget—not as hidden latent states.

### Meier: define the “interesting choices”

Meier’s lens: what is the generator *choosing* that matters?

At swing-level, the interesting choices are not “next tick up/down,” but:

- break vs reject at decision zones,
- continuation vs exhaustion pullback at 2×,
- whether frustration triggers a symmetric retrace,
- whether stacked targets get impulsively “must-hit” resolved or liquidated.

Actionable implication: the game piece vocabulary should make these choices explicit; if a critical market behavior isn’t representable as a discrete choice, it will be hard to tune and explain.

---

## Concrete implications for this codebase

### What must be true about the representation

1. **One oriented coordinate system for bull and bear references.**  
   Define a directed reference frame where the Fibonacci ratio increases in the *expected move direction*:
   - Bull reference: `anchor0 = low`, `anchor1 = high`
   - Bear reference: `anchor0 = high`, `anchor1 = low`  
   Then `ratio(price) = (price - anchor0) / (anchor1 - anchor0)` works for both (denominator sign handles direction). Completion is `ratio ≥ 2.0`; STOP is `ratio ≤ -0.1` (with wick/close thresholds by scale).

2. **State must be hierarchical and local.**  
   Per scale, we need a small `ScaleState`; cross-scale coupling is a context input, not a shared soup of variables.

3. **Moves are level-to-level at each scale.**  
   The atomic transition is between adjacent Fibonacci boundaries (plus explicitly logged tail exceptions). Partial progress is handled by the next lower scale and by the renderer.

4. **Time is semi-Markov.**  
   Durations/dwell times are sampled; they are not implicit in the number of discrete transitions.

5. **Every second-order rule is an explicit mechanism.**  
   Frustration, measured-move, exhaustion pullback, and “too many targets” must appear as state variables and/or event types, not as emergent side effects.

6. **Canonical log is replayable.**  
   A game record must be sufficient to regenerate OHLC deterministically (given seeds), enabling audit and calibration.

### What must be preserved

- Fibonacci level geometry and named zones (decision zones, liquidity voids).
- Termination rules: completion at 2×, invalidation at STOP (scale-dependent tolerance).
- “Big moves drive small moves” causality direction (parents gate children).
- Fractal self-similarity across scales, with scale-dependent extremity allowance.
- Momentum/volatility characteristics (clustering, asymmetry).

### What can be discarded (and reintroduced in rendering)

- Intra-level microstructure (tick paths, micro-wiggles).
- Semantic content of news (we only need polarity/intensity/timing later).
- Full price history beyond the active swing stack and a small set of counters/regime states.

### Non-negotiable constraints

- **No black-box latent states** as core dynamics.
- **No lookahead** in forward discretization (when extracting statistics from real data).
- **No implicit violations**: if the model breaks a rule, it must do so through a logged tail override.

### Degrees of freedom we can exploit

- Level set granularity (which Fibonacci boundaries are discrete).
- Whether the “atomic action” is a step, an intent, or a motif (or a hybrid).
- Duration distributions and volatility regime dynamics.
- How many active reference frames per scale to maintain (1 vs few).
- How we represent stacked targets (counts, density metrics, or explicit lists).

---

## Discretization options (implementable)

### Option A — Hierarchical Semi‑Markov Level Machine (HSMLM)

**Summary:** Each scale is a semi-Markov process over Fibonacci *bands* (intervals between named levels). Transitions are adjacent-band moves with durations; cross-scale coupling is explicit parent conditioning. This is the cleanest “state/action/termination” core.

#### Representation

**Directed reference frame**

```text
ReferenceFrame:
  anchor0_price  # defended pivot (low for bull ref, high for bear ref)
  anchor1_price  # opposite pivot
  range = anchor1_price - anchor0_price  # sign encodes direction

  ratio(price) = (price - anchor0_price) / range
  price(ratio) = anchor0_price + ratio * range
```

**State**

```text
ScaleState:
  scale ∈ {S, M, L, XL}
  frame: ReferenceFrame
  band_id: discrete interval index between adjacent ratios
  dwell: bars spent in current band
  impulse_ema: smoothed (distance / bars) proxy for momentum/volatility

  attempts: map[level_name → count]           # failed tests near key levels
  frustration_flags: set[level_name]         # active frustrations
  exhaustion_flag: bool                      # after completion
  target_stack_density: float                # “too many targets” pressure

  news_bias: optional (polarity, intensity, ttl)
  tail_mode: optional override context

GameState:
  t: integer (in 1-minute bars)
  scales: dict[scale → ScaleState]
```

#### Actions

```text
Move:
  scale
  from_band_id → to_band_id   # usually adjacent
  duration_bars               # semi-Markov timing
  rationale                   # enum: void_snap, decision_chop, exhaustion_pullback, …
  rng_seed

Event:
  scale
  type ∈ {COMPLETION, INVALIDATION, FRUSTRATION, MEASURED_MOVE, TARGET_STACK_RELEASE}
  level_name / ratio / metadata

Reanchor:
  scale
  new_frame (anchor0, anchor1)  # after completion/invalidation
```

#### Termination

Per scale, the active frame terminates on:

- **Completion:** `ratio(close) ≥ 2.0` (with optional “must pull back” constraints at highest scale).
- **Invalidation:** `ratio(close) ≤ -0.1` and/or `ratio(wick) ≤ -0.15` (tolerance by scale per North Star).

Termination triggers `Reanchor` to establish the next reference frame for that scale.

#### Recursion across scales

Top-down causality is implemented as **parent-conditioned transition sampling**:

- Each child scale receives a context vector from its parent: `(parent_band_id, parent_pending_direction, parent_distance_to_target, parent_exhaustion_flag, …)`.
- Child transitions are allowed broadly but are reweighted so that, in aggregate, they progress the parent toward its next boundary unless a tail override is active.

Operationally, generation can run as:

1. Choose an XL move (next band + duration).  
2. Within that duration, generate a sequence of L moves conditioned on XL.  
3. Within each L move, generate M; within each M move, generate S; S renders to 1-minute bars.

This preserves “big moves drive small moves” by construction: the parent commits first; children fill.

#### Mapping to/from OHLC

- **Forward discretization (analysis/calibration):** given OHLC and a chosen set of reference frames, compute `ratio(t)` per scale and emit `Move`s on boundary crossings, plus `Event`s on completion/invalidation/frustration triggers.
- **Reverse mapping (generation):** render each `Move` into OHLC using a bridge (e.g., Brownian bridge / piecewise-linear + noise) that starts/ends at the implied prices `price(ratio_boundary)` and respects tick quantization. Volatility regime controls noise and wick budgets.

#### Stochastic elements

- **Next-band choice:** categorical distribution over allowed targets conditioned on `(band, zone_type, parent_context, impulse, news_bias, target_stack_density)`.
- **Duration:** log-normal or gamma conditioned on `(distance, zone_type, impulse, direction)`; volatility clustering via `impulse_ema`.
- **Tail channel:** low-probability mechanism that allows (logged) non-adjacent jumps or rare parent-contradicting behavior; probability and severity are scale-dependent (smaller scales heavier tail).

#### Canonical game record

The canonical record is an append-only log:

```json
{
  "meta": {"instrument":"ES","tick":0.25,"start_ts":0,"seed":123},
  "initial_state": {"XL": {...}, "L": {...}, "M": {...}, "S": {...}},
  "news": [{"t": 1280, "polarity": -1, "intensity": 0.7, "ttl": 60}],
  "log": [
    {"t":0, "type":"move", "scale":"L", "from":"1.0-1.382", "to":"1.382-1.5", "bars":180, "why":"void_snap", "seed":991},
    {"t":180, "type":"event", "scale":"L", "event":"FRUSTRATION", "level":"1.5", "attempts":4},
    {"t":180, "type":"move", "scale":"L", "from":"1.382-1.5", "to":"1.0-1.382", "bars":220, "why":"symmetric_retrace", "seed":992}
  ]
}
```

#### How the generator samples the next move (sketch)

1. Identify current zone type from `band_id` (decision zone vs void vs retracement zone).  
2. Compute legal target set (adjacent bands + any explicit tail options).  
3. Apply multiplicative weights:
   - parent-conditioning weight,
   - zone-specific behavior (chop vs snap),
   - exhaustion/frustration/measured-move constraints,
   - stacked-target pressure,
   - news bias,
   - volatility regime.
4. Sample target band; sample duration; emit `Move`; update state and counters; emit `Event`s if thresholds were crossed.

---

### Option B — Intent/Attempt Model (explicit decision-zone dynamics)

**Summary:** Make the primary choice an **intent** (“we are trying to reach 1.5”) and treat decision zones as explicit **attempt loops** (tests, rejections, eventual break, or frustration-driven symmetric retrace). This option is excellent at producing the *feel* of chop without inventing hidden state, but it adds bookkeeping.

#### Representation

```text
IntentState (per scale):
  current_intent: target_level_name (e.g., "1.5", "1.618", "0.5", "0.618", "2.0")
  intent_direction: toward_higher_ratio | toward_lower_ratio
  attempts: integer
  near_miss_count: integer
  time_in_intent: bars
  frustration_threshold: function(scale, level, volatility)

ScaleState = ReferenceFrame + current_band + IntentState + volatility regime
```

#### Actions

- `SetIntent(target_level, rationale)`  
- `Attempt(result ∈ {progress, reject, break, overshoot}, duration_bars)`  
- `ForceSymmetricRetrace(level)` (frustration rule)  
- `Complete / Invalidate / Reanchor` (same termination as Option A)

#### Recursion across scales

- Parent scales choose intents that define the envelope (e.g., “pull back to 1.618” after exhaustion).  
- Child scales generate attempt dynamics inside that envelope (tests, failures, small overshoots) without changing the parent intent unless an explicit event occurs.

#### Mapping to/from OHLC

Attempt events naturally map to OHLC motifs (test wick, reject candle sequence, break candle). Rendering becomes more structured than in Option A, because “attempt” is already a narrative unit.

#### Stochastic elements

- `P(break | attempts, time_in_intent, news_bias, impulse, zone_type)`  
- Attempt duration distributions conditioned on volatility regime  
- Tail channel that can instantly flip intent or force an extreme attempt (logged)

#### Canonical game record

Log `SetIntent` and `Attempt` outcomes (plus seeds). Replay regenerates the same attempt sequence and renders it deterministically.

---

### Option C — Motif Templates (interpretable macro-moves)

**Summary:** Define a small library of **interpretable macro-motifs** (each a structured sequence of level transitions and attempt behaviors), then sample motifs conditioned on state. Motifs can recurse: a motif at L calls motifs at M/S to fill its interior.

Examples of motif types aligned to the North Star:

- `void_snap(1.1 → 1.382)`  
- `decision_chop_then_break(1.382 ↔ 1.5 → 1.618)`  
- `fakeout_then_measured_move(fail at 1.5 → measured move down)`  
- `exhaustion_pullback(2.0 → 1.618)`  
- `stop_run_and_reclaim(-0.1 → 0.382)` (scale-dependent rarity)

#### Representation

Motifs are parameterized templates:

```text
MotifInstance:
  motif_type
  scale
  start_ratio, end_ratio
  params: {duration, chop_cycles, overshoot_prob, wick_budget, …}
  rng_seed
```

The game state can be lean (similar to Option A), because the motif carries much of the structure for that segment.

#### Actions

- `SelectMotif(motif_type, params)`  
- Motif expands into a sequence of `Move` and `Event` primitives (Option A) and/or `Attempt` primitives (Option B).

#### Recursion across scales

Motifs define the “why” at a scale; sub-motifs define the “how” at lower scales. This can be made strictly top-down: choose motif at XL, expand into L motifs, etc.

#### Stochastic elements

The randomness is in motif choice and in motif parameter sampling—not in opaque latent states.

#### Canonical game record

Store motif choices + sampled parameters + seeds; expansion is deterministic and auditable.

---

## Tradeoff analysis (voice of Andy Grove)

> “The point of a plan is to force you to make decisions. Don’t pick the elegant architecture—pick the one that will survive contact with reality and still let you debug.”

**What matters most in this phase:** interpretability, structural correctness, and the ability to iterate quickly with small data.

| Criterion | Weight | A: HSMLM | B: Intent/Attempt | C: Motifs |
|----------|--------|----------|-------------------|-----------|
| Interpretability + audit | 0.25 | **9** | 8 | 8 |
| Structural fidelity (rules) | 0.25 | **9** | **9** | 8 |
| Decision-zone realism | 0.10 | 7 | **9** | **9** |
| Learnability (small data) | 0.15 | **8** | 7 | 6 |
| Extensibility | 0.10 | **9** | 7 | 7 |
| Implementation risk | 0.10 | **8** | 6 | 6 |
| Computational cost | 0.05 | **9** | 8 | 7 |
| **Weighted total** | 1.00 | **8.55** | 7.75 | 7.40 |

**Verdict:** Option A is the best canonical core. Option B is too valuable to ignore (decision zones, frustration), but it is best treated as an augmentation to A rather than a separate architecture. Option C is powerful for realism, but as a *primary* model it risks turning into a growing library of special cases; it is best positioned as a renderer/macro layer driven by A’s logged decisions.

---

## Recommendation (decisive)

Adopt a **hybrid** with a single canonical representation:

1. **Canonical core:** Option A (HSMLM) as the state/action/termination model and the canonical game record.  
2. **Augment state + events:** bring in Option B’s intent/attempt counters specifically for decision zones, frustration, and exhaustion—implemented as explicit state variables and event types inside HSMLM.  
3. **Rendering + variety:** use Option C motifs only as a controlled expansion layer for OHLC rendering and for higher-level macro-actions later (motifs compile down to HSMLM moves/events).

This keeps the generator inspectable and data-efficient while still being able to reproduce the “chop vs snap” behaviors that define realism.

---

## Sequencing plan (implementation-oriented)

1. **Lock the coordinate system and invariants.**  
   - Implement the directed reference frame (`ratio()` / `price()`), band definitions, and invariant checks (adjacency, completion, invalidation).

2. **Define the canonical log schema + deterministic replay.**  
   - Treat the log as first-class output; ensure replay produces identical OHLC given seeds.

3. **Build a forward discretizer for calibration.**  
   - Convert real OHLC (plus detected reference frames) into HSMLM logs to extract: transition counts, dwell distributions by zone, attempt/frustration frequencies, volatility proxy behavior.

4. **Implement single-scale generation, then add hierarchy.**  
   - Start with one scale (e.g., M or L), validate behavior visually and via invariants; then add parent conditioning and recursive filling down to S for 1-minute output.

5. **Add second-order rule mechanisms.**  
   - Frustration counters and symmetric retrace, exhaustion pullback expectations, measured-move triggers, and stacked-target pressure—all as explicit events and state variables.

6. **Renderer: controlled motifs and volatility realism.**  
   - Start with simple bridges; introduce a small motif set only where it improves realism without hiding causality.

---

## “Done” criteria (for discretization, not the full generator)

- The representation can encode bull and bear references with one oriented ratio system (same level names, same termination semantics).
- Every generated segment produces a replayable, auditable log where each transition is explainable in one sentence.
- The hierarchy enforces top-down causality: child behavior cannot change parent state except through explicit logged structural events or a logged tail override.
- Decision-zone vs liquidity-void behavior is visible in the discrete logs (dwell/attempt distributions differ by zone) and recognizable in charts after rendering.
- Volatility clustering and asymmetry are captured via explicit regime variables and timing distributions, not latent vectors.
- A forward discretizer can extract HSMLM statistics from real OHLC without lookahead, enabling empirical calibration of probabilities and durations.

