# Discretization Proposal Generation Prompt

> **What this is:** A reusable prompt template for generating independent discretization proposals through expert panel simulation.
>
> **When to use:** When you need fresh perspectives on how to convert continuous OHLC time series into discrete game pieces for the market generator.
>
> **Reuse potential:** This pattern (problem synthesis → tenets → virtual expert panel → deliberation → proposal) can be adapted for any complex design problem requiring multiple independent viewpoints.

---

You are a world-class polymath and strategic thinker. You excel at seeing new ways of looking at problems, looking around corners, and building insightful narratives on where to go from here and how to get there.

---

## Orientation

First, read all documents in `Docs/Reference/*` to understand what this codebase is about, why it exists, and what's built so far. Read `why.md` to familiarize yourself with what's at stake and why you should care.

---

## Context: The Scientific Journey

Science advances with explanations. We observe something and we propose causal explanations for the phenomena we observe. We have to necessarily make a leap of faith in coming up with explanations because we don't know what we don't know. Then our explanations (theories) make predictions that can be falsified. This leads to more data that needs explanation. This is the beginning of infinity as David Deutsch describes. It's the same journey we're on.

We ask ourselves, *why does market turn where it does?* It's very similar to asking *why does a river turn where it does?* One can never truly measure the length of a riverbank because it's fractal. One has to choose a scale to even attempt to measure it. We have a similar problem statement with our market generator. So we have chosen some scales and proposed an explanation to begin the journey to infinity.

The first step on this journey is nearly complete. The swings being detected have very few false negatives and false positives as observed by this human. We can work to reduce it, but at this point we have entered diminishing returns. The next logical thing to do is to use empiricism to advance the theory. This requires that we make falsifiable predictions and use data to falsify and refine our theory. Crucially—we must refine our explanation until it fits the reality we observe really well. Towards this journey, the next step is to discretize the time series data we possess.

**Your task:** Think about what's a good way to discretize the continuous time series data. Think OHLC of ES-1m as an example. It has 6 million bars—enough to observe patterns but nowhere near enough to even consider training any model (all data points will be fit to parameters if we tried). How do we convert this data to discrete game pieces?

You are one of 5–6 agents who will independently work on this. Mechanically, start by creating a document in `Proposals/Drafts/Discretization/inprogress-UUID.md` (we'll rename this in the end). You may enter planning mode, create todos, or use tools as you see fit. This will be a long-running complex task to solve a hard problem. Prepare accordingly. At each step, consider writing your output down in the document so you can make clear progress.

---

## Suggested Approach

### Step 1: Problem Synthesis

Write the synthesis of a problem statement. Use reference documents and this prompt to write it as you see fit. This should include key problems to address in your document.

Going back to the beginning of infinity, a well-formed problem statement is more than half the battle to getting better understanding of reality. We understand that we can never fully grasp reality but we can get better asymptotically. The problem statement or the question you pose limits how close you get to reality. Think through this carefully.

### Step 2: Guiding Tenets

What guiding tenets will you use to make your decisions sharper and to anchor your virtual discussion? Good tenets anticipate and tiebreak hard tradeoffs that cannot be made with data or with what's already given.

Think about potential tradeoffs you have to make to serve your problem statement. Or think about general guiding principles that you must adhere to given the nature of the project and your task. If your readers or your panel disagree with these, then that creates good discussion that we can later reflect on.

*See Appendix 1 for guidance on writing good tenets.*

### Step 3: Virtual Expert Consultation

Find eminent experts whose expertise and opinion will be valuable in this exercise. They can be current or past geniuses. It doesn't matter as long as you can authentically think in their voice (i.e., enough is known about their worldview and it's useful for your exercise).

Personify each of these experts and have them speak in their voice—expressing opinions, questions, or directions on the problem statement and where the project is headed. They can be contrarians or aligned.

**Do not moderate these discussions prematurely.** Good discussions rarely go straight to the point. They sometimes meander. But this meandering that may seem tangential at first may turn out to be very important at synthesis. Think of the master and the emissary. The emissary line of thinking is direct and explicit, but it often misses the holistic picture that integrates conflicting points of view without reducing any of them or turning them into explicit compromised chimeras. That is the master's domain.

Think of any meandering experts as exploring important intuitive spaces that are explicitly tangential but very pertinent in a broader view. That said, there is a point to this. All experts you've chosen care about the project and want to move it meaningfully forward. That's the synthesis they all (and you) want.

### Step 4: Deliberation and Synthesis

Once you've considered all the experts' points of view, think about their implications for the problem at hand. Use your own voice (or use an expert) and deliberate on options and tradeoffs. There can be more than one good option or it may be a synthesis.

Break them down and think through them. Consider tenets to break tensions if you find any. Alternatively, use the voice of experts and eminent thinkers as necessary. For example, is one expert clearly very deep in the direction you're going? If so, would they think you're applying it right or would they steer you towards something else?

After you've done this analysis, you should be in a place to make your case for where we should go. Don't give the reader ingredients—bake the cake. What's the solution you're honing in on? That should become clear once you've completed this rumination.

### Step 5: Executive Summary

Finally, write the executive summary and project proposal sections at the very top. Don't bury the lede—lead with it. Use active voice, direct sentences, and make your case directly here.

You should explain your recommended solution, why you think this is right, the alternatives you considered, and why you strongly believe this is in the best interest of the project. It may be one of the options or a combination of many.

You may iterate on the document if you are not satisfied that the recommendation you came up with is a high-quality solution.

---

## Key Considerations

### 1. Interpretability is Paramount

The key to our success here is interpretability. This may be the single most important consideration to evaluate market generator's output for fidelity with real markets.

If we use a black-box neural approach, we risk overfitting the admittedly small amount of data. Even at 1m interval, ES data for 20 years amounts to 6 million bars. The number of discrete features we extract from it will necessarily be orders of magnitude smaller.

This explanation is based on a discretionary trader's view of backtesting 4+ years of ES and SPX data, so we cannot simply extend it by using other tickers. Tickers like NQ, Mag7, and BTC follow similar rules, but this human hasn't extensively backtested them as much as ES and SPX. Other tickers may have completely different sets of rules. That is to say, we cannot overcome the data problem by bringing in more tickers, as those require more explanatory theories.

**For now, start with the hypothesis that the data we have to learn rules is ES-1M OHLCV.** If this proves to be strictly not enough (see notes on news later), then bring that up. Making this work just with available data has high impact on the momentum of the project.

Given the volume of data, any attempt to learn more than a few dozen or at most a hundred tunable parameters likely results in overfitting. You're free to consult experts about this as it's a consideration worth keeping at the top of your list. A stochastic interpretable rule-based model, on the other hand, can be expanded endlessly without loss of fidelity. The question of whether this accurately models the market is a key question. We can start with the hypothesis that this must be so given our theory. But we must seek evidence to improve our theory or (in the worst case) falsify it as quickly as possible.

### 2. Ultimate Goal: Realistic Market Generation

What's our ultimate goal with this generator? The key goal is to enable creation of a market data generator that can generate realistic markets. This will be used to train models, to gamify and learn for humans, etc.

In this first step, we don't have to solve this whole problem—only how to discretize it. But we cannot stray from this goal; discretization is merely a step to get there. So deliberate on the bigger problem as long as you want before honing in on the discretization proposal.

We will be successful if we can create realistic market simulation. Evaluation criteria are unknown and you can deliberate. Expert confusion may be a decent starting point but will be very hard to measure. A discriminator model may be easier to measure but could be challenging to construct one that doesn't memorize real market data. Consider this carefully.

### 3. Game Pieces in the Current Theory

At its core, the game pieces are valid bear and bull reference swings. We hypothesize that all market moves can be decomposed to level-to-level moves in some relevant swing. Move completions are invalidations or 2x swings as defined in the north star document.

This is not to say markets cannot move many levels or even transcend completions. They can, and often do (for example, a move can go 3x or even 4x, but very likely this is in service of a larger move). Our aim is to look at the decomposed ES data and learn these patterns as cleanly as we can.

We use rules from the north star as predictions made by this theory at the XL and L scales. We hold these strong opinions weakly, especially at smaller scales. We hypothesize that there can be multiple swings with competing levels that can introduce "battles" that are stochastically resolved. Our core assumption is that we can convert this data into OHLC by reversing the discretization step. You can deliberate on this as needed to build a clearer picture.

### 4. The News Model

We hypothesize that stochastic news prediction provides causal explanations for momentum, volatility clustering, breakouts and breakdowns, and failed breakouts or breakdowns. Our theory is one model of causality, so we take the null hypothesis that the implied causality in the north star document is false and will aim to reject it. If this is correct, then Fibonacci relationships and momentum characteristics will ideally be indistinguishable from real markets.

This will require additional components named in the north star. Most important is a news model. This provides stochastic generation of "news" events with polarity and intensity. We don't need to treat this as a black box. One way to make this tractable for the discretization step is to just consume another data source that has CPI, FOMC, NFP, etc.—high-impact market events from the past decade or so.

**This is explicitly out of scope for the work at hand** as we don't have this dataset right now. But it's an important consideration so we don't make one-way door decisions that end up being expensive later. For now, we can simplify this and use predictable news dates (economic data) and known past tail events (like COVID) as proxy for an actual news model.

### 5. Self-Similarity: Implied but Not Rigid

We assume there is one set of rules for all scales that are self-similar. But this is not rigid, as bigger scales influence smaller scales causally, allowing noisy completions. This means smaller scales may have more exceptions allowed to the rules than larger scales. As we get larger, the market structure should dominate the moves much more than stochastic noise.

Ultimately, our theory suggests even small-scale "noise" has causal factors, but they're obscured from us at this level, so we approximate them using larger-scale rules.

### 6. Game Piece Structure (Exploratory)

Game pieces thus far envisioned look something like: **scale → swing → advance/retreat level → complete/invalidate**. But read extensively in this repo, have the experts explore creatively, question, and convince themselves of what the right approach is.

How to model this is entirely unclear at present—whether to model them as time series (something like language tokens), hierarchical structures, or something else entirely. It's up to you to decide.

### 7. Accept Lossy Translation

This translation will necessarily be lossy. But the only loss should be in *how* the smallest move that we can reasonably make is made. We can have some sense of this "how"—such as time it took or volume (if available)—but we may not know the exact path.

This is acceptable and completely expected. The idea is not to preserve 100% of the data; rather, it is to build a model of how it operates based on our theory.

---

## Finalizing Your Document

As you end your document, consider naming. In computer science there are only two hard problems: naming, cache invalidation, and off-by-one errors. :)

Before you end, consider naming:
1. **Name your team of experts.** It should be a simple one-word (or max two-word) name.
2. **Name your proposal.** Again, it should be something simple and elegant.
3. **Write the heading.** What are you telling your reader? Write this deliberately and carefully. You're not writing an academic paper. You're writing a project proposal in the context of the north star and why this project exists.
4. **Write the subheading or tagline.**
5. **Sign the document** with your name, time, and date at the very end.

Finally, use the names you came up with and rename the document to the following format:

```
Proposals/Drafts/Discretization/<HHmm-dd-mmm-yyyy>-<your_team_name>_<your_proposal_name>.md
```

---

If this is clear, begin.

---

## Appendix 1: Writing Good Tenets

> "Once you make a decision, the universe conspires to make it happen."
> — Ralph Waldo Emerson

Complex design problems require countless decisions. Each of us interprets problems differently, informed by our own biases and experiences. When multiple agents or experts deliberate on a problem, differing assumptions can lead to proposals that talk past each other. Tenets create a common framework for making decisions, surfacing disagreements early rather than burying them in implementation details.

### What is a tenet?

A tenet is a belief that accelerates decision-making by clarifying what matters and what doesn't. Good tenets act as tie-breakers when data alone cannot resolve a choice.

A good tenet concisely articulates a single idea. Consider:

> "We optimize for speed. Speed enables us to learn quickly, pivot if needed, and scale quickly."

This tenet doesn't say speed is the only thing that matters—it says when forced to choose, we favor speed. It acknowledges the tradeoff and takes a stance. A similar tenet, "progress over perfection," makes imperfection permissible, avoiding endless planning cycles in pursuit of an unattainable ideal.

### Good tenets have defensible opposites

To be effective, a tenet needs an opposite that a reasonable person could defend. This prevents obvious statements from becoming tenets. Consider:

- **Bad tenet:** "We will deliver value." (Who would argue for not delivering value?)
- **Good tenet:** "We prefer simple solutions that solve 80% of the problem over complex solutions that solve 95%."

The second tenet has a defensible opposite—someone could reasonably argue that the extra 15% coverage justifies additional complexity. That tension is what makes it useful.

Generic mantras ("think outside the box") and specific decisions ("use Python") also make poor tenets. They don't help with the countless smaller decisions that follow.

### Tenets create productive tension

There will typically be tensions between tenets. Consider two complementary tenets:

> "We optimize for speed."

> "We optimize for correctness."

Do we ship faster with known limitations, or slower with higher confidence? The answer depends on context. Tenets don't eliminate judgment—they focus it on the right questions.

When your expert panel debates, these tensions should surface. That's the point. Unresolved tensions in tenets become unresolved tensions in implementation.

### Practical guidance

**Keep it short.** No more than 5–7 tenets, in priority order. This forces precision and prevents hedging.

**State the tradeoff.** "We prefer X over Y" is clearer than "X is important."

**Test with scenarios.** For each tenet, imagine a concrete decision it would influence. If you can't find one, the tenet is too abstract.

**Invite challenge.** End your tenets with the implicit question: "unless you know better ones." Tenets should be durable but not sacred. If an expert on your panel disagrees with a tenet, that disagreement is valuable—surface it, don't suppress it.
