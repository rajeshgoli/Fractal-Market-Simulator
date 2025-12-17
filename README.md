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

**Phase:** Replay View v2 complete. User testing and ground truth annotation.

### Replay View

The primary tool for understanding swing detection behavior. Provides calibration-first, forward-only playback with event-driven pauses at structural moments.

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Build frontend (one-time)
cd frontend && npm install && npm run build && cd ..

# Launch and open Replay View
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --resolution 5m --window 10000
open http://127.0.0.1:8000/replay
```

**Features:**
- **Calibration phase**: Auto-analyze first 10K bars, detect active swings, show calibration report
- **Forward-only playback**: New bars appear beyond calibration window (no look-ahead bias)
- **Split-chart view**: Independent aggregation (Source, S, M, L, XL) on top/bottom charts
- **Event navigation**: Jump by structural event (◀◀/▶▶), not just bars
- **Scale filtering**: Toggle XL/L/M/S scales, control active swing count (1-5)
- **Swing markers**: H/L labels with Fibonacci levels (0, 0.382, 1, 2) on charts
- **Speed control**: Aggregation-relative playback ("10x per 1H bar")

### Additional Tools

| Tool | Purpose | Access |
|------|---------|--------|
| **Discretization View** | Visualize structural events overlaid on price | `/discretization` |
| **Ground Truth Annotator** | Expert swing annotation with Review Mode | `/` |

See [User Guide](Docs/Reference/user_guide.md) for detailed documentation on all tools.

### Quick Start

```bash
# Replay View (recommended starting point)
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --resolution 5m --window 10000
open http://127.0.0.1:8000/replay

# Ground Truth Annotation (cascade mode)
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random
open http://127.0.0.1:8000

# Run tests (780 tests)
source venv/bin/activate && python -m pytest tests/ -v
```

## Documentation

| Document | Purpose |
|----------|---------|
| [User Guide](Docs/Reference/user_guide.md) | Tool usage and workflows |
| [Developer Guide](Docs/Reference/developer_guide.md) | Architecture and API reference |
| [Product Direction](Docs/State/product_direction.md) | Current objectives and next steps |
| [Architect Notes](Docs/State/architect_notes.md) | Technical status and system state |
