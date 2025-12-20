import React from 'react';
import { DagStateResponse, DagLeg } from '../lib/api';
import { LegEvent, HighlightedDagItem } from '../types';
import { GitBranch, Circle, Target, History } from 'lucide-react';

interface DAGStatePanelProps {
  dagState: DagStateResponse | null;
  recentLegEvents: LegEvent[];
  isLoading?: boolean;
  onHoverItem?: (item: HighlightedDagItem | null) => void;
  highlightedItem?: HighlightedDagItem | null;
}

// Format price for display
const formatPrice = (value: number, decimals: number = 2): string => {
  return value.toFixed(decimals);
};

// Get color class based on direction
const getDirectionColor = (direction: 'bull' | 'bear'): string => {
  return direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
};

// Get background color class based on direction
const getDirectionBg = (direction: 'bull' | 'bear'): string => {
  return direction === 'bull' ? 'bg-trading-bull/10' : 'bg-trading-bear/10';
};

// Get status badge style
const getStatusStyle = (status: string): string => {
  switch (status) {
    case 'active':
      return 'bg-trading-blue/20 text-trading-blue border-trading-blue/30';
    case 'stale':
      return 'bg-trading-orange/20 text-trading-orange border-trading-orange/30';
    case 'invalidated':
      return 'bg-trading-bear/20 text-trading-bear border-trading-bear/30';
    default:
      return 'bg-app-card text-app-muted border-app-border';
  }
};

// Leg item component
interface LegItemProps {
  leg: DagLeg;
  isHighlighted?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

const LegItem: React.FC<LegItemProps> = ({ leg, isHighlighted, onMouseEnter, onMouseLeave }) => (
  <div
    className={`text-xs p-2 rounded border transition-all duration-150 cursor-pointer ${
      isHighlighted
        ? 'border-trading-blue ring-2 ring-trading-blue/50 scale-[1.02]'
        : 'border-app-border/50 hover:border-app-border'
    } ${getDirectionBg(leg.direction)}`}
    onMouseEnter={onMouseEnter}
    onMouseLeave={onMouseLeave}
  >
    <div className="flex items-center justify-between mb-1">
      <span className={`font-medium ${getDirectionColor(leg.direction)}`}>
        {leg.direction.toUpperCase()}
      </span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getStatusStyle(leg.status)}`}>
        {leg.status}
      </span>
    </div>
    <div className="grid grid-cols-2 gap-1 text-app-muted">
      <div>
        <span className="text-[10px] uppercase">Pivot:</span>{' '}
        <span className="font-mono">{formatPrice(leg.pivot_price)}</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Origin:</span>{' '}
        <span className="font-mono">{formatPrice(leg.origin_price)}</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Retr:</span>{' '}
        <span className="font-mono">{(leg.retracement_pct * 100).toFixed(1)}%</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Bars:</span>{' '}
        <span className="font-mono">{leg.bar_count}</span>
      </div>
    </div>
  </div>
);

// Event type badge
const EventTypeBadge: React.FC<{ type: LegEvent['type'] }> = ({ type }) => {
  let style = '';
  let label = '';

  switch (type) {
    case 'LEG_CREATED':
      style = 'bg-trading-blue/20 text-trading-blue';
      label = 'CREATED';
      break;
    case 'LEG_PRUNED':
      style = 'bg-trading-orange/20 text-trading-orange';
      label = 'PRUNED';
      break;
    case 'LEG_INVALIDATED':
      style = 'bg-trading-bear/20 text-trading-bear';
      label = 'INVALID';
      break;
  }

  return (
    <span className={`text-[9px] px-1 py-0.5 rounded ${style}`}>
      {label}
    </span>
  );
};

export const DAGStatePanel: React.FC<DAGStatePanelProps> = ({
  dagState,
  recentLegEvents,
  isLoading = false,
  onHoverItem,
  highlightedItem,
}) => {
  if (isLoading) {
    return (
      <div className="h-full bg-app-secondary border-t border-app-border flex items-center justify-center">
        <div className="text-app-muted text-sm">Loading DAG state...</div>
      </div>
    );
  }

  if (!dagState) {
    return (
      <div className="h-full bg-app-secondary border-t border-app-border flex items-center justify-center">
        <div className="text-app-muted text-sm">No DAG state available</div>
      </div>
    );
  }

  const { active_legs, orphaned_origins, pending_pivots, leg_counts } = dagState;

  return (
    <div className="h-full bg-app-secondary border-t border-app-border flex flex-col font-sans text-sm">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-app-border bg-app-bg/40">
        <div className="flex items-center gap-2 text-app-text font-semibold tracking-wider uppercase">
          <GitBranch size={16} className="text-trading-purple" />
          <span>DAG Internal State</span>
        </div>
        <div className="h-4 w-px bg-app-border mx-2"></div>
        <div className="flex gap-3 text-xs">
          <span className="text-trading-bull">
            Bull: <span className="font-mono">{leg_counts.bull}</span>
          </span>
          <span className="text-trading-bear">
            Bear: <span className="font-mono">{leg_counts.bear}</span>
          </span>
        </div>
      </div>

      {/* Content Grid */}
      <div className="flex-1 grid grid-cols-4 divide-x divide-app-border/50 overflow-hidden">
        {/* Column 1: Active Legs */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <Circle size={12} className="text-trading-blue" />
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider">
              Active Legs
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {active_legs.length === 0 ? (
              <div className="text-xs text-app-muted italic">No active legs</div>
            ) : (
              active_legs.slice(0, 6).map((leg) => (
                <LegItem
                  key={leg.leg_id}
                  leg={leg}
                  isHighlighted={highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id}
                  onMouseEnter={() => onHoverItem?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                  onMouseLeave={() => onHoverItem?.(null)}
                />
              ))
            )}
            {active_legs.length > 6 && (
              <div className="text-xs text-app-muted text-center">
                +{active_legs.length - 6} more
              </div>
            )}
          </div>
        </div>

        {/* Column 2: Orphaned Origins */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <Target size={12} className="text-trading-orange" />
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider">
              Orphaned Origins
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {/* Bull Origins */}
            <div>
              <span className="text-[10px] text-trading-bull uppercase block mb-1">Bull</span>
              {orphaned_origins.bull.length === 0 ? (
                <span className="text-xs text-app-muted italic">None</span>
              ) : (
                <div className="space-y-1">
                  {orphaned_origins.bull.slice(0, 4).map((origin, idx) => {
                    const originId = `bull-${idx}`;
                    const isHighlighted = highlightedItem?.type === 'orphaned_origin' && highlightedItem.id === originId;
                    return (
                      <div
                        key={idx}
                        className={`text-xs bg-trading-bull/10 rounded px-2 py-1 flex justify-between cursor-pointer transition-all duration-150 ${
                          isHighlighted ? 'ring-2 ring-trading-bull/50 scale-[1.02]' : 'hover:bg-trading-bull/20'
                        }`}
                        onMouseEnter={() => onHoverItem?.({ type: 'orphaned_origin', id: originId, direction: 'bull' })}
                        onMouseLeave={() => onHoverItem?.(null)}
                      >
                        <span className="font-mono">{formatPrice(origin.price)}</span>
                        <span className="text-app-muted">@{origin.bar_index}</span>
                      </div>
                    );
                  })}
                  {orphaned_origins.bull.length > 4 && (
                    <div className="text-[10px] text-app-muted">+{orphaned_origins.bull.length - 4} more</div>
                  )}
                </div>
              )}
            </div>
            {/* Bear Origins */}
            <div>
              <span className="text-[10px] text-trading-bear uppercase block mb-1">Bear</span>
              {orphaned_origins.bear.length === 0 ? (
                <span className="text-xs text-app-muted italic">None</span>
              ) : (
                <div className="space-y-1">
                  {orphaned_origins.bear.slice(0, 4).map((origin, idx) => {
                    const originId = `bear-${idx}`;
                    const isHighlighted = highlightedItem?.type === 'orphaned_origin' && highlightedItem.id === originId;
                    return (
                      <div
                        key={idx}
                        className={`text-xs bg-trading-bear/10 rounded px-2 py-1 flex justify-between cursor-pointer transition-all duration-150 ${
                          isHighlighted ? 'ring-2 ring-trading-bear/50 scale-[1.02]' : 'hover:bg-trading-bear/20'
                        }`}
                        onMouseEnter={() => onHoverItem?.({ type: 'orphaned_origin', id: originId, direction: 'bear' })}
                        onMouseLeave={() => onHoverItem?.(null)}
                      >
                        <span className="font-mono">{formatPrice(origin.price)}</span>
                        <span className="text-app-muted">@{origin.bar_index}</span>
                      </div>
                    );
                  })}
                  {orphaned_origins.bear.length > 4 && (
                    <div className="text-[10px] text-app-muted">+{orphaned_origins.bear.length - 4} more</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Column 3: Pending Pivots */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <Target size={12} className="text-trading-purple" />
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider">
              Pending Pivots
            </span>
          </div>
          <div className="flex-1 space-y-3">
            {/* Bull Pivot */}
            <div>
              <span className="text-[10px] text-trading-bull uppercase block mb-1">Bull</span>
              {pending_pivots.bull ? (
                <div className="text-xs bg-trading-bull/10 rounded px-2 py-2 border border-trading-bull/20">
                  <div className="flex justify-between mb-1">
                    <span className="font-mono font-medium">{formatPrice(pending_pivots.bull.price)}</span>
                    <span className="text-app-muted">@{pending_pivots.bull.bar_index}</span>
                  </div>
                  <div className="text-[10px] text-app-muted">
                    Source: {pending_pivots.bull.source}
                  </div>
                </div>
              ) : (
                <span className="text-xs text-app-muted italic">None pending</span>
              )}
            </div>
            {/* Bear Pivot */}
            <div>
              <span className="text-[10px] text-trading-bear uppercase block mb-1">Bear</span>
              {pending_pivots.bear ? (
                <div className="text-xs bg-trading-bear/10 rounded px-2 py-2 border border-trading-bear/20">
                  <div className="flex justify-between mb-1">
                    <span className="font-mono font-medium">{formatPrice(pending_pivots.bear.price)}</span>
                    <span className="text-app-muted">@{pending_pivots.bear.bar_index}</span>
                  </div>
                  <div className="text-[10px] text-app-muted">
                    Source: {pending_pivots.bear.source}
                  </div>
                </div>
              ) : (
                <span className="text-xs text-app-muted italic">None pending</span>
              )}
            </div>
          </div>
        </div>

        {/* Column 4: Recent Events Log */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <History size={12} className="text-app-muted" />
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider">
              Recent Events
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-1 pr-1">
            {recentLegEvents.length === 0 ? (
              <div className="text-xs text-app-muted italic">No recent events</div>
            ) : (
              recentLegEvents.slice(0, 10).map((event, idx) => (
                <div
                  key={`${event.leg_id}-${idx}`}
                  className="text-xs p-1.5 rounded bg-app-card/30 border border-app-border/30"
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    <EventTypeBadge type={event.type} />
                    <span className={`text-[10px] ${getDirectionColor(event.direction)}`}>
                      {event.direction.toUpperCase()}
                    </span>
                    <span className="text-[10px] text-app-muted ml-auto">@{event.bar_index}</span>
                  </div>
                  {event.reason && (
                    <div className="text-[10px] text-app-muted truncate" title={event.reason}>
                      {event.reason}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
