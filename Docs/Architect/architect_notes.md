# Market Simulator - Architecture & Direction

## Current Project State

This project builds a fractal market simulator that generates realistic 1-minute OHLC data by modeling actual market structure using Fibonacci-based swing analysis. **Historical data validation infrastructure is now complete** and ready for systematic validation of swing detection logic across diverse market regimes.

## Deployed Architecture

### Foundation: Swing Visualization Harness (Production Ready)

The visualization harness provides a complete analytical pipeline for processing historical OHLC data and validating swing detection across four structural scales (S, M, L, XL):

**Core Components:**
- **ScaleCalibrator**: Determines size boundaries for swing categorization
- **BarAggregator**: Pre-computes aggregated OHLC bars for efficient retrieval  
- **SwingStateManager**: Tracks active swings with event-driven state transitions
- **EventDetector**: Identifies structural events (completions, invalidations, level crossings)
- **VisualizationRenderer**: 4-panel synchronized display with Fibonacci overlays
- **PlaybackController**: Interactive historical data replay with auto-pause

### Extension: Historical Data Validation System (Newly Complete)

**Data Pipeline:**
```
Historical CSV Files → DataLoader → ValidationSession → ExpertReview
         ↓               ↓              ↓               ↓
   DateFiltered     BarObjects    IssueTracking    FindingsExport
```

**Validation Components:**
- **Enhanced DataLoader**: Date range filtering with multi-resolution support (1m, 5m, 1d)
- **ValidationSession**: Expert review workflow with progress tracking and session persistence
- **IssueCatalog**: Structured issue classification and analysis system
- **ValidationHarness**: Composition-based integration with existing visualization harness
- **CLI Extension**: `validate` command for systematic historical analysis

**Integration Architecture:**
```
CLI validate → DataLoader → ValidationSession → ValidationHarness → VisualizationHarness
      ↓            ↓              ↓                    ↓                    ↓
  DateRange    HistoricalBars  ProgressTracking  IssueLogging    InteractiveReplay
```

## Immediate Development Phase: Validation Execution

### Current Objective
Execute systematic validation of swing detection logic using completed infrastructure to establish expert confidence before any generation development.

### Validation Methodology

**Target Market Regimes:**
- **Trending Markets**: Extended directional moves with clear swing progression
- **Ranging Markets**: Sideways consolidation with contained oscillation
- **Volatile Markets**: High volatility periods with rapid swing formation
- **Transition Periods**: Market state changes and structural shifts

**Expert Review Process:**
1. **Historical Data Loading**: Use `validate` command to load specific date ranges
2. **Systematic Playback**: Step through historical periods with swing annotations visible
3. **Issue Documentation**: Log detection problems through ValidationSession interface
4. **Pattern Analysis**: Identify systematic vs. isolated detection issues
5. **Confidence Assessment**: Determine foundation readiness for next phase

**Success Criteria:**
- Detection logic behaves correctly across diverse market conditions
- Expert confidence established in swing detection foundation
- Issue inventory complete with clear categorization
- Performance adequate for interactive historical analysis

### Architectural Priorities for Validation Phase

**Performance Optimization:**
- Validate memory usage patterns with large historical datasets
- Ensure responsive UI during extended replay sessions
- Monitor session persistence overhead during long validation runs

**User Experience Enhancement:**
- Progress indicators for historical data loading operations
- Enhanced error context for data availability and loading issues
- Interactive help system for expert validation workflow

**Data Management:**
- Automatic session cleanup for old validation sessions
- Concurrent session access controls for multi-expert scenarios
- Export format optimization for development iteration feedback

## Technical Debt Resolution Pipeline

### Immediate Technical Debt (Low Risk, High Value)
1. **Memory Usage Monitoring**: Add tracking and warnings for large dataset scenarios
2. **Session Directory Cleanup**: Implement automatic cleanup of sessions older than 30 days
3. **Progress Indicators**: Add real-time feedback for data loading operations
4. **Error Context Enhancement**: Improve error messages with specific resolution guidance

### Medium-Term Refactoring (Architectural Improvement)
1. **Harness Integration**: Replace temporary file approach with direct Bar list integration
2. **Bar Object Migration**: Move Bar dataclass from legacy module to core data structures  
3. **Configuration System**: Implement centralized configuration management
4. **Data Source Abstraction**: Unify data loading paths under common interface

### Future Scalability Considerations
1. **Streaming Data Processing**: Chunked processing for very large historical datasets
2. **Concurrent Session Management**: Multi-user session locking and conflict resolution
3. **Performance Testing Framework**: Automated testing with realistic dataset sizes
4. **Memory Management Strategy**: Implement memory optimization for production deployment

## Future Phase: Market Data Generator

**Architecture Readiness**: Generator architecture design is complete but **development is explicitly deferred** until validation phase establishes expert confidence in swing detection foundations.

**Planned Generator Components:**
1. **Market Rules Engine**: Fibonacci-based price level definitions and probability distributions
2. **Swing Formation Simulator**: Progressive swing development with realistic timing patterns
3. **Price Tick Generator**: Realistic bid/ask spreads and microstructure modeling
4. **Data Output Pipeline**: OHLC aggregation with metadata preservation for validation

**Integration Strategy**: Generator will reverse the analytical process, using validated swing detection logic as the foundation for creating realistic market structure in synthetic data.

## Development Sequencing

**Current Phase: Historical Validation Execution**
- Use completed validation infrastructure for systematic swing detection testing
- Execute expert review across representative market regimes
- Document findings and prioritize any required detection logic refinements

**Next Phase Gate: Foundation Validation**
- Advancement to generator development gated by expert confidence establishment
- All systematic detection issues must be resolved before generation work begins
- Performance characteristics validated for production historical analysis scenarios

**Future Phase: Market Data Generation** 
- Implement synthetic data generation using validated swing detection as foundation
- Build realistic market structure modeling with proven Fibonacci-based analysis
- Create production-quality synthetic datasets for market simulation applications

## Risk Mitigation Strategy

**Validation Phase Risks:**
- **Detection Logic Issues**: Systematic problems may require architectural changes
- **Performance Degradation**: Historical data loading may impact responsiveness  
- **Scope Expansion**: Validation requirements may grow beyond core detection verification

**Mitigation Approach:**
- Maintain strict focus on swing detection validation only
- Leverage existing harness architecture with minimal extensions
- Document all issues systematically for prioritized resolution
- Gate advancement by correctness validation, not calendar timelines

The current architecture provides a solid foundation for systematic validation while maintaining clear separation between validation infrastructure and future generation capabilities.