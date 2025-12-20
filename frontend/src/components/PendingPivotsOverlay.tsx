import { useEffect, useRef, useCallback } from 'react';
import { IChartApi, ISeriesApi, CreatePriceLineOptions, IPriceLine } from 'lightweight-charts';
import { DagPendingPivot } from '../lib/api';

interface PendingPivotsOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  bullPivot: DagPendingPivot | null;
  bearPivot: DagPendingPivot | null;
  highlightedPivot?: 'bull' | 'bear' | null;
}

// Colors for pivot lines
const BULL_PIVOT_COLOR = 'rgba(59, 130, 246, 0.8)'; // Blue
const BEAR_PIVOT_COLOR = 'rgba(239, 68, 68, 0.8)'; // Red

/**
 * PendingPivotsOverlay renders horizontal price lines for pending pivots.
 *
 * Only the highlighted pivot is shown - this provides clear visual feedback
 * when hovering over a pending pivot in the DAG State Panel.
 */
export const PendingPivotsOverlay: React.FC<PendingPivotsOverlayProps> = ({
  chart,
  series,
  bullPivot,
  bearPivot,
  highlightedPivot,
}) => {
  // Track created price lines so we can remove them on update
  const priceLinesRef = useRef<IPriceLine[]>([]);

  // Clear all existing price lines
  const clearPriceLines = useCallback(() => {
    if (!series) return;

    for (const priceLine of priceLinesRef.current) {
      try {
        series.removePriceLine(priceLine);
      } catch {
        // Price line may already be removed
      }
    }
    priceLinesRef.current = [];
  }, [series]);

  // Create a price line for a pivot
  const createPriceLine = useCallback((
    price: number,
    direction: 'bull' | 'bear',
    label: string
  ): IPriceLine | null => {
    if (!series) return null;

    const color = direction === 'bull' ? BULL_PIVOT_COLOR : BEAR_PIVOT_COLOR;

    try {
      const options: CreatePriceLineOptions = {
        price,
        color,
        lineWidth: 2,
        lineStyle: 2, // Dashed
        axisLabelVisible: true,
        title: label,
      };

      return series.createPriceLine(options);
    } catch (error) {
      console.error('Failed to create pending pivot price line:', error);
      return null;
    }
  }, [series]);

  // Update price lines when highlighted pivot changes
  useEffect(() => {
    if (!chart || !series) return;

    // Clear existing lines
    clearPriceLines();

    // Only show the highlighted pivot
    if (highlightedPivot === 'bull' && bullPivot) {
      const line = createPriceLine(bullPivot.price, 'bull', 'Pending Bull Pivot');
      if (line) {
        priceLinesRef.current.push(line);
      }
    } else if (highlightedPivot === 'bear' && bearPivot) {
      const line = createPriceLine(bearPivot.price, 'bear', 'Pending Bear Pivot');
      if (line) {
        priceLinesRef.current.push(line);
      }
    }

    // Cleanup on unmount
    return () => {
      clearPriceLines();
    };
  }, [chart, series, bullPivot, bearPivot, highlightedPivot, clearPriceLines, createPriceLine]);

  // This component doesn't render any DOM elements
  return null;
};
