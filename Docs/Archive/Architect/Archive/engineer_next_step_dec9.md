# Engineer Instructions: Visualization Harness Implementation

**Task Assignment:** Implement the complete Visualization Harness (Tasks 1.5-1.8)  
**Priority:** High - Critical validation tool for market simulator  
**Timeline:** Core functionality first, then polish features  

## Overview

You are implementing a 4-panel synchronized visualization system for real-time market structure analysis. The core analytical pipeline is **complete and production-ready** - your focus is entirely on the user interface and interaction layer.

## Foundation Status ✅

**All analytical components are complete:**
- ✅ SwingStateManager: Tracks active swings across S/M/L/XL scales (27ms performance)
- ✅ EventDetector: Identifies structural events (completions, invalidations, level crossings)
- ✅ BarAggregator: Pre-computes multi-timeframe OHLC data
- ✅ ScaleCalibrator: Determines scale boundaries from historical data

**Key Integration APIs Ready:**
```python
# Primary data sources
swing_state_manager.get_active_swings(scale='M')  # Scale-specific swings
swing_state_manager.update_swings(bar, idx)       # Returns events + state changes
event_detector.detect_events(bar, swings)         # Real-time event detection
bar_aggregator.get_bars(timeframe_minutes=5)      # Aggregated OHLC data
```

## Task Breakdown

### Task 1.5: Visualization Renderer (Start Here)
**Priority: Critical - Core visualization functionality**

**Objective:** Create matplotlib-based 4-panel display showing synchronized OHLC charts with structural overlays.

**Key Deliverables:**
1. `src/visualization/renderer.py` - Core VisualizationRenderer class
2. `src/visualization/config.py` - RenderConfig and styling
3. `tests/test_visualization_renderer.py` - Test suite

**Visual Requirements:**
- **Panel Layout:** 2x2 grid (S-scale top-left, M-scale top-right, L-scale bottom-left, XL-scale bottom-right)
- **OHLC Bars:** Green/red candlesticks with current bar highlighted
- **Fibonacci Levels:** Horizontal lines from active swings (solid/dashed/dotted per level type)
- **Event Markers:** Triangles for crossings, stars for completions, X for invalidations
- **Performance:** <100ms UI updates, 500 bar sliding window

**Integration Pattern:**
```python
# Usage in playback loop
result = swing_state_manager.update_swings(new_bar, bar_idx)
renderer.update_display(
    current_bar_idx=bar_idx,
    active_swings=swing_state_manager.get_active_swings(),
    recent_events=result.events
)
```

### Task 1.6: Playback Controller
**Priority: High - Interactive navigation**

**Objective:** Interactive playback with step/auto modes and intelligent pause on major events.

**Key Deliverables:**
1. `src/playback/controller.py` - PlaybackController class
2. `src/playback/config.py` - Configuration and state enums
3. `tests/test_playback_controller.py` - Threading tests

**Core Features:**
- **Auto-playback** with configurable speed (1000ms default)
- **Auto-pause** on MAJOR severity events (completions, invalidations)
- **Navigation:** Step forward/backward, jump to specific bars
- **Threading:** Background auto-play without blocking UI

### Task 1.7: Event Logger
**Priority: Medium - Analysis and export**

**Objective:** Comprehensive event logging with filtering, search, and export capabilities.

**Key Deliverables:**
1. `src/logging/event_logger.py` - EventLogger class
2. `src/logging/display.py` - Real-time display component
3. `tests/test_event_logger.py` - Logging tests

**Core Features:**
- **Rich logging** with market context (swing age, price distance)
- **Filtering** by scale, event type, severity, time range
- **Export** to CSV/JSON with configurable filters
- **Real-time display** with color coding

### Task 1.8: Integration & CLI Entry Point
**Priority: Medium - End-to-end integration**

**Objective:** Unified CLI integrating all components with configuration management.

**Key Deliverables:**
1. `swing_harness.py` - Main CLI script
2. `src/harness/integration.py` - VisualizationHarness class
3. `tests/test_integration.py` - End-to-end tests

**Core Features:**
- **CLI interface** with comprehensive arguments
- **Component integration** with proper initialization order
- **Error handling** with graceful degradation
- **Batch mode** for automated testing

## Getting Started

### Step 1: Environment Setup
```bash
# Verify existing components work
source venv/bin/activate
python -m pytest tests/test_swing_state_manager.py -v  # Should pass all 22 tests

# Test data loading
python -c "
from src.data.ohlc_loader import load_ohlc
bars = load_ohlc('test.csv')
print(f'Loaded {len(bars)} bars')
"
```

### Step 2: Start with Visualization Renderer
**Recommended approach:** Build incrementally

1. **Basic 4-panel setup** - Empty matplotlib subplots with proper layout
2. **OHLC rendering** - Simple candlestick bars from BarAggregator data  
3. **Swing level overlays** - Horizontal lines from ActiveSwing.levels
4. **Event markers** - Basic symbols at event locations
5. **Real-time updates** - Integrate with SwingStateManager updates

### Step 3: Integration Points

**Critical data flow:**
```python
# In playback step callback
result = swing_state_manager.update_swings(source_bars[bar_idx], bar_idx)

# Get visualization data
active_swings = swing_state_manager.get_active_swings()  # All scales
s_swings = swing_state_manager.get_active_swings('S')    # Single scale

# Update renderer
renderer.update_display(
    current_bar_idx=bar_idx,
    active_swings=active_swings, 
    recent_events=result.events,
    highlighted_events=[e for e in result.events if e.severity == EventSeverity.MAJOR]
)
```

## Reference Documentation

### Primary References
1. **`architect_notes.md`** - Complete specifications for Tasks 1.5-1.8
2. **`engineer_reports/swingstatemanager.md`** - Latest implementation details and performance metrics
3. **`src/analysis/swing_state_manager.py`** - Core API with 406 lines of production code
4. **`src/analysis/event_detector.py`** - Event structures and detection logic

### Test Data
- **`test.csv`** - 6,794 hourly ES bars (primary test dataset)
- **`5min.csv`** - 25,950 5-minute bars (additional test data)

### Performance Targets
- **Total latency:** <500ms per playback step
- **Analytical pipeline:** 27ms (already achieved)
- **Visualization budget:** 473ms remaining
- **UI responsiveness:** <100ms for user interactions

## Development Tips

### Use Existing Patterns
The analytical components follow consistent patterns:
```python
# Configuration objects
config = ScaleConfig(boundaries={...}, aggregations={...})

# Initialization with source data  
component = ComponentClass(config)
component.initialize_with_bars(historical_bars)

# Real-time updates
result = component.update_with_bar(new_bar, bar_idx)
```

### Testing Strategy
1. **Unit tests:** Each component in isolation
2. **Integration tests:** Component interactions
3. **Visual tests:** Screenshot comparison for known scenarios
4. **Performance tests:** Latency under target thresholds

### Error Handling
Follow graceful degradation pattern:
```python
try:
    # Component operation
    pass
except Exception as e:
    logging.error(f"Component failed: {e}")
    # Continue with reduced functionality
    self.component = None
```

## Questions & Support

**Architecture questions:** Refer to `architect_notes.md` sections for Tasks 1.5-1.8  
**API questions:** Check existing component implementations and tests  
**Data questions:** Use `test.csv` and examine existing test patterns  

The analytical foundation is solid - focus on creating an intuitive, responsive user interface that showcases the market structure analysis capabilities.

**Ready to start? Begin with Task 1.5 (Visualization Renderer) and build incrementally.**