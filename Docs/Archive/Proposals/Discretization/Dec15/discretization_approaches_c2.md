# Discretization Approaches for Swing-Based Market Modeling

*Fractal Market Simulator — December 2025*

---

## Problem Statement

The Fractal Market Simulator aims to generate realistic OHLC data indistinguishable from real market behavior. The core insight from the Product North Star is that markets are recursive: every large move is composed of smaller moves obeying the same structural rules. This document addresses how to convert continuous OHLC time-series data into discrete "game pieces" suitable for a recursive, swing-based market model.

The challenge is threefold:

1. **Representation**: What discrete structures capture the essential dynamics of price action?
2. **Recursion**: How do these structures compose across scales while preserving self-similarity?
3. **Generation**: How can a stochastic process sample these structures to produce realistic price trajectories?

The destination is a market data generator. The game pieces we define here are the atomic units that generator will manipulate.

---

## Key Questions

These questions must be answered well for the discretization to succeed. Their quality is a primary deliverable.

| # | Question | Why It Matters |
|---|----------|----------------|
| Q1 | What is the minimal state representation that captures a market's structural position? | Determines memory requirements, interpretability, and whether the model can generalize |
| Q2 | What constitutes a "move" in this discrete game—and when is a move complete? | Defines the action space and terminal conditions |
| Q3 | How should multiple active swings at different scales interact during generation? | The North Star says big moves drive small moves—how does this constraint manifest? |
| Q4 | What information must be preserved in the game record for the system to be reversible (map back to OHLC)? | Ensures generated output is useful, not just abstractly correct |
| Q5 | Where should stochasticity enter—in move selection, magnitude, timing, or all three? | Balances realism against overfitting; determines generator's degrees of freedom |
| Q6 | How do we handle the "news" dimension without modeling semantic content? | The North Star treats news as accelerants with polarity and intensity—how to inject this? |
| Q7 | What makes one discretization more "learnable" than another given limited ground truth data? | Practical constraint: we have ~10-15 quality annotation sessions, not 10,000 |

---

## Guiding Tenets

These tenets are explicit tiebreakers. If you disagree with one, that disagreement becomes a productive focal point for discussion.

### T1: Interpretability Over Expressiveness

The representation must be human-readable. A trader should be able to look at the game state and understand "we're at 0.618 retracement of swing X, waiting for news to resolve direction." Black-box latent spaces may have higher fidelity but cannot be inspected, debugged, or extended.

**Tiebreaker**: When choosing between a more compact but opaque representation and a more verbose but interpretable one, choose interpretability.

### T2: Fibonacci Levels Are Attractors, Not Predictions

Fibonacci levels define where the market "wants" to go—they are probabilistic attractors, not deterministic targets. A move toward 2.0 extension doesn't mean 2.0 will be reached; it means 2.0 is the completion target that price orbits around.

**Tiebreaker**: When modeling transitions, use Fibonacci levels as probability modifiers on transitions, not hard constraints on destinations.

### T3: Scale Hierarchy Is Causal

The North Star is explicit: big moves drive smaller moves, not vice versa. The XL swing defines the gravity well; L, M, S swings are perturbations within it. This is not just a filtering heuristic—it's a causal claim about market structure.

**Tiebreaker**: When generating, always condition smaller-scale decisions on larger-scale state. Never let S-scale events drive XL-scale outcomes except through explicit "black swan" news mechanisms.

### T4: Stochastic But Not Random

The generator should produce diverse outputs that share structural DNA with real markets. This means: stochastic selection among valid moves, deterministic application of structural rules, no arbitrary randomness in price levels.

**Tiebreaker**: Randomness enters through *which* valid move occurs, not through *what* that move looks like once selected.

### T5: Data Efficiency Is Non-Negotiable

With 10-15 annotation sessions providing ground truth, the system cannot rely on learning from thousands of examples. The discretization must enable rule-based generation with parameters informed by (not derived from) limited data.

**Tiebreaker**: Prefer interpretable rules with tunable parameters over learned models requiring large training sets.

### T6: Reversibility Over Compression

The canonical game record must allow reconstruction of OHLC data. It's acceptable if the reconstruction is lossy at sub-swing granularity, but the structural events (level crossings, completions, invalidations) must be recoverable.

**Tiebreaker**: When compression conflicts with reversibility, choose reversibility.

---

## Expert Consultation

I consult a panel of thinkers whose reasoning styles suit these questions. The goal is to extract principles that translate into concrete design decisions.

---

### Claude Shannon on Minimal State Representation (Q1)

*"The fundamental problem of communication is that of reproducing at one point either exactly or approximately a message selected at another point."*

**Shannon's counsel:**

The minimal sufficient state is that which allows prediction of future behavior given past structure. For markets, this means:

1. **Current price** — where we are
2. **Active reference swings** — the gravitational wells we're orbiting (one per scale, maybe 2-3 competing at smaller scales)
3. **Level position** — where current price sits on each swing's Fibonacci grid (0.382? 0.618? 1.5?)
4. **Trend bias** — the prevailing direction at each scale
5. **Time since last structural event** — markets have memory of "how long we've been here"

You don't need the full price history—you need the structural summary. A trader looking at a chart derives exactly this information: "We're at 0.618 of the daily swing, inside a larger weekly structure at 1.382, and it's been three days since the last breakout attempt."

**Principle**: State = active swings (per scale) + current level position + directional bias + dwell time. Everything else is derivable or irrelevant.

---

### John von Neumann on Move Definition (Q2)

*"There's no sense in being precise when you don't even know what you're talking about."*

**Von Neumann's counsel:**

Before defining moves, be clear about what game you're playing. The North Star defines completion as reaching 2x extension of a swing. Invalidation occurs when price violates the swing point beyond threshold. Between these terminal states, price traverses Fibonacci levels.

A "move" in this game should be the atomic transition that changes structural state. Two candidates:

**Option A: Level-to-Level Moves**
A move is a transition from one Fibonacci band to an adjacent band. Example: price moves from the 0.618-1.0 band to the 1.0-1.382 band. These are numerous but granular.

**Option B: Structural Events**
A move is a completion, invalidation, or emergence of a new swing. These are sparse but significant.

The correct answer is both, with hierarchy. *Major moves* are structural events (completion, invalidation). *Minor moves* are level crossings. The generator samples minor moves until a major move occurs, then updates the swing structure.

**Principle**: Two-tier move space—major moves change swing structure, minor moves traverse levels within active swings.

---

### Benoit Mandelbrot on Scale Interaction (Q3)

*"Clouds are not spheres, mountains are not cones, coastlines are not circles, and bark is not smooth, nor does lightning travel in a straight line."*

**Mandelbrot's counsel:**

Self-similarity is the heart of fractal geometry. The rules at S-scale must be the same rules at XL-scale, differing only in magnitude. But the North Star adds a crucial asymmetry: larger scales provide boundary conditions for smaller scales.

Think of it as nested constraints:
- XL swing defines the "room" (the price range that makes sense)
- L swing defines "furniture placement" within the room
- M swing defines "movement paths" around the furniture
- S swing defines "footsteps" along the paths

A footstep (S move) can't suddenly relocate the room (XL swing), but the room's walls constrain where footsteps can go.

**Implementation**: When generating S-scale moves, first check compatibility with M, L, XL constraints. The probability of an S-scale move that would violate an L-scale structure should be near-zero unless a "black swan" news event permits it.

**Principle**: Scale hierarchy manifests as conditional probability—P(S move | L, M, XL state). Larger scales are conditioning, not conditioned.

---

### Richard Hamming on Canonical Game Records (Q4)

*"The purpose of computing is insight, not numbers."*

**Hamming's counsel:**

The game record should store decisions, not prices. Prices are derivable from decisions plus initial conditions. If you store:
- Initial reference swing (high, low, timestamps)
- Sequence of moves (level transitions, structural events)
- News events (polarity, intensity, timing)

You can reconstruct OHLC by replaying the sequence. The reconstruction may be lossy at the micro level (exact intra-bar movement) but exact at the structural level (which levels were crossed, when completions occurred).

This is analogous to storing a chess game as move notation rather than board images. The notation is complete for understanding the game; images are derivable.

**Storage format**:
```
{
  "initial_state": {
    "XL_swing": {"high": 5100, "low": 4800, "direction": "bull"},
    "L_swing": {...},
    "M_swing": {...},
    "S_swing": {...}
  },
  "moves": [
    {"type": "level_cross", "scale": "M", "from": "0.618", "to": "1.0", "bars": 12},
    {"type": "news", "polarity": +0.6, "intensity": "medium"},
    {"type": "completion", "scale": "M", "new_swing": {...}},
    ...
  ]
}
```

**Principle**: Store decisions and durations. Derive prices during replay.

---

### Nassim Taleb on Stochasticity (Q5)

*"The problem is that we read too much into shallow recent history, with emphasis on the anecdotal, the news, and the conspicuous."*

**Taleb's counsel:**

Markets exhibit two types of randomness:
1. **Gaussian noise**: Small, mean-reverting fluctuations (most news, most price action)
2. **Black swan events**: Rare, high-impact, history-altering moves

The discretization must handle both. For Gaussian randomness, stochasticity enters in:
- *Which* level transition occurs next (given multiple valid options)
- *How long* the transition takes (bars duration)
- *How much* overshoot/undershoot around the target level

For black swans, stochasticity enters as:
- Probability of a tail event (very low)
- Magnitude of the event (heavy-tailed distribution)
- Which structural rules it overrides (can force invalidation of higher scales)

**Implementation**: Sample from two distributions. 95% of moves are "normal" (structurally constrained, Gaussian-ish duration). 5% are "exceptional" (can break one level of hierarchy). <0.1% are "black swan" (can reset multiple scales simultaneously).

**Principle**: Bi-modal stochasticity—normal moves within structure, rare moves that restructure.

---

### Daniel Kahneman on News Modeling (Q6)

*"Nothing in life is as important as you think it is while you are thinking about it."*

**Kahneman's counsel:**

News doesn't create moves—news permits moves that were structurally pending. This is the North Star's insight: price at certain levels has tendencies, news provides the catalyst.

Model news not as a cause but as a modifier:
- **Polarity**: Positive or negative (-1 to +1)
- **Intensity**: Weak, medium, strong
- **Scheduled vs. surprise**: CPI is scheduled; COVID is surprise

A pending bullish move at 0.618 retracement needs only neutral-to-positive news to trigger. Strong negative news might delay it or trigger the opposite move. Very strong news can override structural expectations entirely.

**Implementation**: News is a stream of (polarity, intensity) tuples. When sampling the next move, news modifies transition probabilities. Scheduled news is known in advance; surprise news is sampled from a background process.

**Principle**: News as probability modifier, not move generator. Structure proposes, news disposes.

---

### George Pólya on Learnability (Q7)

*"If you can't solve a problem, then there is an easier problem you can solve: find it."*

**Pólya's counsel:**

With limited data, you cannot learn a complex generative model end-to-end. But you can:
1. Learn parameters of a rule-based model
2. Validate rules against ground truth
3. Extend rules incrementally as more data arrives

The discretization should decompose into components that can be validated independently:
- Level transition probabilities (from annotation data: how often do swings complete vs. invalidate?)
- Duration distributions (from OHLC: how many bars between structural events?)
- News impact functions (deferred: assumes existence of news predictor)

Each component is small enough to estimate from 10-15 sessions. The combined model is the product of these components.

**Principle**: Factor the model into independently learnable/validatable pieces. Compose at generation time.

---

## Concrete Implications

Synthesizing the consultation, here are the non-negotiable constraints and available degrees of freedom:

### Must Preserve

| Element | Why |
|---------|-----|
| Fibonacci levels as structural attractors | Core to North Star; defines where "completion" and "pullback" mean |
| Scale hierarchy (XL → L → M → S) | Causal structure; big drives small |
| Self-similarity of rules across scales | Fractal property; enables recursion |
| Two-tier events (major structural, minor level) | Matches real market behavior |
| Reversibility to OHLC | Output must be usable |

### Must Discard

| Element | Why |
|---------|-----|
| Exact intra-bar price paths | Not structural; adds noise without signal |
| Semantic news content | We model polarity/intensity, not text |
| Trader identity/positioning | We model aggregate behavior, not individual actors |
| Historical path dependence beyond active swings | State should be Markovian given swing structure |

### Degrees of Freedom

| Element | Range |
|---------|-------|
| Number of active swings per scale | 1-3 (currently defaulting to 1 primary, 2 alternates) |
| Level transition probability distributions | Can be uniform, empirical, or rule-derived |
| Duration model (bars per transition) | Exponential, log-normal, or empirical |
| News intensity distribution | Normal with long tail vs. explicit bi-modal |
| Black swan probability | 0.1% to 1% depending on scale |

---

## Discretization Options

I present three options for discretization, each with sufficient detail for implementation.

---

### Option A: Level-Grid Markov Model

**Philosophy**: Treat the market as a Markov chain over Fibonacci level positions, with scale providing hierarchy.

#### Representation

**State**: A tuple of level positions, one per scale:
```
State = (XL_band, L_band, M_band, S_band)

where band ∈ {<0, 0-0.382, 0.382-0.5, 0.5-0.618, 0.618-1.0, 1.0-1.382, 1.382-1.5, 1.5-1.618, 1.618-2.0, >2.0}
```

Each swing also has direction (bull/bear) and a reference price range (high, low).

**Full state** includes:
- Per-scale: (band, direction, reference_high, reference_low, bars_in_band)
- Global: last_news_polarity, last_news_intensity

#### Actions

**Level Transition**: Move to adjacent band. Not all transitions are valid:
- From 0.618-1.0 band: can go to 0.5-0.618 (pullback) or 1.0-1.382 (extension)
- Cannot skip bands except during black swan events

**Structural Event**: Completion (reach >2.0) or Invalidation (reach <0 for bull). These trigger swing replacement.

**News Injection**: Modify transition probabilities for next move based on (polarity, intensity).

#### Recursion Across Scales

Transitions are conditioned:
```
P(S_move | S_state, M_state, L_state, XL_state)
```

In practice:
1. Sample XL move (unconditional except for news)
2. Given XL move, sample L move (must be compatible)
3. Given L move, sample M move
4. Given M move, sample S move

Compatibility means: if XL is in pullback mode (moving toward 0), S cannot make net progress toward 2.0 except transiently.

#### OHLC Mapping

**Forward (discretize)**:
1. Initialize swing references from detected swings
2. Walk price bars, track which band price is in
3. Record band transitions as moves
4. Record structural events when thresholds are crossed

**Backward (generate)**:
1. Start with initial state
2. For each move, sample duration (bars) and price path within band
3. Concatenate paths
4. Aggregate to desired timeframe

#### Stochastic Elements

| Element | Distribution | Parameters |
|---------|--------------|------------|
| Next band | Categorical | Transition matrix (from ground truth or heuristic) |
| Bars in band | Log-normal | μ, σ per band per scale |
| Price path within band | Brownian bridge | Anchored at entry/exit prices, volatility σ |
| News arrival | Poisson | λ = 1 event per 50 bars (tunable) |
| News polarity | Normal | μ=0, σ=0.3, clipped to [-1, 1] |
| News intensity | Categorical | 70% weak, 25% medium, 5% strong |

#### Canonical Game Record

```json
{
  "version": 1,
  "initial_swings": {
    "XL": {"high": 5200, "low": 4800, "direction": "bull"},
    "L": {"high": 5100, "low": 4950, "direction": "bull"},
    "M": {"high": 5050, "low": 4980, "direction": "bull"},
    "S": {"high": 5020, "low": 4995, "direction": "bull"}
  },
  "moves": [
    {
      "timestamp": 0,
      "scale": "S",
      "type": "transition",
      "from_band": "0.618-1.0",
      "to_band": "1.0-1.382",
      "bars": 8
    },
    {
      "timestamp": 8,
      "scale": "S",
      "type": "completion",
      "new_swing": {"high": 5020, "low": 5002, "direction": "bear"}
    },
    {
      "timestamp": 12,
      "type": "news",
      "polarity": -0.4,
      "intensity": "medium"
    }
  ]
}
```

#### Trade-offs

| Criterion | Score | Notes |
|-----------|-------|-------|
| Interpretability | High | State is directly readable as "where price is structurally" |
| Fidelity | Medium | Loses intra-band price detail; preserves structural events |
| Extensibility | High | New rules = new transition probabilities |
| Learnability | High | Transition matrices estimable from annotation data |
| Robustness to small data | Medium | Requires some estimation; can bootstrap with heuristics |
| Computational cost | Low | Markov chain sampling is O(N) in output length |

---

### Option B: Event-Sequence Model

**Philosophy**: Focus on structural events (completion, invalidation, new swing formation) rather than level traversal. Price paths between events are derived, not tracked.

#### Representation

**State**: A stack of active swings, each with:
- Direction (bull/bear)
- Reference prices (high, low)
- Formation bar (when this swing was established)
- Status (pending, confirmed, frustrated)

The stack has implicit hierarchy: bottom = XL, top = S.

**No explicit level tracking**—levels are computed on demand from current price and reference swing.

#### Actions

**Structural Events**:
- `COMPLETE(scale)`: Swing at scale reaches 2.0; triggers new swing formation
- `INVALIDATE(scale)`: Swing at scale is violated; triggers swing removal and possible cascade
- `FORM(scale, swing)`: New swing detected; push to appropriate stack position
- `FRUSTRATE(scale)`: Price fails to advance toward target repeatedly; triggers measured move

**Level Crossings**: Not tracked as explicit moves. Levels are implicit in the price path.

#### Recursion Across Scales

Events cascade:
- An XL completion may trigger L, M, S re-evaluation
- An S invalidation cannot affect XL unless compounded by news

Generation works backward from structural events:
1. Sample next structural event type and timing
2. Fill in price path to reach that event
3. Update state
4. Repeat

#### OHLC Mapping

**Forward (discretize)**:
1. Run swing detection at all scales
2. Identify structural events (completion, invalidation, formation)
3. Record event sequence with timestamps

**Backward (generate)**:
1. Sample sequence of events with inter-event durations
2. For each interval, generate price path that ends at the event condition
3. Constrained path generation: "price must reach 2.0 by bar T"

#### Stochastic Elements

| Element | Distribution | Parameters |
|---------|--------------|------------|
| Next event type | Categorical | P(complete), P(invalidate), P(continue) per state |
| Bars to event | Negative binomial | Based on historical event frequency |
| Swing size | Log-normal | Calibrated from scale boundaries |
| Retracement depth | Mixture | 0.382 (30%), 0.5 (40%), 0.618 (30%) |
| News impact | Modifier on event probability | +/- based on polarity/intensity |

#### Canonical Game Record

```json
{
  "version": 1,
  "events": [
    {
      "bar": 0,
      "type": "FORM",
      "scale": "M",
      "swing": {"high": 5050, "low": 4980, "direction": "bull"}
    },
    {
      "bar": 45,
      "type": "COMPLETE",
      "scale": "M",
      "completion_price": 5120
    },
    {
      "bar": 46,
      "type": "FORM",
      "scale": "M",
      "swing": {"high": 5120, "low": 5080, "direction": "bear"}
    },
    {
      "bar": 52,
      "type": "NEWS",
      "polarity": 0.7,
      "intensity": "strong"
    },
    {
      "bar": 78,
      "type": "INVALIDATE",
      "scale": "M",
      "violation_price": 5125
    }
  ]
}
```

#### Trade-offs

| Criterion | Score | Notes |
|-----------|-------|-------|
| Interpretability | Medium | Events are readable; inter-event paths are implicit |
| Fidelity | Medium | Captures structural events; loses level-by-level detail |
| Extensibility | Medium | New rules require new event types |
| Learnability | High | Event frequencies directly countable from annotations |
| Robustness to small data | High | Fewer parameters to estimate |
| Computational cost | Medium | Path generation between events requires care |

---

### Option C: Hierarchical State Machine

**Philosophy**: Model each scale as a finite state machine with explicit states for "trending toward completion," "in pullback," "frustrated," etc. Scales communicate through messages.

#### Representation

**Per-Scale State Machine**:
```
States: {FORMING, ADVANCING, PULLBACK, DECISION_ZONE, EXHAUSTION, COMPLETE, INVALID}

Transitions:
  FORMING → ADVANCING (swing confirmed)
  ADVANCING → PULLBACK (retracement begins)
  PULLBACK → ADVANCING (retracement complete)
  PULLBACK → DECISION_ZONE (deep retracement, direction unclear)
  DECISION_ZONE → ADVANCING (breakout up)
  DECISION_ZONE → INVALID (breakdown)
  ADVANCING → EXHAUSTION (reach 2.0)
  EXHAUSTION → COMPLETE (pullback from 2.0 confirms completion)
  Any → INVALID (swing point violation)
```

**Global State**: Four state machines (XL, L, M, S) + communication channels between them.

**Messages**:
- `CONSTRAINT(scale, direction)`: Larger scale imposes directional constraint
- `RELEASE(scale)`: Larger scale removes constraint (reached target or invalidated)
- `NEWS(polarity, intensity)`: External input that modifies transition probabilities

#### Actions

Each state machine tick:
1. Receive messages from larger scales
2. Update transition probabilities based on messages
3. Sample next state
4. Generate price movement consistent with transition
5. Send messages to smaller scales if state changed

#### Recursion Across Scales

**Explicit message passing**:
- XL in ADVANCING sends CONSTRAINT(XL, bull) to L, M, S
- L in PULLBACK while XL is ADVANCING sends CONSTRAINT(L, pullback) to M, S
- When messages conflict, smaller scale resolves via probabilistic weighting

**Rule**: Messages from larger scales have higher weight. An XL CONSTRAINT dominates an L RELEASE.

#### OHLC Mapping

**Forward (discretize)**:
1. Detect swings, classify into states based on price position relative to levels
2. Track state transitions with timestamps
3. Record message events

**Backward (generate)**:
1. Initialize all state machines
2. Tick XL, then L, then M, then S (propagate constraints down)
3. Generate price consistent with lowest-level (S) state transition
4. Aggregate S price paths to higher timeframes
5. Repeat

#### Stochastic Elements

| Element | Distribution | Parameters |
|---------|--------------|------------|
| State transition | Categorical | Transition matrix per state, modified by messages |
| Duration in state | Geometric | p = P(exit state) per bar |
| Price movement per bar | Normal | μ based on state direction, σ from volatility |
| Message strength | Categorical | CONSTRAINT: 80% strong, 20% weak |
| News effect | Multiplier on transition to favorable state | Polarity aligns with direction |

#### Canonical Game Record

```json
{
  "version": 1,
  "scale_traces": {
    "XL": [
      {"bar": 0, "state": "ADVANCING", "duration": 120},
      {"bar": 120, "state": "PULLBACK", "duration": 35},
      {"bar": 155, "state": "DECISION_ZONE", "duration": 22}
    ],
    "L": [
      {"bar": 0, "state": "ADVANCING", "duration": 45},
      {"bar": 45, "state": "COMPLETE", "duration": 5},
      {"bar": 50, "state": "FORMING", "duration": 15}
    ]
  },
  "messages": [
    {"bar": 0, "from": "XL", "to": "L,M,S", "type": "CONSTRAINT", "direction": "bull"},
    {"bar": 120, "from": "XL", "to": "L,M,S", "type": "CONSTRAINT", "direction": "pullback"}
  ],
  "news": [
    {"bar": 140, "polarity": -0.3, "intensity": "medium"}
  ]
}
```

#### Trade-offs

| Criterion | Score | Notes |
|-----------|-------|-------|
| Interpretability | High | State names are meaningful; message flow is traceable |
| Fidelity | High | Captures both structure and market "mood" |
| Extensibility | High | New states/messages for new behaviors |
| Learnability | Medium | More parameters (transition matrices per state per scale) |
| Robustness to small data | Medium | Can initialize with rule-based matrices, tune with data |
| Computational cost | Medium | Message passing adds overhead; still O(N) |

---

## Trade-off Analysis

*In the voice of Daniel Kahneman, applying decision discipline:*

The three options represent different bets about what matters most:

**Option A (Level-Grid Markov)** bets that Fibonacci levels are the primary structural element, and that tracking position on the grid is sufficient. This is the most direct translation of the North Star's rules into a computational model. The risk is that the grid may be too rigid—real markets don't always snap to exact levels.

**Option B (Event-Sequence)** bets that structural events are the primary signal, and that level-by-level movement is noise. This is more parsimonious—fewer parameters, easier to learn from limited data. The risk is that inter-event dynamics may matter more than this model assumes; the "chop" between events carries information.

**Option C (Hierarchical State Machine)** bets that market "mood" (trending, pulling back, deciding, exhausted) is a first-class construct worth modeling explicitly. This is the most expressive option and maps well to how traders think. The risk is complexity—more states means more parameters, more edge cases, more debugging.

**Evaluation matrix:**

| Criterion | Weight | A (Level-Grid) | B (Event-Seq) | C (State Machine) |
|-----------|--------|----------------|---------------|-------------------|
| Interpretability | 25% | High (0.9) | Medium (0.7) | High (0.9) |
| Fidelity to North Star | 20% | High (0.85) | Medium (0.7) | High (0.85) |
| Extensibility | 15% | High (0.8) | Medium (0.65) | High (0.85) |
| Learnability (small data) | 25% | Medium (0.7) | High (0.85) | Medium (0.65) |
| Implementation complexity | 15% | Low (0.8) | Low (0.75) | Medium (0.6) |
| **Weighted Total** | | **0.795** | **0.745** | **0.77** |

The quantitative assessment slightly favors Option A, but the margin is narrow. Let me apply qualitative judgment:

**Option A's strength** is that it directly operationalizes the North Star's Fibonacci-centric worldview. The level grid *is* the market's coordinate system in this model. This alignment reduces translation errors between the spec and implementation.

**Option B's strength** is parsimony, but the North Star is explicit about levels mattering: pullbacks to 1.618, 1.5, 1.382 are distinct with different implications. An event-sequence model that ignores these distinctions loses fidelity.

**Option C's strength** is expressiveness—it can model phenomena like "frustration" that the North Star mentions but that don't fit neatly into level crossings. However, this expressiveness comes at the cost of more parameters to tune.

**My evaluation**: Option A is the right starting point, with hooks for Option C's concepts (frustration, exhaustion) as state annotations on bands rather than separate state machines. This gives:
- The rigor of Fibonacci-based positions
- The interpretability of explicit levels
- The extensibility to add market-mood concepts later
- The learnability of a single transition matrix per scale

---

## Recommendation

**Implement Option A (Level-Grid Markov Model) with state annotations.**

This means:
1. State = level band position per scale, with optional annotations (e.g., "frustrated", "explosive")
2. Actions = band transitions (minor) and structural events (major)
3. Recursion = top-down conditioning (XL → L → M → S)
4. Stochasticity = transition matrices + duration distributions + news modifiers
5. Record = sequence of transitions and events with timestamps

### Sequencing Plan

**Phase 1: Representation Layer**
1. Define `SwingState` dataclass: band, direction, reference prices, annotations
2. Define `GameState` as tuple of SwingStates (one per scale)
3. Define `Move` types: BandTransition, Completion, Invalidation, NewsEvent
4. Implement state → level mapping and level → band mapping

**Phase 2: Forward Mapping (Discretization)**
1. Given OHLC + detected swings, produce game state sequence
2. Walk bars, track band positions, emit moves on transitions
3. Validate: reconstructed structural events should match swing detector output

**Phase 3: Backward Mapping (Generation)**
1. Given game state sequence, produce OHLC
2. For each move, sample duration (bars) and price path
3. Use Brownian bridge or similar for intra-move paths
4. Validate: generated OHLC should produce same game state sequence when discretized

**Phase 4: Stochastic Sampling**
1. Implement transition probability matrices (initialize with rule-based heuristics)
2. Implement duration distributions (from historical data)
3. Implement news injection mechanism
4. Validate: sampled paths should be diverse but structurally valid

**Phase 5: Calibration**
1. Use ground truth annotation data to refine transition probabilities
2. Compare generated vs. real price action visually
3. Iterate on probability parameters

### Done Criteria

- [ ] `GameState` can represent any market configuration from the North Star rules
- [ ] Discretization produces interpretable move sequences from real OHLC
- [ ] Generation produces OHLC that passes visual inspection against real data
- [ ] Round-trip: discretize(generate(state)) ≈ state (within tolerance)
- [ ] Parameter estimation works with 10-15 annotation sessions
- [ ] Documentation enables extension by future developers

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Grid too rigid | Add "soft" band boundaries (probabilistic, not hard cutoffs) |
| Transition matrices overfit | Use Bayesian priors based on North Star rules |
| Generation looks artificial | Use variable volatility and realistic duration distributions |
| News model too simplistic | Deferred; current phase assumes news model exists |

---

## Summary

Discretizing continuous OHLC into game pieces requires:
1. **State**: Position on Fibonacci grids across four scales
2. **Actions**: Band transitions (minor) and structural events (major)
3. **Hierarchy**: Top-down conditioning (XL constrains L constrains M constrains S)
4. **Stochasticity**: Transition probabilities modified by news, duration sampled from distributions
5. **Reversibility**: Game record stores moves; OHLC is derivable

The Level-Grid Markov Model (Option A) best balances the North Star's Fibonacci-centric rules, interpretability requirements, and the constraint of limited training data. It is directly implementable, extensible to handle additional market behaviors, and produces game records that can be audited by human experts.

*"The price of reliability is the pursuit of the utmost simplicity."* — Tony Hoare
