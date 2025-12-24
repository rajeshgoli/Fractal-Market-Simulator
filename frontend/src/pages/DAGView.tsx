import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { IChartApi, ISeriesApi, createSeriesMarkers, Time, ISeriesMarkersPluginApi } from 'lightweight-charts';
import { Header } from '../components/Header';
import { Sidebar, DAG_LINGER_EVENTS, LingerEventConfig, DagContext } from '../components/Sidebar';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { DAGStatePanel, AttachableItem } from '../components/DAGStatePanel';
import { LegOverlay } from '../components/LegOverlay';
import { PendingOriginsOverlay } from '../components/PendingOriginsOverlay';
import { HierarchyModeOverlay } from '../components/HierarchyModeOverlay';
import { EventMarkersOverlay } from '../components/EventMarkersOverlay';
import { EventInspectionPopup } from '../components/EventInspectionPopup';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import { useHierarchyMode } from '../hooks/useHierarchyMode';
import { useFollowLeg, LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';
import {
  fetchBars,
  fetchSession,
  fetchCalibration,
  fetchDagState,
  fetchDetectionConfig,
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
  getSmallestValidAggregation,
  clampAggregationToSource,
  ActiveLeg,
  LegEvent,
  HighlightedDagItem,
  DetectionConfig,
  DEFAULT_DETECTION_CONFIG,
} from '../types';
import { ViewMode } from '../App';

/**
 * Convert DagLeg from API to ActiveLeg for visualization.
 * The API returns csv_index values (#300), so we subtract windowOffset
 * to get local bar indices for chart rendering.
 */
function dagLegToActiveLeg(leg: DagLeg, windowOffset: number = 0): ActiveLeg {
  return {
    leg_id: leg.leg_id,
    direction: leg.direction,
    pivot_price: leg.pivot_price,
    pivot_index: leg.pivot_index - windowOffset,  // Convert csv_index to local bar index
    origin_price: leg.origin_price,
    origin_index: leg.origin_index - windowOffset,  // Convert csv_index to local bar index
    retracement_pct: leg.retracement_pct,
    formed: leg.formed,
    status: leg.status,
    bar_count: leg.bar_count,
    impulsiveness: leg.impulsiveness,
    spikiness: leg.spikiness,
    parent_leg_id: leg.parent_leg_id,
    swing_id: leg.swing_id,
    // Segment impulse tracking (#307)
    impulse_to_deepest: leg.impulse_to_deepest,
    impulse_back: leg.impulse_back,
    net_segment_impulse: leg.net_segment_impulse,
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
 * - DAG internal state panel (legs, orphaned origins, pending origins)
 */
interface DAGViewProps {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

export const DAGView: React.FC<DAGViewProps> = ({ currentMode, onModeChange }) => {
  // Chart aggregation state
  const [chart1Aggregation, setChart1Aggregation] = useState<AggregationScale>('1H');
  const [chart2Aggregation, setChart2Aggregation] = useState<AggregationScale>('5m');

  // Speed control state
  const [sourceResolutionMinutes, setSourceResolutionMinutes] = useState<number>(5);
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(1);
  const [speedAggregation, setSpeedAggregation] = useState<AggregationScale>('1H');

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
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [isDagLoading, _setIsDagLoading] = useState(false);

  // Hover highlighting state for DAG items
  const [highlightedDagItem, setHighlightedDagItem] = useState<HighlightedDagItem | null>(null);

  // Focus state for chart-clicked leg (scrolls panel to leg)
  const [focusedLegId, setFocusedLegId] = useState<string | null>(null);

  // Linger toggle state (for DAG mode, default OFF for continuous observation)
  const [lingerEnabled, setLingerEnabled] = useState(false);

  // Sidebar state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Linger event toggles (DAG-specific events)
  const [lingerEvents, setLingerEvents] = useState<LingerEventConfig[]>(DAG_LINGER_EVENTS);

  // Feedback attachment state (max 5 items)
  const [attachedItems, setAttachedItems] = useState<AttachableItem[]>([]);

  // Event inspection popup state (#267)
  const [eventPopup, setEventPopup] = useState<{
    events: LifecycleEventWithLegInfo[];
    barIndex: number;
    position: { x: number; y: number };
  } | null>(null);

  // Highlighted event marker (shown when clicking Recent Events panel)
  const [highlightedEvent, setHighlightedEvent] = useState<LifecycleEventWithLegInfo | null>(null);

  // Detection config state (#288)
  const [detectionConfig, setDetectionConfig] = useState<DetectionConfig>(DEFAULT_DETECTION_CONFIG);

  const handleAttachItem = useCallback((item: AttachableItem) => {
    setAttachedItems(prev => {
      if (prev.length >= 5) return prev; // Max 5 attachments
      // Check if already attached
      const isDuplicate = prev.some(existing => {
        if (existing.type !== item.type) return false;
        if (item.type === 'leg') {
          return (existing.data as { leg_id: string }).leg_id === (item.data as { leg_id: string }).leg_id;
        } else if (item.type === 'pending_origin') {
          return (existing.data as { direction: string }).direction === (item.data as { direction: string }).direction;
        } else if (item.type === 'lifecycle_event') {
          // Lifecycle events are unique by leg_id + event_type + bar_index
          const existingEvent = existing.data as { leg_id: string; event_type: string; bar_index: number };
          const newEvent = item.data as { leg_id: string; event_type: string; bar_index: number };
          return existingEvent.leg_id === newEvent.leg_id &&
                 existingEvent.event_type === newEvent.event_type &&
                 existingEvent.bar_index === newEvent.bar_index;
        }
        return false;
      });
      if (isDuplicate) return prev;
      return [...prev, item];
    });
  }, []);

  const handleDetachItem = useCallback((item: AttachableItem) => {
    setAttachedItems(prev => prev.filter(existing => {
      if (existing.type !== item.type) return true;
      if (item.type === 'leg') {
        return (existing.data as { leg_id: string }).leg_id !== (item.data as { leg_id: string }).leg_id;
      } else if (item.type === 'pending_origin') {
        return (existing.data as { direction: string }).direction !== (item.data as { direction: string }).direction;
      } else if (item.type === 'lifecycle_event') {
        const existingEvent = existing.data as { leg_id: string; event_type: string; bar_index: number };
        const itemEvent = item.data as { leg_id: string; event_type: string; bar_index: number };
        return !(existingEvent.leg_id === itemEvent.leg_id &&
                 existingEvent.event_type === itemEvent.event_type &&
                 existingEvent.bar_index === itemEvent.bar_index);
      }
      return true;
    }));
  }, []);

  const handleClearAttachments = useCallback(() => {
    setAttachedItems([]);
  }, []);

  // Handle leg hover from chart - update highlight state
  const handleChartLegHover = useCallback((legId: string | null) => {
    if (legId) {
      const leg = dagState?.active_legs.find(l => l.leg_id === legId);
      if (leg) {
        setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
      }
    } else {
      setHighlightedDagItem(null);
    }
  }, [dagState]);

  // Handle leg click from chart - focus in panel
  const handleChartLegClick = useCallback((legId: string) => {
    const leg = dagState?.active_legs.find(l => l.leg_id === legId);
    if (leg) {
      // Set focus to scroll panel to this leg
      setFocusedLegId(legId);
      // Also highlight it
      setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
    }
  }, [dagState]);

  // Handle leg double-click from chart - attach
  const handleChartLegDoubleClick = useCallback((legId: string) => {
    const leg = dagState?.active_legs.find(l => l.leg_id === legId);
    if (leg) {
      handleAttachItem({ type: 'leg', data: leg });
    }
  }, [dagState, handleAttachItem]);

  // Handle recent event click - show popup and highlight leg (no chart scrolling)
  const handleRecentEventClick = useCallback((event: LegEvent, clickEvent: React.MouseEvent) => {
    // Capture position before any async operations
    const popupPosition = { x: clickEvent.clientX, y: clickEvent.clientY - 100 };

    // Convert LegEvent to LifecycleEventWithLegInfo for the popup
    const eventTypeMap: Record<LegEvent['type'], LifecycleEventWithLegInfo['event_type']> = {
      'LEG_CREATED': 'formed',
      'LEG_PRUNED': 'pruned',
      'LEG_INVALIDATED': 'invalidated',
    };

    const lifecycleEvent: LifecycleEventWithLegInfo = {
      leg_id: event.leg_id,
      event_type: eventTypeMap[event.type],
      bar_index: event.bar_index,
      csv_index: (sessionInfo?.windowOffset ?? 0) + event.bar_index,
      timestamp: new Date().toISOString(),
      explanation: event.reason || `${event.type} at bar ${event.bar_index}`,
      legColor: event.direction === 'bull' ? '#22c55e' : '#ef4444',
      legDirection: event.direction,
    };

    // Defer all state updates to next frame to avoid chart disposal race
    requestAnimationFrame(() => {
      // If the leg still exists, highlight and focus it
      const leg = dagState?.active_legs.find(l => l.leg_id === event.leg_id);
      if (leg) {
        setFocusedLegId(event.leg_id);
        setHighlightedDagItem({ type: 'leg', id: event.leg_id, direction: leg.direction });
      } else {
        setFocusedLegId(null);
        setHighlightedDagItem(null);
      }

      // Show popup and marker
      setHighlightedEvent(lifecycleEvent);
      setEventPopup({
        events: [lifecycleEvent],
        barIndex: event.bar_index,
        position: popupPosition,
      });
    });
  }, [dagState, sessionInfo?.windowOffset]);

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

  // Calculate bars per advance (aggregation factor)
  const aggregationBarsPerAdvance = useMemo(() => {
    const aggMinutes = getAggregationMinutes(speedAggregation);
    return Math.max(1, Math.round(aggMinutes / sourceResolutionMinutes));
  }, [speedAggregation, sourceResolutionMinutes]);

  // Calculate playback interval and speed compensation
  // When speed exceeds 20x, the 50ms floor kicks in - compensate by advancing more bars per tick
  const MIN_INTERVAL_MS = 50;
  const { effectivePlaybackIntervalMs, barsPerAdvance } = useMemo(() => {
    const rawIntervalMs = 1000 / speedMultiplier;
    // If raw interval is below minimum, calculate how many bars to advance per tick to compensate
    const speedCompensationMultiplier = rawIntervalMs < MIN_INTERVAL_MS
      ? Math.ceil(MIN_INTERVAL_MS / rawIntervalMs)
      : 1;
    return {
      effectivePlaybackIntervalMs: Math.max(MIN_INTERVAL_MS, Math.round(rawIntervalMs)),
      barsPerAdvance: aggregationBarsPerAdvance * speedCompensationMultiplier,
    };
  }, [speedMultiplier, aggregationBarsPerAdvance]);

  // Handler for aggregated bars from API response (replaces separate fetchBars calls)
  const handleAggregatedBarsChange = useCallback((aggBars: import('../lib/api').AggregatedBarsResponse) => {
    // Aggregation keys match the AggregationScale values directly
    const chart1Bars = aggBars[chart1Aggregation as keyof typeof aggBars];
    const chart2Bars = aggBars[chart2Aggregation as keyof typeof aggBars];

    if (chart1Bars) {
      setChart1Bars(chart1Bars);
    }
    if (chart2Bars) {
      setChart2Bars(chart2Bars);
    }
  }, [chart1Aggregation, chart2Aggregation]);

  // Handler for DAG state from API response (replaces separate fetchDagState call)
  const handleDagStateChange = useCallback((state: import('../lib/api').DagStateResponse) => {
    setDagState(state);
  }, []);

  // Forward playback hook
  // For DAG mode with bar_count=0 calibration, we start from position -1 (before first bar)
  const forwardPlayback = useForwardPlayback({
    calibrationBarCount: calibrationData?.calibration_bar_count ?? 0,
    calibrationBars,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    barsPerAdvance,
    filters: lingerEvents,
    lingerEnabled, // Use lingerEnabled state for toggle
    // Request aggregated bars for both chart scales + DAG state
    chartAggregationScales: [chart1Aggregation, chart2Aggregation],
    includeDagState: true,
    onNewBars: useCallback((newBars: BarData[]) => {
      setSourceBars(prev => [...prev, ...newBars]);
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        syncChartsToPositionRef.current(lastBar.index);
      }
    }, []),
    onAggregatedBarsChange: handleAggregatedBarsChange,
    onDagStateChange: handleDagStateChange,
  });

  // Convert DAG legs to ActiveLeg[] for visualization
  const activeLegs = useMemo((): ActiveLeg[] => {
    if (!dagState) return [];
    const offset = sessionInfo?.windowOffset ?? 0;
    return dagState.active_legs.map(leg => dagLegToActiveLeg(leg, offset));
  }, [dagState, sessionInfo?.windowOffset]);

  // Hierarchy exploration mode (#250)
  const hierarchyMode = useHierarchyMode(activeLegs);

  // Follow Leg feature (#267)
  const followLeg = useFollowLeg();

  // Create followedLegColors Map for LegOverlay (#267)
  const followedLegColors = useMemo(() => {
    const colors = new Map<string, string>();
    for (const leg of followLeg.followedLegs) {
      colors.set(leg.leg_id, leg.color);
    }
    return colors;
  }, [followLeg.followedLegs]);

  // Handle tree icon click - enter hierarchy mode
  const handleTreeIconClick = useCallback((legId: string) => {
    hierarchyMode.enterHierarchyMode(legId);
  }, [hierarchyMode]);

  // Handle recenter in hierarchy mode (click on another leg in hierarchy)
  const handleHierarchyRecenter = useCallback((legId: string) => {
    if (hierarchyMode.state.isActive && hierarchyMode.isInHierarchy(legId)) {
      hierarchyMode.recenterOnLeg(legId);
    }
  }, [hierarchyMode]);

  // Get current playback position
  const currentPlaybackPosition = useMemo(() => {
    if (calibrationPhase === CalibrationPhase.PLAYING) {
      return forwardPlayback.currentPosition;
    } else if (calibrationPhase === CalibrationPhase.CALIBRATED && calibrationData) {
      return calibrationData.calibration_bar_count - 1;
    }
    return 0;
  }, [calibrationPhase, forwardPlayback.currentPosition, calibrationData]);

  // Compute a "live" aggregated bar from source bars for incremental display
  // This prevents look-ahead bias by only using source bars up to currentPosition
  const computeLiveBar = useCallback((
    aggBar: BarData,
    currentPosition: number
  ): BarData | null => {
    // Find source bars within this aggregated bar's range, up to current position
    const relevantSourceBars = sourceBars.filter(
      sb => sb.index >= aggBar.source_start_index && sb.index <= currentPosition
    );

    if (relevantSourceBars.length === 0) return null;

    // Compute OHLC from the source bars we have so far
    const firstBar = relevantSourceBars[0];
    const lastBar = relevantSourceBars[relevantSourceBars.length - 1];

    return {
      ...aggBar,
      open: firstBar.open,
      high: Math.max(...relevantSourceBars.map(b => b.high)),
      low: Math.min(...relevantSourceBars.map(b => b.low)),
      close: lastBar.close,
      // Update source_end_index to reflect what we've actually processed
      source_end_index: currentPosition,
    };
  }, [sourceBars]);

  // Filter chart bars to only show candles up to current playback position
  // Complete bars use backend data; the "live" bar is computed incrementally from source bars
  const visibleChart1Bars = useMemo(() => {
    if (calibrationPhase !== CalibrationPhase.PLAYING) {
      return chart1Bars;
    }

    const result: BarData[] = [];

    for (const bar of chart1Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        // Complete bar - use backend's final OHLC
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        // Live/incomplete bar - compute OHLC from source bars we have
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        if (liveBar) {
          result.push(liveBar);
        }
      }
      // Bars that haven't started yet (source_start_index > currentPlaybackPosition) are skipped
    }

    return result;
  }, [chart1Bars, currentPlaybackPosition, calibrationPhase, computeLiveBar]);

  const visibleChart2Bars = useMemo(() => {
    if (calibrationPhase !== CalibrationPhase.PLAYING) {
      return chart2Bars;
    }

    const result: BarData[] = [];

    for (const bar of chart2Bars) {
      if (bar.source_end_index <= currentPlaybackPosition) {
        result.push(bar);
      } else if (bar.source_start_index <= currentPlaybackPosition) {
        const liveBar = computeLiveBar(bar, currentPlaybackPosition);
        if (liveBar) {
          result.push(liveBar);
        }
      }
    }

    return result;
  }, [chart2Bars, currentPlaybackPosition, calibrationPhase, computeLiveBar]);

  // Handle eye icon click - toggle follow state (#267)
  const handleEyeIconClick = useCallback((legId: string) => {
    if (followLeg.isFollowed(legId)) {
      followLeg.unfollowLeg(legId);
    } else {
      const leg = dagState?.active_legs.find(l => l.leg_id === legId);
      if (leg) {
        followLeg.followLeg(leg, currentPlaybackPosition);
      }
    }
  }, [followLeg, dagState, currentPlaybackPosition]);

  // Fetch lifecycle events for followed legs when playback advances (#267)
  useEffect(() => {
    if (calibrationPhase === CalibrationPhase.PLAYING && followLeg.followedLegs.length > 0) {
      followLeg.fetchEventsForFollowedLegs(currentPlaybackPosition);
    }
  }, [calibrationPhase, currentPlaybackPosition, followLeg]);

  // Handle marker click - show event inspection popup (#267)
  const handleMarkerClick = useCallback((
    barIndex: number,
    events: LifecycleEventWithLegInfo[],
    position: { x: number; y: number }
  ) => {
    setEventPopup({
      events,
      barIndex,
      position,
    });
  }, []);

  // Handle attaching an event to feedback (#267)
  const handleAttachEvent = useCallback((event: LifecycleEventWithLegInfo) => {
    handleAttachItem({ type: 'lifecycle_event', data: event });
    setEventPopup(null);
  }, [handleAttachItem]);

  // Handle marker double-click - attach all events from marker (#267)
  const handleMarkerDoubleClick = useCallback((events: LifecycleEventWithLegInfo[]) => {
    // Attach the primary (most significant) event
    if (events.length > 0) {
      handleAttachItem({ type: 'lifecycle_event', data: events[0] });
    }
  }, [handleAttachItem]);

  // Handler to start playback
  const handleStartPlayback = useCallback(() => {
    if (calibrationPhase === CalibrationPhase.CALIBRATED) {
      setCalibrationPhase(CalibrationPhase.PLAYING);
      forwardPlayback.play();
    }
  }, [calibrationPhase, forwardPlayback]);

  // Handler to step forward one bar (without starting continuous playback)
  const handleStepForward = useCallback(() => {
    if (calibrationPhase === CalibrationPhase.CALIBRATED) {
      setCalibrationPhase(CalibrationPhase.PLAYING);
    }
    forwardPlayback.stepForward();
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
      csvIndex: forwardPlayback.csvIndex,  // Authoritative CSV index from backend (#297)
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
    forwardPlayback.csvIndex,
    calibrationData?.calibration_bar_count,
    currentPlaybackPosition,
  ]);

  // Compute DAG context for feedback - now includes full data for debugging (#187)
  const dagContext = useMemo((): DagContext | undefined => {
    if (!dagState) return undefined;
    return {
      activeLegs: dagState.active_legs.map(leg => ({
        leg_id: leg.leg_id,
        direction: leg.direction,
        pivot_price: leg.pivot_price,
        pivot_index: leg.pivot_index,
        origin_price: leg.origin_price,
        origin_index: leg.origin_index,
        range: Math.abs(leg.origin_price - leg.pivot_price),
      })),
      pendingOrigins: {
        bull: dagState.pending_origins.bull
          ? { price: dagState.pending_origins.bull.price, bar_index: dagState.pending_origins.bull.bar_index }
          : null,
        bear: dagState.pending_origins.bear
          ? { price: dagState.pending_origins.bear.price, bar_index: dagState.pending_origins.bear.bar_index }
          : null,
      },
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

        // Adjust chart aggregations if they're below source resolution
        const smallestValid = getSmallestValidAggregation(resolutionMinutes);
        const validChart1 = clampAggregationToSource(chart1Aggregation, resolutionMinutes);
        const validChart2 = clampAggregationToSource(chart2Aggregation, resolutionMinutes);
        if (validChart1 !== chart1Aggregation) setChart1Aggregation(validChart1);
        if (validChart2 !== chart2Aggregation) setChart2Aggregation(validChart2);

        // Load source bars (need these for total count display, but won't show initially)
        const source = await fetchBars(smallestValid);

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
          fetchBars(validChart1),
          fetchBars(validChart2),
        ]);
        setChart1Bars(bars1);
        setChart2Bars(bars2);

        // Fetch initial DAG state (should be empty)
        const initialDagState = await fetchDagState();
        setDagState(initialDagState);

        // Fetch initial detection config (#288)
        try {
          const config = await fetchDetectionConfig();
          setDetectionConfig(config);
        } catch (err) {
          console.warn('Failed to fetch detection config, using defaults:', err);
        }

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

  // Sync charts to position (used during playback - avoids scrolling if already visible)
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

  // NOTE: DAG state is now fetched via /advance API response (onDagStateChange callback)
  // This eliminates the extra API call per bar advance.

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
        currentMode={currentMode}
        onModeChange={onModeChange}
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
            lingerEnabled={lingerEnabled}
            attachedItems={attachedItems}
            onDetachItem={handleDetachItem}
            onClearAttachments={handleClearAttachments}
            detectionConfig={detectionConfig}
            onDetectionConfigUpdate={setDetectionConfig}
            isCalibrated={calibrationPhase === CalibrationPhase.CALIBRATED || calibrationPhase === CalibrationPhase.PLAYING}
          />
        </div>

        <main ref={mainContentRef} className="flex-1 flex flex-col min-w-0">
          {/* Charts Area */}
          <ChartArea
            chart1Data={visibleChart1Bars}
            chart2Data={visibleChart2Bars}
            chart1Aggregation={chart1Aggregation}
            chart2Aggregation={chart2Aggregation}
            onChart1AggregationChange={handleChart1AggregationChange}
            onChart2AggregationChange={handleChart2AggregationChange}
            onChart1Ready={handleChart1Ready}
            onChart2Ready={handleChart2Ready}
            sourceResolutionMinutes={sourceResolutionMinutes}
          />

          {/* Leg Overlays - render diagonal leg lines on charts */}
          <LegOverlay
            chart={chart1Ref.current}
            series={series1Ref.current}
            legs={activeLegs}
            bars={visibleChart1Bars}
            currentPosition={currentPlaybackPosition}
            highlightedLegId={highlightedDagItem?.type === 'leg' ? highlightedDagItem.id : undefined}
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
            chart={chart2Ref.current}
            series={series2Ref.current}
            legs={activeLegs}
            bars={visibleChart2Bars}
            currentPosition={currentPlaybackPosition}
            highlightedLegId={highlightedDagItem?.type === 'leg' ? highlightedDagItem.id : undefined}
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

          {/* Pending Origins Overlays - render price lines for highlighted pending origins */}
          <PendingOriginsOverlay
            chart={chart1Ref.current}
            series={series1Ref.current}
            bullOrigin={dagState?.pending_origins.bull ?? null}
            bearOrigin={dagState?.pending_origins.bear ?? null}
            highlightedOrigin={
              highlightedDagItem?.type === 'pending_origin'
                ? highlightedDagItem.direction
                : null
            }
          />
          <PendingOriginsOverlay
            chart={chart2Ref.current}
            series={series2Ref.current}
            bullOrigin={dagState?.pending_origins.bull ?? null}
            bearOrigin={dagState?.pending_origins.bear ?? null}
            highlightedOrigin={
              highlightedDagItem?.type === 'pending_origin'
                ? highlightedDagItem.direction
                : null
            }
          />

          {/* Hierarchy Mode Overlays - exit button, connection lines (#250) */}
          <HierarchyModeOverlay
            chart={chart1Ref.current}
            series={series1Ref.current}
            legs={activeLegs}
            bars={visibleChart1Bars}
            lineage={hierarchyMode.state.lineage}
            focusedLegId={hierarchyMode.state.focusedLegId}
            isActive={hierarchyMode.state.isActive}
            onExit={hierarchyMode.exitHierarchyMode}
            onRecenter={handleHierarchyRecenter}
          />
          <HierarchyModeOverlay
            chart={chart2Ref.current}
            series={series2Ref.current}
            legs={activeLegs}
            bars={visibleChart2Bars}
            lineage={hierarchyMode.state.lineage}
            focusedLegId={hierarchyMode.state.focusedLegId}
            isActive={hierarchyMode.state.isActive}
            onExit={hierarchyMode.exitHierarchyMode}
            onRecenter={handleHierarchyRecenter}
          />

          {/* Event Markers Overlays - lifecycle event markers on candles (#267) */}
          <EventMarkersOverlay
            chart={chart1Ref.current}
            series={series1Ref.current}
            markersPlugin={markers1Ref.current}
            bars={visibleChart1Bars}
            eventsByBar={followLeg.eventsByBar}
            onMarkerClick={handleMarkerClick}
            onMarkerDoubleClick={handleMarkerDoubleClick}
            highlightedEvent={highlightedEvent}
          />
          <EventMarkersOverlay
            chart={chart2Ref.current}
            series={series2Ref.current}
            markersPlugin={markers2Ref.current}
            bars={visibleChart2Bars}
            eventsByBar={followLeg.eventsByBar}
            onMarkerClick={handleMarkerClick}
            onMarkerDoubleClick={handleMarkerDoubleClick}
            highlightedEvent={highlightedEvent}
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
              onHoverItem={setHighlightedDagItem}
              highlightedItem={highlightedDagItem}
              attachedItems={attachedItems}
              onAttachItem={handleAttachItem}
              onDetachItem={handleDetachItem}
              focusedLegId={focusedLegId}
              followedLegs={followLeg.followedLegs}
              onUnfollowLeg={followLeg.unfollowLeg}
              onFollowedLegClick={(legId) => {
                setFocusedLegId(legId);
                const leg = dagState?.active_legs.find(l => l.leg_id === legId);
                if (leg) {
                  setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
                }
              }}
              onEventClick={handleRecentEventClick}
            />
          </div>
        </main>

        {/* Event Inspection Popup (#267) */}
        {eventPopup && (
          <EventInspectionPopup
            events={eventPopup.events}
            barIndex={eventPopup.barIndex}
            csvIndex={sessionInfo ? sessionInfo.windowOffset + eventPopup.barIndex : undefined}
            position={eventPopup.position}
            onClose={() => { setEventPopup(null); setHighlightedEvent(null); }}
            onAttachEvent={handleAttachEvent}
            onFocusLeg={(legId) => {
              setFocusedLegId(legId);
              const leg = dagState?.active_legs.find(l => l.leg_id === legId);
              if (leg) {
                setHighlightedDagItem({ type: 'leg', id: legId, direction: leg.direction });
              }
              setEventPopup(null);
            }}
          />
        )}
      </div>
    </div>
  );
};
