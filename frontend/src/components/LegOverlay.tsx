import { useEffect, useRef, useCallback } from 'react';
import { IChartApi, ISeriesApi, LineStyle, Time, LineData, LineSeries } from 'lightweight-charts';
import { ActiveLeg, BarData, LEG_STATUS_STYLES } from '../types';

interface LegOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  legs: ActiveLeg[];
  bars: BarData[];
  currentPosition: number;
}

/**
 * Get color with opacity applied (hex to rgba).
 */
function getColorWithOpacity(hexColor: string, opacity: number): string {
  const r = parseInt(hexColor.slice(1, 3), 16);
  const g = parseInt(hexColor.slice(3, 5), 16);
  const b = parseInt(hexColor.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

/**
 * Get line style for LineSeries based on leg status.
 */
function getLineStyleValue(status: 'active' | 'stale' | 'invalidated'): LineStyle {
  const style = LEG_STATUS_STYLES[status];
  switch (style.lineStyle) {
    case 'dashed':
      return LineStyle.Dashed;
    case 'dotted':
      return LineStyle.Dotted;
    default:
      return LineStyle.Solid;
  }
}

/**
 * LegOverlay renders active legs as diagonal lines connecting origin to pivot.
 *
 * For each leg, it draws:
 * - A line from (origin_index, origin_price) to (pivot_index, pivot_price)
 *
 * Visual treatment:
 * - Active legs: Solid lines, blue (bull) / red (bear), 70% opacity
 * - Stale legs: Dashed lines, yellow, 50% opacity
 * - Invalidated legs: Not shown (pruned from display)
 */
export const LegOverlay: React.FC<LegOverlayProps> = ({
  chart,
  series,
  legs,
  bars,
  currentPosition,
}) => {
  // Track created line series so we can remove them on update
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lineSeriesRef = useRef<Map<string, ISeriesApi<any>>>(new Map());

  // Clear all existing line series
  const clearLineSeries = useCallback(() => {
    if (!chart) return;

    for (const [, lineSeries] of lineSeriesRef.current) {
      try {
        chart.removeSeries(lineSeries);
      } catch {
        // Series may already be removed
      }
    }
    lineSeriesRef.current.clear();
  }, [chart]);

  // Find bar timestamp by index
  const getTimestampForIndex = useCallback((barIndex: number): number | null => {
    // Find bar with matching source index range
    for (const bar of bars) {
      if (bar.source_start_index !== undefined && bar.source_end_index !== undefined) {
        if (barIndex >= bar.source_start_index && barIndex <= bar.source_end_index) {
          return bar.timestamp;
        }
      }
      // Fallback: match by exact index
      if (bar.index === barIndex) {
        return bar.timestamp;
      }
    }
    // If not found, try to estimate from bar index
    if (bars.length > 0) {
      const firstBar = bars[0];
      const lastBar = bars[bars.length - 1];
      if (bars.length >= 2) {
        // Estimate timestamp based on linear interpolation
        const barDuration = (lastBar.timestamp - firstBar.timestamp) / (bars.length - 1);
        return firstBar.timestamp + barIndex * barDuration;
      }
    }
    return null;
  }, [bars]);

  // Create line series for a leg
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const createLegLine = useCallback((leg: ActiveLeg): ISeriesApi<any> | null => {
    if (!chart || !series) return null;

    const style = LEG_STATUS_STYLES[leg.status];
    const color = getColorWithOpacity(
      style.color[leg.direction],
      style.opacity
    );
    const lineStyle = getLineStyleValue(leg.status);

    // Get timestamps for origin and pivot
    const originTime = getTimestampForIndex(leg.origin_index);
    const pivotTime = getTimestampForIndex(leg.pivot_index);

    if (originTime === null || pivotTime === null) {
      return null;
    }

    try {
      // Create line series for this leg using v5 API
      const lineSeries = chart.addSeries(LineSeries, {
        color,
        lineWidth: 2,
        lineStyle,
        crosshairMarkerVisible: false,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // Set data: line from origin to pivot
      const data: LineData<Time>[] = [
        { time: originTime as Time, value: leg.origin_price },
        { time: pivotTime as Time, value: leg.pivot_price },
      ];

      // Sort by time (required by lightweight-charts)
      data.sort((a, b) => (a.time as number) - (b.time as number));

      lineSeries.setData(data);

      return lineSeries;
    } catch (error) {
      console.error('Failed to create leg line:', error);
      return null;
    }
  }, [chart, series, getTimestampForIndex]);

  // Update line series when legs or bars change
  useEffect(() => {
    if (!chart || !series || bars.length === 0) return;

    // Clear existing lines
    clearLineSeries();

    // Filter legs to only show those visible up to current position
    // and exclude invalidated legs
    const visibleLegs = legs.filter(leg => {
      // Skip invalidated legs (they should not be shown)
      if (leg.status === 'invalidated') {
        return false;
      }
      // Only show legs where pivot is at or before current position
      return leg.pivot_index <= currentPosition;
    });

    // Create line series for each visible leg
    for (const leg of visibleLegs) {
      const lineSeries = createLegLine(leg);
      if (lineSeries) {
        lineSeriesRef.current.set(leg.leg_id, lineSeries);
      }
    }

    // Cleanup on unmount
    return () => {
      clearLineSeries();
    };
  }, [chart, series, legs, bars, currentPosition, clearLineSeries, createLegLine]);

  // This component doesn't render any DOM elements
  // It only manages line series on the chart via side effects
  return null;
};
