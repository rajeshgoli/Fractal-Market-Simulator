# Discretization Approaches for Recursive Swing-Based Market Generation

*Fractal Market Simulator — December 2025*

---

## Problem Statement

This project exists to generate realistic OHLC market data indistinguishable from actual price action. The generation mechanism must embody the core insight from the Product North Star: **all market motion decomposes into level-to-level moves within swing structures, and these structures are fractally self-similar across scales**.

The immediate challenge: continuous OHLC time-series data must be transformed into discrete "game pieces"—a representation that enables:

1. **Recursive reasoning**: Big moves contain smaller moves obeying the same rules
2. **Stochastic generation**: Sampling plausible next states given current structure
3. **Interpretability**: Every generated move traceable to explicit structural rules
4. **Fidelity**: Generated data statistically indistinguishable from reference markets (ES, SPX)

The representation must bridge two worlds: the continuous reality of price (flowing through time at arbitrary precision) and the discrete logic of market structure (swings, levels, completions, invalidations). The discretization must preserve what matters—Fibonacci relationships, causal ordering, fractal self-similarity—while discarding what doesn't—intra-level noise, microsecond timing, sub-structural price wiggles.

**The core question**: What is the minimal discrete representation that captures the generative essence of market structure?

---

## Key Questions

The quality of any discretization depends on answering these questions with precision. Getting the questions right is half the work.

| # | Question | Why It Matters |
|---|----------|----------------|
| Q1 | What is the **minimal state** that uniquely determines valid next moves? | Over-specification wastes bits; under-specification loses causality |
| Q2 | What are the **primitive actions** at the swing level? | Too few loses expressiveness; too many loses tractability |
| Q3 | How does **recursion manifest** between scales? | Wrong coupling produces either chaos or rigidity |
| Q4 | Where does **stochasticity** enter the representation? | Determines what's rule-governed vs. what's sampled |
| Q5 | What **termination conditions** define move completion? | From the North Star: 2x extension or invalidation |
| Q6 | How do we **map back** from discrete moves to OHLC? | The representation must be invertible with controlled loss |
| Q7 | What makes a discretization **learnable** from limited data? | Overfitting risk is paramount; interpretability constrains this |
| Q8 | How do we preserve **momentum and volatility** characteristics? | Generated data must feel right, not just hit levels |

---

## Guiding Tenets

These are explicit tiebreakers for hard tradeoffs. If you disagree with a tenet, that becomes a productive focal point for discussion.

### T1: Interpretability Over Compression

*Every state transition must map to an English sentence about market structure.*

A move from "1.382 → 1.5" is interpretable ("price broke through initial extension toward decision zone"). A 64-bit latent vector is not. When compression and interpretability conflict, choose interpretability. Black-box approaches may achieve higher fidelity on training data, but they cannot generalize to regime shifts because they capture correlation, not causation.

**Tiebreaker**: If an architecture requires explanation by visualization rather than verbal description, it violates this tenet.

### T2: Structure-First, Time-Second

*The canonical representation is structural position, not temporal position.*

Markets don't care what time it is; they care where price is relative to structure. A swing at 1.618 behaves the same whether it took 2 hours or 2 days to get there. Time enters only as a secondary factor for momentum/volatility characteristics, not as a primary state coordinate.

**Tiebreaker**: If adding a temporal feature improves realism, encode it as a structural modifier (e.g., "impulse = distance/bars") rather than a clock.

### T3: Scale Hierarchy Is Causal, Not Correlational

*Larger scales constrain smaller scales, not vice versa.*

This is the North Star's "big moves drive smaller moves" axiom. The XL swing provides the playing field; the S swing plays within it. Upward causation (S influencing XL) exists only through structural events (invalidations, completions)—not through aggregation of noise.

**Tiebreaker**: If a representation allows small-scale noise to directly influence large-scale state (other than through defined events), it violates this tenet.

### T4: Moves Are Complete or Pending, Never Partial

*A move between levels is atomic at each scale.*

The generator doesn't produce "40% of the way from 1.382 to 1.5." It produces "at 1.382, pending move to 1.5" or "at 1.5, move completed." Sub-level price action is the domain of the next smaller scale. This discretization is what makes recursion tractable.

**Tiebreaker**: If the representation requires tracking partial progress within a level transition, it's operating at the wrong scale granularity.

### T5: Prefer Stochastic Rules Over Learned Weights

*Extend the ruleset, don't train the network.*

Given limited historical data, a parameterized stochastic rule (e.g., "probability of frustration = f(time_at_level, trend_alignment)") generalizes better than learned weights. Rules can be inspected, debugged, and extended. Weights cannot.

**Tiebreaker**: If performance requires learning from data, learn the *parameters* of an interpretable distribution, not the *structure* of a neural approximator.

### T6: Failure Modes Must Be Structural, Not Statistical

*When generation fails, it should produce structurally invalid output—not subtly wrong output.*

A generator that occasionally outputs impossible transitions (e.g., jumping from 0.382 to 2.0 without touching intermediate levels) is debuggable. A generator that outputs plausible-looking but regime-inappropriate sequences is not. Design the representation so violations are obvious.

**Tiebreaker**: Prefer hard constraints that reject invalid states over soft penalties that down-weight them.

---

## Virtual Panel Consultation

I will consult thinkers whose work directly addresses the nature of discretization, recursion, stochastic modeling, and market microstructure. The goal is not roleplay but synthesis: extracting actionable principles from their reasoning frameworks.

### Panel Assignments

| Question | Consultant | Relevance |
|----------|------------|-----------|
| Q1 (Minimal state) | **Herbert Simon** (Bounded Rationality) | Understood minimal representations for complex systems |
| Q2 (Primitive actions) | **Noam Chomsky** (Generative Grammar) | Defined primitives for recursive symbolic systems |
| Q3 (Scale recursion) | **Benoit Mandelbrot** (Fractals & Markets) | Literally wrote the book on fractal market structure |
| Q4 (Stochasticity) | **E.T. Jaynes** (Probability Theory) | Maximum entropy reasoning under constraints |
| Q5 (Termination) | **Alonzo Church** (Lambda Calculus) | Formalized recursion and termination |
| Q6 (Invertibility) | **Claude Shannon** (Information Theory) | Rate-distortion tradeoffs in lossy encoding |
| Q7 (Learnability) | **Leslie Valiant** (PAC Learning) | Formal bounds on learning from finite samples |
| Q8 (Momentum/volatility) | **Robert Engle** (ARCH/GARCH) | Captured volatility clustering in financial time series |

---

### Consultation: Herbert Simon on Minimal State (Q1)

*"A complex system can be described at many levels of abstraction. The appropriate level is the one that supports the decisions you need to make."*

**Simon's counsel:**

The state representation should contain exactly what's needed to determine valid next moves—no more, no less. For a swing-based market model, I would ask: what does a market participant need to know to predict the next structural event?

They need:
1. **Where price is** relative to active swing structures (not absolute price)
2. **What swings are active** at each scale (pending, not yet invalidated or completed)
3. **What the completion/invalidation targets are** (derived from swing endpoints)

They do *not* need:
- The full price history (only the structural summary)
- Exact timestamps (only relative duration for momentum)
- Inter-level price paths (abstracted away at current scale)

**Principle for this codebase:** The minimal state is {active_swings × current_levels}. An "active swing" is defined by (high, low, direction, scale). The "current level" is the Fibonacci band containing price. Everything else is derivable or irrelevant.

---

### Consultation: Noam Chomsky on Primitive Actions (Q2)

*"Human language is generated from a finite set of recursive rules operating on atomic symbols. The power lies not in the vocabulary but in the combinatorics of composition."*

**Chomsky's counsel:**

The action space should be small and combinatorially expressive. In linguistics, we have a handful of syntactic operations (merge, move) that generate infinite sentences. For markets, I would seek analogous primitives.

Examining the North Star rules, I see three irreducible actions:
1. **ADVANCE**: Price moves from current level to an adjacent level
2. **COMPLETE**: A swing reaches its 2x target, becoming a historical reference
3. **INVALIDATE**: A swing's protective level is violated, removing it from play

All complex price paths decompose into sequences of these primitives. "Price rallied to 1.5, pulled back to 1.382, then completed at 2.0" is ADVANCE(1.382→1.5), ADVANCE(1.5→1.382), ADVANCE(1.382→1.5), ADVANCE(1.5→1.618), ADVANCE(1.618→2.0), COMPLETE.

**Principle for this codebase:** Three primitive actions suffice. Additional "actions" (frustration, measured moves) are *composite* patterns of the primitives—sequences with attached probability modifiers, not new atomic types.

---

### Consultation: Benoit Mandelbrot on Scale Recursion (Q3)

*"Fractals are structures where the parts resemble the whole. Market prices exhibit this property: a daily chart and a minute chart have statistically similar patterns. This is not coincidence—it reflects the self-similar nature of the generative process."*

**Mandelbrot's counsel:**

Your North Star is correct: the same rules apply at every scale, with scale providing the boundary conditions. But be precise about what "self-similar" means operationally:

1. **Rule invariance**: The transitions (ADVANCE, COMPLETE, INVALIDATE) are identical at S, M, L, XL
2. **Parameter variation**: Extremity tolerance varies (S/M strict invalidation; L/XL allow -0.15 buffer)
3. **Causal coupling**: Larger scales provide the swing endpoints that define smaller-scale levels

The recursion is *nested*, not *parallel*. An M swing doesn't operate independently—it operates within the level bands defined by the containing L swing. When the M swing completes, it may trigger an L-scale ADVANCE.

**Principle for this codebase:** Represent scales as nested contexts. The XL swing defines the universe; each smaller scale operates on progressively finer Fibonacci subdivisions of the same price space. Cross-scale events (completion at M causing advance at L) are the joints of the recursive structure.

---

### Consultation: E.T. Jaynes on Stochasticity (Q4)

*"The maximum entropy distribution is the one that makes the fewest assumptions beyond the stated constraints. Any other distribution smuggles in information you don't have."*

**Jaynes' counsel:**

Stochasticity should enter precisely where the rules don't determine the outcome. Looking at your North Star:

- **Deterministic**: If price at 2.0, a pullback is required (the rule)
- **Stochastic**: Whether pullback targets 1.618, 1.5, or 1.382 (the selection)
- **Deterministic**: If at -0.1 (stop level), bias flips
- **Stochastic**: Whether recovery is explosive or grinding (the character)

The maximum entropy approach: given constraints (valid targets, structural context), assign probabilities that maximize uncertainty subject to those constraints. Concretely:

```
P(next_level | current_level, swing_state) = max_entropy distribution
subject to:
  - only adjacent levels reachable
  - completion probability increases near 2.0
  - invalidation probability increases below 0
  - historical frequencies from reference markets
```

**Principle for this codebase:** Stochasticity is target selection and timing, not rule selection. The *which* (rules) is deterministic; the *where within allowed* (specific target) is stochastic; the *when* (bars to transition) is stochastic with volatility clustering.

---

### Consultation: Alonzo Church on Termination (Q5)

*"A recursive function must have base cases—conditions under which it returns without further recursion. Without base cases, the function never terminates."*

**Church's counsel:**

Your swing model has clear termination conditions—the North Star specifies them:

1. **COMPLETE**: Price closes above/below 2.0 extension → swing becomes historical
2. **INVALIDATE**: Price violates protective level beyond threshold → swing is removed
3. **FRUSTRATE**: Price fails repeatedly at target → symmetric retracement triggered

These are the base cases. A swing in progress is a recursive call; termination requires reaching one of these conditions.

But note the subtlety: termination at one scale may *initiate* recursion at another. M-swing completion might trigger L-swing advancement. The generator must track which scales have active "open calls" and ensure eventual termination at each.

**Principle for this codebase:** Every swing has exactly three exits: COMPLETE, INVALIDATE, or FRUSTRATE (which is really "invalidate the bullish thesis, initiate bearish move"). The generator must guarantee reaching one of these for every initiated swing.

---

### Consultation: Claude Shannon on Invertibility (Q6)

*"Information can be compressed with loss if the receiver can tolerate reconstruction error. The key is understanding which details matter."*

**Shannon's counsel:**

Mapping discrete moves back to OHLC requires filling in sub-level detail. This is lossy reconstruction—you've abstracted away the microsctructure. The question is: what fidelity matters?

For your use case (training models, human learning, simulation), the requirements are:
- **Structural fidelity**: High, low, close must hit the declared levels
- **Path fidelity**: Between-level motion should have realistic character (trending, mean-reverting, impulsive)
- **Timing fidelity**: Bar counts between levels should match volatility regime

The inversion algorithm:
1. Given: discrete sequence (L1 → L2 → L3) with bar budgets (n1, n2)
2. Generate: n1 bars starting at L1, ending at L2, with regime-appropriate path
3. Path character: sample from library of level-to-level motifs (impulse, grind, chop)

**Principle for this codebase:** The discrete representation is the structure; OHLC is the rendering. Treat inversion as a graphics problem: the discrete moves are keyframes, OHLC interpolation fills the frames between.

---

### Consultation: Leslie Valiant on Learnability (Q7)

*"A concept class is efficiently learnable if the number of examples required grows polynomially with the complexity of the concept and the desired accuracy."*

**Valiant's counsel:**

Your constraint is limited data—perhaps hundreds of swing completions per scale in reference markets. What can be learned from this?

- **Transition probabilities** between adjacent levels: Yes, with reasonable confidence
- **Conditional distributions** (P(target | source, context)): Yes, if context is low-dimensional
- **Complex dependencies** (multi-step correlations): Marginal, prone to overfitting

The interpretability constraint is also a learnability constraint. A rule like "P(pullback to 1.382) = 0.4 if at 2.0 after explosive move" has 2-3 parameters. It can be estimated from ~30 examples. A neural network modeling the same relationship has thousands of parameters and requires thousands of examples.

**Principle for this codebase:** Each distributional component should have O(1) parameters estimable from O(10-100) examples. If a pattern requires more data than you have, make it a rule with default parameters rather than a learned distribution.

---

### Consultation: Robert Engle on Momentum/Volatility (Q8)

*"Volatility clusters—periods of high volatility follow high volatility, periods of low volatility follow low volatility. This is not noise; it's structure that can be modeled."*

**Engle's counsel:**

The discretization must capture that a move from 1.0 to 1.5 can be either:
- **Impulsive**: 5 bars, large candles, one-directional
- **Grinding**: 50 bars, small candles, back-and-forth

The structural level reached is the same; the character differs. This matters for:
1. **Swing classification**: Impulsive moves are "explosive" (higher structural significance)
2. **Subsequent behavior**: Impulsive completion more likely to trigger strong pullback
3. **Realism**: Human observers can instantly distinguish regimes

Encode volatility regime as a modifier on each transition:
- **impulse** = price_distance / bars_elapsed
- Transitions carry impulse values
- High-impulse transitions bias subsequent transitions toward high-impulse (clustering)

**Principle for this codebase:** Impulse is a first-class property of transitions, not an emergent artifact. The discrete state includes {level, active_swings, volatility_regime}. The generator samples from regime-conditional distributions.

---

## Synthesis: What Must Be True

Translating expert guidance into constraints on any valid discretization:

### Representation Requirements

| Requirement | Source | Constraint |
|-------------|--------|------------|
| Minimal state | Simon | State = {active_swings, current_levels, volatility_regime} |
| Three primitives | Chomsky | Actions = {ADVANCE, COMPLETE, INVALIDATE} |
| Nested scales | Mandelbrot | XL → L → M → S containment, not parallel independence |
| Max-entropy sampling | Jaynes | Distributions over targets, not over rules |
| Explicit termination | Church | Every swing exits via COMPLETE, INVALIDATE, or FRUSTRATE |
| Invertible encoding | Shannon | Discrete → OHLC via regime-conditioned path generation |
| Low-parameter learning | Valiant | O(1) parameters per distribution, O(10-100) samples |
| Volatility as state | Engle | Impulse modifies transitions and persists |

### What Must Be Preserved

- **Fibonacci grid**: Levels at 0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0, and extended (0.236, 0.786, 1.236, 1.786 for separation)
- **Causal ordering**: High-before-low (bull) or low-before-high (bear) determines swing direction
- **Scale hierarchy**: Larger swings bound smaller swings; cross-scale events defined explicitly
- **Termination semantics**: 2x completion, protective invalidation, frustration rules

### What Must Be Discarded

- **Absolute prices**: Only relative position within swing matters
- **Absolute time**: Only bar counts and impulse ratios matter
- **Sub-level paths**: Within-level motion is the domain of the next smaller scale
- **Microsecond precision**: Structural events happen on closes, not ticks

### Degrees of Freedom

These are design choices, not requirements:
- **Transition probability parameterization**: Discrete tables vs. continuous functions
- **Volatility regime encoding**: Discrete (high/medium/low) vs. continuous impulse
- **Cross-scale event handling**: Synchronous (immediate) vs. queued (end-of-bar)
- **Path generation method**: Motif library vs. generative model vs. interpolation

---

## Discretization Options

I present three options, each implementable. They differ in expressiveness, complexity, and alignment with the tenets.

---

### Option A: Level-Graph State Machine

**Philosophy:** The market at each scale is a finite state machine over Fibonacci levels. Transitions are stochastic; cross-scale events modify the state space.

#### Representation

**State:**
```python
@dataclass
class LevelState:
    scale: str  # S, M, L, XL
    level: float  # Current Fibonacci level (0, 0.382, ..., 2.0)
    active_swings: List[ActiveSwing]  # Swings with this scale
    volatility: float  # Impulse measure (0.0 to 1.0)

@dataclass
class GameState:
    levels: Dict[str, LevelState]  # One per scale
    global_bar: int  # For timing
```

**Actions:**
```python
@dataclass
class Action:
    action_type: str  # ADVANCE, COMPLETE, INVALIDATE
    scale: str
    target_level: Optional[float]  # For ADVANCE
    bars: int  # Duration
    impulse: float  # Character of move
```

**Transition function:**
```python
def transition(state: GameState, action: Action) -> GameState:
    """Apply action to state, return new state."""
    # 1. Validate action is legal (adjacent level, etc.)
    # 2. Update level for the scale
    # 3. If COMPLETE or INVALIDATE, update active_swings
    # 4. Check for cross-scale events (completion triggers L advance, etc.)
    # 5. Update volatility based on impulse
    return new_state
```

#### Recursion Across Scales

The level graph at each scale is bounded by the containing scale's current level:

```
XL at 1.5 → L operates in [1.382, 1.618] (XL decision zone)
L at 0.618 → M operates in [0.5, 0.786]
M at 1.0 → S operates in [0.786, 1.236]
```

Cross-scale events:
- S completes at 2.0 → M may advance
- M invalidates at -0.1 → L may shift bias

#### Stochastic Elements

**Target selection:** Given current level, sample target from:
```python
P(target | source, swing_state, volatility) = categorical distribution
# Parameters estimated from reference market counts
```

**Timing:** Given target, sample bars from:
```python
bars ~ Gamma(shape=f(distance), scale=g(volatility))
# Parameterized by distance and regime
```

**Impulse:** Given bars and distance:
```python
impulse = distance / bars
# Clipped to [0, 1], used to update volatility_regime
```

#### Canonical Game Record

```json
{
  "initial_state": { "XL": 1.0, "L": 0.618, "M": 0.382, "S": 0.236 },
  "swings": [
    {"scale": "XL", "high": 5100, "low": 5000, "direction": "bull"}
  ],
  "actions": [
    {"type": "ADVANCE", "scale": "S", "target": 0.382, "bars": 3, "impulse": 0.7},
    {"type": "ADVANCE", "scale": "S", "target": 0.5, "bars": 8, "impulse": 0.3},
    {"type": "COMPLETE", "scale": "S", "bars": 12}
  ]
}
```

#### OHLC Generation

For each action, generate bars:
1. Determine start and end prices from levels and active swing
2. Sample path character from motif library (impulse-indexed)
3. Generate OHLC sequence with appropriate high/low wicks
4. Ensure close of final bar hits target level

#### Strengths

- **Maximally interpretable**: Every transition is "price moved from X to Y"
- **Provably terminating**: Finite state machine with absorbing states
- **Low parameter count**: O(n_levels^2) transition matrix per scale
- **Easy validation**: Generated sequences can be verified against rules

#### Weaknesses

- **Coarse time resolution**: All time abstracted to bar counts
- **Limited path expressiveness**: Motif library may feel repetitive
- **Rigid level grid**: May miss off-grid structure that matters

---

### Option B: Swing Completion Graph

**Philosophy:** The game is played at the swing level, not the level level. Swings are nodes; edges are structural relationships (contains, invalidates, completes).

#### Representation

**State:**
```python
@dataclass
class Swing:
    swing_id: str
    scale: str
    direction: str  # bull, bear
    high: float
    low: float
    status: str  # pending, completed, invalidated
    parent_swing_id: Optional[str]  # Containing swing
    child_swings: List[str]  # Contained swings

@dataclass
class GameState:
    swings: Dict[str, Swing]
    current_price_level: Dict[str, float]  # Per-scale
    bar: int
```

**Actions:**
```python
@dataclass
class SwingAction:
    action_type: str  # SPAWN, ADVANCE, COMPLETE, INVALIDATE
    swing_id: str
    details: Dict  # Action-specific payload
```

**SPAWN:** Create a new swing at scale S contained within parent swing at scale M+
**ADVANCE:** Price moves toward swing's completion target
**COMPLETE:** Swing reaches 2x, becomes reference for future swings
**INVALIDATE:** Swing's protective level violated, removed from graph

#### Recursion Across Scales

Swings form a tree:
```
XL swing (root)
├── L swing 1 (child)
│   ├── M swing 1a
│   │   ├── S swing 1a-i
│   │   └── S swing 1a-ii
│   └── M swing 1b
└── L swing 2 (child)
```

New swings SPAWN only inside existing swings. Completion at a child level triggers potential advancement at parent level.

#### Stochastic Elements

**Swing spawning:** Given parent swing and current level, probability of new swing:
```python
P(spawn | parent_level, volatility)
# Higher at decision zones, lower in voids
```

**Completion vs. extension:** Given swing near 2.0, probability of:
```python
P(complete) vs P(extend_to_2.382) vs P(pullback)
# Depends on impulse of approach
```

**Invalidation cascade:** Given swing invalidated, probability of parent impact:
```python
P(parent_invalidation | child_invalidation, depth)
# Deeper invalidations less impactful
```

#### Canonical Game Record

```json
{
  "swings": {
    "XL-1": {"direction": "bull", "high": 5200, "low": 5000, "status": "pending"},
    "L-1": {"direction": "bull", "high": 5150, "low": 5050, "parent": "XL-1"},
    "M-1": {"direction": "bear", "high": 5120, "low": 5080, "parent": "L-1"}
  },
  "events": [
    {"bar": 100, "type": "SPAWN", "swing": "M-1"},
    {"bar": 150, "type": "ADVANCE", "swing": "M-1", "level": 1.382},
    {"bar": 200, "type": "COMPLETE", "swing": "M-1"}
  ]
}
```

#### OHLC Generation

For each event, generate bars:
1. Determine which swings are active and their level requirements
2. Sample path that satisfies all active swing constraints
3. On COMPLETE/INVALIDATE, ensure bar hits trigger level
4. On SPAWN, ensure high/low of forming swing are valid

#### Strengths

- **Captures swing relationships explicitly**: Parent-child structure is first-class
- **Natural for the North Star**: Matches the swing-centric worldview
- **Flexible scale interaction**: Cross-scale events emerge from graph structure

#### Weaknesses

- **More complex state management**: Graph operations vs. array updates
- **Less interpretable transitions**: "Swing M-1 advances" vs. "Price moves to 1.5"
- **Termination harder to verify**: Graph can grow unboundedly without care

---

### Option C: Hierarchical Hidden Markov Model (HHMM)

**Philosophy:** Each scale is a hidden Markov model; the hierarchy couples them through observation and transition modulation.

#### Representation

**State:**
```python
@dataclass
class ScaleHMM:
    scale: str
    hidden_state: int  # Discrete state (trend_up, trend_down, ranging, exhaustion)
    level: float  # Observable position
    transition_matrix: np.array  # P(s' | s)
    emission_params: Dict  # P(level_delta | s)

@dataclass
class GameState:
    hmms: Dict[str, ScaleHMM]  # Coupled through parent_state modulation
```

**Coupling:**
- Parent HMM state modulates child transition matrix
- Child emissions aggregate to parent observations

#### Recursion Across Scales

```
XL HMM: states = {bull_trend, bear_trend, consolidation}
        ↓ modulates
L HMM: transition_matrix *= parent_bias_multiplier
        ↓ modulates
M HMM: ...
```

#### Stochastic Elements

**Transition sampling:**
```python
s' ~ Categorical(P[:, s] * parent_modulation)
```

**Level emission:**
```python
level_delta ~ Gaussian(mu[s], sigma[s] * volatility)
```

**Cross-scale observation:**
```python
child_completes → parent_observation += completion_signal
```

#### Strengths

- **Established framework**: HMMs are well-understood, have inference algorithms
- **Natural volatility clustering**: Regime states capture clustering
- **Probabilistically principled**: Proper generative model with likelihoods

#### Weaknesses

- **Less interpretable**: "State 3 with emission 0.7" vs. "Bull swing at 1.618"
- **Harder to enforce hard constraints**: Fibonacci levels become soft targets
- **More parameters**: Transition matrices grow quadratically with states
- **Risk of black-box behavior**: Learned parameters may capture spurious patterns

---

## Trade-off Analysis

*In the voice of Daniel Kahneman (Thinking, Fast and Slow), known for clear-eyed assessment of cognitive biases and decision quality.*

---

The three options represent different bets on what matters most. Let me evaluate them against the criteria that actually determine success, not the criteria that feel impressive.

### Interpretability

This is stated as paramount. Let's be honest about what each option offers:

**Option A (Level-Graph)** is maximally interpretable. "Price is at 1.382, valid moves are to 1.5 or 1.236, we sampled 1.5." A child could follow the logic.

**Option B (Swing Graph)** is moderately interpretable. "Swing M-1 is advancing toward completion." You need the swing context to understand, but the concepts are natural.

**Option C (HHMM)** is marginally interpretable. "State transitioned from 2 to 3." What is state 3? You'd need to build interpretation apparatus on top.

**Verdict:** A > B >> C

### Fidelity to Reference Markets

Can the generated output be mistaken for real ES/SPX data?

**Option A** will produce data that hits all the structural levels perfectly but may feel mechanical. The motif library limits path variety.

**Option B** will produce data with natural swing relationships but may have awkward inter-swing transitions.

**Option C** will produce data with good statistical properties (volatility clustering, regime switching) but may violate structural rules that a trader would notice.

**Verdict:** B ≈ A > C (for structural fidelity); C > A ≈ B (for statistical fidelity). The Product North Star emphasizes structure, so A/B win.

### Extensibility

Can new rules be added without rebuilding the system?

**Option A:** Adding a new rule means adding transition probability modifiers. Clean extension.

**Option B:** Adding a new rule means adding swing event types. Clean extension.

**Option C:** Adding a new rule means retraining or hand-coding emission modifications. Awkward.

**Verdict:** A ≈ B > C

### Learnability from Limited Data

With perhaps 100-500 swing completions per scale in training data:

**Option A:** Needs to estimate ~20×20 transition probabilities per scale × 4 scales = ~1600 parameters. With 500 samples, this is borderline—many cells will be sparse. But most transitions are zero (non-adjacent), so effective parameters are ~100.

**Option B:** Needs to estimate spawn/complete/invalidate probabilities conditioned on parent state. Similar magnitude.

**Option C:** Needs to estimate N_states² × N_scales transition parameters plus emission parameters. With N_states = 4, this is comparable, but HHMM inference is less robust to sparse data.

**Verdict:** A ≈ B > C

### Computational Cost

For generating 1 million bars:

**Option A:** O(1M) level checks and samples. Trivial.

**Option B:** O(1M) swing tree operations. Slightly more, but still linear.

**Option C:** O(1M) HMM forward passes with parent modulation. More expensive, but linear.

**Verdict:** A > B > C, but all are tractable.

### Robustness to Small Data

When the training data doesn't cover a regime, what happens?

**Option A:** Falls back to uniform sampling over allowed transitions. Degrades gracefully.

**Option B:** Falls back to spawning minimal swings. May produce degenerate output.

**Option C:** May extrapolate poorly—learned parameters don't generalize to unseen regimes.

**Verdict:** A > B > C

### Summary Matrix

| Criterion | Weight | A (Level-Graph) | B (Swing Graph) | C (HHMM) |
|-----------|--------|-----------------|-----------------|----------|
| Interpretability | 30% | 10 | 7 | 3 |
| Structural fidelity | 25% | 8 | 9 | 5 |
| Extensibility | 15% | 9 | 8 | 5 |
| Learnability | 15% | 8 | 7 | 5 |
| Computational cost | 5% | 10 | 8 | 6 |
| Robustness | 10% | 9 | 6 | 4 |
| **Weighted Total** | 100% | **8.8** | **7.6** | **4.5** |

The HHMM (Option C) is clearly dominated. The question is whether the swing-centric view of Option B justifies its complexity over the level-centric simplicity of Option A.

---

## Recommendation

**Implement Option A (Level-Graph State Machine), with Option B's swing tracking as an overlay.**

### Rationale

Option A wins on the criteria that matter most: interpretability, robustness to limited data, and alignment with the "rules over learning" tenet. The level-centric view is also more natural for the OHLC inversion step—you're always asking "what level are we targeting?" not "which swing are we advancing?"

However, Option B's explicit swing graph addresses a real need: tracking which swings are active, which are completed, and how they relate. This is *bookkeeping*, not *generation*. The generator operates on levels; the bookkeeper maintains swing state.

### Hybrid Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LEVEL GENERATOR                       │
│  For each scale (XL → L → M → S):                       │
│    1. Sample next level from transition distribution    │
│    2. Sample bar count from timing distribution         │
│    3. Sample impulse from volatility regime             │
│    4. Emit (level, bars, impulse) action               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    SWING BOOKKEEPER                      │
│  For each action:                                        │
│    1. Check if action triggers swing event              │
│       - Level 2.0 crossed → COMPLETE                    │
│       - Level -0.1 crossed → INVALIDATE                 │
│       - New swing detected → SPAWN                      │
│    2. Update active swing registry                      │
│    3. Propagate cross-scale events                      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    OHLC RENDERER                         │
│  For each (level, bars, impulse) action:                │
│    1. Compute start and end prices from active swings   │
│    2. Sample path character from impulse-indexed motifs │
│    3. Generate OHLC sequence                            │
│    4. Append to output                                   │
└─────────────────────────────────────────────────────────┘
```

### Sequencing Plan

**Phase 1: Core State Machine (Foundation)**

1. Implement `LevelState` and `GameState` dataclasses
2. Implement transition validation (adjacent levels only, respecting active swings)
3. Implement basic transition sampling (uniform within allowed)
4. Test: Generate random walks that respect level constraints

**Milestone:** Can generate syntactically valid action sequences.

**Phase 2: Swing Bookkeeping**

1. Implement `SwingRegistry` that tracks active swings per scale
2. Implement event detection (COMPLETE when 2.0 crossed, etc.)
3. Implement cross-scale propagation rules
4. Test: Verify swing lifecycle matches North Star definitions

**Milestone:** Action sequences correctly update swing state.

**Phase 3: Probability Estimation**

1. Run swing detection on reference market data (ES, SPX)
2. Count level-to-level transitions per scale
3. Estimate transition probabilities with Laplace smoothing
4. Estimate timing distributions (Gamma fits to bar counts)
5. Test: Generated sequences have similar transition frequencies

**Milestone:** Transition distributions match reference markets.

**Phase 4: Volatility Regime**

1. Add impulse tracking to state
2. Implement regime-dependent transition modulation
3. Implement volatility clustering (impulse autoregression)
4. Test: Generated sequences have realistic volatility clustering

**Milestone:** Generated data has correct "feel" (impulsive moves cluster).

**Phase 5: OHLC Rendering**

1. Build motif library from reference market segments
2. Implement path generation given (start, end, bars, impulse)
3. Implement wick generation (realistic high/low relative to open/close)
4. Test: Generated OHLC visually resembles reference charts

**Milestone:** Can generate 1M bars of realistic OHLC.

**Phase 6: Validation**

1. Visual inspection by domain expert (the user)
2. Statistical comparison (level hit frequencies, swing durations, volatility)
3. Structural validation (all swings terminate correctly, no impossible transitions)
4. Iterate based on findings

**Milestone:** Domain expert cannot reliably distinguish generated from real data in blind test.

### Done Criteria

- [ ] State machine generates syntactically valid action sequences
- [ ] Swing bookkeeper correctly tracks swing lifecycle per North Star rules
- [ ] Transition probabilities estimated from ≥100 swings per scale
- [ ] Volatility regime produces realistic clustering (verified visually)
- [ ] OHLC renderer produces chartable output
- [ ] Domain expert validation: "This could be real" on ≥80% of samples
- [ ] All North Star rules implemented and testable

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Motif library feels repetitive | Expand library; add random variation to motifs |
| Transition distributions overfit | Use Laplace smoothing; validate on held-out data |
| Cross-scale propagation causes cascades | Add dampening; limit propagation depth |
| OHLC rendering artifacts | Visual inspection checkpoint before scaling |

---

## Appendix: Glossary

| Term | Definition |
|------|------------|
| **Level** | A Fibonacci ratio (0, 0.382, 0.5, ..., 2.0) defining a price threshold |
| **Swing** | A high-low or low-high pair defining a structural reference |
| **Bull swing** | High-before-low: sets up bullish structure |
| **Bear swing** | Low-before-high: sets up bearish structure |
| **ADVANCE** | Primitive action: price moves from one level to an adjacent level |
| **COMPLETE** | Primitive action: swing reaches 2x target and becomes historical |
| **INVALIDATE** | Primitive action: swing's protective level is violated |
| **Impulse** | distance / bars: measures move conviction |
| **Volatility regime** | Current impulse context affecting transition sampling |
| **Motif** | A characteristic level-to-level path shape (impulsive, grinding, choppy) |

---

## Appendix: Reference Implementation Sketch

```python
# Core state machine (Phase 1)
class LevelGenerator:
    LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0,
              1.236, 1.382, 1.5, 1.618, 1.786, 2.0]

    def __init__(self, scale: str, transition_probs: Dict):
        self.scale = scale
        self.transition_probs = transition_probs
        self.current_level_idx = 6  # Start at 1.0
        self.volatility = 0.5

    def valid_targets(self) -> List[int]:
        """Return indices of adjacent levels."""
        targets = []
        if self.current_level_idx > 0:
            targets.append(self.current_level_idx - 1)
        if self.current_level_idx < len(self.LEVELS) - 1:
            targets.append(self.current_level_idx + 1)
        return targets

    def sample_transition(self) -> Tuple[int, int, float]:
        """Sample (target_idx, bars, impulse)."""
        targets = self.valid_targets()
        probs = [self.transition_probs.get((self.current_level_idx, t), 0.5)
                 for t in targets]
        probs = np.array(probs) / sum(probs)

        target_idx = np.random.choice(targets, p=probs)

        # Sample timing
        distance = abs(target_idx - self.current_level_idx)
        bars = max(1, int(np.random.gamma(2 + distance, 3 / self.volatility)))
        impulse = distance / bars

        return target_idx, bars, impulse

    def advance(self, target_idx: int, bars: int, impulse: float):
        """Execute transition."""
        self.current_level_idx = target_idx
        self.volatility = 0.9 * self.volatility + 0.1 * impulse  # EMA update
```

This sketch illustrates the simplicity of Option A. The full implementation will layer swing bookkeeping and OHLC rendering on this foundation.

---

*"The purpose of abstraction is not to be vague, but to create a new semantic level in which one can be absolutely precise."* — Edsger Dijkstra

This discretization creates exactly that: a semantic level where market structure can be described with precision, generated with interpretable rules, and rendered back to the continuous domain of price.
