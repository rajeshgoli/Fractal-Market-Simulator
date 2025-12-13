# Fractal Market Simulator

A market simulator that generates realistic OHLC price data by modeling structural market dynamics rather than random walks.

## Vision

Markets are short-term voting machines driven by liquidity and momentum. This project models those dynamics through:

- **Recursive structure**: Monthly swings constrain daily, daily constrain hourly, hourly constrain minute bars
- **Fibonacci-based levels**: Reference swings generate dynamic structural levels that serve as attractors and decision points
- **Trigger model**: Stochastically distributed news events with polarity and intensity

The goal is synthetic price data realistic enough for model training (GAN-style applications) and market structure analysis.

For full specification, see [Product North Star](Docs/Reference/product_north_star.md).

## Current State

**Phase:** Ground truth annotation for swing detection validation.

Before building the generator, swing detection must be validated against expert annotation. The project currently provides:

- **Swing detection algorithms** - O(N log N) vectorized detection with multi-scale support (S/M/L/XL)
- **Ground Truth Annotator** - Web-based two-click annotation tool with Review Mode for qualitative feedback

### Quick Start

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run annotator
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random

# Run tests
python -m pytest tests/ -v
```

### Documentation

| Document | Purpose |
|----------|---------|
| [User Guide](Docs/Reference/user_guide.md) | Annotator usage and workflows |
| [Product Direction](Docs/State/product_direction.md) | Current objectives and next steps |
| [Architect Notes](Docs/State/architect_notes.md) | Technical status and system state |
