# The Dual Frame Proposal

**A Two-Phase Discretization for Market Structure and Path Rendering**

*From the Resonance Panel — 16 December 2025*

---

## Executive Summary

### The Recommendation

**Discretize market data into two interlocking representations: a sparse Structural Log of decision events, and a Path Envelope for each segment that enables realistic price path generation.**

This "Dual Frame" approach addresses the fundamental tension in market discretization: structural decisions are discrete and sparse (swing completions, level tests, invalidations), while price paths between decisions are continuous and dense. Trying to force both into a single representation either loses structure (pure bar-by-bar tokenization) or loses path dynamics (pure event sequences).

### Why Dual Frame

We evaluated four paradigms:

| Paradigm | Strength | Weakness |
|----------|----------|----------|
| Token Sequence | Proven ML tooling | Loses hierarchy, requires long context |
| Hierarchical Tree | Preserves causality | Complex generation, hard to handle competing swings |
| State Machine | Explicit state, interpretable | May be rigid, single-phase generation |
| **Dual Frame** | Separates structure from path, natural two-phase generation | Two-part complexity |

Dual Frame wins because generation has two distinct questions: *What structural event happens next?* and *How does price get there?* Separating these questions enables:

1. **Sparse structural sampling**: ~50K-100K events from 6M bars, preserving hierarchy and testable predictions
2. **Dense path rendering**: Continuous stochastic processes constrained by structural endpoints and path envelopes
3. **Natural falsification**: If generated markets fail structural tests, the theory is challenged; if they fail path tests, the rendering needs work

### The Core Components

**1. Reference Frame Stack**: At any moment, track up to 4 active reference frames (one per scale). Each frame orients price in Fibonacci coordinates, tracks level interaction history (tests, probes, outcomes), and provides context for transitions.

**2. Structural Event Log**: ~15 event types capturing structural decisions:
- `SWING_FORM`, `SWING_COMPLETE`, `SWING_INVALIDATE`
- `LEVEL_TEST`, `LEVEL_BREAK`
- `REGIME_SHIFT`, `SESSION_BOUNDARY`, `NEWS_SHOCK`

**3. Path Envelope**: For each segment between events, parameters describing how the path unfolded:
- Duration, volatility regime, path character (impulsive/grinding/choppy), extreme ratio

**4. Two-Phase Generation**:
- Phase 1: Sample next structural event from conditional distribution over frame stack
- Phase 2: Render price path using constrained stochastic process shaped by path envelope

### What This Achieves

- **Compression**: 6M bars → ~50K structural events + ~50K path envelopes
- **Interpretability**: Every component has semantic meaning from the theory
- **Generativity**: Natural two-phase process produces both structure and paths
- **Testability**: Explicit predictions about level reactions, scale constraints, frustration dynamics

### Falsifiable Predictions

The representation makes these predictions testable:
1. Transition probabilities differ by level band (ext_high completions >> mid_retrace completions)
2. L-scale behavior depends on XL position (hierarchical constraint)
3. Test count predicts invalidation (Frustration rule)
4. Path character is predictable from context

### Recommended Next Steps

1. **Build event extractor** from existing swing detection
2. **Compute path envelopes** for historical segments
3. **Measure structural statistics** — test falsifiable predictions
4. **Build minimal generator** — structural sampler + path renderer
5. **Validate iteratively** — statistical, expert, adversarial tests

### Risks

The main risk is that the theory itself is incomplete—that Fibonacci relationships and hierarchical causality don't capture enough of market dynamics. Dual Frame embraces this risk: **falsification is a feature**. If generated markets fail despite following the rules, we learn what the theory is missing.

---

## Part I: Problem Statement Synthesis

### The Fundamental Question

We face a problem that appears technical but is fundamentally epistemological: **How do we convert a continuous stream of price data into discrete symbols without destroying the very structure we hope to learn?**

This question has a hidden depth. Most discretization approaches in machine learning treat the raw data as "ground truth" and the discrete representation as a compressed approximation. But our situation is inverted. We have a *theory* about market structure—expressed in the North Star document—and the raw OHLC bars are merely shadows cast by that deeper structure. The discretization is not a compression of the bars; it is an attempt to *recover* the generative process that produced them.

This inversion matters profoundly. If we discretize the bars as they appear (tokenizing candle patterns, binning returns, encoding sequences), we capture the *output* of the market's generative process. But output is not mechanism. To build a generator that produces realistic markets, we need to capture the *mechanism itself*—the swings, levels, completions, and invalidations that constitute the market's decision-making process.

### The Riverbank Paradox

Mandelbrot famously showed that the length of Britain's coastline depends on your ruler. Use a 100km ruler and you get one number; use a 1km ruler and you get a larger number; use a 1m ruler and it grows again. The coastline has no "true" length—only scale-dependent measurements.

Markets exhibit the same property. "How big is this swing?" is not a well-formed question without specifying scale. A 50-point move on ES might be:
- A complete swing at M scale (retracement of a larger structure)
- A sub-wave within an incomplete L swing
- Noise within an XL context where the "real" moves are 500+ points

Our theory embraces this explicitly with four scales (S, M, L, XL), but discretization forces us to confront it operationally. The same price path admits multiple valid descriptions depending on which scale we privilege. There is no "correct" discretization—only discretizations that serve different purposes.

**The question becomes: what purpose does our discretization serve?**

### Three Interlocking Problems

Our discretization must solve three problems simultaneously:

**Problem 1: Measurement (Falsification)**
We need a representation that lets us ask: *Is the theory true?* Do swings really complete at 2x? Do Fibonacci levels really provide support and resistance? Do larger scales really constrain smaller scales?

This requires a representation where the theory's predictions are explicit and testable. If the representation embeds the theory's assumptions, we cannot falsify it—we can only confirm our own presuppositions.

**Problem 2: Generation (Synthesis)**
We need a representation that can be "run forward" to produce new market data. Given a discrete state, we must be able to:
1. Generate the next discrete state (structural transition)
2. Generate the price path connecting those states (intra-state dynamics)

This requires a representation with a clear *inverse mapping*—from discrete symbols back to continuous price.

**Problem 3: Validation (Discrimination)**
We need to know if generated data is "realistic." But what does realistic mean? The validation problem is itself multidimensional:
- **Statistical**: Does generated data have the right distributional properties (fat tails, volatility clustering, autocorrelation structure)?
- **Structural**: Do generated swings obey the rules (completions at 2x, retracements to fib levels)?
- **Perceptual**: Can an expert trader distinguish generated from real charts?
- **Adversarial**: Can a discriminator model separate real from generated?

### The Data Constraint

We have approximately 6 million 1-minute bars of ES data. This sounds substantial but is actually quite constrained:

- With 6M bars, fitting even 100 parameters risks overfitting (60,000 bars per parameter seems generous until you realize market regimes cluster temporally)
- The bars are highly autocorrelated—6M bars do not give us 6M independent observations
- Structural events (swing completions, invalidations) number in the thousands or tens of thousands, not millions
- Cross-ticker validation is limited: we hypothesize that NQ/BTC/Mag7 follow "similar" rules, but this similarity is itself a claim requiring verification

**Any discretization that produces more parameters than the data can constrain is presumptively wrong.**

### What Must Be Preserved

Not all information in the OHLC stream matters equally. Some information is structural (which levels were crossed, in what order, with what outcome). Some is parametric (how long it took, how volatile the path was). Some is noise (the exact wick geometry of bar 3,847,291).

Our discretization must:

1. **Preserve structural commitments**: Which swings formed, completed, or invalidated. Which levels were tested, broken, or defended. Which scale dominated the action.

2. **Capture path character**: Whether a move was impulsive or grinding. Whether a level was quickly broken or slowly absorbed. Whether volatility was expanding or contracting.

3. **Discard reconstructible detail**: The exact bar-by-bar path within a structural segment can be regenerated stochastically without loss of meaning. We do not need to memorize whether bar 47 was green or red if both the origin and destination of that segment are preserved.

### The Dual Representation Insight

Here is a key insight that the problem demands: **we need two representations working in tandem.**

**Representation A: The Structural Log**
A sparse sequence of events capturing structural commitments:
- Swing formations, completions, invalidations
- Level tests, breaches, recaptures
- Scale transitions (when a move "graduates" to the next scale)

This representation is highly compressed—perhaps 50,000-100,000 events from 6M bars. It captures *what* happened structurally.

**Representation B: The Path Envelope**
For each structural segment, metadata about the path:
- Duration (time between structural events)
- Volatility (realized range relative to structural magnitude)
- Effort (volume or time spent near levels, if available)
- Shape (impulsive, corrective, choppy)

This representation is still compressed (one record per structural segment, not per bar) but captures *how* the path unfolded.

**Generation requires both**: First, generate the next structural event (from A). Then, generate a plausible path to reach it (informed by B).

### The Circularity Trap

A final problem must be named explicitly: **our theory shapes how we identify swings, and swings are the basis for testing the theory.**

If we detect swings using Fibonacci logic, of course we'll see Fibonacci reactions—because we defined the coordinate system to make them visible. This is not validation; it is tautology.

Our discretization must either:
1. Use swing detection methods independent of Fibonacci assumptions (then test whether Fibonacci relationships emerge), or
2. Commit to the Fibonacci-based swing detection but test against *out-of-sample* level predictions, or
3. Compare against null hypotheses (alternative level ratios, randomized swings) as controls

Without circularity controls, any discretization merely confirms its own assumptions.

---

## Part II: Guiding Tenets

The following tenets are not aspirations or values—they are decision rules. Each represents a genuine tradeoff where the opposite position is defensible. When we face hard choices during implementation, these tenets break ties.

### Tenet 1: The Generator Is the Test

**We judge our discretization by whether it can generate realistic markets, not by how well it describes historical markets.**

*The opposite position*: "Descriptive accuracy is sufficient—if we capture the patterns in historical data, generation will follow naturally."

*Why we reject it*: Description and generation are different problems. A highly descriptive representation might capture historical patterns perfectly but be useless for generation if it lacks the causal structure needed to "run forward." Example: recording that "ES dropped 50 points on March 15, 2023" is perfectly descriptive but gives no generative power. We prioritize generative capacity over descriptive fidelity.

*How this tiebreaks*: When choosing between a representation that fits historical data better and one that has clearer generative mechanics, choose the latter.

### Tenet 2: Levels Are Coordinates, Not Predictions

**Fibonacci levels define the coordinate system in which we measure market behavior. They are not themselves predictions about price movement.**

*The opposite position*: "Fibonacci levels should be treated as predictions—if price reaches the 1.618 level, we predict it will bounce."

*Why we reject it*: Conflating coordinates with predictions creates unfalsifiable circularity. Instead, we use levels as *reference frames* for measuring what actually happens. The prediction is not "price will bounce at 0.618" but "when price reaches 0.618, it will either bounce, consolidate, or break—and the distribution over these outcomes has specific, testable properties."

*How this tiebreaks*: When designing the representation, encode level position as state information, not as outcome prediction. Test predictions against the distribution of outcomes at levels, not against whether individual levels "worked."

### Tenet 3: Structure Dominates at Large Scales, Noise Dominates at Small

**As scale increases, deterministic structure should increasingly dominate stochastic noise. As scale decreases, noise is acceptable and even expected.**

*The opposite position*: "All scales should be modeled with equal precision—noise at small scales is just structure we haven't captured yet."

*Why we reject it*: This would require unbounded model complexity. The theory itself suggests that small-scale moves have "more room for extreme behavior" because they are less constrained by structure. We embrace this: large-scale events (XL swing completions, L invalidations) should be highly predictable given context; small-scale events (S-level wiggles) can be stochastic within structural bounds.

*How this tiebreaks*: When setting model parameters, allocate complexity budget to large-scale accuracy over small-scale precision. Accept that generated S-scale paths may look "different" from historical paths while insisting that XL-scale behavior matches statistical properties.

### Tenet 4: Causality Flows Downward (Mostly)

**Larger scales constrain smaller scales, not vice versa. When there appears to be "bottom-up" causality, model it as the larger scale being in an unstable state that small perturbations can trigger.**

*The opposite position*: "Markets are bidirectional—small moves can cascade up into large moves, so causality flows both ways equally."

*Why we reject it*: The theory is explicit that big moves drive small moves. "GameStop moments" where small-scale activity creates large-scale structure are real but rare—and they're better modeled as the large scale being in a fragile state (stacked targets, exhaustion) where small events act as triggers. The discretization should make large-scale state explicit so that these fragilities can be represented.

*How this tiebreaks*: When designing state representation, large-scale state is *input* to small-scale dynamics, not derived from aggregating small-scale events. When modeling transitions, condition smaller-scale transitions on larger-scale context.

### Tenet 5: No Lookahead, Even for Labels

**Every discrete label must be computable from information available at or before the labeled moment. Future information cannot "clean up" past labels.**

*The opposite position*: "It's acceptable to use future bars to determine what 'really happened'—this gives cleaner labels and better training signal."

*Why we reject it*: A representation that requires lookahead for labeling cannot be used for generation. If we need bar t+10 to decide what happened at bar t, we cannot generate bar t+1 from bar t. Lookahead creates a fatal disconnect between training (offline, full visibility) and inference (online, causal).

*How this tiebreaks*: When there's ambiguity about whether a swing has formed or a level has been tested, the discretization must reflect that ambiguity rather than resolve it with future information. Uncertainty at time t should be represented as uncertainty, not retroactively corrected.

### Tenet 6: Sparse Events, Dense Paths

**Structural events (swing formations, completions, level tests) should be sparse and precisely defined. Path dynamics between events should be densely parameterized but stochastically generated.**

*The opposite position*: "Every bar should have equal representational weight—a unified representation across all granularities."

*Why we reject it*: Not all bars are equally informative. Bar 3,847,291 in the middle of a consolidation carries little structural information. But the bar where a swing completes is a decision point. Our representation should be sparse where the market is "between decisions" and detailed where structural commitments are made.

*How this tiebreaks*: The event vocabulary should be small (tens of event types, not thousands). Path generation between events should use continuous models (Brownian motion with drift, constrained random walks) rather than discrete per-bar tokens.

### Tenet 7: Falsification Over Flexibility

**Design the representation to make the theory testable, even if this limits what patterns we can capture.**

*The opposite position*: "Add degrees of freedom until the model can capture any pattern—we can always prune later."

*Why we reject it*: A model flexible enough to capture any pattern cannot falsify the theory. We want a representation where, if the theory is wrong, the model *fails visibly*. If generated markets don't complete at 2x, or don't respect fib levels, or don't show scale-dependent structure, we want to know—not have the model paper over these failures with learned exceptions.

*How this tiebreaks*: When the model fits poorly, ask whether the theory is wrong before adding parameters. Prefer to surface prediction errors rather than absorb them into learned corrections.

---

## Part III: Virtual Expert Consultation

*To explore the problem space, we convene a panel of thinkers whose frameworks bring orthogonal perspectives to market structure and representation.*

### The Resonance Panel

I call this panel "Resonance" because its members share a common thread: they all studied how complex systems organize themselves, how patterns emerge and propagate, and how information flows through hierarchical structures. Each brings a distinct lens:

1. **Gregory Bateson** (1904-1980) — Anthropologist and cyberneticist who studied "the pattern which connects." Expert on hierarchy, recursion, and how information creates difference.

2. **Ilya Prigogine** (1917-2003) — Nobel laureate in chemistry who studied dissipative structures—systems far from equilibrium that maintain order through constant energy flow.

3. **Per Bak** (1948-2002) — Physicist who developed the theory of self-organized criticality, showing how systems naturally evolve to critical states where small events can trigger cascades.

4. **John Holland** (1929-2015) — Computer scientist who pioneered complex adaptive systems and genetic algorithms, studying how systems learn and evolve.

5. **Nassim Taleb** (1960-) — Practitioner and philosopher of uncertainty, fat tails, and robustness. Skeptic of naive models, advocate for antifragility.

6. **Jesse Livermore** (1877-1940) — Legendary speculator whose trading rules anticipated modern market structure concepts. The voice of practical experience.

---

### Session 1: On the Nature of Market Structure

**Bateson**: You speak of "swings" and "levels" as if they were objects in the world. But they are not objects—they are differences that make a difference. A swing high is not the price; it is the *information* that price reversed there. Your discretization should not catalog prices; it should catalog *meaningful differences*.

**Livermore**: The old man is right, in his way. I never cared what the price was—I cared what it *meant*. A stock at $50 dropping to $48 means nothing. A stock at $50 that had been $30 six weeks ago and then dropped to $48? That means something. The pivot is not the price but the context.

**Prigogine**: You are describing a dissipative structure. The market is far from equilibrium—money flows in, information flows in, and structure emerges to process that flow. Your levels are not static markers; they are *attractors* in a dynamic system. Price doesn't "respect" levels; price is drawn toward them because that's where the structure dissipates imbalances.

**Bak**: This is self-organized criticality in action. The market evolves to states where small events can trigger large responses—precisely because participants optimize until the system is critical. Your "support" and "resistance" levels are the edges of sandpile slopes. Add one more grain—one more order—and you get either nothing or an avalanche. The distribution is power-law, not Gaussian.

**Taleb**: And this is exactly why your model will fail if you train it on average behavior. The market is not the average; the market is the tail. If your discretization cannot represent "two-level jump without retest," you will build a turkey that thinks life is normal right up until Thanksgiving.

**Holland**: You're all describing different aspects of an adaptive system. The market has many agents with different strategies, different time horizons, different information. They're all adapting to each other. Your levels "work" not because of magic numbers but because enough agents believe in them—and that belief creates the structure. But beliefs evolve. What worked in 2010 may not work in 2025.

**Bateson**: Yes! The map is not the territory, but the map affects the territory when the agents use the map. Your Fibonacci levels are not discovered; they are *co-created* by the theory and the theorists. This is not a criticism—all measurement is like this. But it means your test must ask not "are fibs true?" but "does the system behave *as if* fibs matter?"

---

### Session 2: On Representation and Compression

**Livermore**: Can we cut the philosophy and talk about what matters? When I traded, I cared about three things: Where is the pivot? What's the trend? How is the action—is it behaving right or wrong? Your discretization should answer these questions, nothing more.

**Taleb**: I agree with the speculator. You're building a model with limited data. Every variable you add is a coffin nail. What's the minimal representation that captures what matters? Not what's mathematically elegant—what actually matters for the thing you're trying to do.

**Prigogine**: The minimal representation depends on what you want to predict. If you want to predict next bar's close, you need dense microstructure. If you want to predict structural transitions—completions, invalidations—you need the hierarchy of attractors. These are different questions requiring different representations.

**Bak**: And don't forget the distribution of event sizes. Your representation must capture that most moves are small and some are huge. If you discretize into fixed-size bins, you lose the power-law structure that makes markets what they are.

**Holland**: Here's a practical suggestion: think about what your generator needs to *decide*. At each step, what choices does it face? Design your representation around those decision points. If the generator doesn't need to know whether bar 47 was a doji, don't encode that information.

**Bateson**: The recursive structure is key. A swing is made of sub-swings which are made of sub-sub-swings. The information at each level is *about* the level below. Don't flatten this into a sequence—preserve the hierarchy. Let each level describe *patterns of patterns*.

---

### Session 3: On Generation and Validity

**Livermore**: The test is simple: would I trade it? Show me a generated chart. If I can tell it's fake, your model has failed. The tape doesn't lie, and neither do my instincts.

**Taleb**: Livermore's gut is a good test, but insufficient. You also need statistical tests—but the right ones. Don't test whether means and variances match. Test whether the tails match. Test whether volatility clusters. Test whether drawdowns have the right duration distribution. These are the fingerprints.

**Prigogine**: Test whether the structure is stable. A dissipative structure maintains itself through flows. If your generated market slowly loses structure—levels become meaningless, swings become random—then you've lost the dynamics that maintain order. The generated market should be in a *steady state* of structure, not decaying toward randomness.

**Bak**: Test for criticality. Real markets show power-law distributions in event sizes, and temporal clustering. Generate a long series and measure these. If they match, you're capturing something real. If they don't, you've built a toy.

**Holland**: Here's the adversarial test: train a classifier to distinguish real from generated. Use the classifier's failures as a guide—what features is it using to tell them apart? Then improve those features in your generator. Iterate until the classifier can't do better than chance.

**Bateson**: But be careful of the final test. If your discriminator succeeds by finding superficial differences (timestamp patterns, specific price ranges), fixing those doesn't mean your structure is right. The discriminator should force you to improve structure, not surface features.

---

### Session 4: On the Dynamics of Levels

**Livermore**: A level is not a line on a chart. It's a battlefield. When price approaches a level, there's a fight. You can see it in the tape—the stuttering, the probes, the volume. Sometimes bulls win, sometimes bears win. Your model needs to capture this fight, not just the outcome.

**Prigogine**: The fight is the dissipation. Energy (money, conviction) accumulates at the level and must be resolved. The outcome depends on which side exhausts first. Your representation should track this accumulation—time at level, failed attempts, volume absorbed—not just whether the level held or broke.

**Bak**: And the resolution can cascade. Breaking one level doesn't just mean price moves—it means the entire structure shifts. Stops are hit, new orders are placed, the potential landscape reconfigures. Your state machine must represent these cascade possibilities.

**Taleb**: The cascades are where models die. They train on normal behavior and fall apart when the cascade happens. Your representation must have explicit hooks for extreme events—not as outliers to be smoothed away but as essential structure to be modeled.

**Holland**: The cascade is emergence. It's not predictable from the local rules alone—it's a phase transition. Your model should have *qualitatively different regimes*: the normal grinding, the breakout, the panic. Trying to model all of these with one set of parameters is a category error.

**Bateson**: The levels create a logical hierarchy. The 2x level of a swing is qualitatively different from the 0.618 level—not just quantitatively. Your representation should encode this qualitative difference. Breaking 2x *means* something different from testing 0.618.

---

### Session 5: On Time and Duration

**Livermore**: Time is everything and nothing. A stock that takes three weeks to drop is different from one that drops in three days, even if the points are the same. But you can't just count bars—some bars are full of action, some are dead time.

**Prigogine**: Time in dissipative systems is not clock time; it's *process time*—the time for the system to dissipate accumulated imbalances. In quiet markets, a day might be one "unit" of process time. In fast markets, an hour might be ten units. Your representation needs internal time, not external time.

**Bak**: The waiting time between events is part of the criticality signature. In critical systems, there's no characteristic timescale—waiting times are power-law distributed. If your model generates events at regular intervals, it's not capturing the burstiness of real markets.

**Holland**: Build time into your representation, but as *relative* time—time since last event, time at current level, time in current regime. Absolute timestamps are rarely useful; relative durations are what drive behavior.

**Taleb**: And beware the calendar. Overnight gaps, weekend gaps, holiday gaps—these are regime changes, not missing data. Your discretization should mark these discontinuities explicitly. Don't let your model think Saturday is just two more bars of quiet.

**Bateson**: Time is the context in which patterns unfold. A pattern that takes three days is *constituted differently* from the same price pattern in three hours—even if the points match. The duration is part of the meaning, not a secondary attribute.

---

## Part IV: Deliberation on Options

### Synthesizing the Expert Input

The Resonance panel surfaced several key insights that constrain our design space:

**From Bateson**: Discretize differences, not things. Swings are not objects; they are information about reversal. Preserve the recursive structure—patterns of patterns.

**From Prigogine**: Levels are attractors in a dynamic system. The market dissipates imbalances at levels. Track accumulation (time, volume, attempts) not just outcomes.

**From Bak**: The system is critical. Power-law distributions in event sizes and waiting times are essential signatures. Don't model averages; model the criticality.

**From Holland**: Design around decision points. What does the generator need to decide? Don't encode information the generator won't use.

**From Taleb**: Model the tails explicitly. Include shock representation. Don't build a turkey.

**From Livermore**: What matters is pivot, trend, and "how is the action?" Keep it simple. The test is: would I trade it?

### The Fundamental Design Choices

Integrating these perspectives, we face three fundamental design choices:

**Choice 1: Representation Paradigm**

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **Sequence** | Market as a stream of tokens (events, bars) | Simple, proven ML; loses hierarchy |
| **Tree** | Market as nested structure (swings contain sub-swings) | Preserves hierarchy; complex generation |
| **State Machine** | Market as state vector with transitions | Explicit state; may be rigid |
| **Dual (Proposed)** | Structural log + path envelope | Generatively native; two-part complexity |

The existing Consilience Cascade proposal recommends State Machine. I propose extending this with an explicit **dual representation**:

1. **Structural Log**: A sparse sequence of structural events (swing births, level tests, completions, invalidations). This captures *what* happened.

2. **Path Envelope**: For each structural segment, parameters describing *how* the path unfolded (duration, volatility regime, effort at levels).

Why dual? Because generation requires both deciding *what* happens next (sample from structural transition distribution) and rendering *how* it happens (generate price path satisfying those constraints).

**Choice 2: Coordinate System**

How do we represent price position?

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **Absolute** | Price in dollars/points | Simple; no structural context |
| **Relative** | Price as % of range | Context-aware; which range? |
| **Fib-Oriented** | Price as position in level grid | Theory-aligned; assumes fib validity |

The theory demands Fib-Oriented coordinates. A price of 5847.25 means nothing. A price "at the 0.618 retracement of the active L bull swing" is information that can guide generation.

**Key insight**: We need *multiple simultaneous coordinate systems*—one per active swing. Price position is not a scalar but a vector: [position in XL swing, position in L swing, position in M swing, position in S swing].

**Choice 3: Level Dynamics**

How do we represent the "battlefield" at levels?

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **Binary** | Level held or broke | Simple; loses dynamics |
| **Count** | Number of tests before resolution | Captures persistence; coarse |
| **Full dynamics** | Time at level, volume, probe depth, outcome | Rich; many parameters |

Given data constraints, I propose a middle path: **Test Counts with Outcome**.

Track:
- Number of tests (approaches within tolerance)
- Maximum probe depth (how far past the level before rejection)
- Resolution (held, broke, absorbed)
- Duration (bars spent near level)

This captures Livermore's "fight" and Prigogine's "accumulation" without requiring tick data.

---

### The Dual Frame Proposal

Synthesizing the above, I propose a discretization called **Dual Frame** with the following components:

#### Component 1: Reference Frame Stack

At any moment, maintain a stack of active reference frames—one per scale with an active swing:

```
Frame = {
    scale: XL | L | M | S,
    direction: bull | bear,
    anchor: {high_price, high_bar, low_price, low_bar},
    current_level: 0.382 | 0.5 | 0.618 | ... | 2.0,
    level_history: [(level, test_count, probe_depth, outcome), ...],
    impulse: size / duration,
    formation_bar: int
}
```

The **current_level** is defined by which Fibonacci band currently contains price. Bands are:

```
Below 0:     "Violated" (swing invalid)
0 to 0.382: "Deep retracement"
0.382 to 0.5: "Mid retracement"
0.5 to 0.618: "Shallow retracement"
0.618 to 1:   "Origin zone"
1 to 1.382:   "Extension low"
1.382 to 1.618: "Decision zone"
1.618 to 2:   "Extension high"
Above 2:      "Completion"
```

This gives 8-9 discrete positions per swing. With 4 scales × 2 directions × 8 positions, the structural state has ~60 dimensions before considering combinations—but most combinations are empty (no active swing at that scale/direction).

#### Component 2: Structural Event Log

The discrete event vocabulary:

```
SWING_FORM(scale, direction, anchor_prices)
    - A new swing has been validated

LEVEL_TEST(scale, level, test_count, probe_depth)
    - Price entered a level band and probed beyond it

LEVEL_BREAK(scale, level, break_type: clean | violent | grind)
    - Price moved through a level decisively

SWING_COMPLETE(scale)
    - Price closed above 2x (bull) or below 2x (bear)

SWING_INVALIDATE(scale, severity: shallow | deep)
    - Price violated the swing's protected point

NEWS_SHOCK(polarity: bull | bear, intensity: 1-5)
    - Exogenous catalyst (for future integration)

REGIME_SHIFT(from_regime, to_regime)
    - Market character changed (trending, ranging, crisis)
```

This gives ~15 event types with parameters. The structural log is a sequence of these events, sparse relative to bars.

#### Component 3: Path Envelope

For each structural segment (between events), store:

```
PathEnvelope = {
    duration_bars: int,
    volatility_regime: low | normal | high | extreme,
    path_character: impulsive | grinding | choppy,
    volume_profile: front_loaded | even | back_loaded,  # if available
    extreme_ratio: max_excursion / segment_range
}
```

This is ~5 parameters per segment. With perhaps 50,000 structural events across 6M bars, this adds 250K parameters—but these are descriptive, not learned.

#### Component 4: The Generation Algorithm

Generation proceeds as a two-phase process:

**Phase 1: Structural Sampling**
Given current Reference Frame Stack, sample the next structural event:
```
P(next_event | frame_stack, path_context)
```

This distribution is learned from historical data. The theory provides constraints:
- Swings in "Extension high" zone are likely to complete or pull back
- Swings with many failed level tests are likely to invalidate (Frustration rule)
- Larger scale events take precedence

**Phase 2: Path Rendering**
Given the structural event and path envelope parameters, generate the actual bar sequence:
```
bars = render_path(from_state, to_event, path_envelope)
```

This can use constrained Brownian motion, Ornstein-Uhlenbeck processes, or other continuous stochastic models. The key is that the path must:
- Start at the current price
- End at a price consistent with the structural event
- Have volatility consistent with the envelope
- Respect any intermediate levels

---

### Addressing the Core Problems

**Problem 1 (Measurement/Falsification)**

The dual frame representation makes the theory's predictions explicit:
- "Swings complete at 2x" → Measure: what % of swings that reach Extension High continue to Completion?
- "Levels provide reactions" → Measure: when price enters a level band, what's the distribution over (test, break, reverse)?
- "Larger scales constrain" → Measure: conditional on XL position, does L behavior differ?

These are testable against historical data and against generated data.

**Problem 2 (Generation)**

The two-phase generation is designed for invertibility:
- Phase 1 produces discrete structural trajectories
- Phase 2 renders those trajectories as continuous price paths
- The path envelope provides sufficient statistics for Phase 2 without requiring memorization

**Problem 3 (Validation)**

Multiple validation criteria:
- **Structural**: Do generated swings complete/invalidate at theory-predicted rates?
- **Statistical**: Do generated returns have correct fat-tail and clustering properties?
- **Expert**: Can Livermore (or his modern equivalent) tell it's fake?
- **Adversarial**: Train discriminator on (real, generated) pairs; iterate until chance-level

---

### What This Proposal Does Differently

Compared to the existing Consilience Cascade proposal, Dual Frame:

1. **Separates structure from path**: The Cascade proposes a single state machine. Dual Frame explicitly separates structural decisions (discrete) from path rendering (continuous). This makes generation more natural.

2. **Multiple simultaneous frames**: Rather than tracking one state, we track a stack of frames—one per active swing. This captures the "competing swings" dynamic mentioned in the North Star.

3. **Level dynamics as first-class**: The "test count + probe depth + outcome" representation captures Livermore's "battlefield" insight without requiring tick data.

4. **Path envelope**: The explicit path parameterization (volatility regime, character, extreme ratio) allows rendered paths to vary in character while respecting structural constraints.

5. **Regime as separate dimension**: The REGIME_SHIFT event acknowledges that markets have qualitatively different modes (Taleb's turkeys, Holland's different regimes) rather than trying to model all behavior with one set of parameters.

---

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Frame stack becomes too complex | Cap at 4 active frames (one per scale); older frames archived |
| Path rendering produces implausible bars | Constrain with market-realism checks (no negative prices, reasonable gap sizes, tick quantization) |
| Structural transitions are too sparse for learning | Augment with synthetic data from simplified models; transfer learning from related instruments |
| Theory is fundamentally wrong | Falsification is a feature. If generated data fails structural tests despite following rules, the theory needs revision |
| Level dynamics require parameters we can't estimate | Start with simple (binary hold/break); add dynamics only if validation demands |

---

### Comparison with Alternatives

| Aspect | Dual Frame | State Machine (Cascade) | Token Sequence |
|--------|------------|------------------------|----------------|
| Hierarchy | Explicit (frame stack) | Explicit (state vector) | Implicit |
| Generation | Two-phase (structure + path) | Single-phase | Autoregressive |
| Level dynamics | Test counts + outcome | Level in state | Token per test |
| Path variation | Envelope-constrained continuous | Rule-based | Learned per-bar |
| Complexity | Medium | Medium | High |
| Interpretability | High | High | Low |

All three approaches have merit. Dual Frame distinguishes itself by:
- Making the structure/path separation explicit
- Treating levels as battlefields, not just thresholds
- Providing a natural two-phase generation process

---

## Part V: Recommendation

### The Synthesis

After consulting the Resonance panel and deliberating on options, a clear recommendation emerges:

**Discretize the market as a dual representation: a sparse Structural Log of decision events, plus a Path Envelope for each segment that enables continuous path rendering.**

This is not a compromise between alternatives. It is a recognition that the generation problem has two distinct parts—*what* structural transition happens, and *how* the price path realizes it—and these parts demand different representations.

### The Complete Dual Frame Specification

#### State Representation

At any moment, the market state consists of:

**1. Reference Frame Stack** (up to 4 active frames)
```python
@dataclass
class ReferenceFrame:
    scale: Literal["XL", "L", "M", "S"]
    direction: Literal["bull", "bear"]
    high_price: float
    high_bar: int
    low_price: float
    low_bar: int
    current_level_band: Literal[
        "violated", "deep_retrace", "mid_retrace", "shallow_retrace",
        "origin", "ext_low", "decision", "ext_high", "complete"
    ]
    level_history: List[LevelInteraction]
    impulse: float  # size / formation_bars
    formation_bar: int

@dataclass
class LevelInteraction:
    level: float  # 0.382, 0.5, etc.
    test_count: int
    max_probe_depth: float  # % past level before rejection
    resolution: Literal["held", "broke", "absorbed", "pending"]
    bars_at_level: int
```

**2. Global Context**
```python
@dataclass
class MarketContext:
    regime: Literal["trending", "ranging", "volatile", "crisis"]
    session: Literal["pre_market", "regular", "post_market", "overnight"]
    calendar: Optional[str]  # "FOMC", "CPI", "NFP", etc.
    bars_since_regime_change: int
```

#### Event Vocabulary

The structural event types:

```python
class EventType(Enum):
    SWING_FORM = "swing_form"           # New swing validated
    LEVEL_TEST = "level_test"           # Approach + probe of level
    LEVEL_BREAK = "level_break"         # Decisive move through level
    SWING_COMPLETE = "swing_complete"   # 2x reached
    SWING_INVALIDATE = "swing_invalid"  # Protected point violated
    REGIME_SHIFT = "regime_shift"       # Market character changed
    SESSION_BOUNDARY = "session_bound"  # Market open/close/gap
    NEWS_SHOCK = "news_shock"           # Exogenous catalyst

@dataclass
class StructuralEvent:
    event_type: EventType
    bar_index: int
    scale: Optional[str]  # For swing-related events
    parameters: Dict[str, Any]  # Type-specific details
```

#### Path Envelope

For each segment between structural events:

```python
@dataclass
class PathEnvelope:
    duration_bars: int
    volatility_regime: Literal["low", "normal", "high", "extreme"]
    path_character: Literal["impulsive", "grinding", "choppy", "balanced"]
    extreme_ratio: float  # max_excursion / segment_range
    # Optional if volume available:
    volume_profile: Optional[Literal["front", "even", "back"]]
```

### The Discretization Pipeline

**Input**: 6M bars of ES-1m OHLC (+ existing swing detection output)

**Step 1: Extract Reference Frames**
- Use existing SwingDetector output for swing identification
- For each bar, compute which frames are active and their current level bands
- Track level interactions (tests, probes, outcomes)

**Step 2: Identify Structural Events**
- Walk through bars, emitting events when:
  - New swing validates (from SwingDetector)
  - Level band changes (with test count, probe depth)
  - Swing completes or invalidates
  - Session boundaries or calendar events occur

**Step 3: Compute Path Envelopes**
- For each segment between events:
  - Count bars (duration)
  - Classify volatility regime (vs. rolling average)
  - Classify path character (momentum, mean-reversion, noise)
  - Compute extreme ratio

**Output**:
- `structural_log.json`: Sequence of ~50K-100K events
- `path_envelopes.json`: One envelope per event pair
- `frame_snapshots/`: Reference frame state at each event

### The Generation Pipeline

**Input**: Initial state (from historical snapshot or random consistent state)

**Step 1: Sample Next Event**
```
event = sample(P(event | frame_stack, context, path_history))
```

The conditional distribution is estimated from historical structural log. Key factors:
- Current level band (swings in "ext_high" likely complete or pull back)
- Level interaction history (many tests → frustration)
- Larger-scale context (XL position constrains L options)
- Time since last event (burstiness)

**Step 2: Render Path**
```
bars = render_path(
    start_price=current_price,
    end_event=event,
    envelope=sample_envelope(event_type, context)
)
```

Path rendering uses constrained stochastic process:
- Start at current price
- End at price consistent with event (e.g., for LEVEL_BREAK at 1.618, end price is above that level)
- Volatility scaled to envelope's regime
- Character shapes the path (impulsive = directional, grinding = slow progress, choppy = two-way)

**Step 3: Update State**
- Apply event to frame stack
- Update level histories
- Check for cascade effects (e.g., L completion may invalidate S swings)
- Update context if regime shift detected

**Step 4: Iterate**
- Continue until target bar count reached

### Validation Criteria

**Structural Validation**
| Metric | Target | How to Measure |
|--------|--------|----------------|
| Completion rate | Match historical | % of swings reaching ext_high that complete |
| Invalidation rate | Match historical | % of swings that invalidate (by severity) |
| Level reaction rate | Match historical | % of level tests that result in (hold, break, absorb) |
| Frustration rate | Match historical | % of swings with 3+ failed tests that invalidate |

**Statistical Validation**
| Metric | Target | How to Measure |
|--------|--------|----------------|
| Return distribution | Fat tails match | Compare tail exponents (real vs. generated) |
| Volatility clustering | ACF match | Autocorrelation of squared returns |
| Drawdown distribution | Duration match | Distribution of drawdown lengths |
| Inter-event waiting times | Power-law | Test for power-law vs. exponential |

**Expert Validation**
- Show generated charts to experienced trader
- Ask: "Would you trade this? Can you tell it's synthetic?"
- Iterate until expert consistently confused

**Adversarial Validation**
- Train discriminator on (real_window, generated_window) pairs
- Use discriminator gradients to identify weak points
- Target: discriminator at chance level (50% accuracy)

### Falsifiable Predictions

The Dual Frame representation makes these predictions testable:

**Prediction 1**: Conditional transition probabilities differ by level band
- If true: P(complete | ext_high) >> P(complete | mid_retrace)
- If false: Level bands don't provide predictive information; theory weakened

**Prediction 2**: Larger scales constrain smaller scales
- If true: L-scale behavior should differ based on XL position
- If false: Scales are independent; hierarchical causality claim falsified

**Prediction 3**: Level test count predicts outcome
- If true: More tests → higher invalidation probability (Frustration rule)
- If false: Level persistence is noise; Frustration rule falsified

**Prediction 4**: Path character is predictable from context
- If true: Impulsive paths more common after prolonged consolidation
- If false: Path character is independent of context; reduces generation quality

### Implementation Phases

**Phase 1: Event Extraction (2 issues)**
- Build structural event extractor from existing swing detection
- Compute level band transitions and interactions
- Output: `structural_log.json` for historical data

**Phase 2: Path Analysis (1 issue)**
- Compute path envelopes for historical segments
- Classify volatility regimes, path characters
- Output: `path_envelopes.json`

**Phase 3: Measurement (1 issue)**
- Compute structural statistics from historical log
- Test falsifiable predictions against historical data
- Output: Validation report with pass/fail per prediction

**Phase 4: Generator v0 (2 issues)**
- Build structural sampler (simple conditional probabilities)
- Build path renderer (constrained Brownian bridge)
- Output: Basic synthetic OHLC

**Phase 5: Validation Loop (ongoing)**
- Run statistical + expert + adversarial validation
- Identify weakest components
- Iterate

### What This Enables

If Dual Frame succeeds:

1. **Measurement**: We can ask (and answer) whether the North Star rules hold statistically
2. **Generation**: We can produce unlimited synthetic market data for training, testing, and gamification
3. **Falsification**: If generation fails despite following rules, we have clear evidence the theory needs revision
4. **Extension**: The framework accommodates future additions (news model, order flow) without restructuring

If Dual Frame fails:

1. **Learning**: We discover which aspects of market structure the theory misses
2. **Direction**: Failure modes point toward theory revision
3. **Not catastrophic**: The discretization infrastructure remains useful for alternative theories

---

## Part VI: Final Considerations

### Why "Dual Frame"?

The name captures the essence:
- **Dual**: Two interlocking representations (structure + path)
- **Frame**: Reference frames that orient price in meaningful coordinates

Each swing creates a "frame" through which price action is interpreted. Multiple frames coexist, creating a rich, multi-scale context. The duality acknowledges that markets have both discrete structure (events) and continuous dynamics (paths).

### What We're Betting On

This proposal bets that:

1. **Markets have structure** — not random walks but organized behavior around levels
2. **Structure is hierarchical** — large scales constrain small scales
3. **Structure is sparse** — most bars are "between decisions"; decisions themselves are rare
4. **Paths are secondary** — the route matters less than the destination
5. **The theory is testable** — if wrong, we'll see it in the validation metrics

These are strong claims. The proposal is designed to either vindicate them or expose their failures clearly.

### The Invitation

This proposal is one voice among several exploring the discretization problem. It complements rather than contradicts the Consilience Cascade proposal—both see state machines with hierarchical structure as the right paradigm. Dual Frame's contribution is to:

1. Make the structure/path separation explicit
2. Treat levels as dynamic battlefields
3. Provide a natural two-phase generation process

The ultimate test is not which proposal is most elegant but which produces markets that pass validation. I propose Dual Frame as a candidate worth implementing and testing.

---

## Appendix A: The Resonance Panel

### Panel Members

| Expert | Dates | Contribution |
|--------|-------|--------------|
| **Gregory Bateson** | 1904-1980 | "The pattern which connects" — hierarchy, recursion, information as difference |
| **Ilya Prigogine** | 1917-2003 | Dissipative structures, far-from-equilibrium dynamics, self-organization |
| **Per Bak** | 1948-2002 | Self-organized criticality, power laws, avalanche dynamics |
| **John Holland** | 1929-2015 | Complex adaptive systems, genetic algorithms, emergence |
| **Nassim Taleb** | 1960- | Fat tails, antifragility, robustness under uncertainty |
| **Jesse Livermore** | 1877-1940 | Practical market structure, pivots, tape reading |

### Why "Resonance"

The panel members share a common thread: they all studied how complex systems organize themselves, how patterns emerge and propagate, and how information flows through hierarchical structures. The name "Resonance" captures their shared insight that markets are not random—they exhibit organized structure that emerges from the interaction of many agents operating at different scales. Like resonance in physics, where systems naturally vibrate at certain frequencies, markets naturally organize around certain levels and transitions.

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Reference Frame** | A coordinate system defined by an active swing, orienting price relative to Fibonacci levels |
| **Structural Event** | A discrete decision point: swing formation, level test, completion, invalidation |
| **Path Envelope** | Parameters describing how price moved between structural events |
| **Level Band** | Discrete zone between Fibonacci levels (e.g., "deep_retrace" = 0 to 0.382) |
| **Level Interaction** | The history of tests, probes, and outcomes at a specific level |
| **Frame Stack** | The set of active reference frames across all scales |
| **Dual Representation** | The pairing of structural log (what happened) with path envelopes (how it happened) |

---

## Appendix C: Relationship to Existing Proposals

This proposal builds on and complements the Consilience Cascade proposal:

| Aspect | Consilience Cascade | Dual Frame |
|--------|---------------------|------------|
| Core paradigm | State machine | State machine + path envelope |
| Hierarchy | State vector per scale | Frame stack with interaction history |
| Level treatment | Level as state component | Level as battlefield with dynamics |
| Generation | Single-phase (rules + parameters) | Two-phase (structure sampling + path rendering) |
| Path variation | Rule-based transitions | Envelope-constrained continuous processes |

Both proposals agree on:
- State machine as core paradigm
- Explicit hierarchical structure (XL → L → M → S)
- Fibonacci levels as coordinate system
- Sparse event representation
- Theory-driven structure with data-driven parameters

Dual Frame extends Cascade by:
- Making structure/path separation explicit
- Adding level interaction dynamics
- Providing path envelopes for rendering variation

---

*Prepared by the Resonance Panel*
*Proposal: Dual Frame*
*Claude Opus 4.5 — 16 December 2025, 12:45 UTC*
