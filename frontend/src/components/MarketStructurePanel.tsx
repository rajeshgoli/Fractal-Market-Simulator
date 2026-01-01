import React, { useMemo } from 'react';
import { GitBranch, ChevronDown, ChevronRight, Maximize2, Zap } from 'lucide-react';
import { LegEvent, HighlightedDagItem } from '../types';
import { DagLeg } from '../lib/api';
import { calculateLegStats } from '../utils/legStatsUtils';

// DAG context leg for display
export interface DagContextLeg {
  leg_id: string;
  direction: 'bull' | 'bear';
  pivot_price: number;
  pivot_index: number;
  origin_price: number;
  origin_index: number;
  range: number;
}

export interface DagContextPendingOrigin {
  price: number;
  bar_index: number;
}

export interface DagContext {
  activeLegs: DagContextLeg[];
  pendingOrigins: {
    bull: DagContextPendingOrigin | null;
    bear: DagContextPendingOrigin | null;
  };
}

interface MarketStructurePanelProps {
  dagContext: DagContext;
  legEvents: LegEvent[];
  activeLegs: DagLeg[];
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onHoverLeg?: (item: HighlightedDagItem | null) => void;
  highlightedItem?: HighlightedDagItem | null;
}

export const MarketStructurePanel: React.FC<MarketStructurePanelProps> = ({
  dagContext,
  legEvents,
  activeLegs,
  isCollapsed,
  onToggleCollapse,
  onHoverLeg,
  highlightedItem,
}) => {
  // Compute leg statistics from events using shared utility
  const legStats = useMemo(() => calculateLegStats(legEvents, activeLegs), [legEvents, activeLegs]);

  // Top 5 biggest legs (by price range)
  const biggestLegs = useMemo(() => {
    return [...activeLegs]
      .map(leg => ({
        ...leg,
        range: Math.abs(leg.pivot_price - leg.origin_price),
      }))
      .filter(leg => leg.range > 0)
      .sort((a, b) => b.range - a.range)
      .slice(0, 5);
  }, [activeLegs]);

  // Top 5 most impulsive legs
  const mostImpulsiveLegs = useMemo(() => {
    return [...activeLegs]
      .filter(leg => leg.impulsiveness !== null && leg.impulsiveness > 0)
      .sort((a, b) => (b.impulsiveness ?? 0) - (a.impulsiveness ?? 0))
      .slice(0, 5);
  }, [activeLegs]);

  return (
    <div className="border-t border-app-border mt-auto">
      <button
        className="w-full p-3 hover:bg-app-card/30 transition-colors"
        onClick={onToggleCollapse}
      >
        <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          <GitBranch size={14} />
          Market Structure
        </h2>
      </button>

      {!isCollapsed && (
        <div className="px-3 pb-3 space-y-3">
          {/* Current State + Pruning Stats - compact side by side (#404 simplified) */}
          <div className="grid grid-cols-2 gap-3 text-[10px]">
            <div className="space-y-0.5">
              <div className="flex justify-between">
                <span className="text-app-muted">Active</span>
                <span className="text-app-text font-medium">{dagContext.activeLegs.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-app-muted">Engulfed</span>
                <span className="text-trading-orange font-medium">{legStats.engulfed}</span>
              </div>
            </div>
            <div className="space-y-0.5">
              <div className="flex justify-between">
                <span className="text-app-muted">Proximity</span>
                <span className="text-app-text font-medium">{legStats.proximity}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-app-muted">Heft</span>
                <span className="text-app-text font-medium">{legStats.heft}</span>
              </div>
            </div>
          </div>

          {/* Top Legs - side by side */}
          {(biggestLegs.length > 0 || mostImpulsiveLegs.length > 0) && (
            <div className="grid grid-cols-2 gap-3">
              {/* Biggest (by range) */}
              {biggestLegs.length > 0 && (
                <div>
                  <h3 className="text-[10px] font-bold text-app-muted uppercase tracking-wider mb-1 flex items-center gap-1">
                    <Maximize2 size={10} />
                    Biggest
                  </h3>
                  <div className="space-y-0.5 text-[10px]">
                    {biggestLegs.map((leg) => {
                      const isHighlighted = highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id;
                      return (
                        <div
                          key={leg.leg_id}
                          className={`flex items-center justify-between px-1 py-0.5 rounded cursor-pointer transition-colors ${
                            isHighlighted ? 'bg-trading-blue/30 ring-1 ring-trading-blue' : 'hover:bg-app-card/50'
                          }`}
                          onMouseEnter={() => onHoverLeg?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                          onMouseLeave={() => onHoverLeg?.(null)}
                        >
                          <span className={`${leg.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}`}>
                            {leg.direction.charAt(0).toUpperCase()}
                          </span>
                          <span className="text-app-muted font-mono">
                            {leg.range.toFixed(2)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Most Impulsive */}
              {mostImpulsiveLegs.length > 0 && (
                <div>
                  <h3 className="text-[10px] font-bold text-app-muted uppercase tracking-wider mb-1 flex items-center gap-1">
                    <Zap size={10} />
                    Impulsive
                  </h3>
                  <div className="space-y-0.5 text-[10px]">
                    {mostImpulsiveLegs.map((leg) => {
                      const isHighlighted = highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id;
                      return (
                        <div
                          key={leg.leg_id}
                          className={`flex items-center justify-between px-1 py-0.5 rounded cursor-pointer transition-colors ${
                            isHighlighted ? 'bg-trading-blue/30 ring-1 ring-trading-blue' : 'hover:bg-app-card/50'
                          }`}
                          onMouseEnter={() => onHoverLeg?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                          onMouseLeave={() => onHoverLeg?.(null)}
                        >
                          <span className={`${leg.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}`}>
                            {leg.direction.charAt(0).toUpperCase()}
                          </span>
                          <span className="text-app-muted font-mono">
                            {(leg.impulsiveness ?? 0).toFixed(1)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
