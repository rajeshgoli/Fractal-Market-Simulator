# Valid Swing Rules

This document defines the rules for valid swing detection. These rules are the source of truth - the algorithm must implement them correctly.

## Terminology

- **Reference Swing**: A price range defined by a high point and a low point that is later used to predict future price action
- **Bull Reference swing**: High occurs before low (price falls from high to low, then reverses up)
- **Bear Reference swing**: Low occurs before high (price rises from low to high, then reverses down)
- **Symmetric Reference frame**: A reference frame where the origin is 1, the defended pivot is 0, and the target is 2. This is used to describe the swing in a normalized way without reference to direction.
- **Origin**: The first extremum (high for bull, low for bear). This is 1 in symmetric reference frame.
- **Defended pivot**: The second extremum that must hold for the reference swing to remain valid (low for bull, high for bear). This is 0 in symmetric reference frame.
- **Target**: This is the target when the swing is completed. For bull swing, it is Low + 2 * (High - Low). For bear swing, it is High - 2 * (High - Low). This is 2 in symmetric reference frame.
- **Formation**: When a reference swing is detected and becomes active
- **Invalidation**: When a reference swing's defended pivot is violated after formation
- **Completion**: When a reference swing's target is reached it's said to be completed. This is 2 in symmetric reference frame.

## What is a reference swing?

Using the symmetric reference frame, a valid reference swing exists when:
1. 0 < current price < 2 (refer to rule 1 for temporal ordering requirement)
2. 0 was never violated after swing was created (refer rule 2 for precise definition)
3. At some point after 0, price breached a defined fib extension from the defended pivot (currently defined as 0.287, previously we used 0.382) (refer rule 3)
4. 1 is structurally differentiated from other candidate 1s (refer rule 7 for precise definition)

## Rule 1: Swing Structure

A valid reference swing consists of exactly two extremum points:
- A **high bar** with a high price
- A **low bar** with a low price

The temporal order determines direction:
- Bull: `high_bar_index < low_bar_index`
- Bear: `low_bar_index < high_bar_index`

## Rule 2: Defended Pivot Uniqueness

The defended pivot should be the actual extremum within the swing range. Otherwise it's not a valid range.

For bull swings: The low_bar_index should point to the bar with the lowest low between the origin and formation.

For bear swings: The high_bar_index should point to the bar with the highest high between the origin and formation.

### 2.1 At the time of formation, extremum requirement is absolute.

For bull swings (high before low):
- No bar between high and low may have a HIGH exceeding the swing's high price
- No bar between high and low may have a LOW undercutting the swing's low price

For bear swings (low before high):
- No bar between low and high may have a LOW undercutting the swing's low price
- No bar between low and high may have a HIGH exceeding the swing's high price

### 2.2 Post-Formation Invalidation: defened pivot violation has tolerance for big swings

In general, a swing is invalidated if price trades beyond the defened pivot. For all small swings (big swings are defined below, small swings are all swings other than the big swings), this is absolute, any violation of 0 (below L for bull, above H for bear) invalidates the swing.

**Monthly / yearly swings**: Big swings are defined as those whose range is within 10% of all the reference swings (in the code we arbitrarily named these XL swings). 

**Daily / Weekly swings**: These swings are child swings of monthly / yearly swings. These typically have higher defended pivot than 0. For example, the in ES today, the defened pivot is between 1.1 and 1.287 of the yearly defened pivot.

For these big swings, we allow some tolerance before invalidation.

**Invalidation Rules for big swings**: 

Invalidates if price trades beyond extreme - 0.15 × swing range
Invalidates if price closes beyond extreme - 0.10 × swing range (close is calcluated at the swing's aggregation level, not raw data.)

Example: ES monthly candle swing is from 6166 to 4832, so swing range is 6166 - 4832 = 1334. 0.15 × swing range is 199.1. 0.10 × swing range is 133.4. Trading below 4832 - 199.1 = 4632.9 or close below 4832 - 133.4 = 4698.6 in a daily or weekly candle is required before we invalidate the swing. Wicks may be a sign of defense. so we won't be quick to invalidate it. 

Note: this tolerance only applies to swings already formed. That is to say, 0 and 1 established, price breached min fib extension as configured (0.287 or 0.382). These tolerances do not apply at detection time. 

## Rule 3: Formation Trigger

A reference swing is confirmed when price breaches a defined fib extension from the defended pivot. This can be configured. For current swing_detection.py implementation, we use 0.236 fib extension. In the past we have used 0.382 fib extension. We can choose any of the fib extension here.  

## Rule 4: Extrema separation

Defened pivots must be always defended, i.e., no violation of the defended pivot is allowed as specified in Rule 2. 

The other extrema (1) must be separated from other possible candidates for the other extrema in a structurally meaningful way. 

**Heuristic we agreed to**: (The following are heuristics for "structurally meaningful separation" that we agreed to. We can evolve these as we find better ways to find separation.): 

#### 4.1 Self-separation
At detection time measure the range of the swing from 0 to 1. 1 is only valid if no other candidate 1s exist within 0.1 of the swing range. If such a candidate exists, we prefer that 1. We recursively apply the rule until we cannot find a better 1. This allows for scale specific separation (bigger swings require bigger separation to be considered valid inner structure).

## 4.2 Parent-child separation
At detection time, any swing that is a child of another swing must have 0 or 1 that's at least 1 fib level of the parent swing away. In practice this means the 0 or 1 of a child swing should be at least 0.1 of the parent swing away from parent's 0 and 1 and from any sibling swing's 0 and 1. 

## 5: Heirarchy of swings

At the beginning of the project, we arbitarily classified swings as XL, L, M, S based on quartiles of swing ranges to make calibration easier. 

In reality only heirarchial relationship exists between them. There aren't 4 disctinct scales, and in practice there can be as many as 10 or 15 nested heirarchies. For example, in ES as of Dec 18 2025, there is a monthly yearly swing from 6166 to 4832 (Jan to Apr 2025), lets call this L1. There is a nested swing within this that is structurally separated from 5837 to 4832 (Impulsive swing down in April), L2. The next level swing is from 6955 to 6524 (Oct - Nov 2025), L3. L3 is a child of L1 (from 1.5 to below 1.382) and of L2 (from 2 to above 1.618).  Within this range there are two structurally signfifcant highs (1s) at 6896 (mid nov) and 6790 (Nov 17 and Nov 20) that are paired with the same low (6524), L4 and L5. L4 and L5 are children of L3. The current weekly swing is from 6929 to 6771 (Dec 2025), L6. This is a child of L3 (0.9 to 0.618), L4, and L5. Within this, we find daily bull reference swing L7 from 6882 to 6770 and a bear reference swing from 6815 to 6828. L7 is a child of L6. These do not include the daily bear reference that's still active (from a defended all time high of 6955, which is also L1's 1). 

