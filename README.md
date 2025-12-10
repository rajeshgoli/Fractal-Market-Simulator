# Fractal Market Simulator (FMS)

A recursive OHLC price data generator that models short- to medium-term market behavior by simulating structural market dynamics rather than random walks.

## Overview

The Fractal Market Simulator generates realistic 1-minute price bars constrained by Fibonacci-based reference swings across multiple timeframes. Monthly swings constrain daily swings, which constrain hourly swings, which constrain minute bars. This top-down recursive structure, combined with a stochastic news trigger model, produces self-similar price action that exhibits the characteristic patterns of real markets.

### Core Concept

Following Warren Buffett's insight that markets are short-term voting machines (driven by liquidity and momentum) and long-term weighing machines (driven by fundamentals), FMS models the voting machine dynamics through:

- **Structural Rules**: Move completion at 2x extensions, decision zones, liquidity voids, measured moves, frustration rules
- **Trigger Model**: Stochastically distributed news events with polarity and intensity
- **Recursive Constraint**: Each timeframe generates price action that respects larger timeframe structure while allowing emergent volatility at smaller scales

## Key Features

- **Top-Down Recursion**: Price generation flows from monthly → daily → hourly → minute, never upward
- **Fibonacci-Based Levels**: Reference swings generate dynamic structural levels (0.382, 0.618, 1.0, 1.382, 1.618, 2x) that serve as attractors and decision points
- **Multi-Reference Swing Selection**: Dynamically selects valid reference swings based on size, impulsiveness, and recency, supporting multiple simultaneous references
- **Realistic Market Asymmetry**: Captures "stairs up, elevator down" behavior and explosive moves at key levels
- **OHLC Consistency**: Every generated bar maintains valid OHLC relationships and respects quantization (0.25 for indices, 0.01 for stocks)
- **Structural Validation**: Minute-bar generation automatically satisfies rules at higher timeframes through proper constraint enforcement

## Architecture

### Core Modules

**Module A: Data Structures**
- Price and time primitives with quantization awareness
- Level calculator computing Fibonacci-based structural levels
- Swing detector identifying swing highs/lows
- Reference swing selector implementing recursive validation

**Module B: Structural Price Model**
- State machine for swing lifecycle (inception → extension → exhaustion → pullback)
- Multi-timeframe swing container enforcing top-down constraint
- Level stacking calculator identifying overlapping levels and alignment
- Frustration detector tracking stalls at key levels
- Measured move calculator for clean level failures

**Module C: Trigger Model**
- Stochastic trigger event generator (normal distribution with long tail)
- Support for scheduled (CPI) and unscheduled events
- Trigger-structure interaction rules (alignment, opposition, noise)

**Module D: Price Generation Engine**
- Single-bar generator respecting structural context
- Session-aware generation (pre-market, regular hours, after-hours)
- Recursive descent generator orchestrating multi-timeframe generation
- Aggregation validator ensuring structural rules at all timeframes

**Module E: Output and Debugging**
- CSV/Parquet export with reproducibility metadata
- Visualization scaffold for rapid iteration
- Statistical validation suite comparing against real-market baselines

**Module F: Integration**
- End-to-end pipeline with configurable parameters
- Performance profiling targeting < 10 minutes for 1 year of minute data
- Reproducibility verification ensuring deterministic output

## Core Invariants

These architectural commitments cannot be violated without significant rework:

1. **Top-Down Recursion is Inviolable**: Monthly constrains daily, daily constrains hourly, hourly constrains minute. Never propagate information upward.

2. **Levels Are Derived, Not Stored**: Fibonacci levels always computed from reference swings, never cached as absolute prices. When swings complete, all dependent levels shift.

3. **Reference Swing Selection is Contextual**: Multiple valid references coexist; selection criteria (large, impulsive, early) applied dynamically based on price position and timeframe.

4. **Triggers Accelerate but Don't Determine**: News events can only accelerate or delay structurally primed moves, never force forbidden actions.

5. **OHLC Bars Must Be Internally Consistent**: Every bar satisfies Low ≤ Open ≤ High, Low ≤ Close ≤ High, with coherent internal path structure.

6. **Timeframe Aggregation Preserves Structure**: Minute bars correctly aggregated to higher timeframes automatically satisfy structural rules; no post-hoc corrections needed.

## Development Phases

**Phase 1: Foundation (Week 1)**
- Data structures, level calculation, swing detection, reference swing selection
- Stochastic trigger generator

**Phase 2: Core Behavior (Weeks 2-3)**
- Swing state machine
- Multi-timeframe container with top-down constraint enforcement
- Level stacking, frustration detection, measured move calculation

**Phase 3: Integration Bridge (Week 3)**
- Trigger-structure interaction rules

**Phase 4: Generation (Weeks 4-5)**
- Single-bar generator
- Session-aware generation
- Recursive descent multi-timeframe generator
- Aggregation validation

**Phase 5: Validation and Output (Weeks 5-6)**
- CSV/Parquet export
- Visualization tools
- Statistical validation

**Phase 6: Hardening (Week 6+)**
- End-to-end pipeline
- Performance optimization
- Reproducibility verification

## Critical Design Principles

- **Test-Driven**: Write tests first (e.g., 674→646 downswing producing 702 as 2x target)
- **Architect Review for Structural Code**: A2, A4, B1, B2, C3, D1, D3 require architect review
- **No Premature Optimization**: Establish correctness before performance tuning
- **Validate Against Real Data**: Test against ES futures and other reference markets
- **Statistical Rigor**: Beyond visual inspection, validate distribution properties and market statistics

## Failure Modes to Avoid

1. Circular dependencies in recursion (lower timeframes informing higher)
2. Floating-point level comparison without tolerance bands
3. Unbounded reference swing growth (memory/performance death)
4. Trigger-structure desynchronization
5. Timeframe boundary artifacts (midnight UTC, market open/close)
6. Tuning to single runs without statistical validation
7. State coupling explosion in recursive structure
8. Optimization before correctness is established

## Output

Primary output is 1-minute OHLC data in CSV/Parquet format with metadata for reproducibility. Higher timeframes are aggregations automatically satisfying structural rules. Output suitable for training models (GAN-style applications) or analyzing market structure behavior.

## Configuration

- Timeframe: Daily, weekly, monthly generation with minute-level output
- Duration: Configurable (days, months, years)
- Seed: For reproducibility
- Reference Markets: ES, SPX (primary); NQ, BTC, Mag7 stocks (secondary)
- Quantization: 0.25 for indices, 0.01 for stocks
- Timezone: UTC with PST/EST mapping

## Getting Started

1. Review specification and tech design documents
2. Start with Phase 1 tasks in parallel tracks
3. Implement test cases first for each module
4. Use visualization for rapid iteration and validation
5. Progress through phases with architect checkpoints

---

**Status**: In active development following task decomposition and phase sequencing outlined in tech design document.
