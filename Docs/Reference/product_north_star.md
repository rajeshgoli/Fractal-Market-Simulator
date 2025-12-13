# Market Simulator Specification

This project aims to create a market simulator whose job is to generate OHLC data that's as close to real market behavior as possible.

## Foundational Philosophy

Let's start with basics. Warren Buffett once said that in the short run, the market is a voting machine, but in the long run, it is a weighing machine. It follows that most price action in the short to medium term is driven by liquidity and momentum rather than fundamental analysis. However, longer term, price converges on the perceived future value of the asset.

So our model of the market has two sets of inputs: (1) price levels and targets, and (2) triggers. We assume triggers are stochastically normally distributed with a long tail—meaning most news is mildly positive to mildly negative, stronger news is rarer, and so on.

Price at certain levels also has tendencies. I'll describe these rules more precisely later, but an example is that after a deep drawdown, if price is retracing back to 90% of a swing, then it is much more likely to reclaim the high even on mildly negative news (i.e., buy the news even when the news is ambiguous or mildly negative). Conversely, a market at a pivot might sell on mildly good news if it has been waiting for a decision for a long time (because the default expectancy of moving up before the news has not occurred).

Our job is to build two models. One is a news generator model that creates news flow. The second is a recursive model of price. Why recursive? Every large move is made up of smaller moves. These smaller moves must obey the same rules. However, smaller moves have more room for extreme behavior compared to larger moves (e.g., 2x range extension without a pullback is possible in small moves). Small and big are relative, but for the purpose here, the biggest moves are swings on monthly charts, big ones are swings on daily charts, and small ones are moves on 1-hour or minute charts.

## Recursion

Big moves drive smaller moves, not vice versa. Only exogenous news in the very long tail can move a big move completely off its completion. Small moves follow the same rules that I will define for big moves—they're self-similar to that extent. However, as already stated, they can be more extreme. There are no explicit rules for this; these behaviors are emergent based on the input model.

## News Events

News events can serve both roles, but generally they are accelerants. A move is pending; news likely makes it possible. For example, the rules dictate a move up, but negative news depresses it slightly without creating the move up. Next we get mildly positive news—this then creates the expected rip. Then a down move is expected and we get positive news. Again, the market may stall or not react. But when something negative happens, it may correct sharply.

A news trigger that is not aligned with the expected move adds "noise" to the system—it creates measured moves that are then countered (I will define this rule separately).

We don't need to produce semantic labels, merely a stream of events with their polarity and intensity. These can be scheduled (CPI) or unscheduled (COVID).

## Long-Term Convergence

Leave this out. Here we're only modeling short- to medium-term price action (months to years), not long-term (decades, when it really pans out).

## Output Requirements

We want realistic price action. The output will be used to train a model (think GAN style). I don't care about visualization other than for debugging.

We want 1-minute OHLC. Other timeframes should be aggregations of this data. However, higher timeframes must meet rules we will discuss.

No feedback exists; it's purely driven by price and level rules and triggers.

---

# Rules

## Move Completion

There are "moves." A bull move is completed when price reaches the 2x extension of a "biggest" swing in the same timeframe. For example: price starts at 674 and drops to 646—that's a 28-point drop. Now if price reaches 702 (that's 2x of 28), a bull move has been successfully completed. The bias at this point is bullish, but we're also at exhaustion.

At exhaustion, a minimum expected pullback is to 1.618, but then the subsequent rally is correspondingly smaller unless other triggers and structure are present (i.e., another larger swing to which this now becomes a valid pullback or retracement).

Pullbacks can also be to 1.5 or 1.382. Between 1.618 and 1.382 there is a liquidity void (unless there are other levels from other swings as described above).

If price retraces below 1.382, it must go to at least 1.1, failing which it can go to 1 and 0.9. Below this, our bias might turn, as we're now in retracement territory. A move can still recover from 0.618, 0.5, or 0.382. Failing that, there is again a liquidity void until 0.1, 0, and -0.1.

**-0.1 is the "STOP" level.** Price can still recover from here, and typically this produces the most explosive moves as it is countering a lot of opposite-end positioning (short or long covering). This is quite common in reference markets on the bullish side (a failed breakdown) and is the most common explosive move, especially at lower timeframes. It is not as common on the bearish side (a failed breakout) and isn't normally as explosive, because the original breakdown is more powerful (first move down by bears is an elevator, second move down is stairs countered at every turn by bulls; first move up by bulls is stairs, but a second move up can be an elevator).

## Timeframe-Specific Behavior

Big-timeframe pullbacks are typically to 1.1 or 1 (think recession, where the market structure is not completely erased). Smaller timeframes can pull back to anything.

When a trigger is needed to make a big move (e.g., from 1.5 to 1.618 or 1.618 to 2 after a steep move down) and a trigger is absent, chop might ensue. Here we see a bull move and a counter bear move in smaller timeframes. Often neither completes, producing no coherent direction.

Bull moves always take multiple smaller bull moves to complete. Bear moves can be completed without any smaller bear moves—i.e., markets take the stairs up but the elevator down. Bear moves can also be completed with smaller bear moves (think rolling recession).

**2x exhaustion at the highest timeframe always requires a pullback.** Markets generally have a positive bias (more liquidity is generated and constantly flows into them by design—think retirement accounts, funds, etc.).

## Black Swan Events

Even exogenous black swan events complete moves to nearest attractors before moving as expected. E.g., when COVID happened, markets moved UP to 2x of the previous rally (it was already in the 1.95+ range) and sharply moved downward all the way to 1.1. (Think of all the liquidity that needs to be dried up—weak shorts with buy orders just below and stop orders just above—before it can move down rapidly.)

## Decision Zones and Liquidity Voids

Between 1.382 and 1.618, you should expect chop and a lot of action—it's a decision zone.

Liquidity voids: 1.1 to 1.382 and 1.618 to 2. This doesn't mean that as soon as 1.1 happens it runs to 1.382; it might reverse from 1.15, for example. Typically it tries a couple of times, and if it fails, it snaps to 1.382, where resistance might reform.

1.1–1–0.9 can also be a chop zone (decision zone). Also remember: if these overlap with other levels from other zones from potentially different timeframes, then those expectations will also apply. Expectations that are aligned contribute to explosive moves; expectations that are contrary can produce slow grinding moves.

## Measured Move Rule

This rule applies only to big moves (month or year). If a level is expected to provide a reaction (e.g., support at 1.382 after failure to capture 1.5) but doesn't, then price must move the same amount in the other direction before finding support.

**Example:** For SPY, 1.382 for the monthly move is 664, 1.5 is 678. Price reaches 672 and fails to resolve to 678 after many days. Then it must fall to at least 651 before finding support.

## Frustration Rule

This rule applies only to hourly and higher timeframes. If a key level is nearly reached (within 5% threshold) but is repeatedly pushed back, then the move completion has been frustrated. This means it must retrace back to the symmetric level. E.g., frustration at 1.5 leads to 0.5; frustration at 1.618 leads to 0.618. The levels in between can provide interim support, and unexpectedly strong news can reverse, but the bias is toward the symmetric level.

**Note:** Frustration of the highest swing uses the measured move rule, not the frustration rule.

Frustration can also occur at 5% above a key level if the rejection is strong (think wicks only, with closures at daily or higher).

## Multi-Swing Rule

If there is a sharper swing within a bigger swing, that swing might interrupt what the bigger swing is trying to do.

**Concrete example:** The January 2025 to April 2025 correction can be broken into two phases. January to April 4 was high volatility trending down with multiple tests of key levels up to 1.382. The last 4 days in April were a violent breakdown from 1.5 to 1.1 (value lost per day is very high, low volatility with direction resolved singularly—sell). This changed abruptly once price was below 1.1, and volatility increased rapidly.

Now 1.5 of the big swing corresponds to 2x of the April carnage. So 1.5 is a bigger resistance than it usually is (typically 1.5 is a pivot, accelerating price in both directions).

## Can't Have Too Many Targets Rule

If multiple swings have targets that are stacking but not reached, they form a strong indicator of a countertrend forming.

**Example:** A reference bull swing has a 2x completion target that's not yet reached. Another reference swing forms as the price goes to 1.5 and traces back to 0.382 and back above that high. The 2x now is stacked close to the previous swing's 2x. If many of these line up close to each other, then this is a must-hit zone for bulls. If it isn't taken out with an impulsive move, the next news event is likely to liquidate all those bull structures and find support lower.

---

# Reference Swings

## Swing Definition

A **bull swing** (bullish reference) is established by a high H followed by a low L—a downswing that sets up bullish structure. A **bear swing** (bearish reference) is established by a low L followed by a high H—an upswing that sets up bearish structure.

## Swing Validation

For a swing to remain valid as a reference:

1. **Location**: Current price must be between H and L.
2. **Minimum encroachment**: After the swing extreme is printed (L for bull, H for bear), price must retrace at least 0.382 of the swing range back toward the origin.
3. **No structural violation**: Price must not violate the swing extreme beyond allowed thresholds.

### Scale-Dependent Violation Rules

**S and M scales**: Swing invalidates if price trades beyond the extreme at all (below L for bull, above H for bear).

**L and XL scales**: More tolerance for noise at higher timeframes:
- Invalidates if price **trades** beyond extreme - 0.15 × swing range
- Invalidates if price **closes** beyond extreme - 0.10 × swing range (at the swing's aggregation level, not raw data)

Bear swings follow symmetric rules with directions reversed.

## Swing Selection

We recursively look for bigger swings from smaller ones nearest to us until we can find no more.

There can be many valid reference swings. The ideal reference swing is big, impulsive, and early—in other words, it has explosive moves (i.e., more than one level taken out in a single move), is the earliest one that's still valid, and is the biggest one for that timeframe. If none can be found, you may have multiple reference swings for similar time periods: earliest, most impulsive, biggest.

**In other words:** As you get to smaller and smaller swings, the reference swings have the same rules except they have a recency preference over earliest/most explosive. In the continuum, the biggest swings have an early-reference bias; the smallest have the most recent bias for building next moves.

## Practical Note on Swings

HTF swings are likely thousands of bars behind if you're looking at 1-minute OHLC data. Even if you're using days, the highest reference swing high occurred in January 2025 and reference low in April 2025—both are hundreds of days before today.

For the data generator, swing detection logic should work in generative context—i.e., no data is available before the data generation started, so it should update reference swings continuously until some are established clearly.

Practically there can be 3–4 reference swings per stage of hierarchy: biggest, most explosive, most recent, and perhaps one or two more depending on other salience. These are generally grouped by size or timeframe: 10–20 points (minute level), the next one will be 50–60 points (hour level), and so on until no bigger reference can be found. For simplicity in detection logic, this can be hierarchical groupings rather than time-based.

---

# Reference Markets

Reference markets are primarily ES and SPX. NQ, BTC, and individual Mag7 stocks are secondary reference markets.

For indices, prices are divided into 4 ticks per unit (0, 0.25, 0.5, 0.75, 1). For stocks, prices are measured up to two decimal points (0.01 to 0.99 are allowed between each dollar value).

Time can be UTC and mapped to the user's locale. Users are in PST primarily and EST secondarily.

---

# Data Generator

The data generator must apply the rules fractally by giving them weights. The higher-timeframe levels have proportionally higher "weight" in the next decision, but they also have more room to play (i.e., 5% of an HTF level may be 50–60 points, and that may be a complete swing for a lower level). If the stochastic trigger model doesn't produce any trigger at these levels, LTF may continue to chop until resolution.

---

# Development Approach

The primary validation mechanism is visual inspection of generated charts against real market behavior. Development should prioritize producing chartable output early and iterate based on visual feedback. Avoid overbuilding—each iteration should produce observable improvements in price action realism.
