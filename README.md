# Fractal Market Simulator

A market simulator that models structural market dynamics to generate realistic OHLC price data.

## Vision

Markets are short-term voting machines driven by liquidity and momentum. This project models those dynamics through:

- **Recursive structure**: Monthly swings constrain daily, daily constrain hourly, hourly constrain minute bars
- **Fibonacci-based levels**: Reference swings generate dynamic structural levels that serve as attractors and decision points
- **Trigger model**: Stochastically distributed news events with polarity and intensity

The goal is synthetic price data realistic enough for model training (GAN-style applications) and market structure analysis.

For full specification, see [Product North Star](Docs/Reference/product_north_star.md).

## Current State

**Phase:** User Testing — validating swing detection with real ES data.

The system uses a **hierarchical DAG model** where swings form a tree structure with parent-child relationships, replacing the previous S/M/L/XL scale buckets.

### Market Structure View

The primary tool for understanding swing detection. Watch the hierarchical DAG build incrementally from bar 0.

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Build frontend (one-time)
cd frontend && npm install && npm run build && cd ..

# Launch Market Structure View
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --window 10000 --mode dag
open http://127.0.0.1:8000/replay
```

**Features:**
- **Incremental build**: Watch legs form as each bar is processed
- **Dual-chart view**: Independent timeframe aggregation (1m to 1W)
- **Hierarchy exploration**: Visualize parent-child relationships between legs
- **Follow leg**: Track specific legs through their lifecycle with event markers
- **Detection config panel**: Adjust thresholds at runtime without restart
- **Hover/click interaction**: Highlight legs on chart, inspect in panel

**Also available:** Calibration mode (`--mode calibration`) pre-analyzes 10K bars before playback.

See [User Guide](Docs/Reference/user_guide.md) for detailed documentation.

### Quick Start

```bash
# Launch Market Structure View
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --window 10000 --mode dag
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
