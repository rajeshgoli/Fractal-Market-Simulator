/**
 * HierarchyModeOverlay - Overlay for hierarchy exploration mode.
 *
 * Displays when hierarchy mode is active:
 * - Exit button (X) in top-right corner (#255)
 * - Connection lines between parent-child legs (#254)
 * - Status indicator showing current leg and depth
 *
 * Issue #250 - Hierarchy Exploration Mode
 */

import React, { useCallback, useMemo, useEffect, useState } from 'react';
import { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { ActiveLeg, BarData } from '../types';
import { LegLineageResponse } from '../lib/api';

interface HierarchyModeOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  legs: ActiveLeg[];
  bars: BarData[];
  lineage: LegLineageResponse | null;
  focusedLegId: string | null;
  isActive: boolean;
  onExit: () => void;
  onRecenter: (legId: string) => void;
}

interface ConnectionLine {
  parentId: string;
  childId: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export const HierarchyModeOverlay: React.FC<HierarchyModeOverlayProps> = ({
  chart,
  series,
  legs,
  bars,
  lineage,
  focusedLegId,
  isActive,
  onExit,
  onRecenter,
}) => {
  const [connectionLines, setConnectionLines] = useState<ConnectionLine[]>([]);
  const [containerRect, setContainerRect] = useState<DOMRect | null>(null);

  // Build a lookup map for legs
  const legsById = useMemo(() => {
    const map = new Map<string, ActiveLeg>();
    legs.forEach(leg => map.set(leg.leg_id, leg));
    return map;
  }, [legs]);

  // Get timestamp for a bar index
  const getTimestampForIndex = useCallback((barIndex: number): number | null => {
    // Find the bar that contains this source index
    for (const bar of bars) {
      if (barIndex >= bar.source_start_index && barIndex <= bar.source_end_index) {
        return bar.timestamp;
      }
    }
    // If not found, try to find nearest
    if (bars.length > 0) {
      if (barIndex < bars[0].source_start_index) {
        return bars[0].timestamp;
      }
      if (barIndex > bars[bars.length - 1].source_end_index) {
        return bars[bars.length - 1].timestamp;
      }
    }
    return null;
  }, [bars]);

  // Calculate connection lines when lineage or chart changes
  useEffect(() => {
    if (!isActive || !chart || !series || !lineage || bars.length === 0) {
      setConnectionLines([]);
      return;
    }

    const chartContainer = chart.chartElement()?.parentElement;
    if (!chartContainer) {
      setConnectionLines([]);
      return;
    }

    setContainerRect(chartContainer.getBoundingClientRect());

    const timeScale = chart.timeScale();
    const lines: ConnectionLine[] = [];

    // Build parent-child connections
    // For each leg in the hierarchy, find its children
    const hierarchyLegIds = new Set([
      lineage.leg_id,
      ...lineage.ancestors,
      ...lineage.descendants,
    ]);

    for (const legId of hierarchyLegIds) {
      const leg = legsById.get(legId);
      if (!leg || !leg.parent_leg_id) continue;

      const parentLeg = legsById.get(leg.parent_leg_id);
      if (!parentLeg) continue;

      // Both legs must be in the hierarchy
      if (!hierarchyLegIds.has(leg.parent_leg_id)) continue;

      // Get positions for both legs (use pivot points for connection)
      const childPivotTime = getTimestampForIndex(leg.pivot_index);
      const parentPivotTime = getTimestampForIndex(parentLeg.pivot_index);

      if (childPivotTime === null || parentPivotTime === null) continue;

      const childX = timeScale.timeToCoordinate(childPivotTime as Time);
      const childY = series.priceToCoordinate(leg.pivot_price);
      const parentX = timeScale.timeToCoordinate(parentPivotTime as Time);
      const parentY = series.priceToCoordinate(parentLeg.pivot_price);

      if (childX === null || childY === null || parentX === null || parentY === null) continue;

      lines.push({
        parentId: leg.parent_leg_id,
        childId: legId,
        x1: parentX,
        y1: parentY,
        x2: childX,
        y2: childY,
      });
    }

    setConnectionLines(lines);
  }, [isActive, chart, series, lineage, bars, legsById, getTimestampForIndex]);

  // Update lines when chart moves
  useEffect(() => {
    if (!isActive || !chart) return;

    const handleVisibleTimeRangeChange = () => {
      // Trigger recalculation by forcing a state update
      const chartContainer = chart.chartElement()?.parentElement;
      if (chartContainer) {
        setContainerRect(chartContainer.getBoundingClientRect());
      }
    };

    chart.timeScale().subscribeVisibleTimeRangeChange(handleVisibleTimeRangeChange);

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(handleVisibleTimeRangeChange);
    };
  }, [isActive, chart]);

  // Get focused leg details
  const focusedLeg = focusedLegId ? legsById.get(focusedLegId) : null;

  if (!isActive) {
    return null;
  }

  return (
    <>
      {/* Exit button (#255) */}
      <div
        style={{
          position: 'fixed',
          top: containerRect ? containerRect.top + 8 : 80,
          right: containerRect ? window.innerWidth - containerRect.right + 8 : 8,
          zIndex: 1001,
        }}
      >
        <button
          onClick={onExit}
          className="w-8 h-8 bg-slate-800 border border-slate-600 rounded-md flex items-center justify-center hover:bg-red-900/50 hover:border-red-400 transition-colors cursor-pointer shadow-lg"
          title="Exit hierarchy mode (ESC)"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-slate-300"
          >
            <path d="M18 6L6 18" />
            <path d="M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Status indicator */}
      {focusedLeg && lineage && (
        <div
          style={{
            position: 'fixed',
            top: containerRect ? containerRect.top + 8 : 80,
            left: containerRect ? containerRect.left + 8 : 8,
            zIndex: 1001,
          }}
        >
          <div className="bg-slate-800/95 border border-slate-600 rounded-md px-3 py-2 shadow-lg">
            <div className="text-xs text-slate-400 mb-1">Hierarchy Mode</div>
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  focusedLeg.direction === 'bull' ? 'bg-green-400' : 'bg-red-400'
                }`}
              />
              <span className="text-sm font-mono text-slate-200">
                {focusedLeg.leg_id.slice(0, 8)}
              </span>
              <span className="text-xs text-slate-400">
                Depth {lineage.depth}
              </span>
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {lineage.ancestors.length} ancestors, {lineage.descendants.length} descendants
            </div>
          </div>
        </div>
      )}

      {/* Connection lines SVG overlay (#254) */}
      {containerRect && connectionLines.length > 0 && (
        <svg
          style={{
            position: 'fixed',
            top: containerRect.top,
            left: containerRect.left,
            width: containerRect.width,
            height: containerRect.height,
            pointerEvents: 'none',
            zIndex: 999,
          }}
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="6"
              markerHeight="6"
              refX="5"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 6 3, 0 6" fill="#60A5FA" />
            </marker>
          </defs>
          {connectionLines.map((line, idx) => {
            const isFocusedConnection =
              line.parentId === focusedLegId || line.childId === focusedLegId;
            return (
              <line
                key={`${line.parentId}-${line.childId}-${idx}`}
                x1={line.x1}
                y1={line.y1}
                x2={line.x2}
                y2={line.y2}
                stroke={isFocusedConnection ? '#60A5FA' : '#475569'}
                strokeWidth={isFocusedConnection ? 2 : 1}
                strokeDasharray={isFocusedConnection ? 'none' : '4 4'}
                opacity={isFocusedConnection ? 0.8 : 0.4}
                markerEnd={isFocusedConnection ? 'url(#arrowhead)' : undefined}
              />
            );
          })}
        </svg>
      )}
    </>
  );
};
