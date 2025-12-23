import { useState, useCallback, useMemo, useEffect } from 'react';
import { fetchBars } from '../lib/api';
import {
  BarData,
  AggregationScale,
  getAggregationLabel,
  getAggregationMinutes,
} from '../types';

interface UsePageSetupOptions {
  sourceResolutionMinutes: number;
  initialChart1Aggregation?: AggregationScale;
  initialChart2Aggregation?: AggregationScale;
  initialSpeedMultiplier?: number;
}

interface UsePageSetupResult {
  // Chart aggregation state
  chart1Aggregation: AggregationScale;
  chart2Aggregation: AggregationScale;
  setChart1Aggregation: (scale: AggregationScale) => void;
  setChart2Aggregation: (scale: AggregationScale) => void;

  // Speed control state
  speedMultiplier: number;
  setSpeedMultiplier: (multiplier: number) => void;
  speedAggregation: AggregationScale;
  setSpeedAggregation: (scale: AggregationScale) => void;

  // Derived values
  availableSpeedAggregations: { value: AggregationScale; label: string }[];
  barsPerAdvance: number;
  effectivePlaybackIntervalMs: number;

  // Handlers for aggregation changes
  handleChart1AggregationChange: (scale: AggregationScale) => void;
  handleChart2AggregationChange: (scale: AggregationScale) => void;

  // Chart bars state
  chart1Bars: BarData[];
  chart2Bars: BarData[];
  setChart1Bars: (bars: BarData[]) => void;
  setChart2Bars: (bars: BarData[]) => void;

  // Refresh handler
  handleRefreshAggregatedBars: () => Promise<void>;
}

/**
 * Hook for common page setup state and handlers.
 *
 * Shared by Replay and DAGView pages to avoid code duplication.
 * Handles:
 * - Chart aggregation state and changes
 * - Speed control state and calculations
 * - Chart bars loading on aggregation changes
 */
export function usePageSetup({
  sourceResolutionMinutes,
  initialChart1Aggregation = '1H',
  initialChart2Aggregation = '5m',
  initialSpeedMultiplier = 1,
}: UsePageSetupOptions): UsePageSetupResult {
  // Chart aggregation state
  const [chart1Aggregation, setChart1Aggregation] = useState<AggregationScale>(initialChart1Aggregation);
  const [chart2Aggregation, setChart2Aggregation] = useState<AggregationScale>(initialChart2Aggregation);

  // Speed control state
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(initialSpeedMultiplier);
  const [speedAggregation, setSpeedAggregation] = useState<AggregationScale>(initialChart1Aggregation);

  // Chart bars state
  const [chart1Bars, setChart1Bars] = useState<BarData[]>([]);
  const [chart2Bars, setChart2Bars] = useState<BarData[]>([]);

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
  const barsPerAdvance = useMemo(() => {
    const aggMinutes = getAggregationMinutes(speedAggregation);
    return Math.max(1, Math.round(aggMinutes / sourceResolutionMinutes));
  }, [speedAggregation, sourceResolutionMinutes]);

  // Calculate playback interval in ms
  const effectivePlaybackIntervalMs = useMemo(() => {
    return Math.max(50, Math.round(1000 / speedMultiplier));
  }, [speedMultiplier]);

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

  // Keep speedAggregation valid when chart aggregations change
  useEffect(() => {
    const validAggregations = [chart1Aggregation, chart2Aggregation];
    if (!validAggregations.includes(speedAggregation)) {
      // Default to chart1 aggregation if current is no longer valid
      setSpeedAggregation(chart1Aggregation);
    }
  }, [chart1Aggregation, chart2Aggregation, speedAggregation]);

  return {
    chart1Aggregation,
    chart2Aggregation,
    setChart1Aggregation,
    setChart2Aggregation,
    speedMultiplier,
    setSpeedMultiplier,
    speedAggregation,
    setSpeedAggregation,
    availableSpeedAggregations,
    barsPerAdvance,
    effectivePlaybackIntervalMs,
    handleChart1AggregationChange,
    handleChart2AggregationChange,
    chart1Bars,
    chart2Bars,
    setChart1Bars,
    setChart2Bars,
    handleRefreshAggregatedBars,
  };
}
