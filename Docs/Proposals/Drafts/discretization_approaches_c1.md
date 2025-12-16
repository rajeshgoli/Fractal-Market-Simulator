# Discretizing Market Swings: From Continuous Time Series to Game Pieces

> **Purpose**: This document explores approaches for converting continuous OHLC price data into discrete representational units ("game pieces") suitable for realistic market data generation.

---

## 1. Problem Statement

We have a market simulator that operates on the following axiom: **all price movement is recursive**. Every large move is composed of smaller moves, and those smaller moves follow the same structural rules. The rules involve Fibonacci relationships, completion targets (2x extension), invalidation thresholds, and liquidity dynamics at key levels.

Currently, we can:
- Detect swings at multiple scales (S, M, L, XL) from OHLC data
- Validate swing structure using Fib-based rules
- Track completions and invalidations

**The challenge**: We want to *generate* realistic price data, not just analyze it. This requires converting the continuous OHLC representation into discrete units that:

1. **Can be sequenced** — A generative model needs tokens, states, or symbols to work with
2. **Preserve structure** — Fib relationships, parent-child hierarchies, completion/invalidation dynamics
3. **Enable reconstruction** — We must be able to render discrete sequences back to OHLC
4. **Are learnable** — The representation must be compact enough for a model to learn patterns

The fundamental tension: **continuous price action has infinite precision, but generative models need finite vocabularies**. How do we discretize without losing the essential structure?

### Constraints

| Constraint | Source | Implication |
|------------|--------|-------------|
| Fractal self-similarity | Axiomatic | Same discretization must work at all scales |
| Fib level adherence | Product north star | Discretization boundaries should align with Fib ratios |
| Move completion semantics | Product north star | 2x extension = completion; must be representable |
| Invalidation semantics | Product north star | Scale-dependent violations must be encodable |
| Stochastic news overlay | Product north star | Discrete moves should allow for trigger injection |

### What We're NOT Solving Here

- Bar-by-bar OHLC generation (too granular, misses structure)
- News event modeling (assume this layer exists separately)
- Long-term convergence (decades-scale; out of scope per north star)

---

## 2. Key Questions

Getting the questions right is half the battle. These are the critical questions we must answer:

### Q1: What is the atomic unit of a "game piece"?

Is it a single swing (H→L or L→H)? A completed move (reaching 2x)? A swing with its completion status? The choice of atomic unit determines vocabulary size and expressiveness.

### Q2: How do we encode swing magnitude?

Swings vary from 5 points to 500+ points. Do we:
- Use absolute sizes (infinite vocabulary)?
- Bucket into scale categories (S/M/L/XL)?
- Encode relative to parent swing (Fib-relative)?
- Use percentile ranks (relative to distribution)?

### Q3: How do we encode completion state?

A swing can be at various stages: 0.382 (just formed), 0.618, 1.0, 1.382, 1.5, 1.618, 2.0 (completed), or invalidated. Is this part of the token, or tracked separately?

### Q4: How do we represent parent-child relationships?

A Large swing contains Medium swings which contain Small swings. Do we:
- Flatten to a single sequence (lose hierarchy)?
- Use nested structures (complex, hard to generate)?
- Interleave scales with markers?
- Use separate streams per scale?

### Q5: How do we preserve temporal dependencies?

Moves at one scale influence moves at other scales. The frustration rule, measured move rule, and multi-swing rule all involve temporal dependencies across scales. How do we encode these?

### Q6: What vocabulary size is tractable?

LLMs work with 50K-100K tokens. Smaller vocabularies are easier to learn but may lose expressiveness. What's the right size for swing representation?

---

## 3. Expert Consultation

We now consult domain experts to answer these questions. Each expert brings a unique lens.

---

### Claude Shannon (Information Theory)

*On the atomic unit and encoding efficiency:*

> "The fundamental problem of communication is that of reproducing at one point either exactly or approximately a message selected at another point."
>
> Your atomic unit should be the **minimum unit that carries semantic meaning in your domain**. In markets, that's a *completed structural move* — not a point, not a bar, but a swing that has resolved (either to completion or invalidation).
>
> Consider entropy. If you encode swings with too much precision (exact prices), you waste bits on noise. If you encode too coarsely, you lose signal. The optimal encoding captures **just enough information to distinguish meaningful states**.
>
> For magnitude: don't encode absolute values. Encode *relative to context*. A 10-point move means nothing in isolation; a move to the 0.618 retracement level is universally meaningful. **Normalize all magnitudes to Fibonacci ratios of containing structure.**
>
> Vocabulary size follows from entropy analysis. Count the meaningful distinctions: ~8 Fib levels × 2 directions × ~4 completion states × ~4 scales = ~256 distinct atomic states. This is tractable. Anything beyond this is likely noise.

---

### Benoit Mandelbrot (Fractal Geometry, Market Analysis)

*On self-similarity and multi-scale structure:*

> "Markets are fractal. The same patterns appear at every scale, from minute charts to monthly charts. This is not metaphor — it's measurable."
>
> Your discretization **must respect self-similarity**. This means: whatever representation you choose for Large swings must work identically for Small swings. The grammar is scale-invariant.
>
> The parent-child problem has an elegant solution: **recursive composition**. A Large swing IS a sequence of Medium swings. A Medium swing IS a sequence of Small swings. You don't need separate encodings — you need **one grammar that applies recursively**.
>
> Think of it like an L-system in biology. A tree branch looks like a smaller tree. You don't describe branches and twigs separately; you describe a branching rule and apply it recursively.
>
> For market moves: define a swing as `[approach → climax → resolution]`. Each phase can itself be a swing at a smaller scale. **The recursion is the representation.**
>
> This also solves temporal dependencies. A parent swing constrains its children. When you're at 1.5 of a Large swing, the Medium swings within it are constrained by that context. **Context flows down the tree, not across a flat sequence.**

---

### Robert Shiller (Behavioral Economics, Market Psychology)

*On what the discretization must capture:*

> "Markets are driven by narratives and feedback loops. Price levels become significant because participants believe they are significant. This is reflexive."
>
> Your Fibonacci levels matter not because of mystical math, but because **enough traders watch them**. The 0.618 retracement works because people expect it to work, creating self-fulfilling prophecy.
>
> This means your discretization must capture **level semantics**, not just price. It's not that price is at 5050; it's that price is at the 0.618 retracement of the parent swing. The latter is meaningful; the former is noise.
>
> For completion states: the difference between 1.95 and 2.0 is enormous psychologically. One is "almost there," creating tension. The other is "done," triggering profit-taking. **Your encoding must distinguish these states sharply**, not blur them on a continuous scale.
>
> I'd advocate for a discretization that mirrors how traders think: "We're at the 0.618 pullback of the daily swing, attempting the 1.5 extension of the hourly swing." This is the language of the market. Your tokens should speak this language.

---

### Fischer Black (Quantitative Finance, Option Pricing)

*On noise vs. signal and what's worth encoding:*

> "Noise trading is trading on noise as if it were information. Most short-term price movement is noise."
>
> Your discretization should be **robust to noise**. Don't encode every wiggle. Encode structural events: a swing forming, a level being tested, a breakout, a failure.
>
> For magnitude encoding: I'd use **quantiles rather than absolute thresholds**. A "large" swing is one in the top quartile of recent swings — not one above some fixed point value. This naturally adapts to volatility regimes.
>
> For completion states: coarsen aggressively. I'd suggest three states: FORMING (sub-0.382), ACTIVE (0.382 to 1.618), RESOLVED (above 1.618 or invalidated). Fine distinctions within these bands are mostly noise.
>
> The parent-child relationship is where signal lives. **A swing's behavior is largely predicted by its context in the parent structure.** Encode this relationship explicitly. A swing at the 0.618 of its parent behaves differently than one at 1.382.

---

### Andrej Karpathy (Deep Learning, Sequence Modeling)

*On what makes a representation learnable:*

> "The best representations are those where similar things are close and different things are far — in embedding space."
>
> For a generative model to work, your tokens need to be **compositional**. The meaning of a sequence should emerge from the meanings of its parts. This argues against encoding too much context into each token.
>
> I'd split the representation:
> - **Structural tokens**: direction, relative magnitude (Fib-based), completion state
> - **Context embeddings**: parent swing state, scale, position in larger structure
>
> Don't try to cram everything into the token. Let the model learn to combine base tokens with context. This is how language models work — "bank" means different things in different contexts, and the model learns this.
>
> For vocabulary size: smaller is better, as long as you can express what you need. **256-512 base tokens** with contextual embeddings is probably optimal. Larger vocabularies make learning harder without clear benefit.
>
> On temporal dependencies: use attention mechanisms. They're designed for exactly this problem — learning which past states matter for the current prediction. Don't try to encode all dependencies in the tokenization itself.

---

### Ilya Sutskever (Sequence-to-Sequence Learning)

*On generation and reconstruction:*

> "The key insight of seq2seq is that you can map arbitrary sequences to arbitrary sequences if you have enough capacity and the right architecture."
>
> For market generation, your challenge is invertibility. You need to go:
> - OHLC → Swings → Tokens (analysis)
> - Tokens → Swings → OHLC (generation)
>
> The middle representation (tokens) doesn't need to preserve everything — just enough for **plausible reconstruction**. The generated OHLC doesn't need to match any real OHLC; it just needs to *look real* and *obey the rules*.
>
> This relaxes the discretization problem. You can lose information (exact prices, exact timestamps) as long as you preserve **structural invariants** (Fib relationships, completion logic, scale hierarchy).
>
> For the generative model: I'd use an autoregressive transformer. Feed it the current market state (active swings at all scales, their completion states), and have it predict the next structural event. The event space is discrete and bounded.
>
> Key insight: **Generate events, not prices.** Events like "swing completes to 2.0" or "new swing forms from 0.618 pullback" are discrete and learnable. Translate events to prices only at the final rendering step.

---

### Will Wright (Game Design, Emergent Systems)

*On making it playable and intuitive:*

> "The best simulations are ones where simple rules create complex, emergent behavior. Players should be able to understand the rules but be surprised by the outcomes."
>
> Your "game pieces" should be **tangible and manipulable**. A trader looking at your system should think: "Ah, this is a 0.618 pullback in the daily, trying for the 1.618 extension." The pieces should map to how humans conceptualize markets.
>
> I'd structure it like a tile-based game:
> - **Tiles** (swings) have properties: direction, magnitude class, completion state
> - **Placement rules**: tiles must connect properly (a swing must start where the previous ended)
> - **Constraint propagation**: parent tiles constrain child tiles (Fib levels, invalidation thresholds)
>
> This gives you a **generative grammar** that's both computational and intuitive. You can generate by placing tiles that satisfy constraints. You can analyze by parsing observed data into tile sequences.
>
> For human learning: let players place tiles and see the resulting price action. "What if the pullback went to 0.382 instead of 0.618? How does the rest of the structure change?" This is how intuition is built.

---

### Sid Meier (Strategy Games, Decision Modeling)

*On meaningful choices and state spaces:*

> "A game is a series of interesting decisions. Each decision should have clear options with distinct consequences."
>
> Your discrete states should represent **decision points**, not arbitrary snapshots. In markets, decision points are: swing formations, level tests, breakouts, failures.
>
> The state space should be **legible**. At any moment, I should be able to ask: "What are the possible next states? What's the probability of each?" If your discretization makes this hard to answer, it's wrong.
>
> I'd organize states around the **completion state of the dominant swing**:
> - FORMING: New swing establishing itself
> - TESTING: Price at a key level (0.618, 1.0, 1.382, etc.)
> - BREAKING: Price moving through a level
> - FAILING: Price rejected from a level
> - COMPLETING: Price reaching terminal target (2.0 or invalidation)
>
> Each state has clear successor states with transition probabilities that depend on context (parent swing, recent history, scale).
>
> This is your game loop: observe state → predict transitions → see outcome → update beliefs. Repeat fractally at all scales.

---

### Addendum: The Interpretability Imperative

*A critical constraint surfaces: with limited training data, interpretability isn't a nice-to-have — it's existential.*

**The Question Posed**: Given that we have limited market data and the generator's output depends on explainability, should we prioritize interpretable stochastic rules over learned representations? Can interpretable rules scale endlessly without loss of fidelity, while black-box models risk overfitting?

---

#### Claude Shannon (Revisited)

> "The fundamental theorem of channel capacity tells us something important here: **with limited samples, you cannot reliably estimate many parameters.**
>
> A transformer with 10 million parameters trained on 10,000 swing sequences is not learning — it's memorizing. The effective degrees of freedom exceed the data.
>
> But consider a stochastic grammar with 50 interpretable parameters (transition probabilities between Fib levels). Each parameter can be estimated reliably from even modest data. And here's the key: **the parameters have meaning**. The probability of completing to 2.0 given you're at 1.618 is something a trader can validate, adjust, and reason about.
>
> With interpretable rules, your 'model' is really a structured hypothesis about market mechanics. You can test each rule independently. You can explain why the generator produced a specific sequence. **Debugging a grammar is possible; debugging a transformer is archaeology.**"

---

#### Benoit Mandelbrot (Revisited)

> "This question reveals a deep truth about fractal systems: **complexity arises from simple rules, not complex encodings.**
>
> Consider the Mandelbrot set — infinite complexity from `z = z² + c`. The complexity is emergent, not learned. You don't need a neural network to generate the Mandelbrot set; you need the right rule.
>
> Markets are similar. The apparent complexity of price action emerges from recursive application of simple structural rules: swings form, extend to targets, or fail. The rules are **finite and knowable**. What varies is the stochastic path through the rule space.
>
> A grammar with 20 production rules, each with interpretable probabilities, can generate infinite variety. Adding more rules increases expressiveness linearly. Adding more data to a neural network increases... overfitting risk.
>
> **The grammar scales by adding rules. The neural network scales by adding data you don't have.**"

---

#### Robert Shiller (Revisited)

> "Market psychology doesn't change. The fear at the 0.618 retracement is the same fear traders felt in 1929, 1987, 2008, and 2020. The greed at 2.0 extension is timeless.
>
> This is why interpretable rules are **more robust across regimes** than learned patterns. A transformer trained on 2015-2020 data learns the specific statistical signature of that period — the low volatility, the buy-the-dip muscle memory. It will fail spectacularly in a 2022-style regime.
>
> An interpretable grammar doesn't have this problem. The rule 'pullbacks to 0.618 have X% chance of holding' can be parameterized differently for different regimes. You can **adjust the probabilities without changing the structure**.
>
> More importantly: **you can explain to a human why the generator did what it did.** 'The simulated price broke 0.618 support because the probability of failure at that level was 40%.' Try explaining that from a transformer's attention weights."

---

#### Fischer Black (Revisited)

> "Let me be blunt: **with small data, you cannot distinguish signal from noise statistically.**
>
> If you train a neural network on 1000 swing patterns, it will find patterns. Some will be real (Fib levels matter), and some will be spurious (some artifact of ES futures in October 2023). You cannot tell which is which without more data.
>
> But if you encode domain knowledge as explicit rules — 'the 0.382 retracement has different statistics than the 0.618 retracement' — you're not learning this from data. You're asserting it based on market theory. The data only estimates the parameters of rules you already believe.
>
> This is **dramatically more data-efficient**. Instead of learning that Fib levels matter (millions of examples needed), you assert it and only estimate how much (hundreds of examples sufficient).
>
> **Encode structure as rules. Estimate probabilities from data. Never try to learn structure from small samples.**"

---

#### Andrej Karpathy (Revisited)

> "I'll be honest: my earlier recommendation assumed you'd have abundant training data. With limited data, the calculus changes entirely.
>
> Transformers are **interpolators**. They learn to map inputs to outputs within the distribution of training data. Outside that distribution, they fail unpredictably. With small data, your training distribution is a tiny island; the ocean of market behavior is vast and uncharted.
>
> A grammar is an **extrapolator**. It encodes structural beliefs that apply everywhere, not just where you have data. If your rules are correct, the grammar generalizes by construction.
>
> Here's my revised take: **use the grammar as the generator, and use a small neural network only for learning the probability parameters — not the structure itself.** This is like learning the 'temperature' of a distribution, not the distribution itself.
>
> Even better: don't use neural networks at all until you have 10x more data. Tune the grammar probabilities by hand, using expert knowledge. **Human judgment is a stronger prior than any pretrained model when n is small.**"

---

#### Ilya Sutskever (Revisited)

> "The question is really about inductive bias. Every model has assumptions built in. The transformer's assumption is: 'patterns in sequences are learnable from data.' The grammar's assumption is: 'markets follow Fib-based structural rules.'
>
> **The stronger your prior, the less data you need.** The grammar has a stronger, more specific prior. Therefore it's more appropriate for small-data regimes.
>
> Here's a thought experiment: Imagine two generators trained on identical small datasets.
>
> Generator A (transformer): Produces realistic-looking output on test data from the same period. Produces garbage on out-of-sample data from a different regime.
>
> Generator B (grammar): Produces somewhat stylized output on test data — it doesn't capture every quirk. But on out-of-sample data, it produces structurally valid sequences because the rules still apply.
>
> **Which is better? The one that generalizes.** With small data, that's always the more constrained model."

---

#### Will Wright (Revisited)

> "SimCity doesn't learn from data. It has interpretable rules: 'residential zones need nearby commercial,' 'crime increases without police,' 'traffic follows capacity.'
>
> These rules are **debuggable**. When the simulation produces unrealistic behavior, I can trace it to a specific rule and fix it. I can explain to players why their city is failing.
>
> Now imagine SimCity trained on satellite imagery of real cities with a neural network. It might produce realistic-looking cities, but when something goes wrong, you're helpless. Why did the industrial zone appear in the residential area? Who knows — it's in the weights somewhere.
>
> **Games need transparent causality.** If your market simulator is going to be used for human learning, the human needs to understand why the market did what it did. 'The market rallied because the 0.618 held and the structure was still intact' is a lesson. 'The market rallied because tensor 847 had high activation' is noise.
>
> Build a game, not an oracle."

---

#### Sid Meier (Revisited)

> "Civilization has been through 6 major versions. Each time, we start with interpretable rules: 'cities grow based on food,' 'military units have attack and defense values.'
>
> We **never** replaced these with neural networks, even though we could. Why? Because **the game designer needs to balance the game.** If I can't understand why cavalry beats archers, I can't balance cavalry.
>
> Your market simulator needs balance too. If the generator produces too many invalidations, you need to adjust that. With interpretable rules, you change the invalidation probability. With a neural network, you... retrain on more data you don't have?
>
> **Interpretable rules are maintainable.** They're debuggable. They're explainable. They're evolvable. A neural network is frozen in the shape of its training data.
>
> Build the rule system first. Make it complete and balanced. Only add learning later, and only for the aspects that genuinely can't be specified upfront."

---

#### New Expert: George Box (Statistician, Empirical Model-Building)

> "All models are wrong, but some are useful. The question is: **which kind of wrong is more useful?**
>
> A neural network is wrong in ways you cannot characterize. Somewhere in its millions of parameters is a wrong assumption, and you'll never find it.
>
> A grammar is wrong in ways you **can** characterize. Rule 47 says 'probability of 2.0 completion after 1.618 is 60%.' You can test this against data. You can ask a trader if it's reasonable. You can adjust it.
>
> **Explicit wrongness is fixable. Implicit wrongness is permanent.**
>
> With limited data, your model will be wrong. The question is whether you want to be wrong explicitly (and improvably) or wrong mysteriously (and unfixably).
>
> Choose the grammar."

---

#### New Expert: Richard Feynman (Physicist, "What I cannot create, I do not understand")

> "If you want to understand something, build it from first principles. If you cannot build it from first principles, you do not understand it.
>
> A neural network trained on market data does not understand markets. It has compressed statistical regularities into weights. When the regularities change, the network is blind.
>
> A grammar built from market structure **is** understanding. Each rule is a hypothesis: 'markets pull back to Fib levels,' 'completions trigger reversals.' You can test each hypothesis. You can argue about it. You can be wrong in specific, identifiable ways.
>
> **The generator should teach you about markets as you build it.** Every rule you add should deepen your understanding. If adding a rule doesn't require understanding — if you're just training weights — you're not learning, you're curve-fitting.
>
> Build understanding, not mimicry."

---

## 4. Implications Synthesis

*Distilling expert insights into design constraints:*

### The Atomic Unit

**Consensus**: A swing with its completion state is the atomic unit. Not a bar, not a price point — a structural move from one level to another.

**Refined definition**: A game piece is a **swing tuple**:
```
(direction, magnitude_class, completion_state, parent_position)
```

Where:
- `direction`: BULL or BEAR
- `magnitude_class`: Fib-relative to parent (0.382, 0.5, 0.618, 1.0, etc.)
- `completion_state`: FORMING | 0.382 | 0.5 | 0.618 | 1.0 | 1.382 | 1.5 | 1.618 | 2.0 | INVALIDATED
- `parent_position`: Where this swing sits in its parent (0.382, 0.5, 0.618, etc.)

### Magnitude Encoding

**Consensus**: Relative, not absolute. All magnitudes are expressed as Fib ratios of containing structure.

**Implication**: A "0.618 swing" means a swing whose size is 0.618× the parent swing. This is scale-invariant and meaningful.

### Parent-Child Relationships

**Consensus**: Hierarchical, with context flowing downward. A swing inherits constraints from its parent.

**Implication**: The representation is a tree, not a flat sequence. Generation is recursive descent.

### Vocabulary Size

**Consensus**: Small is better. 256-512 distinct states are likely sufficient.

**Calculation**:
- 2 directions
- 8 magnitude classes (Fib levels)
- 8 completion states
- 8 parent positions
= 2 × 8 × 8 × 8 = 1024 theoretical maximum

With aggressive coarsening (3 magnitude buckets, 4 completion states, 4 parent positions):
= 2 × 3 × 4 × 4 = 96 practical states

This is very tractable.

### Temporal Dependencies

**Consensus**: Handle via attention/context, not token explosion. The model learns dependencies; the tokens don't encode them.

### Generation Strategy

**Consensus**: Generate events, not prices. Render to OHLC as a final step.

**Implication**: The generative model outputs structural event sequences. A separate renderer converts events to price bars.

### Interpretability Imperative (Added)

**Consensus**: Unanimous. With limited data, interpretability is not optional — it's the primary constraint.

**Key insights from revisited consultation**:

| Expert | Core Argument |
|--------|---------------|
| Shannon | Can't estimate many parameters from small samples; interpretable rules have meaningful, testable parameters |
| Mandelbrot | Complexity emerges from simple rules; grammar scales by adding rules, not data |
| Shiller | Psychology is timeless; rules generalize across regimes, learned patterns don't |
| Black | Encode structure as rules, estimate only probabilities; data-efficient |
| Karpathy | Transformers interpolate; grammars extrapolate; small data needs extrapolation |
| Sutskever | Stronger priors need less data; grammar has stronger prior than transformer |
| Wright | Games need transparent causality for learning; build a game, not an oracle |
| Meier | Interpretable rules are maintainable, debuggable, evolvable |
| Box | Explicit wrongness is fixable; implicit wrongness is permanent |
| Feynman | Build understanding, not mimicry; each rule is a testable hypothesis |

**Implication**: Neural networks are off the table for structure. Grammar-first. Probabilities can be hand-tuned initially, estimated from data later. Learning is a future enhancement, not the core architecture.

---

## 5. High-Level Options

Based on expert synthesis, three distinct approaches emerge:

---

### Option A: Token Vocabulary with Transformer

**Philosophy**: Treat swing sequences like language. Define a vocabulary of swing tokens. Train a transformer to predict the next token.

**Representation**:
```
Token = (direction, magnitude_bucket, completion_state)
Sequence = [Token_1, Token_2, ..., Token_n]
```

**Vocabulary**: ~100-200 tokens (coarsened combinations)

**Generation**: Autoregressive transformer predicts next token given history.

**Scale handling**: Separate token streams per scale, with cross-attention.

**Pros**:
- Proven architecture (GPT-style)
- Captures long-range dependencies
- Easy to train on real data

**Cons**:
- Flat sequence loses hierarchical structure
- Cross-scale constraints hard to enforce
- May generate impossible configurations

---

### Option B: Recursive Grammar (L-System)

**Philosophy**: Define a grammar where swings are rewritten into smaller swings. Generation is recursive expansion.

**Representation**:
```
Grammar rules:
  SWING → APPROACH CLIMAX RESOLUTION
  APPROACH → swing_to_level(0.382 | 0.5 | 0.618)
  CLIMAX → swing_to_level(1.0)
  RESOLUTION → swing_to_level(1.382 | 1.5 | 1.618 | 2.0) | INVALIDATION

  swing_to_level(X) → [SWING]* if current_scale > min_scale else terminal
```

**Generation**: Start with XL swing, recursively expand down to S scale.

**Scale handling**: Built into recursion depth. Natural hierarchical structure.

**Pros**:
- Self-similarity is architectural
- Hierarchical constraints are natural
- Interpretable rules

**Cons**:
- Stochastic grammar tuning is tricky
- May produce overly regular patterns
- Hard to capture statistical anomalies

---

### Option C: Hierarchical State Machine

**Philosophy**: Each scale is a state machine. Parent machine constrains child machine transitions.

**Representation**:
```
State = (scale, completion_level, parent_constraint)
Transitions = probability table: P(next_state | current_state, parent_state)
```

**Generation**: Run state machines in parallel, with parent-to-child message passing.

**Scale handling**: One machine per scale. Parent states modulate child transition probabilities.

**Pros**:
- Explicit probabilistic model
- Easy to inject domain knowledge
- Constraints naturally enforced

**Cons**:
- Combinatorial state space at multiple scales
- Transition tables may not capture complex dependencies
- Markov assumption may be too limiting

---

## 6. Detailed Specifications

### Option A: Token Vocabulary with Transformer

#### Token Schema

```python
@dataclass
class SwingToken:
    direction: Literal["BULL", "BEAR"]
    magnitude: Literal["SHALLOW", "MEDIUM", "DEEP"]  # Fib buckets
    completion: Literal["FORMING", "ACTIVE", "EXTENDED", "RESOLVED"]

    def to_id(self) -> int:
        """Convert to vocabulary index (0-23)."""
        d = 0 if self.direction == "BULL" else 1
        m = {"SHALLOW": 0, "MEDIUM": 1, "DEEP": 2}[self.magnitude]
        c = {"FORMING": 0, "ACTIVE": 1, "EXTENDED": 2, "RESOLVED": 3}[self.completion]
        return d * 12 + m * 4 + c
```

**Magnitude buckets**:
- SHALLOW: 0.236-0.382 of parent
- MEDIUM: 0.382-0.618 of parent
- DEEP: 0.618-1.0+ of parent

**Completion buckets**:
- FORMING: 0-0.382 of own range
- ACTIVE: 0.382-1.0 of own range
- EXTENDED: 1.0-1.618 of own range
- RESOLVED: 1.618+ or invalidated

#### Multi-Scale Handling

Four parallel token streams (XL, L, M, S). Cross-attention between streams.

```
XL stream: [XL_1, XL_2, ...]
L stream:  [L_1, L_2, L_3, L_4, ...]  (more tokens, faster timescale)
M stream:  [M_1, ..., M_n]
S stream:  [S_1, ..., S_m]

Cross-attention: S tokens attend to M, L, XL context
                 M tokens attend to L, XL context
                 etc.
```

#### Generation Algorithm

```python
def generate_sequence(context: MarketContext, n_steps: int) -> List[SwingToken]:
    """Autoregressive generation at all scales."""
    streams = {scale: [] for scale in ["XL", "L", "M", "S"]}

    for step in range(n_steps):
        for scale in ["XL", "L", "M", "S"]:
            # Get parent context
            parent_scale = get_parent_scale(scale)
            parent_tokens = streams.get(parent_scale, [])

            # Predict next token
            next_token = model.predict(
                history=streams[scale],
                parent_context=parent_tokens,
                scale=scale
            )

            streams[scale].append(next_token)

            # Check if we should advance parent
            if should_advance_parent(streams, scale):
                continue  # Parent will advance on its own

    return interleave_streams(streams)
```

#### OHLC Reconstruction

```python
def render_to_ohlc(tokens: List[SwingToken], base_price: float, scale_sizes: Dict[str, float]) -> pd.DataFrame:
    """Convert token sequence to OHLC bars."""
    bars = []
    current_price = base_price

    for token in tokens:
        # Determine swing size from magnitude and scale
        swing_size = scale_sizes[token.scale] * magnitude_to_ratio(token.magnitude)

        # Determine price trajectory
        if token.direction == "BULL":
            swing_low = current_price
            swing_high = current_price + swing_size
        else:
            swing_high = current_price
            swing_low = current_price - swing_size

        # Generate bars within swing
        swing_bars = generate_swing_bars(
            swing_low, swing_high, token.direction, token.completion
        )
        bars.extend(swing_bars)

        # Update current price based on completion
        current_price = compute_exit_price(swing_low, swing_high, token.completion)

    return pd.DataFrame(bars, columns=["open", "high", "low", "close"])
```

---

### Option B: Recursive Grammar (L-System)

#### Grammar Definition

```python
# Terminal symbols
TERMINAL_UP = "↑"    # Single upward micro-move
TERMINAL_DOWN = "↓"  # Single downward micro-move

# Non-terminals
SWING_BULL = "SB"    # Bullish swing (H then L, setting up upward move)
SWING_BEAR = "SH"    # Bearish swing (L then H, setting up downward move)
APPROACH = "A"       # Move toward structure
CLIMAX = "C"         # Move to swing extreme
RESOLUTION = "R"     # Move to completion or invalidation

# Production rules with probabilities
RULES = {
    # A bullish swing is: approach to low, climax at low, then resolution upward
    "SB": [
        (0.4, ["A_down", "C_low", "R_up_1.618"]),
        (0.3, ["A_down", "C_low", "R_up_2.0"]),
        (0.2, ["A_down", "C_low", "R_up_1.382"]),
        (0.1, ["A_down", "C_low", "INVALIDATE"]),
    ],

    # Approach can be a sub-swing or terminal
    "A_down": [
        (0.6, [TERMINAL_DOWN]),  # Simple move
        (0.3, ["SH"]),            # Sub-swing (bear swing within bull approach)
        (0.1, ["SH", "SH"]),      # Two sub-swings
    ],

    # Resolution upward to various Fib levels
    "R_up_2.0": [
        (0.5, [TERMINAL_UP, TERMINAL_UP]),  # Simple completion
        (0.3, ["SB", TERMINAL_UP]),          # Sub-swing then completion
        (0.2, ["SB", "SB"]),                  # Multiple sub-swings
    ],

    # ... more rules for each non-terminal
}
```

#### Expansion Algorithm

```python
def expand(symbol: str, depth: int, max_depth: int) -> List[str]:
    """Recursively expand a symbol to terminal sequence."""
    if depth >= max_depth:
        # Force terminal
        return [TERMINAL_UP if "up" in symbol.lower() or "bull" in symbol.lower()
                else TERMINAL_DOWN]

    if symbol in [TERMINAL_UP, TERMINAL_DOWN]:
        return [symbol]

    # Choose a production rule stochastically
    productions = RULES.get(symbol, [])
    if not productions:
        return [symbol]  # Unknown symbol, keep as-is

    probs = [p[0] for p in productions]
    expansions = [p[1] for p in productions]

    chosen = random.choices(expansions, weights=probs)[0]

    # Recursively expand each symbol in chosen production
    result = []
    for s in chosen:
        result.extend(expand(s, depth + 1, max_depth))

    return result
```

#### Scale Mapping

Recursion depth maps to scale:
- Depth 0-1: XL
- Depth 2-3: L
- Depth 4-5: M
- Depth 6+: S

```python
def depth_to_scale(depth: int) -> str:
    if depth <= 1: return "XL"
    if depth <= 3: return "L"
    if depth <= 5: return "M"
    return "S"
```

#### OHLC Reconstruction

Terminal symbols become micro-moves. Aggregate based on scale.

```python
def terminals_to_ohlc(terminals: List[str], base_price: float, tick_size: float) -> pd.DataFrame:
    """Convert terminal sequence to OHLC."""
    bars = []
    price = base_price

    for t in terminals:
        delta = tick_size if t == TERMINAL_UP else -tick_size

        open_price = price
        close_price = price + delta
        high_price = max(open_price, close_price)
        low_price = min(open_price, close_price)

        bars.append({
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price
        })

        price = close_price

    return pd.DataFrame(bars)
```

---

### Option C: Hierarchical State Machine

#### State Definition

```python
@dataclass
class ScaleState:
    scale: str  # "XL", "L", "M", "S"
    direction: str  # "BULL", "BEAR"
    completion_level: float  # 0.0 to 2.0+, or -1 for invalidated
    bars_in_state: int  # Duration

# Full market state is composition of scale states
@dataclass
class MarketState:
    xl_state: ScaleState
    l_state: ScaleState
    m_state: ScaleState
    s_state: ScaleState
```

#### Transition Tables

```python
# Transition probabilities conditioned on parent state
# P(child_next | child_current, parent_current)

TRANSITION_PROBS = {
    # When parent is in early stage (0-0.618), child has room to move
    ("BULL", "early"): {
        (0.0, 0.382): 0.4,
        (0.382, 0.618): 0.3,
        (0.618, 1.0): 0.2,
        (1.0, 1.382): 0.08,
        "invalidate": 0.02,
    },

    # When parent is extended (1.382-2.0), child moves tend to resolve
    ("BULL", "extended"): {
        (0.0, 0.382): 0.1,
        (0.382, 0.618): 0.2,
        (0.618, 1.0): 0.2,
        (1.0, 1.382): 0.15,
        (1.382, 1.618): 0.15,
        (1.618, 2.0): 0.15,
        "invalidate": 0.05,
    },

    # When parent has just invalidated, child structure resets
    ("invalidated", None): {
        "new_swing": 1.0,  # Force new swing formation
    },

    # ... many more conditions
}
```

#### Generation Algorithm

```python
def step_market(state: MarketState) -> MarketState:
    """Advance market state by one step."""
    new_state = copy(state)

    # Cascade from XL down to S
    for scale in ["XL", "L", "M", "S"]:
        current = getattr(state, f"{scale.lower()}_state")
        parent = get_parent_state(state, scale)

        # Get transition probabilities
        parent_phase = get_phase(parent) if parent else "none"
        probs = TRANSITION_PROBS.get((current.direction, parent_phase), DEFAULT_PROBS)

        # Sample next state
        next_level = sample_transition(probs)

        if next_level == "invalidate":
            new_current = ScaleState(scale, current.direction, -1, 0)
        elif next_level == "new_swing":
            new_dir = "BULL" if current.direction == "BEAR" else "BEAR"
            new_current = ScaleState(scale, new_dir, 0.0, 0)
        else:
            new_current = ScaleState(
                scale, current.direction,
                sample_within_range(next_level),
                current.bars_in_state + 1
            )

        setattr(new_state, f"{scale.lower()}_state", new_current)

    return new_state
```

#### OHLC Reconstruction

```python
def state_to_bar(prev_state: MarketState, curr_state: MarketState, prev_price: float) -> dict:
    """Convert state transition to OHLC bar."""
    # Use S-scale (finest) to determine bar movement
    s_prev = prev_state.s_state
    s_curr = curr_state.s_state

    # Compute price change based on completion level change
    level_delta = s_curr.completion_level - s_prev.completion_level

    # Get swing size from parent context
    swing_size = get_swing_size_from_parent(prev_state)
    price_delta = level_delta * swing_size

    if s_curr.direction == "BULL":
        close = prev_price + price_delta
    else:
        close = prev_price - price_delta

    # Estimate OHLC from price trajectory
    return estimate_ohlc(prev_price, close, s_curr.direction)
```

---

## 7. Tradeoff Analysis

*Channeling Herbert Simon on bounded rationality and satisficing:*

> "Decision-makers can rarely optimize; they satisfice — selecting solutions that are 'good enough' given constraints. The question is not 'which approach is best?' but 'which approach is good enough for our purposes with acceptable costs?'"

### Evaluation Criteria (Revised Post-Interpretability Discussion)

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Interpretability** | **Critical** | Can humans understand, debug, and tune? **(Now primary constraint)** |
| Structural fidelity | High | Must preserve Fib relationships, completion logic |
| Self-similarity | High | Same mechanism at all scales |
| Debuggability | High | Can you trace why the generator produced specific output? |
| Data efficiency | High | Can it work with limited training examples? |
| Scalability (rules) | Medium | Can you add new rules without retraining? |
| Generation quality | Medium | Does output look like real markets? (downgraded: can iterate) |
| Learnability | Low | Can a model learn patterns? **(Deprioritized: not enough data)** |

### Option A: Token Vocabulary (Transformer)

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Interpretability** | 2/10 | Black box; cannot explain why a token was generated |
| Structural fidelity | 6/10 | Can encode but doesn't enforce; may generate impossible states |
| Self-similarity | 7/10 | Same vocabulary at all scales |
| Debuggability | 2/10 | Attention weights are not explanations |
| Data efficiency | 3/10 | Needs abundant data to avoid overfitting |
| Scalability (rules) | 3/10 | Adding rules requires retraining |
| Generation quality | 8/10 | With enough data, produces realistic output |
| Learnability | 9/10 | Transformers are well-understood |

**Simon's revised assessment**: "This approach is disqualified by the interpretability constraint. With limited data, it will overfit. When it fails, you cannot diagnose why. The high learnability score is irrelevant when you don't have data to learn from."

**Verdict**: ❌ Not viable for current phase.

### Option B: Recursive Grammar (L-System)

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Interpretability** | 10/10 | Every rule is readable; every generation is traceable |
| Structural fidelity | 9/10 | Rules encode structure explicitly; impossible states are ungrammatical |
| Self-similarity | 10/10 | Recursion IS self-similarity; architectural guarantee |
| Debuggability | 10/10 | Can trace exact rule sequence that produced any output |
| Data efficiency | 9/10 | Needs data only for probability estimation, not structure |
| Scalability (rules) | 10/10 | Add rules incrementally; no retraining |
| Generation quality | 6/10 | May be too regular initially; improves as rules refine |
| Learnability | 4/10 | Hard to learn grammar from data (but we're not doing that) |

**Simon's revised assessment**: "This approach satisfices on every criterion that matters under the interpretability constraint. The lower generation quality is acceptable because you can iterate: observe unrealistic output, trace to rule, fix rule, regenerate. This is engineering, not alchemy."

**Verdict**: ✅ **Primary recommendation.**

### Option C: Hierarchical State Machine

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Interpretability** | 8/10 | Probabilities are inspectable; states are nameable |
| Structural fidelity | 8/10 | States and transitions encode structure |
| Self-similarity | 8/10 | Same machine at each scale |
| Debuggability | 7/10 | Can trace state transitions, but less elegant than grammar |
| Data efficiency | 7/10 | Transition tables need more parameters than grammar |
| Scalability (rules) | 6/10 | Adding states is possible but increases combinatorics |
| Generation quality | 7/10 | Reasonable, but Markov assumption limits realism |
| Learnability | 7/10 | Tables can be estimated from data |

**Simon's revised assessment**: "This is a viable alternative if the grammar proves too rigid. It trades some interpretability for flexibility. Consider as fallback if pure grammar produces output that's too mechanical."

**Verdict**: ⚠️ Viable fallback.

### Revised Summary Matrix (Weighted by Interpretability Priority)

| Option | Interpret (×3) | Structure | Self-Sim | Debug | Data-Eff | Scale | Quality | **Weighted Total** |
|--------|---------------|-----------|----------|-------|----------|-------|---------|-------------------|
| A: Tokens | 2×3=6 | 6 | 7 | 2 | 3 | 3 | 8 | **35** |
| B: Grammar | 10×3=30 | 9 | 10 | 10 | 9 | 10 | 6 | **84** |
| C: States | 8×3=24 | 8 | 8 | 7 | 7 | 6 | 7 | **67** |

**The grammar wins decisively when interpretability is weighted appropriately.**

---

## 8. Recommendation (Revised)

### Pure Grammar Approach: Interpretable Stochastic Rules

Given the interpretability imperative, we abandon the hybrid approach. **No neural networks.** The entire generator is a stochastic grammar with hand-tuned (later data-estimated) probabilities.

**Core idea**:
1. L-system grammar defines the *structure* of valid swing sequences
2. Each production rule has *interpretable probabilities* that can be tuned
3. Generation is recursive expansion with stochastic choices
4. Every output is *fully traceable* to the rule sequence that produced it

#### Architecture (Simplified)

```
┌─────────────────────────────────────────────────────────────┐
│                    STOCHASTIC GRAMMAR                        │
│                                                             │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │  Production     │────▶│  Probability    │               │
│  │  Rules          │     │  Tables         │               │
│  │  (structure)    │     │  (tunable)      │               │
│  └─────────────────┘     └─────────────────┘               │
│           │                      │                          │
│           └──────────┬───────────┘                          │
│                      ▼                                      │
│           ┌─────────────────┐                               │
│           │ Weighted Sample │                               │
│           │ & Expand        │                               │
│           └────────┬────────┘                               │
│                    │                                        │
│                    ▼                                        │
│              (recurse until terminal)                       │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    OHLC RENDERER                             │
│  Terminal sequence → Bar sequence                           │
│  (deterministic, interpretable mapping)                     │
└─────────────────────────────────────────────────────────────┘
```

#### The Game Piece (Refined)

```python
@dataclass
class SwingPiece:
    """The atomic game piece — fully interpretable."""

    # Structural identity
    direction: Literal["BULL", "BEAR"]
    magnitude_fib: float  # 0.236, 0.382, 0.5, 0.618, 0.786, 1.0 (relative to parent)

    # Completion state
    completion_fib: float  # 0.382, 0.618, 1.0, 1.382, 1.618, 2.0, or -1 (invalid)

    # Context
    parent_position_fib: float  # Where in parent this swing sits
    scale: Literal["XL", "L", "M", "S"]

    # Traceability
    rule_path: List[str]  # Sequence of rules that produced this piece

    def explain(self) -> str:
        """Human-readable explanation of this piece."""
        return (
            f"{self.direction} swing at {self.scale} scale, "
            f"size={self.magnitude_fib}x parent, "
            f"completed to {self.completion_fib}, "
            f"at parent position {self.parent_position_fib}. "
            f"Produced by: {' → '.join(self.rule_path)}"
        )
```

#### Grammar Rules (Explicit and Interpretable)

```python
# Each rule is named, documented, and has interpretable probabilities
GRAMMAR = {
    # ===== SWING FORMATION =====
    "SWING_BULL": Rule(
        name="Bull Swing Formation",
        doc="A bullish reference swing: price drops (approach), finds low (climax), then rallies (resolution)",
        productions=[
            (0.35, ["APPROACH_DOWN", "CLIMAX_LOW", "RESOLUTION_UP_2.0"],
             "Full completion to 2x target"),
            (0.30, ["APPROACH_DOWN", "CLIMAX_LOW", "RESOLUTION_UP_1.618"],
             "Strong completion to golden extension"),
            (0.20, ["APPROACH_DOWN", "CLIMAX_LOW", "RESOLUTION_UP_1.382"],
             "Moderate completion to first extension"),
            (0.10, ["APPROACH_DOWN", "CLIMAX_LOW", "INVALIDATION"],
             "Failure: low gets taken out"),
            (0.05, ["APPROACH_DOWN", "CLIMAX_LOW", "RESOLUTION_UP_1.0"],
             "Weak: only reaches origin, stalls"),
        ]
    ),

    # ===== APPROACH PHASE =====
    "APPROACH_DOWN": Rule(
        name="Downward Approach",
        doc="Price moves down toward swing low. Can be simple or contain sub-swings.",
        productions=[
            (0.50, [TERMINAL_DOWN],
             "Simple drop: one directional move"),
            (0.30, ["SWING_BEAR_MINOR"],
             "Complex drop: contains a bearish sub-swing"),
            (0.15, [TERMINAL_DOWN, "SWING_BEAR_MINOR"],
             "Drop with failed bounce"),
            (0.05, ["SWING_BEAR_MINOR", "SWING_BEAR_MINOR"],
             "Choppy drop: multiple sub-swings"),
        ]
    ),

    # ===== RESOLUTION PHASE =====
    "RESOLUTION_UP_2.0": Rule(
        name="Resolution to 2x Extension",
        doc="Price rallies to full 2x completion. Can be impulsive or contain pullbacks.",
        productions=[
            (0.40, [TERMINAL_UP, TERMINAL_UP],
             "Impulsive: direct move to target"),
            (0.35, ["SWING_BULL_MINOR", TERMINAL_UP],
             "With pullback: consolidate then complete"),
            (0.20, ["SWING_BULL_MINOR", "SWING_BULL_MINOR"],
             "Grinding: multiple pullbacks on the way"),
            (0.05, [TERMINAL_UP, "SWING_BULL_MINOR", TERMINAL_UP],
             "Stair-step: up, pull back, complete"),
        ]
    ),

    # ===== CONTEXT-DEPENDENT RULES =====
    "RESOLUTION_AT_PARENT_1.618": Rule(
        name="Resolution when Parent at Golden Extension",
        doc="Behavior changes when parent swing is extended. Higher chance of failure.",
        productions=[
            (0.25, [TERMINAL_UP, TERMINAL_UP],
             "Push through despite exhaustion"),
            (0.35, ["SWING_BULL_MINOR", TERMINAL_UP],
             "Hesitant completion"),
            (0.30, ["SWING_BULL_MINOR", "INVALIDATION"],
             "Fail at parent resistance"),
            (0.10, ["INVALIDATION"],
             "Immediate rejection"),
        ]
    ),

    # ... many more rules, all explicit and documented
}
```

#### The Probability Table (The Tunable Part)

```python
# Separate structure from probabilities for easy tuning
PROBABILITY_TABLE = {
    # Rule name: [prob1, prob2, prob3, ...]
    "SWING_BULL": [0.35, 0.30, 0.20, 0.10, 0.05],
    "APPROACH_DOWN": [0.50, 0.30, 0.15, 0.05],
    "RESOLUTION_UP_2.0": [0.40, 0.35, 0.20, 0.05],
    "RESOLUTION_AT_PARENT_1.618": [0.25, 0.35, 0.30, 0.10],
    # ...
}

def update_probability(rule_name: str, production_idx: int, new_prob: float):
    """
    Adjust a single probability. Renormalizes automatically.
    This is how we tune the grammar based on observation.
    """
    probs = PROBABILITY_TABLE[rule_name]
    probs[production_idx] = new_prob
    total = sum(probs)
    PROBABILITY_TABLE[rule_name] = [p / total for p in probs]
```

#### Generation with Full Traceability

```python
def generate_swing(rule_name: str, context: Context, depth: int = 0) -> Tuple[List[str], List[str]]:
    """
    Generate a swing sequence from a grammar rule.

    Returns:
        terminals: List of terminal symbols (for OHLC rendering)
        trace: List of rule applications (for explainability)
    """
    if depth > MAX_DEPTH:
        # Force termination at finest scale
        return [TERMINAL_UP if "BULL" in rule_name else TERMINAL_DOWN], [f"FORCE_TERMINAL({rule_name})"]

    if rule_name in [TERMINAL_UP, TERMINAL_DOWN]:
        return [rule_name], [rule_name]

    rule = GRAMMAR[rule_name]
    probs = get_context_adjusted_probs(rule_name, context)

    # Sample a production
    production_idx = random.choices(range(len(rule.productions)), weights=probs)[0]
    _, symbols, explanation = rule.productions[production_idx]

    trace = [f"{rule_name}[{production_idx}]: {explanation}"]
    terminals = []

    # Recursively expand
    for symbol in symbols:
        sub_terminals, sub_trace = generate_swing(symbol, context.descend(), depth + 1)
        terminals.extend(sub_terminals)
        trace.extend(["  " + t for t in sub_trace])  # Indent for readability

    return terminals, trace

def explain_generation(trace: List[str]) -> str:
    """Convert trace to human-readable explanation."""
    return "\n".join(trace)
```

#### Context-Dependent Probability Adjustment

```python
def get_context_adjusted_probs(rule_name: str, context: Context) -> List[float]:
    """
    Adjust rule probabilities based on market context.
    All adjustments are explicit and interpretable.
    """
    base_probs = PROBABILITY_TABLE[rule_name].copy()

    # Rule: At parent 1.618+, higher failure probability
    if context.parent_completion >= 1.618 and "RESOLUTION" in rule_name:
        failure_idx = find_failure_production(rule_name)
        if failure_idx is not None:
            base_probs[failure_idx] *= 1.5  # 50% more likely to fail

    # Rule: After 3+ consecutive failures, mean reversion more likely
    if context.consecutive_failures >= 3:
        completion_idx = find_completion_production(rule_name)
        if completion_idx is not None:
            base_probs[completion_idx] *= 1.3  # 30% more likely to complete

    # Rule: News event biases toward extremes
    if context.pending_news:
        extreme_idxs = find_extreme_productions(rule_name)
        for idx in extreme_idxs:
            base_probs[idx] *= (1 + context.news_magnitude)

    # Renormalize
    total = sum(base_probs)
    return [p / total for p in base_probs]
```

#### Why This Works Better Than Hybrid

1. **100% Interpretable**: Every generation can be traced to specific rule applications. "Why did price fail at 1.618?" → "Rule RESOLUTION_AT_PARENT_1.618 chose production 2 (Fail at parent resistance) with 30% probability."

2. **No Overfitting Risk**: There are no learned weights. The grammar structure encodes domain knowledge. Only ~50-100 probability parameters exist, each with clear meaning.

3. **Incrementally Improvable**: When output looks wrong:
   - Generate with tracing
   - Find the offending rule
   - Adjust its probabilities
   - Regenerate and verify

   This is **engineering**, not training.

4. **Scales Infinitely**: Add new rules for new market behaviors. Each rule is independent. No retraining, no data requirements.

5. **Regime Adaptable**: Different probability tables for different regimes (low vol, high vol, trending, ranging). Switch tables, same grammar.

6. **Debuggable**: When the generator produces unrealistic output, you can trace exactly why and fix it.

#### Implementation Phases (Revised)

1. **Phase 1: Core Grammar** (weeks 1-2)
   - Implement 10-15 core production rules based on product north star
   - Uniform probabilities initially
   - OHLC renderer from terminal sequences
   - Visual inspection of output

2. **Phase 2: Probability Tuning** (weeks 3-4)
   - Hand-tune probabilities based on visual inspection
   - Add tracing and explanation features
   - Compare generated vs. real charts qualitatively

3. **Phase 3: Context Rules** (weeks 5-6)
   - Add context-dependent probability adjustments
   - Parent swing influence on child behavior
   - Consecutive failure / success patterns

4. **Phase 4: Multi-Scale Coordination** (weeks 7-8)
   - Coordinate XL → L → M → S generation
   - Parent constraints flow to children
   - Full recursive structure

5. **Phase 5: Statistical Validation** (later)
   - Measure distribution statistics (fat tails, autocorrelation)
   - Estimate probability parameters from real swing data
   - Refine rules based on quantitative feedback

6. **Phase 6: News Overlay** (later)
   - Add trigger injection points
   - Model impact on probability adjustments
   - Validate against event-driven price action

### Future: When to Consider Neural Networks

Neural networks may be appropriate **later**, under these conditions:

1. **Abundant data**: 100,000+ labeled swing sequences across multiple regimes
2. **Grammar is complete**: The rule structure captures all known market behaviors
3. **Specific gap**: A particular aspect (e.g., volatility clustering) that the grammar handles poorly
4. **Contained scope**: Use neural network only for that specific gap, not the whole system

Even then, prefer **small, interpretable models** (e.g., a small MLP to estimate one probability parameter) over large black boxes.

---

## Next Steps

1. **Define the core grammar rules**: Map the product north star rules to explicit production rules. Start with swing formation, approach, climax, resolution phases.

2. **Prototype the generator**: Implement stochastic grammar expansion with uniform probabilities. Generate terminal sequences.

3. **Build the OHLC renderer**: Convert terminal sequences to price bars. Validate that output looks like charts.

4. **Add traceability**: Every generated sequence should have an explanation. Test that traces are readable and useful.

5. **Tune probabilities by inspection**: Generate samples, compare to real charts, adjust rule probabilities. Iterate.

6. **Define "realistic" qualitatively first**: Before statistical tests, establish visual benchmarks. What does "good" output look like?

---

## Appendix: Expert Panel

| Expert | Field | Key Contribution |
|--------|-------|------------------|
| Claude Shannon | Information Theory | Entropy-based encoding; meaningful parameters |
| Benoit Mandelbrot | Fractal Geometry | Self-similarity; recursive composition |
| Robert Shiller | Behavioral Economics | Level semantics; regime robustness |
| Fischer Black | Quantitative Finance | Noise vs. signal; data efficiency |
| Andrej Karpathy | Deep Learning | Interpolation vs. extrapolation |
| Ilya Sutskever | Sequence Modeling | Inductive bias; prior strength |
| Will Wright | Game Design | Transparent causality; emergent complexity |
| Sid Meier | Strategy Games | Maintainable rules; balance |
| George Box | Statistics | Explicit wrongness is fixable |
| Richard Feynman | Physics | Build understanding, not mimicry |

---

*Document version: 2.0*
*Created: 2025-12-15*
*Revised: 2025-12-15 — Added interpretability imperative; revised recommendation to pure grammar approach*
