# Market Simulator - Architecture & Direction

## Current Project State (December 2025)

This project builds a fractal market simulator that generates realistic 1-minute OHLC data by modeling actual market structure using Fibonacci-based swing analysis. **The validation harness is feature-complete** with robust visualization, playback controls, and scale-differentiated swing validation logic. The system is production-ready for systematic validation of swing detection across historical market data.

## System Architecture

### Complete Component Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLI Layer                                      │
│  main.py → validate command → list-data/describe/inspect commands           │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                         Validation Harness                                  │
│  harness.py: Orchestrates all components, handles interactive REPL          │
│  session.py: ValidationSession with progress tracking, persistence          │
│  issue_catalog.py: Structured issue classification and export               │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                        Visualization Layer                                  │
│  renderer.py: 4-panel matplotlib display with OHLC + Fibonacci levels       │
│  keyboard_handler.py: SPACE/arrows/1-4/V for interactive control            │
│  layout_manager.py: Quad ↔ Expanded panel transitions                       │
│  pip_inset.py: Picture-in-Picture for off-screen swing reference            │
│  swing_visibility.py: All/Single/Recent visibility modes                    │
│  progress_logger.py: Verbose CLI feedback during playback                   │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                          Analysis Pipeline                                  │
│  scale_calibrator.py: Quartile-based S/M/L/XL boundary computation          │
│  bar_aggregator.py: Pre-computed aggregations (1m/5m/15m/30m/60m/240m)      │
│  swing_state_manager.py: Multi-scale swing tracking with state transitions  │
│  event_detector.py: Scale-differentiated invalidation + encroachment        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                            Data Layer                                       │
│  loader.py: Historical data with date filtering, multi-resolution support   │
│  ohlc_loader.py: CSV parsing with duplicate timestamp handling              │
│  Data/Historical/: ES futures data (1m: 2007-2024, 5m, 1d available)        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Technical Achievements

| Component | Performance | Key Features |
|-----------|-------------|--------------|
| Scale Calibrator | <50ms for 7K bars | Quartile boundaries, 0.25 ES tick rounding |
| Bar Aggregator | O(1) retrieval | 6 timeframes, natural boundary alignment |
| Swing State Manager | 27ms/bar | Multi-scale independence, intelligent replacement |
| Event Detector | <1ms/bar | Scale-aware invalidation (S/M strict, L/XL soft) |
| Visualization | <100ms updates | Frame skipping at 16 FPS, PiP for off-screen swings |
| Data Loading | 22s for 114K bars | Duplicate handling, date range filtering |

## Swing Validation Rules (Issue #13)

### S/M Scales (Strict Rules)
- **Bull swing**: Invalidates when price ever trades below L (swing low)
- **Bear swing**: Invalidates when price ever trades above H (swing high)

### L/XL Scales (Soft Rules)
| Condition | Bull Swing | Bear Swing |
|-----------|------------|------------|
| Deep threshold | Trade below L - 0.15*delta | Trade above H + 0.15*delta |
| Soft threshold | Close below L - 0.10*delta | Close above H + 0.10*delta |

### Encroachment Tracking
- Swing achieves encroachment when price retraces to 0.382 Fibonacci level
- Tracked per-swing for potential future use in validation confidence

## Visualization Features

### Keyboard Controls
| Key | Action | Key | Action |
|-----|--------|-----|--------|
| SPACE | Toggle play/pause | V | Cycle visibility mode |
| RIGHT | Step one bar | [ / ] | Cycle through swings |
| UP/DOWN | Double/halve speed | 1-4 | Expand panel S/M/L/XL |
| R | Reset to beginning | 0/ESC | Restore quad layout |
| H | Show help | Click | Toggle panel expand |

### Layout Modes
- **Quad (default)**: 2x2 grid showing all scales simultaneously
- **Expanded**: One panel at 90% with mini-panels for context

### PiP (Picture-in-Picture)
- Appears when reference swing body scrolls off left edge
- Shows normalized schematic with key levels (0, 0.5, 1.0, 1.618, 2.0)
- Bull (green) / Bear (red) color coding

## CLI Reference

### Data Discovery
```bash
# List available data
python3 -m src.cli.main list-data --symbol ES
python3 -m src.cli.main list-data --symbol ES --resolution 1m --verbose

# Aliases
python3 -m src.cli.main describe --symbol ES
python3 -m src.cli.main inspect --symbol ES --verbose
```

### Validation Commands
```bash
# Basic validation
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31

# With reference period (calibrate on Jan-Mar, playback from April)
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2020-01-01 --end 2020-05-01 \
  --playback-start 2020-04-01

# With timeframe stepping (60-minute chunks for faster review)
python3 -m src.cli.main validate --symbol ES --resolution 1m \
  --start 2024-01-01 --end 2024-01-31 \
  --step-timeframe 60 --verbose
```

### Interactive Commands
| Command | Description |
|---------|-------------|
| `play` / `play fast` | Start auto/fast playback |
| `pause` | Pause playback |
| `step [N]` | Step forward N bars (default 1) |
| `jump <idx>` | Jump to bar index |
| `speed <mult>` | Set speed multiplier |
| `status` | Show current position |
| `log <type> [desc]` | Log validation issue |
| `help` / `h` / `?` | Show command reference |
| `quit` / `q` | End session |

## Resolved Technical Issues

### Threading and GUI (Issues #5, #7)
- **Problem**: Matplotlib GUI operations from background thread caused crashes
- **Solution**: Select-based non-blocking input on main thread, producer-consumer pattern for GUI updates
- **Key**: All matplotlib operations must run on main thread

### Large Reference Period Hang (Issue #10)
- **Problem**: S-scale override propagated to SwingStateManager, causing 86K bar processing
- **Solution**: Separate `scale_config` (analysis) from `display_aggregations` (visualization)
- **Key**: Shared configuration objects must be deep-copied when divergent behavior needed

### Duplicate Timestamps (Issues #1, #2)
- **Problem**: pandas `get_loc()` returns slice for duplicates, breaking arithmetic
- **Solution**: Check for slice type, use `.start` for first occurrence
- **Key**: High-frequency data commonly has duplicates from overlapping sources

### Scale-Differentiated Validation (Issue #13)
- **Problem**: Single invalidation threshold inappropriate for all scales
- **Solution**: S/M strict rules (any trade-through), L/XL soft rules (threshold-based)
- **Key**: Larger scales need tolerance for noise; smaller scales need precision

## Configuration Architecture

### Analysis vs Display Separation
```python
# Analysis configuration (for SwingStateManager)
scale_config = calibrator.calibrate(bars)  # Original calibrated values

# Display configuration (for VisualizationRenderer)
display_aggregations = dict(scale_config.aggregations)
display_aggregations['S'] = 1  # Override S to 1m for per-bar visibility
display_scale_config = deepcopy(scale_config)
display_scale_config.aggregations = display_aggregations
```

### State Caching for Layout Transitions
```python
# Cache state before layout change
_cached_active_swings = active_swings
_cached_recent_events = recent_events

# After _apply_layout(), re-render from cache
_rerender_cached_state()
```

## Performance Characteristics

### Initialization Timing (114K bars, 3-month reference)
| Phase | Duration |
|-------|----------|
| Data loading | ~22s |
| Scale calibration | ~68s |
| SwingStateManager init | 0.7s |
| Visualization setup | <1s |
| **Total** | **~92s** |

### Memory Considerations
- Sliding window display prevents unbounded artist accumulation
- Session persistence every 100 bars balances safety vs overhead
- Frame skipping at 60ms intervals prevents UI thread starvation

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| ScaleCalibrator | 9 | Pass |
| BarAggregator | 8 | Pass |
| SwingStateManager | 22 | Pass |
| EventDetector | 36 | Pass |
| VisualizationRenderer | 15 | Pass |
| PlaybackController | 23 | Pass |
| EventLogger | 33 | Pass |
| **Total** | **158+** | **Pass** |

## Future Development: Market Data Generator

**Status**: Architecture designed, development deferred until validation establishes expert confidence.

### Planned Components
1. **Market Rules Engine**: Fibonacci-based level definitions, probability distributions
2. **Swing Formation Simulator**: Progressive swing development with realistic timing
3. **Price Tick Generator**: Bid/ask spreads, microstructure modeling
4. **Data Output Pipeline**: OHLC aggregation with metadata preservation

### Integration Strategy
Generator will reverse the analytical process:
- Validated swing detection logic becomes the rule set for generation
- Swing formation rules drive realistic price development
- Generated data can be validated using the same harness (feedback loop)

## Risk Mitigation

### Current Phase Risks
| Risk | Mitigation |
|------|------------|
| Detection logic issues | Systematic validation with expert review |
| Performance degradation | Monitoring, frame skipping, sliding windows |
| Scope expansion | Strict focus on swing validation only |

### Architectural Guardrails
- Generator development explicitly gated by validation confidence
- All detection issues must be resolved before generation work
- Performance validated for production historical analysis scenarios

## Development Standards

### Error Handling
- Graceful degradation over termination (preserve session state)
- Specific error messages with resolution guidance
- Logging at appropriate levels (WARNING for data anomalies)

### Threading Rules
- All matplotlib operations on main thread
- Use `select()` for non-blocking input (not background threads)
- Producer-consumer pattern for cross-thread communication

### Configuration Patterns
- Deep copy shared objects when divergent behavior needed
- Separate analysis config from display config
- Cache state before layout transitions
