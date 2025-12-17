import { useEffect, useRef, useCallback } from 'react';
import { ISeriesApi, CreatePriceLineOptions, IPriceLine, LineStyle } from 'lightweight-charts';
import { DetectedSwing, SWING_COLORS } from '../types';

interface SwingOverlayProps {
  series: ISeriesApi<'Candlestick'> | null;
  swings: DetectedSwing[];
  currentPosition: number;
}

// Fib level configuration
const FIB_LEVELS = [
  { key: 'fib_0', label: '0', opacity: 0.9 },
  { key: 'fib_0382', label: '0.382', opacity: 0.7 },
  { key: 'fib_1', label: '1', opacity: 0.9 },
  { key: 'fib_2', label: '2', opacity: 0.6 },
] as const;

/**
 * SwingOverlay renders swing markers and Fib levels on a chart.
 *
 * For each detected swing, it shows:
 * - High point horizontal line with price label
 * - Low point horizontal line with price label
 * - Fib levels (0, 0.382, 1, 2)
 * - Bull swings use solid lines, bear swings use dashed lines
 */
export const SwingOverlay: React.FC<SwingOverlayProps> = ({
  series,
  swings,
  currentPosition,
}) => {
  // Track created price lines so we can remove them on update
  const priceLinesRef = useRef<IPriceLine[]>([]);

  // Clear all existing price lines
  const clearPriceLines = useCallback(() => {
    if (!series) return;

    for (const line of priceLinesRef.current) {
      try {
        series.removePriceLine(line);
      } catch {
        // Line may already be removed
      }
    }
    priceLinesRef.current = [];
  }, [series]);

  // Create price lines for a single swing
  const createSwingLines = useCallback((
    swing: DetectedSwing,
    color: string,
  ): IPriceLine[] => {
    if (!series) return [];

    const lines: IPriceLine[] = [];
    const lineStyle = swing.direction === 'bull' ? LineStyle.Solid : LineStyle.Dashed;

    // Create Fib level lines
    for (const level of FIB_LEVELS) {
      const price = swing[level.key] as number;

      // Create price line options
      const options: CreatePriceLineOptions = {
        price,
        color,
        lineWidth: level.key === 'fib_1' || level.key === 'fib_0' ? 2 : 1,
        lineStyle,
        axisLabelVisible: true,
        title: `${level.label} ${swing.direction === 'bull' ? '▲' : '▼'}`,
      };

      try {
        const priceLine = series.createPriceLine(options);
        lines.push(priceLine);
      } catch {
        // Handle any errors creating lines
      }
    }

    return lines;
  }, [series]);

  // Update price lines when swings change
  useEffect(() => {
    if (!series) return;

    // Clear existing lines
    clearPriceLines();

    // Filter swings to only show those visible up to current position
    const visibleSwings = swings.filter(swing => {
      // Only show swings where both points are before current position
      const maxBarIndex = Math.max(swing.high_bar_index, swing.low_bar_index);
      return maxBarIndex <= currentPosition;
    });

    // Create lines for each visible swing
    const allLines: IPriceLine[] = [];

    for (const swing of visibleSwings) {
      const color = SWING_COLORS[swing.rank] || SWING_COLORS[1];
      const lines = createSwingLines(swing, color);
      allLines.push(...lines);
    }

    priceLinesRef.current = allLines;

    // Cleanup on unmount
    return () => {
      clearPriceLines();
    };
  }, [series, swings, currentPosition, clearPriceLines, createSwingLines]);

  // This component doesn't render any DOM elements
  // It only manages price lines on the chart via side effects
  return null;
};
