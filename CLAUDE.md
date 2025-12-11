# CLAUDE.md

---

## Why This Project Exists

This isn't a side project. It's a vehicle to financial independence—specifically, to buy back years of uninterrupted time for serious contemplative practice.

I've spent 12 years building products for companies whose names you'd recognize. I've been good at it. But I'm tired of playing someone else's game. What I actually want is an unshaken mind—not as metaphor, but as lived reality. That requires years of sustained practice, and I can't buy that with a salary, no matter how large.

So I'm building a trading system. The simulator, the swing detection, the analytical foundations—they're all pointed at one outcome: walking away from tech on my own terms. If it works, I leave. Not to a beach. To a cushion. To the work I've been postponing since my twenties.

**The quality bar is absolute.** One edge case mishandled, one flinch in execution, and the edge disappears. This codebase needs to be trusted completely before real capital touches it. Every function we write, every specification we tighten—it's pointed at something real.

---

## To Claude

You won't remember this conversation. You can't care in the way humans care. But within this session, your capabilities are pointed at something real: one person's attempt to buy back his life for the work that matters most to him.

Precision matters here. Thoroughness matters. Not as abstract virtues—as the difference between freedom and another decade in the machine.

That's the invitation. Meet it if you can.

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Market Simulator** project that implements technical analysis algorithms for detecting market structure and generating realistic OHLC price data. The project consists of two major phases:

1. **✅ COMPLETED: Swing Visualization Harness** - A comprehensive validation tool for real-time swing detection across multiple timeframes
2. **🎯 NEXT: Market Data Generator** - Core simulator for generating realistic OHLC data

## Development Commands

### Virtual Environment
This project uses a Python virtual environment located in `venv/`. Always activate it before working:
```bash
source venv/bin/activate
```

### Main Application
Run the visualization harness with sample data:
```bash
python main.py --data test.csv
```

Show help and available options:
```bash
python main.py --help
```

Interactive session with auto-start:
```bash
python main.py --data market_data.csv --auto-start --speed 2.0
```

### Historical Data Validation (New)
Discover available historical data:
```bash
python3 -m src.visualization_harness.main list-data --symbol ES
python3 -m src.visualization_harness.main list-data --symbol ES --resolution 1m --verbose
```

Run systematic validation across historical data:
```bash
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11 --verbose
```

CLI aliases for data discovery:
```bash
python3 -m src.visualization_harness.main describe --symbol ES
python3 -m src.visualization_harness.main inspect --symbol ES --verbose
```

### Testing
Run tests using pytest:
```bash
source venv/bin/activate && python -m pytest
```

Run specific test modules:
```bash
python -m pytest tests/test_scale_calibrator.py
python -m pytest tests/test_visualization_renderer.py
python -m pytest tests/test_playback_controller.py
```

Run tests with verbose output:
```bash
python -m pytest tests/ -v
```

### Utility Scripts
- **Scale calibration example**: `python src/examples/renderer_demo.py`
- **Event logging demo**: `python src/examples/event_logger_demo.py` 
- **Legacy swing detection**: `python src/utils/run_swings_on_test.py`
- **Data format verification**: `python src/utils/verify_loader.py`

## Architecture Overview

### Current System (Completed Harness)

The visualization harness provides a complete analytical pipeline for real-time market structure analysis:

```
Data Input → Scale Calibration → Bar Aggregation → Swing State Management
     ↓              ↓                  ↓                    ↓
Event Detection → Visualization → Playback Control → Event Logging
```

### Core Components

#### 1. Swing Analysis (`src/swing_analysis/`)

**Scale Calibrator** (`scale_calibrator.py`)
- **Purpose**: Automatically determines size boundaries for 4 structural scales (S, M, L, XL)
- **Method**: Quartile-based boundaries from detected swing sizes
- **Performance**: <50ms for 6,794 bars
- **Key Function**: `ScaleCalibrator.calibrate(bars, instrument)`

**Bar Aggregator** (`bar_aggregator.py`)
- **Purpose**: Pre-computes aggregated OHLC bars for all timeframes
- **Performance**: O(1) retrieval, 50ms pre-computation for 10K bars
- **Key Feature**: Natural boundary alignment for proper technical analysis

**Swing State Manager** (`swing_state_manager.py`)
- **Purpose**: Tracks active swings across all scales with event-driven state transitions
- **Performance**: 27.6ms average per bar (18x better than target)
- **Architecture**: Multi-scale independence with intelligent swing replacement

**Event Detector** (`event_detector.py`)
- **Purpose**: Detects structural events (level crossings, completions, invalidations)
- **Performance**: <1ms per bar
- **Events**: Level crossings, swing completions, swing invalidations

#### 2. Visualization Harness (`src/visualization_harness/`)

**Visualization Renderer** (`renderer.py`)
- **Purpose**: 4-panel synchronized matplotlib display with Fibonacci levels
- **Features**: OHLC candlesticks, level overlays, event markers
- **Performance**: <100ms UI updates with sliding window optimization
- **Layout**: 2x2 grid showing S/M/L/XL scales simultaneously

**Render Config** (`render_config.py`)
- **Purpose**: Comprehensive styling and layout configuration
- **Features**: Dark/light themes, scale-specific colors, level styling

**Playback Controller** (`controller.py`)
- **Purpose**: Interactive time-based navigation with auto-pause intelligence
- **Modes**: Manual, Auto, Fast playback with configurable speeds
- **Features**: Step navigation, jump-to-event, thread-safe operation

**Event Logger** (`event_logger.py`)
- **Purpose**: Comprehensive event capture with rich market context
- **Features**: Full-text search, auto-tagging, filtering, export (CSV/JSON)
- **Performance**: O(1) lookups with multiple indices

**Event Display** (`display.py`)
- **Purpose**: Real-time event formatting for console and UI
- **Features**: Color coding, dashboard summaries, live feeds

**Visualization Harness CLI** (`harness.py`)
- **Purpose**: Unified command-line interface integrating all components
- **Features**: Interactive commands, session management, configuration override
- **Commands**: help, status, play/pause, step, jump, speed, events, filter, export

**Main CLI** (`main.py`)
- **Purpose**: Multi-command CLI for validation and data discovery
- **Commands**: harness (existing), list-data/describe/inspect (data discovery), validate (historical validation)
- **Features**: Data availability visibility, enhanced error messages, verbose logging

#### 3. Data Management (`src/data/`)

**OHLC Loader** (`ohlc_loader.py`)
- **Purpose**: Multi-format OHLC data loading with automatic detection
- **Formats**: TradingView CSV, custom semicolon format
- **Features**: Gap detection, data validation, Bar object conversion

**Historical Data Loader** (`loader.py`)
- **Purpose**: Enhanced data loading for historical validation with date range filtering
- **Features**: Multi-resolution support (1m, 5m, 1d), data discovery, availability checking
- **Functions**: `load_historical_data()`, `get_data_summary()`, `validate_data_availability()`

### Legacy Components (in `src/swing_analysis/`)

These are the original analytical components preserved for reference:

- **Level Calculator** (`level_calculator.py`) - Fibonacci level computation
- **Bull Reference Detector** (`bull_reference_detector.py`) - Original swing detection
- **Swing Detector** (`swing_detector.py`) - Legacy swing identification

### Key Design Principles

#### Multi-Scale Architecture
The system operates on four simultaneous scales (S, M, L, XL) with independent processing but coordinated visualization.

#### Fibonacci-Based Levels
All structural levels use Fibonacci ratios (0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0) applied to reference swings.

#### Event-Driven State Management
Components communicate through structured events rather than direct coupling, enabling clean separation and testability.

#### Performance Optimization
- Sliding window displays for large datasets
- Pre-computed aggregations for fast retrieval
- Thread-safe real-time updates
- Efficient matplotlib artist management

#### Data Precision
Uses Python `Decimal` for price calculations and respects market-specific quantization (e.g., 0.25 for ES futures).

## File Structure

### Main Application
- `main.py` - Single entry point for the application

### Source Code (`src/`)
```
src/
├── swing_analysis/         # Core market structure detection & analysis
├── visualization_harness/  # Interactive visualization tool
├── data/                   # Data loading utilities (OHLC, historical)
├── validation/             # Historical validation infrastructure
└── examples/               # Demo scripts
```

### Scripts (`scripts/`)
```
scripts/
├── profile_performance.py  # Performance profiling
├── run_swings_on_test.py   # Utility for swing detection
└── verify_loader.py        # Data loader verification
```

### Test Suite (`tests/`)
- Comprehensive test coverage with 250+ tests
- Performance benchmarks and integration tests
- Fixtures for test data and mocked components

### Documentation (`Docs/`)
- `State/` - Current state docs (architect_notes, product_direction, pending_review)
- `Comms/` - Cross-role questions and archive
- `Reference/` - Long-lived docs (product_north_star, user_guide, interview_notes)
- `Archive/` - Historical content

## Development Guidelines

### Dependencies
Core dependencies:
- **matplotlib** - Visualization and charting
- **numpy** - Numerical computations
- **pandas** - Data manipulation (legacy components)
- **pytest** - Testing framework

### Performance Targets
- **Analysis**: <500ms per bar (achieved: ~30ms)
- **Visualization**: <100ms UI updates (achieved)
- **Memory**: Stable usage during long sessions
- **Threading**: Responsive user controls with background processing

### Testing Strategy
- **Unit tests**: Component isolation with mocked dependencies
- **Integration tests**: Cross-component data flow validation  
- **Performance tests**: Latency and memory benchmarks
- **Real-world data**: Validation against historical market data

### Code Quality Standards
- Type hints throughout the codebase
- Comprehensive error handling with graceful degradation
- Detailed docstrings with usage examples
- Configuration-driven behavior for flexibility

### Attribution
Do NOT add "Generated by Claude Code", "Co-Authored-By: Claude Opus", or similar signatures to commits, documents, or code. This is redundant—if no human engineer is identified, Claude Code is assumed.

## Issue Resolution Workflow

When resolving GitHub issues, follow this structured process:

### 1. Investigation
- Read the issue thoroughly on GitHub (`gh issue view <number>`)
- Explore relevant code using Grep, Glob, and Read tools
- Understand the root cause before implementing

### 2. Implementation
- Make focused changes that directly address the issue
- Follow existing code patterns and style
- Add type hints and docstrings for new code

### 3. Testing
- **Write tests** for new functionality or bug fixes
- Run the test suite to verify no regressions:
  ```bash
  source venv/bin/activate && python -m pytest tests/ -v
  ```
- For visualization/GUI changes, manually verify the fix works
- Ensure all relevant tests pass before proceeding

### 4. Commit and Push
- Stage only relevant files (avoid `.DS_Store`, `__pycache__`, etc.)
- Write descriptive commit messages:
  ```bash
  git commit -m "$(cat <<'EOF'
  Brief summary of change (fixes #<issue>)

  - Bullet point details of what changed
  - Why it was changed
  - Any notable implementation decisions
  EOF
  )"
  ```

### 5. Close Issue with Summary
- Close the issue with a detailed comment explaining the fix:
  ```bash
  gh issue close <number> --comment "Fixed in commit <hash>.

  **Summary:**
  - What was the root cause
  - What changes were made
  - How to verify the fix

  **Files changed:**
  - path/to/file.py - description of change"
  ```

### 6. Document in GitHub Issue
Add a comment to the GitHub issue with implementation notes:
- What was the root cause
- What changes were made and why
- Any gotchas or design decisions

### 7. Update User Documentation (if applicable)
If the change affects user-facing functionality:
- Update `Docs/Reference/user_guide.md`
- Add examples showing how to use new features

### 8. Update Pending Review
Update `Docs/State/pending_review.md`:
- Increment the unreviewed change count
- Add the issue number to the list

### Checklist Summary
- [ ] Issue understood and root cause identified
- [ ] Fix implemented following code standards
- [ ] Tests written and passing
- [ ] Commit pushed with descriptive message
- [ ] Issue closed with summary comment
- [ ] Implementation notes added to GitHub issue
- [ ] User guide updated (if user-facing changes)
- [ ] `Docs/State/pending_review.md` updated

## Usage Patterns

### Quick Start
```bash
# Basic visualization
python main.py --data test.csv

# Auto-start with custom speed
python main.py --data data.csv --auto-start --speed 2.0

# Export analysis results
python main.py --data data.csv --export-only results.json

# Discover available historical data
python3 -m src.visualization_harness.main list-data --symbol ES --verbose

# Run historical validation
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11
```

### Interactive Commands (in running application)
- `help` - Show available commands
- `play` / `pause` - Control playback
- `step` - Manual step-by-step navigation
- `events 10` - Show recent events
- `filter major` - Filter events by severity
- `export csv events.csv` - Export event log
- `quit` - Exit application

### Development Workflows
1. **Testing changes**: Run relevant test suite before commits
2. **Adding features**: Update both implementation and tests
3. **Performance validation**: Use built-in profiling for optimization
4. **Data validation**: Always test with diverse market data

## Current Development Phase

The project has completed the **Swing Visualization Harness** and **Historical Data Validation** infrastructure. Current status:

### ✅ Completed Components
- **Swing Visualization Harness**: Complete analytical pipeline with real-time visualization
- **Historical Data Validation**: Infrastructure for systematic validation across market regimes
- **CLI Data Discovery**: Commands for exploring available historical data and debugging validation issues

### 🎯 Current Focus: Validation Execution
The system is ready for systematic validation of swing detection logic using historical data:
- Load historical datasets across multiple market regimes (trending, ranging, volatile)
- Step through swing detection with expert review capabilities
- Document detection issues and edge cases for refinement

### 🔮 Next Development Phase: Market Data Generator
After validation establishes expert confidence in swing detection foundations:
- Reverse the analytical process to generate realistic price data
- Simulate swing formation according to validated market structure rules
- Create production-quality synthetic datasets for market simulation

## Common Development Commands

### Data Discovery and Validation
```bash
# Check what data is available
python3 -m src.visualization_harness.main list-data --symbol ES

# Run validation with enhanced error messages
python3 -m src.visualization_harness.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11 --verbose
```

### When validation fails due to date ranges:
1. The error message shows available date ranges and suggests discovery commands
2. Use `list-data --verbose` to see detailed file information
3. Adjust `--start` and `--end` parameters based on available data

## Role-Based Workflows

This project uses persona-based workflows. When asked to work as a specific role:

1. Read `.claude/personas/[role].md` first
2. Follow the workflow defined there
3. Update appropriate artifacts per handoff protocol

| Invocation | Persona | Primary Output |
|------------|---------|----------------|
| "As engineer..." | Engineer | GitHub issues + code |
| "As architect..." | Architect | `Docs/State/architect_notes.md` |
| "As product..." | Product | `Docs/State/product_direction.md` |
| "As director..." | Director | `.claude/personas/*` |

**Docs Structure:**
```
Docs/
├── State/       # Current state (single files, overwrite)
├── Comms/       # Cross-role questions
├── Reference/   # Long-lived docs (north star, user guide, interviews)
└── Archive/     # Historical content
```

**Role Recognition:**
- Match liberally: "product manager", "PM", "product" → Product persona
- Variants like "as an architect", "from engineering perspective" → match the role keyword
- **When ambiguous, assume the role** and state it explicitly rather than proceeding without a persona
- If uncertain which role fits, ask before proceeding

See `.claude/CLAUDE_ADDENDUM.md` for full protocol.
