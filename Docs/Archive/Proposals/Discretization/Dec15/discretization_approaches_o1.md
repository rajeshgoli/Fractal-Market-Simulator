# Discretization Approaches (Option 1 Track)

## Problem Statement

The Product North Star commits us to a recursive market model in which every swing, regardless of timeframe, obeys the same structural laws: Fibonacci-defined attractors, 2× completions, scale-aware invalidation tolerances, and causality that flows from higher swings down to lower ones. We can already detect these structures from continuous OHLC data, but the simulator cannot yet *generate* believable markets because we lack the discrete “game pieces” that a generator can manipulate. We need a representation that:

- Captures structural context without resorting to uninterpretable latent vectors.
- Preserves fractal self-similarity so that XL→L→M→S recursion is built-in, not bolted on.
- Enables reversible mapping between OHLC bars and game state so every generated history can be audited.
- Leaves room for stochastic “news” triggers that modulate but do not overwrite the structural rules.
- Can be parameterized and tuned with the limited, expert-curated swing annotations we actually possess today.

This document defines the question set, tenets, expert guidance, implications, design options, tradeoffs, and recommendation for discretizing continuous market motion into reusable swing “pieces” that satisfy those constraints.

## Critical Questions

1. **What is the atomic game piece we should model?** Is it a swing, a level-to-level move, an event, or a structured tuple containing all of the above?
2. **How much history must the state retain to remain Markovian?** Do we only track currently active swings, or do we need trailing context like frustration counters, retrace counts, or stacked targets?
3. **How do higher scales gate lower scales without collapsing recursion into a single timeline?**
4. **Where do stochastic triggers enter?** Should randomness affect move selection, durations, magnitudes, or only the timing of externally-caused regime shifts?
5. **What must the canonical game record store so that OHLC ↔ game state roundtrips are lossless at the structural level?**
6. **How do we embed Fibonacci, completion, invalidation, and frustration rules directly into the representation rather than layering them afterward?**
7. **Given scant labeled data, which parts of the model can be learned empirically and which must remain rule-driven primitives?**

## Guiding Tenets

1. **Interpretability Beats Compression.** When faced with a choice between a dense latent code and an explicit tuple (direction, band, completion status, context), favor the explicit tuple so experts can reason about it.
2. **Structure First, Noise Later.** Encode deterministic structural constraints in the game pieces; inject stochasticity only when selecting among structurally valid moves.
3. **Top-Down Causality Is Mandatory.** XL and L swings set the expectation space for M and S; lower scales may add texture but cannot contradict their parents absent a black-swan override.
4. **Fibonacci Bands Are the Coordinate System.** All positions, transitions, and completions are measured relative to Fib ratios of active swings; absolute ticks are derived artifacts.
5. **Canonical Records Must Be Reversible.** Every simulated sequence must be auditable back to the structural decisions that produced it; game logs store causes, not just outcomes.
6. **Stochastic News Modulates, Never Dictates.** News inputs tilt probabilities for pending moves but cannot fabricate levels or invalidate causality rules except through explicitly-modeled tail events.
7. **Small-Data Bias Is by Design.** Assume we will live in a data-scarce world; representations that require thousands of samples to tune are disqualified no matter how elegant they are in theory.

## Expert Consultation

**Benoit Mandelbrot — Atomic Game Piece (Q1).** Mandelbrot reminds us that markets are fractal, not smooth functions. He argues the only unit that respects fractality is the *swing* paired with its current position on the parent swing’s Fibonacci grid. Bars are too granular, while arbitrary “patterns” hide the recursive law. Therefore the atomic piece should be “reference swing + relative progress + tension state,” a template we can reuse at every scale.

**Claude Shannon — Minimal Sufficient State (Q2).** Shannon pushes for entropy-aware parsimony: store only what reduces uncertainty about the next structural move. In our context, that means (a) the active swing stack (one per scale), (b) the exact band each swing currently occupies, (c) timers measuring dwell time in band, and (d) the last structural outcome (completion, invalidation, frustration). Anything else can be reconstructed or is noise.

**Donella Meadows — Cross-Scale Interlocks (Q3).** Meadows, steeped in system dynamics, argues the hierarchy should be modeled as nested feedback loops. XL swings broadcast constraints downstream; smaller scales respond via damped oscillations unless a threshold is crossed. Coding this as explicit control signals avoids ad-hoc heuristics and keeps recursion transparent.

**John Boyd — Stochastic Triggers (Q4 & Q6).** Boyd frames markets as rapid OODA loops. News is the “Orient” stage perturbation; it should accelerate or delay decisions but never replace structural objectives. He recommends modeling news as state modifiers that temporarily widen probability distributions or open rare transitions, keeping the core rule set intact.

**Nassim Nicholas Taleb — Tail Risk Injection (Q4).** Taleb insists that any discretization lacking explicit fat tails is doomed. He recommends a two-channel stochastic pipeline: one log-normal channel for ordinary structural noise and a separate Pareto-tailed channel for rare “reset” moves that can violate a higher-scale swing exactly once before normal rules resume.

**Richard Hamming — Canonical Record & Reversibility (Q5).** Hamming argues we should store decisions, not pixels. A log consisting of “scale, band transition, duration, stochastic modifier used” is enough to rebuild OHLC deterministically. This aligns with the Product North Star requirement that generated sequences remain auditable.

**Herbert Simon — Learnability Under Scarcity (Q7).** Simon stresses satisficing: solve the subset we can validate today, design hooks for tomorrow. He recommends parameterizing transition probabilities and durations with priors derived from rules, then refining them incrementally with each annotation batch instead of chasing statistically-perfect fits we’ll never be able to verify.

## Structural Implications

**Non-Negotiable Preservations**
- *Swing Stack Integrity:* Always maintain at least one active swing per scale, with explicit references to highs/lows so new swings can inherit context.
- *Band Semantics:* Each swing’s price must always map to a discrete Fib band, and transitions may only cross adjacent bands unless a tail event fires.
- *Parent Conditioning:* No child move may contradict parent direction unless a modeled invalidation has occurred.
- *Event Traceability:* Every completion, invalidation, frustration, or measured-move trigger must emit an explicit record entry.

**What We Can Safely Drop**
- Raw tick-level price noise (reconstructable via stochastic bridges).
- Semantic content of news (we only need polarity/intensity/timing).
- Deep historical backlog beyond active swings (state can be Markovian given swing stack plus timers).

**Constraints Derived from North Star**
- Completion definition (2× of reference range) is law; exhaustion must trigger mandated pullback expectations.
- Liquidity voids (1.1–1.382 and 1.618–2) must show as probabilistic snapping regions when transitions begin.
- Frustration and measured-move rules require counters that track failed attempts per level.

**Degrees of Freedom**
- How many alternate reference swings per scale we carry (1 vs 3).
- Functional form of transition probability modifiers (logistic vs lookup table).
- Encoding of durations (geometric vs log-normal) so long as they reflect observed persistence.
- How fine-grained we make stochastic channels (single vs dual vs tri-modal).

## Discretization Options

### Option 1: Fibonacci Band State Machine

- **Representation (State).** A `GameState` contains one `SwingState` per scale. Each `SwingState = (direction, reference_high, reference_low, band, dwell_bars, frustration_count, news_bias)`.
- **Actions.** Two classes: (a) `BandTransition(scale, from_band, to_band, duration)` for intra-swing moves, (b) `StructuralEvent(scale, type∈{completion, invalidation, measured_move, frustration_release})`. Transitions are only allowed between adjacent bands unless a taleb-channel override fires.
- **Recursion.** Top-down gating: before sampling an M-scale transition we check if its parent L band permits it (e.g., if L is in pullback, M upward transitions are down-weighted). Parent completions broadcast constraint updates to children.
- **OHLC Mapping.** Forward mapping quantizes each bar into the appropriate band, emitting transitions when boundaries are crossed. Reverse mapping converts transitions to price paths by sampling a duration, drawing a Brownian bridge anchored at entry/exit ticks, and concatenating across scales (XL defines slow drift, L adds texture, M/S add intra-bar noise).
- **Stochastic Elements.** Transition selection uses a categorical distribution per `(scale, current_band, parent_band_state)`. Durations draw from scale-specific log-normal distributions. Two stochastic modifiers exist: `news_bias` (short-lived) and `tail_override` (Pareto distributed) for rare multi-band jumps.
- **Game Record.** Log entries look like `{"t":42,"scale":"M","type":"band_transition","from":"0.618-1.0","to":"1.0-1.382","bars":9,"news_bias":0.2}` or `{"t":118,"scale":"L","type":"completion","target_price":5120.5}`. This log is replayable into OHLC.
- **Sampling Next Move.** Evaluate allowed transitions given current band, apply parent-conditioning weights, perturb probabilities with any active news bias, sample one, then sample duration and optional overshoot.

### Option 2: Recursive Production Grammar

- **Representation.** Swings are nodes in a recursive grammar tree. Each node stores `(direction, relative_size=Fib_ratio_to_parent, completion_state, child_sequence_reference, context_flags)`; children represent the approach/turn/resolution phases at the next smaller scale.
- **Actions.** Grammar production rules expand a swing node into sequences like `[approach_down, climax_low, resolution_up_to_1.618]`. Leaf productions map directly to terminal moves (e.g., `terminal_up_half_band`).
- **Recursion.** Built-in: applying the same rule set to XL and S nodes yields self-similar structure. Parents pass context (e.g., “parent at 1.5 band”) to child productions to tilt probabilities.
- **OHLC Mapping.** Forward discretization parses OHLC into a grammar derivation tree using existing swing detection; reverse generation traverses the tree depth-first, emitting price path fragments per terminal symbol. Adjacent terminals are stitched via smoothing splines while respecting parent anchor prices.
- **Stochastic Elements.** Randomness enters when choosing among rule alternatives. Each rule has interpretable probabilities (e.g., “30% chance this resolution hits 2×”). Additional modifiers handle news (bias certain branches) and tail events (force alternate production).
- **Game Record.** Stored as a derivation log: `RuleApplied(rule_name, chosen_variant, context_snapshot)` plus terminal payloads (start price, end price, duration). Replay simply re-expands the same derivation with deterministic rendering.
- **Sampling Next Move.** At runtime we expand the frontier node whose completion window is next in time, sample the next production conditioned on context, and continue until all leaf nodes produce terminal moves; this naturally fills in lower scales after higher scales commit.

### Option 3: Event Chronicle Graph

- **Representation.** Maintain a chronologically ordered graph where vertices are structural events (`FORM`, `LEVEL_TEST`, `FRUSTRATION`, `COMPLETION`, `INVALIDATION`) and edges capture causal links (e.g., “L-level frustration triggered M measured move”). Each vertex stores `(scale, direction, reference_id, triggering_level, elapsed_bars, news_context)`.
- **Actions.** The generator advances by adding new event vertices based on current graph frontier. Between events, price follows deterministic interpolation bounded by last/next event targets. Events include explicit `LEVEL_TEST(from_band,to_band)` nodes to capture decision-zone chop.
- **Recursion.** Edges carry scale relationships: an XL completion vertex spawns children edges requiring L to reset; M or S events can only back-propagate if they accumulate enough evidence (e.g., repeated invalidations) to trigger a higher-scale event.
- **OHLC Mapping.** Discretization scans existing annotations, emits an event whenever a rule-defined condition occurs, and connects edges using detection IDs. Regen uses the graph as a storyboard: fill in bars between event timestamps by solving for smooth paths that satisfy boundary constraints and do not violate pending parent events.
- **Stochastic Elements.** Event selection uses hazard rates per event type (estimated from annotation frequency). Durations draw from mixture models that include heavy-tail components for waiting-time anomalies. News nodes attach to edges and temporarily alter hazards for adjoining vertices.
- **Game Record.** A JSON graph with arrays of vertices/edges: `{"events":[{"id":17,"scale":"M","type":"LEVEL_TEST","from":"1.382","to":"1.618","elapsed":14}], "edges":[{"from":17,"to":18,"relation":"chop_resolved"}]}`. Replaying reproduces both structure and order of decisions.
- **Sampling Next Move.** Evaluate hazard for each candidate event given current graph, draw waiting time, pick the event with smallest sampled time, update graph, and emit any derived lower-scale requirements before continuing.

## Tradeoff Analysis

*Delivered in the voice of Andy Grove—blunt, structured, focused on forcing functions:*

> “Bad companies are destroyed by crisis, good companies survive them, great companies are improved by them. Treat this decision as a mini-crisis: force it to reveal weaknesses before we commit.”

| Criterion | Weight | Option 1: Fib Band State Machine | Option 2: Recursive Grammar | Option 3: Event Chronicle Graph |
|-----------|--------|----------------------------------|-----------------------------|---------------------------------|
| Interpretability | 0.25 | **0.9** — band positions are literally what the trader sees | 0.85 — derivations are readable but trees are abstract | 0.75 — graphs are legible but more complex |
| Structural Fidelity | 0.2 | 0.85 — embeds band rules directly | **0.9** — rules enforce full swing lifecycle | 0.8 — events capture highlights but may miss intra-band nuance |
| Self-Similar Recursion | 0.15 | 0.8 — recursion handled via conditioning, not innate | **0.95** — grammar intrinsically recursive | 0.75 — relies on edge semantics for recursion |
| Learnability w/ Small Data | 0.15 | 0.8 — transition tables per band per scale manageable | 0.7 — more parameters (rule probabilities) to calibrate | 0.75 — hazard rates per event type feasible |
| Robustness to Noise / News | 0.1 | **0.85** — news modifiers simple, tail overrides explicit | 0.75 — context injection harder to reason about | 0.8 — hazards adapt cleanly to modifiers |
| Computational Cost | 0.05 | **0.9** — O(N) generation, simple sampling | 0.75 — tree expansion overhead | 0.7 — hazard competition + graph ops |
| Extensibility | 0.1 | 0.8 — add new bands/annotations easily | **0.9** — add rules modularly | 0.75 — graph schema changes ripple |
| **Weighted Score** | 1.0 | **0.856** | 0.836 | 0.771 |

Grove verdict: Option 1 slightly outruns Option 2 because it lands the interpretability punch while remaining computationally light. Option 2 shines on recursion elegance but costs more tuning cycles than our current data budget allows. Option 3 trails due to event-graph complexity; it might be a better moment later when we care more about causal storytelling than immediate generator bring-up.

## Recommendation

**Adopt Option 1 (Fibonacci Band State Machine) as the primary representation, but embed two hooks from Option 2:**
1. Treat each `BandTransition` as implicitly composed of phase tokens (approach / pivot / resolution) so we can later swap in grammar-derived substructure without rewriting the state machine.
2. Store the rule-choice metadata in the game log (even if currently trivial) so probability tuning can pivot toward a grammar when data volume warrants it.

This hybrid keeps the state machine simple enough to implement immediately while future-proofing for richer recursive composition.

### Sequencing Plan

1. **State & Logging Layer (Week 1).**
   - Implement `SwingState`/`GameState` dataclasses, Fib band quantization helpers, and canonical log schema.
   - Unit tests: round-trip a handful of annotated sessions through quantization/logging with zero structural drift.
2. **Forward Discretizer (Week 2).**
   - Feed existing swing detection output into the quantizer to produce band transition logs.
   - Validate logs via visual overlays (do levels and events align with annotation ground truth?).
3. **Generator Core (Weeks 3–4).**
   - Implement transition sampling with parent-conditioning, duration sampling, and Brownian bridge rendering.
   - Add news modifier hook and tail-event override path.
   - Visual smoke tests: produce charts, review versus reference markets for structural believability.
4. **Calibration Loop (Weeks 5–6).**
   - Seed transition matrices using Product North Star priors, then refine using aggregated annotation statistics.
   - Add CLI to tweak probabilities live and replay sequences for black-box-free iteration.
5. **Trace & Audit Tooling (Week 7).**
   - Build a trace viewer that maps each generated segment back to its logged transition, enabling expert review sessions.
   - Document mapping rules, file formats, and extension points.

### “Done” Criteria

- [ ] All four scales emit consistent `SwingState` entries and maintain parent-child causality checks.
- [ ] Discretizer/game log round-trip reproduces original structural events within tolerance on at least three long-form reference datasets.
- [ ] Generator produces OHLC sequences whose Fib level statistics (hit rates, dwell distributions, completion frequencies) fall within ±10% of real-market baselines for each scale.
- [ ] News bias and tail override knobs demonstrably tilt outcomes without violating structural invariants.
- [ ] Trace viewer can explain any bar in terms of the exact `BandTransition`/`StructuralEvent` that caused it, satisfying the interpretability north star.
- [ ] Documentation captured in `Docs/Reference` describing the representation, log schema, and tuning workflow so future contributors can extend without rediscovering context.
