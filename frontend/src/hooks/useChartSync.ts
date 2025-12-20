import { useCallback, useEffect, useRef, RefObject } from 'react';
import { IChartApi } from 'lightweight-charts';
import { BarData } from '../types';

interface UseChartSyncOptions {
  chart1Ref: RefObject<IChartApi | null>;
  chart2Ref: RefObject<IChartApi | null>;
  chart1Bars: BarData[];
  chart2Bars: BarData[];
}

interface UseChartSyncResult {
  syncChartsToPosition: (sourceIndex: number) => void;
  syncChartsToPositionRef: RefObject<(sourceIndex: number) => void>;
  findAggBarForSourceIndex: (bars: BarData[], sourceIndex: number) => number;
}

/**
 * Hook for synchronizing chart scroll positions across multiple charts.
 *
 * Shared by Replay and DAGView pages to avoid code duplication.
 * Handles:
 * - Finding aggregated bar index for a source bar index
 * - Syncing chart scroll positions while preserving zoom level
 * - Providing a stable ref for use in callbacks
 */
export function useChartSync({
  chart1Ref,
  chart2Ref,
  chart1Bars,
  chart2Bars,
}: UseChartSyncOptions): UseChartSyncResult {
  // Ref to hold the latest syncChartsToPosition function (avoids stale closure in callback)
  const syncChartsToPositionRef = useRef<(sourceIndex: number) => void>(() => {});

  // Find aggregated bar index for a source bar index
  const findAggBarForSourceIndex = useCallback((bars: BarData[], sourceIndex: number): number => {
    for (let i = 0; i < bars.length; i++) {
      if (sourceIndex >= bars[i].source_start_index && sourceIndex <= bars[i].source_end_index) {
        return i;
      }
    }
    return bars.length - 1;
  }, []);

  // Sync charts to current position (scrolling only - markers handled separately)
  // IMPORTANT: This preserves user's zoom level and only scrolls when current bar is out of view
  const syncChartsToPosition = useCallback((sourceIndex: number) => {
    const syncChart = (
      chart: IChartApi | null,
      bars: BarData[],
      _forceCenter: boolean = false
    ) => {
      if (!chart || bars.length === 0) return;

      const aggIndex = findAggBarForSourceIndex(bars, sourceIndex);
      const visibleRange = chart.timeScale().getVisibleLogicalRange();

      if (!visibleRange) {
        // No visible range yet - use default 100 bar window
        const barsToShow = 100;
        const halfWindow = Math.floor(barsToShow / 2);
        const from = Math.max(0, aggIndex - halfWindow);
        const to = Math.min(bars.length - 1, aggIndex + halfWindow);
        chart.timeScale().setVisibleLogicalRange({ from, to });
        return;
      }

      const rangeSize = visibleRange.to - visibleRange.from;

      // Check if current bar is visible with small margin (5%)
      const margin = rangeSize * 0.05;
      if (aggIndex >= visibleRange.from + margin && aggIndex <= visibleRange.to - margin) {
        return; // Already visible - no scroll needed
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
  }, [chart1Bars, chart2Bars, chart1Ref, chart2Ref, findAggBarForSourceIndex]);

  // Keep the ref updated with the latest syncChartsToPosition
  useEffect(() => {
    syncChartsToPositionRef.current = syncChartsToPosition;
  }, [syncChartsToPosition]);

  return {
    syncChartsToPosition,
    syncChartsToPositionRef,
    findAggBarForSourceIndex,
  };
}
