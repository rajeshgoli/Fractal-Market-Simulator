# CLAUDE.md

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
python3 -m src.cli.main list-data --symbol ES
python3 -m src.cli.main list-data --symbol ES --resolution 1m --verbose
```

Run systematic validation across historical data:
```bash
python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11 --verbose
```

CLI aliases for data discovery:
```bash
python3 -m src.cli.main describe --symbol ES
python3 -m src.cli.main inspect --symbol ES --verbose
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

#### 1. Analysis Pipeline (`src/analysis/`)

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

#### 2. Visualization System (`src/visualization/`)

**Visualization Renderer** (`renderer.py`)
- **Purpose**: 4-panel synchronized matplotlib display with Fibonacci levels
- **Features**: OHLC candlesticks, level overlays, event markers
- **Performance**: <100ms UI updates with sliding window optimization
- **Layout**: 2x2 grid showing S/M/L/XL scales simultaneously

**Render Config** (`config.py`)
- **Purpose**: Comprehensive styling and layout configuration
- **Features**: Dark/light themes, scale-specific colors, level styling

#### 3. Playback System (`src/playback/`)

**Playback Controller** (`controller.py`)
- **Purpose**: Interactive time-based navigation with auto-pause intelligence
- **Modes**: Manual, Auto, Fast playback with configurable speeds
- **Features**: Step navigation, jump-to-event, thread-safe operation

#### 4. Event Logging (`src/logging/`)

**Event Logger** (`event_logger.py`)
- **Purpose**: Comprehensive event capture with rich market context
- **Features**: Full-text search, auto-tagging, filtering, export (CSV/JSON)
- **Performance**: O(1) lookups with multiple indices

**Event Display** (`display.py`)
- **Purpose**: Real-time event formatting for console and UI
- **Features**: Color coding, dashboard summaries, live feeds

#### 5. CLI Integration (`src/cli/`)

**Visualization Harness** (`harness.py`)
- **Purpose**: Unified command-line interface integrating all components
- **Features**: Interactive commands, session management, configuration override
- **Commands**: help, status, play/pause, step, jump, speed, events, filter, export

**Main CLI** (`main.py`)
- **Purpose**: Multi-command CLI for validation and data discovery
- **Commands**: harness (existing), list-data/describe/inspect (data discovery), validate (historical validation)
- **Features**: Data availability visibility, enhanced error messages, verbose logging

#### 6. Data Management (`src/data/`)

**OHLC Loader** (`ohlc_loader.py`)
- **Purpose**: Multi-format OHLC data loading with automatic detection
- **Formats**: TradingView CSV, custom semicolon format
- **Features**: Gap detection, data validation, Bar object conversion

**Historical Data Loader** (`loader.py`)
- **Purpose**: Enhanced data loading for historical validation with date range filtering
- **Features**: Multi-resolution support (1m, 5m, 1d), data discovery, availability checking
- **Functions**: `load_historical_data()`, `get_data_summary()`, `validate_data_availability()`

### Legacy Components (`src/legacy/`)

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
├── analysis/           # Core analytical pipeline
├── cli/               # Command-line interface and validation tools
├── data/              # Data loading utilities (OHLC, historical)
├── examples/          # Demo scripts and examples
├── legacy/            # Historical components (preserved)
├── logging/           # Event logging system
├── playback/          # Playback control system
├── utils/             # Utility scripts and tools
├── validation/        # Historical validation infrastructure
└── visualization/     # Visualization components
```

### Test Suite (`tests/`)
- Comprehensive test coverage with 158+ tests
- Performance benchmarks and integration tests
- Fixtures for test data and mocked components

### Documentation (`Docs/`)
- `Spec.txt` - Market behavior specification
- Engineering reports and architectural notes

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
python3 -m src.cli.main list-data --symbol ES --verbose

# Run historical validation
python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11
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
python3 -m src.cli.main list-data --symbol ES

# Run validation with enhanced error messages
python3 -m src.cli.main validate --symbol ES --resolution 1m --start 2024-10-10 --end 2024-10-11 --verbose
```

### When validation fails due to date ranges:
1. The error message shows available date ranges and suggests discovery commands
2. Use `list-data --verbose` to see detailed file information
3. Adjust `--start` and `--end` parameters based on available data