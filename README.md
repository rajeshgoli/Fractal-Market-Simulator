# Fractal Market Simulator

A market simulator that models structural market dynamics to generate realistic OHLC price data.

**Live Demo:** https://fractal.rajeshgo.li — Try it now with ES 30-minute data.

## Vision

Markets are short-term voting machines driven by liquidity and momentum. This project models those dynamics through:

- **Recursive structure**: Monthly swings constrain daily, daily constrain hourly, hourly constrain minute bars
- **Fibonacci-based levels**: Reference swings generate dynamic structural levels that serve as attractors and decision points
- **Trigger model**: Stochastically distributed news events with polarity and intensity

The goal is synthetic price data realistic enough for model training (GAN-style applications) and market structure analysis.

For full specification, see [Product North Star](Docs/Reference/product_north_star.md).

## Current State

**Phase:** Reference Layer complete — exploration and Outcome Layer definition next.

The system uses a **hierarchical DAG model** where swings form a tree structure with parent-child relationships. The Reference Layer filters these into valid trading references with bin-based classification, formation tracking, and level analysis.

### Two Views

**Structural Legs** — Watch the hierarchical DAG build incrementally from bar 0. Primary tool for understanding swing detection.

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Build frontend (one-time)
cd frontend && npm install && npm run build && cd ..

# Launch Market Structure View
python -m src.replay_server.main
open http://127.0.0.1:8000/replay
```

The UI will prompt you to select a data file on first launch.

**Levels at Play** — Reference Layer view showing valid trading references with fib levels and level crossing events.

**Features:**
- **Incremental build**: Watch legs form as each bar is processed
- **Dual-chart view**: Independent timeframe aggregation (1m to 1W)
- **Hierarchy exploration**: Visualize parent-child relationships between legs
- **Follow leg**: Track specific legs through their lifecycle with event markers
- **Detection config panel**: Adjust thresholds at runtime without restart
- **Reference Layer**: Bin-based classification (median multiples), formation tracking, fib level interaction
- **Level crossing**: Opt-in tracking for specific legs

See [User Guide](Docs/Reference/user_guide.md) for detailed documentation.

### Quick Start

```bash
# Launch Market Structure View
python -m src.replay_server.main
open http://127.0.0.1:8000/replay

# Run tests
source venv/bin/activate && python -m pytest tests/ -v
```

## Documentation

| Document | Purpose |
|----------|---------|
| [User Guide](Docs/Reference/user_guide.md) | Tool usage and workflows |
| [Developer Guide](Docs/Reference/developer_guide.md) | Architecture and API reference |
| [Product Direction](Docs/State/product_direction.md) | Current objectives and next steps |
| [Architect Notes](Docs/State/architect_notes.md) | Technical status and system state |
