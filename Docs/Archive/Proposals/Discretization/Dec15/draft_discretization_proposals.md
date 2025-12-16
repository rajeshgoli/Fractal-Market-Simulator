# Discretization Proposal Drafts (Consolidated Reference)

*This document concatenates all draft proposals for reference. Each section preserves the original draft content.*

---

# DRAFT: discretization_approaches_c1

*Source: Docs/Proposals/Drafts/discretization_approaches_c1.md*

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

---

# DRAFT: discretization_approaches_c2

*Source: Docs/Proposals/Drafts/discretization_approaches_c2.md*

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

---

# DRAFT: discretization_approaches_c3

*Source: Docs/Proposals/Drafts/discretization_approaches_c3.md*

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

---

# DRAFT: discretization_approaches_cl1

*Source: Docs/Proposals/Drafts/discretization_approaches_cl1.md*

# Discretization of OHLC into Swing-Level Game Pieces

**Status:** Synthesis Proposal (S1)
**Date:** December 15, 2025
**Synthesized from:** C1, C2, C3, O1, O2, G1 drafts

---

## Executive Summary

This document synthesizes six competing proposals for discretizing continuous OHLC data into discrete "game pieces" suitable for recursive market generation. After analysis, I recommend a **Fibonacci Band State Machine with Structural Event Overlay**—a hybrid that combines the interpretability and data-efficiency of level-based Markov models with explicit mechanisms for the North Star's second-order rules (frustration, exhaustion, measured moves).

The core insight driving this recommendation: **interpretability is not a luxury—it is the constraint that makes this project possible given limited data.** Every draft converges on this conclusion. Neural networks are off the table. The question is which explicit, rule-based architecture best balances fidelity to the North Star, debuggability, and implementation tractability.

---

## 1. Problem Statement

### The Challenge

The Fractal Market Simulator must generate 1-minute OHLC data indistinguishable from real markets. The Product North Star establishes that all price movement is recursive: every large move decomposes into smaller moves obeying identical structural rules. We can already *detect* these structures; we cannot yet *generate* them.

The gap is a discrete representation—"game pieces"—that:
1. Can be sequenced by a generative model
2. Preserves Fibonacci relationships, completion semantics, and scale hierarchy
3. Enables reconstruction back to OHLC
4. Is learnable from limited data (10-15 expert annotation sessions)
5. Is fully interpretable (every generated bar traceable to explicit decisions)

### Success Criteria

| Criterion | Measure | Threshold |
|-----------|---------|-----------|
| **Interpretability** | Every state transition maps to a single English sentence | 100% |
| **Structural Fidelity** | Completion (2x), invalidation (-0.1), Fib levels enforced | No violations |
| **Self-Similarity** | Same rules apply at S, M, L, XL scales | Verified by inspection |
| **Learnability** | Transition parameters estimable from available data | <100 samples per parameter |
| **Reversibility** | Game record → OHLC → Game record round-trip | Structural events preserved |
| **Visual Realism** | Domain expert cannot reliably distinguish from real data | >70% confusion rate |

### What We Are NOT Solving

- Bar-by-bar tick generation (wrong granularity—structure is lost)
- News event modeling (assume this layer exists; we define injection points)
- Long-term convergence (decades-scale; out of scope per North Star)
- Sub-swing microstructure (belongs in renderer, not game state)

---

## 2. The Discrete Representation

### 2.1 State: What the Generator Knows

The minimal sufficient state for predicting the next structural move is:

```
GameState:
  scales: Dict[Scale, ScaleState]  # XL, L, M, S
  global_bar: int                  # Current time position
  news_context: Optional[NewsModifier]

ScaleState:
  frame: ReferenceFrame            # The active swing defining the Fib grid
  band: FibBand                    # Current position on that grid (e.g., 0.618–1.0)
  dwell_bars: int                  # Time in current band
  impulse: float                   # Recent momentum (distance/bars EMA)

  # Second-order rule state
  attempts: Dict[Level, int]       # Failed tests at key levels
  frustration: Optional[Level]     # Active frustration (triggers symmetric retrace)
  exhaustion: bool                 # Post-completion state (mandated pullback)
  target_pressure: float           # Stacked targets density (too-many-targets rule)

ReferenceFrame:
  anchor0: Decimal                 # Defended pivot (low for bull, high for bear)
  anchor1: Decimal                 # Opposite pivot
  direction: Direction             # BULL or BEAR

  def ratio(self, price) -> float:
    return (price - self.anchor0) / (self.anchor1 - self.anchor0)

  def price(self, ratio) -> Decimal:
    return self.anchor0 + ratio * (self.anchor1 - self.anchor0)
```

**Key Design Decisions:**

1. **Oriented Reference Frame**: Bull and bear swings share one coordinate system. Ratio increases in the expected move direction. Completion is `ratio >= 2.0`; STOP is `ratio <= -0.1`. This eliminates asymmetric handling throughout the codebase.

2. **Band-Based Position**: Price position is discretized into Fibonacci bands (0–0.382, 0.382–0.5, ..., 1.618–2.0, >2.0). Transitions occur between adjacent bands only (except logged tail events).

3. **Explicit Second-Order State**: Frustration counters, exhaustion flags, and target pressure are first-class state—not emergent side effects. This is essential for debugging and rule validation.

4. **Semi-Markov Timing**: Durations are explicit (`dwell_bars`), not implicit in transition counts. This captures decision-zone chop vs. liquidity-void snaps.

### 2.2 Action: What the Generator Chooses

```
Action = BandTransition | StructuralEvent | Reanchor

BandTransition:
  scale: Scale
  from_band: FibBand
  to_band: FibBand                 # Usually adjacent; logged exception for tail
  duration_bars: int
  impulse: float                   # Character of this move
  rationale: TransitionRationale   # void_snap, decision_chop, exhaustion_pullback, ...
  seed: int                        # For deterministic replay

StructuralEvent:
  scale: Scale
  event_type: COMPLETION | INVALIDATION | FRUSTRATION | MEASURED_MOVE
  level: FibLevel
  metadata: Dict

Reanchor:
  scale: Scale
  new_frame: ReferenceFrame        # Established after completion/invalidation
```

**Three Primitive Operations:**
1. **ADVANCE**: Move from one band to an adjacent band
2. **COMPLETE**: Reach 2.0 extension; swing becomes historical
3. **INVALIDATE**: Protective level violated beyond threshold; swing removed

All complex behaviors (frustration, measured moves, exhaustion pullbacks) are *composite patterns* of these primitives with attached probability modifiers—not new atomic types.

### 2.3 Episode Termination

An episode ends when a swing terminates. Per the North Star, termination occurs via:

| Condition | Trigger | Consequence |
|-----------|---------|-------------|
| **Completion** | `ratio(close) >= 2.0` | Swing becomes reference for new structure; mandatory pullback at highest scale |
| **Invalidation** | `ratio(close) <= -0.1` (S/M) or `ratio(wick) <= -0.15` (L/XL) | Swing removed; bias may flip |
| **Frustration** | `attempts[level] >= threshold` | Symmetric retrace triggered; level blocked |

The generator must guarantee eventual termination for every initiated swing. This is Church's base-case requirement: recursion without termination is undefined.

### 2.4 Recursion Across Scales

**Principle: Big moves drive small moves.**

Scale hierarchy is causal, not correlational. Implementation:

1. **Top-Down Gating**: When generating an M-scale transition, the generator receives parent context: `(L_band, L_direction, L_distance_to_target, L_exhaustion)`. This context *weights* child transitions—it does not *determine* them.

2. **Nested Filling**: Generation proceeds:
   - Sample XL move (band transition + duration)
   - Within that duration window, sample sequence of L moves conditioned on XL
   - Within each L move, sample M moves conditioned on L
   - Within each M move, sample S moves conditioned on M
   - S moves render to 1-minute bars

3. **Upward Propagation**: Child events (completion, invalidation) can trigger parent state updates, but *only* through explicit structural events—never through noise aggregation.

```
XL defines the room (price range)
  └─ L defines furniture placement (major structures within room)
       └─ M defines movement paths (intermediate swings)
            └─ S defines footsteps (1-minute bar generation)
```

**The fractal property**: The same `ScaleState` structure and transition rules apply at every scale. What differs is:
- Magnitude (XL swings are larger than S swings)
- Tolerance (L/XL allow soft invalidation buffer; S/M are strict)
- Extremity allowance (smaller scales can be "wilder")

### 2.5 Canonical Game Record

The game record is the **primary artifact**. OHLC is a rendered derivative. The record must be:
- **Sufficient**: Replay produces identical OHLC given seeds
- **Auditable**: Every bar traceable to specific decisions
- **Compact**: Store decisions, not pixels

```json
{
  "meta": {
    "instrument": "ES",
    "tick_size": 0.25,
    "start_timestamp": 1702656000,
    "master_seed": 42
  },
  "initial_state": {
    "XL": {"frame": {"anchor0": 4800, "anchor1": 5200, "direction": "bull"}, "band": "1.0-1.382"},
    "L": {...},
    "M": {...},
    "S": {...}
  },
  "news": [
    {"t": 1280, "polarity": -0.7, "intensity": "strong", "ttl_bars": 60}
  ],
  "log": [
    {
      "t": 0,
      "type": "band_transition",
      "scale": "M",
      "from": "1.0-1.382",
      "to": "1.382-1.5",
      "bars": 45,
      "impulse": 0.6,
      "rationale": "void_snap",
      "seed": 12345
    },
    {
      "t": 45,
      "type": "event",
      "scale": "M",
      "event": "FRUSTRATION",
      "level": "1.5",
      "attempts": 4
    },
    {
      "t": 45,
      "type": "band_transition",
      "scale": "M",
      "from": "1.382-1.5",
      "to": "1.0-1.382",
      "bars": 60,
      "rationale": "symmetric_retrace",
      "seed": 12346
    }
  ]
}
```

---

## 3. Stochastic Elements

### Where Randomness Enters

| Element | Distribution | Parameters | Source |
|---------|--------------|------------|--------|
| **Target band** | Categorical | P(to_band \| from_band, zone_type, parent_context, impulse) | Estimated from data |
| **Duration** | Log-normal or Gamma | μ, σ conditioned on (distance, zone_type, impulse) | Estimated from data |
| **Impulse** | EMA update | Decay rate, sensitivity | Rule-based default |
| **News arrival** | Poisson | λ per scale | External input |
| **Tail override** | Bernoulli × Pareto | Rare probability, heavy-tailed magnitude | Scale-dependent |

### Probability Modifiers

Transition probabilities are modified by context:

1. **Zone Type**: Decision zones (1.382–1.618) increase dwell; liquidity voids (1.1–1.382, 1.618–2.0) increase snap probability
2. **Parent Constraint**: If XL is in pullback, M upward transitions are down-weighted
3. **Frustration Pressure**: Failed attempts at a level increase retrace probability
4. **News Bias**: Pending news tilts toward aligned moves
5. **Target Stack**: Accumulated untouched targets increase impulsive resolution or liquidation probability

### The Interpretability Constraint on Stochasticity

Every probability modifier must be:
- **Named**: "frustration_penalty", "void_snap_bonus"
- **Inspectable**: Current value visible in state
- **Tunable**: Single parameter adjustable without retraining
- **Documented**: Why this modifier, what it represents

This is non-negotiable. If we cannot explain why the generator chose a transition, we cannot debug it.

---

## 4. Avoiding Overfitting with Limited Data

### The Data Reality

We have ~10-15 expert annotation sessions. Each session yields perhaps 50-100 labeled structural decisions. This is **radically insufficient** for learning representations end-to-end.

### The Strategy: Learn Parameters, Not Structure

| Component | Approach |
|-----------|----------|
| **Transition rules** | Fixed by North Star (which levels are adjacent, what triggers completion) |
| **Transition probabilities** | Start with rule-based priors; refine with data |
| **Duration distributions** | Log-normal with priors; fit parameters to observed inter-event times |
| **Second-order thresholds** | Fixed by North Star (frustration threshold, exhaustion behavior) |

**Key Insight**: The North Star already provides strong priors. We don't need to *learn* that 1.382 is a pivot or that 2.0 is completion—these are axioms. We only need to *estimate* the conditional probabilities of transitions between known states.

### Parameter Budget

With ~500-1000 structural decisions in our data:
- ~20 transition probabilities per scale × 4 scales = ~80 core parameters
- ~10 duration parameters per zone type = ~40 parameters
- ~10 second-order rule parameters = ~10 parameters

Total: ~130 meaningful parameters from ~1000 observations. This is learnable with proper regularization.

### Validation Strategy

1. **Leave-one-session-out cross-validation**: Train on N-1 sessions, validate on 1
2. **Structural invariant checking**: Generated sequences must never violate hard constraints
3. **Statistical comparison**: Transition frequencies, dwell distributions, completion rates match reference
4. **Visual inspection**: Domain expert review (the ultimate test)

---

## 5. Forward Path

### Phase 1: Foundation (Week 1-2)

**Goal**: Lock the coordinate system, state representation, and canonical record schema.

**Deliverables**:
1. Implement `ReferenceFrame` with oriented ratio computation
2. Implement `ScaleState` and `GameState` dataclasses
3. Implement `FibBand` enumeration and adjacency rules
4. Define canonical JSON log schema
5. Implement deterministic replay (log → OHLC given seeds)

**Validation**: Unit tests for ratio computation, band assignment, and round-trip.

### Phase 2: Forward Discretization (Week 3-4)

**Goal**: Convert real OHLC + detected swings into game records for calibration.

**Deliverables**:
1. Implement forward discretizer: OHLC → log
2. Extract transition counts by (from_band, to_band, zone_type, parent_context)
3. Extract duration distributions by (distance, zone_type)
4. Validate: discretized logs reproduce detected structural events

**Validation**: Visual overlays showing discretized bands align with annotations.

### Phase 3: Single-Scale Generation (Week 5-6)

**Goal**: Generate syntactically valid action sequences at one scale (suggest M).

**Deliverables**:
1. Implement transition sampler with categorical distribution
2. Implement duration sampler with log-normal distribution
3. Implement basic OHLC renderer (Brownian bridge between band boundaries)
4. Add invariant checking (no impossible transitions, no infinite loops)

**Validation**: Generated M-scale sequences pass structural invariant checks; visual inspection shows plausible level interactions.

### Phase 4: Multi-Scale Coordination (Week 7-8)

**Goal**: Full recursive generation XL → L → M → S.

**Deliverables**:
1. Implement parent-child context passing
2. Implement nested filling (parent duration constrains child sequence)
3. Implement cross-scale event propagation
4. Generate complete 1-minute OHLC streams

**Validation**: Generated data shows proper scale hierarchy; XL moves contain coherent L/M/S substructure.

### Phase 5: Second-Order Rules (Week 9-10)

**Goal**: Implement frustration, exhaustion, measured-move, and target-stacking rules.

**Deliverables**:
1. Add attempt counters and frustration detection
2. Add exhaustion flag and mandatory pullback logic
3. Add measured-move triggers
4. Add target-stack pressure computation

**Validation**: Generated data exhibits decision-zone chop, symmetric retraces on frustration, and exhaustion pullbacks.

### Phase 6: Calibration and Tuning (Week 11-12)

**Goal**: Refine probability parameters using empirical data.

**Deliverables**:
1. Estimate transition probabilities from discretized real data
2. Estimate duration parameters by zone type
3. Tune second-order thresholds
4. Build CLI for interactive parameter adjustment

**Validation**: Statistical comparison of generated vs. real data; domain expert review.

### Falsification Experiments

Early falsification prevents wasted effort. Run these experiments before committing to full implementation:

| Experiment | Question | Kill Criterion |
|------------|----------|----------------|
| **Band Coverage** | Does the Fib band discretization capture all significant price positions? | >10% of real price time spent in undefined zones |
| **Adjacency Sufficiency** | Can we model real transitions with adjacent-only moves (plus rare tails)? | >5% of real transitions require non-adjacent jumps |
| **Duration Stationarity** | Do duration distributions hold across regimes? | Kolmogorov-Smirnov test fails on held-out data |
| **Hierarchy Coherence** | Does parent conditioning produce sensible child behavior? | Visual inspection shows parent-child conflicts |

### Definition of "Done"

The discretization is complete when:

- [ ] Every state transition maps to one English sentence
- [ ] Canonical log round-trips through OHLC with structural fidelity
- [ ] Generator produces sequences passing all structural invariant checks
- [ ] Transition frequencies match reference data within 15%
- [ ] Duration distributions match reference data (KS test p > 0.05)
- [ ] Domain expert rates >70% of generated samples as "could be real"
- [ ] Documentation enables extension without rediscovering context

---

## 6. Risk Controls

### Detecting Drift from Fidelity

| Indicator | Detection | Response |
|-----------|-----------|----------|
| **Structural violation** | Invariant checks in generator | Immediate crash with trace |
| **Distribution drift** | Periodic statistical comparison | Re-calibrate parameters |
| **Visual artificiality** | Expert review sessions | Identify and log specific patterns |
| **Regime blindness** | Test on held-out regimes (2022 vol, 2019 low vol) | Regime-specific parameter tables |

### Detecting Broken Fractal Assumptions

The fractal assumption (same rules at all scales) could be wrong. Detect via:

1. **Scale-specific validation**: Run structural checks per scale, not just aggregate
2. **Cross-scale coherence**: Verify parent-child relationships are bidirectionally consistent
3. **Extremity gradient**: Verify smaller scales show higher variance (as North Star predicts)

If fractal assumption breaks, consider scale-specific rule variants (an extension, not a redesign).

### Handling Weak News Model

The current design assumes a news model providing (polarity, intensity, timing) streams. If this model is weaker than expected:

**Fallback 1**: Treat news as uniform random perturbations with configurable frequency/magnitude. This produces variety without semantic content.

**Fallback 2**: Remove news injection entirely; generate "quiet market" data that obeys structural rules without external catalysts. This is still useful for validation.

**Fallback 3**: Let users manually inject news events into game records for scenario analysis.

The core discretization remains valid regardless of news model quality—news modifies probabilities, it doesn't define the state space.

---

## 7. Failure Modes and Uncertainties

### Known Unknowns

1. **Volatility Regime Dynamics**: The current design uses impulse EMA. Real volatility clustering may require more sophisticated dynamics (GARCH-like). Monitor and extend if needed.

2. **Cross-Scale Timing**: When parent commits to a duration, children must fill it. What if child dynamics naturally want longer/shorter? Current design uses soft constraints; may need adjustment.

3. **Motif Variety**: Brownian bridges may feel repetitive. May need small motif library for OHLC rendering. Defer until visual inspection demands it.

4. **Off-Grid Structure**: Real markets occasionally exhibit price levels that don't align with Fib bands. Current design treats these as noise. Monitor whether this loses important signal.

### What Could Go Wrong

| Failure Mode | Symptom | Mitigation |
|--------------|---------|------------|
| **Too rigid** | Generated data looks mechanical | Add noise in renderer; expand tail probability |
| **Too random** | Generated data loses structure | Tighten transition constraints; increase invariant strictness |
| **Scale drift** | Lower scales don't respect parents | Strengthen parent conditioning weights |
| **Parameter instability** | Small data changes cause large output changes | Use stronger priors; Bayesian smoothing |

### Honest Assessment

This approach is **not** a guarantee of success. It is the **most likely path** given our constraints. The key risks are:

1. **Visual realism may lag**: The first generated data will probably look artificial. This is expected and acceptable if structurally correct. Realism comes from iteration.

2. **Calibration is manual**: We will spend significant time adjusting parameters by hand, looking at charts, making judgment calls. This is not a bug—it's how expert systems are built.

3. **Scope is large**: The full implementation touches data loading, swing detection, state management, generation, rendering, and validation. Phased delivery with early falsification reduces risk but doesn't eliminate it.

---

## Appendix 1: Document Synthesis

### Summary of Drafts Reviewed

| Draft | Primary Recommendation | Key Strength | Key Weakness |
|-------|----------------------|--------------|--------------|
| **C1** | Pure stochastic grammar (L-system) | Deepest interpretability analysis; explicit rule traceability | Grammar may be too regular; rendering underspecified |
| **C2** | Level-Grid Markov Model | Clean state definition; explicit tenets | Less attention to second-order rules |
| **C3** | Level-Graph State Machine + swing bookkeeping | Best separation of concerns (generator vs bookkeeper vs renderer) | Complex three-layer architecture |
| **O1** | Fibonacci Band State Machine | Compact; Andy Grove-style decisiveness | Light on recursion details |
| **O2** | HSMLM with Intent/Attempt augmentation | Best second-order rule handling; explicit volatility treatment | Most complex state |
| **G1** | Recursive Structural Grammar (FSM + Grammar hybrid) | Clear "Game Piece" definition (TargetedMove) | Less implementation detail |

### Common Ground (Unanimous or Near-Unanimous)

1. **Interpretability is the primary constraint.** Every draft, without exception, prioritizes interpretability over compression. Several drafts explicitly reject neural networks due to data scarcity and debugging requirements.

2. **Fibonacci bands are the coordinate system.** All drafts use Fib levels as the discrete state space. Position is always relative to an active reference swing, never absolute price.

3. **Top-down causality is causal, not correlational.** All drafts enforce that XL/L constrain M/S, never the reverse (except through explicit structural events).

4. **State machine (or equivalent) is the core abstraction.** Whether called "Markov model," "FSM," or "band machine," all drafts converge on discrete states with probabilistic transitions.

5. **The canonical record stores decisions, not OHLC.** All drafts agree that the game log should be replayable and auditable—OHLC is a rendering artifact.

6. **Limited data requires rule-based priors.** All drafts acknowledge that parameters can be tuned, but structure must be defined by the North Star, not learned from data.

### Key Disagreements

| Topic | Position A | Position B | Resolution |
|-------|------------|------------|------------|
| **Grammar vs State Machine** | C1: Pure grammar is more elegant and inherently recursive | C2, C3, O1, O2: State machine is simpler and more debuggable | State machine as core, with grammar-inspired rule organization |
| **Explicit intent/attempts** | O2: Decision zones need explicit attempt tracking | C2, C3: This is bookkeeping, not state | Include as state (O2 is correct—chop is structural, not noise) |
| **Volatility treatment** | C3, O2: Impulse/volatility is first-class state | C1, C2: Volatility is a duration modifier only | Include as state but keep simple (EMA, not GARCH) |
| **Motif library** | O2, G1: Motifs improve realism | C1, C2, C3: Motifs risk becoming a grab-bag of special cases | Defer to renderer layer; use only if visual inspection demands |

### Blind Spots Across Drafts

1. **News modeling**: All drafts hand-wave the news stream. "Assume it exists" is the consensus, but injection points and interaction with structural rules need more specificity.

2. **Validation methodology**: Statistical comparisons are mentioned but not detailed. What exact metrics? What thresholds?

3. **Existing codebase integration**: Drafts define representations but don't specify how they integrate with `SwingDetector`, `ScaleCalibrator`, `BarAggregator`, etc.

4. **Error handling**: What happens when the generator encounters an impossible state (e.g., parent says go up, all up transitions blocked)?

### How This Proposal Resolves Conflicts

1. **State machine as core, grammar as organization**: The recommendation uses a Fibonacci Band State Machine (C2/C3/O1 convergence) but organizes rules in interpretable named blocks with documented probabilities (C1 grammar influence).

2. **Explicit second-order state**: Following O2, the recommendation includes attempt counters, frustration flags, and exhaustion state directly in `ScaleState`. This is worth the complexity because decision-zone behavior is central to realism.

3. **Volatility as impulse EMA**: Following C3 and O2, volatility is a first-class state variable, but kept simple (EMA) rather than sophisticated (GARCH). Extend later if needed.

4. **Motifs deferred to renderer**: Following the conservative consensus, motifs are not part of the core representation. If Brownian bridges feel too uniform, add a small motif library to the OHLC renderer—but keep it separate from the game state.

5. **News as injection points**: Define explicit injection points (probability modifiers) without requiring a full news model. The design remains valid if news is weak or absent.

### What Each Draft Contributes Uniquely

| Draft | Unique Contribution |
|-------|---------------------|
| **C1** | The "interpretability imperative" argument (strongest case for rejecting neural networks) |
| **C2** | The "tenets as explicit tiebreakers" methodology (adopted here) |
| **C3** | The three-primitive action space (ADVANCE, COMPLETE, INVALIDATE) |
| **O1** | The week-by-week sequencing plan with concrete milestones |
| **O2** | The directed reference frame (oriented ratio that works for bull and bear) |
| **G1** | The "TargetedMove" framing (every move has an intended destination) |

### What Each Draft Misses

| Draft | Gap |
|-------|-----|
| **C1** | Under-specifies OHLC rendering; grammar may be too abstract for debugging |
| **C2** | Light on second-order rules (frustration, exhaustion); may feel too "clean" |
| **C3** | Three-layer architecture may be over-engineered for initial implementation |
| **O1** | Sparse on recursion mechanics; how exactly does parent constrain child? |
| **O2** | Most complex state; may be hard to implement incrementally |
| **G1** | Least detailed; needs more implementation specificity |

---

*Document version: 1.0*
*Created: December 15, 2025*

---

# DRAFT: discretization_approaches_g1

*Source: Docs/Proposals/Drafts/discretization_approaches_g1.md*

# Proposal: Discretization Approaches for Fractal Market Generation

**Status:** Draft (G1)
**Date:** December 15, 2025
**Author:** Antigravity (AI Agent)

---

## 1. Problem Statement

The Fractal Market Simulator (FMS) aims to generate realistic 1-minute OHLC market data by recursively simulating price action across multiple timeframes (XL to S). While the market outputs continuous price streams, the *generative logic* must operate on discrete units of "market behavior" (moves, swings, completions) to be learnable, interpretable, and controllable.

**The core problem is to define the atomic "Game Piece" of this system.**

We need a representation that bridges the continuous domain of price/time (where OHLC bars live) and the discrete domain of game states (where the recursive generator lives). This representation must preserve the specific physics of the Product North Star—Fibonacci relationships, fractal self-similarity, and momentum rules—without introducing artifacts that break the illusion of realism. If the pieces are too coarse, we lose the fractal "roughness"; if too fine, the generator becomes a chaotic random walker.

## 2. Key Questions

1.  **State Definition:** What constitutes the minimal sufficient state to predict the next "move"? Does a "move" know its own history, or is the history encoded in the board state (levels)?
2.  **Vocabulary Size:** How many distinct types of "moves" exist? Is the set finite (e.g., "Impulse", "Retrace") or parametric (e.g., "Move(delta_x, delta_y)")?
3.  **Causality & Termination:** How strictly does the discrete model enforce the "2x Completion" or "Invalidation" rules? Are these hard constraints in the grammar, or emergent properties of the sampling?
4.  **Information Loss:** When we look at a "Game Record" (sequence of discrete moves), can we strictly reconstruct a valid OHLC chart, and does that chart look "right" to a human expert?
5.  **Stochasticity:** Where does the randomness live? In the selection of the next move type? In the exact extension of that move? Or in the "News" events that interrupt moves?

## 3. Guiding Tenets

1.  **Scale Invariance (The Mandelbrot Constraint):** The "Game Piece" definition must be identical at all scales. A move on the XL timeframe is structurally indistinguishable from a move on the S timeframe, differing only in magnitude and duration.
2.  **Narrative Causality:** Every move must have a reason grounded in the *current* structure (e.g., "Seeking liquidity at 1.382"). Randomness is allowed in the *outcome*, not the *intent*.
3.  **Hard Structure, Soft Edges:** Key structural rules (e.g., "Invalidation at -0.1") are hard constraints for the game logic. The "fuzziness" of real markets (wicks, noise) is a rendering detail, not a state transition ambiguity.
4.  **Interpretation > Optimization:** The representation must be human-readable. We prioritize a grammar that an expert can read ("XL Bull Swing failed at 1.5, retesting 1.0") over a latent vector that achieves marginally higher loss performance.

## 4. Virtual Consultation

I have "consulted" a panel of three experts to inform this design.

| Expert | Role | Core Question |
| :--- | :--- | :--- |
| **Benoit Mandelbrot** | Father of Fractals | "How do we preserve roughness while discretizing?" |
| **Claude Shannon** | Information Theorist | "What is the efficient encoding of a market move?" |
| **Jesse Livermore** | Legendary Trader | "What actually matters to the price action?" |

### Benoit Mandelbrot on Roughness & Scale
*"You are tempted to smooth the data to find the trend. Do not. The 'roughness' is not noise; it is the generator itself visible at a smaller scale. Your 'Game Piece' cannot be a straight line vector. It must be a container for volatility. If you define a move from A to B, you must strictly bound the path it takes, but you must allow the path to be jagged. The generator at Scale N specifies the 'Trend' for Scale N-1. The 'Game Piece' is not a vector; it is a **corridor**."*

### Claude Shannon on Information Density
*"The market is redundant. Most tick data is noise. To discretize efficiently, you must identify the signals that reduce uncertainty. 'Price went up 1 tick' contains almost zero information. 'Price crossed the 1.382 level' contains massive information because it resolves a state of uncertainty (the Decision Zone). Your discrete states should only change when information changes. If the price is wandering between 1.1 and 1.3, the state is constant: 'Testing Decision Zone'. Do not generate a new game token until the state resolves."*

### Jesse Livermore on The Line of Least Resistance
*"I don't care about the wiggles. I care about the line of least resistance. Is the market trying to break the high? Is it failing? Your 'pieces' need to capture the **struggle**. A move isn't just 'Distance X'. It is 'Attacking 1.5'. If it fails, that's a specific move: 'Rejection'. If it succeeds, that's 'Breakout'. The identity of the move is defined by the **Levels** it interacts with, not just its length. Discretize based on the interaction with the levels."*

## 5. Concrete Implications

Synthesizing the panel:
1.  **Discrete States are Regions, not Points:** The game state is defined by which "Zone" the price is in relative to the active Reference Swing (e.g., "In Liquidity Void 1.1–1.382").
2.  **Moves are Transitions:** The atomic "action" is a transition from one Zone to another (e.g., "Crossed 1.382").
3.  **Recursive Corridors:** A "Move" at Scale N defines the High/Low bounds for the generator at Scale N-1. The Scale N-1 generator must complete its sub-moves *within* those bounds (or slightly beyond, effectively "wicks").
4.  **Event-Driven Sampling:** We do not sample "next price". We sample "next structural event" (e.g., "Will we hit 1.5 or 1.0 next?").

## 6. Discretization Options

### Option A: The Fibonacci State Machine (FSM)

**Concept:** The market is strictly a Finite State Machine where "States" are the Fibonacci zones of the *current active reference swing*.

**Representation:**
*   **State:** `(ActiveSwing, CurrentZone)`
    *   `ActiveSwing`: The reference swing (H, L) defining the grid.
    *   `CurrentZone`: Enum `[Retracement_Deep (<0.382), Decision_Zone (1.382-1.618), Extension_Target (1.618-2.0), ...]`.
*   **Action:** `Transition(TargetLevel, SuccessBoolean)`
    *   e.g., `TryReach(1.382) -> Success` implies a move from current price to 1.382.
    *   e.g., `TryReach(2.0) -> Fail` implies a move towards 2.0 that exhausts/reverses before touching.

**Recursion:**
*   A `Transition` at Scale L (e.g., "Go from 1.0 to 1.382") becomes the *Objective* for the Scale M generator.
*   The Scale M generator spawns a sequence of M-swings to traverse that price distance.

**Pros:**
*   Highly interpretable (maps 1:1 to North Star zones).
*   Enforces Fibonacci physics strictly.
*   "Narrative" is explicit (the "why" is the target level).

**Cons:**
*   May feel robotic if transitions are too clean.
*   Handling "Fails" (rejections) requires complex logic (how close did it get?).

### Option B: The "Move Grammar" (Syntactic Approach)

**Concept:** Treat market generation as a language generation problem. We define a grammar of valid market "sentences" (swings).

**Representation:**
*   **Vocabulary:** `[Impulse, Correction, Rejection, Consolidation, StopRun]`
*   **Grammar Rule:** `BullSwing -> Impulse + Pullback + (Continuation | Failure)`
*   **Token:** `Piece(Type, Magnitude, Duration)`

**Recursion:**
*   `Impulse(XL)` expands to `[Impulse(L), Correction(L), Impulse(L)]`.
*   Expansion rules are stochastic grammar productions.

**Pros:**
*   Naturally fractal (Context Free Grammars are recursive).
*   Easy to train sequence models (Transformers) on token streams.
*   Good for "Black Swan" or "News" injection (just insert a special token).

**Cons:**
*   Harder to enforce strict price levels (grammar knows "Impulse" but not "Stop at exactly 4150.50").
*   Risk of determining "syntax" that doesn't align with market "physics".

### Option C: The Structural Event Chain (Hybrid)

**Concept:** Discrete simulation of "Forces" and "Barriers". The game pieces are *Intentions* colliding with *Levels*.

**Representation:**
*   **Board:** A set of horizontal Lines (Fib levels from all scales).
*   **Piece:** A `SwingSegment` with a `Vector` (Direction, Velocity).
*   **Interaction:** When a `Vector` hits a `Line`:
    *   *Resolve:* Break, Reject, or Piercing (Wick).
    *   *Outcome:* Update Vector.

**Recursion:**
*   Scale L simulation runs collision detection on L-Lines.
*   Between L-events, Scale M simulation runs locally.

**Pros:**
*   Most "realistic" dynamics (velocity vs. resistance).
*   Captures the "Momentum" requirement naturally.
*   Wicks/Piercings emerge naturally from "velocity > resistance".

**Cons:**
*   Most complex state to manage (physics engine vs. logic engine).
*   Hardest to interpret "why" a move happened (was it structural or just high velocity?).

## 7. Tradeoff Analysis

*Evaluated by "The Architect" (System Designer Persona)*

| Criterion | Option A (FSM) | Option B (Grammar) | Option C (Event Chain) |
| :--- | :--- | :--- | :--- |
| **Interpretability** | **High** - Explicit states | Medium - Token seq | Medium - Physics logic |
| **Fidelity (Fibs)** | **Perfect** - Baked in | Low - Drift risk | High - Collision logic |
| **Fractal Config** | Medium - Explicit handoff | **High** - Natural recursion | Medium - Simulation steps |
| **Learnability** | High - Discrete RL | **High** - LLM/Transformer | Low - Physics tuning |
| **Extensibility** | Medium - Add states | High - Add tokens | Low - Complex interactions |
| **North Star Align** | **Best Match** | Good | Deviation risk |

**Analysis:**
Option B (Grammar) is seductive because it treats the market as language, which fits modern AI generation. However, it struggles with the *strictness* of the Fibonacci constraints (North Star: "Price at certain levels has tendencies"). A grammar model often hallucinates precise arithmetic.
Option C (Event Chain) is too essentially a physics simulation; it risks becoming a "bouncing ball" model rather than a "psychological/liquidity" model.
Option A (FSM) aligns perfectly with the "Zones" and "Decision" logic described in the Product North Star. The market *is* a state machine of liquidity seeking. The main risk is rigidity.

## 8. Recommendation

**Adopt a Hybrid of Option A (FSM) and Option B (Grammar).**

We should use **The Recursive Structural Grammar**.

1.  **Structure (from Option A):** The "Alphabet" of the grammar is strictly defined by the Fibonacci State Machine. You cannot output a token "Move Up"; you must output a token "Target 1.382". This binds the grammar to the grid.
2.  **Sequence (from Option B):** The generation logic is a probabilistic grammar that selects the next target based on history.
    *   *Example:* `Context: [Came from 1.0, Rejected 1.5] -> Next Token Probabilities: [Retest 1.382: 60%, Break 1.0: 30%, StopRun -0.1: 10%]`

**The "Game Piece":**
A **`TargetedMove`**.
*   **Start Point:** Current Price / Zone.
*   **Intended Destination:** A specific Fib level of the active reference swing.
*   **Outcome:** `Hit`, `Miss`, `Piercing`, `Reversal`.
*   **Duration/Shape:** Parametric constraints for the lower-scale generator.

**Why this works:**
*   It is **Rigid on Price** (Fibs are exact).
*   It is **Flexible on Sequence** (Grammar learns the "song" of the market).
*   It is **Fractal** (The `TargetedMove` at Scale L is just the bounded container for a sequence of `TargetedMoves` at Scale M).

### Done Criteria for "Game Piece" Definition
*   [ ] Define the exact list of "Zones" (0-0.382, 0.382–0.618, etc.).
*   [ ] Define the set of "Outcomes" (Clean Hit, Wick, Front-run).
*   [ ] Define the "Handoff" protocol from Scale N to Scale N-1.

This approach gives us the "Game Board" (Fibs) and the "Moves" (Grammar), satisfying both the physicist (Mandelbrot) and the information theorist (Shannon).

---

# DRAFT: discretization_approaches_o1

*Source: Docs/Proposals/Drafts/discretization_approaches_o1.md*

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

---

# DRAFT: discretization_approaches_o2

*Source: Docs/Proposals/Drafts/discretization_approaches_o2.md*

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


---

# DRAFT: discretization_approaches_os1

*Source: Docs/Proposals/Drafts/discretization_approaches_os1.md*

# Discretizing Continuous OHLC into Recursive Swing “Game Pieces” (OS1)

## Main proposal

### Problem statement (North Star aligned)

We need a discretization of continuous OHLC into **swing-level game pieces** that a recursive generator can manipulate to produce **1‑minute OHLC that looks real** while obeying the project’s structural laws (Fibonacci attractors, 2× completion, scale-aware invalidation, decision zones/liquidity voids, and top‑down causality). This discretization is the bridge between:

- **Analysis** (what the repo already does: multi-scale swings + Fib levels + structural events), and
- **Generation** (the North Star: synthesize OHLC with the same laws, not a black-box imitation).

Per `.claude/why.md`, **trust is existential**: the representation must be interpretable and replayable so every generated bar can be traced to explicit, auditable decisions before real capital ever touches it.

### Success criteria (what “good discretization” means)

1. **Interpretability is first-class**
   - Every discrete transition is explainable in one sentence in market-structure language (“L scale tested 1.5 four times and triggered frustration → symmetric retrace to 0.5”).
   - No “latent state” is required to understand why an outcome happened.

2. **Structural correctness is enforced, not hoped for**
   - Completion, invalidation thresholds, allowed transitions, and top‑down causality are hard invariants, with a single explicit escape hatch (“tail override”) that is always logged.

3. **Data efficiency / anti-overfitting**
   - The representation is learnable/tunable from **small data** (expert swing annotations + counts from OHLC), using strong priors and maximum-entropy defaults.
   - Parameters are few, human-meaningful, and stable across regimes; avoid large conditional tables that memorize one dataset.

4. **Stochastic richness without structural drift**
   - Diversity comes from sampling *among structurally valid options* (targets, durations, path shapes) and from a controlled tail channel—not from breaking rules.

5. **Replayable canonical truth**
   - There is a single canonical “game record” log that deterministically regenerates OHLC given seeds (OHLC is a rendering of decisions, not the decisions themselves).

---

## The recommended discretization: HSMLM + explicit decision dynamics

### One canonical coordinate system (bull and bear unify)

Define an **oriented swing frame** where Fibonacci “ratio” always increases in the *expected move direction*.

**ReferenceFrame**

- For a bull reference: `anchor0 = low`, `anchor1 = high`
- For a bear reference: `anchor0 = high`, `anchor1 = low`

Then:

```
range = anchor1 - anchor0              # sign encodes direction
ratio(p) = (p - anchor0) / range       # works for bull and bear
price(r) = anchor0 + r * range
```

Interpretation:
- `ratio == 0` is the defended pivot (low for bull, high for bear).
- `ratio == 1` is the origin extremum (high for bull, low for bear).
- `ratio == 2` is the 2× completion target.
- Negative ratios are “beyond the defended pivot” (stop-run territory).

This gives us a universal notion of “where price is” relative to structure, without separate bull/bear logic in the discrete layer.

### Discrete “board”: named levels and bands

Use a small, fixed set of ratios as **named boundaries**; the discrete state is the **band** (interval) between adjacent boundaries, not the raw ratio.

**Phase 1 level set (match the North Star rules, keep it small):**

- `STOP = -0.10` (explicit stop-run depth; invalidation threshold is scale-specific)
- `0.00`, `0.10`, `0.382`, `0.50`, `0.618`
- `0.90`, `1.00`, `1.10`
- `1.382`, `1.50`, `1.618`
- `2.00` (completion)

This level set is intentionally *structural*: it encodes the decision-zone / void geometry in `Docs/Reference/product_north_star.md` without needing pattern libraries on day one.

**Bands** are the adjacent intervals (e.g., `1.382–1.50`, `1.50–1.618`, `1.618–2.00`, `0.10–0.382`, etc.).

**Scale-dependent termination thresholds (explicit)**

Completion/invalidation semantics are hard constraints, but the thresholds vary by scale (mirrors the repo’s documented validation rules).

| Scale | Completion (bull/bear) | Invalidation (trade) | Invalidation (close) |
|-------|-------------------------|----------------------|----------------------|
| S / M | `ratio(close) ≥ 2.0` | `ratio(wick) < 0.0` | `ratio(close) < 0.0` |
| L / XL | `ratio(close) ≥ 2.0` | `ratio(wick) ≤ -0.15` | `ratio(close) ≤ -0.10` |

Notes:
- `STOP = -0.10` is a named behavioral boundary (“stop run” depth). On S/M it sits *past* invalidation; recoveries still exist but are represented as a new `Reanchor` after invalidation (not as “quiet violations”).
- “Wick” vs “close” is evaluated at the swing’s aggregation level, not raw 1‑minute bars.

### Atomic “game piece” (what we discretize into)

The atomic game piece is a **BandTransition** at a given scale:

> “At scale M, price moved from band `1.00–1.10` to band `1.10–1.382` over 47 minutes, under parent context X, with rationale Y.”

This is the smallest unit that:
- maps cleanly to OHLC reconstruction (entry/exit prices are defined),
- supports recursion (lower scales fill the interior),
- remains interpretable (it is literally “which structural boundary did we cross?”).

### State (what exists on the board)

Model each scale as a **Hierarchical Semi‑Markov Level Machine (HSMLM)**: a semi‑Markov process over bands, with explicit counters for second‑order rules.

**Per‑scale state (`ScaleState`)**

- `scale ∈ {S, M, L, XL}`
- `frame: ReferenceFrame` (anchor0/anchor1 + derived prices)
- `band_id` (current band)
- `dwell_bars` (semi‑Markov time spent in current band)
- `impulse_ema` (distance / time proxy; drives volatility clustering)
- `attempts[level_name]` (failed tests near key levels; fuels frustration)
- `frustrated[level_name]` (boolean flags)
- `exhausted` (set after completion; forces pullback expectations at top scale)
- `target_stack_pressure` (scalar; tracks “too many targets” rule)
- `tail_mode` (rare override active? if yes, must be logged)
- `parent_context` (derived inputs from the parent scale; see recursion)

**Global state (`GameState`)**

- `t` (time in 1‑minute bars)
- `scales: {XL, L, M, S} → ScaleState`
- `news_stream` (optional, exogenous events; see assumptions)

This is intentionally *small* and *auditable*: it’s the minimum that lets us implement decision zones, liquidity voids, frustration/measured-move/exhaustion, and volatility clustering without hidden variables.

### Actions / moves (what changes state)

At the discrete layer, there are only three primitives:

1. **`BandTransition`**
   - `(scale, from_band, to_band, duration_bars, rationale, rng_seed)`
   - Default constraint: transitions are to **adjacent bands** only.

2. **`StructuralEvent`**
   - `(scale, event_type, level_name, metadata)`
   - Types: `LEVEL_TEST`, `FRUSTRATION`, `MEASURED_MOVE_TRIGGER`, `COMPLETION`, `INVALIDATION`, `TARGET_STACK_RELEASE`, `TAIL_OVERRIDE`.

3. **`Reanchor`**
   - `(scale, new_frame, reason)` after completion/invalidation or explicit model rules.

### What ends an episode

Define episodes in two ways (both useful; choose per experiment):

- **Structural episode (recommended):** one full lifecycle of the **top available scale frame** in the window (ideally XL): begins at `Reanchor`, ends at `COMPLETION` or `INVALIDATION` on that scale.
- **Fixed-horizon episode (practical for simulation runs):** generate for `N` minutes; any active frames persist across horizons in the log.

In both cases, lower scales terminate and reanchor multiple times within a higher-scale episode.

### Recursion across scales (how “big moves drive small moves” becomes code)

Top‑down causality is enforced by **parent‑conditioned sampling**, not by letting children “vote” a parent into existence.

For each child scale `k`, compute a parent context `C_{k+1→k}` including:

- parent band and zone type (void vs decision zone),
- parent pending direction (toward higher ratio vs lower),
- parent distance to next key boundary / completion,
- parent exhaustion/frustration constraints,
- parent “allowed play” envelope (soft bounds for child exploration).

Then sample child transitions as:

```
P(child_next | child_state, C_parent) ∝ base(child_band, zone_type) × gate(parent_direction, distance, constraints) × modifiers(news, impulse, target_stack)
```

**Hard rule:** child behavior may only change parent state via explicit logged structural events (completion/invalidation) or an explicit logged tail override. This makes causal direction auditable.

### Canonical truth: the “game record” (what is real)

The canonical truth is an append‑only log of:

- initial frames per scale,
- exogenous news events (optional),
- band transitions + structural events + reanchors,
- RNG seeds for deterministic replay.

OHLC is a deterministic rendering of this log (given seeds + renderer version).

**Minimal schema sketch**

```json
{
  "meta": {"instrument":"ES", "tick":0.25, "seed":123, "level_set":"os1-v1"},
  "initial": {
    "XL": {"anchor0": 5000.0, "anchor1": 5100.0, "as_of_t": 0},
    "L":  {"anchor0": 5030.0, "anchor1": 5090.0, "as_of_t": 0}
  },
  "news": [{"t": 1280, "polarity": -1, "intensity": 0.7, "ttl": 60}],
  "log": [
    {"id":"m1","t": 0, "type":"move", "scale":"L", "from":"1.00–1.10", "to":"1.10–1.382", "bars": 47, "why":"void_snap", "seed": 991},
    {"id":"e1","t":47, "type":"event","scale":"L", "event":"LEVEL_TEST", "level":"1.382", "attempt":1},
    {"id":"m2","t":47, "type":"move", "scale":"L", "from":"1.10–1.382", "to":"1.00–1.10", "bars": 33, "why":"decision_reject", "seed": 992},
    {"id":"e2","t":80, "type":"event","scale":"L", "event":"FRUSTRATION", "level":"1.382", "attempts":4},
    {"id":"m3","t":80, "type":"move", "scale":"L", "from":"1.00–1.10", "to":"0.50–0.618", "bars": 210, "why":"symmetric_retrace", "seed": 993},
    {"id":"m4","t":80, "type":"move", "scale":"M", "parent":"m3", "from":"1.00–1.10", "to":"1.10–1.382", "bars": 23, "why":"child_fill", "seed": 1991}
  ]
}
```

This log is the “game record” we will calibrate against and debug against. If the generator produces nonsense, the log tells us exactly which rule/path did it.

---

## Avoiding overfitting while enabling stochastic richness

### The anti-overfitting posture

1. **Fixed representation; learn only parameters**
   - The level set, invariants, event types, and recursion wiring are fixed by the North Star.
   - What we estimate from data: a small number of transition weights, duration distributions, and modifier strengths.

2. **Maximum entropy defaults**
   - Where data is sparse, prefer the maximum‑entropy distribution consistent with the constraints (no bespoke conditionals until falsified by evidence).

3. **Strong priors + partial pooling**
   - Use Dirichlet priors for categorical transitions and Gamma/LogNormal priors for durations.
   - Pool parameters across scales where the rule is asserted to be self‑similar; allow scale‑specific multipliers for “smaller can be more extreme.”

4. **Keep the degrees of freedom orthogonal**
   - Separate: (a) target choice, (b) duration choice, (c) rendering noise/wicks. This prevents “fixing structure” by hiding it in the renderer.

### Where stochastic richness comes from (without breaking rules)

- **Choice randomness:** which adjacent band is targeted next (with interpretable weights).
- **Timing randomness:** semi‑Markov durations per transition (captures chop vs snap).
- **Volatility clustering:** impulse/vol regime evolves slowly (EMA), modulating durations and wick budgets.
- **Rendering randomness:** intra‑band path shape and wick placement (bounded, reversible at the structural level).
- **Tail channel:** rare, explicitly logged non‑adjacent transitions / overshoots (scale‑dependent heaviness).
- **News (optional):** exogenous tilts to probabilities and/or duration (accelerants), never a hidden driver.

---

## Forward path (implementation-oriented)

### Implement first (fast feedback, low regret)

1. **Lock OS1 coordinate + level set**
   - Implement `ReferenceFrame.ratio()` / `price()` and the OS1 boundary list (including `0.9/1.1/0.1/-0.1`).
   - Add invariant checks as reusable validators.

2. **Define the canonical log schema + deterministic replay contract**
   - Version the schema and renderer; enforce “same log + same seeds ⇒ same OHLC.”

3. **Build a forward discretizer (OHLC → game record)**
   - Input: OHLC + chosen reference frames (start with human annotations; later system‑detected).
   - Output: OS1 log of band transitions + events; extract empirical transition counts and dwell distributions by zone.
   - This is the quickest falsification tool: if discretization produces messy, non‑stable logs, generation will be worse.

4. **Build a minimal renderer (game record → OHLC)**
   - Start with piecewise-linear + bounded noise / wicks; ensure tick quantization.
   - Validate round‑trip at the structural level: `discretize(render(log))` ≈ `log` (up to tolerance).

### Defer (until the core is stable)

- Full motif library (beyond a handful of interpretable templates).
- Multiple concurrent reference frames per scale (stacking/alternates), except as a simple `target_stack_pressure` scalar.
- Learned news process; semantic news; cross‑market coupling.
- Sophisticated “multi-swing rule” interactions beyond explicit events.

### Fast falsification experiments (kill the approach quickly if it’s wrong)

1. **Band stability test:** On annotated windows, does the forward discretizer produce a compact log where most movement is captured by band transitions and not by constant reanchoring?
2. **Zone separation test:** In real OHLC logs, do decision zones (`1.382–1.618`) show materially higher dwell/attempt counts than liquidity voids (`1.618–2.0`, `1.10–1.382`)? If not, either the level set is wrong or the event definitions are.
3. **Replay test:** Can we render → rediscretize and recover the same structural events (completions/invalidations/frustrations) with high consistency?
4. **Causality leakage test:** In generated data, measure the rate at which child net progress contradicts parent direction absent tail overrides. If it’s high, recursion wiring is wrong.

### “Done” for this phase (discretization, not full generation)

- OS1 logs can be extracted from real OHLC windows (with annotated frames) without lookahead and with stable event semantics.
- The log is auditable: any event or move has a human-readable explanation and an invariant justification.
- Rendering a log produces OHLC whose rediscretization recovers the same structural event sequence within tolerance.
- We can compute and track a small set of drift metrics (below) and use them as regression gates.

### Risk controls (detect drift and fractal-assumption breakage early)

**Hard invariant checks (must never fail)**
- Adjacent-band transitions only (unless `TAIL_OVERRIDE` logged).
- Scale-dependent invalidation semantics enforced.
- Parent can only change via explicit events.

**Drift dashboards (should stay within bands)**
- Per-scale: transition frequencies, completion/invalidation rates, dwell distributions by zone.
- Attempt/frustration rates at key levels (1.5, 1.618, 2.0, 1.382).
- Volatility clustering proxies (impulse autocorrelation; asymmetry of up vs down impulses).
- “Target stacking pressure” distribution vs liquidation events frequency.

**Fractal consistency checks (soft, but monitored)**
- Similarity of normalized band-transition patterns across scales (after allowing heavier tails at smaller scales).
- Scaling of “time to completion” distributions vs scale (should increase; shape should be similar).

---

## Key uncertainties and failure modes (candid)

1. **Reference frame selection is a dependency**
   - Logs are only as good as the frames. Early phases should condition on human annotations to avoid compounding swing-detection error.
   - If frames are unstable, generation will chase noise; this is why the discretizer is the first falsification surface.

2. **Too many levels vs too few**
   - Too many boundaries increases parameters and risks overfitting; too few makes decision-zone behavior unrepresentable.
   - OS1 starts with the North Star’s explicitly named “special” ratios; if that explodes complexity, the fallback is to collapse `0.9/1.0/1.1` and `0/0.1` into zones (not remove them entirely).

3. **Chop realism may require explicit attempt semantics**
   - If pure band transitions feel too “teleporty,” we’ll promote `LEVEL_TEST`/`ATTEMPT` to first-class events (still within HSMLM) rather than growing a pattern zoo.

4. **Tail modeling can become an excuse**
   - Tail overrides must remain rare and logged; if we start needing tails for everyday behavior, the core transition logic is wrong.

5. **News driver weakness**
   - Assumption: “news” is an exogenous stream of (time, polarity, intensity, TTL) that *tilts* transition and timing distributions.
   - If the news component is weak or absent, the model remains valid: internal structural tension (frustration, target stacking, exhaustion) still produces regime-like accelerations; “news” becomes just one of several modifiers rather than the sole source of motion.

---

## Appendix 1: Document synthesis

### Common threads across drafts

- **Interpretability is non-negotiable** (all drafts converge): the generator must be debuggable via explicit structural decisions, not latent vectors.
- **Fib levels are the coordinate system**: discretization should happen in ratio space relative to active swings, not in raw price space.
- **Hierarchy is causal (XL→L→M→S)**: child behavior is constrained by parent structure; “upward causation” must be explicit and rare.
- **Canonical game record + reversibility**: the discrete log should be the auditable truth; OHLC is a rendering.
- **Small-data reality**: designs that require massive training corpora are misaligned with current ground truth volume.

### The main disagreements (and why they matter)

1. **Grammar-first vs state-machine-first**
   - `discretization_approaches_c1.md` pushes a pure stochastic grammar (L-system) as the whole generator.
   - `*_o2.md`, `*_c2.md`, `*_c3.md`, `*_o1.md` prefer a Fib band/level machine with stochastic transitions.
   - Practical difference: grammars are elegant for recursion but tend to drift on precise arithmetic constraints and make OHLC inversion harder; level machines align directly with “price crossed level X.”

2. **Atomic unit: band transition vs intent/attempt vs motif**
   - Some drafts emphasize **level-to-level steps** (band transitions) as the primitive.
   - Others emphasize **intent/attempt loops** to capture decision-zone chop.
   - Others emphasize **motif templates** as macro-moves for realism.
   - OS1 treats band transitions as the canonical primitive and upgrades intent/attempt to explicit counters/events (not a separate architecture), with motifs reserved for rendering variety.

3. **How “hard” the Fib grid is**
   - `discretization_approaches_c2.md` explicitly frames Fib levels as attractors (soft), suggesting probabilistic boundaries.
   - `product_north_star.md` defines hard termination semantics (completion/invalidation) but soft preferences elsewhere.
   - OS1 resolves this by making *termination and legal transitions hard*, and everything else soft via weights.

### Blind spots / missing pieces across drafts

- **Reference frame selection and multi-reference stacking**: most drafts assume a clean “one swing per scale,” while the North Star and interview notes suggest multiple salient references and target stacking dynamics.
- **No-lookahead discipline in calibration**: several drafts gesture at “use real OHLC to learn probabilities” but don’t specify how to avoid using future behavior; OS1 makes the forward discretizer (with annotated frames) the first-class, no-lookahead artifact.
- **Drift detection and fractal assumption checks**: drafts mention realism but rarely propose concrete drift metrics and invariants as regression gates.
- **Integration with the existing repo**: some proposals are architecture-level but don’t leverage that the code already emits multi-scale swings and structural events; OS1 treats existing `ActiveSwing`/`StructuralEvent`-style semantics as the natural substrate.

### What each draft uniquely contributes (and what it misses)

- `Docs/Proposals/Drafts/discretization_approaches_o2.md`
  - **Unique**: HSMLM framing; unified oriented ratio frame; “log is the product”; maximum-entropy stance; clear layering (core vs attempt vs motif).
  - **Misses**: A sharper operational definition of episode termination and explicit drift/falsification tests (OS1 adds these).

- `Docs/Proposals/Drafts/discretization_approaches_o1.md`
  - **Unique**: Crisp engineering sequencing and “done” checklist; pragmatic Grove-style decision discipline.
  - **Misses**: Less explicit about semi-Markov timing and second-order rule mechanisms.

- `Docs/Proposals/Drafts/discretization_approaches_c2.md`
  - **Unique**: Factorization into independently learnable components; explicit “reversibility over compression”; suggests Bayesian priors and softening where needed.
  - **Misses**: T2 (“Fib as attractors”) risks undermining hard invariants unless carefully scoped; less concrete on recursion wiring and tail logging.

- `Docs/Proposals/Drafts/discretization_approaches_c3.md`
  - **Unique**: “Swing bookkeeper overlay” separation (generation vs lifecycle bookkeeping); includes a concrete implementation sketch and additional level granularity options.
  - **Misses**: More levels can expand parameters quickly; needs stronger anti-overfitting controls and clearer criteria for adding/removing boundaries.

- `Docs/Proposals/Drafts/discretization_approaches_g1.md`
  - **Unique**: The “corridor” intuition (moves define bounded paths, not straight vectors); emphasizes “struggle at levels” (attempt/reject/break) as the meaningful unit.
  - **Misses**: Less explicit about canonical log schema, replay contract, and how to keep a corridor model from becoming a hidden physics engine.

- `Docs/Proposals/Drafts/discretization_approaches_c1.md`
  - **Unique**: Strong argument for fully traceable named rules; separates grammar structure from probability tables; clear “tune by inspection” workflow.
  - **Misses**: Pure grammar as the primary engine is high risk for precise Fib arithmetic + OHLC inversion; it can also become a large handcrafted library (a different kind of overfitting) unless tightly constrained by a canonical level machine.

### How the ideas complement (and undermine) each other

- The **level/band machine** gives a shared, auditable coordinate system and makes inversion straightforward; the **intent/attempt lens** restores decision-zone realism; **motifs** add variety in rendering *after* causality is decided.
- Pure **grammar-first** approaches complement the system as a way to author higher-level “macro move” templates later, but undermine OS1 if used as the canonical representation because they blur arithmetic constraints and complicate regression testing.

---

