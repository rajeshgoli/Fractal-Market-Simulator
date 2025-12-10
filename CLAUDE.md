# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Virtual Environment
This project uses a Python virtual environment located in `venv/`. Always activate it before working:
```bash
source venv/bin/activate
```

### Testing
Run tests using pytest:
```bash
source venv/bin/activate && python -m pytest
```

Run specific test files:
```bash
source venv/bin/activate && python -m pytest test_level_calculator.py
source venv/bin/activate && python -m pytest test_swing_detector.py
source venv/bin/activate && python -m pytest tests/test_ohlc_loader.py
```

### Running Core Components
- Level calculator example: `python generate_example.py`
- Swing detector example: `python generate_swing_sample.py`
- Test swing detection on data: `python run_swings_on_test.py`
- Data format verification: `python verify_loader.py`

## Architecture Overview

This is a **Market Simulator** project that implements technical analysis algorithms for detecting market structure and generating realistic OHLC price data. The codebase follows a top-down recursive approach where larger timeframes drive smaller ones.

### Core Components

#### 1. Level Calculator (`level_calculator.py`)
- **Purpose**: Computes structural price levels from reference swings using Fibonacci ratios
- **Key Function**: `calculate_levels(high, low, direction, quantization)` 
- **Returns**: List of `Level` objects with multipliers (-0.1 to 2.0) and level types:
  - STOP (-0.1)
  - SWING_EXTREME (0)
  - SUPPORT_RESISTANCE (0.1, 0.382, 0.5, 0.618, 0.9, 1, 1.1)
  - DECISION_ZONE (1.382, 1.5, 1.618)
  - EXHAUSTION (2)

#### 2. Swing Detector (`swing_detector.py`)
- **Purpose**: Identifies swing highs and lows from OHLC data using lookback windows
- **Key Function**: `detect_swings(df, lookback)`
- **Architecture**: Uses sliding window analysis to find local extrema that meet significance criteria

#### 3. Bull Reference Detector (`bull_reference_detector.py`)
- **Purpose**: Detects valid bull reference swings (completed bear legs being countered)
- **Algorithm**:
  1. Finds swing lows using configurable lookback
  2. Scans backward for bear legs feeding into each low
  3. Filters by retracement validity (current price between 0.382x and 2x)
  4. Applies subsumption to remove redundant swings
- **Key Classes**: `SwingType`, `Bar`, `BullReferenceSwing`

#### 4. Data Loading (`src/data/ohlc_loader.py`)
- **Purpose**: Loads OHLC data from multiple CSV formats
- **Supports**:
  - Format A: Semicolon-separated with DD/MM/YYYY HH:MM:SS timestamps
  - Format B: TradingView comma-separated with Unix timestamps
- **Key Function**: `load_ohlc(filepath)` with automatic format detection

### Key Design Principles

#### Fibonacci-Based Structural Levels
All price targets use Fibonacci ratios applied to reference swings. Levels are **always derived from swings, never stored as absolute prices**.

#### Top-Down Recursion
Larger timeframes constrain smaller ones. Monthly swings drive daily swings, which drive hourly swings. Information never flows upward.

#### Reference Swing Selection
Multiple valid reference swings can coexist. Selection criteria prioritize:
- Large swings (by range)
- Explosive swings (high speed)
- Swing high terminations
- Recent swings for immediate context

#### Price Quantization
All price calculations respect market-specific quantization rules (e.g., 0.25 for indices).

## File Structure

### Core Modules
- `level_calculator.py` - Fibonacci level computation
- `swing_detector.py` - Swing high/low detection with filtering
- `bull_reference_detector.py` - Bull reference swing identification
- `src/data/ohlc_loader.py` - Multi-format OHLC data loading

### Test Utilities  
- `generate_example.py` - Level calculator examples
- `generate_swing_sample.py` - Swing detection examples
- `run_swings_on_test.py` - Test swing detection on real data
- `verify_loader.py` - Data loader verification

### Test Files
- `test_level_calculator.py` - Level calculation tests with spec examples
- `test_swing_detector.py` - Swing detection algorithm tests
- `tests/test_ohlc_loader.py` - Data loading tests with fixtures
- `tests/fixtures/` - Test data files

### Data Files
- `test.csv` - Sample OHLC data (264KB)
- `sample_output.json` - Example algorithm output
- `valid_swings.txt` - Validated swing detection results

### Documentation
- `Docs/Spec.txt` - Market behavior specification and rules
- `Docs/TechSpec.txt` - Technical implementation guidelines and failure modes

## Development Notes

### Dependencies
The project uses minimal dependencies:
- pandas (OHLC data manipulation)
- pytest (testing)
- Standard library (decimal, dataclasses, typing, datetime)

### Data Precision
Uses Python `Decimal` for all price calculations to avoid floating-point precision issues in financial calculations.

### Testing Approach
Tests follow specification examples with known inputs/outputs. The test files contain extensive comments explaining the mathematical expectations and edge cases.