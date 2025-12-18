import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { IChartApi, ISeriesApi, createSeriesMarkers, SeriesMarker, Time, ISeriesMarkersPluginApi } from 'lightweight-charts';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { ExplanationPanel } from '../components/ExplanationPanel';
import { SwingOverlay } from '../components/SwingOverlay';
import { usePlayback } from '../hooks/usePlayback';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import { fetchBars, fetchDiscretizationState, runDiscretization, fetchDiscretizationEvents, fetchDiscretizationSwings, fetchSession, fetchDetectedSwings, fetchCalibration } from '../lib/api';
import { INITIAL_FILTERS, LINGER_DURATION_MS } from '../constants';
import {
  BarData,
  FilterState,
  AggregationScale,
  DiscretizationEvent,
  DiscretizationSwing,
  DetectedSwing,
  CalibrationData,
  CalibrationSwing,
  CalibrationPhase,
  SWING_COLORS,
  parseResolutionToMinutes,
  getAggregationLabel,
  getAggregationMinutes,
  SwingDisplayConfig,
  SwingScaleKey,
  DEFAULT_SWING_DISPLAY_CONFIG,
} from '../types';
import { useSwingDisplay } from '../hooks/useSwingDisplay';

/**
 * Convert a discretization swing to a DetectedSwing for chart overlay.
 * Needed because discretization swings and windowed detected swings use different ID formats.
 */
function discretizationSwingToDetected(swing: DiscretizationSwing): DetectedSwing {
  const isBull = swing.direction.toUpperCase() === 'BULL';

  // For bull: anchor0 is low (defended pivot), anchor1 is high (origin)
  // For bear: anchor0 is high (defended pivot), anchor1 is low (origin)
  const highPrice = isBull ? swing.anchor1 : swing.anchor0;
  const lowPrice = isBull ? swing.anchor0 : swing.anchor1;
  const highBarIndex = isBull ? swing.anchor1_bar : swing.anchor0_bar;
  const lowBarIndex = isBull ? swing.anchor0_bar : swing.anchor1_bar;

  const swingRange = highPrice - lowPrice;

  // Calculate Fib levels
  let fib_0: number, fib_0382: number, fib_1: number, fib_2: number;
  if (isBull) {
    fib_0 = lowPrice;  // Defended pivot
    fib_0382 = lowPrice + swingRange * 0.382;
    fib_1 = highPrice;  // Origin
    fib_2 = lowPrice + swingRange * 2.0;  // Completion target
  } else {
    fib_0 = highPrice;  // Defended pivot
    fib_0382 = highPrice - swingRange * 0.382;
    fib_1 = lowPrice;  // Origin
    fib_2 = highPrice - swingRange * 2.0;  // Completion target
  }

  return {
    id: swing.swing_id,
    direction: isBull ? 'bull' : 'bear',
    high_price: highPrice,
    high_bar_index: highBarIndex,
    low_price: lowPrice,
    low_bar_index: lowBarIndex,
    size: swingRange,
    rank: 1,  // Highlighted swing gets rank 1 (primary color)
    fib_0,
    fib_0382,
    fib_1,
    fib_2,
  };
}

/**
 * Convert a calibration swing to a DetectedSwing for chart overlay.
 */
function calibrationSwingToDetected(swing: CalibrationSwing, rank: number = 1): DetectedSwing {
  return {
    id: swing.id,
    direction: swing.direction,
    high_price: swing.high_price,
    high_bar_index: swing.high_bar_index,
    low_price: swing.low_price,
    low_bar_index: swing.low_bar_index,
    size: swing.size,
    rank,
    fib_0: swing.fib_0,
    fib_0382: swing.fib_0382,
    fib_1: swing.fib_1,
    fib_2: swing.fib_2,
  };
}

export const Replay: React.FC = () => {
  // UI state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [filters, setFilters] = useState<FilterState[]>(INITIAL_FILTERS);

  // Chart aggregation state
  const [chart1Aggregation, setChart1Aggregation] = useState<AggregationScale>('L');
  const [chart2Aggregation, setChart2Aggregation] = useState<AggregationScale>('S');

  // Speed control state
  const [sourceResolutionMinutes, setSourceResolutionMinutes] = useState<number>(5); // Default 5m
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(1);
  const [speedAggregation, setSpeedAggregation] = useState<AggregationScale>('L'); // Default to chart1

  // Data state
  const [sourceBars, setSourceBars] = useState<BarData[]>([]);
  const [calibrationBars, setCalibrationBars] = useState<BarData[]>([]); // Bars at calibration end
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);
  const [events, setEvents] = useState<DiscretizationEvent[]>([]);
  const [swings, setSwings] = useState<Record<string, DiscretizationSwing>>({});
  const [detectedSwings, setDetectedSwings] = useState<DetectedSwing[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Calibration state
  const [calibrationPhase, setCalibrationPhase] = useState<CalibrationPhase>(CalibrationPhase.NOT_STARTED);
  const [calibrationData, setCalibrationData] = useState<CalibrationData | null>(null);
  const [currentActiveSwingIndex, setCurrentActiveSwingIndex] = useState<number>(0);

  // Swing display configuration (scale toggles, active swing count)
  const [displayConfig, setDisplayConfig] = useState<SwingDisplayConfig>({
    enabledScales: new Set(DEFAULT_SWING_DISPLAY_CONFIG.enabledScales),
    activeSwingCount: DEFAULT_SWING_DISPLAY_CONFIG.activeSwingCount,
  });

  // Use hook to filter and rank swings based on display config
  const { filteredActiveSwings, filteredStats } = useSwingDisplay(calibrationData, displayConfig);

  // Chart refs for syncing
  const chart1Ref = useRef<IChartApi | null>(null);
  const chart2Ref = useRef<IChartApi | null>(null);
  const series1Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const series2Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);

  // Marker plugin refs (single plugin per chart for all markers)
  const markers1Ref = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const markers2Ref = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Ref to hold the latest syncChartsToPosition function (avoids stale closure in callback)
  const syncChartsToPositionRef = useRef<(sourceIndex: number) => void>(() => {});

  // Compute available speed aggregation options (only aggregations selected on charts)
  const availableSpeedAggregations = useMemo(() => {
    const options: { value: AggregationScale; label: string }[] = [];
    const seen = new Set<AggregationScale>();

    // Add chart1 aggregation
    if (!seen.has(chart1Aggregation)) {
      options.push({ value: chart1Aggregation, label: getAggregationLabel(chart1Aggregation) });
      seen.add(chart1Aggregation);
    }

    // Add chart2 aggregation if different
    if (!seen.has(chart2Aggregation)) {
      options.push({ value: chart2Aggregation, label: getAggregationLabel(chart2Aggregation) });
      seen.add(chart2Aggregation);
    }

    return options;
  }, [chart1Aggregation, chart2Aggregation]);

  // Calculate effective playback interval in ms
  // Speed = N aggregated bars per second at selected aggregation
  // effectiveSourceBarsPerSecond = speedMultiplier * (aggMinutes / sourceMinutes)
  // interval = 1000 / effectiveSourceBarsPerSecond
  const effectivePlaybackIntervalMs = useMemo(() => {
    const aggMinutes = getAggregationMinutes(speedAggregation);
    const aggregationFactor = aggMinutes / sourceResolutionMinutes;
    const effectiveSourceBarsPerSecond = speedMultiplier * aggregationFactor;
    // Clamp to minimum 10ms interval for stability
    return Math.max(10, Math.round(1000 / effectiveSourceBarsPerSecond));
  }, [speedMultiplier, speedAggregation, sourceResolutionMinutes]);

  // Legacy playback hook (used for calibration phase scrubbing, not forward playback)
  const playback = usePlayback({
    sourceBars,
    events,
    swings,
    filters,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    onPositionChange: useCallback((position: number) => {
      syncChartsToPositionRef.current(position);
    }, []),
  });

  // Handler to refresh aggregated bars after playback advance
  // Backend now controls visibility via playback_index, so we re-fetch to get updated bars
  const handleRefreshAggregatedBars = useCallback(async () => {
    try {
      const [bars1, bars2] = await Promise.all([
        fetchBars(chart1Aggregation),
        fetchBars(chart2Aggregation),
      ]);
      setChart1Bars(bars1);
      setChart2Bars(bars2);
    } catch (err) {
      console.error('Failed to refresh aggregated bars:', err);
    }
  }, [chart1Aggregation, chart2Aggregation]);

  // Forward playback hook (used for forward-only playback after calibration)
  const forwardPlayback = useForwardPlayback({
    calibrationBarCount: calibrationData?.calibration_bar_count || 10000,
    calibrationBars,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    onNewBars: useCallback((newBars: BarData[]) => {
      // Append new bars to source bars for chart display
      setSourceBars(prev => [...prev, ...newBars]);
      // Sync charts when new bars arrive
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        syncChartsToPositionRef.current(lastBar.index);
      }
    }, []),
    onRefreshAggregatedBars: handleRefreshAggregatedBars,
  });

  // Compute highlighted swing for linger state (from forward playback or legacy playback)
  const highlightedSwing = useMemo((): DetectedSwing | undefined => {
    // Check forward playback first (when in PLAYING phase)
    if (calibrationPhase === CalibrationPhase.PLAYING && forwardPlayback.lingerEvent?.swing) {
      const swing = forwardPlayback.lingerEvent.swing;
      return {
        id: swing.id,
        direction: swing.direction as 'bull' | 'bear',
        high_price: swing.high_price,
        high_bar_index: swing.high_bar_index,
        low_price: swing.low_price,
        low_bar_index: swing.low_bar_index,
        size: swing.size,
        rank: swing.rank,
        fib_0: swing.fib_0,
        fib_0382: swing.fib_0382,
        fib_1: swing.fib_1,
        fib_2: swing.fib_2,
      };
    }
    // Fall back to legacy playback
    if (!playback.lingerSwingId) return undefined;
    const swing = swings[playback.lingerSwingId];
    if (!swing) return undefined;
    return discretizationSwingToDetected(swing);
  }, [calibrationPhase, forwardPlayback.lingerEvent, playback.lingerSwingId, swings]);

  // Compute current active swing for calibration mode
  const currentActiveSwing = useMemo((): CalibrationSwing | null => {
    if (calibrationPhase !== CalibrationPhase.CALIBRATED || filteredActiveSwings.length === 0) {
      return null;
    }
    return filteredActiveSwings[currentActiveSwingIndex] || null;
  }, [calibrationPhase, filteredActiveSwings, currentActiveSwingIndex]);

  // Convert current active swing to DetectedSwing for chart overlay
  const calibrationHighlightedSwing = useMemo((): DetectedSwing | undefined => {
    if (!currentActiveSwing) return undefined;
    return calibrationSwingToDetected(currentActiveSwing, 1);
  }, [currentActiveSwing]);

  // Navigation functions for active swing cycling
  const navigatePrevActiveSwing = useCallback(() => {
    if (filteredActiveSwings.length === 0) return;
    setCurrentActiveSwingIndex(prev =>
      prev === 0 ? filteredActiveSwings.length - 1 : prev - 1
    );
  }, [filteredActiveSwings.length]);

  const navigateNextActiveSwing = useCallback(() => {
    if (filteredActiveSwings.length === 0) return;
    setCurrentActiveSwingIndex(prev =>
      prev === filteredActiveSwings.length - 1 ? 0 : prev + 1
    );
  }, [filteredActiveSwings.length]);

  // Handler for toggling scale filter
  const handleToggleScale = useCallback((scale: SwingScaleKey) => {
    setDisplayConfig(prev => {
      const newEnabledScales = new Set(prev.enabledScales);
      if (newEnabledScales.has(scale)) {
        newEnabledScales.delete(scale);
      } else {
        newEnabledScales.add(scale);
      }
      return { ...prev, enabledScales: newEnabledScales };
    });
    // Reset index when filter changes
    setCurrentActiveSwingIndex(0);
  }, []);

  // Handler for setting active swing count
  const handleSetActiveSwingCount = useCallback((count: number) => {
    setDisplayConfig(prev => ({ ...prev, activeSwingCount: count }));
    // Reset index when count changes
    setCurrentActiveSwingIndex(0);
  }, []);

  // Handler to start playback (transition from calibrated to playing)
  const handleStartPlayback = useCallback(() => {
    if (calibrationPhase === CalibrationPhase.CALIBRATED) {
      setCalibrationPhase(CalibrationPhase.PLAYING);
      // Use forward playback for forward-only mode
      forwardPlayback.play();
    }
  }, [calibrationPhase, forwardPlayback]);

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        // Load session info to get source resolution
        const session = await fetchSession();
        const resolutionMinutes = parseResolutionToMinutes(session.resolution);
        setSourceResolutionMinutes(resolutionMinutes);

        // Load source bars
        const source = await fetchBars('S');
        setSourceBars(source);

        // Load chart bars
        const [bars1, bars2] = await Promise.all([
          fetchBars(chart1Aggregation),
          fetchBars(chart2Aggregation),
        ]);
        setChart1Bars(bars1);
        setChart2Bars(bars2);

        // Run discretization if needed
        const state = await fetchDiscretizationState();
        if (!state.has_log) {
          await runDiscretization();
        }

        // Load events and swings
        const [eventData, swingData] = await Promise.all([
          fetchDiscretizationEvents(),
          fetchDiscretizationSwings(),
        ]);
        setEvents(eventData);

        // Index swings by ID
        const swingMap: Record<string, DiscretizationSwing> = {};
        for (const swing of swingData) {
          swingMap[swing.swing_id] = swing;
        }
        setSwings(swingMap);

        // Run calibration - this sets playback_index on the backend
        setCalibrationPhase(CalibrationPhase.CALIBRATING);
        const calibration = await fetchCalibration(Math.min(10000, source.length));
        setCalibrationData(calibration);

        // Re-fetch chart bars now that playback_index is set
        // (initial fetch happened before calibration when playback_index was None)
        const [newBars1, newBars2, newSourceBars] = await Promise.all([
          fetchBars(chart1Aggregation),
          fetchBars(chart2Aggregation),
          fetchBars('S'),
        ]);
        setChart1Bars(newBars1);
        setChart2Bars(newBars2);
        setSourceBars(newSourceBars);

        // Store calibration bars for forward playback
        const calBars = newSourceBars.slice(0, calibration.calibration_bar_count);
        setCalibrationBars(calBars);

        // Reset index and transition to calibrated phase
        // (filteredActiveSwings will be computed by useSwingDisplay hook)
        setCurrentActiveSwingIndex(0);
        setCalibrationPhase(CalibrationPhase.CALIBRATED);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, []);

  // Load chart bars when aggregation changes
  const loadChart1Bars = useCallback(async (scale: AggregationScale) => {
    try {
      const bars = await fetchBars(scale);
      setChart1Bars(bars);
    } catch (err) {
      console.error('Failed to load chart 1 bars:', err);
    }
  }, []);

  const loadChart2Bars = useCallback(async (scale: AggregationScale) => {
    try {
      const bars = await fetchBars(scale);
      setChart2Bars(bars);
    } catch (err) {
      console.error('Failed to load chart 2 bars:', err);
    }
  }, []);

  // Handle aggregation changes
  const handleChart1AggregationChange = useCallback((scale: AggregationScale) => {
    setChart1Aggregation(scale);
    loadChart1Bars(scale);
  }, [loadChart1Bars]);

  const handleChart2AggregationChange = useCallback((scale: AggregationScale) => {
    setChart2Aggregation(scale);
    loadChart2Bars(scale);
  }, [loadChart2Bars]);

  // Keep speedAggregation valid when chart aggregations change
  useEffect(() => {
    const validAggregations = [chart1Aggregation, chart2Aggregation];
    if (!validAggregations.includes(speedAggregation)) {
      // Default to chart1 aggregation if current is no longer valid
      setSpeedAggregation(chart1Aggregation);
    }
  }, [chart1Aggregation, chart2Aggregation, speedAggregation]);

  // Find aggregated bar index for a source bar index
  const findAggBarForSourceIndex = useCallback((bars: BarData[], sourceIndex: number): number => {
    for (let i = 0; i < bars.length; i++) {
      if (sourceIndex >= bars[i].source_start_index && sourceIndex <= bars[i].source_end_index) {
        return i;
      }
    }
    return bars.length - 1;
  }, []);

  // Find the aggregated bar timestamp that contains a given source bar index
  const findBarTimestamp = useCallback((bars: BarData[], sourceIndex: number): number | null => {
    for (const bar of bars) {
      if (sourceIndex >= bar.source_start_index && sourceIndex <= bar.source_end_index) {
        return bar.timestamp;
      }
    }
    // Fallback: find closest bar
    if (bars.length === 0) return null;

    let closest = bars[0];
    for (const bar of bars) {
      if (bar.source_end_index <= sourceIndex) {
        closest = bar;
      } else {
        break;
      }
    }
    return closest.timestamp;
  }, []);

  // Update all markers (position + swing markers) using a single markers plugin
  const updateAllMarkers = useCallback((
    markersPlugin: ISeriesMarkersPluginApi<Time> | null,
    bars: BarData[],
    sourceIndex: number,
    swings: DetectedSwing[],
    highlighted?: DetectedSwing
  ) => {
    if (!markersPlugin || bars.length === 0) return;

    const markers: SeriesMarker<Time>[] = [];

    // Add position marker
    const aggIndex = findAggBarForSourceIndex(bars, sourceIndex);
    if (aggIndex >= 0 && aggIndex < bars.length) {
      const bar = bars[aggIndex];
      markers.push({
        time: bar.timestamp as Time,
        position: 'aboveBar',
        color: '#f7d63e',
        shape: 'arrowDown',
        text: '',
      });
    }

    // Determine which swings to show markers for
    let visibleSwings: DetectedSwing[];
    if (highlighted) {
      visibleSwings = [highlighted];
    } else {
      visibleSwings = swings.filter(swing => {
        const maxBarIndex = Math.max(swing.high_bar_index, swing.low_bar_index);
        return maxBarIndex <= sourceIndex;
      });
    }

    // Add swing HIGH/LOW markers
    for (const swing of visibleSwings) {
      const color = SWING_COLORS[swing.rank] || SWING_COLORS[1];

      // Find timestamps for high and low bars
      const highTimestamp = findBarTimestamp(bars, swing.high_bar_index);
      const lowTimestamp = findBarTimestamp(bars, swing.low_bar_index);

      // Add HIGH marker
      if (highTimestamp !== null) {
        markers.push({
          time: highTimestamp as Time,
          position: 'aboveBar',
          color,
          shape: 'arrowDown',
          text: 'H',
        });
      }

      // Add LOW marker
      if (lowTimestamp !== null) {
        markers.push({
          time: lowTimestamp as Time,
          position: 'belowBar',
          color,
          shape: 'arrowUp',
          text: 'L',
        });
      }
    }

    // Sort markers by time (required by lightweight-charts)
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    markersPlugin.setMarkers(markers);
  }, [findAggBarForSourceIndex, findBarTimestamp]);

  // Get the current playback position based on phase
  const currentPlaybackPosition = useMemo(() => {
    if (calibrationPhase === CalibrationPhase.PLAYING) {
      return forwardPlayback.currentPosition;
    } else if (calibrationPhase === CalibrationPhase.CALIBRATED && calibrationData) {
      return calibrationData.calibration_bar_count - 1;
    }
    return playback.currentPosition;
  }, [calibrationPhase, forwardPlayback.currentPosition, playback.currentPosition, calibrationData]);

  // Note: No client-side filtering needed - backend controls visibility via playback_index
  // The /api/bars endpoint automatically respects the current playback position

  // Sync charts to current position (scrolling only - markers handled separately)
  const syncChartsToPosition = useCallback((sourceIndex: number) => {
    const syncChart = (
      chart: IChartApi | null,
      bars: BarData[],
      forceCenter: boolean = false
    ) => {
      if (!chart || bars.length === 0) return;

      const aggIndex = findAggBarForSourceIndex(bars, sourceIndex);
      const visibleRange = chart.timeScale().getVisibleLogicalRange();

      if (!forceCenter && visibleRange) {
        // Check if current bar is visible with margin
        const rangeSize = visibleRange.to - visibleRange.from;
        const margin = rangeSize * 0.1;
        if (aggIndex >= visibleRange.from + margin && aggIndex <= visibleRange.to - margin) {
          return; // Already visible - no scroll needed
        }
      }

      // Center on current bar with ~100 bars visible
      const barsToShow = 100;
      const halfWindow = Math.floor(barsToShow / 2);
      let from = aggIndex - halfWindow;
      let to = aggIndex + halfWindow;

      if (from < 0) {
        to -= from;
        from = 0;
      }
      if (to >= bars.length) {
        from -= (to - bars.length + 1);
        to = bars.length - 1;
      }
      from = Math.max(0, from);

      chart.timeScale().setVisibleLogicalRange({ from, to });
    };

    syncChart(chart1Ref.current, chart1Bars);
    syncChart(chart2Ref.current, chart2Bars);
  }, [chart1Bars, chart2Bars, findAggBarForSourceIndex]);

  // Update all chart markers when position or swings change
  useEffect(() => {
    updateAllMarkers(
      markers1Ref.current,
      chart1Bars,
      currentPlaybackPosition,
      detectedSwings,
      highlightedSwing
    );
    updateAllMarkers(
      markers2Ref.current,
      chart2Bars,
      currentPlaybackPosition,
      detectedSwings,
      highlightedSwing
    );
  }, [currentPlaybackPosition, detectedSwings, highlightedSwing, chart1Bars, chart2Bars, updateAllMarkers]);

  // Keep the ref updated with the latest syncChartsToPosition
  useEffect(() => {
    syncChartsToPositionRef.current = syncChartsToPosition;
  }, [syncChartsToPosition]);

  // Scroll charts to calibration end when entering CALIBRATED phase
  useEffect(() => {
    if (calibrationPhase === CalibrationPhase.CALIBRATED && calibrationData) {
      // Wait a tick for chart refs to be ready
      const timeout = setTimeout(() => {
        const calibrationEndIndex = calibrationData.calibration_bar_count - 1;
        syncChartsToPositionRef.current(calibrationEndIndex);
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [calibrationPhase, calibrationData]);

  // Fetch detected swings when playback position changes
  // Use debouncing to avoid too many API calls during fast playback
  const lastFetchedPositionRef = useRef<number>(-1);
  const fetchSwingsDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const currentPos = playback.currentPosition;

    // Skip if position hasn't changed significantly (within 5 bars)
    if (Math.abs(currentPos - lastFetchedPositionRef.current) < 5) {
      return;
    }

    // Clear any pending fetch
    if (fetchSwingsDebounceRef.current) {
      clearTimeout(fetchSwingsDebounceRef.current);
    }

    // Debounce the fetch (100ms delay)
    fetchSwingsDebounceRef.current = setTimeout(async () => {
      try {
        const result = await fetchDetectedSwings(currentPos + 1, 2);
        setDetectedSwings(result.swings);
        lastFetchedPositionRef.current = currentPos;
      } catch (err) {
        console.error('Failed to fetch detected swings:', err);
      }
    }, 100);

    return () => {
      if (fetchSwingsDebounceRef.current) {
        clearTimeout(fetchSwingsDebounceRef.current);
      }
    };
  }, [playback.currentPosition]);

  // Handle chart ready callbacks - create marker plugins
  const handleChart1Ready = useCallback((chart: IChartApi, series: ISeriesApi<'Candlestick'>) => {
    chart1Ref.current = chart;
    series1Ref.current = series;
    markers1Ref.current = createSeriesMarkers(series, []);
  }, []);

  const handleChart2Ready = useCallback((chart: IChartApi, series: ISeriesApi<'Candlestick'>) => {
    chart2Ref.current = chart;
    series2Ref.current = series;
    markers2Ref.current = createSeriesMarkers(series, []);
  }, []);

  // Toggle filter
  const handleToggleFilter = useCallback((id: string) => {
    setFilters(prev => prev.map(f =>
      f.id === id ? { ...f, isEnabled: !f.isEnabled } : f
    ));
  }, []);

  // Reset filters to defaults
  const handleResetFilters = useCallback(() => {
    setFilters(INITIAL_FILTERS);
  }, []);

  // Keyboard shortcuts for navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Calibration mode: [ and ] for swing cycling, Space/Enter to start playback
      if (calibrationPhase === CalibrationPhase.CALIBRATED) {
        if (e.key === '[') {
          e.preventDefault();
          navigatePrevActiveSwing();
        } else if (e.key === ']') {
          e.preventDefault();
          navigateNextActiveSwing();
        } else if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          handleStartPlayback();
        }
        return;
      }

      // Playing mode: event navigation and linger navigation
      if (calibrationPhase === CalibrationPhase.PLAYING) {
        // Linger queue navigation (when multiple events at same bar)
        if (forwardPlayback.isLingering && forwardPlayback.lingerQueuePosition && forwardPlayback.lingerQueuePosition.total > 1) {
          // Arrow keys navigate within linger queue
          if (e.key === 'ArrowLeft' && !e.shiftKey) {
            e.preventDefault();
            forwardPlayback.navigatePrevEvent();
            return;
          } else if (e.key === 'ArrowRight' && !e.shiftKey) {
            e.preventDefault();
            forwardPlayback.navigateNextEvent();
            return;
          }
        }

        // Event navigation: [ / ] or Arrow keys jump between events
        // Shift + [ / ] for fine control (bar-by-bar)
        if (e.key === '[') {
          e.preventDefault();
          if (e.shiftKey) {
            // Fine control: step back one bar
            forwardPlayback.stepBack();
          } else {
            // Jump to previous event
            forwardPlayback.jumpToPreviousEvent();
          }
        } else if (e.key === ']') {
          e.preventDefault();
          if (e.shiftKey) {
            // Fine control: step forward one bar
            forwardPlayback.stepForward();
          } else {
            // Jump to next event
            forwardPlayback.jumpToNextEvent();
          }
        } else if (e.key === 'ArrowLeft' && !forwardPlayback.isLingering) {
          e.preventDefault();
          if (e.shiftKey) {
            forwardPlayback.stepBack();
          } else {
            forwardPlayback.jumpToPreviousEvent();
          }
        } else if (e.key === 'ArrowRight' && !forwardPlayback.isLingering) {
          e.preventDefault();
          if (e.shiftKey) {
            forwardPlayback.stepForward();
          } else {
            forwardPlayback.jumpToNextEvent();
          }
        }
        return;
      }

      // Legacy linger mode: Arrow keys for navigation
      if (!playback.isLingering || !playback.lingerQueuePosition) return;
      if (playback.lingerQueuePosition.total <= 1) return;

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        playback.navigatePrevEvent();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        playback.navigateNextEvent();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    calibrationPhase,
    navigatePrevActiveSwing,
    navigateNextActiveSwing,
    handleStartPlayback,
    forwardPlayback.isLingering,
    forwardPlayback.lingerQueuePosition,
    forwardPlayback.navigatePrevEvent,
    forwardPlayback.navigateNextEvent,
    forwardPlayback.jumpToPreviousEvent,
    forwardPlayback.jumpToNextEvent,
    forwardPlayback.stepBack,
    forwardPlayback.stepForward,
    playback.isLingering,
    playback.lingerQueuePosition,
    playback.navigatePrevEvent,
    playback.navigateNextEvent
  ]);

  // Get current timestamp for header
  const currentTimestamp = sourceBars[currentPlaybackPosition]?.timestamp
    ? new Date(sourceBars[currentPlaybackPosition].timestamp * 1000).toISOString()
    : undefined;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-app-bg text-app-text">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-trading-blue border-t-transparent rounded-full mx-auto mb-4"></div>
          <p>Loading data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-app-bg text-app-text">
        <div className="text-center">
          <p className="text-trading-bear mb-4">Error: {error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-trading-blue text-white rounded hover:bg-blue-600"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen w-full bg-app-bg text-app-text font-sans overflow-hidden">
      {/* Header */}
      <Header
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        currentTimestamp={currentTimestamp}
        sourceBarCount={sourceBars.length}
        calibrationStatus={
          calibrationPhase === CalibrationPhase.CALIBRATING
            ? 'calibrating'
            : calibrationPhase === CalibrationPhase.CALIBRATED
            ? 'calibrated'
            : calibrationPhase === CalibrationPhase.PLAYING
            ? 'playing'
            : undefined
        }
      />

      {/* Main Layout */}
      <div className="flex-1 flex min-h-0">
        {/* Sidebar */}
        <div className={`${isSidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 ease-in-out overflow-hidden`}>
          <Sidebar
            filters={filters}
            onToggleFilter={handleToggleFilter}
            onResetDefaults={handleResetFilters}
            className="w-64"
          />
        </div>

        {/* Center Content */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* Charts Area */}
          <ChartArea
            chart1Data={chart1Bars}
            chart2Data={chart2Bars}
            chart1Aggregation={chart1Aggregation}
            chart2Aggregation={chart2Aggregation}
            onChart1AggregationChange={handleChart1AggregationChange}
            onChart2AggregationChange={handleChart2AggregationChange}
            onChart1Ready={handleChart1Ready}
            onChart2Ready={handleChart2Ready}
          />

          {/* Swing Overlays - render Fib level price lines on charts */}
          <SwingOverlay
            series={series1Ref.current}
            swings={calibrationPhase === CalibrationPhase.CALIBRATED ? [] : detectedSwings}
            currentPosition={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentPosition : playback.currentPosition}
            highlightedSwing={calibrationPhase === CalibrationPhase.CALIBRATED ? calibrationHighlightedSwing : highlightedSwing}
          />
          <SwingOverlay
            series={series2Ref.current}
            swings={calibrationPhase === CalibrationPhase.CALIBRATED ? [] : detectedSwings}
            currentPosition={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentPosition : playback.currentPosition}
            highlightedSwing={calibrationPhase === CalibrationPhase.CALIBRATED ? calibrationHighlightedSwing : highlightedSwing}
          />

          {/* Playback Controls */}
          <div className="shrink-0 z-10">
            <PlaybackControls
              playbackState={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.playbackState : playback.playbackState}
              onPlayPause={calibrationPhase === CalibrationPhase.CALIBRATED ? handleStartPlayback : (calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.togglePlayPause : playback.togglePlayPause)}
              onStepBack={calibrationPhase === CalibrationPhase.CALIBRATED ? (() => {}) : (calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.stepBack : playback.stepBack)}
              onStepForward={calibrationPhase === CalibrationPhase.CALIBRATED ? handleStartPlayback : (calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.stepForward : playback.stepForward)}
              onJumpToStart={calibrationPhase === CalibrationPhase.CALIBRATED ? (() => {}) : (calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.jumpToStart : playback.jumpToStart)}
              onJumpToEnd={calibrationPhase === CalibrationPhase.CALIBRATED ? undefined : (calibrationPhase === CalibrationPhase.PLAYING ? undefined : playback.jumpToEnd)}
              // Event navigation (only in PLAYING phase)
              onJumpToPreviousEvent={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.jumpToPreviousEvent : undefined}
              onJumpToNextEvent={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.jumpToNextEvent : undefined}
              hasPreviousEvent={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.hasPreviousEvent : false}
              hasNextEvent={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.hasNextEvent : true}
              currentEventIndex={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentEventIndex : -1}
              totalEvents={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.allEvents.length : 0}
              currentBar={calibrationPhase === CalibrationPhase.CALIBRATED ? (calibrationData?.calibration_bar_count ?? 0) - 1 : (calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentPosition : playback.currentPosition)}
              totalBars={sourceBars.length}
              speedMultiplier={speedMultiplier}
              onSpeedMultiplierChange={setSpeedMultiplier}
              speedAggregation={speedAggregation}
              onSpeedAggregationChange={setSpeedAggregation}
              availableSpeedAggregations={availableSpeedAggregations}
              isLingering={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.isLingering : playback.isLingering}
              lingerTimeLeft={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.lingerTimeLeft : playback.lingerTimeLeft}
              lingerTotalTime={LINGER_DURATION_MS / 1000}
              lingerEventType={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.lingerEvent?.type : playback.lingerEventType}
              lingerQueuePosition={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.lingerQueuePosition : playback.lingerQueuePosition}
              onNavigatePrev={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.navigatePrevEvent : playback.navigatePrevEvent}
              onNavigateNext={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.navigateNextEvent : playback.navigateNextEvent}
              onDismissLinger={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.dismissLinger : playback.dismissLinger}
            />
          </div>

          {/* Explanation Panel / Calibration Report */}
          <div className="h-48 md:h-56 shrink-0">
            <ExplanationPanel
              swing={playback.currentSwing}
              previousSwing={playback.previousSwing}
              calibrationPhase={calibrationPhase}
              calibrationData={calibrationData}
              currentActiveSwing={currentActiveSwing}
              currentActiveSwingIndex={currentActiveSwingIndex}
              totalActiveSwings={filteredActiveSwings.length}
              onNavigatePrev={navigatePrevActiveSwing}
              onNavigateNext={navigateNextActiveSwing}
              onStartPlayback={handleStartPlayback}
              displayConfig={displayConfig}
              filteredStats={filteredStats}
              onToggleScale={handleToggleScale}
              onSetActiveSwingCount={handleSetActiveSwingCount}
            />
          </div>
        </main>
      </div>
    </div>
  );
};
