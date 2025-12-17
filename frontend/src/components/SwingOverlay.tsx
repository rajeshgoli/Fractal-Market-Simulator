import { useEffect, useRef, useCallback } from 'react';
import { ISeriesApi, CreatePriceLineOptions, IPriceLine, LineStyle, ISeriesMarkersPluginApi, Time, SeriesMarker } from 'lightweight-charts';
import { DetectedSwing, SWING_COLORS, BarData } from '../types';

interface SwingOverlayProps {
  series: ISeriesApi<'Candlestick'> | null;
  swings: DetectedSwing[];
  currentPosition: number;
  highlightedSwing?: DetectedSwing;
  markersPlugin?: ISeriesMarkersPluginApi<Time> | null;
  bars?: BarData[];
}

// Fib level configuration - show HIGH/LOW labels for the swing endpoints
const FIB_LEVELS = [
  { key: 'fib_0', label: '0', opacity: 0.9 },
  { key: 'fib_0382', label: '0.382', opacity: 0.7 },
  { key: 'fib_1', label: '1', opacity: 0.9 },
  { key: 'fib_2', label: '2', opacity: 0.6 },
] as const;

/**
 * Get label for a Fib level based on swing direction.
 * For endpoints (0 and 1), show HIGH/LOW to make swing anchors clear.
 */
function getLevelLabel(levelKey: string, direction: 'bull' | 'bear'): string {
  const arrow = direction === 'bull' ? '▲' : '▼';

  if (levelKey === 'fib_0') {
    // For bull: 0 = defended pivot = LOW; For bear: 0 = defended pivot = HIGH
    return direction === 'bull' ? `LOW ${arrow}` : `HIGH ${arrow}`;
  }
  if (levelKey === 'fib_1') {
    // For bull: 1 = origin = HIGH; For bear: 1 = origin = LOW
    return direction === 'bull' ? `HIGH ${arrow}` : `LOW ${arrow}`;
  }
  // Other levels show the ratio
  const level = FIB_LEVELS.find(l => l.key === levelKey);
  return `${level?.label ?? levelKey} ${arrow}`;
}

/**
 * Find the aggregated bar that contains a given source bar index.
 * Returns the bar's timestamp for placing markers.
 */
function findBarTimestamp(bars: BarData[], sourceIndex: number): number | null {
  // Binary search for the bar containing this source index
  for (const bar of bars) {
    if (sourceIndex >= bar.source_start_index && sourceIndex <= bar.source_end_index) {
      return bar.timestamp;
    }
  }
  // Fallback: find closest bar
  if (bars.length === 0) return null;

  // Find bar with closest source_end_index
  let closest = bars[0];
  for (const bar of bars) {
    if (bar.source_end_index <= sourceIndex) {
      closest = bar;
    } else {
      break;
    }
  }
  return closest.timestamp;
}

/**
 * SwingOverlay renders swing markers and Fib levels on a chart.
 *
 * For each detected swing, it shows:
 * - HIGH/LOW markers at the actual swing anchor bar positions
 * - Fib levels (0, 0.382, 1, 2) as horizontal price lines
 * - Bull swings use solid lines, bear swings use dashed lines
 */
export const SwingOverlay: React.FC<SwingOverlayProps> = ({
  series,
  swings,
  currentPosition,
  highlightedSwing,
  markersPlugin,
  bars,
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

      // Create price line options with descriptive labels
      const options: CreatePriceLineOptions = {
        price,
        color,
        lineWidth: level.key === 'fib_1' || level.key === 'fib_0' ? 2 : 1,
        lineStyle,
        axisLabelVisible: true,
        title: getLevelLabel(level.key, swing.direction),
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

  // Update price lines and markers when swings change
  useEffect(() => {
    if (!series) return;

    // Clear existing lines
    clearPriceLines();

    // When a specific swing is highlighted (during linger), only show that swing
    // Use the highlighted swing directly since it comes from discretization (different ID format)
    let visibleSwings: DetectedSwing[];
    if (highlightedSwing) {
      visibleSwings = [highlightedSwing];
    } else {
      // Filter swings to only show those visible up to current position
      visibleSwings = swings.filter(swing => {
        // Only show swings where both points are before current position
        const maxBarIndex = Math.max(swing.high_bar_index, swing.low_bar_index);
        return maxBarIndex <= currentPosition;
      });
    }

    // Create lines for each visible swing
    const allLines: IPriceLine[] = [];

    for (const swing of visibleSwings) {
      const color = SWING_COLORS[swing.rank] || SWING_COLORS[1];
      const lines = createSwingLines(swing, color);
      allLines.push(...lines);
    }

    priceLinesRef.current = allLines;

    // Create markers for swing high/low points if plugin and bars available
    if (markersPlugin && bars && bars.length > 0) {
      const markers: SeriesMarker<Time>[] = [];

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
    }

    // Cleanup on unmount
    return () => {
      clearPriceLines();
      if (markersPlugin) {
        markersPlugin.setMarkers([]);
      }
    };
  }, [series, swings, currentPosition, highlightedSwing, clearPriceLines, createSwingLines, markersPlugin, bars]);

  // This component doesn't render any DOM elements
  // It only manages price lines on the chart via side effects
  return null;
};
