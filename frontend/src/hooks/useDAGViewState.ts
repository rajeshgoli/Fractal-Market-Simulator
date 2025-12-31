import { useState, useCallback, useRef, useMemo } from 'react';
import { IChartApi, ISeriesApi, Time, ISeriesMarkersPluginApi, createSeriesMarkers } from 'lightweight-charts';
import {
  DagStateResponse,
  DagLeg,
} from '../lib/api';
import {
  BarData,
  CalibrationData,
  CalibrationPhase,
  ActiveLeg,
  LegEvent,
  HighlightedDagItem,
  DetectionConfig,
  DEFAULT_DETECTION_CONFIG,
} from '../types';
import { LingerEventConfig, DAG_LINGER_EVENTS, DagContext } from '../components/Sidebar';
import { AttachableItem } from '../components/DAGStatePanel';
import { LifecycleEventWithLegInfo } from './useFollowLeg';

/**
 * Convert DagLeg from API to ActiveLeg for visualization.
 * The API returns csv_index values (#300), so we subtract windowOffset
 * to get local bar indices for chart rendering.
 */
export function dagLegToActiveLeg(leg: DagLeg, windowOffset: number = 0): ActiveLeg {
  return {
    leg_id: leg.leg_id,
    direction: leg.direction,
    pivot_price: leg.pivot_price,
    pivot_index: leg.pivot_index - windowOffset,
    origin_price: leg.origin_price,
    origin_index: leg.origin_index - windowOffset,
    retracement_pct: leg.retracement_pct,
    formed: leg.formed,
    status: leg.status as 'active' | 'stale',
    origin_breached: leg.origin_breached,
    bar_count: leg.bar_count,
    impulsiveness: leg.impulsiveness,
    spikiness: leg.spikiness,
    parent_leg_id: leg.parent_leg_id,
    swing_id: leg.swing_id,
    impulse_to_deepest: leg.impulse_to_deepest,
    impulse_back: leg.impulse_back,
    net_segment_impulse: leg.net_segment_impulse,
  };
}

interface SessionInfo {
  windowOffset: number;
  totalSourceBars: number;
}

interface EventPopupState {
  events: LifecycleEventWithLegInfo[];
  barIndex: number;
  position: { x: number; y: number };
}

interface UseDAGViewStateProps {
  // From chart preferences (persisted)
  savedLingerEnabled: boolean;
  savedLingerEvents: Record<string, boolean>;
  saveLingerEnabled: (value: boolean) => void;
  saveLingerEvents: (value: Record<string, boolean>) => void;
  savedDetectionConfig: DetectionConfig | null;
  saveDetectionConfig: (value: DetectionConfig) => void;
}

interface UseDAGViewStateReturn {
  // Session state
  sessionInfo: SessionInfo | null;
  setSessionInfo: React.Dispatch<React.SetStateAction<SessionInfo | null>>;
  sourceResolutionMinutes: number;
  setSourceResolutionMinutes: React.Dispatch<React.SetStateAction<number>>;
  dataFileName: string;
  setDataFileName: React.Dispatch<React.SetStateAction<string>>;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  error: string | null;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  isSettingsOpen: boolean;
  setIsSettingsOpen: React.Dispatch<React.SetStateAction<boolean>>;

  // Bar data
  sourceBars: BarData[];
  setSourceBars: React.Dispatch<React.SetStateAction<BarData[]>>;
  calibrationBars: BarData[];
  setCalibrationBars: React.Dispatch<React.SetStateAction<BarData[]>>;
  chart1Bars: BarData[];
  setChart1Bars: React.Dispatch<React.SetStateAction<BarData[]>>;
  chart2Bars: BarData[];
  setChart2Bars: React.Dispatch<React.SetStateAction<BarData[]>>;

  // Calibration state
  calibrationPhase: CalibrationPhase;
  setCalibrationPhase: React.Dispatch<React.SetStateAction<CalibrationPhase>>;
  calibrationData: CalibrationData | null;
  setCalibrationData: React.Dispatch<React.SetStateAction<CalibrationData | null>>;

  // DAG state
  dagState: DagStateResponse | null;
  setDagState: React.Dispatch<React.SetStateAction<DagStateResponse | null>>;
  recentLegEvents: LegEvent[];
  setRecentLegEvents: React.Dispatch<React.SetStateAction<LegEvent[]>>;
  isDagLoading: boolean;

  // Highlight and focus state
  highlightedDagItem: HighlightedDagItem | null;
  setHighlightedDagItem: React.Dispatch<React.SetStateAction<HighlightedDagItem | null>>;
  focusedLegId: string | null;
  setFocusedLegId: React.Dispatch<React.SetStateAction<string | null>>;

  // UI state
  isSidebarOpen: boolean;
  setIsSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  isProcessingTill: boolean;
  setIsProcessingTill: React.Dispatch<React.SetStateAction<boolean>>;

  // Linger state
  lingerEnabled: boolean;
  setLingerEnabled: (value: boolean | ((prev: boolean) => boolean)) => void;
  lingerEvents: LingerEventConfig[];
  setLingerEvents: (value: LingerEventConfig[] | ((prev: LingerEventConfig[]) => LingerEventConfig[])) => void;

  // Attachment state
  attachedItems: AttachableItem[];
  handleAttachItem: (item: AttachableItem) => void;
  handleDetachItem: (item: AttachableItem) => void;
  handleClearAttachments: () => void;

  // Event popup state
  eventPopup: EventPopupState | null;
  setEventPopup: React.Dispatch<React.SetStateAction<EventPopupState | null>>;
  highlightedEvent: LifecycleEventWithLegInfo | null;
  setHighlightedEvent: React.Dispatch<React.SetStateAction<LifecycleEventWithLegInfo | null>>;

  // Detection config
  detectionConfig: DetectionConfig;
  setDetectionConfig: (value: DetectionConfig) => void;
  setDetectionConfigFromServer: (value: DetectionConfig) => void;

  // Chart refs
  chart1Ref: React.MutableRefObject<IChartApi | null>;
  chart2Ref: React.MutableRefObject<IChartApi | null>;
  series1Ref: React.MutableRefObject<ISeriesApi<'Candlestick'> | null>;
  series2Ref: React.MutableRefObject<ISeriesApi<'Candlestick'> | null>;
  markers1Ref: React.MutableRefObject<ISeriesMarkersPluginApi<Time> | null>;
  markers2Ref: React.MutableRefObject<ISeriesMarkersPluginApi<Time> | null>;
  mainContentRef: React.MutableRefObject<HTMLElement | null>;
  syncChartsToPositionRef: React.MutableRefObject<(sourceIndex: number) => void>;

  // Chart ready handlers
  handleChart1Ready: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => void;
  handleChart2Ready: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => void;

  // Computed values
  activeLegs: ActiveLeg[];
  dagContext: DagContext | undefined;
}

export function useDAGViewState({
  savedLingerEnabled,
  savedLingerEvents,
  saveLingerEnabled,
  saveLingerEvents,
  savedDetectionConfig,
  saveDetectionConfig,
}: UseDAGViewStateProps): UseDAGViewStateReturn {
  // Session state
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [sourceResolutionMinutes, setSourceResolutionMinutes] = useState<number>(5);
  const [dataFileName, setDataFileName] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Bar data
  const [sourceBars, setSourceBars] = useState<BarData[]>([]);
  const [calibrationBars, setCalibrationBars] = useState<BarData[]>([]);
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);

  // Calibration state
  const [calibrationPhase, setCalibrationPhase] = useState<CalibrationPhase>(CalibrationPhase.NOT_STARTED);
  const [calibrationData, setCalibrationData] = useState<CalibrationData | null>(null);

  // DAG state
  const [dagState, setDagState] = useState<DagStateResponse | null>(null);
  const [recentLegEvents, setRecentLegEvents] = useState<LegEvent[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [isDagLoading, _setIsDagLoading] = useState(false);

  // Highlight and focus state
  const [highlightedDagItem, setHighlightedDagItem] = useState<HighlightedDagItem | null>(null);
  const [focusedLegId, setFocusedLegId] = useState<string | null>(null);

  // UI state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isProcessingTill, setIsProcessingTill] = useState(false);

  // Linger state - initialized from saved preferences
  const [lingerEnabled, setLingerEnabledState] = useState(savedLingerEnabled);
  const [lingerEvents, setLingerEventsState] = useState<LingerEventConfig[]>(() =>
    DAG_LINGER_EVENTS.map(event => ({
      ...event,
      isEnabled: savedLingerEvents[event.id] ?? event.isEnabled,
    }))
  );

  // Wrap setLingerEnabled to also save to preferences
  const setLingerEnabled = useCallback((value: boolean | ((prev: boolean) => boolean)) => {
    setLingerEnabledState(prev => {
      const newValue = typeof value === 'function' ? value(prev) : value;
      saveLingerEnabled(newValue);
      return newValue;
    });
  }, [saveLingerEnabled]);

  // Wrap setLingerEvents to also save to preferences
  const setLingerEvents = useCallback((value: LingerEventConfig[] | ((prev: LingerEventConfig[]) => LingerEventConfig[])) => {
    setLingerEventsState(prev => {
      const newEvents = typeof value === 'function' ? value(prev) : value;
      const eventStates: Record<string, boolean> = {};
      newEvents.forEach(e => { eventStates[e.id] = e.isEnabled; });
      saveLingerEvents(eventStates);
      return newEvents;
    });
  }, [saveLingerEvents]);

  // Attachment state
  const [attachedItems, setAttachedItems] = useState<AttachableItem[]>([]);

  const handleAttachItem = useCallback((item: AttachableItem) => {
    setAttachedItems(prev => {
      if (prev.length >= 5) return prev;
      const isDuplicate = prev.some(existing => {
        if (existing.type !== item.type) return false;
        if (item.type === 'leg') {
          return (existing.data as { leg_id: string }).leg_id === (item.data as { leg_id: string }).leg_id;
        } else if (item.type === 'pending_origin') {
          return (existing.data as { direction: string }).direction === (item.data as { direction: string }).direction;
        } else if (item.type === 'lifecycle_event') {
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

  // Event popup state
  const [eventPopup, setEventPopup] = useState<EventPopupState | null>(null);
  const [highlightedEvent, setHighlightedEvent] = useState<LifecycleEventWithLegInfo | null>(null);

  // Detection config state - server config is authoritative
  const [detectionConfig, setDetectionConfigState] = useState<DetectionConfig>(
    savedDetectionConfig ?? DEFAULT_DETECTION_CONFIG
  );

  const setDetectionConfig = useCallback((value: DetectionConfig) => {
    setDetectionConfigState(value);
    saveDetectionConfig(value);
  }, [saveDetectionConfig]);

  // Server initialization path - updates state without saving to localStorage
  // Used when fetching config from server on page load (#358)
  const setDetectionConfigFromServer = useCallback((value: DetectionConfig) => {
    setDetectionConfigState(value);
  }, []);

  // Chart refs
  const chart1Ref = useRef<IChartApi | null>(null);
  const chart2Ref = useRef<IChartApi | null>(null);
  const series1Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const series2Ref = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const markers1Ref = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const markers2Ref = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const mainContentRef = useRef<HTMLElement | null>(null);
  const syncChartsToPositionRef = useRef<(sourceIndex: number) => void>(() => {});

  // Chart ready handlers
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

  // Computed: Convert DAG legs to ActiveLeg[] for visualization
  const activeLegs = useMemo((): ActiveLeg[] => {
    if (!dagState) return [];
    const offset = sessionInfo?.windowOffset ?? 0;
    return dagState.active_legs.map(leg => dagLegToActiveLeg(leg, offset));
  }, [dagState, sessionInfo?.windowOffset]);

  // Computed: DAG context for feedback
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

  return {
    // Session state
    sessionInfo,
    setSessionInfo,
    sourceResolutionMinutes,
    setSourceResolutionMinutes,
    dataFileName,
    setDataFileName,
    isLoading,
    setIsLoading,
    error,
    setError,
    isSettingsOpen,
    setIsSettingsOpen,

    // Bar data
    sourceBars,
    setSourceBars,
    calibrationBars,
    setCalibrationBars,
    chart1Bars,
    setChart1Bars,
    chart2Bars,
    setChart2Bars,

    // Calibration state
    calibrationPhase,
    setCalibrationPhase,
    calibrationData,
    setCalibrationData,

    // DAG state
    dagState,
    setDagState,
    recentLegEvents,
    setRecentLegEvents,
    isDagLoading,

    // Highlight and focus state
    highlightedDagItem,
    setHighlightedDagItem,
    focusedLegId,
    setFocusedLegId,

    // UI state
    isSidebarOpen,
    setIsSidebarOpen,
    isProcessingTill,
    setIsProcessingTill,

    // Linger state
    lingerEnabled,
    setLingerEnabled,
    lingerEvents,
    setLingerEvents,

    // Attachment state
    attachedItems,
    handleAttachItem,
    handleDetachItem,
    handleClearAttachments,

    // Event popup state
    eventPopup,
    setEventPopup,
    highlightedEvent,
    setHighlightedEvent,

    // Detection config
    detectionConfig,
    setDetectionConfig,
    setDetectionConfigFromServer,

    // Chart refs
    chart1Ref,
    chart2Ref,
    series1Ref,
    series2Ref,
    markers1Ref,
    markers2Ref,
    mainContentRef,
    syncChartsToPositionRef,

    // Chart ready handlers
    handleChart1Ready,
    handleChart2Ready,

    // Computed values
    activeLegs,
    dagContext,
  };
}
