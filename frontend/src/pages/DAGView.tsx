import React, { useEffect, useCallback, useMemo } from 'react';
import { Header } from '../components/Header';
import { Sidebar, DAG_LINGER_EVENTS } from '../components/Sidebar';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { DAGStatePanel } from '../components/DAGStatePanel';
import { ResizeHandle } from '../components/ResizeHandle';
import { LegOverlay } from '../components/LegOverlay';
import { PendingOriginsOverlay } from '../components/PendingOriginsOverlay';
import { HierarchyModeOverlay } from '../components/HierarchyModeOverlay';
import { EventMarkersOverlay } from '../components/EventMarkersOverlay';
import { EventInspectionPopup } from '../components/EventInspectionPopup';
import { SettingsPanel } from '../components/SettingsPanel';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import { useHierarchyMode } from '../hooks/useHierarchyMode';
import { useFollowLeg, LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';
import { useChartPreferences } from '../hooks/useChartPreferences';
import { useSessionSettings } from '../hooks/useSessionSettings';
import { useDAGViewState } from '../hooks/useDAGViewState';
import {
  fetchBars,
  fetchSession,
  fetchCalibration,
  fetchDagState,
  fetchDetectionConfig,
  updateDetectionConfig,
  restartSession,
  advanceReplay,
} from '../lib/api';
import { formatReplayBarsData } from '../utils/barDataUtils';
import { LINGER_DURATION_MS } from '../constants';
import {
  BarData,
  AggregationScale,
  CalibrationPhase,
  PlaybackState,
  parseResolutionToMinutes,
  getAggregationLabel,
  getAggregationMinutes,
  getSmallestValidAggregation,
  clampAggregationToSource,
  LegEvent,
} from '../types';
import type { ViewMode } from '../App';

interface DAGViewProps {
  onNavigate?: (view: ViewMode) => void;
}

export const DAGView: React.FC<DAGViewProps> = ({ onNavigate }) => {
  // Chart and speed preferences (persisted to localStorage)
  const chartPrefs = useChartPreferences();

  // Session settings (persisted to localStorage)
  const sessionSettings = useSessionSettings();

  // DAG View state (consolidated state management)
  const state = useDAGViewState({
    savedLingerEnabled: chartPrefs.lingerEnabled,
    savedLingerEvents: chartPrefs.dagLingerEvents,
    saveLingerEnabled: chartPrefs.setLingerEnabled,
    saveLingerEvents: chartPrefs.setDagLingerEvents,
    savedDetectionConfig: chartPrefs.detectionConfig,
    saveDetectionConfig: chartPrefs.setDetectionConfig,
  });

  // Handle panel resize
  const handlePanelResize = useCallback((deltaY: number) => {
    chartPrefs.setExplanationPanelHeight(
      Math.max(100, Math.min(600, chartPrefs.explanationPanelHeight + deltaY))
    );
  }, [chartPrefs.explanationPanelHeight, chartPrefs.setExplanationPanelHeight]);

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
    return Math.max(1, Math.round(aggMinutes / state.sourceResolutionMinutes));
  }, [chartPrefs.speedAggregation, state.sourceResolutionMinutes]);

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
  const handleAggregatedBarsChange = useCallback((aggBars: import('../lib/api').AggregatedBarsResponse) => {
    const chart1Bars = aggBars[chartPrefs.chart1Aggregation as keyof typeof aggBars];
    const chart2Bars = aggBars[chartPrefs.chart2Aggregation as keyof typeof aggBars];
    if (chart1Bars) state.setChart1Bars(chart1Bars);
    if (chart2Bars) state.setChart2Bars(chart2Bars);
  }, [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation, state.setChart1Bars, state.setChart2Bars]);

  // Handler for DAG state from API response
  const handleDagStateChange = useCallback((dagState: import('../lib/api').DagStateResponse) => {
    state.setDagState(dagState);
  }, [state.setDagState]);

  // Forward playback hook
  const forwardPlayback = useForwardPlayback({
    calibrationBarCount: state.calibrationData?.calibration_bar_count ?? 0,
    calibrationBars: state.calibrationBars,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    barsPerAdvance,
    filters: state.lingerEvents,
    lingerEnabled: state.lingerEnabled,
    chartAggregationScales: [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation],
    includeDagState: true,
    onNewBars: useCallback((newBars: BarData[]) => {
      state.setSourceBars(prev => [...prev, ...newBars]);
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        state.syncChartsToPositionRef.current(lastBar.index);
      }
    }, [state.setSourceBars]),
    onAggregatedBarsChange: handleAggregatedBarsChange,
    onDagStateChange: handleDagStateChange,
  });

  // Hierarchy exploration mode
  const hierarchyMode = useHierarchyMode(state.activeLegs);

  // Follow Leg feature
  const followLeg = useFollowLeg();

  // Create followedLegColors Map for LegOverlay
  const followedLegColors = useMemo(() => {
    const colors = new Map<string, string>();
    for (const leg of followLeg.followedLegs) {
      colors.set(leg.leg_id, leg.color);
    }
    return colors;
  }, [followLeg.followedLegs]);

  // Get current playback position
  const currentPlaybackPosition = useMemo(() => {
    if (state.calibrationPhase === CalibrationPhase.PLAYING) {
      return forwardPlayback.currentPosition;
    } else if (state.calibrationPhase === CalibrationPhase.CALIBRATED && state.calibrationData) {
      return state.calibrationData.calibration_bar_count - 1;
    }
    return 0;
  }, [state.calibrationPhase, forwardPlayback.currentPosition, state.calibrationData]);

  // Compute a "live" aggregated bar from source bars for incremental display
  const computeLiveBar = useCallback((
    aggBar: BarData,
    currentPosition: number
  ): BarData | null => {
    const relevantSourceBars = state.sourceBars.filter(
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
  }, [state.sourceBars]);

  // Filter chart bars to only show candles up to current playback position
  const visibleChart1Bars = useMemo(() => {
    if (state.calibrationPhase !== CalibrationPhase.PLAYING) {
      return state.chart1Bars;
    }
    const result: BarData[] = [];
    for (const bar of state.chart1Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        if (liveBar) result.push(liveBar);
      }
    }
    return result;
  }, [state.chart1Bars, currentPlaybackPosition, state.calibrationPhase, computeLiveBar]);

  const visibleChart2Bars = useMemo(() => {
    if (state.calibrationPhase !== CalibrationPhase.PLAYING) {
      return state.chart2Bars;
    }
    const result: BarData[] = [];
    for (const bar of state.chart2Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        if (liveBar) result.push(liveBar);
      }
    }
    return result;
  }, [state.chart2Bars, currentPlaybackPosition, state.calibrationPhase, computeLiveBar]);

  // Event handlers
  const handleTreeIconClick = useCallback((legId: string) => {
    hierarchyMode.enterHierarchyMode(legId);
  }, [hierarchyMode]);

  const handleHierarchyRecenter = useCallback((legId: string) => {
    if (hierarchyMode.state.isActive && hierarchyMode.isInHierarchy(legId)) {
      hierarchyMode.recenterOnLeg(legId);
    }
  }, [hierarchyMode]);

  const handleChartLegHover = useCallback((legId: string | null) => {
    if (legId) {
      const leg = state.dagState?.active_legs.find(l => l.leg_id === legId);
      if (leg) {
        state.setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
      }
    } else {
      state.setHighlightedDagItem(null);
    }
  }, [state.dagState, state.setHighlightedDagItem]);

  const handleChartLegClick = useCallback((legId: string) => {
    const leg = state.dagState?.active_legs.find(l => l.leg_id === legId);
    if (leg) {
      state.setFocusedLegId(legId);
      state.setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
    }
  }, [state.dagState, state.setFocusedLegId, state.setHighlightedDagItem]);

  const handleChartLegDoubleClick = useCallback((legId: string) => {
    const leg = state.dagState?.active_legs.find(l => l.leg_id === legId);
    if (leg) {
      state.handleAttachItem({ type: 'leg', data: leg });
    }
  }, [state.dagState, state.handleAttachItem]);

  const handleEyeIconClick = useCallback((legId: string) => {
    if (followLeg.isFollowed(legId)) {
      followLeg.unfollowLeg(legId);
    } else {
      const leg = state.dagState?.active_legs.find(l => l.leg_id === legId);
      if (leg) {
        followLeg.followLeg(leg, currentPlaybackPosition);
      }
    }
  }, [followLeg, state.dagState, currentPlaybackPosition]);

  const handleRecentEventClick = useCallback((event: LegEvent, clickEvent: React.MouseEvent) => {
    const popupPosition = { x: clickEvent.clientX, y: clickEvent.clientY - 100 };
    const eventTypeMap: Record<LegEvent['type'], LifecycleEventWithLegInfo['event_type']> = {
      'LEG_CREATED': 'formed',
      'LEG_PRUNED': 'pruned',
      'ORIGIN_BREACHED': 'origin_breached',
    };

    const lifecycleEvent: LifecycleEventWithLegInfo = {
      leg_id: event.leg_id,
      event_type: eventTypeMap[event.type],
      bar_index: event.bar_index,
      csv_index: (state.sessionInfo?.windowOffset ?? 0) + event.bar_index,
      timestamp: new Date().toISOString(),
      explanation: event.reason || `${event.type} at bar ${event.bar_index}`,
      legColor: event.direction === 'bull' ? '#22c55e' : '#ef4444',
      legDirection: event.direction,
    };

    requestAnimationFrame(() => {
      const leg = state.dagState?.active_legs.find(l => l.leg_id === event.leg_id);
      if (leg) {
        state.setFocusedLegId(event.leg_id);
        state.setHighlightedDagItem({ type: 'leg', id: event.leg_id, direction: leg.direction });
      } else {
        state.setFocusedLegId(null);
        state.setHighlightedDagItem(null);
      }
      state.setHighlightedEvent(lifecycleEvent);
      state.setEventPopup({
        events: [lifecycleEvent],
        barIndex: event.bar_index,
        position: popupPosition,
      });
    });
  }, [state.dagState, state.sessionInfo?.windowOffset, state.setFocusedLegId, state.setHighlightedDagItem, state.setHighlightedEvent, state.setEventPopup]);

  const handleMarkerClick = useCallback((
    barIndex: number,
    events: LifecycleEventWithLegInfo[],
    position: { x: number; y: number }
  ) => {
    state.setEventPopup({ events, barIndex, position });
  }, [state.setEventPopup]);

  const handleAttachEvent = useCallback((event: LifecycleEventWithLegInfo) => {
    state.handleAttachItem({ type: 'lifecycle_event', data: event });
    state.setEventPopup(null);
  }, [state.handleAttachItem, state.setEventPopup]);

  const handleMarkerDoubleClick = useCallback((events: LifecycleEventWithLegInfo[]) => {
    if (events.length > 0) {
      state.handleAttachItem({ type: 'lifecycle_event', data: events[0] });
    }
  }, [state.handleAttachItem]);

  const handleStartPlayback = useCallback(() => {
    if (state.calibrationPhase === CalibrationPhase.CALIBRATED) {
      state.setCalibrationPhase(CalibrationPhase.PLAYING);
      forwardPlayback.play();
    }
  }, [state.calibrationPhase, state.setCalibrationPhase, forwardPlayback]);

  const handleStepForward = useCallback(() => {
    if (state.calibrationPhase === CalibrationPhase.CALIBRATED) {
      state.setCalibrationPhase(CalibrationPhase.PLAYING);
    }
    forwardPlayback.stepForward();
  }, [state.calibrationPhase, state.setCalibrationPhase, forwardPlayback]);

  const handleToggleLingerEvent = useCallback((eventId: string) => {
    state.setLingerEvents(prev =>
      prev.map(e => e.id === eventId ? { ...e, isEnabled: !e.isEnabled } : e)
    );
  }, [state.setLingerEvents]);

  const handleResetDefaults = useCallback(() => {
    state.setLingerEvents(DAG_LINGER_EVENTS);
  }, [state.setLingerEvents]);

  const handleProcessTill = useCallback(async (_targetTimestamp: number, barCount: number) => {
    if (state.calibrationPhase === CalibrationPhase.PLAYING && forwardPlayback.playbackState === PlaybackState.PLAYING) {
      throw new Error('Stop playback first');
    }
    if (barCount <= 0) {
      throw new Error('Must advance at least 1 bar');
    }

    state.setIsProcessingTill(true);
    try {
      if (state.calibrationPhase === CalibrationPhase.CALIBRATED) {
        state.setCalibrationPhase(CalibrationPhase.PLAYING);
      }

      const response = await advanceReplay(
        0,
        currentPlaybackPosition,
        barCount,
        [chartPrefs.chart1Aggregation, chartPrefs.chart2Aggregation],
        true
      );

      if (response.new_bars && response.new_bars.length > 0) {
        const newBars = formatReplayBarsData(response.new_bars);
        state.setSourceBars(prev => [...prev, ...newBars]);
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

      if (response.dag_state) {
        handleDagStateChange(response.dag_state);
      }

      if (response.current_bar_index >= 0) {
        state.syncChartsToPositionRef.current(response.current_bar_index);
      }
    } finally {
      state.setIsProcessingTill(false);
    }
  }, [
    state.calibrationPhase,
    forwardPlayback.playbackState,
    forwardPlayback.visibleBars,
    forwardPlayback.syncToPosition,
    currentPlaybackPosition,
    chartPrefs.chart1Aggregation,
    chartPrefs.chart2Aggregation,
    handleAggregatedBarsChange,
    handleDagStateChange,
    state.setSourceBars,
    state.setCalibrationPhase,
    state.setIsProcessingTill,
  ]);

  // Load chart bars when aggregation changes
  const loadChart1Bars = useCallback(async (scale: AggregationScale) => {
    try {
      const bars = await fetchBars(scale);
      state.setChart1Bars(bars);
    } catch (err) {
      console.error('Failed to load chart 1 bars:', err);
    }
  }, [state.setChart1Bars]);

  const loadChart2Bars = useCallback(async (scale: AggregationScale) => {
    try {
      const bars = await fetchBars(scale);
      state.setChart2Bars(bars);
    } catch (err) {
      console.error('Failed to load chart 2 bars:', err);
    }
  }, [state.setChart2Bars]);

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
    const syncChart = (chart: import('lightweight-charts').IChartApi | null, bars: BarData[]) => {
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

    syncChart(state.chart1Ref.current, state.chart1Bars);
    syncChart(state.chart2Ref.current, state.chart2Bars);
  }, [state.chart1Bars, state.chart2Bars, findAggBarForSourceIndex, state.chart1Ref, state.chart2Ref]);

  // Keep sync refs updated
  useEffect(() => {
    state.syncChartsToPositionRef.current = syncChartsToPosition;
  }, [syncChartsToPosition, state.syncChartsToPositionRef]);

  // Scroll charts when entering CALIBRATED phase
  useEffect(() => {
    if (state.calibrationPhase === CalibrationPhase.CALIBRATED && state.calibrationData) {
      const timeout = setTimeout(() => {
        const calibrationEndIndex = state.calibrationData!.calibration_bar_count - 1;
        state.syncChartsToPositionRef.current(calibrationEndIndex);
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [state.calibrationPhase, state.calibrationData, state.syncChartsToPositionRef]);

  // Compute all leg events from forward playback
  const allLegEvents = useMemo(() => {
    const events: LegEvent[] = [];
    for (const event of forwardPlayback.allEvents) {
      if (event.type === 'LEG_CREATED' || event.type === 'LEG_PRUNED' || event.type === 'LEG_INVALIDATED') {
        events.push({
          type: event.type as LegEvent['type'],
          leg_id: event.swing_id,
          bar_index: event.bar_index,
          direction: event.direction as 'bull' | 'bear',
          reason: event.trigger_explanation,
        });
      }
    }
    return events;
  }, [forwardPlayback.allEvents]);

  // Collect leg events from forward playback (last 20 for display)
  useEffect(() => {
    state.setRecentLegEvents(allLegEvents.slice(-20).reverse());
  }, [allLegEvents, state.setRecentLegEvents]);

  // Fetch lifecycle events for followed legs when playback advances
  useEffect(() => {
    if (state.calibrationPhase === CalibrationPhase.PLAYING && followLeg.followedLegs.length > 0) {
      followLeg.fetchEventsForFollowedLegs(currentPlaybackPosition);
    }
  }, [state.calibrationPhase, currentPlaybackPosition, followLeg]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      if (state.calibrationPhase === CalibrationPhase.CALIBRATED) {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          handleStartPlayback();
        }
        return;
      }

      if (state.calibrationPhase === CalibrationPhase.PLAYING) {
        if (e.key === 'Escape' && forwardPlayback.isLingering) {
          e.preventDefault();
          forwardPlayback.dismissLinger();
          return;
        }

        if (e.key === ' ') {
          e.preventDefault();
          forwardPlayback.togglePlayPause();
          return;
        }

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

        if (e.key === '[') {
          e.preventDefault();
          forwardPlayback.stepBack();
        } else if (e.key === ']') {
          e.preventDefault();
          forwardPlayback.stepForward();
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
    state.calibrationPhase,
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

  // Load initial data with startup flow
  useEffect(() => {
    const loadData = async () => {
      if (!sessionSettings.isLoaded) return;

      state.setIsLoading(true);
      state.setError(null);
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
              state.setIsSettingsOpen(true);
              state.setIsLoading(false);
              return;
            }
          } else {
            state.setIsSettingsOpen(true);
            state.setIsLoading(false);
            return;
          }
        }

        await loadSessionData(session);
      } catch (err) {
        state.setError(err instanceof Error ? err.message : 'Failed to load data');
        state.setIsLoading(false);
      }
    };

    const loadSessionData = async (session: Awaited<ReturnType<typeof fetchSession>>) => {
      try {
        const resolutionMinutes = parseResolutionToMinutes(session.resolution);
        state.setSourceResolutionMinutes(resolutionMinutes);
        state.setSessionInfo({
          windowOffset: session.window_offset,
          totalSourceBars: session.total_source_bars,
        });

        const fileName = session.data_file.split('/').pop() || session.data_file;
        state.setDataFileName(fileName);

        if (!sessionSettings.hasSavedSession) {
          sessionSettings.saveSession(session.data_file, null);
        }

        const smallestValid = getSmallestValidAggregation(resolutionMinutes);
        const validChart1 = clampAggregationToSource(chartPrefs.chart1Aggregation, resolutionMinutes);
        const validChart2 = clampAggregationToSource(chartPrefs.chart2Aggregation, resolutionMinutes);
        if (validChart1 !== chartPrefs.chart1Aggregation) chartPrefs.setChart1Aggregation(validChart1);
        if (validChart2 !== chartPrefs.chart2Aggregation) chartPrefs.setChart2Aggregation(validChart2);

        const source = await fetchBars(smallestValid);

        state.setCalibrationPhase(CalibrationPhase.CALIBRATING);
        const calibration = await fetchCalibration(0);
        state.setCalibrationData(calibration);

        state.setSourceBars([]);
        state.setCalibrationBars([]);

        const [bars1, bars2] = await Promise.all([
          fetchBars(validChart1),
          fetchBars(validChart2),
        ]);
        state.setChart1Bars(bars1);
        state.setChart2Bars(bars2);

        const initialDagState = await fetchDagState();
        state.setDagState(initialDagState);

        try {
          // If we have saved preferences, push them to server to override defaults (#358)
          if (chartPrefs.detectionConfig) {
            const savedConfig = chartPrefs.detectionConfig;
            const pushedConfig = await updateDetectionConfig({
              bull: {
                formation_fib: savedConfig.bull.formation_fib,
                engulfed_breach_threshold: savedConfig.bull.engulfed_breach_threshold,
              },
              bear: {
                formation_fib: savedConfig.bear.formation_fib,
                engulfed_breach_threshold: savedConfig.bear.engulfed_breach_threshold,
              },
              stale_extension_threshold: savedConfig.stale_extension_threshold,
              origin_range_threshold: savedConfig.origin_range_threshold,
              origin_time_threshold: savedConfig.origin_time_threshold,
              min_branch_ratio: savedConfig.min_branch_ratio,
              min_turn_ratio: savedConfig.min_turn_ratio,
              max_turns_per_pivot: savedConfig.max_turns_per_pivot,
              max_turns_per_pivot_raw: savedConfig.max_turns_per_pivot_raw,
              enable_engulfed_prune: savedConfig.enable_engulfed_prune,
            });
            state.setDetectionConfigFromServer(pushedConfig);
          } else {
            // No saved preferences, just fetch server defaults
            const config = await fetchDetectionConfig();
            state.setDetectionConfigFromServer(config);
          }
        } catch (err) {
          console.warn('Failed to sync detection config:', err);
        }

        state.setCalibrationPhase(CalibrationPhase.CALIBRATED);

        state.setSessionInfo(prev => prev ? {
          ...prev,
          totalSourceBars: source.length,
        } : { windowOffset: session.window_offset, totalSourceBars: source.length });
      } finally {
        state.setIsLoading(false);
      }
    };

    loadData();
  }, [sessionSettings.isLoaded]);

  // Compute feedback context for DAG mode
  const feedbackContext = useMemo(() => {
    if (state.calibrationPhase !== CalibrationPhase.CALIBRATED && state.calibrationPhase !== CalibrationPhase.PLAYING) {
      return null;
    }

    let stateString: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
    if (state.calibrationPhase === CalibrationPhase.CALIBRATED) {
      stateString = 'calibration_complete';
    } else if (forwardPlayback.playbackState === PlaybackState.PLAYING) {
      stateString = 'playing';
    } else {
      stateString = 'paused';
    }

    let swingsInvalidated = 0;
    let swingsCompleted = 0;
    for (const event of forwardPlayback.allEvents) {
      if (event.type === 'SWING_INVALIDATED' || event.type === 'LEG_INVALIDATED') swingsInvalidated++;
      if (event.type === 'SWING_COMPLETED') swingsCompleted++;
    }

    return {
      playbackState: forwardPlayback.playbackState,
      calibrationPhase: stateString,
      csvIndex: forwardPlayback.csvIndex,
      calibrationBarCount: state.calibrationData?.calibration_bar_count || 0,
      currentBarIndex: currentPlaybackPosition,
      swingsFoundByScale: { XL: 0, L: 0, M: 0, S: 0 },
      totalEvents: forwardPlayback.allEvents.length,
      swingsInvalidated,
      swingsCompleted,
    };
  }, [
    state.calibrationPhase,
    forwardPlayback.playbackState,
    forwardPlayback.allEvents,
    forwardPlayback.csvIndex,
    state.calibrationData?.calibration_bar_count,
    currentPlaybackPosition,
  ]);

  // Get current timestamp for header
  const currentTimestamp = state.sourceBars[currentPlaybackPosition]?.timestamp
    ? new Date(state.sourceBars[currentPlaybackPosition].timestamp * 1000).toISOString()
    : undefined;

  if (state.isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-app-bg text-app-text">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-trading-blue border-t-transparent rounded-full mx-auto mb-4"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="flex items-center justify-center h-screen bg-app-bg text-app-text">
        <div className="text-center">
          <p className="text-trading-bear mb-4">Error: {state.error}</p>
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
        onToggleSidebar={() => state.setIsSidebarOpen(!state.isSidebarOpen)}
        currentTimestamp={currentTimestamp}
        sourceBarCount={state.sourceBars.length}
        calibrationStatus={
          state.calibrationPhase === CalibrationPhase.CALIBRATING
            ? 'calibrating'
            : state.calibrationPhase === CalibrationPhase.CALIBRATED
            ? 'calibrated'
            : state.calibrationPhase === CalibrationPhase.PLAYING
            ? 'playing'
            : undefined
        }
        dataFileName={state.dataFileName}
        onOpenSettings={() => state.setIsSettingsOpen(true)}
        currentView="dag"
        onNavigate={onNavigate}
      />

      <div className="flex-1 flex min-h-0">
        <div className={`${state.isSidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 ease-in-out overflow-hidden`}>
          <Sidebar
            mode="dag"
            lingerEvents={state.lingerEvents}
            onToggleLingerEvent={handleToggleLingerEvent}
            onResetDefaults={handleResetDefaults}
            className="w-64"
            showFeedback={state.calibrationPhase === CalibrationPhase.CALIBRATED || state.calibrationPhase === CalibrationPhase.PLAYING}
            isLingering={forwardPlayback.isLingering}
            lingerEvent={forwardPlayback.lingerEvent}
            currentPlaybackBar={currentPlaybackPosition}
            feedbackContext={feedbackContext || undefined}
            onFeedbackFocus={forwardPlayback.pauseLingerTimer}
            onFeedbackBlur={forwardPlayback.resumeLingerTimer}
            onPausePlayback={forwardPlayback.pause}
            dagContext={state.dagContext}
            screenshotTargetRef={state.mainContentRef}
            lingerEnabled={state.lingerEnabled}
            attachedItems={state.attachedItems}
            onDetachItem={state.handleDetachItem}
            onClearAttachments={state.handleClearAttachments}
            detectionConfig={state.detectionConfig}
            initialDetectionConfig={chartPrefs.detectionConfig ?? undefined}
            onDetectionConfigUpdate={state.setDetectionConfig}
            isCalibrated={state.calibrationPhase === CalibrationPhase.CALIBRATED || state.calibrationPhase === CalibrationPhase.PLAYING}
            legEvents={allLegEvents}
            activeLegs={state.dagState?.active_legs}
            onHoverLeg={state.setHighlightedDagItem}
            highlightedItem={state.highlightedDagItem}
          />
        </div>

        <main ref={state.mainContentRef} className="flex-1 flex flex-col min-w-0">
          <ChartArea
            chart1Data={visibleChart1Bars}
            chart2Data={visibleChart2Bars}
            chart1Aggregation={chartPrefs.chart1Aggregation}
            chart2Aggregation={chartPrefs.chart2Aggregation}
            onChart1AggregationChange={handleChart1AggregationChange}
            onChart2AggregationChange={handleChart2AggregationChange}
            onChart1Ready={state.handleChart1Ready}
            onChart2Ready={state.handleChart2Ready}
            sourceResolutionMinutes={state.sourceResolutionMinutes}
            chart1Zoom={chartPrefs.chart1Zoom}
            chart2Zoom={chartPrefs.chart2Zoom}
            onChart1ZoomChange={chartPrefs.setChart1Zoom}
            onChart2ZoomChange={chartPrefs.setChart2Zoom}
            maximizedChart={chartPrefs.maximizedChart}
            onMaximizedChartChange={chartPrefs.setMaximizedChart}
          />

          <LegOverlay
            chart={state.chart1Ref.current}
            series={state.series1Ref.current}
            legs={state.activeLegs}
            bars={visibleChart1Bars}
            currentPosition={currentPlaybackPosition}
            highlightedLegId={state.highlightedDagItem?.type === 'leg' ? state.highlightedDagItem.id : undefined}
            onLegHover={handleChartLegHover}
            onLegClick={hierarchyMode.state.isActive ? handleHierarchyRecenter : handleChartLegClick}
            onLegDoubleClick={handleChartLegDoubleClick}
            hierarchyMode={{
              isActive: hierarchyMode.state.isActive,
              highlightedLegIds: hierarchyMode.state.highlightedLegIds,
              focusedLegId: hierarchyMode.state.focusedLegId,
            }}
            onTreeIconClick={handleTreeIconClick}
            onEyeIconClick={handleEyeIconClick}
            followedLegColors={followedLegColors}
          />
          <LegOverlay
            chart={state.chart2Ref.current}
            series={state.series2Ref.current}
            legs={state.activeLegs}
            bars={visibleChart2Bars}
            currentPosition={currentPlaybackPosition}
            highlightedLegId={state.highlightedDagItem?.type === 'leg' ? state.highlightedDagItem.id : undefined}
            onLegHover={handleChartLegHover}
            onLegClick={hierarchyMode.state.isActive ? handleHierarchyRecenter : handleChartLegClick}
            onLegDoubleClick={handleChartLegDoubleClick}
            hierarchyMode={{
              isActive: hierarchyMode.state.isActive,
              highlightedLegIds: hierarchyMode.state.highlightedLegIds,
              focusedLegId: hierarchyMode.state.focusedLegId,
            }}
            onTreeIconClick={handleTreeIconClick}
            onEyeIconClick={handleEyeIconClick}
            followedLegColors={followedLegColors}
          />

          <PendingOriginsOverlay
            chart={state.chart1Ref.current}
            series={state.series1Ref.current}
            bullOrigin={state.dagState?.pending_origins.bull ?? null}
            bearOrigin={state.dagState?.pending_origins.bear ?? null}
            highlightedOrigin={
              state.highlightedDagItem?.type === 'pending_origin'
                ? state.highlightedDagItem.direction
                : null
            }
          />
          <PendingOriginsOverlay
            chart={state.chart2Ref.current}
            series={state.series2Ref.current}
            bullOrigin={state.dagState?.pending_origins.bull ?? null}
            bearOrigin={state.dagState?.pending_origins.bear ?? null}
            highlightedOrigin={
              state.highlightedDagItem?.type === 'pending_origin'
                ? state.highlightedDagItem.direction
                : null
            }
          />

          <HierarchyModeOverlay
            chart={state.chart1Ref.current}
            series={state.series1Ref.current}
            legs={state.activeLegs}
            bars={visibleChart1Bars}
            lineage={hierarchyMode.state.lineage}
            focusedLegId={hierarchyMode.state.focusedLegId}
            isActive={hierarchyMode.state.isActive}
            onExit={hierarchyMode.exitHierarchyMode}
            onRecenter={handleHierarchyRecenter}
          />
          <HierarchyModeOverlay
            chart={state.chart2Ref.current}
            series={state.series2Ref.current}
            legs={state.activeLegs}
            bars={visibleChart2Bars}
            lineage={hierarchyMode.state.lineage}
            focusedLegId={hierarchyMode.state.focusedLegId}
            isActive={hierarchyMode.state.isActive}
            onExit={hierarchyMode.exitHierarchyMode}
            onRecenter={handleHierarchyRecenter}
          />

          <EventMarkersOverlay
            chart={state.chart1Ref.current}
            series={state.series1Ref.current}
            markersPlugin={state.markers1Ref.current}
            bars={visibleChart1Bars}
            eventsByBar={followLeg.eventsByBar}
            onMarkerClick={handleMarkerClick}
            onMarkerDoubleClick={handleMarkerDoubleClick}
            highlightedEvent={state.highlightedEvent}
          />
          <EventMarkersOverlay
            chart={state.chart2Ref.current}
            series={state.series2Ref.current}
            markersPlugin={state.markers2Ref.current}
            bars={visibleChart2Bars}
            eventsByBar={followLeg.eventsByBar}
            onMarkerClick={handleMarkerClick}
            onMarkerDoubleClick={handleMarkerDoubleClick}
            highlightedEvent={state.highlightedEvent}
          />

          <div className="shrink-0 z-10">
            <PlaybackControls
              playbackState={
                state.calibrationPhase === CalibrationPhase.PLAYING
                  ? forwardPlayback.playbackState
                  : PlaybackState.STOPPED
              }
              onPlayPause={
                state.calibrationPhase === CalibrationPhase.CALIBRATED
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
              totalBars={state.sessionInfo?.totalSourceBars || 0}
              calibrationBarCount={0}
              windowOffset={state.sessionInfo?.windowOffset}
              totalSourceBars={state.sessionInfo?.totalSourceBars}
              speedMultiplier={chartPrefs.speedMultiplier}
              onSpeedMultiplierChange={chartPrefs.setSpeedMultiplier}
              speedAggregation={chartPrefs.speedAggregation}
              onSpeedAggregationChange={chartPrefs.setSpeedAggregation}
              availableSpeedAggregations={availableSpeedAggregations}
              isLingering={forwardPlayback.isLingering}
              lingerTimeLeft={forwardPlayback.lingerTimeLeft}
              lingerTotalTime={LINGER_DURATION_MS / 1000}
              lingerEventType={forwardPlayback.lingerEvent?.type}
              lingerQueuePosition={forwardPlayback.lingerQueuePosition}
              onNavigatePrev={forwardPlayback.navigatePrevEvent}
              onNavigateNext={forwardPlayback.navigateNextEvent}
              onDismissLinger={forwardPlayback.dismissLinger}
              lingerEnabled={state.lingerEnabled}
              onToggleLinger={() => state.setLingerEnabled(prev => !prev)}
              currentTimestamp={state.sourceBars[currentPlaybackPosition]?.timestamp}
              maxTimestamp={
                state.sourceBars[currentPlaybackPosition]?.timestamp && state.sessionInfo?.totalSourceBars
                  ? state.sourceBars[currentPlaybackPosition].timestamp +
                    ((state.sessionInfo.totalSourceBars - currentPlaybackPosition - 1) * state.sourceResolutionMinutes * 60)
                  : undefined
              }
              resolutionMinutes={state.sourceResolutionMinutes}
              onProcessTill={handleProcessTill}
              isProcessingTill={state.isProcessingTill}
            />
          </div>

          <ResizeHandle onResize={handlePanelResize} />

          <div className="shrink-0" style={{ height: chartPrefs.explanationPanelHeight }}>
            <DAGStatePanel
              dagState={state.dagState}
              recentLegEvents={state.recentLegEvents}
              isLoading={state.isDagLoading}
              onHoverItem={state.setHighlightedDagItem}
              highlightedItem={state.highlightedDagItem}
              attachedItems={state.attachedItems}
              onAttachItem={state.handleAttachItem}
              onDetachItem={state.handleDetachItem}
              focusedLegId={state.focusedLegId}
              followedLegs={followLeg.followedLegs}
              onUnfollowLeg={followLeg.unfollowLeg}
              onFollowedLegClick={(legId) => {
                state.setFocusedLegId(legId);
                const leg = state.dagState?.active_legs.find(l => l.leg_id === legId);
                if (leg) {
                  state.setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
                }
              }}
              onEventClick={handleRecentEventClick}
            />
          </div>
        </main>

        {state.eventPopup && (
          <EventInspectionPopup
            events={state.eventPopup.events}
            barIndex={state.eventPopup.barIndex}
            csvIndex={state.sessionInfo ? state.sessionInfo.windowOffset + state.eventPopup.barIndex : undefined}
            position={state.eventPopup.position}
            onClose={() => { state.setEventPopup(null); state.setHighlightedEvent(null); }}
            onAttachEvent={handleAttachEvent}
            onFocusLeg={(legId) => {
              state.setFocusedLegId(legId);
              const leg = state.dagState?.active_legs.find(l => l.leg_id === legId);
              if (leg) {
                state.setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
              }
              state.setEventPopup(null);
            }}
          />
        )}

        <SettingsPanel
          isOpen={state.isSettingsOpen}
          onClose={() => state.setIsSettingsOpen(false)}
          currentDataFile={sessionSettings.dataFile || ''}
          onSessionRestart={() => window.location.reload()}
          onSaveSession={sessionSettings.saveSession}
        />
      </div>
    </div>
  );
};
