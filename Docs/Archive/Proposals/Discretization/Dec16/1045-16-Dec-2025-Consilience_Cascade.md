# The Cascade Proposal

**Converting Market Time Series to Structural State Machines**

*A discretization framework for the Fractal Market Simulator*

---

## Executive Summary

### Recommendation

**We recommend discretizing ES-1m data using a Hierarchical State Machine (HSM) approach.** This framework:

1. **Represents market state** as a structured tuple of active swings across scales (XL, L, M, S), their Fibonacci level positions, and a simplified news model
2. **Encodes structural events** (swing formations, completions, invalidations, level crosses) as discrete state transitions
3. **Separates theory from parameters**: The structure (what can happen) comes from the fractal market theory; only the transition probabilities come from data
4. **Supports generation natively**: The state machine runs forward to produce OHLC bars, making the inverse mapping tractable

### Why This Approach

We evaluated three alternatives:

| Approach | Core Idea | Verdict |
|----------|-----------|---------|
| **Sequential (Token-Based)** | Market as event stream, like language tokens | Loses causal hierarchy; requires long context |
| **Hierarchical (Tree-Based)** | Swings contain sub-swings in nested structure | Elegant but hard to handle competing swings; generation tooling immature |
| **Hybrid State Machine** | Explicit state vector with rule-governed transitions | Best alignment with tenets; interpretable; naturally generative |

The state machine approach wins because it **embeds the theory directly into representation**. If the theory says "swings complete at 2x," this is a rule in the state machine. If data shows 73% complete cleanly while 27% overshoot, these become parameters. Structure is theory-driven; parameters are data-driven. This separation is essential for falsifiability.

### Critical Design Choices

1. **Active Swing Registry**: At any moment, track exactly one active swing per scale-direction pair, with its direction, origin price, current level band, and impulse measure

2. **Event Alphabet**: Five event types capture all structural transitions:
   - `SWING_START`, `SWING_COMPLETE`, `SWING_INVALID`, `LEVEL_CROSS`, `NEWS_SHOCK`

3. **Cross-Scale Coupling**: Larger scales explicitly constrain smaller scales. An XL completion doesn't just affect XL—it resets bias and may invalidate dependent swings at L, M, S

4. **News Model**: Separated into background drift (long-term bullish bias), scheduled events (CPI, FOMC), and stochastic shocks. News provides the randomness that the structural rules channel

### What This Achieves

- **Compression**: 6M bars → ~50K structural events
- **Interpretability**: Every state component has semantic meaning from the theory
- **Generativity**: State machine naturally runs forward to produce price paths
- **Falsifiability**: Predictions are explicit—if generated data doesn't complete at 2x, the theory fails

### Immediate Next Steps

1. Define state representation as Python dataclasses
2. Build state extraction pipeline from existing SwingDetector output
3. Compute empirical transition probabilities from historical ES data
4. Build minimal generator (rules only, no learned parameters)
5. Visual inspection by domain expert

### Risks

The main risk is that the theory itself is wrong—that Fibonacci relationships are post-hoc pattern-matching rather than causal structure. This proposal embraces that risk: **falsification is a feature, not a bug**. If generated data fails to look like real markets despite following the rules, we learn that the theory needs revision.

---

*This proposal was developed by the Consilience panel: a virtual consultation of Mandelbrot (fractals), Shannon (information), Simon (hierarchies), Feynman (simplification), Lo (adaptive markets), and Deutsch (good explanations).*

---

## Part I: Problem Statement Synthesis

### The Epistemological Challenge

Science advances through explanation, not mere correlation. We observe phenomena, propose causal theories, derive falsifiable predictions, and let reality arbitrate. This is Popperian science at its core, but David Deutsch takes it further: explanations that are *hard to vary* while still accounting for what they purport to explain are the hallmarks of good theories. Easy-to-vary explanations—those that can be adjusted post-hoc to fit any data—tell us nothing.

The Fractal Market Simulator faces this epistemological challenge directly. We have a theory—that market moves are fractal, that they complete at Fibonacci extensions, that bigger moves causally drive smaller ones. This theory makes specific predictions about *where* markets turn. But having a theory is not enough. We must now subject it to empirical test in a way that avoids the twin traps of:

1. **Overfitting**: Learning the noise instead of the signal, such that our "model" is just a memorization of historical data
2. **Circularity**: Validating the theory using the same assumptions that generated the theory

The fundamental question we face is not "how do we discretize market data?" but rather:

**How do we convert continuous price action into discrete representations that preserve the causal structure posited by our theory, enabling us to test whether that causal structure actually exists?**

### The Measurement Problem

Consider the analogy to coastlines. The length of Britain's coastline depends entirely on the scale of measurement. Mandelbrot showed this is not a bug but a feature—coastlines are fractal, and their "length" is not a meaningful quantity without specifying scale. Markets exhibit similar scale-dependent properties. A "swing" that appears massive on a 1-minute chart may be invisible noise on a daily chart. The question "how big is this swing?" requires an answer to "at what scale are you looking?"

Our theory embraces this explicitly with four scales (S, M, L, XL), but discretization forces us to confront it operationally:

- **When does one swing end and another begin?**
- **Which swings matter at which scales?**
- **How do we represent the hierarchical relationships between swings at different scales?**
- **What information must be preserved, and what can be discarded as noise?**

### The Data Reality

We have approximately 6 million 1-minute bars of ES (E-mini S&P 500) data spanning roughly 20 years. This sounds like a lot, but consider:

- At 6M bars, even fitting 100 parameters risks overfitting (60,000 data points per parameter seems generous until you realize that market regimes cluster temporally)
- The bars are not independent samples—they are highly autocorrelated
- Major structural events (swing completions, invalidations) number in the thousands or tens of thousands, not millions
- Cross-ticker validation is constrained: NQ/BTC/Mag7 may follow "similar rules" but the similarity is hypothesized, not verified

This data scarcity relative to model complexity is the central constraint. Any discretization scheme must produce a representation tractable for learning without inviting overfitting.

### What We Are Actually Trying to Accomplish

The project's north star is a market data generator. Discretization is not an end in itself but serves three purposes:

1. **Compression**: Reduce 6M bars to a manageable representation that captures structural features
2. **Abstraction**: Extract the causal relationships (swing → levels → completions/invalidations) from raw price
3. **Generativity**: Enable the learned representation to generate new, realistic market data

The third purpose is the ultimate test. If we can generate market data that experts cannot distinguish from real markets, and that exhibits the statistical properties of real markets (momentum, volatility clustering, Fibonacci relationships), then our theory has passed a stringent empirical test.

### The Core Problems to Solve

Given the above framing, the discretization proposal must address:

**Problem 1: Swing Identification and Boundary Determination**
When exactly does a swing begin and end? The current implementation uses lookback windows and protection validation, but these are heuristics that may not align with the causal structure we're trying to capture. We need a principled answer to: what makes a price point a swing endpoint?

**Problem 2: Scale Assignment**
Currently, swings are assigned to scales (S/M/L/XL) based on size quartiles. But the theory suggests causality flows from large to small scales. Should scale assignment be hierarchical (a swing is "L" because it's made of "M" sub-swings) rather than purely size-based?

**Problem 3: State Representation**
At any point in time, what is the "state" of the market? Multiple swings are active simultaneously across scales. How do we represent this multivariate state in a way that captures the relevant structure for prediction and generation?

**Problem 4: Transition Modeling**
Given a state, what are the possible next states? The theory provides rules (completions at 2x, frustration rules, measured moves), but these must be translated into a transition model. How stochastic should transitions be? What role does the "news model" play?

**Problem 5: Inverse Mapping**
If we generate a sequence of discrete states, how do we convert back to OHLC bars? This is the generative step. The discretization must be designed with this inverse problem in mind—we need to be able to "render" discrete states as plausible price paths.

**Problem 6: Validation Criteria**
How do we know if the discretization is "good"? We need measurable criteria that don't merely assess fit to training data but capture whether the essential causal structure is preserved.

---

## Part II: Guiding Tenets

The following tenets guide decision-making throughout this proposal. Each represents a genuine tradeoff where the opposite position is defensible. They are ordered by priority.

### Tenet 1: Interpretability Over Prediction Accuracy

**We prefer models whose components have clear semantic meaning over black-box models that may fit data better.**

*Why this is a real tradeoff*: Neural networks or other flexible models could potentially fit market patterns more accurately. We deliberately sacrifice potential accuracy for the ability to inspect, understand, and trust our model's reasoning.

*Rationale*: The goal is not to build a trading system that exploits market inefficiencies until they disappear. The goal is to understand market structure well enough to generate realistic data and validate a theory. A model we don't understand cannot validate anything—it just memorizes.

### Tenet 2: Theory-Driven Structure, Data-Driven Parameters

**The structure of our representation (what elements exist, how they relate) comes from the theory. Only the specific parameter values come from data.**

*Why this is a real tradeoff*: Letting data determine structure (e.g., discovering that five scales work better than four) could improve fit. We choose to fix structure from theory and only learn parameters within that structure.

*Rationale*: This is Deutsch's "hard to vary" criterion operationalized. If we let data determine structure, we lose the ability to falsify the theory. If the theory says four scales with Fibonacci relationships, we test that—not whether the data suggests 3.7 scales with phi^0.8 relationships.

### Tenet 3: Preservation of Causal Hierarchy

**Discretization must preserve the causal direction: larger scales drive smaller scales, not vice versa.**

*Why this is a real tradeoff*: Treating scales as independent might simplify modeling. We insist on representing the hierarchical causal structure even if it complicates implementation.

*Rationale*: The theory's core claim is that big moves drive small moves. A discretization that loses this structure cannot test this claim.

### Tenet 4: Minimal Sufficient Representation

**Include the minimum information needed to reconstruct plausible price paths. No more.**

*Why this is a real tradeoff*: More information (volume, order flow, time of day) might improve realism. We deliberately limit scope to keep the learning problem tractable.

*Rationale*: With 6M bars generating perhaps tens of thousands of structural events, we cannot afford to learn complex joint distributions. Better to model the core structure well than to add dimensions we can't reliably learn.

### Tenet 5: Falsifiability Over Flexibility

**Design the representation to make the theory's predictions testable, even if this limits expressiveness.**

*Why this is a real tradeoff*: A more flexible representation could capture "exceptions" to the theory. We prefer a representation that forces the theory's predictions to be clearly right or wrong.

*Rationale*: The point is to learn whether the theory is true, not to build a model that always works. If the theory is wrong, we want to know.

### Tenet 6: Reversibility Over Compression

**A discretization that can be reversed to generate price paths is more valuable than a more compressed but lossy representation.**

*Why this is a real tradeoff*: Maximum compression might capture "essence" better but make generation difficult. We prioritize the inverse mapping.

*Rationale*: The ultimate deliverable is a data generator. If we can't go from discrete states to OHLC bars, the discretization is useless regardless of how well it captures patterns.

---

## Part III: Expert Consultation

*To explore the problem space thoroughly, we convene a virtual panel of thinkers whose frameworks illuminate different aspects of the challenge. We call this panel **Consilience**—a term coined by William Whewell and revived by E.O. Wilson to describe the unity of knowledge across disciplines. The discretization problem sits at the intersection of mathematics, information theory, cognitive science, physics, finance, and epistemology. No single discipline owns the answer.*

### The Consilience Panel

1. **Benoit Mandelbrot** — Fractal geometry, fat tails in financial markets
2. **Claude Shannon** — Information theory, optimal coding, channel capacity
3. **Herbert Simon** — Bounded rationality, satisficing, hierarchical systems
4. **Richard Feynman** — Physical intuition, simplification, "what can I eliminate?"
5. **Andrew Lo** — Adaptive Market Hypothesis, reconciling efficiency with behavioral anomalies
6. **David Deutsch** — Constructor theory, good explanations, the structure of reality

### Session 1: On the Nature of Market Structure

**Mandelbrot**: *The markets are fractal, obviously. I spent decades showing this. But you must understand what fractal means—it does not mean that patterns repeat exactly at different scales. It means that the statistics are scale-invariant. The distribution of returns looks the same whether you measure hourly, daily, or weekly. This is different from your theory, which posits specific structural relationships between scales.*

**Feynman**: *Wait, let me make sure I understand. You're saying the market has self-similar statistical properties, but the project assumes self-similar structural properties—that specific swings at one scale cause specific swings at another scale?*

**Mandelbrot**: *Precisely. Statistical self-similarity is a statement about ensembles. Structural causality is a statement about individual trajectories. They are not the same thing. Your Fibonacci relationships might be artifacts of the statistical self-similarity rather than causal mechanisms.*

**Lo**: *This is the efficient market debate in disguise. If Fibonacci levels "work," is it because they reflect something fundamental about markets, or because enough traders believe in them that they become self-fulfilling? Either way, they might be real enough to model—but the causal story differs.*

**Deutsch**: *The question is whether the explanation is hard to vary. A statistical regularity that could have many causes is easy to vary—you can always post-hoc justify it. A causal mechanism that makes specific predictions is harder to vary. What predictions does the Fibonacci theory make that other theories don't?*

**Simon**: *I want to step back. Markets are complex systems with bounded-rational agents. Hierarchy emerges naturally in such systems because hierarchy is an efficient way to manage complexity. Your four scales might reflect genuine hierarchical structure in how traders process information—institutional traders on weekly charts, day traders on minute charts, each reacting to their own scale while creating structure for other scales.*

**Shannon**: *From an information-theoretic perspective, the interesting question is: what is the channel capacity of market price? How many bits per bar actually convey structural information versus noise? Your discretization is essentially a coding problem—you want to encode the signal and discard the noise. But to do that, you need to know the signal's structure.*

### Session 2: On Discretization Approaches

**Feynman**: *Let me suggest the simplest possible approach: just look at swing completions and invalidations. A swing completes or it doesn't. That's binary. Everything else is noise. Can you model markets with just a sequence of completion/invalidation events?*

**Mandelbrot**: *Too simple. The path matters. A swing that grinds slowly to completion has different implications than one that rockets there. Your theory even says this—impulse matters, not just size.*

**Simon**: *The right level of abstraction preserves decision-relevant information. What decisions does the generator need to make? At each moment, it needs to decide: does price go up or down? By how much? The discretization should capture the factors that determine these decisions.*

**Shannon**: *Think of it as quantization. You're taking a continuous signal and representing it with discrete symbols. The question is: what is the optimal quantization for your purposes? Rate-distortion theory tells us there's a tradeoff between bit rate (how many symbols you use) and distortion (how much information you lose).*

**Lo**: *In adaptive markets, patterns work until they don't. Your discretization should capture not just the pattern but the regime—are we in a trending market, a ranging market, a crisis? The same swing has different implications in different regimes.*

**Deutsch**: *You mentioned a "news model." This is interesting. In physics, we separate the laws (deterministic structure) from the initial conditions (what happens to be true). Your market structure is like laws; news is like initial conditions. The discretization should separate these concerns.*

### Session 3: On Representation and Learning

**Shannon**: *How much information is actually in your swings? Let me think... A swing has a start and end point, so that's maybe 10-12 bits for price levels (assuming reasonable quantization). It has a duration—another 10 bits perhaps. Direction is 1 bit. Scale is 2 bits. So maybe 25-30 bits per swing. If you have tens of thousands of swings, that's hundreds of thousands of bits to learn from. Your model should have at most hundreds of parameters, not thousands.*

**Feynman**: *Can we write down equations? In physics, we always write equations. What's the equation for the next swing given the current state? If you can't write it down, you don't understand it.*

**Simon**: *The equation might be stochastic. Markets involve many agents with hidden information. Even if the causal structure is deterministic, the best we can do is probabilistic predictions. But the probabilities should come from the theory, not be free parameters.*

**Mandelbrot**: *Be careful with probability distributions. Market returns are not Gaussian—they have fat tails. Your transition model must account for extreme events without overfitting to the specific extreme events in your training data.*

**Lo**: *This is where the news model matters. Extreme events are often news-driven. If you separate the "structural" component (what would happen without news) from the "shock" component (what news does), you might be able to model each more cleanly.*

**Deutsch**: *You need a model that could generate markets you haven't seen, not just reproduce the markets you have seen. This is the key test. Can your discretization plus generator produce January 2025 if trained only on data through 2020? That would be a real test of the theory.*

### Session 4: On Hierarchy and Scale

**Simon**: *Hierarchical systems have a beautiful property: you can often analyze them level by level. Each level has its own dynamics, with higher levels setting constraints for lower levels. Your XL swings constrain L swings, which constrain M swings, and so on.*

**Feynman**: *So the state at any moment is: what swings are active at each scale, and where is price relative to their Fibonacci levels? That's a lot of state, but it's structured state.*

**Mandelbrot**: *The challenge is that scales interact. A "small" move can trigger a cascade across scales. Your 2x completion at one scale might be a level touch at a larger scale. The discretization must capture these cross-scale interactions.*

**Shannon**: *This suggests a tree structure rather than a sequence. Each swing contains sub-swings. The natural representation is hierarchical.*

**Lo**: *But markets don't always respect hierarchy. Sometimes the tail wags the dog—a small event cascades up. The GameStop episode was fundamentally a small-scale phenomenon that created large-scale structure.*

**Simon**: *Those are the interesting cases! When hierarchy breaks down, something important is happening. Your discretization should be able to represent hierarchy-breaking events, even if the theory says they're rare.*

**Deutsch**: *Perhaps the hierarchy is probabilistic, not deterministic. Large scales usually constrain small scales, but occasionally there's a "phase transition" where small scales bubble up. The news model might govern when this happens.*

### Session 5: On Generation and Validation

**Feynman**: *The ultimate test is: can you generate data that fools an expert? I don't mean machine-learning fools—I mean actually fools a trader looking at a chart.*

**Lo**: *Visual inspection is underrated in quantitative finance. The eye is a sophisticated pattern detector. If generated charts "look wrong," they probably are wrong in ways that matter.*

**Mandelbrot**: *Check the statistical properties too. Does generated data have the right autocorrelation structure? The right fat tails? The right volatility clustering? These are fingerprints of real markets.*

**Shannon**: *You could train a discriminator—a model that tries to distinguish real from generated data. If you can train such a model, your generator is failing. If you can't, the generated data is statistically indistinguishable.*

**Simon**: *But beware Goodhart's Law. If you optimize for statistical indistinguishability, you might produce data that passes statistical tests but fails structural tests. The generator should be optimizing for structural correctness, with statistical properties as a consequence.*

**Deutsch**: *The deepest test is: does the generated data obey the theory? If your theory says swings complete at 2x and you generate data where they complete at 2.3x, something is wrong—either with the theory or the generator. Either way, you've learned something.*

---

## Part IV: Deliberation on Options

*Having gathered perspectives from the expert panel, we now synthesize their insights into concrete options for discretization.*

### The Fundamental Choice: Sequence vs. Hierarchy

The panel repeatedly surfaced a tension between two representation paradigms:

**Option A: Sequential Representation (Token-Based)**
Represent market evolution as a sequence of discrete events, analogous to tokens in a language model:

```
[XL_BULL_START] [L_BEAR_START] [LEVEL_CROSS:0.382] [M_BULL_START] [COMPLETION:L_BEAR] ...
```

*Advantages*:
- Proven machinery (transformers, RNNs) for sequence modeling
- Natural handling of time ordering
- Flexible—can represent any event sequence

*Disadvantages*:
- Hierarchy implicit, not explicit
- Cross-scale interactions hard to model
- May require very long context to capture relevant structure

**Option B: Hierarchical Representation (Tree-Based)**
Represent the market state as a tree where each swing contains sub-swings:

```
XL_Bull_Swing
├── L_Bear_Swing (retracement)
│   ├── M_Bull_Swing
│   └── M_Bear_Swing
└── L_Bull_Swing (continuation)
    └── M_Bear_Swing (pullback)
```

*Advantages*:
- Causal hierarchy explicit in structure
- Natural for reasoning about containment relationships
- Aligns with Tenet 3 (preserve causal hierarchy)

*Disadvantages*:
- Less mature tooling for hierarchical generation
- Tree structure may not naturally handle competing/overlapping swings
- More complex to convert back to price paths

**Option C: Hybrid (State Machine with Hierarchical State)**
Maintain a state vector that explicitly tracks active swings at each scale, with transitions governed by rules:

```
State = {
    XL: {direction: bull, level: 1.382, started: 50000},
    L:  {direction: bear, level: 0.618, started: 55000},
    M:  {direction: bull, level: 1.0, started: 55800},
    S:  {direction: bull, level: 0.5, started: 55900}
}
Transition: price tick → update levels → check completions/invalidations → emit events
```

*Advantages*:
- Explicit state makes rules directly implementable
- Hierarchy captured in state structure
- Natural for simulation (step through time)
- Aligns with Tenet 1 (interpretability) and Tenet 2 (theory-driven structure)

*Disadvantages*:
- Fixed structure may miss emergent patterns
- Rule-based transitions may be brittle
- Parameter estimation for transitions is non-trivial

### Assessing the Options Against Tenets

| Tenet | Sequence | Hierarchy | Hybrid State |
|-------|----------|-----------|--------------|
| 1. Interpretability | Medium | High | High |
| 2. Theory-driven | Low | Medium | High |
| 3. Causal hierarchy | Implicit | Explicit | Explicit |
| 4. Minimal representation | Variable | Low | Medium |
| 5. Falsifiability | Medium | High | High |
| 6. Reversibility | Medium | Medium | High |

The hybrid state machine approach scores highest across tenets. This aligns with Simon's view of hierarchical systems and Feynman's desire for explicit equations.

### The State Representation

Following the hybrid approach, the discrete state at any moment consists of:

**1. Active Swing Registry**
For each scale (XL, L, M, S), track:
- Direction (bull/bear)
- Origin price (the swing point—low for bull, high for bear)
- Current level band (which Fibonacci zone price currently occupies)
- Formation timestamp (when the swing started)
- Impulse measure (how rapidly it formed)

**2. Level Stack**
The set of all Fibonacci levels from all active swings, sorted by price. Each level has:
- Price
- Source swing (which swing generated this level)
- Type (support, resistance, target, completion)

**3. News State**
A simplified news model:
- Next scheduled event (if any) and countdown
- Current "shock" polarity and intensity (decaying over time)
- Background drift (long-term bullish bias)

### Transition Rules

Transitions are governed by the theory's rules, made operational:

**Price Evolution (Micro-Level)**
Between structural events, price evolves as a constrained random walk:
- Bias toward nearest incomplete target
- Volatility proportional to distance from recent extrema
- Clustering (high vol follows high vol)
- News shocks add impulse

**Structural Events (Macro-Level)**
When price crosses a significant level:
- **Level Cross**: Update current_level_band for affected swings
- **Completion (2x)**: Mark swing complete, may trigger new swing formation
- **Invalidation**: Remove swing from active registry
- **Frustration**: After N failed attempts at level, bias reverses

**Cross-Scale Cascade**
When a larger-scale event occurs:
- Smaller-scale swings that depended on the larger swing may invalidate
- New smaller-scale swings may form in the new context
- Parameters (volatility, bias) shift based on larger-scale state

### The Discretization Process

Given raw OHLC bars, discretization proceeds as:

**Step 1: Swing Detection (existing system)**
Use the current SwingDetector to identify swings at each scale. This produces the raw material.

**Step 2: State Sequence Extraction**
Walk through time, maintaining the state representation. At each bar:
- Update level bands based on price
- Detect structural events (completions, invalidations)
- Update active swing registry
- Record state transitions

**Step 3: Event Sequence Construction**
Extract the sequence of structural events:
- Swing formation
- Level crosses
- Completions
- Invalidations
This is the "compressed" representation of the market.

**Step 4: Parameter Estimation**
From the event sequence, estimate:
- Transition probabilities (given state X, what's P(next event = Y)?)
- Duration distributions (how long between events?)
- Price path characteristics within states

### The Generation Process

Given the learned parameters, generation proceeds as:

**Step 1: Initialize State**
Set up initial active swings (could be from historical state or random consistent state)

**Step 2: Simulate Micro-Path**
Generate OHLC bars until a structural event:
- Sample next bar direction and magnitude from learned distributions
- Apply news model perturbations
- Check for level crossings

**Step 3: Handle Structural Events**
When a level crossing or other trigger occurs:
- Determine event type (completion? invalidation? new swing?)
- Update state accordingly
- Apply cross-scale cascades

**Step 4: Iterate**
Continue until target duration reached.

### Addressing the Core Problems

**Problem 1 (Swing Boundaries)**: Boundaries are determined by the existing SwingDetector, which uses lookback windows and protection validation. The discretization takes these as given, treating swing detection as a separate (already addressed) problem.

**Problem 2 (Scale Assignment)**: Maintain the current size-based scale assignment, but overlay causal relationships: a swing at scale L is considered "contained by" the most recent active swing at scale XL that brackets its price range.

**Problem 3 (State Representation)**: The state is explicitly defined as the active swing registry plus level stack plus news state. This is a structured, interpretable representation.

**Problem 4 (Transition Modeling)**: Transitions are rule-based (from theory) with stochastic elements (from data). The rules determine what can happen; the data determines probabilities.

**Problem 5 (Inverse Mapping)**: Generation is designed into the representation. The state machine can be run forward to produce price paths.

**Problem 6 (Validation Criteria)**:
- Structural: Do generated swings obey the rules? (completions at 2x, retracements to fib levels)
- Statistical: Do generated bars have correct distributional properties?
- Visual: Can experts distinguish generated from real charts?
- Discriminative: Can a classifier learn to separate real from generated?

---

## Part V: Synthesis and Recommendation

### The Core Insight

Through the expert consultation and deliberation, a clear picture emerges: **the discretization should be a state machine whose states are theory-defined and whose transitions are rule-governed but stochastically parameterized.**

This approach:
- Embeds the theory directly into the structure (satisfying Tenet 2)
- Makes hierarchy explicit (Tenet 3)
- Produces an interpretable model (Tenet 1)
- Naturally supports generation (Tenet 6)
- Makes predictions testable (Tenet 5)
- Uses minimal representation (Tenet 4)

### The Specific Proposal

**We propose a Hierarchical State Machine (HSM) discretization with the following components:**

**1. State Space**
The market state at time t is a tuple:
- `active_swings`: Dict mapping scale → active swing info
- `levels`: Ordered list of price levels with metadata
- `news_state`: Background + scheduled + shock components
- `time_context`: Bar index, time of day, day of week

**2. Alphabet of Events**
Discrete events that mark transitions:
- `SWING_START(scale, direction, origin_price)`
- `SWING_COMPLETE(scale, direction)`
- `SWING_INVALID(scale, direction)`
- `LEVEL_CROSS(level_type, price, from_swing)`
- `NEWS_SHOCK(polarity, intensity)`

**3. Transition Rules**
Deterministic structure with stochastic parameters:
- Rule: "Bull swing completes when price closes above 2x"
- Parameter: P(clean completion vs. throw-over) = f(impulse, scale)

**4. Duration Model**
Between structural events, time passes:
- Inter-event duration modeled by scale-appropriate distribution
- Intra-event price path modeled as constrained random walk

**5. Cross-Scale Coupling**
Explicit rules for how large-scale events affect small scales:
- Completion at scale L sets bias for scale M/S
- Invalidation at scale L may cascade invalidations down

### What This Achieves

1. **Compression**: 6M bars → tens of thousands of events, with state sufficient for prediction
2. **Abstraction**: Swings, levels, completions are first-class objects
3. **Generativity**: State machine can be run forward to generate new paths
4. **Interpretability**: Every component has semantic meaning from the theory
5. **Testability**: Predictions are explicit and falsifiable

### What Remains to be Determined

1. **Specific state representation details**: Exact encoding of active swings
2. **Parameter estimation method**: Maximum likelihood? Bayesian? How to handle regime changes?
3. **News model specifics**: How to extract/model news shocks from historical data
4. **Validation metrics**: Exact thresholds for "indistinguishable from real"
5. **Scale interaction rules**: Precise specification of cross-scale cascades

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Theory is wrong | Falsification is a feature. If generated data fails, we learn. |
| Too few parameters to capture reality | Start simple, add complexity only when data demands it |
| Cross-scale rules are brittle | Build flexibility into rule parameters, not rule structure |
| Generation produces implausible paths | Constrain generation with market realism checks |
| Overfitting to ES | Eventually test on NQ/other instruments |

### Recommended Next Steps

1. **Formalize state representation** in code (dataclass definitions)
2. **Build state extraction pipeline** from existing swing detection output
3. **Compute event sequence statistics** from historical data
4. **Estimate baseline transition probabilities**
5. **Build simplest possible generator** (no learning, just rules)
6. **Visual inspection** of generated output
7. **Iterate** based on discrepancies

---

## Appendix A: Expert Biographies and Relevance

### Benoit Mandelbrot (1924-2010)
Mathematician who developed fractal geometry and applied it to financial markets. His work on "fat tails" and self-similarity directly informs our understanding of market structure at multiple scales.

### Claude Shannon (1916-2001)
Father of information theory. His framework for quantifying information and optimal coding illuminates the discretization problem as one of efficient representation.

### Herbert Simon (1916-2001)
Economist and cognitive scientist who studied bounded rationality and hierarchical systems. His insight that complex systems organize hierarchically provides theoretical grounding for our multi-scale approach.

### Richard Feynman (1918-1988)
Physicist known for his ability to simplify complex problems and his insistence on truly understanding rather than merely calculating. His approach guides our emphasis on interpretability.

### Andrew Lo (1960-)
Financial economist who developed the Adaptive Market Hypothesis, reconciling efficient markets with behavioral anomalies. His perspective helps us think about how patterns in markets evolve.

### David Deutsch (1953-)
Physicist and philosopher who developed constructor theory and criteria for good explanations. His epistemological framework informs our approach to theory testing and falsification.

---

## Appendix B: Glossary of Key Terms

- **Swing**: A high-low or low-high price movement that establishes structure
- **Reference Swing**: A validated swing used to project Fibonacci levels
- **Completion**: Price reaching the 2x extension of a swing
- **Invalidation**: Price violating the swing's structural point
- **Scale**: A size classification (S, M, L, XL) for swings
- **Level**: A Fibonacci-derived price target from a reference swing
- **State**: The complete description of active swings and their relationships at a point in time

---

*Prepared by the Consilience Panel*
*Proposal: Cascade*
*16 December 2025, 10:45 UTC*

