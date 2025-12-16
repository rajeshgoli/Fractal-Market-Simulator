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
*   [ ] Define the "Handoff" protocol from Scale N to Scale N-1.

This approach gives us the "Game Board" (Fibs) and the "Moves" (Grammar), satisfying both the physicist (Mandelbrot) and the information theorist (Shannon).
