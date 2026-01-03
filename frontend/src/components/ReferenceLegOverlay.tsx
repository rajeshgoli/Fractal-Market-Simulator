import React, { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import type { IChartApi, ISeriesApi, Time, LineData, LineWidth } from 'lightweight-charts';
import { LineSeries, LineStyle } from 'lightweight-charts';
import { ReferenceSwing, FilteredLeg, FilterReason } from '../lib/api';
import { BarData } from '../types';
import { getBinHexColors, getBinLineWidth, formatMedianMultiple } from '../utils/binUtils';

interface ReferenceLegOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  references: ReferenceSwing[];
  fadingRefs: Set<string>;
  bars: BarData[];
  // All bars (unfiltered) for timestamp lookup - needed when visible bars
  // don't cover historical reference origins
  allBars?: BarData[];
  // Current playback position - filter legs to only show those formed up to this position
  currentPosition: number;
  // Phase 2: Sticky leg support
  stickyLegIds?: Set<string>;
  onLegClick?: (legId: string) => void;
  // Double-click to attach leg to feedback observation
  onLegDoubleClick?: (ref: ReferenceSwing) => void;
  // Reference Observation mode (Issue #400)
  filteredLegs?: FilteredLeg[];
  showFiltered?: boolean;
  // Bidirectional sidebar linking (Issue #430)
  externalHoveredLegId?: string | null;
  onLegHover?: (legId: string | null) => void;
}

// Bin to line width mapping - uses shared utility
const getBinLineWidthForChart = (bin: number): LineWidth => getBinLineWidth(bin) as LineWidth;

// Bin badge colors - uses shared utility with white text for SVG
const getBinBadgeColors = (bin: number): { bg: string; text: string } => {
  const colors = getBinHexColors(bin);
  return { bg: colors.bg, text: '#ffffff' };
};

// Fib ratios for level display
const FIB_RATIOS = [0, 0.382, 0.5, 0.618, 1, 1.382, 1.5, 1.618, 2];

// Color palette for multiple sticky refs (distinguish sources)
const STICKY_COLORS = [
  '#22c55e', // green
  '#ef4444', // red
  '#3b82f6', // blue
  '#f59e0b', // amber
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#14b8a6', // teal
  '#f97316', // orange
];

// Grid cell size for viewport-based label density limiting (#432)
// Labels are limited to 1 per cell; zooming in spreads legs across more cells
const LABEL_GRID_CELL_SIZE = 150; // pixels

// Filter reason badge colors (Issue #400, #457)
const FILTER_REASON_COLORS: Record<FilterReason, { bg: string; text: string; label: string }> = {
  'valid': { bg: '#22c55e', text: '#ffffff', label: 'Valid' },
  'not_formed': { bg: '#eab308', text: '#000000', label: 'Not Formed' },
  'pivot_breached': { bg: '#ef4444', text: '#ffffff', label: 'Pivot' },
  'origin_breached': { bg: '#f97316', text: '#ffffff', label: 'Origin' },
  'completed': { bg: '#3b82f6', text: '#ffffff', label: 'Complete' },
  'cold_start': { bg: '#6b7280', text: '#ffffff', label: 'Cold' },
  'active_not_salient': { bg: '#8b5cf6', text: '#ffffff', label: 'On Deck' },
};

/**
 * ReferenceLegOverlay renders reference legs using lightweight-charts LineSeries.
 *
 * Phase 2 features:
 * - Hover on leg shows 9 fib levels as horizontal lines
 * - Click on leg makes levels sticky (persist after mouse leave)
 * - Multiple sticky legs show color-coded levels
 */
export const ReferenceLegOverlay: React.FC<ReferenceLegOverlayProps> = ({
  chart,
  series,
  references,
  fadingRefs,
  bars,
  allBars,
  currentPosition,
  stickyLegIds = new Set(),
  onLegClick,
  onLegDoubleClick,
  filteredLegs = [],
  showFiltered = false,
  // Bidirectional sidebar linking (Issue #430)
  externalHoveredLegId = null,
  onLegHover,
}) => {
  // Use allBars for timestamp lookups if provided, otherwise fall back to bars
  const barsForTimestampLookup = allBars ?? bars;

  // Filter references to only show legs formed up to current playback position
  // This prevents "future" legs from rendering before their candles exist
  const visibleReferences = useMemo(() => {
    return references.filter(ref => ref.pivot_index <= currentPosition);
  }, [references, currentPosition]);

  // Also filter filteredLegs by currentPosition
  const visibleFilteredLegs = useMemo(() => {
    return filteredLegs.filter(leg => leg.pivot_index <= currentPosition);
  }, [filteredLegs, currentPosition]);
  // Track created line series so we can remove them on update
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lineSeriesRef = useRef<Map<string, ISeriesApi<any>>>(new Map());
  // Fib level series (separate from leg lines)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fibSeriesRef = useRef<Map<string, ISeriesApi<any>>>(new Map());

  // Label positions state (for rendering scale/location badges)
  const [labelPositions, setLabelPositions] = useState<Map<string, { x: number; y: number; ref: ReferenceSwing }>>(new Map());
  // Leg line positions for hit testing (origin to pivot)
  const [legLinePositions, setLegLinePositions] = useState<Map<string, {
    originX: number; originY: number;
    pivotX: number; pivotY: number;
    ref: ReferenceSwing
  }>>(new Map());
  // Filtered leg label positions (Issue #400)
  const [filteredLabelPositions, setFilteredLabelPositions] = useState<Map<string, { x: number; y: number; leg: FilteredLeg }>>(new Map());
  // Filtered leg line positions for hit testing
  const [filteredLinePositions, setFilteredLinePositions] = useState<Map<string, {
    originX: number; originY: number;
    pivotX: number; pivotY: number;
    leg: FilteredLeg
  }>>(new Map());
  // Hovered filtered leg
  const [hoveredFilteredLegId, setHoveredFilteredLegId] = useState<string | null>(null);

  // Internal hover state (from chart interaction)
  const [internalHoveredLegId, setInternalHoveredLegId] = useState<string | null>(null);

  // Effective hover state: combine internal (chart) and external (sidebar) hover
  const hoveredLegId = useMemo(() => {
    return internalHoveredLegId || externalHoveredLegId;
  }, [internalHoveredLegId, externalHoveredLegId]);

  // Assign colors to sticky legs
  const stickyColorMap = useMemo(() => {
    const map = new Map<string, string>();
    let colorIndex = 0;
    stickyLegIds.forEach(legId => {
      map.set(legId, STICKY_COLORS[colorIndex % STICKY_COLORS.length]);
      colorIndex++;
    });
    return map;
  }, [stickyLegIds]);

  // Find bar timestamp by source index - uses allBars if provided for historical lookup
  const getTimestampForIndex = useCallback((barIndex: number): number | null => {
    for (const bar of barsForTimestampLookup) {
      if (bar.source_start_index !== undefined && bar.source_end_index !== undefined) {
        if (barIndex >= bar.source_start_index && barIndex <= bar.source_end_index) {
          return bar.timestamp;
        }
      }
    }
    return null;
  }, [barsForTimestampLookup]);

  // Get chart visible time range for fib lines
  const getVisibleTimeRange = useCallback((): { from: number; to: number } | null => {
    if (!chart || bars.length === 0) return null;
    const visibleRange = chart.timeScale().getVisibleLogicalRange();
    if (!visibleRange) return null;

    const startIdx = Math.max(0, Math.floor(visibleRange.from));
    const endIdx = Math.min(bars.length - 1, Math.ceil(visibleRange.to));

    const fromTime = bars[startIdx]?.timestamp;
    const toTime = bars[endIdx]?.timestamp;

    return fromTime && toTime ? { from: fromTime, to: toTime } : null;
  }, [chart, bars]);

  // Clear all existing line series
  const clearLineSeries = useCallback(() => {
    if (!chart) return;

    // Check if chart is still valid (has DOM element) before removing series
    // This prevents errors when chart is being destroyed during view changes
    const chartElement = chart.chartElement?.();
    if (!chartElement || !chartElement.isConnected) {
      lineSeriesRef.current.clear();
      return;
    }

    for (const [, lineSeries] of lineSeriesRef.current) {
      try {
        chart.removeSeries(lineSeries);
      } catch {
        // Series may already be removed
      }
    }
    lineSeriesRef.current.clear();
  }, [chart]);

  // Clear all fib level series
  const clearFibSeries = useCallback(() => {
    if (!chart) return;

    // Check if chart is still valid (has DOM element) before removing series
    const chartElement = chart.chartElement?.();
    if (!chartElement || !chartElement.isConnected) {
      fibSeriesRef.current.clear();
      return;
    }

    for (const [, fibSeries] of fibSeriesRef.current) {
      try {
        chart.removeSeries(fibSeries);
      } catch {
        // Series may already be removed
      }
    }
    fibSeriesRef.current.clear();
  }, [chart]);

  // Compute fib levels for a reference
  const computeFibLevels = useCallback((ref: ReferenceSwing): { ratio: number; price: number }[] => {
    const pivot = ref.pivot_price;
    const origin = ref.origin_price;

    // For bull reference (bear leg): pivot is LOW, origin is HIGH
    // For bear reference (bull leg): pivot is HIGH, origin is LOW
    // Fib levels: 0 = pivot, 1 = origin, 2 = target

    return FIB_RATIOS.map(ratio => {
      // Location 0 = pivot, 1 = origin
      // price = pivot + ratio * (origin - pivot)
      const price = pivot + ratio * (origin - pivot);
      return { ratio, price };
    });
  }, []);

  // Create fib level lines for a reference
  const createFibLines = useCallback((
    ref: ReferenceSwing,
    color: string,
    opacity: number = 0.6
  ): void => {
    if (!chart || !series) return;

    const timeRange = getVisibleTimeRange();
    if (!timeRange) return;

    const fibLevels = computeFibLevels(ref);

    fibLevels.forEach(({ ratio, price }) => {
      const key = `${ref.leg_id}_fib_${ratio}`;
      if (fibSeriesRef.current.has(key)) return;

      try {
        const fibSeries = chart.addSeries(LineSeries, {
          color,
          lineWidth: 1 as LineWidth,
          lineStyle: LineStyle.Dashed,
          crosshairMarkerVisible: false,
          priceLineVisible: false,
          lastValueVisible: false,
          // Prevent fib lines from affecting chart auto-scale (#411)
          autoscaleInfoProvider: () => null,
        });

        // Apply opacity
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        fibSeries.applyOptions({
          color: `rgba(${r}, ${g}, ${b}, ${opacity})`,
        });

        // Horizontal line spanning visible range
        const data: LineData<Time>[] = [
          { time: timeRange.from as Time, value: price },
          { time: timeRange.to as Time, value: price },
        ];

        fibSeries.setData(data);
        fibSeriesRef.current.set(key, fibSeries);
      } catch (error) {
        console.error('Failed to create fib line:', error);
      }
    });
  }, [chart, series, getVisibleTimeRange, computeFibLevels]);

  // Create line series for a reference
  const createRefLine = useCallback((
    ref: ReferenceSwing,
    isFading: boolean,
    fadeForFilter: boolean = false,
    fadeForHover: boolean = false,
    isHoveredLeg: boolean = false
  ): ISeriesApi<'Line'> | null => {
    if (!chart || !series) return null;

    // Direction determines color
    // Bull reference (bear leg) = green (price went down, looking to go long)
    // Bear reference (bull leg) = red (price went up, looking to go short)
    const color = ref.direction === 'bear' ? '#22c55e' : '#ef4444';
    const lineWidth = isHoveredLeg ? Math.min(4, getBinLineWidthForChart(ref.bin) + 1) as LineWidth : getBinLineWidthForChart(ref.bin);
    // Opacity priority: filter mode > hover fade > fading refs > normal
    // When hovering, fade non-hovered legs heavily, highlight hovered leg
    const opacity = fadeForFilter ? 0.08
      : fadeForHover ? 0.15
      : isHoveredLeg ? 1.0
      : isFading ? 0.3
      : 0.8;

    // Get timestamps for origin and pivot
    const originTime = getTimestampForIndex(ref.origin_index);
    const pivotTime = getTimestampForIndex(ref.pivot_index);

    if (originTime === null || pivotTime === null) {
      return null;
    }

    try {
      // Create line series for this reference
      const lineSeries = chart.addSeries(LineSeries, {
        color,
        lineWidth,
        lineStyle: LineStyle.Solid,
        crosshairMarkerVisible: false,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // Apply opacity via color
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      lineSeries.applyOptions({
        color: `rgba(${r}, ${g}, ${b}, ${opacity})`,
      });

      // Set data: line from origin to pivot
      const data: LineData<Time>[] = [
        { time: originTime as Time, value: ref.origin_price },
        { time: pivotTime as Time, value: ref.pivot_price },
      ];

      // Sort by time (required by lightweight-charts)
      data.sort((a, b) => (a.time as number) - (b.time as number));

      lineSeries.setData(data);

      return lineSeries;
    } catch (error) {
      console.error('Failed to create reference line:', error);
      return null;
    }
  }, [chart, series, getTimestampForIndex]);

  // Create line series for a filtered leg (highlighted for inspection)
  const createFilteredLegLine = useCallback((leg: FilteredLeg): ISeriesApi<'Line'> | null => {
    if (!chart || !series) return null;

    // Use direction-based color like valid legs, but dashed to indicate filtered
    // Bull reference (bear leg) = green, Bear reference (bull leg) = red
    const color = leg.direction === 'bear' ? '#22c55e' : '#ef4444';
    const lineWidth = getBinLineWidthForChart(leg.bin);
    const opacity = 0.85;

    // Get timestamps for origin and pivot
    const originTime = getTimestampForIndex(leg.origin_index);
    const pivotTime = getTimestampForIndex(leg.pivot_index);

    if (originTime === null || pivotTime === null) {
      return null;
    }

    try {
      // Create dashed line series for filtered leg
      const lineSeries = chart.addSeries(LineSeries, {
        color,
        lineWidth,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // Apply opacity via color
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      lineSeries.applyOptions({
        color: `rgba(${r}, ${g}, ${b}, ${opacity})`,
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
      console.error('Failed to create filtered leg line:', error);
      return null;
    }
  }, [chart, series, getTimestampForIndex]);

  // Update label positions and leg line positions when visible range changes
  const updateLabelPositions = useCallback(() => {
    if (!chart || !series || bars.length === 0) {
      setLabelPositions(new Map());
      setLegLinePositions(new Map());
      return;
    }

    // First pass: collect all candidate labels and line positions
    const candidateLabels: Array<{ x: number; y: number; ref: ReferenceSwing }> = [];
    const linePos = new Map<string, {
      originX: number; originY: number;
      pivotX: number; pivotY: number;
      ref: ReferenceSwing
    }>();

    for (const ref of visibleReferences) {
      if (fadingRefs.has(ref.leg_id)) continue;

      const originTime = getTimestampForIndex(ref.origin_index);
      const pivotTime = getTimestampForIndex(ref.pivot_index);
      if (originTime === null || pivotTime === null) continue;

      const originX = chart.timeScale().timeToCoordinate(originTime as Time);
      const originY = series.priceToCoordinate(ref.origin_price);
      const pivotX = chart.timeScale().timeToCoordinate(pivotTime as Time);
      const pivotY = series.priceToCoordinate(ref.pivot_price);

      if (originX !== null && originY !== null && pivotX !== null && pivotY !== null) {
        // Position label at midpoint of leg body for clear ownership (#432)
        const midX = (originX + pivotX) / 2;
        const midY = (originY + pivotY) / 2;
        candidateLabels.push({ x: midX, y: midY, ref });
        linePos.set(ref.leg_id, { originX, originY, pivotX, pivotY, ref });
      }
    }

    // Second pass: grid-based density limiting (#432)
    // Group labels by grid cell, keep only the most prominent (highest median_multiple) per cell
    const gridCells = new Map<string, { x: number; y: number; ref: ReferenceSwing }>();
    for (const label of candidateLabels) {
      const cellX = Math.floor(label.x / LABEL_GRID_CELL_SIZE);
      const cellY = Math.floor(label.y / LABEL_GRID_CELL_SIZE);
      const cellKey = `${cellX},${cellY}`;

      const existing = gridCells.get(cellKey);
      if (!existing || label.ref.median_multiple > existing.ref.median_multiple) {
        gridCells.set(cellKey, label);
      }
    }

    // Build final label positions from surviving labels
    const labelPos = new Map<string, { x: number; y: number; ref: ReferenceSwing }>();
    for (const label of gridCells.values()) {
      labelPos.set(label.ref.leg_id, label);
    }

    setLabelPositions(labelPos);
    setLegLinePositions(linePos);
  }, [chart, series, visibleReferences, fadingRefs, bars, getTimestampForIndex]);

  // Update filtered label positions (Issue #400)
  const updateFilteredLabelPositions = useCallback(() => {
    if (!chart || !series || bars.length === 0 || !showFiltered) {
      setFilteredLabelPositions(new Map());
      setFilteredLinePositions(new Map());
      return;
    }

    // First pass: collect all candidate labels and line positions
    const candidateLabels: Array<{ x: number; y: number; leg: FilteredLeg }> = [];
    const linePositions = new Map<string, {
      originX: number; originY: number;
      pivotX: number; pivotY: number;
      leg: FilteredLeg
    }>();

    for (const leg of visibleFilteredLegs) {
      const originTime = getTimestampForIndex(leg.origin_index);
      const pivotTime = getTimestampForIndex(leg.pivot_index);
      if (originTime === null || pivotTime === null) continue;

      const originX = chart.timeScale().timeToCoordinate(originTime as Time);
      const originY = series.priceToCoordinate(leg.origin_price);
      const pivotX = chart.timeScale().timeToCoordinate(pivotTime as Time);
      const pivotY = series.priceToCoordinate(leg.pivot_price);

      if (originX !== null && originY !== null && pivotX !== null && pivotY !== null) {
        // Position label at midpoint of leg body for clear ownership (#432)
        const midX = (originX + pivotX) / 2;
        const midY = (originY + pivotY) / 2;
        candidateLabels.push({ x: midX, y: midY, leg });
        linePositions.set(leg.leg_id, { originX, originY, pivotX, pivotY, leg });
      }
    }

    // Second pass: grid-based density limiting (#432)
    // Group labels by grid cell, keep only the most prominent (highest median_multiple) per cell
    const gridCells = new Map<string, { x: number; y: number; leg: FilteredLeg }>();
    for (const label of candidateLabels) {
      const cellX = Math.floor(label.x / LABEL_GRID_CELL_SIZE);
      const cellY = Math.floor(label.y / LABEL_GRID_CELL_SIZE);
      const cellKey = `${cellX},${cellY}`;

      const existing = gridCells.get(cellKey);
      if (!existing || label.leg.median_multiple > existing.leg.median_multiple) {
        gridCells.set(cellKey, label);
      }
    }

    // Build final label positions from surviving labels
    const labelPositions = new Map<string, { x: number; y: number; leg: FilteredLeg }>();
    for (const label of gridCells.values()) {
      labelPositions.set(label.leg.leg_id, label);
    }

    setFilteredLabelPositions(labelPositions);
    setFilteredLinePositions(linePositions);
  }, [chart, series, visibleFilteredLegs, bars, showFiltered, getTimestampForIndex]);

  // Update fib levels for hovered and sticky legs
  const updateFibLevels = useCallback(() => {
    if (!chart || !series) return;

    // Clear existing fib series
    clearFibSeries();

    // Get refs to show fib levels for
    const refsToShow = visibleReferences.filter(ref =>
      ref.leg_id === hoveredLegId || stickyLegIds.has(ref.leg_id)
    );

    // Create fib lines for each
    refsToShow.forEach(ref => {
      const isSticky = stickyLegIds.has(ref.leg_id);
      const color = isSticky
        ? (stickyColorMap.get(ref.leg_id) || (ref.direction === 'bear' ? '#22c55e' : '#ef4444'))
        : (ref.direction === 'bear' ? '#22c55e' : '#ef4444');
      const opacity = isSticky ? 0.7 : 0.5;

      createFibLines(ref, color, opacity);
    });
  }, [chart, series, visibleReferences, hoveredLegId, stickyLegIds, stickyColorMap, clearFibSeries, createFibLines]);

  // Update line series when references, bars, or hover state changes
  useEffect(() => {
    if (!chart || !series || bars.length === 0) {
      clearLineSeries();
      clearFibSeries();
      return;
    }

    try {
      // Clear existing lines
      clearLineSeries();

      // Create line series for each reference
      // When showFiltered is on, fade valid legs so filtered legs stand out
      // When a leg is hovered (from sidebar or chart), fade other legs and highlight hovered
      const hasHoveredLeg = hoveredLegId !== null;
      for (const ref of visibleReferences) {
        const isFading = fadingRefs.has(ref.leg_id);
        const isHoveredLeg = ref.leg_id === hoveredLegId;
        const fadeForHover = hasHoveredLeg && !isHoveredLeg;
        const lineSeries = createRefLine(ref, isFading, showFiltered, fadeForHover, isHoveredLeg);
        if (lineSeries) {
          lineSeriesRef.current.set(ref.leg_id, lineSeries);
        }
      }

      // Create line series for filtered legs when showFiltered is true (Issue #400)
      if (showFiltered) {
        for (const leg of visibleFilteredLegs) {
          const lineSeries = createFilteredLegLine(leg);
          if (lineSeries) {
            lineSeriesRef.current.set(`filtered_${leg.leg_id}`, lineSeries);
          }
        }
      }

      // Update label positions
      updateLabelPositions();
      updateFilteredLabelPositions();

      // Update fib levels
      updateFibLevels();
    } catch (e) {
      console.warn('ReferenceLegOverlay update failed:', e);
    }

    return () => {
      try {
        clearLineSeries();
        clearFibSeries();
      } catch {
        // Ignore disposal errors during cleanup
      }
    };
  }, [chart, series, visibleReferences, fadingRefs, bars, clearLineSeries, clearFibSeries, createRefLine, updateLabelPositions, updateFibLevels, showFiltered, visibleFilteredLegs, createFilteredLegLine, updateFilteredLabelPositions, hoveredLegId]);

  // Update fib levels when hover or sticky state changes
  // Note: Don't include updateFibLevels in deps - it causes infinite loop since
  // it's recreated when stickyLegIds/hoveredLegId change. We only need to trigger
  // on actual data changes.
  useEffect(() => {
    updateFibLevels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredLegId, stickyLegIds]);

  // Subscribe to visible range changes to update label positions and fib levels
  useEffect(() => {
    if (!chart) return;

    const handleRangeChange = () => {
      updateLabelPositions();
      updateFilteredLabelPositions();
      updateFibLevels();
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(handleRangeChange);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleRangeChange);
    };
  }, [chart, updateLabelPositions, updateFilteredLabelPositions, updateFibLevels]);

  // Handle mouse enter on label (Issue #430: bidirectional linking)
  const handleLabelMouseEnter = useCallback((legId: string) => {
    setInternalHoveredLegId(legId);
    if (onLegHover) {
      onLegHover(legId);
    }
  }, [onLegHover]);

  // Handle mouse leave on label (Issue #430: bidirectional linking)
  const handleLabelMouseLeave = useCallback(() => {
    setInternalHoveredLegId(null);
    if (onLegHover) {
      onLegHover(null);
    }
  }, [onLegHover]);

  // Handle click on label (toggle sticky/pinned)
  const handleLabelClick = useCallback((legId: string) => {
    if (onLegClick) {
      onLegClick(legId);
    }
  }, [onLegClick]);

  // Handle double-click on label (attach to feedback observation)
  const handleLabelDoubleClick = useCallback((legId: string) => {
    if (onLegDoubleClick) {
      const ref = visibleReferences.find(r => r.leg_id === legId);
      if (ref) {
        onLegDoubleClick(ref);
      }
    }
  }, [onLegDoubleClick, visibleReferences]);

  // Handle filtered leg hover
  const handleFilteredLegMouseEnter = useCallback((legId: string) => {
    setHoveredFilteredLegId(legId);
  }, []);

  const handleFilteredLegMouseLeave = useCallback(() => {
    setHoveredFilteredLegId(null);
  }, []);

  // Get chart container for label positioning
  const chartContainer = chart?.chartElement()?.closest('.chart-container');
  if (!chartContainer || (labelPositions.size === 0 && legLinePositions.size === 0 && filteredLabelPositions.size === 0 && filteredLinePositions.size === 0)) {
    return null;
  }

  // Render labels as SVG overlay (only labels, not lines)
  return (
    <svg
      className="absolute inset-0"
      style={{ width: '100%', height: '100%', zIndex: 100, pointerEvents: 'none' }}
    >
      {/* Invisible hit-test lines for leg interaction (#411) - disabled when showFiltered is on */}
      {!showFiltered && Array.from(legLinePositions.entries()).map(([legId, { originX, originY, pivotX, pivotY }]) => {
        const isHovered = hoveredLegId === legId;
        const isSticky = stickyLegIds.has(legId);
        return (
          <line
            key={`hitline_${legId}`}
            x1={originX}
            y1={originY}
            x2={pivotX}
            y2={pivotY}
            stroke={isHovered || isSticky ? 'rgba(255,255,255,0.15)' : 'transparent'}
            strokeWidth={12}
            style={{ pointerEvents: 'all', cursor: 'pointer' }}
            onMouseEnter={() => handleLabelMouseEnter(legId)}
            onMouseLeave={handleLabelMouseLeave}
            onClick={() => handleLabelClick(legId)}
            onDoubleClick={() => handleLabelDoubleClick(legId)}
          />
        );
      })}

      {/* Hit-test lines for filtered legs (interactive when showFiltered is on) */}
      {showFiltered && Array.from(filteredLinePositions.entries()).map(([legId, { originX, originY, pivotX, pivotY, leg }]) => {
        const isHovered = hoveredFilteredLegId === legId;
        const color = leg.direction === 'bear' ? '#22c55e' : '#ef4444';
        return (
          <g key={`filtered_hitline_${legId}`}>
            {/* Visible highlight line when hovered */}
            {isHovered && (
              <line
                x1={originX}
                y1={originY}
                x2={pivotX}
                y2={pivotY}
                stroke={color}
                strokeWidth={4}
                strokeOpacity={0.6}
                style={{ pointerEvents: 'none' }}
              />
            )}
            {/* Invisible hit-test line */}
            <line
              x1={originX}
              y1={originY}
              x2={pivotX}
              y2={pivotY}
              stroke="transparent"
              strokeWidth={12}
              style={{ pointerEvents: 'all', cursor: 'pointer' }}
              onMouseEnter={() => handleFilteredLegMouseEnter(legId)}
              onMouseLeave={handleFilteredLegMouseLeave}
            />
          </g>
        );
      })}

      {/* Median multiple/location badges (display only, no pointer events) - hidden when showFiltered is on */}
      {!showFiltered && Array.from(labelPositions.entries()).map(([legId, { x, y, ref }]) => {
        const binBadge = getBinBadgeColors(ref.bin);
        const color = ref.direction === 'bear' ? '#22c55e' : '#ef4444';
        const isSticky = stickyLegIds.has(legId);
        const isHovered = hoveredLegId === legId;
        const medianLabel = formatMedianMultiple(ref.median_multiple);
        // Fade labels when another leg is hovered
        const hasHoveredLeg = hoveredLegId !== null;
        const fadeForHover = hasHoveredLeg && !isHovered;
        const labelOpacity = fadeForHover ? 0.2 : 1.0;

        return (
          <g
            key={legId}
            transform={`translate(${x + 8}, ${y})`}
            opacity={labelOpacity}
          >
            {/* Median multiple badge */}
            <rect
              x={0}
              y={-10}
              width={32}
              height={16}
              rx={3}
              fill={binBadge.bg}
              stroke={isSticky ? '#fbbf24' : (isHovered ? '#ffffff' : 'none')}
              strokeWidth={isSticky ? 2 : 1}
            />
            <text
              x={16}
              y={2}
              textAnchor="middle"
              fill={binBadge.text}
              fontSize={9}
              fontWeight="600"
              fontFamily="system-ui, sans-serif"
            >
              {medianLabel}
            </text>

            {/* Location indicator */}
            <rect
              x={36}
              y={-10}
              width={32}
              height={16}
              rx={3}
              fill="rgba(30, 41, 59, 0.9)"
              stroke={isSticky ? '#fbbf24' : color}
              strokeWidth={isSticky ? 2 : 1}
            />
            <text
              x={52}
              y={2}
              textAnchor="middle"
              fill={color}
              fontSize={9}
              fontWeight="500"
              fontFamily="system-ui, sans-serif"
            >
              {(ref.location ?? 0).toFixed(2)}
            </text>

            {/* Sticky indicator */}
            {isSticky && (
              <circle
                cx={74}
                cy={-2}
                r={4}
                fill="#fbbf24"
              />
            )}
          </g>
        );
      })}

      {/* Fib level labels - hidden when showFiltered is on */}
      {!showFiltered && (hoveredLegId || stickyLegIds.size > 0) && (() => {
        const refsToLabel = visibleReferences.filter(ref =>
          ref.leg_id === hoveredLegId || stickyLegIds.has(ref.leg_id)
        );

        return refsToLabel.flatMap(ref => {
          const fibLevels = computeFibLevels(ref);
          const isSticky = stickyLegIds.has(ref.leg_id);
          const color = isSticky
            ? (stickyColorMap.get(ref.leg_id) || (ref.direction === 'bear' ? '#22c55e' : '#ef4444'))
            : (ref.direction === 'bear' ? '#22c55e' : '#ef4444');

          return fibLevels.map(({ ratio, price }) => {
            const priceCoord = series?.priceToCoordinate(price);
            if (priceCoord === null || priceCoord === undefined) return null;

            return (
              <g key={`${ref.leg_id}_label_${ratio}`} transform={`translate(5, ${priceCoord})`}>
                <rect
                  x={0}
                  y={-8}
                  width={36}
                  height={16}
                  rx={2}
                  fill="rgba(30, 41, 59, 0.85)"
                  stroke={color}
                  strokeWidth={0.5}
                />
                <text
                  x={18}
                  y={4}
                  textAnchor="middle"
                  fill={color}
                  fontSize={9}
                  fontWeight="500"
                  fontFamily="system-ui, sans-serif"
                >
                  {(ratio ?? 0).toFixed(ratio === 0 || ratio === 1 || ratio === 2 ? 0 : 3)}
                </text>
              </g>
            );
          });
        });
      })()}

      {/* Filtered leg badges (Issue #400) */}
      {showFiltered && Array.from(filteredLabelPositions.entries()).map(([legId, { x, y, leg }]) => {
        const filterBadge = FILTER_REASON_COLORS[leg.filter_reason] || FILTER_REASON_COLORS['cold_start'];
        const isHovered = hoveredFilteredLegId === legId;
        const directionColor = leg.direction === 'bear' ? '#22c55e' : '#ef4444';
        const medianLabel = formatMedianMultiple(leg.median_multiple);

        return (
          <g
            key={`filtered_${legId}`}
            transform={`translate(${x + 8}, ${y})`}
            style={{ pointerEvents: 'all', cursor: 'pointer' }}
            onMouseEnter={() => handleFilteredLegMouseEnter(legId)}
            onMouseLeave={handleFilteredLegMouseLeave}
          >
            {/* Filter reason badge */}
            <rect
              x={0}
              y={-10}
              width={48}
              height={16}
              rx={3}
              fill={filterBadge.bg}
              stroke={isHovered ? '#ffffff' : 'none'}
              strokeWidth={isHovered ? 1.5 : 0}
            />
            <text
              x={24}
              y={2}
              textAnchor="middle"
              fill={filterBadge.text}
              fontSize={9}
              fontWeight="500"
              fontFamily="system-ui, sans-serif"
            >
              {filterBadge.label}
            </text>

            {/* Median multiple badge (smaller, to the right) */}
            <rect
              x={52}
              y={-10}
              width={28}
              height={16}
              rx={3}
              fill={isHovered ? 'rgba(75, 85, 99, 0.9)' : 'rgba(75, 85, 99, 0.6)'}
              stroke={isHovered ? directionColor : 'none'}
              strokeWidth={isHovered ? 1 : 0}
            />
            <text
              x={66}
              y={2}
              textAnchor="middle"
              fill={isHovered ? directionColor : '#9ca3af'}
              fontSize={9}
              fontWeight="500"
              fontFamily="system-ui, sans-serif"
            >
              {medianLabel}
            </text>

            {/* Location indicator (only on hover) */}
            {isHovered && (
              <>
                <rect
                  x={84}
                  y={-10}
                  width={32}
                  height={16}
                  rx={3}
                  fill="rgba(30, 41, 59, 0.9)"
                  stroke={directionColor}
                  strokeWidth={1}
                />
                <text
                  x={100}
                  y={2}
                  textAnchor="middle"
                  fill={directionColor}
                  fontSize={9}
                  fontWeight="500"
                  fontFamily="system-ui, sans-serif"
                >
                  {(leg.location ?? 0).toFixed(2)}
                </text>
              </>
            )}
          </g>
        );
      })}

    </svg>
  );
};
