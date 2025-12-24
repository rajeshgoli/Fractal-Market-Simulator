import { useState, useEffect, useCallback, useRef } from 'react';
import { AggregationScale } from '../types';
import { LogicalRange } from 'lightweight-charts';

const STORAGE_KEY = 'chart-preferences';
const ZOOM_DEBOUNCE_MS = 500; // Debounce zoom saves to avoid performance issues

interface ChartPreferences {
  chart1Aggregation: AggregationScale;
  chart2Aggregation: AggregationScale;
  speedMultiplier: number;
  speedAggregation: AggregationScale;
  chart1Zoom: LogicalRange | null;
  chart2Zoom: LogicalRange | null;
  maximizedChart: 1 | 2 | null;
  explanationPanelHeight: number; // Height in pixels
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
};

function loadPreferences(): ChartPreferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        ...DEFAULT_PREFERENCES,
        ...parsed,
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
  setChart1Aggregation: (value: AggregationScale) => void;
  setChart2Aggregation: (value: AggregationScale) => void;
  setSpeedMultiplier: (value: number) => void;
  setSpeedAggregation: (value: AggregationScale) => void;
  setChart1Zoom: (value: LogicalRange | null) => void;
  setChart2Zoom: (value: LogicalRange | null) => void;
  setMaximizedChart: (value: 1 | 2 | null) => void;
  setExplanationPanelHeight: (value: number) => void;
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

  return {
    chart1Aggregation: preferences.chart1Aggregation,
    chart2Aggregation: preferences.chart2Aggregation,
    speedMultiplier: preferences.speedMultiplier,
    speedAggregation: preferences.speedAggregation,
    chart1Zoom: preferences.chart1Zoom,
    chart2Zoom: preferences.chart2Zoom,
    maximizedChart: preferences.maximizedChart,
    explanationPanelHeight: preferences.explanationPanelHeight,
    setChart1Aggregation,
    setChart2Aggregation,
    setSpeedMultiplier,
    setSpeedAggregation,
    setChart1Zoom,
    setChart2Zoom,
    setMaximizedChart,
    setExplanationPanelHeight,
  };
}
