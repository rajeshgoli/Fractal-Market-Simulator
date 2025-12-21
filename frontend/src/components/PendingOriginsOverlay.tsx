import { useEffect, useRef, useCallback } from 'react';
import { IChartApi, ISeriesApi, CreatePriceLineOptions, IPriceLine } from 'lightweight-charts';
import { DagPendingOrigin } from '../lib/api';

interface PendingOriginsOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  bullOrigin: DagPendingOrigin | null;
  bearOrigin: DagPendingOrigin | null;
  highlightedOrigin?: 'bull' | 'bear' | null;
}

// Colors for origin lines
const BULL_ORIGIN_COLOR = 'rgba(59, 130, 246, 0.8)'; // Blue
const BEAR_ORIGIN_COLOR = 'rgba(239, 68, 68, 0.8)'; // Red

/**
 * PendingOriginsOverlay renders horizontal price lines for pending origins.
 *
 * Only the highlighted origin is shown - this provides clear visual feedback
 * when hovering over a pending origin in the DAG State Panel.
 */
export const PendingOriginsOverlay: React.FC<PendingOriginsOverlayProps> = ({
  chart,
  series,
  bullOrigin,
  bearOrigin,
  highlightedOrigin,
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

  // Create a price line for an origin
  const createPriceLine = useCallback((
    price: number,
    direction: 'bull' | 'bear',
    label: string
  ): IPriceLine | null => {
    if (!series) return null;

    const color = direction === 'bull' ? BULL_ORIGIN_COLOR : BEAR_ORIGIN_COLOR;

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
      console.error('Failed to create pending origin price line:', error);
      return null;
    }
  }, [series]);

  // Update price lines when highlighted origin changes
  useEffect(() => {
    if (!chart || !series) return;

    // Clear existing lines
    clearPriceLines();

    // Only show the highlighted origin
    if (highlightedOrigin === 'bull' && bullOrigin) {
      const line = createPriceLine(bullOrigin.price, 'bull', 'Pending Bull Origin');
      if (line) {
        priceLinesRef.current.push(line);
      }
    } else if (highlightedOrigin === 'bear' && bearOrigin) {
      const line = createPriceLine(bearOrigin.price, 'bear', 'Pending Bear Origin');
      if (line) {
        priceLinesRef.current.push(line);
      }
    }

    // Cleanup on unmount
    return () => {
      clearPriceLines();
    };
  }, [chart, series, bullOrigin, bearOrigin, highlightedOrigin, clearPriceLines, createPriceLine]);

  // This component doesn't render any DOM elements
  return null;
};
