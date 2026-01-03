import React, { useEffect, useCallback, useMemo, useState, useRef } from 'react';
import { Header } from '../components/Header';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { ResizeHandle } from '../components/ResizeHandle';
import { ReferenceTelemetryPanel } from '../components/ReferenceTelemetryPanel';
import { ReferenceLegOverlay } from '../components/ReferenceLegOverlay';
import { SettingsPanel } from '../components/SettingsPanel';
import { ReferenceSidebar } from '../components/ReferenceSidebar';
import { AttachableItem } from '../components/DAGStatePanel';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import { useChartPreferences } from '../hooks/useChartPreferences';
import { useSessionSettings } from '../hooks/useSessionSettings';
import { useReferenceState } from '../hooks/useReferenceState';
import { useAuth } from '../hooks/useAuth';
import {
  fetchBars,
  fetchSession,
  restartSession,
  advanceReplay,
  fetchReferenceConfig,
  updateReferenceConfig,
  ReferenceConfig,
  DEFAULT_REFERENCE_CONFIG,
  ReferenceSwing,
  DagLeg,
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
  // Auth state
  const auth = useAuth();

  // Chart and speed preferences (persisted to localStorage)
  const chartPrefs = useChartPreferences();

  // Session settings (persisted to localStorage)
  const sessionSettings = useSessionSettings();

  // Reference state hook (Phase 2: includes sticky leg support, Phase 4: level crossing)
  const {
    referenceState,
    fetchReferenceState,
    setFromSnapshot,  // For buffered playback (#456)
    fadingRefs,
    stickyLegIds,
    toggleStickyLeg,
    crossingEvents,
    trackError,
    clearTrackError,
  } = useReferenceState();

  // Core state
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);
  const [sourceResolutionMinutes, setSourceResolutionMinutes] = useState(1);
  const [dataFileName, setDataFileName] = useState<string>('');
  const [sessionInfo, setSessionInfo] = useState<{ windowOffset: number; totalSourceBars: number } | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isProcessingTill, setIsProcessingTill] = useState(false);
  const [showFiltered, setShowFiltered] = useState(false);  // Reference Observation mode

  // Bidirectional hover/click state (Issue #430)
  const [sidebarHoveredLegId, setSidebarHoveredLegId] = useState<string | null>(null);
  const [chartHoveredLegId, setChartHoveredLegId] = useState<string | null>(null);
  const [selectedLegId, setSelectedLegId] = useState<string | null>(null);
  // Track manual selection vs auto-selection (Issue #433)
  // When user manually clicks a leg, we lock selection until they clear it
  // When salience config changes, we re-auto-select unless manually selected
  const isManualSelectionRef = useRef(false);

  // Reference Config state (Issue #425)
  const [referenceConfig, setReferenceConfig] = useState<ReferenceConfig>(
    chartPrefs.referenceConfig ?? DEFAULT_REFERENCE_CONFIG
  );

  // Feedback attachment state (for Observation form)
  const [attachedItems, setAttachedItems] = useState<AttachableItem[]>([]);

  // Convert ReferenceSwing to DagLeg format for attachment
  const referenceSwingToDagLeg = useCallback((ref: ReferenceSwing): DagLeg => ({
    leg_id: ref.leg_id,
    direction: ref.direction,
    pivot_price: ref.pivot_price,
    pivot_index: ref.pivot_index,
    origin_price: ref.origin_price,
    origin_index: ref.origin_index,
    retracement_pct: ref.location * 100, // location 0-2 maps roughly to retracement
    status: 'active',
    origin_breached: false,
    bar_count: ref.pivot_index - ref.origin_index,
    impulsiveness: ref.impulsiveness,
    spikiness: null,
    parent_leg_id: null,
    impulse_to_deepest: null,
    impulse_back: null,
    net_segment_impulse: null,
  }), []);

  // Handle attaching a reference to feedback
  const handleAttachItem = useCallback((item: AttachableItem) => {
    setAttachedItems(prev => {
      if (prev.length >= 5) return prev;
      const isDuplicate = prev.some(existing => {
        if (existing.type !== item.type) return false;
        if (item.type === 'leg') {
          return (existing.data as DagLeg).leg_id === (item.data as DagLeg).leg_id;
        }
        return false;
      });
      if (isDuplicate) return prev;
      return [...prev, item];
    });
  }, []);

  // Handle double-click on reference leg to attach
  const handleLegDoubleClick = useCallback((ref: ReferenceSwing) => {
    const dagLeg = referenceSwingToDagLeg(ref);
    handleAttachItem({ type: 'leg', data: dagLeg });
  }, [referenceSwingToDagLeg, handleAttachItem]);

  // Handle detaching an item
  const handleDetachItem = useCallback((item: AttachableItem) => {
    setAttachedItems(prev => prev.filter(existing => {
      if (existing.type !== item.type) return true;
      if (item.type === 'leg') {
        return (existing.data as DagLeg).leg_id !== (item.data as DagLeg).leg_id;
      }
      return true;
    }));
  }, []);

  // Clear all attachments
  const handleClearAttachments = useCallback(() => {
    setAttachedItems([]);
  }, []);

  // Sidebar hover handler (Issue #430)
  const handleSidebarHoverLeg = useCallback((legId: string | null) => {
    setSidebarHoveredLegId(legId);
  }, []);

  // Chart hover handler (Issue #430) - called when chart leg is hovered
  const handleChartHoverLeg = useCallback((legId: string | null) => {
    setChartHoveredLegId(legId);
  }, []);

  // Sidebar select handler (Issue #430, #433) - clicking a leg selects it exclusively
  // Single selection model: only one leg is selected/tracked at a time
  // Manual selection locks the choice until user deselects
  const handleSidebarSelectLeg = useCallback(async (legId: string) => {
    if (selectedLegId === legId) {
      // Clicking same leg - deselect and untrack, allow re-auto-selection
      setSelectedLegId(null);
      isManualSelectionRef.current = false; // Allow auto-selection again
      toggleStickyLeg(legId); // Untrack since it's already tracked
    } else {
      // Clicking different leg - untrack old (if any), then track new
      isManualSelectionRef.current = true; // Lock to manual selection
      if (selectedLegId !== null && stickyLegIds.has(selectedLegId)) {
        await toggleStickyLeg(selectedLegId); // Untrack old
      }
      setSelectedLegId(legId);
      if (!stickyLegIds.has(legId)) {
        toggleStickyLeg(legId); // Track new
      }
    }
  }, [selectedLegId, stickyLegIds, toggleStickyLeg]);

  // Effective hovered leg for sidebar (combine sidebar and chart hover)
  const effectiveSidebarHoveredLegId = useMemo(() => {
    return sidebarHoveredLegId || chartHoveredLegId;
  }, [sidebarHoveredLegId, chartHoveredLegId]);


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

  // Handler for playback reset (jumpToStart)
  const handleReset = useCallback(() => {
    // Clear aggregated chart bars (will be repopulated on advance)
    setChart1Bars([]);
    setChart2Bars([]);
  }, []);

  // Forward playback hook
  // #456: Use buffered ref states for efficient high-speed playback
  const forwardPlayback = useForwardPlayback({
    playbackIntervalMs: effectivePlaybackIntervalMs,
    barsPerAdvance,
    filters: [],
    lingerEnabled: false,
    chartAggregationScales: [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation],
    includeDagState: false,
    includePerBarRefStates: true,  // #456: Enable buffered ref states
    onNewBars: useCallback((newBars: BarData[]) => {
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        syncChartsToPositionRef.current(lastBar.index);
      }
    }, []),
    onAggregatedBarsChange: handleAggregatedBarsChange,
    onDagStateChange: () => {},
    onRefStateChange: setFromSnapshot,  // #456: Apply buffered ref states during playback
    onReset: handleReset,
  });

  // Get current playback position
  const currentPlaybackPosition = useMemo(() => {
    return forwardPlayback.currentPosition >= 0 ? forwardPlayback.currentPosition : 0;
  }, [forwardPlayback.currentPosition]);

  // Fetch reference state when playback position changes
  // #456: During active playback, ref states come from buffer via onRefStateChange
  // #469: On pause, keep buffered state (don't overwrite with stale API data)
  // Only fetch via API on view switch (referenceState is null)
  useEffect(() => {
    // Skip during active playback - buffer is updated via onRefStateChange
    if (forwardPlayback.playbackState === PlaybackState.PLAYING) {
      return;
    }

    // #469: Skip if we already have reference state (from buffer)
    // This prevents overwriting correct buffered state with stale API data on pause
    if (referenceState !== null) {
      return;
    }

    // Only fetch when we need initial state (view switch, initial load)
    // and have a valid position
    if (forwardPlayback.currentPosition >= 0 || isPlaying) {
      // #469: Trigger BE resync before fetching to ensure correct state
      // This handles view switch when BE has buffered ahead of FE
      const resyncAndFetch = async () => {
        try {
          // Call advance with advanceBy=0 and fromIndex to trigger resync without advancing
          await advanceReplay(
            currentPlaybackPosition - 1,  // current_bar_index (before current position)
            0,                             // advance_by=0 (just resync, don't advance)
            undefined,                     // includeAggregatedBars
            false,                         // includeDagState
            false,                         // includePerBarDagStates
            currentPlaybackPosition,       // fromIndex (triggers resync if BE is ahead)
            false                          // includePerBarRefStates
          );
        } catch (err) {
          // Resync failed, but still try to fetch (might work if BE was already in sync)
          console.warn('[LevelsAtPlayView] Resync failed, fetching anyway:', err);
        }
        // Now fetch reference state with BE at correct position
        fetchReferenceState(currentPlaybackPosition);
      };
      resyncAndFetch();
    }
  }, [currentPlaybackPosition, forwardPlayback.currentPosition, isPlaying, fetchReferenceState, forwardPlayback.playbackState, referenceState]);

  // Save playback position to session settings for view switching (#451)
  useEffect(() => {
    if (isPlaying && currentPlaybackPosition >= 0) {
      sessionSettings.setPlaybackPosition(currentPlaybackPosition);
    }
  }, [currentPlaybackPosition, isPlaying, sessionSettings.setPlaybackPosition]);

  // Auto-select top-ranked leg when references change (Issue #433, #458)
  // - On initial load: auto-select top leg
  // - When salience config changes: re-auto-select new top leg
  // - When user manually selects: lock selection until they deselect
  // #458: Skip track API calls during auto-selection - crossing events come from buffer
  useEffect(() => {
    // Skip if user has manually selected a leg
    if (isManualSelectionRef.current) return;

    // Skip if no references available
    if (!referenceState?.references || referenceState.references.length === 0) return;

    const topLeg = referenceState.references[0]; // Sorted by salience

    // Skip if already selected (no change needed)
    if (selectedLegId === topLeg.leg_id) return;

    // #458: Only update UI selection, don't call track/untrack API
    // During buffered playback, crossing events come from the buffer's auto_tracked_leg_id
    // We only call the track API when user manually pins a leg (see handleSidebarSelectLeg)
    setSelectedLegId(topLeg.leg_id);
  }, [referenceState?.references, selectedLegId]);

  // Reference Config update handler (Issue #425, #458)
  const handleReferenceConfigUpdate = useCallback(async (newConfig: ReferenceConfig) => {
    try {
      // Send to backend API
      const updatedConfig = await updateReferenceConfig(newConfig);
      // Update local state
      setReferenceConfig(updatedConfig);
      // Persist to localStorage
      chartPrefs.setReferenceConfig(updatedConfig);
      // #458: Invalidate buffer - salience rankings are now stale
      forwardPlayback.clearRefStateBuffer();
      // Refresh reference state to reflect new salience weights
      if (forwardPlayback.currentPosition >= 0) {
        fetchReferenceState(currentPlaybackPosition);
      }
    } catch (err) {
      console.error('Failed to update reference config:', err);
    }
  }, [chartPrefs.setReferenceConfig, forwardPlayback, currentPlaybackPosition, fetchReferenceState]);

  // Sync reference config with backend on mount (Issue #425, #468)
  // If we have saved preferences, push them to server to override defaults (like DAGView does)
  useEffect(() => {
    const syncReferenceConfig = async () => {
      try {
        if (chartPrefs.referenceConfig) {
          // Push saved config to server to override defaults
          const pushedConfig = await updateReferenceConfig(chartPrefs.referenceConfig);
          setReferenceConfig(pushedConfig);
        } else {
          // No saved preferences, just fetch server defaults
          const config = await fetchReferenceConfig();
          setReferenceConfig(config);
        }
      } catch (err) {
        console.error('Failed to sync reference config:', err);
        // Fall back to localStorage or defaults (already set in useState initializer)
      }
    };
    syncReferenceConfig();
  }, []);

  // Compute a "live" aggregated bar from source bars for incremental display
  const computeLiveBar = useCallback((
    aggBar: BarData,
    currentPosition: number
  ): BarData | null => {
    const relevantSourceBars = forwardPlayback.visibleBars.filter(
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
  }, [forwardPlayback.visibleBars]);

  // Filter chart bars to only show candles up to current playback position
  // Always filter based on position - don't show all bars before playback starts (#412)
  // If computeLiveBar fails (no source bars), include original bar for timestamp mapping
  const visibleChart1Bars = useMemo(() => {
    const result: BarData[] = [];
    for (const bar of chart1Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        // Include original bar if live computation fails - needed for timestamp mapping in overlays
        result.push(liveBar ?? bar);
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
        // Include original bar if live computation fails - needed for timestamp mapping in overlays
        result.push(liveBar ?? bar);
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
        currentPlaybackPosition,
        barCount,
        [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation],
        false,
        false,  // includePerBarDagStates
        currentPlaybackPosition  // fromIndex for BE resync (#471)
      );

      if (response.new_bars && response.new_bars.length > 0) {
        const newBars = formatReplayBarsData(response.new_bars);
        // Use last bar's index from newBars to ensure currentPosition matches array
        // This mirrors the pattern in useForwardPlayback.ts for normal playback
        const lastBarIndex = newBars[newBars.length - 1].index;
        forwardPlayback.syncToPosition(
          lastBarIndex,
          [...forwardPlayback.visibleBars, ...newBars],
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

      // Fetch reference state at the new position (#474)
      // Process Till bypasses the buffered playback path, so we need to
      // explicitly refresh reference state to avoid stale UI
      if (response.current_bar_index >= 0) {
        await fetchReferenceState(response.current_bar_index);
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
    fetchReferenceState,
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

  // Scroll charts to current position when data is available
  useEffect(() => {
    if (!isPlaying && forwardPlayback.currentPosition >= 0) {
      const timeout = setTimeout(() => {
        syncChartsToPositionRef.current(forwardPlayback.currentPosition);
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [isPlaying, forwardPlayback.currentPosition]);

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
          // Use saved playback position if available, otherwise use server position (#451)
          // This preserves the render position when switching views
          const targetPosition = sessionSettings.playbackPosition !== null
            ? sessionSettings.playbackPosition
            : session.current_bar_index!;

          // Sync forward playback with saved position and bars up to that position
          // This populates visibleBars so timestamp lookups work after view switch (#463)
          const barsUpToPosition = source.slice(0, targetPosition + 1);
          forwardPlayback.syncToPosition(targetPosition, barsUpToPosition, 0, []);
        }
        // No else needed - backend will auto-init on first /dag/state call (#412)

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
  const currentTimestamp = forwardPlayback.visibleBars[currentPlaybackPosition]?.timestamp
    ? new Date(forwardPlayback.visibleBars[currentPlaybackPosition].timestamp * 1000).toISOString()
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
        onToggleSidebar={() => chartPrefs.setLevelsAtPlaySidebarOpen(!chartPrefs.levelsAtPlaySidebarOpen)}
        currentTimestamp={currentTimestamp}
        sourceBarCount={forwardPlayback.currentPosition + 1}
        initStatus={isPlaying ? 'playing' : 'initialized'}
        dataFileName={dataFileName}
        onOpenSettings={() => setIsSettingsOpen(true)}
        currentView="levels-at-play"
        onNavigate={onNavigate}
        user={auth.user}
        onLogout={auth.multiTenant ? auth.logout : () => { window.location.href = '/'; }}
      />

      <div className="flex-1 flex min-h-0">
        {/* Reference Sidebar - Left side with toggle (Issue #426) */}
        <div className={`${chartPrefs.levelsAtPlaySidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 ease-in-out overflow-hidden shrink-0`}>
          <ReferenceSidebar
            referenceConfig={referenceConfig}
            onReferenceConfigUpdate={handleReferenceConfigUpdate}
            telemetryData={referenceState ? {
              counts_by_bin: Object.fromEntries(
                Object.entries(referenceState.by_bin).map(([bin, refs]) => [parseInt(bin), refs.length])
              ) as Record<number, number>,
              total_count: referenceState.references.length,
              bull_count: referenceState.by_direction.bull.length,
              bear_count: referenceState.by_direction.bear.length,
              direction_imbalance: referenceState.direction_imbalance,
              imbalance_ratio: null,
              biggest_reference: null,
              most_impulsive: null,
            } : undefined}
            // Filters (Issue #445 - moved from bottom panel)
            filterStats={referenceState?.filter_stats}
            showFiltered={showFiltered}
            onToggleShowFiltered={() => setShowFiltered(prev => !prev)}
            onResetDefaults={() => handleReferenceConfigUpdate(DEFAULT_REFERENCE_CONFIG)}
            className="w-64 h-full"
            showFeedback={true}
            currentPlaybackBar={currentPlaybackPosition}
            feedbackContext={{
              playbackState: isPlaying ? forwardPlayback.playbackState : PlaybackState.STOPPED,
              csvIndex: currentPlaybackPosition,
              currentBarIndex: currentPlaybackPosition,
              swingsFoundByScale: {
                // Group bins into legacy scale categories for feedback context
                XL: referenceState?.by_bin[10]?.length ?? 0,
                L: referenceState?.by_bin[9]?.length ?? 0,
                M: referenceState?.by_bin[8]?.length ?? 0,
                S: Object.entries(referenceState?.by_bin ?? {})
                  .filter(([bin]) => parseInt(bin) <= 7)
                  .reduce((sum, [, refs]) => sum + refs.length, 0),
              },
              totalEvents: forwardPlayback.allEvents.length,
              swingsInvalidated: 0,
              swingsCompleted: 0,
            }}
            attachedItems={attachedItems}
            onDetachItem={handleDetachItem}
            onClearAttachments={handleClearAttachments}
          />
        </div>

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
                allBars={chart1Bars}
                currentPosition={currentPlaybackPosition}
                stickyLegIds={stickyLegIds}
                onLegClick={toggleStickyLeg}
                onLegDoubleClick={handleLegDoubleClick}
                filteredLegs={referenceState?.filtered_legs ?? []}
                showFiltered={showFiltered}
                externalHoveredLegId={sidebarHoveredLegId}
                onLegHover={handleChartHoverLeg}
                selectedLegId={selectedLegId}
              />
            }
            chart2Overlay={
              <ReferenceLegOverlay
                chart={chart2Ref.current}
                series={series2Ref.current}
                references={referenceState?.references ?? []}
                fadingRefs={fadingRefs}
                bars={visibleChart2Bars}
                allBars={chart2Bars}
                currentPosition={currentPlaybackPosition}
                stickyLegIds={stickyLegIds}
                onLegClick={toggleStickyLeg}
                onLegDoubleClick={handleLegDoubleClick}
                filteredLegs={referenceState?.filtered_legs ?? []}
                showFiltered={showFiltered}
                externalHoveredLegId={sidebarHoveredLegId}
                onLegHover={handleChartHoverLeg}
                selectedLegId={selectedLegId}
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
              currentTimestamp={forwardPlayback.visibleBars[currentPlaybackPosition]?.timestamp}
              maxTimestamp={
                forwardPlayback.visibleBars[currentPlaybackPosition]?.timestamp && sessionInfo?.totalSourceBars
                  ? forwardPlayback.visibleBars[currentPlaybackPosition].timestamp +
                    ((sessionInfo.totalSourceBars - currentPlaybackPosition - 1) * sourceResolutionMinutes * 60)
                  : undefined
              }
              resolutionMinutes={sourceResolutionMinutes}
              onProcessTill={handleProcessTill}
              isProcessingTill={isProcessingTill}
            />
          </div>

          <ResizeHandle onResize={handlePanelResize} />

          {/* Bottom Panel: LEVELS AT PLAY + EVENTS (Issue #445) */}
          <div className="shrink-0" style={{ height: chartPrefs.explanationPanelHeight }}>
            <ReferenceTelemetryPanel
              referenceState={referenceState}
              crossingEvents={crossingEvents}
              trackError={trackError}
              onClearTrackError={clearTrackError}
              onEventHover={handleSidebarHoverLeg}
              // Levels at Play (Issue #445 - moved from sidebar, #457 - split panels)
              allReferences={referenceState?.references ?? []}
              activeFiltered={referenceState?.active_filtered ?? []}
              selectedLegId={selectedLegId}
              hoveredLegId={effectiveSidebarHoveredLegId}
              onHoverLeg={handleSidebarHoverLeg}
              onSelectLeg={handleSidebarSelectLeg}
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
