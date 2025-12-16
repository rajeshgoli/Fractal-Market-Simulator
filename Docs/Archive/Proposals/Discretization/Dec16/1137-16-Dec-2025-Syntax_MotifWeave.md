# MotifWeave: A Fractal Grammar for Discretizing Markets
*Syntax Council proposal — turning ES-1m into playable structural pieces for falsifiable simulation.*

---

## Executive Summary

### Recommendation
Discretize OHLC into **MotifWeave**: a two-layer representation:
1) A **measurement-first oriented event record** in Fibonacci coordinates per active swing (level/band crossings, completion, invalidation), and
2) A small vocabulary of **boundary-interaction motifs** (test/reject, break/retest, fakeout, drift, impulse, stop-run) that become the actual **game pieces**, each annotated with compact **effort** and **shock** side-channels.

Motifs are conditioned on **parent-scale state** (XL→L→M→S), capturing downward causality without forcing a brittle parse tree.

### Why this is the right move now
- **Interpretability:** Every piece is a one-sentence trader narrative (“REJECT at 1.236 in L-frame while XL sits in 1.382–1.5”).
- **Parameter discipline:** Motifs + small context features yield a few dozen–hundreds of estimable parameters from ES-1m, not millions.
- **Falsifiability:** The corpus can refute (or support) North Star hypotheses via motif statistics (voids, frustration, completion attractors, downward conditioning).
- **Generator readiness:** Pieces are replayable into OHLC via a constrained stochastic renderer (future milestone) because they preserve endpoints, constraints, effort, and shocks.

### Alternatives considered
Per-bar tokens (too noisy), zigzag-only swings (too lossy), pure event logs (telemetry but not yet “pieces”), full parse trees (too complex too early). MotifWeave is the middle layer that turns telemetry into move primitives.

---

## Project Proposal (What to build)

**Goal:** Convert ES-1m (and aggregations) into a compact, auditable corpus of multi-scale motif tokens for measurement and later generation.

**Milestone A — Instrumentation (measurement-first)**
- Oriented reference frames + explicit level lattice
- Event extraction: band occupancy, level crosses, completion, invalidation
- Visual overlay for spot-checking correctness

**Milestone B — “Pieceification” (MotifWeave)**
- Motif extractor: convert event/band stream → motif tokens with effort/shock
- Context binding: attach parent-scale band snapshot at motif start
- Corpus stats: transition tables + falsification tests for key hypotheses

**Out of scope (for this proposal)**
- Full generator, discriminator, or news integration (except reserving a shock channel hook)

**Success criteria**
- Compression: 6M bars → O(10^4–10^5) motif tokens (order-of-magnitude)
- Auditability: every token maps to visible chart behavior in overlay samples
- Measurability: produce at least 5 hypothesis tables (voids, frustration, completion, downward conditioning, stop-runs)

---

## 1) Problem Statement Synthesis (Why discretize, really?)

We already have a credible first artifact: **multi-scale reference swings** (S/M/L/XL) detected with low false negatives/positives by a human’s eye. That matters because swings are the *objects* our North Star theory talks about: defended pivots, Fibonacci lattices, completions, invalidations, stacked targets, and the claim that **larger-scale structure causally constrains smaller-scale motion**.

Now we have to do the thing explanations are for: **make falsifiable predictions and let the corpus judge us**.

The immediate challenge is not “predict the next bar.” ES-1m has ~6 million bars; at that granularity most of what a model could learn is *micro-path noise*. If we ask a learner to predict bar-to-bar deltas with any flexibility, it will either (a) overfit the dataset, (b) learn a mush of weak correlations with no causal story, or (c) smuggle in lookahead via labels.

The discretization problem is therefore:

> **How do we convert continuous OHLC(V) into a discrete set of game pieces whose semantics are the same objects the theory claims are causal (swings + level lattices + triggers), such that the resulting representation is (1) auditable, (2) usable for generation without lookahead, and (3) compact enough to learn only a few dozen–hundred parameters from ES-1m?**

This expands into five concrete sub-problems we must solve explicitly:

### P1 — What are the “game pieces”?
If the pieces are too low-level (per-bar tokens), we drown in noise and parameter-count. If they’re too high-level (swing-only zigzag), we lose the “battle” at levels that the theory claims is the mechanism (frustration, liquidity voids, stop-runs, failed breakouts).

We need a vocabulary that sits at the same abstraction layer as the theory’s causal claims: **interaction with a level lattice inside an oriented reference frame**, across multiple scales.

### P2 — How do we avoid circularity?
If we define pieces in a way that already assumes Fibonacci levels “work”, we can accidentally guarantee that “we observe Fibonacci behavior.” Discretization should therefore *log* what happens in a reference frame (measurement-first), and only later compress that log into higher-level pieces.

### P3 — How do we remain causal (no lookahead)?
A representation that needs future bars to decide what happened “at time t” is useless for a generator. Discretization must be computable from information available up to time t (plus already-established higher-scale context).

### P4 — How do we handle hierarchy and overlap?
Real price action contains multiple valid swings and competing targets. We must define:
- Which swings are “active” (bounded set; quota/ranking)
- How cross-scale context conditions smaller-scale behavior
- How overlapping swings’ lattices interact (confluence zones, stacked targets)

### P5 — How do we get back to OHLC?
The translation will be lossy. That’s acceptable—expected, even. But the loss should primarily be the **micro-path** between structural commitments, not the commitments themselves. “Reverse discretization” must be possible via a constrained stochastic renderer (future work), or the pieces won’t actually be game pieces.

In short: we are not compressing pixels; we are extracting **a playable structural language**.

---

## 2) Guiding Tenets (Tie-breakers)

These tenets are intentionally tension-creating; they exist to force hard choices.

1) **Causality Over Clean Labels**
   - *We do not use future data to “clean up” what happened.* If the market is ambiguous at time t, the representation must carry ambiguity (or defer a label until the event resolves).

2) **Hard-To-Vary Explanations**
   - Prefer representations that make the North Star easy to falsify. If the discretization can be tweaked to fit anything, it teaches us nothing.

3) **Semantics Before Statistics**
   - Every discrete symbol must be explainable to a discretionary trader in one sentence. If we can’t name it cleanly, it’s not a piece—it's just a code.

4) **Structure First, Path Second**
   - Separate “what structural decision happened?” from “how did price traverse the micro-path?” Keep path rendering stochastic and constrained; keep structure discrete and auditable.

5) **Downward Causality as Default**
   - Condition smaller-scale transitions on larger-scale state. Only allow bottom-up cascades as rare, explicitly modeled “fragility” conditions.

6) **Bounded State, Bounded Parameters**
   - The representation must prevent state explosion. If something can be unbounded (active swings, confluence sets), we cap it and log the cap. Treat new parameters as expensive.

7) **Replayability Is Non-Negotiable**
   - A third party should be able to replay the discrete record forward and understand *why* any bar exists. Auditability is part of correctness, not an extra.

---

## 3) Virtual Consult: The Syntax Council

*Panel:* Noam Chomsky (grammar), Judea Pearl (causality), Claude Shannon (information), Benoit Mandelbrot (fractals), Richard Wyckoff (effort/result), Nassim Taleb (tails & model risk), David Deutsch (hard-to-vary explanations).

### Session 1 — “Are we building a code, a theory test, or a generator?”

**Shannon:** “Before you name tokens, tell me the channel. How many bits per minute bar are *actually* informative about your structural story? If your discretization preserves everything, you have not discretized—you’ve just re-encoded the raw.”

**Deutsch:** “And tell me what would falsify you. A good explanation forbids most possible worlds. If your representation can always be adjusted so Fibonacci ‘sort of’ appears, you’re not doing science. You’re doing aesthetic compression.”

**Mandelbrot:** “I will be the curmudgeon: markets are fractal statistically. Your project is not purely statistical; it is asserting a structural mechanism with Fibonacci landmarks. ‘Fractal’ is not a permission slip to carve the world into your favorite ratios.”

**Wyckoff:** “Ratios are fine. But the market is an auction. What matters is *effort versus result*: how much time and volume does it take to move through a zone, and what happens when the effort increases but progress stalls? Your ‘battle at levels’ is not only price; it’s absorption.”

**Taleb:** “And it’s not only absorption—it’s ruin. If your discretization hides the tails, you will build a generator that looks pretty in the center and kills you in the tails. Don’t average away the rare. Preserve a way to represent shocks without inventing a thousand parameters.”

**Pearl:** “You’re all circling the same thing. The discretization should be a *state* that mediates prediction. If your next-move distribution depends on the past only through some variables—active swings, level positions, frustration counters—that’s your causal state. Write it down. Then you can talk about interventions: ‘What if a shock hits here?’”

**Chomsky:** “And once you have state, you may have grammar. But be careful: the generator has competence and performance. Competence is the underlying rule system; performance is the messy realization with noise, limitations, and slips. Your structural events are competence; OHLC paths are performance.”

### Session 2 — “What should a token mean?”

**Chomsky:** “A token that means ‘+3 ticks’ is phonetics—surface form. A token that means ‘test and reject at 1.618 of the active frame’ is syntax—deep structure. If your theory is about deep structure, your discretization must live there.”

**Shannon:** “But do not confuse meaning with utility. The optimal code depends on the distortion measure. If your goal is to later regenerate OHLC, then your symbols must preserve the constraints that bound the renderer. Otherwise you’ll get a beautiful discrete story that can’t be realized as a path.”

**Wyckoff:** “If you log only crosses, you miss the story. The market can spend hours ‘doing work’ and go nowhere, then jump. That stall is information. Call it ‘effort.’”

**Taleb:** “Log the jump too. Better yet, log that you *cannot* model it deterministically. Have an explicit ‘shock’ channel so you don’t sneak it into 47 ad hoc exceptions.”

**Pearl:** “Also: do not hide your assumptions in token definitions. If you define ‘frustration’ as ‘three failed tests causes reversal’, you’ve encoded the theory as a label. Instead log observable counters—number of approaches, dwell time, failed closes—and let the data tell you if reversal probability rises.”

**Deutsch:** “This is critical. The discretizer should be an *instrument*, not a proof. If you want to keep faith with explanation, separate measurement from conjecture.”

### Session 3 — “Hierarchy: stack, tree, or soup?”

**Mandelbrot:** “Self-similar does not mean nested. The coastline doesn’t have a neat parent-child tree; it has overlapping roughness. Your swings may overlap too.”

**Pearl:** “Yet you can still represent hierarchy if it is causal. If larger scales constrain smaller, then smaller-scale transition probabilities should be conditioned on larger-scale variables. That is a DAG: XL → L → M → S.”

**Chomsky:** “A pure tree may be too strict, but a pure soup loses structure. Linguists use feature structures: objects with attributes that unify under constraints. Perhaps your ‘active swings’ are feature structures, and your ‘next event’ is chosen under unification constraints.”

**Shannon:** “Whichever representation you choose, keep the state compact. If you need an unbounded set of active swings, you’re describing the raw market, not a model.”

**Deutsch:** “And remember: if you can’t explain why you cap it at N swings, you have a problem. But you can: ‘bounded rationality and bounded compute’ are part of your explanation. The market doesn’t consider infinite swings either.”

### Session 4 — “The uncomfortable question: what if fibs aren’t causal?”

**Mandelbrot:** “Then your discretization should reveal that quickly. If price does not behave differently in ‘voids’ versus ‘decision zones’, the hypothesis fails.”

**Taleb:** “Or it fails only in crises—which is when you die. So test conditional on regimes and tails.”

**Shannon:** “Your representation should allow the null hypothesis to win. Don’t bake the conclusion into the alphabet.”

**Deutsch:** “If the theory is wrong, you want the generator to fail loudly, not succeed by becoming a flexible curve-fitting machine. That’s the whole point.”

---

## 4) Implications: What the panel forces us to admit

1) **A “discretizer” is two things**
   - As *instrumentation*: a mechanical recorder of what happened in a reference frame (measurement-first).
   - As *game design*: a small vocabulary of pieces you can play forward to create new paths.

   The first is necessary to avoid circularity. The second is necessary to build a generator that is not just “replay history with noise.”

2) **Events aren’t yet pieces**
   - A raw event log (level crosses, completions, invalidations) is excellent telemetry, but it can still be a very long sequence. Modeling it directly is “language modeling” with huge context requirements and weak semantics for long-range causality.

3) **The missing middle layer is “motifs”**
   - The market repeatedly “does the same kind of thing” at boundaries: test/reject, break/retest, fakeout, grind, impulse, stop-run.
   - These are natural *discrete move primitives* that traders already reason with. They are also “hard to vary” if we define them in a reference frame with explicit thresholds.

4) **Hierarchy is best treated as conditioning, not nesting**
   - True nesting (a clean parse tree) is elegant but brittle given overlap and competing swings.
   - Conditioning smaller-scale motif probabilities on larger-scale state captures downward causality without forcing everything into a tree.

5) **Effort and shock deserve first-class channels**
   - If we don’t preserve time/volume/range spent inside a band, we erase absorption and volatility clustering.
   - If we don’t preserve multi-level jumps, we erase tails (the generator will be “pretty” and wrong).

These implications point to a specific synthesis: **event log → motif tokens → hierarchical grammar**.

---

## 5) The Recommendation (“Bake the cake”): MotifWeave

### One-sentence definition
**MotifWeave discretizes OHLC into a hierarchical sequence of boundary-interaction motifs expressed in oriented Fibonacci coordinates, with small side-channels for effort and shock.**

Think of it as:
- **Phonemes:** level bands in a reference frame
- **Morphemes:** boundary interactions (test/reject/break/fake/impulse)
- **Sentences:** swing lifecycles (form → interact → complete/invalidate)
- **Paragraphs:** regime slices (trend/range/crisis), optional later

### Why this is different from “just an event log”
An event log says: “a crossing happened.”
MotifWeave says: “*this kind of attempt* happened, it took *this much effort*, it resolved as *this outcome*.”

That turns telemetry into **playable pieces**.

### Alternatives considered (and why MotifWeave wins)

1) **Per-bar tokenization (delta bins, candle classes)**
   - *Fails:* overfits noise; uninterpretable; huge context; not “hard to vary.”

2) **Swing-only zigzag / turning points**
   - *Fails:* discards the mechanism (tests, frustration, voids, stop-runs).

3) **Pure event log**
   - *Wins for measurement*, but as a standalone “piece set” it tends to be too granular and too long to model without building a big sequence learner.

4) **Full hierarchical parse tree / graph**
   - *Promising*, but complexity front-loads the project before we have measured anything.

5) **MotifWeave (recommended)**
   - *Fits tenets:* semantic, bounded, causal, replayable; separates structure from path; retains effort and shock; supports downward conditioning.

---

## 6) What exactly is a “motif”?

### 6.1 Coordinate system (shared with the repo’s Milestone-1 discretizer work)
Use an **oriented reference frame** for every active swing so that ratios mean the same thing in bull and bear cases.

Let:
- `anchor0` = defended pivot (L for bull ref; H for bear ref)
- `anchor1` = origin extremum (H for bull ref; L for bear ref)
- `r(price) = (price - anchor0) / (anchor1 - anchor0)`  (direction handled by sign)

Then `r=0` is defended, `r=1` is origin, `r=2` is completion, and `r<0` is stop-run territory.

### 6.2 Level set and bands
Pick an explicit lattice (start with North Star levels; extend only with evidence):

`LEVELS = [-0.15, -0.10, 0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.236, 1.382, 1.5, 1.618, 1.786, 2.0, 2.236]`

Define **bands** as intervals between adjacent levels. The instantaneous *band index* is a discrete state.

### 6.3 Motif types (finite vocabulary)
For each boundary interaction at level `ℓ`, classify the attempt into one of a small set:

- `BREAK(ℓ)`: close crosses from band below to band above
- `REJECT(ℓ)`: price probes toward ℓ but closes back in the originating band (no close-cross)
- `FAKE(ℓ)`: close crosses ℓ but returns across within a short horizon (a bounded, causal “fake” definition)
- `IMPULSE(ℓ→ℓ+k)`: multi-level cross with low dwell (levels_jumped ≥ k)
- `DRIFT(band)`: long dwell inside a band without boundary resolution (effort-without-result)

This is the core “move set.” Everything else is either continuous side-channel (effort/shock) or a composition of these primitives.

### 6.4 Side-channels (small, explicit)
Every motif carries:
- **Effort:** `dwell_bars`, `dwell_volume` (if available), `dwell_range`, `test_count` (approach → retreat patterns)
- **Shock:** `levels_jumped`, `range_multiple` (relative to trailing median range)

These are *not* a backdoor for black-boxing. They are bounded, human-interpretable observables.

### 6.5 Motif token schema (concrete)
Store as JSONL (one token per motif) plus a shared swing table:

```json
{
  "ts_start": "2025-01-15T12:00:00Z",
  "ts_end": "2025-01-15T13:05:00Z",
  "scale": "L",
  "swing_id": "l_042",
  "parent": {"scale": "XL", "swing_id": "xl_007", "band": "1.382-1.5"},
  "band_start": "1.0-1.236",
  "boundary": 1.236,
  "motif": "REJECT",
  "band_end": "1.0-1.236",
  "effort": {"bars": 65, "range_r": 0.18, "tests": 4},
  "shock": {"levels_jumped": 0, "range_multiple": 1.1}
}
```

Key point: the **piece** is not “bar N”. The piece is “REJECT at 1.236 in L-frame while XL is in 1.382–1.5.”

---

## 7) How to extract MotifWeave from OHLC (mechanically)

Assume the repo’s swing detection and oriented reference frames exist (they mostly do).

For each scale independently:
1) **Maintain active swing frames** (bounded by quota/ranking).
2) For each bar (at that scale’s aggregation), compute `r_close`, `r_high`, `r_low`, and the current band.
3) Track **band dwell segments** (run-length encode consecutive bars in same band).
4) Detect **boundary interactions** at the boundary of each segment:
   - If band changes via close-cross → `BREAK` or `IMPULSE`
   - If high/low probes boundary but close does not cross → count as test; if segment ends without crossing → `REJECT`
   - If a cross occurs and reverses within bounded horizon → `FAKE` (horizon expressed as “N bars or M% of median span,” chosen per scale to stay causal-for-generation)
5) Emit one motif token per resolved interaction, attaching effort/shock aggregated over the segment.

For hierarchy:
- At motif start time, snapshot the **parent-scale band** (and optionally parent direction / completion proximity). This becomes conditioning context.

This yields four parallel motif streams (S/M/L/XL) plus the swing table that defines frames.

---

## 8) What do we learn from MotifWeave? (Falsifiable predictions)

MotifWeave produces tables you can measure without inventing new labels:

1) **Liquidity void hypothesis**
   - Prediction: dwell time in the 1.382–1.618 decision corridor is shorter than in neighboring bands *conditional on context* (scale, regime).

2) **Frustration hypothesis**
   - Prediction: `test_count` at boundary ℓ increases the probability of opposite-direction resolution (e.g., REJECT→move back toward 1.0) and/or increases shock magnitude when it finally breaks.

3) **Completion-as-attractor hypothesis**
   - Prediction: conditional on being above 1.382 with low frustration, the probability mass shifts strongly toward completion (2.0) vs deep retracement.

4) **Downward causality hypothesis**
   - Prediction: the distribution of L motifs is significantly different conditioned on XL band (e.g., L BREAK rates higher when XL is in early-trend bands vs exhaustion bands).

5) **Stop-run symmetry / asymmetry**
   - Prediction: stop-runs (r < 0) occur with heavy-tailed depth, but recovery probability depends sharply on scale (L/XL softer invalidation).

If the corpus doesn’t support these, we learn where the theory is wrong or incomplete—without hiding the failure in a flexible model.

---

## 9) Risks and mitigations

1) **Risk: motif definitions become arbitrary**
   - *Mitigation:* keep vocabulary small; ground definitions in observable, frame-invariant quantities; push nuance into side-channels and later analysis.

2) **Risk: overlap of multiple swings makes “the” frame ambiguous**
   - *Mitigation:* cap active swings per scale-direction via quota; log which swings were in-play and accept bounded approximation as part of explanation (bounded rationality).

3) **Risk: FAKE requires lookahead**
   - *Mitigation:* define FAKE causally as a two-step motif sequence (BREAK then BREAK-back within a bounded horizon) rather than a retroactive label at the first break.

4) **Risk: ES-only biases the vocabulary**
   - *Mitigation:* keep pieces defined in invariant ratio space; later test on NQ/BTC as *out-of-domain* falsification, not as more training data.

---

## Naming

- **Expert team:** Syntax
- **Panel:** Syntax Council
- **Proposal name:** MotifWeave

**Signed:** Codex (GPT-5.2)  
**Time:** 11:37  
**Date:** 16-Dec-2025
