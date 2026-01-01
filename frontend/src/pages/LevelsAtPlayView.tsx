import React, { useEffect, useCallback, useMemo, useState, useRef } from 'react';
import { Header } from '../components/Header';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { ResizeHandle } from '../components/ResizeHandle';
import { ReferenceTelemetryPanel } from '../components/ReferenceTelemetryPanel';
import { ReferenceLegOverlay } from '../components/ReferenceLegOverlay';
import { SettingsPanel } from '../components/SettingsPanel';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import { useChartPreferences } from '../hooks/useChartPreferences';
import { useSessionSettings } from '../hooks/useSessionSettings';
import { useReferenceState } from '../hooks/useReferenceState';
import {
  fetchBars,
  fetchSession,
  restartSession,
  advanceReplay,
} from '../lib/api';
import { formatReplayBarsData } from '../utils/barDataUtils';
import {
  BarData,
  AggregationScale,
  PlaybackState,
  parseResolutionToMinutes,
  getAggregationLabel,
  getAggregationMinutes,
  getSmallestValidAggregation,
  clampAggregationToSource,
} from '../types';
import type { ViewMode } from '../App';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

interface LevelsAtPlayViewProps {
  onNavigate: (view: ViewMode) => void;
}

export const LevelsAtPlayView: React.FC<LevelsAtPlayViewProps> = ({ onNavigate }) => {
  // Chart and speed preferences (persisted to localStorage)
  const chartPrefs = useChartPreferences();

  // Session settings (persisted to localStorage)
  const sessionSettings = useSessionSettings();

  // Reference state hook (Phase 2: includes sticky leg support)
  const { referenceState, fetchReferenceState, fadingRefs, stickyLegIds, toggleStickyLeg } = useReferenceState();

  // Core state (#412: simplified from CalibrationData)
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [calibrationBarCount, setCalibrationBarCount] = useState(0);
  const [calibrationBars, setCalibrationBars] = useState<BarData[]>([]);
  const [sourceBars, setSourceBars] = useState<BarData[]>([]);
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);
  const [sourceResolutionMinutes, setSourceResolutionMinutes] = useState(1);
  const [dataFileName, setDataFileName] = useState<string>('');
  const [sessionInfo, setSessionInfo] = useState<{ windowOffset: number; totalSourceBars: number } | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isProcessingTill, setIsProcessingTill] = useState(false);
  const [showFiltered, setShowFiltered] = useState(false);  // Reference Observation mode

  // Chart refs
  const chart1Ref = useRef<IChartApi | null>(null);
  const chart2Ref = useRef<IChartApi | null>(null);
  const series1Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const series2Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const syncChartsToPositionRef = useRef<(index: number) => void>(() => {});

  // Compute available speed aggregation options
  const availableSpeedAggregations = useMemo(() => {
    const options: { value: AggregationScale; label: string }[] = [];
    const seen = new Set<AggregationScale>();

    if (!seen.has(chartPrefs.chart1Aggregation)) {
      options.push({ value: chartPrefs.chart1Aggregation, label: getAggregationLabel(chartPrefs.chart1Aggregation) });
      seen.add(chartPrefs.chart1Aggregation);
    }

    if (!seen.has(chartPrefs.chart2Aggregation)) {
      options.push({ value: chartPrefs.chart2Aggregation, label: getAggregationLabel(chartPrefs.chart2Aggregation) });
      seen.add(chartPrefs.chart2Aggregation);
    }

    return options;
  }, [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation]);

  // Calculate bars per advance (aggregation factor)
  const aggregationBarsPerAdvance = useMemo(() => {
    const aggMinutes = getAggregationMinutes(chartPrefs.speedAggregation);
    return Math.max(1, Math.round(aggMinutes / sourceResolutionMinutes));
  }, [chartPrefs.speedAggregation, sourceResolutionMinutes]);

  // Calculate playback interval and speed compensation
  const MIN_INTERVAL_MS = 50;
  const { effectivePlaybackIntervalMs, barsPerAdvance } = useMemo(() => {
    const rawIntervalMs = 1000 / chartPrefs.speedMultiplier;
    const speedCompensationMultiplier = rawIntervalMs < MIN_INTERVAL_MS
      ? Math.ceil(MIN_INTERVAL_MS / rawIntervalMs)
      : 1;
    return {
      effectivePlaybackIntervalMs: Math.max(MIN_INTERVAL_MS, Math.round(rawIntervalMs)),
      barsPerAdvance: aggregationBarsPerAdvance * speedCompensationMultiplier,
    };
  }, [chartPrefs.speedMultiplier, aggregationBarsPerAdvance]);

  // Handler for aggregated bars from API response
  const handleAggregatedBarsChange = useCallback((aggBars: any) => {
    const chart1BarData = aggBars[chartPrefs.chart1Aggregation as keyof typeof aggBars];
    const chart2BarData = aggBars[chartPrefs.chart2Aggregation as keyof typeof aggBars];
    if (chart1BarData) setChart1Bars(chart1BarData);
    if (chart2BarData) setChart2Bars(chart2BarData);
  }, [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation]);

  // Forward playback hook (#412: simplified from CalibrationData)
  const forwardPlayback = useForwardPlayback({
    calibrationBarCount,
    calibrationBars,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    barsPerAdvance,
    filters: [],
    lingerEnabled: false,
    chartAggregationScales: [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation],
    includeDagState: false,
    onNewBars: useCallback((newBars: BarData[]) => {
      setSourceBars(prev => [...prev, ...newBars]);
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        syncChartsToPositionRef.current(lastBar.index);
      }
    }, []),
    onAggregatedBarsChange: handleAggregatedBarsChange,
    onDagStateChange: () => {},
  });

  // Get current playback position (#412: simplified from CalibrationData)
  const currentPlaybackPosition = useMemo(() => {
    if (isPlaying) {
      return forwardPlayback.currentPosition;
    }
    return calibrationBarCount > 0 ? calibrationBarCount - 1 : 0;
  }, [isPlaying, forwardPlayback.currentPosition, calibrationBarCount]);

  // Fetch reference state when playback position changes (#412: simplified from CalibrationData)
  useEffect(() => {
    if (calibrationBarCount > 0) {
      fetchReferenceState(currentPlaybackPosition);
    }
  }, [currentPlaybackPosition, calibrationBarCount, fetchReferenceState]);

  // Compute a "live" aggregated bar from source bars for incremental display
  const computeLiveBar = useCallback((
    aggBar: BarData,
    currentPosition: number
  ): BarData | null => {
    const relevantSourceBars = sourceBars.filter(
      sb => sb.index >= aggBar.source_start_index && sb.index <= currentPosition
    );
    if (relevantSourceBars.length === 0) return null;

    const firstBar = relevantSourceBars[0];
    const lastBar = relevantSourceBars[relevantSourceBars.length - 1];

    return {
      ...aggBar,
      open: firstBar.open,
      high: Math.max(...relevantSourceBars.map(b => b.high)),
      low: Math.min(...relevantSourceBars.map(b => b.low)),
      close: lastBar.close,
      source_end_index: currentPosition,
    };
  }, [sourceBars]);

  // Filter chart bars to only show candles up to current playback position
  // Always filter based on position - don't show all bars before playback starts (#412)
  const visibleChart1Bars = useMemo(() => {
    const result: BarData[] = [];
    for (const bar of chart1Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        if (liveBar) result.push(liveBar);
      }
    }
    return result;
  }, [chart1Bars, currentPlaybackPosition, computeLiveBar]);

  const visibleChart2Bars = useMemo(() => {
    const result: BarData[] = [];
    for (const bar of chart2Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        if (liveBar) result.push(liveBar);
      }
    }
    return result;
  }, [chart2Bars, currentPlaybackPosition, computeLiveBar]);

  // Chart ready handlers
  const handleChart1Ready = useCallback((chart: IChartApi, series: ISeriesApi<'Candlestick'>) => {
    chart1Ref.current = chart;
    series1Ref.current = series;
  }, []);

  const handleChart2Ready = useCallback((chart: IChartApi, series: ISeriesApi<'Candlestick'>) => {
    chart2Ref.current = chart;
    series2Ref.current = series;
  }, []);

  const handleStartPlayback = useCallback(() => {
    if (!isPlaying) {
      setIsPlaying(true);
      forwardPlayback.play();
    }
  }, [isPlaying, forwardPlayback]);

  const handleStepForward = useCallback(() => {
    if (!isPlaying) {
      setIsPlaying(true);
    }
    forwardPlayback.stepForward();
  }, [isPlaying, forwardPlayback]);

  const handleProcessTill = useCallback(async (_targetTimestamp: number, barCount: number) => {
    if (isPlaying && forwardPlayback.playbackState === PlaybackState.PLAYING) {
      throw new Error('Stop playback first');
    }
    if (barCount <= 0) {
      throw new Error('Must advance at least 1 bar');
    }

    setIsProcessingTill(true);
    try {
      if (!isPlaying) {
        setIsPlaying(true);
      }

      const response = await advanceReplay(
        0,
        currentPlaybackPosition,
        barCount,
        [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation],
        false
      );

      if (response.new_bars && response.new_bars.length > 0) {
        const newBars = formatReplayBarsData(response.new_bars);
        setSourceBars(prev => [...prev, ...newBars]);
        const allVisibleBars = [...forwardPlayback.visibleBars, ...newBars];
        forwardPlayback.syncToPosition(
          response.current_bar_index,
          allVisibleBars,
          response.csv_index,
          response.events
        );
      }

      if (response.aggregated_bars) {
        handleAggregatedBarsChange(response.aggregated_bars);
      }

      if (response.current_bar_index >= 0) {
        syncChartsToPositionRef.current(response.current_bar_index);
      }
    } finally {
      setIsProcessingTill(false);
    }
  }, [
    isPlaying,
    forwardPlayback,
    currentPlaybackPosition,
    chartPrefs.chart1Aggregation,
    chartPrefs.chart2Aggregation,
    handleAggregatedBarsChange,
  ]);

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

  const handleChart1AggregationChange = useCallback((scale: AggregationScale) => {
    chartPrefs.setChart1Aggregation(scale);
    loadChart1Bars(scale);
  }, [chartPrefs.setChart1Aggregation, loadChart1Bars]);

  const handleChart2AggregationChange = useCallback((scale: AggregationScale) => {
    chartPrefs.setChart2Aggregation(scale);
    loadChart2Bars(scale);
  }, [chartPrefs.setChart2Aggregation, loadChart2Bars]);

  // Keep speedAggregation valid
  useEffect(() => {
    const validAggregations = [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation];
    if (!validAggregations.includes(chartPrefs.speedAggregation)) {
      chartPrefs.setSpeedAggregation(chartPrefs.chart1Aggregation);
    }
  }, [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation, chartPrefs.speedAggregation, chartPrefs.setSpeedAggregation]);

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

  // Keep sync refs updated
  useEffect(() => {
    syncChartsToPositionRef.current = syncChartsToPosition;
  }, [syncChartsToPosition]);

  // Scroll charts when data is first loaded (before playing) (#412: simplified from CalibrationData)
  useEffect(() => {
    if (!isPlaying && calibrationBarCount > 0) {
      const timeout = setTimeout(() => {
        const calibrationEndIndex = calibrationBarCount - 1;
        syncChartsToPositionRef.current(calibrationEndIndex);
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [isPlaying, calibrationBarCount]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      // Space/Enter to start or toggle playback
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        if (!isPlaying) {
          handleStartPlayback();
        } else {
          forwardPlayback.togglePlayPause();
        }
        return;
      }

      if (isPlaying) {
        if (e.key === '[') {
          e.preventDefault();
          forwardPlayback.stepBack();
        } else if (e.key === ']') {
          e.preventDefault();
          forwardPlayback.stepForward();
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          forwardPlayback.stepBack();
        } else if (e.key === 'ArrowRight') {
          e.preventDefault();
          forwardPlayback.stepForward();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isPlaying, handleStartPlayback, forwardPlayback]);

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      if (!sessionSettings.isLoaded) return;

      setIsLoading(true);
      setError(null);
      try {
        const session = await fetchSession();

        if (!session.initialized) {
          if (sessionSettings.hasSavedSession && sessionSettings.dataFile) {
            try {
              await restartSession({
                data_file: sessionSettings.dataFile,
                start_date: sessionSettings.startDate || undefined,
              });
              const newSession = await fetchSession();
              if (!newSession.initialized) {
                throw new Error('Failed to initialize session after restart');
              }
              return loadSessionData(newSession);
            } catch (restartErr) {
              console.warn('Failed to restore saved session:', restartErr);
              sessionSettings.clearSession();
              setIsSettingsOpen(true);
              setIsLoading(false);
              return;
            }
          } else {
            setIsSettingsOpen(true);
            setIsLoading(false);
            return;
          }
        }

        await loadSessionData(session);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data');
        setIsLoading(false);
      }
    };

    const loadSessionData = async (session: Awaited<ReturnType<typeof fetchSession>>) => {
      try {
        const resolutionMinutes = parseResolutionToMinutes(session.resolution);
        setSourceResolutionMinutes(resolutionMinutes);
        setSessionInfo({
          windowOffset: session.window_offset,
          totalSourceBars: session.total_source_bars,
        });

        const fileName = session.data_file.split('/').pop() || session.data_file;
        setDataFileName(fileName);

        if (!sessionSettings.hasSavedSession) {
          sessionSettings.saveSession(session.data_file, null);
        }

        const smallestValid = getSmallestValidAggregation(resolutionMinutes);
        const validChart1 = clampAggregationToSource(chartPrefs.chart1Aggregation, resolutionMinutes);
        const validChart2 = clampAggregationToSource(chartPrefs.chart2Aggregation, resolutionMinutes);
        if (validChart1 !== chartPrefs.chart1Aggregation) chartPrefs.setChart1Aggregation(validChart1);
        if (validChart2 !== chartPrefs.chart2Aggregation) chartPrefs.setChart2Aggregation(validChart2);

        const source = await fetchBars(smallestValid);

        // Check if backend already has state (don't reset on view switch)
        const hasExistingState = session.current_bar_index !== null && session.current_bar_index >= 0;

        if (hasExistingState) {
          // Backend has state - use it without resetting (#412: simplified from CalibrationData)
          setCalibrationBarCount(session.current_bar_index! + 1);
          // Sync forward playback with backend position
          forwardPlayback.syncToPosition(session.current_bar_index!, [], 0, []);
        } else {
          // No existing state - backend will auto-init on first /dag/state call (#412)
          setCalibrationBarCount(0);
        }

        setSourceBars([]);
        setCalibrationBars([]);

        const [bars1, bars2] = await Promise.all([
          fetchBars(validChart1),
          fetchBars(validChart2),
        ]);
        setChart1Bars(bars1);
        setChart2Bars(bars2);

        // If we had existing state, go straight to PLAYING mode (#412)
        if (hasExistingState) {
          setIsPlaying(true);
        }
        // Otherwise isPlaying stays false (ready to play)

        setSessionInfo(prev => prev ? {
          ...prev,
          totalSourceBars: source.length,
        } : { windowOffset: session.window_offset, totalSourceBars: source.length });
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [sessionSettings.isLoaded]);

  // Handle panel resize
  const handlePanelResize = useCallback((deltaY: number) => {
    chartPrefs.setExplanationPanelHeight(
      Math.max(100, Math.min(600, chartPrefs.explanationPanelHeight + deltaY))
    );
  }, [chartPrefs.explanationPanelHeight, chartPrefs.setExplanationPanelHeight]);

  // Get current timestamp for header
  const currentTimestamp = sourceBars[currentPlaybackPosition]?.timestamp
    ? new Date(sourceBars[currentPlaybackPosition].timestamp * 1000).toISOString()
    : undefined;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-app-bg text-app-text">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-trading-blue border-t-transparent rounded-full mx-auto mb-4"></div>
          <p>Loading...</p>
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
      <Header
        onToggleSidebar={() => {}}
        currentTimestamp={currentTimestamp}
        sourceBarCount={forwardPlayback.currentPosition + 1}
        initStatus={isPlaying ? 'playing' : 'initialized'}
        dataFileName={dataFileName}
        onOpenSettings={() => setIsSettingsOpen(true)}
        currentView="levels-at-play"
        onNavigate={onNavigate}
      />

      <div className="flex-1 flex min-h-0">
        <main className="flex-1 flex flex-col min-w-0">
          <ChartArea
            chart1Data={visibleChart1Bars}
            chart2Data={visibleChart2Bars}
            chart1Aggregation={chartPrefs.chart1Aggregation}
            chart2Aggregation={chartPrefs.chart2Aggregation}
            onChart1AggregationChange={handleChart1AggregationChange}
            onChart2AggregationChange={handleChart2AggregationChange}
            onChart1Ready={handleChart1Ready}
            onChart2Ready={handleChart2Ready}
            sourceResolutionMinutes={sourceResolutionMinutes}
            chart1Zoom={chartPrefs.chart1Zoom}
            chart2Zoom={chartPrefs.chart2Zoom}
            onChart1ZoomChange={chartPrefs.setChart1Zoom}
            onChart2ZoomChange={chartPrefs.setChart2Zoom}
            maximizedChart={chartPrefs.maximizedChart}
            onMaximizedChartChange={chartPrefs.setMaximizedChart}
            chart1Overlay={
              <ReferenceLegOverlay
                chart={chart1Ref.current}
                series={series1Ref.current}
                references={referenceState?.references ?? []}
                fadingRefs={fadingRefs}
                bars={visibleChart1Bars}
                stickyLegIds={stickyLegIds}
                onLegClick={toggleStickyLeg}
                filteredLegs={referenceState?.filtered_legs ?? []}
                showFiltered={showFiltered}
              />
            }
            chart2Overlay={
              <ReferenceLegOverlay
                chart={chart2Ref.current}
                series={series2Ref.current}
                references={referenceState?.references ?? []}
                fadingRefs={fadingRefs}
                bars={visibleChart2Bars}
                stickyLegIds={stickyLegIds}
                onLegClick={toggleStickyLeg}
                filteredLegs={referenceState?.filtered_legs ?? []}
                showFiltered={showFiltered}
              />
            }
          />

          <div className="shrink-0 z-10">
            <PlaybackControls
              playbackState={
                isPlaying
                  ? forwardPlayback.playbackState
                  : PlaybackState.STOPPED
              }
              onPlayPause={
                !isPlaying
                  ? handleStartPlayback
                  : forwardPlayback.togglePlayPause
              }
              onStepBack={forwardPlayback.stepBack}
              onStepForward={handleStepForward}
              onJumpToStart={forwardPlayback.jumpToStart}
              onJumpToEnd={undefined}
              onJumpToPreviousEvent={undefined}
              onJumpToNextEvent={undefined}
              hasPreviousEvent={false}
              hasNextEvent={!forwardPlayback.endOfData}
              canStepBack={forwardPlayback.canStepBack}
              currentEventIndex={forwardPlayback.currentEventIndex}
              totalEvents={forwardPlayback.allEvents.length}
              currentBar={Math.max(0, currentPlaybackPosition + 1)}
              totalBars={sessionInfo?.totalSourceBars || 0}
              calibrationBarCount={0}
              windowOffset={sessionInfo?.windowOffset}
              totalSourceBars={sessionInfo?.totalSourceBars}
              speedMultiplier={chartPrefs.speedMultiplier}
              onSpeedMultiplierChange={chartPrefs.setSpeedMultiplier}
              speedAggregation={chartPrefs.speedAggregation}
              onSpeedAggregationChange={chartPrefs.setSpeedAggregation}
              availableSpeedAggregations={availableSpeedAggregations}
              isLingering={false}
              lingerTimeLeft={0}
              lingerTotalTime={0}
              lingerEventType={undefined}
              lingerQueuePosition={undefined}
              onNavigatePrev={() => {}}
              onNavigateNext={() => {}}
              onDismissLinger={() => {}}
              lingerEnabled={false}
              lingerDisabled={true}
              currentTimestamp={sourceBars[currentPlaybackPosition]?.timestamp}
              maxTimestamp={
                sourceBars[currentPlaybackPosition]?.timestamp && sessionInfo?.totalSourceBars
                  ? sourceBars[currentPlaybackPosition].timestamp +
                    ((sessionInfo.totalSourceBars - currentPlaybackPosition - 1) * sourceResolutionMinutes * 60)
                  : undefined
              }
              resolutionMinutes={sourceResolutionMinutes}
              onProcessTill={handleProcessTill}
              isProcessingTill={isProcessingTill}
            />
          </div>

          <ResizeHandle onResize={handlePanelResize} />

          <div className="shrink-0" style={{ height: chartPrefs.explanationPanelHeight }}>
            <ReferenceTelemetryPanel
              referenceState={referenceState}
              showFiltered={showFiltered}
              onToggleShowFiltered={() => setShowFiltered(prev => !prev)}
            />
          </div>
        </main>

        <SettingsPanel
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
          currentDataFile={sessionSettings.dataFile || ''}
          onSessionRestart={() => window.location.reload()}
          onSaveSession={sessionSettings.saveSession}
        />
      </div>
    </div>
  );
};
