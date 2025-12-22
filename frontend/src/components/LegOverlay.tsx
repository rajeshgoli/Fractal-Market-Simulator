import { useEffect, useRef, useCallback, useState } from 'react';
import { IChartApi, ISeriesApi, LineStyle, Time, LineData, LineSeries, LineWidth } from 'lightweight-charts';
import { ActiveLeg, BarData, LEG_STATUS_STYLES } from '../types';

interface LegOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  legs: ActiveLeg[];
  bars: BarData[];
  currentPosition: number;
  highlightedLegId?: string;
  onLegHover?: (legId: string | null) => void;
  onLegClick?: (legId: string) => void;
  onLegDoubleClick?: (legId: string) => void;
  // Hierarchy mode props (#250)
  hierarchyMode?: {
    isActive: boolean;
    highlightedLegIds: Set<string>;
    focusedLegId: string | null;
  };
  onTreeIconClick?: (legId: string) => void;
  // Eye icon for follow (#267)
  onEyeIconClick?: (legId: string) => void;
  // Follow colors (#267) - Map from leg_id to hex color
  followedLegColors?: Map<string, string>;
}

/**
 * Calculate the distance from a point to a line segment.
 * Returns the perpendicular distance if the projection falls on the segment,
 * otherwise returns the distance to the nearest endpoint.
 */
function distanceToLineSegment(
  px: number, py: number,  // point
  x1: number, y1: number,  // segment start
  x2: number, y2: number   // segment end
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSq = dx * dx + dy * dy;

  if (lengthSq === 0) {
    // Segment is a point
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }

  // Project point onto line, clamped to segment
  let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
  t = Math.max(0, Math.min(1, t));

  const projX = x1 + t * dx;
  const projY = y1 + t * dy;

  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
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
 * LegOverlay renders legs as diagonal lines connecting origin to pivot.
 *
 * For each leg, it draws:
 * - A line from (origin_index, origin_price) to (pivot_index, pivot_price)
 *
 * Visual treatment (#203):
 * - Active legs: Solid lines, green (bull) / red (bear), 70% opacity
 * - Stale legs: Dashed lines, yellow, 50% opacity
 * - Invalidated legs: Dotted lines, same direction colors, 50% opacity (shown until 3× extension prune)
 */
export const LegOverlay: React.FC<LegOverlayProps> = ({
  chart,
  series,
  legs,
  bars,
  currentPosition,
  highlightedLegId,
  onLegHover,
  onLegClick,
  onLegDoubleClick,
  hierarchyMode,
  onTreeIconClick,
  onEyeIconClick,
  followedLegColors,
}) => {
  // Track created line series so we can remove them on update
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lineSeriesRef = useRef<Map<string, ISeriesApi<any>>>(new Map());

  // Track last click time for double-click detection
  const lastClickTimeRef = useRef<number>(0);
  const lastClickLegRef = useRef<string | null>(null);

  // Track current hovered leg to avoid redundant callbacks
  const currentHoveredLegRef = useRef<string | null>(null);

  // Tree icon state - shown on click (#252)
  const [treeIconLegId, setTreeIconLegId] = useState<string | null>(null);
  const [treeIconPosition, setTreeIconPosition] = useState<{ x: number; y: number } | null>(null);

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
  const createLegLine = useCallback((leg: ActiveLeg, isHighlighted: boolean): ISeriesApi<any> | null => {
    if (!chart || !series) return null;

    const style = LEG_STATUS_STYLES[leg.status];

    // Determine opacity and line style based on hierarchy mode (#253)
    let opacity: number;
    let lineWidth: LineWidth;
    let lineStyle: LineStyle;

    if (hierarchyMode?.isActive) {
      const isInHierarchy = hierarchyMode.highlightedLegIds.has(leg.leg_id);
      const isFocused = hierarchyMode.focusedLegId === leg.leg_id;

      if (isFocused) {
        // Focused leg: full opacity, thicker line
        opacity = 1.0;
        lineWidth = 4 as LineWidth;
        lineStyle = LineStyle.Solid;
      } else if (isInHierarchy) {
        // In hierarchy but not focused: slightly less prominent
        opacity = 0.8;
        lineWidth = 3 as LineWidth;
        lineStyle = LineStyle.Solid;
      } else {
        // Not in hierarchy: faded/dimmed
        opacity = 0.15;
        lineWidth = 1 as LineWidth;
        lineStyle = getLineStyleValue(leg.status);
      }
    } else {
      // Normal mode: use default highlighting
      opacity = isHighlighted ? 1.0 : style.opacity;
      lineWidth = (isHighlighted ? 4 : 2) as LineWidth;
      lineStyle = isHighlighted ? LineStyle.Solid : getLineStyleValue(leg.status);
    }

    // Use follow color if leg is followed (#267), otherwise use direction color
    const followColor = followedLegColors?.get(leg.leg_id);
    const baseColor = followColor ?? style.color[leg.direction];
    const color = getColorWithOpacity(baseColor, opacity);

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
        lineWidth,
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
  }, [chart, series, getTimestampForIndex, hierarchyMode, followedLegColors]);

  // Find the nearest visible leg to a given price/time position
  // Returns leg_id if within pick threshold, null otherwise
  const findNearestLeg = useCallback((time: number, price: number): string | null => {
    if (!chart || !series || bars.length === 0) return null;

    // Get visible legs
    const visibleLegs = legs.filter(leg => leg.pivot_index <= currentPosition);
    if (visibleLegs.length === 0) return null;

    // Convert time to logical coordinate for distance calculation
    const timeScale = chart.timeScale();

    // Convert click position to pixel coordinates using series API
    const clickX = timeScale.timeToCoordinate(time as Time);
    const clickY = series.priceToCoordinate(price);

    if (clickX === null || clickY === null) return null;

    // Threshold in pixels for picking a leg (generous for usability)
    const PICK_THRESHOLD_PX = 15;

    let nearestLeg: string | null = null;
    let nearestDistance = Infinity;

    for (const leg of visibleLegs) {
      const originTime = getTimestampForIndex(leg.origin_index);
      const pivotTime = getTimestampForIndex(leg.pivot_index);

      if (originTime === null || pivotTime === null) continue;

      // Convert leg endpoints to pixel coordinates using series API
      const originX = timeScale.timeToCoordinate(originTime as Time);
      const originY = series.priceToCoordinate(leg.origin_price);
      const pivotX = timeScale.timeToCoordinate(pivotTime as Time);
      const pivotY = series.priceToCoordinate(leg.pivot_price);

      if (originX === null || originY === null || pivotX === null || pivotY === null) continue;

      // Calculate distance from click to leg line segment in pixels
      const distance = distanceToLineSegment(
        clickX, clickY,
        originX, originY,
        pivotX, pivotY
      );

      if (distance < nearestDistance && distance <= PICK_THRESHOLD_PX) {
        nearestDistance = distance;
        nearestLeg = leg.leg_id;
      }
    }

    return nearestLeg;
  }, [chart, series, legs, bars, currentPosition, getTimestampForIndex]);

  // Handle hover detection via crosshair move
  useEffect(() => {
    if (!chart || !series) return;

    const handleCrosshairMove = (param: { time?: Time; point?: { x: number; y: number }; seriesData?: Map<unknown, unknown> }) => {
      if (!param.time || !param.point) {
        // Mouse left chart area
        if (currentHoveredLegRef.current !== null) {
          currentHoveredLegRef.current = null;
          onLegHover?.(null);
        }
        return;
      }

      // Get price at cursor position using series API
      const price = series.coordinateToPrice(param.point.y);
      if (price === null) return;

      const hoveredLeg = findNearestLeg(param.time as number, price);

      // Only emit if changed
      if (hoveredLeg !== currentHoveredLegRef.current) {
        currentHoveredLegRef.current = hoveredLeg;
        onLegHover?.(hoveredLeg);
      }
    };

    chart.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
    };
  }, [chart, series, onLegHover, findNearestLeg]);

  // Handle click detection - show tree icon on click (#252)
  useEffect(() => {
    if (!chart || !series) return;

    const chartElement = chart.chartElement();

    const handleClick = (event: MouseEvent) => {
      // Get time and price from click position
      const rect = chartElement.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;

      const timeScale = chart.timeScale();

      const time = timeScale.coordinateToTime(x);
      const price = series.coordinateToPrice(y);

      if (time === null || price === null) {
        // Clicked outside valid area - hide tree icon
        setTreeIconLegId(null);
        setTreeIconPosition(null);
        return;
      }

      const clickedLeg = findNearestLeg(time as number, price);

      if (!clickedLeg) {
        // Clicked but no leg nearby - hide tree icon
        setTreeIconLegId(null);
        setTreeIconPosition(null);
        return;
      }

      const now = Date.now();
      const DOUBLE_CLICK_THRESHOLD = 300; // ms

      // Check for double-click
      if (
        lastClickLegRef.current === clickedLeg &&
        now - lastClickTimeRef.current < DOUBLE_CLICK_THRESHOLD
      ) {
        // Double-click detected
        onLegDoubleClick?.(clickedLeg);
        lastClickTimeRef.current = 0;
        lastClickLegRef.current = null;
        // Hide tree icon on double-click
        setTreeIconLegId(null);
        setTreeIconPosition(null);
      } else {
        // Single click - delay to see if it becomes a double-click
        lastClickTimeRef.current = now;
        lastClickLegRef.current = clickedLeg;

        // Fire single-click after threshold if no second click
        setTimeout(() => {
          if (lastClickLegRef.current === clickedLeg && now === lastClickTimeRef.current) {
            onLegClick?.(clickedLeg);

            // Show tree icon near pivot if not in hierarchy mode (#252)
            if (onTreeIconClick && !hierarchyMode?.isActive) {
              const leg = legs.find(l => l.leg_id === clickedLeg);
              if (leg) {
                const pivotTime = getTimestampForIndex(leg.pivot_index);
                if (pivotTime !== null) {
                  const pivotX = timeScale.timeToCoordinate(pivotTime as Time);
                  const pivotY = series.priceToCoordinate(leg.pivot_price);
                  if (pivotX !== null && pivotY !== null) {
                    setTreeIconLegId(clickedLeg);
                    setTreeIconPosition({ x: pivotX, y: pivotY - 25 }); // Position above pivot
                  }
                }
              }
            }
          }
        }, DOUBLE_CLICK_THRESHOLD);
      }
    };

    chartElement.addEventListener('click', handleClick);

    return () => {
      chartElement.removeEventListener('click', handleClick);
    };
  }, [chart, series, onLegClick, onLegDoubleClick, findNearestLeg, onTreeIconClick, hierarchyMode?.isActive, legs, getTimestampForIndex]);

  // Update line series when legs or bars change
  useEffect(() => {
    if (!chart || !series || bars.length === 0) return;

    // Clear existing lines
    clearLineSeries();

    // Filter legs to only show those visible up to current position
    // (#203: now includes invalidated legs with dotted line style)
    const visibleLegs = legs.filter(leg => {
      // Only show legs where pivot is at or before current position
      return leg.pivot_index <= currentPosition;
    });

    // Create line series for each visible leg
    // Render non-highlighted legs first, then highlighted leg on top
    const sortedLegs = [...visibleLegs].sort((a, b) => {
      const aHighlighted = a.leg_id === highlightedLegId ? 1 : 0;
      const bHighlighted = b.leg_id === highlightedLegId ? 1 : 0;
      return aHighlighted - bHighlighted;
    });

    for (const leg of sortedLegs) {
      const isHighlighted = leg.leg_id === highlightedLegId;
      const lineSeries = createLegLine(leg, isHighlighted);
      if (lineSeries) {
        lineSeriesRef.current.set(leg.leg_id, lineSeries);
      }
    }

    // Cleanup on unmount
    return () => {
      clearLineSeries();
    };
  }, [chart, series, legs, bars, currentPosition, highlightedLegId, hierarchyMode, clearLineSeries, createLegLine]);

  // Handle tree icon click
  const handleTreeIconClick = useCallback(() => {
    if (treeIconLegId && onTreeIconClick) {
      onTreeIconClick(treeIconLegId);
      setTreeIconLegId(null);
      setTreeIconPosition(null);
    }
  }, [treeIconLegId, onTreeIconClick]);

  // Handle eye icon click (#267)
  const handleEyeIconClick = useCallback(() => {
    if (treeIconLegId && onEyeIconClick) {
      onEyeIconClick(treeIconLegId);
      setTreeIconLegId(null);
      setTreeIconPosition(null);
    }
  }, [treeIconLegId, onEyeIconClick]);

  // Check if current leg is followed
  const isCurrentLegFollowed = treeIconLegId ? followedLegColors?.has(treeIconLegId) : false;

  // Get chart container for portal positioning
  const chartContainer = chart?.chartElement()?.parentElement;

  // Render tree and eye icons when visible (#252, #267)
  if (!treeIconLegId || !treeIconPosition || !chartContainer) {
    return null;
  }

  const chartRect = chartContainer.getBoundingClientRect();

  return (
    <div
      style={{
        position: 'fixed',
        left: chartRect.left + treeIconPosition.x - 27, // Adjusted for two icons
        top: chartRect.top + treeIconPosition.y - 12,
        zIndex: 1000,
        pointerEvents: 'auto',
      }}
      className="flex gap-1"
    >
      {/* Tree icon - explore hierarchy */}
      {onTreeIconClick && (
        <button
          onClick={handleTreeIconClick}
          className="w-6 h-6 bg-slate-800 border border-slate-600 rounded-md flex items-center justify-center hover:bg-slate-700 hover:border-blue-400 transition-colors cursor-pointer"
          title="Explore hierarchy"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-blue-400"
          >
            {/* Tree/hierarchy icon */}
            <path d="M12 3v6" />
            <path d="M12 9l-4 4" />
            <path d="M12 9l4 4" />
            <circle cx="12" cy="3" r="2" fill="currentColor" />
            <circle cx="8" cy="15" r="2" fill="currentColor" />
            <circle cx="16" cy="15" r="2" fill="currentColor" />
            <path d="M8 17v2" />
            <path d="M16 17v2" />
            <circle cx="8" cy="21" r="1.5" fill="currentColor" />
            <circle cx="16" cy="21" r="1.5" fill="currentColor" />
          </svg>
        </button>
      )}
      {/* Eye icon - follow leg (#267) */}
      {onEyeIconClick && (
        <button
          onClick={handleEyeIconClick}
          className={`w-6 h-6 border rounded-md flex items-center justify-center transition-colors cursor-pointer ${
            isCurrentLegFollowed
              ? 'bg-green-900 border-green-500 hover:bg-green-800'
              : 'bg-slate-800 border-slate-600 hover:bg-slate-700 hover:border-green-400'
          }`}
          title={isCurrentLegFollowed ? "Unfollow leg" : "Follow leg"}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill={isCurrentLegFollowed ? "currentColor" : "none"}
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={isCurrentLegFollowed ? "text-green-400" : "text-green-400"}
          >
            {/* Eye icon */}
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </button>
      )}
    </div>
  );
};
