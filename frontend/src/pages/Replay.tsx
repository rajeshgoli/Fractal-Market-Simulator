import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { IChartApi, ISeriesApi, createSeriesMarkers, SeriesMarker, Time, ISeriesMarkersPluginApi } from 'lightweight-charts';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { ExplanationPanel } from '../components/ExplanationPanel';
import { usePlayback } from '../hooks/usePlayback';
import { fetchBars, fetchDiscretizationState, runDiscretization, fetchDiscretizationEvents, fetchDiscretizationSwings, fetchSession } from '../lib/api';
import { INITIAL_FILTERS, LINGER_DURATION_MS } from '../constants';
import {
  BarData,
  FilterState,
  AggregationScale,
  DiscretizationEvent,
  DiscretizationSwing,
  parseResolutionToMinutes,
  getAggregationLabel,
  getAggregationMinutes,
} from '../types';

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
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);
  const [events, setEvents] = useState<DiscretizationEvent[]>([]);
  const [swings, setSwings] = useState<Record<string, DiscretizationSwing>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Chart refs for syncing
  const chart1Ref = useRef<IChartApi | null>(null);
  const chart2Ref = useRef<IChartApi | null>(null);
  const series1Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const series2Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);

  // Marker plugin refs
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

  // Playback hook - uses ref to avoid stale closure issue
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

  // Update position marker using the markers plugin
  const updatePositionMarker = useCallback((
    markersPlugin: ISeriesMarkersPluginApi<Time> | null,
    bars: BarData[],
    sourceIndex: number
  ) => {
    if (!markersPlugin || bars.length === 0) return;

    const aggIndex = findAggBarForSourceIndex(bars, sourceIndex);
    if (aggIndex < 0 || aggIndex >= bars.length) return;

    const bar = bars[aggIndex];
    const marker: SeriesMarker<Time> = {
      time: bar.timestamp as Time,
      position: 'aboveBar',
      color: '#f7d63e',
      shape: 'arrowDown',
      text: '',
    };
    markersPlugin.setMarkers([marker]);
  }, [findAggBarForSourceIndex]);

  // Sync charts to current position
  const syncChartsToPosition = useCallback((sourceIndex: number) => {
    // Always update position markers regardless of scrolling
    updatePositionMarker(markers1Ref.current, chart1Bars, sourceIndex);
    updatePositionMarker(markers2Ref.current, chart2Bars, sourceIndex);

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
          return; // Already visible - no scroll needed (but marker already updated above)
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
  }, [chart1Bars, chart2Bars, findAggBarForSourceIndex, updatePositionMarker]);

  // Keep the ref updated with the latest syncChartsToPosition
  useEffect(() => {
    syncChartsToPositionRef.current = syncChartsToPosition;
  }, [syncChartsToPosition]);

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

  // Get current timestamp for header
  const currentTimestamp = sourceBars[playback.currentPosition]?.timestamp
    ? new Date(sourceBars[playback.currentPosition].timestamp * 1000).toISOString()
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

          {/* Playback Controls */}
          <div className="shrink-0 z-10">
            <PlaybackControls
              playbackState={playback.playbackState}
              onPlayPause={playback.togglePlayPause}
              onStepBack={playback.stepBack}
              onStepForward={playback.stepForward}
              onJumpToStart={playback.jumpToStart}
              onJumpToEnd={playback.jumpToEnd}
              currentBar={playback.currentPosition}
              totalBars={sourceBars.length}
              speedMultiplier={speedMultiplier}
              onSpeedMultiplierChange={setSpeedMultiplier}
              speedAggregation={speedAggregation}
              onSpeedAggregationChange={setSpeedAggregation}
              availableSpeedAggregations={availableSpeedAggregations}
              isLingering={playback.isLingering}
              lingerTimeLeft={playback.lingerTimeLeft}
              lingerTotalTime={LINGER_DURATION_MS / 1000}
              lingerEventType={playback.lingerEventType}
              lingerQueuePosition={playback.lingerQueuePosition}
            />
          </div>

          {/* Explanation Panel */}
          <div className="h-48 md:h-56 shrink-0">
            <ExplanationPanel
              swing={playback.currentSwing}
              previousSwing={playback.previousSwing}
            />
          </div>
        </main>
      </div>
    </div>
  );
};
