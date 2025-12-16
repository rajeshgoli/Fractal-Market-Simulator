# EventLattice: An Oriented Structural Event Language for Fractal Market Simulation

Discretize OHLC into auditable multi-scale commitments (levels crossed, swings resolved, effort spent) so the theory can be falsified and the generator can be built without black boxes.

## Executive summary

I recommend discretizing ES-1m OHLC into an **Oriented Lattice Event Log (O-LEL)**: a sparse, replayable event stream of **level crossings, completions, invalidations, and swing lifecycle events** computed in **oriented reference frames** defined by the active reference swings at S/M/L/XL scales. Attach two small side-channels—**effort** (time/volume/range spent inside a band) and **shock** (multi-level jumps, range multiples)—to preserve Wyckoff-style “work” and Taleb-style tails without exploding the alphabet.

This representation is the best fit for the project because it:
- Matches the North Star ontology (swings + Fibonacci lattice + recursion) and stays interpretable.
- Is causal/no-lookahead and therefore transferable to generation.
- Compresses 6M bars into “commitments” rather than “pixels,” enabling empirical measurement of the theory with few degrees of freedom.

Alternatives (per-bar tokens, swing-only compression, full parse trees) either miss the causal objects, lose path/effort information, or add complexity before we can even measure hypotheses.

## Project proposal

**Goal:** Build a batch discretization pipeline that converts `OHLCV + detected swings → structural event log` suitable for empirical hypothesis testing and later simulation rendering.

**In scope (Milestone 1)**
- `ReferenceFrame` (oriented ratio()/price() per swing)
- `LevelSet` (small, explicit ratio lattice; tick-quantized)
- `Event schema` (`LEVEL_CROSS`, `COMPLETION`, `INVALIDATION`, `SWING_OPEN/CLOSE`) + effort/shock fields
- `Discretizer` (bar-by-bar across S/M/L/XL aggregations using existing swing state semantics)
- `Log I/O` (JSONL + optional shared swing table)
- `Visual overlay` (event marks on charts for sanity checks)
- `Validation` on a handful of diverse windows + replay determinism

**Out of scope (future milestones)**
- Parameter estimation beyond simple counts/tables
- Generator v0, discriminator, or news integration (except reserving extension hooks)

## 1) Problem statement synthesis

We have ~6M bars of ES 1-minute OHLC(V): plenty to *observe* structure, not enough to safely “learn” a high-dimensional black box without simply parameter-fitting the corpus. Our North Star claims the market is not an arbitrary stochastic process; it is a recursive structure-seeking process shaped by (a) reference swings and their Fibonacci level lattice and (b) exogenous triggers (“news”) that accelerate, frustrate, or invert otherwise-expected paths.

The immediate problem is not “predict the next bar.” It is:

1. **Define a discrete, interpretable representation of a continuous market path** such that:
   - We can **measure** whether the North Star rules are approximately true (treat them as falsifiable hypotheses).
   - We can later **generate** new OHLC paths by sampling in that discrete space and then “rendering” back to bars.

2. **Choose game pieces that survive the fractal paradox**:
   - Like measuring a coastline, any discretization is a choice of scale. Our representation must be **multi-scale by construction** (S/M/L/XL), not a single frozen granularity.
   - The representation must respect **asymmetry of causality**: larger scales constrain smaller scales more than the reverse.

3. **Ensure the discretization is usable in generative context (no lookahead)**:
   - A rule that depends on future bars to decide what “really happened” is not a causal explanation; it is an offline labeling trick.
   - Discretization must be computable from information available up to time *t* (plus already-established higher-scale context), so it can be replayed forward during simulation.

4. **Compress without destroying auditability**:
   - Per `.claude/why.md`, trust is existential. Every generated bar must be traceable back to explicit decisions in discrete space.
   - But per-bar tokenization is too verbose and invites accidental black-boxing. We need a representation that is **sparse where the market is structurally idle** and **dense where it makes commitments** (level hits, invalidations, completions, swing births/deaths).

5. **Avoid state explosion while keeping the “battlefield” intact**:
   - At any moment there can be many valid swings; the simulator cannot carry an unbounded set.
   - The discretization must define which swings are *in play* (e.g., ranked + quota per scale) and how overlapping swings interact (stacked targets, confluence zones, conflicting biases).

6. **Be approximately reversible to OHLC**:
   - The discretization will be lossy, but the loss should mainly be in *how* the smallest path between structural commitments was traversed (intrabar wiggle, wick geometry), not *what* structural commitments were made (which levels mattered, which swings completed/invalidated, how long the market “worked” a level).

In short: **discretize the market into an auditable, multi-scale structural event language** that (a) supports empirical falsification of the current theory and (b) becomes the substrate for a later stochastic generator that can be rendered back into OHLC.

## 2) Guiding tenets

1. **Interpretability beats cleverness.** If we can’t explain a token/event in plain English and trace it to chart structure, it doesn’t belong. *(Opposite: maximize compression/accuracy even if opaque.)*

2. **No lookahead, ever.** Discretization must be computable causally from past + present (and already-established higher-scale context), or it will not transfer to generation. *(Opposite: allow future bars to “clean up” labels.)*

3. **Multi-scale is first-class, not a feature.** A token is incomplete unless it declares its scale and its relationship to higher-scale structure. *(Opposite: flatten everything to one timeline.)*

4. **Events over bars.** Prefer sparse structural commitments (level hits, invalidations, completions, swing lifecycle) over per-bar descriptors; only add per-bar detail if it materially improves reversibility or falsifiability. *(Opposite: tokenize every bar/candle.)*

5. **Conserve degrees of freedom.** Any discretization choice that forces many tunable parameters is presumed wrong until proven otherwise. Favor tables, counts, and invariants over fitted functions. *(Opposite: parameterize to fit.)*

6. **Design for replay.** The discrete representation must be “runnable”: replaying it forward should deterministically reconstruct the same discrete state transitions (and approximately reconstruct OHLC). *(Opposite: treat discretization as an offline dataset only.)*

7. **Leave one-way doors open.** Make room for future exogenous “news” inputs and schedule effects (time-of-day) without rewriting the representation. *(Opposite: bake assumptions that block later causality layers.)*

## 3) Virtual consult

Below is a deliberately unmoderated “council” of voices I trust to pressure-test the discretization question from orthogonal angles.

**Participants**
- **Benoit Mandelbrot** — scaling, fractals, volatility clustering, fat tails
- **David Deutsch** — explanation-first epistemology, falsifiability, “good explanations”
- **Claude Shannon** — information theory, coding, representation choice, compression
- **Richard Feynman** — “don’t fool yourself”, operational definitions, test design
- **Nassim Taleb** — tail risk, robustness, antifragility, narrative fallacies
- **Richard Wyckoff** — market structure as campaigns: effort vs result, tests, absorption

---

**Mandelbrot:** You are already halfway there when you say “riverbank.” The measurement depends on scale; *that is not a bug, it is the object*. If you discretize ES-1m by candles alone, you will build a calendar of noise. If you discretize by swings alone, you will forget that volatility is not constant. Your “game pieces” must carry the scaling law with them: normalize distances by a reference range; normalize time by the tempo of trading. Otherwise you will discover “regimes” that are merely artifacts of units.

**Shannon:** I hear two competing desiderata: compress the stream, and preserve what matters. In coding terms you want a short description length subject to a distortion constraint—but the distortion metric is your theory. If your theory says levels matter, then the distortion should be “did we change which levels were crossed, and in what order?” A per-bar encoding is simply an inefficient code if the market’s *semantic* events are sparse. Make the alphabet event-driven, then run-length encode the quiet.

**Wyckoff:** Quiet is not always quiet. A market can be “doing nothing” on price and doing everything in *positioning*. The tape tells you in the *effort vs result*: lots of volume, little progress, repeated tests of a level. If your discretization only logs that price stayed between 0.618 and 0.5, you lose the difference between absorption and absence. Even without true order book, you can use time-at-level and volume-at-level as proxies. Your tokens must let you ask: “Did the market *work* this area, or just pass through?”

**Deutsch:** You are all sneaking something in: an assumption about what “matters.” That is fine—science proceeds by conjecture—but then your representation must make the conjecture *testable*. Do not build tokens that merely rename your hopes. If you create a “breakout” token, define it in operational terms that could fail. Prefer primitives with clear counterfactuals: “level crossed”, “level rejected N times”, “swing invalidated”, “completion achieved”, “time spent in band.” Then your higher-level stories can be *explanations* rather than definitions.

**Feynman:** And be careful about circularity. If you pick swings using fib logic, then of course you’ll see fib reactions—because you selected the coordinate system that makes them visible. That doesn’t mean the market obeys fibs; it means your lens is fib-shaped. Your test must distinguish “market respects fib lattice” from “any reasonable lattice looks respected once you choose it adaptively.” One way: commit to the swing set online (no lookahead), then measure how often price reacts at out-of-sample levels. Another: compare against null lattices (randomized levels, or alternative ratios) as controls.

**Taleb:** I want to veto one quiet assumption: that the tails are “noise.” The generator will be judged by whether it produces believable extremes—fast moves, gaps, cascades, long volatility clusters. If you discretize by average behavior, you will build a turkey simulator. Include explicit representation for *shock intensity* and *fragility*: “this move was 8× typical range”, “liquidity vacuum”, “cascade through multiple levels without retest.” You do not need a news feed to represent shocks; you need to not erase them.

**Mandelbrot:** Taleb is right about tails, but don’t make “tail” a free parameter you tune until charts look scary. Use invariant scalings: express shock in units of realized volatility or swing-range. If your discretization can’t express “two-level jump” as a natural, rare event across scales, you will never reproduce clustered volatility.

**Shannon:** This suggests a clean separation: keep *structural coordinates* (price position in a swing reference frame) and keep *effort statistics* (time/volume/realized range) as side channels. Then your main event alphabet remains small while still capturing Wyckoff’s “work.”

**Wyckoff:** And you can translate the old words into your primitives. A “test” is repeated probes into a band with diminishing excursion. A “spring” is a breach below a defended low followed quickly by reclaim. These aren’t mystical; they are patterns in your primitives—if your discretization exposes them.

**Deutsch:** Good: build primitives that can compose into explanations. But keep your ontology honest. Your “game pieces” are not the market; they are your current best language for asking questions of it.

**Feynman:** So: define the primitives, build the logging, and then run the harsh tests. If the theory survives, you have earned the right to build a generator on top. If it doesn’t, you have saved yourself years.

---

**Notes I take from this council**
- The discretization should be an **event alphabet + state**, not per-bar labels.
- State must be expressed in **oriented, scale-normalized coordinates** (a “reference frame” per swing).
- We must represent **effort/time/volume near levels** (Wyckoff) without bloating the alphabet.
- We must include explicit hooks for **tails/shocks** (Taleb) but measure them in invariant units (Mandelbrot).
- We must build in **anti-circularity controls** (Feynman) so that our representation doesn’t automatically “prove” the theory.

## 4) Deliberation: options, tradeoffs, implications

### Option A — Per-bar tokenization (candles, returns bins, candlestick “patterns”)
**Idea:** Convert each bar to a discrete symbol (e.g., up/down + body/wick buckets + volume bucket), then learn transition statistics.

- **Pros:** Trivially reversible to OHLC; no dependency on swing detection.
- **Cons (fatal):** Not aligned with the project’s causal objects (swings/levels). Produces a huge token stream (6M+), encourages black-box sequence models, and makes falsifiable North Star hypotheses hard to state (“what does a ‘doji’ predict?”).
- **Hidden failure mode:** You end up learning time-of-day and volatility seasonality instead of structure, because those are the strongest signals in bar-level codes.

### Option B — Swing-only compression (sequence of reference swings)
**Idea:** Reduce OHLC to a sparse list of swing endpoints (H/L pairs), perhaps nested by scale.

- **Pros:** Extreme compression; directly names the core objects of the theory.
- **Cons (fatal):** Loses the path between endpoints: which intermediate levels mattered, how long price spent “working” an area, whether it expressed frustration (near-misses), whether it cascaded through multiple levels, etc. Rendering back to credible OHLC becomes a second, hidden model.

### Option C — Structural event log on a swing lattice (level hits/crosses + swing lifecycle)
**Idea:** Use reference swings as oriented coordinate frames. Quantize price position into a small set of Fibonacci (and theory-relevant) ratios. Emit events when price crosses/touches levels, and when swings complete/invalidate.

- **Pros:** Matches the North Star ontology; sparse and replayable; multi-scale naturally; supports falsifiable measurements (“given we reached 1.5, what is the empirical distribution of next levels?”).
- **Cons:** Requires careful swing selection (quota/ranking) to avoid state explosion; must be explicit about semantics (close vs touch, tolerance, aggregation level); must guard against circular “I saw fibs because I used fibs.”

### Option D — Full hierarchical parse tree / graph of market structure
**Idea:** Build an explicit nested structure (tree/graph) where nodes are swings, edges are containment/interaction, and the time series is a traversal.

- **Pros:** Closest to the “market as recursive object” intuition; could be a powerful substrate for generation.
- **Cons:** High complexity early; difficult to validate and debug; risks building an elegant structure that is not actually necessary for Milestone 1 (measurement).

### Option E (recommended) — Event log + effort side-channel + shock annotations
**Idea:** Take Option C as the spine, but add two lightweight channels:
1) **Effort** in each band (time/volume/range), so “nothing happened” can still mean “absorption happened”.
2) **Shock/cascade markers** expressed in invariant units (e.g., multi-level jumps, range multiple of recent typical range), so tails are not erased.

This stays inside the tenets: primitives remain explicit, it stays causal, and it remains replayable.

**Implication:** Discretization becomes a **measurement pipeline first** (structural event corpus), and only later a generator substrate. That matches the repo’s current phase (validate structure before synthesizing it).

## 5) Recommendation: the “cake”

### Oriented Lattice Event Log (O-LEL)

Discretize OHLC into a **multi-scale structural event language** where:
- **Swings** define oriented reference frames.
- A finite **level set** defines discrete “bands” in each frame.
- The market path becomes a sequence of **band transitions and lifecycle events** (cross, complete, invalidate), augmented by compact **effort** and **shock** statistics.

This is not “tokenize bars.” It is **tokenize commitments**.

### 5.1 Game pieces (ontology)

**1) `ReferenceSwing`**
- `swing_id`, `scale` (S/M/L/XL), `direction` (bull/bear)
- Endpoints: `high_price/high_idx`, `low_price/low_idx`
- Validation policy (strict for S/M; soft for L/XL)
- Optional context: `rank`, `containing_swing_id` (parent context)

**2) `ReferenceFrame` (oriented coordinate system)**
Defines:
- `ratio(price) -> r`
- `price(r) -> price`

Orientation is chosen so **r increases in the expected move direction**:
- Bull reference (H then L): `r = (price - L) / (H - L)` → 0 at L, 1 at H, >1 extension above H
- Bear reference (L then H): `r = (H - price) / (H - L)` → 0 at H, 1 at L, >1 extension below L

Unification win: `r=0.382` always means “minimum encroachment achieved”; `r=2.0` always means “completion zone reached.”

**3) `LevelSet` (discrete ratio lattice)**
A deliberately small, theory-aligned set:
- **Core lattice:** `-0.1, 0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0`
- **Optional near-origin zones (if useful empirically):** `0.9, 1.1`

Level *prices* are quantized to instrument tick size (ES: 0.25) to avoid fake precision.

**4) `Band`**
The interval between adjacent ratios in the `LevelSet`. State is “price is currently in band k” per active swing.

**5) `StructuralEvent` (event alphabet)**
Minimum alphabet (mirrors existing system terminology):
- `LEVEL_CROSS` (minor): bar close moves from one band to another
- `COMPLETION` (major): close crosses 2.0 in the frame
- `INVALIDATION` (major): scale-dependent protection breach
- `SWING_OPEN` / `SWING_CLOSE` (lifecycle): swing becomes active/inactive

Optional derived events (computed later, not required in v1):
- `LEVEL_TOUCH` (wick touch without close cross)
- `REJECTION/TEST` (failed attempts at a boundary)
- `CASCADE` (multi-level cross in one bar)

### 5.2 What gets logged (schema sketch)

Store as **JSON Lines** (one event per line) for streaming inspectability.

Core fields (all events):
- `ts`, `source_bar_idx`
- `scale`, `swing_id`, `event_type`
- `r_close` (ratio at close), `level_from`, `level_to` (when applicable)
- `bar`: `o,h,l,c,v` (so we can debug without reloading raw)

Effort side-channel (emitted on band exit, or attached to `LEVEL_CROSS`):
- `dwell_bars`, `dwell_volume`
- `dwell_range` (high-low during dwell), `max_excursion_r` (max excursion in r-units)
- `tests` (count of approach→retreat patterns at boundary; optional v1)

Shock annotations (attached when relevant):
- `levels_jumped` (how many boundaries crossed in one bar close)
- `range_multiple` (bar range / median range of trailing window at that scale)

Lifecycle payloads:
- For `SWING_OPEN`: endpoints + precomputed level prices (or reference to a shared swing table).
- For `SWING_CLOSE`: reason: `completed|invalidated|replaced`.

### 5.3 How to produce the log (pipeline)

**Inputs**
- OHLCV source series (ES-1m) + aggregation mapping (existing bar aggregator)
- Detected reference swings per scale with ranking/quota and protection validation (existing detector)

**Processing (batch, deterministic, replayable)**
1. **Select the swing set** per scale (quota/rank) and compute each swing’s `ReferenceFrame` and level prices.
2. **Run a swing state machine** over time (existing `SwingStateManager` semantics):
   - Activate swings when valid (location + minimum encroachment + protection).
   - Retire swings on invalidation/completion/replacement.
3. For each bar index (at each scale’s aggregation level):
   - For each active swing:
     - Compute `r_close` in that swing’s frame.
     - Map `r_close` to current `Band`.
     - If band changed: emit `LEVEL_CROSS` and close prior dwell segment with effort stats.
     - If `r_close >= 2.0`: emit `COMPLETION`.
     - If protection rules violated: emit `INVALIDATION`.
4. Emit `SWING_OPEN/SWING_CLOSE` at lifecycle transitions so the log can be replayed from scratch.

**Why bar-close first?**
- Matches existing event semantics and avoids a flood of wick-touch noise.
- Wick touches can be added later once the core pipeline is trusted.

### 5.4 Why this discretization is the right language

It answers the immediate need: **measurement**.
- North Star rules become statements about event sequences and dwell stats.
- We can build empirical tables on top of the log with very few free parameters.

It also sets up the future need: **generation**.
- A generator samples the next event conditioned on current discrete state.
- Rendering back to OHLC can be done by generating a constrained path in `r` space between events and mapping back through the `ReferenceFrame`.

## 6) Validation plan: falsifiable predictions & evaluation

Discretization must be validated on two axes: (A) the representation is correct/replayable, and (B) it enables falsifiable theory tests.

### 6.1 Validate the discretizer (representation correctness)
- **Overlay sanity:** Plot OHLC and overlay event marks for a handful of windows across regimes (trend, range, panic). Confirm events align with intuitive level interactions.
- **Replay determinism:** Replay the event log from the first bar and confirm the reconstructed discrete state (active swings + band indices) matches the original run exactly.
- **Information audit:** Measure compression: events per 10k bars by scale; ensure the log is sparse enough to be usable and dense enough to explain structure.

### 6.2 Validate the theory using the discretized corpus (falsifiable hypotheses)
Examples of hypotheses that become directly measurable:
1. **Encroachment rule:** After a candidate reference forms, does achieving `r>=0.382` materially increase the probability of later completion vs invalidation?
2. **Completion pullback:** After `r>=2.0` (completion), what is the empirical distribution of subsequent minimum retracement bands (1.618/1.5/1.382/etc.), by scale?
3. **Frustration symmetry (hourly+):** If price repeatedly approaches within ε of a key level (e.g., 1.5) without crossing, does it subsequently visit the symmetric level (0.5) at elevated rate vs baseline?
4. **Target stacking:** When multiple 2.0 targets cluster within X ticks, does failure-to-hit predict elevated probability of invalidation/countertrend resolution?
5. **Scale causality:** Condition on higher-scale band location (e.g., XL near 1.618) and measure how it shifts lower-scale transition probabilities.
6. **Volatility clustering proxy:** Do shock annotations (range_multiple) cluster in time and align with multi-level cascades more than under a null model?

### 6.3 Anti-circularity controls (so we don’t “prove” fibs by construction)
- **Null lattice comparison:** Recompute event logs on the same swing frames but with alternative level sets (e.g., equal partitions, randomized ratios) and compare predictive lift of “key levels”.
- **Holdout eras:** Compute transition tables on one era (e.g., 2005–2015) and test predictions on another (2016–2025). If the effect evaporates, it was regime-fit, not structure.

## 7) Naming (team + proposal)

**Expert team name:** **Loom** (weaving structure, effort, and tails into a single language)

**Proposal name:** **EventLattice** (the market as discrete transitions on a level lattice)

**Title**
`EventLattice: An Oriented Structural Event Language for Fractal Market Simulation`

**Tagline**
Discretize OHLC into auditable multi-scale commitments (levels crossed, swings resolved, effort spent) so the theory can be falsified and the generator can be built without black boxes.

---

_Author: Codex (GPT-5.2) — 11:22 16-Dec-2025_
