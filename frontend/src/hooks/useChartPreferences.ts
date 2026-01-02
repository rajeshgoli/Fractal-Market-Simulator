import { useState, useEffect, useCallback, useRef } from 'react';
import { AggregationScale, DetectionConfig, DEFAULT_DETECTION_CONFIG } from '../types';
import { LogicalRange } from 'lightweight-charts';
import { ReferenceConfig, DEFAULT_REFERENCE_CONFIG } from '../lib/api';

const STORAGE_KEY = 'chart-preferences';
const ZOOM_DEBOUNCE_MS = 500; // Debounce zoom saves to avoid performance issues

/**
 * Deep merge saved detection config with defaults to ensure all fields exist.
 * This handles schema evolution when new fields are added (#347, #355).
 */
function mergeDetectionConfig(saved: Partial<DetectionConfig> | null): DetectionConfig | null {
  if (!saved) return null;
  return {
    bull: { ...DEFAULT_DETECTION_CONFIG.bull, ...saved.bull },
    bear: { ...DEFAULT_DETECTION_CONFIG.bear, ...saved.bear },
    stale_extension_threshold: saved.stale_extension_threshold ?? DEFAULT_DETECTION_CONFIG.stale_extension_threshold,
    origin_range_threshold: saved.origin_range_threshold ?? DEFAULT_DETECTION_CONFIG.origin_range_threshold,
    origin_time_threshold: saved.origin_time_threshold ?? DEFAULT_DETECTION_CONFIG.origin_time_threshold,
    max_turns: saved.max_turns ?? DEFAULT_DETECTION_CONFIG.max_turns,
    engulfed_breach_threshold: saved.engulfed_breach_threshold ?? DEFAULT_DETECTION_CONFIG.engulfed_breach_threshold,
  };
}

/**
 * Deep merge saved reference config with defaults to ensure all fields exist.
 * Handles schema evolution: #425 (salience weights), #436 (unified weights).
 * Migrates old per-scale weights (big_xxx/small_xxx) to unified weights.
 */
function mergeReferenceConfig(saved: Partial<ReferenceConfig> & Record<string, unknown> | null): ReferenceConfig | null {
  if (!saved) return null;

  // Migration: if old field names exist, use big_* values as starting point
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const legacy = saved as any;
  const rangeWeight = saved.range_weight ?? legacy.big_range_weight ?? DEFAULT_REFERENCE_CONFIG.range_weight;
  const impulseWeight = saved.impulse_weight ?? legacy.big_impulse_weight ?? DEFAULT_REFERENCE_CONFIG.impulse_weight;
  const recencyWeight = saved.recency_weight ?? legacy.big_recency_weight ?? DEFAULT_REFERENCE_CONFIG.recency_weight;

  return {
    range_weight: rangeWeight,
    impulse_weight: impulseWeight,
    recency_weight: recencyWeight,
    depth_weight: saved.depth_weight ?? DEFAULT_REFERENCE_CONFIG.depth_weight,
    counter_weight: saved.counter_weight ?? DEFAULT_REFERENCE_CONFIG.counter_weight,
    range_counter_weight: saved.range_counter_weight ?? DEFAULT_REFERENCE_CONFIG.range_counter_weight,
    top_n: saved.top_n ?? DEFAULT_REFERENCE_CONFIG.top_n,
    formation_fib_threshold: saved.formation_fib_threshold ?? DEFAULT_REFERENCE_CONFIG.formation_fib_threshold,
    origin_breach_tolerance: saved.origin_breach_tolerance ?? DEFAULT_REFERENCE_CONFIG.origin_breach_tolerance,
    significant_bin_threshold: saved.significant_bin_threshold ?? DEFAULT_REFERENCE_CONFIG.significant_bin_threshold,
  };
}

// Store linger event enabled states as a simple record
type LingerEventStates = Record<string, boolean>;

interface ChartPreferences {
  chart1Aggregation: AggregationScale;
  chart2Aggregation: AggregationScale;
  speedMultiplier: number;
  speedAggregation: AggregationScale;
  chart1Zoom: LogicalRange | null;
  chart2Zoom: LogicalRange | null;
  maximizedChart: 1 | 2 | null;
  explanationPanelHeight: number; // Height in pixels
  // Detection and linger settings
  detectionConfig: DetectionConfig | null; // null = use server defaults
  lingerEnabled: boolean;
  dagLingerEvents: LingerEventStates; // DAG mode linger toggles
  // Reference config (salience weights) - Issue #425
  referenceConfig: ReferenceConfig | null; // null = use server defaults
  // Sidebar open/closed state - Issue #426
  levelsAtPlaySidebarOpen: boolean;
}

const DEFAULT_PREFERENCES: ChartPreferences = {
  chart1Aggregation: '1H',
  chart2Aggregation: '5m',
  speedMultiplier: 1,
  speedAggregation: '1H',
  chart1Zoom: null,
  chart2Zoom: null,
  maximizedChart: null,
  explanationPanelHeight: 224, // ~14rem, matching md:h-56
  detectionConfig: null,
  lingerEnabled: true,
  dagLingerEvents: {},
  referenceConfig: null, // null = use server defaults (#425)
  levelsAtPlaySidebarOpen: true, // Sidebar open by default (#426)
};

function loadPreferences(): ChartPreferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        ...DEFAULT_PREFERENCES,
        ...parsed,
        // Deep merge detection config to handle schema evolution (#347)
        detectionConfig: mergeDetectionConfig(parsed.detectionConfig),
        // Deep merge reference config to handle schema evolution (#425)
        referenceConfig: mergeReferenceConfig(parsed.referenceConfig),
      };
    }
  } catch (e) {
    console.warn('Failed to load chart preferences:', e);
  }
  return DEFAULT_PREFERENCES;
}

function savePreferences(prefs: ChartPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch (e) {
    console.warn('Failed to save chart preferences:', e);
  }
}

interface UseChartPreferencesReturn {
  chart1Aggregation: AggregationScale;
  chart2Aggregation: AggregationScale;
  speedMultiplier: number;
  speedAggregation: AggregationScale;
  chart1Zoom: LogicalRange | null;
  chart2Zoom: LogicalRange | null;
  maximizedChart: 1 | 2 | null;
  explanationPanelHeight: number;
  detectionConfig: DetectionConfig | null;
  lingerEnabled: boolean;
  dagLingerEvents: LingerEventStates;
  referenceConfig: ReferenceConfig | null;
  levelsAtPlaySidebarOpen: boolean;
  setChart1Aggregation: (value: AggregationScale) => void;
  setChart2Aggregation: (value: AggregationScale) => void;
  setSpeedMultiplier: (value: number) => void;
  setSpeedAggregation: (value: AggregationScale) => void;
  setChart1Zoom: (value: LogicalRange | null) => void;
  setChart2Zoom: (value: LogicalRange | null) => void;
  setMaximizedChart: (value: 1 | 2 | null) => void;
  setExplanationPanelHeight: (value: number) => void;
  setDetectionConfig: (value: DetectionConfig | null) => void;
  setLingerEnabled: (value: boolean) => void;
  setDagLingerEvents: (value: LingerEventStates) => void;
  setReferenceConfig: (value: ReferenceConfig | null) => void;
  setLevelsAtPlaySidebarOpen: (value: boolean) => void;
}

export function useChartPreferences(): UseChartPreferencesReturn {
  // Load initial state from localStorage
  const [preferences, setPreferences] = useState<ChartPreferences>(() => loadPreferences());

  // Track if we've initialized (to avoid saving on initial load)
  const isInitializedRef = useRef(false);

  // Save to localStorage whenever preferences change (after initial load)
  useEffect(() => {
    if (isInitializedRef.current) {
      savePreferences(preferences);
    } else {
      isInitializedRef.current = true;
    }
  }, [preferences]);

  const setChart1Aggregation = useCallback((value: AggregationScale) => {
    setPreferences(prev => ({ ...prev, chart1Aggregation: value }));
  }, []);

  const setChart2Aggregation = useCallback((value: AggregationScale) => {
    setPreferences(prev => ({ ...prev, chart2Aggregation: value }));
  }, []);

  const setSpeedMultiplier = useCallback((value: number) => {
    setPreferences(prev => ({ ...prev, speedMultiplier: value }));
  }, []);

  const setSpeedAggregation = useCallback((value: AggregationScale) => {
    setPreferences(prev => ({ ...prev, speedAggregation: value }));
  }, []);

  // Debounced zoom setters to avoid performance issues during continuous scroll/drag
  const chart1ZoomTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chart2ZoomTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setChart1Zoom = useCallback((value: LogicalRange | null) => {
    if (chart1ZoomTimeoutRef.current) {
      clearTimeout(chart1ZoomTimeoutRef.current);
    }
    chart1ZoomTimeoutRef.current = setTimeout(() => {
      setPreferences(prev => ({ ...prev, chart1Zoom: value }));
    }, ZOOM_DEBOUNCE_MS);
  }, []);

  const setChart2Zoom = useCallback((value: LogicalRange | null) => {
    if (chart2ZoomTimeoutRef.current) {
      clearTimeout(chart2ZoomTimeoutRef.current);
    }
    chart2ZoomTimeoutRef.current = setTimeout(() => {
      setPreferences(prev => ({ ...prev, chart2Zoom: value }));
    }, ZOOM_DEBOUNCE_MS);
  }, []);

  const setMaximizedChart = useCallback((value: 1 | 2 | null) => {
    setPreferences(prev => ({ ...prev, maximizedChart: value }));
  }, []);

  const setExplanationPanelHeight = useCallback((value: number) => {
    setPreferences(prev => ({ ...prev, explanationPanelHeight: value }));
  }, []);

  const setDetectionConfig = useCallback((value: DetectionConfig | null) => {
    setPreferences(prev => ({ ...prev, detectionConfig: value }));
  }, []);

  const setLingerEnabled = useCallback((value: boolean) => {
    setPreferences(prev => ({ ...prev, lingerEnabled: value }));
  }, []);

  const setDagLingerEvents = useCallback((value: LingerEventStates) => {
    setPreferences(prev => ({ ...prev, dagLingerEvents: value }));
  }, []);

  const setReferenceConfig = useCallback((value: ReferenceConfig | null) => {
    setPreferences(prev => ({ ...prev, referenceConfig: value }));
  }, []);

  const setLevelsAtPlaySidebarOpen = useCallback((value: boolean) => {
    setPreferences(prev => ({ ...prev, levelsAtPlaySidebarOpen: value }));
  }, []);

  return {
    chart1Aggregation: preferences.chart1Aggregation,
    chart2Aggregation: preferences.chart2Aggregation,
    speedMultiplier: preferences.speedMultiplier,
    speedAggregation: preferences.speedAggregation,
    chart1Zoom: preferences.chart1Zoom,
    chart2Zoom: preferences.chart2Zoom,
    maximizedChart: preferences.maximizedChart,
    explanationPanelHeight: preferences.explanationPanelHeight,
    detectionConfig: preferences.detectionConfig,
    lingerEnabled: preferences.lingerEnabled,
    dagLingerEvents: preferences.dagLingerEvents,
    referenceConfig: preferences.referenceConfig,
    levelsAtPlaySidebarOpen: preferences.levelsAtPlaySidebarOpen,
    setChart1Aggregation,
    setChart2Aggregation,
    setSpeedMultiplier,
    setSpeedAggregation,
    setChart1Zoom,
    setChart2Zoom,
    setMaximizedChart,
    setExplanationPanelHeight,
    setDetectionConfig,
    setLingerEnabled,
    setDagLingerEvents,
    setReferenceConfig,
    setLevelsAtPlaySidebarOpen,
  };
}
