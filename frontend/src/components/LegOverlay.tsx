import { useEffect, useRef, useCallback } from 'react';
import { ISeriesApi, IPriceLine, LineStyle } from 'lightweight-charts';
import { ActiveLeg, LegStatus, LEG_STATUS_STYLES } from '../types';

interface LegOverlayProps {
  series: ISeriesApi<'Candlestick'> | null;
  legs: ActiveLeg[];
  currentPosition: number;
}

/**
 * Get the line style enum value for a leg status.
 */
function getLineStyle(status: LegStatus): LineStyle {
  const style = LEG_STATUS_STYLES[status];
  switch (style.lineStyle) {
    case 'solid':
      return LineStyle.Solid;
    case 'dashed':
      return LineStyle.Dashed;
    case 'dotted':
      return LineStyle.Dotted;
    default:
      return LineStyle.Solid;
  }
}

/**
 * Get color with opacity applied (hex to rgba).
 */
function getColorWithOpacity(hexColor: string, opacity: number): string {
  // Parse hex color
  const r = parseInt(hexColor.slice(1, 3), 16);
  const g = parseInt(hexColor.slice(3, 5), 16);
  const b = parseInt(hexColor.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

/**
 * LegOverlay renders active legs as horizontal price lines on a chart.
 *
 * For each leg, it shows:
 * - Pivot price line (the defended pivot)
 * - Origin price line (the swing origin)
 *
 * Visual treatment:
 * - Active legs: Solid lines, blue (bull) / red (bear), 70% opacity
 * - Stale legs: Dashed lines, yellow, 50% opacity
 * - Invalidated legs: Dotted lines, gray, 30% opacity (briefly shown)
 */
export const LegOverlay: React.FC<LegOverlayProps> = ({
  series,
  legs,
  currentPosition,
}) => {
  // Track created price lines so we can remove them on update
  const priceLinesRef = useRef<Map<string, IPriceLine>>(new Map());

  // Clear all existing price lines
  const clearPriceLines = useCallback(() => {
    if (!series) return;

    for (const [, line] of priceLinesRef.current) {
      try {
        series.removePriceLine(line);
      } catch {
        // Line may already be removed
      }
    }
    priceLinesRef.current.clear();
  }, [series]);

  // Create price lines for a single leg
  const createLegLines = useCallback((
    leg: ActiveLeg,
  ): Map<string, IPriceLine> => {
    if (!series) return new Map();

    const lines = new Map<string, IPriceLine>();
    const style = LEG_STATUS_STYLES[leg.status];
    const lineStyle = getLineStyle(leg.status);
    const color = getColorWithOpacity(
      style.color[leg.direction],
      style.opacity
    );

    // Create pivot price line
    try {
      const pivotLine = series.createPriceLine({
        price: leg.pivot_price,
        color,
        lineWidth: 2,
        lineStyle,
        axisLabelVisible: true,
        title: `${leg.direction === 'bull' ? '▲' : '▼'} Pivot`,
      });
      lines.set(`${leg.leg_id}-pivot`, pivotLine);
    } catch {
      // Handle any errors creating lines
    }

    // Create origin price line
    try {
      const originLine = series.createPriceLine({
        price: leg.origin_price,
        color,
        lineWidth: 1,
        lineStyle,
        axisLabelVisible: false,
        title: `Origin`,
      });
      lines.set(`${leg.leg_id}-origin`, originLine);
    } catch {
      // Handle any errors creating lines
    }

    return lines;
  }, [series]);

  // Update price lines when legs change
  useEffect(() => {
    if (!series) return;

    // Clear existing lines
    clearPriceLines();

    // Filter legs to only show those visible up to current position
    // and exclude invalidated legs after a brief display
    const visibleLegs = legs.filter(leg => {
      // Skip invalidated legs (they should be removed after brief display)
      if (leg.status === 'invalidated') {
        return false;
      }
      // Only show legs where pivot is before current position
      return leg.pivot_index <= currentPosition;
    });

    // Create lines for each visible leg
    for (const leg of visibleLegs) {
      const newLines = createLegLines(leg);
      for (const [key, line] of newLines) {
        priceLinesRef.current.set(key, line);
      }
    }

    // Cleanup on unmount
    return () => {
      clearPriceLines();
    };
  }, [series, legs, currentPosition, clearPriceLines, createLegLines]);

  // This component doesn't render any DOM elements
  // It only manages price lines on the chart via side effects
  return null;
};
