import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { IChartApi, ISeriesApi, createSeriesMarkers, SeriesMarker, Time, ISeriesMarkersPluginApi } from 'lightweight-charts';
import { Header } from '../components/Header';
import { Sidebar, REPLAY_LINGER_EVENTS, LingerEventConfig } from '../components/Sidebar';
import { ChartArea } from '../components/ChartArea';
import { PlaybackControls } from '../components/PlaybackControls';
import { ExplanationPanel } from '../components/ExplanationPanel';
import { DAGStatePanel, AttachableItem } from '../components/DAGStatePanel';
import { SwingOverlay } from '../components/SwingOverlay';
import { usePlayback } from '../hooks/usePlayback';
import { useForwardPlayback } from '../hooks/useForwardPlayback';
import { fetchBars, fetchSession, fetchCalibration, fetchDagState, ReplayEvent, DagStateResponse } from '../lib/api';
import { LINGER_DURATION_MS } from '../constants';
import {
  BarData,
  AggregationScale,
  DiscretizationEvent,
  DiscretizationSwing,
  DetectedSwing,
  CalibrationData,
  CalibrationSwing,
  CalibrationPhase,
  PlaybackState,
  SWING_COLORS,
  parseResolutionToMinutes,
  getAggregationLabel,
  getAggregationMinutes,
  SwingData,
  // Hierarchical types (Issue #166)
  HierarchicalDisplayConfig,
  CalibrationDataHierarchical,
  DEFAULT_HIERARCHICAL_DISPLAY_CONFIG,
  DepthFilterKey,
  SwingStatusKey,
  SwingDirectionKey,
  LegEvent,
} from '../types';
import { useHierarchicalDisplay } from '../hooks/useSwingDisplay';
import { ViewMode } from '../App';

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

/**
 * Convert a ReplayEvent to SwingData for the explanation panel.
 * This allows forward playback events to display swing details.
 */
function replayEventToSwingData(event: ReplayEvent, sourceBars: BarData[]): SwingData | null {
  if (!event.swing) return null;

  const swing = event.swing;

  // Get timestamps from source bars if available
  const highBar = sourceBars[swing.high_bar_index];
  const lowBar = sourceBars[swing.low_bar_index];

  const formatTimestamp = (bar: BarData | undefined): string => {
    if (!bar) return '';
    try {
      const d = new Date(bar.timestamp * 1000);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '';
    }
  };

  // Calculate size percentage (relative to average of H/L)
  const avgPrice = (swing.high_price + swing.low_price) / 2;
  const sizePct = avgPrice > 0 ? (swing.size / avgPrice) * 100 : 0;

  return {
    id: swing.id,
    scale: swing.scale,
    direction: swing.direction.toLowerCase(),
    highPrice: swing.high_price,
    highBar: swing.high_bar_index,
    highTime: formatTimestamp(highBar),
    lowPrice: swing.low_price,
    lowBar: swing.low_bar_index,
    lowTime: formatTimestamp(lowBar),
    size: swing.size,
    sizePct,
    // Note: scaleReason, isAnchor, and separation are not available in ReplayEvent
    // These are calibration-specific fields
    triggerExplanation: event.trigger_explanation,
  };
}

interface ReplayProps {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

export const Replay: React.FC<ReplayProps> = ({ currentMode, onModeChange }) => {
  // UI state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

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
  // Legacy playback state - kept for usePlayback hook compatibility
  const [events] = useState<DiscretizationEvent[]>([]);
  const [swings] = useState<Record<string, DiscretizationSwing>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Session metadata (for playback controls display)
  const [sessionInfo, setSessionInfo] = useState<{
    windowOffset: number;
    totalSourceBars: number;
  } | null>(null);

  // Calibration state
  const [calibrationPhase, setCalibrationPhase] = useState<CalibrationPhase>(CalibrationPhase.NOT_STARTED);
  const [calibrationData, setCalibrationData] = useState<CalibrationData | null>(null);
  const [currentActiveSwingIndex, setCurrentActiveSwingIndex] = useState<number>(0);

  // Hierarchical display configuration (Issue #166)
  const [hierarchicalConfig, setHierarchicalConfig] = useState<HierarchicalDisplayConfig>({
    depthFilter: DEFAULT_HIERARCHICAL_DISPLAY_CONFIG.depthFilter,
    enabledStatuses: new Set(DEFAULT_HIERARCHICAL_DISPLAY_CONFIG.enabledStatuses),
    enabledDirections: new Set(DEFAULT_HIERARCHICAL_DISPLAY_CONFIG.enabledDirections),
    activeSwingCount: DEFAULT_HIERARCHICAL_DISPLAY_CONFIG.activeSwingCount,
  });

  // Show stats toggle (for displaying calibration stats during playback)
  const [showStats, setShowStats] = useState(false);

  // Linger toggle (pause on events)
  const [lingerEnabled, setLingerEnabled] = useState(true);

  // Linger event toggles (Replay-specific events)
  const [lingerEvents, setLingerEvents] = useState<LingerEventConfig[]>(REPLAY_LINGER_EVENTS);

  // DAG visualization mode state (Issue #171)
  const [dagVisualizationMode, setDagVisualizationMode] = useState(false);
  const [dagState, setDagState] = useState<DagStateResponse | null>(null);
  const [recentLegEvents, setRecentLegEvents] = useState<LegEvent[]>([]);
  const [isDagLoading, setIsDagLoading] = useState(false);

  // Feedback attachment state (max 5 items)
  const [attachedItems, setAttachedItems] = useState<AttachableItem[]>([]);

  const handleAttachItem = useCallback((item: AttachableItem) => {
    setAttachedItems(prev => {
      if (prev.length >= 5) return prev; // Max 5 attachments
      // Check if already attached
      const isDuplicate = prev.some(existing => {
        if (existing.type !== item.type) return false;
        if (item.type === 'leg') {
          return (existing.data as { leg_id: string }).leg_id === (item.data as { leg_id: string }).leg_id;
        } else {
          return (existing.data as { direction: string }).direction === (item.data as { direction: string }).direction;
        }
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
      } else {
        return (existing.data as { direction: string }).direction !== (item.data as { direction: string }).direction;
      }
    }));
  }, []);

  const handleClearAttachments = useCallback(() => {
    setAttachedItems([]);
  }, []);

  // Use hierarchical display hook for tree-based filtering (Issue #166)
  // This is now the primary source for swing display and navigation
  const hierarchicalData = calibrationData as CalibrationDataHierarchical | null;
  const {
    filteredActiveSwings: hierarchicalFilteredSwings,
    allNavigableSwings,
    statsByDepth,
  } = useHierarchicalDisplay(hierarchicalData, hierarchicalConfig);

  // Chart refs for syncing
  const chart1Ref = useRef<IChartApi | null>(null);
  const chart2Ref = useRef<IChartApi | null>(null);
  const series1Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const series2Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);

  // Main content ref for screenshot capture
  const mainContentRef = useRef<HTMLElement | null>(null);

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

  // Calculate bars per advance (aggregation factor)
  // This determines how many source bars to skip per playback tick
  // e.g., if source is 5m and user selects "1H" aggregation, skip 12 bars per tick
  const barsPerAdvance = useMemo(() => {
    const aggMinutes = getAggregationMinutes(speedAggregation);
    return Math.max(1, Math.round(aggMinutes / sourceResolutionMinutes));
  }, [speedAggregation, sourceResolutionMinutes]);

  // Calculate playback interval in ms
  // Speed = N ticks per second (each tick advances barsPerAdvance source bars)
  // So "10x at 1H" means 10 aggregated bars per second = 10 ticks per second
  const effectivePlaybackIntervalMs = useMemo(() => {
    // Each tick is one aggregated bar, so interval = 1000ms / speedMultiplier
    // Clamp to minimum 50ms interval for stability
    return Math.max(50, Math.round(1000 / speedMultiplier));
  }, [speedMultiplier]);

  // Legacy playback hook (used for calibration phase scrubbing, not forward playback)
  const playback = usePlayback({
    sourceBars,
    events,
    swings,
    filters: lingerEvents,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    onPositionChange: useCallback((position: number) => {
      syncChartsToPositionRef.current(position);
    }, []),
  });

  // Handler for aggregated bars from API response (replaces separate fetchBars calls)
  const handleAggregatedBarsChange = useCallback((aggBars: import('../lib/api').AggregatedBarsResponse) => {
    const scaleToAggKey = { 'S': 'S', 'M': 'M', 'L': 'L', 'XL': 'XL' } as const;
    const chart1Key = scaleToAggKey[chart1Aggregation as keyof typeof scaleToAggKey];
    const chart2Key = scaleToAggKey[chart2Aggregation as keyof typeof scaleToAggKey];

    if (chart1Key && aggBars[chart1Key]) {
      setChart1Bars(aggBars[chart1Key]!);
    }
    if (chart2Key && aggBars[chart2Key]) {
      setChart2Bars(aggBars[chart2Key]!);
    }
  }, [chart1Aggregation, chart2Aggregation]);

  // Forward playback hook (used for forward-only playback after calibration)
  const forwardPlayback = useForwardPlayback({
    calibrationBarCount: calibrationData?.calibration_bar_count || 10000,
    calibrationBars,
    playbackIntervalMs: effectivePlaybackIntervalMs,
    barsPerAdvance,  // How many source bars to skip per tick (aggregation factor)
    filters: lingerEvents,
    lingerEnabled,  // Whether to pause on events
    // Request aggregated bars for both chart scales
    chartAggregationScales: [chart1Aggregation, chart2Aggregation],
    onNewBars: useCallback((newBars: BarData[]) => {
      // Append new bars to source bars for chart display
      setSourceBars(prev => [...prev, ...newBars]);
      // Sync charts when new bars arrive
      if (newBars.length > 0) {
        const lastBar = newBars[newBars.length - 1];
        syncChartsToPositionRef.current(lastBar.index);
      }
    }, []),
    onAggregatedBarsChange: handleAggregatedBarsChange,
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

  // Convert forward playback's current swing state to DetectedSwing[] for marker rendering
  // Uses hierarchical config's activeSwingCount for display limiting
  const activeSwingsForMarkers = useMemo((): DetectedSwing[] => {
    if (calibrationPhase !== CalibrationPhase.PLAYING || !forwardPlayback.currentSwingState) {
      return [];
    }
    const allSwings: DetectedSwing[] = [];
    const depthKeys = ['depth_1', 'depth_2', 'depth_3', 'deeper'] as const;
    for (const depthKey of depthKeys) {
      const depthSwings = forwardPlayback.currentSwingState[depthKey] || [];
      for (const swing of depthSwings) {
        allSwings.push({
          id: swing.id,
          direction: swing.direction,
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
        });
      }
    }
    // Sort by size and limit to activeSwingCount
    allSwings.sort((a, b) => b.size - a.size);
    return allSwings.slice(0, hierarchicalConfig.activeSwingCount);
  }, [calibrationPhase, forwardPlayback.currentSwingState, hierarchicalConfig.activeSwingCount]);

  // Compute current active swing for calibration mode (navigate through all swings, not just displayed)
  const currentActiveSwing = useMemo((): CalibrationSwing | null => {
    if (calibrationPhase !== CalibrationPhase.CALIBRATED || allNavigableSwings.length === 0) {
      return null;
    }
    return allNavigableSwings[currentActiveSwingIndex] || null;
  }, [calibrationPhase, allNavigableSwings, currentActiveSwingIndex]);

  // Convert current active swing to DetectedSwing for chart overlay
  const calibrationHighlightedSwing = useMemo((): DetectedSwing | undefined => {
    if (!currentActiveSwing) return undefined;
    return calibrationSwingToDetected(currentActiveSwing, 1);
  }, [currentActiveSwing]);

  // Compute current swing for explanation panel based on calibration phase
  const currentExplanationSwing = useMemo((): SwingData | null => {
    if (calibrationPhase === CalibrationPhase.PLAYING && forwardPlayback.lingerEvent) {
      // Convert ReplayEvent to SwingData for forward playback
      return replayEventToSwingData(forwardPlayback.lingerEvent, sourceBars);
    }
    // Fall back to legacy playback swing
    return playback.currentSwing;
  }, [calibrationPhase, forwardPlayback.lingerEvent, playback.currentSwing, sourceBars]);

  // Compute feedback context for always-on observation capture
  const feedbackContext = useMemo(() => {
    // Only provide context during playback phases (CALIBRATED or PLAYING)
    if (calibrationPhase !== CalibrationPhase.CALIBRATED && calibrationPhase !== CalibrationPhase.PLAYING) {
      return null;
    }

    // Determine the calibration phase state string
    let stateString: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
    if (calibrationPhase === CalibrationPhase.CALIBRATED) {
      stateString = 'calibration_complete';
    } else if (forwardPlayback.playbackState === PlaybackState.PLAYING) {
      stateString = 'playing';
    } else {
      stateString = 'paused';
    }

    // Count swings by depth from current swing state or calibration data
    // Note: Legacy XL/L/M/S keys are kept for feedback snapshot compatibility
    const swingsFoundByScale = { XL: 0, L: 0, M: 0, S: 0 };
    if (forwardPlayback.currentSwingState) {
      // During playback, use current swing state (now depth-based)
      const swingState = forwardPlayback.currentSwingState;
      swingsFoundByScale.XL = swingState.depth_1?.length || 0;  // Root (depth 0) -> XL
      swingsFoundByScale.L = swingState.depth_2?.length || 0;   // Depth 1 -> L
      swingsFoundByScale.M = swingState.depth_3?.length || 0;   // Depth 2 -> M
      swingsFoundByScale.S = swingState.deeper?.length || 0;    // Depth 3+ -> S
    } else if (calibrationData?.active_swings_by_depth) {
      // During calibrated state, use calibration data
      swingsFoundByScale.XL = calibrationData.active_swings_by_depth.depth_1?.length || 0;
      swingsFoundByScale.L = calibrationData.active_swings_by_depth.depth_2?.length || 0;
      swingsFoundByScale.M = calibrationData.active_swings_by_depth.depth_3?.length || 0;
      swingsFoundByScale.S = calibrationData.active_swings_by_depth.deeper?.length || 0;
    }

    // Count invalidated and completed from allEvents
    let swingsInvalidated = 0;
    let swingsCompleted = 0;
    for (const event of forwardPlayback.allEvents) {
      if (event.type === 'SWING_INVALIDATED') swingsInvalidated++;
      if (event.type === 'SWING_COMPLETED') swingsCompleted++;
    }

    return {
      playbackState: forwardPlayback.playbackState,
      calibrationPhase: stateString,
      windowOffset: sessionInfo?.windowOffset || 0,
      calibrationBarCount: calibrationData?.calibration_bar_count || 0,
      currentBarIndex: calibrationPhase === CalibrationPhase.PLAYING
        ? forwardPlayback.currentPosition
        : (calibrationData?.calibration_bar_count || 0) - 1,
      swingsFoundByScale,
      totalEvents: forwardPlayback.allEvents.length,
      swingsInvalidated,
      swingsCompleted,
    };
  }, [
    calibrationPhase,
    calibrationData,
    forwardPlayback.playbackState,
    forwardPlayback.currentSwingState,
    forwardPlayback.currentPosition,
    forwardPlayback.allEvents,
    sessionInfo?.windowOffset,
  ]);

  // Navigation functions for active swing cycling (navigate through all swings, not just displayed)
  const navigatePrevActiveSwing = useCallback(() => {
    if (allNavigableSwings.length === 0) return;
    setCurrentActiveSwingIndex(prev =>
      prev === 0 ? allNavigableSwings.length - 1 : prev - 1
    );
  }, [allNavigableSwings.length]);

  const navigateNextActiveSwing = useCallback(() => {
    if (allNavigableSwings.length === 0) return;
    setCurrentActiveSwingIndex(prev =>
      prev === allNavigableSwings.length - 1 ? 0 : prev + 1
    );
  }, [allNavigableSwings.length]);

  // Handler for toggling linger event types
  const handleToggleLingerEvent = useCallback((eventId: string) => {
    setLingerEvents(prev =>
      prev.map(e => e.id === eventId ? { ...e, isEnabled: !e.isEnabled } : e)
    );
  }, []);

  // Hierarchical filter handlers (Issue #166)
  const handleSetDepthFilter = useCallback((depth: DepthFilterKey) => {
    setHierarchicalConfig(prev => ({ ...prev, depthFilter: depth }));
    setCurrentActiveSwingIndex(0);
  }, []);

  const handleToggleStatus = useCallback((status: SwingStatusKey) => {
    setHierarchicalConfig(prev => {
      const newStatuses = new Set(prev.enabledStatuses);
      if (newStatuses.has(status)) {
        newStatuses.delete(status);
      } else {
        newStatuses.add(status);
      }
      return { ...prev, enabledStatuses: newStatuses };
    });
    setCurrentActiveSwingIndex(0);
  }, []);

  const handleToggleDirection = useCallback((direction: SwingDirectionKey) => {
    setHierarchicalConfig(prev => {
      const newDirections = new Set(prev.enabledDirections);
      if (newDirections.has(direction)) {
        newDirections.delete(direction);
      } else {
        newDirections.add(direction);
      }
      return { ...prev, enabledDirections: newDirections };
    });
    setCurrentActiveSwingIndex(0);
  }, []);

  const handleSetHierarchicalActiveSwingCount = useCallback((count: number) => {
    setHierarchicalConfig(prev => ({ ...prev, activeSwingCount: count }));
    setCurrentActiveSwingIndex(0);
  }, []);

  // Handler for browsing swings at a specific depth
  const handleBrowseDepth = useCallback((depthKey: string) => {
    // Set the depth filter to show only that level
    if (depthKey === 'depth_1') {
      setHierarchicalConfig(prev => ({ ...prev, depthFilter: 'root_only' }));
    } else if (depthKey === 'depth_2') {
      setHierarchicalConfig(prev => ({ ...prev, depthFilter: '2_levels' }));
    } else if (depthKey === 'depth_3') {
      setHierarchicalConfig(prev => ({ ...prev, depthFilter: '3_levels' }));
    } else {
      setHierarchicalConfig(prev => ({ ...prev, depthFilter: 'all' }));
    }
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

        // Store session metadata for playback controls
        setSessionInfo({
          windowOffset: session.window_offset,
          totalSourceBars: session.total_source_bars,
        });

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

  // Update all markers (swing markers only) using a single markers plugin
  const updateAllMarkers = useCallback((
    markersPlugin: ISeriesMarkersPluginApi<Time> | null,
    bars: BarData[],
    sourceIndex: number,
    swings: DetectedSwing[],
    highlighted?: DetectedSwing
  ) => {
    if (!markersPlugin || bars.length === 0) return;

    const markers: SeriesMarker<Time>[] = [];

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
  // IMPORTANT: This preserves user's zoom level and only scrolls when current bar is out of view
  const syncChartsToPosition = useCallback((sourceIndex: number) => {
    const syncChart = (
      chart: IChartApi | null,
      bars: BarData[],
      forceCenter: boolean = false
    ) => {
      if (!chart || bars.length === 0) return;

      const aggIndex = findAggBarForSourceIndex(bars, sourceIndex);
      const visibleRange = chart.timeScale().getVisibleLogicalRange();

      if (!visibleRange) {
        // No visible range yet - use default 100 bar window
        const barsToShow = 100;
        const halfWindow = Math.floor(barsToShow / 2);
        let from = Math.max(0, aggIndex - halfWindow);
        let to = Math.min(bars.length - 1, aggIndex + halfWindow);
        chart.timeScale().setVisibleLogicalRange({ from, to });
        return;
      }

      const rangeSize = visibleRange.to - visibleRange.from;

      if (!forceCenter) {
        // Check if current bar is visible with small margin (5%)
        const margin = rangeSize * 0.05;
        if (aggIndex >= visibleRange.from + margin && aggIndex <= visibleRange.to - margin) {
          return; // Already visible - no scroll needed
        }
      }

      // Scroll to show current bar while PRESERVING the user's zoom level (range size)
      // Position current bar at 80% of the way through the visible range
      const positionRatio = 0.8;
      let from = aggIndex - rangeSize * positionRatio;
      let to = from + rangeSize;

      // Clamp to valid range
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

  // Convert hierarchical filtered swings to DetectedSwing format for chart display
  const hierarchicalSwingsForMarkers = useMemo((): DetectedSwing[] => {
    return hierarchicalFilteredSwings.map((swing, index) => ({
      id: swing.id,
      direction: swing.direction,
      high_price: swing.high_price,
      high_bar_index: swing.high_bar_index,
      low_price: swing.low_price,
      low_bar_index: swing.low_bar_index,
      size: swing.size,
      rank: index + 1, // Rank by filtered order
      fib_0: swing.fib_0,
      fib_0382: swing.fib_0382,
      fib_1: swing.fib_1,
      fib_2: swing.fib_2,
    }));
  }, [hierarchicalFilteredSwings]);

  // Update all chart markers when position or swings change
  // During PLAYING phase, use activeSwingsForMarkers (from currentSwingState)
  // During CALIBRATED phase, use hierarchicalSwingsForMarkers (from hierarchical display config)
  const swingsForMarkers = useMemo(() => {
    return calibrationPhase === CalibrationPhase.PLAYING
      ? activeSwingsForMarkers
      : hierarchicalSwingsForMarkers;
  }, [calibrationPhase, activeSwingsForMarkers, hierarchicalSwingsForMarkers]);

  // Use calibrationHighlightedSwing during CALIBRATED phase, highlightedSwing during PLAYING
  const markerHighlightedSwing = calibrationPhase === CalibrationPhase.CALIBRATED
    ? calibrationHighlightedSwing
    : highlightedSwing;

  useEffect(() => {
    updateAllMarkers(
      markers1Ref.current,
      chart1Bars,
      currentPlaybackPosition,
      swingsForMarkers,
      markerHighlightedSwing
    );
    updateAllMarkers(
      markers2Ref.current,
      chart2Bars,
      currentPlaybackPosition,
      swingsForMarkers,
      markerHighlightedSwing
    );
  }, [currentPlaybackPosition, swingsForMarkers, markerHighlightedSwing, chart1Bars, chart2Bars, updateAllMarkers]);

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

  // Fetch DAG state when in DAG visualization mode (Issue #171)
  useEffect(() => {
    if (!dagVisualizationMode || calibrationPhase !== CalibrationPhase.PLAYING) {
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

    // Fetch initially
    fetchState();

    // Refetch when position changes significantly (every 5 bars)
    const positionInterval = setInterval(() => {
      if (forwardPlayback.playbackState === PlaybackState.PLAYING) {
        fetchState();
      }
    }, 500);

    return () => clearInterval(positionInterval);
  }, [dagVisualizationMode, calibrationPhase, forwardPlayback.playbackState]);

  // Collect leg events from forward playback events (Issue #171)
  useEffect(() => {
    if (!dagVisualizationMode) return;

    // Extract leg events from allEvents
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

    // Keep only the most recent 20 events
    setRecentLegEvents(legEvents.slice(-20).reverse());
  }, [dagVisualizationMode, forwardPlayback.allEvents]);

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

  // Keyboard shortcuts for navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keyboard shortcuts when typing in input/textarea elements
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

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
        // Escape key dismisses linger
        if (e.key === 'Escape' && forwardPlayback.isLingering) {
          e.preventDefault();
          forwardPlayback.dismissLinger();
          return;
        }

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
    forwardPlayback.dismissLinger,
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
        currentMode={currentMode}
        onModeChange={onModeChange}
      />

      {/* Main Layout */}
      <div className="flex-1 flex min-h-0">
        {/* Sidebar */}
        <div className={`${isSidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 ease-in-out overflow-hidden`}>
          <Sidebar
            mode="replay"
            lingerEvents={lingerEvents}
            onToggleLingerEvent={handleToggleLingerEvent}
            onResetDefaults={() => setLingerEvents(REPLAY_LINGER_EVENTS)}
            className="w-64"
            // Stats toggle (shown during playback)
            showStatsToggle={calibrationPhase === CalibrationPhase.PLAYING}
            showStats={showStats}
            onToggleShowStats={() => setShowStats(prev => !prev)}
            // Feedback is always visible during CALIBRATED and PLAYING phases
            showFeedback={calibrationPhase === CalibrationPhase.CALIBRATED || calibrationPhase === CalibrationPhase.PLAYING}
            isLingering={calibrationPhase === CalibrationPhase.PLAYING && forwardPlayback.isLingering}
            lingerEvent={forwardPlayback.lingerEvent}
            currentPlaybackBar={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentPosition : (calibrationData?.calibration_bar_count || 0) - 1}
            feedbackContext={feedbackContext || undefined}
            onFeedbackFocus={forwardPlayback.pauseLingerTimer}
            onFeedbackBlur={forwardPlayback.resumeLingerTimer}
            onPausePlayback={forwardPlayback.pause}
            screenshotTargetRef={mainContentRef}
            lingerEnabled={lingerEnabled}
            attachedItems={attachedItems}
            onDetachItem={handleDetachItem}
            onClearAttachments={handleClearAttachments}
          />
        </div>

        {/* Center Content */}
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

          {/* Swing Overlays - render Fib level price lines on charts */}
          <SwingOverlay
            series={series1Ref.current}
            swings={calibrationPhase === CalibrationPhase.CALIBRATED ? [] : swingsForMarkers}
            currentPosition={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentPosition : playback.currentPosition}
            highlightedSwing={calibrationPhase === CalibrationPhase.CALIBRATED ? calibrationHighlightedSwing : highlightedSwing}
          />
          <SwingOverlay
            series={series2Ref.current}
            swings={calibrationPhase === CalibrationPhase.CALIBRATED ? [] : swingsForMarkers}
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
              // Backward navigation (#278)
              canStepBack={calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.canStepBack : true}
              currentBar={calibrationPhase === CalibrationPhase.CALIBRATED ? (calibrationData?.calibration_bar_count ?? 0) - 1 : (calibrationPhase === CalibrationPhase.PLAYING ? forwardPlayback.currentPosition : playback.currentPosition)}
              totalBars={sourceBars.length}
              // Forward playback metadata (only show new UI in PLAYING phase)
              calibrationBarCount={calibrationPhase === CalibrationPhase.PLAYING ? calibrationData?.calibration_bar_count : undefined}
              windowOffset={calibrationPhase === CalibrationPhase.PLAYING ? sessionInfo?.windowOffset : undefined}
              totalSourceBars={calibrationPhase === CalibrationPhase.PLAYING ? sessionInfo?.totalSourceBars : undefined}
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
              lingerEnabled={lingerEnabled}
              onToggleLinger={calibrationPhase === CalibrationPhase.PLAYING ? () => setLingerEnabled(prev => !prev) : undefined}
            />
          </div>

          {/* Explanation Panel / DAG State Panel - with toggle during PLAYING phase */}
          <div className="h-48 md:h-56 shrink-0 relative">
            {/* Panel toggle tabs (only in PLAYING phase) */}
            {calibrationPhase === CalibrationPhase.PLAYING && (
              <div className="absolute -top-7 right-4 flex gap-1 z-10">
                <button
                  onClick={() => setDagVisualizationMode(false)}
                  className={`px-3 py-1 text-xs rounded-t border-t border-l border-r transition-colors ${
                    !dagVisualizationMode
                      ? 'bg-app-secondary border-app-border text-app-text'
                      : 'bg-app-bg border-transparent text-app-muted hover:text-app-text'
                  }`}
                >
                  Swings
                </button>
                <button
                  onClick={() => setDagVisualizationMode(true)}
                  className={`px-3 py-1 text-xs rounded-t border-t border-l border-r transition-colors ${
                    dagVisualizationMode
                      ? 'bg-app-secondary border-app-border text-app-text'
                      : 'bg-app-bg border-transparent text-app-muted hover:text-app-text'
                  }`}
                >
                  DAG State
                </button>
              </div>
            )}

            {/* Conditionally render panel */}
            {dagVisualizationMode && calibrationPhase === CalibrationPhase.PLAYING ? (
              <DAGStatePanel
                dagState={dagState}
                recentLegEvents={recentLegEvents}
                isLoading={isDagLoading}
                attachedItems={attachedItems}
                onAttachItem={handleAttachItem}
                onDetachItem={handleDetachItem}
              />
            ) : (
              <ExplanationPanel
                swing={currentExplanationSwing}
                previousSwing={playback.previousSwing}
                calibrationPhase={calibrationPhase}
                calibrationData={calibrationData}
                currentActiveSwing={currentActiveSwing}
                currentActiveSwingIndex={currentActiveSwingIndex}
                totalActiveSwings={allNavigableSwings.length}
                onNavigatePrev={navigatePrevActiveSwing}
                onNavigateNext={navigateNextActiveSwing}
                onStartPlayback={handleStartPlayback}
                // Hierarchical display config (Issue #166)
                hierarchicalConfig={hierarchicalConfig}
                statsByDepth={statsByDepth}
                onSetDepthFilter={handleSetDepthFilter}
                onToggleStatus={handleToggleStatus}
                onToggleDirection={handleToggleDirection}
                onSetHierarchicalActiveSwingCount={handleSetHierarchicalActiveSwingCount}
                onBrowseDepth={handleBrowseDepth}
                showStats={showStats}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
};
