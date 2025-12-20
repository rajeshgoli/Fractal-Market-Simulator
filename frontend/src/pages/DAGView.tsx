import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { IChartApi, ISeriesApi, createSeriesMarkers, Time, ISeriesMarkersPluginApi } from 'lightweight-charts';
import { Header } from '../components/Header';
import { Sidebar, DAG_LINGER_EVENTS, LingerEventConfig, DagContext } from '../components/Sidebar';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { DAGStatePanel } from '../components/DAGStatePanel';
import { LegOverlay } from '../components/LegOverlay';
import { OrphanedOriginsOverlay } from '../components/OrphanedOriginsOverlay';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import {
  fetchBars,
  fetchSession,
  fetchCalibration,
  fetchDagState,
  DagStateResponse,
  DagLeg,
} from '../lib/api';
import { LINGER_DURATION_MS } from '../constants';
import {
  BarData,
  AggregationScale,
  CalibrationData,
  CalibrationPhase,
  PlaybackState,
  parseResolutionToMinutes,
  getAggregationLabel,
  getAggregationMinutes,
  ActiveLeg,
  LegEvent,
} from '../types';

/**
 * Convert DagLeg from API to ActiveLeg for visualization.
 */
function dagLegToActiveLeg(leg: DagLeg): ActiveLeg {
  return {
    leg_id: leg.leg_id,
    direction: leg.direction,
    pivot_price: leg.pivot_price,
    pivot_index: leg.pivot_index,
    origin_price: leg.origin_price,
    origin_index: leg.origin_index,
    retracement_pct: leg.retracement_pct,
    formed: leg.formed,
    status: leg.status,
    bar_count: leg.bar_count,
  };
}

/**
 * DAGView - Visualization mode for watching the DAG build in real-time.
 *
 * This view focuses on leg visualization (pre-formation candidates) rather than
 * formed swings. It shows:
 * - Active legs drawn as lines from pivot to origin
 * - Bull legs colored blue, bear legs colored red
 * - Stale legs shown dashed/yellow
 * - DAG internal state panel (legs, orphaned origins, pending pivots)
 */
export const DAGView: React.FC = () => {
  // Chart aggregation state
  const [chart1Aggregation, setChart1Aggregation] = useState<AggregationScale>('L');
  const [chart2Aggregation, setChart2Aggregation] = useState<AggregationScale>('S');

  // Speed control state
  const [sourceResolutionMinutes, setSourceResolutionMinutes] = useState<number>(5);
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(1);
  const [speedAggregation, setSpeedAggregation] = useState<AggregationScale>('L');

  // Data state
  const [sourceBars, setSourceBars] = useState<BarData[]>([]);
  const [calibrationBars, setCalibrationBars] = useState<BarData[]>([]);
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Session metadata
  const [sessionInfo, setSessionInfo] = useState<{
    windowOffset: number;
    totalSourceBars: number;
  } | null>(null);

  // Calibration state
  const [calibrationPhase, setCalibrationPhase] = useState<CalibrationPhase>(CalibrationPhase.NOT_STARTED);
  const [calibrationData, setCalibrationData] = useState<CalibrationData | null>(null);

  // DAG state
  const [dagState, setDagState] = useState<DagStateResponse | null>(null);
  const [recentLegEvents, setRecentLegEvents] = useState<LegEvent[]>([]);
  const [isDagLoading, setIsDagLoading] = useState(false);

  // Linger toggle state (for DAG mode, default OFF for continuous observation)
  const [lingerEnabled, setLingerEnabled] = useState(false);

  // Sidebar state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Linger event toggles (DAG-specific events)
  const [lingerEvents, setLingerEvents] = useState<LingerEventConfig[]>(DAG_LINGER_EVENTS);

  // Chart refs
  const chart1Ref = useRef<IChartApi | null>(null);
  const chart2Ref = useRef<IChartApi | null>(null);
  const series1Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const series2Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const markers1Ref = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const markers2Ref = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Main content ref for screenshot capture
  const mainContentRef = useRef<HTMLElement | null>(null);

  // Sync ref
  const syncChartsToPositionRef = useRef<(sourceIndex: number) => void>(() => {});

  // Compute available speed aggregation options
  const availableSpeedAggregations = useMemo(() => {
    const options: { value: AggregationScale; label: string }[] = [];
    const seen = new Set<AggregationScale>();

    if (!seen.has(chart1Aggregation)) {
      options.push({ value: chart1Aggregation, label: getAggregationLabel(chart1Aggregation) });
      seen.add(chart1Aggregation);
    }

    if (!seen.has(chart2Aggregation)) {
      options.push({ value: chart2Aggregation, label: getAggregationLabel(chart2Aggregation) });
      seen.add(chart2Aggregation);
    }

    return options;
  }, [chart1Aggregation, chart2Aggregation]);

  // Calculate bars per advance
  const barsPerAdvance = useMemo(() => {
    const aggMinutes = getAggregationMinutes(speedAggregation);
    return Math.max(1, Math.round(aggMinutes / sourceResolutionMinutes));
  }, [speedAggregation, sourceResolutionMinutes]);

  // Calculate playback interval
  const effectivePlaybackIntervalMs = useMemo(() => {
    return Math.max(50, Math.round(1000 / speedMultiplier));
  }, [speedMultiplier]);

  // Handler to refresh aggregated bars
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

  // Forward playback hook
  // For DAG mode with bar_count=0 calibration, we start from position -1 (before first bar)
  const forwardPlayback = useForwardPlayback({
    calibrationBarCount: calibrationData?.calibration_bar_count ?? 0,
    calibrationBars,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    barsPerAdvance,
    filters: lingerEvents,
    enabledScales: new Set(['XL', 'L', 'M']),
    lingerEnabled, // Use lingerEnabled state for toggle
    onNewBars: useCallback((newBars: BarData[]) => {
      setSourceBars(prev => [...prev, ...newBars]);
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        syncChartsToPositionRef.current(lastBar.index);
      }
    }, []),
    onRefreshAggregatedBars: handleRefreshAggregatedBars,
  });

  // Convert DAG legs to ActiveLeg[] for visualization
  const activeLegs = useMemo((): ActiveLeg[] => {
    if (!dagState) return [];
    return dagState.active_legs.map(dagLegToActiveLeg);
  }, [dagState]);

  // Get current playback position
  const currentPlaybackPosition = useMemo(() => {
    if (calibrationPhase === CalibrationPhase.PLAYING) {
      return forwardPlayback.currentPosition;
    } else if (calibrationPhase === CalibrationPhase.CALIBRATED && calibrationData) {
      return calibrationData.calibration_bar_count - 1;
    }
    return 0;
  }, [calibrationPhase, forwardPlayback.currentPosition, calibrationData]);

  // Handler to start playback
  const handleStartPlayback = useCallback(() => {
    if (calibrationPhase === CalibrationPhase.CALIBRATED) {
      setCalibrationPhase(CalibrationPhase.PLAYING);
      forwardPlayback.play();
    }
  }, [calibrationPhase, forwardPlayback]);

  // Handler for toggling linger event types
  const handleToggleLingerEvent = useCallback((eventId: string) => {
    setLingerEvents(prev =>
      prev.map(e => e.id === eventId ? { ...e, isEnabled: !e.isEnabled } : e)
    );
  }, []);

  // Handler for resetting defaults
  const handleResetDefaults = useCallback(() => {
    setLingerEvents(DAG_LINGER_EVENTS);
  }, []);

  // Compute feedback context for DAG mode
  const feedbackContext = useMemo(() => {
    if (calibrationPhase !== CalibrationPhase.CALIBRATED && calibrationPhase !== CalibrationPhase.PLAYING) {
      return null;
    }

    let stateString: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
    if (calibrationPhase === CalibrationPhase.CALIBRATED) {
      stateString = 'calibration_complete';
    } else if (forwardPlayback.playbackState === PlaybackState.PLAYING) {
      stateString = 'playing';
    } else {
      stateString = 'paused';
    }

    // Count events by type
    let swingsInvalidated = 0;
    let swingsCompleted = 0;
    for (const event of forwardPlayback.allEvents) {
      if (event.type === 'SWING_INVALIDATED' || event.type === 'LEG_INVALIDATED') swingsInvalidated++;
      if (event.type === 'SWING_COMPLETED') swingsCompleted++;
    }

    return {
      playbackState: forwardPlayback.playbackState,
      calibrationPhase: stateString,
      windowOffset: sessionInfo?.windowOffset || 0,
      calibrationBarCount: calibrationData?.calibration_bar_count || 0,
      currentBarIndex: currentPlaybackPosition,
      swingsFoundByScale: { XL: 0, L: 0, M: 0, S: 0 }, // Not used in DAG mode
      totalEvents: forwardPlayback.allEvents.length,
      swingsInvalidated,
      swingsCompleted,
    };
  }, [
    calibrationPhase,
    forwardPlayback.playbackState,
    forwardPlayback.allEvents,
    sessionInfo?.windowOffset,
    calibrationData?.calibration_bar_count,
    currentPlaybackPosition,
  ]);

  // Compute DAG context for feedback
  const dagContext = useMemo((): DagContext | undefined => {
    if (!dagState) return undefined;
    // Count pending pivots (null means none)
    const pendingPivotsCount = (dagState.pending_pivots?.bull ? 1 : 0) +
                               (dagState.pending_pivots?.bear ? 1 : 0);
    return {
      activeLegsCount: dagState.active_legs.length,
      orphanedOriginsCount: {
        bull: dagState.orphaned_origins.bull?.length || 0,
        bear: dagState.orphaned_origins.bear?.length || 0,
      },
      pendingPivotsCount,
    };
  }, [dagState]);

  // Load initial data
  // DAG mode: Initialize with bar_count=0 for incremental build from bar 0 (#179)
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        // Load session info
        const session = await fetchSession();
        const resolutionMinutes = parseResolutionToMinutes(session.resolution);
        setSourceResolutionMinutes(resolutionMinutes);
        setSessionInfo({
          windowOffset: session.window_offset,
          totalSourceBars: session.total_source_bars,
        });

        // Load source bars (need these for total count display, but won't show initially)
        const source = await fetchBars('S');

        // DAG mode: Initialize with bar_count=0 for incremental build
        // This creates an empty detector ready to process bars one by one
        setCalibrationPhase(CalibrationPhase.CALIBRATING);
        const calibration = await fetchCalibration(0);
        setCalibrationData(calibration);

        // Initially no bars visible - they will be added as playback advances
        setSourceBars([]);
        setCalibrationBars([]);

        // Load empty chart bars (backend returns empty when no bars processed)
        const [bars1, bars2] = await Promise.all([
          fetchBars(chart1Aggregation),
          fetchBars(chart2Aggregation),
        ]);
        setChart1Bars(bars1);
        setChart2Bars(bars2);

        // Fetch initial DAG state (should be empty)
        const initialDagState = await fetchDagState();
        setDagState(initialDagState);

        // Ready to play - user presses play to start incremental build
        setCalibrationPhase(CalibrationPhase.CALIBRATED);

        // Store total bar count for display
        setSessionInfo(prev => prev ? {
          ...prev,
          totalSourceBars: source.length,
        } : { windowOffset: session.window_offset, totalSourceBars: source.length });
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

  // Keep speedAggregation valid
  useEffect(() => {
    const validAggregations = [chart1Aggregation, chart2Aggregation];
    if (!validAggregations.includes(speedAggregation)) {
      setSpeedAggregation(chart1Aggregation);
    }
  }, [chart1Aggregation, chart2Aggregation, speedAggregation]);

  // Find aggregated bar index for source index
  const findAggBarForSourceIndex = useCallback((bars: BarData[], sourceIndex: number): number => {
    for (let i = 0; i < bars.length; i++) {
      if (sourceIndex >= bars[i].source_start_index && sourceIndex <= bars[i].source_end_index) {
        return i;
      }
    }
    return bars.length - 1;
  }, []);

  // Sync charts to position
  const syncChartsToPosition = useCallback((sourceIndex: number) => {
    const syncChart = (chart: IChartApi | null, bars: BarData[]) => {
      if (!chart || bars.length === 0) return;

      const aggIndex = findAggBarForSourceIndex(bars, sourceIndex);
      const visibleRange = chart.timeScale().getVisibleLogicalRange();

      if (!visibleRange) {
        const barsToShow = 100;
        const halfWindow = Math.floor(barsToShow / 2);
        const from = Math.max(0, aggIndex - halfWindow);
        const to = Math.min(bars.length - 1, aggIndex + halfWindow);
        chart.timeScale().setVisibleLogicalRange({ from, to });
        return;
      }

      const rangeSize = visibleRange.to - visibleRange.from;
      const margin = rangeSize * 0.05;
      if (aggIndex >= visibleRange.from + margin && aggIndex <= visibleRange.to - margin) {
        return;
      }

      const positionRatio = 0.8;
      let from = aggIndex - rangeSize * positionRatio;
      let to = from + rangeSize;

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

  // Keep sync ref updated
  useEffect(() => {
    syncChartsToPositionRef.current = syncChartsToPosition;
  }, [syncChartsToPosition]);

  // Scroll charts when entering CALIBRATED phase
  useEffect(() => {
    if (calibrationPhase === CalibrationPhase.CALIBRATED && calibrationData) {
      const timeout = setTimeout(() => {
        const calibrationEndIndex = calibrationData.calibration_bar_count - 1;
        syncChartsToPositionRef.current(calibrationEndIndex);
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [calibrationPhase, calibrationData]);

  // Fetch DAG state when position changes (handles both play and step forward)
  useEffect(() => {
    if (calibrationPhase !== CalibrationPhase.PLAYING) {
      return;
    }

    const fetchState = async () => {
      setIsDagLoading(true);
      try {
        const state = await fetchDagState();
        setDagState(state);
      } catch (err) {
        console.error('Failed to fetch DAG state:', err);
      } finally {
        setIsDagLoading(false);
      }
    };

    // Fetch whenever position changes (covers both play and manual step)
    fetchState();
  }, [calibrationPhase, currentPlaybackPosition]);

  // Collect leg events from forward playback
  useEffect(() => {
    const legEvents: LegEvent[] = [];
    for (const event of forwardPlayback.allEvents) {
      if (event.type === 'LEG_CREATED' || event.type === 'LEG_PRUNED' || event.type === 'LEG_INVALIDATED') {
        legEvents.push({
          type: event.type as LegEvent['type'],
          leg_id: event.swing_id,
          bar_index: event.bar_index,
          direction: event.direction as 'bull' | 'bear',
          reason: event.trigger_explanation,
        });
      }
    }
    setRecentLegEvents(legEvents.slice(-20).reverse());
  }, [forwardPlayback.allEvents]);

  // Handle chart ready callbacks
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

  // Keyboard shortcuts for DAG mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keyboard shortcuts when typing in input/textarea elements
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      // Calibrated phase: Space/Enter to start playback
      if (calibrationPhase === CalibrationPhase.CALIBRATED) {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          handleStartPlayback();
        }
        return;
      }

      // Playing phase
      if (calibrationPhase === CalibrationPhase.PLAYING) {
        // Escape key dismisses linger
        if (e.key === 'Escape' && forwardPlayback.isLingering) {
          e.preventDefault();
          forwardPlayback.dismissLinger();
          return;
        }

        // Space toggles play/pause
        if (e.key === ' ') {
          e.preventDefault();
          forwardPlayback.togglePlayPause();
          return;
        }

        // Linger queue navigation (when multiple events at same bar)
        if (forwardPlayback.isLingering && forwardPlayback.lingerQueuePosition && forwardPlayback.lingerQueuePosition.total > 1) {
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

        // Step controls: [ / ] or Arrow keys
        // Shift modifier for fine control (bar-by-bar)
        if (e.key === '[') {
          e.preventDefault();
          if (e.shiftKey) {
            forwardPlayback.stepBack();
          } else {
            forwardPlayback.stepBack();
          }
        } else if (e.key === ']') {
          e.preventDefault();
          if (e.shiftKey) {
            forwardPlayback.stepForward();
          } else {
            forwardPlayback.stepForward();
          }
        } else if (e.key === 'ArrowLeft' && !forwardPlayback.isLingering) {
          e.preventDefault();
          forwardPlayback.stepBack();
        } else if (e.key === 'ArrowRight' && !forwardPlayback.isLingering) {
          e.preventDefault();
          forwardPlayback.stepForward();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    calibrationPhase,
    handleStartPlayback,
    forwardPlayback.isLingering,
    forwardPlayback.lingerQueuePosition,
    forwardPlayback.dismissLinger,
    forwardPlayback.togglePlayPause,
    forwardPlayback.stepBack,
    forwardPlayback.stepForward,
    forwardPlayback.navigatePrevEvent,
    forwardPlayback.navigateNextEvent,
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
          <p>Loading DAG visualization...</p>
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
            mode="dag"
            lingerEvents={lingerEvents}
            onToggleLingerEvent={handleToggleLingerEvent}
            onResetDefaults={handleResetDefaults}
            className="w-64"
            showFeedback={calibrationPhase === CalibrationPhase.CALIBRATED || calibrationPhase === CalibrationPhase.PLAYING}
            isLingering={forwardPlayback.isLingering}
            lingerEvent={forwardPlayback.lingerEvent}
            currentPlaybackBar={currentPlaybackPosition}
            feedbackContext={feedbackContext || undefined}
            onFeedbackFocus={forwardPlayback.pauseLingerTimer}
            onFeedbackBlur={forwardPlayback.resumeLingerTimer}
            onPausePlayback={forwardPlayback.pause}
            dagContext={dagContext}
            screenshotTargetRef={mainContentRef}
          />
        </div>

        <main ref={mainContentRef} className="flex-1 flex flex-col min-w-0">
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

          {/* Leg Overlays - render diagonal leg lines on charts */}
          <LegOverlay
            chart={chart1Ref.current}
            series={series1Ref.current}
            legs={activeLegs}
            bars={chart1Bars}
            currentPosition={currentPlaybackPosition}
          />
          <LegOverlay
            chart={chart2Ref.current}
            series={series2Ref.current}
            legs={activeLegs}
            bars={chart2Bars}
            currentPosition={currentPlaybackPosition}
          />

          {/* Orphaned Origins Overlays - render markers for preserved pivots (#182) */}
          <OrphanedOriginsOverlay
            markersPlugin={markers1Ref.current}
            bullOrigins={dagState?.orphaned_origins.bull ?? []}
            bearOrigins={dagState?.orphaned_origins.bear ?? []}
            bars={chart1Bars}
            currentPosition={currentPlaybackPosition}
          />
          <OrphanedOriginsOverlay
            markersPlugin={markers2Ref.current}
            bullOrigins={dagState?.orphaned_origins.bull ?? []}
            bearOrigins={dagState?.orphaned_origins.bear ?? []}
            bars={chart2Bars}
            currentPosition={currentPlaybackPosition}
          />

          {/* Playback Controls */}
          <div className="shrink-0 z-10">
            <PlaybackControls
              playbackState={
                calibrationPhase === CalibrationPhase.PLAYING
                  ? forwardPlayback.playbackState
                  : calibrationPhase === CalibrationPhase.CALIBRATED
                  ? PlaybackState.STOPPED
                  : PlaybackState.STOPPED
              }
              onPlayPause={
                calibrationPhase === CalibrationPhase.CALIBRATED
                  ? handleStartPlayback
                  : forwardPlayback.togglePlayPause
              }
              onStepBack={forwardPlayback.stepBack}
              onStepForward={
                calibrationPhase === CalibrationPhase.CALIBRATED
                  ? handleStartPlayback
                  : forwardPlayback.stepForward
              }
              onJumpToStart={forwardPlayback.jumpToStart}
              onJumpToEnd={undefined}
              onJumpToPreviousEvent={undefined}
              onJumpToNextEvent={undefined}
              hasPreviousEvent={false}
              hasNextEvent={!forwardPlayback.endOfData}
              currentEventIndex={forwardPlayback.currentEventIndex}
              totalEvents={forwardPlayback.allEvents.length}
              currentBar={Math.max(0, currentPlaybackPosition + 1)}
              totalBars={sessionInfo?.totalSourceBars || 0}
              calibrationBarCount={0}
              windowOffset={sessionInfo?.windowOffset}
              totalSourceBars={sessionInfo?.totalSourceBars}
              speedMultiplier={speedMultiplier}
              onSpeedMultiplierChange={setSpeedMultiplier}
              speedAggregation={speedAggregation}
              onSpeedAggregationChange={setSpeedAggregation}
              availableSpeedAggregations={availableSpeedAggregations}
              isLingering={forwardPlayback.isLingering}
              lingerTimeLeft={forwardPlayback.lingerTimeLeft}
              lingerTotalTime={LINGER_DURATION_MS / 1000}
              lingerEventType={forwardPlayback.lingerEvent?.type}
              lingerQueuePosition={forwardPlayback.lingerQueuePosition}
              onNavigatePrev={forwardPlayback.navigatePrevEvent}
              onNavigateNext={forwardPlayback.navigateNextEvent}
              onDismissLinger={forwardPlayback.dismissLinger}
              lingerEnabled={lingerEnabled}
              onToggleLinger={() => setLingerEnabled(prev => !prev)}
            />
          </div>

          {/* DAG State Panel - Always shown in DAG mode */}
          <div className="h-48 md:h-56 shrink-0">
            <DAGStatePanel
              dagState={dagState}
              recentLegEvents={recentLegEvents}
              isLoading={isDagLoading}
            />
          </div>
        </main>
      </div>
    </div>
  );
};
